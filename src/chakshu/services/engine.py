"""Run one review with the Claude Agent SDK.

The agent gets read-only tools and nothing else: no shell, no network, no
GitHub token. It runs in the workspace folder, loads only the workspace's
project settings (the team's skills and CLAUDE.md), and its config lives in a
throwaway directory so nothing leaks between runs.
"""

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from chakshu.connectors import Toolset
from chakshu.helpers.prompt import FINDINGS_SCHEMA, SYSTEM_PROMPT

log = logging.getLogger(__name__)

TOOLS = ["Read", "Grep", "Glob", "Skill"]
MAX_TURNS = 40


class EngineError(RuntimeError):
    def __init__(self, message: str, cost_usd: float | None = None):
        super().__init__(message)
        self.cost_usd = cost_usd


@dataclass
class ReviewResult:
    summary: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float | None = None
    duration_ms: int | None = None
    turns: int | None = None


def _env(api_key: str | None, config_dir: Path) -> dict[str, str]:
    env = {"CLAUDE_CONFIG_DIR": str(config_dir), "DISABLE_TELEMETRY": "1", "DISABLE_AUTOUPDATER": "1"}
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    # Bedrock/Vertex users configure these in the container environment instead of an API key.
    for name in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "AWS_REGION", "ANTHROPIC_BASE_URL"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    return env


def options(
    workspace: Path,
    *,
    model: str,
    max_usd: float,
    api_key: str | None,
    toolsets: Sequence[Toolset] = (),
) -> ClaudeAgentOptions:
    config_dir = workspace.parent / "claude-config"
    config_dir.mkdir(exist_ok=True)
    return ClaudeAgentOptions(
        cwd=str(workspace),
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        # Connector tools are read-only lookups that run in this process, not in the agent's sandbox.
        allowed_tools=TOOLS + [name for t in toolsets for name in t.tool_names],
        permission_mode="dontAsk",
        setting_sources=["project"],
        skills="all",
        strict_mcp_config=True,
        mcp_servers={t.server_name: t.server for t in toolsets},
        model=model,
        max_turns=MAX_TURNS,
        max_budget_usd=max_usd,
        output_format={"type": "json_schema", "schema": FINDINGS_SCHEMA},
        env=_env(api_key, config_dir),
    )


async def review(
    workspace: Path,
    prompt: str,
    *,
    model: str,
    max_usd: float,
    api_key: str | None,
    toolsets: Sequence[Toolset] = (),
) -> ReviewResult:
    result: ResultMessage | None = None
    opts = options(workspace, model=model, max_usd=max_usd, api_key=api_key, toolsets=toolsets)
    try:
        async for message in query(prompt=prompt, options=opts):
            if isinstance(message, ResultMessage):
                result = message
    except Exception as exc:
        cost = result.total_cost_usd if result else None
        reason = result.subtype if result else type(exc).__name__
        raise EngineError(f"Review stopped: {reason}. {exc}", cost) from exc

    if result is None or result.subtype != "success" or not result.structured_output:
        subtype = result.subtype if result else "no result"
        raise EngineError(f"Review didn't finish ({subtype}).", result.total_cost_usd if result else None)

    output = result.structured_output
    return ReviewResult(
        summary=output.get("summary", ""),
        findings=list(output.get("findings", [])),
        cost_usd=result.total_cost_usd,
        duration_ms=result.duration_ms,
        turns=result.num_turns,
    )
