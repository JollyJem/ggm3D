import io

import numpy as np
import pytest
import trimesh

from app.generator import parts
from app.generator.parametric import (
    BACKSPLASH_H,
    BASIN_DEPTH,
    CASTER_H,
    DBL_BASIN_DEPTH,
    DBL_DRAIN_BACK,
    DBL_DRAINER_X,
    DBL_RIB_PITCH,
    RIB_H,
    build_fridge,
    build_sink,
    build_work_table,
    to_scene,
)
from app.generator.sanitize import sanitize_mesh
from app.schemas import BuildSpec
from scripts.inspect_glb import mesh_stats

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


# Sizes other than the two catalog SKUs. The double-sink layout is written as
# the real 2000 x 700 unit and the single basin defaults to 500 mm wide, so
# both only stay inside their own bounding box if the layout is fitted to the
# spec. Read absolutely, a 1200 mm double sink measured 1634 x 640 and an
# 800 mm single sink 865 mm — a wrong-size object placed in a real room.
RESIZED_SINKS = [
    BuildSpec(
        product_type="sink", width_mm=1200, depth_mm=600, height_mm=850,
        features={"basins": 2, "drainer": "right", "backsplash": True},
    ),
    BuildSpec(
        product_type="sink", width_mm=1600, depth_mm=700, height_mm=900,
        features={"basins": 2, "drainer": "left", "backsplash": True},
    ),
    BuildSpec(
        product_type="sink", width_mm=800, depth_mm=600, height_mm=850,
        features={"basins": 1},
    ),
    BuildSpec(
        product_type="sink", width_mm=600, depth_mm=500, height_mm=850,
        features={"basins": 1, "drainer": "right"},
    ),
]


@pytest.mark.parametrize(
    "spec", RESIZED_SINKS, ids=lambda s: f"{s.width_mm}x{s.depth_mm}_{s.features['basins']}b"
)
def test_sinks_hold_their_bounding_box_at_any_size(spec):
    low, high = build_sink(spec).bounds
    extents = high - low
    assert abs(extents[0] - spec.width_mm * 0.001) <= TOL
    assert abs(extents[1] - spec.height_mm * 0.001) <= TOL
    assert abs(extents[2] - spec.depth_mm * 0.001) <= TOL
    assert abs(low[1]) <= TOL  # still resting on the ground plane


@pytest.mark.parametrize(("builder", "spec"), CASES, ids=IDS)
def test_glb_exports_clean_and_under_1mb(builder, spec):
    glb = builder(spec).export(file_type="glb")
    assert len(glb) < 1_000_000
    reloaded = trimesh.load(io.BytesIO(glb), file_type="glb")
    assert reloaded.geometry
    assert all(m.faces.size > 0 for m in reloaded.geometry.values())


# (metallicFactor, roughnessFactor) per material group
EXPECTED_MATERIALS = {"steel": (1.0, 0.40), "worktop": (1.0, 0.50), "plastic": (0.0, 0.6)}


@pytest.mark.parametrize(("builder", "spec"), CASES, ids=IDS)
def test_material_presets_per_group(builder, spec):
    scene = builder(spec)
    for name, mesh in scene.geometry.items():
        metallic, roughness = EXPECTED_MATERIALS[name]
        material = mesh.visual.material
        assert material.metallicFactor == pytest.approx(metallic), name
        assert material.roughnessFactor == pytest.approx(roughness), name


def test_flat_panels_keep_a_normal_per_face():
    """Shared box vertices would average into corner normals and shade a cube
    like a sphere. Every edge of a box is 90 degrees, or 45 at a chamfer, so
    nothing may be smoothed across: each vertex carries its own face normal."""
    for part in (parts.box_part(600, 700, 40, (0, 0, 20)),
                 parts.chamfer_box(parts.box_part(600, 700, 40, (0, 0, 20)))):
        mesh = to_scene([part]).geometry["steel"]
        expected = np.repeat(mesh.face_normals, 3, axis=0)
        assert np.allclose(mesh.vertex_normals, expected, atol=1e-6)


