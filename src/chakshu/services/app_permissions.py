"""Compare what the GitHub App needs with what it has.

Two places can fall short: the app's own settings (what it asks for) and each
installation (what an owner accepted). Apps created before a feature needed a
permission have to be updated in GitHub, and owners then accept the change.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core.config import get_settings
from chakshu.db.models import Installation
from chakshu.services import github, setup
from chakshu.services.github import AppCredentials

LEVELS = {"read": 1, "write": 2, "admin": 3}


def missing(granted: dict[str, Any], required: dict[str, str] = setup.APP_PERMISSIONS) -> list[str]:
    """'name: level' for each required permission that's absent or too low."""
    return [
        f"{name}: {level}"
        for name, level in required.items()
        if LEVELS.get(str(granted.get(name) or ""), 0) < LEVELS[level]
    ]


def missing_events(granted: list[str], required: list[str] = setup.APP_EVENTS) -> list[str]:
    return [event for event in required if event not in set(granted)]


def _as_dict(permissions: Any) -> dict[str, Any]:
    if permissions is None:
        return {}
    return permissions if isinstance(permissions, dict) else permissions.model_dump(exclude_none=True)


@dataclass
class InstallationGap:
    account: str
    missing: list[str]
    missing_events: list[str]
    review_url: str  # where an owner accepts new permissions


@dataclass
class Report:
    settings_url: str  # the app's permissions page on GitHub
    missing: list[str] = field(default_factory=list)
    missing_events: list[str] = field(default_factory=list)
    installations: list[InstallationGap] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.missing_events or self.installations)


def _owner_path(login: str, account_type: str) -> str:
    return f"/organizations/{login}/settings" if account_type == "Organization" else "/settings"


async def check(session: AsyncSession, creds: AppCredentials) -> Report:
    base = get_settings().github_url
    app_client = github.app_client(creds)  # keep a reference: githubkit namespaces hold the client weakly
    app = (await app_client.rest.apps.async_get_authenticated()).parsed_data
    owner = getattr(app.owner, "login", None) or ""
    owner_type = getattr(app.owner, "type", None) or "Organization"
    report = Report(
        settings_url=f"{base}{_owner_path(owner, owner_type)}/apps/{app.slug}/permissions",
        missing=missing(_as_dict(app.permissions)),
        missing_events=missing_events(list(app.events or [])),
    )
    installs = (await session.scalars(select(Installation).where(Installation.suspended.is_(False)))).all()
    for row in installs:
        live = (await app_client.rest.apps.async_get_installation(row.github_id)).parsed_data
        gap = InstallationGap(
            account=row.account_login,
            missing=missing(_as_dict(live.permissions)),
            missing_events=missing_events(list(live.events or [])),
            review_url=f"{base}{_owner_path(row.account_login, row.account_type)}"
            f"/installations/{row.github_id}",
        )
        if gap.missing or gap.missing_events:
            report.installations.append(gap)
    return report
