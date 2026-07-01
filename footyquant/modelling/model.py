#!/usr/bin/env python3
"""WC 2026 Match Prediction Model.

Market-consensus base + calibrated corrections + Dixon-Coles Poisson.
Stores predictions in Supabase match_predictions table.
"""

from __future__ import annotations

import os
import json
import time
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from supabase import create_client

warnings.filterwarnings("ignore")

# ─── Config ───────────────────────────────────────────────────────────────────

MODEL_VERSION = "v2.0.0"
BOOTSTRAP_N = 1000
DC_HALF_LIFE_DAYS = 730
DC_MAX_GOALS = 5
BLEND_MARKET_WEIGHT = 0.7
BLEND_DC_WEIGHT = 0.3
CORRECTION_CAP = 0.05
LOGISTIC_C = 0.01
SOURCE_WEIGHTS = {
    "kalshi": 1.0,
    "polymarket": 1.0,
    "xlsx_betfair": 0.8,
    "xlsx_avg": 0.8,
    "xlsx_max": 0.8,
    "xlsx_bet365": 0.7,
}
KALSHI_CORRUPT_HIGH = 0.95
KALSHI_CORRUPT_LOW = 0.02

# ─── Supabase Client ──────────────────────────────────────────────────────────


def get_supabase() -> object:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        for dotenv_path in [
            os.path.join(os.path.dirname(__file__), ".env"),
            os.path.join(os.path.dirname(__file__), "..", ".env"),
            os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
            ".env",
        ]:
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
                if url and key:
                    break
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
    return create_client(url, key)


# ─── Data Loading ─────────────────────────────────────────────────────────────


def _fetch_all(
    supabase, table: str, select: str = "*", page_size: int = 1000
) -> list[dict]:
    """Paginated fetch from a Supabase table."""
    rows = []
    offset = 0
    while True:
        resp = (
            supabase.table(table)
            .select(select)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        chunk = resp.data
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size
    return rows


def load_feature_view(supabase) -> pd.DataFrame:
    rows = _fetch_all(supabase, "clean_wc_feature_view")
    df = pd.DataFrame(rows)
    df["match_date"] = pd.to_datetime(df["match_date"])
    return df


def load_market_odds(supabase) -> pd.DataFrame:
    rows = _fetch_all(supabase, "clean_market_odds")
    df = pd.DataFrame(rows)
    df["captured_at_utc"] = pd.to_datetime(df["captured_at_utc"])
    df = df[df["is_prekickoff"] == True].copy()
    return df


def load_international_matches(supabase) -> pd.DataFrame:
    rows = _fetch_all(supabase, "clean_international_matches", page_size=1000)
    df = pd.DataFrame(rows)
    df["date_utc"] = pd.to_datetime(df["date_utc"])
    df = df.dropna(subset=["home_goals", "away_goals"]).copy()
    df["home_goals"] = df["home_goals"].astype(int)
    df["away_goals"] = df["away_goals"].astype(int)
    return df


def load_tournament_matches(supabase) -> pd.DataFrame:
    rows = _fetch_all(supabase, "clean_wc_tournament_matches")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["hgft", "agft"]).copy()
    df["hgft"] = df["hgft"].astype(int)
    df["agft"] = df["agft"].astype(int)
    return df


def load_elo_ratings(supabase) -> pd.DataFrame:
    rows = _fetch_all(supabase, "clean_team_elo", page_size=2000)
    df = pd.DataFrame(rows)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    return df


# ─── Market Consensus Builder ─────────────────────────────────────────────────


def _is_kalshi_corrupted_vec(
    source: pd.Series, market_type: pd.Series, prob: pd.Series
) -> pd.Series:
    """Vectorized detection of settled Kalshi artifacts."""
    mask = (source == "kalshi") & (market_type == "1x2")
    return mask & ((prob >= KALSHI_CORRUPT_HIGH) | (prob <= KALSHI_CORRUPT_LOW))


def _precompute_odds_index(market_odds: pd.DataFrame) -> dict:
    """Pre-index market odds by (match_id, market_type) for O(1) lookups."""
    idx = {}
    corrupt_mask = _is_kalshi_corrupted_vec(
        market_odds["source"], market_odds["market_type"], market_odds["probability"]
    )
    clean = market_odds[~corrupt_mask]
    for key, grp in clean.groupby(["match_id", "market_type"]):
        idx[key] = grp
    return idx


_odds_index_cache: dict = {}


def _get_odds(odds_index: dict, match_id: str, market_type: str) -> pd.DataFrame | None:
    return odds_index.get((match_id, market_type))


def build_1x2_consensus(
    market_odds: pd.DataFrame, match_id: str, odds_index: dict | None = None
) -> dict | None:
    """Build de-vigged weighted consensus 1X2 probabilities for a match."""
    if odds_index is not None:
        odds_1x2 = _get_odds(odds_index, match_id, "1x2")
        if odds_1x2 is None or odds_1x2.empty:
            return None
    else:
        odds = market_odds[market_odds["match_id"] == match_id]
        odds_1x2 = odds[odds["market_type"] == "1x2"]
        corrupt = _is_kalshi_corrupted_vec(
            odds_1x2["source"], odds_1x2["market_type"], odds_1x2["probability"]
        )
        odds_1x2 = odds_1x2[~corrupt]
        if odds_1x2.empty:
            return None

    sources = {}
    for source, grp in odds_1x2.groupby("source"):
        probs = {}
        for _, r in grp.iterrows():
            probs[r["outcome"]] = r["probability"]
        if {"home", "draw", "away"}.issubset(probs.keys()):
            total = probs["home"] + probs["draw"] + probs["away"]
            if total > 0:
                sources[source] = {
                    "home": probs["home"] / total,
                    "draw": probs["draw"] / total,
                    "away": probs["away"] / total,
                }

    if not sources:
        return None

    total_weight = sum(SOURCE_WEIGHTS.get(s, 0.5) for s in sources)
    consensus = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for source, probs in sources.items():
        w = SOURCE_WEIGHTS.get(source, 0.5)
        for k in consensus:
            consensus[k] += w * probs[k]
    for k in consensus:
        consensus[k] /= total_weight

    consensus["sources"] = list(sources.keys())
    consensus["n_sources"] = len(sources)
    return consensus


def build_ou25_consensus(
    market_odds: pd.DataFrame, match_id: str, odds_index: dict | None = None
) -> dict | None:
    """Build de-vigged weighted consensus O/U 2.5 probabilities."""
    if odds_index is not None:
        odds = _get_odds(odds_index, match_id, "over_under")
        if odds is None:
            return None
        odds_25 = odds[odds["line"] == 2.5]
    else:
        odds = market_odds[
            (market_odds["match_id"] == match_id)
            & (market_odds["market_type"] == "over_under")
        ]
        odds_25 = odds[odds["line"] == 2.5]

    if odds_25.empty:
        return None

    sources = {}
    for source, grp in odds_25.groupby("source"):
        probs = {}
        for _, r in grp.iterrows():
            probs[r["outcome"]] = r["probability"]
        if "over" in probs and "under" in probs:
            total = probs["over"] + probs["under"]
            if total > 0:
                sources[source] = {
                    "over": probs["over"] / total,
                    "under": probs["under"] / total,
                }

    if not sources:
        return None

    total_weight = sum(SOURCE_WEIGHTS.get(s, 0.5) for s in sources)
    consensus = {"over": 0.0, "under": 0.0}
    for source, probs in sources.items():
        w = SOURCE_WEIGHTS.get(source, 0.5)
        for k in consensus:
            consensus[k] += w * probs[k]
    for k in consensus:
        consensus[k] /= total_weight

    consensus["sources"] = list(sources.keys())
    consensus["n_sources"] = len(sources)
    return consensus


def build_btts_consensus(
    market_odds: pd.DataFrame, match_id: str, odds_index: dict | None = None
) -> dict | None:
    """Build de-vigged weighted consensus BTTS probabilities."""
    if odds_index is not None:
        odds = _get_odds(odds_index, match_id, "btts")
        if odds is None:
            return None
    else:
        odds = market_odds[
            (market_odds["match_id"] == match_id)
            & (market_odds["market_type"] == "btts")
        ]

    if odds.empty:
        return None

    sources = {}
    for source, grp in odds.groupby("source"):
        probs = {}
        for _, r in grp.iterrows():
            probs[r["outcome"]] = r["probability"]
        if "yes" in probs and "no" in probs:
            total = probs["yes"] + probs["no"]
            if total > 0:
                sources[source] = {
                    "yes": probs["yes"] / total,
                    "no": probs["no"] / total,
                }

    if not sources:
        return None

    total_weight = sum(SOURCE_WEIGHTS.get(s, 0.5) for s in sources)
    consensus = {"yes": 0.0, "no": 0.0}
    for source, probs in sources.items():
        w = SOURCE_WEIGHTS.get(source, 0.5)
        for k in consensus:
            consensus[k] += w * probs[k]
    for k in consensus:
        consensus[k] /= total_weight

    consensus["sources"] = list(sources.keys())
    consensus["n_sources"] = len(sources)
    return consensus


def build_ah_consensus(
    market_odds: pd.DataFrame, match_id: str, odds_index: dict | None = None
) -> dict | None:
    """Build Asian Handicap consensus from Kalshi spread data.

    Finds the line closest to 50/50 split.
    """
    if odds_index is not None:
        odds = _get_odds(odds_index, match_id, "spread")
        if odds is None:
            return None
        odds = odds[odds["source"] == "kalshi"]
    else:
        odds = market_odds[
            (market_odds["match_id"] == match_id)
            & (market_odds["market_type"] == "spread")
            & (market_odds["source"] == "kalshi")
        ]

    if odds.empty:
        return None

    best_line = None
    best_split_diff = 999.0
    best_probs = None

    for line, grp in odds.groupby("line"):
        probs = {}
        for _, r in grp.iterrows():
            probs[r["outcome"]] = r["probability"]
        if "home" in probs and "away" in probs:
            total = probs["home"] + probs["away"]
            if total > 0:
                p_home = probs["home"] / total
                p_away = probs["away"] / total
                split_diff = abs(p_home - 0.5)
                if split_diff < best_split_diff:
                    best_split_diff = split_diff
                    best_line = line
                    best_probs = {"home": p_home, "away": p_away, "line": line}

    if best_probs is None:
        return None

    best_probs["sources"] = ["kalshi"]
    best_probs["n_sources"] = 1
    return best_probs


def build_all_consensus(market_odds: pd.DataFrame, match_ids: list[str]) -> dict:
    """Build consensus for all markets for all given matches."""
    results = {}
    for mid in match_ids:
        results[mid] = {
            "1x2": build_1x2_consensus(market_odds, mid),
            "ou25": build_ou25_consensus(market_odds, mid),
            "btts": build_btts_consensus(market_odds, mid),
            "ah": build_ah_consensus(market_odds, mid),
        }
    return results


# ─── Market Calibration Analysis ──────────────────────────────────────────────


def brier_score_1x2(probs: np.ndarray, actual: np.ndarray) -> float:
    """Brier score for 1X2. probs: (N,3), actual: (N,3) one-hot."""
    return float(np.mean(np.sum((probs - actual) ** 2, axis=1)))


