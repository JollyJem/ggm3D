from app import llm
from app.config import Settings
from app.schemas import Product


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
