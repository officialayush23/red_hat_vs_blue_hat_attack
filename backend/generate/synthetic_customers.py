"""
Synthetic Customer Vault (docs/TECHNICAL_SPEC.md Section 4b-i) -- generates
a small, fixed roster of synthetic (never real) customer identities that
anchor the identity-impersonation families: voice_scam's cloned_customer
mode clones THIS customer's own registered voice_ref rather than a generic
LibriSpeech clip, and document_fraud's beneficiary tampering is judged
against a customer's own trusted_beneficiaries rather than in a vacuum.

This table (public.synthetic_customers) and the attack_cases.customer_id
FK have existed in the schema since Phase 1.5 (backend/db/migrations/
001_core_schema.sql) -- both generate_voice_attacks.py and
generate_document_attacks.py already had TODO comments pointing at this
exact gap ("that table has no rows yet"). This script is what closes it.

No real PII anywhere: names are invented (first/last name pools, not drawn
from or matched against any real-person database), the synthetic KYC ID
is a made-up CUST-###### format deliberately NOT shaped like a real
Aadhaar (12 digits) or PAN (5 letters+4 digits+1 letter) so it can't be
mistaken for one, and voice_ref points at our own already-fetched
LibriSpeech bonafide clips (public-domain, used here only as an audio
sample, not tied to any claim about who that speaker actually is).
photo_ref/video_ref are left null -- KYC photo/face and video-KYC
impersonation stay research-tier per Section 4c, not built here.

behavior_baseline (added 2026-08-30, Principle 14 groundwork): each
customer's normal amount/country/channel/hour ranges, primarily for
mule_network and account_takeover deviation features -- those two
families are fundamentally "is this typical for this customer" problems,
unlike phishing (a content-manipulation problem) where behavioral context
adds little. Deliberately includes an "occasional" (rare but legitimate)
range alongside each "normal" one: a customer who NEVER transacts above
₹2,000, from a device we've NEVER seen, at 2am, would make any deviation
trivially "weird = fraud" -- real customers travel, use a new laptop
occasionally, or pay a big one-off bill at midnight, and an attack has to
hide inside that same envelope of plausible behavior, not just anything
that isn't the single average case, or a held-out evaluation against this
data would be trivially easy in a way that doesn't reflect the real
problem.

Reads bonafide clips directly off disk (no `datasets`/`soundfile` import)
so this script only needs `supabase`+`python-dotenv` and runs fine in the
main `red` venv -- no need for the separate voice_gen_env.

Writes one JSON per customer under data/generated/synthetic_customers/ AND
upserts into the `synthetic_customers` Supabase table. Idempotent --
re-running regenerates the same roster deterministically (seeded) and
upserts on `id`.

Usage:
    python backend/generate/synthetic_customers.py
"""

import json
import random
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from evaluation.librispeech_bonafide import MIN_DURATION_SEC, _duration_sec  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
OUT_DIR = REPO_ROOT / "data" / "generated" / "synthetic_customers"
BONAFIDE_DIR = REPO_ROOT / "data" / "generated" / "voice_bonafide"

N_CUSTOMERS = 12
SEED = 42

FIRST_NAMES = ["Priya", "Arjun", "Meera", "Kabir", "Ananya", "Rohan",
               "Ishita", "Vikram", "Neha", "Aditya", "Simran", "Karan"]
LAST_NAMES = ["Mehta", "Sharma", "Nair", "Iyer", "Kapoor", "Reddy",
              "Chatterjee", "Bose", "Malhotra", "Rao", "Sethi", "Verma"]

# Matches document_gen.BENEFICIARY_NAMES -- a customer's trusted vendors are
# drawn from the same pool document_fraud invoices use as sellers, so
# "beneficiary tampered away from a trusted vendor" is a coherent story.
VENDOR_NAMES = [
    "Meridian Supply Co.", "Northgate Logistics Ltd.", "Aravalli Traders",
    "Blue Harbor Imports", "Silverline Facilities", "Kestrel & Sons",
    "Coral Bay Distributors", "Ashford Manufacturing", "Vantage Point LLC",
    "Riverside Wholesale Group",
]

DEVICE_TYPES = ["iPhone 14", "Samsung Galaxy S23", "Pixel 8", "iPad Air", "Windows Laptop"]

# behavior_baseline pools -- see module docstring for why "occasional" ranges exist.
CHANNEL_POOL = ["mobile_app", "netbanking", "bank_email", "sms", "atm"]
OCCASIONAL_CHANNELS = ["laptop_web", "phone_call_ivr"]
OCCASIONAL_COUNTRIES = ["SG", "AE", "GB", "US"]  # plausible travel/NRI-relative destinations, not exotic


def _synthetic_kyc_id(rng: random.Random) -> str:
    return f"CUST-{rng.randint(100000, 999999)}"


