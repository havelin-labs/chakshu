"""Admin settings. Secrets are write-only: the API returns whether they're set and a masked hint."""

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from chakshu.api.deps import AdminDep, csrf_protect
from chakshu.core import crypto
from chakshu.db.session import SessionDep
from chakshu.services import settings_store as store
from chakshu.services import spend
from chakshu.services.settings_store import Key

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(csrf_protect)])


class SettingsUpdate(BaseModel):
    # Empty string clears the key; None leaves it as it is.
    anthropic_api_key: str | None = Field(default=None, max_length=300)
    default_model: str = Field(min_length=1, max_length=100)
    max_usd_per_review: float = Field(gt=0, le=100)
    # None means no monthly cap.
    monthly_cap_usd: float | None = Field(default=None, gt=0, le=1_000_000)
    reviewers_repo: str = Field(pattern=r"^[A-Za-z0-9._-]{1,100}$")


async def _read(session: SessionDep) -> dict:
    values = await store.get_many(
        session, Key.ANTHROPIC_API_KEY, Key.DEFAULT_MODEL, Key.MAX_USD_PER_REVIEW, Key.REVIEWERS_REPO
    )
    key = values[Key.ANTHROPIC_API_KEY]
    budget = await spend.current(session)
    return {
        "anthropic_api_key": {
            "set": bool(key),
            "hint": crypto.mask(key),
            "from_env": bool(os.environ.get("ANTHROPIC_API_KEY")),
        },
        "default_model": values[Key.DEFAULT_MODEL],
        "max_usd_per_review": float(values[Key.MAX_USD_PER_REVIEW] or 2),
        "monthly_cap_usd": float(budget.cap) if budget.cap is not None else None,
        "spend_this_month": float(budget.month_to_date),
        "reviewers_repo": values[Key.REVIEWERS_REPO],
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
    if body.anthropic_api_key is not None:
        values[Key.ANTHROPIC_API_KEY] = body.anthropic_api_key.strip() or None
    await store.put_many(session, values)
    await session.commit()
    return await _read(session)
