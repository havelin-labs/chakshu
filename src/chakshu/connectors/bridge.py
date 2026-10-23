"""Hand connector tools to the agent as in-process MCP servers.

The servers hold no credentials: each call is forwarded to `call`, which runs
it on the Chakshu server (see services/connectors.py).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from chakshu.connectors import ConnectorTools, ToolError

# (connector, tool, arguments) -> text for the agent. Raises ToolError.
Caller = Callable[[str, str, dict[str, Any]], Awaitable[str]]


@dataclass(frozen=True)
class Toolset:
    server_name: str
    server: Any  # McpSdkServerConfig
    tool_names: list[str]  # full names, mcp__<server>__<tool>
    prompt_hint: str


def _text(text: str, *, error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": error}


def forward(connector: str, tool_name: str, call: Caller):
    """An MCP tool handler that runs the call elsewhere and turns ToolError into an error result."""

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            return _text(await call(connector, tool_name, args))
        except ToolError as exc:
            return _text(str(exc), error=True)

    return handler


def toolset(spec: ConnectorTools, call: Caller) -> Toolset:
    tools = [
        tool(t.name, t.description, t.input_schema)(forward(spec.connector, t.name, call)) for t in spec.tools
    ]
    return Toolset(
        server_name=spec.connector,
        server=create_sdk_mcp_server(name=spec.connector, version="1.0.0", tools=tools),
        tool_names=spec.tool_names,
        prompt_hint=spec.hint,
    )
