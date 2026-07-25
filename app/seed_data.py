"""The 2 demo products. Single source of truth for the seed script and
the local fallback used when Supabase is not configured.

Dimensions from public GGM Gastro catalog pages. Internal demo use only.
"""

from pathlib import Path

_IMG_DIR = Path(__file__).resolve().parent / "static" / "img"


def _image_url(slug: str) -> str:
    """Real product photo ({slug}.jpg) when present, sketch SVG until then.

    Dropping a photo into static/img needs no code changes. In supabase
    mode rerun scripts/seed_products.py so the DB rows pick it up.
    """
    if (_IMG_DIR / f"{slug}.jpg").is_file():
        return f"/static/img/{slug}.jpg"
    return f"/static/img/{slug}.svg"


SEED_PRODUCTS: list[dict] = [
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000001",
        "name": "Commercial Stainless Steel Centre Table PREMIUM - 600x700mm - with Undershelf",
        "category": "work_table",
        "width_mm": 600,
        "depth_mm": 700,
        "height_mm": 850,
        "image_url": _image_url("work_table"),
        "description": "Stainless steel work table with a reinforced top and a full-width undershelf.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000007",
        "name": "Commercial Dishwasher Sink Unit PREMIUM",
        "category": "sink",
        "width_mm": 2000,
        "depth_mm": 700,
        "height_mm": 970,
        "image_url": _image_url("sink_double"),
        "description": "Double sink with right hand drainer and rear backsplash, stainless steel.",
    },
]
