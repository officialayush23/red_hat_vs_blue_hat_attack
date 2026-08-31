"""
Section 8 steps 5-6 (docs/TECHNICAL_SPEC.md) -- the adaptive mutation
loop, built for real 2026-08-30. Step 4 (evaluation/run_adversarial_eval.py)
is what makes this possible: its per-model, per-family recall numbers are
what step 5 reads to find a real weakness, not an assumed one.

Deliberately targets the WEAKEST INDIVIDUAL MODEL's per-family recall, not
the fused score's per-family recall (which showed 1.0 everywhere in
fusion_adversarial_eval) -- see docs/EVALUATION_RESULTS.md's interpretation
note. Fusion corroborating away Autoencoder's individual weakness on
transaction_fraud (recall 0.8242) doesn't mean that weakness stopped
existing; it means XGBoost/LightGBM happened to cover for it on this
specific held-out combination. A harder attack could evade more than one
signal at once, and that has never actually been tested. Targeting the
individual weak model is the honest choice.

This is the Principle 9 rule-based fallback: fully deterministic, no LLM
call, so the loop works with Task #35's LLM strategist disabled or not yet
built. propose_next_combination()'s heuristic is intentionally simple, not
clever -- docs/AGENTIC_CONTRACT.md Section 1 defines the JSON shape an LLM
strategist will eventually produce in its place.

Step 6's case generation calls the EXISTING generator code
(generate.mutation_engine.resolve_params + generate.artifact_generators),
the same functions generate/inject_attacks.py already uses for Stage 4 --
no new generation surface, per Principle 12. New cases are written under
data/generated/attacks/held_out/<family>/weakness_round_2/ and are never
added to attacks_train.parquet -- still held-out, never trained on.

These round-2 cases are also upserted into the real `attack_cases` table
(reusing db/backfill_attack_cases.py's own _load_case() row-shape, not a
second copy of that logic) before evaluation_results rows are written --
evaluation_results.case_id is a foreign key into attack_cases, so skipping
this step would make the Supabase persistence block below fail silently
on every single row. Caught by tracing the FK, not by hitting the error at
runtime.

Writes one weakness_log row per run: the ORIGINAL (before) recall at
discovery time, then updates that same row with followup_run_id once
round 2 has been scored -- the before/after delta is then a real query
(weakness_log.recall vs. followup_run_id's evaluation_results), not two
independently asserted numbers, per AGENTIC_CONTRACT.md Section 1.

Usage:
    python backend/evaluation/adaptive_weakness_round.py
    python backend/evaluation/adaptive_weakness_round.py --n-cases 200
"""

import argparse
import json
import random
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import gc  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from defend.train.dataset import load_training_pool, train_val_split  # noqa: E402
from defend.train.preprocessor import TabularPreprocessor  # noqa: E402
from evaluation.metrics import compute_binary_metrics, record_result  # noqa: E402
from evaluation.run_adversarial_eval import (  # noqa: E402
    _load_frozen_autoencoder, _load_frozen_lightgbm, _load_frozen_xgboost,
)
from evaluation.split_policy import FAMILIES  # noqa: E402
from evaluation.supabase_results import record_run_and_results  # noqa: E402
from evaluation.llm_strategist import propose_next_combination_llm  # noqa: E402
from generate import mutation_engine  # noqa: E402
from generate.artifact_generators import ring_gen, transaction_gen  # noqa: E402
from generate.inject_attacks import CANONICAL_ROW_KEYS, EXTRA_COLUMNS, _graph_features_for_case  # noqa: E402
from generate.validators import validate_case  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
GENERATED_DIR = REPO_ROOT / "data" / "generated" / "attacks"
MODELS_DIR = BACKEND_DIR / "defend" / "models"
RESULTS_JSON = MODELS_DIR / "metrics.json"
RESULTS_MD = REPO_ROOT / "docs" / "EVALUATION_RESULTS.md"
PREPROCESSOR_PATH = MODELS_DIR / "tabular_preprocessor.joblib"

TABULAR_MODELS = ("xgboost", "lightgbm", "autoencoder")


def identify_weakest() -> dict:
    """Step 5: the lowest per-family recall across every individual
    tabular model's real Stage-7 evaluation."""
    data = json.loads(RESULTS_JSON.read_text())
    worst = None
    for model in TABULAR_MODELS:
        key = f"{model}_adversarial_eval"
        if key not in data:
            continue
        for family, recall in data[key].get("per_family_recall", {}).items():
            if worst is None or recall < worst["recall"]:
                worst = {"model": model, "attack_family": family, "recall": float(recall)}
    if worst is None:
        raise RuntimeError("No *_adversarial_eval entries in metrics.json -- run run_adversarial_eval.py first.")
    return worst