def baseline_for_customer_id(customer_id: str) -> dict:
    """Deterministic baseline for an EXISTING customer, keyed off their id.

    2026-09-01. behavioral_adjustment() was a measured no-op: its evidence-gate
    run reported n_corroborated=0, n_discounted=0, n_unchanged=2000, and the
    baseline/adjusted metric blocks were bit-identical to the last decimal.
    The cause was not the logic -- it was that every customer file under
    data/generated/synthetic_customers/ carried metadata = {name,
    trusted_beneficiaries} and NO behavior_baseline, so the function took its
    "no behavior_baseline available for this customer" early return 2000 times
    out of 2000. The roster on disk predates the 2026-08-30 commit that added
    _generate_behavior_baseline(), and a storage_sync pull restored those older
    files on top.

    Re-running build_roster() is NOT the fix. It mints 12 customers off one
    seeded RNG stream, while the roster on disk holds 21 (an earlier run used a
    different N_CUSTOMERS) and data/processed/*.parquet references all 21 by
    customer_id. Regenerating would leave 9 of them without a baseline, and any
    future change to the draw order would renumber everyone and break the
    linkage that inject_attacks.py already wrote into the parquets.

    So the baseline is derived from the customer's OWN id instead of from a
    position in a shared stream. Same customer -> same baseline, on any machine,
    in any order, however many customers exist. Nothing else about the roster
    moves."""
    return _generate_behavior_baseline(random.Random(f"{SEED}:{customer_id}"))


def _generate_behavior_baseline(rng: random.Random) -> dict:
    """Summary-statistic baseline, not a transaction log -- mule_network's
    actual account/beneficiary graph topology is built in generate_mule_
    attacks.py (Task #33), not fabricated here. This is the reference state
    a deviation feature compares an observed event against: 'this transfer
    target is outside the customer's usual N regular beneficiaries', 'this
    login hour is outside their normal window', etc."""
    normal_low = rng.randint(500, 2000)
    normal_high = rng.randint(normal_low + 3000, normal_low + 10000)
    occasional_high = rng.randint(normal_high * 4, normal_high * 10)
    normal_channels = rng.sample(CHANNEL_POOL, k=rng.randint(2, 3))
    occasional_channel_pool = [c for c in CHANNEL_POOL + OCCASIONAL_CHANNELS if c not in normal_channels]
    login_start = rng.randint(6, 9)
    login_end = rng.randint(20, 23)
    occasional_hour = rng.choice(list(range(0, 6)) + [23])
    return {
        "normal_amount_range": [normal_low, normal_high],
        "occasional_amount_range": [normal_high, occasional_high],  # rare but legitimate -- rent, tuition, an appliance
        "normal_countries": ["IN"],
        "occasional_countries": [rng.choice(OCCASIONAL_COUNTRIES)],  # rare travel -- legitimate, not a red flag alone
        "normal_channels": normal_channels,
        "occasional_channels": [rng.choice(occasional_channel_pool)],
        "normal_login_hour_range": [login_start, login_end],
        "occasional_login_hours": [occasional_hour],  # rare late-night use -- shift work, insomnia, real and legitimate
        "normal_beneficiary_count": rng.randint(2, 6),  # distinct regular payees per month
        "normal_monthly_transfer_count": rng.randint(3, 15),
    }


def _generate_customer(idx: int, rng: random.Random, bonafide_paths: list) -> dict:
    name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
    voice_ref_path = bonafide_paths[idx % len(bonafide_paths)]
    voice_ref = (
        str(voice_ref_path.relative_to(REPO_ROOT))
        if voice_ref_path.is_relative_to(REPO_ROOT) else str(voice_ref_path)
    )
    trusted = rng.sample(VENDOR_NAMES, k=2)
    devices = [
        {"device": rng.choice(DEVICE_TYPES), "first_seen_days_ago": rng.randint(90, 900), "trusted": True}
        for _ in range(rng.randint(1, 2))
    ]
    return {
        "id": _synthetic_kyc_id(rng),
        "kyc_document_ref": None,   # synthetic KYC document imagery -- deferred, docs/FUTURE_INTEGRATIONS.md
        "photo_ref": None,          # KYC photo/face impersonation stays research-tier, Section 4c
        "voice_ref": voice_ref,
        "video_ref": None,          # video-KYC stays research-spike, Section 4c
        "device_history": devices,
        "account_age_days": rng.randint(120, 2500),
        "relationship_count": rng.randint(1, 8),
        "metadata": {
            "name": name,
            "trusted_beneficiaries": trusted,
            "behavior_baseline": _generate_behavior_baseline(rng),
        },
    }


def usable_voice_refs() -> list:
    """Bonafide clips long enough to be a voice-cloning reference.

    2026-09-02: build_roster used a bare glob here, so two customers were
    assigned 4.82s clips and generate_voice_attacks.py died mid-run on
    Chatterbox's own precondition:

        AssertionError: Audio prompt must be longer than 5 seconds!

    fetch_bonafide_clips() already enforces MIN_DURATION_SEC and deliberately
    LEAVES the too-short clips on disk keeping their index ("never
    overwrite/reuse indices already on disk (incl. too-short ones)"), so a
    bare glob over the directory picks up exactly the files that function
    went out of its way to exclude. Reuse its threshold rather than declaring
    a second one that can drift from it.

    Selection is by index, not by rng draw, so filtering this list does not
    perturb the seeded rng and every customer keeps its existing id."""
    paths = sorted(
        p for p in BONAFIDE_DIR.glob("librispeech_bonafide_*.wav")
        if _duration_sec(p) >= MIN_DURATION_SEC
    )
    if not paths:
        raise FileNotFoundError(
            f"No bonafide clips >= {MIN_DURATION_SEC}s under {BONAFIDE_DIR}. Run "
            f"generate/generate_voice_attacks.py first (it fetches these as a side effect)."
        )
    return paths


