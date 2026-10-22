import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.core.config import InferenceMode
from agent.core.orchestrator import Orchestrator, _apply_mode, _is_simple_query, NO_THINK_PREFIX
from agent.core.tool_registry import ToolRegistry
from agent.core.telemetry import Telemetry, RunTrace


def _make_chat_response(content: str = "Ok.", tool_calls=None, finish_reason="stop"):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 31, "completion_tokens": 8},
    }


def _tool_call(name, args, call_id="c1"):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


class _FakeTelemetry:
    def __init__(self):
        self.records = []
    def record(self, trace):
        self.records.append(trace)


def _make_orch(responses, mode=InferenceMode.NORMAL):
    client = MagicMock()
    client.model = "test-model"
    client.chat = MagicMock(side_effect=responses)
    registry = ToolRegistry()
    tel = _FakeTelemetry()
    orch = Orchestrator(client, registry, tel, mode=mode)
    return orch, client, tel


class ApplyModeTest(unittest.TestCase):
    def test_normal_no_prefix(self):
        self.assertEqual(_apply_mode("Hola", InferenceMode.NORMAL), "Hola")

    def test_rapido_adds_prefix(self):
        result = _apply_mode("Cuanto es 2+2?", InferenceMode.RAPIDO)
        self.assertTrue(result.startswith(NO_THINK_PREFIX))
        self.assertIn("Cuanto es 2+2?", result)

    def test_automatico_simple_adds_prefix(self):
        result = _apply_mode("Multiplica 5 por 3", InferenceMode.AUTOMATICO)
        self.assertTrue(result.startswith(NO_THINK_PREFIX))

    def test_automatico_complex_no_prefix(self):
        result = _apply_mode("Lee el archivo finanzas_demo.md", InferenceMode.AUTOMATICO)
        self.assertFalse(result.startswith(NO_THINK_PREFIX))

    def test_automatico_analizar_no_prefix(self):
        result = _apply_mode("Analiza el documento adjunto", InferenceMode.AUTOMATICO)
        self.assertFalse(result.startswith(NO_THINK_PREFIX))

    def test_prefix_not_doubled(self):
        result = _apply_mode("Lista los archivos", InferenceMode.RAPIDO)
        self.assertEqual(result.count(NO_THINK_PREFIX), 1)


class SimpleQueryDetectionTest(unittest.TestCase):
    def test_multiplication_is_simple(self):
        self.assertTrue(_is_simple_query("Multiplica 875 por 43"))

    def test_list_files_is_simple(self):
        self.assertTrue(_is_simple_query("Lista los archivos disponibles"))

    def test_read_file_is_complex(self):
        self.assertFalse(_is_simple_query("Lee el archivo finanzas_demo.md"))

    def test_analizar_is_complex(self):
        self.assertFalse(_is_simple_query("Analiza el contenido del documento"))

    def test_resumir_is_complex(self):
        self.assertFalse(_is_simple_query("Resume el archivo de texto"))

    def test_simple_question_is_simple(self):
        self.assertTrue(_is_simple_query("Di solo la palabra hola"))