def _current_held_out_combo(family: str) -> dict:
    combos = FAMILIES[family]["held_out_only"]
    if len(combos) != 1:
        raise NotImplementedError(
            f"{family} has {len(combos)} held-out combinations -- this simple rule-based fallback "
            f"assumes exactly one (true for all four Phase 1 families as of 2026-08-30). Extend "
            f"propose_next_combination() to pick among several before using this on a family with more."
        )
    return dict(combos[0])


def propose_next_combination(family: str, current_combo: dict) -> tuple[dict, list[str]]:
    """Step 6, Principle 9 rule-based fallback -- see module docstring.
    Strips the combo's most numerically-obvious tell (time_of_day or
    velocity) toward 'normal' while leaving its categorical/structural
    fraud signal (e.g. merchant_category=new) intact -- testing whether
    numeric camouflage plus a retained structural signal evades a
    reconstruction-error-based model even further than the original
    combination already does."""
    new_combo = dict(current_combo)
    reasons = []
    if new_combo.get("time_of_day") == "off_hours":
        new_combo["time_of_day"] = "normal"
        reasons.append("removed the off-hours timing tell (time_of_day: off_hours -> normal) -- tests "
                        "whether the structural/categorical fraud signal alone, without an obvious "
                        "numeric-time anomaly, evades detection even more")
    elif new_combo.get("velocity") in ("moderate", "high"):
        new_combo["velocity"] = "normal"
        reasons.append("normalized transaction velocity -- removes a second numeric anomaly signal")
    else:
        reasons.append("no further numeric camouflage available on this combo's dimensions with this "
                        "simple heuristic -- re-running the same combination at a larger sample size instead")
    return new_combo, reasons


def generate_round_2_cases(family: str, combo: dict, n: int, seed: int) -> tuple[list[dict], pd.DataFrame, Path]:
    stats = mutation_engine.load_reference_stats()
    rng = random.Random(seed)
    out_dir = GENERATED_DIR / "held_out" / family / "weakness_round_2"
    out_dir.mkdir(parents=True, exist_ok=True)

    cases, flat_rows = [], []
    for _ in range(n):
        source_dataset = "paysim" if family == "mule_network" else rng.choice(["paysim", "ieee_cis"])
        spec = mutation_engine.resolve_params(family, combo, source_dataset, stats)
        case = (ring_gen.generate_case("held_out", spec, rng) if family == "mule_network"
                else transaction_gen.generate_case(family, "held_out", spec, rng))
        validate_case(case)
        cases.append(case)
        (out_dir / f"{case['case_id']}.json").write_text(json.dumps(case, indent=2))
        # Bug #6 (found via `ADAPTIVE ROUND FAILED: 'graph_src_out_degree'`):
        # this loop used to build flat rows independently of
        # inject_attacks.py's own _flatten_case(), predating the round-4
        # graph-topology feature work -- it never added the 7 graph_*
        # columns, so any model whose training-time prep_spec/vocabulary now
        # includes them (the Autoencoder's transform() indexes df[c] for
        # every spec["numeric_cols"] with no missing-column guard, unlike
        # preprocessor.py's transform_tree()) hard-crashed the moment this
        # generated a round on ANY family. Fixed by calling the SAME
        # _graph_features_for_case() inject_attacks.py already uses --
        # real graph values for mule_network (its cases carry a real
        # networkx graph), all-None (NaN) for every other family, exactly
        # matching _flatten_case()'s own behavior. Same underlying
        # function, no second implementation, per this file's own Principle
        # 12 discipline -- it just wasn't wired to this specific column
        # group.
        graph_feats = _graph_features_for_case(case)
        for row, gfeat in zip(case["transaction_sequence"], graph_feats):
            flat = {k: row.get(k) for k in CANONICAL_ROW_KEYS}
            flat["case_id"] = case["case_id"]
            flat["attack_family"] = case["attack_family"]
            flat["split_portion"] = case["split_portion"]
            extra = case.get("extra_fields", {})
            for k in EXTRA_COLUMNS:
                flat[k] = extra.get(k)
            flat.update(gfeat)
            flat_rows.append(flat)
    return cases, pd.DataFrame(flat_rows), out_dir


