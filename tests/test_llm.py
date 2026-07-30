import types
import typing

import google

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


def _stub_gemini(monkeypatch, reply: BuildSpec) -> dict:
    """Answer the next Gemini call with `reply`. Returns the captured kwargs."""
    captured: dict = {}

    class _Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(text=reply.model_dump_json())

    class _Client:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.models = _Models()

    monkeypatch.setattr(llm, "get_settings", lambda: Settings(gemini_api_key="k"))
    monkeypatch.setattr(google, "genai", types.SimpleNamespace(Client=_Client), raising=False)
    return captured


def test_gemini_cannot_change_the_size_or_the_builder(monkeypatch):
    """Only the features come from the model. A reply that disagrees about the
    dimensions would place a wrong-size object in a real room, and one that
    disagrees about product_type would pick a different builder entirely."""
    product = _product("sink")
    _stub_gemini(
        monkeypatch,
        BuildSpec(
            product_type="work_table",
            width_mm=1,
            depth_mm=2,
            height_mm=3,
            features={"basins": 2, "drainer": "right"},
        ),
    )
    result = llm.get_build_spec(product)
    assert result.source == "gemini"
    assert result.spec.product_type == "sink"
    assert (result.spec.width_mm, result.spec.depth_mm, result.spec.height_mm) == (
        1000,
        600,
        900,
    )
    assert result.spec.features == {"basins": 2, "drainer": "right"}


def test_gemini_call_carries_a_timeout(monkeypatch):
    """Generate has a 30 s budget. Without this a hung request leaves the demo
    on a spinner instead of falling through to the deterministic fallback."""
    product = _product("work_table")
    captured = _stub_gemini(
        monkeypatch,
        BuildSpec(
            product_type="work_table", width_mm=1, depth_mm=1, height_mm=1, features={}
        ),
    )
    llm.get_build_spec(product)
    timeout = captured["client_kwargs"]["http_options"]["timeout"]
    assert 0 < timeout <= 30_000  # milliseconds, inside the Generate budget


def test_spec_matches_rejects_a_resized_product():
    product = _product("sink")
    fresh = llm.fallback_spec(product).spec
    assert llm.spec_matches(fresh, product)
    assert not llm.spec_matches(None, product)
    # the catalog row is corrected; the spec cached from the old row is stale
    product.width_mm = 1400
    assert not llm.spec_matches(fresh, product)
    # so is one built for a different builder
    product.width_mm = 1000
    product.category = "work_table"
    assert not llm.spec_matches(fresh, product)


def test_response_schema_matches_buildspec():
    # the hand-written Gemini schema must not drift from the Pydantic model
    assert set(llm.RESPONSE_SCHEMA["properties"]) == set(BuildSpec.model_fields)
    assert llm.RESPONSE_SCHEMA["properties"]["product_type"]["enum"] == list(
        typing.get_args(BuildSpec.model_fields["product_type"].annotation)
    )
    assert "additionalProperties" not in str(llm.RESPONSE_SCHEMA)
