import json
import subprocess
import threading
import queue
import time
from typing import Any


class MCPError(Exception):
    pass


class MCPClient:
    """Cliente MCP minimo sobre stdio con framing JSON-RPC 2.0 (newline-delimited JSON)."""

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
            stderr=subprocess.DEVNULL,
        )
        self._responses = queue.Queue()
        proc = self._proc
        def reader():
            try:
                while True:
                    line = proc.stdout.readline(4 * 1024 * 1024)
                    if not line:
                        raise MCPError("Servidor MCP cerro la conexion")
                    self._responses.put(json.loads(line))
            except Exception as exc:
                self._responses.put(exc)
        self._reader = threading.Thread(target=reader, daemon=True)
        self._reader.start()
        try:
            self._initialize()
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        if self._proc is None:
            return
        proc, self._proc = self._proc, None
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        self._reader.join(timeout=2)
        for stream in (proc.stdin, proc.stdout):
            if stream:
                stream.close()

    def _write_frame(self, message: dict) -> None:
        if self._proc is None:
            raise MCPError("Servidor desconectado")
        self._proc.stdin.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        self._proc.stdin.flush()

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        with self._lock:
            msg: dict = {"jsonrpc": "2.0", "method": method, "id": self._next_id}
            self._next_id += 1
            if params is not None:
                msg["params"] = params
            self._write_frame(msg)
            deadline = time.monotonic() + self.timeout
            while True:
                if time.monotonic() >= deadline:
                    self.stop()
                    raise MCPError(f"Timeout MCP: {method}")
                try:
                    response = self._responses.get(timeout=max(0, deadline - time.monotonic()))
                except queue.Empty:
                    self.stop()
                    raise MCPError(f"Timeout MCP: {method}")
                if isinstance(response, Exception):
                    raise MCPError(str(response))
                if response.get("id") == msg["id"] and "method" not in response:
                    return response
                if "id" in response and "method" in response:
                    self._write_frame({"jsonrpc": "2.0", "id": response["id"], "error": {"code": -32601, "message": "Client capability unsupported"}})

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
        result = resp.get("result", {})
        tools = result.get("tools", [])
        seen = set()
        while result.get("nextCursor"):
            cursor = result["nextCursor"]
            if cursor in seen:
                raise MCPError("Cursor MCP repetido")
            seen.add(cursor)
            resp = self._rpc("tools/list", {"cursor": cursor})
            if "error" in resp:
                raise MCPError(str(resp["error"]))
            result = resp.get("result", {})
            tools.extend(result.get("tools", []))
        return tools

    def call_tool(self, name: str, arguments: dict) -> Any:
        resp = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if "error" in resp:
            raise MCPError(f"Error en herramienta MCP '{name}': {resp['error']}")
        result = resp.get("result", {})
        if result.get("isError"):
            raise MCPError(json.dumps(result.get("content", []), ensure_ascii=False))
        content = result.get("content", [])
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts) if texts else result
        return result
