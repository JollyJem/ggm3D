"""Tests always run in local mode: real keys from a developer's .env must
never reach Gemini or Supabase. Blank the env before the app is imported."""

import os

for _key in (
    "GEMINI_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_KEY",
    "HF_TOKEN",
):
    os.environ[_key] = ""

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()
