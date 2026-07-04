"""Reusable part functions. All dimensions in mm, built Z-up, floor at z=0.

Builders rotate to glTF Y-up and scale to meters once, on export.
"""

import trimesh

Vec3 = tuple[float, float, float]


def box_part(width: float, depth: float, height: float, center: Vec3) -> trimesh.Trimesh:
    part = trimesh.creation.box(extents=(width, depth, height))
    part.apply_translation(center)
    return part


def cylinder_part(
    radius: float, height: float, center: Vec3, sections: int = 32
) -> trimesh.Trimesh:
    part = trimesh.creation.cylinder(radius=radius, height=height, sections=sections)
    part.apply_translation(center)
    return part


def top_slab(
    width: float, depth: float, top_z: float, thickness: float = 40.0
) -> trimesh.Trimesh:
    return box_part(width, depth, thickness, (0, 0, top_z - thickness / 2))


def legs(
    width: float,
    depth: float,
    height: float,
    side: float = 40.0,
    inset: float = 15.0,
) -> list[trimesh.Trimesh]:
    lx = width / 2 - inset - side / 2
    ly = depth / 2 - inset - side / 2
    return [
        box_part(side, side, height, (sx * lx, sy * ly, height / 2))
        for sx in (-1, 1)
        for sy in (-1, 1)
    ]


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
    return box_part(2 * lx - leg_side, 2 * ly - leg_side, thickness, (0, 0, z))


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
    wall: float = 15.0,
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
