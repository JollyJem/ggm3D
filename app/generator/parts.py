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
# corner radius of a pressed bowl, measured off the product photo rather than
# the dimension drawing: on the 600 mm bowls the corner arc runs about a sixth
# of the width. A basin is drawn from sheet, so it has no sharp vertical corner,
# and at 600 mm across that radius is most of what separates a sink from a crate.
BASIN_RADIUS = 95.0
# A bowl is pressed, not folded: the walls lean in on the way down and turn
# into the floor through a wide fillet rather than meeting it at an edge.
# Both are visible in the manufacturer's close-up (STK_detail_2).
BASIN_TAPER = 30.0
BASIN_FILLET = 45.0


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


# Swivel caster, read off the product photo rather than sketched: a black
# plastic collar caps the bottom of the leg, a bright steel bracket hangs under
# it, and the wheel hangs off to one side of the swivel axis. Only the wheel and
# the collar are dark — a caster modelled entirely in the dark preset reads as a
# lump under the leg, which is the single biggest thing that gave the old table
# away next to the photo.
CASTER_PLATE = 56.0
CASTER_COLLAR_T = 8.0  # how far the collar stands proud of the leg on each side
CASTER_COLLAR_H = 16.0


def swivel_caster(
    center: tuple[float, float],
    top_z: float,
    wheel_radius: float,
    wheel_width: float,
    offset: float,
    leg_side: float = 40.0,
) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """One caster under a leg whose underside sits at top_z, as (steel, dark).

    `offset` shifts the wheel off the swivel axis along X — the trail every
    swivel caster has, and what stops the wheel reading as a peg. Callers pass
    it pointing inward so the wheel can never widen the product past the spec
    footprint, whichever way a real caster would happen to be turned.
    """
    cx, cy = center
    wheel_x = cx + offset
    plate_t = 8.0
    plate_bottom = top_z - plate_t
    swivel_h = 16.0
    fork_top = plate_bottom - swivel_h
    fork_t = 8.0
    fork_y = cy + wheel_width / 2 + fork_t / 2 + 2.0
    x0 = min(cx - leg_side / 2, wheel_x - wheel_radius * 0.7)
    x1 = max(cx + leg_side / 2, wheel_x + wheel_radius * 0.7)
    steel = [
        box_part(CASTER_PLATE, CASTER_PLATE, plate_t, (cx, cy, plate_bottom + plate_t / 2)),
        cylinder_part(18.0, swivel_h, (cx, cy, fork_top + swivel_h / 2)),
    ]
    steel += [
        box_from_bounds(
            x0, x1, y - fork_t / 2, y + fork_t / 2, wheel_radius * 0.75, fork_top
        )
        for y in (fork_y, 2 * cy - fork_y)
    ]
    collar = leg_side + 2 * CASTER_COLLAR_T
    dark = [
        # wraps the bottom of the leg, so it sits above the bracket, not below
        box_part(collar, collar, CASTER_COLLAR_H, (cx, cy, top_z + CASTER_COLLAR_H / 2)),
        caster_wheel(wheel_radius, wheel_width, (wheel_x, cy, wheel_radius)),
    ]
    return steel, dark


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


