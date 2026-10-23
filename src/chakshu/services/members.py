"""Keep `org_members` in step with who is in each installed organization.

The worker syncs on start and every 15 minutes, the `organization` webhook
applies single changes, and admins can ask for a sync from the People view.
If GitHub can't be reached, the last list stays and is reported as stale.
Display names need one call per person, so they're only fetched for people
with no name yet, and at most once a day each.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from githubkit.exception import GitHubException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, OrgMember, User
from chakshu.db.upsert import upsert
from chakshu.services import github
from chakshu.services import settings_store as store
from chakshu.services.github import AppCredentials
from chakshu.services.settings_store import Key

log = logging.getLogger(__name__)

SYNC_EVERY = timedelta(minutes=15)
NAME_REFRESH = timedelta(days=1)
NAMES_PER_SYNC = 100  # bounds the GET /users/{login} calls one sync makes


@dataclass(frozen=True)
class Member:
    login: str
    avatar_url: str | None
    org_role: str  # owner | member


async def fetch_org(creds: AppCredentials, installation_id: int, org: str) -> list[Member]:
    """Every member of `org`. Owners come from a second listing with role=admin."""
    client = github.installation_client(creds, installation_id)

    async def listing(role: str) -> list:
        return [
            user
            async for user in client.rest.paginate(
                client.rest.orgs.async_list_members, org=org, role=role, per_page=100
            )
        ]

    owners = {user.login for user in await listing("admin")}
    return [
        Member(user.login, user.avatar_url, "owner" if user.login in owners else "member")
        for user in await listing("all")
    ]


async def fetch_name(creds: AppCredentials, installation_id: int, login: str) -> str | None:
    client = github.installation_client(creds, installation_id)
    return (await client.rest.users.async_get_by_username(login)).parsed_data.name


async def _org_installs(session: AsyncSession) -> list[Installation]:
    return list(
        (
            await session.scalars(
                select(Installation).where(
                    Installation.account_type == "Organization", Installation.suspended.is_(False)
                )
            )
        ).all()
    )


async def sync(session: AsyncSession, creds: AppCredentials) -> dict:
    """Replace the member list with GitHub's. Returns the members source the People view reports."""
    installs = await _org_installs(session)
    found: dict[str, Member] = {}
    try:
        for install in installs:
            for member in await fetch_org(creds, install.github_id, install.account_login):
                seen = found.get(member.login.lower())
                if seen is None or member.org_role == "owner":  # an owner of any installed org
                    found[member.login.lower()] = member
    except GitHubException:
        log.warning("Couldn't list organization members; keeping the last list", exc_info=True)
        await store.put(session, Key.MEMBERS_STALE, "true")
        await session.commit()
        return await source(session)

    now = datetime.now(UTC)
    # A login GitHub now spells differently replaces the old row, since login is the key.
    await session.execute(
        OrgMember.__table__.delete().where(
            OrgMember.login_lower.in_(list(found)),
            OrgMember.login.not_in([m.login for m in found.values()]),
        )
    )
    await upsert(
        session,
        OrgMember,
        [
            {
                "login": m.login,
                "login_lower": key,
                "avatar_url": m.avatar_url,
                "org_role": m.org_role,
                "in_org": True,
                "synced_at": now,
            }
            for key, m in found.items()
        ],
        key="login",
    )
    await session.execute(
        update(OrgMember).where(OrgMember.login_lower.not_in(list(found))).values(in_org=False, synced_at=now)
    )
    if installs:
        await _fill_names(session, creds, installs[0].github_id, now)
    await store.put_many(session, {Key.MEMBERS_SYNCED_AT: now.isoformat(), Key.MEMBERS_STALE: "false"})
    await session.commit()
    log.info("Synced %s organization member(s)", len(found))
    return await source(session)


async def _fill_names(
    session: AsyncSession, creds: AppCredentials, installation_id: int, now: datetime
) -> None:
    named_users = select(func.lower(User.login)).where(User.name.is_not(None))
    due = (
        await session.scalars(
            select(OrgMember)
            .where(
                OrgMember.in_org.is_(True),
                OrgMember.name.is_(None),
                OrgMember.login_lower.not_in(named_users),
                (OrgMember.name_checked_at.is_(None)) | (OrgMember.name_checked_at < now - NAME_REFRESH),
            )
            .order_by(OrgMember.name_checked_at.nulls_first(), OrgMember.login_lower)
            .limit(NAMES_PER_SYNC)
        )
    ).all()
    for member in due:
        try:
            member.name = await fetch_name(creds, installation_id, member.login)
        except GitHubException:
            log.info("Couldn't look up the name of %s", member.login, exc_info=True)
        member.name_checked_at = now


async def mark_added(session: AsyncSession, login: str, avatar_url: str | None, role: str | None) -> None:
    """From the organization webhook's member_added. The caller commits."""
    now = datetime.now(UTC)
    await session.execute(
        OrgMember.__table__.delete().where(OrgMember.login_lower == login.lower(), OrgMember.login != login)
    )
    await upsert(
        session,
        OrgMember,
        {
            "login": login,
            "login_lower": login.lower(),
            "avatar_url": avatar_url,
            "org_role": "owner" if role == "admin" else "member",
            "in_org": True,
            "synced_at": now,
        },
        key="login",
    )


async def mark_removed(session: AsyncSession, login: str) -> None:
    """From the organization webhook's member_removed. The caller commits."""
    await session.execute(
        update(OrgMember)
        .where(OrgMember.login_lower == login.lower())
        .values(in_org=False, synced_at=datetime.now(UTC))
    )


async def source(session: AsyncSession) -> dict:
    """When the member list was last fetched, and whether the latest attempt failed."""
    values = await store.get_many(session, Key.MEMBERS_SYNCED_AT, Key.MEMBERS_STALE)
    return {"synced_at": values[Key.MEMBERS_SYNCED_AT], "stale": values[Key.MEMBERS_STALE] == "true"}
