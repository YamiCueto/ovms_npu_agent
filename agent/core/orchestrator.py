import json
import time
from dataclasses import asdict
from collections.abc import Callable

from .config import MAX_HOPS, MAX_TOOL_CALLS_PER_RUN, DEVICE, InferenceMode
from .model_client import OVMSClient
from .tool_registry import ToolRegistry
from .telemetry import Telemetry, RunTrace, HopTrace
from .execution_lock import model_lock

NO_THINK_PREFIX = "/no_think\n"

_COMPLEX_KEYWORDS = frozenset([
    "lee ", "leer ", "lee\n", "analiz", "resum", "explica", "describe",
    "document", "compara", "detalla",
])


def _is_simple_query(text: str) -> bool:
    lower = text.lower()
    return not any(kw in lower for kw in _COMPLEX_KEYWORDS)


def _apply_mode(text: str, mode: InferenceMode) -> str:
    if mode == InferenceMode.RAPIDO:
        return NO_THINK_PREFIX + text
    if mode == InferenceMode.AUTOMATICO:
        return (NO_THINK_PREFIX + text) if _is_simple_query(text) else text
    return text


class Orchestrator:
    def __init__(
        self,
        client: OVMSClient,
        registry: ToolRegistry,
        telemetry: Telemetry,
        mode: InferenceMode = InferenceMode.NORMAL,
    ):
        self.client = client
        self.registry = registry
        self.telemetry = telemetry
        self.mode = mode

    def run_turn(self, history: list[dict], user_text: str, on_event: Callable | None = None,
                 run_id: str | None = None) -> tuple[list[dict], str]:
        acquired = False
        try:
            with model_lock(self.client):
                acquired = True
                return self._run_turn(history, user_text, on_event, run_id)
        except Exception as exc:
            if not acquired:
                trace = RunTrace(model=self.client.model, device=DEVICE, mode=self.mode.value,
                                 user_query=user_text[:200], error=str(exc))
                if run_id:
                    trace.run_id = run_id
                self.last_trace = trace
                self.telemetry.record(trace)
                if on_event:
                    on_event({'type':'run_started', 'run_id':trace.run_id, 'elapsed_s':0, 'mode':self.mode.value})
                    on_event({'type':'run_failed', 'run_id':trace.run_id, 'elapsed_s':0, 'trace':trace.to_dict()})
            raise

    def _run_turn(self, history, user_text, on_event=None, run_id=None):
        messages = history + [{"role": "user", "content": _apply_mode(user_text, self.mode)}]
        started = time.perf_counter()
        trace = RunTrace(model=self.client.model, device=DEVICE, mode=self.mode.value, user_query=user_text[:200])
        if run_id:
            trace.run_id = run_id
        self.last_trace = trace
        def emit(kind, **data):
            if on_event:
                on_event({"type": kind, "run_id": trace.run_id, "elapsed_s": time.perf_counter() - started, **data})
        def finish(answer, error=""):
            trace.final_answer, trace.error, trace.success = answer, error, not bool(error)
            trace.total_latency_s = time.perf_counter() - started
            self.telemetry.record(trace)
            emit("run_failed" if error else "run_completed", trace=trace.to_dict())
            return messages, answer
        emit("run_started", mode=self.mode.value, query=user_text)
        tool_count = 0
        try:
            for hop in range(1, MAX_HOPS + 1):
                emit("hop_started", hop=hop)
                t0 = time.perf_counter()
                try:
                    result = self.client.chat(messages, tools=self.registry.schemas())
                except Exception as exc:
                    ht = HopTrace(hop, None, None, None, None, time.perf_counter() - t0, 0.0, None)
                    trace.hops.append(ht)
                    emit('hop_completed', **asdict(ht), error=str(exc))
                    raise
                latency = time.perf_counter() - t0
                choice = result["choices"][0]
                message, usage = choice["message"], result.get("usage") or {}
                reason = choice.get("finish_reason")
                ht = HopTrace(hop, None, None, usage.get("prompt_tokens"), usage.get("completion_tokens"), latency, 0.0, reason)
                trace.hops.append(ht)
                calls = message.get("tool_calls") or []
                emit("hop_completed", **asdict(ht), tool_calls=calls)
                # A truncated tool call must never execute. Preserve the prior valid history.
                if reason == "length":
                    return finish(message.get("content") or "", "length: respuesta truncada por limite de tokens")
                assistant = {"role": "assistant", "content": message.get("content") or ""}
                if calls:
                    assistant["tool_calls"] = calls
                messages.append(assistant)
                if not calls:
                    answer = assistant["content"]
                    return finish(answer, "empty_response" if not answer.strip() else "")
                ids = [c.get("id") for c in calls]
                if any(not i for i in ids) or len(set(ids)) != len(ids):
                    raise ValueError("tool_call_id ausente o duplicado")
                for call in calls:
                    function = call.get("function") or {}
                    name, args = function.get("name", ""), function.get("arguments", "{}")
                    tool_count += 1
                    emit("tool_started", hop=hop, tool_call_id=call["id"], name=name, arguments=args)
                    t0 = time.perf_counter()
                    try:
                        output = self.registry.execute(name, args) if tool_count <= MAX_TOOL_CALLS_PER_RUN else {"error": "max_tool_calls"}
                    except Exception as exc:
                        output = {"error": str(exc)}
                    duration = time.perf_counter() - t0
                    tool = {"tool_call_id": call["id"], "name": name, "arguments": args, "result": output,
                            "latency_s": duration, "error": output.get("error") if isinstance(output, dict) else None}
                    ht.tools.append(tool)
                    ht.tool_latency_s += duration
                    ht.tool_name, ht.tool_result_preview = name, json.dumps(output, ensure_ascii=False)[:300]
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(output, ensure_ascii=False)})
                    emit("tool_completed", hop=hop, **tool)
                if tool_count > MAX_TOOL_CALLS_PER_RUN:
                    return finish("Limite de herramientas alcanzado.", "max_tool_calls")
            return finish("Limite de saltos alcanzado; ejecucion detenida.", "max_hops")
        except Exception as exc:
            finish("", str(exc)[:500])
            raise
