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
    public_url = client.storage.from_(BUCKET).get_public_url(storage_path)

    # 2026-09-24: every run re-uploaded all ~1,700 artifacts (416 MB) and the
    # whole backfill died on the first bad response --
    #   BACKFILL FAILED: Expecting value: line 1 column 1 (char 0)
    # after 240s on Render: Storage answered one upload with a non-JSON body
    # (a gateway error page / rate limit) and supabase-py's json parse raised.
    # Now: an object already in the bucket with the same size is not sent
    # again, and a failed upload is retried, then reported and skipped -- one
    # artifact must not keep every case row out of attack_cases.
    folder, _, name = storage_path.rpartition("/")
    existing = _existing_objects(client, folder)
    if existing.get(name) == local_path.stat().st_size:
        return public_url
    import time
    for attempt in range(3):
        try:
            with open(local_path, "rb") as f:
                client.storage.from_(BUCKET).upload(
                    storage_path, f, file_options={"content-type": content_type, "upsert": "true"},
                )
            return public_url
        except Exception as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    _UPLOAD_FAILURES.append(f"{storage_path}: {last!r}"[:200])
    # Keep the row: point at the object if an older copy exists, else no URL.
    return public_url if name in existing else None


_UPLOAD_FAILURES: list = []
_LISTING_CACHE: dict = {}


def _existing_objects(client, folder: str) -> dict:
    """name -> size for every object already under `folder`, listed once."""
    if folder in _LISTING_CACHE:
        return _LISTING_CACHE[folder]
    out, offset = {}, 0
    try:
        while True:
            page = client.storage.from_(BUCKET).list(folder, {"limit": 1000, "offset": offset})
            for obj in page or []:
                size = (obj.get("metadata") or {}).get("size")
                if obj.get("name"):
                    out[obj["name"]] = size
            if not page or len(page) < 1000:
                break
            offset += 1000
    except Exception as exc:
        print(f"  (could not list {BUCKET}/{folder}: {exc!r} -- uploading everything there)", flush=True)
    _LISTING_CACHE[folder] = out
    return out


def _document_attack_rows(client) -> list:
    rows = []
    for path in sorted((GENERATED_DIR / "document_attacks").glob("*/*.json")):
        raw = json.loads(path.read_text())
        # A path stored in a JSON file written on Windows is backslash-separated;
        # PurePosixPath does not split on it, so this join silently produces one
        # bogus component on Linux/Colab. Same fix as eval_document_consistency.py.
        image_local = REPO_ROOT / raw["image_path"].replace("\\", "/")
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
        # A path stored in a JSON file written on Windows is backslash-separated;
        # PurePosixPath does not split on it, so this join silently produces one
        # bogus component on Linux/Colab. Same fix as eval_document_consistency.py.
        audio_local = REPO_ROOT / raw["audio_path"].replace("\\", "/")
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


