"""The reviewer's side of a review workspace: its skills and CLAUDE.md, as files to send to the runner."""

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from chakshu.db.models import Reviewer
from chakshu.helpers import git
from chakshu.helpers import workspace as files
from chakshu.helpers.catalog import skill_dir
from chakshu.helpers.prompt import render_claude_md
from chakshu.services.catalog import clone_url


@dataclass(frozen=True)
class Bundle:
    files: dict[str, str]  # relative path in the workspace -> text
    skills: list[str]


async def build(*, token: str, reviewers_repo: str, reviewer: Reviewer) -> Bundle:
    """Read the reviewer at the commit it was synced from."""
    with tempfile.TemporaryDirectory(prefix="chakshu-bundle-") as tmp:
        source = await git.checkout(clone_url(reviewers_repo), reviewer.source_sha, Path(tmp) / "src", token)
        return await asyncio.to_thread(_collect, source, reviewer)


def _collect(source: Path, reviewer: Reviewer) -> Bundle:
    folder = reviewer.source_path.rsplit("/", 1)[-1]
    dirs = {files.skill_name(ref): skill_dir(source, folder, ref) for ref in reviewer.skills}
    rules_path = source / reviewer.source_path / reviewer.rules if reviewer.rules else None
    rules = rules_path.read_text(encoding="utf-8") if rules_path and rules_path.is_file() else None
    bundle = files.skill_files(dirs)
    bundle["CLAUDE.md"] = render_claude_md(reviewer.name, reviewer.product, rules)
    return Bundle(files=bundle, skills=sorted(dirs))
