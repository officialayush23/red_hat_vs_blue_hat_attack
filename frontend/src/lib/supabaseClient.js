// Real Supabase browser client -- anon key only, subject to RLS
// (002_rls_policies.sql: public read on every table, service-role-only
// write; see backend/db/README.md). Every services/api/*.js read call
// that's been swapped from a mock should import `supabase` from here and
// query directly -- no custom backend proxy needed for reads, only for
// triggering long-running Python jobs (see services/api/jobs.js).

import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  // Not thrown -- a missing .env.local shouldn't crash the whole app at
  // import time. Every real query against `supabase` will fail loudly
  // instead, which is the right place to notice this.
  console.warn(
    "[supabaseClient] VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are not set. " +
    "Copy frontend/.env.example to frontend/.env.local and fill in the anon key " +
    "(never the service-role key) before any real Supabase-backed page will load data."
  );
}

export const supabase = createClient(url ?? "", anonKey ?? "");
