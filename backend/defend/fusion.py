"""
Section 6 (docs/TECHNICAL_SPEC.md) -- the real fusion layer. Until
2026-08-30 this didn't exist as code: evaluation/supabase_results.py's own
docstring says fused_risk_score was "the single detector's own score
scaled to the 0-100 band," not true multi-signal fusion. This module is
what makes that real for the four tabular attack families
(transaction_fraud, account_takeover, synthetic_identity, mule_network),
where XGBoost, LightGBM, and Autoencoder all score the same transaction.

FUSION_WEIGHTS are read from backend/defend/models/metrics.json's real
Stage-5 validation ROC-AUC per model -- not hand-picked, not the spec's
"equal-ish" placeholder forever. ROC-AUC (not the threshold-dependent
recall/precision numbers) is the right thing to weight by here: it
reflects each model's ranking quality independent of any one operating
threshold, which is what a weighted-average fusion actually consumes.
Computed once at import time from a real file, auditable by reading that
file, not asserted.

Decision bands (0-30 approve / 31-60 review / 61-80 challenge / 81-100
block) live here now as the single canonical source -- previously
duplicated in evaluation/supabase_results.py, which now imports from here.

Behavioral corroboration (Section 6 / Principle 14, Customer Universe's
behavior_baseline -- see docs/TECHNICAL_SPEC.md Section 4b-i) is
implemented as a pure function below, unit-testable and ready to use.

2026-08-31 (Phase 2.5): attack_cases.customer_id linkage, previously None
for every generated case, is now wired -- generate/inject_attacks.py
assigns a customer round-robin per case across all four tabular families,
and account_takeover specifically also derives country/channel from that
customer's own behavior_baseline (artifact_generators/transaction_gen.py's
_behavioral_country_channel()) so behavioral_adjustment() below has real
fields to compare against, not just a customer_id with nothing to check.
This still needs data regenerated AFTER this change (old on-disk cases and
attacks_*.parquet predate it and have customer_id=None) before it's
evidence-gated -- see evaluation/eval_behavioral_adjustment.py, the
Principle 11 gate for exactly this function.
"""

import json
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent / "models"
METRICS_PATH = MODELS_DIR / "metrics.json"

TABULAR_MODELS = ("xgboost", "lightgbm", "autoencoder")

# Section 6 decision bands -- canonical source (evaluation/supabase_results.py imports this).
DECISION_BANDS = ((30, "approve"), (60, "review"), (80, "challenge"), (100, "block"))


def decision_for(fused_score_0_100: float) -> str:
    for ceiling, decision in DECISION_BANDS:
        if fused_score_0_100 <= ceiling:
            return decision
    return "block"


def compute_fusion_weights(metrics_path: Path = METRICS_PATH) -> dict:
    """Weight per tabular model = its Stage-5 validation ROC-AUC, normalized
    to sum to 1. Read fresh from metrics.json every call (not cached at
    import time) so a re-run of train_xgboost.py/train_lightgbm.py/
    train_autoencoder.py is automatically reflected -- this file is the
    single source of truth for what "how much do we trust this model"
    means, and it should never silently go stale against a retrained model."""
    data = json.loads(Path(metrics_path).read_text())
    raw = {}
    for m in TABULAR_MODELS:
        if m not in data:
            raise KeyError(f"metrics.json has no entry for '{m}' -- run its train_*.py script first.")
        roc_auc = data[m]["metrics"]["roc_auc"]
        if roc_auc is None:
            raise ValueError(f"metrics.json's '{m}' entry has no roc_auc recorded.")
        raw[m] = float(roc_auc)
    total = sum(raw.values())
    return {m: v / total for m, v in raw.items()}


def fuse_tabular_scores(scores: dict, weights: dict = None) -> float:
    """scores: {model_name: raw probability in [0,1]} -- need not include
    every TABULAR_MODELS key; missing signals are excluded and remaining
    weights renormalized (a live request might not always run all three,
    e.g. if Autoencoder inference is unavailable). Returns a 0-100 fused
    risk score, a weighted average -- not a re-derived threshold or a
    max/min rule, per Section 6's "weighted-ish" starting point, now
    grounded in real per-model ROC-AUC rather than a guess."""
    if not scores:
        raise ValueError("fuse_tabular_scores called with no signals")
    weights = weights or compute_fusion_weights()
    active = {m: w for m, w in weights.items() if m in scores}
    if not active:
        raise ValueError(f"None of {list(scores)} are known tabular models ({TABULAR_MODELS})")
    norm = sum(active.values())
    fused = sum(scores[m] * (w / norm) for m, w in active.items())
    return round(fused * 100, 2)


def behavioral_adjustment(fused_score_0_100: float, transaction: dict, behavior_baseline: dict):
    """Section 6 / Principle 14: corroborate or discount a fused score using
    the customer's own behavior_baseline (generate/synthetic_customers.py's
    _generate_behavior_baseline() -- normal_amount_range, occasional_*
    ranges for country/channel/login_hour, etc). Returns (adjusted_score,
    reason_string).

    Deliberately conservative and explainable, not a learned model: a
    transaction inside the customer's own normal_* ranges is DISCOUNTED
    (a borderline detector signal is more likely a false positive when it
    matches this specific customer's known-normal behavior); a
    transaction outside BOTH normal_* and occasional_* ranges on 2+
    dimensions is CORROBORATED (boosted) -- otherwise the score passes
    through unchanged. NOT yet run against real evaluation data -- see
    this module's docstring; ready for use once attack_cases.customer_id
    linkage exists (Phase 2.5)."""
    if not behavior_baseline:
        return fused_score_0_100, "no behavior_baseline available for this customer -- score unadjusted"

    outside_count = 0
    inside_normal_count = 0
    checked = 0

    amount = transaction.get("amount")
    normal_amt = behavior_baseline.get("normal_amount_range")
    occ_amt = behavior_baseline.get("occasional_amount_range")
    if amount is not None and normal_amt and occ_amt:
        checked += 1
        if normal_amt[0] <= amount <= normal_amt[1]:
            inside_normal_count += 1
        elif not (occ_amt[0] <= amount <= occ_amt[1]):
            outside_count += 1

    country = transaction.get("country")
    normal_countries = behavior_baseline.get("normal_countries")
    occ_countries = behavior_baseline.get("occasional_countries")
    if country is not None and normal_countries is not None:
        checked += 1
        if country in normal_countries:
            inside_normal_count += 1
        elif occ_countries is None or country not in occ_countries:
            outside_count += 1

    channel = transaction.get("channel")
    normal_channels = behavior_baseline.get("normal_channels")
    occ_channels = behavior_baseline.get("occasional_channels")
    if channel is not None and normal_channels is not None:
        checked += 1
        if channel in normal_channels:
            inside_normal_count += 1
        elif occ_channels is None or channel not in occ_channels:
            outside_count += 1

    if checked == 0:
        return fused_score_0_100, "transaction missing all comparable fields -- score unadjusted"

    if outside_count >= 2:
        adjusted = min(100.0, fused_score_0_100 * 1.15)
        return round(adjusted, 2), f"corroborated: {outside_count}/{checked} dimensions outside both normal and occasional ranges"
    if inside_normal_count == checked:
        adjusted = fused_score_0_100 * 0.7
        return round(adjusted, 2), f"discounted: all {checked} comparable dimensions match this customer's normal behavior"
    return fused_score_0_100, f"no strong corroboration or discount ({inside_normal_count} normal, {outside_count} outside, {checked} checked)"
