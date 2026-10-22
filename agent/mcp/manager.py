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
        result = client.call_tool(original_name, args)
        if isinstance(result, str):
            return {"resultado": result}
        return result
    return handler


class MCPManager:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._clients: dict[str, MCPClient] = {}

    def connect(self, server_id: str, command: list[str]) -> list[dict]:
        client = MCPClient(command)
        client.start()
        self._clients[server_id] = client
        tools = client.list_tools()
        for tool in tools:
            schema = _mcp_to_agent_schema(tool)
            self.registry.register(schema, _make_handler(client, tool["name"]))
        return tools

    def disconnect(self, server_id: str) -> None:
        if server_id in self._clients:
            self._clients[server_id].stop()
            del self._clients[server_id]

    def disconnect_all(self) -> None:
        for client in list(self._clients.values()):
            try:
                client.stop()
            except Exception:
                pass
        self._clients.clear()
