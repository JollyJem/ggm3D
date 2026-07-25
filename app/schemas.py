"""Pydantic models for requests, responses, and build specs."""

from typing import Literal

from pydantic import BaseModel


class Product(BaseModel):
    id: str
    name: str
    category: str
    width_mm: int
    depth_mm: int
    height_mm: int
    image_url: str = ""
    description: str = ""
    # public GGM Gastro catalog page for this product; empty hides the link
    product_url: str = ""


class ModelRecord(BaseModel):
    id: str
    product_id: str
    method: Literal["parametric", "ai"]
    status: Literal["pending", "running", "ready", "failed"]
    glb_url: str = ""
    usdz_url: str = ""
    error: str = ""


class BuildSpec(BaseModel):
    product_type: Literal["work_table", "fridge", "sink"]
    width_mm: int
    depth_mm: int
    height_mm: int
    # examples: {"undershelf": True}, {"doors": 1},
    # {"basins": 2, "drainer": "right", "backsplash": True}
    # sink keys: basins int, drainer "left" | "right" | "none", backsplash bool
    features: dict = {}


class SpecResult(BaseModel):
    # spec is None for ai meshes (placeholder or TripoSR), which have no BuildSpec
    spec: BuildSpec | None = None
    source: Literal["gemini", "fallback", "placeholder", "triposr"]
