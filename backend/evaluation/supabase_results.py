"""
Task #32 -- shared helper so every eval_*.py script persists real per-case
results into Supabase's `evaluation_runs` / `evaluation_results` tables
(001_core_schema.sql), not just an aggregate metrics.json entry. This is
what the evidence-viewer frontend page reads: one real row per scored
case, with the detector's own score and reasoning trace, matched against
the case's ground truth only in the `actual_label` column here -- exactly
Principle 13's boundary, enforced by construction: this module runs AFTER
a detector's score() has already been called, never before.

fused_risk_score is NOT true multi-signal fusion (Section 6) -- that layer
doesn't exist as code yet (#33-36). It's the single detector's own score
scaled to the 0-100 band so the decision-band table in Section 6 can be
applied consistently today; every row's evidence/model_signals makes clear
only one signal contributed. Re-running an eval script re-creates a fresh
evaluation_runs row each time (not upserted) -- each run is its own
historical record, matching evaluation_runs' own append-only shape.
"""

from datetime import datetime, timezone

from defend.fusion import decision_for as _decision_for  # noqa: E402  -- Section 6 decision bands, single source (defend/fusion.py)


def record_run_and_results(client, run_type: str, model_name: str, cases: list, batch_size: int = 200) -> str:
    """cases: list of dicts with keys case_id, score (0-1), threshold,
    is_fraud (bool), evidence (list[str]). Creates one evaluation_runs row
    and one evaluation_results row per case. Returns the new run_id."""
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
        fused = round(c["score"] * 100, 2)
        predicted_fraud = c["score"] >= c["threshold"]
        rows.append({
            "run_id": run_id,
            "case_id": c["case_id"],
            "model_signals": [{"model": model_name, "score": c["score"]}],
            "fused_risk_score": fused,
            "decision": _decision_for(fused),
            "detected": bool(predicted_fraud == c["is_fraud"]),
            "actual_label": "fraud" if c["is_fraud"] else "legit",
            "evidence": c.get("evidence", []),
        })

    for i in range(0, len(rows), batch_size):
        client.table("evaluation_results").insert(rows[i:i + batch_size]).execute()

    return run_id
