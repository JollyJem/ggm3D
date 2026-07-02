"""Product builders. Geometry in mm Z-up, returned as a Y-up meter Scene
with origin at floor center, resting on the ground plane.
"""

import numpy as np
import trimesh

from app.generator import parts
from app.generator.materials import apply_material, dark_plastic, stainless
from app.schemas import BuildSpec

SLAB_T = 40.0
DOOR_T = 25.0
HANDLE_D = 35.0
FEET_H = 100.0
BASIN_DEPTH = 250.0


def _to_scene(
    steel: list[trimesh.Trimesh], plastic: list[trimesh.Trimesh] | None = None
) -> trimesh.Scene:
    """Merge parts per material, rotate Z-up mm -> Y-up meters."""
    rot = trimesh.transformations.rotation_matrix(np.radians(-90), [1, 0, 0])
    scene = trimesh.Scene()
    groups = [("steel", steel, stainless()), ("plastic", plastic or [], dark_plastic())]
    for name, meshes, material in groups:
        if not meshes:
            continue
        mesh = trimesh.util.concatenate(meshes)
        mesh.apply_transform(rot)
        mesh.apply_scale(0.001)
        apply_material(mesh, material)
        scene.add_geometry(mesh, geom_name=name)
    return scene


def build_work_table(spec: BuildSpec) -> trimesh.Scene:
    w, d, h = float(spec.width_mm), float(spec.depth_mm), float(spec.height_mm)
    steel = [parts.top_slab(w, d, top_z=h, thickness=SLAB_T)]
    steel += parts.legs(w, d, height=h - SLAB_T)
    if spec.features.get("undershelf", True):
        steel.append(parts.undershelf(w, d))
    return _to_scene(steel)


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
    return _to_scene(steel, plastic)


def build_sink(spec: BuildSpec) -> trimesh.Scene:
    w, d, h = float(spec.width_mm), float(spec.depth_mm), float(spec.height_mm)
    basins = max(1, int(spec.features.get("basins", 1)))
    bw = min(500.0, w / basins - 150)
    bd = d - 250
    centers = [-w / 4] if basins == 1 else [
        -w / 2 + (i + 0.5) * w / basins for i in range(basins)
    ]
    slab = parts.top_slab(w, d, top_z=h, thickness=SLAB_T)
    for cx in centers:
        hole = parts.box_part(bw, bd, SLAB_T * 3, (cx, 0, h - SLAB_T / 2))
        slab = slab.difference(hole)
    steel = [slab]
    steel += [parts.basin(bw, bd, BASIN_DEPTH, top_z=h, center_x=cx) for cx in centers]
    steel += parts.legs(w, d, height=h - SLAB_T)
    if spec.features.get("undershelf", False):
        steel.append(parts.undershelf(w, d))
    return _to_scene(steel)
