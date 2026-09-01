"""
Move data/generated/ between the machine that produced it and Supabase
Storage, so a deployed container can actually run the pipeline.

Why this exists
---------------
backend/Dockerfile builds an image from the git repo, and .gitignore
excludes data/generated/ (236 MB of generated cases, audio, invoices and
video -- regenerable from generate/, so committing it would be wrong).
The consequence, confirmed live on 2026-08-31 rather than assumed: a run
launched against the Railway deployment completes in under 9 seconds with
returncode 0 and reports

    attack-generator  done | Generation had failures (1.9s)
    blue-team         done | Evaluation had failures (3.1s)
    attacksTested: 0

-- a structurally correct, honestly-reported, completely empty run. The
scripts degrade gracefully instead of crashing (which is right), but the
deployment has nothing to work on.

So: bundle data/generated/ into Supabase Storage once from the machine
that generated it (`push`), and let any container pull what it needs on
demand (`pull`). Storage, not git: the data is large, binary, and
regenerable, and Supabase is already this project's system of record for
everything else.

Design notes, each for a real constraint
----------------------------------------
- ONE ARCHIVE PER TOP-LEVEL DIRECTORY, not per file. data/generated/ holds
  16,414 files (15,640 of them in attacks/ alone). Uploading those
  individually over the Storage REST API would take hours and produce
  16,414 objects to keep consistent; 11 tar.gz bundles take minutes.
- CHUNKED AT 40 MB. Supabase's per-file upload limit is 50 MB on the
  default plan, and two bundles exceed it (voice_attacks ~111 MB,
  attacks ~74 MB). Each archive is therefore split into <=40 MB parts
  (`name.tar.gz.part000`, `.part001`, ...) and reassembled on pull. A
  bundle that fits stays a single part -- the same code path either way.
- SHA-256 PER BUNDLE, recorded in a manifest object. pull skips a bundle
  whose extracted marker already matches, so re-hydrating a warm container
  is free and a partial download is never mistaken for a complete one.
- WINDOWS PATH SEPARATORS. tarfile writes POSIX separators regardless of
  host, so an archive built on Windows extracts correctly on Linux -- the
  opposite of the documented Compress-Archive bug in docs/SESSION_HANDOFF.md
  section 3, which is exactly why tarfile is used here and not zipfile.

Usage
-----
    # On the machine that has the data (once, or after regenerating):
    python tools/storage_sync.py push
    python tools/storage_sync.py push --only voice_attacks,document_attacks

    # In a container / on a fresh machine:
    python tools/storage_sync.py pull
    python tools/storage_sync.py pull --only attacks
    python tools/storage_sync.py status
"""

import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
GENERATED_DIR = REPO_ROOT / "data" / "generated"
sys.path.insert(0, str(BACKEND_DIR))

BUCKET = "generated-data"
MANIFEST_OBJECT = "manifest.json"
# 40 MB: comfortably under Supabase's 50 MB per-object upload limit, with
# room for the multipart/form-data overhead the client adds.
CHUNK_BYTES = 40 * 1024 * 1024
# Written into each extracted directory so pull can tell "already have
# exactly this bundle" from "have some files from an older bundle".
MARKER_NAME = ".storage_bundle.json"


def _client():
    """Imported lazily so `status` still works (and reports the local half)
    on a machine without supabase-py installed or without credentials --
    diagnosing "why is this container empty" should never itself require a
    working Supabase client."""
    from db.supabase_client import get_service_client
    return get_service_client()


def _log(msg: str) -> None:
    print(msg, flush=True)


def _bundle_names() -> list:
    if not GENERATED_DIR.exists():
        return []
    return sorted(p.name for p in GENERATED_DIR.iterdir() if p.is_dir())


def _dir_stats(path: Path):
    files = [p for p in path.rglob("*") if p.is_file() and p.name != MARKER_NAME]
    return len(files), sum(p.stat().st_size for p in files)


