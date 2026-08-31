"""
Stage 1 of the training pipeline -- acquire raw datasets from Kaggle.

Usage:
    python backend/defend/data/acquire.py

Requires a Kaggle API token at ~/.kaggle/kaggle.json (Linux/Mac) or
C:\\Users\\<you>\\.kaggle\\kaggle.json (Windows). Get one from
https://www.kaggle.com/settings -> API -> Create New Token.

IEEE-CIS is a *competition* dataset: you must open
https://www.kaggle.com/c/ieee-fraud-detection in your browser and click
"Join Competition" / accept the rules once, before the API download below
will work. It will fail with a 403 until you do this -- that's expected,
not a bug in this script.

PaySim is a public dataset and needs no rule acceptance.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    print(result.stdout)


def acquire_paysim() -> None:
    target = RAW_DIR / "paysim"
    target.mkdir(parents=True, exist_ok=True)
    _run(["kaggle", "datasets", "download", "-d", "ealaxi/paysim1", "-p", str(target), "--unzip"])
    print(f"PaySim downloaded to {target}")


def acquire_ieee_cis() -> None:
    target = RAW_DIR / "ieee_cis"
    target.mkdir(parents=True, exist_ok=True)
    try:
        _run(["kaggle", "competitions", "download", "-c", "ieee-fraud-detection", "-p", str(target)])
    except RuntimeError:
        print(
            "\nIEEE-CIS download failed. Most likely cause: you haven't joined the "
            "competition yet. Open https://www.kaggle.com/c/ieee-fraud-detection in "
            "your browser, click 'Join Competition' / accept the rules, then re-run "
            "this script.",
            file=sys.stderr,
        )
        raise

    for zip_path in target.glob("*.zip"):
        print(f"Unzipping {zip_path.name}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target)
    print(f"IEEE-CIS downloaded to {target}")


if __name__ == "__main__":
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    acquire_paysim()
    acquire_ieee_cis()
    print("\nDone. Raw data is in", RAW_DIR)
    print("Next: python backend/defend/data/validate_raw.py")
