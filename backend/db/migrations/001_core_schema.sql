-- FraudShield core schema (Phase 1.5, docs/TECHNICAL_SPEC.md)
-- Synthetic data only, no real PII. Every table maps directly to the
-- Section 7 API contract / Section 4 attack taxonomy / Section 8 eval protocol.
--
-- Applied to the live project via Supabase's migration tooling on
-- 2026-08-30. This file is the reproducibility record required by the
-- submission rules -- re-running `supabase db push` (or applying this SQL
-- directly) against a fresh project reconstructs the schema exactly.

create extension if not exists pgcrypto;

-- Synthetic Customer Vault (Section 4b-i): anchor identity for the
-- identity-impersonation research-tier families. Never real Aadhaar/PII --
-- refs point at synthetic artifacts in Storage.
create table public.synthetic_customers (
  id                 text primary key,
  kyc_document_ref   text,
  photo_ref          text,
  voice_ref          text,
  video_ref          text,
  device_history     jsonb not null default '[]'::jsonb,
  account_age_days   integer,
  relationship_count integer,
  metadata           jsonb not null default '{}'::jsonb,
  created_at         timestamptz not null default now()
);

-- One row per generated (or real-labeled) case. Mirrors the Section 7
-- evaluation-case JSON shape.
create table public.attack_cases (
  id                   text primary key,
  attack_family        text not null,
  mutation_params      jsonb not null default '{}'::jsonb,
  split_portion        text not null check (split_portion in ('train', 'held_out')),
  signals_expected     text[] not null default '{}'::text[],
  source_dataset       text,
  is_fraud             boolean not null,
  customer_id          text references public.synthetic_customers(id) on delete set null,
  transaction_sequence jsonb,
  artifacts            jsonb not null default '{}'::jsonb,
  generated_by         text not null default 'deterministic_v1',
  created_at           timestamptz not null default now()
);
create index attack_cases_family_idx on public.attack_cases (attack_family);
create index attack_cases_split_idx on public.attack_cases (split_portion);
create index attack_cases_customer_idx on public.attack_cases (customer_id);

-- One row per adversarial-evaluation-harness invocation (Section 8).
create table public.evaluation_runs (
  id          uuid primary key default gen_random_uuid(),
  run_type    text not null check (run_type in
                ('phase1_val', 'adversarial_train_eval', 'adversarial_held_out', 'targeted_reeval')),
  config      jsonb not null default '{}'::jsonb,
  status      text not null default 'pending' check (status in ('pending', 'running', 'completed', 'failed')),
  started_at  timestamptz,
  finished_at timestamptz,
  created_at  timestamptz not null default now()
);

-- Per-case scoring result within a run. This is what the live Realtime
-- canvas (Section 9) subscribes to.
create table public.evaluation_results (
  id               uuid primary key default gen_random_uuid(),
  run_id           uuid not null references public.evaluation_runs(id) on delete cascade,
  case_id          text not null references public.attack_cases(id) on delete cascade,
  model_signals    jsonb not null default '[]'::jsonb,
  fused_risk_score numeric,
  decision         text check (decision in ('approve', 'review', 'challenge', 'block')),
  detected         boolean,
  actual_label     text check (actual_label in ('fraud', 'legit')),
  evidence         jsonb not null default '[]'::jsonb,
  created_at       timestamptz not null default now()
);
create index evaluation_results_run_idx on public.evaluation_results (run_id);
create index evaluation_results_case_idx on public.evaluation_results (case_id);

-- One evidence card per model, per Principle 11's evidence gate. Nothing
-- appears as "validated" in the dashboard except by upsert into this table
-- from a real training/evaluation script -- never hand-edited.
create table public.model_registry (
  id                text primary key,
  purpose           text,
  dataset           text,
  training_summary  text,
  signal_category   text check (signal_category in
                      ('transaction', 'behavioral', 'device', 'graph', 'text', 'voice', 'document', 'identity')),
  validation_metrics jsonb,
  test_metrics      jsonb,
  status            text not null default 'planned' check (status in ('validated', 'experimental', 'planned')),
  version           text,
  artifact_path     text,
  updated_at        timestamptz not null default now()
);

-- Predefined composite scenarios (Principle 12) -- ordered chains of
-- existing attack-family primitives, not a new orchestration engine.
create table public.attack_campaigns (
  id          text primary key,
  name        text not null,
  description text,
  stages      jsonb not null default '[]'::jsonb,
  created_at  timestamptz not null default now()
);

create table public.campaign_runs (
  id               uuid primary key default gen_random_uuid(),
  campaign_id      text not null references public.attack_campaigns(id) on delete cascade,
  run_id           uuid references public.evaluation_runs(id) on delete set null,
  stage_results    jsonb not null default '[]'::jsonb,
  overall_detected boolean,
  weakest_stage    text,
  created_at       timestamptz not null default now()
);
create index campaign_runs_campaign_idx on public.campaign_runs (campaign_id);

-- Section 8 steps 5-6: the weakest family/combination identified from a
-- held-out run, and the next strategy generated against it (LLM or rule-based).
create table public.weakness_log (
  id             uuid primary key default gen_random_uuid(),
  run_id         uuid references public.evaluation_runs(id) on delete cascade,
  attack_family  text,
  combination    jsonb,
  recall         numeric,
  source         text check (source in ('llm', 'rule_based')),
  next_strategy  jsonb,
  identified_at  timestamptz not null default now()
);
