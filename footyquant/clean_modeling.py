"""SQL contract for rebuildable clean modeling tables."""

CLEAN_TABLES = [
    "clean_wc_teams",
    "clean_wc_fixtures",
    "clean_wc2026_match_stats",
    "clean_wc_qualifiers",
    "clean_wc_tournament_matches",
    "clean_international_matches",
    "clean_team_elo",
    "clean_team_form_stats",
    "clean_team_fotmob_form",
    "clean_wc_feature_view",
]


def build_clean_modeling_sql() -> list[str]:
    """Return ordered SQL statements to rebuild the clean modeling layer."""
    return [
        *[_drop(table) for table in reversed(CLEAN_TABLES)],
        _clean_wc_teams_sql(),
        _clean_wc_fixtures_sql(),
        _clean_wc2026_match_stats_sql(),
        _clean_wc_qualifiers_sql(),
        _clean_wc_tournament_matches_sql(),
        _clean_international_matches_sql(),
        _clean_team_elo_sql(),
        _clean_team_form_stats_sql(),
        _clean_team_fotmob_form_sql(),
        _clean_wc_feature_view_sql(),
        *_index_sql(),
    ]


def _drop(table: str) -> str:
    return f"DROP TABLE IF EXISTS public.{table} CASCADE"


def _clean_wc_teams_sql() -> str:
    return """
CREATE TABLE public.clean_wc_teams AS
WITH wc_team_names AS (
    SELECT DISTINCT name
    FROM (
        SELECT home_team AS name FROM public.wc_matches WHERE home_team NOT SIMILAR TO '[0-9]%' AND home_team NOT ILIKE '%Winner%' AND home_team NOT ILIKE '%Loser%' AND home_team NOT ILIKE '%/%'
        UNION ALL
        SELECT away_team AS name FROM public.wc_matches WHERE away_team NOT SIMILAR TO '[0-9]%' AND away_team NOT ILIKE '%Winner%' AND away_team NOT ILIKE '%Loser%' AND away_team NOT ILIKE '%/%'
    ) names
), resolved AS (
    SELECT
        w.name AS wc_team_name,
        t.canonical_id,
        t.name AS source_team_name,
        t.aliases,
        t.confederation,
        t.oddspapi_participant_id,
        t.sofascore_id,
        t.polymarket_slug,
        t.kalshi_ticker,
        t.fbref_team_id,
        t.elo_count
    FROM wc_team_names w
    LEFT JOIN LATERAL (
        SELECT t.*, COUNT(e.*) AS elo_count
        FROM public.teams t
        LEFT JOIN public.elo_ratings e ON e.team_id = t.canonical_id
        WHERE t.name = w.name OR t.aliases @> to_jsonb(w.name)
        GROUP BY t.canonical_id
        ORDER BY (COUNT(e.*) > 0) DESC, (t.name = w.name) DESC, t.canonical_id
        LIMIT 1
    ) t ON TRUE
)
SELECT * FROM resolved
ORDER BY wc_team_name
""".strip()


def _clean_wc_fixtures_sql() -> str:
    return """
CREATE TABLE public.clean_wc_fixtures AS
SELECT
    w.*,
    (w.stage = 'group') AS is_group_stage,
    (w.stage = 'knockout') AS is_knockout,
    (w.home_score IS NOT NULL AND w.away_score IS NOT NULL) AS is_played,
    CASE WHEN w.home_score IS NULL THEN 'scheduled' ELSE 'played' END AS match_state
FROM public.wc_matches w
""".strip()


def _clean_wc2026_match_stats_sql() -> str:
    return """
CREATE TABLE public.clean_wc2026_match_stats AS
SELECT
    2026 AS tournament_year,
    'wc2026_matches'::text AS source_table,
    m.*,
    CASE
        WHEN m.hgft > m.agft THEN 'H'
        WHEN m.hgft = m.agft THEN 'D'
        WHEN m.hgft < m.agft THEN 'A'
        ELSE NULL
    END AS result_1x2,
    (m.hgft + m.agft) AS total_goals
FROM public.wc2026_matches m
""".strip()


