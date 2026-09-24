"""Make sure data/processed/ holds the tabular attack tables the three
tabular evaluations read (fusion, behavioral_adjustment, adversarial_tabular).

Why this exists (2026-09-24): on the Render container data/ is outside the
build context, so data/processed/ starts empty. The /evaluations/run path
never hydrated at all, and the agent-run path tried to pull the full
`processed` bundle -- 155 MB compressed, mostly features.parquet, which no
evaluation reads -- held entirely in memory by storage_sync.pull(). Either
way fusion / behavioral_adjustment / adversarial_tabular died in ~11s with
"attacks_held_out.parquet not found".

The evaluations only need ~470 KB: attacks_held_out.parquet (+ train,
manifest, reference_stats for inject_attacks.py). Those ship inside the
image at backend/seed_data/processed/ and are copied in here when missing.
They are the same files the `attacks` Storage bundle was pushed alongside
(parquet 2026-09-01 05:57, attacks bundle 06:11), so their case_ids match
attack_cases and results persist.

Never overwrites: a locally regenerated parquet always wins over the seed.
"""
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BACKEND_DIR.parent / "data" / "processed"
SEED_DIR = BACKEND_DIR / "seed_data" / "processed"
REQUIRED = "attacks_held_out.parquet"


def _val_split_available() -> bool:
    """The tabular evals also need the Stage-5 validation split: either the
    shipped cache (seed_data/processed/val_split.parquet, built by
    tools/build_val_split_cache.py) or features.parquet to rebuild it."""
    return any(p.is_file() for p in (
        SEED_DIR / "val_split.parquet", PROCESSED_DIR / "val_split.parquet",
        PROCESSED_DIR / "features.parquet"))


def ensure_processed(verbose: bool = True) -> dict:
    r = _ensure_attack_tables(verbose)
    if not _val_split_available():
        # Last resort: the full `processed` bundle from Storage (155 MB,
        # streamed to disk by storage_sync.pull). Only reached when the
        # val_split cache has not been built and committed yet.
        msg = "No val_split cache and no features.parquet -- pulling the `processed` bundle from Storage"
        print(msg, flush=True)
        try:
            from tools.storage_sync import pull
            pull(PROCESSED_BUNDLE)
        except Exception as exc:
            print(f"  processed pull failed: {exc}", flush=True)
        ok = _val_split_available()
        r["summary"] += f"; {msg}: {'ok' if ok else 'FAILED'}"
        r["ok"] = r["ok"] and ok
    return r


PROCESSED_BUNDLE = "processed"


def _ensure_attack_tables(verbose: bool = True) -> dict:
    target = PROCESSED_DIR / REQUIRED
    if target.is_file() and target.stat().st_size > 0:
        return {"ok": True, "seeded": [], "summary": f"{REQUIRED} already present"}
    if not (SEED_DIR / REQUIRED).is_file():
        return {"ok": False, "seeded": [],
                "summary": f"{REQUIRED} missing and no seed at {SEED_DIR}"}
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    seeded = []
    for src in sorted(SEED_DIR.iterdir()):
        dst = PROCESSED_DIR / src.name
        # val_split is read straight from seed_data by load_val_split(); no copy.
        if src.name.startswith("val_split"):
            continue
        if src.is_file() and not dst.exists():
            shutil.copy2(src, dst)
            seeded.append(src.name)
    msg = f"Seeded data/processed/ from backend/seed_data/processed/: {', '.join(seeded)}"
    if verbose:
        print(msg, flush=True)
    return {"ok": (PROCESSED_DIR / REQUIRED).is_file(), "seeded": seeded, "summary": msg}


if __name__ == "__main__":
    sys.path.insert(0, str(BACKEND_DIR))
    r = ensure_processed()
    print(r["summary"])
    sys.exit(0 if r["ok"] else 1)