def test_curved_parts_are_shaded_smooth():
    """A 16-section cylinder steps 22.5 degrees per facet. Left flat-shaded it
    reads as a nut, which is what caster wheels and pressed basins came out as;
    the wall must share normals while the cap edge stays sharp."""
    mesh = to_scene([parts.cylinder_part(35.0, 100.0, (0, 0, 50))]).geometry["steel"]
    normals = np.asarray(mesh.vertex_normals)
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-6)
    upright = np.abs(normals[:, 1]) < 1e-6  # Y-up scene: the barrel, not the caps
    face_normals_ = np.repeat(mesh.face_normals, 3, axis=0)
    assert upright.any()
    assert not np.allclose(normals[upright], face_normals_[upright], atol=1e-3)
    # the caps meet the barrel at 90 degrees and keep their own normal
    caps = np.abs(face_normals_[:, 1]) > 1 - 1e-6
    assert np.allclose(normals[caps], face_normals_[caps], atol=1e-6)


@pytest.mark.parametrize(("builder", "spec"), CASES, ids=IDS)
def test_every_normal_is_a_unit_vector(builder, spec):
    for mesh in builder(spec).geometry.values():
        lengths = np.linalg.norm(np.asarray(mesh.vertex_normals), axis=1)
        assert np.allclose(lengths, 1.0, atol=1e-6)


def test_worktops_and_drainers_get_the_rougher_preset():
    # both the work table top and the sink worktop plus drainer ribs
    assert "worktop" in build_work_table(WORK_TABLE).geometry
    assert "worktop" in build_sink(DOUBLE_SINK).geometry


def test_chamfer_keeps_the_bounding_box_and_stays_watertight():
    box = parts.box_part(1200, 700, 40, (5, -3, 900))
    cham = parts.chamfer_box(box)
    # face planes are untouched, so the part still matches its spec dimensions
    assert np.allclose(cham.bounds, box.bounds)
    assert cham.is_watertight
    assert cham.is_winding_consistent
    assert cham.volume < box.volume  # material really was cut off the edges


def test_chamfer_never_eats_a_thin_part():
    thin = parts.box_part(8, 400, 4, (0, 0, 0))  # 4 mm rib, thinner than 2x chamfer
    cham = parts.chamfer_box(thin)
    assert np.allclose(cham.bounds, thin.bounds)
    assert cham.is_watertight
    assert cham.volume > 0


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
    # the wheels are dark rubber and are the only thing touching the floor
    assert "plastic" in scene.geometry
    assert scene.geometry["plastic"].bounds[0][1] == pytest.approx(0.0, abs=TOL)
    # the caster bracket is steel, like the bright chrome fork in the photo, so
    # steel now reaches below the leg -- but never down to the ground plane
    assert 0.0 < scene.geometry["steel"].bounds[0][1] < CASTER_H * 0.001
    # tabletop at the full spec height, casters counted inside it
    assert _top_hit_y(scene, 0.0) == pytest.approx(WORK_TABLE.height_mm * 0.001, abs=TOL)


def test_work_table_wheels_stay_inside_the_footprint():
    """A swivel caster's wheel hangs off the swivel axis. Pointed outward it
    would put rubber past the edge of a table the catalog calls 600 mm wide."""
    scene = build_work_table(WORK_TABLE)
    wheels = scene.geometry["plastic"].bounds
    assert wheels[0][0] >= -WORK_TABLE.width_mm * 0.0005 - TOL
    assert wheels[1][0] <= WORK_TABLE.width_mm * 0.0005 + TOL
    assert wheels[0][2] >= -WORK_TABLE.depth_mm * 0.0005 - TOL
    assert wheels[1][2] <= WORK_TABLE.depth_mm * 0.0005 + TOL


# the unit is built in absolute mm (X 0..2000, Y 0..700) then recentered, so a
# probe at absolute (X, Y) maps to centered ray coords (X - 1000, Y - 350).
WORKTOP = (DOUBLE_SINK.height_mm - BACKSPLASH_H) * 0.001  # 0.870 m


def test_double_sink_two_basins_on_the_left():
    scene = build_sink(DOUBLE_SINK)
    # basin 1 (X 90..690) and basin 2 (X 760..1360), the two 600 x 500 x 300 mm
    # bowls the spec sheet gives. Both belong to the cabinet section, left of
    # the right leg line at X 1400 -- 1200 mm of bowl does not fit left of the
    # midpoint of a 2000 mm unit, and the real product does not put it there.
    for cx in (390.0 - 1000, 1060.0 - 1000):
        assert cx < 1400.0 - 1000
        assert _top_hit_y(scene, cx) == pytest.approx(WORKTOP - DBL_BASIN_DEPTH * 0.001, abs=TOL)


