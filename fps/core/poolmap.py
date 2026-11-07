"""The pool hall as AXIS-ALIGNED BOXES (pure Python, no ursina; tests/test_poolmap.py).

Everything solid in the map is a `Box`: slabs, walls (with holes for the windows), ceiling, columns, steps. From the boxes this module derives, with no hand-placed quads:
- `exposed_faces`: the pieces of box faces that touch air inside the room (what is drawn, lit and baked); faces buried in other boxes or facing the outside are dropped, and so is
  everything under the water (the water is opaque, so the pool bottom is never seen);
- `pack_atlas`: where each piece lives in the lightmap atlas;
- `colliders` / `Terrain` inputs: what bullets hit and what the player walks on or bumps into;
- `rail_meshes`: the two steel handrail arches (tubes, the only non-box geometry).
Axes: y up, z forward, x right (Ursina). Face pieces use the axis pair `UV_AXES[axis]` = (u axis, v axis); the metric texture coordinates of the shader are the world coordinates on those axes.
"""
import hashlib
import math
from dataclasses import dataclass

from fps.weapon_data import LookData, MapData

EPS = 1e-6
UV_AXES = {0: (2, 1), 1: (0, 2), 2: (0, 1)}      # normal axis -> (u axis, v axis) lying in the face
BAKE_VERSION = 2                                  # bump when the bake / geometry code changes in a way the stored files cannot reflect (2: the window reveals are drawn)
FLOOR = -2.6                                      # bottom of every slab (never visible; below the deep end of the pool)


@dataclass(frozen=True)
class Box:
    name: str
    lo: tuple
    hi: tuple
    albedo: tuple = (0.75, 0.68, 0.52)
    tile: float = 0.05            # tile size (m) drawn by the shader; 0 = plain colour
    walk: bool = False            # the top face can be stood on (deck, steps, pool floor)
    solid: bool = False           # blocks walking sideways (walls, columns, the invisible window barriers)
    visible: bool = True          # drawn and lit (False: only a collision shape)
    bullets: bool = True          # stops bullets


@dataclass(frozen=True)
class Face:
    """A rectangular piece of one face of one box, in the plane `axis = plane`, spanning [u0, u1] x [v0, v1] on `UV_AXES[axis]`; `sign` is the direction it faces (+1 / -1)."""
    box: int
    axis: int
    sign: int
    plane: float
    u0: float
    u1: float
    v0: float
    v1: float

    @property
    def normal(self) -> tuple:
        n = [0.0, 0.0, 0.0]
        n[self.axis] = float(self.sign)
        return tuple(n)

    def point(self, u: float, v: float) -> tuple:
        """World position of the face-plane point at (u, v) (given in the units of the face's own axes)."""
        p = [0.0, 0.0, 0.0]
        ua, va = UV_AXES[self.axis]
        p[self.axis], p[ua], p[va] = self.plane, u, v
        return tuple(p)

    @property
    def area(self) -> float:
        return (self.u1 - self.u0) * (self.v1 - self.v0)


@dataclass
class PoolMap:
    data: MapData
    boxes: list
    air: list                     # [(lo, hi)] volumes of air the player can see: the room interior and the window recesses
    interior: tuple               # (lo, hi) of the room interior
    water: tuple                  # (x0, x1, z0, z1, y) of the water surface
    ramp: tuple = None            # (x0, x1, z0, z1, y0, y1): the sloping pool bottom between the shallow shelf and the deep end (not a box: walked on via core/terrain.py, drawn by water.frag)

    def exposed_faces(self) -> list:
        if not hasattr(self, '_faces'):
            self._faces = _exposed_faces(self)
        return self._faces


def _box(name, lo, hi, **kw) -> Box:
    return Box(name, tuple(float(c) for c in lo), tuple(float(c) for c in hi), **kw)


