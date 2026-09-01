"""
Stage 4 of the training pipeline — synthetic attack injection (Red Team).

Generates attack cases for the four Phase 1 families (transaction_fraud,
account_takeover, synthetic_identity, mule_network), for both split
portions (train-allowed combinations vs. held-out-only combinations, per
evaluation/split_policy.py), validates each case (generate/validators.py),
and writes:

  - one persistent JSON artifact per case, under
    data/generated/attacks/<split_portion>/<family>/<case_id>.json
    (docs/TECHNICAL_SPEC.md Principle 8 -- every attack is inspectable, not
    just a derived score)
  - two flattened, model-ready parquet files --
    data/processed/attacks_train.parquet and attacks_held_out.parquet --
    one row per generated transaction, in the same canonical schema as
    defend/features/build_features.py's output (plus a few generated-only
    columns for signals neither real dataset carries) so Stage 5 can concat
    real + generated data directly.

  - mule_network rows additionally get real per-edge graph-topology
    features (degree, unique-counterparty count, pass-through ratio,
    in_port) computed from that case's own real generated graph
    (case["graph"]["edges"], 1:1 index-aligned with transaction_sequence --
    see artifact_generators/ring_gen.py). Column names match
    build_features.py's graph_src_*/graph_dst_*/graph_in_port so the two
    sources share one schema (docs/DATASETS.md, round-4 entry). Every other
    family gets NaN in these columns -- transaction_fraud, account_takeover
    and synthetic_identity are single-entity transaction sequences with no
    real multi-account graph structure (verified by reading
    artifact_generators/transaction_gen.py: synthetic_identity's "graph"
    signals_expected label is a conceptual signal-category tag, not a real
    generated graph payload).

Held-out cases are NOT used for training, ever -- they exist specifically
to be scored after the Blue Team is frozen (docs/TECHNICAL_SPEC.md Section
8, the adversarial evaluation protocol). Keeping them in a clearly separate
file rather than one combined file with a column flag is a deliberate
guardrail against a training script accidentally reading the wrong slice.

Usage:
    python backend/generate/inject_attacks.py
    python backend/generate/inject_attacks.py --n-per-family 500 --seed 42
    python backend/generate/inject_attacks.py --families transaction_fraud mule_network
"""

import argparse
import json
import random
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))  # so `evaluation.*` / `generate.*` resolve regardless of cwd

import pandas as pd  # noqa: E402

from evaluation.split_policy import FAMILIES, SPLIT_PORTIONS, get_combination, list_families  # noqa: E402

# The families mutation_engine.mutate() actually implements (its own
# if/elif chain, which raises KeyError for anything else). Kept here rather
# than inferred so adding a family to split_policy.FAMILIES can never again
# silently break this script's default run.
TABULAR_FAMILIES = ("transaction_fraud", "account_takeover", "synthetic_identity", "mule_network")
from generate import mutation_engine  # noqa: E402
from generate.artifact_generators import ring_gen, transaction_gen  # noqa: E402
from generate.validators import validate_case  # noqa: E402

PROCESSED_DIR = BACKEND_DIR.parent / "data" / "processed"
GENERATED_DIR = BACKEND_DIR.parent / "data" / "generated" / "attacks"
CUSTOMERS_DIR = BACKEND_DIR.parent / "data" / "generated" / "synthetic_customers"

CANONICAL_ROW_KEYS = [
    "amount", "log_amount", "hour_of_day", "oldbalance_orig", "newbalance_orig", "balance_delta_orig",
    "orig_balance_wiped", "dest_is_merchant", "dest_balance_delta", "txn_type", "card_type", "card_network",
    "product_cd", "identity_match_score", "entity_txn_count_so_far", "time_since_prev_txn_same_entity",
    "is_first_txn_for_entity", "source_dataset", "is_fraud",
]
EXTRA_COLUMNS = [
    "device_is_new", "location_is_trusted", "beneficiary_changed",
    "account_age_days", "device_history_count", "relationship_count", "behavior_pattern",
    "merchant_unusual", "ring_id", "hop_count", "shared_device", "distributed_beneficiaries", "timing_irregular",
    # 2026-08-31 (Phase 2.5): account_takeover-only, derived from the assigned
    # customer's own behavior_baseline -- see artifact_generators/transaction_gen.py's
    # _behavioral_country_channel(). NaN for every other family and for any case
    # generated without a customer, same "leave it null" convention as every other
    # entry in this list.
    "country", "channel",
]
# Per-row graph-topology features -- real for mule_network (from that case's
# own generated graph), NaN for every other family. Same column names as
# build_features.py's PaySim graph features (module docstring above).
GRAPH_COLUMNS = [
    "graph_src_out_degree", "graph_src_unique_out_counterparties", "graph_src_pass_through_ratio",
    "graph_dst_in_degree", "graph_dst_unique_in_counterparties", "graph_dst_pass_through_ratio",
    "graph_in_port",
]


def _pick_source_dataset(family: str, rng: random.Random) -> str:
    if family == "mule_network":
        return "paysim"  # see artifact_generators/ring_gen.py module docstring
    return rng.choice(["paysim", "ieee_cis"])