def _video_kyc_rows(client) -> list:
    """video_kyc_impersonation cases -> attack_cases, with the video AND the
    reference photo it was compared against uploaded to Storage.

    2026-09-02: there was no persistence path for this family at all. grep
    video_kyc across db/ and tools/ returned only sync_model_registry.py, and
    attack_cases held zero rows for it while metrics.json reported
    video_kyc_detector at 1.000 -- so section C's eval would have written
    metrics and silently persisted nothing, since evaluation_results.case_id
    is a foreign key into this table (the "480 scored, 0 persisted" failure
    the notebook's A2 cell documents).

    TWO things this family does differently from document/voice:

      - attack_family is "video_kyc_impersonation" (what the generator
        writes), not "video_kyc".
      - the generator's case["customer_id"] is a PERSON NAME (the claimed
        identity, e.g. the reference-photo stem), not a CUST-xxxxxx id.
        attack_cases.customer_id is a foreign key into synthetic_customers,
        so writing the name there would be rejected outright. It goes into
        mutation_params.claimed_identity instead and the column stays NULL --
        same convention the bonafide rows above use.

    impostor_customer_id is ground truth and is deliberately NOT copied into
    artifacts: artifacts is what the evidence viewer shows, and Principle 13
    keeps ground truth out of anything a detector or a viewer reads as input.
    It stays in mutation_params, alongside the tier, where the eval harness
    already looks for it."""
    rows = []
    for path in sorted((GENERATED_DIR / "video_kyc_attacks").glob("*/*.json")):
        raw = json.loads(path.read_text())
        video_local = REPO_ROOT / raw["video_path"].replace("\\", "/")
        photo_local = REPO_ROOT / raw["reference_photo_path"].replace("\\", "/")

        video_url = photo_url = None
        if video_local.exists():
            video_url = _upload_file(
                client, video_local, f"video_kyc/{raw['split_portion']}/{video_local.name}")
        if photo_local.exists():
            photo_url = _upload_file(
                client, photo_local, f"video_kyc/reference/{photo_local.name}")

        rows.append({
            "id": raw["case_id"],
            "attack_family": raw.get("attack_family", "video_kyc_impersonation"),
            "mutation_params": {
                **raw.get("mutation_params", {}),
                "resolved_levels": raw.get("resolved_levels", {}),
                "claimed_identity": raw.get("customer_id"),
                "impostor_customer_id": raw.get("impostor_customer_id"),
                "tier": raw.get("tier"),
            },
            "split_portion": raw["split_portion"],
            "signals_expected": raw.get("signals_expected", ["video"]),
            "source_dataset": None,
            "is_fraud": raw["is_fraud"],
            "customer_id": None,  # see docstring -- the generator's value is a name
            "transaction_sequence": None,
            "artifacts": {
                "video_url": video_url,
                "video_type": "video/mp4",
                "reference_photo_url": photo_url,
            },
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
    # tools/storage_sync.py drops a `.storage_bundle.json` marker into every
    # directory it manages, so a bare *.json glob picks it up as a phantom entry
    # after a `storage_sync.py pull` -- on Colab, never locally. Same guard
    # synthetic_customers.load_roster() already carries.
    for path in sorted(p for p in (GENERATED_DIR / "phishing_bonafide").glob("*.json")
                       if not p.name.startswith(".")):
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
    failed = []

    def section(label, build, table="attack_cases"):
        # Each family independently: one family's Storage or PostgREST error
        # (seen: a non-JSON gateway response -> "Expecting value: line 1
        # column 1") must not keep the other families out of attack_cases.
        print(f"Backfilling {label}...", flush=True)
        try:
            rows = build()
            if not rows:
                print(f"  no {label} cases on disk -- skipped", flush=True)
                return 0
            n = _upsert(client, table, rows)
            n_fraud = sum(1 for r in rows if r.get("is_fraud"))
            print(f"  {n} {label} rows upserted ({n_fraud} fraud, {len(rows) - n_fraud} bonafide)", flush=True)
            return len(rows)
        except Exception as exc:
            failed.append(label)
            print(f"  {label} FAILED: {exc!r}"[:400], flush=True)
            return 0

    total = 0
    total += section("document_fraud", lambda: _document_attack_rows(client) + _document_bonafide_rows(client))
    total += section("voice_scam", lambda: _voice_attack_rows(client) + _voice_bonafide_rows(client))
    total += section("video_kyc_impersonation", lambda: _video_kyc_rows(client))
    total += section("phishing_scam", lambda: _phishing_attack_rows() + _phishing_bonafide_rows())

    if _UPLOAD_FAILURES:
        print(f"\n{len(_UPLOAD_FAILURES)} artifact upload(s) failed after retries (rows kept, URL left empty "
              f"where no older copy exists):", flush=True)
        for line in _UPLOAD_FAILURES[:10]:
            print(f"  - {line}", flush=True)
    print(f"\nDone. {total} attack_cases rows backfilled across phase-2 families.")
    if failed:
        raise RuntimeError(f"families that could not be backfilled: {', '.join(failed)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nBACKFILL FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
