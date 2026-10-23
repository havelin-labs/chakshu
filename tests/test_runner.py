"""The GitHub Actions side of a review and the server endpoints it calls."""

import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import jwt
import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from chakshu.api import runner as runner_api
from chakshu.db.models import JobStatus, Run
from chakshu.helpers import workflow
from chakshu.runner import client as runner_client
from chakshu.runner import main as runner_main
from chakshu.runner.protocol import Job, Result
from chakshu.services import oidc, review_results
from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key

ISSUER = "https://token.actions.githubusercontent.com"
AUD = "https://chakshu.example.com"


def _claims(**overrides) -> dict:
    now = int(time.time())
    return {
        "iss": ISSUER,
        "aud": AUD,
        "iat": now,
        "exp": now + 300,
        "repository": "acme/api",
        "repository_id": "3",
        "run_id": "555",
        "workflow_ref": "acme/api/.github/workflows/chakshu.yml@refs/heads/main",
        "event_name": "workflow_dispatch",
    } | overrides


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(key, **overrides) -> str:
    return jwt.encode(_claims(**overrides), key, algorithm="RS256")


def test_oidc_tokens_are_read_into_an_identity(signing_key):
    identity = oidc.decode(_token(signing_key), signing_key.public_key(), issuer=ISSUER, aud=AUD)
    assert identity == oidc.RunnerIdentity(
        repository="acme/api",
        repository_id=3,
        run_id=555,
        workflow_ref="acme/api/.github/workflows/chakshu.yml@refs/heads/main",
        event_name="workflow_dispatch",
    )


@pytest.mark.parametrize(
    "overrides",
    [{"aud": "https://elsewhere.example.com"}, {"iss": "https://evil.example.com"}, {"exp": 1}],
)
def test_oidc_tokens_for_someone_else_or_expired_are_refused(signing_key, overrides):
    with pytest.raises(oidc.InvalidToken):
        oidc.decode(_token(signing_key, **overrides), signing_key.public_key(), issuer=ISSUER, aud=AUD)


