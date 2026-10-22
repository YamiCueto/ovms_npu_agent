from pathlib import Path
from .config import WORKSPACE, ALLOWED_EXTENSIONS, MAX_FILE_BYTES

ALLOWED_TOOLS: set[str] = {"multiplicar", "listar_archivos", "leer_archivo"}


def validate_workspace_path(name: str) -> Path:
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError("Nombre de archivo invalido")
    target = (WORKSPACE / name).resolve()
    if not target.is_relative_to(WORKSPACE):
        raise ValueError("Ruta fuera del workspace")
    if target.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Extension no permitida")
    if target.is_symlink():
        raise ValueError("Enlace simbolico no permitido")
    if not target.is_file():
        raise ValueError("Archivo inexistente")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Archivo demasiado grande")
    return target


def is_tool_allowed(name: str) -> bool:
    return name in ALLOWED_TOOLS
