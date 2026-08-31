"""
Red Team generator for the document_fraud family (Section 4a) -- the
invoice/QR counterpart to generate_voice_attacks.py's voice_scam script.
Same reasons for a standalone script apply: the artifact shape (an image +
structured field data, not a transaction_sequence) is fundamentally
different from the Phase 1 tabular families.

For each split_portion, samples n_per_split combinations from
evaluation/split_policy.py's document_fraud family, generates a tampered
invoice image via document_gen.py, and writes one persistent JSON + PNG
pair per case under
data/generated/document_attacks/<split_portion>/<case_id>.{json,png}
(Principle 8). Also (re)generates the bonafide (fully consistent) bank
under data/generated/document_bonafide/ as a side effect.

Customer Universe wiring (2026-08-30, Section 4b-i): loads the synthetic
customer roster (generate/synthetic_customers.py -- run that first) and
assigns each case a customer_id, round-robin across the roster. Unless the
combo tampers "beneficiary", the invoice's seller is drawn from that
customer's own trusted_beneficiaries, so "beneficiary tampered" concretely
means "payment redirected away from a vendor this customer actually
trusts" rather than an artifact scored with no identity context.

Usage:
    python backend/generate/generate_document_attacks.py
    python backend/generate/generate_document_attacks.py --n-per-split 20 --seed 42
"""

import argparse
import json
import random
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from evaluation.split_policy import SPLIT_PORTIONS, get_combination  # noqa: E402
from generate.artifact_generators.document_gen import (  # noqa: E402
    generate_bonafide_documents,
    generate_invoice,
)
from generate.synthetic_customers import load_roster  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
OUT_DIR = REPO_ROOT / "data" / "generated" / "document_attacks"
BONAFIDE_DIR = REPO_ROOT / "data" / "generated" / "document_bonafide"

FAMILY = "document_fraud"


def _combo_to_tamper_dims(combo: dict) -> set:
    """combo is e.g. {"amount": "tampered", "qr_payload": "tampered"} --
    every key present in a document_fraud combo means "tampered" (there's
    no other value in this family's dimensions), so the dict's keys ARE
    the tamper set."""
    return set(combo.keys())


def _generate_case(combo: dict, split_portion: str, rng: random.Random, customer: dict) -> dict:
    case_id = f"{FAMILY}_{uuid.uuid4().hex[:12]}"
    tamper_dims = _combo_to_tamper_dims(combo)

    out_png = OUT_DIR / split_portion / f"{case_id}.png"
    result = generate_invoice(
        tamper_dims=tamper_dims, rng=rng, out_path=out_png,
        customer_name=customer["metadata"]["name"],
        trusted_beneficiaries=customer["metadata"]["trusted_beneficiaries"],
    )

    case = {
        "case_id": case_id,
        "attack_family": FAMILY,
        "split_portion": split_portion,
        "mutation_params": combo,
        "resolved_levels": {"tampered_fields": result["tampered_fields"]},
        "signals_expected": ["document"],
        "customer_id": customer["id"],
        "printed_fields": result["printed"],
        "qr_payload": result["qr_payload"],
        "image_path": str(Path(result["image_path"]).relative_to(REPO_ROOT)),
        "is_fraud": True,
    }
    return case


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-per-split", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    roster = load_roster()
    print(f"Loaded {len(roster)} synthetic customers")

    print("Generating bonafide (fully consistent) reference invoices...")
    bonafide_paths = generate_bonafide_documents(BONAFIDE_DIR, n=max(40, args.n_per_split), seed=args.seed)
    print(f"  {len(bonafide_paths)} bonafide documents available")

    total = 0
    customer_idx = 0
    for split_portion in SPLIT_PORTIONS:
        split_dir = OUT_DIR / split_portion
        split_dir.mkdir(parents=True, exist_ok=True)
        print(f"Generating {args.n_per_split} {FAMILY} cases ({split_portion})...")
        for i in range(args.n_per_split):
            combo = get_combination(FAMILY, split_portion, rng)
            customer = roster[customer_idx % len(roster)]
            customer_idx += 1
            case = _generate_case(combo, split_portion, rng, customer)
            case_path = split_dir / f"{case['case_id']}.json"
            case_path.write_text(json.dumps(case, indent=2))
            total += 1
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{args.n_per_split}")

    print(f"Done. {total} document_fraud cases written under {OUT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nDOCUMENT GENERATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
