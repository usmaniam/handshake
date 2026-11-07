import os

from alembic import context
from sqlalchemy import create_engine

from handshake.db import normalize_url
from handshake.db.models import Base

# Migrations use the UNPOOLED connection string when available (Neon via Vercel Marketplace).
url = normalize_url(os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL", "sqlite:///./handshake.db"))


def run() -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


run()
