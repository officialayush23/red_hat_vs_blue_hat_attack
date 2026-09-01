"""
One-time (but idempotent, re-runnable) loader: reads the Stage 4 generated
attack case artifacts already on disk (data/generated/attacks/**/*.json,
produced by generate/inject_attacks.py) and upserts them into the
`attack_cases` table (backend/db/migrations/001_core_schema.sql), so the
Supabase-backed API has real data to serve instead of an empty table.

Every generated case is fraud by construction (dataset.py's docstring:
generated rows are 100% fraud), so is_fraud is always True here -- this
script never invents a label, it reflects what inject_attacks.py already
guaranteed.

Safe to re-run after generating more cases (upsert on `id` / case_id) --
existing rows just get overwritten with identical data, nothing duplicates.

Usage:
    python backend/db/backfill_attack_cases.py
    python backend/db/backfill_attack_cases.py --batch-size 250
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from db.supabase_client import get_service_client  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
ATTACKS_DIR = REPO_ROOT / "data" / "generated" / "attacks"


def _load_case(path: Path) -> dict:
    raw = json.loads(path.read_text())
    return {
        "id": raw["case_id"],
        "attack_family": raw["attack_family"],
        # mutation_params in storage = mutation_params + resolved_levels + extra_fields
        # merged, so nothing from the generator is lost even though the DB
        # column list only names the top-level fields explicitly.
        "mutation_params": {
            **raw.get("mutation_params", {}),
            "resolved_levels": raw.get("resolved_levels", {}),
            "extra_fields": raw.get("extra_fields", {}),
        },
        "split_portion": raw["split_portion"],
        "signals_expected": raw.get("signals_expected", []),
        "source_dataset": raw.get("source_dataset"),
        "is_fraud": True,  # every generated case is fraud by construction
        # Phase 2.5 (2026-08-31): real linkage now -- inject_attacks.py assigns a
        # customer round-robin per case. Still None for any case generated before
        # this change, or if generate/synthetic_customers.py's roster didn't exist
        # yet when inject_attacks.py ran -- both degrade gracefully, not an error.
        "customer_id": raw.get("customer_id"),
        "transaction_sequence": raw.get("transaction_sequence"),
        # mule_network cases carry a real networkx graph (nodes/edges/hop/amount) from
        # ring_gen.py -- previously dropped here even though it was already being generated;
        # persisted now so Task #33's GNN has real graph-structured training data in the DB,
        # not just on-disk JSON. Other families still have no artifacts yet (Phase 2).
        "artifacts": {"graph": raw["graph"]} if "graph" in raw else {},
        "generated_by": "deterministic_v1",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()

    if not ATTACKS_DIR.exists():
        # Not an error. This script covers the four TABULAR families only;
        # an environment that pulled just the media bundles (a Colab runtime
        # doing the document or voice evaluation, say) legitimately has no
        # data/generated/attacks/ at all. Hard-failing there marked the whole
        # generation pipeline FAILED and, worse, aborted before
        # backfill_phase2_artifacts could run -- so the media backfill that
        # the run actually needed never happened.
        print(f"{ATTACKS_DIR} not present -- no tabular cases to backfill on this machine. "
              "Skipping (run generate/inject_attacks.py if you expected tabular data here).")
        return

    paths = sorted(ATTACKS_DIR.glob("*/*/*.json"))
    print(f"Found {len(paths):,} generated case files under {ATTACKS_DIR}")
    if not paths:
        print("Nothing to backfill.")
        return

    client = get_service_client()
    total = 0
    for i in range(0, len(paths), args.batch_size):
        batch_paths = paths[i:i + args.batch_size]
        rows = [_load_case(p) for p in batch_paths]
        client.table("attack_cases").upsert(rows, on_conflict="id").execute()
        total += len(rows)
        print(f"  upserted {total:,} / {len(paths):,}")

    print(f"Done. {total:,} attack_cases rows upserted.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nBACKFILL FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
