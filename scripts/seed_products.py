"""Seed the 6 demo products into Supabase.

Usage: python scripts/seed_products.py
In supabase mode (SUPABASE_URL and SUPABASE_SERVICE_KEY set) the products are
upserted into Postgres; in local mode the script prints a note and exits.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.seed_data import SEED_PRODUCTS  # noqa: E402


def main() -> None:
    if db.MODE != "supabase":
        print(
            "Local mode: the app serves the built-in seed list, nothing to do.\n"
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY (see .env.example) to seed."
        )
        return
    result = db.get_client().table("products").upsert(SEED_PRODUCTS).execute()
    print(f"Seeded {len(result.data)} products.")


if __name__ == "__main__":
    main()