def _actual_1x2_vector(result: str) -> np.ndarray:
    if result == "H":
        return np.array([1.0, 0.0, 0.0])
    elif result == "D":
        return np.array([0.0, 1.0, 0.0])
    elif result == "A":
        return np.array([0.0, 0.0, 1.0])
    return np.array([0.0, 0.0, 0.0])


def calibration_analysis(
    feature_df: pd.DataFrame,
    market_odds: pd.DataFrame,
    odds_index: dict | None = None,
) -> dict:
    """Analyze systematic biases in market odds on completed matches.

    Returns correction factors and per-source accuracy.
    """
    completed = feature_df[feature_df["is_training_row"] == True].copy()
    completed = completed.sort_values("match_date").reset_index(drop=True)

    if odds_index is None:
        odds_index = _precompute_odds_index(market_odds)

    per_source_brier = {}
    source_predictions = {}

    for source in [
        "xlsx_bet365",
        "xlsx_betfair",
        "xlsx_avg",
        "xlsx_max",
        "kalshi",
        "polymarket",
    ]:
        probs_list = []
        actuals_list = []
        for _, row in completed.iterrows():
            mid = row["match_id"]
            odds = market_odds[
                (market_odds["match_id"] == mid)
                & (market_odds["source"] == source)
                & (market_odds["market_type"] == "1x2")
            ]
            if odds.empty:
                continue
            probs = {}
            for _, r in odds.iterrows():
                probs[r["outcome"]] = r["probability"]
            if not {"home", "draw", "away"}.issubset(probs.keys()):
                continue
            total = probs["home"] + probs["draw"] + probs["away"]
            if total <= 0:
                continue
            p = np.array(
                [probs["home"] / total, probs["draw"] / total, probs["away"] / total]
            )
            if source == "kalshi" and (
                p[0] >= KALSHI_CORRUPT_HIGH or p[2] >= KALSHI_CORRUPT_HIGH
            ):
                continue
            probs_list.append(p)
            actuals_list.append(_actual_1x2_vector(row["result_1x2"]))
            source_predictions.setdefault(mid, {})[source] = p

        if len(probs_list) >= 5:
            probs_arr = np.array(probs_list)
            actuals_arr = np.array(actuals_list)
            per_source_brier[source] = {
                "brier": brier_score_1x2(probs_arr, actuals_arr),
                "n_matches": len(probs_list),
            }

    # Build consensus for completed matches
    consensus_list = []
    actuals_list = []
    for _, row in completed.iterrows():
        mid = row["match_id"]
        cons = build_1x2_consensus(market_odds, mid, odds_index)
        if cons is None:
            continue
        consensus_list.append([cons["home"], cons["draw"], cons["away"]])
        actuals_list.append(_actual_1x2_vector(row["result_1x2"]))

    consensus_arr = np.array(consensus_list)
    actuals_arr = np.array(actuals_list)
    consensus_brier = brier_score_1x2(consensus_arr, actuals_arr)

    # Bias detection
    n = len(consensus_list)
    actual_home_rate = float(np.mean(actuals_arr[:, 0]))
    actual_draw_rate = float(np.mean(actuals_arr[:, 1]))
    actual_away_rate = float(np.mean(actuals_arr[:, 2]))
    pred_home_rate = float(np.mean(consensus_arr[:, 0]))
    pred_draw_rate = float(np.mean(consensus_arr[:, 1]))
    pred_away_rate = float(np.mean(consensus_arr[:, 2]))

    home_bias = actual_home_rate - pred_home_rate
    draw_bias = actual_draw_rate - pred_draw_rate
    away_bias = actual_away_rate - pred_away_rate

    # Favorite bias: for matches where one side > 0.5, did they win more/less?
    fav_mask = (consensus_arr[:, 0] > 0.5) | (consensus_arr[:, 2] > 0.5)
    if fav_mask.any():
        fav_probs = np.where(
            consensus_arr[fav_mask, 0] > 0.5,
            consensus_arr[fav_mask, 0],
            consensus_arr[fav_mask, 2],
        )
        fav_actual = np.where(
            consensus_arr[fav_mask, 0] > 0.5,
            actuals_arr[fav_mask, 0],
            actuals_arr[fav_mask, 2],
        )
        favorite_bias = float(np.mean(fav_actual - fav_probs))
    else:
        favorite_bias = 0.0

    # Cross-source divergence: where Bet365 disagrees with sharp books by >5%
    divergence_results = {"sharp_right": 0, "soft_right": 0, "neither": 0, "total": 0}
    for mid, sources in source_predictions.items():
        if "xlsx_bet365" not in sources:
            continue
        sharp_probs = []
        for s in ["kalshi", "polymarket"]:
            if s in sources:
                sharp_probs.append(sources[s])
        if not sharp_probs:
            continue
        sharp_avg = np.mean(sharp_probs, axis=0)
        soft = sources["xlsx_bet365"]
        diff = np.abs(sharp_avg - soft)
        if diff.max() < 0.05:
            continue
        row = completed[completed["match_id"] == mid]
        if row.empty:
            continue
        result = row.iloc[0]["result_1x2"]
        actual = _actual_1x2_vector(result)
        sharp_pred = np.argmax(sharp_avg)
        soft_pred = np.argmax(soft)
        actual_idx = np.argmax(actual)
        divergence_results["total"] += 1
        if sharp_pred == actual_idx and soft_pred != actual_idx:
            divergence_results["sharp_right"] += 1
        elif soft_pred == actual_idx and sharp_pred != actual_idx:
            divergence_results["soft_right"] += 1
        else:
            divergence_results["neither"] += 1

    # Correction factors (capped at ±10%)
    corrections = {
        "home": np.clip(home_bias, -0.10, 0.10),
        "draw": np.clip(draw_bias, -0.10, 0.10),
        "away": np.clip(away_bias, -0.10, 0.10),
        "favorite": np.clip(favorite_bias, -0.10, 0.10),
    }

    return {
        "per_source_brier": per_source_brier,
        "consensus_brier": consensus_brier,
        "n_completed": n,
        "actual_rates": {
            "home": actual_home_rate,
            "draw": actual_draw_rate,
            "away": actual_away_rate,
        },
        "predicted_rates": {
            "home": pred_home_rate,
            "draw": pred_draw_rate,
            "away": pred_away_rate,
        },
        "biases": {
            "home": home_bias,
            "draw": draw_bias,
            "away": away_bias,
            "favorite": favorite_bias,
        },
        "corrections": corrections,
        "divergence": divergence_results,
    }


def apply_calibration_corrections(probs: dict, corrections: dict) -> dict:
    """Apply calibration corrections to 1X2 probabilities and renormalize."""
    adjusted = {
        "home": probs["home"] + corrections.get("home", 0),
        "draw": probs["draw"] + corrections.get("draw", 0),
        "away": probs["away"] + corrections.get("away", 0),
    }
    adjusted = {k: max(0.01, v) for k, v in adjusted.items()}
    total = sum(adjusted.values())
    return {k: v / total for k, v in adjusted.items()}


# ─── Feature Correction Model ─────────────────────────────────────────────────

FEATURE_COLS = [
    "elo_diff",
    "form_score_diff",
    "rest_days_diff",
    "h2h_home_win_rate",
    "fotmob_xg_for_diff_l3",
    "fotmob_xg_against_diff_l3",
    "fotmob_possession_diff_l3",
    "fotmob_shots_ot_diff_l3",
    "fotmob_big_chances_diff_l3",
    "fotmob_passes_diff_l3",
    "fotmob_xg_for_diff_l5",
    "fotmob_xg_against_diff_l5",
    "fotmob_possession_diff_l5",
    "fotmob_shots_ot_diff_l5",
    "fotmob_big_chances_diff_l5",
]


def _build_feature_matrix(
    feature_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series | None]:
    """Build feature differentials for completed matches (15 features)."""
    df = feature_df[feature_df["is_training_row"] == True].copy()
    df = df.sort_values("match_date").reset_index(drop=True)

    X = pd.DataFrame(index=df.index)
    X["elo_diff"] = (df["home_elo"] - df["away_elo"]) / 100.0
    X["form_score_diff"] = df["home_form_score"] - df["away_form_score"]
    X["rest_days_diff"] = (
        df["days_since_last_match_home"] - df["days_since_last_match_away"]
    ) / 7.0
    h2h_total = df["h2h_matches_played"].clip(lower=1)
    X["h2h_home_win_rate"] = df["h2h_home_wins"] / h2h_total

    fotmob_diffs = {
        "fotmob_xg_for_diff_l3": ("home_xg_for_l3", "away_xg_for_l3"),
        "fotmob_xg_against_diff_l3": ("home_xg_against_l3", "away_xg_against_l3"),
        "fotmob_possession_diff_l3": ("home_possession_l3", "away_possession_l3"),
        "fotmob_shots_ot_diff_l3": ("home_shots_ot_l3", "away_shots_ot_l3"),
        "fotmob_big_chances_diff_l3": ("home_big_chances_l3", "away_big_chances_l3"),
        "fotmob_passes_diff_l3": ("home_passes_l3", "away_passes_l3"),
        "fotmob_xg_for_diff_l5": ("home_xg_for_l5", "away_xg_for_l5"),
        "fotmob_xg_against_diff_l5": ("home_xg_against_l5", "away_xg_against_l5"),
        "fotmob_possession_diff_l5": ("home_possession_l5", "away_possession_l5"),
        "fotmob_shots_ot_diff_l5": ("home_shots_ot_l5", "away_shots_ot_l5"),
        "fotmob_big_chances_diff_l5": ("home_big_chances_l5", "away_big_chances_l5"),
    }
    for col, (home_col, away_col) in fotmob_diffs.items():
        X[col] = df[home_col].fillna(0.0) - df[away_col].fillna(0.0)

    X = X.fillna(0.0)
    X = X.apply(pd.to_numeric, errors="coerce").fillna(0.0)

    y = df["result_1x2"].map({"H": 0, "D": 1, "A": 2})
    y = pd.to_numeric(y, errors="coerce").fillna(0).astype(int)
    return X, y


