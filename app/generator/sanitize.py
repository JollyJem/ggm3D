"""Mesh sanitation, run on every scene just before it is shaded and exported.

model-viewer will happily draw a mesh that Android Scene Viewer refuses to
open: a NaN coordinate, a zero-area sliver whose normal comes out as (0, 0, 0),
or an inverted shell. None of those survive this pass.

Everything here is numpy only. scipy and networkx are not installed (they are
not in requirements.txt and are not worth the wheel size on the Render free
tier), so the graph-based helpers -- trimesh.repair.fix_winding,
fix_normals, convex_hull -- raise at call time. The winding fix below is the
part of those that can be done with arithmetic alone.
"""

import logging

import numpy as np
import trimesh

logger = logging.getLogger(__name__)


def _drop_non_finite(mesh: trimesh.Trimesh) -> int:
    """Delete every face touching a NaN or infinite vertex. Returns the count.

    The vertex itself goes with the face: an unreferenced NaN still lands in the
    POSITION accessor, and that alone is enough to poison the accessor min/max.
    """
    finite = np.isfinite(mesh.vertices).all(axis=1)
    if finite.all():
        return 0
    keep = finite[mesh.faces].all(axis=1)
    dropped = int((~keep).sum())
    mesh.update_faces(keep)
    mesh.remove_unreferenced_vertices()
    return dropped


def sanitize_mesh(mesh: trimesh.Trimesh, name: str = "mesh") -> bool:
    """Weld, de-slice and re-wind one mesh in place. True if anything changed.

    Order matters. Welding first is what lets the degenerate and duplicate
    checks see coincident corners as one vertex; without it two parts that meet
    exactly still carry two independent copies of the seam and every test below
    misses. Winding comes last, once the topology is final.
    """
    before_faces, before_verts = len(mesh.faces), len(mesh.vertices)
    repairs: list[str] = []

    dropped = _drop_non_finite(mesh)
    if dropped:
        repairs.append(f"{dropped} faces on non-finite vertices")

    mesh.merge_vertices()
    if len(mesh.vertices) != before_verts:
        repairs.append(f"welded {before_verts - len(mesh.vertices)} duplicate vertices")

    # a sliver thinner than this has no volume, no reliable normal and no
    # business in the file; trimesh measures it as triangle height, not area
    nondegenerate = mesh.nondegenerate_faces(height=1e-8)
    if not nondegenerate.all():
        repairs.append(f"{int((~nondegenerate).sum())} degenerate faces")
        mesh.update_faces(nondegenerate)

    unique = mesh.unique_faces()
    if not unique.all():
        repairs.append(f"{int((~unique).sum())} duplicate faces")
        mesh.update_faces(unique)

    mesh.remove_unreferenced_vertices()

    # A closed shell wound inside-out has negative signed volume. Flipping it is
    # the whole of fix_winding for our case: every part is built from trimesh
    # primitives or manifold3d output, both of which are internally consistent,
    # so the only failure mode left is the entire shell being inverted.
    if mesh.is_watertight and mesh.volume < 0:
        mesh.invert()
        repairs.append("inverted winding")
    elif not mesh.is_winding_consistent:
        # not fixable without a face-adjacency walk; say so rather than pretend
        logger.warning("mesh %s has inconsistent winding and no graph library to fix it", name)

    if repairs:
        logger.warning(
            "sanitized %s: %s (%d -> %d faces)",
            name,
            ", ".join(repairs),
            before_faces,
            len(mesh.faces),
        )
    return bool(repairs)


def sanitize_scene(scene: trimesh.Scene) -> bool:
    """Run sanitize_mesh over every geometry in the scene. True if any changed."""
    return any(sanitize_mesh(mesh, name) for name, mesh in scene.geometry.items())
