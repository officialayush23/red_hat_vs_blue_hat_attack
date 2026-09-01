"""
Phase 2.5 (Task #32) -- uploads the Phase 2 attack artifacts (document
images, voice clips) to Supabase Storage's `attack-artifacts` bucket, and
backfills attack_cases for document_fraud, voice_scam, and phishing_scam --
both the attack cases AND their bonafide/negative-class counterparts (so
the evidence viewer has both fraud and legitimate examples to show, not
just fraud cases).

Extends backfill_attack_cases.py (which only covers Phase 1's
transaction-family cases from inject_attacks.py) -- kept as a separate
script rather than folded into that one, since these three families have
real binary artifacts to upload first (Phase 1 never did) and customer_id
linkage that Phase 1 doesn't have.

phishing_scam has no binary artifact -- the message text itself IS the
artifact (Section 4a: "text" signal category) -- so nothing is uploaded to
Storage for it, the case JSON goes straight into attack_cases.artifacts.

document_bonafide/voice_bonafide are bare files on disk with no per-case
JSON (unlike phishing_bonafide, which already has one from Task #31) --
this script synthesizes a minimal case record for each: case_id from
filename, customer_id=None (these bonafide baselines were never assigned
to a specific customer at generation time).

split_portion is NOT NULL with a ('train','held_out') check constraint
(001_core_schema.sql) -- bonafide cases aren't part of that train/held_out
adversarial-holdout scheme at all (they're the shared negative-class
baseline every split is compared against), so they're tagged 'train' by
convention here: always-available, not part of the generalization-gap
story. Noted so this isn't mistaken for an actual train-split fraud case.

Idempotent -- re-running overwrites (Storage upload uses upsert=true,
attack_cases upserts on id).

Usage:
    python backend/db/backfill_phase2_artifacts.py
"""

import json
import mimetypes
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from db.supabase_client import get_service_client  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
GENERATED_DIR = REPO_ROOT / "data" / "generated"
BUCKET = "attack-artifacts"


def _upload_file(client, local_path: Path, storage_path: str) -> str:
    # mimetypes.guess_type returns "audio/x-wav" for .wav on some platforms
    # (Colab's Linux among them) and "audio/wav" on others. The
    # attack-artifacts bucket's allowed_mime_types list (004_storage_buckets.sql)
    # only names the canonical forms, so the x- variant is rejected outright:
    #   {'statusCode': 415, 'error': invalid_mime_type,
    #    'message': mime type audio/x-wav is not supported}
    # That killed the voice half of this backfill on 2026-09-01 AFTER the
    # document half had already succeeded. Normalising here rather than
    # widening the bucket policy: the bucket's allowed list is the schema's
    # contract for what these artifacts are, and "audio/x-wav" is the same
    # thing spelled differently by a local mimetypes database, not a new type.
    _MIME_ALIASES = {
        "audio/x-wav": "audio/wav",
        "audio/wave": "audio/wav",
        "audio/vnd.wave": "audio/wav",
        "audio/x-mpeg": "audio/mpeg",
        "audio/mp3": "audio/mpeg",
        "image/jpg": "image/jpeg",
        "video/x-m4v": "video/mp4",
    }
    _guessed = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
    content_type = _MIME_ALIASES.get(_guessed, _guessed)
    with open(local_path, "rb") as f:
        client.storage.from_(BUCKET).upload(
            storage_path, f, file_options={"content-type": content_type, "upsert": "true"},
        )
    return client.storage.from_(BUCKET).get_public_url(storage_path)


def _document_attack_rows(client) -> list:
    rows = []
    for path in sorted((GENERATED_DIR / "document_attacks").glob("*/*.json")):
        raw = json.loads(path.read_text())
        image_local = REPO_ROOT / raw["image_path"]  # already OS-native separators, see eval_document_consistency.py
        storage_path = f"document_fraud/{raw['split_portion']}/{image_local.name}"
        url = _upload_file(client, image_local, storage_path) if image_local.exists() else None
        rows.append({
            "id": raw["case_id"],
            "attack_family": "document_fraud",
            "mutation_params": {
                **raw.get("mutation_params", {}),
                "resolved_levels": raw.get("resolved_levels", {}),
                "printed_fields": raw.get("printed_fields", {}),
                "qr_payload": raw.get("qr_payload", {}),
            },
            "split_portion": raw["split_portion"],
            "signals_expected": raw.get("signals_expected", ["document"]),
            "source_dataset": None,
            "is_fraud": True,
            "customer_id": raw.get("customer_id"),
            "transaction_sequence": None,
            "artifacts": {"image_url": url, "image_type": "image/png"},
            "generated_by": "deterministic_v1",
        })
    return rows


def _document_bonafide_rows(client) -> list:
    rows = []
    for path in sorted((GENERATED_DIR / "document_bonafide").glob("*.png")):
        storage_path = f"document_fraud/bonafide/{path.name}"
        url = _upload_file(client, path, storage_path)
        rows.append({
            "id": path.stem,
            "attack_family": "document_fraud",
            "mutation_params": {},
            "split_portion": "train",  # convention -- see module docstring
            "signals_expected": ["document"],
            "source_dataset": None,
            "is_fraud": False,
            "customer_id": None,
            "transaction_sequence": None,
            "artifacts": {"image_url": url, "image_type": "image/png"},
            "generated_by": "deterministic_v1",
        })
    return rows


