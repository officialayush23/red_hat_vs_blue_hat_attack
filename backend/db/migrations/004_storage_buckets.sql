-- Storage buckets for generated attack artifacts (Principle 8) and
-- synthetic-customer identity assets (Section 4b-i). Public read (synthetic
-- data, no real PII) so the frontend evidence viewer and audio/image
-- players can hit URLs directly; writes are service-role only via storage
-- policies below, same posture as the table RLS in 002.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('attack-artifacts', 'attack-artifacts', true, 52428800,
   array['audio/mpeg','audio/wav','audio/mp4','image/png','image/jpeg','video/mp4','application/pdf','text/plain']),
  ('customer-identity', 'customer-identity', true, 52428800,
   array['audio/mpeg','audio/wav','audio/mp4','image/png','image/jpeg','video/mp4','application/pdf'])
on conflict (id) do nothing;

create policy "public read attack-artifacts"
  on storage.objects for select
  using (bucket_id = 'attack-artifacts');

create policy "public read customer-identity"
  on storage.objects for select
  using (bucket_id = 'customer-identity');
