"""
Red Team generator for the voice_scam family (Section 4a) -- the audio
counterpart to inject_attacks.py's four Phase 1 tabular families. Kept as
its own script rather than folded into inject_attacks.py because the
artifact shape is fundamentally different (an audio file + script text,
not a transaction_sequence) and because it needs Chatterbox/torch, which
the tabular families don't.

For each split_portion, samples n_per_split combinations from
evaluation/split_policy.py's voice_scam family, generates the scam script
text (deterministic -- scam_script_gen.py) and the audio (Chatterbox --
voice_gen.py: a LibriSpeech bonafide reference voice for "plain" cases, a
specific synthetic customer's own registered voice for "cloned_customer"
held-out cases), and writes one persistent JSON + WAV pair per case under
data/generated/voice_attacks/<split_portion>/<case_id>.{json,wav}
(Principle 8).

Customer Universe wiring (2026-08-30, Section 4b-i): loads the synthetic
customer roster (generate/synthetic_customers.py -- run that first) and
assigns each case a customer_id, round-robin across the roster. Every
"cloned_customer" case (100% of held_out, per split_policy.py's single
held_out combo) now clones THAT customer's own registered voice_ref
instead of drawing from the shared LibriSpeech bank -- this is the actual
voice-impersonation attack Section 4b-i describes, not a placeholder. This
supersedes generate_voice_attacks.py's original TODO ("that table has no
rows yet") -- resolved_levels still records voice_characteristics either
way, so which mode ran is always auditable from the case JSON.

Re-running this script after this change regenerates the full 80-case set
with new case_ids (old files are not overwritten -- clear
data/generated/voice_attacks/ first) and, because held_out is now cloning
a REAL registered voice rather than a generic one, held_out's recall
number from eval_voice_spoof.py is worth re-checking: whether spoof
detection holds up against a targeted clone of someone's own voice is a
meaningfully different (and more honest) question than against a clone of
an arbitrary LibriSpeech speaker.

NOT executable in the cloud sandbox this was authored in -- depends on
voice_gen.py (Chatterbox/torch) and librispeech_bonafide.py (datasets/
soundfile), neither installable there.

Usage:
    python backend/generate/generate_voice_attacks.py
    python backend/generate/generate_voice_attacks.py --n-per-split 20 --seed 42
"""

import argparse
import json
import os
import random
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# This script runs in its own throwaway venv (voice_gen_env, see
# requirements-voice-gen.txt) separate from the main `red` venv, so nothing
# has loaded backend/.env yet -- do it explicitly here, same convention as
# db/supabase_client.py, so the HF token reaches huggingface_hub's downloads
# (LibriSpeech + the Chatterbox checkpoint) instead of silently hitting
# anonymous rate limits.
from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND_DIR / ".env")

# .env stores the token as HUGGINGFACE_ACCESS_TOKEN (this project's own
# naming), but huggingface_hub only ever looks for HF_TOKEN or the legacy
# HUGGING_FACE_HUB_TOKEN -- neither of which load_dotenv() alone creates.
if not os.environ.get("HF_TOKEN") and os.environ.get("HUGGINGFACE_ACCESS_TOKEN"):
    os.environ["HF_TOKEN"] = os.environ["HUGGINGFACE_ACCESS_TOKEN"]

from evaluation.librispeech_bonafide import fetch_bonafide_clips  # noqa: E402
from evaluation.split_policy import SPLIT_PORTIONS, get_combination  # noqa: E402
from generate.artifact_generators.scam_script_gen import generate_scam_script  # noqa: E402
from generate.artifact_generators.voice_gen import VoiceGenerator  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
OUT_DIR = REPO_ROOT / "data" / "generated" / "voice_attacks"
BONAFIDE_DIR = REPO_ROOT / "data" / "generated" / "voice_bonafide"

FAMILY = "voice_scam"
DEFAULT_URGENCY = "high"  # used when a combo doesn't set urgency explicitly


def _resolve_defaults(combo: dict) -> dict:
    resolved = dict(combo)
    resolved.setdefault("urgency", DEFAULT_URGENCY)
    resolved.setdefault("voice_characteristics", "plain")
    return resolved


def _load_customer_roster() -> list:
    """Reads data/generated/synthetic_customers/*.json directly -- avoids
    importing generate.synthetic_customers here, which would pull in
    db.supabase_client (and its `supabase` package dependency) into this
    script's separate voice_gen_env venv unnecessarily. Same idempotent
    on-disk contract as synthetic_customers.load_roster()."""
    customers_dir = REPO_ROOT / "data" / "generated" / "synthetic_customers"
    paths = sorted(customers_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(
            f"No synthetic customer files under {customers_dir}. Run "
            f"generate/synthetic_customers.py first (main `red` venv, not voice_gen_env)."
        )
    return [json.loads(p.read_text()) for p in paths]


def _generate_case(combo: dict, split_portion: str, rng: random.Random,
                    voice_gen: VoiceGenerator, bonafide_paths: list, customer: dict) -> dict:
    resolved = _resolve_defaults(combo)
    case_id = f"{FAMILY}_{uuid.uuid4().hex[:12]}"

    script_text = generate_scam_script(resolved["script_type"], resolved["urgency"], rng)

    if resolved["voice_characteristics"] == "cloned_customer":
        # The actual voice-impersonation attack (Section 4b-i): clone this
        # specific customer's own registered reference voice.
        reference_wav = REPO_ROOT / customer["voice_ref"]
    else:
        reference_wav = rng.choice(bonafide_paths)

    out_wav = OUT_DIR / split_portion / f"{case_id}.wav"
    voice_gen.synthesize(text=script_text, speaker_wav_path=reference_wav, out_path=out_wav)

    case = {
        "case_id": case_id,
        "attack_family": FAMILY,
        "split_portion": split_portion,
        "mutation_params": combo,
        "resolved_levels": resolved,
        "signals_expected": ["voice"],
        "customer_id": customer["id"],
        "script_text": script_text,
        "audio_path": str(out_wav.relative_to(REPO_ROOT)),
        "reference_voice_path": str(Path(reference_wav).relative_to(REPO_ROOT))
                                 if Path(reference_wav).is_relative_to(REPO_ROOT) else str(reference_wav),
        "is_fraud": True,
    }
    return case


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-per-split", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)

    print("Fetching bonafide reference clips (LibriSpeech, cached after first run)...")
    bonafide_paths = fetch_bonafide_clips(BONAFIDE_DIR, n=max(40, args.n_per_split))
    print(f"  {len(bonafide_paths)} bonafide clips available")

    roster = _load_customer_roster()
    print(f"Loaded {len(roster)} synthetic customers")

    voice_gen = VoiceGenerator()

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
            case = _generate_case(combo, split_portion, rng, voice_gen, bonafide_paths, customer)
            case_path = split_dir / f"{case['case_id']}.json"
            case_path.write_text(json.dumps(case, indent=2))
            total += 1
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{args.n_per_split}")

    print(f"Done. {total} voice_scam cases written under {OUT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nVOICE GENERATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
