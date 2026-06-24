from footyquant.clean_odds import (
    build_polymarket_recovery_rows,
    chunked,
    CLEAN_MARKET_ODDS_SOURCES,
    normalize_market_team_name,
    is_kalshi_1x2_usable,
    latest_kalshi_price_before_kickoff,
    latest_price_before_kickoff,
    polymarket_outcome_from_question,
)


def test_latest_price_before_kickoff_ignores_post_kickoff_points():
    history = [
        {"t": 100, "p": 0.42},
        {"t": 120, "p": 0.55},
        {"t": 125, "p": 0.99},
    ]

    assert latest_price_before_kickoff(history, kickoff_ts=121) == 0.55


def test_clean_market_odds_sources_exclude_pinnacle_and_include_xlsx():
    assert "pinnacle" not in CLEAN_MARKET_ODDS_SOURCES
    assert CLEAN_MARKET_ODDS_SOURCES == {
        "kalshi",
        "polymarket",
        "xlsx_bet365",
        "xlsx_betfair",
        "xlsx_max",
        "xlsx_avg",
    }


def test_xlsx_team_name_aliases_normalize_to_fixture_names():
    assert normalize_market_team_name("Czech Republic") == "czechia"
    assert normalize_market_team_name("Turkey") == "turkiye"
    assert (
        normalize_market_team_name("Bosnia & Herzegovina") == "bosnia and herzegovina"
    )
    assert normalize_market_team_name("D.R. Congo") == "dr congo"


def test_chunked_splits_rows_into_batch_sizes():
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_latest_kalshi_price_before_kickoff_uses_candle_close():
    candlesticks = [
        {"end_period_ts": 100, "price": {"close_dollars": "0.41"}},
        {"end_period_ts": 120, "price": {"close_dollars": "0.46"}},
        {"end_period_ts": 140, "price": {"close_dollars": "0.99"}},
    ]

    assert latest_kalshi_price_before_kickoff(candlesticks, kickoff_ts=121) == 0.46


def test_polymarket_recovery_builds_all_three_1x2_outcomes():
    snapshots = [
        {
            "wc_match_id": "4667001",
            "outcome": "home",
            "market_id": "home_condition",
            "raw_response": {"clobTokenIds": '["home_yes", "home_no"]'},
        },
        {
            "wc_match_id": "4667001",
            "outcome": "draw",
            "market_id": "draw_condition",
            "raw_response": {"clobTokenIds": '["draw_yes", "draw_no"]'},
        },
        {
            "wc_match_id": "4667001",
            "outcome": "away",
            "market_id": "away_condition",
            "raw_response": {"clobTokenIds": '["away_yes", "away_no"]'},
        },
    ]
    histories = {
        "home_yes": [{"t": 90, "p": 0.40}, {"t": 110, "p": 0.43}],
        "draw_yes": [{"t": 90, "p": 0.28}, {"t": 110, "p": 0.25}],
        "away_yes": [{"t": 90, "p": 0.32}, {"t": 110, "p": 0.31}],
    }

    rows = build_polymarket_recovery_rows(
        snapshots,
        kickoff_ts=100,
        get_history=lambda token_id: histories[token_id],
    )

    assert rows == [
        {
            "match_id": "4667001",
            "source": "polymarket",
            "market_type": "1x2",
            "outcome": "home",
            "probability": 0.40,
            "quality": "recovered_prekickoff",
            "source_market_id": "home_condition",
            "source_token_id": "home_yes",
        },
        {
            "match_id": "4667001",
            "source": "polymarket",
            "market_type": "1x2",
            "outcome": "draw",
            "probability": 0.28,
            "quality": "recovered_prekickoff",
            "source_market_id": "draw_condition",
            "source_token_id": "draw_yes",
        },
        {
            "match_id": "4667001",
            "source": "polymarket",
            "market_type": "1x2",
            "outcome": "away",
            "probability": 0.32,
            "quality": "recovered_prekickoff",
            "source_market_id": "away_condition",
            "source_token_id": "away_yes",
        },
    ]


def test_polymarket_outcome_from_question_works_for_settled_markets():
    assert (
        polymarket_outcome_from_question(
            "Will Mexico win on June 11?", "Mexico", "South Africa"
        )
        == "home"
    )
    assert (
        polymarket_outcome_from_question(
            "Will Mexico vs South Africa end in a draw?", "Mexico", "South Africa"
        )
        == "draw"
    )
    assert (
        polymarket_outcome_from_question(
            "Will South Africa win on June 11?", "Mexico", "South Africa"
        )
        == "away"
    )
    assert (
        polymarket_outcome_from_question(
            "Will Bosnia and Herzegovina win on 2026-06-12?",
            "Canada",
            "Bosnia-Herzegovina",
        )
        == "away"
    )


def test_kalshi_settled_result_leak_is_not_usable_for_played_training_match():
    assert not is_kalshi_1x2_usable(
        match_state="played",
        result_1x2="H",
        home_prob=0.99,
        draw_prob=0.01,
        away_prob=0.01,
    )

    assert is_kalshi_1x2_usable(
        match_state="scheduled",
        result_1x2=None,
        home_prob=0.76,
        draw_prob=0.18,
        away_prob=0.08,
    )
