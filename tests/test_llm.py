import typing

from app import llm
from app.config import Settings
from app.schemas import BuildSpec, Product


def _product(category: str) -> Product:
    return Product(
        id="test-id",
        name="Test product",
        category=category,
        width_mm=1000,
        depth_mm=600,
        height_mm=900,
    )


def test_fallback_spec_without_key(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: Settings())
    for category, features in [
        ("work_table", {"undershelf": True}),
        ("fridge", {"doors": 1}),
        ("sink", {"basins": 1}),
    ]:
        result = llm.get_build_spec(_product(category))
        assert result.source == "fallback"
        assert result.spec.product_type == category
        assert result.spec.features == features
        assert result.spec.width_mm == 1000


def test_fallback_parses_sink_keywords(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: Settings())
    product = _product("sink")
    product.name = "Double Sink - Right Hand Drainer"
    result = llm.get_build_spec(product)
    assert result.source == "fallback"
    assert result.spec.features == {"basins": 2, "drainer": "right", "backsplash": True}


def test_response_schema_matches_buildspec():
    # the hand-written Gemini schema must not drift from the Pydantic model
    assert set(llm.RESPONSE_SCHEMA["properties"]) == set(BuildSpec.model_fields)
    assert llm.RESPONSE_SCHEMA["properties"]["product_type"]["enum"] == list(
        typing.get_args(BuildSpec.model_fields["product_type"].annotation)
    )
    assert "additionalProperties" not in str(llm.RESPONSE_SCHEMA)
