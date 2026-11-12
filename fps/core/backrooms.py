"""G18 Backrooms - Pool rooms: one floor of the 5-floor level as boxes (pure, no ursina; tests/test_backrooms.py).

A floor = the pool hall of `build_map` (white tiles, no windows, the pool centred on the origin) + pillars, partition walls, ceiling light panels (`Box.emit`),
a door hole in the north wall (the stairs up) and one in the south wall (from the stairs below), and the two STAIR CORRIDORS outside the hall.

The corridors are the trick that makes 5 floors cheap (user's choice 12/11/2026): only ONE floor exists at a time. The exit corridor of floor k and the arrival corridor
of floor k+1 are the SAME shape (same boxes, lights and tile origin relative to the corridor). When the player is halfway up and both corridor doors are closed, the game
swaps floor k for floor k+1 and moves him by `transfer(k)`: nothing around him changes. Corridor frame: s (= z) runs up the stairs from the inner face of the bottom end
wall (s = 0) to the inner face of the top end wall (s = LENGTH); x = 0 is the corridor axis; y = 0 is the bottom landing.
"""
import hashlib
import math
from dataclasses import dataclass, field

from fps.core.poolmap import EPS, FLOOR, Box, PoolMap, build_map
from fps.weapon_data import BACKROOMS, BACKROOMS_CORRIDOR_LIGHT, BACKROOMS_LIGHT, BACKROOMS_LIGHT_SHOWN, FloorSpec

BAKE_VERSION = 1                 # bump when the floor geometry / light bake code changes in a way the stored files cannot reflect
# the stair corridor (identical on every floor: the floor swap depends on it)
C_WIDTH = 2.0                    # inner width
DOOR_W = 1.4
DOOR_H = 2.3
LANDING = 1.8                    # flat landing at each end
STEPS = 14
RISE = 2.4 / STEPS               # 0.171 m (<= PlayerParams.step_up); the climb is 2.4 m = 2 x 1.2 m, a whole number of periods of both tile textures
TREAD = 0.32
CLEAR = 2.9                      # ceiling height above the top landing
SLAB = 0.4
CLIMB = STEPS * RISE
LENGTH = LANDING + STEPS * TREAD + LANDING
DOOR_T = 0.08                    # door leaf thickness (it stands in the middle of the wall)
SWAP_S = LANDING + STEPS * TREAD * 0.5     # s past which the floor swaps (halfway up), once both doors are closed
CORRIDOR_LIGHTS = ((LENGTH * 0.28, 0.9, 0.5), (LENGTH * 0.74, 0.9, 0.5))     # (s, size x, size s) ceiling panels of the corridor


@dataclass
class Door:
    """A door leaf in a wall hole: closed it fills the hole (solid for the player, bullets and the light bake); opening slides it up into the wall."""
    name: str
    lo: tuple
    hi: tuple
    kind: str                    # 'exit' (hall -> stairs up), 'arrive' (stairs below -> hall), 'dead' (a corridor end that leads nowhere: always closed)


@dataclass
class FloorMap(PoolMap):
    """A PoolMap plus what the level needs (doors, corridor frames, where enemies may go)."""
    spec: FloorSpec = None
    index: int = 0
    doors: list = field(default_factory=list)
    exit_origin: tuple = None    # floor coordinates of the exit corridor's frame origin (s = 0 on its axis, bottom landing height)
    arrive_origin: tuple = None
    nav_rect: tuple = None       # (x0, x1, z0, z1): the hall interior, where enemies live
    start: tuple = None          # (x, y, z, yaw): where the player starts the floor (arrival corridor, top landing, facing the door)


def _b(name, lo, hi, **kw) -> Box:
    return Box(name, tuple(float(c) for c in lo), tuple(float(c) for c in hi), **kw)


