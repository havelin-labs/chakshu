"""Which Claude credential a review runs on.

Two kinds can be saved in Settings:
- an Anthropic API key (Console credits), and
- a Claude subscription token from `claude setup-token` (that person's Pro or Max limits).

The API key wins when both are set. With neither, the review uses whatever the
container environment provides (ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN, or
Bedrock/Vertex settings).
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


async def current(session: AsyncSession) -> Access:
    values = await store.get_many(session, Key.ANTHROPIC_API_KEY, Key.CLAUDE_OAUTH_TOKEN)
    return choose(values[Key.ANTHROPIC_API_KEY], values[Key.CLAUDE_OAUTH_TOKEN])
