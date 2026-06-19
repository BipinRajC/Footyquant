"""Import WorldCup2026.xlsx data into matches table."""

import pandas as pd
from sqlalchemy import text

from .db import get_engine, resolve_team


def _val(v):
    if pd.isna(v):
        return None
    return int(v)


def _float(v):
    if pd.isna(v):
        return None
    return float(v)


def main():
    engine = get_engine()
    xlsx = pd.ExcelFile("data/WorldCup2026.xlsx")

    all_names = set()
    sheet_data = {}
    for sheet in xlsx.sheet_names:
        df = pd.read_excel(xlsx, sheet)
        for col in ["Home", "Away"]:
            all_names.update(df[col].dropna().astype(str).str.strip().unique())
        sheet_data[sheet] = df

    print(f"Resolving {len(all_names)} unique team names...")
    name_to_id = {}
    for name in sorted(all_names):
        tid = resolve_team(name)
        name_to_id[name] = tid
        if tid is None:
            print(f"  UNRESOLVED: {name}")

    total_ins = 0
    total_skipped = 0

    for sheet, df in sheet_data.items():
        has_xg = "HxG" in df.columns
        goals_h_col = "HGFT" if "HGFT" in df.columns else "HG"
        goals_a_col = "AGFT" if "AGFT" in df.columns else "AG"

        rows_to_insert = []
        for _, row in df.iterrows():
            home_name = str(row["Home"]).strip()
            away_name = str(row["Away"]).strip()
            home_id = name_to_id.get(home_name)
            away_id = name_to_id.get(away_name)

            if not home_id or not away_id:
                total_skipped += 1
                continue

            date_val = row.get("Date")
            if date_val is None or (isinstance(date_val, float) and pd.isna(date_val)):
                continue
            date_str = str(date_val)[:10]

            home_goals = _val(row.get(goals_h_col))
            away_goals = _val(row.get(goals_a_col))
            home_xg = _float(row.get("HxG")) if has_xg else None
            away_xg = _float(row.get("AxG")) if has_xg else None

            rows_to_insert.append(
                {
                    "date": date_str,
                    "hid": home_id,
                    "aid": away_id,
                    "tourn": sheet,
                    "hg": home_goals,
                    "ag": away_goals,
                    "hxg": home_xg,
                    "axg": away_xg,
                    "status": "completed" if home_goals is not None else "scheduled",
                }
            )

        with engine.begin() as conn:
            for r in rows_to_insert:
                conn.execute(
                    text(
                        """INSERT INTO matches
                        (date_utc, home_team_id, away_team_id, tournament,
                         home_goals, away_goals, home_xg, away_xg, status)
                        VALUES (:date, :hid, :aid, :tourn,
                                :hg, :ag, :hxg, :axg, :status)
                        ON CONFLICT DO NOTHING"""
                    ),
                    r,
                )

        total_ins += len(rows_to_insert)
        print(f"  {sheet}: {len(rows_to_insert)} inserted, {total_skipped} skipped")

    print(f"\nTotal: {total_ins} matches, {total_skipped} skipped")


if __name__ == "__main__":
    main()
