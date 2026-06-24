"""Database helpers for the clean FootyQuant data layer."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return _engine


def resolve_team(name: str) -> int | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT canonical_id FROM teams "
                "WHERE name = :n OR aliases @> to_jsonb(CAST(:n AS text))"
            ),
            {"n": name},
        ).fetchone()
        return row[0] if row else None
