"""Build the folder a review runs in: team skills and rules, plus the PR's code."""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from chakshu.db.models import Reviewer
from chakshu.helpers import git
from chakshu.helpers import workspace as files
from chakshu.helpers.catalog import skill_dir
from chakshu.helpers.prompt import render_claude_md
from chakshu.services.catalog import clone_url

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Workspace:
    root: Path  # the agent's working directory
    code: Path
    skills: list[str]


async def build(
    tmp: Path,
    *,
    token: str,
    reviewers_repo: str,
    reviewer: Reviewer,
    pr_repo: str,
    head_sha: str,
) -> Workspace:
    """Check out the reviewer (at its synced commit) and the PR (at its head) under `tmp`."""
    source = await git.checkout(clone_url(reviewers_repo), reviewer.source_sha, tmp / "reviewers", token)
    root = tmp / "workspace"
    code = await git.checkout(clone_url(pr_repo), head_sha, root / "code", token)
    return await asyncio.to_thread(_assemble, source, root, code, reviewer)


def _assemble(source: Path, root: Path, code: Path, reviewer: Reviewer) -> Workspace:
    removed = files.strip_instruction_files(code) + files.remove_symlinks_leaving(code)
    if removed:
        log.info("Removed from PR checkout: %s", ", ".join(removed[:20]))

    folder = reviewer.source_path.rsplit("/", 1)[-1]
    skills = files.install_skills(
        {files.skill_name(ref): skill_dir(source, folder, ref) for ref in reviewer.skills}, root
    )
    rules_path = source / reviewer.source_path / reviewer.rules if reviewer.rules else None
    rules = rules_path.read_text(encoding="utf-8") if rules_path and rules_path.is_file() else None
    (root / "CLAUDE.md").write_text(
        render_claude_md(reviewer.name, reviewer.product, rules), encoding="utf-8"
    )
    return Workspace(root=root, code=code, skills=skills)