def _clean_wc_qualifiers_sql() -> str:
    return """
CREATE TABLE public.clean_wc_qualifiers AS
SELECT
    'wc2026_qualifiers'::text AS source_table,
    q.*,
    CASE
        WHEN q.hg > q.ag THEN 'H'
        WHEN q.hg = q.ag THEN 'D'
        WHEN q.hg < q.ag THEN 'A'
        ELSE NULL
    END AS result_1x2,
    (q.hg + q.ag) AS total_goals
FROM public.wc2026_qualifiers q
""".strip()


def _clean_wc_tournament_matches_sql() -> str:
    return """
CREATE TABLE public.clean_wc_tournament_matches AS
SELECT 2014 AS tournament_year, 'wc2014_matches'::text AS source_table,
       id, home, away, date, time, hgft, agft, hg1st, ag1st, hg2nd, ag2nd,
       hget, aget, hgp, agp, finished, hs, as_shots, hst, ast, hf, af, hc, ac,
       hy, ay, hr, ar, NULL::double precision AS hxg, NULL::double precision AS axg,
       b365_h, b365_d, b365_a, NULL::double precision AS bf_h, NULL::double precision AS bf_d,
       NULL::double precision AS bf_a, pinny_h, pinny_d, pinny_a, max_h, max_d, max_a,
       avg_h, avg_d, avg_a,
       CASE WHEN hgft > agft THEN 'H' WHEN hgft = agft THEN 'D' WHEN hgft < agft THEN 'A' END AS result_1x2,
       (hgft + agft) AS total_goals,
       to_jsonb(wc2014_matches.*) AS raw_row
FROM public.wc2014_matches
UNION ALL
SELECT 2018, 'wc2018_matches',
       id, home, away, date, time, hgft, agft, hg1st, ag1st, hg2nd, ag2nd,
       hget, aget, hgp, agp, finished, hs, as_shots, hst, ast, hf, af, hc, ac,
       hy, ay, hr, ar, NULL::double precision, NULL::double precision,
       NULL::double precision, NULL::double precision, NULL::double precision,
       NULL::double precision, NULL::double precision, NULL::double precision,
       pinny_h, pinny_d, pinny_a, max_h, max_d, max_a, avg_h, avg_d, avg_a,
       CASE WHEN hgft > agft THEN 'H' WHEN hgft = agft THEN 'D' WHEN hgft < agft THEN 'A' END,
       (hgft + agft),
       to_jsonb(wc2018_matches.*)
FROM public.wc2018_matches
UNION ALL
SELECT 2022, 'wc2022_matches',
       id, home, away, date, time, hgft, agft, hg1st, ag1st, hg2nd, ag2nd,
       hget, aget, hgp, agp, finished, hs, as_shots, hst, ast, hf, af, hc, ac,
       hy, ay, hr, ar, NULL::double precision, NULL::double precision,
       b365_h, b365_d, b365_a, bf_h, bf_d, bf_a,
       NULL::double precision, NULL::double precision, NULL::double precision,
       max_h, max_d, max_a, avg_h, avg_d, avg_a,
       CASE WHEN hgft > agft THEN 'H' WHEN hgft = agft THEN 'D' WHEN hgft < agft THEN 'A' END,
       (hgft + agft),
       to_jsonb(wc2022_matches.*)
FROM public.wc2022_matches
UNION ALL
SELECT 2026, 'wc2026_matches',
       id, home, away, date, time, hgft, agft, hg1st, ag1st, hg2nd, ag2nd,
       hget, aget, hgp, agp, finished, hs, as_shots, hst, ast, hf, af, hc, ac,
       hy, ay, hr, ar, hxg, axg, b365_h, b365_d, b365_a, bf_h, bf_d, bf_a,
       NULL::double precision, NULL::double precision, NULL::double precision,
       max_h, max_d, max_a, avg_h, avg_d, avg_a,
       CASE WHEN hgft > agft THEN 'H' WHEN hgft = agft THEN 'D' WHEN hgft < agft THEN 'A' END,
       (hgft + agft),
       to_jsonb(wc2026_matches.*)
FROM public.wc2026_matches
""".strip()


