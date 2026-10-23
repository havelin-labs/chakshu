"""Admin settings. Secrets are write-only: the API returns whether they're set and a masked hint."""

import os
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from githubkit.exception import RequestFailed
from pydantic import BaseModel, Field, field_validator

from chakshu.api.deps import AdminDep, CredentialsDep, csrf_protect
from chakshu.core import crypto
from chakshu.core.config import get_settings as get_config
from chakshu.db.session import SessionDep
from chakshu.helpers import analytics as calc
from chakshu.helpers import workflow
from chakshu.helpers.urls import is_public_url
from chakshu.services import (
    actions_secrets,
    analytics,
    app_permissions,
    github,
    model_access,
    retention,
    setup,
    spend,
)
from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(csrf_protect)])


class SettingsUpdate(BaseModel):
    # Secrets: an empty string clears it; None leaves it as it is.
    anthropic_api_key: str | None = Field(default=None, max_length=300)
    claude_oauth_token: str | None = Field(default=None, max_length=500)
    default_model: str = Field(min_length=1, max_length=100)
    max_usd_per_review: float = Field(gt=0, le=100)
    # None means no monthly cap.
    monthly_cap_usd: float | None = Field(default=None, gt=0, le=1_000_000)
    reviewers_repo: str = Field(pattern=r"^[A-Za-z0-9._-]{1,100}$")
    # owner/repo@ref of the action the review workflow runs; None keeps the current one.
    actions_action: str | None = Field(default=None, pattern=r"^[\w.-]+/[\w.-]+(/[\w./-]+)?@[\w./-]+$")


# Write-only secrets: request field -> (setting, environment variable that can stand in for it)
SECRETS = {
    "anthropic_api_key": (Key.ANTHROPIC_API_KEY, model_access.API_KEY_ENV),
    "claude_oauth_token": (Key.CLAUDE_OAUTH_TOKEN, model_access.TOKEN_ENV),
}


def _secret_status(value: str | None, env_name: str) -> dict:
    return {"set": bool(value), "hint": crypto.mask(value), "from_env": bool(os.environ.get(env_name))}


async def _read(session: SessionDep) -> dict:
    values = await store.get_many(
        session,
        Key.DEFAULT_MODEL,
        Key.MAX_USD_PER_REVIEW,
        Key.REVIEWERS_REPO,
        Key.ACTIONS_ACTION,
        *(key for key, _ in SECRETS.values()),
    )
    budget = await spend.current(session)
    return {
        **{field: _secret_status(values[key], env) for field, (key, env) in SECRETS.items()},
        "access": (await model_access.current(session)).kind,
        "default_model": values[Key.DEFAULT_MODEL],
        "max_usd_per_review": float(values[Key.MAX_USD_PER_REVIEW] or 2),
        "monthly_cap_usd": float(budget.cap) if budget.cap is not None else None,
        "spend_this_month": float(budget.month_to_date),
        "reviewers_repo": values[Key.REVIEWERS_REPO],
        "actions_action": values[Key.ACTIONS_ACTION] or workflow.DEFAULT_ACTION,
        "runner_url": get_config().public_runner_url,
        "runner_public": is_public_url(get_config().public_runner_url),
        "webhooks": {
            "url": get_config().hook_url,
            "public": setup.webhooks_reachable(),
            "secret_set": bool(await store.get(session, Key.APP_WEBHOOK_SECRET)),
            "events": setup.APP_EVENTS,
        },
    }


@router.get("")
async def get_settings(session: SessionDep, _: AdminDep) -> dict:
    return await _read(session)


@router.put("")
async def update_settings(body: SettingsUpdate, session: SessionDep, _: AdminDep) -> dict:
    values: dict[Key, str | None] = {
        Key.DEFAULT_MODEL: body.default_model.strip(),
        Key.MAX_USD_PER_REVIEW: str(body.max_usd_per_review),
        Key.MONTHLY_CAP_USD: str(body.monthly_cap_usd) if body.monthly_cap_usd else None,
        Key.REVIEWERS_REPO: body.reviewers_repo.strip(),
    }
    if body.actions_action:
        values[Key.ACTIONS_ACTION] = body.actions_action
    changed_secret = False
    for field, (key, _) in SECRETS.items():
        submitted = getattr(body, field)
        if submitted is not None:
            values[key] = submitted.strip() or None
            changed_secret = True
    await store.put_many(session, values)
    await session.commit()
    result = await _read(session)
    creds = await github.load_credentials(session)
    if changed_secret and creds:
        # Reviews run in Actions with these as repository secrets, so a change goes out at once.
        result["secrets_sync"] = asdict(await actions_secrets.sync_all(session, creds))
    return result


