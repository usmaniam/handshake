from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .config import settings
from .db.models import Base
from .paypal import get_rail
from .routers import gateway, mock_carrier, owner, webhooks
from .service import DomainError


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings().auto_create_tables:
        Base.metadata.create_all(db.get_engine())
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Handshake", version="0.1.0", lifespan=lifespan,
                  description="Agents negotiate the deal. Handshake pays when it's delivered.")
    app.state.rail_factory = get_rail
    app.add_middleware(CORSMiddleware, allow_origins=settings().allowed_origins, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(DomainError)
    async def _domain(_: Request, e: DomainError):
        return JSONResponse({"error": str(e)}, status_code=e.status)

    @app.get("/health")
    def health():
        return {"ok": True, "rail": settings().payout_rail}

    @app.get("/health/db")
    def health_db():
        from sqlalchemy import text
        with db.get_engine().connect() as c:
            c.execute(text("select 1"))
        return {"ok": True}

    for r in (gateway.router, owner.router, webhooks.router, mock_carrier.router):
        app.include_router(r)
    return app


app = create_app()