def _clean_international_matches_sql() -> str:
    return """
CREATE TABLE public.clean_international_matches AS
SELECT
    m.match_id,
    m.fotmob_match_id,
    m.oddspapi_fixture_id,
    m.date_utc,
    m.kickoff_utc,
    m.tournament,
    m.is_neutral,
    m.venue,
    m.status,
    m.home_team_id,
    ht.name AS home_team,
    m.away_team_id,
    at.name AS away_team,
    m.home_goals,
    m.away_goals,
    m.home_xg,
    m.away_xg,
    CASE
        WHEN m.home_goals > m.away_goals THEN 'H'
        WHEN m.home_goals = m.away_goals THEN 'D'
        WHEN m.home_goals < m.away_goals THEN 'A'
        ELSE NULL
    END AS result_1x2,
    (m.home_goals + m.away_goals) AS total_goals,
    (m.tournament ILIKE '%friendly%') AS is_friendly,
    (m.home_team_id IN (SELECT canonical_id FROM public.clean_wc_teams)) AS home_is_wc2026_team,
    (m.away_team_id IN (SELECT canonical_id FROM public.clean_wc_teams)) AS away_is_wc2026_team
FROM public.matches m
LEFT JOIN public.teams ht ON ht.canonical_id = m.home_team_id
LEFT JOIN public.teams at ON at.canonical_id = m.away_team_id
WHERE m.date_utc >= DATE '2014-06-12'
  AND m.home_goals IS NOT NULL
  AND m.away_goals IS NOT NULL
  AND (
      m.home_team_id IN (SELECT canonical_id FROM public.clean_wc_teams)
      OR m.away_team_id IN (SELECT canonical_id FROM public.clean_wc_teams)
  )
""".strip()


def _clean_team_elo_sql() -> str:
    return """
CREATE TABLE public.clean_team_elo AS
SELECT
    e.id,
    e.team_id,
    t.wc_team_name,
    e.rating,
    e.as_of_date
FROM public.elo_ratings e
JOIN public.clean_wc_teams t ON t.canonical_id = e.team_id
""".strip()


def _clean_team_form_stats_sql() -> str:
    return """
CREATE TABLE public.clean_team_form_stats AS
SELECT
    ts.id AS source_stat_id,
    c.canonical_id AS team_id,
    c.wc_team_name,
    lt.name AS source_team_name,
    ts.stat_type,
    ts.value,
    ts.sample_window,
    ts.as_of_date,
    ts.match_count_in_window,
    ts.opponent_strength_avg,
    ts.source,
    ts.captured_at_utc,
    ts.raw_response
FROM public.team_stats ts
JOIN public.teams lt ON lt.canonical_id = ts.team_id
JOIN public.clean_wc_teams c ON (
    c.canonical_id = ts.team_id
    OR c.wc_team_name = lt.name
    OR c.source_team_name = lt.name
    OR c.aliases @> to_jsonb(lt.name)
    OR lt.aliases @> to_jsonb(c.wc_team_name)
    OR (c.wc_team_name = 'DR Congo' AND lt.name = 'Congo DR')
)
""".strip()


