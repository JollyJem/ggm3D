"""Gemini provider layer. Single swap point for a local model later.

Without GEMINI_API_KEY (or on any Gemini failure) a deterministic fallback
spec is built from the product's stored dimensions and category defaults,
so Generate works with no keys and survives a Gemini outage.
"""

import logging

from app.config import get_settings
from app.schemas import BuildSpec, Product, SpecResult

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"

CATEGORY_DEFAULTS: dict[str, dict] = {
    "work_table": {"undershelf": True},
    "fridge": {"doors": 1},
    "sink": {"basins": 1},
}


def fallback_spec(product: Product) -> SpecResult:
    spec = BuildSpec(
        product_type=product.category,
        width_mm=product.width_mm,
        depth_mm=product.depth_mm,
        height_mm=product.height_mm,
        features=dict(CATEGORY_DEFAULTS.get(product.category, {})),
    )
    return SpecResult(spec=spec, source="fallback")


def get_build_spec(product: Product) -> SpecResult:
    if not get_settings().gemini_api_key:
        return fallback_spec(product)
    try:
        return _gemini_spec(product)
    except Exception:
        logger.exception("Gemini spec failed, using fallback")
        return fallback_spec(product)


def _gemini_spec(product: Product) -> SpecResult:
    from google import genai

    client = genai.Client(api_key=get_settings().gemini_api_key)
    prompt = (
        "Create a build spec for a 3D model of this commercial kitchen product.\n"
        f"Name: {product.name}\n"
        f"Category: {product.category}\n"
        f"Dimensions (W x D x H): {product.width_mm} x {product.depth_mm} "
        f"x {product.height_mm} mm\n"
        f"Description: {product.description}\n"
        "Use the exact dimensions given. Set features appropriate for the "
        'category, for example {"undershelf": true}, {"doors": 1} or {"basins": 1}.'
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": BuildSpec,
            "temperature": 0.2,
        },
    )
    spec = BuildSpec.model_validate_json(response.text)
    return SpecResult(spec=spec, source="gemini")