def _voice_attack_rows(client) -> list:
    rows = []
    for path in sorted((GENERATED_DIR / "voice_attacks").glob("*/*.json")):
        raw = json.loads(path.read_text())
        audio_local = REPO_ROOT / raw["audio_path"]
        storage_path = f"voice_scam/{raw['split_portion']}/{audio_local.name}"
        url = _upload_file(client, audio_local, storage_path) if audio_local.exists() else None
        rows.append({
            "id": raw["case_id"],
            "attack_family": "voice_scam",
            "mutation_params": {
                **raw.get("mutation_params", {}),
                "resolved_levels": raw.get("resolved_levels", {}),
                "script_text": raw.get("script_text"),
            },
            "split_portion": raw["split_portion"],
            "signals_expected": raw.get("signals_expected", ["voice"]),
            "source_dataset": None,
            "is_fraud": True,
            "customer_id": raw.get("customer_id"),  # may be absent -- not every voice case is customer-linked
            "transaction_sequence": None,
            "artifacts": {"audio_url": url, "audio_type": "audio/wav"},
            "generated_by": "deterministic_v1",
        })
    return rows


def _voice_bonafide_rows(client) -> list:
    rows = []
    for path in sorted((GENERATED_DIR / "voice_bonafide").glob("*.wav")):
        storage_path = f"voice_scam/bonafide/{path.name}"
        url = _upload_file(client, path, storage_path)
        rows.append({
            "id": path.stem,
            "attack_family": "voice_scam",
            "mutation_params": {},
            "split_portion": "train",
            "signals_expected": ["voice"],
            "source_dataset": None,
            "is_fraud": False,
            "customer_id": None,
            "transaction_sequence": None,
            "artifacts": {"audio_url": url, "audio_type": "audio/wav"},
            "generated_by": "deterministic_v1",
        })
    return rows


def _phishing_attack_rows() -> list:
    rows = []
    for path in sorted((GENERATED_DIR / "phishing_attacks").glob("*/*.json")):
        raw = json.loads(path.read_text())
        rows.append({
            "id": raw["case_id"],
            "attack_family": "phishing_scam",
            "mutation_params": {**raw.get("mutation_params", {}), "resolved_levels": raw.get("resolved_levels", {})},
            "split_portion": raw["split_portion"],
            "signals_expected": raw.get("signals_expected", ["text"]),
            "source_dataset": None,
            "is_fraud": True,
            "customer_id": raw.get("customer_id"),
            "transaction_sequence": None,
            "artifacts": {
                "channel": raw.get("channel"), "sender": raw.get("sender"),
                "subject": raw.get("subject"), "body": raw.get("body"), "url": raw.get("url"),
            },
            "generated_by": "deterministic_v1",
        })
    return rows


def _phishing_bonafide_rows() -> list:
    rows = []
    for path in sorted((GENERATED_DIR / "phishing_bonafide").glob("*.json")):
        raw = json.loads(path.read_text())
        rows.append({
            "id": raw["case_id"],
            "attack_family": "phishing_scam",
            "mutation_params": {},
            "split_portion": "train",
            "signals_expected": ["text"],
            "source_dataset": None,
            "is_fraud": False,
            "customer_id": raw.get("customer_id"),
            "transaction_sequence": None,
            "artifacts": {
                "channel": raw.get("channel"), "sender": raw.get("sender"),
                "subject": raw.get("subject"), "body": raw.get("body"), "url": raw.get("url"),
            },
            "generated_by": "deterministic_v1",
        })
    return rows


def _upsert(client, table: str, rows: list, batch_size: int = 100) -> int:
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        client.table(table).upsert(batch, on_conflict="id").execute()
        total += len(batch)
    return total


def main() -> None:
    client = get_service_client()

    print("Uploading document_fraud artifacts + backfilling attack_cases...")
    doc_rows = _document_attack_rows(client) + _document_bonafide_rows(client)
    n = _upsert(client, "attack_cases", doc_rows)
    print(f"  {n} document_fraud rows upserted "
          f"({sum(1 for r in doc_rows if r['is_fraud'])} fraud, {sum(1 for r in doc_rows if not r['is_fraud'])} bonafide)")

    print("Uploading voice_scam artifacts + backfilling attack_cases...")
    voice_rows = _voice_attack_rows(client) + _voice_bonafide_rows(client)
    n = _upsert(client, "attack_cases", voice_rows)
    print(f"  {n} voice_scam rows upserted "
          f"({sum(1 for r in voice_rows if r['is_fraud'])} fraud, {sum(1 for r in voice_rows if not r['is_fraud'])} bonafide)")

    print("Backfilling phishing_scam attack_cases (no Storage upload -- text is the artifact)...")
    phish_rows = _phishing_attack_rows() + _phishing_bonafide_rows()
    n = _upsert(client, "attack_cases", phish_rows)
    print(f"  {n} phishing_scam rows upserted "
          f"({sum(1 for r in phish_rows if r['is_fraud'])} fraud, {sum(1 for r in phish_rows if not r['is_fraud'])} bonafide)")

    total = len(doc_rows) + len(voice_rows) + len(phish_rows)
    print(f"\nDone. {total} total attack_cases rows (document_fraud + voice_scam + phishing_scam, attack + bonafide).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nBACKFILL FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
