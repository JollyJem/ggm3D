import io

import numpy as np
import pytest
import trimesh

from app.generator.parametric import (
    BACKSPLASH_H,
    BASIN_DEPTH,
    CASTER_H,
    DBL_BASIN_DEPTH,
    RIB_H,
    build_fridge,
    build_sink,
    build_work_table,
)
from app.schemas import BuildSpec

TOL = 0.001  # 1 mm, in meters

WORK_TABLE = BuildSpec(
    product_type="work_table",
    width_mm=600,
    depth_mm=700,
    height_mm=850,
    features={"undershelf": True},
)

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
    height_mm=970,  # 870 worktop + 100 backsplash
    features={"basins": 2, "drainer": "right", "backsplash": True},
)

CASES = [
    (build_work_table, WORK_TABLE),
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


def _col_heights(scene: trimesh.Scene, x_mm: float, y_mm: float = 0.0) -> np.ndarray:
    """Heights (scene meters, Y-up) of every surface a vertical ray at (x, y) mm
    crosses.

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
    return (tri[inside, :, 1] * weights).sum(1)


def _top_hit_y(scene: trimesh.Scene, x_mm: float, y_mm: float = 0.0) -> float:
    """Highest surface under a vertical ray at (x, y) mm, in scene meters."""
    return float(_col_heights(scene, x_mm, y_mm).max())


def _bottom_hit_y(scene: trimesh.Scene, x_mm: float, y_mm: float = 0.0) -> float:
    """Lowest surface under a vertical ray at (x, y) mm, in scene meters."""
    return float(_col_heights(scene, x_mm, y_mm).min())


def test_work_table_top_at_spec_height_casters_on_floor():
    scene = build_work_table(WORK_TABLE)
    # casters render in the dark material group and rest on the ground plane
    assert "plastic" in scene.geometry
    assert scene.geometry["plastic"].bounds[0][1] == pytest.approx(0.0, abs=TOL)
    # steel starts above the casters, tabletop at the full spec height
    assert scene.geometry["steel"].bounds[0][1] == pytest.approx(CASTER_H * 0.001, abs=TOL)
    assert _top_hit_y(scene, 0.0) == pytest.approx(WORK_TABLE.height_mm * 0.001, abs=TOL)


# the unit is built in absolute mm (X 0..2000, Y 0..700) then recentered, so a
# probe at absolute (X, Y) maps to centered ray coords (X - 1000, Y - 350).
WORKTOP = (DOUBLE_SINK.height_mm - BACKSPLASH_H) * 0.001  # 0.870 m


def test_double_sink_two_basins_on_the_left():
    scene = build_sink(DOUBLE_SINK)
    # basin 1 (X 120..560) and basin 2 (X 640..1080), both recessed 250 mm; their
    # centers (abs 340, 860) land in the left half of the 2000 mm width
    for cx in (340.0 - 1000, 860.0 - 1000):
        assert cx < 0.0
        assert _top_hit_y(scene, cx) == pytest.approx(WORKTOP - DBL_BASIN_DEPTH * 0.001, abs=TOL)


def test_double_sink_drainer_then_flat_worktop_on_right():
    scene = build_sink(DOUBLE_SINK)
    # ribbed drainer right of the basins: a raised rib sits above the worktop
    assert _top_hit_y(scene, 1150.0 - 1000) == pytest.approx(WORKTOP + RIB_H * 0.001, abs=TOL)
    # flat worktop to the right of the drainer, at the plain worktop height
    assert _top_hit_y(scene, 1800.0 - 1000) == pytest.approx(WORKTOP, abs=TOL)
    # the left section opens into a basin instead of a flat top
    assert _top_hit_y(scene, 340.0 - 1000) < WORKTOP - 0.1


def test_double_sink_open_bay_under_the_drainer():
    scene = build_sink(DOUBLE_SINK)
    # right section (X > 1150) is open: under the cantilevered worktop there is
    # nothing but the slab, so the lowest surface sits high near the worktop.
    # probe at X 1250 (just past the right leg line) and X 1700 to be sure the
    # bay stays open across the whole right section.
    assert _bottom_hit_y(scene, 1250.0 - 1000) > WORKTOP - 0.1
    assert _bottom_hit_y(scene, 1700.0 - 1000) > WORKTOP - 0.1
    # left cabinet has the lower undershelf (~200 mm), far below the worktop
    assert _bottom_hit_y(scene, 600.0 - 1000) < 0.25


def test_double_sink_four_legs_frame_left_section_only():
    scene = build_sink(DOUBLE_SINK)
    # a leg on its foot reaches the floor at the right leg line X 1150...
    y_leg = 80.0 - 350  # front leg row
    assert _bottom_hit_y(scene, 1150.0 - 1000, y_mm=y_leg) == pytest.approx(0.0, abs=TOL)
    # ...and there is no leg past it: at X 1300 the only surface is the
    # cantilevered worktop underside, high above the floor
    assert _bottom_hit_y(scene, 1300.0 - 1000, y_mm=y_leg) > 0.7


def test_double_sink_front_apron_under_the_basins():
    scene = build_sink(DOUBLE_SINK)
    y_front = 7.0 - 350  # just behind the front face, inside the apron panel
    # front apron (X 60..1150) hangs to Z 560 under the basins
    assert _bottom_hit_y(scene, 300.0 - 1000, y_mm=y_front) == pytest.approx(0.560, abs=TOL)
    # apron stops at the right leg line: X 1250 (past 1150) has no apron, only
    # the front rim reaches down, same as the open right bay at X 1700
    assert _bottom_hit_y(scene, 1250.0 - 1000, y_mm=y_front) > 0.7
    assert _bottom_hit_y(scene, 1700.0 - 1000, y_mm=y_front) > 0.7


def test_double_sink_backsplash_at_rear():
    scene = build_sink(DOUBLE_SINK)
    y_rear = 680.0 - 350  # inside the 40 mm rear backsplash (Y 660..700)
    assert _top_hit_y(scene, 0.0, y_mm=y_rear) == pytest.approx(
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
