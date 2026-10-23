"""Run one review, or one answer to a reply, with the Claude Agent SDK.

The agent gets read-only tools and nothing else: no shell, no network, no
GitHub token. It runs in the workspace folder, loads only the workspace's
project settings (the team's skills and CLAUDE.md), and its config lives in a
throwaway directory so nothing leaks between runs.
"""

import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from chakshu.connectors.bridge import Toolset
from chakshu.helpers.prompt import (
    FINDINGS_SCHEMA,
    REPLY_OUTCOMES,
    REPLY_SCHEMA,
    REPLY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
)

log = logging.getLogger(__name__)

TOOLS = ["Read", "Grep", "Glob", "Skill"]
MAX_TURNS = 40
# Answering a reply is a short job: a few reads, then a paragraph.
REPLY_MAX_TURNS = 15
REPLY_MAX_USD = 0.5


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
    outcome: str | None = None  # replies: open, fixed or dismissed


def _env(auth_env: dict[str, str], config_dir: Path) -> dict[str, str]:
    env = {"CLAUDE_CONFIG_DIR": str(config_dir), "DISABLE_TELEMETRY": "1", "DISABLE_AUTOUPDATER": "1"}
    env |= auth_env  # API key or subscription token, from model_access
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
    auth_env: dict[str, str],
    toolsets: Sequence[Toolset] = (),
    system_prompt: str = SYSTEM_PROMPT,
    schema: dict[str, Any] = FINDINGS_SCHEMA,
    max_turns: int = MAX_TURNS,
) -> ClaudeAgentOptions:
    config_dir = workspace.parent / "claude-config"
    config_dir.mkdir(exist_ok=True)
    return ClaudeAgentOptions(
        cwd=str(workspace),
        system_prompt=system_prompt,
        tools=TOOLS,
        # Connector tools are read-only lookups that run in this process, not in the agent's sandbox.
        allowed_tools=TOOLS + [name for t in toolsets for name in t.tool_names],
        permission_mode="dontAsk",
        setting_sources=["project"],
        skills="all",
        strict_mcp_config=True,
        mcp_servers={t.server_name: t.server for t in toolsets},
        model=model,
        max_turns=max_turns,
        max_budget_usd=max_usd,
        output_format={"type": "json_schema", "schema": schema},
        env=_env(auth_env, config_dir),
    )


async def _run(prompt: str, opts: ClaudeAgentOptions, observe: Callable[[Any], None] | None) -> ResultMessage:
    """The agent's final message, once it returned structured output."""
    result: ResultMessage | None = None
    try:
        async for message in query(prompt=prompt, options=opts):
            if observe:
                observe(message)
            if isinstance(message, ResultMessage):
                result = message
    except Exception as exc:
        cost = result.total_cost_usd if result else None
        reason = result.subtype if result else type(exc).__name__
        raise EngineError(f"Review stopped: {reason}. {exc}", cost) from exc

    if result is None or result.subtype != "success" or not result.structured_output:
        subtype = result.subtype if result else "no result"
        raise EngineError(f"Review didn't finish ({subtype}).", result.total_cost_usd if result else None)
    return result


async def review(
    workspace: Path,
    prompt: str,
    *,
    model: str,
    max_usd: float,
    auth_env: dict[str, str],
    toolsets: Sequence[Toolset] = (),
    observe: Callable[[Any], None] | None = None,
) -> ReviewResult:
    """`observe` sees every message as it arrives, e.g. to print progress to the Actions log."""
    opts = options(workspace, model=model, max_usd=max_usd, auth_env=auth_env, toolsets=toolsets)
    result = await _run(prompt, opts, observe)
    output = result.structured_output
    return ReviewResult(
        summary=output.get("summary", ""),
        findings=list(output.get("findings", [])),
        cost_usd=result.total_cost_usd,
        duration_ms=result.duration_ms,
        turns=result.num_turns,
    )


async def reply(
    workspace: Path,
    prompt: str,
    *,
    model: str,
    max_usd: float,
    auth_env: dict[str, str],
    observe: Callable[[Any], None] | None = None,
) -> ReviewResult:
    """Answer a reply to a review comment: the answer is `summary`, plus the finding's `outcome`."""
    opts = options(
        workspace,
        model=model,
        max_usd=min(max_usd, REPLY_MAX_USD),
        auth_env=auth_env,
        system_prompt=REPLY_SYSTEM_PROMPT,
        schema=REPLY_SCHEMA,
        max_turns=REPLY_MAX_TURNS,
    )
    result = await _run(prompt, opts, observe)
    output = result.structured_output
    outcome = output.get("outcome")
    return ReviewResult(
        summary=str(output.get("reply", "")).strip(),
        cost_usd=result.total_cost_usd,
        duration_ms=result.duration_ms,
        turns=result.num_turns,
        outcome=outcome if outcome in REPLY_OUTCOMES else "open",
    )
