"""Print the numbers Scene Viewer cares about for a GLB.

    python scripts/inspect_glb.py app/static/models/<id>.glb
    python scripts/inspect_glb.py https://.../models/<id>.glb

model-viewer forgives a lot; Android Scene Viewer does not. It chokes on NaN or
infinite coordinates, on very high triangle counts, and on scenes made of dozens
of separate nodes. This is the before/after ruler for those four numbers.

Meshes are loaded with process=False so the report describes the file as it is
on disk, not a copy trimesh quietly cleaned up on the way in.
"""

import argparse
import io
import sys
from pathlib import Path

import numpy as np
import trimesh

# a triangle under this area (m^2) is a sliver Scene Viewer gains nothing from.
# 1e-12 m^2 is a micrometre-scale face: real geometry never lands there.
DEGENERATE_AREA = 1e-12


def load_glb(source: str) -> tuple[bytes, trimesh.Scene]:
    """Read a GLB from a local path or an http(s) URL."""
    if source.startswith(("http://", "https://")):
        import httpx

        response = httpx.get(source, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
        data = response.content
    else:
        data = Path(source).read_bytes()
    scene = trimesh.load(io.BytesIO(data), file_type="glb", process=False)
    if isinstance(scene, trimesh.Trimesh):
        scene = trimesh.Scene(scene)
    return data, scene


def face_areas(mesh: trimesh.Trimesh) -> np.ndarray:
    """Triangle areas, computed without trimesh caching or validation."""
    tri = mesh.vertices[mesh.faces]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    return 0.5 * np.linalg.norm(cross, axis=1)


def mesh_stats(mesh: trimesh.Trimesh) -> dict:
    verts = np.asarray(mesh.vertices, dtype=np.float64)
    bad = int((~np.isfinite(verts)).any(axis=1).sum())
    # a merged copy is the only way is_watertight means anything: the exporter
    # unmerges every vertex so each face keeps its own normal, which leaves the
    # raw mesh with zero shared edges by construction.
    merged = mesh.copy()
    merged.merge_vertices()
    return {
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.faces),
        "non_finite_vertices": bad,
        "degenerate_faces": int((face_areas(mesh) < DEGENERATE_AREA).sum())
        if len(mesh.faces)
        else 0,
        "watertight": bool(merged.is_watertight),
        "material": getattr(getattr(mesh.visual, "material", None), "name", "-"),
    }


def report(source: str, data: bytes, scene: trimesh.Scene) -> dict:
    rows = {name: mesh_stats(mesh) for name, mesh in scene.geometry.items()}
    totals = {
        key: sum(row[key] for row in rows.values())
        for key in ("vertices", "triangles", "non_finite_vertices", "degenerate_faces")
    }
    materials = {row["material"] for row in rows.values()}
    low, high = scene.bounds

    print(f"{source}\n")
    print(f"  file size          {len(data) / 1024:9.1f} KB")
    print(f"  vertices           {totals['vertices']:9d}")
    print(f"  triangles          {totals['triangles']:9d}")
    print(f"  scene nodes        {len(scene.graph.nodes_geometry):9d}")
    print(f"  meshes             {len(rows):9d}")
    print(f"  materials          {len(materials):9d}  {', '.join(sorted(materials))}")
    print(f"  NaN/inf vertices   {totals['non_finite_vertices']:9d}")
    print(f"  degenerate faces   {totals['degenerate_faces']:9d}")
    # bool formats as an int under a width spec, so stringify before padding
    print(f"  watertight         {str(all(r['watertight'] for r in rows.values())):>9}")
    print(
        "  bounding box       "
        f"{high[0] - low[0]:.3f} x {high[1] - low[1]:.3f} x {high[2] - low[2]:.3f} m"
    )
    print(f"  floor / center     y0={low[1]:+.4f} xc={(low[0] + high[0]) / 2:+.4f} "
          f"zc={(low[2] + high[2]) / 2:+.4f}")
    print("\n  per mesh:")
    for name, row in rows.items():
        print(
            f"    {name:<12} {row['triangles']:7d} tris  {row['vertices']:7d} verts  "
            f"{row['non_finite_vertices']:4d} bad  {row['degenerate_faces']:5d} degen  "
            f"watertight={row['watertight']}  [{row['material']}]"
        )
    return {"totals": totals, "meshes": rows, "bytes": len(data)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="GLB path or http(s) URL")
    args = parser.parse_args(argv)
    data, scene = load_glb(args.source)
    report(args.source, data, scene)
    return 0


if __name__ == "__main__":
    sys.exit(main())
