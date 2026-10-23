from base64 import b64decode

from nacl import encoding, public

from chakshu.helpers import workflow
from chakshu.services import actions_secrets, app_permissions, proposals
from chakshu.services.repo_setup import ActionsStatus


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
