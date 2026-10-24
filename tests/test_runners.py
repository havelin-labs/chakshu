"""Runner labels for the review workflow: parsing, rendering, the org default and per-repo overrides."""

import uuid

import pytest
import yaml

from chakshu.api import deps
from chakshu.db.models import Installation, Repo, User
from chakshu.helpers import workflow
from chakshu.services import repo_setup
from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key


def test_labels_parse_from_commas_or_spaces_and_drop_repeats():
    assert workflow.parse_runner("self-hosted, linux  x64,linux") == ("self-hosted", "linux", "x64")
    assert workflow.parse_runner("") == workflow.DEFAULT_RUNNER
    assert workflow.parse_runner(None) == workflow.DEFAULT_RUNNER


@pytest.mark.parametrize("bad", ["self hosted;rm", "-linux", "a" * 101, ",".join(f"l{i}" for i in range(11))])
def test_bad_labels_are_refused(bad):
    with pytest.raises(ValueError):
        workflow.parse_runner(bad)


def test_the_default_workflow_is_unchanged_for_existing_installs():
    rendered = workflow.render("acme/chakshu@v1")
    assert workflow.RUNNER_PLACEHOLDER not in rendered
    assert yaml.safe_load(rendered)["jobs"]["review"]["runs-on"] == "ubuntu-latest"


def test_several_labels_render_as_a_list():
    rendered = workflow.render("acme/chakshu@v1", ("self-hosted", "linux", "x64"))
    assert yaml.safe_load(rendered)["jobs"]["review"]["runs-on"] == ["self-hosted", "linux", "x64"]


@pytest.fixture
async def repo(db):
    installation = Installation(
        id=uuid.uuid4(), github_id=41, account_github_id=42, account_login="acme", account_type="Organization"
    )
    repo = Repo(id=uuid.uuid4(), github_id=43, installation_id=installation.id, full_name="acme/api")
    db.add_all([installation, repo])
    await db.commit()
    return repo


async def test_a_repo_override_beats_the_org_default(db, repo):
    assert await repo_setup.runner_for(db, repo) == ("ubuntu-latest",)
    await store.put(db, Key.ACTIONS_RUNS_ON, "self-hosted, linux")
    assert await repo_setup.runner_for(db, repo) == ("self-hosted", "linux")
    repo.runs_on = "gpu-runner"
    assert await repo_setup.runner_for(db, repo) == ("gpu-runner",)
    assert "runs-on: gpu-runner" in await repo_setup.expected_workflow(db, repo)


@pytest.fixture
def as_admin(client):
    app = client._transport.app
    app.dependency_overrides[deps.optional_user] = lambda: User(
        id=uuid.uuid4(), github_id=1, login="owner", is_admin=True
    )
    yield client
    app.dependency_overrides.clear()


async def _csrf(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/session")).json()["csrf_token"]}


async def test_repo_runner_can_be_set_validated_and_cleared(db, repo, as_admin):
    headers = await _csrf(as_admin)
    bad = await as_admin.put(f"/api/repos/{repo.id}", json={"runs_on": "bad;label"}, headers=headers)
    assert bad.status_code == 422
    saved = await as_admin.put(
        f"/api/repos/{repo.id}", json={"runs_on": "self-hosted linux"}, headers=headers
    )
    assert saved.json()["runs_on"] == "self-hosted, linux" and saved.json()["enabled"] is True
    cleared = await as_admin.put(f"/api/repos/{repo.id}", json={"runs_on": ""}, headers=headers)
    assert cleared.json()["runs_on"] is None


async def test_org_default_runner_is_stored_only_when_it_differs(db, as_admin):
    headers = await _csrf(as_admin)
    base = {"default_model": "sonnet", "max_usd_per_review": 2, "reviewers_repo": "chakshu-reviewers"}
    resp = await as_admin.put(
        "/api/settings", json=base | {"actions_runs_on": "self-hosted, x64"}, headers=headers
    )
    assert resp.status_code == 200 and resp.json()["actions_runs_on"] == "self-hosted, x64"
    resp = await as_admin.put("/api/settings", json=base | {"actions_runs_on": ""}, headers=headers)
    assert resp.json()["actions_runs_on"] == "ubuntu-latest"
    assert await store.get(db, Key.ACTIONS_RUNS_ON) is None


async def test_default_runner_endpoint_marks_workflows_outdated(db, repo, as_admin):
    headers = await _csrf(as_admin)
    before = await repo_setup.expected_workflow(db, repo)
    saved = await as_admin.put(
        "/api/settings/actions/runner", json={"runs_on": "self-hosted linux"}, headers=headers
    )
    assert saved.json() == {"actions_runs_on": "self-hosted, linux"}
    after = await repo_setup.expected_workflow(db, repo)
    assert after != before and "runs-on: [self-hosted, linux]" in after
    bad = await as_admin.put("/api/settings/actions/runner", json={"runs_on": "x;y"}, headers=headers)
    assert bad.status_code == 422