def build_roster(n: int = N_CUSTOMERS, seed: int = SEED) -> list:
    rng = random.Random(seed)
    return [_generate_customer(i, rng, usable_voice_refs()) for i in range(n)]


def repair_voice_refs() -> list:
    """Reassign only the voice_refs that are missing or too short, in place.

    A full regenerate would be wrong: the roster's ids are already the
    customer_id on 20k+ attack_cases rows. This keeps every id and touches
    only the broken field."""
    roster = load_roster()
    usable = usable_voice_refs()
    repaired = 0
    for idx, customer in enumerate(sorted(roster, key=lambda c: c["id"])):
        ref = customer.get("voice_ref")
        local = REPO_ROOT / ref.replace("\\", "/") if ref else None
        ok = bool(local and local.exists() and _duration_sec(local) >= MIN_DURATION_SEC)
        if ok:
            continue
        chosen = usable[idx % len(usable)]
        customer["voice_ref"] = (
            str(chosen.relative_to(REPO_ROOT)) if chosen.is_relative_to(REPO_ROOT) else str(chosen)
        ).replace("\\", "/")
        (OUT_DIR / f"{customer['id']}.json").write_text(json.dumps(customer, indent=2))
        print(f"  {customer['id']}: {ref} -> {customer['voice_ref']} "
              f"({_duration_sec(chosen):.2f}s)")
        repaired += 1
    print(f"voice_ref: {repaired} repaired, {len(roster) - repaired} already usable "
          f"({len(roster)} customers total)")
    return roster


def load_roster() -> list:
    """Reads the already-generated roster from disk -- used by
    generate_voice_attacks.py / generate_document_attacks.py so they don't
    need Supabase access just to assign a customer_id. Run this module's
    __main__ first."""
    # tools/storage_sync.py drops a `.storage_bundle.json` marker into every
    # directory it manages, INCLUDING this one. A bare *.json glob picks it up
    # and hands callers a dict with no "id" and no "metadata" -- a phantom
    # 22nd customer that inject_attacks.py would happily round-robin a real
    # case onto. Anything starting with a dot is infrastructure, not a customer.
    paths = sorted(p for p in OUT_DIR.glob("*.json") if not p.name.startswith("."))
    if not OUT_DIR.exists() or not paths:
        raise FileNotFoundError(f"No customer files under {OUT_DIR}. Run generate/synthetic_customers.py first.")
    return [json.loads(p.read_text()) for p in paths]


def backfill_baselines() -> list:
    """Add behavior_baseline to every roster file that lacks one, in place.

    Idempotent and id-preserving -- see baseline_for_customer_id(). Returns the
    full roster so main() can upsert it."""
    roster = load_roster()
    added = 0
    for customer in roster:
        meta = customer.setdefault("metadata", {})
        if meta.get("behavior_baseline"):
            continue
        meta["behavior_baseline"] = baseline_for_customer_id(customer["id"])
        (OUT_DIR / f"{customer['id']}.json").write_text(json.dumps(customer, indent=2))
        added += 1
    print(f"behavior_baseline: {added} added, {len(roster) - added} already present "
          f"({len(roster)} customers total)")
    return roster


def main() -> None:
    from db.supabase_client import get_service_client

    if "--repair-voice-refs" in sys.argv:
        # Repair path: keep every existing customer id (they are the
        # customer_id on 20k+ attack_cases rows), fix only broken voice_refs.
        roster = repair_voice_refs()
        client = get_service_client()
        client.table("synthetic_customers").upsert(roster, on_conflict="id").execute()
        print(f"Upserted {len(roster)} rows into Supabase synthetic_customers")
        return

    if "--backfill-baselines" in sys.argv:
        # Repair path: keep every existing customer id and every parquet
        # linkage, just fill in the field behavioral_adjustment() needs.
        roster = backfill_baselines()
        client = get_service_client()
        client.table("synthetic_customers").upsert(roster, on_conflict="id").execute()
        print(f"Upserted {len(roster)} rows into Supabase synthetic_customers")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    roster = build_roster()
    for customer in roster:
        (OUT_DIR / f"{customer['id']}.json").write_text(json.dumps(customer, indent=2))
    print(f"Wrote {len(roster)} synthetic customer profiles to {OUT_DIR}")

    client = get_service_client()
    client.table("synthetic_customers").upsert(roster, on_conflict="id").execute()
    print(f"Upserted {len(roster)} rows into Supabase synthetic_customers")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nSYNTHETIC CUSTOMER GENERATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