def cut_hole(box: Box, axis: int, u0: float, u1: float, y0: float, y1: float) -> list:
    """Pieces of a wall box (thin along `axis`, 0 = x or 2 = z) left after cutting the hole [u0, u1] x [y0, y1] through its whole thickness (u = the other horizontal
    axis). Nothing is kept under the hole: the deck slab under the wall is the hole's floor (a piece there would put two coplanar faces at y = 0)."""
    ua = 2 if axis == 0 else 0
    pieces = []

    def piece(tag, lo_u, hi_u, lo_y, hi_y):
        if hi_u - lo_u > EPS and hi_y - lo_y > EPS:
            lo, hi = list(box.lo), list(box.hi)
            lo[ua], hi[ua], lo[1], hi[1] = lo_u, hi_u, lo_y, hi_y
            pieces.append(Box(f'{box.name}_{tag}', tuple(lo), tuple(hi), box.albedo, box.tile, box.walk, box.solid, box.visible, box.bullets, box.caster, box.emit, box.uv_origin))
    piece('a', box.lo[ua], u0, box.lo[1], box.hi[1])
    piece('b', u1, box.hi[ua], box.lo[1], box.hi[1])
    piece('top', u0, u1, y1, box.hi[1])
    if y0 > box.lo[1] + EPS and y0 > EPS:          # a hole above the deck (not the case for doors): keep the sill
        piece('sill', u0, u1, box.lo[1], y0)
    return pieces


def corridor_frame_to_floor(origin: tuple, p: tuple) -> tuple:
    return (origin[0] + p[0], origin[1] + p[1], origin[2] + p[2])


def corridor(origin: tuple, tag: str, d, own_bottom_from: float = None, own_top_to: float = None) -> tuple:
    """(boxes, air, doors) of a stair corridor whose frame origin is `origin` (floor coordinates). `d` = the hall's MapData (wall thickness, albedos).
    own_bottom_from: build the bottom end wall from this frame height up (None = the whole wall: an arrival corridor; the exit corridor's bottom end is the
    hall's north wall, so only the part above the hall wall is added). own_top_to: likewise for the top end wall (None = whole; the arrival corridor's top end is
    the hall's south wall)."""
    w = d.wall
    hw = C_WIDTH / 2.0
    top = CLIMB + CLEAR
    o = origin
    wall_kw = dict(albedo=d.wall_albedo, tile=d.wall_tile, solid=True, uv_origin=o)
    floor_kw = dict(albedo=d.floor_albedo, tile=d.floor_tile, walk=True, uv_origin=o)

    def B(name, lo, hi, **kw):
        return _b(f'{tag}_{name}', corridor_frame_to_floor(o, lo), corridor_frame_to_floor(o, hi), **kw)
    boxes = [B('base', (-hw, -SLAB, -w if own_bottom_from is None else 0.0), (hw, 0.0, LENGTH), **floor_kw)]
    for i in range(STEPS):
        end = LENGTH + (w if own_top_to is None else 0.0)
        boxes.append(B(f'stair{i}', (-hw, -SLAB, LANDING + i * TREAD), (hw, (i + 1) * RISE, end), **floor_kw))
    boxes += [B('side_w', (-hw - w, -SLAB, -w), (-hw, top + w, LENGTH + w), **wall_kw),
              B('side_e', (hw, -SLAB, -w), (hw + w, top + w, LENGTH + w), **wall_kw),
              B('ceiling', (-hw - w, top, -w), (hw + w, top + w, LENGTH + w), **wall_kw)]
    hole_b = (-DOOR_W / 2.0, DOOR_W / 2.0, 0.0, DOOR_H)
    hole_t = (-DOOR_W / 2.0, DOOR_W / 2.0, CLIMB, CLIMB + DOOR_H)
    air = [(corridor_frame_to_floor(o, (-hw, 0.0, 0.0)), corridor_frame_to_floor(o, (hw, top, LENGTH)))]
    if own_bottom_from is None:
        end_b = B('end_b', (-hw - w, -SLAB, -w), (hw + w, top + w, 0.0), **wall_kw)
        boxes += cut_hole(end_b, 2, o[0] + hole_b[0], o[0] + hole_b[1], o[1] + hole_b[2], o[1] + hole_b[3])
        air.append((corridor_frame_to_floor(o, (hole_b[0], 0.0, -w)), corridor_frame_to_floor(o, (hole_b[1], DOOR_H, 0.0))))
    elif own_bottom_from < top + w - EPS:
        boxes.append(B('end_b', (-hw - w, own_bottom_from, -w), (hw + w, top + w, 0.0), **wall_kw))
    if own_top_to is None:
        end_t = B('end_t', (-hw - w, -SLAB, LENGTH), (hw + w, top + w, LENGTH + w), **wall_kw)
        boxes += cut_hole(end_t, 2, o[0] + hole_t[0], o[0] + hole_t[1], o[1] + hole_t[2], o[1] + hole_t[3])
        air.append((corridor_frame_to_floor(o, (hole_t[0], CLIMB, LENGTH)), corridor_frame_to_floor(o, (hole_t[1], CLIMB + DOOR_H, LENGTH + w))))
    for k, (s, sx, sz) in enumerate(CORRIDOR_LIGHTS):
        boxes.append(B(f'light{k}', (-sx / 2, top - 0.03, s - sz / 2), (sx / 2, top, s + sz / 2), albedo=(1.0, 1.0, 1.0), tile=0.0, emit=BACKROOMS_CORRIDOR_LIGHT, uv_origin=o))
    mid = -w / 2.0
    doors = [Door(f'{tag}_bottom', corridor_frame_to_floor(o, (hole_b[0], 0.0, mid - DOOR_T / 2)), corridor_frame_to_floor(o, (hole_b[1], DOOR_H, mid + DOOR_T / 2)), ''),
             Door(f'{tag}_top', corridor_frame_to_floor(o, (hole_t[0], CLIMB, LENGTH + w / 2 - DOOR_T / 2)),
                  corridor_frame_to_floor(o, (hole_t[1], CLIMB + DOOR_H, LENGTH + w / 2 + DOOR_T / 2)), '')]
    return boxes, air, doors


