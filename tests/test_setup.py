import pytest

from chakshu.core.config import get_settings
from chakshu.helpers.urls import is_public_url
from chakshu.services import setup


@pytest.mark.parametrize(
    ("url", "public"),
    [
        ("https://chakshu.example.com/webhooks/github", True),
        ("https://smee.io/abc123", True),
        ("http://localhost:8000/webhooks/github", False),
        ("http://127.0.0.1:8000/x", False),
        ("http://192.168.1.20/x", False),
        ("http://web.internal/x", False),
        ("http://intranet/x", False),
    ],
)
def test_is_public_url(url, public):
    assert is_public_url(url) is public


def test_setup_code_format():
    code = setup.new_setup_code()
    assert len(code) == 9 and code[4] == "-"
    assert not set(code.replace("-", "")) & set("01IO")


def test_manifest_skips_webhooks_for_local_urls(monkeypatch):
    monkeypatch.setenv("CHAKSHU_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("CHAKSHU_WEBHOOK_URL", "")  # don't pick up a smee URL from .env
    get_settings.cache_clear()
    try:
        manifest = setup.build_manifest("chakshu-acme")
    finally:
        get_settings.cache_clear()
    assert manifest["redirect_url"] == "http://localhost:8000/api/setup/callback"
    assert manifest["default_permissions"]["pull_requests"] == "write"
    assert "hook_attributes" not in manifest


def test_manifest_includes_webhooks_for_public_urls(monkeypatch):
    monkeypatch.setenv("CHAKSHU_BASE_URL", "https://chakshu.example.com")
    monkeypatch.setenv("CHAKSHU_WEBHOOK_URL", "")
    get_settings.cache_clear()
    try:
        manifest = setup.build_manifest("chakshu-acme")
    finally:
        get_settings.cache_clear()
    assert manifest["hook_attributes"]["url"] == "https://chakshu.example.com/webhooks/github"
    assert set(manifest["default_events"]) == {
        "pull_request",
        "issue_comment",
        "pull_request_review_comment",
        "push",
        "workflow_run",
        "organization",
        "team",
        "membership",
    }


def test_org_apps_are_created_under_the_org():
    assert "/organizations/acme/settings/apps/new?state=s" in setup.manifest_action_url("acme", "s")
    assert setup.manifest_action_url(None, "s").endswith("/settings/apps/new?state=s")


async def test_claim_rejects_wrong_code_and_requires_csrf(client, db):
    await setup.ensure_setup_code(db)
    session = (await client.get("/api/session")).json()
    assert session["configured"] is False

    no_csrf = await client.post("/api/setup/claim", json={"code": "WRONG-CODE"})
    assert no_csrf.status_code == 403

    wrong = await client.post(
        "/api/setup/claim", json={"code": "WRONG-CODE"}, headers={"X-CSRF-Token": session["csrf_token"]}
    )
    assert wrong.status_code == 403
