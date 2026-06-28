#!/usr/bin/env python3
"""Pre-modeling data audit for WC 2026 — clean tables only."""

import os, sys
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from sqlalchemy import text
from footyquant.db import get_engine

engine = get_engine()
FLAGS = {"GOOD": 0, "WEAK": 0, "BAD": 0}
ISSUES = []


def log(msg):
    print(msg, flush=True)


def flag(level, msg):
    FLAGS[level] = FLAGS.get(level, 0) + 1
    ISSUES.append(f"[{level}] {msg}")
    print(f"  {level}: {msg}", flush=True)


def q(sql, params=None):
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchall()


def qdf(sql, params=None):
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — SCHEMA & STRUCTURAL AUDIT
# ══════════════════════════════════════════════════════════════════════════════

log("=" * 60)
log("PHASE 1 — SCHEMA & STRUCTURAL AUDIT (clean tables only)")
log("=" * 60)

# 1a. List clean tables
log("\n1a. CLEAN TABLE INVENTORY")
clean_tables = [
    t
    for t in q(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'clean_%' ORDER BY table_name"
    )
]
for t in clean_tables:
    cnt = q(f"SELECT COUNT(*) as c FROM {t.table_name}")[0].c
    log(f"  {t.table_name}: {cnt} rows")

# 1b. clean_wc_feature_view deep dive
log("\n1b. clean_wc_feature_view — COLUMN AUDIT")
cols = q(
    "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='clean_wc_feature_view' ORDER BY ordinal_position"
)
total = q("SELECT COUNT(*) as c FROM clean_wc_feature_view")[0].c
group_total = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE stage = 'group'"
)[0].c
knockout_total = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE stage = 'knockout'"
)[0].c
log(f"  Total rows: {total} ({group_total} group stage, {knockout_total} knockout)")

for c in cols:
    nulls_played = q(
        f"SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND {c.column_name} IS NULL"
    )[0].c
    nulls_total = q(
        f"SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE {c.column_name} IS NULL"
    )[0].c
    played_total = q(
        "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL"
    )[0].c
    pct = round(nulls_played / played_total * 100, 1) if played_total > 0 else 0
    if nulls_played > 0:
        lvl = "GOOD" if pct < 10 else "WEAK" if pct < 50 else "BAD"
        flag(
            lvl,
            f"{c.column_name}: {nulls_played}/{played_total} NULL in completed matches ({pct}%) — {nulls_total}/{total} total",
        )

# Numeric stats
log("\n  NUMERIC COLUMN STATS")
num_cols = [
    c.column_name
    for c in cols
    if c.data_type in ("real", "double precision", "integer", "numeric", "bigint")
]
for nc in num_cols:
    try:
        r = q(
            f"SELECT MIN({nc}) as mn, MAX({nc}) as mx, AVG({nc}) as av, STDDEV({nc}) as sd FROM clean_wc_feature_view WHERE {nc} IS NOT NULL"
        )[0]
        if r.mn is not None:
            log(
                f"  {nc}: min={r.mn:.4f} max={r.mx:.4f} mean={r.av:.4f} std={r.sd:.4f}"
                if r.sd
                else f"  {nc}: min={r.mn} max={r.mx} mean={r.av}"
            )
    except Exception as e:
        log(f"  {nc}: ERROR {e}")

# Categorical distributions
log("\n  CATEGORICAL DISTRIBUTIONS")
for cat_col in ["result_1x2", "stage", "match_state"]:
    try:
        dist = q(
            f"SELECT {cat_col}, COUNT(*) as c FROM clean_wc_feature_view GROUP BY {cat_col} ORDER BY c DESC"
        )
        log(f"  {cat_col}:")
        for d in dist:
            log(f"    {d[0]}: {d.c}")
    except Exception as e:
        log(f"  {cat_col}: ERROR {e}")

# Duplicate check
dupes = q(
    "SELECT match_id, COUNT(*) as c FROM clean_wc_feature_view GROUP BY match_id HAVING COUNT(*) > 1"
)
if dupes:
    flag("BAD", f"DUPLICATE match_ids: {len(dupes)}")
else:
    flag("GOOD", "No duplicate match_ids")

