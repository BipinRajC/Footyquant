"""Database connection, schema creation, and budget guard."""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return _engine


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS teams (
    canonical_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    confederation TEXT,
    oddspapi_participant_id TEXT,
    sofascore_id TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    match_id SERIAL PRIMARY KEY,
    oddspapi_fixture_id TEXT UNIQUE,
    date_utc DATE,
    kickoff_utc TIMESTAMPTZ,
    home_team_id INTEGER REFERENCES teams(canonical_id),
    away_team_id INTEGER REFERENCES teams(canonical_id),
    tournament TEXT,
    is_neutral BOOLEAN DEFAULT FALSE,
    venue TEXT,
    status TEXT,
    home_goals INTEGER,
    away_goals INTEGER,
    home_xg REAL,
    away_xg REAL
);

CREATE TABLE IF NOT EXISTS elo_ratings (
    id SERIAL PRIMARY KEY,
    team_id INTEGER REFERENCES teams(canonical_id),
    rating REAL NOT NULL,
    as_of_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id SERIAL PRIMARY KEY,
    oddspapi_fixture_id TEXT NOT NULL,
    market TEXT NOT NULL,
    book TEXT NOT NULL,
    selection TEXT NOT NULL,
    line REAL,
    decimal_odds REAL NOT NULL,
    implied_prob REAL NOT NULL,
    is_sharp BOOLEAN DEFAULT FALSE,
    captured_at_utc TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL DEFAULT 'current'
);

CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    match_id INTEGER REFERENCES matches(match_id),
    market TEXT NOT NULL,
    model_prob REAL NOT NULL,
    fair_odds REAL NOT NULL,
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_budget (
    id SERIAL PRIMARY KEY,
    provider TEXT NOT NULL UNIQUE,
    calls_used INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO api_budget (provider, calls_used)
VALUES ('oddspapi', 20)
ON CONFLICT (provider) DO NOTHING;
"""


def init_db():
    engine = get_engine()
    with engine.begin() as conn:
        for statement in SCHEMA_SQL.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))


def can_spend(provider: str, needed: int = 1, cap: int = 250) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT calls_used FROM api_budget WHERE provider = :p"),
            {"p": provider},
        ).fetchone()
        if row is None:
            return True
        return (row[0] + needed) <= cap


def record_call(provider: str, count: int = 1):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE api_budget SET calls_used = calls_used + :c, updated_at = :t WHERE provider = :p"
            ),
            {"c": count, "t": datetime.now(timezone.utc), "p": provider},
        )


def resolve_team(name: str) -> int | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT canonical_id FROM teams WHERE name = :n OR aliases @> to_jsonb(CAST(:n AS text))"
            ),
            {"n": name},
        ).fetchone()
        return row[0] if row else None