def score_with_model(model_name: str, tree_X: pd.DataFrame, raw_df: pd.DataFrame) -> np.ndarray:
    if model_name == "xgboost":
        return _load_frozen_xgboost().predict_proba(tree_X)[:, 1]
    if model_name == "lightgbm":
        return _load_frozen_lightgbm().predict(tree_X)
    if model_name == "autoencoder":
        score_fn, ok = _load_frozen_autoencoder()
        if not ok:
            raise RuntimeError("PyTorch not available in this environment -- cannot score with autoencoder.")
        return score_fn(raw_df)
    raise ValueError(f"Unknown model: {model_name}")


def _frozen_threshold(model_name: str) -> float:
    data = json.loads(RESULTS_JSON.read_text())
    return float(data[model_name]["decision_threshold"])


def _fetch_already_tried_combinations(family: str) -> list:
    """Best-effort: prior weakness_log.combination values for this family,
    so the LLM strategist doesn't propose a repeat (AGENTIC_CONTRACT.md
    Section 1's already_tried_combinations field). Never fatal -- an empty
    list here just means the LLM has less context, not a broken run."""
    try:
        from db.supabase_client import get_service_client
        client = get_service_client()
        resp = (client.table("weakness_log")
                .select("combination")
                .eq("attack_family", family)
                .order("identified_at", desc=True)
                .limit(20)
                .execute())
        return [row["combination"] for row in resp.data if row.get("combination")]
    except Exception:
        return []