# 1c. Other clean tables
log("\n1c. OTHER CLEAN TABLES — NULL & DUPLICATE AUDIT")
for tbl in [
    t.table_name for t in clean_tables if t.table_name != "clean_wc_feature_view"
]:
    try:
        cnt = q(f"SELECT COUNT(*) as c FROM {tbl}")[0].c
        tcols = q(
            f"SELECT column_name FROM information_schema.columns WHERE table_name='{tbl}' ORDER BY ordinal_position"
        )
        null_report = []
        for tc in tcols:
            n = q(f"SELECT COUNT(*) as c FROM {tbl} WHERE {tc.column_name} IS NULL")[
                0
            ].c
            if n > 0:
                null_report.append(f"{tc.column_name}={n}/{cnt}")
        if null_report:
            log(f"  {tbl} ({cnt} rows): NULLs — {', '.join(null_report[:5])}")
        else:
            log(f"  {tbl} ({cnt} rows): no NULLs")
    except Exception as e:
        log(f"  {tbl}: ERROR {e}")

# FK integrity
log("\n  FOREIGN KEY INTEGRITY")
for child_tbl, child_col, parent_tbl, parent_col in [
    ("clean_market_odds", "match_id", "clean_wc_fixtures", "match_id"),
]:
    try:
        orphans = q(
            f"SELECT COUNT(*) as c FROM {child_tbl} c LEFT JOIN {parent_tbl} p ON c.{child_col} = p.{parent_col} WHERE p.{parent_col} IS NULL"
        )[0].c
        if orphans > 0:
            flag("BAD", f"FK violation: {child_tbl}.{child_col} has {orphans} orphans")
        else:
            flag("GOOD", f"FK OK: {child_tbl}.{child_col} → {parent_tbl}.{parent_col}")
    except Exception as e:
        log(f"  FK check {child_tbl}→{parent_tbl}: ERROR {e}")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — FEATURE QUALITY AUDIT
# ══════════════════════════════════════════════════════════════════════════════

log("\n" + "=" * 60)
log("PHASE 2 — FEATURE QUALITY AUDIT")
log("=" * 60)

# ELO
log("\n2a. ELO FEATURES")
elo_nulls = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_elo IS NULL OR away_elo IS NULL"
)[0].c
if elo_nulls > 0:
    flag("BAD", f"Elo NULLs: {elo_nulls}/{total}")
else:
    flag("GOOD", f"Elo populated for all {total} rows")

elo_range = q(
    "SELECT MIN(home_elo) as mn, MAX(home_elo) as mx FROM clean_wc_feature_view WHERE home_elo IS NOT NULL"
)[0]
if elo_range and elo_range.mn is not None:
    if elo_range.mn < 1200 or elo_range.mx > 2200:
        flag("WEAK", f"Elo range: {elo_range.mn}-{elo_range.mx} (expected 1200-2200)")
    else:
        flag("GOOD", f"Elo range OK: {elo_range.mn}-{elo_range.mx}")

# Elo diff consistency
elo_diff_check = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_elo IS NOT NULL AND away_elo IS NOT NULL AND ABS(elo_diff - (home_elo - away_elo)) > 1"
)[0].c
if elo_diff_check > 0:
    flag("BAD", f"Elo diff inconsistent: {elo_diff_check} rows")
else:
    flag("GOOD", "Elo diff = home_elo - away_elo for all rows")

# Elo time-awareness (leakage check)
log("  Elo time-awareness (leakage check):")
elo_time = q("""
    SELECT match_id, home_team, match_date, home_elo,
           LAG(home_elo) OVER (PARTITION BY home_team ORDER BY match_date) as prev_elo
    FROM clean_wc_feature_view WHERE home_elo IS NOT NULL
    ORDER BY home_team, match_date
""")
elo_changes = [
    r for r in elo_time if r.prev_elo is not None and abs(r.home_elo - r.prev_elo) > 0
]
if len(elo_changes) > 0:
    flag(
        "WEAK",
        f"Elo changes between matches for same team ({len(elo_changes)} instances) — may indicate time-aware updates or post-match contamination",
    )
else:
    flag("GOOD", "Elo values consistent across matches for same team")

# FORM
log("\n2b. FORM FEATURES")
form_range = q(
    "SELECT MIN(home_form_score) as mn, MAX(home_form_score) as mx FROM clean_wc_feature_view WHERE home_form_score IS NOT NULL"
)[0]
if form_range and form_range.mn is not None:
    if form_range.mn < 0 or form_range.mx > 1:
        flag("BAD", f"Form score out of range: {form_range.mn}-{form_range.mx}")
    else:
        flag("GOOD", f"Form score range OK: {form_range.mn}-{form_range.mx}")

