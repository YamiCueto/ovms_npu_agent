import json
import subprocess
import threading
from typing import Any


class MCPError(Exception):
    pass


class MCPClient:
    """Cliente MCP minimo sobre stdio con framing JSON-RPC 2.0 (Content-Length)."""

    def __init__(self, command: list[str], timeout: float = 30.0):
        self.command = command
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._next_id = 1
        self._lock = threading.Lock()

    def start(self) -> None:
        self._proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._initialize()

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self._notify("shutdown")
        except Exception:
            pass
        for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
            try:
                if stream:
                    stream.close()
            except Exception:
                pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._proc = None

    def _write_frame(self, message: dict) -> None:
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + body)
        self._proc.stdin.flush()

    def _read_frame(self) -> dict:
        headers: dict[str, str] = {}
        while True:
            raw = self._proc.stdout.readline()
            if not raw:
                raise MCPError("Servidor MCP cerro la conexion")
            line = raw.decode("utf-8").strip()
            if not line:
                break
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length", 0))
        if not length:
            raise MCPError("Content-Length ausente en respuesta MCP")
        body = self._proc.stdout.read(length)
        return json.loads(body.decode("utf-8"))

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        with self._lock:
            msg: dict = {"jsonrpc": "2.0", "method": method, "id": self._next_id}
            self._next_id += 1
            if params is not None:
                msg["params"] = params
            self._write_frame(msg)
            return self._read_frame()

    def _notify(self, method: str, params: dict | None = None) -> None:
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._write_frame(msg)

    def _initialize(self) -> None:
        resp = self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "npu-agent", "version": "2.0"},
        })
        if "error" in resp:
            raise MCPError(f"Error de inicializacion MCP: {resp['error']}")
        self._notify("notifications/initialized")

    def list_tools(self) -> list[dict]:
        resp = self._rpc("tools/list")
        if "error" in resp:
            raise MCPError(f"Error listando herramientas MCP: {resp['error']}")
        return resp.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> Any:
        resp = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if "error" in resp:
            raise MCPError(f"Error en herramienta MCP '{name}': {resp['error']}")
        result = resp.get("result", {})
        content = result.get("content", [])
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts) if texts else result
        return result
