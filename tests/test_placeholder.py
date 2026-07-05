import io

import pytest
import trimesh

from app.generator.placeholder import build_placeholder
from app.schemas import Product

TOL = 0.001  # 1 mm, in meters

# The retired ai seed products, kept as synthetic cases: the placeholder
# builder is still live code and must honor real-scale dimensions.
AI_CASES = [
    Product(
        id="00000000-0000-4000-8000-0000000000a1",
        name="Test planetary mixer",
        category="mixer",
        width_mm=520,
        depth_mm=430,
        height_mm=780,
    ),
    Product(
        id="00000000-0000-4000-8000-0000000000a2",
        name="Test pre-rinse faucet",
        category="faucet",
        width_mm=250,
        depth_mm=300,
        height_mm=1200,
    ),
    Product(
        id="00000000-0000-4000-8000-0000000000a3",
        name="Test contact grill",
        category="grill",
        width_mm=550,
        depth_mm=400,
        height_mm=250,
    ),
]
IDS = [p.category for p in AI_CASES]


@pytest.mark.parametrize("product", AI_CASES, ids=IDS)
def test_placeholder_bounding_box_matches_product(product):
    scene = build_placeholder(product)
    low, high = scene.bounds
    extents = high - low
    assert abs(extents[0] - product.width_mm * 0.001) <= TOL
    assert abs(extents[1] - product.height_mm * 0.001) <= TOL
    assert abs(extents[2] - product.depth_mm * 0.001) <= TOL
    assert abs(low[1]) <= TOL
    assert abs((low[0] + high[0]) / 2) <= TOL
    assert abs((low[2] + high[2]) / 2) <= TOL


@pytest.mark.parametrize("product", AI_CASES, ids=IDS)
def test_placeholder_glb_exports_clean_and_under_1mb(product):
    glb = build_placeholder(product).export(file_type="glb")
    assert len(glb) < 1_000_000
    reloaded = trimesh.load(io.BytesIO(glb), file_type="glb")
    assert reloaded.geometry
    assert all(m.faces.size > 0 for m in reloaded.geometry.values())
