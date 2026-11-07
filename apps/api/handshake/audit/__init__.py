"""Append-only, hash-chained audit log: hash = SHA256(prev_hash + canonical_json(entry))."""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import AuditLog
from ..util import canon, jsonable, utcnow

GENESIS = "0" * 64


def _h(prev: str, entry: dict) -> str:
    return hashlib.sha256((prev + canon(entry)).encode()).hexdigest()


def write(s: Session, actor: str, event: str, ref_type: str, ref_id: str,
          payload: dict[str, Any] | None = None, now=None) -> AuditLog:
    last = s.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1).with_for_update())
    prev = last.hash if last else GENESIS
    entry = {"ts": (now or utcnow()).isoformat(), "actor": actor, "event": event,
             "ref_type": ref_type, "ref_id": ref_id, "payload": jsonable(payload or {})}
    row = AuditLog(prev_hash=prev, hash=_h(prev, entry), **entry)
    s.add(row)
    s.flush()
    return row


def verify(s: Session) -> dict:
    prev, n = GENESIS, 0
    for r in s.scalars(select(AuditLog).order_by(AuditLog.id)):
        entry = {"ts": r.ts, "actor": r.actor, "event": r.event, "ref_type": r.ref_type,
                 "ref_id": r.ref_id, "payload": r.payload}
        if r.prev_hash != prev or r.hash != _h(prev, entry):
            return {"ok": False, "checked": n, "broken_at": r.id}
        prev, n = r.hash, n + 1
    return {"ok": True, "checked": n, "broken_at": None}