def _graph_features_for_case(case: dict) -> list[dict]:
    """Per-row graph-topology features for one case, index-aligned 1:1 with
    case["transaction_sequence"] (true for mule_network -- ring_gen.py
    builds `rows` and `graph.edges` in the same loop, same order, verified
    field-for-field; see docs/DATASETS.md). Returns all-None rows (one per
    transaction) for every family without a real "graph" key -- never
    fabricates a graph where the generator didn't build one.

    Formulas mirror build_features.py's _graph_topology_features exactly
    (out/in degree, unique counterparty count, pass-through ratio, in_port)
    so PaySim rows and generated mule_network rows share one schema.
    """
    n_rows = len(case["transaction_sequence"])
    edges = case.get("graph", {}).get("edges")
    if not edges:
        return [dict.fromkeys(GRAPH_COLUMNS) for _ in range(n_rows)]

    out_degree, out_amt, out_targets = {}, {}, {}
    in_degree, in_amt, in_sources = {}, {}, {}
    for e in edges:
        s, t, amt = e["source"], e["target"], e.get("amount", 0.0) or 0.0
        out_degree[s] = out_degree.get(s, 0) + 1
        out_amt[s] = out_amt.get(s, 0.0) + amt
        out_targets.setdefault(s, set()).add(t)
        in_degree[t] = in_degree.get(t, 0) + 1
        in_amt[t] = in_amt.get(t, 0.0) + amt
        in_sources.setdefault(t, set()).add(s)

    def pass_through(node):
        # Same formula as build_features.py's _graph_topology_features:
        # min(in, out) / max(in, out) when the node has both directions,
        # else 0.0 (pure source or pure sink).
        o, i = out_amt.get(node, 0.0), in_amt.get(node, 0.0)
        if out_degree.get(node, 0) == 0 or in_degree.get(node, 0) == 0:
            return 0.0
        return min(o, i) / max(o, i, 1e-6)

    dst_seen = {}
    rows = []
    for e in edges:
        s, t = e["source"], e["target"]
        rank = dst_seen.get(t, 0)
        rows.append({
            "graph_src_out_degree": float(out_degree.get(s, 0)),
            "graph_src_unique_out_counterparties": float(len(out_targets.get(s, ()))),
            "graph_src_pass_through_ratio": pass_through(s),
            "graph_dst_in_degree": float(in_degree.get(t, 0)),
            "graph_dst_unique_in_counterparties": float(len(in_sources.get(t, ()))),
            "graph_dst_pass_through_ratio": pass_through(t),
            "graph_in_port": float(rank),
        })
        dst_seen[t] = rank + 1
    return rows


def _flatten_case(case: dict) -> list[dict]:
    flat_rows = []
    graph_feats = _graph_features_for_case(case)
    for row, gfeat in zip(case["transaction_sequence"], graph_feats):
        flat = {k: row.get(k) for k in CANONICAL_ROW_KEYS}
        flat["case_id"] = case["case_id"]
        flat["attack_family"] = case["attack_family"]
        flat["split_portion"] = case["split_portion"]
        # 2026-08-31 (Phase 2.5): customer_id rides along per-row the same way
        # case_id/attack_family/split_portion already do (NOT through
        # EXTRA_COLUMNS/extra_fields -- it's a case-identity field, generated by
        # ring_gen.py/transaction_gen.py at the case's top level, not inside
        # extra_fields). NaN on real PaySim/IEEE-CIS rows and on any case
        # generated without a customer -- same "leave it null" convention as
        # every EXTRA_COLUMNS entry. Never fed into TabularPreprocessor as a
        # model feature (see evaluation/eval_behavioral_adjustment.py) -- purely
        # metadata for the post-hoc behavioral adjustment layer.
        flat["customer_id"] = case.get("customer_id")
        extra = case.get("extra_fields", {})
        for k in EXTRA_COLUMNS:
            flat[k] = extra.get(k)
        flat.update(gfeat)
        flat_rows.append(flat)
    return flat_rows


def _load_customer_roster() -> list:
    """Same on-disk contract as generate_voice_attacks.py's / generate_video_
    kyc_attacks.py's own roster loaders -- reads JSON directly, no Supabase
    import needed just to assign a customer_id. Returns [] (not an error) if
    the roster hasn't been generated yet -- customer_id then stays None on
    every case, exactly the old behavior, so this is backward compatible for
    anyone who hasn't run generate/synthetic_customers.py."""
    if not CUSTOMERS_DIR.exists():
        return []
    paths = sorted(CUSTOMERS_DIR.glob("*.json"))
    return [json.loads(p.read_text()) for p in paths]


