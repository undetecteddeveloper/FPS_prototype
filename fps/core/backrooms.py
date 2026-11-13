"""G18 / G19 Backrooms - Pool rooms: the stages of the run as boxes (pure, no ursina; tests/test_backrooms.py; skill `poolrooms-level-design`).

Stage 0 = the pool hall (the default map) with a door at the top of its north-bank stairs; stages 1-5 = the Backrooms floors.

A floor = the pool hall of `build_map` (the ONE big pool, white tiles, no windows) + rooms carved out of SOLID TILE around it: the solid block around everything is cut by every
air volume (rooms, doorways, high windows, lift cabins) with exact box subtraction; what is left is walls, floors and ceilings with no two faces on top of each other.
Pieces that touch no air are dropped. Then pillars, mezzanines, beams, stairs and light panels (`Box.emit`, placed by density per room) go in.

Only ONE floor exists at a time. Two moves between stages, both invisible because the player is boxed into a shape that is identical on both sides:
- the pool hall -> floor 1: the stair corridor (`corridor`): the pool's exit corridor and floor 1's arrival corridor are the same boxes (with their own tile origin);
  halfway up, with both doors shut, the stage swaps (`transfer`);
- floor k -> k+1: the lift cabin (`Cabin`): its frame (door centre x, floor y, wall face z) is a multiple of 1.2 m (both tile periods), so the cabin of the next floor has the
  same tiles; with the doors shut the stage swaps and the ride goes on.
"""
import hashlib
import math
from dataclasses import dataclass, field

from fps.core.poolmap import EPS, FLOOR, Box, PoolMap, build_map
from fps.weapon_data import (BACKROOMS, BACKROOMS_CORRIDOR_LIGHT, BACKROOMS_DENSITY, BACKROOMS_KIND_GAIN, BACKROOMS_LIGHT, BACKROOMS_LIGHT_SHOWN, BACKROOMS_RED_LIGHT, POOL_STAGE_DOOR_X,
                             Cabin, FloorSpec, MapData)

FLOOR1_GEOMETRY_REV = 1          # floor 1 only: its boxes changed (the stair corridor is cut out of the solid slab) without a spec change: re-bake just that floor
BAKE_VERSION = 2              # bump when the geometry / light bake code changes in a way the stored files cannot reflect (2: G19 carved rooms, lifts)
# the stair corridor (pool hall -> floor 1; identical on both sides)
C_WIDTH = 2.0
DOOR_W = 1.4
DOOR_H = 2.3
LANDING = 1.8
STEPS = 14
RISE = 2.4 / STEPS               # 0.171 m (<= PlayerParams.step_up); 2.4 m = 2 x 1.2 m, a whole number of periods of both tile textures
TREAD = 0.32
CLEAR = 2.9
SLAB = 0.4
CLIMB = STEPS * RISE
LENGTH = LANDING + STEPS * TREAD + LANDING
DOOR_T = 0.08
SWAP_S = LANDING + STEPS * TREAD * 0.5
CORRIDOR_LIGHTS = ((LENGTH * 0.28, 0.9, 0.5), (LENGTH * 0.74, 0.9, 0.5))
# the lift cabin (cabin frame: x across the door, y up from its floor, z into the cabin from the wall face on the room side)
CAB_W = 2.4
CAB_D = 2.4
CAB_H = 2.6
CAB_DOOR_W = 1.4
CAB_DOOR_H = 2.3
CAB_LEAF_TRAVEL = 0.68           # each leaf slides this far sideways into the wall
PANEL_SIZE = (1.2, 0.6)          # ceiling light panel (m)
PANEL_SPACING_MIN = 2.4


@dataclass
class Door:
    """A door leaf in a wall hole: shut it fills its part of the hole (solid for the player, enemies, bullets and the light bake); opening slides it along `slide`
    by `travel` m (up into the lintel for the corridor doors, sideways into the wall for the two leaves of a lift)."""
    name: str
    lo: tuple
    hi: tuple
    kind: str                    # 'exit', 'arrive' (the two the level opens / shuts) or 'dead' (a corridor end that leads nowhere: always shut)
    slide: tuple = (0.0, 1.0, 0.0)
    travel: float = 0.0