def test_double_sink_bowls_hold_nothing_but_a_flat_drain():
    """The waste outlet is a disc on the bowl floor. A 200 mm overflow standpipe
    stood here once and from every angle that looked into the bowl -- which is
    most of them, on a 970 mm unit -- it read as a post left in the sink."""
    scene = build_sink(DOUBLE_SINK)
    floor = WORKTOP - DBL_BASIN_DEPTH * 0.001
    drain_y = 325.0 + DBL_DRAIN_BACK  # bowl centre, set back, in absolute mm
    for bowl_x in (355.0, 1000.0):
        top = _top_hit_y(scene, bowl_x - 1000, y_mm=drain_y - 350)
        assert floor < top < floor + 0.01


def test_double_sink_drainer_then_flat_worktop_on_right():
    scene = build_sink(DOUBLE_SINK)
    # the drainer sits over the 600 mm overhang: a raised rib above the worktop.
    # derived from the layout rather than written out, so retuning the flute
    # spacing does not silently move the probe into a gap between ribs.
    rib_x = DBL_DRAINER_X[0] + 7 * DBL_RIB_PITCH
    assert _top_hit_y(scene, rib_x - 1000) == pytest.approx(WORKTOP + RIB_H * 0.001, abs=TOL)
    # flat worktop past the drainer's right end, at the plain worktop height
    assert _top_hit_y(scene, 1975.0 - 1000) == pytest.approx(WORKTOP, abs=TOL)
    # the left section opens into a basin instead of a flat top
    assert _top_hit_y(scene, 390.0 - 1000) < WORKTOP - 0.1


def test_double_sink_open_bay_under_the_drainer():
    scene = build_sink(DOUBLE_SINK)
    # right section (X > 1400) is open: under the cantilevered worktop there is
    # nothing but the slab, so the lowest surface sits high near the worktop.
    # probe just past the right leg line and again near the right end, to be
    # sure the dishwasher bay stays clear across the whole overhang.
    assert _bottom_hit_y(scene, 1500.0 - 1000) > WORKTOP - 0.1
    assert _bottom_hit_y(scene, 1900.0 - 1000) > WORKTOP - 0.1
    # left cabinet has the lower undershelf (~200 mm), far below the worktop
    assert _bottom_hit_y(scene, 600.0 - 1000) < 0.25


def test_double_sink_four_legs_frame_left_section_only():
    scene = build_sink(DOUBLE_SINK)
    # a leg on its foot reaches the floor at the right leg line X 1400...
    y_leg = 80.0 - 350  # front leg row
    assert _bottom_hit_y(scene, 1400.0 - 1000, y_mm=y_leg) == pytest.approx(0.0, abs=TOL)
    # ...and there is no leg past it: at X 1550 the only surface is the
    # cantilevered worktop underside, high above the floor
    assert _bottom_hit_y(scene, 1550.0 - 1000, y_mm=y_leg) > 0.7


def test_double_sink_front_apron_under_the_basins():
    scene = build_sink(DOUBLE_SINK)
    y_front = 7.0 - 350  # just behind the front face, inside the apron panel
    # front apron (X 60..1400) hangs to Z 560 under the basins
    assert _bottom_hit_y(scene, 300.0 - 1000, y_mm=y_front) == pytest.approx(0.560, abs=TOL)
    # apron stops at the right leg line: past X 1400 there is no apron, only
    # the front rim reaches down, same as the open bay further right
    assert _bottom_hit_y(scene, 1500.0 - 1000, y_mm=y_front) > 0.7
    assert _bottom_hit_y(scene, 1900.0 - 1000, y_mm=y_front) > 0.7


def test_double_sink_backsplash_at_rear():
    scene = build_sink(DOUBLE_SINK)
    y_rear = 692.0 - 350  # inside the 15 mm rear upstand (Y 685..700)
    assert _top_hit_y(scene, 0.0, y_mm=y_rear) == pytest.approx(
        DOUBLE_SINK.height_mm * 0.001, abs=TOL
    )


# --- Scene Viewer budget -----------------------------------------------------
# Android Scene Viewer is the tightest consumer of these files and far less
# forgiving than model-viewer: it is the one that has to open the GLB on a
# mid-range phone while ARCore already owns the camera and the GPU. These two
# are the platform ceilings, not the current cost.
AR_TRIANGLE_CEILING = 60_000
AR_BYTE_CEILING = 500_000
# The tripwire. Every builder today lands under 1.5k triangles, so anything
# past this is a geometry bug long before it is a Scene Viewer problem — a
# primitive that quietly went back to 32 sections, or a part built per-rib
# instead of merged. Catching that here is the point; the ceilings above would
# never fire.
TRIANGLE_TRIPWIRE = 4_000


