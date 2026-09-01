"""
Master generation script -- the Red Team counterpart to evaluation/
run_all_evaluations.py (2026-08-31). Runs the real ingestion pipeline in
one command instead of invoking each generate_*.py / db/*.py script by
hand: synthetic customers -> the four Phase 1 tabular families -> the
three media-attack families (voice/document/phishing) -> video-KYC
(whatever identities are on disk today) -> Supabase backfill -> model
registry sync. Also the thing backend/api/main.py's POST /generate/run
endpoint shells out to -- triggering this from the frontend produces the
exact same result as running it here directly.

Every step here is either already idempotent by construction
(inject_attacks.py/backfill_attack_cases.py/sync_model_registry.py all
upsert-on-id) or additive-and-safe-to-repeat (generate_voice_attacks.py /
generate_document_attacks.py / generate_phishing_attacks.py write new
case_ids each run -- re-running grows the case set, it doesn't corrupt
it; generate_video_kyc_attacks.py is explicitly idempotent, see its own
module docstring: it tracks existing (customer_id, tier) keys and skips
anything already authored). Same "keep going on a step failure, don't
abort the batch" posture as run_all_evaluations.py -- a partial ingestion
run with several real families generated is strictly more useful than
aborting on the first failure, and every generate_*.py's own error
message already says what's missing (missing venv, missing media,
missing dataset).

adaptive_weakness_round.py is intentionally NOT in the default step list
-- it's Section 8 steps 5-6, a "round 2" that reads real per-family
recall from run_adversarial_eval.py's already-scored held-out results,
regenerates a harder combination, and re-evaluates. Running it before the
frozen models / a first adversarial eval exist would find no real
weakness to target. Opt in explicitly with --only adaptive_weakness_round
once evaluation/run_all_evaluations.py has produced at least one real
adversarial_tabular result.

Usage:
    python generate/run_all_generation.py
    python generate/run_all_generation.py --n-per-family 50 --n-per-split 10 --seed 42
    python generate/run_all_generation.py --only tabular_attacks,backfill_attack_cases,sync_model_registry
    python generate/run_all_generation.py --only adaptive_weakness_round --n-cases 200
    python generate/run_all_generation.py --json   # machine-readable summary, used by api/main.py
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

GEN_DIR = Path(__file__).resolve().parent
BACKEND_DIR = GEN_DIR.parent
METRICS_JSON = BACKEND_DIR / "defend" / "models" / "metrics.json"

# (name, script path relative to BACKEND_DIR, venv override or None, arg-builder)
# arg-builder takes the parsed argparse Namespace and returns a list[str].
STEPS = [
    ("synthetic_customers", "generate/synthetic_customers.py", None,
     lambda a: []),
    ("tabular_attacks", "generate/inject_attacks.py", None,
     lambda a: ["--n-per-family", str(a.n_per_family), "--seed", str(a.seed)]),
    ("voice_attacks", "generate/generate_voice_attacks.py", "voice_gen_env",
     lambda a: ["--n-per-split", str(a.n_per_split), "--seed", str(a.seed)]),
    ("document_attacks", "generate/generate_document_attacks.py", None,
     lambda a: ["--n-per-split", str(a.n_per_split), "--seed", str(a.seed)]),
    ("phishing_attacks", "generate/generate_phishing_attacks.py", None,
     lambda a: ["--n-per-split", str(a.n_per_split), "--seed", str(a.seed)]),
    ("video_kyc_attacks", "generate/generate_video_kyc_attacks.py", None,
     lambda a: []),
    # backfill_attack_cases.py scans data/generated/attacks/ ONLY -- the four
    # tabular families. The three media families (document_fraud, voice_scam,
    # phishing_scam) live in their own directories and are backfilled by a
    # separate script, backfill_phase2_artifacts.py, which was never in this
    # list.
    #
    # 2026-09-01, the bug that cost a full Colab run: regenerating documents
    # (120 -> 480 cases) and running this pipeline reported every step OK,
    # but attack_cases still held the old 80 document_fraud + 40
    # document_bonafide rows. evaluation_results.case_id has a foreign key to
    # attack_cases, so when the evaluation then scored all 680 cases, every
    # insert batch was rejected for referencing case ids that did not exist.
    # The persistence block is best-effort and caught the exception, printed
    # it to stderr, and continued -- inside a subprocess whose stderr was not
    # displayed. Result: metrics.json updated with real numbers, Supabase
    # still reporting 0 scored document cases, and nothing anywhere saying so.
    ("backfill_attack_cases", "db/backfill_attack_cases.py", None,
     lambda a: []),
    ("backfill_phase2_artifacts", "db/backfill_phase2_artifacts.py", None,
     lambda a: []),
    ("sync_model_registry", "db/sync_model_registry.py", None,
     lambda a: []),
]
# Opt-in only -- see module docstring. Listed separately so a plain
# (no --only) run never triggers it by accident.
ADAPTIVE_STEP = (
    "adaptive_weakness_round", "evaluation/adaptive_weakness_round.py", None,
    lambda a: ["--n-cases", str(a.n_cases)] if a.n_cases else [],
)
ALL_STEPS = STEPS + [ADAPTIVE_STEP]
STEP_NAMES = [name for name, *_ in ALL_STEPS]

# Same convention as evaluation/run_all_evaluations.py's VENV_OVERRIDES --
# only steps that genuinely need a different interpreter than
# sys.executable go here.
VENV_OVERRIDES = {"voice_attacks": "voice_gen_env"}

# Same substring-matched diagnostics as run_all_evaluations.py -- kept in
# sync deliberately rather than imported, so this script stays runnable
# standalone with zero cross-package coupling (matches this repo's
# existing style of small, self-contained scripts).
_FAILURE_HINTS = [
    ("paging file", "Windows virtual memory (pagefile) is too small for this step's peak memory use "
                     "-- NOT a code bug. Fix: System Properties > Advanced > Performance Settings > "
                     "Advanced tab > Virtual Memory > Change > uncheck 'Automatically manage' > set a "
                     "custom size (Initial = your RAM size in MB, Maximum = 2-3x that) > OK > restart "
                     "your machine. Also worth closing other memory-heavy apps before re-running."),
    ("unable to allocate", "Same root cause as a 'paging file too small' error even though the wording "
                            "differs -- see that fix above."),
    ("no module named", "This step's Python environment is missing a dependency. Check VENV_OVERRIDES "
                         "at the top of this file -- if this step needs a dedicated venv that isn't "
                         "listed there yet, add it; otherwise `pip install` the missing package into "
                         "the venv you're running this from."),
    ("no synthetic customer roster found", "Not an error -- run this with 'synthetic_customers' included "
                                            "(it is by default) before generating identity-linked families, "
                                            "or ignore it if you're intentionally generating without "
                                            "customer_id linkage."),
]


def _hint_for(tail: str) -> "str | None":
    lower = tail.lower()
    for needle, hint in _FAILURE_HINTS:
        if needle in lower:
            return hint
    return None


def _interpreter_for(name: str) -> str:
    venv_name = VENV_OVERRIDES.get(name)
    if not venv_name:
        return sys.executable
    venv_dir = BACKEND_DIR / venv_name
    for candidate in (venv_dir / "Scripts" / "python.exe", venv_dir / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    print(f"  WARNING: '{name}' is supposed to run in {venv_dir} but that venv doesn't exist here -- "
          f"falling back to the current interpreter, which will likely fail if the dependency really "
          f"is missing there too.", flush=True)
    return sys.executable


def _run_one(name: str, script: str, extra_args: list, timeout: int) -> dict:
    script_path = BACKEND_DIR / script
    t0 = time.monotonic()
    if not script_path.exists():
        return {"name": name, "script": script, "ok": False, "seconds": 0.0,
                "returncode": None, "tail": f"Script not found: {script_path}", "hint": None}
    interpreter = _interpreter_for(name)
    try:
        proc = subprocess.run(
            [interpreter, str(script_path), *extra_args],
            cwd=str(BACKEND_DIR), capture_output=True, text=True, timeout=timeout,
        )
        dt = time.monotonic() - t0
        ok = proc.returncode == 0
        combined = (proc.stdout or "") + (proc.stderr or "")
        tail = "\n".join(combined.splitlines()[-15:])
        return {"name": name, "script": script, "ok": ok, "seconds": round(dt, 1),
                "returncode": proc.returncode, "tail": tail, "hint": None if ok else _hint_for(combined)}
    except subprocess.TimeoutExpired:
        dt = time.monotonic() - t0
        return {"name": name, "script": script, "ok": False, "seconds": round(dt, 1),
                "returncode": None, "tail": f"TIMED OUT after {timeout}s", "hint": None}
    except Exception as exc:
        return {"name": name, "script": script, "ok": False, "seconds": 0.0,
                "returncode": None, "tail": f"Failed to launch: {exc}", "hint": None}


def run_all(args, only: "set | None" = None, timeout: int = 3600, on_step=None) -> list:
    steps = ALL_STEPS if not only else [s for s in ALL_STEPS if s[0] in only]
    results = []
    for name, script, _venv, arg_builder in steps:
        extra_args = arg_builder(args)
        print(f"\n=== {name} ({script} {' '.join(extra_args)}) ===", flush=True)
        result = _run_one(name, script, extra_args, timeout)
        status = "OK" if result["ok"] else "FAILED"
        print(f"--- {name}: {status} ({result['seconds']}s) ---", flush=True)
        if not result["ok"]:
            print(result["tail"], flush=True)
            if result.get("hint"):
                print(f"  HINT: {result['hint']}", flush=True)
        results.append(result)
        if on_step:  # lets api/main.py stream progress instead of waiting for the whole batch
            on_step(result)
    return results


def case_counts() -> dict:
    """Cheap on-disk snapshot of what exists right now, per family --
    the generation-side counterpart to run_all_evaluations.py's
    scoreboard(). Counts JSON case files directly rather than trusting
    Supabase (which needs a successful backfill step to be current)."""
    repo_root = BACKEND_DIR.parent
    counts = {}
    attacks_dir = repo_root / "data" / "generated" / "attacks"
    if attacks_dir.exists():
        for split_dir in attacks_dir.iterdir():
            if not split_dir.is_dir():
                continue
            for family_dir in split_dir.iterdir():
                if not family_dir.is_dir():
                    continue
                key = family_dir.name
                counts.setdefault(key, {}).setdefault(split_dir.name, 0)
                counts[key][split_dir.name] = sum(1 for f in family_dir.glob("*.json") if not f.name.startswith("."))
    for extra_name, extra_dir in [
        ("voice_scam", repo_root / "data" / "generated" / "voice_attacks"),
        ("document_fraud", repo_root / "data" / "generated" / "document_attacks"),
        ("phishing_scam", repo_root / "data" / "generated" / "phishing_attacks"),
        ("video_kyc_impersonation", repo_root / "data" / "generated" / "video_kyc_attacks"),
    ]:
        if extra_dir.exists():
            n = sum(1 for f in extra_dir.rglob("*.json") if not f.name.startswith("."))
            if n:
                counts[extra_name] = {"total": n}
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", type=str, default=None,
                         help=f"Comma-separated step names to run ({', '.join(STEP_NAMES)}), default: all except adaptive_weakness_round")
    parser.add_argument("--n-per-family", type=int, default=50,
                         help="tabular_attacks: cases per family, per split portion (default 50 -- fast frontend-triggered refresh; use the script directly with --n-per-family 400+ for a full dataset build)")
    parser.add_argument("--n-per-split", type=int, default=10,
                         help="voice/document/phishing_attacks: cases per split portion (default 10)")
    parser.add_argument("--n-cases", type=int, default=None,
                         help="adaptive_weakness_round: cases for the round-2 mutation (default: that script's own default)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=int, default=3600, help="Per-step timeout in seconds (default 3600)")
    parser.add_argument("--json", action="store_true",
                         help="Also print a machine-readable JSON summary block, used by api/main.py")
    args = parser.parse_args()

    only = set(s.strip() for s in args.only.split(",")) if args.only else set(name for name, *_ in STEPS)
    unknown = only - set(STEP_NAMES)
    if unknown:
        print(f"Unknown step name(s): {', '.join(sorted(unknown))}. Valid: {', '.join(STEP_NAMES)}", file=sys.stderr)
        return 2

    results = run_all(args, only=only, timeout=args.timeout)
    counts = case_counts()
    summary = {
        "results": results,
        "n_ok": sum(1 for r in results if r["ok"]),
        "n_failed": sum(1 for r in results if not r["ok"]),
        "case_counts": counts,
    }

    print("\n\n==================== SUMMARY ====================")
    for r in results:
        print(f"  {'OK  ' if r['ok'] else 'FAIL'}  {r['name']:<24} {r['seconds']:>7.1f}s")
        if not r["ok"] and r.get("hint"):
            print(f"        -> {r['hint']}")
    print(f"\n{summary['n_ok']}/{len(results)} generation steps succeeded.")
    print("\nCurrent on-disk case counts:")
    for family, splits in counts.items():
        print(f"  {family:<28} {splits}")

    if args.json:
        print("\n===JSON_SUMMARY_START===")
        print(json.dumps(summary))
        print("===JSON_SUMMARY_END===")

    return 0 if summary["n_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