def drain_boss(
    center_x: float, center_y: float, floor_z: float, radius: float = 40.0
) -> trimesh.Trimesh:
    """The waste outlet on a bowl floor: a low disc, not a standpipe.

    The photo of this unit shows two empty bowls. A 200 mm overflow pipe was
    modelled here once and from any angle that looked into the bowl it read as
    a post someone left standing in the sink.
    """
    return cylinder_part(radius, 5.0, (center_x, center_y, floor_z + 2.5))


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
    upstand: float = 40.0,
    rear_up: bool = True,
) -> list[trimesh.Trimesh]:
    """Folded-metal lower shelf: flat sheet with its edges folded over.

    y0 is the front. With rear_up the back edge folds up instead of down, which
    is what the sink's product photo shows standing proud of the shelf and the
    one edge of that part you actually see from in front of the unit. The work
    table's shelf is hemmed the same way all round, so it passes rear_up=False.
    """
    z0 = top_z - lip
    rear = (
        box_from_bounds(x0, x1, y1 - edge_t, y1, top_z - sheet, top_z + upstand)
        if rear_up
        else box_from_bounds(x0, x1, y1 - edge_t, y1, z0, top_z)
    )
    return [
        chamfer_box(panel)
        for panel in (
            box_from_bounds(x0, x1, y0, y1, top_z - sheet, top_z),
            box_from_bounds(x0, x1, y0, y0 + edge_t, z0, top_z),
            rear,
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


def rounded_box(
    width: float,
    depth: float,
    height: float,
    center: Vec3,
    radius: float,
    sections: int = 16,
) -> trimesh.Trimesh:
    """Box with its four vertical edges rounded off to `radius`.

    Two crossed slabs plus a quarter column at each corner, unioned by
    manifold3d, which merges the coplanar faces back down -- a rounded tub
    costs about 270 triangles, not the thousands an extrusion would.
    """
    radius = min(radius, width / 2 - 1e-3, depth / 2 - 1e-3)
    if radius <= 0:
        return box_part(width, depth, height, center)
    cx, cy, cz = center
    solid = box_part(width - 2 * radius, depth, height, center).union(
        box_part(width, depth - 2 * radius, height, center)
    )
    for sx in (-1, 1):
        for sy in (-1, 1):
            corner = cylinder_part(
                radius,
                height,
                (cx + sx * (width / 2 - radius), cy + sy * (depth / 2 - radius), cz),
                sections=sections,
            )
            solid = solid.union(corner)
    return solid


def _rounded_ring(
    width: float, depth: float, radius: float, corner_sections: int
) -> np.ndarray:
    """Points anticlockwise around a rounded rectangle centred on the origin."""
    radius = max(0.0, min(radius, width / 2, depth / 2))
    hw, hd = width / 2 - radius, depth / 2 - radius
    points = []
    for cx, cy, start in (
        (hw, hd, 0.0),
        (-hw, hd, math.pi / 2),
        (-hw, -hd, math.pi),
        (hw, -hd, 1.5 * math.pi),
    ):
        for k in range(corner_sections + 1):
            angle = start + (math.pi / 2) * k / corner_sections
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return np.array(points, dtype=float)


def _lofted_solid(rings: list[np.ndarray], heights: list[float]) -> trimesh.Trimesh:
    """Closed mesh through equal-length rings, capped at both ends."""
    n = len(rings[0])
    verts = np.vstack(
        [np.column_stack([r, np.full(len(r), z)]) for r, z in zip(rings, heights)]
    )
    faces = []
    for i in range(len(rings) - 1):
        a, b = i * n, (i + 1) * n
        for k in range(n):
            k2 = (k + 1) % n
            faces.append([a + k, a + k2, b + k2])
            faces.append([a + k, b + k2, b + k])
    top_c, bottom_c = len(verts), len(verts) + 1
    verts = np.vstack(
        [
            verts,
            [*rings[0].mean(axis=0), heights[0]],
            [*rings[-1].mean(axis=0), heights[-1]],
        ]
    )
    last = (len(rings) - 1) * n
    for k in range(n):
        k2 = (k + 1) % n
        faces.append([top_c, k2, k])
        faces.append([bottom_c, last + k, last + k2])
    mesh = trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=False)
    if mesh.is_watertight and mesh.volume < 0:
        mesh.invert()
    return mesh


def basin(
    width: float,
    depth: float,
    basin_depth: float,
    top_z: float,
    center_x: float = 0.0,
    center_y: float = 0.0,
    wall: float = BASIN_WALL,
    radius: float = BASIN_RADIUS,
    taper: float = BASIN_TAPER,
    fillet: float = BASIN_FILLET,
    corner_sections: int = 6,
    arc_steps: int = 4,
) -> trimesh.Trimesh:
    """Pressed open-top bowl: rounded corners, walls leaning in, filleted floor.

    A prism with a flat floor reads as a box someone cut a hole for. The
    profile below walks the cavity wall down from the rim, leans it in by
    `taper`, then turns it into the floor through a quarter-arc of `fillet`.
    Both surfaces are lofted and the tub is the difference between them.
    """
    room = min(width, depth) / 2 - 10.0
    if taper + fillet > room:  # a small bowl cannot spare the full profile
        shrink = room / (taper + fillet)
        taper, fillet = taper * shrink, fillet * shrink
    fillet = min(fillet, basin_depth * 0.6)

    profile = [(0.0, 0.0), (taper, -(basin_depth - fillet))]
    for i in range(1, arc_steps + 1):
        angle = (math.pi / 2) * i / arc_steps
        profile.append(
            (
                taper + fillet * (1 - math.cos(angle)),
                -(basin_depth - fillet) - fillet * math.sin(angle),
            )
        )

    inner_rings = [
        _rounded_ring(width - 2 * i, depth - 2 * i, radius, corner_sections)
        for i, _ in profile
    ]
    inner_z = [top_z + dz for _, dz in profile]
    # the cutter has to break the rim plane, or the bowl comes out closed
    inner_rings.insert(0, inner_rings[0].copy())
    inner_z.insert(0, top_z + wall * 2)

    outer_rings = [
        _rounded_ring(width - 2 * i + 2 * wall, depth - 2 * i + 2 * wall,
                      radius + wall, corner_sections)
        for i, _ in profile
    ]
    outer_z = [top_z + dz for _, dz in profile]
    outer_z[-1] -= wall

    tub = _lofted_solid(outer_rings, outer_z).difference(
        _lofted_solid(inner_rings, inner_z)
    )
    tub.apply_translation((center_x, center_y, 0.0))
    return tub
