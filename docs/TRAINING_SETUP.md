# Local training setup

Tailored to: Windows 11, i5-12450HX, 16GB RAM, RTX 3050 6GB Laptop GPU (driver 591.86).

## 1. Python environment

```powershell
cd D:\GITHUB\red_hat_vs_blue_hat_attack
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. PyTorch (GPU build) — for the Autoencoder and, later, the GNN

XGBoost and LightGBM run on CPU in this project (see Section 4 — no real benefit to GPU
tree methods at this data size, and it avoids extra setup). PyTorch is the only thing
that needs a CUDA-specific wheel, and the correct install command depends on exactly
which CUDA version your driver supports right now — rather than hardcoding a command
here that may be stale by the time you run it, check first:

```powershell
nvidia-smi
```

Look at the "CUDA Version" shown in the top-right of the output. Then go to
https://pytorch.org/get-started/locally/, select Stable / Windows / Pip / Python /
your CUDA version, and run the exact command it gives you. Confirm it worked:

```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

This should print `True` and `NVIDIA GeForce RTX 3050 Laptop GPU`.

Note: `nvidia-smi` shows the *maximum* CUDA version your driver supports, not a version
you must match exactly — drivers are backward-compatible, so whatever's the newest option
on pytorch.org's selector will work fine even if it doesn't say the exact same number.

## 3. PyTorch Geometric — needed only when we get to the GNN (Phase 3, not yet)

PyG's compiled extensions are sensitive to your exact torch + CUDA version, so install
it from PyG's own install page (https://pytorch-geometric.readthedocs.io/en/latest/install/installation.html)
matched to whatever `torch.__version__` and CUDA version step 2 gave you, rather than a
generic `pip install torch-geometric`. Not needed until Phase 3 — skip for now.

## 4. Why CPU for XGBoost/LightGBM

Both train on PaySim (6.36M rows) plus IEEE-CIS in low single-digit minutes on a
12th-gen mobile CPU with the feature set we're using (~30-50 engineered columns, not
the full 135-feature spec). GPU histogram methods (`tree_method="gpu_hist"` / LightGBM's
`device="gpu"`) exist but add driver/toolkit surface area for a training time that's
already fast enough not to matter here. Reserve the GPU for the PyTorch models.

## 5. Kaggle API token

The `kaggle` CLI supports four auth methods as of 2026: OAuth login, an env var, a token
file, or the legacy `kaggle.json`. Use the token file — simplest, one line, no JSON to
get wrong:

1. https://www.kaggle.com/settings/api → generate an access token (starts with `KGAT_`)
2. In PowerShell:
   ```powershell
   mkdir -Force "$env:USERPROFILE\.kaggle"
   "KGAT_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" | Out-File -FilePath "$env:USERPROFILE\.kaggle\access_token" -Encoding ascii -NoNewline
   ```
3. Verify: `kaggle competitions list` should print competitions, not an auth error.
4. **IEEE-CIS specifically**: open https://www.kaggle.com/c/ieee-fraud-detection in your
   browser and click "Join Competition" / accept the rules once. The API download will
   403 until you do this — expected, not a bug.

(The legacy `kaggle.json` — username + key, from "Create Legacy API Key" — still works
too, placed at `C:\Users\<you>\.kaggle\kaggle.json`. Either credential type is fine; no
need to set up both.)

## 6. RAM discipline (16GB total)

`acquire.py` downloads full raw CSVs to `data/raw/` (gitignored — do not commit these).
`validate_raw.py` only samples 200k rows for schema checks, so it's cheap regardless of
dataset size. The feature-engineering stage (next) will support a `--sample N` flag for
fast local iteration on a subset — use it while debugging, and only load the full
6.36M-row PaySim set for your final canonical run. Downcast dtypes (float32 instead of
float64, category instead of object) rather than using pandas defaults, to keep the full
load comfortably under a few GB.

## 7. Run it

```powershell
python backend/defend/data/acquire.py
python backend/defend/data/validate_raw.py
python backend/defend/features/build_features.py
python backend/generate/inject_attacks.py
python backend/defend/train/train_xgboost.py
python backend/defend/train/train_lightgbm.py
python backend/defend/train/train_autoencoder.py
```

Expected output from `validate_raw.py`: schema-match confirmation and a fraud-rate
percentage for both datasets, ending in `All raw data validated successfully.` If either
script fails, the error message tells you which specific check failed and why — fix that
before moving on rather than working around it, since everything downstream assumes this
data is clean.

`build_features.py` reads the validated raw data and writes one combined, canonical
feature table to `data/processed/features.parquet` (plus a `feature_manifest.json`
alongside it — row counts, fraud rate, and null rate per column, per source dataset).
Use `--sample N` (e.g. `--sample 300000`) while iterating for speed; omit it for the
final canonical run on the full data. See the module docstring in the script itself for
exactly which columns come from which dataset and why.

`inject_attacks.py` (Stage 4, Red Team) generates synthetic attack cases for the four
Phase 1 families -- transaction fraud, account takeover, synthetic identity, mule
network -- using the train-allowed vs. held-out-only mutation combinations frozen in
`backend/evaluation/split_policy.py`. It writes one JSON artifact per case under
`data/generated/attacks/<train|held_out>/<family>/`, plus two flattened parquet files
(`attacks_train.parquet`, `attacks_held_out.parquet`) that concat directly with
`features.parquet` for Stage 5. Default is 400 cases per family per split portion;
override with `--n-per-family N`, or generate a subset with `--families
transaction_fraud mule_network`. Held-out cases are never used for training -- see
Section 8 of `docs/TECHNICAL_SPEC.md`.

`train_xgboost.py` and `train_lightgbm.py` need nothing beyond `requirements.txt` --
run them directly. `train_autoencoder.py` needs PyTorch (Section 2 above) installed
first; it uses your GPU automatically if available. All three save their model to
`backend/defend/models/` and append their validation metrics to
`docs/EVALUATION_RESULTS.md` and `backend/defend/models/metrics.json`. Once run, a
model is considered frozen (`docs/TECHNICAL_SPEC.md` Principle 10 / Section 8 step 2)
-- re-running a script overwrites its saved model, so do that deliberately rather than
as routine iteration once the adversarial evaluation stage has scored a specific
version.
