"""
Task #32 -- shared helper so every eval_*.py script persists real per-case
results into Supabase's `evaluation_runs` / `evaluation_results` tables
(001_core_schema.sql), not just an aggregate metrics.json entry. This is
what the evidence-viewer frontend page reads: one real row per scored
case, with the detector's own score and reasoning trace, matched against
the case's ground truth only in the `actual_label` column here -- exactly
Principle 13's boundary, enforced by construction: this module runs AFTER
a detector's score() has already been called, never before.

fused_risk_score is NOT true multi-signal fusion (Section 6) -- it is the
scoring detector's own score expressed on the 0-100 band so Section 6's
decision-band table can be applied; every row's evidence/model_signals
makes clear which signals contributed. Re-running an eval script creates a
fresh evaluation_runs row each time (not upserted) -- each run is its own
historical record, matching evaluation_runs' own append-only shape.

2026-09-01 -- CALIBRATION BUG, and the guard that now prevents it.

This function used to compute `fused = round(score * 100, 2)` for every
caller, documenting `score (0-1)` but never checking it. Two of the
detectors do not produce probabilities:

  - autoencoder: the score is a RECONSTRUCTION ERROR, unbounded above.
    A real persisted row: autoencoder_score=19.79 -> fused_risk_score 1979.
  - fusion: a weighted mean over xgboost, lightgbm AND that same
    reconstruction error, so it inherits the same unbounded range.

4,574 rows in evaluation_results carry a fused_risk_score above 100, the
largest 26,488.88 on a documented 0-100 scale. Because decision_for()
returns "block" for anything over 80, every one of those cases was
recorded as blocked -- which is the real reason mule_network and
synthetic_identity report exactly 100% recall. That is a saturated scale,
not a flawless defense.

The fix, deliberately NOT a rescale: there is no honest way to convert an
unbounded reconstruction error into a 0-100 risk band after the fact --
any mapping (min-max over this run, threshold-anchored, logistic) would be
a number this project invented rather than measured. So an uncalibrated
detector now writes fused_risk_score = NULL and a binary decision taken at
its own calibrated threshold, with the raw score preserved in
model_signals and evidence. A missing score is honest; a fabricated band
is not. Callers declare this per run via score_is_probability.

A caller that claims score_is_probability while passing a value outside
[0, 1] now raises instead of silently multiplying by 100 -- the silence is
what let this run for weeks.
"""

from datetime import datetime, timezone

from defend.fusion import decision_for as _decision_for  # noqa: E402  -- Section 6 decision bands, single source (defend/fusion.py)


# Detectors whose score() is a calibrated probability in [0, 1] and can
# therefore be placed on the 0-100 risk band directly. Anything not listed
# here must pass score_is_probability=False; the default is True so a new
# probability-producing detector needs no ceremony, while an unbounded one
# fails loudly on the range check below rather than silently corrupting a
# scale.
PROBABILITY_SCORED_MODELS = frozenset({
    "xgboost", "lightgbm", "phishing_classifier",
    "voice_spoof_detector", "document_consistency_detector", "video_kyc_detector",
})


def record_run_and_results(
    client, run_type: str, model_name: str, cases: list, batch_size: int = 200,
    score_is_probability: bool = None,
) -> str:
    """cases: list of dicts with keys case_id, score, threshold,
    is_fraud (bool), evidence (list[str]). Creates one evaluation_runs row
    and one evaluation_results row per case. Returns the new run_id.

    score_is_probability: whether `score` is a calibrated probability in
    [0, 1]. Defaults to membership of PROBABILITY_SCORED_MODELS. When
    False, fused_risk_score is written as NULL and `decision` is the real
    binary outcome at the detector's own threshold -- see the module
    docstring for why no rescale is applied instead."""
    if score_is_probability is None:
        score_is_probability = model_name in PROBABILITY_SCORED_MODELS
    now = datetime.now(timezone.utc).isoformat()
    run_resp = client.table("evaluation_runs").insert({
        "run_type": run_type,
        "config": {"model": model_name, "n_cases": len(cases)},
        "status": "completed",
        "started_at": now,
        "finished_at": now,
    }).execute()
    run_id = run_resp.data[0]["id"]

    rows = []
    for c in cases:
        score = float(c["score"])
        predicted_fraud = score >= c["threshold"]

        if score_is_probability:
            if not 0.0 <= score <= 1.0:
                raise ValueError(
                    f"{model_name} declared score_is_probability but case {c['case_id']} scored "
                    f"{score!r}, outside [0, 1]. Either the detector is not probability-calibrated "
                    "(pass score_is_probability=False) or its scoring path is wrong. Refusing to "
                    "multiply this by 100 -- doing exactly that is what put 4,574 rows with "
                    "fused_risk_score up to 26,488 on a 0-100 scale into this table."
                )
            fused = round(score * 100, 2)
            decision = _decision_for(fused)
        else:
            # No honest mapping from an unbounded score onto the 0-100 band
            # exists after the fact, so none is invented: the score column
            # is left NULL and the decision records what the detector
            # really did at its calibrated threshold, which is binary.
            fused = None
            decision = "block" if predicted_fraud else "approve"

        evidence = list(c.get("evidence", []))
        if not score_is_probability:
            evidence.append(
                f"raw {model_name} score {score:.4f} vs calibrated threshold {c['threshold']:.4f} "
                "-- not a probability, so no 0-100 risk band is reported for this case"
            )

        rows.append({
            "run_id": run_id,
            "case_id": c["case_id"],
            "model_signals": [{"model": model_name, "score": score}],
            "fused_risk_score": fused,
            "decision": decision,
            # NOTE: `detected` means the harness got this case RIGHT, not
            # that it was flagged as fraud -- for a legitimate case, being
            # let through is "detected". Named for the frontend's
            # caught/missed framing; see liveCases.js's outcomeOf().
            "detected": bool(predicted_fraud == c["is_fraud"]),
            "actual_label": "fraud" if c["is_fraud"] else "legit",
            "evidence": evidence,
        })

    for i in range(0, len(rows), batch_size):
        client.table("evaluation_results").insert(rows[i:i + batch_size]).execute()

    return run_id
