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
BAKE_VERSION = 1                                  # bump when the bake / geometry code changes in a way the stored files cannot reflect
FLOOR = -1.5                                      # bottom of every slab (never visible)


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
              _box('pool_floor', (-px, FLOOR, -pz), (px, d.pool_floor, pz), **floor_kw)]
    rise = -d.pool_floor / (d.steps + 1)
    for i in range(d.steps):
        t = -rise * (i + 1)
        boxes.append(_box(f'step_s{i}', (-px, FLOOR, -pz), (px, t, -pz + (i + 1) * d.step_depth), **floor_kw))
        boxes.append(_box(f'step_n{i}', (d.north_steps_x[0], FLOOR, pz - (i + 1) * d.step_depth), (d.north_steps_x[1], t, pz), **floor_kw))

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
    return PoolMap(d, boxes, air, interior, (-px, px, -pz, pz, d.water_y))


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
    """Whether `p` is in a volume the player can see (interior or window recess) and not inside any box."""
    if not any(all(lo[i] <= p[i] <= hi[i] for i in range(3)) for lo, hi in pm.air):
        return False
    return not any(inside_box(b, p) for b in pm.boxes)


def _exposed_faces(pm: PoolMap) -> list:
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


def reflect_key(d: MapData, look: LookData, lens) -> str:
    """Hash for the stored reflection image: everything the light depends on, plus what changes the picture after the tone curve (exposure, fog colour)."""
    text = repr((bake_key(d, look), look.exposure, look.fog_color, look.fog_density, lens.auto_exposure, lens.exposure_key, lens.exposure_min, lens.exposure_max))
    return hashlib.sha1(text.encode()).hexdigest()[:16]


# ------------------------------------------------------------------ what bullets and feet see
def colliders(pm: PoolMap) -> list:
    """[(lo, hi, owner)] for bullets (the owner is the Box)."""
    return [(b.lo, b.hi, b) for b in pm.boxes if b.bullets]


def walk_tops(pm: PoolMap) -> list:
    """[(x0, x1, z0, z1, top)]: surfaces the player can stand on."""
    return [(b.lo[0], b.hi[0], b.lo[2], b.hi[2], b.hi[1]) for b in pm.boxes if b.walk]


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
