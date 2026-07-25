"""Product builders. Geometry in mm Z-up, returned as a Y-up meter Scene
with origin at floor center, resting on the ground plane.
"""

import numpy as np
import trimesh

from app.generator import parts
from app.generator.materials import (
    apply_material,
    dark_plastic,
    face_normals,
    stainless,
    stainless_worktop,
)
from app.schemas import BuildSpec

SLAB_T = 40.0
DOOR_T = 25.0
HANDLE_D = 35.0
FEET_H = 100.0
BASIN_DEPTH = 250.0
BACKSPLASH_H = 100.0
DRAINER_T = 20.0
# Commercial Dishwasher Sink Unit PREMIUM (product 7): absolute mm layout,
# X 0..2000 left->right, Y 0..700 front->back, then recentered to floor center.
DBL_WORKTOP_T = 45.0  # worktop slab thickness
DBL_RIM_H = 60.0  # downturned front/side rim under the worktop
DBL_BASIN_DEPTH = 250.0  # bowl recess below the worktop top
# basin openings (rims flush with the worktop), left section
DBL_BASIN_1 = (120.0, 560.0)  # x0, x1
DBL_BASIN_2 = (640.0, 1080.0)
DBL_BASIN_Y = (170.0, 560.0)  # both basins, front->back
# ribbed drainer, then a flat worktop out to the right edge
DBL_DRAINER_X = (1150.0, 1650.0)
DBL_DRAINER_Y = (150.0, 560.0)
RIB_H = 4.0  # drainer rib height
# four corner legs frame ONLY the left basin section (X 80..1150). The whole
# right section (drainer + flat worktop) cantilevers over an open dishwasher
# bay: no legs, no apron, no shelf there.
DBL_LEG = 40.0
DBL_LEG_X = (80.0, 1150.0)
DBL_LEG_Y = (80.0, 620.0)
DBL_APRON_X = (60.0, 1150.0)  # solid front panel under the basins only
DBL_APRON_DROP = 250.0
DBL_SHELF_TOP = 200.0  # lower undershelf top, ~200 mm above the floor
DBL_RAIL_R = 15.0  # front cross rail, ~30 mm diameter
FOOT_H = 50.0  # adjustable bullet foot under each leg
FOOT_R = 18.0
# work table: thin top with a downturned lip, legs on swivel casters
TOP_T = 20.0
LIP_H = 60.0
CASTER_H = 100.0
# leg axes sit 35 mm inside the edge; radius must stay under that so the
# wheel disc never widens the bounding box past the spec
WHEEL_R = 32.5
WHEEL_W = 32.0


def to_scene(
    steel: list[trimesh.Trimesh],
    plastic: list[trimesh.Trimesh] | None = None,
    worktop: list[trimesh.Trimesh] | None = None,
) -> trimesh.Scene:
    """Merge parts per material, rotate Z-up mm -> Y-up meters.

    Horizontal surfaces go in `worktop` so they get the rougher preset; the
    frame goes in `steel`, feet/handles/wheels in `plastic`.
    """
    rot = trimesh.transformations.rotation_matrix(np.radians(-90), [1, 0, 0])
    scene = trimesh.Scene()
    groups = [
        ("steel", steel, stainless()),
        ("worktop", worktop or [], stainless_worktop()),
        ("plastic", plastic or [], dark_plastic()),
    ]
    for name, meshes, material in groups:
        if not meshes:
            continue
        mesh = trimesh.util.concatenate(meshes)
        mesh.apply_transform(rot)
        mesh.apply_scale(0.001)
        face_normals(mesh)  # crisp facets and edge highlights, not a smoothed blob
        apply_material(mesh, material)
        scene.add_geometry(mesh, geom_name=name)
    return scene


def build_work_table(spec: BuildSpec) -> trimesh.Scene:
    w, d, h = float(spec.width_mm), float(spec.depth_mm), float(spec.height_mm)
    # h includes the casters, so the tabletop lands at the real height
    worktop = [parts.top_slab(w, d, top_z=h, thickness=TOP_T)]
    steel = parts.edge_lip(w, d, top_z=h - TOP_T, height=LIP_H)
    steel += parts.legs(w, d, height=h - TOP_T - CASTER_H, bottom_z=CASTER_H)
    if spec.features.get("undershelf", True):
        steel.append(parts.undershelf(w, d, z=CASTER_H + 100.0))
    plastic = []
    for x, y in parts.leg_centers(w, d):
        plastic.append(parts.caster_wheel(WHEEL_R, WHEEL_W, (x, y, WHEEL_R)))
        plastic.append(parts.caster_bracket(WHEEL_R, WHEEL_W, CASTER_H, (x, y, WHEEL_R)))
    return to_scene(steel, plastic, worktop)


