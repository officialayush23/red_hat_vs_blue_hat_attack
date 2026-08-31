-- Task #32 follow-on -- closes a real gap found while designing the
-- agentic data contract (docs/AGENTIC_CONTRACT.md): weakness_log
-- (001_core_schema.sql) records the weakness a run FOUND, but nothing
-- links it to the follow-up run that RE-TESTS after a targeted mutation --
-- so the before/after detection-rate delta that Section 8 step 6 calls
-- "the demo's central evidence" had no way to be queried, only asserted.
-- Also adds the exact fields the already-built (mock-data) frontend pages
-- expect (frontend/src/features/weaknesses/{WeaknessAnalysisPage,
-- AdaptiveMutationPage}.jsx, frontend/src/data/mockStore.js) -- so wiring
-- them to real data later (#36) is a data-source swap, not a redesign.

alter table public.weakness_log
  add column if not exists followup_run_id  uuid references public.evaluation_runs(id) on delete set null,
  add column if not exists reasons          text[] not null default '{}'::text[],
  add column if not exists recommended_action text,
  add column if not exists severity         text check (severity in ('low', 'medium', 'high')),
  add column if not exists changes          text[] not null default '{}'::text[];

create index if not exists weakness_log_followup_run_idx on public.weakness_log (followup_run_id);
create index if not exists weakness_log_family_idx on public.weakness_log (attack_family);
