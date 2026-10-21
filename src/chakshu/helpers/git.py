"""Shallow, single-commit checkouts with a token that never touches disk.

The token goes in as a one-off `-c http.extraheader`, so it isn't written into
.git/config where a review agent could read it.
"""

import asyncio
import base64
import os
from pathlib import Path


class GitError(RuntimeError):
    pass


def _auth_args(token: str | None) -> list[str]:
    if not token:
        return []
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.extraheader=AUTHORIZATION: basic {basic}"]


async def git(cwd: Path, *args: str, token: str | None = None) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    process = await asyncio.create_subprocess_exec(
        "git",
        *_auth_args(token),
        *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise GitError(f"git {args[0]} failed: {stderr.decode(errors='replace').strip()}")
    return stdout.decode()


async def checkout(clone_url: str, sha: str, dest: Path, token: str | None = None) -> Path:
    """Fetch exactly one commit into `dest` (created if needed) and check it out."""
    await asyncio.to_thread(dest.mkdir, parents=True, exist_ok=True)
    await git(dest, "init", "-q")
    await git(dest, "remote", "add", "origin", clone_url)
    await git(dest, "fetch", "-q", "--depth=1", "--no-tags", "origin", sha, token=token)
    await git(dest, "checkout", "-q", "--detach", "FETCH_HEAD")
    return dest
