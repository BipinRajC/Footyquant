from footyquant.clean_modeling import CLEAN_TABLES, build_clean_modeling_sql


def test_clean_modeling_table_contract_contains_core_sources():
    assert CLEAN_TABLES == [
        "clean_wc_teams",
        "clean_wc_fixtures",
        "clean_wc2026_match_stats",
        "clean_wc_qualifiers",
        "clean_wc_tournament_matches",
        "clean_international_matches",
        "clean_team_elo",
        "clean_team_form_stats",
        "clean_wc_feature_view",
    ]


def test_clean_modeling_sql_only_drops_clean_tables():
    sql = "\n".join(build_clean_modeling_sql()).lower()

    assert "drop table if exists public.clean_wc_teams" in sql
    assert "drop table if exists public.wc_matches" not in sql
    assert "drop table if exists public.matches" not in sql
    assert "drop table if exists public.teams" not in sql


def test_clean_modeling_sql_filters_international_history_since_2014():
    sql = "\n".join(build_clean_modeling_sql()).lower()

    assert "date '2014-06-12'" in sql
    assert "clean_international_matches" in sql
    assert "home_team_id in (select canonical_id from public.clean_wc_teams)" in sql
    assert "away_team_id in (select canonical_id from public.clean_wc_teams)" in sql


def test_clean_team_mapping_prefers_team_rows_with_elo_history():
    sql = "\n".join(build_clean_modeling_sql()).lower()

    assert "elo_count" in sql
    assert "order by (count(e.*) > 0) desc" in sql


def test_clean_modeling_builds_team_form_and_derived_features():
    sql = "\n".join(build_clean_modeling_sql()).lower()

    assert "create table public.clean_team_form_stats" in sql
    assert "from public.team_stats" in sql
    assert "congo dr" in sql
    assert "home_form_score" in sql
    assert "away_form_score" in sql
    assert "h2h_matches_played" in sql
    assert "days_since_last_match_home" in sql
