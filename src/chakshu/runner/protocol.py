"""What the Chakshu server and a GitHub Actions runner send each other.

    POST /api/runner/runs/{id}/job                      -> Job
    POST /api/runner/runs/{id}/tools/{connector}/{tool} ToolCall -> ToolReply
    POST /api/runner/runs/{id}/result                   Result
    POST /api/runner/runs/{id}/failure                  Failure

Every request carries the Actions OIDC token as a bearer token.
"""

import uuid
from typing import Any

from pydantic import BaseModel, Field

from chakshu.connectors import ConnectorTools

API_PREFIX = "/api/runner/runs"


class Job(BaseModel):
    run_id: uuid.UUID
    repo: str
    pr_number: int
    head_sha: str
    reviewer: str
    model: str
    max_usd: float
    prompt: str
    # Files for the agent's working directory, by relative path: CLAUDE.md and .claude/skills/...
    files: dict[str, str]
    connectors: list[ConnectorTools] = Field(default_factory=list)


class ToolCall(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


class ToolReply(BaseModel):
    text: str
    is_error: bool = False


class Result(BaseModel):
    summary: str
    findings: list[dict[str, Any]] = Field(default_factory=list)
    cost_usd: float | None = None
    duration_ms: int | None = None
    turns: int | None = None


class Failure(BaseModel):
    error: str = Field(max_length=4000)
    cost_usd: float | None = None