@dataclass
class FloorMap(PoolMap):
    """A PoolMap plus what the level needs."""
    spec: FloorSpec = None
    index: int = 0               # stage: 0 = the pool hall, 1..5 = floors
    doors: list = field(default_factory=list)
    exit_origin: tuple = None    # stage 0: the exit corridor frame; floors: the exit cabin frame
    arrive_origin: tuple = None  # floor 1: the arrival corridor frame; floors 2-5: the arrival cabin frame
    arrive_kind: str = None      # 'start' (pool hall), 'corridor' (floor 1), 'cabin'
    exit_kind: str = None        # 'corridor' (pool hall), 'cabin', 'final' (the last floor's cabin)
    nav_rect: tuple = None       # (x0, x1, z0, z1): where enemies live
    start: tuple = None          # (x, y, z, yaw): where the player starts the stage
    arrive_point: tuple = None   # (x, z): where the player comes in (enemies do not spawn near it)
    airs: list = field(default_factory=list)       # named air volumes [(name, lo, hi, light kind)] (hall, rooms, cabins: tools / tests)
    extra_ramps: list = field(default_factory=list)    # the stair flights as walkable ramps (x0, x1, z0, z1, y0, y1[, 'x'])


def _b(name, lo, hi, **kw) -> Box:
    return Box(name, tuple(float(c) for c in lo), tuple(float(c) for c in hi), **kw)


# ------------------------------------------------------------------ box algebra
def overlap(alo, ahi, blo, bhi, eps: float = EPS) -> bool:
    """The two boxes share some volume (touching faces do not count)."""
    return all(alo[i] < bhi[i] - eps and blo[i] < ahi[i] - eps for i in range(3))


def subtract_box(alo, ahi, blo, bhi) -> list:
    """Pieces [(lo, hi)] of box a minus box b (at most 6, no two overlapping)."""
    if not overlap(alo, ahi, blo, bhi):
        return [(tuple(alo), tuple(ahi))]
    out = []
    lo, hi = list(alo), list(ahi)
    for axis in range(3):
        if blo[axis] > lo[axis] + EPS:
            plo, phi = list(lo), list(hi)
            phi[axis] = blo[axis]
            out.append((tuple(plo), tuple(phi)))
            lo[axis] = blo[axis]
        if bhi[axis] < hi[axis] - EPS:
            plo, phi = list(lo), list(hi)
            plo[axis] = bhi[axis]
            out.append((tuple(plo), tuple(phi)))
            hi[axis] = bhi[axis]
    return out


def carve(pieces: list, cuts: list) -> list:
    for clo, chi in cuts:
        nxt = []
        for lo, hi in pieces:
            nxt += subtract_box(lo, hi, clo, chi)
        pieces = nxt
    return pieces


def touches(lo, hi, alo, ahi, eps: float = 1e-4) -> bool:
    """The box (lo, hi) shares a face patch with the air box (or overlaps it)."""
    return all(lo[i] <= ahi[i] + eps and alo[i] <= hi[i] + eps for i in range(3)) and \
        sum(1 for i in range(3) if min(hi[i], ahi[i]) - max(lo[i], alo[i]) > eps) >= 2


# ------------------------------------------------------------------ the stair corridor (pool hall -> floor 1)
def corridor_frame_to_floor(origin: tuple, p: tuple) -> tuple:
    return (origin[0] + p[0], origin[1] + p[1], origin[2] + p[2])


def cut_hole(box: Box, axis: int, u0: float, u1: float, y0: float, y1: float) -> list:
    """Pieces of a wall box (thin along `axis`, 0 = x or 2 = z) after cutting the hole [u0, u1] x [y0, y1] through it. Under a hole at deck level nothing is kept
    (the deck slab under the wall is the hole's floor); a hole above the deck keeps its sill."""
    ua = 2 if axis == 0 else 0
    pieces = []

    def piece(tag, lo_u, hi_u, lo_y, hi_y, walk=None):
        if hi_u - lo_u > EPS and hi_y - lo_y > EPS:
            lo, hi = list(box.lo), list(box.hi)
            lo[ua], hi[ua], lo[1], hi[1] = lo_u, hi_u, lo_y, hi_y
            pieces.append(Box(f'{box.name}_{tag}', tuple(lo), tuple(hi), box.albedo, box.tile, box.walk if walk is None else walk, box.solid, box.visible, box.bullets,
                              box.caster, box.emit, box.uv_origin))
    piece('a', box.lo[ua], u0, box.lo[1], box.hi[1])
    piece('b', u1, box.hi[ua], box.lo[1], box.hi[1])
    piece('top', u0, u1, y1, box.hi[1])
    if y0 > EPS:
        piece('sill', u0, u1, box.lo[1], y0, walk=True)           # the doorway's floor: stood on, not a ledge to be pushed off (a slow walker fell into the gap and was stopped by it)
    return pieces


