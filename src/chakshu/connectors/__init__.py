"""Read-only lookups reviewers can use beyond the code, such as Jira issues.

Each connector kind turns an admin's settings into an in-process MCP server
for one review. Tools run inside the worker with the stored credentials; the
agent only sees what a tool returns, fenced as untrusted text.

Adding a kind: write a module with `build()` and `check()` and register it in KINDS.
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
class Toolset:
    server_name: str
    server: Any  # McpSdkServerConfig
    tool_names: list[str]  # full names, mcp__<server>__<tool>
    prompt_hint: str


@dataclass(frozen=True)
class Kind:
    label: str
    build: Callable[[ConnectorConfig, str], Toolset]  # (config, PR text) -> tools for one review
    check: Callable[[ConnectorConfig], Awaitable[str]]  # verify settings; returns a short description


def _registry() -> dict[str, Kind]:
    from chakshu.connectors import jira

    return {"jira": jira.KIND}


KINDS = _registry()
