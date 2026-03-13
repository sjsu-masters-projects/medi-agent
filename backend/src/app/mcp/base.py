"""Base MCP server interface.

Each server exposes domain-specific tools to AI agents via get_tools() / call_tool().
"""

from abc import ABC, abstractmethod
from typing import Any


class MCPServer(ABC):
    """Base class for MCP servers."""

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description

    @abstractmethod
    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools with their JSON schemas."""

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by name with the given arguments."""