def corridor(origin: tuple, tag: str, d, own_bottom_from: float = None, own_top_to: float = None) -> tuple:
    """(boxes, air, doors) of a stair corridor with frame origin `origin`. own_bottom_from: build the bottom end wall from this FLOOR height up (None = the whole
    wall: an arrival corridor; an exit corridor's bottom end is the hall wall). own_top_to: likewise for the top end (None = whole; the arrival corridor's top end is
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
    elif own_bottom_from - o[1] < top + w - EPS:
        boxes.append(B('end_b', (-hw - w, own_bottom_from - o[1], -w), (hw + w, top + w, 0.0), **wall_kw))
    if own_top_to is None:
        end_t = B('end_t', (-hw - w, -SLAB, LENGTH), (hw + w, top + w, LENGTH + w), **wall_kw)
        boxes += cut_hole(end_t, 2, o[0] + hole_t[0], o[0] + hole_t[1], o[1] + hole_t[2], o[1] + hole_t[3])
        air.append((corridor_frame_to_floor(o, (hole_t[0], CLIMB, LENGTH)), corridor_frame_to_floor(o, (hole_t[1], CLIMB + DOOR_H, LENGTH + w))))
    for k, (s, sx, sz) in enumerate(CORRIDOR_LIGHTS):
        boxes.append(B(f'light{k}', (-sx / 2, top - 0.03, s - sz / 2), (sx / 2, top, s + sz / 2), albedo=(1.0, 1.0, 1.0), tile=0.0, emit=BACKROOMS_CORRIDOR_LIGHT, uv_origin=o))
    mid = -w / 2.0
    travel = DOOR_H - 0.1
    doors = [Door(f'{tag}_bottom', corridor_frame_to_floor(o, (hole_b[0], 0.0, mid - DOOR_T / 2)), corridor_frame_to_floor(o, (hole_b[1], DOOR_H, mid + DOOR_T / 2)), '',
                  travel=travel),
             Door(f'{tag}_top', corridor_frame_to_floor(o, (hole_t[0], CLIMB, LENGTH + w / 2 - DOOR_T / 2)),
                  corridor_frame_to_floor(o, (hole_t[1], CLIMB + DOOR_H, LENGTH + w / 2 + DOOR_T / 2)), '', travel=travel)]
    return boxes, air, doors


# ------------------------------------------------------------------ the lift cabin
def cabin_air(c: Cabin, w: float) -> list:
    """[(lo, hi)] air of a cabin: its inside and the door hole through the wall (z from the wall face c.z to c.z + w)."""
    return [((c.x - CAB_W / 2, c.y, c.z + w), (c.x + CAB_W / 2, c.y + CAB_H, c.z + w + CAB_D)),
            ((c.x - CAB_DOOR_W / 2, c.y, c.z), (c.x + CAB_DOOR_W / 2, c.y + CAB_DOOR_H, c.z + w))]


def cabin_frame(c: Cabin) -> tuple:
    return (c.x, c.y, c.z)


def cabin_parts(c: Cabin, tag: str, kind: str, w: float) -> tuple:
    """(boxes, doors) of a cabin: its ceiling panel, a lit button plate beside the door, and the two door leaves (they slide sideways into the wall)."""
    x, y, z = c.x, c.y, c.z
    cz = z + w + CAB_D / 2
    boxes = [_b(f'{tag}_light', (x - 0.45, y + CAB_H - 0.03, cz - 0.35), (x + 0.45, y + CAB_H, cz + 0.35), albedo=(1.0, 1.0, 1.0), tile=0.0, emit=BACKROOMS_CORRIDOR_LIGHT),
             _b(f'{tag}_buttons', (x + CAB_DOOR_W / 2 + 0.15, y + 1.05, z + w), (x + CAB_DOOR_W / 2 + 0.35, y + 1.45, z + w + 0.03), albedo=(0.3, 0.3, 0.3), tile=0.0)]
    half = CAB_DOOR_W / 2
    zm = z + w / 2
    doors = [Door(f'{tag}_left', (x - half, y, zm - DOOR_T / 2), (x, y + CAB_DOOR_H, zm + DOOR_T / 2), kind, slide=(-1.0, 0.0, 0.0), travel=CAB_LEAF_TRAVEL),
             Door(f'{tag}_right', (x, y, zm - DOOR_T / 2), (x + half, y + CAB_DOOR_H, zm + DOOR_T / 2), kind, slide=(1.0, 0.0, 0.0), travel=CAB_LEAF_TRAVEL)]
    return boxes, doors


def in_cabin(c, w: float, p: tuple) -> bool:
    """The point (x, y, z) is inside the cabin (behind the door line)."""
    if c is None:
        return False
    return abs(p[0] - c.x) <= CAB_W / 2 + 1e-6 and c.z + w - 0.05 <= p[2] <= c.z + w + CAB_D + 1e-6 and c.y - 0.5 <= p[1] <= c.y + CAB_H


# ------------------------------------------------------------------ lights by density
def room_panels(lo, hi, kind: str, tag: str, room_gain: float = 1.0) -> list:
    """Ceiling panels for the room interior (lo, hi): a grid whose spacing gives the light kind's panel density (at least one panel)."""
    density = BACKROOMS_DENSITY[kind]
    sx, sz = PANEL_SIZE
    w, d = hi[0] - lo[0], hi[2] - lo[2]
    if w < sx + 0.3:                                                    # a narrow tunnel: panels turned across
        sx, sz = sz, sx
    spacing = max(PANEL_SPACING_MIN, math.sqrt(sx * sz / density))
    nx, nz = max(1, round(w / spacing)), max(1, round(d / spacing))
    while nx * nz > 1 and nx * nz * sx * sz / (w * d) > density * 1.5:    # a small room: do not exceed the density much
        if nx >= nz:
            nx -= 1
        else:
            nz -= 1
    gain = BACKROOMS_KIND_GAIN[kind] * room_gain
    le = tuple(c * gain for c in (BACKROOMS_RED_LIGHT if kind == 'red' else BACKROOMS_LIGHT))
    out = []
    for i in range(nx):
        for j in range(nz):
            cx = lo[0] + (i + 0.5) * w / nx
            cz = lo[2] + (j + 0.5) * d / nz
            out.append(_b(f'{tag}_light{i}_{j}', (cx - sx / 2, hi[1] - 0.03, cz - sz / 2), (cx + sx / 2, hi[1], cz + sz / 2), albedo=(1.0, 1.0, 1.0), tile=0.0, emit=le))
    return out


