"""FootyQuant CLI."""

import sys
from .db import init_db, get_engine, can_spend, record_call


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m footyquant <command>")
        print("Commands:")
        print("  db init          Create all tables")
        print("  budget           Show API budget status")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "db" and len(sys.argv) > 2 and sys.argv[2] == "init":
        init_db()
        print("All tables created.")
    elif cmd == "budget":
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                __import__("sqlalchemy").text(
                    "SELECT calls_used FROM api_budget WHERE provider = 'oddspapi'"
                )
            ).fetchone()
            if row:
                used = row[0]
                print(f"OddsAPI calls used: {used}/250")
                print(f"Can spend: {can_spend('oddspapi', 1)}")
            else:
                print("No budget record found. Run 'db init' first.")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