def _make_archive(src: Path) -> bytes:
    """tar.gz a directory in memory. Deterministic enough to be useful --
    entries are added in sorted order so an unchanged directory produces a
    similar archive run to run (gzip still stamps a mtime, so the digest is
    of the archive actually uploaded, never assumed to be reproducible)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(src.rglob("*")):
            if path.is_file() and path.name != MARKER_NAME:
                tar.add(path, arcname=str(path.relative_to(src)).replace("\\", "/"))
    return buf.getvalue()


def _ensure_bucket(client) -> None:
    try:
        existing = {b.id if hasattr(b, "id") else b["id"] for b in client.storage.list_buckets()}
    except Exception as exc:  # listing can fail on restricted keys; try to create anyway
        _log(f"  (could not list buckets: {exc}; attempting create)")
        existing = set()
    if BUCKET in existing:
        return
    try:
        client.storage.create_bucket(
            BUCKET,
            options={"public": False, "file_size_limit": 52428800},
        )
        _log(f"  created private bucket '{BUCKET}'")
    except Exception as exc:
        # Already-exists is fine; anything else is worth seeing rather than
        # failing three steps later with a confusing 404 on upload.
        if "already exists" in str(exc).lower() or "duplicate" in str(exc).lower():
            return
        raise


def push(only=None) -> int:
    if not GENERATED_DIR.exists():
        _log(f"{GENERATED_DIR} does not exist -- nothing to push. Run generate/run_all_generation.py first.")
        return 1

    client = _client()
    _ensure_bucket(client)

    names = _bundle_names()
    if only:
        wanted = {n.strip() for n in only.split(",") if n.strip()}
        unknown = wanted - set(names)
        if unknown:
            _log(f"Unknown bundle(s): {sorted(unknown)}. Available: {names}")
            return 2
        names = [n for n in names if n in wanted]

    manifest = {"bundles": {}, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    # Merge into the existing manifest so a --only push doesn't erase the
    # record of bundles it didn't touch.
    try:
        raw = client.storage.from_(BUCKET).download(MANIFEST_OBJECT)
        manifest["bundles"] = json.loads(raw.decode("utf-8")).get("bundles", {})
    except Exception:
        pass

    total_bytes = 0
    for name in names:
        src = GENERATED_DIR / name
        n_files, raw_bytes = _dir_stats(src)
        if n_files == 0:
            _log(f"- {name}: empty, skipped")
            continue

        _log(f"- {name}: packing {n_files} files ({raw_bytes / 1e6:.1f} MB raw)...")
        blob = _make_archive(src)
        digest = hashlib.sha256(blob).hexdigest()
        parts = [blob[i:i + CHUNK_BYTES] for i in range(0, len(blob), CHUNK_BYTES)]
        _log(f"  {len(blob) / 1e6:.1f} MB compressed -> {len(parts)} part(s), sha256 {digest[:12]}")

        for idx, part in enumerate(parts):
            key = f"{name}.tar.gz.part{idx:03d}"
            client.storage.from_(BUCKET).upload(
                key, part,
                {"content-type": "application/gzip", "upsert": "true"},
            )
            _log(f"  uploaded {key} ({len(part) / 1e6:.1f} MB)")

        spec = {
            "parts": len(parts),
            "bytes": len(blob),
            "sha256": digest,
            "files": n_files,
            "rawBytes": raw_bytes,
        }
        manifest["bundles"][name] = spec
        # Write the same marker pull writes, so `status` can tell that the
        # machine that pushed is in sync with Storage. Without this, push
        # left every local directory unmarked and status reported
        # "inSync": [] immediately after a successful upload of everything
        # -- technically true of the marker files, actively misleading
        # about the data.
        (src / MARKER_NAME).write_text(json.dumps({**spec, "name": name}, indent=2))
        total_bytes += len(blob)

    client.storage.from_(BUCKET).upload(
        MANIFEST_OBJECT,
        json.dumps(manifest, indent=2).encode("utf-8"),
        {"content-type": "application/json", "upsert": "true"},
    )
    _log(f"\nPushed {len(names)} bundle(s), {total_bytes / 1e6:.1f} MB compressed, manifest updated.")
    return 0


def _read_manifest(client) -> dict:
    try:
        raw = client.storage.from_(BUCKET).download(MANIFEST_OBJECT)
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"No manifest in Storage bucket '{BUCKET}' ({exc}). "
            "Run `python tools/storage_sync.py push` from the machine that has data/generated/."
        ) from exc


def _local_marker(name: str):
    marker = GENERATED_DIR / name / MARKER_NAME
    if not marker.exists():
        return None
    try:
        return json.loads(marker.read_text())
    except Exception:
        return None


def pull(only=None, force=False) -> int:
    client = _client()
    manifest = _read_manifest(client)
    bundles = manifest.get("bundles", {})
    names = sorted(bundles)
    if only:
        wanted = {n.strip() for n in only.split(",") if n.strip()}
        unknown = wanted - set(names)
        if unknown:
            _log(f"Not in Storage: {sorted(unknown)}. Available: {names}")
            return 2
        names = [n for n in names if n in wanted]

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for name in names:
        spec = bundles[name]
        local = _local_marker(name)
        if not force and local and local.get("sha256") == spec["sha256"]:
            _log(f"- {name}: already present (sha matches), skipped")
            continue

        _log(f"- {name}: downloading {spec['parts']} part(s), {spec['bytes'] / 1e6:.1f} MB...")
        chunks = []
        for idx in range(spec["parts"]):
            key = f"{name}.tar.gz.part{idx:03d}"
            chunks.append(client.storage.from_(BUCKET).download(key))
        blob = b"".join(chunks)

        digest = hashlib.sha256(blob).hexdigest()
        if digest != spec["sha256"]:
            # Never extract an archive that isn't the one the manifest
            # describes -- a truncated part would otherwise silently produce
            # a partial dataset that every downstream metric would be
            # computed over without anyone noticing.
            _log(f"  CHECKSUM MISMATCH for {name}: got {digest[:12]}, manifest says {spec['sha256'][:12]}. Not extracting.")
            return 3

        dest = GENERATED_DIR / name
        dest.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / f"{name}.tar.gz"
            archive.write_bytes(blob)
            with tarfile.open(archive, mode="r:gz") as tar:
                tar.extractall(dest)
        (dest / MARKER_NAME).write_text(json.dumps({**spec, "name": name}, indent=2))
        n_files, raw_bytes = _dir_stats(dest)
        _log(f"  extracted {n_files} files ({raw_bytes / 1e6:.1f} MB) into data/generated/{name}/")
        fetched += 1

    _log(f"\nHydrated {fetched} bundle(s); {len(names) - fetched} already current.")
    return 0


def status() -> int:
    local = {}
    for name in _bundle_names():
        n_files, raw_bytes = _dir_stats(GENERATED_DIR / name)
        local[name] = {"files": n_files, "rawBytes": raw_bytes, "marker": _local_marker(name)}

    remote = {}
    error = None
    try:
        remote = _read_manifest(_client()).get("bundles", {})
    except Exception as exc:
        error = str(exc)

    report = {
        "generatedDir": str(GENERATED_DIR),
        "generatedDirExists": GENERATED_DIR.exists(),
        "local": local,
        "remote": remote,
        "remoteError": error,
        "inSync": sorted(
            n for n in remote
            if (local.get(n, {}).get("marker") or {}).get("sha256") == remote[n]["sha256"]
        ),
        "missingLocally": sorted(n for n in remote if n not in local or not local[n]["files"]),
    }
    print(json.dumps(report, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["push", "pull", "status"])
    parser.add_argument("--only", type=str, default=None, help="Comma-separated bundle names (top-level dirs of data/generated/)")
    parser.add_argument("--force", action="store_true", help="pull: re-download even if the local sha already matches")
    args = parser.parse_args()

    if args.command == "push":
        return push(args.only)
    if args.command == "pull":
        return pull(args.only, args.force)
    return status()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"\nstorage_sync FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
