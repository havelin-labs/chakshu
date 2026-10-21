"""File-level rules for the review workspace. Pure filesystem helpers, no network.

Layout the agent sees (its working directory):

    .claude/skills/<skill>/SKILL.md   the team's skills, from the reviewers repo
    CLAUDE.md                         review task + the team's RULES.md
    code/                             the pull request at its head commit

Only the first two can carry instructions. Anything in code/ that Claude Code
would treat as instructions or config is deleted before the agent starts.
"""

import shutil
from pathlib import Path

# Files and folders Claude Code reads as instructions or settings, at any depth.
INSTRUCTION_NAMES = frozenset({".claude", "CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", ".mcp.json"})


def strip_instruction_files(code: Path) -> list[str]:
    """Delete instruction/config files from the PR checkout. Returns what was removed."""
    removed: list[str] = []
    for path in sorted(code.rglob("*"), key=lambda p: len(p.parts)):
        if not path.exists() and not path.is_symlink():
            continue  # already gone with a parent folder
        if path.name in INSTRUCTION_NAMES or path.name == ".git":
            removed.append(path.relative_to(code).as_posix())
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    return removed


def remove_symlinks_leaving(code: Path) -> list[str]:
    """Delete symlinks that point outside the checkout, so Read can't follow them out."""
    root = code.resolve()
    removed = []
    for path in code.rglob("*"):
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            removed.append(path.relative_to(code).as_posix())
            path.unlink()
    return removed


def install_skills(skill_dirs: dict[str, Path], workspace: Path) -> list[str]:
    """Copy each skill folder to .claude/skills/<name>. Returns the installed names."""
    target = workspace / ".claude" / "skills"
    target.mkdir(parents=True, exist_ok=True)
    for name, source in skill_dirs.items():
        shutil.copytree(source, target / name, symlinks=False)
    return sorted(skill_dirs)


def skill_name(reference: str) -> str:
    """'shared/secure-coding' -> 'secure-coding'."""
    return reference.rsplit("/", 1)[-1]