def _exported_stats(builder, spec) -> tuple[list[dict], int]:
    """Per-mesh stats of the real exported GLB, read back the way a viewer
    reads it. Uses the same helpers as scripts/inspect_glb.py so the numbers in
    a report and the numbers in this test cannot drift apart."""
    glb = builder(spec).export(file_type="glb")
    scene = trimesh.load(io.BytesIO(glb), file_type="glb", process=False)
    return [mesh_stats(mesh) for mesh in scene.geometry.values()], len(glb)


def test_double_sink_fits_the_scene_viewer_budget():
    """Product 7 is the heaviest product: 2 m wide, two basins cut out of the
    worktop with booleans, a ribbed drainer, legs, feet and a backsplash."""
    stats, size = _exported_stats(build_sink, DOUBLE_SINK)
    triangles = sum(row["triangles"] for row in stats)
    assert triangles < AR_TRIANGLE_CEILING
    assert triangles < TRIANGLE_TRIPWIRE
    assert size < AR_BYTE_CEILING
    assert size < 1_000_000


@pytest.mark.parametrize(("builder", "spec"), CASES, ids=IDS)
def test_no_non_finite_or_degenerate_geometry(builder, spec):
    """A NaN coordinate or a zero-area sliver is what actually stops Scene
    Viewer, and neither shows up in Chrome. sanitize_scene runs on every export
    precisely so these stay at zero."""
    stats, _ = _exported_stats(builder, spec)
    assert stats, "builder exported no geometry"
    for row in stats:
        assert row["non_finite_vertices"] == 0
        assert row["degenerate_faces"] == 0


@pytest.mark.parametrize(("builder", "spec"), CASES, ids=IDS)
def test_triangle_count_stays_under_the_tripwire(builder, spec):
    stats, _ = _exported_stats(builder, spec)
    assert sum(row["triangles"] for row in stats) < TRIANGLE_TRIPWIRE


@pytest.mark.parametrize(("builder", "spec"), CASES, ids=IDS)
def test_one_node_per_material_not_one_per_part(builder, spec):
    """Scene Viewer pays per node. Every part sharing a material is merged into
    a single mesh before export, so a product is at most three nodes however
    many boxes went into it."""
    scene = builder(spec)
    assert len(scene.geometry) <= 3
    assert set(scene.geometry) <= {"steel", "worktop", "plastic"}


def test_sanitize_removes_nan_slivers_and_inverted_winding():
    """The exports come out clean, so prove the sanitizer is what does it by
    handing it geometry that is deliberately broken in all three ways."""
    box = parts.box_part(100, 100, 100, (0, 0, 50))
    verts = np.vstack([box.vertices, [[np.nan, 0, 0], [0, 0, 0], [1, 0, 0]]])
    n = len(box.vertices)
    faces = np.vstack([
        box.faces,
        [n, n + 1, n + 2],  # face on a NaN vertex
        [0, 0, 1],  # zero-area sliver
        box.faces[0],  # exact duplicate of an existing face
    ])
    dirty = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    dirty.invert()  # whole shell wound inside out

    assert sanitize_mesh(dirty, "dirty") is True
    assert np.isfinite(dirty.vertices).all()
    assert len(dirty.faces) == len(box.faces)
    assert dirty.is_watertight
    assert dirty.volume > 0  # re-wound outward


def test_sanitize_leaves_a_clean_mesh_alone():
    clean = parts.box_part(100, 100, 100, (0, 0, 50))
    before = clean.faces.copy()
    assert sanitize_mesh(clean, "clean") is False
    assert np.array_equal(clean.faces, before)


def test_single_basin_sink_unchanged():
    scene = build_sink(SINGLE_SINK)
    h = SINGLE_SINK.height_mm * 0.001
    # counter top still at full height: no backsplash, no drainer slab
    assert scene.bounds[1][1] == pytest.approx(h, abs=TOL)
    # single basin opening at -w/4, flat counter on the right, as before
    w4 = SINGLE_SINK.width_mm / 4
    assert _top_hit_y(scene, -w4) == pytest.approx(h - BASIN_DEPTH * 0.001, abs=TOL)
    assert _top_hit_y(scene, w4) == pytest.approx(h, abs=TOL)
