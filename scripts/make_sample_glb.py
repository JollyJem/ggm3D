"""Generate the Phase 1 hand-placed sample GLB (a simple work table).

Usage: python scripts/make_sample_glb.py
Writes app/static/models/sample.glb. Geometry is built in mm with Z up,
rotated to glTF Y-up and scaled to meters on export. Origin at floor
center, model resting on the ground plane, so AR shows true size.
"""

from pathlib import Path

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial

OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "models" / "sample.glb"

# Work table with undershelf, 1200 x 700 x 850 mm
W, D, H = 1200.0, 700.0, 850.0
TOP_T = 40.0     # top slab thickness
LEG = 40.0       # square leg side
INSET = 15.0     # leg inset from edges
SHELF_T = 20.0   # undershelf thickness
SHELF_Z = 150.0  # undershelf height


def box(size_xyz: tuple, center_xyz: tuple) -> trimesh.Trimesh:
    b = trimesh.creation.box(extents=size_xyz)
    b.apply_translation(center_xyz)
    return b


def build_table() -> trimesh.Trimesh:
    parts = [box((W, D, TOP_T), (0, 0, H - TOP_T / 2))]
    lx = W / 2 - INSET - LEG / 2
    ly = D / 2 - INSET - LEG / 2
    leg_h = H - TOP_T
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box((LEG, LEG, leg_h), (sx * lx, sy * ly, leg_h / 2)))
    shelf_w = 2 * lx - LEG
    shelf_d = 2 * ly - LEG
    parts.append(box((shelf_w, shelf_d, SHELF_T), (0, 0, SHELF_Z)))
    return trimesh.util.concatenate(parts)


def main() -> None:
    mesh = build_table()
    # Z-up mm -> Y-up meters
    rot = trimesh.transformations.rotation_matrix(np.radians(-90), [1, 0, 0])
    mesh.apply_transform(rot)
    mesh.apply_scale(0.001)
    mesh.visual = trimesh.visual.TextureVisuals(
        material=PBRMaterial(
            baseColorFactor=[0.82, 0.83, 0.85, 1.0],
            metallicFactor=0.9,
            roughnessFactor=0.3,
        )
    )
    scene = trimesh.Scene({"work_table": mesh})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    scene.export(OUT)
    size_kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT} ({size_kb:.0f} KB), bounds m: {scene.bounds.round(3).tolist()}")


if __name__ == "__main__":
    main()