def exit_origin(spec: FloorSpec) -> tuple:
    d = spec.hall
    return (spec.exit_x, 0.0, d.room_z / 2.0 + d.wall)


def arrive_origin(spec: FloorSpec) -> tuple:
    d = spec.hall
    return (spec.arrive_x, -CLIMB, -d.room_z / 2.0 - d.wall - LENGTH)


def transfer(k: int, floors: tuple = BACKROOMS) -> tuple:
    """Offset added to the player's position when floor k is swapped for floor k + 1 (same spot of the same corridor shape)."""
    a, b = exit_origin(floors[k]), arrive_origin(floors[k + 1])
    return (b[0] - a[0], b[1] - a[1], b[2] - a[2])


def build_floor(k: int, floors: tuple = BACKROOMS) -> FloorMap:
    spec = floors[k]
    d = spec.hall
    pm = build_map(d)
    hx, hz = d.room_x / 2.0, d.room_z / 2.0
    w, top = d.wall, d.ceiling
    wall_kw = dict(albedo=d.wall_albedo, tile=d.wall_tile, solid=True)
    boxes = []
    for b in pm.boxes:
        if b.name == 'wall_n':
            boxes += cut_hole(b, 2, spec.exit_x - DOOR_W / 2, spec.exit_x + DOOR_W / 2, 0.0, DOOR_H)
        elif b.name == 'wall_s':
            boxes += cut_hole(b, 2, spec.arrive_x - DOOR_W / 2, spec.arrive_x + DOOR_W / 2, 0.0, DOOR_H)
        else:
            boxes.append(b)
    air = list(pm.air)
    air.append(((spec.exit_x - DOOR_W / 2, 0.0, hz), (spec.exit_x + DOOR_W / 2, DOOR_H, hz + w)))
    air.append(((spec.arrive_x - DOOR_W / 2, 0.0, -hz - w), (spec.arrive_x + DOOR_W / 2, DOOR_H, -hz)))
    for i, (x, z, s) in enumerate(spec.pillars):
        boxes.append(_b(f'pillar{i}', (x - s / 2, 0.0, z - s / 2), (x + s / 2, top, z + s / 2), **wall_kw))
    for i, (x0, z0, x1, z1, h) in enumerate(spec.walls):
        boxes.append(_b(f'partition{i}', (x0, 0.0, z0), (x1, min(h, top), z1), **wall_kw))
    for i, (x, z, sx, sz) in enumerate(spec.lights):
        boxes.append(_b(f'light{i}', (x - sx / 2, top - 0.03, z - sz / 2), (x + sx / 2, top, z + sz / 2), albedo=(1.0, 1.0, 1.0), tile=0.0, emit=BACKROOMS_LIGHT))
    eo, ao = exit_origin(spec), arrive_origin(spec)
    xb, xa, xd = corridor(eo, 'up', d, own_bottom_from=top + w)
    ab, aa, ad = corridor(ao, 'down', d, own_top_to=top + w)
    boxes += xb + ab
    air += xa + aa
    # doors: the hall's two doors are the exit corridor's bottom and the arrival corridor's top; the other two corridor ends lead nowhere
    doors = []
    for door, kind in ((xd[0], 'exit'), (xd[1], 'dead'), (ad[0], 'dead'), (ad[1], 'arrive')):
        doors.append(Door(door.name, door.lo, door.hi, kind))
        boxes.append(Box(f'{door.name}_shadow', door.lo, door.hi, albedo=(0.5, 0.5, 0.5), tile=0.0, visible=False, bullets=False, caster=True))   # baked closed: no light leaks through
    xs = [p for lo, hi in air for p in (lo[0], hi[0])]
    zs = [p for lo, hi in air for p in (lo[2], hi[2])]
    fm = FloorMap(d, boxes, air, pm.interior, pm.water, pm.ramp, bounds=(min(xs), max(xs), min(zs), max(zs)),
                  spec=spec, index=k, doors=doors, exit_origin=eo, arrive_origin=ao, nav_rect=(-hx, hx, -hz, hz))
    fm.start = (ao[0], ao[1] + CLIMB, ao[2] + LENGTH - 1.0, 0.0)
    return fm