def feature_correction_loo_cv(
    feature_df: pd.DataFrame,
    market_odds: pd.DataFrame,
    corrections: dict,
    odds_index: dict | None = None,
) -> dict:
    """LOO CV for feature correction model.

    Tries multiple C values and picks the best via LOO Brier.
    Returns per-feature correction magnitudes, LOO Brier scores,
    and whether the feature model adds signal.
    """
    df = feature_df[feature_df["is_training_row"] == True].copy()
    df = df.sort_values("match_date").reset_index(drop=True)

    X, y = _build_feature_matrix(df)
    if y is None or len(y) < 10:
        return {
            "use_feature_model": False,
            "loo_brier_with": float("inf"),
            "loo_brier_without": float("inf"),
            "correction_magnitudes": {},
            "mean_abs_correction": 0.0,
            "negligible_signal": True,
            "lr_model": None,
            "best_C": None,
        }

    # Build consensus probs for each completed match
    consensus_probs = []
    valid_idx = []
    for i, row in df.iterrows():
        cons = build_1x2_consensus(market_odds, row["match_id"], odds_index)
        if cons is None:
            continue
        calibrated = apply_calibration_corrections(cons, corrections)
        consensus_probs.append(
            [calibrated["home"], calibrated["draw"], calibrated["away"]]
        )
        valid_idx.append(i)

    consensus_probs = np.array(consensus_probs)
    X_valid = X.loc[valid_idx].reset_index(drop=True)
    y_valid = y.loc[valid_idx].reset_index(drop=True)

    n = len(valid_idx)
    if n < 10:
        return {
            "use_feature_model": False,
            "loo_brier_with": float("inf"),
            "loo_brier_without": float("inf"),
            "correction_magnitudes": {},
            "mean_abs_correction": 0.0,
            "negligible_signal": True,
            "lr_model": None,
            "best_C": None,
        }

    # One-hot encode actual
    y_onehot = np.zeros((n, 3))
    for i in range(n):
        y_onehot[i, y_valid.iloc[i]] = 1.0

    # Baseline Brier (consensus only)
    loo_brier_without = brier_score_1x2(consensus_probs, y_onehot)

    # Try multiple C values — pick the one with best LOO Brier
    C_VALUES = [0.01, 0.1, 1.0, 10.0]
    best_brier = loo_brier_without
    best_C = None
    best_preds = consensus_probs.copy()
    best_corrections = []
    best_lr = None

    for C_val in C_VALUES:
        loo_preds = consensus_probs.copy()
        correction_values = []
        lr_final = None

        for leave_out in range(n):
            train_mask = np.ones(n, dtype=bool)
            train_mask[leave_out] = False

            X_train = X_valid.loc[train_mask].values
            y_train = y_valid.loc[train_mask].values

            try:
                lr = LogisticRegression(
                    C=C_val,
                    penalty="l2",
                    multi_class="multinomial",
                    solver="lbfgs",
                    max_iter=1000,
                )
                lr.fit(X_train, y_train)
            except Exception:
                correction_values.append(np.zeros(3))
                continue

            lr_final = lr

            x_test = X_valid.loc[leave_out].values.reshape(1, -1)
            feat_pred = lr.predict_proba(x_test)[0]

            consensus_test = consensus_probs[leave_out]
            correction = feat_pred - consensus_test
            correction = np.clip(correction, -CORRECTION_CAP, CORRECTION_CAP)
            correction_values.append(correction)

            adjusted = consensus_test + correction
            adjusted = np.clip(adjusted, 0.01, 0.99)
            adjusted /= adjusted.sum()
            loo_preds[leave_out] = adjusted

        loo_brier = brier_score_1x2(loo_preds, y_onehot)

        if loo_brier < best_brier:
            best_brier = loo_brier
            best_C = C_val
            best_preds = loo_preds.copy()
            best_corrections = correction_values[:]
            best_lr = lr_final

    loo_brier_with = best_brier

    # Per-feature correction magnitudes (from best model, or last model if none beat baseline)
    correction_arr = (
        np.array(best_corrections) if best_corrections else np.zeros((1, 3))
    )
    mean_abs_correction = float(np.mean(np.abs(correction_arr)))

    # Also fit a final model on ALL data with best C for coefficient reporting
    correction_magnitudes = {}
    lr_for_coefs = None
    report_C = best_C if best_C is not None else C_VALUES[-1]
    try:
        lr_for_coefs = LogisticRegression(
            C=report_C,
            penalty="l2",
            multi_class="multinomial",
            solver="lbfgs",
            max_iter=1000,
        )
        lr_for_coefs.fit(X_valid.values, y_valid.values)
    except Exception:
        pass

    if lr_for_coefs is not None and hasattr(lr_for_coefs, "coef_"):
        for j, feat in enumerate(FEATURE_COLS):
            correction_magnitudes[feat] = {
                "coef_home": float(lr_for_coefs.coef_[0][j]),
                "coef_draw": float(lr_for_coefs.coef_[1][j]),
                "coef_away": float(lr_for_coefs.coef_[2][j]),
                "abs_mean": float(np.mean(np.abs(lr_for_coefs.coef_[:, j]))),
            }

    use_feature_model = best_C is not None and loo_brier_with < loo_brier_without
    negligible_signal = mean_abs_correction < 0.01

    # Use the full-data model for predictions if we're using the feature model
    lr_model = lr_for_coefs if use_feature_model else None

    return {
        "use_feature_model": use_feature_model,
        "loo_brier_with": loo_brier_with,
        "loo_brier_without": loo_brier_without,
        "correction_magnitudes": correction_magnitudes,
        "mean_abs_correction": mean_abs_correction,
        "negligible_signal": negligible_signal,
        "lr_model": lr_model,
        "best_C": best_C,
    }


def apply_feature_corrections(
    consensus_probs: np.ndarray,
    X_match: np.ndarray,
    lr_model: LogisticRegression,
) -> np.ndarray:
    """Apply feature-based corrections to consensus probabilities."""
    feat_pred = lr_model.predict_proba(X_match.reshape(1, -1))[0]
    correction = np.clip(feat_pred - consensus_probs, -CORRECTION_CAP, CORRECTION_CAP)
    adjusted = consensus_probs + correction
    adjusted = np.clip(adjusted, 0.01, 0.99)
    adjusted /= adjusted.sum()
    return adjusted


# ─── Dixon-Coles Poisson Model ────────────────────────────────────────────────


