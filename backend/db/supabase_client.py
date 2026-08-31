"""
Thin Supabase client factory for the backend. Two entry points, deliberately
kept separate so a script can't accidentally write with a read-only key or
leak the service-role key into anything client-facing:

- get_service_client(): service-role key, bypasses RLS -- used by every
  backend script that WRITES (backfill, training scripts recording to
  model_registry, the evaluation harness recording runs/results).
- get_anon_client(): anon/publishable key, subject to the "public read"
  RLS policies in migrations/002_rls_policies.sql -- used anywhere a
  read-only client is enough (mirrors what the frontend does).

Both read credentials from environment variables (see .env.example at the
repo root) via python-dotenv -- never hardcoded, never committed.
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

# Real credentials live in backend/.env (SUPABASE_URL / SUPABASE_ANON_KEY /
# SUPABASE_SERVICE_ROLE_KEY are already populated there). Load it explicitly
# by path so this works regardless of the caller's cwd -- a bare load_dotenv()
# only checks cwd and would silently miss it when a script is run from the
# repo root. Falls back to a repo-root .env if one exists (won't override
# values already loaded from backend/.env, load_dotenv defaults to non-clobber).
_BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")


def _require(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env at the repo root and fill it in "
            f"(SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY -- "
            f"Project Settings -> API in the Supabase dashboard)."
        )
    return value


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    """Service-role client -- bypasses RLS. Writes only. Never expose this key
    to the frontend or commit it anywhere."""
    url = _require(SUPABASE_URL, "SUPABASE_URL")
    key = _require(SUPABASE_SERVICE_ROLE_KEY, "SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    """Anon/publishable-key client -- subject to the public-read RLS policies.
    Use this for anything that should behave the same way the frontend does."""
    url = _require(SUPABASE_URL, "SUPABASE_URL")
    key = _require(SUPABASE_ANON_KEY, "SUPABASE_ANON_KEY")
    return create_client(url, key)
