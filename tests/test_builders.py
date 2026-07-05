import io

import numpy as np
import pytest
import trimesh

from app.generator.parametric import (
    BACKSPLASH_H,
    BASIN_DEPTH,
    DRAINER_T,
    build_fridge,
    build_sink,
    build_work_table,
)
from app.schemas import BuildSpec

TOL = 0.001  # 1 mm, in meters

SINGLE_SINK = BuildSpec(
    product_type="sink",
    width_mm=1200,
    depth_mm=600,
    height_mm=850,
    features={"basins": 1},
)

DOUBLE_SINK = BuildSpec(
    product_type="sink",
    width_mm=2000,
    depth_mm=700,
    height_mm=850,
    features={"basins": 2, "drainer": "right", "backsplash": True},
)

CASES = [
    (
        build_work_table,
        BuildSpec(
            product_type="work_table",
            width_mm=600,
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
    (build_sink, SINGLE_SINK),
    (build_sink, DOUBLE_SINK),
]
IDS = ["work_table", "fridge", "sink", "sink_double"]


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


def _top_hit_y(scene: trimesh.Scene, x_mm: float, y_mm: float = 0.0) -> float:
    """Highest surface under a vertical ray at (x, y) mm, in scene meters (Y-up).

    Pure numpy (no rtree): project triangles onto the ground plane, find the
    ones containing the point, and interpolate their height barycentrically.
    """
    tri = scene.to_geometry().triangles  # (n, 3, 3), scene coords
    point = np.array([x_mm * 0.001, -y_mm * 0.001])  # build (x, y) -> scene (x, z)
    a, b, c = (tri[:, i][:, [0, 2]] for i in range(3))
    v0, v1, v2 = b - a, c - a, point - a
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    denom = d00 * d11 - d01 * d01
    flat = np.abs(denom) < 1e-12  # vertical faces project to degenerate triangles
    denom[flat] = 1.0
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    inside = ~flat & (u >= -1e-9) & (v >= -1e-9) & (w >= -1e-9)
    weights = np.stack([u[inside], v[inside], w[inside]], axis=1)
    return float((tri[inside, :, 1] * weights).sum(1).max())


def test_double_sink_has_two_basin_openings():
    scene = build_sink(DOUBLE_SINK)
    counter = (DOUBLE_SINK.height_mm - BACKSPLASH_H) * 0.001
    # basin zone is the left 1300 mm, basins centered at -675 and -25
    for cx in (-675.0, -25.0):
        assert _top_hit_y(scene, cx) == pytest.approx(counter - BASIN_DEPTH * 0.001, abs=TOL)


def test_double_sink_drainer_raised_on_right():
    scene = build_sink(DOUBLE_SINK)
    counter = (DOUBLE_SINK.height_mm - BACKSPLASH_H) * 0.001
    # drainer zone is the right 700 mm, its slab sits on the counter
    assert _top_hit_y(scene, 650.0) == pytest.approx(counter + DRAINER_T * 0.001, abs=TOL)
    # the mirrored point on the left opens into a basin instead
    assert _top_hit_y(scene, -650.0) < counter - 0.1


def test_double_sink_backsplash_at_rear():
    scene = build_sink(DOUBLE_SINK)
    back_y = -DOUBLE_SINK.depth_mm / 2 + 15  # inside the 30 mm rear panel
    assert _top_hit_y(scene, 0.0, y_mm=back_y) == pytest.approx(
        DOUBLE_SINK.height_mm * 0.001, abs=TOL
    )


def test_single_basin_sink_unchanged():
    scene = build_sink(SINGLE_SINK)
    h = SINGLE_SINK.height_mm * 0.001
    # counter top still at full height: no backsplash, no drainer slab
    assert scene.bounds[1][1] == pytest.approx(h, abs=TOL)
    # single basin opening at -w/4, flat counter on the right, as before
    w4 = SINGLE_SINK.width_mm / 4
    assert _top_hit_y(scene, -w4) == pytest.approx(h - BASIN_DEPTH * 0.001, abs=TOL)
    assert _top_hit_y(scene, w4) == pytest.approx(h, abs=TOL)
