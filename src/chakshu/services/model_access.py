"""Which Claude credential reviews run on.

Two kinds can be saved in Settings:
- an Anthropic API key (Console credits), and
- a Claude subscription token from `claude setup-token` (that person's Pro or Max limits).

The API key wins when both are set. With neither, the server's own environment
(ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN) stands in. Reviews run in GitHub
Actions, so Chakshu copies these values into each repository's Actions secrets
(see services/actions_secrets.py).
"""

import os
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key

API_KEY_ENV = "ANTHROPIC_API_KEY"
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
PROVIDER_ENV = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")


@dataclass(frozen=True)
class Access:
    kind: str  # api_key | subscription | environment | none
    env: dict[str, str] = field(default_factory=dict)  # variables to hand the agent


def choose(api_key: str | None, token: str | None, environ: dict[str, str] | None = None) -> Access:
    environ = os.environ if environ is None else environ
    if api_key:
        return Access("api_key", {API_KEY_ENV: api_key})
    if token:
        return Access("subscription", {TOKEN_ENV: token})
    if any(environ.get(name) for name in (API_KEY_ENV, TOKEN_ENV, *PROVIDER_ENV)):
        return Access("environment")
    return Access("none")


async def credentials(session: AsyncSession) -> dict[str, str | None]:
    """The API key and token runners should get: from Settings, else this server's environment."""
    values = await store.get_many(session, Key.ANTHROPIC_API_KEY, Key.CLAUDE_OAUTH_TOKEN)
    return {
        API_KEY_ENV: values[Key.ANTHROPIC_API_KEY] or os.environ.get(API_KEY_ENV) or None,
        TOKEN_ENV: values[Key.CLAUDE_OAUTH_TOKEN] or os.environ.get(TOKEN_ENV) or None,
    }


async def current(session: AsyncSession) -> Access:
    values = await store.get_many(session, Key.ANTHROPIC_API_KEY, Key.CLAUDE_OAUTH_TOKEN)
    return choose(values[Key.ANTHROPIC_API_KEY], values[Key.CLAUDE_OAUTH_TOKEN])
