import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.core.tool_registry import ToolRegistry


def _reg():
    return ToolRegistry()


class OriginalToolsTest(unittest.TestCase):
    """Los cinco tests originales, conservados intactos."""

    def test_multiplication(self):
        self.assertEqual(_reg().execute("multiplicar", '{"a":875,"b":43}'), {"resultado": 37625})

    def test_rejects_unknown_tool(self):
        self.assertIn("error", _reg().execute("ejecutar_comando", "{}"))

    def test_rejects_path_traversal(self):
        self.assertIn("error", _reg().execute("leer_archivo", '{"nombre":"../../secreto.txt"}'))

    def test_lists_demo_file(self):
        self.assertIn("finanzas_demo.md", _reg().execute("listar_archivos", "{}")["archivos"])

    def test_reads_demo_file(self):
        result = _reg().execute("leer_archivo", '{"nombre":"finanzas_demo.md"}')
        self.assertIn("Datos de prueba", result["contenido"])


class MultiplicationExtendedTest(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(_reg().execute("multiplicar", '{"a":0,"b":999}'), {"resultado": 0})

    def test_negative(self):
        self.assertEqual(_reg().execute("multiplicar", '{"a":-3,"b":7}'), {"resultado": -21})

    def test_rejects_float(self):
        self.assertIn("error", _reg().execute("multiplicar", '{"a":1.5,"b":2}'))

    def test_rejects_string(self):
        self.assertIn("error", _reg().execute("multiplicar", '{"a":"dos","b":3}'))

    def test_rejects_overflow(self):
        self.assertIn("error", _reg().execute("multiplicar", '{"a":999999999999999,"b":2}'))

    def test_rejects_missing_param(self):
        self.assertIn("error", _reg().execute("multiplicar", '{"a":5}'))

    def test_rejects_bad_json(self):
        self.assertIn("error", _reg().execute("multiplicar", "no-json"))


class FilesystemSecurityTest(unittest.TestCase):
    def test_rejects_absolute_path(self):
        self.assertIn("error", _reg().execute("leer_archivo", '{"nombre":"/etc/passwd"}'))

    def test_rejects_null_byte(self):
        self.assertIn("error", _reg().execute("leer_archivo", '{"nombre":"fin\\x00anzas.md"}'))

    def test_rejects_nonexistent(self):
        self.assertIn("error", _reg().execute("leer_archivo", '{"nombre":"no_existe.md"}'))

    def test_rejects_wrong_extension(self):
        self.assertIn("error", _reg().execute("leer_archivo", '{"nombre":"finanzas_demo.py"}'))

    def test_rejects_empty_name(self):
        self.assertIn("error", _reg().execute("leer_archivo", '{"nombre":""}'))

    def test_rejects_too_long_name(self):
        self.assertIn("error", _reg().execute("leer_archivo", '{"nombre":"' + "a" * 300 + '"}'))

    def test_listar_rejects_args(self):
        self.assertIn("error", _reg().execute("listar_archivos", '{"extra":1}'))

    def test_listar_returns_list(self):
        result = _reg().execute("listar_archivos", "{}")
        self.assertIn("archivos", result)
        self.assertIsInstance(result["archivos"], list)


class RegistryTest(unittest.TestCase):
    def test_dynamic_registration(self):
        reg = _reg()
        schema = {
            "type": "function",
            "function": {
                "name": "doble",
                "description": "test",
                "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}},
            },
        }
        reg.register(schema, lambda args: {"resultado": args["x"] * 2})
        self.assertEqual(reg.execute("doble", '{"x":5}'), {"resultado": 10})

    def test_schemas_returns_copy(self):
        reg = _reg()
        s1 = reg.schemas()
        s1.append({"extra": True})
        self.assertEqual(len(reg.schemas()), 3)

    def test_names_contains_base_tools(self):
        names = _reg().names()
        for name in ("multiplicar", "listar_archivos", "leer_archivo"):
            self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()
