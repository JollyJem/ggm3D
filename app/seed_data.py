"""The 6 demo products. Single source of truth for the seed script and
the local fallback used when Supabase is not configured.

Dimensions from public GGM Gastro catalog pages. Internal demo use only.
"""

SEED_PRODUCTS: list[dict] = [
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000001",
        "name": "Work table with undershelf",
        "category": "work_table",
        "width_mm": 1200,
        "depth_mm": 700,
        "height_mm": 850,
        "image_url": "/static/img/work_table.svg",
        "description": "Stainless steel work table with a reinforced top and a full-width undershelf.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000002",
        "name": "Refrigerated cabinet",
        "category": "fridge",
        "width_mm": 700,
        "depth_mm": 810,
        "height_mm": 2050,
        "image_url": "/static/img/fridge.svg",
        "description": "Upright stainless steel refrigerated cabinet with a single full-height door.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000003",
        "name": "Sink unit with one basin",
        "category": "sink",
        "width_mm": 1200,
        "depth_mm": 600,
        "height_mm": 850,
        "image_url": "/static/img/sink.svg",
        "description": "Stainless steel sink unit with one deep basin and a drainer surface.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000004",
        "name": "Planetary mixer",
        "category": "mixer",
        "width_mm": 520,
        "depth_mm": 430,
        "height_mm": 780,
        "image_url": "/static/img/mixer.svg",
        "description": "Planetary dough mixer for bakeries and commercial kitchens.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000005",
        "name": "Pre-rinse faucet",
        "category": "faucet",
        "width_mm": 250,
        "depth_mm": 300,
        "height_mm": 1200,
        "image_url": "/static/img/faucet.svg",
        "description": "Pre-rinse spray faucet for commercial dishwashing stations.",
    },
    {
        "id": "0b6f9c1a-1111-4a01-8a01-000000000006",
        "name": "Contact grill",
        "category": "grill",
        "width_mm": 550,
        "depth_mm": 400,
        "height_mm": 250,
        "image_url": "/static/img/grill.svg",
        "description": "Electric contact grill with grooved cast iron plates.",
    },
]
