"""Sign-in with GitHub and the admin rule."""

import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core import crypto, ids
from chakshu.core.config import get_settings
from chakshu.db.models import Installation, User
from chakshu.db.upsert import upsert
from chakshu.services import github, orgs
from chakshu.services.github import AppCredentials

log = logging.getLogger(__name__)


class SignInRefused(Exception):
    """The GitHub account isn't part of any org or account this install serves."""


def authorize_url(creds: AppCredentials, state: str) -> str:
    settings = get_settings()
    query = urlencode(
        {"client_id": creds.client_id, "redirect_uri": f"{settings.base_url}/auth/callback", "state": state}
    )
    return f"{settings.github_url}/login/oauth/authorize?{query}"


async def access(session: AsyncSession, creds: AppCredentials, login: str) -> tuple[bool, bool]:
    """(allowed, is_admin) for a GitHub login.

    Allowed: a member of an installed org, the owner of an installed personal
    account, or listed in CHAKSHU_ADMINS. Admin: an org owner, the personal
    account owner, or listed in CHAKSHU_ADMINS.
    """
    if login.lower() in get_settings().admin_logins:
        return True, True
    allowed = False
    installs = (await session.scalars(select(Installation).where(Installation.suspended.is_(False)))).all()
    for install in installs:
        if install.account_type == "User":
            if install.account_login.lower() == login.lower():
                return True, True
            continue
        role = await orgs.org_role(creds, install.github_id, install.account_login, login)
        if role == "admin":
            return True, True
        allowed = allowed or role == "member"
    return allowed, False


async def sign_in(session: AsyncSession, creds: AppCredentials, code: str) -> User:
    oauth = github.oauth_client(creds)
    token = (await oauth.auth.as_web_user(code).async_exchange_token(oauth)).token
    profile = (await github.user_client(token).rest.users.async_get_authenticated()).parsed_data

    allowed, is_admin = await access(session, creds, profile.login)
    if not allowed:
        raise SignInRefused(profile.login)

    user_id = ids.eid(creds.namespace, "user", profile.id)
    await upsert(
        session,
        User,
        {
            "id": user_id,
            "github_id": profile.id,
            "login": profile.login,
            "name": profile.name,
            "avatar_url": profile.avatar_url,
            "is_admin": is_admin,
            "token_enc": crypto.encrypt(token),
            "last_login_at": datetime.now(UTC),
        },
    )
    await session.commit()
    log.info("%s signed in%s", profile.login, " as admin" if is_admin else "")
    return await session.get(User, user_id, populate_existing=True)


def public(user: User) -> dict:
    return {"login": user.login, "name": user.name, "avatar_url": user.avatar_url, "is_admin": user.is_admin}
