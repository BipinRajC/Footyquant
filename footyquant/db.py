"""Database helpers for the clean FootyQuant data layer.

Falls back to Supabase REST API (IPv4) when direct PostgreSQL (IPv6) is unavailable.
"""

import json
import os
import urllib.request
import urllib.error

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY", "")
_engine = None


def _load_env():
    global SUPABASE_URL, SUPABASE_KEY
    if not SUPABASE_URL or not SUPABASE_KEY:
        dotenv = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(dotenv):
            with open(dotenv) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SUPABASE_URL=") and not SUPABASE_URL:
                        SUPABASE_URL = line.split("=", 1)[1]
                    elif line.startswith("SUPABASE_ANON_KEY=") and not SUPABASE_KEY:
                        SUPABASE_KEY = line.split("=", 1)[1]
                    elif line.startswith("SUPABASE_KEY=") and not SUPABASE_KEY:
                        SUPABASE_KEY = line.split("=", 1)[1]


def _rest_request(method: str, path: str, body: dict | None = None):
    _load_env()
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:500]
        raise RuntimeError(f"REST API {e.code}: {err_body}") from e


def get_engine():
    global _engine
    if _engine is not None:
        return _engine

    if DATABASE_URL:
        try:
            eng = create_engine(
                DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 5}
            )
            with eng.connect() as c:
                c.execute(text("SELECT 1"))
            _engine = eng
            return _engine
        except Exception:
            pass

    _engine = _RestEngine()
    return _engine


class _RestEngine:
    def connect(self):
        return _RestConnection()

    def begin(self):
        return _RestConnection()


class _RestConnection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, stmt, params=None):
        query = str(stmt).strip().rstrip(";")
        if params:
            for k, v in params.items():
                placeholder = f":{k}"
                if placeholder not in query:
                    continue
                if v is None:
                    replacement = "NULL"
                elif isinstance(v, bool):
                    replacement = "TRUE" if v else "FALSE"
                elif isinstance(v, (int, float)):
                    replacement = str(v)
                elif hasattr(v, "isoformat"):
                    replacement = f"'{v.isoformat()}'"
                else:
                    escaped = str(v).replace("'", "''")
                    replacement = f"'{escaped}'"
                query = query.replace(placeholder, replacement)
        result = _rest_request("POST", "rpc/pg_query", {"query_text": query})
        return _RestResult(result)

    def close(self):
        pass


class _RestResult:
    def __init__(self, data):
        raw = data if isinstance(data, list) else []
        self.data = [_RestRow(r) if isinstance(r, dict) else r for r in raw]
        self._rows = self.data

    def mappings(self):
        return self

    def fetchone(self):
        return self.data[0] if self.data else None

    def fetchall(self):
        return self.data

    def rowcount(self):
        if isinstance(self.data, dict):
            return self.data.get("rows_affected", 0)
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def all(self):
        return self.data


class _RestRow:
    """Row that supports both dict key access and integer index access."""

    def __init__(self, data: dict):
        self._data = data
        self._keys = list(data.keys())

    def __getitem__(self, key):
        if isinstance(key, (int,)):
            return self._data[self._keys[key]]
        return self._data[key]

    def __getattr__(self, name):
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._keys

    def values(self):
        return list(self._data.values())

    def __repr__(self):
        return repr(self._data)


def resolve_team(name: str) -> int | None:
    try:
        result = _rest_request(
            "GET",
            f"teams?select=canonical_id&name=eq.{name}&limit=1",
        )
        return result[0]["canonical_id"] if result else None
    except Exception:
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
