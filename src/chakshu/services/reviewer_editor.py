"""Load reviewers from the reviewers repo for the portal's editor, and propose changes as pull requests.

Saving never writes to the default branch: each save opens (or refreshes) a PR
in the reviewers repo, and the reviewer goes live when someone merges it.
"""

import base64
from dataclasses import dataclass

import yaml
from githubkit import GitHub
from githubkit.exception import RequestFailed
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, Repo, Reviewer
from chakshu.helpers import reviewer_drafts as drafts
from chakshu.helpers.reviewer_drafts import ReviewerDraft
from chakshu.services import catalog, connectors, github, proposals
from chakshu.services.github import AppCredentials


class DraftError(Exception):
    """The draft can't be saved; `errors` say why, one per problem."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class ReviewersRepo:
    repo: Repo
    client: GitHub
    sha: str  # head of the default branch
    paths: set[str]  # every file in the repo at that commit

    @property
    def owner(self) -> str:
        return self.repo.full_name.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.repo.full_name.split("/", 1)[1]

    async def read(self, path: str) -> str | None:
        if path not in self.paths:
            return None
        content = (
            await self.client.rest.repos.async_get_content(self.owner, self.name, path, ref=self.sha)
        ).parsed_data
        return base64.b64decode(getattr(content, "content", "") or "").decode(errors="replace")


async def installation_for(session: AsyncSession, account: str) -> Installation | None:
    return await session.scalar(
        select(Installation).where(func.lower(Installation.account_login) == account.lower())
    )


async def open_repo(
    session: AsyncSession, creds: AppCredentials, installation: Installation
) -> ReviewersRepo:
    repo = await catalog.reviewers_repo(session, installation)
    if repo is None:
        raise DraftError([f"{installation.account_login} has no reviewers repo that Chakshu can see."])
    owner, name = repo.full_name.split("/", 1)
    client = github.installation_client(creds, installation.github_id)
    branch = (await client.rest.repos.async_get_branch(owner, name, repo.default_branch)).parsed_data
    tree = (await client.rest.git.async_get_tree(owner, name, branch.commit.sha, recursive="1")).parsed_data
    paths = {entry.path for entry in tree.tree if entry.type == "blob" and entry.path}
    return ReviewersRepo(repo=repo, client=client, sha=branch.commit.sha, paths=paths)


def _folder(reviewer: Reviewer) -> str:
    return reviewer.source_path.removeprefix(f"{drafts.REVIEWERS_DIR}/")


async def load_draft(
    session: AsyncSession, creds: AppCredentials, installation: Installation, reviewer: Reviewer
) -> ReviewerDraft:
    """The reviewer as it is on the default branch now, ready to edit."""
    target = await open_repo(session, creds, installation)
    base = drafts.folder_path(_folder(reviewer))
    text = await target.read(f"{base}/reviewer.yaml")
    try:
        raw = yaml.safe_load(text or "") or {}
    except yaml.YAMLError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("name", reviewer.name)
    rules = await target.read(f"{base}/{drafts.rules_file(raw)}") or ""
    skills = {}
    for skill in raw.get("skills") or []:
        skill = str(skill)
        if not skill.startswith(drafts.SHARED_PREFIX):
            skills[skill] = await target.read(f"{base}/skills/{skill}/{drafts.SKILL_FILE}") or ""
    try:
        return drafts.from_files(installation.account_login, raw, rules, skills)
    except ValueError as exc:
        raise DraftError([f"reviewer.yaml can't be opened here ({exc}). Fix it in GitHub first."]) from exc


async def _check(
    session: AsyncSession,
    installation: Installation,
    target: ReviewersRepo,
    draft: ReviewerDraft,
    folder: str,
    reviewer: Reviewer | None,
) -> list[str]:
    """Problems only the repo and the database can show: name clashes, missing skills and connectors."""
    errors = []
    taken = await session.scalar(
        select(Reviewer).where(Reviewer.installation_id == installation.id, Reviewer.name == draft.name)
    )
    if taken is not None and taken.id != (reviewer.id if reviewer else None):
        errors.append(f"name: '{draft.name}' is already used by {taken.source_path}")
    if reviewer is None and any(p.startswith(f"{drafts.folder_path(folder)}/") for p in target.paths):
        errors.append(f"name: {drafts.folder_path(folder)} already exists in {target.repo.full_name}")
    for skill in draft.shared_skills:
        if skill.strip() and drafts.shared_skill_path(skill.strip()) not in target.paths:
            errors.append(f"shared skill '{skill}' isn't in {drafts.SHARED_SKILLS_DIR}")
    configured = {c.name for c in await connectors.list_all(session)}
    errors += [f"connector '{c}' isn't set up in Chakshu" for c in draft.connectors if c not in configured]
    return errors


def _change(
    target: ReviewersRepo, files: dict[str, str | None], name: str, branch: str, adding: bool, login: str
) -> proposals.Change:
    verb = "add" if adding else "update"
    body = (
        f"This PR {verb}s the `{name}` reviewer. Chakshu picks it up once this is merged.\n\n"
        f"Proposed by @{login} in Chakshu."
    )
    return proposals.Change(
        owner=target.owner,
        repo=target.name,
        base=target.repo.default_branch,
        branch=branch,
        files=files,
        message=f"feat: {verb} {name} reviewer\n\nProposed by @{login} in Chakshu.",
        title=f"feat: {verb} {name} reviewer",
        body=body,
    )


async def propose(
    session: AsyncSession,
    creds: AppCredentials,
    installation: Installation,
    draft: ReviewerDraft,
    reviewer: Reviewer | None,
    login: str,
) -> proposals.Proposal:
    """Open or refresh the PR that adds (reviewer=None) or updates a reviewer. Raises DraftError."""
    spec, errors = drafts.to_spec(draft)
    if spec is None:
        raise DraftError(errors)
    draft = draft.model_copy(update={"name": spec.name})
    folder = _folder(reviewer) if reviewer else spec.name
    target = await open_repo(session, creds, installation)
    errors = await _check(session, installation, target, draft, folder, reviewer)
    if errors:
        raise DraftError(errors)
    files = drafts.render_files(spec, draft, folder, target.paths)
    # Edits keep the branch of the reviewer's current name, so a rename refreshes the same PR.
    branch = f"chakshu/reviewer-{reviewer.name if reviewer else spec.name}"
    change = _change(target, files, spec.name, branch, adding=reviewer is None, login=login)
    try:
        return await proposals.open_pull_request(target.client, change)
    except RequestFailed as exc:
        raise DraftError(
            [
                f"GitHub refused the change ({exc.response.status_code}). The app needs contents and "
                "pull requests write access to the reviewers repo."
            ]
        ) from exc
