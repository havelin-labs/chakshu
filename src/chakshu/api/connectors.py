"""Admin CRUD for connectors. Secrets are write-only."""

import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from chakshu.api.deps import AdminDep, CredentialsDep, csrf_protect
from chakshu.connectors import KINDS
from chakshu.core import crypto
from chakshu.db.session import SessionDep
from chakshu.services import connectors

router = APIRouter(prefix="/api/connectors", tags=["connectors"], dependencies=[Depends(csrf_protect)])


class ConnectorBody(BaseModel):
    kind: str
    base_url: str = Field(pattern=r"^https://", max_length=300)
    username: str | None = Field(default=None, max_length=200)
    # None keeps the stored secret; "" clears it.
    secret: str | None = Field(default=None, max_length=500)
    enabled: bool = True


def _check_name(name: str) -> None:
    if not re.fullmatch(connectors.NAME_PATTERN, name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use lowercase letters, digits and dashes.")


async def _require(session: SessionDep, name: str):
    row = await connectors.get(session, name)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No connector with that name.")
    return row


@router.get("")
async def list_connectors(session: SessionDep, _: AdminDep) -> dict:
    rows = await connectors.list_all(session)
    return {
        "kinds": {key: kind.label for key, kind in KINDS.items()},
        "connectors": [
            {
                "name": r.name,
                "kind": r.kind,
                "base_url": r.base_url,
                "username": r.username,
                "secret_hint": crypto.mask(crypto.decrypt(r.secret_enc)),
                "enabled": r.enabled,
            }
            for r in rows
        ],
    }


@router.put("/{name}")
async def save_connector(
    name: str, body: ConnectorBody, session: SessionDep, creds: CredentialsDep, _: AdminDep
) -> dict:
    _check_name(name)
    if body.kind not in KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown kind '{body.kind}'.")
    await connectors.save(session, creds, name=name, **body.model_dump())
    await session.commit()
    return {"ok": True}


@router.delete("/{name}")
async def delete_connector(name: str, session: SessionDep, _: AdminDep) -> dict:
    await connectors.remove(session, name)
    await session.commit()
    return {"ok": True}


@router.post("/{name}/check")
async def check_connector(name: str, session: SessionDep, _: AdminDep) -> dict:
    row = await _require(session, name)
    try:
        message = await KINDS[row.kind].check(connectors.config(row))
    except httpx.HTTPError as exc:
        return {"ok": False, "message": f"Couldn't connect: {exc}"}
    return {"ok": True, "message": message}
