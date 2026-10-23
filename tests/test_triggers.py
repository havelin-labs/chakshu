import hashlib
import hmac
from dataclasses import dataclass, field

import pytest

from chakshu.helpers import mentions, messages, selection


@dataclass
class R:
    name: str
    owner_team: str = "core"
    repos: list[str] = field(default_factory=lambda: ["*"])
    paths: list[str] = field(default_factory=list)
    auto: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


PAYMENTS = R("payments", "payments", repos=["payments-*"], paths=["src/refunds/**"], auto=["opened"])
PLATFORM = R("platform", "platform", repos=["*"], paths=["deploy/**", "*.tf"])
DEFAULT = R("default", "platform")
BROKEN = R("broken", errors=["bad yaml"])
ALL = [PAYMENTS, PLATFORM, DEFAULT, BROKEN]


def names(reviewers):
    return [r.name for r in reviewers]


def test_repo_and_path_matching():
    files = ["src/refunds/service.ts", "README.md"]
    assert names(selection.applicable(ALL, "acme/payments-api", files)) == ["payments", "default"]
    assert names(selection.applicable(ALL, "acme/web", ["main.tf"])) == ["platform", "default"]


def test_auto_runs_only_opted_in_reviewers():
    files = ["src/refunds/a.py"]
    assert names(selection.applicable(ALL, "acme/payments-api", files, event="opened")) == ["payments"]
    assert selection.applicable(ALL, "acme/payments-api", files, event="synchronize") == []


@pytest.mark.parametrize(
    ("note", "picked", "rest"),
    [
        ("payments platform check refunds", ["payments", "platform"], "check refunds"),
        ("Payments, PLATFORM: check", ["payments", "platform"], "check"),
        ("payments,platform", ["payments", "platform"], ""),
        ("payments payments", ["payments"], ""),
        ("check payments", [], "check payments"),
        ("broken check", [], "broken check"),
        ("", [], ""),
    ],
)
def test_pick_named_takes_leading_reviewer_names(note, picked, rest):
    chosen, left = selection.pick_named(ALL, note)
    assert (names(chosen), left) == (picked, rest)


def test_by_names_reports_unknown_and_broken_reviewers():
    chosen, unknown = selection.by_names(ALL, ["Platform", "broken", "nope", "platform"])
    assert names(chosen) == ["platform"]
    assert unknown == ["broken", "nope"]


def test_nothing_matched_explains_calling_by_name():
    body = messages.nothing_matched("ana", "@acme/chakshu", ["payments", "platform"])
    assert "`@acme/chakshu payments`" in body
    assert "- `platform`" in body
    assert "no reviewers yet" in messages.nothing_matched("ana", "@acme/chakshu", [])


def test_fallback_is_the_healthy_default_reviewer():
    assert names(selection.fallback(ALL, "acme/anything")) == ["default"]
    assert selection.fallback([R("default", errors=["x"])], "acme/anything") == []


@pytest.mark.parametrize(
    ("body", "note"),
    [
        ("@acme/chakshu", ""),
        ("@ACME/Chakshu please check the refund flow", "please check the refund flow"),
        ("Looks good. @acme/chakshu: focus on errors", "focus on errors"),
        ("/chakshu", ""),
        ("> @acme/chakshu quoted", None),
        ("```\n@acme/chakshu\n```", None),
        ("@acme/chakshu-bots ping", None),
        ("@other/chakshu", None),
        ("email me@acme/chakshu", None),
        ("nothing here", None),
    ],
)
def test_parse_request(body, note):
    assert mentions.parse_request(body, "acme") == note


async def test_webhook_rejects_bad_signatures(client, db):
    from chakshu.services import settings_store as store
    from chakshu.services.settings_store import Key

    await store.put_many(db, {Key.APP_ID: "1", Key.APP_PRIVATE_KEY: "pem", Key.APP_WEBHOOK_SECRET: "s3cret"})
    await db.commit()
    body = b'{"zen": "ok"}'
    good = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    headers = {"X-GitHub-Event": "ping", "X-GitHub-Delivery": "d-1", "Content-Type": "application/json"}

    bad = await client.post(
        "/webhooks/github", content=body, headers=headers | {"X-Hub-Signature-256": "sha256=0"}
    )
    first = await client.post(
        "/webhooks/github", content=body, headers=headers | {"X-Hub-Signature-256": good}
    )
    again = await client.post(
        "/webhooks/github", content=body, headers=headers | {"X-Hub-Signature-256": good}
    )

    assert bad.status_code == 401
    assert first.json() == {"status": "accepted"}
    assert again.json() == {"status": "duplicate"}
