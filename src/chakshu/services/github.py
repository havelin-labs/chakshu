"""GitHub clients for the app itself, its installations and signed-in users.

Every other module gets a client from here, so base URLs (GitHub Enterprise
Server) and auth strategies are decided in one place.
"""

import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from githubkit import (
    AppAuthStrategy,
    GitHub,
    OAuthAppAuthStrategy,
    TokenAuthStrategy,
    UnauthAuthStrategy,
)
from githubkit.auth.base import BaseAuthStrategy
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core import ids
from chakshu.core.config import get_settings
from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key


class NotConfiguredError(RuntimeError):
    """The GitHub App hasn't been created yet."""


@dataclass(frozen=True)
class AppCredentials:
    app_id: int
    slug: str
    client_id: str
    client_secret: str
    private_key: str
    webhook_secret: str | None

    @property
    def namespace(self) -> uuid.UUID:
        """Root of every deterministic ID in this install."""
        return ids.instance_ns(github_host(), self.app_id)


def github_host() -> str:
    return urlparse(get_settings().github_url).hostname or "github.com"


def install_url(slug: str) -> str:
    return f"{get_settings().github_url}/apps/{slug}/installations/new"


async def load_credentials(session: AsyncSession) -> AppCredentials | None:
    values = await store.get_many(
        session,
        Key.APP_ID,
        Key.APP_SLUG,
        Key.APP_CLIENT_ID,
        Key.APP_CLIENT_SECRET,
        Key.APP_PRIVATE_KEY,
        Key.APP_WEBHOOK_SECRET,
    )
    if not (values[Key.APP_ID] and values[Key.APP_PRIVATE_KEY]):
        return None
    return AppCredentials(
        app_id=int(values[Key.APP_ID]),
        slug=values[Key.APP_SLUG] or "",
        client_id=values[Key.APP_CLIENT_ID] or "",
        client_secret=values[Key.APP_CLIENT_SECRET] or "",
        private_key=values[Key.APP_PRIVATE_KEY],
        webhook_secret=values[Key.APP_WEBHOOK_SECRET],
    )


async def require_credentials(session: AsyncSession) -> AppCredentials:
    creds = await load_credentials(session)
    if creds is None:
        raise NotConfiguredError("Connect Chakshu to GitHub first.")
    return creds


def _client(auth: BaseAuthStrategy) -> GitHub:
    return GitHub(auth, base_url=get_settings().github_api_url)


def unauth_client() -> GitHub:
    return _client(UnauthAuthStrategy())


def app_client(creds: AppCredentials) -> GitHub:
    return _client(AppAuthStrategy(str(creds.app_id), creds.private_key))


def installation_client(creds: AppCredentials, installation_id: int) -> GitHub:
    app = app_client(creds)
    return app.with_auth(app.auth.as_installation(installation_id))


def oauth_client(creds: AppCredentials) -> GitHub:
    return _client(OAuthAppAuthStrategy(creds.client_id, creds.client_secret))


def user_client(token: str) -> GitHub:
    return _client(TokenAuthStrategy(token))


async def installation_token(creds: AppCredentials, installation_id: int) -> str:
    """Short-lived token for git operations (clones), valid for about an hour."""
    resp = await app_client(creds).rest.apps.async_create_installation_access_token(installation_id)
    return resp.parsed_data.token
