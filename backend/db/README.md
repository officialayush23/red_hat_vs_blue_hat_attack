# FraudShield database (Supabase)

Schema for the live project (`RED_VS_BLUE_MASTERCARD`, `ap-south-1`) is defined
in `migrations/`, applied in numeric order. These files are the reproducibility
record for the submission -- they are exactly what was run against the live
project on 2026-08-30, not an after-the-fact description.

- `001_core_schema.sql` -- the 8 tables (see docs/TECHNICAL_SPEC.md Section
  4b-i / 4c / 7 / 8 for what each maps to).
- `002_rls_policies.sql` -- RLS on every table, public read, service-role-only
  write (no insert/update/delete policy exists for anon/authenticated).
- `003_realtime.sql` -- adds `evaluation_runs`, `evaluation_results`,
  `campaign_runs` to the `supabase_realtime` publication for the live
  attack-canvas requirement (Section 9).
- `004_storage_buckets.sql` -- `attack-artifacts` and `customer-identity`
  Storage buckets, public read, with matching `storage.objects` policies.

## Applying against a fresh project

Either paste each file's contents into the Supabase SQL editor in order, or
(if the Supabase CLI is set up) `supabase db push` after placing these under
a `supabase/migrations/` directory per the CLI's own convention. They were
originally applied directly via the Supabase management API, not the CLI.

## Local setup

`backend/.env` already has real `SUPABASE_URL` / `SUPABASE_ANON_KEY` /
`SUPABASE_SERVICE_ROLE_KEY` values (plus `SUPABASE_PASSWORD` and the pooler
connection strings, for anything that needs raw Postgres access instead of
the REST client) -- nothing to fill in for Supabase specifically. If
re-cloning fresh, `backend/.env.example` documents the shape.

1. `pip install -r backend/requirements.txt` (adds the `supabase` package).
2. Any backend script that writes uses `backend/db/supabase_client.get_service_client()`.
   Anything read-only (mirrors frontend behavior) uses `get_anon_client()`.
   Both load `backend/.env` explicitly (by path, not cwd-dependent), so
   scripts work the same whether run from the repo root or `backend/`.
3. Frontend: copy `frontend/.env.example` to `frontend/.env.local`, fill in
   `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` from the same dashboard
   page (anon key only -- never the service role key, it ships to the browser).

## Backfilling existing Stage 4 data

`backend/db/backfill_attack_cases.py` reads the already-generated
`data/generated/attacks/**/*.json` case artifacts (plus
`data/processed/attacks_manifest.json` if present) and upserts them into
`attack_cases`, so the tables aren't empty once the API exists. Run it after
setting up `.env`:

```
python backend/db/backfill_attack_cases.py
```

It's idempotent (upsert on `id`) -- safe to re-run after generating more
cases.
