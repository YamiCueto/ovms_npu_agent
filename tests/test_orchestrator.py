import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.core.tool_registry import ToolRegistry
from agent.core.telemetry import Telemetry
from agent.core.orchestrator import Orchestrator


def _make_chat_response(content: str | None = "Listo.", tool_calls: list | None = None, finish_reason: str = "stop") -> dict:
    message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10},
    }


def _tool_call(name: str, args: dict, call_id: str = "c1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


class _FakeTelemetry:
    def __init__(self):
        self.records = []
    def record(self, trace):
        self.records.append(trace)


def _make_orchestrator(chat_side_effect):
    client = MagicMock()
    client.model = "test-model"
    client.chat = MagicMock(side_effect=chat_side_effect)
    registry = ToolRegistry()
    telemetry = _FakeTelemetry()
    with patch("agent.core.orchestrator.DEVICE", "NPU"):
        orch = Orchestrator(client, registry, telemetry)
    return orch, client, registry, telemetry


class OrchestratorDirectAnswerTest(unittest.TestCase):
    def test_direct_answer(self):
        orch, client, _, tel = _make_orchestrator([_make_chat_response("La respuesta es 42.")])
        history = [{"role": "system", "content": "sys"}]
        new_hist, answer = orch.run_turn(history, "Dime algo.")
        self.assertEqual(answer, "La respuesta es 42.")
        self.assertEqual(len(tel.records), 1)
        self.assertTrue(tel.records[0].success)

    def test_tool_call_then_answer(self):
        calls = [
            _make_chat_response(tool_calls=[_tool_call("multiplicar", {"a": 5, "b": 6})], content=None, finish_reason="tool_calls"),
            _make_chat_response("El resultado es 30."),
        ]
        orch, client, _, tel = _make_orchestrator(calls)
        history = [{"role": "system", "content": "sys"}]
        _, answer = orch.run_turn(history, "Cuanto es 5 por 6?")
        self.assertIn("30", answer)
        self.assertEqual(client.chat.call_count, 2)

    def test_empty_content_warns(self):
        orch, _, _, _ = _make_orchestrator([_make_chat_response(content="")])
        history = [{"role": "system", "content": "sys"}]
        _, answer = orch.run_turn(history, "Pregunta.")
        self.assertEqual(answer, "")

    def test_max_hops_reached(self):
        infinite_tool_call = _make_chat_response(
            tool_calls=[_tool_call("multiplicar", {"a": 1, "b": 1})],
            content=None,
            finish_reason="tool_calls",
        )
        with patch("agent.core.orchestrator.MAX_HOPS", 3):
            orch, client, _, tel = _make_orchestrator([infinite_tool_call] * 10)
            _, answer = orch.run_turn([{"role": "system", "content": "sys"}], "test")
        self.assertIn("saltos", answer.lower())
        self.assertFalse(tel.records[0].success)
        self.assertEqual(tel.records[0].error, "max_hops")

    def test_unknown_tool_returns_error_in_message(self):
        calls = [
            _make_chat_response(tool_calls=[_tool_call("herramienta_inexistente", {})], content=None, finish_reason="tool_calls"),
            _make_chat_response("No pude ejecutar la herramienta."),
        ]
        orch, _, _, _ = _make_orchestrator(calls)
        _, answer = orch.run_turn([{"role": "system", "content": "sys"}], "Usa herramienta_inexistente.")
        self.assertIsNotNone(answer)

    def test_client_error_propagates(self):
        orch, client, _, tel = _make_orchestrator(RuntimeError("Conexion rechazada"))
        with self.assertRaises(RuntimeError):
            orch.run_turn([{"role": "system", "content": "sys"}], "test")
        self.assertEqual(len(tel.records), 1)
        self.assertIn("Conexion", tel.records[0].error)

    def test_reasoning_content_not_in_answer(self):
        response = _make_chat_response("Respuesta final.")
        response["choices"][0]["message"]["reasoning_content"] = "Pensamiento interno largo..."
        orch, _, _, _ = _make_orchestrator([response])
        _, answer = orch.run_turn([{"role": "system", "content": "sys"}], "Pregunta.")
        self.assertEqual(answer, "Respuesta final.")
        self.assertNotIn("Pensamiento", answer)

    def test_telemetry_records_tokens(self):
        orch, _, _, tel = _make_orchestrator([_make_chat_response("Ok.")])
        orch.run_turn([{"role": "system", "content": "sys"}], "test")
        trace = tel.records[0]
        self.assertEqual(trace.total_prompt_tokens(), 20)
        self.assertEqual(trace.total_completion_tokens(), 10)


if __name__ == "__main__":
    unittest.main()
