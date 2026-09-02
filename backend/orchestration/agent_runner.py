"""
Real Red-Team/Blue-Team agent orchestrator (2026-08-31) -- replaces
frontend/src/data/mockStore.js's getAgentSteps(), which fabricated a
7-agent play-by-play with Math.random() and no backend behind it at all.
There is no separate "AI agent framework" here: each of the 7 stages
below is a thin wrapper that calls ALREADY REAL project code
(evaluation/split_policy.py's real family/combination data,
generate/run_all_generation.py, evaluation/run_all_evaluations.py,
evaluation/adaptive_weakness_round.py) and reports exactly what that code
actually did. If a stage has nothing real to report (e.g. the mutation
stage when severity isn't "adaptive", or the weakest family this run
found isn't one adaptive_weakness_round.py currently supports), it says
so honestly instead of inventing a result -- same "must degrade
gracefully, never fabricate" posture as the rest of this project.

Persists live progress into Supabase's `campaign_runs.stage_results`
(001_core_schema.sql) after every stage STARTS and again when it
COMPLETES -- not just at the end. That's what lets a browser poll real
in-flight progress via a direct (RLS read-only, anon-key) query while
this process is still running, with zero backend polling loop needed.
stage_results is a jsonb OBJECT (not the bare array its default suggests
-- jsonb doesn't enforce a shape, and this shape is more useful here):

    {"meta": {objective, scope, severity, scenarioCount, status,
              currentIteration, totalIterations, createdAt, completedAt},
     "steps": [...one AgentStepList-shaped entry per stage...]}

Each step mirrors frontend/src/components/shared/AgentStepList.jsx's
expected shape field-for-field (agent/detail/observation/decision/tool/
action/result/next/status/timestamp) -- that component already existed
before this script did, it just had nothing real feeding it.

One attack_campaigns row + one campaign_runs row is created per run
(both real tables from Phase 1.5's schema, previously unused by any
script -- Principle 12's "predefined composite scenarios" tables turned
out to be exactly the right shape for an ad-hoc orchestrated run too).

Usage:
    python orchestration/agent_runner.py --objective "Harden against mule networks" \
        --scope transaction,graph --severity adaptive --scenario-count 200
"""

import argparse
import tempfile
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from db.supabase_client import get_service_client  # noqa: E402
from evaluation.split_policy import FAMILIES  # noqa: E402

METRICS_JSON = BACKEND_DIR / "defend" / "models" / "metrics.json"
GEN_SCRIPT = BACKEND_DIR / "generate" / "run_all_generation.py"
EVAL_SCRIPT = BACKEND_DIR / "evaluation" / "run_all_evaluations.py"
ADAPTIVE_SCRIPT = BACKEND_DIR / "evaluation" / "adaptive_weakness_round.py"
STORAGE_SYNC_SCRIPT = BACKEND_DIR / "tools" / "storage_sync.py"
GENERATED_DIR = BACKEND_DIR.parent / "data" / "generated"

# Which data/generated/ bundles a family needs, for the hydration step
# below. Only what the run's own scope requires is pulled -- a
# transaction-only run has no reason to download 108 MB of voice audio.
BUNDLES_FOR_FAMILY = {
    "transaction_fraud": ["attacks", "synthetic_customers"],
    "account_takeover": ["attacks", "synthetic_customers"],
    "synthetic_identity": ["attacks", "synthetic_customers"],
    "mule_network": ["attacks", "synthetic_customers"],
    "voice_scam": ["voice_attacks", "voice_bonafide", "synthetic_customers"],
    "document_fraud": ["document_attacks", "document_bonafide"],
    "phishing_scam": ["phishing_attacks", "phishing_bonafide"],
}

TABULAR_FAMILIES = {"transaction_fraud", "account_takeover", "synthetic_identity", "mule_network"}

# Honest mapping from the frontend's scope categories (types/index.js's
# ATTACK_CATEGORY_LABEL) to real attack families (split_policy.py's
# FAMILIES). "qr" has no dedicated family of its own -- document_fraud is
# the closest real family (it has a qr_payload tampering dimension), so
# qr maps there rather than to a fabricated family that doesn't exist.
SCOPE_TO_FAMILIES = {
    "transaction": ["transaction_fraud"],
    "behavioral": ["account_takeover"],
    "graph": ["mule_network"],
    "voice": ["voice_scam"],
    "text": ["phishing_scam"],
    "qr": ["document_fraud"],
    "document": ["document_fraud"],
    "account-takeover": ["account_takeover"],
}

GEN_STEP_FOR_FAMILY = {
    "transaction_fraud": "tabular_attacks", "account_takeover": "tabular_attacks",
    "synthetic_identity": "tabular_attacks", "mule_network": "tabular_attacks",
    "voice_scam": "voice_attacks", "document_fraud": "document_attacks", "phishing_scam": "phishing_attacks",
}
EVAL_STEP_FOR_FAMILY = {
    "transaction_fraud": ["adversarial_tabular", "fusion"],
    "account_takeover": ["adversarial_tabular", "fusion", "behavioral_adjustment"],
    "synthetic_identity": ["adversarial_tabular", "fusion"],
    "mule_network": ["adversarial_tabular", "fusion", "gnn"],
    "voice_scam": ["voice_spoof"],
    "document_fraud": ["document_consistency"],
    "phishing_scam": ["phishing_classifier"],
}
# family -> metrics.json key holding that family's real held_out_recall,
# for the single-signal (non-tabular) families. Tabular families read
# fusion_adversarial_eval.per_family_recall instead (see evaluation-agent
# stage below) since fusion, not any single detector, is the real
# decision-maker for those four.
HELD_OUT_KEY_FOR_FAMILY = {
    "voice_scam": "voice_spoof_detector",
    "document_fraud": "document_consistency_detector",
    "phishing_scam": "phishing_classifier_evidence_gate",
}

