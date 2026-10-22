import json
from collections.abc import Callable

from ..tools.calculator import multiplicar
from ..tools.filesystem import listar_archivos, leer_archivo

_BASE_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "multiplicar",
            "description": "Multiplica dos numeros enteros y devuelve el resultado exacto.",
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_archivos",
            "description": "Lista archivos .txt y .md dentro del espacio de pruebas, sin modificar nada.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leer_archivo",
            "description": "Lee un archivo .txt o .md del espacio de pruebas, por nombre relativo.",
            "parameters": {
                "type": "object",
                "properties": {"nombre": {"type": "string"}},
                "required": ["nombre"],
                "additionalProperties": False,
            },
        },
    },
]

_BASE_HANDLERS: dict[str, Callable] = {
    "multiplicar": multiplicar,
    "listar_archivos": listar_archivos,
    "leer_archivo": leer_archivo,
}


class ToolRegistry:
    def __init__(self):
        self._schemas: list[dict] = list(_BASE_SCHEMAS)
        self._handlers: dict[str, Callable] = dict(_BASE_HANDLERS)

    def register(self, schema: dict, handler: Callable) -> None:
        name = schema["function"]["name"]
        self._schemas.append(schema)
        self._handlers[name] = handler

    def schemas(self) -> list[dict]:
        return list(self._schemas)

    def names(self) -> list[str]:
        return list(self._handlers)

    def execute(self, name: str, raw_arguments: str) -> dict:
        if name not in self._handlers:
            return {"error": "Herramienta no autorizada"}
        try:
            args = json.loads(raw_arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError("Argumentos deben ser un objeto JSON")
            return self._handlers[name](args)
        except (ValueError, OSError, UnicodeError, TypeError) as exc:
            return {"error": str(exc)}
