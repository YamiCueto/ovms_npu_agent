from ..core.config import WORKSPACE, ALLOWED_EXTENSIONS
from ..core.permissions import validate_workspace_path


def listar_archivos(args: dict) -> dict:
    if args:
        raise ValueError("listar_archivos no acepta argumentos")
    files = sorted(
        str(p.relative_to(WORKSPACE)).replace("\\", "/")
        for p in WORKSPACE.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and p.suffix.lower() in ALLOWED_EXTENSIONS
        and p.resolve().is_relative_to(WORKSPACE)
    )
    return {"archivos": files[:25], "total_mostrados": min(len(files), 25)}


def leer_archivo(args: dict) -> dict:
    nombre = args.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip() or len(nombre) > 200:
        raise ValueError("Nombre de archivo invalido")
    target = validate_workspace_path(nombre)
    return {
        "nombre": str(target.relative_to(WORKSPACE)).replace("\\", "/"),
        "contenido": target.read_text(encoding="utf-8"),
    }
