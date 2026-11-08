"""CPU light baker for the pool hall (numpy; build-time only, the game just loads the PNG: tests/test_lightbake.py).

The sun is fixed, so everything the walls need is computed once:
- DIRECT sun: per lightmap texel, shadow rays over the sun disc (soft edge) against all visible boxes; the window holes are real holes in the boxes, so the hard-edged patches fall out of the geometry;
- INDIRECT light, in two passes, on a sparse grid of texels (`MapData.coarse`) and stretched to the fine texels: cosine-weighted rays remember what they hit.
  Pass 1: a hit spot is as bright as its direct sun. Pass 2: a hit spot is as bright as pass 1 found it (so light bounces twice and the shade fills in); `bounce_gain` stands for the later bounces.
  A ray that leaves through a window brings back `LookData.sky_irradiance`.
The atlas stores IRRADIANCE (what hits the surface), not colour: the shader multiplies it by the tile albedo. 8 bit, gamma 2 (`sqrt(E / lightmap_max)`) so the dark shade keeps resolution.
"""
import math
from dataclasses import dataclass

import numpy as np

from fps.core.poolmap import UV_AXES, Face, PoolMap, face_texels, pack_atlas
from fps.weapon_data import LookData, MapData

CHUNK = 60000                      # rays per numpy batch (keeps the temporary arrays small)
SURFACE_OFFSET = 1e-3              # rays start this far in front of the surface
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


@dataclass
class BakeResult:
    rgb: np.ndarray                # (H, W, 3) uint8, row 0 = first image row
    e_max: float
    atlas: object                  # poolmap.Atlas
    faces: list
    probes: list                   # [(position, normal)] in the same order as atlas.probes
    stats: dict
    ambient: dict = None           # AmbientGrid.to_dict(): the local ambient light for the gun and hands


class Occluders:
    """The boxes that block light (visible ones, and the G14 shadow casters that stand for the ladder tubes), as arrays."""

    def __init__(self, pm: PoolMap):
        vis = [b for b in pm.boxes if b.visible or b.caster]
        self.box_index = np.array([i for i, b in enumerate(pm.boxes) if b.visible or b.caster], dtype=np.int64)     # position in pm.boxes (Face.box)
        self.lo = np.array([b.lo for b in vis], dtype=np.float64)
        self.hi = np.array([b.hi for b in vis], dtype=np.float64)
        self.albedo = np.array([b.albedo for b in vis], dtype=np.float64)
        self.albedo_by_box = np.zeros((len(pm.boxes), 3))                                               # indexed like Face.box / Gather.box
        for i, b in enumerate(pm.boxes):
            if b.visible or b.caster:
                self.albedo_by_box[i] = b.albedo


def _safe_inverse(d: np.ndarray) -> np.ndarray:
    return 1.0 / np.where(np.abs(d) < 1e-12, np.where(d < 0, -1e-12, 1e-12), d)


def cast(occ: Occluders, origins: np.ndarray, dirs: np.ndarray, t_min: float = 1e-4) -> tuple:
    """Nearest box hit of rays from `origins` (N, 3) along `dirs` ((N, 3) or (3,), unit): (t, box index, axis, sign), t = inf where nothing is hit.
    A box that already contains the origin is ignored (the ray starts inside a solid only by mistake)."""
    n = origins.shape[0]
    d = np.broadcast_to(np.asarray(dirs, dtype=np.float64), (n, 3))
    inv = _safe_inverse(d)
    best_t = np.full(n, np.inf)
    best_i = np.full(n, -1, dtype=np.int64)
    best_axis = np.zeros(n, dtype=np.int64)
    for b in range(len(occ.lo)):
        t1 = (occ.lo[b] - origins) * inv
        t2 = (occ.hi[b] - origins) * inv
        tn = np.minimum(t1, t2)
        tf = np.maximum(t1, t2)
        t_in = tn.max(axis=1)
        t_out = tf.min(axis=1)
        hit = (t_out >= t_in) & (t_in > t_min) & (t_in < best_t)
        if hit.any():
            best_t[hit] = t_in[hit]
            best_i[hit] = b
            best_axis[hit] = np.argmax(tn[hit], axis=1)
    sign = np.where(np.take_along_axis(d, best_axis[:, None], axis=1)[:, 0] > 0, -1, 1)
    return best_t, best_i, best_axis, sign