def stair_ramp(st) -> tuple:
    """The walkable ramp of a flight: its steps are only drawn (and stop bullets). A step deeper than a body is wide (0.32 m tread vs 0.34-0.55 m enemy radius) pushed
    the body back off the stairs (core/terrain.py treats a top above step_up as a wall), so feet and the flow field walk a smooth slope instead."""
    x0, z0, x1, z1, ylo, yhi, direction = st
    if direction == 'n':
        return (x0, x1, z0, z1, ylo, yhi)
    if direction == 's':
        return (x0, x1, z0, z1, yhi, ylo)
    if direction == 'e':
        return (x0, x1, z0, z1, ylo, yhi, 'x')
    return (x0, x1, z0, z1, yhi, ylo, 'x')


def _stairs(st, tag: str, kw) -> list:
    x0, z0, x1, z1, ylo, yhi, direction = st
    n = max(1, round((yhi - ylo) / RISE))
    rise = (yhi - ylo) / n
    out = []
    for i in range(n):
        top = ylo + (i + 1) * rise
        if direction == 'n':
            lo, hi = (x0, ylo - SLAB, z0 + (z1 - z0) * i / n), (x1, top, z1)
        elif direction == 's':
            lo, hi = (x0, ylo - SLAB, z0), (x1, top, z1 - (z1 - z0) * i / n)
        elif direction == 'e':
            lo, hi = (x0 + (x1 - x0) * i / n, ylo - SLAB, z0), (x1, top, z1)
        else:
            lo, hi = (x0, ylo - SLAB, z0), (x1 - (x1 - x0) * i / n, top, z1)
        out.append(_b(f'{tag}{i}', lo, hi, **kw))
    return out


# ------------------------------------------------------------------ stages
def stage_count() -> int:
    return 1 + len(BACKROOMS)


def exit_origin(spec=None) -> tuple:
    """The frame of the corridor that leaves the POOL HALL toward floor 1 (at the top of the north-bank stairs)."""
    d = MapData()
    return (POOL_STAGE_DOOR_X, d.stair_rise * d.stair_count, d.room_z / 2.0 + d.wall)


