import uuid

import pytest

from chakshu.connectors import KINDS, ConnectorTools, ToolError
from chakshu.connectors import jira as jira_kind
from chakshu.connectors.bridge import forward, toolset
from chakshu.connectors.jira import format_issue, issue_keys
from chakshu.services import connectors
from chakshu.services.github import AppCredentials

CREDS = AppCredentials(
    app_id=1, slug="x", client_id="c", client_secret="s", private_key="k", webhook_secret=None
)


def test_issue_keys_are_found_in_order_without_duplicates():
    text = "PAY-412: partial refunds\nbranch pay-999-lowercase, see PAY-412 and CORE-7. Not ABCDEFGHIJKL-1"
    assert issue_keys(text) == ["PAY-412", "CORE-7"]


def test_format_issue_is_plain_and_bounded():
    data = {
        "fields": {
            "summary": "Partial refunds",
            "issuetype": {"name": "Story"},
            "status": {"name": "In Progress"},
            "priority": None,
            "labels": ["payments"],
            "description": "x" * 10_000,
        }
    }
    text = format_issue("PAY-412", data)
    assert text.startswith("PAY-412: Partial refunds\nType: Story | Status: In Progress | Priority: -")
    assert text.endswith("[truncated]")


def test_jira_hint_lists_the_keys_in_the_pull_request():
    assert "PAY-412" in KINDS["jira"].hint("jira", "PAY-412 partial refunds")
    assert "doesn't name an issue" in KINDS["jira"].hint("jira", "no keys here")


async def test_jira_call_rejects_bad_keys_and_unknown_tools():
    config = connectors.ConnectorConfig("jira", "jira", "https://x", "u", "s")
    with pytest.raises(ToolError, match="isn't a Jira issue key"):
        await jira_kind.call(config, "get_issue", {"key": "not a key"})
    with pytest.raises(ToolError, match="Unknown tool"):
        await jira_kind.call(config, "delete_issue", {})


async def _save(db, name, kind, enabled):
    await connectors.save(
        db, CREDS, name=name, kind=kind, base_url="https://x", username="u", secret="s", enabled=enabled
    )


async def test_only_enabled_known_connectors_named_by_the_reviewer(db):
    for name, kind, enabled in [("jira", "jira", True), ("old", "jira", False), ("weird", "nope", True)]:
        await _save(db, name, kind, enabled)
    await db.commit()

    specs = await connectors.tools_for(db, ["jira", "old", "weird", "missing"], "PAY-1")
    assert [s.connector for s in specs] == ["jira"]
    assert specs[0].tool_names == ["mcp__jira__get_issue"]
    assert await connectors.tools_for(db, [], "") == []
    assert uuid.UUID(str((await connectors.get(db, "jira")).id))


async def test_calls_are_limited_to_the_reviewers_connectors(db):
    await _save(db, "jira", "jira", True)
    await _save(db, "other", "jira", True)
    await db.commit()

    with pytest.raises(ToolError, match="isn't available"):
        await connectors.call(db, ["jira"], "other", "get_issue", {"key": "PAY-1"})
    with pytest.raises(ToolError, match="isn't a Jira issue key"):
        await connectors.call(db, ["jira"], "jira", "get_issue", {"key": "nope"})


async def test_bridge_forwards_calls_and_reports_tool_errors():
    calls = []

    async def call(connector, tool, args):
        calls.append((connector, tool, args))
        if args["key"] == "bad":
            raise ToolError("no such issue")
        return "issue text"

    spec = ConnectorTools(connector="jira", tools=list(KINDS["jira"].tools), hint="use jira")
    built = toolset(spec, call)
    assert built.tool_names == ["mcp__jira__get_issue"]
    assert built.prompt_hint == "use jira"

    handler = forward("jira", "get_issue", call)
    assert await handler({"key": "PAY-1"}) == {
        "content": [{"type": "text", "text": "issue text"}],
        "is_error": False,
    }
    assert (await handler({"key": "bad"}))["is_error"] is True
    assert calls == [("jira", "get_issue", {"key": "PAY-1"}), ("jira", "get_issue", {"key": "bad"})]
