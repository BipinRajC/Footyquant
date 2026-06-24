"""FootyQuant CLI for clean data-layer rebuilds."""

import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m footyquant <command>")
        print("Commands:")
        print("  rebuild odds       Rebuild clean_market_odds")
        print("  rebuild modeling   Rebuild clean modeling tables")
        sys.exit(1)

    cmd = sys.argv[1:]
    if cmd == ["rebuild", "odds"]:
        from .rebuild_clean_market_odds import main as rebuild_odds

        rebuild_odds()
    elif cmd == ["rebuild", "modeling"]:
        from .rebuild_clean_modeling_tables import main as rebuild_modeling

        rebuild_modeling()
    else:
        print(f"Unknown command: {' '.join(cmd)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
