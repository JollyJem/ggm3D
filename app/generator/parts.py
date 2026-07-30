"""Reusable part functions. All dimensions in mm, built Z-up, floor at z=0.

Builders rotate to glTF Y-up and scale to meters once, on export.
"""

import itertools
import math

import numpy as np
import trimesh

Vec3 = tuple[float, float, float]

CHAMFER = 2.0  # mm, the bevel cut off each edge of a visible box part
# tub wall thickness; a basin's outer shell is its inner width plus twice this,
# which is what a caller has to leave room for inside the worktop
BASIN_WALL = 15.0


def box_part(width: float, depth: float, height: float, center: Vec3) -> trimesh.Trimesh:
    part = trimesh.creation.box(extents=(width, depth, height))
    part.apply_translation(center)
    return part


def _chamfer_topology() -> np.ndarray:
    """Triangles of the chamfered box, as indices into its 24 vertex slots.

    Slot a * 8 + 4 * sx + 2 * sy + sz is the corner with signs (sx, sy, sz) of
    the shrunken box that keeps its full extent on axis a. The shape is always
    the same 26 facets: 6 shrunken faces, 12 edge bevels, 8 corner triangles.
    Built once at import; chamfer_box only moves the vertices.
    """
    tris: list[tuple[int, int, int]] = []

    def idx(axis: int, s: tuple[int, int, int]) -> int:
        return axis * 8 + 4 * s[0] + 2 * s[1] + s[2]

    def quad(a: int, b: int, c: int, d: int) -> None:
        tris.extend([(a, b, c), (a, c, d)])

    for axis in range(3):  # the six face rectangles
        u, v = (i for i in range(3) if i != axis)
        for s_axis in (0, 1):
            ring = []
            for su, sv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                s = [0, 0, 0]
                s[axis], s[u], s[v] = s_axis, su, sv
                ring.append(idx(axis, tuple(s)))
            quad(*ring)

    for a, b in ((0, 1), (0, 2), (1, 2)):  # the twelve edge bevels
        other = 3 - a - b
        for sa in (0, 1):
            for sb in (0, 1):
                ring = []
                for group, order in ((a, (0, 1)), (b, (1, 0))):
                    for sc in order:
                        s = [0, 0, 0]
                        s[a], s[b], s[other] = sa, sb, sc
                        ring.append(idx(group, tuple(s)))
                quad(*ring)

    for corner in _SIGN_KEYS:  # the eight corner triangles
        tris.append(tuple(idx(axis, corner) for axis in range(3)))
    return np.array(tris, dtype=np.int64)


_SIGN_KEYS = list(itertools.product((0, 1), repeat=3))
_SIGNS = np.array(_SIGN_KEYS, dtype=float) * 2.0 - 1.0
_CHAMFER_FACES = _chamfer_topology()


def chamfer_box(part: trimesh.Trimesh, size: float = CHAMFER) -> trimesh.Trimesh:
    """Cut a 45 degree bevel off every edge of an axis-aligned box.

    Each face plane is left untouched and only the edges are cut back, so the
    bounding box still matches the spec exactly. Real sheet steel has no
    infinitely sharp edge, and the bevel catches a bright specular line that
    reads as metal instead of a flat white panel.
    """
    low, high = part.bounds
    center = (low + high) / 2.0
    extents = high - low
    size = min(size, float(extents.min()) / 3.0)  # never eat a thin part
    corners = []
    for axis in range(3):
        half = extents / 2.0 - size
        half[axis] = extents[axis] / 2.0
        corners.append(center + _SIGNS * half)
    verts = np.vstack(corners)
    # the shape is convex around `center`, so a triangle is wound correctly when
    # its normal points away from the center. Cheaper and surer than a repair pass.
    faces = _CHAMFER_FACES.copy()
    tri = verts[faces]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    inward = ((tri[:, 0] - center) * normals).sum(axis=1) < 0
    faces[inward] = faces[inward][:, ::-1]
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def box_from_bounds(
    x0: float, x1: float, y0: float, y1: float, z0: float, z1: float
) -> trimesh.Trimesh:
    """Axis-aligned box from its min/max corners. Handy for absolute layouts."""
    return box_part(
        x1 - x0, y1 - y0, z1 - z0, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    )


