-- Storage bucket for the generated dataset bundles that let a deployed
-- container actually run the pipeline (backend/tools/storage_sync.py).
--
-- Distinct from 004's two buckets on purpose:
--   attack-artifacts / customer-identity  -- PUBLIC, per-artifact, so the
--       frontend evidence viewer can play a spoofed call or show a tampered
--       invoice by URL.
--   generated-data (here)                 -- PRIVATE, per-bundle tar.gz
--       parts. Nothing in the browser reads these; only a backend process
--       holding the service-role key pulls them to hydrate data/generated/.
--       Private because these bundles are the whole corpus at once (every
--       held-out case included), and a public URL to the held-out split is
--       a way to leak an evaluation set, not a feature.
--
-- 50 MB file_size_limit matches the platform's per-object upload limit;
-- storage_sync.py splits every archive into <=40 MB parts to stay under it
-- (voice_attacks and attacks both exceed it as single archives).
--
-- storage_sync.py creates this bucket itself if it is missing, so a fresh
-- environment works without anyone running this migration by hand. It is
-- recorded here so the bucket is declared in the same place as every other
-- piece of this project's schema rather than existing only as a side effect
-- of a script someone happened to run.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('generated-data', 'generated-data', false, 52428800,
   array['application/gzip', 'application/json'])
on conflict (id) do nothing;

-- No public-read policy, deliberately: service-role access only, which
-- bypasses RLS and therefore needs no policy of its own.