def build_fridge(spec: BuildSpec) -> trimesh.Scene:
    w, d, h = float(spec.width_mm), float(spec.depth_mm), float(spec.height_mm)
    body_d = d - DOOR_T - HANDLE_D
    body_y = -d / 2 + body_d / 2  # body sits against the back
    door_front = d / 2 - HANDLE_D
    steel = [parts.box_part(w, body_d, h - FEET_H, (0, body_y, FEET_H + (h - FEET_H) / 2))]
    steel += parts.feet(w, body_d, height=FEET_H, center=(0.0, body_y))
    doors = max(1, int(spec.features.get("doors", 1)))
    door_w = w / doors - 20
    door_h = h - FEET_H - 40
    plastic = []
    for i in range(doors):
        cx = -w / 2 + (i + 0.5) * w / doors
        steel.append(
            parts.door_panel(door_w, door_h, cx, FEET_H + 20, door_front, DOOR_T)
        )
        handle_len = min(600.0, door_h * 0.5)
        handle_center = (
            cx + door_w / 2 - 40,
            door_front + HANDLE_D / 2,
            FEET_H + 20 + door_h / 2,
        )
        plastic.append(parts.handle(handle_len, handle_center, depth=HANDLE_D))
    return to_scene(steel, plastic)


def _basin_layout(w: float, basins: int, drainer: str, drainer_w: float):
    """Basin width and center x positions; basins share the non-drainer zone."""
    if drainer in ("left", "right"):
        zone_w = w - drainer_w
        zone_x0 = -w / 2 if drainer == "right" else -w / 2 + drainer_w
        bw = min(500.0, zone_w / basins - 150)
        centers = [zone_x0 + (i + 0.5) * zone_w / basins for i in range(basins)]
        return bw, centers
    bw = min(500.0, w / basins - 150)
    centers = [-w / 4] if basins == 1 else [
        -w / 2 + (i + 0.5) * w / basins for i in range(basins)
    ]
    return bw, centers


def _dbl_worktop(
    w: float,
    d: float,
    top_z: float,
    steel: list[trimesh.Trimesh],
    worktop: list[trimesh.Trimesh],
) -> None:
    """Full worktop: slab with two basin openings cut, recessed tubs, the ribbed
    drainer, a downturned front/side rim, and the rear backsplash."""
    slab = parts.chamfer_box(parts.box_from_bounds(0, w, 0, d, top_z - DBL_WORKTOP_T, top_z))
    y0, y1 = DBL_BASIN_Y
    for x0, x1 in (DBL_BASIN_1, DBL_BASIN_2):
        slab = slab.difference(
            parts.box_from_bounds(x0, x1, y0, y1, top_z - DBL_WORKTOP_T * 2, top_z + 1)
        )
    worktop.append(slab)
    for x0, x1 in (DBL_BASIN_1, DBL_BASIN_2):
        steel.append(
            parts.basin(
                x1 - x0, y1 - y0, DBL_BASIN_DEPTH, top_z=top_z,
                center_x=(x0 + x1) / 2, center_y=(y0 + y1) / 2,
            )
        )
    dx0, dx1 = DBL_DRAINER_X
    dy0, dy1 = DBL_DRAINER_Y
    worktop += parts.drainer_ribs(dx0, dx1, dy0, dy1, top_z, rib_h=RIB_H)
    # downturned rim on the front and both sides (the rear carries the backsplash)
    rz0, rz1 = top_z - DBL_WORKTOP_T - DBL_RIM_H, top_z - DBL_WORKTOP_T
    steel += [
        parts.box_from_bounds(0, w, 0, 15, rz0, rz1),
        parts.box_from_bounds(0, 15, 0, d, rz0, rz1),
        parts.box_from_bounds(w - 15, w, 0, d, rz0, rz1),
    ]
    steel.append(parts.box_from_bounds(0, w, d - 40, d, top_z, top_z + BACKSPLASH_H))