def _clean_team_fotmob_form_sql() -> str:
    return """
CREATE TABLE public.clean_team_fotmob_form AS
WITH team_matches AS (
    SELECT
        r.home_team AS team_name,
        r.match_date,
        r.xg_home AS xg_for,
        r.xg_away AS xg_against,
        r.possession_home AS possession,
        r.shots_ontarget_home AS shots_ontarget,
        r.big_chances_home AS big_chances,
        r.passes_accurate_home AS passes_accurate,
        r.duels_won_home AS duels_won,
        r.corners_home AS corners,
        r.yellow_cards_home AS yellow_cards
    FROM public.wcmatches_richstat_fotmob r
    WHERE r.home_score IS NOT NULL
    UNION ALL
    SELECT
        r.away_team AS team_name,
        r.match_date,
        r.xg_away AS xg_for,
        r.xg_home AS xg_against,
        r.possession_away AS possession,
        r.shots_ontarget_away AS shots_ontarget,
        r.big_chances_away AS big_chances,
        r.passes_accurate_away AS passes_accurate,
        r.duels_won_away AS duels_won,
        r.corners_away AS corners,
        r.yellow_cards_away AS yellow_cards
    FROM public.wcmatches_richstat_fotmob r
    WHERE r.home_score IS NOT NULL
), team_matches_ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY team_name ORDER BY match_date DESC) AS rn
    FROM team_matches
), team_form AS (
    SELECT
        team_name,
        match_date AS as_of_date,
        AVG(xg_for) FILTER (WHERE rn <= 3) AS xg_for_l3,
        AVG(xg_against) FILTER (WHERE rn <= 3) AS xg_against_l3,
        AVG(possession) FILTER (WHERE rn <= 3) AS possession_l3,
        AVG(shots_ontarget) FILTER (WHERE rn <= 3) AS shots_ontarget_l3,
        AVG(big_chances) FILTER (WHERE rn <= 3) AS big_chances_l3,
        AVG(passes_accurate) FILTER (WHERE rn <= 3) AS passes_accurate_l3,
        AVG(duels_won) FILTER (WHERE rn <= 3) AS duels_won_l3,
        AVG(corners) FILTER (WHERE rn <= 3) AS corners_l3,
        AVG(yellow_cards) FILTER (WHERE rn <= 3) AS yellow_cards_l3,
        AVG(xg_for) FILTER (WHERE rn <= 5) AS xg_for_l5,
        AVG(xg_against) FILTER (WHERE rn <= 5) AS xg_against_l5,
        AVG(possession) FILTER (WHERE rn <= 5) AS possession_l5,
        AVG(shots_ontarget) FILTER (WHERE rn <= 5) AS shots_ontarget_l5,
        AVG(big_chances) FILTER (WHERE rn <= 5) AS big_chances_l5,
        AVG(passes_accurate) FILTER (WHERE rn <= 5) AS passes_accurate_l5,
        AVG(duels_won) FILTER (WHERE rn <= 5) AS duels_won_l5,
        AVG(corners) FILTER (WHERE rn <= 5) AS corners_l5,
        AVG(yellow_cards) FILTER (WHERE rn <= 5) AS yellow_cards_l5,
        COUNT(*) FILTER (WHERE rn <= 3) AS match_count_l3,
        COUNT(*) FILTER (WHERE rn <= 5) AS match_count_l5
    FROM team_matches_ranked
    GROUP BY team_name, match_date
)
SELECT * FROM team_form
ORDER BY team_name, as_of_date
""".strip()


