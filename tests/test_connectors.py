import uuid

from chakshu.connectors import KINDS, ConnectorConfig
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


def test_jira_toolset_names_its_tool_and_lists_keys():
    config = ConnectorConfig("jira", "jira", "https://acme.atlassian.net", "me@acme.com", "token")
    toolset = KINDS["jira"].build(config, "PAY-412 partial refunds")
    assert toolset.tool_names == ["mcp__jira__get_issue"]
    assert "PAY-412" in toolset.prompt_hint


async def test_only_enabled_known_connectors_named_by_the_reviewer(db):
    for name, kind, enabled in [("jira", "jira", True), ("old", "jira", False), ("weird", "nope", True)]:
        await connectors.save(
            db, CREDS, name=name, kind=kind, base_url="https://x", username="u", secret="s", enabled=enabled
        )
    await db.commit()

    toolsets = await connectors.toolsets_for(db, ["jira", "old", "weird", "missing"], "")
    assert [t.server_name for t in toolsets] == ["jira"]
    assert await connectors.toolsets_for(db, [], "") == []
    assert uuid.UUID(str((await connectors.get(db, "jira")).id))