def arrive_origin(spec: FloorSpec) -> tuple:
    d = spec.hall
    return (spec.arrive_x, -CLIMB, -d.room_z / 2.0 - d.wall - LENGTH)


def transfer(stage: int, floors: tuple = BACKROOMS) -> tuple:
    """Offset added to the player's position when stage `stage` is swapped for stage + 1 (the same spot of the same corridor / cabin)."""
    if stage == 0:
        a, b = exit_origin(), arrive_origin(floors[0])
    else:
        a, b = cabin_frame(floors[stage - 1].exit), cabin_frame(floors[stage].arrive)
    return (b[0] - a[0], b[1] - a[1], b[2] - a[2])


def build_stage(stage: int, floors: tuple = BACKROOMS) -> 'FloorMap':
    return build_pool_stage() if stage == 0 else build_floor(stage, floors)


def _finish(pm, d, boxes, air, spec, stage, doors) -> FloorMap:
    xs = [p for lo, hi in air for p in (lo[0], hi[0])]
    zs = [p for lo, hi in air for p in (lo[2], hi[2])]
    hx, hz = d.room_x / 2.0, d.room_z / 2.0
    return FloorMap(d, boxes, air, pm.interior, pm.water, pm.ramp, bounds=(min(xs), max(xs), min(zs), max(zs)),
                    spec=spec, index=stage, doors=doors, nav_rect=(-hx, hx, -hz, hz))


def build_pool_stage() -> FloorMap:
    """Stage 0: the pool hall as it was, plus a door at the top of its north-bank stairs into the stair corridor up to floor 1."""
    d = MapData()
    pm = build_map(d)
    hz, w = d.room_z / 2.0, d.wall
    y0 = d.stair_rise * d.stair_count
    x = POOL_STAGE_DOOR_X
    boxes = []
    for b in pm.boxes:
        if b.name == 'wall_n':
            boxes += cut_hole(b, 2, x - DOOR_W / 2, x + DOOR_W / 2, y0, y0 + DOOR_H)
        else:
            boxes.append(b)
    air = list(pm.air) + [((x - DOOR_W / 2, y0, hz), (x + DOOR_W / 2, y0 + DOOR_H, hz + w))]
    eo = exit_origin()
    cb, ca, cd = corridor(eo, 'up', d, own_bottom_from=d.ceiling + w)
    boxes += cb
    air += ca
    doors = [Door(cd[0].name, cd[0].lo, cd[0].hi, 'exit', travel=cd[0].travel), Door(cd[1].name, cd[1].lo, cd[1].hi, 'dead', travel=cd[1].travel)]
    boxes += [Box(f'{dr.name}_shadow', dr.lo, dr.hi, albedo=(0.5, 0.5, 0.5), tile=0.0, visible=False, bullets=False, caster=True) for dr in doors]
    fm = _finish(pm, d, boxes, air, None, 0, doors)
    fm.exit_origin, fm.exit_kind, fm.arrive_kind = eo, 'corridor', 'start'
    pz = d.pool_z / 2.0
    fm.start = (0.0, 0.0, -(pz + (hz - pz) / 2.0), 0.0)
    fm.arrive_point = (0.0, -hz)
    hx = d.room_x / 2.0
    fm.airs = [('hall', (-hx, 0.0, -hz), (hx, d.ceiling, hz), 'sun')]
    return fm


def room_air(r) -> tuple:
    return (r.x0, r.floor, r.z0), (r.x1, r.floor + r.ceiling, r.z1)