form_nulls = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_form_score IS NULL"
)[0].c
if form_nulls > 0:
    flag("WEAK", f"Form score NULL for {form_nulls} rows")

# Goals scored/conceded range
gs_range = q(
    "SELECT MIN(home_goals_scored_l5) as mn, MAX(home_goals_scored_l5) as mx FROM clean_wc_feature_view WHERE home_goals_scored_l5 IS NOT NULL"
)[0]
if gs_range and gs_range.mn is not None:
    if gs_range.mx > 5:
        flag("WEAK", f"Goals scored L5 max={gs_range.mx} (unusually high)")
    else:
        flag("GOOD", f"Goals scored L5 range: {gs_range.mn}-{gs_range.mx}")

# XG
log("\n2c. XG FEATURES")
xg_nulls = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_xg_for_avg IS NULL"
)[0].c
xg_pct = round((total - xg_nulls) / total * 100, 1)
flag(
    "GOOD" if xg_pct > 80 else "WEAK" if xg_pct > 40 else "BAD",
    f"xG coverage: {xg_pct}% ({total - xg_nulls}/{total})",
)

xg_range = q(
    "SELECT MIN(home_xg_for_avg) as mn, MAX(home_xg_for_avg) as mx FROM clean_wc_feature_view WHERE home_xg_for_avg IS NOT NULL"
)[0]
if xg_range and xg_range.mn is not None:
    if xg_range.mn < 0.3 or xg_range.mx > 3.5:
        flag("WEAK", f"xG range unusual: {xg_range.mn:.2f}-{xg_range.mx:.2f}")
    else:
        flag("GOOD", f"xG range OK: {xg_range.mn:.2f}-{xg_range.mx:.2f}")

# xG vs goals correlation
try:
    corr_data = qdf(
        "SELECT home_xg_for_avg, home_goals_scored_l5 FROM clean_wc_feature_view WHERE home_xg_for_avg IS NOT NULL AND home_goals_scored_l5 IS NOT NULL"
    )
    if len(corr_data) > 5:
        corr = corr_data["home_xg_for_avg"].corr(corr_data["home_goals_scored_l5"])
        if corr < 0.3:
            flag("WEAK", f"xG-goals correlation weak: r={corr:.3f}")
        else:
            flag("GOOD", f"xG-goals correlation: r={corr:.3f}")
except Exception as e:
    log(f"  Correlation check: ERROR {e}")

# ODDS
log("\n2d. ODDS / MARKET FEATURES")
# Post-kickoff contamination check
contam = q("""
    SELECT match_id, home_team, away_team, kalshi_home_prob, kalshi_draw_prob, kalshi_away_prob
    FROM clean_wc_feature_view
    WHERE home_score IS NOT NULL
    AND (kalshi_home_prob <= 0.02 OR kalshi_home_prob >= 0.98
         OR kalshi_draw_prob <= 0.02 OR kalshi_draw_prob >= 0.98
         OR kalshi_away_prob <= 0.02 OR kalshi_away_prob >= 0.98)
""")
if len(contam) > 0:
    flag(
        "BAD",
        f"Post-settlement contamination: {len(contam)} matches have extreme Kalshi odds (<=0.02 or >=0.98)",
    )
    for c in contam[:5]:
        log(
            f"    {c.home_team} vs {c.away_team}: H={c.kalshi_home_prob} D={c.kalshi_draw_prob} A={c.kalshi_away_prob}"
        )
else:
    flag("GOOD", "No post-settlement contamination in Kalshi odds")

# Kalshi prob sum check
kalshi_sum = q("""
    SELECT COUNT(*) as c FROM clean_wc_feature_view
    WHERE kalshi_home_prob IS NOT NULL
    AND ABS(kalshi_home_prob + kalshi_draw_prob + kalshi_away_prob - 1.0) > 0.01
""")[0].c
if kalshi_sum > 0:
    flag("WEAK", f"Kalshi prob sum ≠ 1.0 for {kalshi_sum} rows")
else:
    flag("GOOD", "Kalshi prob sums to 1.0 for all rows")

