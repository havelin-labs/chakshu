"""Jira: let the reviewer read the issues a pull request refers to."""

import re

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

from chakshu.connectors import ConnectorConfig, Kind, Toolset
from chakshu.helpers.prompt import fence

KEY_RE = re.compile(r"\b([A-Z][A-Z0-9_]{1,9}-\d{1,7})\b")
FIELDS = "summary,description,status,issuetype,priority,labels,parent"
MAX_KEYS = 10
MAX_TEXT = 8_000
TIMEOUT = 15.0


def issue_keys(text: str) -> list[str]:
    """Issue keys mentioned in the PR, in order, without duplicates."""
    seen: dict[str, None] = {}
    for key in KEY_RE.findall(text or ""):
        seen.setdefault(key)
    return list(seen)[:MAX_KEYS]


def _client(config: ConnectorConfig) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=config.base_url.rstrip("/"),
        auth=(config.username or "", config.secret or ""),
        timeout=TIMEOUT,
        headers={"Accept": "application/json"},
    )


def format_issue(key: str, data: dict) -> str:
    fields = data.get("fields") or {}

    def name(field: str) -> str:
        return (fields.get(field) or {}).get("name") or "-"

    lines = [
        f"{key}: {fields.get('summary') or ''}",
        f"Type: {name('issuetype')} | Status: {name('status')} | Priority: {name('priority')}",
    ]
    if fields.get("labels"):
        lines.append(f"Labels: {', '.join(fields['labels'])}")
    if parent := fields.get("parent"):
        lines.append(f"Parent: {parent.get('key')} {(parent.get('fields') or {}).get('summary') or ''}")
    lines += ["", fields.get("description") or "(no description)"]
    text = "\n".join(lines)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n[truncated]"


async def fetch_issue(config: ConnectorConfig, key: str) -> str:
    async with _client(config) as client:
        resp = await client.get(f"/rest/api/2/issue/{key}", params={"fields": FIELDS})
    if resp.status_code == 404:
        return f"{key} doesn't exist or this connector can't see it."
    resp.raise_for_status()
    return format_issue(key, resp.json())


async def check(config: ConnectorConfig) -> str:
    async with _client(config) as client:
        resp = await client.get("/rest/api/2/myself")
    resp.raise_for_status()
    return f"Connected as {resp.json().get('displayName') or config.username}"


def build(config: ConnectorConfig, pr_text: str) -> Toolset:
    @tool(
        "get_issue",
        "Read a Jira issue by its key, e.g. PAY-412: summary, type, status, priority, labels, "
        "parent and description.",
        {"key": str},
    )
    async def get_issue(args: dict) -> dict:
        key = str(args.get("key", "")).strip().upper()
        if not KEY_RE.fullmatch(key):
            return {
                "content": [{"type": "text", "text": f"'{key}' isn't a Jira issue key."}],
                "is_error": True,
            }
        try:
            text = await fetch_issue(config, key)
        except httpx.HTTPError as exc:
            return {"content": [{"type": "text", "text": f"Couldn't read {key}: {exc}"}], "is_error": True}
        return {"content": [{"type": "text", "text": fence(f"jira issue {key}", text)}]}

    keys = issue_keys(pr_text)
    referenced = (
        f"The pull request refers to {', '.join(keys)}."
        if keys
        else "The pull request doesn't name an issue, so only look one up if the code or comments do."
    )
    return Toolset(
        server_name=config.name,
        server=create_sdk_mcp_server(name=config.name, version="1.0.0", tools=[get_issue]),
        tool_names=[f"mcp__{config.name}__get_issue"],
        prompt_hint=(
            f"Jira is available through the `{config.name}` get_issue tool. {referenced} "
            "Read the issue and check the change does what it asks; report gaps as findings."
        ),
    )


KIND = Kind(label="Jira", build=build, check=check)
