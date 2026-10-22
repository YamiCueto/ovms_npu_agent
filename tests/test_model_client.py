import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from io import BytesIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.core.model_client import OVMSClient


def _make_response(data: dict) -> MagicMock:
    body = json.dumps(data).encode("utf-8")
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read = MagicMock(return_value=body)
    mock.readline = MagicMock(return_value=b"")
    # Make json.load work
    mock.__iter__ = MagicMock(return_value=iter([]))

    class _FakeResponse:
        def __init__(self):
            self._data = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return self._data if n < 0 else self._data[:n]

    return _FakeResponse()


_MINIMAL_RESPONSE = {
    "choices": [
        {
            "message": {"role": "assistant", "content": "Hola", "tool_calls": None},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


class TestOVMSClient(unittest.TestCase):
    def _client(self):
        return OVMSClient(base_url="http://localhost:8000/v1", model="test-model", timeout=5)

    @patch("agent.core.model_client.urlopen")
    def test_successful_response(self, mock_urlopen):
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        import io
        body = json.dumps(_MINIMAL_RESPONSE).encode("utf-8")
        mock_urlopen.return_value = io.BytesIO(body)
        # Patch json.load to work with BytesIO
        with patch("agent.core.model_client.json") as mock_json:
            mock_json.dumps = json.dumps
            mock_json.load = MagicMock(return_value=_MINIMAL_RESPONSE)

            class FakeCtx:
                def __enter__(self): return self
                def __exit__(self, *a): return False

            mock_urlopen.return_value = FakeCtx()
            mock_json.load.return_value = _MINIMAL_RESPONSE

            result = self._client().chat([{"role": "user", "content": "hola"}])
            self.assertIn("choices", result)

    @patch("agent.core.model_client.urlopen")
    def test_http_error_raises_runtime(self, mock_urlopen):
        err = HTTPError(url="http://x", code=500, msg="err", hdrs={}, fp=BytesIO(b"internal"))
        mock_urlopen.side_effect = err
        with self.assertRaises(RuntimeError) as ctx:
            self._client().chat([{"role": "user", "content": "x"}])
        self.assertIn("500", str(ctx.exception))

    @patch("agent.core.model_client.urlopen")
    def test_url_error_raises_runtime(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("conexion rechazada")
        with self.assertRaises(RuntimeError) as ctx:
            self._client().chat([{"role": "user", "content": "x"}])
        self.assertIn("OVMS", str(ctx.exception))

    @patch("agent.core.model_client.urlopen")
    def test_empty_choices_raises_runtime(self, mock_urlopen):
        import io
        with patch("agent.core.model_client.json") as mock_json:
            mock_json.dumps = json.dumps
            mock_json.load = MagicMock(return_value={"choices": []})

            class FakeCtx:
                def __enter__(self): return self
                def __exit__(self, *a): return False

            mock_urlopen.return_value = FakeCtx()
            with self.assertRaises(RuntimeError) as ctx:
                self._client().chat([{"role": "user", "content": "x"}])
            self.assertIn("choices", str(ctx.exception))

    def test_payload_includes_tools_when_provided(self):
        captured = []

        def fake_urlopen(req, timeout=None):
            body = req.data
            captured.append(json.loads(body.decode("utf-8")))

            class FakeCtx:
                def __enter__(self): return self
                def __exit__(self, *a): return False
                pass

            import io
            class Ctx:
                def __enter__(self): return io.BytesIO(json.dumps(_MINIMAL_RESPONSE).encode())
                def __exit__(self, *a): return False

            return Ctx()

        with patch("agent.core.model_client.urlopen", fake_urlopen):
            tools = [{"type": "function", "function": {"name": "test"}}]
            self._client().chat([{"role": "user", "content": "x"}], tools=tools)

        self.assertIn("tools", captured[0])
        self.assertEqual(captured[0]["tool_choice"], "auto")

    def test_payload_no_tools_key_when_none(self):
        captured = []

        class Ctx:
            def __enter__(self):
                import io
                return io.BytesIO(json.dumps(_MINIMAL_RESPONSE).encode())
            def __exit__(self, *a): return False

        def fake_urlopen(req, timeout=None):
            captured.append(json.loads(req.data.decode("utf-8")))
            return Ctx()

        with patch("agent.core.model_client.urlopen", fake_urlopen):
            self._client().chat([{"role": "user", "content": "x"}], tools=None)

        self.assertNotIn("tools", captured[0])


if __name__ == "__main__":
    unittest.main()
