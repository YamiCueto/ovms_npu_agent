import json
import time

from .config import MAX_HOPS, DEVICE, InferenceMode
from .model_client import OVMSClient
from .tool_registry import ToolRegistry
from .telemetry import Telemetry, RunTrace, HopTrace

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

    def run_turn(self, history: list[dict], user_text: str) -> tuple[list[dict], str]:
        effective_text = _apply_mode(user_text, self.mode)
        messages = history + [{"role": "user", "content": effective_text}]
        run_started = time.perf_counter()
        trace = RunTrace(
            model=self.client.model,
            device=DEVICE,
            mode=self.mode.value,
            user_query=user_text[:200],
        )

        try:
            for hop in range(1, MAX_HOPS + 1):
                inference_start = time.perf_counter()
                result = self.client.chat(messages, tools=self.registry.schemas())
                inference_latency = time.perf_counter() - inference_start

                choice = result["choices"][0]
                message = choice["message"]
                usage = result.get("usage", {})
                finish_reason = choice.get("finish_reason")
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                print(
                    f"[salto {hop}] {inference_latency:.2f}s | "
                    f"tokens: {prompt_tokens} entrada / {completion_tokens} salida | "
                    f"fin: {finish_reason} | modo: {self.mode.value}"
                )

                calls = message.get("tool_calls") or []
                assistant_msg: dict = {"role": "assistant", "content": message.get("content") or ""}
                if calls:
                    assistant_msg["tool_calls"] = calls
                messages.append(assistant_msg)

                tool_latency = 0.0
                tool_name_used: str | None = None
                tool_result_preview: str | None = None

                if not calls:
                    answer = message.get("content") or ""
                    if not answer.strip():
                        print("[aviso] Respuesta vacia; el modelo pudo consumir los tokens en razonamiento.")

                    trace.hops.append(HopTrace(
                        hop=hop,
                        tool_name=None,
                        tool_result_preview=None,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        inference_latency_s=round(inference_latency, 3),
                        tool_latency_s=0.0,
                        finish_reason=finish_reason,
                    ))
                    trace.final_answer = answer
                    trace.success = True
                    trace.total_latency_s = time.perf_counter() - run_started
                    self.telemetry.record(trace)
                    return messages, answer

                for call in calls:
                    function = call.get("function") or {}
                    name = function.get("name", "")
                    tool_name_used = name
                    print(f"  herramienta solicitada: {name}")
                    tool_start = time.perf_counter()
                    output = self.registry.execute(name, function.get("arguments", "{}"))
                    tool_latency = time.perf_counter() - tool_start
                    tool_result_preview = json.dumps(output, ensure_ascii=False)[:300]
                    print(f"  resultado: {tool_result_preview} ({tool_latency:.3f}s)")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(output, ensure_ascii=False),
                    })

                trace.hops.append(HopTrace(
                    hop=hop,
                    tool_name=tool_name_used,
                    tool_result_preview=tool_result_preview,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    inference_latency_s=round(inference_latency, 3),
                    tool_latency_s=round(tool_latency, 3),
                    finish_reason=finish_reason,
                ))

            final = "Limite de saltos alcanzado; ejecucion detenida."
            trace.final_answer = final
            trace.success = False
            trace.error = "max_hops"
            trace.total_latency_s = time.perf_counter() - run_started
            self.telemetry.record(trace)
            return messages, final

        except Exception as exc:
            trace.error = str(exc)[:500]
            trace.total_latency_s = time.perf_counter() - run_started
            self.telemetry.record(trace)
            raise
