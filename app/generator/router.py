"""Picks parametric or ai per product category."""

from typing import Literal

import trimesh

from app.generator.parametric import build_fridge, build_sink, build_work_table
from app.schemas import BuildSpec

BUILDERS = {
    "work_table": build_work_table,
    "fridge": build_fridge,
    "sink": build_sink,
}


def method_for(category: str) -> Literal["parametric", "ai"]:
    return "parametric" if category in BUILDERS else "ai"


def build_scene(spec: BuildSpec) -> trimesh.Scene:
    return BUILDERS[spec.product_type](spec)
