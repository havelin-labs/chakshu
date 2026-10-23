"""Talk to the Chakshu server from inside a GitHub Actions job."""

import asyncio
import os
import uuid
from typing import Any

import httpx
from pydantic import BaseModel

from chakshu.connectors import ToolError
from chakshu.runner.protocol import API_PREFIX, Failure, Job, Result, ToolCall, ToolReply

TIMEOUT = httpx.Timeout(60.0, connect=15.0)
RETRIES = 4


class ServerError(RuntimeError):
    pass


class OidcTokens:
    """Mints GitHub Actions OIDC tokens for one audience.

    The request URL and token are taken out of the environment at start-up, so
    the review agent (a child process) never inherits them.
    """

    URL_ENV = "ACTIONS_ID_TOKEN_REQUEST_URL"
    TOKEN_ENV = "ACTIONS_ID_TOKEN_REQUEST_TOKEN"

    def __init__(self, request_url: str, request_token: str, audience: str):
        self._url, self._token, self._audience = request_url, request_token, audience

    @classmethod
    def from_env(cls, audience: str) -> "OidcTokens":
        url, token = os.environ.pop(cls.URL_ENV, ""), os.environ.pop(cls.TOKEN_ENV, "")
        if not (url and token):
            raise ServerError("No OIDC token available. The workflow needs `permissions: id-token: write`.")
        return cls(url, token, audience)

    async def get(self, http: httpx.AsyncClient) -> str:
        resp = await http.get(
            self._url, params={"audience": self._audience}, headers={"Authorization": f"Bearer {self._token}"}
        )
        resp.raise_for_status()
        return resp.json()["value"]


class ServerClient:
    def __init__(self, server: str, run_id: uuid.UUID, tokens: OidcTokens, http: httpx.AsyncClient):
        self._base = f"{server.rstrip('/')}{API_PREFIX}/{run_id}"
        self._tokens = tokens
        self._http = http

    async def _post(self, path: str, body: BaseModel | None = None) -> dict[str, Any]:
        """POST with a fresh token, retrying network errors and 5xx. 4xx errors are final."""
        payload = body.model_dump(mode="json") if body else {}
        for attempt in range(RETRIES):
            try:
                token = await self._tokens.get(self._http)
                resp = await self._http.post(
                    f"{self._base}{path}", json=payload, headers={"Authorization": f"Bearer {token}"}
                )
            except httpx.TransportError as exc:
                error: str = f"can't reach Chakshu: {exc}"
            else:
                if resp.is_success:
                    return resp.json()
                detail = resp.json().get("detail") if "json" in resp.headers.get("content-type", "") else None
                error = f"{resp.status_code} {detail or resp.text[:300]}"
                if resp.status_code < 500:
                    raise ServerError(error)
            if attempt < RETRIES - 1:
                await asyncio.sleep(2**attempt * 2)
        raise ServerError(error)

    async def job(self) -> Job:
        return Job.model_validate(await self._post("/job"))

    async def call_tool(self, connector: str, tool: str, args: dict[str, Any]) -> str:
        reply = ToolReply.model_validate(await self._post(f"/tools/{connector}/{tool}", ToolCall(args=args)))
        if reply.is_error:
            raise ToolError(reply.text)
        return reply.text

    async def result(self, result: Result) -> str | None:
        return (await self._post("/result", result)).get("review_url")

    async def failure(self, failure: Failure) -> None:
        await self._post("/failure", failure)


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": "chakshu-action"})