def build_map(d: MapData) -> PoolMap:
    hx, hz = d.room_x / 2.0, d.room_z / 2.0
    px, pz = d.pool_x / 2.0, d.pool_z / 2.0
    w, top = d.wall, d.ceiling
    wall_kw = dict(albedo=d.wall_albedo, tile=d.wall_tile, solid=True)
    floor_kw = dict(albedo=d.floor_albedo, tile=d.floor_tile, walk=True)
    boxes = []

    # deck: four slabs around the pool opening, then the pool bottom and the steps
    xe, ze = hx + w, hz + w
    boxes += [_box('deck_s', (-xe, FLOOR, -ze), (xe, 0, -pz), **floor_kw), _box('deck_n', (-xe, FLOOR, pz), (xe, 0, ze), **floor_kw),
              _box('deck_w', (-xe, FLOOR, -pz), (-px, 0, pz), **floor_kw), _box('deck_e', (px, FLOOR, -pz), (xe, 0, pz), **floor_kw),
              _box('pool_floor', (-px, FLOOR, -pz), (px, d.pool_deep, pz), **floor_kw),
              _box('step_shelf', (-px, FLOOR, -pz), (px, d.pool_floor, d.slope_z[0]), **floor_kw)]        # the flat shallow end (a 'step_' box: water.frag traces it like a step)
    rise = -d.pool_floor / (d.steps + 1)
    for i in range(d.steps):
        t = -rise * (i + 1)
        boxes.append(_box(f'step_s{i}', (-px, FLOOR, -pz), (px, t, -pz + (i + 1) * d.step_depth), **floor_kw))
        if d.north_steps:
            boxes.append(_box(f'step_n{i}', (d.north_steps_x[0], FLOOR, pz - (i + 1) * d.step_depth), (d.north_steps_x[1], t, pz), **floor_kw))
    ramp = (-px, px, d.slope_z[0], d.slope_z[1], d.pool_floor, d.pool_deep)

    # walls and ceiling; the east wall is cut by the windows
    boxes += [_box('wall_s', (-xe, FLOOR, -ze), (xe, top + w, -hz), **wall_kw), _box('wall_n', (-xe, FLOOR, hz), (xe, top + w, ze), **wall_kw),
              _box('wall_w', (-xe, FLOOR, -hz), (-hx, top + w, hz), **wall_kw),
              _box('ceiling', (-xe, top, -ze), (xe, top + w, ze), **wall_kw)]
    holes = sorted((zc - d.window_width / 2.0, zc + d.window_width / 2.0) for zc in d.window_z)
    z = -hz
    air = [((-hx, FLOOR, -hz), (hx, top, hz))]
    for i, (z0, z1) in enumerate(holes):
        if z0 > z + EPS:
            boxes.append(_box(f'wall_e_pier{i}', (hx, FLOOR, z), (hx + w, top + w, z0), **wall_kw))
        boxes.append(_box(f'wall_e_sill{i}', (hx, FLOOR, z0), (hx + w, d.window_sill, z1), **wall_kw))
        boxes.append(_box(f'wall_e_lintel{i}', (hx, d.window_top, z0), (hx + w, top + w, z1), **wall_kw))
        # the window itself is an open hole: only an invisible barrier keeps the player in (bullets fly out)
        boxes.append(_box(f'window_gap{i}', (hx, d.window_sill, z0), (hx + w, d.window_top, z1), solid=True, visible=False, bullets=False))
        air.append(((hx, d.window_sill, z0), (hx + w, d.window_top, z1)))
        z = z1
    if z < hz - EPS:
        boxes.append(_box('wall_e_pier_end', (hx, FLOOR, z), (hx + w, top + w, hz), **wall_kw))

    s = d.column_size / 2.0
    for i, cz in enumerate(d.column_z):
        boxes.append(_box(f'column{i}', (d.column_x - s, 0, cz - s), (d.column_x + s, top, cz + s), **wall_kw))

    # a flight of stairs on the north bank, ending in a landing against the north wall
    z_start = pz + 0.4
    for i in range(d.stair_count):
        boxes.append(_box(f'stair{i}', (d.stair_x[0], 0, z_start + i * d.stair_tread), (d.stair_x[1], d.stair_rise * (i + 1), hz), **floor_kw))

    interior = ((-hx, FLOOR, -hz), (hx, top, hz))
    return PoolMap(d, boxes, air, interior, (-px, px, -pz, pz, d.water_y), ramp)


