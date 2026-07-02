"""Settings loaded from environment variables, with a minimal .env loader."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from a .env file into os.environ (no override)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class Settings(BaseModel):
    gemini_api_key: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    hf_token: str = ""

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


@lru_cache
def get_settings() -> Settings:
    _load_env_file(ENV_FILE)
    return Settings(
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", ""),
        supabase_service_key=os.environ.get("SUPABASE_SERVICE_KEY", ""),
        hf_token=os.environ.get("HF_TOKEN", ""),
    )
