"""Read-only lookups reviewers can use beyond the code, such as Jira issues.

A connector kind has two halves:
- tool definitions (name, description, input schema) that travel to wherever
  the review runs, so the agent can call them, and
- `call`, which runs on the Chakshu server with the stored credentials. The
  agent only ever sees the text a call returns, fenced as untrusted.

Adding a kind: write a module with a `Kind` and register it in KINDS.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConnectorConfig:
    name: str
    kind: str
    base_url: str
    username: str | None
    secret: str | None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema for the arguments


class ToolError(Exception):
    """A tool call that failed in a way the agent should read about (bad key, not found)."""


@dataclass(frozen=True)
class Kind:
    label: str
    tools: tuple[ToolSpec, ...]
    # (config, tool name, arguments) -> text for the agent. Raises ToolError.
    call: Callable[[ConnectorConfig, str, dict[str, Any]], Awaitable[str]]
    # (connector name, PR title/branch/body) -> a line for the prompt
    hint: Callable[[str, str], str]
    # verify settings; returns a short description
    check: Callable[[ConnectorConfig], Awaitable[str]]


@dataclass(frozen=True)
class ConnectorTools:
    """What one review is told about one connector. Sent to the runner as JSON."""

    connector: str
    tools: list[ToolSpec]
    hint: str

    @property
    def tool_names(self) -> list[str]:
        """Full names as the agent sees them: mcp__<connector>__<tool>."""
        return [f"mcp__{self.connector}__{t.name}" for t in self.tools]


def _registry() -> dict[str, Kind]:
    from chakshu.connectors import jira

    return {"jira": jira.KIND}


KINDS = _registry()