# ------------------------------------------------------------------ exposed faces
def _subtract(rects: list, hole: tuple) -> list:
    """Rectangles (u0, u1, v0, v1) left after cutting the rectangle `hole` out of each."""
    hu0, hu1, hv0, hv1 = hole
    out = []
    for u0, u1, v0, v1 in rects:
        if hu1 <= u0 + EPS or hu0 >= u1 - EPS or hv1 <= v0 + EPS or hv0 >= v1 - EPS:
            out.append((u0, u1, v0, v1))
            continue
        if hu0 > u0 + EPS:
            out.append((u0, hu0, v0, v1))
        if hu1 < u1 - EPS:
            out.append((hu1, u1, v0, v1))
        mu0, mu1 = max(u0, hu0), min(u1, hu1)
        if hv0 > v0 + EPS:
            out.append((mu0, mu1, v0, hv0))
        if hv1 < v1 - EPS:
            out.append((mu0, mu1, hv1, v1))
    return out


def inside_box(b: Box, p, margin: float = 1e-4) -> bool:
    return all(b.lo[i] + margin < p[i] < b.hi[i] - margin for i in range(3))


def is_air(pm: PoolMap, p) -> bool:
    """Whether `p` is in a volume the player can see (interior or window recess) and not inside any VISIBLE box. The invisible window barriers fill the window holes (they only stop the player),
    so counting them as solid dropped every face inside a window hole: the walls looked paper-thin there (user report 7/11/2026)."""
    if not any(all(lo[i] <= p[i] <= hi[i] for i in range(3)) for lo, hi in pm.air):
        return False
    return not any(inside_box(b, p) for b in pm.boxes if b.visible)


def _exposed_faces(pm: PoolMap, under: bool = False) -> list:
    """under=False: the room (everything above the water); under=True: the complementary pieces inside the pool below the surface (G12 `basin_faces`)."""
    px0, px1, pz0, pz1, wy = pm.water
    faces = []
    for bi, b in enumerate(pm.boxes):
        if not b.visible:
            continue
        for axis in range(3):
            ua, va = UV_AXES[axis]
            for sign in (-1, 1):
                plane = b.hi[axis] if sign > 0 else b.lo[axis]
                pieces = [(b.lo[ua], b.hi[ua], b.lo[va], b.hi[va])]
                for oi, o in enumerate(pm.boxes):
                    if oi == bi or not o.visible:
                        continue
                    covers = (o.lo[axis] <= plane + EPS and o.hi[axis] > plane + EPS) if sign > 0 else (o.lo[axis] < plane - EPS and o.hi[axis] >= plane - EPS)
                    if covers:
                        pieces = _subtract(pieces, (o.lo[ua], o.hi[ua], o.lo[va], o.hi[va]))
                        if not pieces:
                            break
                for u0, u1, v0, v1 in pieces:
                    if (u1 - u0) < 1e-3 or (v1 - v0) < 1e-3:
                        continue
                    f = Face(bi, axis, sign, plane, u0, u1, v0, v1)
                    c = f.point((u0 + u1) / 2.0, (v0 + v1) / 2.0)
                    probe = list(c)
                    probe[axis] += sign * 0.002
                    if not is_air(pm, probe):
                        continue
                    # under the water nothing is ever seen: drop the pieces that lie fully below the surface inside the pool, and clip the pool wall at the surface
                    in_pool = px0 - 1e-3 <= c[0] <= px1 + 1e-3 and pz0 - 1e-3 <= c[2] <= pz1 + 1e-3
                    if under:
                        if not in_pool:
                            continue
                        if axis == 1:
                            if plane < wy - 1e-3:
                                faces.append(f)
                            continue
                        hi_y = min(v1, wy - 0.02)                # up to where the room's pool wall starts (no overlapping coplanar strip)
                        if hi_y > v0 + 1e-3:
                            faces.append(Face(bi, axis, sign, plane, u0, u1, v0, hi_y))
                        continue
                    if in_pool:
                        if axis == 1 and plane < wy - 1e-3:
                            continue
                        if axis != 1:                    # the v axis of an x- or z-face is y
                            lo_y = max(v0, wy - 0.02)
                            if v1 <= lo_y + 1e-3:
                                continue
                            f = Face(bi, axis, sign, plane, u0, u1, lo_y, v1)
                    faces.append(f)
    return faces


