-- Section 9: "evaluation runs push updates via Supabase Realtime as they
-- progress" -- the live attack-simulation canvas subscribes to these.
alter publication supabase_realtime add table
  public.evaluation_runs,
  public.evaluation_results,
  public.campaign_runs;
