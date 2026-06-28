"""Tests for xG-enhanced DC and expanded feature model."""

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_intl_df():
    return pd.DataFrame(
        {
            "date_utc": pd.to_datetime(["2026-01-15", "2026-02-10"]),
            "home_team": ["Brazil", "Germany"],
            "away_team": ["Argentina", "France"],
            "home_goals": [2, 1],
            "away_goals": [1, 1],
            "is_neutral": [False, False],
        }
    )


@pytest.fixture
def sample_tour_df():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-11", "2026-06-12"]),
            "home": ["Mexico", "South Korea"],
            "away": ["South Africa", "Czech Republic"],
            "hgft": [3, 0],
            "agft": [1, 2],
        }
    )


@pytest.fixture
def sample_feature_df():
    return pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "match_date": pd.to_datetime(["2026-06-11", "2026-06-12"]),
            "home_team": ["Mexico", "South Korea"],
            "away_team": ["South Africa", "Czech Republic"],
            "fotmob_xg_home": [2.8, 0.4],
            "fotmob_xg_away": [0.9, 1.8],
        }
    )


def test_prepare_dc_data_uses_xg_when_available(
    sample_intl_df, sample_tour_df, sample_feature_df
):
    from footyquant.modelling.model import _prepare_dc_data

    df = _prepare_dc_data(sample_intl_df, sample_tour_df, feature_df=sample_feature_df)

    mexico_row = df[df["home"] == "Mexico"].iloc[0]
    assert mexico_row["hg"] == pytest.approx(2.8, abs=0.01)
    assert mexico_row["ag"] == pytest.approx(0.9, abs=0.01)
    assert mexico_row["dc_weight"] == pytest.approx(1.5, abs=0.01)

    sk_row = df[df["home"] == "South Korea"].iloc[0]
    assert sk_row["hg"] == pytest.approx(0.4, abs=0.01)
    assert sk_row["ag"] == pytest.approx(1.8, abs=0.01)
    assert sk_row["dc_weight"] == pytest.approx(1.5, abs=0.01)


def test_prepare_dc_data_uses_raw_goals_when_no_xg(sample_intl_df, sample_tour_df):
    from footyquant.modelling.model import _prepare_dc_data

    df = _prepare_dc_data(sample_intl_df, sample_tour_df)

    brazil_row = df[df["home"] == "Brazil"].iloc[0]
    assert brazil_row["hg"] == 2
    assert brazil_row["ag"] == 1
    assert brazil_row["dc_weight"] == pytest.approx(1.0, abs=0.01)

    mexico_row = df[df["home"] == "Mexico"].iloc[0]
    assert mexico_row["hg"] == 3
    assert mexico_row["ag"] == 1
    assert mexico_row["dc_weight"] == pytest.approx(1.0, abs=0.01)


def test_prepare_dc_data_mixed_xg_and_raw(
    sample_intl_df, sample_tour_df, sample_feature_df
):
    from footyquant.modelling.model import _prepare_dc_data

    df = _prepare_dc_data(sample_intl_df, sample_tour_df, feature_df=sample_feature_df)

    xg_rows = df[df["dc_weight"] > 1.0]
    raw_rows = df[df["dc_weight"] == 1.0]

    assert len(xg_rows) == 2
    assert len(raw_rows) == 2
    assert set(xg_rows["home"]) == {"Mexico", "South Korea"}
    assert set(raw_rows["home"]) == {"Brazil", "Germany"}


def test_dc_time_weights_with_xg_boost():
    from footyquant.modelling.model import _dc_time_weights

    dates = pd.Series(pd.to_datetime(["2026-06-01", "2026-06-15", "2026-06-29"]))
    weights = _dc_time_weights(dates)

    assert len(weights) == 3
    assert weights[0] < weights[1] < weights[2]
    assert weights[2] == pytest.approx(1.0, abs=0.01)


def test_build_feature_matrix_15_features(sample_feature_df):
    from footyquant.modelling.model import _build_feature_matrix, FEATURE_COLS

    assert len(FEATURE_COLS) == 15
    assert "fotmob_xg_for_diff_l3" in FEATURE_COLS
    assert "fotmob_possession_diff_l3" in FEATURE_COLS
    assert "fotmob_shots_ot_diff_l3" in FEATURE_COLS
    assert "fotmob_big_chances_diff_l3" in FEATURE_COLS
    assert "fotmob_xg_for_diff_l5" in FEATURE_COLS
    assert "fotmob_xg_against_diff_l5" in FEATURE_COLS
    assert "elo_diff" in FEATURE_COLS
    assert "form_score_diff" in FEATURE_COLS
    assert "rest_days_diff" in FEATURE_COLS
    assert "h2h_home_win_rate" in FEATURE_COLS
    assert "xg_diff" not in FEATURE_COLS


def test_stats_market_corners_ou():
    from footyquant.modelling.model import predict_stats_market

    result = predict_stats_market(
        home_stat=5.0,
        away_stat=4.0,  # avg corners per match
        lines=[7.5, 9.5, 10.5],
    )

    assert "line" in result
    assert "over_prob" in result
    assert "under_prob" in result
    assert 0 < result["over_prob"] < 1
    assert 0 < result["under_prob"] < 1
    assert abs(result["over_prob"] + result["under_prob"] - 1.0) < 0.01


def test_stats_market_shots_on_target():
    from footyquant.modelling.model import predict_stats_market

    result = predict_stats_market(
        home_stat=6.0,
        away_stat=3.0,
        lines=[6.5, 8.5, 10.5],
    )

    assert result["line"] == 8.5
    assert result["over_prob"] > 0.5


def test_stats_market_cards():
    from footyquant.modelling.model import predict_stats_market

    result = predict_stats_market(
        home_stat=1.5,
        away_stat=1.0,
        lines=[2.5, 3.5, 4.5],
    )

    assert result["line"] == 2.5
    assert result["over_prob"] == pytest.approx(0.4562, abs=0.01)
    assert result["under_prob"] == pytest.approx(0.5438, abs=0.01)


def test_stats_market_confidence_high():
    from footyquant.modelling.model import assign_stats_confidence

    assert assign_stats_confidence(match_count_l3=3, ci_width=0.10) == "HIGH"
    assert assign_stats_confidence(match_count_l3=2, ci_width=0.10) == "MEDIUM"
    assert assign_stats_confidence(match_count_l3=1, ci_width=0.10) == "LOW"
    assert assign_stats_confidence(match_count_l3=3, ci_width=0.20) == "MEDIUM"
