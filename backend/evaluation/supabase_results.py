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

2026-09-01 -- GHOST RUNS, and why the run row is now written LAST.

Ten of the twenty most recent evaluation_runs rows carried status
`completed` and ZERO evaluation_results rows -- including all four held-out
tabular models (xgboost, lightgbm, autoencoder, fusion, n=2000 each). Three
defects lined up:

  1. This function inserted the evaluation_runs row BEFORE building or
     inserting any result row, and hard-coded status "completed" at that
     moment. Anything that failed afterwards left a run that claims success.
  2. Every caller wraps the persistence block in `except Exception` and
     prints "skipped (non-fatal)" to stderr -- which Colab does not surface.
  3. The failure itself: case_id is minted as `uuid4().hex[:12]`
     (artifact_generators/transaction_gen.py:91), so regenerating the
     dataset produces case_ids that share nothing with the previous
     generation. data/processed/attacks_held_out.parquet was rewritten at
     05:57; attack_cases had last been backfilled at 05:22. A 25-id probe of
     that parquet against attack_cases found 0 of 25 present. The FK
     rejected all 2000, ten times over, for four models.

So: rows are built and pre-flight-checked first, the run row is inserted as
`running`, and it is marked `completed` only once every batch has landed --
`failed` otherwise. A run in this table now means what it says.
"""

import os
from datetime import datetime, timezone

from defend.fusion import decision_for as _decision_for  # noqa: E402  -- Section 6 decision bands, single source (defend/fusion.py)


def explain_persistence_failure(exc: Exception) -> str:
    """Turns a failed per-case persistence into advice that matches the
    ACTUAL failure.

    Every eval script prints the same three-line hint when persistence
    raises, and that hint assumed the cause was a foreign-key rejection --
    the failure mode that hid a 100% persistence loss on 2026-09-01. On
    2026-09-02 the cause was instead a missing `import os` in THIS module,
    added alongside the campaign_id stamping. The hint duly told the user
    to re-run a backfill, which had nothing to do with it and would not
    have helped.

    So the advice is now derived from the exception type. A NameError or
    AttributeError here is a bug in this file, not something the user's
    data or environment can fix, and saying so is the difference between a
    two-minute fix and an afternoon spent re-running backfills.
    """
    if isinstance(exc, (NameError, AttributeError, ImportError, TypeError)):
        return ("This is a BUG IN THE PERSISTENCE CODE ITSELF "
                "(evaluation/supabase_results.py), not a problem with your data, "
                "your environment or your Supabase credentials. Re-running a "
                "backfill will not help. Fix the code and re-run this eval -- "
                "the scores above are real, they just never reached the database.")
    text = f"{exc}".lower()
    if "foreign key" in text or "violates" in text or "23503" in text:
        return ("A foreign key on case_id was rejected: this family's cases are missing "
                "from attack_cases. Run `python generate/run_all_generation.py --only "
                "backfill_attack_cases,backfill_phase2_artifacts` and re-run this eval.")
    if "jwt" in text or "auth" in text or "credential" in text or "401" in text:
        return ("Supabase rejected the credentials. Check SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY in .env -- the service-role key is the one "
                "that can write, and it may have been rotated.")
    return ("Cause not recognised. The scores above are real and metrics.json was "
            "written; only the per-case rows were lost. Re-run this eval once the "
            "cause below is addressed.")


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

    # The evaluation_runs row is created LAST, not first. See the module
    # docstring's "GHOST RUNS" note: inserting it up front is what let ten
    # of the last twenty runs sit in the dashboard as `completed` while
    # holding zero result rows.
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
            # run_id filled in after the pre-flight check, below
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

    # PRE-FLIGHT: every case_id must already exist in attack_cases, because
    # evaluation_results.case_id has a hard FK to it. When it does not, the
    # insert fails wholesale, every caller catches it as "non-fatal", and the
    # only trace is a stderr line Colab never showed. The check below turns
    # that into one sentence naming the actual cause.
    _assert_cases_exist(client, [r["case_id"] for r in rows], model_name)

    now = datetime.now(timezone.utc).isoformat()
    # WHICH DEFENSE RUN PRODUCED THIS. Until 2026-09-02 nothing recorded it:
    # config held {model, n_cases} and no campaign id, so a defense run could
    # not be joined to the eval rows it produced. Every per-run number in the
    # UI therefore had to be either corpus-wide (tiles that never moved) or
    # inferred from a time window (right only while exactly one run is in
    # flight). agent_runner.py exports FRAUDSHIELD_CAMPAIGN_ID before it
    # spawns anything, so every child inherits it; absent when a script is run
    # by hand, which is a real distinction worth keeping rather than faking.
    campaign_id = os.environ.get("FRAUDSHIELD_CAMPAIGN_ID") or None
    config = {"model": model_name, "n_cases": len(cases)}
    if campaign_id:
        config["campaign_id"] = campaign_id
    run_resp = client.table("evaluation_runs").insert({
        "run_type": run_type,
        "config": config,
        "status": "running",
        "started_at": now,
    }).execute()
    run_id = run_resp.data[0]["id"]
    for r in rows:
        r["run_id"] = run_id

    try:
        for i in range(0, len(rows), batch_size):
            client.table("evaluation_results").insert(rows[i:i + batch_size]).execute()
    except Exception:
        # A run that persisted nothing must never read as `completed`. The
        # row is left behind deliberately rather than deleted -- a failed
        # attempt is itself part of the record -- but it is labelled for
        # what it is, so no dashboard aggregate can silently include it.
        try:
            client.table("evaluation_runs").update(
                {"status": "failed", "finished_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", run_id).execute()
        except Exception:
            pass
        raise

    client.table("evaluation_runs").update(
        {"status": "completed", "finished_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", run_id).execute()

    return run_id


def _assert_cases_exist(client, case_ids: list, model_name: str, probe: int = 40) -> None:
    """Sample-probe attack_cases before writing anything.

    A full membership check would be one request per 1000 ids (PostgREST's
    response cap) on a 2000-case held-out set. A sample is enough because
    the failure this catches is never partial: case_id is minted as
    `uuid4().hex[:12]` in artifact_generators/transaction_gen.py, so a
    regenerated dataset shares NO ids with the previous one. Either the
    backfill has seen this generation or it has seen none of it.
    """
    if not case_ids:
        return
    seen = sorted(set(case_ids))
    step = max(1, len(seen) // probe)
    sample = seen[::step][:probe]

    resp = client.table("attack_cases").select("id").in_("id", sample).execute()
    found = {r["id"] for r in (resp.data or [])}
    missing = [c for c in sample if c not in found]
    if not missing:
        return

    raise RuntimeError(
        f"{model_name}: {len(missing)} of {len(sample)} probed case_ids are absent from "
        f"attack_cases, e.g. {missing[0]}. evaluation_results.case_id is a foreign key, so "
        "EVERY insert would be rejected and this run would persist zero rows.\n\n"
        "Cause: case_id is uuid4().hex[:12], minted fresh on every generation. The dataset "
        "on disk was regenerated after the last backfill, so its ids are new and Supabase "
        "still holds the previous generation's.\n\n"
        "Fix: python generate/run_all_generation.py --only backfill_attack_cases,backfill_phase2_artifacts"
    )
