from __future__ import annotations

import hmac
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..db.models import Agent, IdemRecord, Owner
from ..paypal import Rail, get_rail
from ..seed import hash_key
from ..verifier.llm import get_llm


def rail_dep() -> Rail:
    return get_rail()


def llm_dep():
    return get_llm()


def agent_auth(authorization: str = Header(default=""), s: Session = Depends(get_session)) -> Agent:
    tok = authorization.removeprefix("Bearer ").strip()
    agent = s.scalar(select(Agent).where(Agent.api_key_hash == hash_key(tok))) if tok else None
    if not agent or agent.status != "active":
        raise HTTPException(401, "invalid or revoked agent key")
    return agent


def owner_auth(authorization: str = Header(default=""), x_owner_id: str | None = Header(default=None),
               s: Session = Depends(get_session)) -> Owner:
    admin = settings().admin_token
    tok = authorization.removeprefix("Bearer ").strip()
    if not admin or not hmac.compare_digest(tok, admin):
        raise HTTPException(401, "invalid admin token")
    owner = s.get(Owner, x_owner_id) if x_owner_id else s.scalar(select(Owner).order_by(Owner.id))
    if not owner:
        raise HTTPException(404, "no owner; run the seed script")
    return owner


def idem_key(idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key")) -> str:
    return idempotency_key


def idem_run(s: Session, scope: str, key: str, fn: Callable[[], dict]) -> dict:
    """Replaying the same (scope, key) returns the stored response without re-running side effects."""
    if (rec := s.scalar(select(IdemRecord).where(IdemRecord.scope == scope, IdemRecord.key == key))):
        return rec.response
    resp = jsonable_encoder(fn())
    s.add(IdemRecord(scope=scope, key=key, response=resp))
    try:
        s.commit()
    except IntegrityError:
        s.rollback()
        rec = s.scalar(select(IdemRecord).where(IdemRecord.scope == scope, IdemRecord.key == key))
        if rec:
            return rec.response
        raise
    return resp
