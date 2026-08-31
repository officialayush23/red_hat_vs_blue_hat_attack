-- Enable RLS everywhere. Synthetic-only data (Principle 8: no real PII) so
-- public read is fine for the demo; writes go through the service-role key
-- from the Python backend only -- no insert/update/delete policy exists for
-- anon/authenticated, so RLS denies those by default. Real security posture,
-- not a workaround.

alter table public.synthetic_customers enable row level security;
alter table public.attack_cases        enable row level security;
alter table public.evaluation_runs     enable row level security;
alter table public.evaluation_results  enable row level security;
alter table public.model_registry      enable row level security;
alter table public.attack_campaigns    enable row level security;
alter table public.campaign_runs       enable row level security;
alter table public.weakness_log        enable row level security;

create policy "public read" on public.synthetic_customers for select using (true);
create policy "public read" on public.attack_cases        for select using (true);
create policy "public read" on public.evaluation_runs     for select using (true);
create policy "public read" on public.evaluation_results  for select using (true);
create policy "public read" on public.model_registry      for select using (true);
create policy "public read" on public.attack_campaigns    for select using (true);
create policy "public read" on public.campaign_runs       for select using (true);
create policy "public read" on public.weakness_log        for select using (true);
