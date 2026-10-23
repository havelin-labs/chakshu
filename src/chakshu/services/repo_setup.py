"""Get a repository ready for reviews in GitHub Actions: the workflow file and the Claude secrets.

The workflow arrives as a pull request (Chakshu never pushes to a default
branch); the secrets are written directly, since they can't be reviewed anyway.
"""

import base64
from dataclasses import dataclass, field
from typing import Literal

from githubkit import GitHub
from githubkit.exception import RequestFailed
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Repo
from chakshu.helpers import workflow
from chakshu.services import actions_secrets, proposals
from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key

SETUP_BRANCH = "chakshu/setup-actions"
WorkflowState = Literal["current", "outdated", "missing"]


@dataclass
class ActionsStatus:
    workflow: WorkflowState
    proposal_url: str | None  # open PR adding or updating the workflow
    secrets: dict[str, bool] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.workflow != "missing" and any(self.secrets.values())


async def action_ref(session: AsyncSession) -> str:
    return await store.get(session, Key.ACTIONS_ACTION) or workflow.DEFAULT_ACTION


async def _workflow_state(client: GitHub, repo: Repo, expected: str) -> WorkflowState:
    owner, name = repo.full_name.split("/", 1)
    try:
        content = (
            await client.rest.repos.async_get_content(
                owner, name, workflow.WORKFLOW_PATH, ref=repo.default_branch
            )
        ).parsed_data
    except RequestFailed as exc:
        if exc.response.status_code == 404:
            return "missing"
        raise
    text = base64.b64decode(getattr(content, "content", "") or "").decode(errors="replace")
    return "current" if text.strip() == expected.strip() else "outdated"


async def status(session: AsyncSession, client: GitHub, repo: Repo) -> ActionsStatus:
    owner, name = repo.full_name.split("/", 1)
    expected = workflow.render(await action_ref(session))
    return ActionsStatus(
        workflow=await _workflow_state(client, repo, expected),
        proposal_url=await proposals.open_proposal(client, owner, name, SETUP_BRANCH),
        secrets=await actions_secrets.present(client, repo.full_name),
    )


def _change(repo: Repo, content: str, requester: str, adding: bool) -> proposals.Change:
    owner, name = repo.full_name.split("/", 1)
    verb = "add" if adding else "update"
    return proposals.Change(
        owner=owner,
        repo=name,
        base=repo.default_branch,
        branch=SETUP_BRANCH,
        files={workflow.WORKFLOW_PATH: content},
        message=(
            f"ci: {verb} the chakshu review workflow\n\n"
            "Chakshu runs code reviews in this repository's GitHub Actions, so the logs\n"
            "are here. It starts this workflow with workflow_dispatch; it never runs on\n"
            "pushes or pull requests by itself."
        ),
        title=f"ci: {verb} the Chakshu review workflow",
        body=(
            f"Chakshu reviews pull requests here when someone asks for one. This PR {verb}s "
            f"`{workflow.WORKFLOW_PATH}`, the workflow it starts for each review, so you can follow "
            "each review in the Actions tab.\n\n"
            "It only runs when Chakshu dispatches it. It can read the code and request an OIDC token "
            "(`id-token: write`), which is how the runner proves to Chakshu which review it is doing. "
            "The Claude credential comes from repository secrets that Chakshu manages.\n\n"
            f"Requested by @{requester} in Chakshu."
        ),
    )


async def set_up(session: AsyncSession, client: GitHub, repo: Repo, requester: str) -> ActionsStatus:
    """Propose the workflow if it's missing or old, and write the secrets. Returns the new status."""
    expected = workflow.render(await action_ref(session))
    state = await _workflow_state(client, repo, expected)
    if state != "current":
        await proposals.open_pull_request(
            client, _change(repo, expected, requester, adding=state == "missing")
        )
    await actions_secrets.sync_repo(client, repo.full_name, await actions_secrets.wanted(session))
    return await status(session, client, repo)
