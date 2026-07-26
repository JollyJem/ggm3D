"""Supabase client and product queries.

Falls back to the local seed list when Supabase is not configured, so the
dev server and the demo keep working without a database connection.
"""

import time
from functools import lru_cache
from typing import Literal

from app.config import Settings, get_settings
from app.schemas import Product
from app.seed_data import SEED_PRODUCTS

Mode = Literal["local", "supabase"]

# The catalog is six rows that change when someone reruns the seed script, but
# it is re-queried on every page view and on every 2 s poll of a running build.
# Serving it from memory for a minute takes that traffic to roughly zero without
# anyone having to notice a stale name.
PRODUCT_TTL_SECONDS = 60.0
_products_cache: tuple[float, list[Product]] | None = None


def resolve_mode(settings: Settings | None = None) -> Mode:
    """supabase when SUPABASE_URL and SUPABASE_SERVICE_KEY are set, else local."""
    if settings is None:
        settings = get_settings()
    return "supabase" if settings.supabase_configured else "local"


MODE: Mode = resolve_mode()


@lru_cache
def get_client():
    """Server-side Supabase client (service key). None when not configured."""
    settings = get_settings()
    if not settings.supabase_configured:
        return None
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_service_key)


def _to_product(row: dict) -> Product:
    return Product(**{k: v for k, v in row.items() if k in Product.model_fields})


def list_products() -> list[Product]:
    global _products_cache
    client = get_client()
    if client is None:
        return [Product(**p) for p in SEED_PRODUCTS]
    if _products_cache and time.monotonic() - _products_cache[0] < PRODUCT_TTL_SECONDS:
        return _products_cache[1]
    rows = (
        client.table("products").select("*").order("created_at").execute().data
    )
    products = [_to_product(r) for r in rows]
    _products_cache = (time.monotonic(), products)
    return products


def get_product(product_id: str) -> Product | None:
    client = get_client()
    if client is None:
        return next(
            (Product(**p) for p in SEED_PRODUCTS if p["id"] == product_id), None
        )
    # the catalog is already in memory nine times out of ten, and a detail page
    # is always reached through it, so this is usually a dict lookup, not a query
    hit = next((p for p in list_products() if p.id == product_id), None)
    if hit is not None:
        return hit
    # not in the cached list: a row added since it was filled, so go and look.
    # Postgres rejects a malformed uuid outright rather than matching nothing,
    # so a mistyped URL arrives here as an exception and has to become a 404.
    try:
        rows = client.table("products").select("*").eq("id", product_id).execute().data
    except Exception:
        return None
    return _to_product(rows[0]) if rows else None


def invalidate_products() -> None:
    """Forget the cached catalog.

    The seed script is a separate process, so a running server picks up a
    reseed when the TTL lapses rather than through this. It exists for tests
    and for anything that ever writes products in-process.
    """
    global _products_cache
    _products_cache = None
