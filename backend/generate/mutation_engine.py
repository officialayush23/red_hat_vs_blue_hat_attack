"""
Deterministic mutation engine — turns a qualitative combination from
evaluation/split_policy.py (e.g. {"amount": "low", "velocity": "high"})
into concrete numeric generation parameters (e.g. amount in $2-$40, gaps of
1-6 seconds between transactions).

This is the layer Principle 3 in docs/TECHNICAL_SPEC.md is about: an LLM
strategist (Phase 4, not yet built) may eventually pick WHICH combination to
target, but this file is what turns a combination into actual numbers, and
it is 100% deterministic code with a seeded RNG -- no LLM call anywhere in
this module, ever.

Amount and inter-transaction-gap ranges are grounded in the real legitimate
(is_fraud == 0) transaction distribution per source dataset, not hardcoded
magic numbers -- see load_reference_stats(). This is what gives generated
attacks distributional fidelity (the "fidelity of attacks in simulation"
judging criterion) instead of looking synthetic-obviously-synthetic.
"""

import json
from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
FEATURES_PATH = PROCESSED_DIR / "features.parquet"
REFERENCE_STATS_PATH = PROCESSED_DIR / "reference_stats.json"

# Unset dimensions in a chosen combo fall back to these.
DEFAULT_PARAMS = {
    "transaction_fraud": {"amount": "mid", "velocity": "normal", "merchant_category": "normal", "time_of_day": "normal"},
    "account_takeover": {"device": "known", "location": "trusted", "beneficiary_change": False, "velocity": "normal"},
    "synthetic_identity": {"account_age": "normal", "device_history": "normal", "behavior_pattern": "normal", "relationship_count": "normal"},
    "mule_network": {"hop_count": "2_3", "shared_device": False, "timing_gaps": "normal", "cash_out": True},
}


def compute_reference_stats() -> dict:
    """Quantiles of `amount` and `time_since_prev_txn_same_entity`, per
    source_dataset, computed from legitimate (is_fraud == 0) rows only --
    an attack should look like it belongs to the real distribution it's
    impersonating, not like an out-of-range outlier by construction.
    """
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(
            f"{FEATURES_PATH} not found. Run backend/defend/features/build_features.py first."
        )
    cols = ["amount", "time_since_prev_txn_same_entity", "source_dataset", "is_fraud"]
    df = pd.read_parquet(FEATURES_PATH, columns=cols)
    legit = df[df["is_fraud"] == 0]

    stats = {}
    for source in legit["source_dataset"].unique():
        subset = legit[legit["source_dataset"] == source]
        amount = subset["amount"].dropna()
        gap = subset.loc[subset["time_since_prev_txn_same_entity"] > 0, "time_since_prev_txn_same_entity"].dropna()

        stats[str(source)] = {
            "amount": {
                "min": float(amount.min()), "p25": float(amount.quantile(0.25)),
                "p50": float(amount.quantile(0.50)), "p75": float(amount.quantile(0.75)),
                "p99": float(amount.quantile(0.99)),
            },
            "gap": {
                "p10": float(gap.quantile(0.10)), "p25": float(gap.quantile(0.25)),
                "p50": float(gap.quantile(0.50)), "p75": float(gap.quantile(0.75)),
                "p90": float(gap.quantile(0.90)),
            } if len(gap) else {"p10": 60.0, "p25": 300.0, "p50": 3600.0, "p75": 21600.0, "p90": 86400.0},
        }
    return stats


def load_reference_stats(force_recompute: bool = False) -> dict:
    if not force_recompute and REFERENCE_STATS_PATH.exists():
        return json.loads(REFERENCE_STATS_PATH.read_text())
    stats = compute_reference_stats()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_STATS_PATH.write_text(json.dumps(stats, indent=2))
    return stats


def _amount_range(level: str, amount_stats: dict) -> tuple[float, float]:
    a = amount_stats
    if level == "low":
        return (max(a["min"], 1.0), a["p25"])
    if level == "high":
        return (a["p75"], max(a["p99"], a["p75"] * 1.5))
    return (a["p25"], a["p75"])  # mid / normal


def _gap_range(level: str, gap_stats: dict) -> tuple[float, float]:
    g = gap_stats
    if level == "high":  # high velocity == short gaps
        return (1.0, max(g["p10"], 2.0))
    if level == "low":  # low velocity == long gaps
        return (g["p90"], g["p90"] * 2)
    if level == "moderate":
        return (g["p25"], g["p50"])
    return (g["p25"], g["p75"])  # normal


def resolve_params(family: str, combo: dict, source_dataset: str, stats: dict) -> dict:
    """Combo (qualitative levels) + reference stats -> a concrete spec dict
    that the artifact generators sample actual transaction values from.
    """
    if family not in DEFAULT_PARAMS:
        raise KeyError(f"No mutation logic for family {family!r}")
    params = {**DEFAULT_PARAMS[family], **combo}
    s = stats[source_dataset]
    spec = {"family": family, "source_dataset": source_dataset, "raw_combo": combo, "resolved_levels": params}

    if family == "transaction_fraud":
        spec["amount_range"] = _amount_range(params["amount"], s["amount"])
        spec["gap_range"] = _gap_range(params["velocity"], s["gap"])
        spec["merchant_unusual"] = params["merchant_category"] in ("mismatch", "new")
        spec["hour_range"] = (0, 5) if params["time_of_day"] == "off_hours" else (6, 22)
        spec["n_transactions"] = 3 if params["velocity"] in ("high", "moderate") else 1

    elif family == "account_takeover":
        spec["device_is_new"] = params["device"] == "new"
        spec["location_is_trusted"] = params["location"] == "trusted"
        spec["beneficiary_changed"] = bool(params.get("beneficiary_change", False))
        spec["gradual_ramp"] = params["velocity"] == "gradual_ramp"
        spec["gap_range"] = _gap_range("normal" if spec["gradual_ramp"] else params["velocity"], s["gap"])
        spec["amount_range"] = _amount_range("mid", s["amount"])
        spec["n_transactions"] = 4

    elif family == "synthetic_identity":
        slow_burn = "relationship_building" in str(params["behavior_pattern"])
        spec["account_age_days_range"] = (0, 30) if params["account_age"] == "low" else (90, 365)
        spec["device_history_count_range"] = (0, 2) if params["device_history"] == "limited" else (3, 10)
        spec["behavior_pattern"] = params["behavior_pattern"]
        spec["relationship_count_range"] = (3, 8) if slow_burn else (1, 3)
        spec["amount_range"] = _amount_range("mid", s["amount"])
        spec["gap_range"] = _gap_range("moderate" if slow_burn else "normal", s["gap"])
        spec["n_transactions"] = 6 if slow_burn else 4

    elif family == "mule_network":
        spec["hop_count_range"] = (2, 3) if params["hop_count"] == "2_3" else (4, 7)
        spec["shared_device"] = bool(params["shared_device"])
        spec["timing_irregular"] = params["timing_gaps"] == "long_irregular"
        spec["gap_range"] = _gap_range("high" if params["timing_gaps"] == "short" else "low", s["gap"])
        spec["cash_out"] = bool(params.get("cash_out", True))
        spec["distributed_beneficiaries"] = params.get("beneficiaries") == "distributed"
        spec["amount_range"] = _amount_range("mid", s["amount"])

    return spec
