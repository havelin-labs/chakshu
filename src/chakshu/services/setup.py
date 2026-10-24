"""First-run setup: claim the instance, then create the GitHub App from a manifest.

https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest
"""

import hmac
import secrets
from typing import Any
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core.config import get_settings
from chakshu.helpers.urls import is_public_url
from chakshu.services import github
from chakshu.services import settings_store as store
from chakshu.services.github import AppCredentials
from chakshu.services.settings_store import Key

# No 0/O or 1/I, so a code read from a log is hard to mistype.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

APP_PERMISSIONS = {
    # write: open pull requests with the workflow and with reviewer changes; never pushes to a default branch
    "contents": "write",
    "pull_requests": "write",
    "checks": "write",
    "issues": "write",
    "members": "write",  # list members and owners; create the empty chakshu team during setup
    "metadata": "read",
    "actions": "write",  # start the review workflow and hear when it ends
    "workflows": "write",  # propose .github/workflows/chakshu.yml
    "secrets": "write",  # keep the Claude credential in each repo's Actions secrets
}
# pull_request_review_comment: someone replied to one of Chakshu's review comments
# organization: members joining and leaving, for the People directory
# team, membership: teams and who is directly in them, for the Teams view
# pull_request_review: when a person first reviews a PR, for review speed
APP_EVENTS = [
    "pull_request",
    "issue_comment",
    "pull_request_review_comment",
    "push",
    "workflow_run",
    "organization",
    "team",
    "membership",
    "pull_request_review",
]


def new_setup_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def _normalize(code: str) -> str:
    return code.strip().upper().replace(" ", "").replace("-", "")


async def ensure_setup_code(session: AsyncSession) -> str | None:
    """Return the setup code, creating one if needed. None once the app exists."""
    if await github.load_credentials(session):
        return None
    code = await store.get(session, Key.SETUP_CODE)
    if not code:
        code = new_setup_code()
        await store.put(session, Key.SETUP_CODE, code)
        await session.commit()
    return code


async def check_setup_code(session: AsyncSession, submitted: str) -> bool:
    expected = await store.get(session, Key.SETUP_CODE)
    return bool(expected) and hmac.compare_digest(_normalize(submitted), _normalize(expected))


def webhooks_reachable() -> bool:
    return is_public_url(get_settings().hook_url)


def build_manifest(name: str) -> dict[str, Any]:
    settings = get_settings()
    manifest: dict[str, Any] = {
        "name": name,
        "url": settings.base_url,
        "redirect_url": f"{settings.base_url}/api/setup/callback",
        "callback_urls": [f"{settings.base_url}/auth/callback"],
        "setup_url": f"{settings.base_url}/setup/installed",
        "setup_on_update": True,
        "public": False,
        "default_permissions": APP_PERMISSIONS,
    }
    # GitHub rejects webhook URLs it can't reach, so a laptop install
    # starts without webhooks. Portal-started reviews still work.
    if webhooks_reachable():
        manifest["hook_attributes"] = {"url": settings.hook_url, "active": True}
        manifest["default_events"] = APP_EVENTS
    return manifest


def manifest_action_url(org: str | None, state: str) -> str:
    base = get_settings().github_url
    path = f"/organizations/{quote(org)}/settings/apps/new" if org else "/settings/apps/new"
    return f"{base}{path}?state={quote(state)}"


async def connect_webhooks(session: AsyncSession, creds: AppCredentials) -> str:
    """Point the app's webhook at this instance with a fresh secret, and store the secret.

    For apps created without webhooks (e.g. on localhost). Returns the URL used.
    """
    url = get_settings().hook_url
    secret = secrets.token_urlsafe(32)
    client = github.app_client(creds)  # keep a reference: githubkit namespaces hold the client weakly
    await client.rest.apps.async_update_webhook_config_for_app(url=url, secret=secret, content_type="json")
    await store.put(session, Key.APP_WEBHOOK_SECRET, secret)
    await session.commit()
    return url


async def complete_manifest(session: AsyncSession, code: str) -> AppCredentials:
    """Swap the one-time manifest code for the app's credentials and store them."""
    client = github.unauth_client()  # keep a reference: githubkit namespaces hold the client weakly
    app = (await client.rest.apps.async_create_from_manifest(code)).parsed_data
    await store.put_many(
        session,
        {
            Key.APP_ID: str(app.id),
            Key.APP_SLUG: app.slug or "",
            Key.APP_CLIENT_ID: app.client_id,
            Key.APP_CLIENT_SECRET: app.client_secret,
            Key.APP_PRIVATE_KEY: app.pem,
            Key.APP_WEBHOOK_SECRET: app.webhook_secret,
            Key.APP_OWNER: getattr(app.owner, "login", None) or "",
            Key.SETUP_CODE: None,
        },
    )
    await session.commit()
    return await github.require_credentials(session)
