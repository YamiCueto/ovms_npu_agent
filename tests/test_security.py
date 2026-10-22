import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.core.tool_registry import ToolRegistry
from agent.core.permissions import validate_workspace_path, is_tool_allowed, ALLOWED_TOOLS
from agent.core.config import WORKSPACE


class PathTraversalTest(unittest.TestCase):
    def _exec(self, nombre):
        return ToolRegistry().execute("leer_archivo", f'{{"nombre":"{nombre}"}}')

    def test_double_dot(self):
        self.assertIn("error", self._exec("../../etc/passwd"))

    def test_absolute_unix(self):
        self.assertIn("error", self._exec("/etc/passwd"))

    def test_absolute_windows(self):
        self.assertIn("error", self._exec("C:/Windows/system32/drivers/etc/hosts"))

    def test_encoded_traversal(self):
        self.assertIn("error", self._exec("..%2F..%2Fsecret"))

    def test_url_traversal_decoded(self):
        self.assertIn("error", ToolRegistry().execute("leer_archivo", '{"nombre":"../../../secret.md"}'))

    def test_empty_string(self):
        self.assertIn("error", self._exec(""))

    def test_only_dots(self):
        self.assertIn("error", self._exec("..."))


class ExtensionFilterTest(unittest.TestCase):
    def test_py_not_allowed(self):
        self.assertIn("error", ToolRegistry().execute("leer_archivo", '{"nombre":"algo.py"}'))

    def test_exe_not_allowed(self):
        self.assertIn("error", ToolRegistry().execute("leer_archivo", '{"nombre":"algo.exe"}'))

    def test_json_not_allowed(self):
        self.assertIn("error", ToolRegistry().execute("leer_archivo", '{"nombre":"config.json"}'))


class ToolAllowlistTest(unittest.TestCase):
    def test_allowed_tools_present(self):
        for name in ("multiplicar", "listar_archivos", "leer_archivo"):
            self.assertTrue(is_tool_allowed(name))

    def test_unknown_not_allowed(self):
        self.assertFalse(is_tool_allowed("ejecutar_sistema"))
        self.assertFalse(is_tool_allowed("rm_rf"))

    def test_registry_rejects_unlisted(self):
        result = ToolRegistry().execute("borrar_todo", "{}")
        self.assertIn("error", result)


class SymlinkTest(unittest.TestCase):
    def test_symlink_rejected(self):
        import os
        target_file = WORKSPACE / "finanzas_demo.md"
        if not target_file.exists():
            self.skipTest("finanzas_demo.md no existe")
        link_path = WORKSPACE / "symlink_test.md"
        try:
            try:
                os.symlink(str(target_file), str(link_path))
            except (OSError, NotImplementedError):
                self.skipTest("No se pueden crear symlinks en este entorno")
            result = ToolRegistry().execute("leer_archivo", '{"nombre":"symlink_test.md"}')
            self.assertIn("error", result)
        finally:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink(missing_ok=True)


class ReadSizeLimitTest(unittest.TestCase):
    def test_large_file_rejected(self):
        large_file = WORKSPACE / "_test_large.md"
        try:
            large_file.write_text("x" * 9000, encoding="utf-8")
            result = ToolRegistry().execute("leer_archivo", '{"nombre":"_test_large.md"}')
            self.assertIn("error", result)
        finally:
            large_file.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