# ------------------------------------------------------------------ lightmap atlas
@dataclass(frozen=True)
class Placement:
    """A piece in the atlas: the inner area is [x, x + w) x [y, y + h) texels (row 0 = first row of the image); a 1-texel border around it is filled with its edge colour."""
    x: int
    y: int
    w: int
    h: int


@dataclass
class Atlas:
    width: int
    height: int
    faces: list          # [Placement] per exposed face, same order
    probes: list         # [Placement] 2 x 2 patches for the objects that have no UV of their own (handrails)


def face_texels(f: Face, texel: float) -> tuple:
    """(nu, nv): the number of lightmap texels along the u and v axes of a face."""
    return max(1, math.ceil((f.u1 - f.u0) / texel - 1e-9)), max(1, math.ceil((f.v1 - f.v0) / texel - 1e-9))


def pack_atlas(faces: list, texel: float, n_probes: int = 0, width: int = 1024) -> Atlas:
    """Shelf packing (tallest first). The height is rounded up to a power of two."""
    items = [(i, *face_texels(f, texel)) for i, f in enumerate(faces)] + [(len(faces) + k, 2, 2) for k in range(n_probes)]
    order = sorted(items, key=lambda it: (-it[2], -it[1]))
    placed = {}
    x = y = shelf = 0
    for idx, nu, nv in order:
        w, h = nu + 2, nv + 2
        if w > width:
            raise ValueError(f'a face needs {nu} texels but the atlas is {width} wide: raise MapData.texel')
        if x + w > width:
            x, y, shelf = 0, y + shelf, 0
        placed[idx] = Placement(x + 1, y + 1, nu, nv)
        x += w
        shelf = max(shelf, h)
    height = 1
    while height < y + shelf:
        height *= 2
    return Atlas(width, height, [placed[i] for i in range(len(faces))], [placed[len(faces) + k] for k in range(n_probes)])


def lightmap_uv(f: Face, p: Placement, atlas: Atlas, u: float, v: float) -> tuple:
    """Atlas coordinates (U, V) of the face-plane point (u, v), in the OpenGL convention of Panda: V = 1 is the TOP row of the PNG."""
    col = p.x + (u - f.u0) / (f.u1 - f.u0) * p.w
    row = p.y + (v - f.v0) / (f.v1 - f.v0) * p.h
    return col / atlas.width, 1.0 - row / atlas.height


def probe_uv(p: Placement, atlas: Atlas) -> tuple:
    """Atlas coordinates of the middle of a 2 x 2 probe patch."""
    return (p.x + p.w / 2.0) / atlas.width, 1.0 - (p.y + p.h / 2.0) / atlas.height


def bake_key(d: MapData, look: LookData) -> str:
    """Hash of everything the stored lightmap / reflection depend on: the map numbers, the sun and sky, and the code version."""
    text = repr((BAKE_VERSION, d, look.sun_dir, look.sun_color, look.sky_irradiance))
    return hashlib.sha1(text.encode()).hexdigest()[:16]


