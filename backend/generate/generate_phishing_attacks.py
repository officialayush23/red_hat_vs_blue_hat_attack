"""
Red Team generator for the phishing_scam family (Section 4a) -- the
text-message counterpart to generate_voice_attacks.py (voice_scam) and
generate_document_attacks.py (document_fraud). Artifact shape here is the
simplest of the three: no audio/image file, just structured message
text -- so, unlike those two, the case JSON *is* the artifact, there's no
separate media file to write.

For each split_portion, samples n_per_split combinations from
evaluation/split_policy.py's phishing_scam family, generates the message
text via phishing_text_gen.py, and writes one persistent JSON per case
under data/generated/phishing_attacks/<split_portion>/<case_id>.json
(Principle 8). Also (re)generates a bonafide (legitimate-looking) message
bank under data/generated/phishing_bonafide/ as a side effect -- kept
separate from difraud/difraud's own non-deceptive rows (which
train_phishing_classifier.py trains on) so the evidence-gate eval never
scores the classifier against data it was trained on.

Customer Universe wiring (Section 4b-i): loads the synthetic customer
roster (generate/synthetic_customers.py -- run that first) and assigns
each case a customer_id, round-robin across the roster, so the greeting
line addresses that customer by name -- a targeted/spear-phishing shape
rather than a generic blast, and consistent with how document_fraud and
voice_scam anchor their artifacts to a specific synthetic identity.

Usage:
    python backend/generate/generate_phishing_attacks.py
    python backend/generate/generate_phishing_attacks.py --n-per-split 20 --seed 42
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
from generate.artifact_generators.phishing_text_gen import (  # noqa: E402
    CHANNELS,
    generate_bonafide_message,
    generate_phishing_message,
)
from generate.synthetic_customers import load_roster  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
OUT_DIR = REPO_ROOT / "data" / "generated" / "phishing_attacks"
BONAFIDE_DIR = REPO_ROOT / "data" / "generated" / "phishing_bonafide"

FAMILY = "phishing_scam"
DEFAULT_LANGUAGE = "english"  # used when a combo doesn't set language explicitly


def _resolve_defaults(combo: dict) -> dict:
    resolved = dict(combo)
    resolved.setdefault("language", DEFAULT_LANGUAGE)
    return resolved


def _generate_case(combo: dict, split_portion: str, rng: random.Random, customer: dict) -> dict:
    resolved = _resolve_defaults(combo)
    case_id = f"{FAMILY}_{uuid.uuid4().hex[:12]}"

    message = generate_phishing_message(
        impersonation_target=resolved["impersonation_target"],
        urgency=resolved["urgency"],
        channel=resolved["channel"],
        language=resolved["language"],
        rng=rng,
        customer_name=customer["metadata"]["name"],
    )

    case = {
        "case_id": case_id,
        "attack_family": FAMILY,
        "split_portion": split_portion,
        "mutation_params": combo,
        "resolved_levels": resolved,
        "signals_expected": ["text"],
        "customer_id": customer["id"],
        **message,
        "is_fraud": True,
    }
    return case


def generate_bonafide_messages(out_dir: Path, n: int, seed: int, roster: list) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed + 1)  # offset from the attack-case seed, same convention as document_gen/librispeech_bonafide
    paths = []
    for i in range(n):
        channel = CHANNELS[i % len(CHANNELS)]
        customer = roster[i % len(roster)]
        message = generate_bonafide_message(channel, rng, customer_name=customer["metadata"]["name"])
        record = {
            "case_id": f"phishing_bonafide_{i:03d}",
            "customer_id": customer["id"],
            **message,
            "is_fraud": False,
        }
        path = out_dir / f"phishing_bonafide_{i:03d}.json"
        path.write_text(json.dumps(record, indent=2))
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-per-split", type=int, default=100)  # bumped from 40 on 2026-08-30 for statistical power
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    roster = load_roster()
    print(f"Loaded {len(roster)} synthetic customers")

    print("Generating bonafide (legitimate-looking) reference messages...")
    bonafide_paths = generate_bonafide_messages(BONAFIDE_DIR, n=max(40, args.n_per_split), seed=args.seed, roster=roster)
    print(f"  {len(bonafide_paths)} bonafide messages available")

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

    print(f"Done. {total} phishing_scam cases written under {OUT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nPHISHING GENERATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
