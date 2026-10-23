"""Propose changes as pull requests: one commit with any number of files on a branch, then a PR.

Chakshu never writes to a default branch. Everything it changes in a
repository (the workflow, reviewers) goes through a pull request that people
review and merge, so branch protection and code owners still apply.
"""

from dataclasses import dataclass

from githubkit import GitHub
from githubkit.exception import RequestFailed

FILE_MODE = "100644"


@dataclass(frozen=True)
class Change:
    owner: str
    repo: str
    base: str  # branch the PR targets
    branch: str  # branch Chakshu writes; reused (force-updated) by later proposals for the same thing
    files: dict[str, str | None]  # path -> new text, or None to delete
    message: str  # commit message
    title: str
    body: str


@dataclass(frozen=True)
class Proposal:
    url: str
    number: int
    created: bool  # False when an open PR for the branch was updated instead


def _tree_entries(files: dict[str, str | None]) -> list[dict]:
    return [
        {"path": path, "mode": FILE_MODE, "type": "blob", "content": text}
        if text is not None
        else {"path": path, "mode": FILE_MODE, "type": "blob", "sha": None}
        for path, text in sorted(files.items())
    ]


async def _commit(client: GitHub, change: Change) -> str:
    ref = (await client.rest.git.async_get_ref(change.owner, change.repo, f"heads/{change.base}")).parsed_data
    parent = ref.object_.sha
    base_tree = (
        await client.rest.git.async_get_commit(change.owner, change.repo, parent)
    ).parsed_data.tree.sha
    tree = (
        await client.rest.git.async_create_tree(
            change.owner, change.repo, base_tree=base_tree, tree=_tree_entries(change.files)
        )
    ).parsed_data
    commit = (
        await client.rest.git.async_create_commit(
            change.owner, change.repo, message=change.message, tree=tree.sha, parents=[parent]
        )
    ).parsed_data
    return commit.sha


async def _point_branch(client: GitHub, change: Change, sha: str) -> None:
    try:
        await client.rest.git.async_create_ref(
            change.owner, change.repo, ref=f"refs/heads/{change.branch}", sha=sha
        )
    except RequestFailed as exc:
        if exc.response.status_code != 422:  # 422: the branch exists already
            raise
        await client.rest.git.async_update_ref(
            change.owner, change.repo, f"heads/{change.branch}", sha=sha, force=True
        )


async def open_pull_request(client: GitHub, change: Change) -> Proposal:
    """Commit the files on top of the base branch and open (or refresh) the PR for them."""
    sha = await _commit(client, change)
    await _point_branch(client, change, sha)
    existing = (
        await client.rest.pulls.async_list(
            change.owner, change.repo, state="open", head=f"{change.owner}:{change.branch}"
        )
    ).parsed_data
    if existing:
        pr = existing[0]
        await client.rest.pulls.async_update(
            change.owner, change.repo, pr.number, title=change.title, body=change.body
        )
        return Proposal(url=pr.html_url, number=pr.number, created=False)
    pr = (
        await client.rest.pulls.async_create(
            change.owner,
            change.repo,
            title=change.title,
            head=change.branch,
            base=change.base,
            body=change.body,
        )
    ).parsed_data
    return Proposal(url=pr.html_url, number=pr.number, created=True)


async def open_proposal(client: GitHub, owner: str, repo: str, branch: str) -> str | None:
    """URL of the open PR from `branch`, if there is one."""
    pulls = (
        await client.rest.pulls.async_list(owner, repo, state="open", head=f"{owner}:{branch}")
    ).parsed_data
    return pulls[0].html_url if pulls else None
