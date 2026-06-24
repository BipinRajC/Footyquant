from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_package_modules_do_not_reference_deleted_legacy_tables():
    deleted_tables = {
        "api_budget",
        "data_coverage",
        "historical_odds",
        "match_odds",
        "odds_snapshots",
        "prediction_market_snapshots",
        "predictions",
        "wc_feature_view",
    }
    live_files = [
        ROOT / "footyquant" / "db.py",
        ROOT / "footyquant" / "__main__.py",
        ROOT / "footyquant" / "team_mapping.py",
        ROOT / "footyquant" / "polymarket.py",
    ]

    offenders = []
    for path in live_files:
        text = path.read_text()
        for table in deleted_tables:
            if table in text:
                offenders.append((path.name, table))

    assert offenders == []


def test_polymarket_parser_does_not_depend_on_deleted_collector_module():
    text = (ROOT / "footyquant" / "polymarket.py").read_text()

    assert "polymarket_collector" not in text


def test_deleted_oddspapi_modules_are_absent():
    stale_modules = [
        ROOT / "footyquant" / "collector.py",
        ROOT / "footyquant" / "load_reference.py",
        ROOT / "footyquant" / "oddspapi.py",
    ]

    assert [path for path in stale_modules if path.exists()] == []