@router.post("/actions/secrets")
async def sync_secrets(session: SessionDep, creds: CredentialsDep, _: AdminDep) -> dict:
    """Copy the Claude credential into every enabled repository's Actions secrets."""
    return asdict(await actions_secrets.sync_all(session, creds))


@router.get("/permissions")
async def permissions(session: SessionDep, creds: CredentialsDep, _: AdminDep) -> dict:
    """What the GitHub App is missing, in its own settings and in each installation."""
    report = await app_permissions.check(session, creds)
    return asdict(report) | {"ok": report.ok}


@router.post("/webhooks")
async def connect_webhooks(session: SessionDep, creds: CredentialsDep, _: AdminDep) -> dict:
    """Set the GitHub App's webhook URL and a new secret, so GitHub can deliver events here."""
    try:
        url = await setup.connect_webhooks(session, creds)
    except RequestFailed as exc:
        if exc.response.status_code == 404:
            # GitHub only creates an app's webhook once a URL is saved in its settings page.
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This GitHub App has no webhook yet. In its settings on GitHub, tick Webhook Active, "
                f"set the URL to {get_config().hook_url}, leave the secret empty and save. "
                "Then press Connect webhooks again.",
            ) from exc
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"GitHub refused the webhook settings ({exc.response.status_code})."
        ) from exc
    return {"url": url}


class AnalyticsSettingsUpdate(BaseModel):
    show_names: bool | None = None
    min_group: int | None = None
    # 0 keeps people on runs indefinitely; otherwise clear them after this many days.
    retention_days: int | None = Field(default=None, ge=0, le=retention.MAX_DAYS)
    export_people: bool | None = None

    @field_validator("min_group")
    @classmethod
    def _min_group(cls, value: int | None) -> int | None:
        if value is not None and not calc.valid_min_group(value):
            raise ValueError(
                f"Use {calc.MIN_GROUP_OFF} to show every group, "
                f"or a group size from {calc.MIN_GROUP_FLOOR} to {calc.MIN_GROUP_MAX}."
            )
        return value


@router.get("/analytics")
async def get_analytics_settings(session: SessionDep, _: AdminDep) -> dict:
    return asdict(await analytics.privacy(session))


@router.patch("/analytics")
async def update_analytics_settings(
    body: AnalyticsSettingsUpdate, session: SessionDep, user: AdminDep
) -> dict:
    """Name people in analytics or not, and the smallest group shown (1 turns hiding off). Audited."""
    old = asdict(await analytics.privacy(session))
    new = old | body.model_dump(exclude_none=True)
    if new["retention_days"] == 0:
        new["retention_days"] = None
    if new["retention_days"] is not None and new["retention_days"] < retention.MIN_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Keep people for at least {retention.MIN_DAYS} days, or use 0 to keep them.",
        )
    return await _save_privacy(session, user.login, "settings.analytics.update", old, new)


async def _save_privacy(session: SessionDep, login: str, action: str, old: dict, new: dict) -> dict:
    await store.put_many(
        session,
        {
            Key.ANALYTICS_SHOW_NAMES: "true" if new["show_names"] else "false",
            Key.ANALYTICS_MIN_GROUP: str(new["min_group"]),
            Key.ANALYTICS_RETENTION_DAYS: str(new["retention_days"]) if new["retention_days"] else None,
            Key.ANALYTICS_EXPORT_PEOPLE: "true" if new["export_people"] else "false",
        },
    )
    await analytics.record_access(session, login, action, "settings", {"old": old, "new": new})
    return new


WORKS_COUNCIL_MIN_GROUP = 10


@router.post("/analytics/works-council")
async def works_council_mode(session: SessionDep, user: AdminDep) -> dict:
    """One step for a works council or employee agreement: no names, larger groups, no person export."""
    old = asdict(await analytics.privacy(session))
    new = old | {
        "show_names": False,
        "min_group": max(old["min_group"], WORKS_COUNCIL_MIN_GROUP),
        "export_people": False,
    }
    return await _save_privacy(session, user.login, "settings.analytics.works_council", old, new)


@router.get("/analytics/audit")
async def analytics_audit(
    session: SessionDep, _: AdminDep, limit: int = Query(200, ge=1, le=1000)
) -> list[dict]:
    """Who looked at, exported or changed analytics about named people, newest first."""
    return await analytics.audit_log(session, limit)