def floor_key(fm: FloorMap, look) -> str:
    """Hash of everything a floor's stored lightmap / reflection depend on."""
    text = repr((BAKE_VERSION, fm.spec, C_WIDTH, DOOR_W, DOOR_H, LANDING, STEPS, TREAD, CLEAR, SLAB, CORRIDOR_LIGHTS, BACKROOMS_LIGHT, BACKROOMS_CORRIDOR_LIGHT,
                 BACKROOMS_LIGHT_SHOWN, look.sky_irradiance))
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def in_corridor(origin: tuple, p: tuple) -> float:
    """s (metres up the corridor) of floor point p if it is inside the corridor whose frame origin is `origin`, else None."""
    x, z = p[0] - origin[0], p[2] - origin[2]
    if abs(x) <= C_WIDTH / 2.0 + 1e-6 and -0.5 <= z <= LENGTH + 0.5:
        return z
    return None


def door_open_offset(door: Door, amount: float) -> float:
    """How far up the leaf has slid (m) when `amount` (0 closed .. 1 open) of the opening is done (smoothstep, ~0.1 m stays visible at the top of the hole)."""
    t = min(max(amount, 0.0), 1.0)
    return (t * t * (3.0 - 2.0 * t)) * (door.hi[1] - door.lo[1] - 0.1)


def door_box(door: Door, amount: float) -> tuple:
    """(lo, hi) of the leaf at this opening amount."""
    dy = door_open_offset(door, amount)
    return (door.lo[0], door.lo[1] + dy, door.lo[2]), (door.hi[0], door.hi[1] + dy, door.hi[2])


def emitters(pm: PoolMap) -> list:
    """[(lo, hi, radiance)] of the ceiling light panels (boxes with `emit`)."""
    return [(b.lo, b.hi, b.emit) for b in pm.boxes if b.emit is not None]


def light_area(lo: tuple, hi: tuple) -> float:
    return (hi[0] - lo[0]) * (hi[2] - lo[2])


def distance_xz(a: tuple, b: tuple) -> float:
    return math.hypot(a[0] - b[0], a[2] - b[2])
