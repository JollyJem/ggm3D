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


class ModelRecord(BaseModel):
    id: str
    product_id: str
    method: Literal["parametric", "ai"]
    status: Literal["pending", "running", "ready", "failed"]
    glb_url: str = ""
    error: str = ""


class BuildSpec(BaseModel):
    product_type: Literal["work_table", "fridge", "sink"]
    width_mm: int
    depth_mm: int
    height_mm: int
    features: dict = {}  # example: {"undershelf": True, "doors": 1, "basins": 1}


class SpecResult(BaseModel):
    spec: BuildSpec
    source: Literal["gemini", "fallback"]
