"""Pure math for the closed shooting range: size, boxes of walls / columns / beams / ceiling, ceiling lamp positions, and the lamp shadow-map layout.
No ursina import (pytest-able). Axes as in Ursina: y up, the firing lane runs along +z, the player stands at z = 0.

Real shadows of point lamps: each lamp is a 5-face cubemap (+x, -x, -y, +z, -z; the upward face is dropped since the lamps hang under the ceiling),
packed into tiles in ONE depth texture (atlas). The shader picks the face by the largest axis of the lamp-to-point vector (`cube_face`),
then picks the tile by (lamp, face) (`tile_rect`). Each face is drawn with a view slightly wider than 90 degrees (`face_fov`), so the 4 PCF samples at the face edge
still lie within its own tile.
"""
import math
from dataclasses import dataclass

from fps.core.ballistics import BoxGroup

FACES = ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0))   # view directions of the 5 faces
FACE_COUNT = len(FACES)


@dataclass(frozen=True)
class RoomLayout:
    """Room size (m). The INSIDE of the walls is at x = ±half_width, z = z_back, z = z_end; the ceiling is at y = height."""
    half_width: float = 12.0
    z_back: float = -20.0
    z_end: float = 216.0
    height: float = 5.5
    wall_thickness: float = 0.5
    pillar_z0: float = -10.0          # pillar columns against both side walls, evenly spaced; ceiling beams join opposite columns
    pillar_spacing: float = 10.0
    pillar_width: float = 0.6         # along z
    pillar_depth: float = 0.35        # protrudes from the wall
    beam_width: float = 0.4
    beam_depth: float = 0.45          # hangs below the ceiling
    walk_margin: float = 1.2          # player stays at least this far from the wall face (columns protrude 0.35 m)


def pillar_zs(room: RoomLayout) -> list:
    zs, z = [], room.pillar_z0
    while z < room.z_end - room.pillar_width:
        if z > room.z_back + room.pillar_width:
            zs.append(z)
        z += room.pillar_spacing
    return zs


def wall_boxes(room: RoomLayout) -> list:
    """(lo, hi) of the 4 walls, `wall_thickness` thick toward the outside, as high as the ceiling top; closed room corners."""
    w, t, h = room.half_width, room.wall_thickness, room.height + room.wall_thickness
    z0, z1 = room.z_back - t, room.z_end + t
    return [((-w - t, 0.0, z0), (-w, h, z1)),                 # left
            ((w, 0.0, z0), (w + t, h, z1)),                   # right
            ((-w - t, 0.0, z0), (w + t, h, room.z_back)),     # behind the player
            ((-w - t, 0.0, room.z_end), (w + t, h, z1))]      # end of the lane


def ceiling_box(room: RoomLayout) -> tuple:
    w, t = room.half_width + room.wall_thickness, room.wall_thickness
    return (-w, room.height, room.z_back - t), (w, room.height + t, room.z_end + t)


def pillar_boxes(room: RoomLayout) -> list:
    w, d, hw = room.half_width, room.pillar_depth, room.pillar_width / 2
    out = []
    for z in pillar_zs(room):
        out.append(((-w, 0.0, z - hw), (-w + d, room.height, z + hw)))
        out.append(((w - d, 0.0, z - hw), (w, room.height, z + hw)))
    return out


def beam_boxes(room: RoomLayout) -> list:
    w, hw = room.half_width, room.beam_width / 2
    return [((-w, room.height - room.beam_depth, z - hw), (w, room.height, z + hw)) for z in pillar_zs(room)]


def panel_boxes(room: RoomLayout, y0: float = 1.6, y1: float = 4.3, thickness: float = 0.06, gap: float = 0.9) -> list:
    """Acoustic panels on the two side walls: one panel per bay (between two columns): [(lo, hi)]."""
    zs = pillar_zs(room)
    w = room.half_width
    out = []
    for i in range(0, len(zs) - 1, 2):
        z0, z1 = zs[i] + room.pillar_width / 2 + gap, zs[i + 1] - room.pillar_width / 2 - gap
        out.append(((-w, y0, z0), (-w + thickness, y1, z1)))
        out.append(((w - thickness, y0, z0), (w, y1, z1)))
    return out


def walk_bounds(room: RoomLayout, z_min: float, z_max: float) -> tuple:
    """(x_min, x_max, z_min, z_max) for `movement.clamp_to_bounds`: inside the room, `walk_margin` from the walls."""
    x = room.half_width - room.walk_margin
    return (-x, x, max(z_min, room.z_back + room.walk_margin), min(z_max, room.z_end - room.walk_margin))


def grouped(boxes: list, owner, chunk: float) -> list:
    """Group the small boxes (columns, beams) in runs of `chunk` metres along z into `BoxGroup`s; returns the items for `first_hit`."""
    buckets = {}
    for lo, hi in boxes:
        side = 0 if lo[0] + hi[0] < 0 else 1
        buckets.setdefault((side, math.floor((lo[2] + hi[2]) / 2 / chunk)), []).append((lo, hi, owner))
    return [BoxGroup(v).entry() for _, v in sorted(buckets.items())]


# --- ceiling lamps ---
def lamp_positions(x: float, y: float, z0: float, spacing: float, count: int) -> list:
    return [(x, y, z0 + i * spacing) for i in range(count)]


def nearest_lamp(z: float, z0: float, spacing: float, count: int) -> int:
    """Index of the nearest lamp by z (like the shader: it checks this lamp and two on each side)."""
    return min(max(int(math.floor((z - z0) / spacing + 0.5)), 0), count - 1)


def cube_face(v) -> int:
    """Cubemap face containing the lamp-to-point vector `v`: index in FACES, or None if it is the upward face (not drawn: lamp close to the ceiling)."""
    ax, ay, az = abs(v[0]), abs(v[1]), abs(v[2])
    if ax >= ay and ax >= az:
        return 0 if v[0] > 0 else 1
    if ay >= az:
        return None if v[1] > 0 else 2
    return 3 if v[2] > 0 else 4


def atlas_grid(tiles: int) -> tuple:
    """(columns, rows), nearly square, enough to hold `tiles` tiles."""
    cols = math.ceil(math.sqrt(tiles))
    return cols, math.ceil(tiles / cols)


def tile_index(lamp: int, face: int) -> int:
    return lamp * FACE_COUNT + face


def tile_rect(index: int, cols: int, rows: int) -> tuple:
    """(left, right, bottom, top) of the tile in the atlas, 0..1 coordinates as in Panda's DisplayRegion (0 = bottom).
    The shader uses exactly this formula: column = index mod cols, row = index div cols."""
    c, r = index % cols, index // cols
    return c / cols, (c + 1) / cols, r / rows, (r + 1) / rows


def face_fov(tile_px: int, guard_px: float) -> float:
    """View angle (degrees) of one face, chosen so that exactly 90 degrees fall on the `tile_px - 2*guard_px` pixels in the middle of the tile:
    the `guard_px` pixel border on each side holds the overflow of the neighbouring face, so PCF samples at the edge do not reach into other tiles."""
    return 2.0 * math.degrees(math.atan(tile_px / (tile_px - 2.0 * guard_px)))