def any_hit(occ: Occluders, origins: np.ndarray, dirs: np.ndarray, t_min: float = 1e-4) -> np.ndarray:
    """Whether each ray hits any box (no distance limit: the sun is far away)."""
    n = origins.shape[0]
    d = np.broadcast_to(np.asarray(dirs, dtype=np.float64), (n, 3))
    inv = _safe_inverse(d)
    blocked = np.zeros(n, dtype=bool)
    for b in range(len(occ.lo)):
        t1 = (occ.lo[b] - origins) * inv
        t2 = (occ.hi[b] - origins) * inv
        t_in = np.minimum(t1, t2).max(axis=1)
        t_out = np.maximum(t1, t2).min(axis=1)
        blocked |= (t_out >= t_in) & (t_in > t_min)
    return blocked


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    return v / (np.linalg.norm(v) or 1.0)


def sun_directions(sun_dir, samples: int, radius: float) -> np.ndarray:
    """`samples` unit directions spread over the sun disc (a Vogel spiral around the centre direction); one sample = the centre."""
    s = unit(sun_dir)
    if samples <= 1:
        return s[None, :]
    helper = np.array([0.0, 1.0, 0.0]) if abs(s[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    t1 = unit(np.cross(s, helper))
    t2 = np.cross(s, t1)
    k = np.arange(samples)
    r = radius * np.sqrt((k + 0.5) / samples)
    phi = k * GOLDEN
    dirs = s[None, :] + r[:, None] * (np.cos(phi)[:, None] * t1[None, :] + np.sin(phi)[:, None] * t2[None, :])
    return dirs / np.linalg.norm(dirs, axis=1, keepdims=True)


def sun_visibility(occ: Occluders, points: np.ndarray, sun_dir, samples: int, radius: float) -> np.ndarray:
    """Fraction (0..1) of the sun disc visible from each point (N, 3)."""
    dirs = sun_directions(sun_dir, samples, radius)
    vis = np.zeros(points.shape[0])
    for start in range(0, points.shape[0], CHUNK):
        p = points[start:start + CHUNK]
        for d in dirs:
            vis[start:start + CHUNK] += ~any_hit(occ, p, d)
    return vis / len(dirs)


def texel_positions(f: Face, nu: int, nv: int) -> np.ndarray:
    """(nv, nu, 3) centres of the texels of a face piece, pushed a hair in front of the surface."""
    ua, va = UV_AXES[f.axis]
    us = f.u0 + (np.arange(nu) + 0.5) * (f.u1 - f.u0) / nu
    vs = f.v0 + (np.arange(nv) + 0.5) * (f.v1 - f.v0) / nv
    uu, vv = np.meshgrid(us, vs)
    pts = np.zeros((nv, nu, 3))
    pts[..., ua], pts[..., va] = uu, vv
    pts[..., f.axis] = f.plane + f.sign * SURFACE_OFFSET
    return pts


def _tangents(normal: np.ndarray) -> tuple:
    helper = np.array([0.0, 1.0, 0.0]) if abs(normal[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    t1 = unit(np.cross(normal, helper))
    return t1, np.cross(normal, t1)


def direct_light(occ: Occluders, points: np.ndarray, normal: np.ndarray, look: LookData, d: MapData) -> np.ndarray:
    """(N, 3) irradiance from the sun alone at points with this normal."""
    ndl = float(np.dot(normal, unit(look.sun_dir)))
    if ndl <= 0.0:
        return np.zeros((points.shape[0], 3))
    vis = sun_visibility(occ, points, look.sun_dir, d.sun_samples, d.sun_radius)
    return (ndl * vis)[:, None] * np.asarray(look.sun_color)[None, :]


@dataclass
class Gather:
    """Cosine-weighted rays shot from a set of points: what each one hit (or that it left through a window), kept so a second pass can ask 'how bright is that spot'."""
    m: int                         # number of points
    rays: int                      # rays per point
    escaped: np.ndarray            # (m * rays,) bool: the ray left the room (sky)
    box: np.ndarray                # (m * rays,) int16: index into pm.boxes of the box hit (-1 if escaped)
    axis: np.ndarray               # int8
    sign: np.ndarray               # int8
    point: np.ndarray              # (m * rays, 3) float32 hit position
    direct: np.ndarray             # (m * rays, 3) float32 direct sun irradiance at the hit (used when the second pass finds no baked value there)


def gather(occ: Occluders, points: np.ndarray, normal: np.ndarray, look: LookData, d: MapData, rng: np.random.Generator) -> Gather:
    """Shoot `d.bounce_rays` cosine-weighted rays from each point (N, 3) with this surface normal and record what they hit."""
    n_pts, rays = points.shape[0], max(int(d.bounce_rays), 4)
    t1, t2 = _tangents(normal)
    sun = unit(look.sun_dir)
    sun_color = np.asarray(look.sun_color, dtype=np.float64)
    total = n_pts * rays
    g = Gather(n_pts, rays, np.ones(total, dtype=bool), np.full(total, -1, dtype=np.int16), np.zeros(total, dtype=np.int8), np.zeros(total, dtype=np.int8),
               np.zeros((total, 3), dtype=np.float32), np.zeros((total, 3), dtype=np.float32))
    per_chunk = max(1, CHUNK // rays)
    k = np.arange(rays)
    r = np.sqrt((k + 0.5) / rays)
    rotation = rng.uniform(0.0, 2.0 * math.pi)                                                        # one rotation per call (= per face): neighbouring points share the pattern, so the light varies smoothly (a rotation per point shows as blotches)
    for start in range(0, n_pts, per_chunk):
        p = points[start:start + per_chunk]
        m = p.shape[0]
        phi = np.broadcast_to(k[None, :] * GOLDEN + rotation, (m, rays))
        lx, ly = r[None, :] * np.cos(phi), r[None, :] * np.sin(phi)
        lz = np.sqrt(np.maximum(1.0 - r * r, 0.0))[None, :]
        dirs = (lx[..., None] * t1 + ly[..., None] * t2 + lz[..., None] * normal).reshape(-1, 3)
        origins = np.repeat(p, rays, axis=0)
        t, idx, axis, sign = cast(occ, origins, dirs)
        hit = np.isfinite(t)
        g.escaped[start * rays:(start + m) * rays] = ~hit
        if hit.any():
            hp = origins[hit] + dirs[hit] * t[hit][:, None]
            hn = np.zeros((hp.shape[0], 3))
            hn[np.arange(hp.shape[0]), axis[hit]] = sign[hit]
            hp = hp + hn * SURFACE_OFFSET * 2
            ndl = np.maximum(hn @ sun, 0.0)
            lit = ~any_hit(occ, hp, sun) & (ndl > 0)
            rows = np.nonzero(hit)[0] + start * rays
            g.box[rows] = occ.box_index[idx[hit]]
            g.axis[rows], g.sign[rows], g.point[rows] = axis[hit], sign[hit], hp
            g.direct[rows] = (ndl * lit)[:, None] * sun_color[None, :]
    return g


class SurfaceLookup:
    """Finds the baked (coarse) irradiance at a point on a face piece: the second bounce asks 'how bright is the spot this ray hit'."""

    def __init__(self, faces: list):
        self.faces = faces
        self.by_key = {}
        for fi, f in enumerate(faces):
            self.by_key.setdefault((f.box, f.axis, 1 if f.sign > 0 else -1), []).append(fi)

    def __call__(self, g: Gather, grids: list) -> tuple:
        """(E (M, 3), found (M,) bool) for every ray of `g`; rays that escaped or hit a spot with no baked piece (under the water) are not found."""
        out = np.zeros((g.box.shape[0], 3))
        found = np.zeros(g.box.shape[0], dtype=bool)
        hit_rows = np.nonzero(~g.escaped)[0]
        keys = g.box[hit_rows].astype(np.int64) * 6 + g.axis[hit_rows].astype(np.int64) * 2 + (g.sign[hit_rows] > 0)
        for key in np.unique(keys):
            rows = hit_rows[keys == key]
            box, axis, sign = int(key) // 6, (int(key) % 6) // 2, 1 if int(key) % 2 else -1
            for fi in self.by_key.get((box, axis, sign), ()):
                f = self.faces[fi]
                ua, va = UV_AXES[f.axis]
                u, v = g.point[rows, ua], g.point[rows, va]
                inside = (u >= f.u0 - 1e-6) & (u <= f.u1 + 1e-6) & (v >= f.v0 - 1e-6) & (v <= f.v1 + 1e-6) & ~found[rows]
                if not inside.any():
                    continue
                grid = grids[fi]
                cv, cu = grid.shape[:2]
                iu = np.clip(((u[inside] - f.u0) / (f.u1 - f.u0) * cu).astype(int), 0, cu - 1)
                iv = np.clip(((v[inside] - f.v0) / (f.v1 - f.v0) * cv).astype(int), 0, cv - 1)
                sel = rows[inside]
                out[sel] = grid[iv, iu]
                found[sel] = True
        return out, found


def resolve(g: Gather, look: LookData, albedo_by_box: np.ndarray, lookup=None, grids=None) -> np.ndarray:
    """(m, 3) mean light brought back by the rays. Sky for rays that escaped; for a hit: albedo x (baked irradiance there if known, else the direct sun there)."""
    sky = np.asarray(look.sky_irradiance, dtype=np.float64)
    radiance = np.tile(sky, (g.box.shape[0], 1))
    hit = ~g.escaped
    e_hit = g.direct.astype(np.float64)
    if lookup is not None:
        e_baked, found = lookup(g, grids)
        e_hit = np.where(found[:, None], e_baked, g.direct.astype(np.float64))
    radiance[hit] = albedo_by_box[g.box[hit]] * e_hit[hit]
    return radiance.reshape(g.m, g.rays, 3).mean(axis=1)


def _stretch(coarse: np.ndarray, nu: int, nv: int) -> np.ndarray:
    """Bilinear resize of a (cv, cu, 3) grid of texel-centre samples to (nv, nu, 3)."""
    cv, cu = coarse.shape[:2]

    def axis_weights(n_fine: int, n_coarse: int):
        pos = np.clip((np.arange(n_fine) + 0.5) * n_coarse / n_fine - 0.5, 0.0, n_coarse - 1.0)
        i0 = np.floor(pos).astype(int)
        i1 = np.minimum(i0 + 1, n_coarse - 1)
        return i0, i1, (pos - i0)

    u0, u1, uw = axis_weights(nu, cu)
    rows = coarse[:, u0] * (1 - uw)[None, :, None] + coarse[:, u1] * uw[None, :, None]
    v0, v1, vw = axis_weights(nv, cv)
    return rows[v0] * (1 - vw)[:, None, None] + rows[v1] * vw[:, None, None]


def _smooth(grid: np.ndarray) -> np.ndarray:
    """3 x 3 box blur of a (cv, cu, 3) grid with clamped edges: the indirect light is smooth, so this only removes the sampling noise of the rays."""
    cv, cu = grid.shape[:2]
    if cv < 2 and cu < 2:
        return grid
    padded = np.pad(grid, ((1, 1), (1, 1), (0, 0)), mode='edge')
    out = np.zeros_like(grid)
    for dv in range(3):
        for du in range(3):
            out += padded[dv:dv + cv, du:du + cu]
    return out / 9.0


def encode(e: np.ndarray, e_max: float) -> np.ndarray:
    return np.rint(np.sqrt(np.clip(e / e_max, 0.0, 1.0)) * 255.0).astype(np.uint8)


def decode(rgb: np.ndarray, e_max: float) -> np.ndarray:
    return (rgb.astype(np.float64) / 255.0) ** 2 * e_max


AMBIENT_STEP = 1.0                 # m between the ambient probes on the floor plan
AMBIENT_HEIGHT = 1.4               # m above the deck: where the gun is held


def ambient_grid(pm: PoolMap, occ: Occluders, look: LookData, lookup, grids1, rng) -> dict:
    """The ambient light (sky + bounces + fill, NOT the direct sun) a gun held in the room receives, on a grid over the floor plan: irradiance on an up-facing and a down-facing surface
    (the shader mixes the two by the normal, like `ambient_at`). Probes that fall inside a column take the mean of their neighbours."""
    d = pm.data
    hx, hz = d.room_x / 2.0, d.room_z / 2.0
    xs = np.arange(-hx + AMBIENT_STEP / 2, hx, AMBIENT_STEP)
    zs = np.arange(-hz + AMBIENT_STEP / 2, hz, AMBIENT_STEP)
    gx, gz = np.meshgrid(xs, zs)
    pts = np.stack([gx.ravel(), np.full(gx.size, AMBIENT_HEIGHT), gz.ravel()], axis=1)
    inside = np.zeros(len(pts), dtype=bool)
    for lo, hi in zip(occ.lo, occ.hi):
        inside |= np.all((pts > lo) & (pts < hi), axis=1)
    sky = np.asarray(look.sky_irradiance, dtype=np.float64)
    fill = d.fill * sky / max(sky.mean(), 1e-6)
    out = {}
    for name, normal in (('up', (0.0, 1.0, 0.0)), ('down', (0.0, -1.0, 0.0))):
        g = gather(occ, pts, np.array(normal), look, d, rng)
        e = resolve(g, look, occ.albedo_by_box, lookup, grids1) * d.bounce_gain + fill
        grid = e.reshape(len(zs), len(xs), 3)
        bad = inside.reshape(len(zs), len(xs))
        if bad.any() and (~bad).any():
            mean_all = grid[~bad].mean(axis=0)
            for iz, ix in zip(*np.nonzero(bad)):
                near = [grid[jz, jx] for jz in range(max(iz - 2, 0), min(iz + 3, len(zs))) for jx in range(max(ix - 2, 0), min(ix + 3, len(xs))) if not bad[jz, jx]]
                grid[iz, ix] = np.mean(near, axis=0) if near else mean_all
        out[name] = grid
    return {'x0': float(xs[0]), 'z0': float(zs[0]), 'step': AMBIENT_STEP, 'nx': len(xs), 'nz': len(zs),
            'up': np.round(out['up'], 4).tolist(), 'down': np.round(out['down'], 4).tolist()}


def bake(pm: PoolMap, look: LookData, probes: list = (), progress=None) -> BakeResult:
    """Bake the whole map. `probes`: [(position, normal)] single points that get a 2 x 2 patch in the atlas (objects with no UV of their own).
    Pass 1: direct sun (fine) + rays that remember what they hit. Pass 2: the same rays, but a hit spot is as bright as pass 1 found it."""
    d = pm.data
    faces = pm.exposed_faces()
    atlas = pack_atlas(faces, d.texel, n_probes=len(probes))
    occ = Occluders(pm)
    rng = np.random.default_rng(12345)
    fine_direct, gathers, coarse_dims, grids1 = [], [], [], []
    rays_cast = 0
    for fi, f in enumerate(faces):
        nu, nv = face_texels(f, d.texel)
        normal = np.array(f.normal)
        fine = texel_positions(f, nu, nv).reshape(-1, 3)
        fine_direct.append(direct_light(occ, fine, normal, look, d).reshape(nv, nu, 3))
        cu = max(1, math.ceil((f.u1 - f.u0) / d.coarse - 1e-9))
        cv = max(1, math.ceil((f.v1 - f.v0) / d.coarse - 1e-9))
        cpts = texel_positions(f, cu, cv).reshape(-1, 3)
        g = gather(occ, cpts, normal, look, d, rng)
        gathers.append(g)
        coarse_dims.append((cv, cu))
        direct_c = direct_light(occ, cpts, normal, look, d).reshape(cv, cu, 3)
        grids1.append(direct_c + resolve(g, look, occ.albedo_by_box).reshape(cv, cu, 3))               # light after ONE bounce: what the second pass reads
        rays_cast += cpts.shape[0] * d.bounce_rays * 2 + fine.shape[0] * d.sun_samples
        if progress:
            progress(fi + 1, 2 * len(faces))
    lookup = SurfaceLookup(faces)
    sky = np.asarray(look.sky_irradiance, dtype=np.float64)
    fill = d.fill * sky / max(sky.mean(), 1e-6)
    image = np.zeros((atlas.height, atlas.width, 3), dtype=np.float64)
    for fi, (f, place) in enumerate(zip(faces, atlas.faces)):
        nu, nv = face_texels(f, d.texel)
        cv, cu = coarse_dims[fi]
        second = _smooth(resolve(gathers[fi], look, occ.albedo_by_box, lookup, grids1).reshape(cv, cu, 3)) * d.bounce_gain
        gathers[fi] = None                                                           # free the rays as we go
        e = fine_direct[fi] + _stretch(second, nu, nv) + fill
        image[place.y - 1:place.y + nv + 1, place.x - 1:place.x + nu + 1] = np.pad(e, ((1, 1), (1, 1), (0, 0)), mode='edge')
        if progress:
            progress(len(faces) + fi + 1, 2 * len(faces))
    for (pos, normal), place in zip(probes, atlas.probes):
        pos, normal = np.asarray(pos, dtype=np.float64)[None, :], unit(normal)
        g = gather(occ, pos, normal, look, d, rng)
        e = direct_light(occ, pos, normal, look, d) + resolve(g, look, occ.albedo_by_box, lookup, grids1) * d.bounce_gain + fill
        image[place.y - 1:place.y + 3, place.x - 1:place.x + 3] = e[0]
    ambient = ambient_grid(pm, occ, look, lookup, grids1, rng)
    return BakeResult(encode(image, d.lightmap_max), d.lightmap_max, atlas, faces, list(probes), {'rays': rays_cast, 'texels': int(atlas.width * atlas.height)}, ambient)