class OrchestratorModeTest(unittest.TestCase):
    def _history(self):
        return [{"role": "system", "content": "sys"}]

    def test_normal_mode_sends_original_text(self):
        orch, client, _ = _make_orch([_make_chat_response("Ok.")], InferenceMode.NORMAL)
        orch.run_turn(self._history(), "Hola mundo")
        sent_messages = client.chat.call_args[0][0]
        user_msg = next(m for m in sent_messages if m["role"] == "user")
        self.assertEqual(user_msg["content"], "Hola mundo")

    def test_rapido_mode_prepends_no_think(self):
        orch, client, _ = _make_orch([_make_chat_response("42.")], InferenceMode.RAPIDO)
        orch.run_turn(self._history(), "Cuanto es 15 + 27?")
        sent_messages = client.chat.call_args[0][0]
        user_msg = next(m for m in sent_messages if m["role"] == "user")
        self.assertTrue(user_msg["content"].startswith(NO_THINK_PREFIX))
        self.assertIn("15 + 27", user_msg["content"])

    def test_rapido_mode_tool_call_still_works(self):
        responses = [
            _make_chat_response(tool_calls=[_tool_call("multiplicar", {"a": 5, "b": 6})],
                                content=None, finish_reason="tool_calls"),
            _make_chat_response("El resultado es 30."),
        ]
        orch, client, tel = _make_orch(responses, InferenceMode.RAPIDO)
        _, answer = orch.run_turn(self._history(), "Multiplica 5 por 6")
        self.assertIn("30", answer)
        self.assertEqual(client.chat.call_count, 2)

    def test_rapido_no_think_only_on_first_user_message(self):
        responses = [
            _make_chat_response(tool_calls=[_tool_call("multiplicar", {"a": 2, "b": 3})],
                                content=None, finish_reason="tool_calls"),
            _make_chat_response("El resultado es 6."),
        ]
        orch, client, _ = _make_orch(responses, InferenceMode.RAPIDO)
        orch.run_turn(self._history(), "Multiplica 2 por 3")

        first_call_messages = client.chat.call_args_list[0][0][0]
        second_call_messages = client.chat.call_args_list[1][0][0]

        user_msgs_first = [m for m in first_call_messages if m["role"] == "user"]
        self.assertTrue(user_msgs_first[0]["content"].startswith(NO_THINK_PREFIX))

        tool_msgs_second = [m for m in second_call_messages if m["role"] == "tool"]
        for tm in tool_msgs_second:
            self.assertNotIn(NO_THINK_PREFIX, tm["content"])

    def test_automatico_simple_uses_no_think(self):
        orch, client, _ = _make_orch([_make_chat_response("30.")], InferenceMode.AUTOMATICO)
        orch.run_turn(self._history(), "Multiplica 5 por 6")
        sent = client.chat.call_args[0][0]
        user_msg = next(m for m in sent if m["role"] == "user")
        self.assertTrue(user_msg["content"].startswith(NO_THINK_PREFIX))

    def test_automatico_complex_no_no_think(self):
        orch, client, _ = _make_orch([_make_chat_response("Resumen...")], InferenceMode.AUTOMATICO)
        orch.run_turn(self._history(), "Lee el archivo finanzas_demo.md y resumelo")
        sent = client.chat.call_args[0][0]
        user_msg = next(m for m in sent if m["role"] == "user")
        self.assertFalse(user_msg["content"].startswith(NO_THINK_PREFIX))

    def test_telemetry_records_mode(self):
        orch, _, tel = _make_orch([_make_chat_response("Ok.")], InferenceMode.RAPIDO)
        orch.run_turn(self._history(), "test")
        self.assertEqual(tel.records[0].mode, "rapido")

    def test_mode_change_affects_next_run(self):
        orch, client, _ = _make_orch(
            [_make_chat_response("A"), _make_chat_response("B")],
            InferenceMode.NORMAL,
        )
        orch.run_turn(self._history(), "primera consulta")
        first = client.chat.call_args_list[0][0][0]
        user_first = next(m for m in first if m["role"] == "user")
        self.assertFalse(user_first["content"].startswith(NO_THINK_PREFIX))

        orch.mode = InferenceMode.RAPIDO
        orch.run_turn(self._history(), "segunda consulta")
        second = client.chat.call_args_list[1][0][0]
        user_second = next(m for m in second if m["role"] == "user")
        self.assertTrue(user_second["content"].startswith(NO_THINK_PREFIX))


class ModeConfigTest(unittest.TestCase):
    def test_inference_mode_values(self):
        self.assertEqual(InferenceMode.NORMAL.value, "normal")
        self.assertEqual(InferenceMode.RAPIDO.value, "rapido")
        self.assertEqual(InferenceMode.AUTOMATICO.value, "automatico")

    def test_inference_mode_from_string(self):
        self.assertEqual(InferenceMode("rapido"), InferenceMode.RAPIDO)

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            InferenceMode("turbo")


if __name__ == "__main__":
    unittest.main()