def _dbl_understructure(
    top_z: float, steel: list[trimesh.Trimesh], plastic: list[trimesh.Trimesh]
) -> None:
    """Four corner legs on bullet feet, the solid front apron under the basins,
    the lower undershelf, and the front cross rail. The right bay stays open."""
    leg_top = top_z - DBL_WORKTOP_T  # legs meet the worktop underside
    for lx in DBL_LEG_X:
        for ly in DBL_LEG_Y:
            steel.append(
                parts.chamfer_box(
                    parts.box_from_bounds(
                        lx - DBL_LEG / 2, lx + DBL_LEG / 2,
                        ly - DBL_LEG / 2, ly + DBL_LEG / 2, FOOT_H, leg_top,
                    )
                )
            )
            plastic.append(parts.cylinder_part(FOOT_R, FOOT_H, (lx, ly, FOOT_H / 2)))
    apron_top = top_z - DBL_RIM_H  # 810: just under the front rim
    apron_bottom = apron_top - DBL_APRON_DROP  # 560
    ax0, ax1 = DBL_APRON_X
    steel.append(
        parts.chamfer_box(parts.box_from_bounds(ax0, ax1, 0, 15, apron_bottom, apron_top))
    )
    lx0, lx1 = DBL_LEG_X
    ly0, ly1 = DBL_LEG_Y
    steel += parts.lipped_shelf(lx0, lx1, ly0, ly1, DBL_SHELF_TOP)
    steel.append(parts.round_bar_x(lx0, lx1, ly0, apron_bottom, DBL_RAIL_R))


def build_double_sink(spec: BuildSpec) -> trimesh.Scene:
    """Commercial Dishwasher Sink Unit PREMIUM (product 7). Left to right: two
    recessed basins, a ribbed drainer, then a flat worktop that cantilevers over
    an open dishwasher bay. A front apron and lower undershelf enclose the left
    cabinet; four legs on adjustable feet; a rear backsplash. Built in absolute
    mm (X 0..w, Y 0..d) then recentered so the origin sits at floor center."""
    w, d, h = float(spec.width_mm), float(spec.depth_mm), float(spec.height_mm)
    top_z = h - BACKSPLASH_H  # backsplash occupies the top 100 mm
    steel: list[trimesh.Trimesh] = []
    plastic: list[trimesh.Trimesh] = []
    worktop: list[trimesh.Trimesh] = []
    _dbl_worktop(w, d, top_z, steel, worktop)
    _dbl_understructure(top_z, steel, plastic)
    for mesh in steel + plastic + worktop:
        mesh.apply_translation((-w / 2, -d / 2, 0.0))  # origin to floor center
    return to_scene(steel, plastic, worktop)


def build_sink(spec: BuildSpec) -> trimesh.Scene:
    w, d, h = float(spec.width_mm), float(spec.depth_mm), float(spec.height_mm)
    basins = max(1, int(spec.features.get("basins", 1)))
    if basins >= 2:
        return build_double_sink(spec)
    drainer = spec.features.get("drainer", "none")
    has_splash = bool(spec.features.get("backsplash", False))
    # raised parts stay under h so the bounding box matches the spec height
    rise = BACKSPLASH_H if has_splash else DRAINER_T if drainer in ("left", "right") else 0.0
    top = h - rise
    drainer_w = min(700.0, w * 0.35)
    bw, centers = _basin_layout(w, basins, drainer, drainer_w)
    bd = d - 250
    slab = parts.top_slab(w, d, top_z=top, thickness=SLAB_T)
    for cx in centers:
        hole = parts.box_part(bw, bd, SLAB_T * 3, (cx, 0, top - SLAB_T / 2))
        slab = slab.difference(hole)
    worktop = [slab]
    steel = [parts.basin(bw, bd, BASIN_DEPTH, top_z=top, center_x=cx) for cx in centers]
    steel += parts.legs(w, d, height=top - SLAB_T)
    if drainer in ("left", "right"):
        sign = 1.0 if drainer == "right" else -1.0
        dx = sign * (w - drainer_w) / 2
        worktop.append(
            parts.drainer_board(drainer_w - 60, bd, top, center_x=dx, thickness=DRAINER_T)
        )
    if has_splash:
        steel.append(parts.backsplash(w, BACKSPLASH_H, top, back_y=-d / 2))
    if spec.features.get("undershelf", False):
        steel.append(parts.undershelf(w, d))
    return to_scene(steel, worktop=worktop)
