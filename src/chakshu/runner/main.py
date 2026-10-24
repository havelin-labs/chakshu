"""`chakshu action`: do one review, or answer one reply to a review comment, inside GitHub Actions.

fetch the job -> prepare the workspace -> run the agent (logging as it goes)
-> send the result, or the reason it failed, back to Chakshu.

Workspace layout (the agent's working directory):
    code/                             the PR, checked out by the workflow
    CLAUDE.md, .claude/skills/...     the reviewer's files, from the job
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock

from chakshu.connectors import bridge
from chakshu.helpers import workspace as files
from chakshu.runner import engine
from chakshu.runner.client import OidcTokens, ServerClient, ServerError, http_client
from chakshu.runner.protocol import Failure, Job, Result, Usage

log = logging.getLogger("chakshu.action")

API_KEY_ENV = "ANTHROPIC_API_KEY"
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"


class RunnerError(RuntimeError):
    pass


def claude_access() -> dict[str, str]:
    """The Claude credential from the repository secrets. The API key wins when both are set.

    Actions sets a missing secret to "", so empty values are removed from the
    environment rather than passed on.
    """
    values = {name: os.environ.pop(name, "") for name in (API_KEY_ENV, TOKEN_ENV)}
    for name in (API_KEY_ENV, TOKEN_ENV):
        if values[name]:
            return {name: values[name]}
    raise RunnerError(
        "No Claude credential in this repository's Actions secrets. Add an API key or a subscription "
        "token in Chakshu's settings; Chakshu copies it to every repository it reviews."
    )


def prepare(workspace: Path, job: Job) -> None:
    code = workspace / "code"
    if not code.is_dir():
        raise RunnerError(f"No pull request checkout at {code}.")
    removed = files.strip_instruction_files(code) + files.remove_symlinks_leaving(code)
    if removed:
        log.info("Removed from the checkout so they can't instruct the reviewer: %s", ", ".join(removed[:20]))
    files.write_files(workspace, job.files)


def _brief(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


def observe(message: Any) -> None:
    """Print what the agent does, so the Actions log shows the review as it happens."""
    if not isinstance(message, AssistantMessage):
        return
    for block in message.content:
        if isinstance(block, ToolUseBlock):
            log.info("→ %s %s", block.name, _brief(block.input))
        elif isinstance(block, TextBlock) and block.text.strip():
            log.info("%s", _brief(block.text.strip(), 400))


def _summary_lines(job: Job, result: Result, review_url: str | None) -> list[str]:
    if job.kind == "reply":
        lines = [f"## Chakshu · {job.reviewer} · reply", "", result.summary]
        lines += ["", f"Finding: {result.outcome or 'open'}"]
        return lines + (["", f"[Open the thread]({review_url})"] if review_url else [])
    lines = [
        f"## Chakshu · {job.reviewer}",
        "",
        result.summary,
        "",
        f"{len(result.findings)} finding(s) · {job.model}"
        + (f" · ${result.cost_usd:.4f}" if result.cost_usd is not None else ""),
    ]
    if result.findings:
        lines += ["", "| Severity | Where | Finding |", "| --- | --- | --- |"]
        lines += [
            f"| {f.get('severity', '')} | `{f.get('path', '')}:{f.get('line', '')}` | "
            f"{str(f.get('title', '')).replace('|', '/')} |"
            for f in result.findings
        ]
    if review_url:
        lines += ["", f"[Open the review]({review_url})"]
    return lines


def write_step_summary(job: Job, result: Result, review_url: str | None) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as summary:
        summary.write("\n".join(_summary_lines(job, result, review_url)) + "\n")


async def _report_failure(client: ServerClient, failure: Failure) -> None:
    try:
        await client.failure(failure)
    except ServerError as exc:
        log.error("Couldn't tell Chakshu the review failed: %s", exc)


async def run(server: str, run_id: uuid.UUID, workspace: Path) -> int:
    tokens = OidcTokens.from_env(audience=server.rstrip("/"))
    async with http_client() as http:
        client = ServerClient(server, run_id, tokens, http)
        log.info("Fetching the review job from %s", server)
        try:
            job = await client.job()
        except ServerError as exc:
            log.error("Chakshu didn't hand out the job: %s", exc)
            return 1
        log.info(
            "%s %s#%s at %s with the %s reviewer (%s)",
            "Answering a reply on" if job.kind == "reply" else "Reviewing",
            job.repo,
            job.pr_number,
            job.head_sha[:7],
            job.reviewer,
            job.model,
        )
        try:
            auth_env = claude_access()
            prepare(workspace, job)
            if job.kind == "reply":
                reviewed = await engine.reply(
                    workspace,
                    job.prompt,
                    model=job.model,
                    max_usd=job.max_usd,
                    auth_env=auth_env,
                    observe=observe,
                )
            else:
                toolsets = [bridge.toolset(c, client.call_tool) for c in job.connectors]
                reviewed = await engine.review(
                    workspace,
                    job.prompt,
                    model=job.model,
                    max_usd=job.max_usd,
                    auth_env=auth_env,
                    toolsets=toolsets,
                    observe=observe,
                )
        except Exception as exc:  # noqa: BLE001 - reported to Chakshu, then the job fails
            log.error("Review failed: %s", exc)
            cost = exc.cost_usd if isinstance(exc, engine.EngineError) else None
            await _report_failure(client, Failure(error=str(exc)[:4000], cost_usd=cost))
            return 1

        result = Result(
            summary=reviewed.summary,
            findings=reviewed.findings,
            cost_usd=reviewed.cost_usd,
            duration_ms=reviewed.duration_ms,
            turns=reviewed.turns,
            outcome=reviewed.outcome,
            usage=Usage(**reviewed.usage) if reviewed.usage else None,
        )
        if job.kind == "reply":
            log.info("Done (finding %s). Sending the answer to Chakshu to post.", result.outcome)
        else:
            log.info("Done: %s finding(s). Sending them to Chakshu to post.", len(result.findings))
        try:
            review_url = await client.result(result)
        except ServerError as exc:
            log.error("Chakshu couldn't post the review: %s", exc)
            await _report_failure(
                client, Failure(error=f"Couldn't post the review: {exc}", cost_usd=result.cost_usd)
            )
            return 1
        write_step_summary(job, result, review_url)
        log.info("Posted: %s", review_url or "nothing new to post")
        return 0
