import uuid
from base64 import b64decode
from typing import Any

import httpx
from githubkit import Response
from githubkit.exception import RequestFailed
from nacl import encoding, public

from chakshu.db.models import Installation, Repo
from chakshu.helpers import workflow
from chakshu.services import actions_secrets, app_permissions, orgs, proposals, setup
from chakshu.services.repo_setup import ActionsStatus


def test_released_servers_pin_the_action_to_their_minor_version():
    assert workflow.default_action("0.1.0") == "havelin-labs/chakshu@v0.1"
    assert workflow.default_action("1.12.3") == "havelin-labs/chakshu@v1.12"
    assert workflow.default_action("0.2.0.dev0") == "havelin-labs/chakshu@main"
    assert workflow.default_action("0.2.0rc1") == "havelin-labs/chakshu@main"
    assert f"uses: {workflow.DEFAULT_ACTION}" in workflow.render()


def test_secrets_are_sealed_for_the_repositorys_key():
    private = public.PrivateKey.generate()
    repo_key = private.public_key.encode(encoding.Base64Encoder()).decode()
    sealed = actions_secrets.seal(repo_key, "sk-ant-secret")
    assert "sk-ant-secret" not in sealed
    assert public.SealedBox(private).decrypt(b64decode(sealed)) == b"sk-ant-secret"


def test_each_credential_has_its_own_prefixed_secret():
    assert actions_secrets.SECRET_FOR == {
        "ANTHROPIC_API_KEY": workflow.API_KEY_SECRET,
        "CLAUDE_CODE_OAUTH_TOKEN": workflow.TOKEN_SECRET,
    }
    assert all(name.startswith("CHAKSHU_") for name in actions_secrets.SECRET_FOR.values())


def test_missing_permissions_compare_levels():
    required = {"contents": "write", "actions": "write", "metadata": "read"}
    granted = {"contents": "read", "metadata": "write"}
    assert app_permissions.missing(granted, required) == ["contents: write", "actions: write"]
    assert (
        app_permissions.missing({"contents": "admin", "actions": "write", "metadata": "read"}, required) == []
    )


def test_apps_made_before_team_creation_are_told_to_upgrade_members():
    granted = setup.APP_PERMISSIONS | {"members": "read"}
    assert app_permissions.missing(granted) == ["members: write"]


def test_missing_events():
    assert app_permissions.missing_events(["push"], ["push", "workflow_run"]) == ["workflow_run"]


def test_proposal_trees_write_and_delete_files():
    entries = proposals._tree_entries({"b.md": None, "a.md": "text"})
    assert entries == [
        {"path": "a.md", "mode": "100644", "type": "blob", "content": "text"},
        {"path": "b.md", "mode": "100644", "type": "blob", "sha": None},
    ]


def test_a_repo_is_ready_with_the_workflow_and_one_secret():
    assert ActionsStatus("current", None, {"A": True, "B": False}).ready
    assert ActionsStatus("outdated", None, {"A": True}).ready
    assert not ActionsStatus("missing", "https://pr", {"A": True}).ready
    assert not ActionsStatus("current", None, {"A": False}).ready


async def test_review_teams_cover_each_installed_org(db, monkeypatch):
    def add(github_id: int, login: str, account_type: str = "Organization", suspended: bool = False):
        install = Installation(
            id=uuid.uuid4(),
            github_id=github_id,
            account_github_id=github_id * 10,
            account_login=login,
            account_type=account_type,
            suspended=suspended,
        )
        db.add(install)
        return install

    acme = add(1, "acme")
    add(2, "globex")
    add(3, "alice", account_type="User")
    add(4, "initech", suspended=True)
    await db.flush()
    db.add_all(
        [
            Repo(id=uuid.uuid4(), github_id=11, installation_id=acme.id, full_name="acme/web"),
            Repo(id=uuid.uuid4(), github_id=12, installation_id=acme.id, full_name="acme/api"),
        ]
    )
    await db.commit()

    calls = []

    async def ensure(creds, installation_id, org, repo_names):
        calls.append((installation_id, org, repo_names))
        if org == "globex":
            request = httpx.Request("POST", "https://api.github.com/orgs/globex/teams")
            raise RequestFailed(Response(httpx.Response(403, request=request), Any))
        return "created"

    monkeypatch.setattr(orgs, "ensure_review_team", ensure)

    results = await orgs.ensure_review_teams(db, creds=None)

    assert results == {"acme": "created", "globex": "failed (403)"}
    assert sorted(calls) == [(1, "acme", ["acme/api", "acme/web"]), (2, "globex", [])]
