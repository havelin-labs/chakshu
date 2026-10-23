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

SKILLS_DIR = ".claude/skills"
MAX_BUNDLE_BYTES = 2_000_000

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


class BundleTooLarge(ValueError):
    pass


def skill_files(skill_dirs: dict[str, Path], max_bytes: int = MAX_BUNDLE_BYTES) -> dict[str, str]:
    """Text files in each skill folder, keyed by where they go: .claude/skills/<name>/<file>.

    Symlinks and binary files are skipped; neither is something a reviewer reads.
    """
    files: dict[str, str] = {}
    total = 0
    for name, source in sorted(skill_dirs.items()):
        for path in sorted(source.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            total += len(text.encode())
            if total > max_bytes:
                raise BundleTooLarge(f"The skills are over {max_bytes // 1_000_000} MB of text.")
            files[f"{SKILLS_DIR}/{name}/{path.relative_to(source).as_posix()}"] = text
    return files


def write_files(workspace: Path, files: dict[str, str]) -> None:
    """Write the server's files (CLAUDE.md, skills) into the workspace, never into code/ or outside it."""
    root = workspace.resolve()
    code = (workspace / "code").resolve()
    for relative, text in files.items():
        target = (workspace / relative).resolve()
        if Path(relative).is_absolute() or not target.is_relative_to(root) or target.is_relative_to(code):
            raise ValueError(f"Refusing to write {relative!r} outside the workspace")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def skill_name(reference: str) -> str:
    """'shared/secure-coding' -> 'secure-coding'."""
    return reference.rsplit("/", 1)[-1]
