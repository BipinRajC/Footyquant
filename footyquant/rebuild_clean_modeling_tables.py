#!/usr/bin/env python3
"""Rebuild clean modeling tables from curated/source tables."""

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from footyquant.clean_modeling import build_clean_modeling_sql  # noqa: E402
from footyquant.db import get_engine  # noqa: E402


def main() -> None:
    statements = build_clean_modeling_sql()
    engine = get_engine()
    with engine.begin() as conn:
        for index, statement in enumerate(statements, start=1):
            first_line = statement.splitlines()[0]
            print(f"[{index}/{len(statements)}] {first_line}", flush=True)
            conn.execute(text(statement))
    print("Clean modeling tables rebuilt", flush=True)


if __name__ == "__main__":
    main()