class AmbientGrid:
    """The baked LOCAL AMBIENT light (core/lightbake.py `ambient_grid`: sky + bounces, no direct sun) on a floor-plan grid: the irradiance an up-facing and a down-facing surface receives
    at gun height. The gun and hands are lit by this (interpolated at the player's spot), so they go dark where the room is dark instead of keeping one fixed ambient value."""

    def __init__(self, data: dict):
        self.x0, self.z0, self.step = float(data['x0']), float(data['z0']), float(data['step'])
        self.nx, self.nz = int(data['nx']), int(data['nz'])
        self.up, self.down = data['up'], data['down']                 # [nz][nx][r, g, b]

    def sample(self, x: float, z: float) -> tuple:
        """((r, g, b) up, (r, g, b) down) at floor position (x, z), bilinear, clamped to the grid."""
        fx = min(max((x - self.x0) / self.step, 0.0), self.nx - 1.0)
        fz = min(max((z - self.z0) / self.step, 0.0), self.nz - 1.0)
        ix, iz = min(int(fx), self.nx - 2), min(int(fz), self.nz - 2)
        tx, tz = fx - ix, fz - iz

        def mix(grid):
            return tuple((grid[iz][ix][c] * (1 - tx) + grid[iz][ix + 1][c] * tx) * (1 - tz) + (grid[iz + 1][ix][c] * (1 - tx) + grid[iz + 1][ix + 1][c] * tx) * tz for c in range(3))
        return mix(self.up), mix(self.down)


def reflect_key(d: MapData, look: LookData, lens) -> str:
    """Hash for the stored reflection image: everything the light depends on, plus what changes the picture after the tone curve (exposure, fog colour)."""
    text = repr((bake_key(d, look), look.exposure, look.fog_color, look.fog_density, lens.auto_exposure, lens.exposure_key, lens.exposure_min, lens.exposure_max))
    return hashlib.sha1(text.encode()).hexdigest()[:16]


# ------------------------------------------------------------------ what the shaders need to know about the geometry (G10)
def window_rects(d: MapData) -> tuple:
    """((z0, z1, y0, y1) per window hole, (x of the inner wall face, x of the outer face)): the only openings the sun comes through (east wall)."""
    rects = tuple((zc - d.window_width / 2.0, zc + d.window_width / 2.0, d.window_sill, d.window_top) for zc in d.window_z)
    return rects, (d.room_x / 2.0, d.room_x / 2.0 + d.wall)


def sun_visible(p, sun, rects, wall, soft: float = 0.0) -> float:
    """Mirror of sun_window.glsl `sun_visible`: 1 if the ray from `p` toward the sun leaves the room through a window hole (it must pass inside the hole at BOTH the inner and
    the outer wall face, so the reveal shades), else 0. `soft` (m) blurs the edges like the shader. Only the east wall has openings and nothing stands between it and the room
    on the sun's side, so for this map that is the whole sun test."""
    sx, sy, sz = sun
    if sx <= 1e-4 or p[0] > wall[0]:
        return 0.0
    best = 0.0
    for z0, z1, y0, y1 in rects:
        k = 1.0
        for x in wall:
            t = (x - p[0]) / sx
            z, y = p[2] + sz * t, p[1] + sy * t
            k *= _inside(z, z0, z1, soft) * _inside(y, y0, y1, soft)
        best = max(best, k)
    return best


def _inside(v: float, lo: float, hi: float, soft: float) -> float:
    if soft <= 0.0:
        return 1.0 if lo <= v <= hi else 0.0

    def ss(a, b, x):
        t = min(max((x - a) / (b - a), 0.0), 1.0)
        return t * t * (3 - 2 * t)
    return ss(lo - soft, lo + soft, v) * (1.0 - ss(hi - soft, hi + soft, v))


def _clip(t0: float, t1: float, a: float, b: float, lo: float, hi: float) -> tuple:
    """Narrow [t0, t1] to the t where lo <= a + b t <= hi."""
    if abs(b) < 1e-9:
        return (t0, t1) if lo <= a <= hi else (1.0, 0.0)
    ta, tb = (lo - a) / b, (hi - a) / b
    if ta > tb:
        ta, tb = tb, ta
    return max(t0, ta), min(t1, tb)