def round_bar_x(
    x0: float, x1: float, y: float, z: float, radius: float, sections: int = 12
) -> trimesh.Trimesh:
    """Round tube running along X (front cross rail), centered at (·, y, z).

    12 sections: a 30 mm rail seen from two metres is four pixels wide, and an
    even count keeps a vertex on each axis so the bounding box stays exact.
    """
    bar = trimesh.creation.cylinder(radius=radius, height=x1 - x0, sections=sections)
    bar.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    bar.apply_translation(((x0 + x1) / 2, y, z))
    return bar


def cylinder_part(
    radius: float, height: float, center: Vec3, sections: int = 16
) -> trimesh.Trimesh:
    """Upright cylinder. Only ever a foot or a leg here, all under 50 mm across,
    so 16 sections is already past the point where more shows on a phone."""
    part = trimesh.creation.cylinder(radius=radius, height=height, sections=sections)
    part.apply_translation(center)
    return part


def top_slab(
    width: float, depth: float, top_z: float, thickness: float = 40.0
) -> trimesh.Trimesh:
    return chamfer_box(box_part(width, depth, thickness, (0, 0, top_z - thickness / 2)))


def leg_centers(
    width: float, depth: float, side: float = 40.0, inset: float = 15.0
) -> list[tuple[float, float]]:
    """(x, y) of the four leg axes; casters reuse them to sit under the legs."""
    lx = width / 2 - inset - side / 2
    ly = depth / 2 - inset - side / 2
    return [(sx * lx, sy * ly) for sx in (-1, 1) for sy in (-1, 1)]


def legs(
    width: float,
    depth: float,
    height: float,
    side: float = 40.0,
    inset: float = 15.0,
    bottom_z: float = 0.0,
) -> list[trimesh.Trimesh]:
    return [
        chamfer_box(box_part(side, side, height, (x, y, bottom_z + height / 2)))
        for x, y in leg_centers(width, depth, side, inset)
    ]


def edge_lip(
    width: float,
    depth: float,
    top_z: float,
    height: float = 60.0,
    thickness: float = 15.0,
) -> list[trimesh.Trimesh]:
    """Downturned rim under the top slab: four thin plates flush with the edges."""
    z = top_z - height / 2
    return [
        box_part(width, thickness, height, (0, s * (depth - thickness) / 2, z))
        for s in (-1, 1)
    ] + [
        box_part(thickness, depth - 2 * thickness, height, (s * (width - thickness) / 2, 0, z))
        for s in (-1, 1)
    ]


def cabinet_walls(
    width: float,
    depth: float,
    height: float,
    bottom_z: float,
    center: tuple[float, float] = (0.0, 0.0),
    thickness: float = 15.0,
    floor: bool = False,
) -> list[trimesh.Trimesh]:
    """Box of four side panels (front, back, left, right) enclosing a cabinet
    zone under a counter. With floor=True a bottom panel closes the base."""
    cx, cy = center
    z = bottom_z + height / 2
    front_back = [
        box_part(width, thickness, height, (cx, cy + s * (depth - thickness) / 2, z))
        for s in (-1, 1)
    ]
    left_right = [
        box_part(thickness, depth - 2 * thickness, height, (cx + s * (width - thickness) / 2, cy, z))
        for s in (-1, 1)
    ]
    panels = front_back + left_right
    if floor:
        panels.append(box_part(width, depth, thickness, (cx, cy, bottom_z + thickness / 2)))
    return panels


def caster_wheel(radius: float, width: float, center: Vec3) -> trimesh.Trimesh:
    """Caster wheel disc, axle along the y axis; center is the axle center."""
    wheel = trimesh.creation.cylinder(radius=radius, height=width, sections=16)
    wheel.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    wheel.apply_translation(center)
    return wheel


def caster_bracket(
    wheel_radius: float, wheel_width: float, top_z: float, center: Vec3
) -> trimesh.Trimesh:
    """Swivel fork: mount plate under the leg plus two plates straddling the wheel.

    center is the wheel's axle center; the fork sides reach just below it.
    """
    cx, cy, axle_z = center
    plate_t = 10.0
    plate = box_part(55.0, 55.0, plate_t, (cx, cy, top_z - plate_t / 2))
    side_t = 8.0
    side_h = (top_z - plate_t) - (axle_z - 12.0)
    sides = [
        box_part(
            wheel_radius * 1.4,
            side_t,
            side_h,
            (cx, cy + s * (wheel_width / 2 + side_t / 2 + 2.0), axle_z - 12.0 + side_h / 2),
        )
        for s in (-1, 1)
    ]
    return trimesh.util.concatenate([plate, *sides])


