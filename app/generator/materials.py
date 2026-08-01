"""PBR material presets.

Stainless is a real metal: metallicFactor 1.0 and near-white baseColor, so the
surface colour comes from what it reflects, not from a painted-on grey. Without
an environment image a fully metallic surface renders black, so the viewer must
supply environment-image (see templates/partials/viewer.html).
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from trimesh.visual import TextureVisuals
from trimesh.visual.material import PBRMaterial

# Brushed stainless reflects almost neutrally, very slightly cool. Held bright:
# the catalog photos are shot in a white studio and the panels come out close to
# white, so a darker base reads as painted grey steel next to them.
STEEL_BASE_COLOR = [0.87, 0.88, 0.89, 1.0]


def stainless() -> PBRMaterial:
    """Vertical panels and frame: brushed steel, not a mirror.

    0.4 rather than the 0.25 this started at. Brushed stainless scatters its
    reflection, and a crisper setting made every vertical panel a picture of
    whatever happened to be opposite it: dark where the environment is dark,
    which is the opposite of the near-white apron in the catalog photo.
    """
    return PBRMaterial(
        name="stainless",
        baseColorFactor=STEEL_BASE_COLOR,
        metallicFactor=1.0,
        roughnessFactor=0.40,
    )


def stainless_worktop() -> PBRMaterial:
    """Horizontal surfaces. Worktops are scuffed by use and face the ceiling,
    so a rougher finish reads as steel instead of a mirror."""
    return PBRMaterial(
        name="stainless_worktop",
        baseColorFactor=STEEL_BASE_COLOR,
        metallicFactor=1.0,
        roughnessFactor=0.50,
    )


def dark_plastic() -> PBRMaterial:
    """Feet, handles and caster wheels: a true dielectric, metallic 0.

    Grey rather than near-black. The caster tyres in the product photo are grey
    rubber, and at 0.15 they rendered as holes punched under the legs.
    """
    return PBRMaterial(
        name="dark_plastic",
        baseColorFactor=[0.30, 0.30, 0.31, 1.0],
        metallicFactor=0.0,
        roughnessFactor=0.6,
    )


def nameplate() -> PBRMaterial:
    """The riveted ggmgastro plate on the front edge, as a texture.

    The only textured material here, and the only reason a product exports a
    fourth node: lettering cannot be shared with the steel it sits on, and as
    geometry it would cost more triangles than the whole unit. A dielectric,
    not metal — the plate is printed, so its colour is its own.
    """
    return PBRMaterial(
        name="nameplate",
        baseColorTexture=_badge_image(),
        metallicFactor=0.0,
        roughnessFactor=0.45,
    )


@lru_cache(maxsize=1)
def _badge_image() -> Image.Image:
    """app/generator/badge.png, written by scripts/make_badge.py."""
    image = Image.open(Path(__file__).resolve().parent / "badge.png")
    image.load()
    return image


def apply_material(mesh: trimesh.Trimesh, material: PBRMaterial) -> None:
    mesh.visual = TextureVisuals(material=material)


# Two faces meeting at less than this are treated as one curved surface and get
# a shared normal; anything sharper keeps its own. 35 degrees sits between the
# 45 degree chamfer bevels and the ~22 degree steps of every curve built here
# (16-section cylinders, the basin's corner arcs and floor fillet), so panels
# and bevels stay crisp while bowls and wheels go smooth.
SMOOTH_ANGLE = np.radians(35.0)


def face_normals(mesh: trimesh.Trimesh, angle: float = SMOOTH_ANGLE) -> None:
    """Shade flat across sharp edges, smooth across curved ones.

    trimesh.creation.box shares 8 vertices across 12 faces, so plain averaged
    vertex normals point diagonally out of the corners and a cube shades like a
    sphere. Unmerging fixes that but overcorrects: with a normal per face a
    pressed basin comes out as an angular pan and a caster wheel as a nut,
    because the facets a curve is approximated by become visible surfaces.

    So the normal for each face corner is the average of the faces meeting at
    that vertex whose own normal is within `angle` of this one. Curves get
    their facets averaged away; a 90 degree panel edge or a 45 degree chamfer
    finds no neighbour to average with and stays exactly as sharp as before.
    """
    slot_normals = _slot_normals(mesh, np.cos(angle))
    mesh.unmerge_vertices()  # a vertex per face corner, in face-corner order
    mesh.vertex_normals = slot_normals


def _slot_normals(mesh: trimesh.Trimesh, cos_angle: float) -> np.ndarray:
    """One normal per face corner (3 * len(faces), 3), smoothed by angle."""
    corner_vertex = mesh.faces.reshape(-1)
    corner_face = np.repeat(np.arange(len(mesh.faces)), 3)
    face_normal = np.asarray(mesh.face_normals)
    normals = face_normal[corner_face].copy()

    order = np.argsort(corner_vertex, kind="stable")
    starts = np.searchsorted(corner_vertex[order], np.arange(len(mesh.vertices) + 1))
    for begin, end in zip(starts[:-1], starts[1:]):
        if end - begin < 2:  # nothing to average with
            continue
        slots = order[begin:end]
        group = face_normal[corner_face[slots]]
        summed = (group @ group.T >= cos_angle) @ group
        lengths = np.linalg.norm(summed, axis=1, keepdims=True)
        normals[slots] = np.where(lengths > 1e-9, summed / np.maximum(lengths, 1e-9), group)
    return normals