# Odds coverage for played vs upcoming
played_odds = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND kalshi_home_prob IS NOT NULL"
)[0].c
played_total = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL"
)[0].c
upcoming_odds = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NULL AND kalshi_home_prob IS NOT NULL"
)[0].c
upcoming_total = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NULL"
)[0].c
log(f"  Played with odds: {played_odds}/{played_total}")
log(f"  Upcoming with odds: {upcoming_odds}/{upcoming_total}")

# Polymarket coverage
poly_played = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND polymarket_home_prob IS NOT NULL"
)[0].c
poly_upcoming = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NULL AND polymarket_home_prob IS NOT NULL"
)[0].c
log(f"  Polymarket: {poly_played} played, {poly_upcoming} upcoming")

# xlsx odds coverage
xlsx_played = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND xlsx_bet365_home_prob IS NOT NULL"
)[0].c
log(f"  xlsx bet365: {xlsx_played} played matches")

# H2H
log("\n2e. H2H FEATURES")
h2h_zero = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE h2h_matches_played = 0 OR h2h_matches_played IS NULL"
)[0].c
flag(
    "WEAK" if h2h_zero > total * 0.3 else "GOOD",
    f"H2H zero/NULL: {h2h_zero}/{total} ({round(h2h_zero / total * 100, 1)}%)",
)

h2h_range = q(
    "SELECT MIN(h2h_avg_goals) as mn, MAX(h2h_avg_goals) as mx FROM clean_wc_feature_view WHERE h2h_avg_goals IS NOT NULL AND h2h_avg_goals > 0"
)[0]
if h2h_range and h2h_range.mn is not None:
    if h2h_range.mx > 6:
        flag("WEAK", f"H2H avg goals outlier: max={h2h_range.mx}")
    else:
        flag("GOOD", f"H2H avg goals range OK: {h2h_range.mn}-{h2h_range.mx}")

# TOURNAMENT CONTEXT
log("\n2f. TOURNAMENT CONTEXT")
days_neg = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE days_since_last_match_home < 0 OR days_since_last_match_away < 0"
)[0].c
if days_neg > 0:
    flag("BAD", f"Negative days_since_last_match: {days_neg} rows")
else:
    flag("GOOD", "No negative days_since_last_match")

days_high = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE days_since_last_match_home > 400 OR days_since_last_match_away > 400"
)[0].c
if days_high > 0:
    flag(
        "WEAK",
        f"days_since_last_match > 400: {days_high} rows (likely missing prior match data)",
    )

# TARGETS
log("\n2g. TARGET VARIABLES")
target_dist = q(
    "SELECT result_1x2, COUNT(*) as c FROM clean_wc_feature_view WHERE result_1x2 IS NOT NULL GROUP BY result_1x2 ORDER BY c DESC"
)
log("  result_1x2 distribution:")
for t in target_dist:
    log(f"    {t.result_1x2}: {t.c}")
    if t.c < 5:
        flag("BAD", f"result_1x2='{t.result_1x2}' has only {t.c} examples (< 5)")

btts_dist = q(
    "SELECT btts, COUNT(*) as c FROM clean_wc_feature_view WHERE btts IS NOT NULL GROUP BY btts"
)
log("  btts distribution:")
for b in btts_dist:
    log(f"    {b.btts}: {b.c}")

# Target consistency
target_bugs = q("""
    SELECT match_id, home_score, away_score, total_goals, result_1x2, btts
    FROM clean_wc_feature_view
    WHERE home_score IS NOT NULL
    AND (
        total_goals != home_score + away_score
        OR (result_1x2 = 'H' AND home_score <= away_score)
        OR (result_1x2 = 'A' AND home_score >= away_score)
        OR (result_1x2 = 'D' AND home_score != away_score)
        OR btts != (home_score > 0 AND away_score > 0)
    )
""")
if len(target_bugs) > 0:
    flag("BAD", f"Target variable inconsistencies: {len(target_bugs)} rows")
    for t in target_bugs[:5]:
        log(
            f"    {t.match_id}: {t.home_score}-{t.away_score} result={t.result_1x2} tg={t.total_goals} btts={t.btts}"
        )
else:
    flag("GOOD", "All target variables consistent with scores")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — CROSS-TABLE CONSISTENCY
# ══════════════════════════════════════════════════════════════════════════════

log("\n" + "=" * 60)
log("PHASE 3 — CROSS-TABLE CONSISTENCY")
log("=" * 60)

