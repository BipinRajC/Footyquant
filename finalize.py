#!/usr/bin/env python3
"""Create wc_feature_view and run validation."""

from footyquant.db import get_engine, text

engine = get_engine()

with engine.begin() as conn:
    conn.execute(text("DROP VIEW IF EXISTS wc_feature_view"))
    conn.execute(
        text("""
        CREATE VIEW wc_feature_view AS
        SELECT
            w.match_id, w.match_date, w.home_team, w.away_team,
            w.home_score, w.away_score, w.result_1x2, w.btts, w.total_goals,
            w.stage, w.group_name,
            h5.value as home_form_last5,
            hgf5.value as home_goals_for_last5,
            hga5.value as home_goals_against_last5,
            hxg5.value as home_xg_for_last5,
            hxga5.value as home_xg_against_last5,
            a5.value as away_form_last5,
            agf5.value as away_goals_for_last5,
            aga5.value as away_goals_against_last5,
            axg5.value as away_xg_for_last5,
            axga5.value as away_xg_against_last5,
            hgf_t.value as home_goals_for_tournament,
            hga_t.value as home_goals_against_tournament,
            agf_t.value as away_goals_for_tournament,
            aga_t.value as away_goals_against_tournament,
            mo_poly_h.implied_probability as polymarket_home,
            mo_poly_d.implied_probability as polymarket_draw,
            mo_poly_a.implied_probability as polymarket_away,
            mo_kal_h.implied_probability as kalshi_home,
            mo_kal_d.implied_probability as kalshi_draw,
            mo_kal_a.implied_probability as kalshi_away
        FROM wc_matches w
        LEFT JOIN team_stats h5 ON h5.team_id = (SELECT canonical_id FROM teams WHERE name = w.home_team)
            AND h5.stat_type = 'form_score' AND h5.sample_window = 'last_5_win_rate'
        LEFT JOIN team_stats hgf5 ON hgf5.team_id = (SELECT canonical_id FROM teams WHERE name = w.home_team)
            AND hgf5.stat_type = 'goals_for' AND hgf5.sample_window = 'last_5_avg_per_match'
        LEFT JOIN team_stats hga5 ON hga5.team_id = (SELECT canonical_id FROM teams WHERE name = w.home_team)
            AND hga5.stat_type = 'goals_against' AND hga5.sample_window = 'last_5_avg_per_match'
        LEFT JOIN team_stats hxg5 ON hxg5.team_id = (SELECT canonical_id FROM teams WHERE name = w.home_team)
            AND hxg5.stat_type = 'xg_for' AND hxg5.sample_window = 'last_5_avg_per_match'
        LEFT JOIN team_stats hxga5 ON hxga5.team_id = (SELECT canonical_id FROM teams WHERE name = w.home_team)
            AND hxga5.stat_type = 'xg_against' AND hxga5.sample_window = 'last_5_avg_per_match'
        LEFT JOIN team_stats a5 ON a5.team_id = (SELECT canonical_id FROM teams WHERE name = w.away_team)
            AND a5.stat_type = 'form_score' AND a5.sample_window = 'last_5_win_rate'
        LEFT JOIN team_stats agf5 ON agf5.team_id = (SELECT canonical_id FROM teams WHERE name = w.away_team)
            AND agf5.stat_type = 'goals_for' AND agf5.sample_window = 'last_5_avg_per_match'
        LEFT JOIN team_stats aga5 ON aga5.team_id = (SELECT canonical_id FROM teams WHERE name = w.away_team)
            AND aga5.stat_type = 'goals_against' AND aga5.sample_window = 'last_5_avg_per_match'
        LEFT JOIN team_stats axg5 ON axg5.team_id = (SELECT canonical_id FROM teams WHERE name = w.away_team)
            AND axg5.stat_type = 'xg_for' AND axg5.sample_window = 'last_5_avg_per_match'
        LEFT JOIN team_stats axga5 ON axga5.team_id = (SELECT canonical_id FROM teams WHERE name = w.away_team)
            AND axga5.stat_type = 'xg_against' AND axga5.sample_window = 'last_5_avg_per_match'
        LEFT JOIN team_stats hgf_t ON hgf_t.team_id = (SELECT canonical_id FROM teams WHERE name = w.home_team)
            AND hgf_t.stat_type = 'goals_for' AND hgf_t.sample_window = 'tournament_avg_per_match'
        LEFT JOIN team_stats hga_t ON hga_t.team_id = (SELECT canonical_id FROM teams WHERE name = w.home_team)
            AND hga_t.stat_type = 'goals_against' AND hga_t.sample_window = 'tournament_avg_per_match'
        LEFT JOIN team_stats agf_t ON agf_t.team_id = (SELECT canonical_id FROM teams WHERE name = w.away_team)
            AND agf_t.stat_type = 'goals_for' AND agf_t.sample_window = 'tournament_avg_per_match'
        LEFT JOIN team_stats aga_t ON aga_t.team_id = (SELECT canonical_id FROM teams WHERE name = w.away_team)
            AND aga_t.stat_type = 'goals_against' AND aga_t.sample_window = 'tournament_avg_per_match'
        LEFT JOIN match_odds mo_poly_h ON mo_poly_h.match_id = w.match_id
            AND mo_poly_h.source = 'polymarket' AND mo_poly_h.market_type = '1x2_home'
        LEFT JOIN match_odds mo_poly_d ON mo_poly_d.match_id = w.match_id
            AND mo_poly_d.source = 'polymarket' AND mo_poly_d.market_type = '1x2_draw'
        LEFT JOIN match_odds mo_poly_a ON mo_poly_a.match_id = w.match_id
            AND mo_poly_a.source = 'polymarket' AND mo_poly_a.market_type = '1x2_away'
        LEFT JOIN match_odds mo_kal_h ON mo_kal_h.match_id = w.match_id
            AND mo_kal_h.source = 'kalshi' AND mo_kal_h.market_type = '1x2_home'
        LEFT JOIN match_odds mo_kal_d ON mo_kal_d.match_id = w.match_id
            AND mo_kal_d.source = 'kalshi' AND mo_kal_d.market_type = '1x2_draw'
        LEFT JOIN match_odds mo_kal_a ON mo_kal_a.match_id = w.match_id
            AND mo_kal_a.source = 'kalshi' AND mo_kal_a.market_type = '1x2_away'
    """)
    )
    print("View created")

