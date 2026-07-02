"""Supabase client and product queries.

Falls back to the local seed list when Supabase is not configured, so the
dev server and the demo keep working without a database connection.
"""

from functools import lru_cache

from app.config import get_settings
from app.schemas import Product
from app.seed_data import SEED_PRODUCTS


@lru_cache
def get_client():
    """Server-side Supabase client (service key). None when not configured."""
    settings = get_settings()
    if not settings.supabase_configured:
        return None
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_service_key)


def list_products() -> list[Product]:
    client = get_client()
    if client is None:
        return [Product(**p) for p in SEED_PRODUCTS]
    rows = (
        client.table("products").select("*").order("created_at").execute().data
    )
    return [Product(**{k: v for k, v in r.items() if k in Product.model_fields}) for r in rows]


def get_product(product_id: str) -> Product | None:
    client = get_client()
    if client is None:
        return next(
            (Product(**p) for p in SEED_PRODUCTS if p["id"] == product_id), None
        )
    rows = client.table("products").select("*").eq("id", product_id).execute().data
    if not rows:
        return None
    r = rows[0]
    return Product(**{k: v for k, v in r.items() if k in Product.model_fields})