def test_oidc_tokens_signed_by_another_key_are_refused(signing_key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(oidc.InvalidToken):
        oidc.decode(_token(other), signing_key.public_key(), issuer=ISSUER, aud=AUD)


def _ctx(status=JobStatus.DISPATCHED, actions_run_id=555):
    return SimpleNamespace(
        repo=SimpleNamespace(github_id=3, full_name="acme/api"),
        run=SimpleNamespace(actions_run_id=actions_run_id, status=status),
    )


def _identity(**overrides) -> oidc.RunnerIdentity:
    values = {
        "repository": "acme/api",
        "repository_id": 3,
        "run_id": 555,
        "workflow_ref": "acme/api/.github/workflows/chakshu.yml@refs/heads/main",
        "event_name": "workflow_dispatch",
    } | overrides
    return oidc.RunnerIdentity(**values)


@pytest.mark.parametrize(
    ("identity", "ctx", "code"),
    [
        (_identity(repository_id=4), _ctx(), 404),
        (_identity(workflow_ref="acme/api/.github/workflows/ci.yml@refs/heads/main"), _ctx(), 403),
        (_identity(event_name="push"), _ctx(), 403),
        (_identity(run_id=556), _ctx(), 403),
        (_identity(), _ctx(status=JobStatus.SUCCEEDED), 409),
    ],
)
def test_only_the_dispatched_actions_run_may_act_for_a_review(identity, ctx, code):
    with pytest.raises(HTTPException) as caught:
        runner_api.authorize(identity, ctx)
    assert caught.value.status_code == code


def test_the_dispatched_actions_run_is_allowed():
    runner_api.authorize(_identity(), _ctx())


def test_workflow_template_declares_what_the_dispatcher_sends():
    rendered = workflow.render("acme/chakshu@v1")
    assert workflow.ACTION_PLACEHOLDER not in rendered
    spec = yaml.safe_load(rendered)
    declared = set(spec[True]["workflow_dispatch"]["inputs"])  # YAML reads the `on` key as True
    sent = workflow.dispatch_inputs(run_id="r", pr=1, head_sha="s", reviewer="x", server="https://c")
    assert declared == set(sent)
    assert spec["permissions"] == {"contents": "read", "id-token": "write"}
    step = spec["jobs"]["review"]["steps"][1]
    assert step["uses"] == "acme/chakshu@v1"
    assert set(step["env"]) == {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"}


def test_claude_access_prefers_the_api_key_and_drops_empty_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert runner_main.claude_access() == {"CLAUDE_CODE_OAUTH_TOKEN": "tok"}
    import os

    assert "ANTHROPIC_API_KEY" not in os.environ

    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert runner_main.claude_access() == {"ANTHROPIC_API_KEY": "key"}

    with pytest.raises(runner_main.RunnerError, match="No Claude credential"):
        runner_main.claude_access()


def test_step_summary_lists_the_findings(tmp_path, monkeypatch):
    path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    job = Job(
        run_id=uuid.uuid4(),
        repo="acme/api",
        pr_number=7,
        head_sha="b" * 40,
        reviewer="default",
        model="sonnet",
        max_usd=2,
        prompt="p",
        files={},
    )
    result = Result(
        summary="Adds refunds.",
        findings=[{"severity": "high", "path": "a.py", "line": 3, "title": "Off by one | again"}],
        cost_usd=0.05,
    )
    runner_main.write_step_summary(job, result, "https://github.com/acme/api/pull/7#review")
    text = path.read_text(encoding="utf-8")
    assert "## Chakshu · default" in text
    assert "| high | `a.py:3` | Off by one / again |" in text
    assert "[Open the review](https://github.com/acme/api/pull/7#review)" in text


async def _server_client(handler) -> tuple[runner_client.ServerClient, httpx.AsyncClient]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tokens = runner_client.OidcTokens("https://oidc.test/token?x=1", "req", AUD)
    return runner_client.ServerClient(AUD, uuid.uuid4(), tokens, http), http


async def test_client_retries_server_errors_with_a_fresh_token(monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr(runner_client.asyncio, "sleep", no_sleep)
    seen = {"oidc": 0, "server": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oidc.test":
            seen["oidc"] += 1
            assert request.url.params["audience"] == AUD
            return httpx.Response(200, json={"value": f"jwt-{seen['oidc']}"})
        seen["server"] += 1
        assert request.headers["Authorization"] == f"Bearer jwt-{seen['oidc']}"
        if seen["server"] == 1:
            return httpx.Response(503, json={"detail": "busy"})
        return httpx.Response(200, json={"review_url": "https://x"})

    client, http = await _server_client(handler)
    async with http:
        assert await client.result(Result(summary="s")) == "https://x"
    assert seen == {"oidc": 2, "server": 2}


async def test_client_does_not_retry_refusals():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oidc.test":
            return httpx.Response(200, json={"value": "jwt"})
        return httpx.Response(403, json={"detail": "not this run"})

    client, http = await _server_client(handler)
    async with http:
        with pytest.raises(runner_client.ServerError, match="403 not this run"):
            await client.job()


def test_oidc_request_settings_are_taken_out_of_the_environment(monkeypatch):
    import os

    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_URL", "https://oidc.test/token")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "req")
    runner_client.OidcTokens.from_env(AUD)
    assert "ACTIONS_ID_TOKEN_REQUEST_TOKEN" not in os.environ
    with pytest.raises(runner_client.ServerError, match="id-token: write"):
        runner_client.OidcTokens.from_env(AUD)


@pytest.fixture
async def dispatched_run(db, seed_runs, monkeypatch):
    """A run waiting on Actions run 555, with app credentials stored and OIDC checks faked."""
    (run_id,) = await seed_runs(1)
    run = await db.get(Run, run_id)
    run.status, run.actions_run_id = JobStatus.DISPATCHED, 555
    run.started_at = datetime.now(UTC)
    await store.put(db, Key.APP_ID, "1")
    await store.put(db, Key.APP_PRIVATE_KEY, "k")
    await db.commit()

    async def verify(token: str) -> oidc.RunnerIdentity:
        if token != "good":
            raise oidc.InvalidToken("bad signature")
        return _identity()

    monkeypatch.setattr(oidc, "verify", verify)
    return run_id


async def test_runner_endpoints_need_a_valid_token(client, dispatched_run):
    url = f"/api/runner/runs/{dispatched_run}/failure"
    assert (await client.post(url, json={"error": "x"})).status_code == 401
    bad = await client.post(url, json={"error": "x"}, headers={"Authorization": "Bearer forged"})
    assert bad.status_code == 401


async def test_runner_failure_is_recorded_once(client, db, dispatched_run):
    url = f"/api/runner/runs/{dispatched_run}/failure"
    headers = {"Authorization": "Bearer good"}
    resp = await client.post(
        url, json={"error": "Review stopped: error_max_budget_usd.", "cost_usd": 1.5}, headers=headers
    )
    assert resp.status_code == 200
    run = await db.get(Run, dispatched_run, populate_existing=True)
    assert run.status == JobStatus.FAILED
    assert run.error == "Review stopped: error_max_budget_usd."
    assert float(run.cost_usd) == 1.5
    # The review is over, so the same Actions run can't report again.
    assert (await client.post(url, json={"error": "again"}, headers=headers)).status_code == 409


async def test_runner_tool_calls_only_reach_the_reviewers_connectors(client, dispatched_run):
    resp = await client.post(
        f"/api/runner/runs/{dispatched_run}/tools/jira/get_issue",
        json={"args": {"key": "PAY-1"}},
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"text": "The connector 'jira' isn't available to this reviewer.", "is_error": True}


async def test_silent_dispatched_runs_expire(db, dispatched_run):
    run = await db.get(Run, dispatched_run)
    run.started_at = datetime.now(UTC) - timedelta(hours=1)
    await db.commit()
    assert await review_results.expire_dispatched(db) == 1
    run = await db.get(Run, dispatched_run, populate_existing=True)
    assert run.status == JobStatus.FAILED
    assert "45 minutes" in run.error


async def test_an_actions_run_that_ends_without_a_result_fails_the_review(db, dispatched_run):
    from chakshu.handlers import workflow_run
    from chakshu.handlers.context import Context
    from chakshu.services import github

    creds = await github.load_credentials(db)
    payload = {"action": "completed", "workflow_run": {"id": 555, "conclusion": "cancelled"}}
    await workflow_run.handle(Context(db, creds, "d1"), payload)
    await db.commit()
    run = await db.get(Run, dispatched_run, populate_existing=True)
    assert run.status == JobStatus.FAILED
    assert "ended (cancelled)" in run.error
