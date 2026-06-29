"""Update wc2026_matches from the Excel sheet.

Reads data/WorldCup2026.xlsx and upserts all 72 rows into wc2026_matches.
Run this after updating the Excel sheet with new match results.
"""

import os
import pandas as pd
from supabase import create_client


def get_supabase():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(dotenv_path):
            with open(dotenv_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SUPABASE_URL="):
                        url = line.split("=", 1)[1]
                    elif line.startswith("SUPABASE_ANON_KEY="):
                        key = line.split("=", 1)[1]
                    elif line.startswith("SUPABASE_KEY=") and not key:
                        key = line.split("=", 1)[1]
    return create_client(url, key)


def main():
    print("  Updating wc2026_matches from Excel...")

    root = os.path.dirname(os.path.dirname(__file__))
    df = pd.read_excel(
        os.path.join(root, "data", "WorldCup2026.xlsx"), sheet_name="WorldCup2026"
    )
    print(f"    Excel rows: {len(df)}")

    supabase = get_supabase()

    existing = supabase.table("wc2026_matches").select("id").execute()
    existing_ids = {r["id"] for r in existing.data}
    print(f"    DB rows: {len(existing.data)}")

    upserted = 0
    for idx, row in df.iterrows():
        record = {
            "id": idx + 1,
            "home": str(row["Home"]),
            "away": str(row["Away"]),
            "date": str(row["Date"])[:10] if pd.notna(row["Date"]) else None,
            "time": str(row["Time"]) if pd.notna(row["Time"]) else None,
            "hgft": int(row["HGFT"]) if pd.notna(row["HGFT"]) else None,
            "agft": int(row["AGFT"]) if pd.notna(row["AGFT"]) else None,
            "hg1st": int(row["HG1st"]) if pd.notna(row["HG1st"]) else None,
            "ag1st": int(row["AG1st"]) if pd.notna(row["AG1st"]) else None,
            "hg2nd": int(row["HG2nd"]) if pd.notna(row["HG2nd"]) else None,
            "ag2nd": int(row["AG2nd"]) if pd.notna(row["AG2nd"]) else None,
            "hget": int(row["HGET"]) if pd.notna(row["HGET"]) else None,
            "aget": int(row["AGET"]) if pd.notna(row["AGET"]) else None,
            "hgp": int(row["HGP"]) if pd.notna(row["HGP"]) else None,
            "agp": int(row["HGP.1"]) if pd.notna(row["HGP.1"]) else None,
            "finished": str(row["Finished"]) if pd.notna(row["Finished"]) else None,
            "hs": int(row["HS"]) if pd.notna(row["HS"]) else None,
            "as_shots": int(row["AS"]) if pd.notna(row["AS"]) else None,
            "hst": int(row["HST"]) if pd.notna(row["HST"]) else None,
            "ast": int(row["AST"]) if pd.notna(row["AST"]) else None,
            "hf": int(row["HF"]) if pd.notna(row["HF"]) else None,
            "af": int(row["AF"]) if pd.notna(row["AF"]) else None,
            "hc": int(row["HC"]) if pd.notna(row["HC"]) else None,
            "ac": int(row["AC"]) if pd.notna(row["AC"]) else None,
            "hy": int(row["HY"]) if pd.notna(row["HY"]) else None,
            "ay": int(row["AY"]) if pd.notna(row["AY"]) else None,
            "hr": int(row["HR"]) if pd.notna(row["HR"]) else None,
            "ar": int(row["AR"]) if pd.notna(row["AR"]) else None,
            "hxg": float(row["HxG"]) if pd.notna(row["HxG"]) else None,
            "axg": float(row["AxG"]) if pd.notna(row["AxG"]) else None,
            "b365_h": float(row["bet365-H"]) if pd.notna(row["bet365-H"]) else None,
            "b365_d": float(row["bet365-D"]) if pd.notna(row["bet365-D"]) else None,
            "b365_a": float(row["bet365-A"]) if pd.notna(row["bet365-A"]) else None,
            "bf_h": float(row["Betfair_Exch-H"])
            if pd.notna(row["Betfair_Exch-H"])
            else None,
            "bf_d": float(row["Betfair_Exch-D"])
            if pd.notna(row["Betfair_Exch-D"])
            else None,
            "bf_a": float(row["Betfair_Exch-A"])
            if pd.notna(row["Betfair_Exch-A"])
            else None,
            "max_h": float(row["H-Max"]) if pd.notna(row["H-Max"]) else None,
            "max_d": float(row["D-Max"]) if pd.notna(row["D-Max"]) else None,
            "max_a": float(row["A-Max"]) if pd.notna(row["A-Max"]) else None,
            "avg_h": float(row["H-Avg"]) if pd.notna(row["H-Avg"]) else None,
            "avg_d": float(row["D-Avg"]) if pd.notna(row["D-Avg"]) else None,
            "avg_a": float(row["A-Avg"]) if pd.notna(row["A-Avg"]) else None,
        }

        record = {k: v for k, v in record.items() if v is not None}

        try:
            supabase.table("wc2026_matches").upsert(record).execute()
            upserted += 1
        except Exception as e:
            print(f"    Error on row {idx + 1} ({row['Home']} vs {row['Away']}): {e}")

    print(f"    Upserted {upserted} rows")

    final = supabase.table("wc2026_matches").select("id").execute()
    print(f"    Final DB rows: {len(final.data)}")
    print("  Done.")


if __name__ == "__main__":
    main()
