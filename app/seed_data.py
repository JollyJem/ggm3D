"""The 7 demo products. Single source of truth for the seed script and
the local fallback used when Supabase is not configured.

Dimensions from public GGM Gastro catalog pages. Internal demo use only.
"""

from pathlib import Path

_IMG_DIR = Path(__file__).resolve().parent / "static" / "img"


def _image_url(slug: str) -> str:
    """Real product photo ({slug}.jpg) when present, sketch SVG until then.

    The same {category}.jpg is what pregenerate_ai_meshes.py feeds to TripoSR,
    so dropping the 6 photos into static/img needs no code changes. In
    supabase mode rerun scripts/seed_products.py so the DB rows pick them up.
    """
    if (_IMG_DIR / f"{slug}.jpg").is_file():
        return f"/static/img/{slug}.jpg"
    return f"/static/img/{slug}.svg"


SEED_PRODUCTS: list[dict] = [
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000001",
        "name": "Work table with undershelf",
        "category": "work_table",
        "width_mm": 1200,
        "depth_mm": 700,
        "height_mm": 850,
        "image_url": _image_url("work_table"),
        "description": "Stainless steel work table with a reinforced top and a full-width undershelf.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000002",
        "name": "Refrigerated cabinet",
        "category": "fridge",
        "width_mm": 700,
        "depth_mm": 810,
        "height_mm": 2050,
        "image_url": _image_url("fridge"),
        "description": "Upright stainless steel refrigerated cabinet with a single full-height door.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000003",
        "name": "Sink unit with one basin",
        "category": "sink",
        "width_mm": 1200,
        "depth_mm": 600,
        "height_mm": 850,
        "image_url": _image_url("sink"),
        "description": "Stainless steel sink unit with one deep basin and a drainer surface.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000004",
        "name": "Planetary mixer",
        "category": "mixer",
        "width_mm": 520,
        "depth_mm": 430,
        "height_mm": 780,
        "image_url": _image_url("mixer"),
        "description": "Planetary dough mixer for bakeries and commercial kitchens.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000005",
        "name": "Pre-rinse faucet",
        "category": "faucet",
        "width_mm": 250,
        "depth_mm": 300,
        "height_mm": 1200,
        "image_url": _image_url("faucet"),
        "description": "Pre-rinse spray faucet for commercial dishwashing stations.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000006",
        "name": "Contact grill",
        "category": "grill",
        "width_mm": 550,
        "depth_mm": 400,
        "height_mm": 250,
        "image_url": _image_url("grill"),
        "description": "Electric contact grill with grooved cast iron plates.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000007",
        "name": "Commercial Dishwasher Sink Unit PREMIUM",
        "category": "sink",
        "width_mm": 2000,
        "depth_mm": 700,
        "height_mm": 850,
        "image_url": _image_url("sink_double"),
        "description": "Double sink with right hand drainer and rear backsplash, stainless steel.",
    },
]
