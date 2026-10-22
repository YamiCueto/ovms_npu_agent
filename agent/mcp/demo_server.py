"""
Servidor MCP de demostracion: herramientas de solo lectura sobre agent/workspace.
Se comunica por stdin/stdout con framing JSON-RPC 2.0 (newline-delimited JSON).

Uso:
    python agent/mcp/demo_server.py
"""
import json
import sys
from pathlib import Path

WORKSPACE = (Path(__file__).resolve().parents[1] / "workspace").resolve()
ALLOWED_EXTENSIONS = {".txt", ".md"}
MAX_FILE_BYTES = 8192

TOOLS_MANIFEST = [
    {
        "name": "ws_listar_archivos",
        "description": "Lista archivos .txt y .md del workspace de solo lectura.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "ws_leer_archivo",
        "description": "Lee el contenido de un archivo del workspace por nombre relativo.",
        "inputSchema": {
            "type": "object",
            "properties": {"nombre": {"type": "string"}},
            "required": ["nombre"],
            "additionalProperties": False,
        },
    },
]


def _safe_path(name: str) -> Path:
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError("Nombre invalido")
    target = (WORKSPACE / name).resolve()
    if not target.is_relative_to(WORKSPACE):
        raise ValueError("Ruta fuera del workspace")
    if target.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Extension no permitida")
    if target.is_symlink() or not target.is_file():
        raise ValueError("Archivo no accesible")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Archivo demasiado grande")
    return target


def _handle_tool(name: str, args: dict) -> list[dict]:
    if name == "ws_listar_archivos":
        files = sorted(
            str(p.relative_to(WORKSPACE)).replace("\\", "/")
            for p in WORKSPACE.rglob("*")
            if p.is_file() and not p.is_symlink()
            and p.suffix.lower() in ALLOWED_EXTENSIONS
            and p.resolve().is_relative_to(WORKSPACE)
        )
        text = "\n".join(files[:25]) or "(sin archivos)"
        return [{"type": "text", "text": text}]
    if name == "ws_leer_archivo":
        target = _safe_path(args.get("nombre", ""))
        return [{"type": "text", "text": target.read_text(encoding="utf-8")}]
    raise ValueError(f"Herramienta desconocida: {name}")


def _read_frame() -> dict | None:
    raw = sys.stdin.buffer.readline()
    return json.loads(raw) if raw else None


def _write_frame(message: dict) -> None:
    sys.stdout.buffer.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _error_response(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def main() -> None:
    initialized = False
    while True:
        msg = _read_frame()
        if msg is None:
            break

        method = msg.get("method", "")
        req_id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            _write_frame({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "npu-agent-demo", "version": "2.0"},
                },
            })
            continue

        if method == "notifications/initialized":
            initialized = True
            continue

        if method == "shutdown":
            if req_id is not None:
                _write_frame({"jsonrpc": "2.0", "id": req_id, "result": {}})
            break

        if not initialized:
            if req_id is not None:
                _write_frame(_error_response(req_id, -32002, "Servidor no inicializado"))
            continue

        if method == "tools/list":
            _write_frame({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS_MANIFEST},
            })
            continue

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            try:
                content = _handle_tool(tool_name, arguments)
                _write_frame({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": content, "isError": False},
                })
            except (ValueError, OSError, UnicodeError) as exc:
                _write_frame({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {exc}"}],
                        "isError": True,
                    },
                })
            continue

        if req_id is not None:
            _write_frame(_error_response(req_id, -32601, f"Metodo desconocido: {method}"))


if __name__ == "__main__":
    main()
