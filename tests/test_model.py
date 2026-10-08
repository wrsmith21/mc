"""The data-science layer: measured, calibrated, and the shipped artifacts match what was measured."""
import json
import os
from pathlib import Path

import numpy as np

os.environ["DEMO_MODE"] = "replay"

from backend import model as ds  # noqa: E402
from backend.engine.recommend import Recommender  # noqa: E402
from backend.store import get_store  # noqa: E402

MODEL = Path(__file__).resolve().parent.parent / "data" / "model"


def test_artifacts_exist_and_production_model_is_measured():
    m = ds.metrics()
    assert m and m["production_model"] in m["models"]
    for f in ("metrics.json", "calibration.json", "model_card.json", "dataset_manifest.json", "challenger_weights.npz"):
        assert (MODEL / f).exists(), f
    assert m["lines"]["test"] > 3000 and m["split"]["test"] == ["2026-07", "2026-09"]


def test_first_time_right_does_not_regress():
    """A regression floor: retraining that loses more than a point blocks deploy."""
    prod = ds.metrics()["models"][ds.metrics()["production_model"]]
    assert prod["first_time_right"] >= 0.94 and prod["top3"] >= 0.99


def test_calibration_is_monotone_and_improves_error():
    for name, curve in json.loads((MODEL / "calibration.json").read_text()).items():
        assert all(b >= a for a, b in zip(curve["y"], curve["y"][1:])), name
        r = ds.metrics()["models"][name]
        assert r["ece_calibrated"] <= r["ece_raw"]


def test_recommendation_carries_model_version_and_second_opinion():
    s = get_store()
    rec = Recommender(s)
    r = rec.recommend_line("V1102", "Monthly mobile service – Sep 2026", 1, 26840.2, 26840.2)
    assert r["raw_confidence"] <= 1 and 0 <= r["confidence"] <= 0.99
    assert r["model"]["version"] == ds.metrics()["version"] and r["model"]["second_opinion"]["account"] == "6310"


def test_anomaly_sweep_finds_every_planted_journal():
    a = ds.metrics()["anomaly"]
    assert a["journals"]["planted_found"] == a["journals"]["planted"]
    assert a["ap_ledger"]["precision"] >= 0.9


def test_challenger_probabilities_sum_to_one():
    p = ds.challenger().proba("Latitude 7450 laptop", "V1043", "it_hardware", "US01", 18450, 1845)
    assert abs(float(np.sum(p)) - 1) < 1e-9
