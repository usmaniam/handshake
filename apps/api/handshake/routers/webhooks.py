from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from .. import db, service

router = APIRouter(prefix="/v1", tags=["webhooks"])


def _handle(headers, raw: bytes, rail) -> dict:
    s = db.new_session()
    try:
        return service.handle_webhook(s, headers, raw, rail)
    finally:
        s.close()


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request):
    raw = await request.body()  # exact bytes: re-serializing would break signature verification
    return await run_in_threadpool(_handle, request.headers, raw, request.app.state.rail_factory())