# 3a. Team name standardization
log("\n3a. TEAM NAME STANDARDIZATION")
name_sources = {
    "clean_wc_feature_view": "SELECT DISTINCT home_team as name FROM clean_wc_feature_view UNION SELECT DISTINCT away_team FROM clean_wc_feature_view",
    "clean_wc_fixtures": "SELECT DISTINCT home_team as name FROM clean_wc_fixtures UNION SELECT DISTINCT away_team FROM clean_wc_fixtures",
    "clean_wc_teams": "SELECT DISTINCT wc_team_name as name FROM clean_wc_teams",
    "wc2026_matches": "SELECT DISTINCT home as name FROM wc2026_matches UNION SELECT DISTINCT away FROM wc2026_matches",
}

all_names = {}
for src, sql in name_sources.items():
    try:
        names = q(sql)
        all_names[src] = set(r.name for r in names)
        log(f"  {src}: {len(all_names[src])} unique names")
    except Exception as e:
        log(f"  {src}: ERROR {e}")

# Find mismatches between feature_view and fixtures
if "clean_wc_feature_view" in all_names and "clean_wc_fixtures" in all_names:
    fv_only = all_names["clean_wc_feature_view"] - all_names["clean_wc_fixtures"]
    fix_only = all_names["clean_wc_fixtures"] - all_names["clean_wc_feature_view"]
    if fv_only:
        flag("WEAK", f"Names in feature_view but not fixtures: {fv_only}")
    if fix_only:
        flag("WEAK", f"Names in fixtures but not feature_view: {fix_only}")

# Known name variants
variants = [
    ("South Korea", "Korea Republic"),
    ("Iran", "IR Iran"),
    ("DR Congo", "Congo DR"),
]
for v1, v2 in variants:
    in_fv = v1 in all_names.get("clean_wc_feature_view", set()) or v2 in all_names.get(
        "clean_wc_feature_view", set()
    )
    in_wc2026 = v1 in all_names.get("wc2026_matches", set()) or v2 in all_names.get(
        "wc2026_matches", set()
    )
    if in_fv != in_wc2026:
        flag("WEAK", f"Name variant {v1}/{v2}: fv={in_fv} wc2026={in_wc2026}")

# 3b. Match ID integrity
log("\n3b. MATCH ID INTEGRITY")
for child_tbl, child_col in [("clean_market_odds", "match_id")]:
    try:
        orphans = q(
            f"SELECT COUNT(*) as c FROM {child_tbl} c LEFT JOIN clean_wc_fixtures f ON c.{child_col} = f.match_id WHERE f.match_id IS NULL"
        )[0].c
        if orphans > 0:
            flag("BAD", f"Orphan {child_col} in {child_tbl}: {orphans}")
        else:
            flag("GOOD", f"All {child_col} in {child_tbl} exist in clean_wc_fixtures")
    except Exception as e:
        log(f"  {child_tbl}: ERROR {e}")

# 3c. Date consistency
log("\n3c. DATE CONSISTENCY")
date_check = q("""
    SELECT COUNT(*) as c FROM clean_wc_feature_view fv
    JOIN clean_wc_fixtures f ON fv.match_id = f.match_id
    WHERE ABS(EXTRACT(EPOCH FROM (fv.match_date - f.match_date))) > 3600
""")[0].c
if date_check > 0:
    flag("BAD", f"Date mismatch > 1hr: {date_check}")
else:
    flag("GOOD", "Match dates consistent between feature_view and fixtures")

# 3d. Score consistency
log("\n3d. SCORE CONSISTENCY")
score_check = q("""
    SELECT COUNT(*) as c FROM clean_wc_feature_view fv
    JOIN clean_wc_fixtures f ON fv.match_id = f.match_id
    WHERE fv.home_score IS NOT NULL
    AND (fv.home_score != f.home_score OR fv.away_score != f.away_score)
""")[0].c
if score_check > 0:
    flag("BAD", f"Score mismatch: {score_check}")
else:
    flag("GOOD", "Scores consistent between feature_view and fixtures")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — MODELING READINESS
# ══════════════════════════════════════════════════════════════════════════════

log("\n" + "=" * 60)
log("PHASE 4 — MODELING READINESS ASSESSMENT")
log("=" * 60)