def generate_family(family: str, split_portion: str, n: int, rng: random.Random, stats: dict,
                     roster: list, customer_counter: list) -> list[dict]:
    cases = []
    for _ in range(n):
        source_dataset = _pick_source_dataset(family, rng)
        combo = get_combination(family, split_portion, rng)
        spec = mutation_engine.resolve_params(family, combo, source_dataset, stats)
        # Round-robin across the whole run (customer_counter is a shared
        # single-element list, mutated across every family/split_portion call --
        # same convention generate_voice_attacks.py uses) so customers get an
        # even mix of attack families rather than each family reusing the same
        # few customers.
        customer = None
        if roster:
            customer = roster[customer_counter[0] % len(roster)]
            customer_counter[0] += 1
        if family == "mule_network":
            case = ring_gen.generate_case(split_portion, spec, rng, customer)
        else:
            case = transaction_gen.generate_case(family, split_portion, spec, rng, customer)
        validate_case(case)
        cases.append(case)
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-per-family", type=int, default=400,
                         help="Cases generated per family, per split portion (default 400).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--families", nargs="*", default=None,
                         help="Subset of families to generate (default: all Phase 1 families).")
    args = parser.parse_args()

    # This script generates TABULAR attack families only -- the ones
    # mutation_engine.mutate() has real mutation logic for. The other three
    # families in split_policy.FAMILIES (voice_scam, document_fraud,
    # phishing_scam) are media families with their own generators
    # (generate_voice_attacks.py / generate_document_attacks.py /
    # generate_phishing_attacks.py), and always had.
    #
    # Defaulting to list_families() was correct when split_policy only held
    # the four Phase 1 families. Once Phase 2 added the media families to
    # that same dict, this default silently started asking mutation_engine
    # for logic that does not exist, and the run died with
    # `KeyError: "No mutation logic for family 'voice_scam'"` -- AFTER
    # generating all four tabular families, so the per-case JSON was written
    # but attacks_train/held_out.parquet, which is written at the end, was
    # not. That is why eval_behavioral_adjustment then failed with "1600
    # account_takeover rows but NONE carry a customer_id": it was reading a
    # parquet from before the identity-linkage change, because the run that
    # should have replaced it crashed one step short.
    families = args.families or list_families()
    unknown = set(families) - set(FAMILIES.keys())
    if unknown:
        raise SystemExit(f"Unknown families: {unknown}. Known: {list_families()}")
    non_tabular = [f for f in families if f not in TABULAR_FAMILIES]
    if args.families and non_tabular:
        raise SystemExit(
            f"{non_tabular} are media families, not tabular ones -- this script has no mutation "
            f"logic for them. Generate them with their own scripts: voice_scam -> "
            f"generate_voice_attacks.py, document_fraud -> generate_document_attacks.py, "
            f"phishing_scam -> generate_phishing_attacks.py."
        )
    if non_tabular:
        print(f"Skipping non-tabular families {non_tabular} -- they have their own generators.")
        families = [f for f in families if f in TABULAR_FAMILIES]

    rng = random.Random(args.seed)
    print("Loading reference stats (amount/gap quantiles from real legitimate transactions)...")
    stats = mutation_engine.load_reference_stats()

    # 2026-08-31 (Phase 2.5): identity-family linkage. Empty roster (not
    # generated yet) degrades gracefully to the old behavior -- every case
    # gets customer_id=None, same as before this change.
    roster = _load_customer_roster()
    if roster:
        print(f"Loaded {len(roster)} synthetic customers -- assigning customer_id round-robin across all cases")
    else:
        print(f"No synthetic customer roster found under {CUSTOMERS_DIR} -- run generate/synthetic_customers.py "
              f"first for identity-family linkage (behavioral_adjustment evidence-gating needs it). "
              f"Continuing without it: every case gets customer_id=None, same as before.")
    customer_counter = [0]  # shared mutable counter, see generate_family()

    all_flat_rows = {"train": [], "held_out": []}
    manifest = {"n_per_family": args.n_per_family, "seed": args.seed, "counts": {}}

    for family in families:
        for split_portion in SPLIT_PORTIONS:
            print(f"Generating {args.n_per_family} '{family}' cases ({split_portion})...")
            cases = generate_family(family, split_portion, args.n_per_family, rng, stats, roster, customer_counter)

            out_dir = GENERATED_DIR / split_portion / family
            out_dir.mkdir(parents=True, exist_ok=True)
            for case in cases:
                (out_dir / f"{case['case_id']}.json").write_text(json.dumps(case, indent=2))
                all_flat_rows[split_portion].extend(_flatten_case(case))

            manifest["counts"].setdefault(family, {})[split_portion] = len(cases)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for split_portion in SPLIT_PORTIONS:
        df = pd.DataFrame(all_flat_rows[split_portion])
        out_path = PROCESSED_DIR / f"attacks_{split_portion}.parquet"
        df.to_parquet(out_path, index=False)
        print(f"Wrote {len(df):,} rows ({df['case_id'].nunique():,} cases) to {out_path}")

    manifest_path = PROCESSED_DIR / "attacks_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest: {manifest_path}")
    print(f"Per-case JSON artifacts: {GENERATED_DIR}")
    print("\nDone. Next: train/validation split + XGBoost/LightGBM/Autoencoder training (Stage 5, coming next turn).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nATTACK INJECTION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
