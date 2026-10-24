"""Keep `github_teams` and dated `team_memberships` in step with GitHub.

Only direct members count: someone in a child team isn't counted in its parent.
A membership opens when Chakshu first sees it and closes when it's gone, so a
run stays with the teams its people were in at the time. Memberships found on
the first sync of an organization have no start date, since they began before
Chakshu was watching. The worker syncs nightly, the `team` and `membership`
webhooks apply single changes, and admins can ask for a sync from the Teams view.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from githubkit.exception import GitHubException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import GithubTeam, Installation, TeamMembership
from chakshu.db.upsert import upsert
from chakshu.services import github
from chakshu.services import settings_store as store
from chakshu.services.github import AppCredentials
from chakshu.services.settings_store import Key

log = logging.getLogger(__name__)

SYNC_EVERY = timedelta(days=1)

TEAMS_QUERY = """
query($org: String!, $after: String) {
  organization(login: $org) {
    teams(first: 50, after: $after) {
      nodes {
        databaseId slug name
        parentTeam { databaseId }
        members(first: 100, membership: IMMEDIATE) {
          nodes { login }
          pageInfo { hasNextPage endCursor }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

MEMBERS_QUERY = """
query($org: String!, $slug: String!, $after: String) {
  organization(login: $org) {
    team(slug: $slug) {
      members(first: 100, after: $after, membership: IMMEDIATE) {
        nodes { login }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class Team:
    id: int
    slug: str
    name: str
    parent_id: int | None
    members: list[str] = field(default_factory=list)  # logins of direct members


async def fetch_org(creds: AppCredentials, installation_id: int, org: str) -> list[Team]:
    """Every team in `org` with its direct members."""
    client = github.installation_client(creds, installation_id)
    teams, after = [], None
    while True:
        page = (await client.async_graphql(TEAMS_QUERY, {"org": org, "after": after}))["organization"][
            "teams"
        ]
        for node in page["nodes"]:
            members = node["members"]
            logins = [m["login"] for m in members["nodes"]]
            cursor = members["pageInfo"]["endCursor"] if members["pageInfo"]["hasNextPage"] else None
            while cursor:
                more = (
                    await client.async_graphql(
                        MEMBERS_QUERY, {"org": org, "slug": node["slug"], "after": cursor}
                    )
                )["organization"]["team"]["members"]
                logins += [m["login"] for m in more["nodes"]]
                cursor = more["pageInfo"]["endCursor"] if more["pageInfo"]["hasNextPage"] else None
            parent = node.get("parentTeam") or {}
            teams.append(
                Team(node["databaseId"], node["slug"], node["name"], parent.get("databaseId"), logins)
            )
        if not page["pageInfo"]["hasNextPage"]:
            return teams
        after = page["pageInfo"]["endCursor"]


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


async def _save_team(session: AsyncSession, install: Installation, team: Team, now: datetime) -> None:
    await upsert(
        session,
        GithubTeam,
        {
            "id": team.id,
            "installation_id": install.id,
            "org": install.account_login,
            "slug": team.slug,
            "name": team.name,
            "parent_id": team.parent_id,
            "deleted_at": None,
            "synced_at": now,
        },
    )


async def _open(session: AsyncSession, team_id: int) -> dict[str, TeamMembership]:
    rows = await session.scalars(
        select(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.valid_to.is_(None))
    )
    return {m.login_lower: m for m in rows.all()}


def _start(session: AsyncSession, team_id: int, login: str, since: datetime | None) -> None:
    session.add(
        TeamMembership(
            id=uuid.uuid4(), team_id=team_id, login=login, login_lower=login.lower(), valid_from=since
        )
    )


async def _close_team(session: AsyncSession, team_id: int, now: datetime) -> None:
    await session.execute(
        update(TeamMembership)
        .where(TeamMembership.team_id == team_id, TeamMembership.valid_to.is_(None))
        .values(valid_to=now)
    )


async def sync(session: AsyncSession, creds: AppCredentials) -> dict:
    """Bring teams and memberships in line with GitHub. Returns the teams source the Teams view reports."""
    now = datetime.now(UTC)
    for install in await _org_installs(session):
        try:
            fetched = await fetch_org(creds, install.github_id, install.account_login)
        except GitHubException:
            log.warning(
                "Couldn't list the teams of %s; keeping the last list", install.account_login, exc_info=True
            )
            await store.put(session, Key.TEAMS_STALE, "true")
            await session.commit()
            return await source(session)
        known = set(
            (
                await session.scalars(select(GithubTeam.id).where(GithubTeam.installation_id == install.id))
            ).all()
        )
        first_sync = not known
        for team in fetched:
            await _save_team(session, install, team, now)
            current = await _open(session, team.id)
            found = {login.lower(): login for login in team.members}
            for key, membership in current.items():
                if key not in found:
                    membership.valid_to = now
            for key, login in found.items():
                if key not in current:
                    _start(session, team.id, login, None if first_sync else now)
        gone = known - {t.id for t in fetched}
        for team_id in gone:
            await _close_team(session, team_id, now)
        if gone:
            await session.execute(
                update(GithubTeam)
                .where(GithubTeam.id.in_(gone), GithubTeam.deleted_at.is_(None))
                .values(deleted_at=now, synced_at=now)
            )
        await session.flush()
    await store.put_many(session, {Key.TEAMS_SYNCED_AT: now.isoformat(), Key.TEAMS_STALE: "false"})
    await session.commit()
    log.info("Synced organization teams")
    return await source(session)


def _team_of(payload_team: dict) -> Team:
    parent = payload_team.get("parent") or {}
    return Team(payload_team["id"], payload_team["slug"], payload_team["name"], parent.get("id"))


async def apply_team(session: AsyncSession, install: Installation, action: str, payload_team: dict) -> None:
    """From the `team` webhook. The caller commits."""
    now = datetime.now(UTC)
    if action == "deleted":
        await _close_team(session, payload_team["id"], now)
        await session.execute(
            update(GithubTeam)
            .where(GithubTeam.id == payload_team["id"])
            .values(deleted_at=now, synced_at=now)
        )
    elif action in ("created", "edited"):
        await _save_team(session, install, _team_of(payload_team), now)


async def apply_membership(
    session: AsyncSession, install: Installation, action: str, payload_team: dict, login: str
) -> None:
    """From the `membership` webhook (direct membership of a team). The caller commits."""
    now = datetime.now(UTC)
    if payload_team.get("deleted"):
        return  # the team webhook closes everything when a team is deleted
    await _save_team(session, install, _team_of(payload_team), now)
    current = await _open(session, payload_team["id"])
    if action == "added" and login.lower() not in current:
        _start(session, payload_team["id"], login, now)
    elif action == "removed" and (membership := current.get(login.lower())):
        membership.valid_to = now


async def options(session: AsyncSession) -> list[dict]:
    """Teams for the filter, live ones first, with the org they belong to."""
    rows = await session.scalars(
        select(GithubTeam).order_by(GithubTeam.deleted_at.is_not(None), GithubTeam.org, GithubTeam.name)
    )
    return [
        {"id": t.id, "org": t.org, "slug": t.slug, "name": t.name, "deleted": t.deleted_at is not None}
        for t in rows.all()
    ]


async def source(session: AsyncSession) -> dict:
    values = await store.get_many(session, Key.TEAMS_SYNCED_AT, Key.TEAMS_STALE)
    return {"synced_at": values[Key.TEAMS_SYNCED_AT], "stale": values[Key.TEAMS_STALE] == "true"}
