from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from ..config import settings

_engine: Engine | None = None
_factory: sessionmaker | None = None


def normalize_url(url: str) -> str:
    for p in ("postgres://", "postgresql://"):
        if url.startswith(p):
            return "postgresql+psycopg://" + url[len(p):]
    return url


def configure(url: str | None = None) -> Engine:
    global _engine, _factory
    url = normalize_url(url or settings().database_url)
    if url.startswith("sqlite"):
        kw: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kw["poolclass"] = StaticPool
        _engine = create_engine(url, **kw)
    else:
        # Serverless + Neon pooled endpoint: no client-side pool, no prepared statements.
        _engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True,
                                connect_args={"prepare_threshold": None})
    _factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    return _engine or configure()


def new_session() -> Session:
    get_engine()
    assert _factory is not None
    return _factory()


def get_session() -> Iterator[Session]:
    s = new_session()
    try:
        yield s
    finally:
        s.close()
