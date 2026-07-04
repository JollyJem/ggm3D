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

# Hand-written schema for Gemini structured output. BuildSpec.features is an
# open dict, whose generated schema carries additionalProperties — rejected by
# the Gemini Developer API — so the known feature keys are spelled out here.
# The reply is still validated with BuildSpec below.
RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "product_type": {
            "type": "string",
            "enum": ["work_table", "fridge", "sink"],
        },
        "width_mm": {"type": "integer"},
        "depth_mm": {"type": "integer"},
        "height_mm": {"type": "integer"},
        "features": {
            "type": "object",
            "properties": {
                "undershelf": {"type": "boolean"},
                "doors": {"type": "integer"},
                "basins": {"type": "integer"},
                "drainer": {"type": "string", "enum": ["left", "right", "none"]},
                "backsplash": {"type": "boolean"},
            },
        },
    },
    "required": ["product_type", "width_mm", "depth_mm", "height_mm", "features"],
}


def _sink_features(product: Product) -> dict:
    """Parse sink features from the product wording, mirroring the Gemini rules."""
    text = f"{product.name} {product.description}".lower()
    features: dict = {"basins": 2 if "double" in text else 1}
    drainer = "right" if "right" in text else "left" if "left" in text else "none"
    if drainer != "none":
        features["drainer"] = drainer
    if drainer != "none" or "backsplash" in text or "upstand" in text:
        features["backsplash"] = True
    return features


def fallback_spec(product: Product) -> SpecResult:
    if product.category == "sink":
        features = _sink_features(product)
    else:
        features = dict(CATEGORY_DEFAULTS.get(product.category, {}))
    spec = BuildSpec(
        product_type=product.category,
        width_mm=product.width_mm,
        depth_mm=product.depth_mm,
        height_mm=product.height_mm,
        features=features,
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
        'category, for example {"undershelf": true}, {"doors": 1} or {"basins": 1}.\n'
        'For sinks infer "basins" (1 or 2), "drainer" ("left", "right" or "none") '
        'and "backsplash" (true or false) from the name and description. Example: '
        '"Double Sink - Right Hand Drainer" means basins 2, drainer "right", '
        "backsplash true."
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": RESPONSE_SCHEMA,
            "temperature": 0.2,
        },
    )
    spec = BuildSpec.model_validate_json(response.text)
    return SpecResult(spec=spec, source="gemini")
