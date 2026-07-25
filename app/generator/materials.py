"""PBR material presets.

Stainless is a real metal: metallicFactor 1.0 and near-white baseColor, so the
surface colour comes from what it reflects, not from a painted-on grey. Without
an environment image a fully metallic surface renders black, so the viewer must
supply environment-image (see templates/partials/viewer.html).
"""

import numpy as np
import trimesh
from trimesh.visual import TextureVisuals
from trimesh.visual.material import PBRMaterial

# brushed stainless reflects almost neutrally, very slightly cool
STEEL_BASE_COLOR = [0.80, 0.81, 0.82, 1.0]


def stainless() -> PBRMaterial:
    """Vertical panels and frame: brushed steel, fairly crisp reflections."""
    return PBRMaterial(
        name="stainless",
        baseColorFactor=STEEL_BASE_COLOR,
        metallicFactor=1.0,
        roughnessFactor=0.25,
    )


def stainless_worktop() -> PBRMaterial:
    """Horizontal surfaces. Worktops are scuffed by use and face the ceiling,
    so a rougher finish reads as steel instead of a mirror."""
    return PBRMaterial(
        name="stainless_worktop",
        baseColorFactor=STEEL_BASE_COLOR,
        metallicFactor=1.0,
        roughnessFactor=0.35,
    )


def dark_plastic() -> PBRMaterial:
    """Feet, handles and caster wheels: a true dielectric, metallic 0."""
    return PBRMaterial(
        name="dark_plastic",
        baseColorFactor=[0.15, 0.15, 0.16, 1.0],
        metallicFactor=0.0,
        roughnessFactor=0.6,
    )


def apply_material(mesh: trimesh.Trimesh, material: PBRMaterial) -> None:
    mesh.visual = TextureVisuals(material=material)


def face_normals(mesh: trimesh.Trimesh) -> None:
    """Give every triangle its own vertices so each face keeps its true normal.

    trimesh.creation.box shares 8 vertices across 12 faces, so the averaged
    vertex normals point diagonally out of the corners and a cube shades like a
    sphere. Unmerging first makes the exported NORMAL accessor per-face: flat
    panels stay flat and chamfers read as distinct bright edge highlights.
    """
    mesh.unmerge_vertices()
    mesh.vertex_normals = np.repeat(mesh.face_normals, 3, axis=0)
