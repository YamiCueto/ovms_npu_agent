import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.mcp.client import MCPClient, MCPError
from agent.mcp.manager import MCPManager, _mcp_to_agent_schema
from agent.core.tool_registry import ToolRegistry


class SchemaConversionTest(unittest.TestCase):
    def test_basic_conversion(self):
        tool = {
            "name": "mi_herramienta",
            "description": "Hace algo.",
            "inputSchema": {
                "type": "object",
                "properties": {"x": {"type": "string"}},
            },
        }
        schema = _mcp_to_agent_schema(tool)
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "mcp_mi_herramienta")
        self.assertEqual(schema["function"]["description"], "Hace algo.")
        self.assertEqual(schema["function"]["parameters"]["properties"]["x"]["type"], "string")

    def test_missing_description_defaults_empty(self):
        tool = {"name": "t", "inputSchema": {"type": "object", "properties": {}}}
        schema = _mcp_to_agent_schema(tool)
        self.assertEqual(schema["function"]["description"], "")

    def test_missing_input_schema_defaults(self):
        tool = {"name": "t", "description": "d"}
        schema = _mcp_to_agent_schema(tool)
        self.assertIn("type", schema["function"]["parameters"])


class MCPManagerRegistrationTest(unittest.TestCase):
    def _mock_client(self, tools: list[dict]) -> MagicMock:
        client = MagicMock(spec=MCPClient)
        client.list_tools.return_value = tools
        client.call_tool.return_value = "resultado ok"
        return client

    def test_tools_registered_in_registry(self):
        registry = ToolRegistry()
        manager = MCPManager(registry)

        tools = [
            {"name": "ws_listar", "description": "Lista.", "inputSchema": {"type": "object", "properties": {}}},
        ]
        fake_client = self._mock_client(tools)

        with patch("agent.mcp.manager.MCPClient", return_value=fake_client):
            manager.connect("demo", ["python", "demo_server.py"])

        self.assertIn("mcp_ws_listar", registry.names())

    def test_registered_handler_calls_client(self):
        registry = ToolRegistry()
        manager = MCPManager(registry)

        tools = [{"name": "ws_info", "description": "Info.", "inputSchema": {"type": "object", "properties": {}}}]
        fake_client = self._mock_client(tools)

        with patch("agent.mcp.manager.MCPClient", return_value=fake_client):
            manager.connect("demo", ["python", "x"])

        result = registry.execute("mcp_ws_info", "{}")
        self.assertNotIn("error", result)
        fake_client.call_tool.assert_called_once_with("ws_info", {})

    def test_connect_error_propagates(self):
        registry = ToolRegistry()
        manager = MCPManager(registry)

        fake_client = MagicMock(spec=MCPClient)
        fake_client.start.side_effect = MCPError("No se pudo iniciar")

        with patch("agent.mcp.manager.MCPClient", return_value=fake_client):
            with self.assertRaises(MCPError):
                manager.connect("bad", ["nonexistent_cmd"])

    def test_disconnect_all(self):
        registry = ToolRegistry()
        manager = MCPManager(registry)

        tools = [{"name": "t", "description": "", "inputSchema": {"type": "object", "properties": {}}}]
        fake_client = self._mock_client(tools)

        with patch("agent.mcp.manager.MCPClient", return_value=fake_client):
            manager.connect("s1", ["x"])

        manager.disconnect_all()
        fake_client.stop.assert_called()


class MCPClientFramingTest(unittest.TestCase):
    def _make_client(self):
        return MCPClient(["dummy"], timeout=5)

    def test_client_instantiation(self):
        client = self._make_client()
        self.assertIsNone(client._proc)

    def test_mcp_error_is_exception(self):
        with self.assertRaises(MCPError):
            raise MCPError("prueba")


if __name__ == "__main__":
    unittest.main()