def _prepare_dc_data(
    intl_df: pd.DataFrame,
    tour_df: pd.DataFrame,
    feature_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge international and tournament matches into a unified DC dataset.

    When feature_df is provided with fotmob_xg_home/away columns, those
    matches use xG as the target instead of raw goals, with a confidence
    weight multiplier (1.5x) since xG is more predictive.
    """
    intl = pd.DataFrame(
        {
            "date": intl_df["date_utc"],
            "home": intl_df["home_team"],
            "away": intl_df["away_team"],
            "hg": intl_df["home_goals"],
            "ag": intl_df["away_goals"],
            "is_neutral": intl_df["is_neutral"].fillna(False),
        }
    )

    tour = pd.DataFrame(
        {
            "date": tour_df["date"],
            "home": tour_df["home"],
            "away": tour_df["away"],
            "hg": tour_df["hgft"],
            "ag": tour_df["agft"],
            "is_neutral": True,
        }
    )

    df = pd.concat([intl, tour], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.dropna(subset=["hg", "ag", "home", "away"]).copy()
    df["hg"] = df["hg"].astype(int)
    df["ag"] = df["ag"].astype(int)
    df = df[(df["hg"] >= 0) & (df["ag"] >= 0) & (df["hg"] <= 10) & (df["ag"] <= 10)]
    df["dc_weight"] = 1.0
    df["hg"] = df["hg"].astype(float)
    df["ag"] = df["ag"].astype(float)

    if feature_df is not None and "fotmob_xg_home" in feature_df.columns:
        xg_map = feature_df[
            ["match_date", "home_team", "away_team", "fotmob_xg_home", "fotmob_xg_away"]
        ].dropna()
        for _, xrow in xg_map.iterrows():
            match_mask = (
                (df["date"].dt.date == pd.to_datetime(xrow["match_date"]).date())
                & (df["home"] == xrow["home_team"])
                & (df["away"] == xrow["away_team"])
            )
            if match_mask.any():
                df.loc[match_mask, "hg"] = float(xrow["fotmob_xg_home"])
                df.loc[match_mask, "ag"] = float(xrow["fotmob_xg_away"])
                df.loc[match_mask, "dc_weight"] = 1.5

    df = df.sort_values("date").reset_index(drop=True)
    return df


def _dc_time_weights(
    dates: pd.Series, half_life_days: int = DC_HALF_LIFE_DAYS
) -> np.ndarray:
    """Exponential time-decay weights."""
    latest = dates.max()
    days_ago = (latest - dates).dt.total_seconds() / 86400.0
    return np.exp(-np.log(2) * days_ago / half_life_days)


_LOG_FACTORIAL_CACHE = np.array(
    [
        0.0,
        0.0,
        np.log(2),
        np.log(6),
        np.log(24),
        np.log(120),
        np.log(720),
        np.log(5040),
        np.log(40320),
        np.log(362880),
        np.log(3628800),
        np.log(39916800),
    ]
)


def _log_factorial_arr(arr: np.ndarray) -> np.ndarray:
    """Vectorized log factorial for integer arrays."""
    global _LOG_FACTORIAL_CACHE
    max_n = int(arr.max()) + 1
    if max_n > len(_LOG_FACTORIAL_CACHE):
        for i in range(len(_LOG_FACTORIAL_CACHE), max_n):
            _LOG_FACTORIAL_CACHE = np.append(
                _LOG_FACTORIAL_CACHE, np.sum(np.log(np.arange(1, i + 1)))
            )
    return _LOG_FACTORIAL_CACHE[arr]


def fit_dixon_coles(dc_df: pd.DataFrame) -> dict:
    """Fit Dixon-Coles model via maximum likelihood (vectorized).

    Supports xG-enhanced training: when dc_df has a 'dc_weight' column,
    those weights are multiplied into the likelihood. xG values (floats)
    use gamma-based log factorial for non-integer support.

    Returns dict with attack/defense params, home advantage, and team index.
    """
    teams = sorted(set(dc_df["home"].unique()) | set(dc_df["away"].unique()))
    team_idx = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)

    time_weights = _dc_time_weights(dc_df["date"])
    dc_weight = (
        dc_df["dc_weight"].values
        if "dc_weight" in dc_df.columns
        else np.ones(len(dc_df))
    )
    weights = time_weights * dc_weight

    home_idx = dc_df["home"].map(team_idx).values.astype(int)
    away_idx = dc_df["away"].map(team_idx).values.astype(int)
    hg = dc_df["hg"].values.astype(float)
    ag = dc_df["ag"].values.astype(float)
    neutral = dc_df["is_neutral"].values.astype(float)
    n_matches = len(hg)

    # Precompute masks for Dixon-Coles low-score correction
    mask_00 = (hg == 0) & (ag == 0)
    mask_10 = (hg == 1) & (ag == 0)
    mask_01 = (hg == 0) & (ag == 1)
    mask_11 = (hg == 1) & (ag == 1)

    def neg_log_likelihood(params):
        attack = params[:n_teams]
        defense = params[n_teams : 2 * n_teams]
        home_adv = params[2 * n_teams]
        rho = params[2 * n_teams + 1]

        # Vectorized lambda computation
        ha = home_adv * (1.0 - neutral)
        lambda_h = np.exp(attack[home_idx] + defense[away_idx] + ha)
        lambda_a = np.exp(attack[away_idx] + defense[home_idx])

        # Vectorized Poisson PMF using log for stability
        # Use gammaln for float xG values, factorial cache for integer goals
        if np.issubdtype(hg.dtype, np.floating):
            log_fact_hg = gammaln(hg + 1)
            log_fact_ag = gammaln(ag + 1)
        else:
            log_fact_hg = _log_factorial_arr(hg.astype(int))
            log_fact_ag = _log_factorial_arr(ag.astype(int))
        log_p_hg = hg * np.log(lambda_h) - lambda_h - log_fact_hg
        log_p_ag = ag * np.log(lambda_a) - lambda_a - log_fact_ag

        # Dixon-Coles correction (vectorized)
        correction = np.ones(n_matches)
        correction[mask_00] = 1.0 - lambda_h[mask_00] * lambda_a[mask_00] * rho
        correction[mask_10] = 1.0 + lambda_a[mask_10] * rho
        correction[mask_01] = 1.0 + lambda_h[mask_01] * rho
        correction[mask_11] = 1.0 - rho
        correction = np.clip(correction, 1e-10, None)

        log_prob = log_p_hg + log_p_ag + np.log(correction)
        log_lik = np.sum(weights * log_prob)

        return -log_lik

    # Smart initialization: use log of per-team average goals
    home_goals_avg = np.zeros(n_teams)
    away_goals_avg = np.zeros(n_teams)
    home_games = np.zeros(n_teams)
    away_games = np.zeros(n_teams)
    for i in range(n_matches):
        home_goals_avg[home_idx[i]] += hg[i]
        away_goals_avg[away_idx[i]] += ag[i]
        home_games[home_idx[i]] += 1
        away_games[away_idx[i]] += 1
    overall_avg_h = np.mean(hg)
    overall_avg_a = np.mean(ag)
    init_attack = np.zeros(n_teams)
    init_defense = np.zeros(n_teams)
    for t in range(n_teams):
        h_g = home_goals_avg[t] / max(home_games[t], 1)
        a_g = away_goals_avg[t] / max(away_games[t], 1)
        init_attack[t] = np.log(max(h_g, 0.1)) - np.log(overall_avg_h)
        init_defense[t] = np.log(overall_avg_a) - np.log(max(a_g, 0.1))

    x0 = np.concatenate(
        [
            init_attack,
            init_defense,
            [0.3],
            [-0.1],
        ]
    )

    # Use L-BFGS-B with penalty for sum(attack)=0 constraint
    def neg_log_likelihood_penalized(params):
        penalty = 1000.0 * np.sum(params[:n_teams]) ** 2
        return neg_log_likelihood(params) + penalty

    result = minimize(
        neg_log_likelihood_penalized,
        x0,
        method="L-BFGS-B",
        options={"maxiter": 2000, "ftol": 1e-8, "gtol": 1e-6},
    )

    attack = result.x[:n_teams]
    defense = result.x[n_teams : 2 * n_teams]
    home_adv = result.x[2 * n_teams]
    rho = result.x[2 * n_teams + 1]

    return {
        "team_idx": team_idx,
        "attack": attack,
        "defense": defense,
        "home_adv": home_adv,
        "rho": rho,
        "n_teams": n_teams,
        "converged": result.success,
    }


def dc_expected_goals(
    dc_model: dict, home_team: str, away_team: str
) -> tuple[float, float]:
    """Compute expected goals for a match."""
    idx = dc_model["team_idx"]
    if home_team not in idx or away_team not in idx:
        return 1.35, 1.15  # tournament averages fallback

    h = idx[home_team]
    a = idx[away_team]
    lambda_h = np.exp(
        dc_model["attack"][h] + dc_model["defense"][a] + dc_model["home_adv"]
    )
    lambda_a = np.exp(dc_model["attack"][a] + dc_model["defense"][h])
    return float(lambda_h), float(lambda_a)


def dc_scoreline_matrix(
    lambda_h: float, lambda_a: float, rho: float = 0.0, max_goals: int = DC_MAX_GOALS
) -> np.ndarray:
    """Generate scoreline probability matrix with Dixon-Coles correction."""
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson.pmf(i, lambda_h) * poisson.pmf(j, lambda_a)
            if i == 0 and j == 0:
                p *= 1 - lambda_h * lambda_a * rho
            elif i == 1 and j == 0:
                p *= 1 + lambda_a * rho
            elif i == 0 and j == 1:
                p *= 1 + lambda_h * rho
            elif i == 1 and j == 1:
                p *= 1 - rho
            matrix[i, j] = max(p, 0)
    matrix /= matrix.sum()
    return matrix


def dc_top_scorelines(matrix: np.ndarray, n: int = 5) -> list[dict]:
    """Extract top N most likely scorelines."""
    scores = []
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            scores.append(
                {
                    "scoreline": f"{i}-{j}",
                    "home_goals": i,
                    "away_goals": j,
                    "probability": float(matrix[i, j]),
                }
            )
    scores.sort(key=lambda x: x["probability"], reverse=True)
    return scores[:n]


def dc_market_probs(matrix: np.ndarray) -> dict:
    """Derive 1X2, O/U 2.5, BTTS from scoreline matrix."""
    home_win = float(np.tril(matrix, -1).sum())
    draw = float(np.trace(matrix))
    away_win = float(np.triu(matrix, 1).sum())

    total_goals = np.zeros_like(matrix)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            total_goals[i, j] = i + j
    over = float(matrix[total_goals > 2.5].sum())
    under = float(matrix[total_goals <= 2.5].sum())

    btts_mask = np.zeros_like(matrix, dtype=bool)
    for i in range(1, matrix.shape[0]):
        for j in range(1, matrix.shape[1]):
            btts_mask[i, j] = True
    btts_yes = float(matrix[btts_mask].sum())
    btts_no = 1.0 - btts_yes

    return {
        "1x2": {"home": home_win, "draw": draw, "away": away_win},
        "ou25": {"over": over, "under": under},
        "btts": {"yes": btts_yes, "no": btts_no},
    }


# ─── Blending & Calibration ───────────────────────────────────────────────────


def compute_qualification_probs(
    dc_model: dict,
    home_team: str,
    away_team: str,
    probs_90min: dict,
) -> dict:
    """Derive To Qualify probabilities from 90-minute model output.

    Uses the DC model to simulate extra time (30 min, reduced home advantage).
    Penalties are modelled as 50/50 with a slight home-favouring adjustment
    based on the DC home advantage parameter.
    """
    p_home_90 = probs_90min["home"]
    p_draw_90 = probs_90min["draw"]
    p_away_90 = probs_90min["away"]

    if p_draw_90 <= 0:
        return {
            "home_qualify_prob": p_home_90,
            "away_qualify_prob": p_away_90,
            "extra_time_prob": 0.0,
            "penalties_prob": 0.0,
        }

    idx = dc_model["team_idx"]
    if home_team not in idx or away_team not in idx:
        et_home_adv = 0.05
        p_home_et = 0.40
        p_draw_et = 0.20
        p_away_et = 0.40
    else:
        h = idx[home_team]
        a = idx[away_team]
        et_home_adv = dc_model["home_adv"] * 0.4
        lambda_h_et = np.exp(
            dc_model["attack"][h] + dc_model["defense"][a] + et_home_adv
        ) * (30.0 / 90.0)
        lambda_a_et = np.exp(dc_model["attack"][a] + dc_model["defense"][h]) * (
            30.0 / 90.0
        )
        et_matrix = dc_scoreline_matrix(
            lambda_h_et, lambda_a_et, dc_model["rho"], max_goals=6
        )
        p_home_et = float(np.tril(et_matrix, -1).sum())
        p_draw_et = float(np.trace(et_matrix))
        p_away_et = float(np.triu(et_matrix, 1).sum())

    penalty_home_adv = min(dc_model.get("home_adv", 0.12) * 0.3, 0.05)
    p_home_pen = 0.5 + penalty_home_adv
    p_away_pen = 0.5 - penalty_home_adv

    p_extra_time = p_draw_90
    p_penalties = p_draw_90 * p_draw_et

    home_qualify = p_home_90 + p_draw_90 * (p_home_et + p_draw_et * p_home_pen)
    away_qualify = p_away_90 + p_draw_90 * (p_away_et + p_draw_et * p_away_pen)
    total = home_qualify + away_qualify
    home_qualify /= total
    away_qualify /= total

    return {
        "home_qualify_prob": round(home_qualify, 4),
        "away_qualify_prob": round(away_qualify, 4),
        "extra_time_prob": round(p_extra_time, 4),
        "penalties_prob": round(p_penalties, 4),
    }


def blend_market_dc(
    market_probs: np.ndarray,
    dc_probs: np.ndarray,
    market_weight: float = BLEND_MARKET_WEIGHT,
    dc_weight: float = BLEND_DC_WEIGHT,
) -> np.ndarray:
    """Blend market consensus with Dixon-Coles probabilities."""
    blended = market_weight * market_probs + dc_weight * dc_probs
    blended = np.clip(blended, 0.01, 0.99)
    blended /= blended.sum()
    return blended


def isotonic_calibrate(probs: np.ndarray, actuals: np.ndarray) -> IsotonicRegression:
    """Fit isotonic regression for probability calibration."""
    n = len(probs)
    x = probs.flatten()
    y = np.repeat(actuals, 3) if actuals.ndim == 1 else actuals.flatten()
    # For 1X2: calibrate each outcome independently
    iso_models = []
    for k in range(3):
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(probs[:, k], actuals[:, k])
        iso_models.append(iso)
    return iso_models


def apply_isotonic(
    probs: np.ndarray, iso_models: list[IsotonicRegression]
) -> np.ndarray:
    """Apply isotonic calibration models to probabilities."""
    calibrated = np.zeros_like(probs)
    for k in range(min(len(iso_models), probs.shape[1])):
        calibrated[:, k] = iso_models[k].transform(probs[:, k])
    # Renormalize
    calibrated = np.clip(calibrated, 0.01, 0.99)
    row_sums = calibrated.sum(axis=1, keepdims=True)
    calibrated /= row_sums
    return calibrated


# ─── Bootstrap Confidence Intervals ──────────────────────────────────────────


def _fast_bias_correction(
    precomputed_consensus: np.ndarray,
    precomputed_actuals: np.ndarray,
    bootstrap_idx: np.ndarray,
) -> dict:
    """Fast vectorized bias computation for bootstrap."""
    sampled_consensus = precomputed_consensus[bootstrap_idx]
    sampled_actuals = precomputed_actuals[bootstrap_idx]

    actual_home = float(np.mean(sampled_actuals[:, 0]))
    actual_draw = float(np.mean(sampled_actuals[:, 1]))
    actual_away = float(np.mean(sampled_actuals[:, 2]))
    pred_home = float(np.mean(sampled_consensus[:, 0]))
    pred_draw = float(np.mean(sampled_consensus[:, 1]))
    pred_away = float(np.mean(sampled_consensus[:, 2]))

    return {
        "home": float(np.clip(actual_home - pred_home, -0.10, 0.10)),
        "draw": float(np.clip(actual_draw - pred_draw, -0.10, 0.10)),
        "away": float(np.clip(actual_away - pred_away, -0.10, 0.10)),
    }


def bootstrap_predictions(
    feature_df: pd.DataFrame,
    market_odds: pd.DataFrame,
    corrections: dict,
    feature_result: dict,
    dc_model: dict,
    upcoming_df: pd.DataFrame,
    n_boot: int = BOOTSTRAP_N,
    odds_index: dict | None = None,
) -> dict:
    """Bootstrap resampling to get 95% CIs for upcoming match predictions.

    Fully optimized: precomputes everything, vectorized inner loop.
    """
    completed = feature_df[feature_df["is_training_row"] == True].copy()
    completed = completed.sort_values("match_date").reset_index(drop=True)
    n = len(completed)

    # Pre-compute odds index once
    if odds_index is None:
        odds_index = _precompute_odds_index(market_odds)

    # Pre-compute consensus + actuals for completed matches as arrays
    precomputed_consensus = np.zeros((n, 3))
    precomputed_actuals = np.zeros((n, 3))
    for i, row in completed.iterrows():
        cons = build_1x2_consensus(market_odds, row["match_id"], odds_index)
        if cons is not None:
            precomputed_consensus[i] = [cons["home"], cons["draw"], cons["away"]]
        else:
            precomputed_consensus[i] = [0.4, 0.3, 0.3]
        precomputed_actuals[i] = _actual_1x2_vector(row["result_1x2"])

    # Pre-compute feature matrix for completed matches
    X_completed, y_completed = _build_feature_matrix(completed)
    X_completed_np = X_completed.values
    y_completed_np = y_completed.values if y_completed is not None else np.zeros(n)

    # Pre-compute all upcoming data as arrays (not dicts)
    n_up = len(upcoming_df)
    up_mids = []
    up_cons_1x2 = []
    up_cons_ou25 = []
    up_cons_btts = []
    up_dc_1x2 = []
    up_dc_ou = []
    up_dc_btts = []
    up_X = []

    for _, row in upcoming_df.iterrows():
        mid = row["match_id"]
        up_mids.append(mid)
        up_cons_1x2.append(build_1x2_consensus(market_odds, mid, odds_index))
        up_cons_ou25.append(build_ou25_consensus(market_odds, mid, odds_index))
        up_cons_btts.append(build_btts_consensus(market_odds, mid, odds_index))
        lh, la = dc_expected_goals(dc_model, row["home_team"], row["away_team"])
        matrix = dc_scoreline_matrix(lh, la, dc_model["rho"])
        dc_probs = dc_market_probs(matrix)
        up_dc_1x2.append(
            np.array(
                [
                    dc_probs["1x2"]["home"],
                    dc_probs["1x2"]["draw"],
                    dc_probs["1x2"]["away"],
                ]
            )
        )
        up_dc_ou.append(np.array([dc_probs["ou25"]["over"], dc_probs["ou25"]["under"]]))
        up_dc_btts.append(np.array([dc_probs["btts"]["yes"], dc_probs["btts"]["no"]]))
        up_X.append(_build_upcoming_feature_vector(row))

    up_dc_1x2 = np.array(up_dc_1x2)  # (n_up, 3)
    up_dc_ou = np.array(up_dc_ou)  # (n_up, 2)
    up_dc_btts = np.array(up_dc_btts)  # (n_up, 2)
    up_X = np.array(up_X)  # (n_up, 5)

    # Precompute which upcoming matches have which markets
    has_1x2 = np.array([c is not None for c in up_cons_1x2])
    has_ou25 = np.array([c is not None for c in up_cons_ou25])
    has_btts = np.array([c is not None for c in up_cons_btts])

    # Precompute raw consensus arrays for upcoming
    up_cons_1x2_arr = np.zeros((n_up, 3))
    up_cons_ou25_arr = np.zeros((n_up, 2))
    up_cons_btts_arr = np.zeros((n_up, 2))
    for i in range(n_up):
        if up_cons_1x2[i] is not None:
            up_cons_1x2_arr[i] = [
                up_cons_1x2[i]["home"],
                up_cons_1x2[i]["draw"],
                up_cons_1x2[i]["away"],
            ]
        if up_cons_ou25[i] is not None:
            up_cons_ou25_arr[i] = [up_cons_ou25[i]["over"], up_cons_ou25[i]["under"]]
        if up_cons_btts[i] is not None:
            up_cons_btts_arr[i] = [up_cons_btts[i]["yes"], up_cons_btts[i]["no"]]

    # Collect bootstrap predictions as lists
    boot_1x2 = [[] for _ in range(n_up)]
    boot_ou25 = [[] for _ in range(n_up)]
    boot_btts = [[] for _ in range(n_up)]

    rng = np.random.RandomState(42)
    use_feature = feature_result.get("use_feature_model", False)

    for b in range(n_boot):
        idx = rng.choice(n, size=n, replace=True)

        # Vectorized bias correction
        boot_corrections = _fast_bias_correction(
            precomputed_consensus, precomputed_actuals, idx
        )

        # Fast logistic refit
        boot_lr = None
        if use_feature:
            try:
                boot_lr = LogisticRegression(
                    C=LOGISTIC_C,
                    penalty="l2",
                    multi_class="multinomial",
                    solver="lbfgs",
                    max_iter=500,
                )
                boot_lr.fit(X_completed_np[idx], y_completed_np[idx])
            except Exception:
                boot_lr = None

        # Precompute correction arrays
        corr_h = boot_corrections["home"]
        corr_d = boot_corrections["draw"]
        corr_a = boot_corrections["away"]

        for i in range(n_up):
            # 1X2
            if has_1x2[i]:
                base = up_cons_1x2_arr[i]
                market_1x2 = np.array(
                    [
                        max(0.01, base[0] + corr_h),
                        max(0.01, base[1] + corr_d),
                        max(0.01, base[2] + corr_a),
                    ]
                )
                market_1x2 /= market_1x2.sum()

                if boot_lr is not None:
                    feat_pred = boot_lr.predict_proba(up_X[i].reshape(1, -1))[0]
                    correction = np.clip(
                        feat_pred - market_1x2, -CORRECTION_CAP, CORRECTION_CAP
                    )
                    market_1x2 = np.clip(market_1x2 + correction, 0.01, 0.99)
                    market_1x2 /= market_1x2.sum()

                blended = (
                    BLEND_MARKET_WEIGHT * market_1x2 + BLEND_DC_WEIGHT * up_dc_1x2[i]
                )
                blended /= blended.sum()
                boot_1x2[i].append(blended)

            # O/U 2.5
            if has_ou25[i]:
                blended_ou = (
                    BLEND_MARKET_WEIGHT * up_cons_ou25_arr[i]
                    + BLEND_DC_WEIGHT * up_dc_ou[i]
                )
                blended_ou /= blended_ou.sum()
                boot_ou25[i].append(blended_ou)

            # BTTS
            if has_btts[i]:
                blended_btts = (
                    BLEND_MARKET_WEIGHT * up_cons_btts_arr[i]
                    + BLEND_DC_WEIGHT * up_dc_btts[i]
                )
                blended_btts /= blended_btts.sum()
                boot_btts[i].append(blended_btts)

    # Compute 95% CIs
    cis = {}
    for i, mid in enumerate(up_mids):
        cis[mid] = {}
        if boot_1x2[i]:
            arr = np.array(boot_1x2[i])
            cis[mid]["1x2"] = {
                "low": np.percentile(arr, 2.5, axis=0).tolist(),
                "high": np.percentile(arr, 97.5, axis=0).tolist(),
            }
        else:
            cis[mid]["1x2"] = None
        if boot_ou25[i]:
            arr = np.array(boot_ou25[i])
            cis[mid]["ou25"] = {
                "low": np.percentile(arr, 2.5, axis=0).tolist(),
                "high": np.percentile(arr, 97.5, axis=0).tolist(),
            }
        else:
            cis[mid]["ou25"] = None
        if boot_btts[i]:
            arr = np.array(boot_btts[i])
            cis[mid]["btts"] = {
                "low": np.percentile(arr, 2.5, axis=0).tolist(),
                "high": np.percentile(arr, 97.5, axis=0).tolist(),
            }
        else:
            cis[mid]["btts"] = None

    return cis


def _build_upcoming_feature_vector(row: pd.Series) -> np.ndarray:
    """Build feature vector for an upcoming match."""
    h2h_total = max(row.get("h2h_matches_played", 1) or 1, 1)
    features = np.array(
        [
            ((row.get("home_elo", 0) or 0) - (row.get("away_elo", 0) or 0)) / 100.0,
            (row.get("home_form_score", 0) or 0) - (row.get("away_form_score", 0) or 0),
            (row.get("home_xg_diff", 0) or 0) - (row.get("away_xg_diff", 0) or 0),
            (
                (row.get("days_since_last_match_home", 0) or 0)
                - (row.get("days_since_last_match_away", 0) or 0)
            )
            / 7.0,
            (row.get("h2h_home_wins", 0) or 0) / h2h_total,
        ]
    )
    return np.nan_to_num(features, nan=0.0)


# ─── Stats-Based Markets ──────────────────────────────────────────────────────


def predict_stats_market(
    home_stat: float,
    away_stat: float,
    lines: list[float],
) -> dict:
    """Predict O/U probability for a stats market using Poisson distribution.

    Args:
        home_stat: Rolling average stat for home team (e.g., avg corners)
        away_stat: Rolling average stat for away team
        lines: List of O/U lines to evaluate (e.g., [7.5, 9.5, 10.5])

    Returns dict with chosen line, over_prob, under_prob.
    """
    expected_total = (home_stat + away_stat) / 2.0 * 2.0
    if expected_total <= 0:
        return {"line": lines[0], "over_prob": 0.5, "under_prob": 0.5}

    best_line = lines[0]
    best_diff = 999.0
    best_over = 0.5

    for line in lines:
        over_prob = 1.0 - poisson.cdf(line, expected_total)
        diff = abs(over_prob - 0.5)
        if diff < best_diff:
            best_diff = diff
            best_line = line
            best_over = over_prob

    return {
        "line": best_line,
        "over_prob": round(best_over, 4),
        "under_prob": round(1.0 - best_over, 4),
    }


def assign_stats_confidence(
    match_count_l3: int,
    ci_width: float = 0.20,
) -> str:
    """Assign confidence for stats-based markets (no market consensus)."""
    if match_count_l3 >= 3 and ci_width < 0.15:
        return "HIGH"
    elif match_count_l3 >= 2:
        return "MEDIUM"
    else:
        return "LOW"


# ─── Confidence Levels ────────────────────────────────────────────────────────


def assign_confidence(
    ci: dict | None, n_sources: int, model_beats_baseline: bool
) -> str:
    """Assign HIGH/MEDIUM/LOW confidence based on CI width and data quality."""
    if ci is None:
        return "LOW"

    ci_widths = [h - l for l, h in zip(ci["low"], ci["high"])]
    max_width = max(ci_widths) if ci_widths else 1.0

    if max_width < 0.10 and n_sources >= 2 and model_beats_baseline:
        return "HIGH"
    elif max_width < 0.20 or (n_sources >= 2 and model_beats_baseline):
        return "MEDIUM"
    else:
        return "LOW"


# ─── Asian Handicap ───────────────────────────────────────────────────────────


def get_ah_recommendation(
    market_odds: pd.DataFrame,
    match_id: str,
    dc_model: dict,
    home_team: str,
    away_team: str,
    odds_index: dict | None = None,
) -> dict:
    """Get recommended Asian Handicap line and probabilities."""
    ah = build_ah_consensus(market_odds, match_id, odds_index)
    if ah is not None:
        return ah

    # Fallback: derive from Dixon-Coles
    lh, la = dc_expected_goals(dc_model, home_team, away_team)
    matrix = dc_scoreline_matrix(lh, la, dc_model["rho"])

    # Try common handicap lines, find closest to 50/50
    best_line = 0.0
    best_diff = 999.0
    best_probs = None

    for line in np.arange(-3.0, 3.25, 0.25):
        home_cover = 0.0
        away_cover = 0.0
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                margin = i - j + line
                if margin > 0:
                    home_cover += matrix[i, j]
                elif margin < 0:
                    away_cover += matrix[i, j]
                else:
                    home_cover += matrix[i, j] * 0.5
                    away_cover += matrix[i, j] * 0.5
        diff = abs(home_cover - 0.5)
        if diff < best_diff:
            best_diff = diff
            best_line = line
            best_probs = {"home": home_cover, "away": away_cover, "line": line}

    if best_probs is None:
        best_probs = {"home": 0.5, "away": 0.5, "line": 0.0}

    best_probs["sources"] = ["dixon_coles"]
    best_probs["n_sources"] = 0
    return best_probs


# ─── Narrative Generation ─────────────────────────────────────────────────────


def generate_narrative(
    row: pd.Series,
    consensus_1x2: dict | None,
    final_1x2: np.ndarray,
    dc_lh: float,
    dc_la: float,
    top_scorelines: list[dict],
    confidence_1x2: str,
    feature_result: dict,
    corrections: dict,
    qual: dict | None = None,
) -> str:
    """Generate a 3-5 sentence plain English narrative for a match.

    For knockout matches, the narrative focuses on qualification probability
    with 90-minute probabilities as supporting detail.
    """
    home = row["home_team"]
    away = row["away_team"]
    elo_diff = (row.get("home_elo", 0) or 0) - (row.get("away_elo", 0) or 0)
    is_knockout = row.get("stage") == "knockout"

    # Qualification headline (knockout only)
    qual_str = ""
    if is_knockout and qual is not None:
        hq = qual["home_qualify_prob"]
        aq = qual["away_qualify_prob"]
        et = qual["extra_time_prob"]
        pen = qual["penalties_prob"]
        if hq > aq:
            qual_str = (
                f"{home} are favoured to qualify ({hq:.1%}) over {away} ({aq:.1%}). "
            )
        else:
            qual_str = (
                f"{away} are favoured to qualify ({aq:.1%}) over {home} ({hq:.1%}). "
            )
        if et > 0.25:
            qual_str += f"There is a {et:.0%} chance the match reaches extra time"
            if pen > 0.10:
                qual_str += f", with a {pen:.0%} chance of penalties. "
            else:
                qual_str += ". "

    # Team strength
    if abs(elo_diff) < 50:
        strength = f"{home} and {away} are closely matched (Elo diff: {elo_diff:+.0f})"
    elif elo_diff > 0:
        strength = f"{home} are the stronger side by Elo ({elo_diff:+.0f})"
    else:
        strength = f"{away} are the stronger side by Elo ({abs(elo_diff):+.0f})"

    # Form
    home_form = row.get("home_form_score", None)
    away_form = row.get("away_form_score", None)
    form_str = ""
    if home_form is not None and away_form is not None:
        if abs(home_form - away_form) > 0.2:
            better_form = home if home_form > away_form else away
            form_str = f" {better_form} carry better recent form ({home_form:.1f} vs {away_form:.1f})."
        else:
            form_str = f" Both teams enter in similar form ({home_form:.1f} vs {away_form:.1f})."

    # Market implication
    if consensus_1x2 is not None:
        fav_idx = np.argmax(
            [consensus_1x2["home"], consensus_1x2["draw"], consensus_1x2["away"]]
        )
        fav_name = ["home", "draw", "away"][fav_idx]
        fav_prob = [
            consensus_1x2["home"],
            consensus_1x2["draw"],
            consensus_1x2["away"],
        ][fav_idx]
        market_str = f"The market prices {fav_name} at {fav_prob:.1%}"
    else:
        market_str = "Market odds are limited"

    # Model agreement
    model_fav_idx = np.argmax(final_1x2)
    model_fav_name = ["home", "draw", "away"][model_fav_idx]
    model_fav_prob = final_1x2[model_fav_idx]

    if consensus_1x2 is not None and fav_idx == model_fav_idx:
        diff = abs(model_fav_prob - fav_prob)
        if diff < 0.03:
            agree_str = f"and the model agrees ({model_fav_prob:.1%}), with no meaningful edge detected."
        else:
            agree_str = f"and the model broadly agrees ({model_fav_prob:.1%}) but adjusts by {diff:+.1%}."
    elif consensus_1x2 is not None:
        agree_str = f"but the model leans {model_fav_name} ({model_fav_prob:.1%}), diverging from the market."
    else:
        agree_str = f"and the model estimates {model_fav_name} at {model_fav_prob:.1%}."

    # Feature correction note
    feat_note = ""
    if feature_result.get("use_feature_model", False) and not feature_result.get(
        "negligible_signal", True
    ):
        feat_note = " Feature corrections are contributing marginal signal."
    elif feature_result.get("negligible_signal", True):
        feat_note = (
            " Feature corrections are negligible; relying on calibrated market prior."
        )

    # Scoreline
    top_sc = top_scorelines[0] if top_scorelines else None
    score_str = ""
    if top_sc:
        score_str = f" Most likely scoreline: {top_sc['scoreline']} ({top_sc['probability']:.1%})."

    # Confidence
    conf_str = f" Confidence: {confidence_1x2}."

    narrative = f"{strength}.{form_str} {market_str} {agree_str}{feat_note}{score_str}{conf_str}"
    return narrative


# ─── Table Creation & Storage ─────────────────────────────────────────────────

CREATE_TABLE_SQL = """
DROP TABLE IF EXISTS public.match_predictions CASCADE;
CREATE TABLE public.match_predictions (
    match_id TEXT PRIMARY KEY,
    match_date TIMESTAMPTZ,
    home_team TEXT,
    away_team TEXT,
    stage TEXT,
    group_name TEXT,
    prob_home DOUBLE PRECISION,
    prob_draw DOUBLE PRECISION,
    prob_away DOUBLE PRECISION,
    prob_home_ci DOUBLE PRECISION[],
    prob_draw_ci DOUBLE PRECISION[],
    prob_away_ci DOUBLE PRECISION[],
    confidence_1x2 TEXT,
    ah_line DOUBLE PRECISION,
    ah_home_prob DOUBLE PRECISION,
    ah_away_prob DOUBLE PRECISION,
    ah_home_ci DOUBLE PRECISION[],
    ah_away_ci DOUBLE PRECISION[],
    confidence_ah TEXT,
    over_25_prob DOUBLE PRECISION,
    under_25_prob DOUBLE PRECISION,
    over_25_ci DOUBLE PRECISION[],
    under_25_ci DOUBLE PRECISION[],
    confidence_ou TEXT,
    btts_yes_prob DOUBLE PRECISION,
    btts_no_prob DOUBLE PRECISION,
    btts_yes_ci DOUBLE PRECISION[],
    btts_no_ci DOUBLE PRECISION[],
    confidence_btts TEXT,
    dc_home_xg DOUBLE PRECISION,
    dc_away_xg DOUBLE PRECISION,
    dc_top_scorelines JSONB,
    narrative TEXT,
    model_version TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""


def create_predictions_table(supabase):
    """Check if match_predictions table exists, print SQL if not."""
    try:
        supabase.table("match_predictions").select("match_id").limit(1).execute()
        print("  match_predictions table exists")
    except Exception:
        print("  WARNING: match_predictions table does not exist.")
        print("  Please run this SQL in Supabase dashboard:")
        print(CREATE_TABLE_SQL)
        raise


def _sanitize_nan(d: dict) -> dict:
    """Replace NaN/inf values with None for JSON serialization."""
    clean = {}
    for k, v in d.items():
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            clean[k] = None
        elif isinstance(v, list):
            clean[k] = [
                None if isinstance(x, float) and (np.isnan(x) or np.isinf(x)) else x
                for x in v
            ]
        else:
            clean[k] = v
    return clean


def store_predictions(supabase, predictions: list[dict]):
    """Upsert predictions — inserts new, updates existing by match_id."""
    for pred in predictions:
        clean_pred = _sanitize_nan(pred)
        supabase.table("match_predictions").upsert(clean_pred).execute()
    print(f"  Stored {len(predictions)} predictions")


def store_model_params(
    supabase,
    dc_model: dict,
    corrections: dict,
    feature_result: dict,
    calib_result: dict,
    temporal_result: dict,
    n_training: int,
):
    """Store trained model parameters for TUI lightweight recomputation."""
    dc_params = {
        "team_idx": dc_model["team_idx"],
        "attack": dc_model["attack"].tolist(),
        "defense": dc_model["defense"].tolist(),
        "home_adv": float(dc_model["home_adv"]),
        "rho": float(dc_model["rho"]),
        "n_teams": dc_model["n_teams"],
        "converged": dc_model["converged"],
    }

    feature_coefs = {}
    if feature_result.get("correction_magnitudes"):
        for feat, info in feature_result["correction_magnitudes"].items():
            feature_coefs[feat] = {
                "coef_home": info["coef_home"],
                "coef_draw": info["coef_draw"],
                "coef_away": info["coef_away"],
            }

    feature_meta = {
        "use_feature_model": feature_result.get("use_feature_model", False),
        "negligible_signal": feature_result.get("negligible_signal", True),
        "mean_abs_correction": feature_result.get("mean_abs_correction", 0.0),
        "loo_brier_with": feature_result.get("loo_brier_with", 0.0),
        "loo_brier_without": feature_result.get("loo_brier_without", 0.0),
    }

    validation = {
        "consensus_brier": calib_result.get("consensus_brier", 0.0),
        "per_source_brier": {
            k: v["brier"] for k, v in calib_result.get("per_source_brier", {}).items()
        },
        "biases": calib_result.get("biases", {}),
        "temporal": {
            "brier_model": temporal_result.get("brier_model"),
            "brier_baseline": temporal_result.get("brier_baseline"),
        },
    }

    params = {
        "model_version": MODEL_VERSION,
        "dc_params": json.dumps(dc_params),
        "calibration_corrections": json.dumps(corrections),
        "feature_model_coefs": json.dumps(feature_coefs),
        "feature_model_metadata": json.dumps(feature_meta),
        "validation_metrics": json.dumps(validation),
        "n_training_matches": n_training,
    }

    try:
        supabase.table("model_params").insert(params).execute()
        print("  Stored model params to model_params table")
    except Exception as e:
        print(f"  Could not store model params: {e}")


# ─── Validation Summary ───────────────────────────────────────────────────────


def temporal_holdout_validation(
    feature_df: pd.DataFrame,
    market_odds: pd.DataFrame,
    corrections: dict,
    feature_result: dict,
    dc_model: dict,
    odds_index: dict | None = None,
) -> dict:
    """Train on first 60% of completed matches, test on remaining 40%."""
    completed = feature_df[feature_df["is_training_row"] == True].copy()
    completed = completed.sort_values("match_date").reset_index(drop=True)

    n = len(completed)
    split = max(int(n * 0.6), n - 10)
    train = completed.iloc[:split]
    test = completed.iloc[split:]

    if len(test) < 3:
        return {
            "train_size": split,
            "test_size": len(test),
            "brier_model": None,
            "brier_baseline": None,
        }

    # Recompute corrections on train only
    train_result = calibration_analysis(train, market_odds)
    train_corrections = train_result["corrections"]

    # Refit feature model on train
    train_feat = feature_correction_loo_cv(train, market_odds, train_corrections)
    lr_model = train_feat.get("lr_model")

    model_briers = []
    baseline_briers = []

    for _, row in test.iterrows():
        mid = row["match_id"]
        cons = build_1x2_consensus(market_odds, mid, odds_index)
        if cons is None:
            continue

        calibrated = apply_calibration_corrections(cons, train_corrections)
        market_1x2 = np.array(
            [calibrated["home"], calibrated["draw"], calibrated["away"]]
        )

        if lr_model is not None and train_feat["use_feature_model"]:
            X_match = _build_upcoming_feature_vector(row)
            market_1x2 = apply_feature_corrections(market_1x2, X_match, lr_model)

        lh, la = dc_expected_goals(dc_model, row["home_team"], row["away_team"])
        matrix = dc_scoreline_matrix(lh, la, dc_model["rho"])
        dc_1x2 = np.array(
            [
                dc_market_probs(matrix)["1x2"]["home"],
                dc_market_probs(matrix)["1x2"]["draw"],
                dc_market_probs(matrix)["1x2"]["away"],
            ]
        )
        blended = blend_market_dc(market_1x2, dc_1x2)

        actual = _actual_1x2_vector(row["result_1x2"])

        baseline = np.array([cons["home"], cons["draw"], cons["away"]])

        model_briers.append(np.sum((blended - actual) ** 2))
        baseline_briers.append(np.sum((baseline - actual) ** 2))

    return {
        "train_size": split,
        "test_size": len(model_briers),
        "brier_model": float(np.mean(model_briers)) if model_briers else None,
        "brier_baseline": float(np.mean(baseline_briers)) if baseline_briers else None,
    }


def print_validation_summary(
    calib_result: dict,
    feature_result: dict,
    temporal_result: dict,
    dc_model: dict,
):
    """Print comprehensive validation summary to console."""
    print("\n" + "=" * 80)
    print("  WC 2026 PREDICTION MODEL — VALIDATION SUMMARY")
    print("=" * 80)

    print(f"\n  Training matches: {calib_result['n_completed']}")
    print(
        f"  Dixon-Coles matches: {dc_model['n_teams']} teams, converged={dc_model['converged']}"
    )

    # Per-source Brier scores
    print("\n  ── Per-Source Brier Scores (1X2) ──")
    for source, info in sorted(
        calib_result["per_source_brier"].items(), key=lambda x: x[1]["brier"]
    ):
        print(f"    {source:20s}  Brier={info['brier']:.4f}  n={info['n_matches']}")
    print(
        f"    {'Consensus':20s}  Brier={calib_result['consensus_brier']:.4f}  n={calib_result['n_completed']}"
    )

    # Bias detection
    print("\n  ── Systematic Bias Detection ──")
    biases = calib_result["biases"]
    actual = calib_result["actual_rates"]
    predicted = calib_result["predicted_rates"]
    print(
        f"    Home:  actual={actual['home']:.1%}  predicted={predicted['home']:.1%}  bias={biases['home']:+.1%}"
    )
    print(
        f"    Draw:  actual={actual['draw']:.1%}  predicted={predicted['draw']:.1%}  bias={biases['draw']:+.1%}"
    )
    print(
        f"    Away:  actual={actual['away']:.1%}  predicted={predicted['away']:.1%}  bias={biases['away']:+.1%}"
    )
    print(f"    Favorite bias: {biases['favorite']:+.1%}")

    # Correction factors
    print("\n  ── Calibration Correction Factors ──")
    corr = calib_result["corrections"]
    print(f"    Home correction:      {corr['home']:+.1%}")
    print(f"    Draw correction:      {corr['draw']:+.1%}")
    print(f"    Away correction:      {corr['away']:+.1%}")
    print(f"    Favorite correction:  {corr['favorite']:+.1%}")

    # Cross-source divergence
    div = calib_result["divergence"]
    if div["total"] > 0:
        print(f"\n  ── Cross-Source Divergence (Bet365 vs Sharp) ──")
        print(
            f"    Sharp right: {div['sharp_right']}  Soft right: {div['soft_right']}  Neither: {div['neither']}  Total: {div['total']}"
        )

    # Feature correction model
    print("\n  ── Feature Correction Model ──")
    print(f"    LOO Brier WITH corrections:    {feature_result['loo_brier_with']:.4f}")
    print(
        f"    LOO Brier WITHOUT corrections: {feature_result['loo_brier_without']:.4f}"
    )
    print(f"    Use feature model: {feature_result['use_feature_model']}")
    print(f"    Best C: {feature_result.get('best_C', 'N/A')}")
    print(f"    Mean absolute correction: {feature_result['mean_abs_correction']:.4f}")

    if feature_result["correction_magnitudes"]:
        print("\n    Per-feature coefficient magnitudes:")
        for feat, info in feature_result["correction_magnitudes"].items():
            print(
                f"      {feat:25s}  |coef|={info['abs_mean']:.4f}  (H={info['coef_home']:+.3f}, D={info['coef_draw']:+.3f}, A={info['coef_away']:+.3f})"
            )

    if feature_result["negligible_signal"]:
        print(
            "\n    *** FEATURE MODEL CONTRIBUTING NEGLIGIBLE SIGNAL (mean abs correction < 0.01) ***"
        )
        print("    *** Relying on calibrated market prior only. ***")

    # Temporal holdout
    print("\n  ── Temporal Holdout Validation ──")
    if temporal_result["brier_model"] is not None:
        print(
            f"    Train: {temporal_result['train_size']} matches  Test: {temporal_result['test_size']} matches"
        )
        print(f"    Model Brier:    {temporal_result['brier_model']:.4f}")
        print(f"    Baseline Brier: {temporal_result['brier_baseline']:.4f}")
        if temporal_result["brier_model"] < temporal_result["brier_baseline"]:
            print("    Model BEATS baseline on temporal holdout.")
        else:
            print("    Model does NOT beat baseline — corrections may be adding noise.")
    else:
        print("    Insufficient data for temporal holdout.")

    print("\n" + "=" * 80 + "\n")


# ─── Main Pipeline ────────────────────────────────────────────────────────────


def main():
    print("\n  WC 2026 Match Prediction Model")
    print(f"  Version: {MODEL_VERSION}")
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}\n")

    # 1. Load data
    print("  [1/9] Loading data from Supabase...")
    supabase = get_supabase()

    feature_df = load_feature_view(supabase)
    print(f"    Feature view: {len(feature_df)} rows")

    market_odds = load_market_odds(supabase)
    print(f"    Market odds (pre-kickoff): {len(market_odds)} rows")

    try:
        intl_df = load_international_matches(supabase)
        print(f"    International matches: {len(intl_df)} rows")
    except Exception as e:
        print(f"    International matches: SKIPPED ({e})")
        intl_df = pd.DataFrame()

    try:
        tour_df = load_tournament_matches(supabase)
        print(f"    Tournament matches: {len(tour_df)} rows")
    except Exception as e:
        print(f"    Tournament matches: SKIPPED ({e})")
        tour_df = pd.DataFrame()

    # 2. Pre-compute odds index (used everywhere)
    print("  [2/9] Building odds index...")
    odds_index = _precompute_odds_index(market_odds)
    print(f"    Indexed {len(odds_index)} (match, market_type) pairs")

    # 3. Prepare Dixon-Coles data and fit
    print("\n  [3/9] Fitting Dixon-Coles model...")
    dc_df = _prepare_dc_data(intl_df, tour_df, feature_df=feature_df)
    print(
        f"    DC training data: {len(dc_df)} matches, {dc_df['home'].nunique()} teams"
    )
    dc_model = fit_dixon_coles(dc_df)
    print(f"    Converged: {dc_model['converged']}")
    print(f"    Home advantage: {dc_model['home_adv']:.3f}")
    print(f"    Rho (DC correction): {dc_model['rho']:.4f}")

    # 4. Market calibration analysis
    print("\n  [4/9] Running market calibration analysis...")
    calib_result = calibration_analysis(feature_df, market_odds, odds_index)
    corrections = calib_result["corrections"]
    print(f"    Consensus Brier: {calib_result['consensus_brier']:.4f}")
    print(f"    Draw bias: {calib_result['biases']['draw']:+.1%}")

    # 5. Feature correction model
    print("\n  [5/9] Fitting feature correction model (LOO CV)...")
    feature_result = feature_correction_loo_cv(
        feature_df, market_odds, corrections, odds_index
    )
    print(f"    LOO Brier with corrections: {feature_result['loo_brier_with']:.4f}")
    print(
        f"    LOO Brier without corrections: {feature_result['loo_brier_without']:.4f}"
    )
    print(f"    Use feature model: {feature_result['use_feature_model']}")
    print(f"    Mean abs correction: {feature_result['mean_abs_correction']:.4f}")
    best_c = feature_result.get("best_C")
    print(f"    Best C: {best_c if best_c is not None else 'none beat baseline'}")

    if feature_result["correction_magnitudes"]:
        print("    Per-feature magnitudes:")
        for feat, info in feature_result["correction_magnitudes"].items():
            print(f"      {feat:25s}  |coef|={info['abs_mean']:.4f}")

    if feature_result["negligible_signal"]:
        print("    *** NEGLIGIBLE SIGNAL — feature model effectively doing nothing ***")

    # 6. Temporal holdout validation
    print("\n  [6/9] Temporal holdout validation...")
    temporal_result = temporal_holdout_validation(
        feature_df, market_odds, corrections, feature_result, dc_model, odds_index
    )
    if temporal_result["brier_model"] is not None:
        print(
            f"    Model Brier: {temporal_result['brier_model']:.4f} vs Baseline: {temporal_result['brier_baseline']:.4f}"
        )

    # 7. Identify upcoming matches to predict
    print("\n  [7/9] Identifying prediction targets...")
    now_utc = datetime.now(timezone.utc)
    upcoming = feature_df[
        (feature_df["result_1x2"].isna())
        & (feature_df["home_team"].notna())
        & (feature_df["away_team"].notna())
        & (feature_df["match_date"] > now_utc)
    ].copy()

    # Filter out knockout placeholders — team names that start with a digit
    # or contain "Winner"/"Loser"/"Runner" are not real teams yet
    def is_real_team(name):
        if name is None or (isinstance(name, float) and np.isnan(name)):
            return False
        s = str(name)
        if s[0].isdigit():
            return False
        if any(kw in s for kw in ["Winner", "Loser", "Runner"]):
            return False
        return True

    upcoming = upcoming[
        upcoming["home_team"].apply(is_real_team)
        & upcoming["away_team"].apply(is_real_team)
    ].copy()
    upcoming = upcoming.sort_values("match_date").reset_index(drop=True)
    print(
        f"    Upcoming matches with known teams (after {now_utc.isoformat()}): {len(upcoming)}"
    )

    if upcoming.empty:
        print("    No upcoming matches to predict. Exiting.")
        return

    # 8. Bootstrap CIs
    print(
        f"\n  [8/9] Computing bootstrap confidence intervals ({BOOTSTRAP_N} resamples)..."
    )
    t0 = time.time()
    boot_cis = bootstrap_predictions(
        feature_df,
        market_odds,
        corrections,
        feature_result,
        dc_model,
        upcoming,
        n_boot=BOOTSTRAP_N,
        odds_index=odds_index,
    )
    print(f"    Bootstrap completed in {time.time() - t0:.1f}s")

    # 9. Generate final predictions
    print("\n  [9/9] Generating final predictions...")
    lr_model = feature_result.get("lr_model")
    model_beats_baseline = (
        feature_result["loo_brier_with"] < feature_result["loo_brier_without"]
    )

    predictions = []
    for _, row in upcoming.iterrows():
        mid = row["match_id"]

        # Consensus
        cons_1x2 = build_1x2_consensus(market_odds, mid, odds_index)
        cons_ou25 = build_ou25_consensus(market_odds, mid, odds_index)
        cons_btts = build_btts_consensus(market_odds, mid, odds_index)

        # DC
        dc_lh, dc_la = dc_expected_goals(dc_model, row["home_team"], row["away_team"])
        dc_matrix = dc_scoreline_matrix(dc_lh, dc_la, dc_model["rho"])
        dc_probs = dc_market_probs(dc_matrix)
        top_scorelines = dc_top_scorelines(dc_matrix)

        # 1X2 final
        if cons_1x2 is not None:
            calibrated = apply_calibration_corrections(cons_1x2, corrections)
            market_1x2 = np.array(
                [calibrated["home"], calibrated["draw"], calibrated["away"]]
            )

            if lr_model is not None and feature_result["use_feature_model"]:
                X_match = _build_upcoming_feature_vector(row)
                market_1x2 = apply_feature_corrections(market_1x2, X_match, lr_model)

            dc_1x2 = np.array(
                [
                    dc_probs["1x2"]["home"],
                    dc_probs["1x2"]["draw"],
                    dc_probs["1x2"]["away"],
                ]
            )
            final_1x2 = blend_market_dc(market_1x2, dc_1x2)
        else:
            final_1x2 = np.array(
                [
                    dc_probs["1x2"]["home"],
                    dc_probs["1x2"]["draw"],
                    dc_probs["1x2"]["away"],
                ]
            )

        # O/U 2.5 final
        if cons_ou25 is not None:
            market_ou = np.array([cons_ou25["over"], cons_ou25["under"]])
            dc_ou = np.array([dc_probs["ou25"]["over"], dc_probs["ou25"]["under"]])
            final_ou = BLEND_MARKET_WEIGHT * market_ou + BLEND_DC_WEIGHT * dc_ou
            final_ou /= final_ou.sum()
        else:
            final_ou = np.array([dc_probs["ou25"]["over"], dc_probs["ou25"]["under"]])

        # BTTS final
        if cons_btts is not None:
            market_btts = np.array([cons_btts["yes"], cons_btts["no"]])
            dc_btts = np.array([dc_probs["btts"]["yes"], dc_probs["btts"]["no"]])
            final_btts = BLEND_MARKET_WEIGHT * market_btts + BLEND_DC_WEIGHT * dc_btts
            final_btts /= final_btts.sum()
        else:
            final_btts = np.array([dc_probs["btts"]["yes"], dc_probs["btts"]["no"]])

        # Asian Handicap
        ah = get_ah_recommendation(
            market_odds, mid, dc_model, row["home_team"], row["away_team"], odds_index
        )

        # Confidence levels
        ci_1x2 = boot_cis.get(mid, {}).get("1x2")
        ci_ou = boot_cis.get(mid, {}).get("ou25")
        ci_btts = boot_cis.get(mid, {}).get("btts")

        n_sources_1x2 = cons_1x2["n_sources"] if cons_1x2 else 0
        n_sources_ou = cons_ou25["n_sources"] if cons_ou25 else 0
        n_sources_btts = cons_btts["n_sources"] if cons_btts else 0

        conf_1x2 = assign_confidence(ci_1x2, n_sources_1x2, model_beats_baseline)
        conf_ou = assign_confidence(ci_ou, n_sources_ou, model_beats_baseline)
        conf_btts = assign_confidence(ci_btts, n_sources_btts, model_beats_baseline)
        conf_ah = "LOW" if ah.get("n_sources", 0) == 0 else "MEDIUM"

        # Qualification probabilities (knockout stage)
        qual = compute_qualification_probs(
            dc_model,
            row["home_team"],
            row["away_team"],
            {
                "home": float(final_1x2[0]),
                "draw": float(final_1x2[1]),
                "away": float(final_1x2[2]),
            },
        )

        # Narrative
        narrative = generate_narrative(
            row,
            cons_1x2,
            final_1x2,
            dc_lh,
            dc_la,
            top_scorelines,
            conf_1x2,
            feature_result,
            corrections,
            qual,
        )

        # Build prediction row
        pred = {
            "match_id": mid,
            "match_date": row["match_date"].isoformat()
            if pd.notna(row["match_date"])
            else None,
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "stage": row["stage"],
            "group_name": row["group_name"],
            "prob_home": float(final_1x2[0]),
            "prob_draw": float(final_1x2[1]),
            "prob_away": float(final_1x2[2]),
            "confidence_1x2": conf_1x2,
            "ah_line": float(ah["line"]),
            "ah_home_prob": float(ah["home"]),
            "ah_away_prob": float(ah["away"]),
            "confidence_ah": conf_ah,
            "over_25_prob": float(final_ou[0]),
            "under_25_prob": float(final_ou[1]),
            "confidence_ou": conf_ou,
            "btts_yes_prob": float(final_btts[0]),
            "btts_no_prob": float(final_btts[1]),
            "confidence_btts": conf_btts,
            "dc_home_xg": dc_lh,
            "dc_away_xg": dc_la,
            "dc_top_scorelines": json.dumps(top_scorelines),
            "narrative": narrative,
            "model_version": MODEL_VERSION,
            "home_qualify_prob": qual["home_qualify_prob"],
            "away_qualify_prob": qual["away_qualify_prob"],
            "extra_time_prob": qual["extra_time_prob"],
            "penalties_prob": qual["penalties_prob"],
        }

        # Stats-based markets (from rolling Fotmob averages)
        home_corners = row.get("home_corners_l3", None)
        away_corners = row.get("away_corners_l3", None)
        if home_corners is not None and away_corners is not None:
            corners = predict_stats_market(home_corners, away_corners, [7.5, 9.5, 10.5])
            pred["corners_line"] = corners["line"]
            pred["corners_over_prob"] = corners["over_prob"]
            pred["corners_under_prob"] = corners["under_prob"]
            pred["confidence_corners"] = assign_stats_confidence(
                int(row.get("home_match_count_l3", 0))
            )

        home_sot = row.get("home_shots_ot_l3", None)
        away_sot = row.get("away_shots_ot_l3", None)
        if home_sot is not None and away_sot is not None:
            sot = predict_stats_market(home_sot, away_sot, [6.5, 8.5, 10.5])
            pred["sot_line"] = sot["line"]
            pred["sot_over_prob"] = sot["over_prob"]
            pred["sot_under_prob"] = sot["under_prob"]
            pred["confidence_sot"] = assign_stats_confidence(
                int(row.get("home_match_count_l3", 0))
            )

        home_yellow = row.get("home_yellow_l3", None)
        away_yellow = row.get("away_yellow_l3", None)
        if home_yellow is not None and away_yellow is not None:
            cards = predict_stats_market(home_yellow, away_yellow, [2.5, 3.5, 4.5])
            pred["cards_line"] = cards["line"]
            pred["cards_over_prob"] = cards["over_prob"]
            pred["cards_under_prob"] = cards["under_prob"]
            pred["confidence_cards"] = assign_stats_confidence(
                int(row.get("home_match_count_l3", 0))
            )

        # Add CIs as arrays
        if ci_1x2:
            pred["prob_home_ci"] = [ci_1x2["low"][0], ci_1x2["high"][0]]
            pred["prob_draw_ci"] = [ci_1x2["low"][1], ci_1x2["high"][1]]
            pred["prob_away_ci"] = [ci_1x2["low"][2], ci_1x2["high"][2]]
        if ci_ou:
            pred["over_25_ci"] = [ci_ou["low"][0], ci_ou["high"][0]]
            pred["under_25_ci"] = [ci_ou["low"][1], ci_ou["high"][1]]
        if ci_btts:
            pred["btts_yes_ci"] = [ci_btts["low"][0], ci_btts["high"][0]]
            pred["btts_no_ci"] = [ci_btts["low"][1], ci_btts["high"][1]]

        predictions.append(pred)

    # 9. Store predictions and model params
    print(f"\n  [9/9] Storing {len(predictions)} predictions to Supabase...")
    try:
        create_predictions_table(supabase)
    except Exception:
        print("    Table check failed. Please create tables manually (see SQL above).")
        print("    Predictions will be printed to console but not stored.\n")
        print_validation_summary(
            calib_result, feature_result, temporal_result, dc_model
        )
        _print_predictions(predictions)
        return

    try:
        store_predictions(supabase, predictions)
    except Exception as e:
        print(f"    Storage error: {e}")
        print("    Predictions generated but not stored. See console output.")

    try:
        store_model_params(
            supabase,
            dc_model,
            corrections,
            feature_result,
            calib_result,
            temporal_result,
            len(upcoming),
        )
    except Exception as e:
        print(f"    Model params storage error: {e}")

    # Print validation summary
    print_validation_summary(calib_result, feature_result, temporal_result, dc_model)

    # Print predictions summary
    _print_predictions(predictions)

    print(f"  Completed: {datetime.now(timezone.utc).isoformat()}")
    print(f"  Total predictions: {len(predictions)}\n")


def _print_predictions(predictions: list[dict]):
    """Print predictions summary to console."""
    print("  ── Predictions Summary ──\n")
    for pred in predictions:
        hq = pred.get("home_qualify_prob")
        aq = pred.get("away_qualify_prob")
        et = pred.get("extra_time_prob")
        if hq is not None and aq is not None:
            qual_line = f"  To Qualify: {pred['home_team']} {hq:.1%} | {pred['away_team']} {aq:.1%}"
            if et and et > 0:
                qual_line += f"  ET: {et:.0%}"
            print(f"    {pred['home_team']:25s} vs {pred['away_team']:25s}")
            print(f"      {qual_line}")
        else:
            print(
                f"    {pred['home_team']:25s} vs {pred['away_team']:25s}  "
                f"H={pred['prob_home']:.1%} D={pred['prob_draw']:.1%} A={pred['prob_away']:.1%}  "
                f"[{pred['confidence_1x2']}]"
            )
        print(
            f"      90-min: H={pred['prob_home']:.1%} D={pred['prob_draw']:.1%} A={pred['prob_away']:.1%}  "
            f"O/U 2.5: {pred['over_25_prob']:.1%}/{pred['under_25_prob']:.1%}  "
            f"BTTS: {pred['btts_yes_prob']:.1%}/{pred['btts_no_prob']:.1%}  "
            f"AH: {pred['ah_line']:+.1f}"
        )
        print(f"      DC xG: {pred['dc_home_xg']:.2f} - {pred['dc_away_xg']:.2f}")
        print(f"      {pred['narrative']}")
        print()


if __name__ == "__main__":
    main()