with engine.connect() as conn:
    wc = conn.execute(
        text("SELECT COUNT(*) as c, COUNT(home_score) as p FROM wc_matches")
    ).fetchone()
    ts = conn.execute(
        text("SELECT COUNT(DISTINCT team_id) as c FROM team_stats")
    ).fetchone()
    ts_xg = conn.execute(
        text(
            "SELECT COUNT(DISTINCT team_id) as c FROM team_stats WHERE stat_type = 'xg_for'"
        )
    ).fetchone()
    mo = conn.execute(text("SELECT COUNT(*) as c FROM match_odds")).fetchone()
    mo_src = conn.execute(
        text(
            "SELECT source, COUNT(*) as c FROM match_odds GROUP BY source ORDER BY source"
        )
    ).fetchall()
    ho = conn.execute(text("SELECT COUNT(*) as c FROM historical_odds")).fetchone()
    ho_comp = conn.execute(
        text(
            "SELECT competition, COUNT(*) as c FROM historical_odds GROUP BY competition ORDER BY competition"
        )
    ).fetchall()
    pms = conn.execute(
        text("SELECT COUNT(*) as c FROM prediction_market_snapshots")
    ).fetchone()
    pms_src = conn.execute(
        text(
            "SELECT source, COUNT(*) as c FROM prediction_market_snapshots GROUP BY source"
        )
    ).fetchall()
    vw = conn.execute(text("SELECT COUNT(*) as c FROM wc_feature_view")).fetchone()

    print()
    print("  ┌─────────────────────────────────────────┐")
    print("  │  DATA PIPELINE VALIDATION REPORT        │")
    print("  ├─────────────────────────────────────────┤")
    print(f"  │  wc_matches          total: {wc.c:<5}           │")
    print(f"  │    → with scores:    {wc.p:<5}  (played)       │")
    print(f"  │    → upcoming:       {wc.c - wc.p:<5}               │")
    print(f"  │  team_stats          teams: {ts.c:<5}            │")
    print(f"  │    → with xG data:   {ts_xg.c:<5}                │")
    print(f"  │  match_odds          total: {mo.c:<5} rows       │")
    print(f"  │    → by source:                         │")
    for s in mo_src:
        print(f"  │       {s.source:<16} {s.c:<5}               │")
    print(f"  │  historical_odds     total: {ho.c:<5} rows  │")
    for c2 in ho_comp:
        print(f"  │       {c2.competition:<16} {c2.c:<5}               │")
    print(f"  │  prediction_market_  total: {pms.c:<5} rows      │")
    print(f"  │  snapshots                              │")
    for p in pms_src:
        print(f"  │    → {p.source:<16} {p.c:<5}               │")
    print(f"  │  wc_feature_view     rows: {vw.c:<5}            │")
    print("  ├─────────────────────────────────────────┤")

    gaps = []
    if wc.c < 48:
        gaps.append(f"wc_matches ({wc.c}) < 48")
    if ts.c < 16:
        gaps.append(f"team_stats ({ts.c}) < 16 teams")
    if mo.c == 0:
        gaps.append("match_odds has 0 rows")
    if ho.c < 500:
        gaps.append(f"historical_odds ({ho.c}) < 500 rows")

    if gaps:
        print(f"  │  VERDICT: GAPS FOUND — see below ✗       │")
        for g in gaps:
            print(f"  │    \u2022 {g:<37} │")
    else:
        print(f"  │  VERDICT: READY FOR MODELING \u2713            │")
    print("  └─────────────────────────────────────────┘")
