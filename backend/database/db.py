import os
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1
        )

    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True
    )
else:
    engine = None

def db_enabled() -> bool:
    return engine is not None

@contextmanager
def session():
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")
    with engine.begin() as conn:
        yield conn


def fetch_all(sql: str, params: dict[str, Any] | None = None):
    with session() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params or {})]


def fetch_one(sql: str, params: dict[str, Any] | None = None):
    with session() as conn:
        r = conn.execute(text(sql), params or {}).first()
        return dict(r._mapping) if r else None
