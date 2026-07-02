"""Rough placeholder meshes for ai-category products.

Composed from parts.py primitives at the product's real dimensions so AR
scale is correct. Replaced by real TripoSR meshes via
scripts/pregenerate_ai_meshes.py.
"""

import trimesh

from app.generator import parts
from app.generator.parametric import to_scene
from app.schemas import Product


def build_placeholder(product: Product) -> trimesh.Scene:
    builders = {"mixer": _mixer, "faucet": _faucet, "grill": _grill}
    builder = builders[product.category]
    w, d, h = float(product.width_mm), float(product.depth_mm), float(product.height_mm)
    return to_scene(builder(w, d, h))


def _mixer(w: float, d: float, h: float) -> list[trimesh.Trimesh]:
    base_h = 0.15 * h
    bowl_r = 0.28 * min(w, d)
    return [
        parts.box_part(w, d, base_h, (0, 0, base_h / 2)),
        # column at the back, carries the full height
        parts.box_part(0.35 * w, 0.35 * d, h - base_h, (0, -0.325 * d, base_h + (h - base_h) / 2)),
        # head cantilevered forward over the bowl
        parts.box_part(0.3 * w, 0.8 * d, 0.18 * h, (0, -0.1 * d, h - 0.09 * h)),
        parts.cylinder_part(bowl_r, 0.3 * h, (0, 0.1 * d, base_h + 0.15 * h)),
    ]


def _faucet(w: float, d: float, h: float) -> list[trimesh.Trimesh]:
    plate_h = 30.0
    riser_r = 0.12 * min(w, d)
    riser_y = -0.15 * d
    return [
        parts.box_part(w, d, plate_h, (0, 0, plate_h / 2)),
        parts.cylinder_part(riser_r, h - plate_h - 150, (0, riser_y, plate_h + (h - plate_h - 150) / 2)),
        # spout arm reaching forward at mid height
        parts.box_part(40.0, 0.5 * d, 35.0, (0, riser_y + 0.25 * d, 0.55 * h)),
        # spray head on top of the riser
        parts.cylinder_part(0.14 * min(w, d), 150.0, (0, riser_y, h - 75.0)),
    ]


def _grill(w: float, d: float, h: float) -> list[trimesh.Trimesh]:
    return [
        parts.box_part(w, d, 0.5 * h, (0, 0, 0.25 * h)),
        # lower and upper plates with a grill gap between them
        parts.box_part(0.9 * w, 0.85 * d, 0.06 * h, (0, 0, 0.53 * h)),
        parts.box_part(0.9 * w, 0.85 * d, 0.12 * h, (0, 0, 0.68 * h)),
        # chunky handle block at the front of the upper plate
        parts.box_part(0.45 * w, 0.15 * d, 0.26 * h, (0, 0.425 * d, 0.87 * h)),
    ]