def build_floor(stage: int, floors: tuple = BACKROOMS) -> FloorMap:
    """Stage 1..5 (floors[stage - 1])."""
    spec = floors[stage - 1]
    d = spec.hall
    pm = build_map(d)
    hx, hz = d.room_x / 2.0, d.room_z / 2.0
    w, top = d.wall, d.ceiling
    wall_kw = dict(albedo=d.wall_albedo, tile=d.wall_tile, solid=True)
    floor_kw = dict(albedo=d.floor_albedo, tile=d.floor_tile, walk=True)
    openings = [((o[0], o[4], o[1]), (o[2], o[5], o[3])) for o in spec.openings]
    corr = None
    corr_cut = []
    if spec.arrive_x is not None:                         # floor 1: the stairs from the pool hall come in through the south wall
        openings.append(((spec.arrive_x - DOOR_W / 2, 0.0, -hz - w), (spec.arrive_x + DOOR_W / 2, DOOR_H, -hz)))
        corr = arrive_origin(spec)
        # the corridor's whole outer volume is cut out of the solid around the hall: the corridor builds its own walls, and the 0.4 m slab outside the hall's south wall
        # would otherwise plug the last 0.4 m of its air in front of the open door (the player stopped dead at the top of the stairs)
        corr_cut = [((corr[0] - C_WIDTH / 2 - w, corr[1] - SLAB, corr[2] - w), (corr[0] + C_WIDTH / 2 + w, corr[1] + CLIMB + CLEAR + w, corr[2] + LENGTH + w))]
    # the hall: its walls get the openings (a doorway at deck level is cut down to the slab bottom: the deck under the wall is its floor, a piece left there would
    # put a second face at y = 0)
    wall_cuts = [((lo[0], FLOOR if lo[1] <= EPS else lo[1], lo[2]), hi) for lo, hi in openings]
    boxes = []
    for b in pm.boxes:
        if b.name.startswith('wall_'):
            for k, (lo, hi) in enumerate(carve([(b.lo, b.hi)], wall_cuts)):
                boxes.append(Box(f'{b.name}_{k}', lo, hi, b.albedo, b.tile, b.walk, b.solid, b.visible, b.bullets, b.caster, b.emit, b.uv_origin))
        else:
            boxes.append(b)
    hall_lo, hall_hi = pm.interior
    airs = [('hall', (hall_lo[0], 0.0, hall_lo[2]), hall_hi, spec.hall_light)]
    airs += [(f'room{i}', *room_air(r), r.light) for i, r in enumerate(spec.rooms)]
    cabins = [(name, c) for name, c in (('lift_in', spec.arrive), ('lift_out', spec.exit)) if c is not None]
    cab_air = [a for _, c in cabins for a in cabin_air(c, w)]
    room_airs = [(lo, hi) for _, lo, hi, _ in airs[1:]]
    annex_air = room_airs + openings + cab_air
    # the solid around the hall, carved by every annex air volume
    main_outer = ((-hx - w, FLOOR, -hz - w), (hx + w, top + w, hz + w))
    lo = [min(a[0][i] for a in annex_air) - w for i in range(3)]
    hi = [max(a[1][i] for a in annex_air) + w for i in range(3)]
    lo[1] = min(lo[1], -SLAB)
    all_air = annex_air + [(hall_lo, hall_hi)]
    for k, (plo, phi) in enumerate(carve([(tuple(lo), tuple(hi))], [main_outer] + annex_air + corr_cut)):
        if not any(touches(plo, phi, alo, ahi) for alo, ahi in all_air):
            continue                                                    # buried: never seen, never touched
        is_floor = any(abs(alo[1] - phi[1]) < 1e-4 and plo[0] < ahi[0] - EPS and alo[0] < phi[0] - EPS and plo[2] < ahi[2] - EPS and alo[2] < phi[2] - EPS
                       for alo, ahi in annex_air)
        boxes.append(Box(f'solid{k}', plo, phi, **(floor_kw if is_floor else wall_kw)))
    air = list(pm.air) + annex_air

    def under(x, z):
        """(floor, ceiling) of the hall / room at (x, z)."""
        for _, alo, ahi, _ in airs:
            if alo[0] <= x <= ahi[0] and alo[2] <= z <= ahi[2]:
                return alo[1], ahi[1]
        return 0.0, top
    for i, (x, z, s) in enumerate(spec.pillars):
        y0, y1 = under(x, z)
        boxes.append(_b(f'pillar{i}', (x - s / 2, y0, z - s / 2), (x + s / 2, y1, z + s / 2), **wall_kw))
    for i, (x0, z0, x1, z1, y0, y1, kind) in enumerate(spec.blocks):
        boxes.append(_b(f'block{i}', (x0, y0, z0), (x1, y1, z1), **(floor_kw if kind == 'floor' else wall_kw)))
    step_kw = dict(albedo=d.floor_albedo, tile=d.floor_tile)                 # drawn steps only: the ramp is what is walked
    for i, st in enumerate(spec.stairs):
        boxes += _stairs(st, f'flight{i}_', step_kw)
    gains = {f'room{i}': r.gain for i, r in enumerate(spec.rooms)}
    for name, alo, ahi, kind in airs:
        boxes += room_panels(alo, ahi, kind, name, gains.get(name, 1.0))
    doors = []
    for name, c in cabins:
        cb, cd = cabin_parts(c, name, 'arrive' if name == 'lift_in' else 'exit', w)
        boxes += cb
        doors += cd
    if corr is not None:
        cb, ca, cd = corridor(corr, 'down', d, own_top_to=top + w)
        boxes += cb
        air += ca
        doors += [Door(cd[0].name, cd[0].lo, cd[0].hi, 'dead', travel=cd[0].travel), Door(cd[1].name, cd[1].lo, cd[1].hi, 'arrive', travel=cd[1].travel)]
    boxes += [Box(f'{dr.name}_shadow', dr.lo, dr.hi, albedo=(0.5, 0.5, 0.5), tile=0.0, visible=False, bullets=False, caster=True) for dr in doors]
    fm = _finish(pm, d, boxes, air, spec, stage, doors)
    fm.extra_ramps = [stair_ramp(st) for st in spec.stairs]
    xs = [p for _, alo, ahi, _ in airs for p in (alo[0], ahi[0])]
    zs = [p for _, alo, ahi, _ in airs for p in (alo[2], ahi[2])]
    fm.nav_rect = (min(xs), max(xs), min(zs), max(zs))
    fm.airs = airs + [(name, *cabin_air(c, w)[0], 'cabin') for name, c in cabins]
    fm.exit_kind = 'final' if stage == len(floors) else 'cabin'
    fm.exit_origin = cabin_frame(spec.exit)
    if corr is not None:
        fm.arrive_kind, fm.arrive_origin = 'corridor', corr
        fm.start = (corr[0], corr[1] + CLIMB, corr[2] + LENGTH - 1.0, 0.0)
        fm.arrive_point = (spec.arrive_x, -hz)
    else:
        c = spec.arrive
        fm.arrive_kind, fm.arrive_origin = 'cabin', cabin_frame(c)
        fm.start = (c.x, c.y, c.z + w + CAB_D * 0.55, 180.0)
        fm.arrive_point = (c.x, c.z)
    return fm


