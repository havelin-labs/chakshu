"""Check that a request comes from a GitHub Actions run, using the run's OIDC token.

The runner asks GitHub for a token whose audience is this server's runner URL.
GitHub signs it and puts the repository and run ID in it, so the server knows
which Actions run is calling without any shared secret in the repository.
"""

import asyncio
from dataclasses import dataclass
from functools import lru_cache

import jwt

from chakshu.core.config import get_settings

LEEWAY_SECONDS = 30
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "repository", "repository_id", "run_id", "workflow_ref"]


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class RunnerIdentity:
    repository: str  # owner/name
    repository_id: int
    run_id: int  # the Actions run
    workflow_ref: str  # owner/name/.github/workflows/<file>@<ref>
    event_name: str


def audience() -> str:
    return get_settings().public_runner_url


@lru_cache
def _jwks(issuer: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{issuer}/.well-known/jwks", cache_keys=True, lifespan=3600)


def decode(token: str, key, *, issuer: str, aud: str) -> RunnerIdentity:
    """Validate signature, issuer, audience and expiry, then read the claims we use."""
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=aud,
            issuer=issuer,
            leeway=LEEWAY_SECONDS,
            options={"require": REQUIRED_CLAIMS},
        )
        return RunnerIdentity(
            repository=str(claims["repository"]),
            repository_id=int(claims["repository_id"]),
            run_id=int(claims["run_id"]),
            workflow_ref=str(claims["workflow_ref"]),
            event_name=str(claims.get("event_name") or ""),
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidToken(str(exc)) from exc


async def verify(token: str) -> RunnerIdentity:
    issuer = get_settings().oidc_issuer
    try:
        signing_key = await asyncio.to_thread(_jwks(issuer).get_signing_key_from_jwt, token)
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    return decode(token, signing_key.key, issuer=issuer, aud=audience())
