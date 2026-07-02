"""Seed the 6 demo products into Supabase.

Usage: python scripts/seed_products.py
Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in the environment or .env.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.seed_data import SEED_PRODUCTS  # noqa: E402


def main() -> None:
    settings = get_settings()
    if not settings.supabase_configured:
        sys.exit("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set (see .env.example).")

    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_service_key)
    result = client.table("products").upsert(SEED_PRODUCTS).execute()
    print(f"Seeded {len(result.data)} products.")


if __name__ == "__main__":
    main()