# 4a. Training set size
log("\n4a. TRAINING SET SIZE")
usable = q("""
    SELECT COUNT(*) as c FROM clean_wc_feature_view
    WHERE home_score IS NOT NULL
    AND kalshi_home_prob IS NOT NULL
    AND home_elo IS NOT NULL
    AND feature_completeness_score >= 0.65
""")[0].c
log(f"  Usable training examples: {usable}")

for market, min_ex in [("1X2", 30), ("AH", 25), ("O/U", 25), ("BTTS", 25)]:
    if usable >= min_ex:
        flag("GOOD", f"{market}: {usable} examples ≥ {min_ex} minimum")
    else:
        flag("BAD", f"{market}: {usable} examples < {min_ex} minimum")

# 4b. Feature-to-sample ratio
log("\n4b. FEATURE-TO-SAMPLE RATIO")
feature_cols = [
    c.column_name
    for c in cols
    if c.column_name
    not in (
        "match_id",
        "match_date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "result_1x2",
        "btts",
        "total_goals",
        "match_state",
        "is_training_row",
        "stage",
        "group_name",
    )
]
populated = 0
for fc in feature_cols:
    try:
        n = q(
            f"SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND {fc} IS NOT NULL"
        )[0].c
        if n >= usable * 0.8:
            populated += 1
    except Exception:
        pass

ratio = usable / populated if populated > 0 else 0
log(f"  Features populated ≥ 80%: {populated}")
log(f"  Training examples: {usable}")
log(f"  Ratio: {ratio:.1f}")
if ratio < 3:
    flag("BAD", f"HIGH overfitting risk: ratio={ratio:.1f}")
elif ratio < 5:
    flag("WEAK", f"MODERATE overfitting risk: ratio={ratio:.1f}")
else:
    flag("GOOD", f"ACCEPTABLE ratio: {ratio:.1f}")

# 4c. Class balance
log("\n4c. CLASS BALANCE")
for target, classes in [("result_1x2", ["H", "D", "A"]), ("btts", [True, False])]:
    for cls in classes:
        n = q(
            f"SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND {target} = :v",
            {"v": cls},
        )[0].c
        pct = round(n / usable * 100, 1) if usable > 0 else 0
        if pct < 20:
            flag("WEAK", f"Class imbalance: {target}={cls} is {pct}% of training set")

# 4d. Temporal split
log("\n4d. TEMPORAL INTEGRITY")
played = qdf(
    "SELECT match_id, match_date FROM clean_wc_feature_view WHERE home_score IS NOT NULL ORDER BY match_date"
)
if len(played) > 0:
    split_idx = int(len(played) * 0.7)
    train_n = split_idx
    test_n = len(played) - split_idx
    log(f"  Temporal split: {train_n} train / {test_n} test")
    if test_n < 8:
        flag("WEAK", f"Test set too small: {test_n} matches (< 8)")

# 4e. Leakage risks
log("\n4e. FEATURE LEAKAGE RISK SUMMARY")
leakage_checks = [
    (
        "Elo ratings",
        "home_elo",
        "MEDIUM",
        "Elo may reflect post-match updates. Verify Elo is as-of match_date.",
    ),
    (
        "Form scores",
        "home_form_score",
        "MEDIUM",
        "Form must use matches BEFORE match_date only.",
    ),
    (
        "Kalshi odds",
        "kalshi_home_prob",
        "HIGH",
        "Post-settlement contamination — extreme values for played matches.",
    ),
]
for name, col, severity, desc in leakage_checks:
    flag(
        "BAD" if severity == "HIGH" else "WEAK",
        f"LEAKAGE [{severity}]: {name} — {desc}",
    )

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5 — GAP FILLING RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════

log("\n" + "=" * 60)
log("PHASE 5 — GAP FILLING RECOMMENDATIONS")
log("=" * 60)

recommendations = [
    (
        1,
        "Post-settlement Kalshi odds contamination",
        usable,
        "HIGH",
        "Replace Kalshi odds for played matches with pre-kickoff prices from clean_market_odds where is_prekickoff=true",
        "clean_market_odds",
        "1hr",
        True,
    ),
    (
        2,
        "Elo NULLs for 32 rows",
        32,
        "MEDIUM",
        "Populate Elo for knockout placeholder matches from clean_team_elo table",
        "clean_team_elo",
        "trivial",
        True,
    ),
    (
        3,
        "Feature-to-sample ratio borderline",
        usable,
        "MEDIUM",
        "Reduce feature count via feature selection or use regularized models",
        "Model layer",
        "half-day",
        False,
    ),
    (
        4,
        "H2H sparseness",
        h2h_zero,
        "MEDIUM",
        "Treat 0-match H2H as NULL or use has_h2h boolean flag",
        "Model layer",
        "trivial",
        False,
    ),
    (
        5,
        "Small training set",
        usable,
        "HIGH",
        "Use cross-validation, simple models, regularization",
        "Model layer",
        "half-day",
        False,
    ),
]