def sunlit_segments(eye, p, sun, rects, wall, max_len: float = 1e9) -> list:
    """Mirror of sun_window.glsl `sun_shaft`: the exact pieces [t0, t1] (metres from the eye) of the segment eye -> p that lie in a sun beam. A beam is the window hole pushed
    along the sun: the projection of a point along the sun onto a wall plane is LINEAR in the point, so along the ray every window gives one interval (both wall faces,
    both axes of the hole, and inside the room)."""
    d = [p[i] - eye[i] for i in range(3)]
    length = math.sqrt(sum(c * c for c in d))
    if length < 1e-6 or sun[0] <= 1e-4:
        return []
    d = [c / length for c in d]
    length = min(length, max_len)
    out = []
    for z0, z1, y0, y1 in rects:
        t0, t1 = 0.0, length
        if abs(d[0]) > 1e-9:                                                     # inside the room: eye.x + d.x t <= inner wall face
            if d[0] > 0:
                t1 = min(t1, (wall[0] - eye[0]) / d[0])
            else:
                t0 = max(t0, (wall[0] - eye[0]) / d[0])
        elif eye[0] > wall[0]:
            continue
        for x in wall:
            k = (x - eye[0]) / sun[0]
            az, ay = eye[2] + sun[2] * k, eye[1] + sun[1] * k                     # projection of the eye onto the wall plane along the sun
            bz, by = d[2] - sun[2] * d[0] / sun[0], d[1] - sun[1] * d[0] / sun[0]   # ... and how it moves per metre along the ray
            t0, t1 = _clip(t0, t1, az, bz, z0, z1)
            t0, t1 = _clip(t0, t1, ay, by, y0, y1)
        if t1 > t0:
            out.append((t0, t1))
    return out


def basin_boxes(pm: PoolMap) -> tuple:
    """((lo, hi) of the water volume, [(lo, hi)] of the step boxes inside it): what the water shader traces a refracted ray against (a ray leaves the basin box from inside,
    and enters a step box from outside)."""
    x0, x1, z0, z1, wy = pm.water
    d = pm.data
    basin = ((x0, d.pool_deep, z0), (x1, wy, z1))
    steps = [(b.lo, b.hi) for b in pm.boxes if b.name.startswith('step_')]
    return basin, steps


def basin_faces(pm: PoolMap) -> list:
    """G12: the faces of the pool basin under the water (floor, steps, walls up to 2 cm below the surface, where the room mesh takes over), for the camera under the water.
    Horizontal faces under the sloping bottom are cut away (the ramp hides them); the ramp itself is `ramp_quad`."""
    faces = _exposed_faces(pm, under=True)
    r = pm.ramp
    if not r:
        return faces
    low = min(r[4], r[5])
    out = []
    for f in faces:
        if f.axis == 1 and f.plane <= low + 1e-3:
            for u0, u1, v0, v1 in _subtract([(f.u0, f.u1, f.v0, f.v1)], (r[0], r[1], r[2], r[3])):
                if u1 - u0 > 1e-3 and v1 - v0 > 1e-3:
                    out.append(Face(f.box, f.axis, f.sign, f.plane, u0, u1, v0, v1))
        else:
            out.append(f)
    return out


def ramp_quad(pm: PoolMap):
    """(four corners, normal) of the sloping pool bottom, or None. The normal (toward the water) matches water.frag's ramp normal."""
    r = pm.ramp
    if not r:
        return None
    x0, x1, z0, z1, y0, y1 = r
    k = (y1 - y0) / (z1 - z0)
    ln = math.sqrt(1.0 + k * k)
    return ((x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1)), (0.0, 1.0 / ln, -k / ln)


def pool_bottom_y(pm: PoolMap, x: float, z: float) -> float:
    """Height of the pool bottom at (x, z) (shelf, ramp, deep floor, steps): what the water shader sees and what the feet stand on."""
    tops = [b.hi[1] for b in pm.boxes if b.walk and b.lo[0] <= x <= b.hi[0] and b.lo[2] <= z <= b.hi[2] and b.hi[1] < pm.water[4]]
    r = pm.ramp
    if r and r[0] <= x <= r[1] and r[2] <= z <= r[3]:
        tops.append(r[4] + (r[5] - r[4]) * (z - r[2]) / (r[3] - r[2]))
    return max(tops)


# ------------------------------------------------------------------ what bullets and feet see
def colliders(pm: PoolMap) -> list:
    """[(lo, hi, owner)] for bullets (the owner is the Box)."""
    return [(b.lo, b.hi, b) for b in pm.boxes if b.bullets]