def undershelf(
    width: float,
    depth: float,
    z: float = 150.0,
    thickness: float = 20.0,
    inset: float = 15.0,
    leg_side: float = 40.0,
) -> trimesh.Trimesh:
    lx = width / 2 - inset - leg_side / 2
    ly = depth / 2 - inset - leg_side / 2
    return chamfer_box(box_part(2 * lx - leg_side, 2 * ly - leg_side, thickness, (0, 0, z)))


def door_panel(
    width: float,
    height: float,
    center_x: float,
    bottom_z: float,
    front_y: float,
    thickness: float = 25.0,
) -> trimesh.Trimesh:
    center = (center_x, front_y - thickness / 2, bottom_z + height / 2)
    return box_part(width, thickness, height, center)


def handle(
    length: float, center: Vec3, thickness: float = 25.0, depth: float = 35.0
) -> trimesh.Trimesh:
    return box_part(thickness, depth, length, center)


def feet(
    width: float,
    depth: float,
    height: float = 100.0,
    radius: float = 25.0,
    inset: float = 60.0,
    center: tuple[float, float] = (0.0, 0.0),
) -> list[trimesh.Trimesh]:
    fx = width / 2 - inset
    fy = depth / 2 - inset
    return [
        cylinder_part(
            radius, height, (center[0] + sx * fx, center[1] + sy * fy, height / 2)
        )
        for sx in (-1, 1)
        for sy in (-1, 1)
    ]


def drainer_board(
    width: float,
    depth: float,
    counter_top: float,
    center_x: float,
    thickness: float = 20.0,
) -> trimesh.Trimesh:
    """Raised drainer slab resting on the counter top."""
    return box_part(width, depth, thickness, (center_x, 0.0, counter_top + thickness / 2))


def drainer_ribs(
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    top_z: float,
    pitch: float = 30.0,
    rib_w: float = 8.0,
    rib_h: float = 4.0,
) -> list[trimesh.Trimesh]:
    """Parallel raised ribs running front to back (along Y), evenly spaced
    across X at the given pitch, resting on the drainer surface at top_z."""
    z = top_z + rib_h / 2
    n = int((x1 - x0) / pitch)
    xs = [x0 + i * pitch for i in range(n + 1)]
    return [box_part(rib_w, y1 - y0, rib_h, (x, (y0 + y1) / 2, z)) for x in xs]


def lipped_shelf(
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    top_z: float,
    lip: float = 25.0,
    sheet: float = 6.0,
    edge_t: float = 12.0,
) -> list[trimesh.Trimesh]:
    """Flat sheet with four short downturned edges: a folded-metal lower shelf."""
    z0 = top_z - lip
    return [
        chamfer_box(panel)
        for panel in (
            box_from_bounds(x0, x1, y0, y1, top_z - sheet, top_z),
            box_from_bounds(x0, x1, y0, y0 + edge_t, z0, top_z),
            box_from_bounds(x0, x1, y1 - edge_t, y1, z0, top_z),
            box_from_bounds(x0, x0 + edge_t, y0, y1, z0, top_z),
            box_from_bounds(x1 - edge_t, x1, y0, y1, z0, top_z),
        )
    ]


def backsplash(
    width: float,
    height: float,
    counter_top: float,
    back_y: float,
    thickness: float = 30.0,
) -> trimesh.Trimesh:
    """Rear upstand panel rising from the counter top along the back edge."""
    center = (0.0, back_y + thickness / 2, counter_top + height / 2)
    return box_part(width, thickness, height, center)


def basin(
    width: float,
    depth: float,
    basin_depth: float,
    top_z: float,
    center_x: float = 0.0,
    center_y: float = 0.0,
    wall: float = BASIN_WALL,
) -> trimesh.Trimesh:
    """Open-top tub: outer shell minus inner cavity (manifold3d boolean)."""
    outer = box_part(
        width + 2 * wall,
        depth + 2 * wall,
        basin_depth + wall,
        (center_x, center_y, top_z - (basin_depth + wall) / 2),
    )
    inner = box_part(
        width,
        depth,
        basin_depth + wall,
        (center_x, center_y, top_z - basin_depth / 2 + wall / 2),
    )
    return outer.difference(inner)