def _find_source_run_id(client, model_name: str) -> str | None:
    """Best-effort lookup of the evaluation_runs row that originally
    discovered this weakness (Stage 7's adversarial_held_out run for this
    model), so weakness_log.run_id points at real evidence rather than
    being left null. Not fatal if it can't be found."""
    try:
        resp = (client.table("evaluation_runs")
                .select("id, config, started_at")
                .eq("run_type", "adversarial_held_out")
                .order("started_at", desc=True)
                .limit(20)
                .execute())
        for row in resp.data:
            if row.get("config", {}).get("model") == model_name:
                return row["id"]
    except Exception:
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-cases", type=int, default=400, help="Round-2 cases to generate (default 400, matching Stage 4's original per-family count).")
    parser.add_argument("--seed", type=int, default=43, help="Different from Stage 4's seed=42 on purpose -- this is a genuinely new sample, not a re-derivation of the same cases.")
    args = parser.parse_args()

    weakness = identify_weakest()
    print(f"Step 5 -- weakest signal: {weakness['model']} / {weakness['attack_family']} "
          f"(recall={weakness['recall']:.4f})")

    current_combo = _current_held_out_combo(weakness["attack_family"])
    print(f"Step 6 -- current combo: {current_combo}")

    already_tried = _fetch_already_tried_combinations(weakness["attack_family"])
    llm_result = propose_next_combination_llm(weakness["attack_family"], current_combo, weakness, already_tried)
    if llm_result is not None:
        new_combo, reasons, recommended_action, severity = llm_result
        source = "llm"
        print("Step 6 -- LLM strategist proposed a validated combination.")
    else:
        new_combo, reasons = propose_next_combination(weakness["attack_family"], current_combo)
        recommended_action = f"Harden {weakness['attack_family']} generation toward: {new_combo}"
        severity = "high" if weakness["recall"] < 0.85 else ("medium" if weakness["recall"] < 0.95 else "low")
        source = "rule_based"
        print("Step 6 -- LLM strategist unavailable or its proposal failed validation; "
              "using the Principle 9 rule-based fallback.")
    print(f"Step 6 -- proposed combo ({source}): {new_combo}")
    for r in reasons:
        print(f"  reason: {r}")

    print(f"\nGenerating {args.n_cases} round-2 cases (seed={args.seed})...")
    cases, round2_df, out_dir = generate_round_2_cases(weakness["attack_family"], new_combo, args.n_cases, args.seed)
    print(f"  {len(round2_df):,} rows across {round2_df['case_id'].nunique():,} cases, "
          f"written under data/generated/attacks/held_out/{weakness['attack_family']}/weakness_round_2/")

    if not PREPROCESSOR_PATH.exists():
        raise FileNotFoundError(f"{PREPROCESSOR_PATH} not found. Run defend/train/fit_preprocessor.py first.")
    prep = TabularPreprocessor.load(PREPROCESSOR_PATH)
    round2_X = prep.transform_tree(round2_df)

    print("\nLoading Stage-5 training pool for the legitimate comparison set (same discipline as run_adversarial_eval.py)...")
    pool = load_training_pool()
    X_train, X_val, y_train, y_val = train_val_split(pool)
    legit_X = X_val[(y_val == 0).to_numpy()].copy()
    del pool, X_train, y_train, X_val, y_val
    gc.collect()

    threshold = _frozen_threshold(weakness["model"])
    legit_scores = score_with_model(weakness["model"], legit_X, legit_X)
    round2_scores = score_with_model(weakness["model"], round2_X, round2_df)

    y_true = np.concatenate([np.zeros(len(legit_scores)), np.ones(len(round2_scores))])
    y_score = np.concatenate([legit_scores, round2_scores])
    after_metrics = compute_binary_metrics(y_true, y_score, threshold=threshold)
    print(f"\nAfter (round 2, {weakness['model']} on the hardened combo): "
          f"recall={after_metrics['recall']:.4f} precision={after_metrics['precision']:.4f} "
          f"(before was {weakness['recall']:.4f})")

    record_result(
        RESULTS_JSON, f"{weakness['model']}_weakness_round2_{weakness['attack_family']}", after_metrics,
        extra={
            "before_recall": weakness["recall"], "after_recall": after_metrics["recall"],
            "delta": after_metrics["recall"] - weakness["recall"],
            "original_combo": current_combo, "hardened_combo": new_combo, "reasons": reasons,
            "note": "Section 8 step 6 -- targeted second round on the weakest signal found in step 5.",
        },
    )
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_MD, "a") as f:
        f.write(
            f"\n## Section 8 step 6 -- targeted mutation round: {weakness['model']} / {weakness['attack_family']}\n\n"
            f"- Before (step 5, original held-out combo): recall={weakness['recall']:.4f}\n"
            f"- Original combo: {current_combo}\n"
            f"- Hardened combo: {new_combo}\n"
            f"- Reason: {'; '.join(reasons)}\n"
            f"- After (round 2, {len(round2_df):,} new rows / {round2_df['case_id'].nunique():,} cases): "
            f"recall={after_metrics['recall']:.4f}, precision={after_metrics['precision']:.4f}, "
            f"roc_auc={after_metrics['roc_auc']:.4f}\n"
            f"- Delta: {after_metrics['recall'] - weakness['recall']:+.4f}\n"
        )

    try:
        from db.backfill_attack_cases import _load_case
        from db.supabase_client import get_service_client
        client = get_service_client()

        # evaluation_results.case_id is a foreign key into attack_cases -- these
        # round-2 cases are brand new and were never backfilled, so they must be
        # upserted first or every evaluation_results insert below fails on the FK.
        # Reuses backfill_attack_cases.py's own row-shape function rather than
        # re-deriving it, per Principle 12.
        case_rows = [_load_case(out_dir / f"{c['case_id']}.json") for c in cases]
        client.table("attack_cases").upsert(case_rows, on_conflict="id").execute()
        print(f"\nSupabase: upserted {len(case_rows)} round-2 attack_cases rows.")

        case_scores = round2_df[["case_id"]].copy()
        case_scores["score"] = round2_scores
        agg = case_scores.groupby("case_id", as_index=False)["score"].max()
        followup_cases = [
            {"case_id": row.case_id, "score": float(row.score), "threshold": threshold,
             "is_fraud": True, "evidence": [f"{weakness['model']}_score={row.score:.4f} (weakness_round_2)"]}
            for row in agg.itertuples()
        ]
        followup_run_id = record_run_and_results(
            client, run_type="targeted_reeval", model_name=weakness["model"], cases=followup_cases,
        )
        print(f"Supabase: followup evaluation_run {followup_run_id} (targeted_reeval, {len(followup_cases)} cases)")

        source_run_id = _find_source_run_id(client, weakness["model"])
        insert_resp = client.table("weakness_log").insert({
            "run_id": source_run_id,
            "attack_family": weakness["attack_family"],
            "combination": current_combo,
            "recall": weakness["recall"],
            "source": source,
            "reasons": reasons,
            "recommended_action": recommended_action,
            "severity": severity,
            "next_strategy": {
                "attack_family": weakness["attack_family"], "combination": new_combo,
                "generator": "generate/inject_attacks.py (via adaptive_weakness_round.py's direct call)",
                "n_cases": args.n_cases,
            },
            "followup_run_id": followup_run_id,
            "changes": reasons,
        }).execute()
        weakness_log_id = insert_resp.data[0]["id"]
        print(f"Supabase: weakness_log row {weakness_log_id} written, followup_run_id={followup_run_id} "
              f"-- before/after delta is now a real query, not two asserted numbers.")
    except Exception as exc:
        print(f"Supabase persistence skipped (non-fatal, real local numbers above stand regardless): {exc}", file=sys.stderr)

    print(f"\nDone. Recorded to {RESULTS_JSON} and {RESULTS_MD}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nADAPTIVE ROUND FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
