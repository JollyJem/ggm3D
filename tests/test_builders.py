import io

import pytest
import trimesh

from app.generator.parametric import build_fridge, build_sink, build_work_table
from app.schemas import BuildSpec

TOL = 0.001  # 1 mm, in meters

CASES = [
    (
        build_work_table,
        BuildSpec(
            product_type="work_table",
            width_mm=1200,
            depth_mm=700,
            height_mm=850,
            features={"undershelf": True},
        ),
    ),
    (
        build_fridge,
        BuildSpec(
            product_type="fridge",
            width_mm=700,
            depth_mm=810,
            height_mm=2050,
            features={"doors": 1},
        ),
    ),
    (
        build_sink,
        BuildSpec(
            product_type="sink",
            width_mm=1200,
            depth_mm=600,
            height_mm=850,
            features={"basins": 1},
        ),
    ),
]
IDS = [spec.product_type for _, spec in CASES]


@pytest.mark.parametrize(("builder", "spec"), CASES, ids=IDS)
def test_bounding_box_matches_spec(builder, spec):
    scene = builder(spec)
    low, high = scene.bounds
    extents = high - low
    # Y-up meters: X=width, Y=height, Z=depth
    assert abs(extents[0] - spec.width_mm * 0.001) <= TOL
    assert abs(extents[1] - spec.height_mm * 0.001) <= TOL
    assert abs(extents[2] - spec.depth_mm * 0.001) <= TOL
    # rests on the ground plane, origin at floor center
    assert abs(low[1]) <= TOL
    assert abs((low[0] + high[0]) / 2) <= TOL
    assert abs((low[2] + high[2]) / 2) <= TOL


@pytest.mark.parametrize(("builder", "spec"), CASES, ids=IDS)
def test_glb_exports_clean_and_under_1mb(builder, spec):
    glb = builder(spec).export(file_type="glb")
    assert len(glb) < 1_000_000
    reloaded = trimesh.load(io.BytesIO(glb), file_type="glb")
    assert reloaded.geometry
    assert all(m.faces.size > 0 for m in reloaded.geometry.values())