def _clean_wc_feature_view_sql() -> str:
    return """
CREATE TABLE public.clean_wc_feature_view AS
WITH odds AS (
    SELECT
        match_id,
        MAX(probability) FILTER (WHERE source = 'kalshi' AND market_type = '1x2' AND outcome = 'home') AS kalshi_home_prob,
        MAX(probability) FILTER (WHERE source = 'kalshi' AND market_type = '1x2' AND outcome = 'draw') AS kalshi_draw_prob,
        MAX(probability) FILTER (WHERE source = 'kalshi' AND market_type = '1x2' AND outcome = 'away') AS kalshi_away_prob,
        MAX(probability) FILTER (WHERE source = 'polymarket' AND market_type = '1x2' AND outcome = 'home') AS polymarket_home_prob,
        MAX(probability) FILTER (WHERE source = 'polymarket' AND market_type = '1x2' AND outcome = 'draw') AS polymarket_draw_prob,
        MAX(probability) FILTER (WHERE source = 'polymarket' AND market_type = '1x2' AND outcome = 'away') AS polymarket_away_prob,
        MAX(probability) FILTER (WHERE source = 'kalshi' AND market_type = 'btts' AND outcome = 'yes') AS kalshi_btts_yes_prob,
        MAX(probability) FILTER (WHERE source = 'kalshi' AND market_type = 'over_under' AND outcome = 'over' AND line = 2.5) AS kalshi_over_25_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_bet365' AND market_type = '1x2' AND outcome = 'home') AS xlsx_bet365_home_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_bet365' AND market_type = '1x2' AND outcome = 'draw') AS xlsx_bet365_draw_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_bet365' AND market_type = '1x2' AND outcome = 'away') AS xlsx_bet365_away_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_betfair' AND market_type = '1x2' AND outcome = 'home') AS xlsx_betfair_home_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_betfair' AND market_type = '1x2' AND outcome = 'draw') AS xlsx_betfair_draw_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_betfair' AND market_type = '1x2' AND outcome = 'away') AS xlsx_betfair_away_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_avg' AND market_type = '1x2' AND outcome = 'home') AS xlsx_avg_home_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_avg' AND market_type = '1x2' AND outcome = 'draw') AS xlsx_avg_draw_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_avg' AND market_type = '1x2' AND outcome = 'away') AS xlsx_avg_away_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_max' AND market_type = '1x2' AND outcome = 'home') AS xlsx_max_home_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_max' AND market_type = '1x2' AND outcome = 'draw') AS xlsx_max_draw_prob,
        MAX(probability) FILTER (WHERE source = 'xlsx_max' AND market_type = '1x2' AND outcome = 'away') AS xlsx_max_away_prob
    FROM public.clean_market_odds
    GROUP BY match_id
), form AS (
    SELECT
        team_id,
        MAX(value) FILTER (WHERE stat_type = 'form_score' AND sample_window = 'last_5_win_rate') AS form_score_l5,
        MAX(value) FILTER (WHERE stat_type = 'form_score' AND sample_window = 'last_10_win_rate') AS form_score_l10,
        MAX(value) FILTER (WHERE stat_type = 'form_score' AND sample_window = 'last_20_win_rate') AS form_score_l20,
        MAX(value) FILTER (WHERE stat_type = 'win_rate' AND sample_window = 'last_5_fraction') AS win_rate_l5,
        MAX(value) FILTER (WHERE stat_type = 'goals_for' AND sample_window = 'last_5_avg_per_match') AS goals_for_l5,
        MAX(value) FILTER (WHERE stat_type = 'goals_against' AND sample_window = 'last_5_avg_per_match') AS goals_against_l5,
        MAX(value) FILTER (WHERE stat_type = 'xg_for' AND sample_window = 'last_5_avg_per_match') AS xg_for_l5,
        MAX(value) FILTER (WHERE stat_type = 'xg_against' AND sample_window = 'last_5_avg_per_match') AS xg_against_l5,
        MAX(value) FILTER (WHERE stat_type = 'xg_for' AND sample_window = 'last_10_avg_per_match') AS xg_for_l10,
        MAX(value) FILTER (WHERE stat_type = 'xg_against' AND sample_window = 'last_10_avg_per_match') AS xg_against_l10
    FROM public.clean_team_form_stats
    GROUP BY team_id
), fixture_teams AS (
    SELECT
        f.*,
        ht.canonical_id AS home_team_id,
        at.canonical_id AS away_team_id
    FROM public.clean_wc_fixtures f
    LEFT JOIN public.clean_wc_teams ht ON ht.wc_team_name = f.home_team
    LEFT JOIN public.clean_wc_teams at ON at.wc_team_name = f.away_team
), fotmob_stats AS (
    SELECT DISTINCT ON (f.match_id)
        f.match_id,
        r.possession_home, r.possession_away,
        r.xg_home, r.xg_away,
        r.xgot_home, r.xgot_away,
        r.shots_home, r.shots_away,
        r.shots_ontarget_home, r.shots_ontarget_away,
        r.corners_home, r.corners_away,
        r.yellow_cards_home, r.yellow_cards_away,
        r.fouls_home, r.fouls_away,
        r.passes_accurate_home, r.passes_accurate_away,
        r.tackles_home, r.tackles_away,
        r.saves_home, r.saves_away,
        r.duels_won_home, r.duels_won_away,
        r.aerials_won_home, r.aerials_won_away,
        r.big_chances_home, r.big_chances_away,
        r.touches_opp_box_home, r.touches_opp_box_away,
        r.offsides_home, r.offsides_away
    FROM public.wcmatches_richstat_fotmob r
    JOIN public.matches m ON m.fotmob_match_id = r.fotmob_match_id
    JOIN public.clean_wc_fixtures f ON f.match_date::date = m.date_utc
    JOIN public.clean_wc_teams ht ON ht.canonical_id = m.home_team_id
    JOIN public.clean_wc_teams at ON at.canonical_id = m.away_team_id
    WHERE (f.home_team = ht.wc_team_name AND f.away_team = at.wc_team_name)
       OR (f.home_team = at.wc_team_name AND f.away_team = ht.wc_team_name)
)
SELECT
    f.match_id,
    f.match_date,
    f.stage,
    f.group_name,
    f.home_team,
    f.away_team,
    f.home_score,
    f.away_score,
    f.result_1x2,
    f.btts,
    f.total_goals,
    f.match_state,
    he.rating AS home_elo,
    ae.rating AS away_elo,
    (he.rating - ae.rating) AS elo_diff,
    o.kalshi_home_prob,
    o.kalshi_draw_prob,
    o.kalshi_away_prob,
    o.polymarket_home_prob,
    o.polymarket_draw_prob,
    o.polymarket_away_prob,
    o.kalshi_btts_yes_prob,
    o.kalshi_over_25_prob,
    (1 - o.kalshi_over_25_prob) AS kalshi_under_25_prob,
    o.xlsx_bet365_home_prob,
    o.xlsx_bet365_draw_prob,
    o.xlsx_bet365_away_prob,
    o.xlsx_betfair_home_prob,
    o.xlsx_betfair_draw_prob,
    o.xlsx_betfair_away_prob,
    o.xlsx_avg_home_prob,
    o.xlsx_avg_draw_prob,
    o.xlsx_avg_away_prob,
    o.xlsx_max_home_prob,
    o.xlsx_max_draw_prob,
    o.xlsx_max_away_prob,
    hf.form_score_l5 AS home_form_score,
    af.form_score_l5 AS away_form_score,
    hf.win_rate_l5 AS home_win_rate_l5,
    af.win_rate_l5 AS away_win_rate_l5,
    hf.goals_for_l5 AS home_goals_scored_l5,
    af.goals_for_l5 AS away_goals_scored_l5,
    hf.goals_against_l5 AS home_goals_conceded_l5,
    af.goals_against_l5 AS away_goals_conceded_l5,
    hf.xg_for_l5 AS home_xg_for_avg,
    af.xg_for_l5 AS away_xg_for_avg,
    hf.xg_against_l5 AS home_xg_against_avg,
    af.xg_against_l5 AS away_xg_against_avg,
    (hf.xg_for_l5 - hf.xg_against_l5) AS home_xg_diff,
    (af.xg_for_l5 - af.xg_against_l5) AS away_xg_diff,
    home_last.days_since_last_match AS days_since_last_match_home,
    away_last.days_since_last_match AS days_since_last_match_away,
    h2h.h2h_matches_played,
    h2h.h2h_home_wins,
    h2h.h2h_draws,
    h2h.h2h_away_wins,
    h2h.h2h_avg_goals,
    h2h.h2h_btts_rate,
    (o.kalshi_home_prob IS NOT NULL AND o.kalshi_draw_prob IS NOT NULL AND o.kalshi_away_prob IS NOT NULL) AS has_clean_kalshi_1x2,
    (o.polymarket_home_prob IS NOT NULL AND o.polymarket_draw_prob IS NOT NULL AND o.polymarket_away_prob IS NOT NULL) AS has_clean_polymarket_1x2,
    (
        (o.kalshi_home_prob IS NOT NULL)::int +
        (o.polymarket_home_prob IS NOT NULL)::int +
        (he.rating IS NOT NULL AND ae.rating IS NOT NULL)::int +
        (hf.form_score_l5 IS NOT NULL AND af.form_score_l5 IS NOT NULL)::int +
        (h2h.h2h_matches_played IS NOT NULL)::int
    ) / 5.0 AS feature_completeness_score,
    (f.match_state = 'played') AS is_training_row,
    fs.possession_home, fs.possession_away,
    fs.xg_home AS fotmob_xg_home, fs.xg_away AS fotmob_xg_away,
    fs.xgot_home, fs.xgot_away,
    fs.shots_home AS fotmob_shots_home, fs.shots_away AS fotmob_shots_away,
    fs.shots_ontarget_home, fs.shots_ontarget_away,
    fs.corners_home AS fotmob_corners_home, fs.corners_away AS fotmob_corners_away,
    fs.yellow_cards_home, fs.yellow_cards_away,
    fs.fouls_home AS fotmob_fouls_home, fs.fouls_away AS fotmob_fouls_away,
    fs.passes_accurate_home, fs.passes_accurate_away,
    fs.tackles_home AS fotmob_tackles_home, fs.tackles_away AS fotmob_tackles_away,
    fs.saves_home, fs.saves_away,
    fs.duels_won_home, fs.duels_won_away,
    fs.aerials_won_home, fs.aerials_won_away,
    fs.big_chances_home, fs.big_chances_away,
    fs.touches_opp_box_home, fs.touches_opp_box_away,
    fs.offsides_home, fs.offsides_away,
    hff.xg_for_l3 AS home_xg_for_l3, aff.xg_for_l3 AS away_xg_for_l3,
    hff.xg_against_l3 AS home_xg_against_l3, aff.xg_against_l3 AS away_xg_against_l3,
    hff.possession_l3 AS home_possession_l3, aff.possession_l3 AS away_possession_l3,
    hff.shots_ontarget_l3 AS home_shots_ot_l3, aff.shots_ontarget_l3 AS away_shots_ot_l3,
    hff.big_chances_l3 AS home_big_chances_l3, aff.big_chances_l3 AS away_big_chances_l3,
    hff.passes_accurate_l3 AS home_passes_l3, aff.passes_accurate_l3 AS away_passes_l3,
    hff.duels_won_l3 AS home_duels_l3, aff.duels_won_l3 AS away_duels_l3,
    hff.corners_l3 AS home_corners_l3, aff.corners_l3 AS away_corners_l3,
    hff.yellow_cards_l3 AS home_yellow_l3, aff.yellow_cards_l3 AS away_yellow_l3,
    hff.xg_for_l5 AS home_xg_for_l5, aff.xg_for_l5 AS away_xg_for_l5,
    hff.xg_against_l5 AS home_xg_against_l5, aff.xg_against_l5 AS away_xg_against_l5,
    hff.possession_l5 AS home_possession_l5, aff.possession_l5 AS away_possession_l5,
    hff.shots_ontarget_l5 AS home_shots_ot_l5, aff.shots_ontarget_l5 AS away_shots_ot_l5,
    hff.big_chances_l5 AS home_big_chances_l5, aff.big_chances_l5 AS away_big_chances_l5,
    hff.match_count_l3 AS home_match_count_l3, aff.match_count_l3 AS away_match_count_l3,
    hff.match_count_l5 AS home_match_count_l5, aff.match_count_l5 AS away_match_count_l5
FROM fixture_teams f
LEFT JOIN fotmob_stats fs ON fs.match_id = f.match_id
LEFT JOIN odds o ON o.match_id = f.match_id
LEFT JOIN form hf ON hf.team_id = f.home_team_id
LEFT JOIN form af ON af.team_id = f.away_team_id
LEFT JOIN LATERAL (
    SELECT rating
    FROM public.clean_team_elo e
    WHERE e.team_id = f.home_team_id AND e.as_of_date <= f.match_date::date
    ORDER BY e.as_of_date DESC
    LIMIT 1
) he ON TRUE
LEFT JOIN LATERAL (
    SELECT rating
    FROM public.clean_team_elo e
    WHERE e.team_id = f.away_team_id AND e.as_of_date <= f.match_date::date
    ORDER BY e.as_of_date DESC
    LIMIT 1
) ae ON TRUE
LEFT JOIN LATERAL (
    SELECT (f.match_date::date - MAX(im.date_utc))::int AS days_since_last_match
    FROM public.clean_international_matches im
    WHERE im.date_utc < f.match_date::date
      AND (im.home_team_id = f.home_team_id OR im.away_team_id = f.home_team_id)
) home_last ON TRUE
LEFT JOIN LATERAL (
    SELECT (f.match_date::date - MAX(im.date_utc))::int AS days_since_last_match
    FROM public.clean_international_matches im
    WHERE im.date_utc < f.match_date::date
      AND (im.home_team_id = f.away_team_id OR im.away_team_id = f.away_team_id)
) away_last ON TRUE
LEFT JOIN LATERAL (
    SELECT
        COUNT(*)::int AS h2h_matches_played,
        COUNT(*) FILTER (
            WHERE (im.home_team_id = f.home_team_id AND im.home_goals > im.away_goals)
               OR (im.away_team_id = f.home_team_id AND im.away_goals > im.home_goals)
        )::int AS h2h_home_wins,
        COUNT(*) FILTER (WHERE im.home_goals = im.away_goals)::int AS h2h_draws,
        COUNT(*) FILTER (
            WHERE (im.home_team_id = f.away_team_id AND im.home_goals > im.away_goals)
               OR (im.away_team_id = f.away_team_id AND im.away_goals > im.home_goals)
        )::int AS h2h_away_wins,
        ROUND(AVG(im.total_goals)::numeric, 3)::double precision AS h2h_avg_goals,
        ROUND(AVG(CASE WHEN im.home_goals > 0 AND im.away_goals > 0 THEN 1.0 ELSE 0.0 END)::numeric, 3)::double precision AS h2h_btts_rate
    FROM public.clean_international_matches im
    WHERE im.date_utc < f.match_date::date
      AND (
          (im.home_team_id = f.home_team_id AND im.away_team_id = f.away_team_id)
          OR (im.home_team_id = f.away_team_id AND im.away_team_id = f.home_team_id)
      )
) h2h ON TRUE
LEFT JOIN LATERAL (
    SELECT
        xg_for_l3, xg_against_l3, possession_l3, shots_ontarget_l3,
        big_chances_l3, passes_accurate_l3, duels_won_l3, corners_l3, yellow_cards_l3,
        xg_for_l5, xg_against_l5, possession_l5, shots_ontarget_l5,
        big_chances_l5, passes_accurate_l5, duels_won_l5, corners_l5, yellow_cards_l5,
        match_count_l3, match_count_l5
    FROM public.clean_team_fotmob_form ff
    WHERE ff.team_name = f.home_team AND ff.as_of_date <= f.match_date::date
    ORDER BY ff.as_of_date DESC
    LIMIT 1
) hff ON TRUE
LEFT JOIN LATERAL (
    SELECT
        xg_for_l3, xg_against_l3, possession_l3, shots_ontarget_l3,
        big_chances_l3, passes_accurate_l3, duels_won_l3, corners_l3, yellow_cards_l3,
        xg_for_l5, xg_against_l5, possession_l5, shots_ontarget_l5,
        big_chances_l5, passes_accurate_l5, duels_won_l5, corners_l5, yellow_cards_l5,
        match_count_l3, match_count_l5
    FROM public.clean_team_fotmob_form ff
    WHERE ff.team_name = f.away_team AND ff.as_of_date <= f.match_date::date
    ORDER BY ff.as_of_date DESC
    LIMIT 1
) aff ON TRUE
""".strip()


def _index_sql() -> list[str]:
    return [
        "CREATE UNIQUE INDEX clean_wc_teams_name_idx ON public.clean_wc_teams (wc_team_name)",
        "CREATE UNIQUE INDEX clean_wc_fixtures_match_idx ON public.clean_wc_fixtures (match_id)",
        "CREATE INDEX clean_international_matches_date_idx ON public.clean_international_matches (date_utc)",
        "CREATE INDEX clean_international_matches_home_idx ON public.clean_international_matches (home_team_id)",
        "CREATE INDEX clean_international_matches_away_idx ON public.clean_international_matches (away_team_id)",
        "CREATE INDEX clean_team_elo_team_date_idx ON public.clean_team_elo (team_id, as_of_date)",
        "CREATE INDEX clean_team_form_stats_team_idx ON public.clean_team_form_stats (team_id, stat_type, sample_window)",
        "CREATE UNIQUE INDEX clean_wc_feature_view_match_idx ON public.clean_wc_feature_view (match_id)",
        "CREATE INDEX clean_team_fotmob_form_team_date_idx ON public.clean_team_fotmob_form (team_name, as_of_date)",
    ]