def floor_key(fm: FloorMap, look) -> str:
    """Hash of everything a stage's stored lightmap / reflection depend on (the pool hall: its sun too)."""
    sun = (look.sun_dir, look.sun_color) if fm.index == 0 else None
    text = repr((BAKE_VERSION, FLOOR1_GEOMETRY_REV if fm.index == 1 else 0, fm.index, fm.spec, MapData() if fm.index == 0 else None, C_WIDTH, DOOR_W, DOOR_H, LANDING, STEPS, TREAD, CLEAR, SLAB, CORRIDOR_LIGHTS,
                 CAB_W, CAB_D, CAB_H, CAB_DOOR_W, PANEL_SIZE, BACKROOMS_DENSITY, BACKROOMS_KIND_GAIN, BACKROOMS_LIGHT, BACKROOMS_CORRIDOR_LIGHT, BACKROOMS_RED_LIGHT, BACKROOMS_LIGHT_SHOWN,
                 look.sky_irradiance, sun, POOL_STAGE_DOOR_X))
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def in_corridor(origin: tuple, p: tuple) -> float:
    """s (metres up the corridor) of floor point p if it is inside the corridor whose frame origin is `origin`, else None."""
    if origin is None:
        return None
    x, z = p[0] - origin[0], p[2] - origin[2]
    if abs(x) <= C_WIDTH / 2.0 + 1e-6 and -0.5 <= z <= LENGTH + 0.5:
        return z
    return None


def door_offset(door: Door, amount: float) -> tuple:
    """How far the leaf has slid (vector, m) at `amount` (0 shut .. 1 open), smoothstep."""
    t = min(max(amount, 0.0), 1.0)
    k = t * t * (3.0 - 2.0 * t) * door.travel
    return (door.slide[0] * k, door.slide[1] * k, door.slide[2] * k)


def door_box(door: Door, amount: float) -> tuple:
    off = door_offset(door, amount)
    return tuple(door.lo[i] + off[i] for i in range(3)), tuple(door.hi[i] + off[i] for i in range(3))


def emitters(pm: PoolMap) -> list:
    """[(lo, hi, radiance)] of the light panels (boxes with `emit`)."""
    return [(b.lo, b.hi, b.emit) for b in pm.boxes if b.emit is not None]