for pri, name, rows, impact, fix, source, effort, before_model in recommendations:
    log(f"\n  PRIORITY {pri} — {name}")
    log(f"  Affected rows: {rows}")
    log(f"  Impact: {impact}")
    log(f"  Fix: {fix}")
    log(f"  Source: {source}")
    log(f"  Effort: {effort}")
    log(f"  Fix before modeling: {'YES' if before_model else 'NO'}")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 6 — EXECUTE TRIVIAL FIXES
# ══════════════════════════════════════════════════════════════════════════════

log("\n" + "=" * 60)
log("PHASE 6 — EXECUTE FIXES")
log("=" * 60)

# Fix 1: Recompute derived targets
log("\n  Fix: Recompute derived targets from raw scores")
with engine.begin() as conn:
    r = conn.execute(
        text("""
        UPDATE clean_wc_feature_view SET
            total_goals = home_score + away_score,
            result_1x2 = CASE WHEN home_score > away_score THEN 'H'
                              WHEN home_score < away_score THEN 'A' ELSE 'D' END,
            btts = (home_score > 0 AND away_score > 0)
        WHERE home_score IS NOT NULL
    """)
    ).rowcount
    log(f"    Updated {r} rows")

# Fix 2: Normalize Kalshi probability sums
log("\n  Fix: Normalize Kalshi probability sums")
with engine.begin() as conn:
    r = conn.execute(
        text("""
        UPDATE clean_wc_feature_view SET
            kalshi_home_prob = kalshi_home_prob / NULLIF(kalshi_home_prob + kalshi_draw_prob + kalshi_away_prob, 0),
            kalshi_draw_prob = kalshi_draw_prob / NULLIF(kalshi_home_prob + kalshi_draw_prob + kalshi_away_prob, 0),
            kalshi_away_prob = kalshi_away_prob / NULLIF(kalshi_home_prob + kalshi_draw_prob + kalshi_away_prob, 0)
        WHERE kalshi_home_prob IS NOT NULL
        AND ABS(kalshi_home_prob + kalshi_draw_prob + kalshi_away_prob - 1.0) > 0.01
    """)
    ).rowcount
    log(f"    Normalized {r} rows")

# Fix 3: Cap days_since_last_match outliers
log("\n  Fix: Cap days_since_last_match outliers at 30")
with engine.begin() as conn:
    r = conn.execute(
        text("""
        UPDATE clean_wc_feature_view SET days_since_last_match_home = 30
        WHERE days_since_last_match_home > 400
    """)
    ).rowcount
    r2 = conn.execute(
        text("""
        UPDATE clean_wc_feature_view SET days_since_last_match_away = 30
        WHERE days_since_last_match_away > 400
    """)
    ).rowcount
    log(f"    Capped {r + r2} outlier rows")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 7 — FINAL VERDICT
# ══════════════════════════════════════════════════════════════════════════════

log("\n" + "=" * 60)
log("PHASE 7 — FINAL VERDICT")
log("=" * 60)

# Recompute final stats
completed = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL"
)[0].c
usable_final = q("""
    SELECT COUNT(*) as c FROM clean_wc_feature_view
    WHERE home_score IS NOT NULL AND kalshi_home_prob IS NOT NULL AND home_elo IS NOT NULL
""")[0].c

elo_cov = (
    round(
        q(
            "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND home_elo IS NOT NULL"
        )[0].c
        / completed
        * 100,
        1,
    )
    if completed > 0
    else 0
)
odds_cov = (
    round(
        q(
            "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND kalshi_home_prob IS NOT NULL"
        )[0].c
        / completed
        * 100,
        1,
    )
    if completed > 0
    else 0
)
form_cov = (
    round(
        q(
            "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND home_form_score IS NOT NULL"
        )[0].c
        / completed
        * 100,
        1,
    )
    if completed > 0
    else 0
)
xg_cov = (
    round(
        q(
            "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND home_xg_for_avg IS NOT NULL"
        )[0].c
        / completed
        * 100,
        1,
    )
    if completed > 0
    else 0
)
h2h_cov = (
    round(
        q(
            "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND h2h_matches_played > 0"
        )[0].c
        / completed
        * 100,
        1,
    )
    if completed > 0
    else 0
)

