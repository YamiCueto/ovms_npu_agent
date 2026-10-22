from collections.abc import Callable

from .client import MCPClient, MCPError
from ..core.tool_registry import ToolRegistry


def _mcp_to_agent_schema(tool: dict, prefix: str = "mcp_") -> dict:
    return {
        "type": "function",
        "function": {
            "name": f"{prefix}{tool['name']}",
            "description": tool.get("description", ""),
            "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
        },
    }


def _make_handler(client: MCPClient, original_name: str) -> Callable:
    def handler(args: dict) -> dict:
        try:
            result = client.call_tool(original_name, args)
        except MCPError as exc:
            return {'error': str(exc)}
        if isinstance(result, str):
            return {"resultado": result}
        return result
    return handler


class MCPManager:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._clients: dict[str, MCPClient] = {}
        self._tools: dict[str, list[str]] = {}

    def connect(self, server_id: str, command: list[str]) -> list[dict]:
        if server_id in self._clients:
            raise ValueError("Servidor ya conectado")
        client = MCPClient(command)
        registered = []
        try:
            client.start()
            tools = client.list_tools()
            for tool in tools:
                schema = _mcp_to_agent_schema(tool)
                self.registry.register(schema, _make_handler(client, tool["name"]))
                registered.append(schema["function"]["name"])
            self._clients[server_id] = client
            self._tools[server_id] = registered
            return tools
        except Exception:
            for name in registered:
                self.registry.unregister(name)
            client.stop()
            raise

    def disconnect(self, server_id: str) -> None:
        client = self._clients.pop(server_id, None)
        for name in self._tools.pop(server_id, []):
            self.registry.unregister(name)
        if client:
            client.stop()

    def disconnect_all(self) -> None:
        for server_id in list(self._clients):
            self.disconnect(server_id)
