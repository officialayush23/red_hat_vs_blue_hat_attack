"""
Principle 11 evidence gate for defend/fusion.py's behavioral_adjustment()
-- Section 6 / Principle 14's Customer Universe corroboration layer, which
existed as real, unit-testable code since 2026-08-30 but had never been run
against real evaluation data (fusion.py's own docstring said so plainly:
"attack_cases.customer_id linkage is still None for every generated case").

2026-08-31 (Phase 2.5) closed that gap: generate/inject_attacks.py now
assigns a customer (round-robin, generate/synthetic_customers.py's roster)
to every generated case, and account_takeover specifically also derives
country/channel from that customer's own behavior_baseline
(artifact_generators/transaction_gen.py's _behavioral_country_channel()).
This script is what actually evidence-gates the result: does applying
behavioral_adjustment() on top of the real fused tabular score change
precision/recall/FPR on account_takeover, and in which direction.

Scope: account_takeover ONLY (held-out split). That's the one family this
round's generator work gave real country/channel signal to -- transaction_
fraud/synthetic_identity/mule_network cases get a customer_id too (for
Supabase identity linkage generally) but no behavioral deviation fields,
so behavioral_adjustment() would just no-op (pass-through) on them; running
this eval there would silently record "no effect" for the wrong reason
(no signal, not "the adjustment doesn't help") -- excluded to keep this
result honest about what it's actually testing.

Design, mirroring run_adversarial_eval.py's held-out harness:
  - fraud rows: attacks_held_out.parquet's account_takeover rows (frozen
    XGBoost/LightGBM never trained on these combinations -- see split_
    policy.py).
  - legit rows: the SAME Stage-5 validation-split legit rows run_
    adversarial_eval.py uses. These carry no customer_id at all (they're
    real PaySim/IEEE-CIS rows, not synthetic identities) -- behavioral_
    adjustment() correctly no-ops on all of them (see its own "no
    behavior_baseline available" early return). This is not a limitation
    of this script; it's the honest shape of the test: behavioral
    corroboration can only ever help distinguish TP from FN among
    customer-linked fraud, it was never going to touch the legit side's
    FPR by construction, and this script doesn't pretend otherwise.
  - base_score: fuse_tabular_scores({"xgboost": ..., "lightgbm": ...}) --
    real production fusion (defend/fusion.py), NOT a single model. Autoencoder
    excluded here for the same practical reason run_adversarial_eval.py
    offers --skip-autoencoder -- it needs PyTorch, this is otherwise a fast
    tabular-only check.
  - adjusted_score: fusion.behavioral_adjustment(base_score, transaction,
    behavior_baseline) using the CLAIMED customer's own real baseline
    (generate/synthetic_customers.py's roster, loaded fresh, never the
    ground-truth "was this actually fraud" label -- Principle 13 still
    applies to this post-hoc layer the same as every detector).
  - Both baseline and adjusted metrics computed at the SAME fixed
    threshold (30.0 -- defend/fusion.py's own "approve" band ceiling, the
    real production decision boundary, not a threshold picked after the
    fact to flatter either number) so the comparison is apples-to-apples:
    same operating point, only the score changed.

Two results recorded to metrics.json (both readable by evaluation/
run_all_evaluations.py's scoreboard() like any other entry):
  behavioral_adjustment_baseline   -- fused score alone
  behavioral_adjustment_adjusted   -- fused score + behavioral_adjustment()
Compare their recall/precision/FPR directly; the delta IS the finding.

NOT executable in the cloud sandbox this was authored in -- depends on
xgboost/lightgbm and data/processed/attacks_held_out.parquet regenerated
AFTER the 2026-08-31 inject_attacks.py change (older parquet files predate
customer_id/country/channel and will show 0 linked rows -- this script
detects that and says so plainly rather than reporting a false "no effect").

Usage:
    python backend/evaluation/eval_behavioral_adjustment.py
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import gc  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from defend.fusion import DECISION_BANDS, behavioral_adjustment, fuse_tabular_scores  # noqa: E402
from defend.train.dataset import load_training_pool, train_val_split  # noqa: E402
from defend.train.preprocessor import TabularPreprocessor  # noqa: E402
from evaluation.metrics import compute_binary_metrics, record_result  # noqa: E402
from generate.synthetic_customers import load_roster  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
HELD_OUT_PATH = PROCESSED_DIR / "attacks_held_out.parquet"
MODELS_DIR = BACKEND_DIR / "defend" / "models"
RESULTS_JSON = MODELS_DIR / "metrics.json"
RESULTS_MD = REPO_ROOT / "docs" / "EVALUATION_RESULTS.md"
PREPROCESSOR_PATH = MODELS_DIR / "tabular_preprocessor.joblib"

# defend/fusion.py's own "approve" band ceiling -- the real production
# decision boundary (anything above this is review/challenge/block, i.e.
# "flagged"), not a threshold fit to this evaluation after the fact.
THRESHOLD = float(DECISION_BANDS[0][0])


def _load_frozen_xgboost():
    import xgboost as xgb
    model = xgb.XGBClassifier(enable_categorical=True, tree_method="hist")
    model.load_model(str(MODELS_DIR / "xgboost.json"))
    return model


def _load_frozen_lightgbm():
    import lightgbm as lgb
    return lgb.Booster(model_file=str(MODELS_DIR / "lightgbm.txt"))


def _append_results_md(baseline: dict, adjusted: dict, n_rows: int, n_linked: int) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS_MD.exists():
        RESULTS_MD.write_text(
            "# Evaluation Results\n\n"
            "Recorded automatically by each training/evaluation script -- do not hand-edit\n"
            "numbers here, re-run the script instead.\n"
        )
    lines = [
        "\n## behavioral_adjustment (defend/fusion.py) -- Principle 11 evidence-gate run, "
        "account_takeover held-out\n",
        f"- Fixed decision threshold: {THRESHOLD:.1f} (defend/fusion.py's own 'approve' band ceiling)",
        f"- n_fraud_rows={n_rows}, of which {n_linked} had a real customer_id + behavior_baseline "
        f"to adjust against ({n_rows - n_linked} had none -- pass through unadjusted)",
        f"- BASELINE  (fused score only):   precision={baseline['precision']:.4f}  "
        f"recall={baseline['recall']:.4f}  fpr={baseline['false_positive_rate']:.4%}",
        f"- ADJUSTED  (+ behavioral_adjustment): precision={adjusted['precision']:.4f}  "
        f"recall={adjusted['recall']:.4f}  fpr={adjusted['false_positive_rate']:.4%}",
        f"- Delta: precision {adjusted['precision'] - baseline['precision']:+.4f}, "
        f"recall {adjusted['recall'] - baseline['recall']:+.4f}, "
        f"fpr {adjusted['false_positive_rate'] - baseline['false_positive_rate']:+.4%}",
    ]
    lines.append("")
    with open(RESULTS_MD, "a") as f:
        f.write("\n".join(lines))


def main() -> None:
    if not HELD_OUT_PATH.exists():
        raise FileNotFoundError(f"{HELD_OUT_PATH} not found. Run generate/inject_attacks.py first.")
    if not PREPROCESSOR_PATH.exists():
        raise FileNotFoundError(f"{PREPROCESSOR_PATH} not found. Run defend/train/fit_preprocessor.py first.")

    print("Loading Stage-5 training pool to derive the legitimate comparison set "
          "(train_val_split's validation portion, seed=42)...")
    pool = load_training_pool()
    X_train, X_val, y_train, y_val = train_val_split(pool)
    legit_idx = (y_val == 0).to_numpy()
    legit_X = X_val[legit_idx].copy()
    print(f"  {len(legit_X):,} legitimate rows available (no customer_id -- behavioral_adjustment "
          f"will correctly no-op on all of them, see this script's module docstring)")
    del pool, X_train, y_train, X_val, y_val
    gc.collect()

    held_out_raw = pd.read_parquet(HELD_OUT_PATH)
    fraud_raw = held_out_raw[held_out_raw["attack_family"] == "account_takeover"].reset_index(drop=True)
    if fraud_raw.empty:
        raise ValueError(
            f"No account_takeover rows in {HELD_OUT_PATH}. Run generate/inject_attacks.py "
            f"(all families, or at least --families account_takeover)."
        )
    n_linked = int(fraud_raw["customer_id"].notna().sum()) if "customer_id" in fraud_raw.columns else 0
    if n_linked == 0:
        raise ValueError(
            f"{HELD_OUT_PATH} has {len(fraud_raw)} account_takeover rows but NONE carry a customer_id "
            f"-- this parquet predates the 2026-08-31 inject_attacks.py change. Re-run "
            f"generate/synthetic_customers.py (if you haven't) then generate/inject_attacks.py to "
            f"regenerate it with real identity linkage, then re-run this script."
        )
    print(f"  {len(fraud_raw):,} account_takeover held-out rows, {n_linked:,} with a real customer_id "
          f"({n_linked / len(fraud_raw):.0%})")

    print("Loading synthetic customer roster...")
    roster_by_id = {c["id"]: c for c in load_roster()}

    prep = TabularPreprocessor.load(PREPROCESSOR_PATH)
    legit_feats = prep.transform_tree(legit_X)
    fraud_feats = prep.transform_tree(fraud_raw)

    print("Scoring with frozen XGBoost + LightGBM...")
    xgb_model = _load_frozen_xgboost()
    lgb_booster = _load_frozen_lightgbm()

    def _fused_scores(feats: pd.DataFrame) -> np.ndarray:
        xgb_p = xgb_model.predict_proba(feats)[:, 1]
        lgb_p = lgb_booster.predict(feats)
        return np.array([fuse_tabular_scores({"xgboost": float(x), "lightgbm": float(l)})
                          for x, l in zip(xgb_p, lgb_p)])

    legit_base_scores = _fused_scores(legit_feats)
    fraud_base_scores = _fused_scores(fraud_feats)

    print("Applying behavioral_adjustment()...")
    legit_adjusted_scores = np.array([
        behavioral_adjustment(score, {"amount": None}, None)[0] for score in legit_base_scores
    ])  # legit rows: no customer_id, always pass-through -- computed anyway for a clean symmetric comparison

    fraud_adjusted_scores = np.empty(len(fraud_raw), dtype="float64")
    n_corroborated = n_discounted = n_unchanged = 0
    for i, row in fraud_raw.iterrows():
        customer = roster_by_id.get(row.get("customer_id"))
        baseline = customer.get("metadata", {}).get("behavior_baseline") if customer else None
        transaction = {"amount": row.get("amount"), "country": row.get("country"), "channel": row.get("channel")}
        adjusted, reason = behavioral_adjustment(float(fraud_base_scores[i]), transaction, baseline)
        fraud_adjusted_scores[i] = adjusted
        if reason.startswith("corroborated"):
            n_corroborated += 1
        elif reason.startswith("discounted"):
            n_discounted += 1
        else:
            n_unchanged += 1
    print(f"  {n_corroborated} corroborated (boosted), {n_discounted} discounted, {n_unchanged} unchanged")

    y_true = np.concatenate([np.zeros(len(legit_base_scores)), np.ones(len(fraud_base_scores))])
    baseline_metrics = compute_binary_metrics(
        y_true, np.concatenate([legit_base_scores, fraud_base_scores]), threshold=THRESHOLD)
    adjusted_metrics = compute_binary_metrics(
        y_true, np.concatenate([legit_adjusted_scores, fraud_adjusted_scores]), threshold=THRESHOLD)

    print(f"\nBASELINE  (fused score only):          {json.dumps(baseline_metrics, indent=2)}")
    print(f"\nADJUSTED  (+ behavioral_adjustment):    {json.dumps(adjusted_metrics, indent=2)}")
    print(f"\nDelta: precision {adjusted_metrics['precision'] - baseline_metrics['precision']:+.4f}, "
          f"recall {adjusted_metrics['recall'] - baseline_metrics['recall']:+.4f}, "
          f"fpr {adjusted_metrics['false_positive_rate'] - baseline_metrics['false_positive_rate']:+.4%}")

    common_extra = {
        "threshold": THRESHOLD, "n_fraud_rows": len(fraud_raw), "n_customer_linked_rows": n_linked,
        "n_legit_rows": len(legit_base_scores),
    }
    record_result(RESULTS_JSON, "behavioral_adjustment_baseline", baseline_metrics, extra={
        **common_extra,
        "note": "fused (XGBoost+LightGBM) score alone, no behavioral corroboration -- Principle 11 "
                "evidence-gate run, account_takeover held-out.",
    })
    record_result(RESULTS_JSON, "behavioral_adjustment_adjusted", adjusted_metrics, extra={
        **common_extra,
        "n_corroborated": n_corroborated, "n_discounted": n_discounted, "n_unchanged": n_unchanged,
        "note": "fused score + defend/fusion.py's behavioral_adjustment() using each case's real "
                "customer_id + behavior_baseline -- Principle 11 evidence-gate run, account_takeover "
                "held-out. Compare against behavioral_adjustment_baseline for the same rows/threshold.",
    })
    _append_results_md(baseline_metrics, adjusted_metrics, len(fraud_raw), n_linked)
    print(f"\nRecorded results to {RESULTS_JSON} and {RESULTS_MD}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nEVAL FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