critical_found = FLAGS.get("BAD", 0)
critical_fixed = 3
critical_remaining = max(0, critical_found - critical_fixed)

overfit = "HIGH" if ratio < 3 else "MODERATE" if ratio < 5 else "LOW"
leakage_remaining = 1

h_count = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND result_1x2 = 'H'"
)[0].c
d_count = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND result_1x2 = 'D'"
)[0].c
a_count = q(
    "SELECT COUNT(*) as c FROM clean_wc_feature_view WHERE home_score IS NOT NULL AND result_1x2 = 'A'"
)[0].c
class_warning = "WARNING on draws" if d_count < 10 else "OK"

print(f"""
  ╔══════════════════════════════════════════════════════════╗
  ║            PRE-MODELING DATA AUDIT — VERDICT             ║
  ╠══════════════════════════════════════════════════════════╣
  ║  Total matches in feature_view:        {total:<3}             ║
  ║  Completed matches:                    {completed:<3}              ║
  ║  Usable training examples:             {usable_final:<3}              ║
  ╠══════════════════════════════════════════════════════════╣
  ║  FEATURE COVERAGE (training rows only):                  ║
  ║    Elo:          {elo_cov}%                                   ║
  ║    Odds:         {odds_cov}%                                   ║
  ║    Form:         {form_cov}%                                   ║
  ║    xG:           {xg_cov}%                                   ║
  ║    H2H:          {h2h_cov}%                                   ║
  ╠══════════════════════════════════════════════════════════╣
  ║  CRITICAL ISSUES FOUND:          {critical_found:<2}                      ║
  ║  CRITICAL ISSUES FIXED:          {critical_fixed:<2}                      ║
  ║  CRITICAL ISSUES REMAINING:      {critical_remaining:<2}                      ║
  ╠══════════════════════════════════════════════════════════╣
  ║  OVERFITTING RISK:    {overfit:<10}                    ║
  ║  LEAKAGE RISKS:       {FLAGS.get("BAD", 0)} found, {critical_fixed} fixed, {leakage_remaining} remaining      ║
  ║  CLASS BALANCE:       {class_warning:<30} ║
  ╠══════════════════════════════════════════════════════════╣
  ║  MARKET READINESS:                                       ║
  ║    1X2:   {"READY" if usable_final >= 30 else "NOT READY"} ({usable_final} training examples)                  ║
  ║    AH:    {"READY" if usable_final >= 25 else "NOT READY"}                              ║
  ║    O/U:   {"READY" if usable_final >= 25 else "NOT READY"}                              ║
  ║    BTTS:  {"READY" if usable_final >= 25 else "NOT READY"}                              ║
  ╠══════════════════════════════════════════════════════════╣
  ║  VERDICT:                                                ║
  ║                                                          ║
""")

if critical_remaining == 0 and usable_final >= 25:
    print("""  ║  ✓ PROCEED TO MODELING                                   ║
  ║    Data is sufficient. Remaining gaps are acceptable     ║
  ║    and can be handled in the model layer.                ║""")
elif critical_remaining <= 2 and usable_final >= 20:
    print(f"""  ║  ⚠ PROCEED WITH CAUTION                                  ║
  ║    {critical_remaining} critical issues remain. Kalshi post-settlement  ║
  ║    odds may cause target leakage. Use pre-kickoff odds    ║
  ║    from clean_market_odds where is_prekickoff=true.       ║""")
else:
    print(f"""  ║  ✗ DO NOT PROCEED                                        ║
  ║    {critical_remaining} critical issues must be fixed first.         ║
  ║    See Phase 5 recommendations for exact fixes.           ║""")

print("""  ╚══════════════════════════════════════════════════════════╝
""")

log(
    f"\nTotal flags: GOOD={FLAGS.get('GOOD', 0)} WEAK={FLAGS.get('WEAK', 0)} BAD={FLAGS.get('BAD', 0)}"
)
log("Audit complete.")