# Human-readable labels for the frontend (WeaknessAnalysisPage / ReportPage /
# AdaptiveMutationPage), keyed by real family id -- not flavor text, just
# plain names for the real thing.
FAMILY_LABEL = {
    "transaction_fraud": "Transaction fraud",
    "account_takeover": "Account takeover",
    "synthetic_identity": "Synthetic identity",
    "mule_network": "Mule-network laundering",
    "voice_scam": "Voice-clone impersonation",
    "document_fraud": "Document / invoice fraud",
    "phishing_scam": "Phishing (text / GenAI)",
}

# Reverse of SCOPE_TO_FAMILIES, for display only -- WeaknessAnalysisPage and
# ReportPage look up ATTACK_CATEGORY_LABEL[category] using the frontend's
# scope-category keys (types/index.js), not family ids, so weaknesses need
# to carry a category the frontend actually recognizes. Where more than one
# scope category maps to the same family (document_fraud <- qr, document),
# this picks one canonical category for display; it doesn't affect which
# family was actually evaluated. synthetic_identity has no scope category
# of its own yet (SCOPE_TO_FAMILIES never resolves to it), so it's bucketed
# under "transaction" here purely so a label always exists if it's ever
# surfaced -- it will not appear in practice via this orchestrator today.
FAMILY_TO_CATEGORY = {
    "transaction_fraud": "transaction",
    "account_takeover": "account-takeover",
    "synthetic_identity": "transaction",
    "mule_network": "graph",
    "voice_scam": "voice",
    "document_fraud": "document",
    "phishing_scam": "text",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_metrics() -> dict:
    if not METRICS_JSON.exists():
        return {}
    return json.loads(METRICS_JSON.read_text())


def _run_script(script: Path, args: list, timeout: int = 3600) -> dict:
    t0 = time.monotonic()
    if not script.exists():
        return {"ok": False, "seconds": 0.0, "tail": f"Script not found: {script}", "returncode": None, "stdout": ""}
    try:
        proc = subprocess.run([sys.executable, str(script), *args], cwd=str(BACKEND_DIR),
                               capture_output=True, text=True, timeout=timeout)
        combined = (proc.stdout or "") + (proc.stderr or "")
        return {"ok": proc.returncode == 0, "seconds": round(time.monotonic() - t0, 1),
                "tail": "\n".join(combined.splitlines()[-20:]), "returncode": proc.returncode,
                "stdout": proc.stdout or ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "seconds": round(time.monotonic() - t0, 1), "tail": f"TIMED OUT after {timeout}s", "returncode": None, "stdout": ""}
    except Exception as exc:
        return {"ok": False, "seconds": 0.0, "tail": f"Failed to launch: {exc}", "returncode": None, "stdout": ""}


def _run_script_streaming(script: Path, args: list, timeout: int = 3600, on_line=None) -> dict:
    """Same contract as _run_script(), but reads the child's stdout LINE BY
    LINE as it is produced and hands each line to on_line().

    Why this exists: _run_script() uses subprocess.run(capture_output=True),
    which returns nothing at all until the child exits. The blue-team stage
    routinely runs for several minutes across many detectors, and for that
    whole time the war room had exactly one "running" step and no way to
    tell a slow run from a hung one. run_all_evaluations.py already prints
    a per-step banner and flushes it; nobody was listening.

    stderr goes to a temp FILE rather than a second pipe: reading two pipes
    from one thread deadlocks as soon as either fills its buffer, and
    merging stderr into stdout would let a warning printed mid-flush land
    inside the ===JSON_SUMMARY_START=== block that _parse_json_summary()
    has to parse. A file costs nothing and keeps both streams intact.
    """
    t0 = time.monotonic()
    if not script.exists():
        return {"ok": False, "seconds": 0.0, "tail": f"Script not found: {script}", "returncode": None, "stdout": ""}

    out_lines = []
    try:
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errf:
            proc = subprocess.Popen(
                [sys.executable, str(script), *args], cwd=str(BACKEND_DIR),
                stdout=subprocess.PIPE, stderr=errf, text=True, bufsize=1,
            )
            try:
                for line in proc.stdout:
                    line = line.rstrip("\n")
                    out_lines.append(line)
                    if on_line is not None:
                        try:
                            on_line(line)
                        except Exception:
                            # A progress callback must never be able to kill
                            # the run it is only reporting on.
                            pass
                    if timeout is not None and time.monotonic() - t0 > timeout:
                        proc.kill()
                        return {"ok": False, "seconds": round(time.monotonic() - t0, 1),
                                "tail": f"TIMED OUT after {timeout}s", "returncode": None,
                                "stdout": "\n".join(out_lines)}
                proc.wait(timeout=60)
            finally:
                if proc.stdout:
                    proc.stdout.close()
            errf.seek(0)
            err_text = errf.read()
    except Exception as exc:
        return {"ok": False, "seconds": 0.0, "tail": f"Failed to launch: {exc}", "returncode": None, "stdout": ""}

    stdout = "\n".join(out_lines)
    combined = stdout + err_text
    return {"ok": proc.returncode == 0, "seconds": round(time.monotonic() - t0, 1),
            "tail": "\n".join(combined.splitlines()[-20:]), "returncode": proc.returncode,
            "stdout": stdout}


def _banner_reporter(tracker, step, running_detail: str):
    """Turns run_all_evaluations.py / run_all_generation.py's step banners
    into live substeps on `step`.

    Both scripts print (and flush) the same pair around every child they
    run:
        === voice_spoof (evaluation/eval_voice_spoof.py) ===
        --- voice_spoof: OK (41.2s) ---
    That is the only honest progress signal available: it comes from the
    child actually starting and finishing real work, not from a timer
    pretending to know how long the stage will take. Every other line is
    ignored, so a chatty detector costs zero extra Supabase writes.
    """
    def on_line(line: str):
        text = line.strip()
        if text.startswith("=== ") and text.endswith(" ==="):
            name = text[4:-4].split(" (")[0].strip()
            if name:
                tracker.push_substep(step, name, "running", running_detail)
        elif text.startswith("--- ") and text.endswith(" ---") and ":" in text:
            name, _, rest = text[4:-4].strip().partition(":")
            rest = rest.strip()
            tracker.push_substep(step, name.strip(),
                                 "done" if rest.upper().startswith("OK") else "failed",
                                 rest)
    return on_line


def _parse_json_summary(stdout: str):
    """Extracts the ===JSON_SUMMARY_START/END=== block run_all_generation.py
    (and run_all_evaluations.py) print with --json. Returns None rather than
    raising if the block is missing or malformed -- a run whose subprocess
    failed before printing it should degrade gracefully, not crash the
    orchestrator."""
    if not stdout or "===JSON_SUMMARY_START===" not in stdout:
        return None
    try:
        block = stdout.split("===JSON_SUMMARY_START===", 1)[1].split("===JSON_SUMMARY_END===", 1)[0]
        return json.loads(block.strip())
    except Exception:
        return None


def _family_case_count(case_counts: dict, fam: str) -> int:
    """case_counts (from run_all_generation.py's real on-disk scan) keys
    tabular families to a {split: count} dict and non-tabular families to
    a {"total": count} dict -- sum either shape to one real number."""
    entry = case_counts.get(fam)
    if not entry:
        return 0
    return sum(v for v in entry.values() if isinstance(v, (int, float)))


def _family_metrics_from(metrics: dict, fam: str):
    """Real per-family recall/precision/f1/pr_auc/false_positives from
    defend/models/metrics.json -- see module docstring / docs/DATASETS.md
    for why tabular families read fusion_adversarial_eval (fusion is the
    real decision-maker for those four) while the three single-signal
    families read their own held-out evidence-gate entry. Returns None if
    metrics.json doesn't have this family's numbers yet (never fabricated)."""
    if fam in TABULAR_FAMILIES:
        fusion = metrics.get("fusion_adversarial_eval")
        if not fusion:
            return None
        recall = fusion.get("per_family_recall", {}).get(fam)
        if recall is None:
            return None
        m = fusion.get("metrics", {})
        return {
            "recall": recall, "precision": m.get("precision"), "f1": m.get("f1"),
            "pr_auc": m.get("pr_auc"), "false_positives": m.get("false_positives"),
            "scope": "fusion_adversarial_eval (global across all tabular families scored this run, not per-family)",
        }
    key = HELD_OUT_KEY_FOR_FAMILY.get(fam)
    if not key or key not in metrics:
        return None
    entry = metrics[key]
    recall = entry.get("held_out_recall")
    if recall is None:
        return None
    m = entry.get("metrics", {})
    return {
        "recall": recall, "precision": m.get("precision"), "f1": m.get("f1"),
        "pr_auc": m.get("pr_auc"), "false_positives": m.get("false_positives"),
        "scope": f"{key} (its own real held-out evaluation)",
    }


def _build_weaknesses(family_metrics: dict, weakest) -> list:
    """Real weakness cards for WeaknessAnalysisPage/ReportPage. Every value
    comes from _family_metrics_from() (real metrics.json numbers).

    2026-08-31 -- this used to emit one "Defense weakness detected" card per
    family unconditionally, ranked by recall, and label the lowest-ranked
    one the run's weakness even when its recall was 1.0000. On a run where
    nothing was missed that rendered as:

        Defense weakness detected -- Account takeover      [High]
        Detection rate 100%   Miss rate 0%
        WHY THE DEFENSE MISSES THIS
        - Lowest real recall this run (1.0000) among the families scored

    which is incoherent: a family that missed nothing is not a weakness,
    "why the defense misses this" has no answer, and calling it High
    severity next to a 0% miss rate destroys trust in every other number on
    the page. A run where nothing was missed must say so.

    So: a family only becomes a weakness card when it actually missed
    something (recall < 1.0). Families that missed nothing are still
    reported -- as clean results, with the false-positive count that a
    perfect recall usually costs -- because "we caught everything, here is
    what that cost in customer friction" is the honest framing, and because
    a perfect recall is itself worth flagging as a signal that the attacks
    may be too easy rather than the defense being flawless."""
    out = []
    # Weakest-first, but a family with a real miss always outranks one
    # without, regardless of any other metric.
    for fam, m in sorted(family_metrics.items(), key=lambda kv: kv[1]["recall"]):
        recall = m["recall"]
        detection_pct = round(recall * 100, 1)
        missed_something = recall < 1.0
        is_weakest = fam == weakest and missed_something
        fps = m.get("false_positives")
        fp_note = (
            f"At this operating point it also raised {fps:,} false positives on legitimate traffic."
            if isinstance(fps, (int, float)) and fps else None
        )

        if missed_something:
            reasons = [
                f"Real recall {recall:.4f} on {m['scope']} — "
                f"{round(100 - detection_pct, 1)}% of this family's attacks reached the system."
            ]
            if fp_note:
                reasons.append(fp_note)
            out.append({
                "id": f"weak-{fam}",
                "category": FAMILY_TO_CATEGORY.get(fam, fam),
                "label": FAMILY_LABEL.get(fam, fam),
                "detectionRate": detection_pct,
                "missRate": round(100 - detection_pct, 1),
                "kind": "weakness",
                "reasons": reasons,
                "recommendedAction": (
                    "Run a real adaptive mutation round targeting this family (severity=adaptive)"
                    if is_weakest else "Queue for a later adaptive round — a real miss, but not the largest this run"
                ),
                "severity": "high" if is_weakest else "medium",
            })
            continue

        # recall == 1.0 -- not a weakness. Reported honestly as a clean
        # result, with the caveat that earns it.
        reasons = [
            f"No misses at this operating point — real recall {recall:.4f} on {m['scope']}."
        ]
        if fp_note:
            reasons.append(fp_note)
        reasons.append(
            "A perfect recall is more likely to mean the generated attacks for this family are too "
            "easily separated than that the defense is flawless — the next adaptive round should make "
            "them harder rather than treat this as solved."
        )
        out.append({
            "id": f"clean-{fam}",
            "category": FAMILY_TO_CATEGORY.get(fam, fam),
            "label": FAMILY_LABEL.get(fam, fam),
            "detectionRate": detection_pct,
            "missRate": 0.0,
            "kind": "clean",
            "reasons": reasons,
            "recommendedAction": "Raise attack difficulty for this family — nothing to fix in the defense here",
            "severity": "none",
        })
    return out


def _bundle_present(name: str) -> bool:
    """A bundle counts as present only if its directory holds real files --
    an empty directory left behind by a partial pull is not data."""
    d = GENERATED_DIR / name
    if not d.is_dir():
        return False
    return any(p.is_file() and p.name != ".storage_bundle.json" for p in d.rglob("*"))


def _hydrate_if_needed(families: list) -> dict:
    """Pull the data/generated/ bundles this run's scope needs, if they are
    not already on disk.

    This runs as part of the run itself rather than behind a separate
    "hydrate" button, because a container built from this repo has no
    data/generated/ (gitignored, 236 MB) and a run launched against it
    completes in seconds reporting "Generation had failures" and
    attacksTested: 0 -- structurally correct and completely empty. Making
    the person notice that, find a button and press it first is a worse
    design than the run fetching what it needs; the fetch is a real,
    reported stage, not a hidden side effect.

    On a machine that already has the data (a developer's laptop) every
    bundle is present and this returns immediately, having done nothing."""
    needed = sorted({b for f in families for b in BUNDLES_FOR_FAMILY.get(f, [])})
    missing = [b for b in needed if not _bundle_present(b)]
    if not missing:
        return {"needed": needed, "missing": [], "pulled": [], "ok": True,
                "summary": f"All {len(needed)} required bundle(s) already on disk"}

    result = _run_script(STORAGE_SYNC_SCRIPT, ["pull", "--only", ",".join(missing)], timeout=1800)
    still_missing = [b for b in missing if not _bundle_present(b)]
    return {
        "needed": needed,
        "missing": missing,
        "pulled": [b for b in missing if b not in still_missing],
        "stillMissing": still_missing,
        "ok": result["ok"] and not still_missing,
        "seconds": result["seconds"],
        "tail": result["tail"],
        "summary": (
            f"Pulled {len(missing) - len(still_missing)}/{len(missing)} bundle(s) from Supabase Storage "
            f"in {result['seconds']}s"
            if result["ok"] else f"Storage pull failed after {result['seconds']}s -- {result['tail'][-200:]}"
        ),
    }


def _objective_short(objective: str) -> str:
    return (objective[:77] + "...") if len(objective) > 80 else objective


class RunTracker:
    """Persists live stage-by-stage progress into campaign_runs.stage_results
    after every stage starts AND completes -- see module docstring for the
    exact jsonb shape."""

    def __init__(self, client, run_id: str, objective: str, scope: list, severity: str, scenario_count: int):
        self.client = client
        self.run_id = run_id
        self.meta = {
            "objective": objective, "scope": scope, "severity": severity,
            "scenarioCount": scenario_count, "status": "running",
            "currentIteration": 1, "totalIterations": 2 if severity == "adaptive" else 1,
            "createdAt": _now_iso(),
        }
        self.steps = []
        self._campaign_row()
        self._run_row()

    def _campaign_row(self):
        self.client.table("attack_campaigns").insert({
            "id": self.run_id,
            "name": _objective_short(self.meta["objective"]),
            "description": (f"Ad-hoc orchestrated run -- scope={self.meta['scope']}, "
                             f"severity={self.meta['severity']}, scenario_count={self.meta['scenarioCount']}"),
            "stages": [{"agent": a} for a in
                       ["orchestrator", "threat-research", "attack-planner",
                        "attack-generator", "blue-team", "evaluation", "mutation-engine"]],
        }).execute()

    def _run_row(self):
        resp = self.client.table("campaign_runs").insert({
            "campaign_id": self.run_id,
            "stage_results": {"meta": self.meta, "steps": []},
        }).execute()
        self.campaign_run_id = resp.data[0]["id"]

    def add_step(self, agent, detail, observation="", decision="", tool="—", action="", result="", next_=""):
        """For cheap/instant stages -- appends an already-"done" step."""
        step = {"id": f"{self.run_id}-step-{len(self.steps)}", "agent": agent, "detail": detail,
                "observation": observation, "decision": decision, "tool": tool, "action": action,
                "result": result, "next": next_, "status": "done", "timestamp": _now_iso()}
        self.steps.append(step)
        self._flush()
        return step

    def start_step(self, agent, detail):
        """For real, possibly minutes-long stages -- appends a "running"
        step immediately (visible to a polling browser before the
        subprocess even finishes), returns it for complete_step() to fill in."""
        step = {"id": f"{self.run_id}-step-{len(self.steps)}", "agent": agent, "detail": detail,
                "observation": "", "decision": "", "tool": "—", "action": "", "result": "", "next": "",
                "status": "running", "timestamp": _now_iso()}
        self.steps.append(step)
        self._flush()
        return step

    def update_step(self, step, **fields):
        """Live update of a step that is still RUNNING.

        complete_step() is terminal -- it stamps status="done" -- so there
        was no way to say "this stage is still going, and here is how far
        it has got". Every long stage therefore looked identical to a hung
        one for its entire duration. This writes progress without closing
        the step.

        Each call is a Supabase round-trip, so callers must throttle: emit
        on real milestones (a detector starting or finishing), never per
        line of subprocess output.
        """
        step.update(fields)
        step["timestamp"] = _now_iso()
        self._flush()

    def push_substep(self, step, label, status="running", detail=""):
        """Appends/updates a named child of a running stage.

        The war room renders these underneath the stage, so a blue-team
        stage scoring six detectors shows six lines ticking over instead of
        one spinner. Re-calling with the same label updates that child
        rather than appending a duplicate -- which is what makes
        "voice_spoof: running" become "voice_spoof: done (41.2s)" in place.
        """
        subs = step.setdefault("substeps", [])
        for sub in subs:
            if sub["label"] == label:
                sub["status"] = status
                if detail:
                    sub["detail"] = detail
                sub["timestamp"] = _now_iso()
                break
        else:
            subs.append({"label": label, "status": status, "detail": detail,
                         "timestamp": _now_iso()})
        # Denominator is how many children have ANNOUNCED themselves, not
        # how many will eventually run -- neither script declares its plan
        # up front, so "2/3" here means "3 started, 2 finished" and the 3
        # can still grow. Worded to match.
        step["progress"] = (f"{sum(1 for x in subs if x['status'] == 'done')}"
                            f" of {len(subs)} started so far")
        step["timestamp"] = _now_iso()
        self._flush()

    def complete_step(self, step, **fields):
        step.update(fields)
        step["status"] = "done"
        step["timestamp"] = _now_iso()
        # Any child still marked "running" when its parent finishes never
        # printed its own completion banner -- the subprocess died, was
        # killed, or the marker changed shape. Leaving it spinning forever
        # in the UI would be a lie about a process that is definitively
        # over.
        for sub in step.get("substeps", []):
            if sub["status"] == "running":
                sub["status"] = "unknown"
                sub["detail"] = sub.get("detail") or "no completion banner -- outcome unknown"
        self._flush()

    def set_iteration(self, n):
        self.meta["currentIteration"] = n
        self._flush()

    def update_meta(self, fields: dict):
        """Merges real run-level aggregate fields (attacksTested,
        weaknesses, mutationIterations, etc. -- see main()) into meta and
        flushes. Called once after the evaluation-agent stage, and again
        after a successful mutation-engine stage to record the after-
        numbers -- never before there's a real value to write."""
        self.meta.update(fields)
        self._flush()

    def finish(self, overall_detected, weakest_stage):
        self.meta["status"] = "completed"
        self.meta["completedAt"] = _now_iso()
        self.meta["currentIteration"] = self.meta["totalIterations"]
        self._flush()
        self.client.table("campaign_runs").update({
            "overall_detected": overall_detected, "weakest_stage": weakest_stage,
        }).eq("id", self.campaign_run_id).execute()

    def fail(self, error):
        self.meta["status"] = "failed"
        self.meta["error"] = str(error)
        self._flush()

    def _flush(self):
        self.client.table("campaign_runs").update({
            "stage_results": {"meta": self.meta, "steps": self.steps},
        }).eq("id", self.campaign_run_id).execute()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--objective", type=str, default="Harden the fraud defense against adaptive payment fraud.")
    parser.add_argument("--scope", type=str, default="transaction,behavioral,graph",
                         help="Comma-separated scope categories: " + ",".join(SCOPE_TO_FAMILIES))
    parser.add_argument("--severity", type=str, default="adaptive", choices=["low", "medium", "high", "adaptive"])
    parser.add_argument("--scenario-count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-id", type=str, default=None, help="Reuse a specific run id (default: generated)")
    args = parser.parse_args()

    scope = [s.strip() for s in args.scope.split(",") if s.strip()]
    unknown = set(scope) - set(SCOPE_TO_FAMILIES)
    if unknown:
        print(f"Unknown scope categories: {unknown}. Valid: {list(SCOPE_TO_FAMILIES)}", file=sys.stderr)
        return 2

    run_id = args.run_id or f"run_{uuid.uuid4().hex[:10]}"
    client = get_service_client()
    # Every subprocess this run spawns -- generators, evaluators, and the
    # eval_*.py scripts THEY spawn -- inherits this, which is how
    # supabase_results.py stamps evaluation_runs.config.campaign_id and makes
    # a defense run joinable to the rows it produced. Set before the tracker,
    # so nothing can be spawned without it.
    os.environ["FRAUDSHIELD_CAMPAIGN_ID"] = run_id

    tracker = RunTracker(client, run_id, args.objective, scope, args.severity, args.scenario_count)
    print(f"Run {run_id} started. Live progress: select * from campaign_runs where campaign_id = '{run_id}'")

    try:
        # ---- 1. orchestrator: turn scope into real attack families ----
        families = sorted({f for cat in scope for f in SCOPE_TO_FAMILIES[cat]})
        n_per_family = max(5, min(args.scenario_count // max(1, len(families)), 200))
        tracker.add_step(
            "orchestrator",
            detail=f'Goal received: "{args.objective}"',
            observation=f"New run requested -- scope categories: {', '.join(scope)}",
            decision="Map scope categories to real attack families and delegate discovery",
            action=f"Resolve {len(scope)} scope categories to concrete attack families",
            result=f"Resolved to: {', '.join(families)} ({n_per_family} cases/family planned)",
            next_="Hand off to Threat Research",
        )

        # ---- 1b. data-loader: make sure this instance actually has data ----
        # Reported as a real step so the war room shows it happening,
        # rather than a silent pause before generation. On a machine that
        # already has data/generated/ this completes instantly and says so.
        hydrate_step = tracker.start_step(
            "orchestrator",
            detail="Checking this instance has the generated data these families need",
        )
        hydration = _hydrate_if_needed(families)
        tracker.complete_step(
            hydrate_step,
            observation=(
                f"Required bundles: {', '.join(hydration['needed']) or 'none'}. "
                + (f"Missing locally: {', '.join(hydration['missing'])}"
                   if hydration["missing"] else "All present on disk.")
            ),
            decision=("Pull the missing bundles from Supabase Storage before generating -- "
                      "generating over an empty data/generated/ produces a run with 0 attacks tested"
                      if hydration["missing"] else
                      "Nothing to fetch -- proceed straight to generation"),
            tool="tools/storage_sync.py pull (Supabase Storage bucket 'generated-data')",
            action=(f"Pull {len(hydration['missing'])} bundle(s)" if hydration["missing"]
                    else "Verify bundle presence on disk"),
            result=hydration["summary"],
            next_="Hand off to Threat Research",
        )
        if not hydration["ok"]:
            # Not fatal: the generation stage below already degrades
            # honestly when its inputs are missing, and stopping here would
            # hide the rest of the trace. But the run must not later look
            # like the data was fine.
            tracker.update_meta({"dataHydrationFailed": True})

        # ---- 2. threat-research: real combinations from split_policy.py ----
        combo_summaries = []
        for fam in families:
            spec = FAMILIES[fam]
            combo_summaries.append(
                f"{fam}: {len(spec['training_allowed'])} train combo(s), "
                f"{len(spec['held_out_only'])} held-out combo(s) on dimensions {spec['dimensions']}"
            )
        tracker.add_step(
            "threat-research",
            detail=f"Identified real mutation-parameter combinations for {len(families)} families",
            observation="Reading evaluation/split_policy.py's real FAMILIES definitions (not simulated)",
            decision="Use each family's real held-out-only combination(s) as the hard case to target",
            tool="evaluation/split_policy.py",
            action="Enumerate real training/held-out combinations per family",
            result="; ".join(combo_summaries) if combo_summaries else "No families resolved for this scope",
            next_="Hand off to Attack Planner",
        )

        # ---- 3. attack-planner: finalize the generation plan ----
        gen_steps_needed = sorted({GEN_STEP_FOR_FAMILY[f] for f in families})
        tracker.add_step(
            "attack-planner",
            detail=f"Planned {n_per_family} cases/family across {len(gen_steps_needed)} generator(s)",
            observation=f"{len(families)} candidate families available",
            decision=(f"Severity={args.severity} -> escalate with a real adaptive weakness round if the Blue Team "
                      f"finds a gap" if args.severity == "adaptive" else
                      f"Severity={args.severity} -> single pass, no adaptive escalation"),
            tool="generate/run_all_generation.py",
            action=f"Generation steps: {', '.join(gen_steps_needed)}",
            result="Plan finalized",
            next_="Hand off to Attack Generator",
        )

        # ---- 4. attack-generator: REAL subprocess ----
        gen_only = ",".join(gen_steps_needed + ["backfill_attack_cases", "sync_model_registry"])
        gen_step = tracker.start_step("attack-generator", f"Running generate/run_all_generation.py --only {gen_only} ...")
        gen_result = _run_script_streaming(
            GEN_SCRIPT, ["--only", gen_only, "--n-per-family", str(n_per_family),
                          "--n-per-split", str(n_per_family), "--seed", str(args.seed), "--json"],
            on_line=_banner_reporter(tracker, gen_step, "generating..."))
        tracker.complete_step(
            gen_step,
            observation="Attack plan approved",
            decision="Synthesize real adversarial cases via the project's real generators",
            tool="generate/run_all_generation.py (real subprocess)",
            action=f"generate/run_all_generation.py --only {gen_only} --n-per-family {n_per_family}",
            result=(f"Generation succeeded in {gen_result['seconds']}s" if gen_result["ok"]
                    else f"Generation had failures ({gen_result['seconds']}s) -- {gen_result['tail'][-300:]}"),
            next_="Send generated cases to the Blue Team",
        )
        # Real on-disk case counts per family, from run_all_generation.py's own
        # --json summary (case_counts()) -- used below to turn per-family
        # recall into real attack-count aggregates (attacksTested/Caught/Missed),
        # not a fabricated total.
        gen_summary = _parse_json_summary(gen_result.get("stdout", ""))
        case_counts = gen_summary.get("case_counts", {}) if gen_summary else {}

        # ---- 5. blue-team: REAL subprocess ----
        eval_steps_needed = sorted({s for f in families for s in EVAL_STEP_FOR_FAMILY[f]})
        eval_only = ",".join(eval_steps_needed)
        bt_step = tracker.start_step("blue-team", f"Running evaluation/run_all_evaluations.py --only {eval_only} ...")

        # LIVE PROGRESS. run_all_evaluations.py prints (and flushes) a
        # banner around every detector it runs:
        #     === voice_spoof (evaluation/eval_voice_spoof.py) ===
        #     --- voice_spoof: OK (41.2s) ---
        # Those markers are the only honest progress signal available --
        # they come from the child actually starting and finishing real
        # work, not from a timer pretending to know how long it will take.
        # Anything that isn't a banner is ignored, so a detector printing
        # a thousand lines costs zero extra Supabase writes.
        eval_result = _run_script_streaming(
            EVAL_SCRIPT, ["--only", eval_only, "--json"],
            on_line=_banner_reporter(tracker, bt_step, "scoring..."))
        tracker.complete_step(
            bt_step,
            observation="New batch of real adversarial cases available",
            decision="Score every real case across the relevant detection models",
            tool="evaluation/run_all_evaluations.py (real subprocess)",
            action=f"evaluation/run_all_evaluations.py --only {eval_only}",
            result=(f"Evaluation succeeded in {eval_result['seconds']}s" if eval_result["ok"]
                    else f"Evaluation had failures ({eval_result['seconds']}s) -- {eval_result['tail'][-300:]}"),
            next_="Hand off to Evaluation Agent",
        )

        # ---- 6. evaluation-agent: real per-family metrics from metrics.json ----
        metrics = _load_metrics()
        family_metrics = {}
        for fam in families:
            m = _family_metrics_from(metrics, fam)
            if m is not None:
                family_metrics[fam] = m
        family_recall = {fam: m["recall"] for fam, m in family_metrics.items()}
        # A family that missed nothing is not a weakness. Picking the
        # argmin unconditionally made a run where every family scored
        # recall 1.0 report one of them as "this run's primary weakness"
        # with a 0% miss rate -- see _build_weaknesses' docstring. Only
        # families that actually let an attack through are candidates.
        _missed = {fam: r for fam, r in family_recall.items() if r is not None and r < 1.0}
        weakest = min(_missed, key=_missed.get) if _missed else None
        tracker.add_step(
            "evaluation",
            detail=(f"Weakest real signal: {weakest} (recall={family_recall.get(weakest)})" if weakest
                    else "No real recall numbers available yet for this scope"),
            observation=(f"Real recall by family: {family_recall}" if family_recall
                         else "metrics.json has no matching entries yet for this scope -- see the Blue Team step above for why"),
            decision=("Flag the lowest real recall as this run's primary weakness" if weakest
                      else ("Every family scored caught everything -- no weakness to flag; the honest next "
                            "move is harder attacks, not a defense fix" if family_recall
                            else "Nothing to flag -- re-run once metrics.json has this scope's numbers")),
            tool="defend/models/metrics.json (real evidence-gate output)",
            action="Compare real per-family recall across the scored families",
            result=(f"Weakness identified: {weakest}" if weakest
                    else ("No family missed anything this run (every scored recall = 1.0000) -- reported as a "
                          "clean result, not as a weakness" if family_recall
                          else "No weakness identified this run")),
            next_=("Hand off to Adaptation Agent" if args.severity == "adaptive"
                   else "Run complete (severity not adaptive -- no escalation)"),
        )

        # ---- Real run-level aggregates for the frontend (Dashboard / Results /
        # Weakness / Report pages) -- attack counts come from real on-disk case
        # counts (case_counts, stage 4) times real per-family recall
        # (family_metrics, above); a family with no real numbers yet just
        # contributes 0, it is never fabricated to fill a gap.
        attacks_tested = sum(_family_case_count(case_counts, fam) for fam in families)
        attacks_caught = 0
        for fam in families:
            n = _family_case_count(case_counts, fam)
            m = family_metrics.get(fam)
            if n and m and m.get("recall") is not None:
                attacks_caught += round(n * m["recall"])
        attacks_missed = max(0, attacks_tested - attacks_caught)
        # false_positives is a MAX across families, not a sum -- every tabular
        # family's false_positives is the SAME real number (fusion's global
        # count -- see _family_metrics_from's "scope" note), so summing would
        # multiply-count the one real fusion run by len(TABULAR_FAMILIES).
        fp_values = [m["false_positives"] for m in family_metrics.values() if m.get("false_positives") is not None]
        false_positives = max(fp_values) if fp_values else 0
        precisions = [m["precision"] for m in family_metrics.values() if m.get("precision") is not None]
        recalls = [m["recall"] for m in family_metrics.values() if m.get("recall") is not None]
        f1s = [m["f1"] for m in family_metrics.values() if m.get("f1") is not None]
        pr_aucs = [m["pr_auc"] for m in family_metrics.values() if m.get("pr_auc") is not None]
        run_precision = round(sum(precisions) / len(precisions), 4) if precisions else None
        run_recall = round(sum(recalls) / len(recalls), 4) if recalls else None
        run_f1 = round(sum(f1s) / len(f1s), 4) if f1s else None
        run_pr_auc = round(sum(pr_aucs) / len(pr_aucs), 4) if pr_aucs else None
        detection_rate = round(run_recall * 100, 1) if run_recall is not None else None
        attack_coverage_pct = round(100 * len(family_metrics) / len(families), 1) if families else 0.0
        weaknesses = _build_weaknesses(family_metrics, weakest) if family_metrics else []
        mutation_iterations = [{
            "iteration": 1,
            "detectionRate": detection_rate,
            "weakness": (f"{FAMILY_LABEL.get(weakest, weakest)} -- real recall {family_recall.get(weakest):.4f}"
                         if weakest else "No weakness identified this run"),
            "changes": ["Baseline evaluation -- evaluation/run_all_evaluations.py (real subprocess)"],
        }]
        tracker.update_meta({
            "attacksTested": attacks_tested,
            "attacksCaught": attacks_caught,
            "attacksMissed": attacks_missed,
            "falsePositives": false_positives,
            "precision": run_precision,
            "recall": run_recall,
            "f1": run_f1,
            "prAuc": run_pr_auc,
            "detectionRateBefore": detection_rate,
            "detectionRateAfter": detection_rate,
            "improvementPct": 0,
            "attackCoveragePct": attack_coverage_pct,
            "weaknesses": weaknesses,
            "mutationIterations": mutation_iterations,
            "weakestCategory": FAMILY_TO_CATEGORY.get(weakest) if weakest else None,
        })

        # ---- 7. mutation-engine: REAL adaptive round, only when it applies ----
        overall_detected = bool(family_recall) and min(family_recall.values()) >= 0.5
        weakest_stage = weakest
        if args.severity != "adaptive":
            tracker.add_step(
                "mutation-engine",
                detail="Skipped -- severity is not 'adaptive'",
                result=(f"No mutation round run (this run's severity was '{args.severity}'); "
                        f"re-run with severity=adaptive to trigger a real weakness round."),
            )
        elif weakest is None:
            tracker.add_step(
                "mutation-engine",
                detail="Skipped -- no weakness was identified to target",
                result="The evaluation-agent step above found no real recall numbers for this scope, so there is nothing real to target.",
            )
        elif weakest not in TABULAR_FAMILIES:
            tracker.add_step(
                "mutation-engine",
                detail="Skipped -- adaptive_weakness_round.py currently only targets the four tabular families",
                observation=f"Weakest family this run was '{weakest}', which isn't tabular",
                result=(f"evaluation/adaptive_weakness_round.py supports {sorted(TABULAR_FAMILIES)} only -- "
                        f"'{weakest}' needs its own round-2 script (not built yet), reported as skipped rather than faked."),
            )
        else:
            tracker.set_iteration(2)
            before_keys = set(metrics.keys())
            mut_step = tracker.start_step("mutation-engine", "Running evaluation/adaptive_weakness_round.py ...")
            adaptive_result = _run_script(ADAPTIVE_SCRIPT, ["--n-cases", str(max(20, n_per_family))], timeout=3600)
            after_metrics = _load_metrics()
            new_keys = [k for k in after_metrics if k not in before_keys and "weakness_round2" in k]
            round2_entry = after_metrics.get(new_keys[0]) if new_keys else None
            if round2_entry:
                before_r, after_r, delta = (round2_entry.get("before_recall"),
                                             round2_entry.get("after_recall"), round2_entry.get("delta"))
                overall_detected = (after_r or 0) >= (before_r or 0)
                weakest_stage = new_keys[0]
                tracker.complete_step(
                    mut_step,
                    observation=f"Weakness confirmed: {weakest} at recall {family_recall.get(weakest)}",
                    decision="Generate a real harder follow-up combination targeting this weak signal",
                    tool="evaluation/adaptive_weakness_round.py (real subprocess)",
                    action=f"evaluation/adaptive_weakness_round.py --n-cases {max(20, n_per_family)}",
                    result=f"{new_keys[0]}: recall {before_r} -> {after_r} (delta {delta})",
                    next_="Round-2 cases + real results persisted to Supabase (weakness_log, attack_cases, evaluation_results)",
                )
                # Real after-numbers: substitute the weakest family's real
                # post-round recall into the same run-level aggregate computed
                # after stage 6, so detectionRateAfter/improvementPct reflect
                # the one real adaptive round that actually ran here -- not a
                # re-derivation from scratch, and never fabricated when
                # after_r is missing (round2_entry parsed but had no recall).
                if after_r is not None:
                    after_recalls = dict(family_recall)
                    after_recalls[weakest] = after_r
                    recall_values_after = list(after_recalls.values())
                    run_recall_after = (round(sum(recall_values_after) / len(recall_values_after), 4)
                                         if recall_values_after else None)
                    detection_rate_after = round(run_recall_after * 100, 1) if run_recall_after is not None else None
                    improvement_pct = (round(detection_rate_after - detection_rate, 1)
                                        if detection_rate is not None and detection_rate_after is not None else 0)
                    attacks_caught_after = 0
                    for fam in families:
                        n = _family_case_count(case_counts, fam)
                        r = after_recalls.get(fam)
                        if n and r is not None:
                            attacks_caught_after += round(n * r)
                    attacks_missed_after = max(0, attacks_tested - attacks_caught_after)
                    hardened_combo = round2_entry.get("hardened_combo") or {}
                    changes = [f"{k}: {v}" for k, v in hardened_combo.items()] or [
                        f"evaluation/adaptive_weakness_round.py -- {new_keys[0]}"
                    ]
                    mutation_iterations.append({
                        "iteration": 2,
                        "detectionRate": detection_rate_after,
                        "weakness": f"{FAMILY_LABEL.get(weakest, weakest)} -- real recall {before_r} -> {after_r} (delta {delta})",
                        "changes": changes,
                    })
                    tracker.update_meta({
                        "attacksCaught": attacks_caught_after,
                        "attacksMissed": attacks_missed_after,
                        "detectionRateAfter": detection_rate_after,
                        "improvementPct": improvement_pct,
                        "recall": run_recall_after,
                        "mutationIterations": mutation_iterations,
                    })
            else:
                tracker.complete_step(
                    mut_step,
                    result=("Adaptive round finished but produced no parseable weakness_round2 metrics entry" if adaptive_result["ok"]
                            else f"Adaptive round failed ({adaptive_result['seconds']}s) -- {adaptive_result['tail'][-300:]}"),
                )

        tracker.finish(overall_detected, weakest_stage)
        print(f"Run {run_id} complete.")
        return 0
    except Exception as exc:
        tracker.fail(exc)
        print(f"Run {run_id} FAILED: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())