def walk_tops(pm: PoolMap) -> list:
    """[(x0, x1, z0, z1, top)]: surfaces the player can stand on."""
    return [(b.lo[0], b.hi[0], b.lo[2], b.hi[2], b.hi[1]) for b in pm.boxes if b.walk]


def pool_terrain(pm: PoolMap, radius: float):
    """The walkable map for the player: box tops, the sloping pool bottom (down to the 2 m deep end, G12) and the room walls (minus his radius)."""
    from fps.core.terrain import Terrain
    d = pm.data
    hx, hz = d.room_x / 2.0, d.room_z / 2.0
    return Terrain(walk_tops(pm), solid_boxes(pm), (-hx + radius, hx - radius, -hz + radius, hz - radius), ramps=[pm.ramp] if pm.ramp else [])


def solid_boxes(pm: PoolMap) -> list:
    """[(lo, hi)]: boxes that push the player sideways while his body overlaps them vertically."""
    return [(b.lo, b.hi) for b in pm.boxes if b.solid]


def triangle_count(pm: PoolMap, rails: bool = True) -> int:
    n = 2 * len(pm.exposed_faces())
    if rails:
        n += sum(len(tris) for _, tris in rail_meshes(pm))
    return n


# ------------------------------------------------------------------ handrails
RAIL_SIDES = 8


def _rail_path(d: MapData, x: float) -> list:
    """Centre line (x, y, z) of one handrail arch standing on the north deck edge and curving out over the water: up, a half circle over the pool, down into the water."""
    pz = d.pool_z / 2.0
    anchor_z, r, h = pz + 0.35, 0.5, 0.65
    cz = anchor_z - r
    pts = [(x, 0.0, anchor_z), (x, h * 0.5, anchor_z)]
    for k in range(15):
        a = math.pi * k / 14.0
        pts.append((x, h + r * math.sin(a), cz + r * math.cos(a)))
    leg = cz - r
    pts += [(x, h * 0.5, leg), (x, d.water_y - 0.2, leg)]
    return pts


def _tube(path: list, radius: float, sides: int = RAIL_SIDES) -> tuple:
    verts, tris = [], []
    n = len(path)
    for i, p in enumerate(path):
        a, b = path[max(i - 1, 0)], path[min(i + 1, n - 1)]
        t = tuple(b[k] - a[k] for k in range(3))
        tl = math.sqrt(sum(c * c for c in t)) or 1.0
        t = tuple(c / tl for c in t)
        ref = (1.0, 0.0, 0.0) if abs(t[0]) < 0.9 else (0.0, 1.0, 0.0)
        n1 = (t[1] * ref[2] - t[2] * ref[1], t[2] * ref[0] - t[0] * ref[2], t[0] * ref[1] - t[1] * ref[0])
        nl = math.sqrt(sum(c * c for c in n1)) or 1.0
        n1 = tuple(c / nl for c in n1)
        n2 = (t[1] * n1[2] - t[2] * n1[1], t[2] * n1[0] - t[0] * n1[2], t[0] * n1[1] - t[1] * n1[0])
        for s in range(sides):
            ang = 2.0 * math.pi * s / sides
            ca, sa = math.cos(ang) * radius, math.sin(ang) * radius
            verts.append(tuple(p[k] + n1[k] * ca + n2[k] * sa for k in range(3)))
    for i in range(n - 1):
        for s in range(sides):
            a0, a1 = i * sides + s, i * sides + (s + 1) % sides
            b0, b1 = (i + 1) * sides + s, (i + 1) * sides + (s + 1) % sides
            tris += [(a0, b0, a1), (a1, b0, b1)]
    return verts, tris


def rail_meshes(pm: PoolMap) -> list:
    """[(vertices, triangles)] for the two handrail arches standing on the two sides of the north steps."""
    d = pm.data
    x0, x1 = d.north_steps_x
    return [_tube(_rail_path(d, x), d.rail_radius) for x in (x0 - 0.06, x1 + 0.06)]
