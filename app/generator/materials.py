"""PBR material presets."""

import trimesh
from trimesh.visual import TextureVisuals
from trimesh.visual.material import PBRMaterial


def stainless() -> PBRMaterial:
    return PBRMaterial(
        name="stainless",
        baseColorFactor=[0.82, 0.83, 0.85, 1.0],
        metallicFactor=0.9,
        roughnessFactor=0.3,
    )


def dark_plastic() -> PBRMaterial:
    return PBRMaterial(
        name="dark_plastic",
        baseColorFactor=[0.15, 0.15, 0.16, 1.0],
        metallicFactor=0.1,
        roughnessFactor=0.6,
    )


def apply_material(mesh: trimesh.Trimesh, material: PBRMaterial) -> None:
    mesh.visual = TextureVisuals(material=material)
