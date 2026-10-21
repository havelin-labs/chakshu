from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, Repo
from chakshu.services import installations
from chakshu.services.github import AppCredentials

Payload = dict[str, Any]


@dataclass
class Context:
    session: AsyncSession
    creds: AppCredentials
    delivery_id: str


async def installation_for(ctx: Context, payload: Payload) -> Installation | None:
    github_id = (payload.get("installation") or {}).get("id")
    if not github_id:
        return None
    row = await ctx.session.scalar(select(Installation).where(Installation.github_id == github_id))
    if row is None:
        await installations.sync_installation(ctx.session, ctx.creds, github_id)
        row = await ctx.session.scalar(select(Installation).where(Installation.github_id == github_id))
    return row


async def resolve(ctx: Context, payload: Payload) -> tuple[Installation, Repo] | None:
    """The installation and repo an event is about, creating rows we haven't seen yet."""
    installation = await installation_for(ctx, payload)
    repo_payload = payload.get("repository")
    if installation is None or installation.suspended or not repo_payload:
        return None
    repo = await installations.ensure_repo(ctx.session, ctx.creds, installation, repo_payload)
    return (installation, repo) if repo.enabled else None
