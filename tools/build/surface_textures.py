"""Procedural surface textures with DEPTH (numpy; build time only, the game never imports numpy). Shared by tools/build/make_surface_textures.py.

Every texture is a pair: a colour image (RGBA8) and a RELIEF image (RGB8): R = height (255 = the surface, 0 = the deepest point), G / B = the surface normal's x / y
(0.5 = flat). The game reads the relief for parallax occlusion mapping (the grout / the crater really looks sunk in when seen at an angle) and for normal shading.

Coordinates inside a texture: x, y in [-1, 1]; the bullet hole is drawn in "half-size units" (the decal quad is 2 units wide).
Everything is a function of the seed: running the tool again gives the same files.
"""
import numpy as np

HOLE_DEPTH = 0.16        # the deepest point of a bullet hole, as a share of the decal's width (the game's parallax uses the same number: HoleDecals DEPTH)


# ------------------------------------------------------------------ noise helpers
def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def fbm(n: int, seed: int, base: int = 4, octaves: int = 5, gain: float = 0.5, tile: bool = True) -> np.ndarray:
    """n x n value noise in 0..1 (several octaves, bilinear + smoothstep); `tile` makes it wrap, so it repeats without a seam."""
    rng = np.random.default_rng(seed)
    out = np.zeros((n, n))
    amp, total = 1.0, 0.0
    lin = np.arange(n) / n
    for o in range(octaves):
        cells = base * (2 ** o)
        grid = rng.random((cells + 1, cells + 1))
        if tile:
            grid[-1, :], grid[:, -1] = grid[0, :], grid[:, 0]
        g = lin * cells
        i0 = np.floor(g).astype(int)
        f = g - i0
        f = f * f * (3.0 - 2.0 * f)
        i1 = i0 + 1
        a = grid[np.ix_(i0, i0)] * (1 - f)[None, :] + grid[np.ix_(i0, i1)] * f[None, :]
        b = grid[np.ix_(i1, i0)] * (1 - f)[None, :] + grid[np.ix_(i1, i1)] * f[None, :]
        out += amp * (a * (1 - f)[:, None] + b * f[:, None])
        total += amp
        amp *= gain
    return out / total


def blur(img: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur through the FFT (wraps around: fine for tiling textures; the hole fades to nothing before its borders)."""
    n, m = img.shape[:2]
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.fftfreq(m)[None, :]
    kernel = np.exp(-2.0 * (np.pi * sigma) ** 2 * (fx * fx + fy * fy))
    if img.ndim == 2:
        return np.real(np.fft.ifft2(np.fft.fft2(img) * kernel))
    return np.stack([np.real(np.fft.ifft2(np.fft.fft2(img[..., c]) * kernel)) for c in range(img.shape[2])], axis=-1)


def normals_from_height(h: np.ndarray, slope: float, tile: bool = False) -> np.ndarray:
    """(n, n, 2) normal x / y of a height field in 0..1; `slope` = how many units of depth a full 0..1 height step is worth against one pixel of width (bigger = steeper)."""
    if tile:
        gx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
        gy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    else:
        gy, gx = np.gradient(h)
    nx, ny, nz = -gx * slope, -gy * slope, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / ln, ny / ln], axis=-1)


def pack_relief(height: np.ndarray, normal_xy: np.ndarray) -> np.ndarray:
    """RGB8: R = height, G = nx * 0.5 + 0.5, B = ny * 0.5 + 0.5."""
    out = np.stack([height, normal_xy[..., 0] * 0.5 + 0.5, normal_xy[..., 1] * 0.5 + 0.5], axis=-1)
    return (np.clip(out, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def to_u8(rgba: np.ndarray) -> np.ndarray:
    return (np.clip(rgba, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


# ------------------------------------------------------------------ cracks
def _segment_distance(px, py, ax, ay, bx, by):
    """Distance from every pixel (px, py) to the segment a -> b, and the position along it (0..1)."""
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy + 1e-12
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / ll, 0.0, 1.0)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


def crack_field(n: int, rng: np.random.Generator, start_r: float, count: int, length: tuple, width: float, branch: float = 0.35, rings: int = 0, ring_r: tuple = (0.45, 0.7)) -> tuple:
    """(darkness 0..1, depth 0..1) of a web of cracks: `count` jagged cracks from radius `start_r` outward (some branch), plus `rings` partial arcs around the centre.
    The line gets thinner and fainter toward its tip."""
    lin = (np.arange(n) + 0.5) / n * 2.0 - 1.0
    px, py = np.meshgrid(lin, lin)
    dark = np.zeros((n, n))
    segs = []                                              # (ax, ay, bx, by, w0, w1)

    def walk(x, y, ang, total, w0, depth_level):
        steps = max(int(total / 0.045), 3)
        w = w0
        for k in range(steps):
            ang += rng.normal(0.0, 0.32)
            step = total / steps * rng.uniform(0.7, 1.3)
            nx_, ny_ = x + np.cos(ang) * step, y + np.sin(ang) * step
            w1 = w0 * (1.0 - (k + 1) / steps) ** 0.8
            segs.append((x, y, nx_, ny_, w, w1))
            if depth_level == 0 and rng.random() < branch / steps * 3.0 and k > 1:
                walk(nx_, ny_, ang + rng.choice([-1, 1]) * rng.uniform(0.35, 0.8), total * rng.uniform(0.25, 0.45), w1 * 0.8, 1)
            x, y, w = nx_, ny_, w1

    base = rng.uniform(0.0, 2.0 * np.pi)
    for i in range(count):
        ang = base + (i + rng.uniform(-0.3, 0.3)) * 2.0 * np.pi / count
        walk(np.cos(ang) * start_r, np.sin(ang) * start_r, ang, rng.uniform(*length), width, 0)
    for _ in range(rings):                                 # a partial ring crack joining several radial ones
        r = rng.uniform(*ring_r)
        a0 = rng.uniform(0.0, 2.0 * np.pi)
        span = rng.uniform(0.9, 2.4)
        pts = a0 + np.linspace(0.0, span, int(span / 0.12) + 2)
        rad = r + rng.normal(0.0, 0.012, len(pts)).cumsum() * 0.5
        for j in range(len(pts) - 1):
            segs.append((np.cos(pts[j]) * rad[j], np.sin(pts[j]) * rad[j], np.cos(pts[j + 1]) * rad[j + 1], np.sin(pts[j + 1]) * rad[j + 1], width * 0.7, width * 0.7))
    depth = np.zeros((n, n))
    for ax, ay, bx, by, w0, w1 in segs:
        d, t = _segment_distance(px, py, ax, ay, bx, by)
        w = w0 + (w1 - w0) * t
        line = np.exp(-((d / np.maximum(w, 1e-4)) ** 2))
        dark = np.maximum(dark, line)
        depth = np.maximum(depth, np.exp(-((d / np.maximum(w * 0.7, 1e-4)) ** 2)))
    return dark, depth


# ------------------------------------------------------------------ bullet hole
def bullet_hole(seed: int, n: int = 256, crater: float = 0.30, spall: float = 0.46, bore: float = 0.085, cracks: int = 7, crack_len: tuple = (0.45, 0.8),
                rings: int = 1, lobe: tuple = None) -> tuple:
    """One bullet hole in a glazed ceramic tile, drawn straight on. Returns (colour RGBA float n x n x 4, height float n x n in 0..1 with 1 = the surface).

    From the outside in: a faint pale dust halo, the SPALL (the glaze flaked off around the crater: shallow, ragged, shows the pale ceramic body), the CRATER (a bowl
    that gets deeper toward the middle, rough cement), the BORE (a dark round hole), and a web of hairline cracks in the glaze that runs out past the spall.
    `lobe` = (angle, distance, radius): a second flake that spalled off to one side."""
    rng = np.random.default_rng(seed)
    lin = (np.arange(n) + 0.5) / n * 2.0 - 1.0
    x, y = np.meshgrid(lin, lin)
    r = np.hypot(x, y)
    ang = np.arctan2(y, x)

    wob = fbm(n, seed + 1, base=3, octaves=4)                       # rough edges: low-frequency radius change + fine chipping
    fine = fbm(n, seed + 2, base=12, octaves=3)
    rough = fbm(n, seed + 3, base=16, octaves=4)
    knots = rng.random(24)                                          # a closed random curve over the angle: the crater and spall edges are not circles
    knots = (np.roll(knots, 1) + 2.0 * knots + np.roll(knots, -1)) / 4.0
    ang_noise = np.interp(ang, np.linspace(-np.pi, np.pi, 25), np.r_[knots, knots[0]])
    r_c = crater * (0.78 + 0.5 * ang_noise) + 0.05 * (wob - 0.5)
    r_s = spall * (0.80 + 0.45 * ang_noise) + 0.07 * (wob - 0.5) + 0.03 * (fine - 0.5)
    if lobe is not None:                                            # a flake knocked off to one side: grow the spall toward it
        la, ld, lr = lobe
        cx, cy = np.cos(la) * ld, np.sin(la) * ld
        rl = np.hypot(x - cx, y - cy)
        lobe_mask = 1.0 - smoothstep(lr * 0.85, lr * 1.05, rl + 0.06 * (fine - 0.5))
    else:
        lobe_mask = np.zeros((n, n))

    in_spall = np.maximum(1.0 - smoothstep(r_s * 0.93, r_s * 1.02, r), lobe_mask)
    in_crater = np.maximum(1.0 - smoothstep(r_c * 0.9, r_c * 1.0, r), lobe_mask * 0.55)
    in_bore = 1.0 - smoothstep(bore * 0.9, bore * 1.08, r + 0.012 * (rough - 0.5))

    # depth 0 = surface .. 1 = deepest (the height map is 1 - depth)
    spall_depth = 0.16 + 0.07 * (fine - 0.5)
    crater_depth = 0.36 + 0.48 * (1.0 - smoothstep(0.0, 1.0, np.clip((r - bore) / np.maximum(r_c - bore, 1e-3), 0.0, 1.0))) ** 1.3 + 0.1 * (rough - 0.5)
    depth = in_spall * spall_depth
    depth = np.maximum(depth, in_crater * crater_depth)
    depth = np.maximum(depth, in_bore * 1.0)
    depth = np.where(in_bore > 0.5, 1.0, depth)

    dark, c_depth = crack_field(n, rng, start_r=crater * 0.9, count=cracks, length=crack_len, width=0.016, rings=rings, ring_r=(spall * 1.1, spall * 1.5))
    depth = np.maximum(depth, c_depth * 0.22 * (1.0 - in_crater))
    depth = np.clip(blur(depth, 0.8), 0.0, 1.0)

    # colour: glaze white is the tile under the decal (alpha 0); here only what the shot exposed
    body = np.array([0.84, 0.78, 0.66])                            # pale ceramic body (biscuit) where only the glaze flaked off
    cement = np.array([0.62, 0.59, 0.54])                          # rougher cement deeper in the crater
    grain = 0.86 + 0.28 * rough + 0.05 * (blur(rng.random((n, n)), 0.7) - 0.5) * 4.0
    streak = 0.88 + 0.24 * np.interp(ang, np.linspace(-np.pi, np.pi, 49), np.r_[rng.random(48), 0.5])   # radial streaks where the glaze sheared off
    ao = 0.34 + 0.66 * smoothstep(bore * 1.0, bore + (r_c - bore) * 0.55, r)          # dark only close to the bore
    base_col = body[None, None, :] * (1.0 - in_crater[..., None]) + cement[None, None, :] * in_crater[..., None]
    col = base_col * (grain * streak)[..., None] * (1.0 - in_crater[..., None] * (1.0 - ao)[..., None] - in_spall[..., None] * (1.0 - in_crater[..., None]) * 0.12 * depth[..., None])
    glaze_edge = np.array([0.98, 0.97, 0.93])                      # the cut edge of the glaze catches the light
    rim_s = (1.0 - smoothstep(0.0, 0.05, 1.0 - r / np.maximum(r_s, 1e-3))) * in_spall * (1.0 - in_crater)
    rim_c = (1.0 - smoothstep(0.0, 0.08, 1.0 - r / np.maximum(r_c, 1e-3))) * in_crater * (1.0 - in_bore)
    col = col * (1.0 - 0.75 * rim_s[..., None]) + glaze_edge[None, None, :] * 0.75 * rim_s[..., None]
    col = col * (1.0 - 0.45 * rim_c[..., None]) + np.array([0.72, 0.68, 0.60])[None, None, :] * 0.45 * rim_c[..., None]
    col = col * (1.0 - in_bore[..., None] * 0.97)
    col = col * (1.0 - 0.8 * dark[..., None] * (1.0 - in_crater[..., None]))

    # shards of glaze lying around the crater (colour only: the surface they sit on is the flat tile)
    shards = np.zeros((n, n))
    for _ in range(14):
        sa = rng.uniform(0.0, 2.0 * np.pi)
        sr = rng.uniform(crater * 0.8, spall * 1.4)
        sx, sy = np.cos(sa) * sr, np.sin(sa) * sr
        ta = rng.uniform(0.0, np.pi)
        ux, uy = (x - sx) * np.cos(ta) + (y - sy) * np.sin(ta), -(x - sx) * np.sin(ta) + (y - sy) * np.cos(ta)
        ra, rb = rng.uniform(0.026, 0.06), rng.uniform(0.012, 0.028)
        shards = np.maximum(shards, 1.0 - smoothstep(0.85, 1.0, np.hypot(ux / ra, uy / rb)))
    shard_edge = np.clip(blur(shards, 1.2) * 3.0 - 1.5, 0.0, 1.0)
    col = col * (1.0 - shards[..., None]) + (glaze_edge[None, None, :] * 0.94) * shards[..., None] * (1.0 - 0.35 * shard_edge[..., None])

    dust = (0.22 * (1.0 - smoothstep(spall * 0.9, spall * 1.9, r)) * (0.5 + 0.8 * fine)) * (1.0 - in_spall)
    alpha = np.maximum(in_spall, dust * 0.9)
    alpha = np.maximum(alpha, dark * 0.9 * (1.0 - smoothstep(0.78, 0.98, r)))
    alpha = np.maximum(alpha, shards)
    alpha = np.maximum(alpha, in_bore)
    # the dust halo and the cracks are pale / dark lines over the white glaze: colour them there
    pale = np.array([0.80, 0.77, 0.72])
    only_dust = np.clip((dust * 0.9 - in_spall) / np.maximum(alpha, 1e-3), 0.0, 1.0)
    col = col * (1.0 - only_dust[..., None]) + pale[None, None, :] * only_dust[..., None]
    crack_only = np.clip(dark * 0.9 * (1.0 - in_spall), 0.0, 1.0)
    crack_col = np.array([0.20, 0.17, 0.14])
    col = col * (1.0 - crack_only[..., None]) + crack_col[None, None, :] * crack_only[..., None]
    alpha = alpha * (1.0 - smoothstep(0.86, 1.0, r))               # nothing touches the cell border (the atlas cells must not bleed into each other)

    rgba = np.concatenate([np.clip(col, 0.0, 1.0), alpha[..., None]], axis=-1)
    return rgba, 1.0 - depth


def bullet_hole_atlas(cell: int = 256, cols: int = 2, rows: int = 2, base_seed: int = 1700) -> tuple:
    """(colour RGBA8, relief RGB8) of a `cols` x `rows` atlas of different holes (row 0 of the array = the TOP of the image)."""
    specs = [
        dict(crater=0.36, spall=0.54, bore=0.105, cracks=7, crack_len=(0.45, 0.80), rings=1),
        dict(crater=0.30, spall=0.47, bore=0.095, cracks=10, crack_len=(0.40, 0.85), rings=2, lobe=(2.4, 0.34, 0.30)),
        dict(crater=0.26, spall=0.40, bore=0.090, cracks=5, crack_len=(0.35, 0.65), rings=0),
        dict(crater=0.34, spall=0.51, bore=0.100, cracks=8, crack_len=(0.5, 0.9), rings=1, lobe=(-0.6, 0.31, 0.26)),
    ]
    color = np.zeros((rows * cell, cols * cell, 4), np.uint8)
    relief = np.zeros((rows * cell, cols * cell, 3), np.uint8)
    for i in range(cols * rows):
        rgba, h = bullet_hole(base_seed + i * 37, cell, **specs[i % len(specs)])
        ny = rows - 1 - i // cols                              # file row 0 = top; texture v = 0 is the bottom (Panda flips on load): the cell index counts from v = 0
        nx = i % cols
        sl = (slice(ny * cell, (ny + 1) * cell), slice(nx * cell, (nx + 1) * cell))
        color[sl] = to_u8(rgba)
        nxy = normals_from_height(h, slope=cell * HOLE_DEPTH)      # 1 unit of height = HOLE_DEPTH of the decal's width, one pixel = 1 / cell of it
        nxy[..., 1] *= -1.0                                        # array rows run DOWN the image, texture v runs UP
        relief[sl] = pack_relief(h, nxy)
    return color, relief


# ------------------------------------------------------------------ ceramic tiles with grout joints (tile floor, tile walls, the pool basin)
# The reference depths the relief's normals are baked with (metres of the whole 0..1 height range): the game's `LookData.tile_depth_*` can be changed live, the normals only scale.
TILE_DEPTH_FLOOR = 0.006
TILE_DEPTH_WALL = 0.003


def tile_texture(n: int, tiles: int, tile_m: float, grout: float, kind: str, seed: int, depth_m: float) -> tuple:
    """A square of `tiles` x `tiles` ceramic tiles that repeats without a seam (grout lines are centred on the cell borders: the game lays it so cell borders fall on multiples of the tile size).

    Returns (colour RGB float n x n x 3 as a MULTIPLIER of the tile colour the map gives each box (a tile face is ~1.0, grout ~0.6), height n x n in 0..1 with 1 = a tile face,
    normal xy n x n x 2). `grout` = joint width as a share of the tile; `kind` 'floor' = matte glaze with anti-slip grit, 'wall' = glossy glaze with hairline crazing and pinholes.
    `tile_m` / `depth_m` = the tile's size and the full height range in metres (they set how steep the baked normals are)."""
    rng = np.random.default_rng(seed)
    lin = (np.arange(n) + 0.5) / n * tiles                         # tile units
    x, y = np.meshgrid(lin, lin)
    fx, fy = x % 1.0, y % 1.0
    tid = np.floor(y).astype(int) * tiles + np.floor(x).astype(int)
    count = tiles * tiles
    tone = rng.normal(0.0, 1.0, count)                             # per tile: colour shift
    tilt_x, tilt_y = rng.normal(0.0, 1.0, count), rng.normal(0.0, 1.0, count)     # per tile: the tile is laid a little crooked (lippage): its normal differs from its neighbour's
    tone_t, tx_t, ty_t = tone[tid], tilt_x[tid], tilt_y[tid]

    px, py = np.abs(fx - 0.5), np.abs(fy - 0.5)
    hs = 0.5 - grout / 2.0
    r = 0.035 if kind == 'floor' else 0.05                         # rounded corners of a tile face
    qx, qy = px - (hs - r), py - (hs - r)
    sd = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0)) + np.minimum(np.maximum(qx, qy), 0.0) - r      # < 0 inside the tile face, > 0 in the joint
    bevel = 0.022 if kind == 'floor' else 0.016
    face = smoothstep(0.0, bevel, -sd)                             # 0 in the joint, 1 on the tile (a bevelled edge between)

    grit = fbm(n, seed + 1, base=tiles * 24, octaves=3)            # tiling noises: base is a multiple of the period
    blotch = fbm(n, seed + 2, base=tiles * 3, octaves=3)
    sand = fbm(n, seed + 3, base=tiles * 40, octaves=2)
    ridge = 1.0 - np.abs(2.0 * fbm(n, seed + 4, base=tiles * 10, octaves=2) - 1.0)

    # height: joint at the bottom (sandy), tiles up on top; each tile a little crooked, the glaze a little uneven
    wavy = (grit - 0.5) * (0.020 if kind == 'floor' else 0.008) + (blotch - 0.5) * (0.010 if kind == 'floor' else 0.016)
    lip = 0.012
    height = 0.04 + 0.06 * sand + face * (0.90 + wavy + lip * (tx_t * (fx - 0.5) + ty_t * (fy - 0.5)))
    height = np.clip(height, 0.0, 1.0)

    # colour
    face_col = 1.0 + 0.045 * tone_t + (blotch - 0.5) * 0.06
    if kind == 'floor':
        fine_grit = fbm(n, seed + 7, base=tiles * 96, octaves=2, gain=0.6)     # anti-slip grit: tiny sparse dots (the coarse `grit` noise made big stains)
        speck = smoothstep(0.64, 0.70, fine_grit) * 0.11           # darker grains
        fleck = smoothstep(0.66, 0.72, fbm(n, seed + 5, base=tiles * 110, octaves=2, gain=0.6)) * 0.09     # lighter grains
        face_col = face_col - speck + fleck
    else:
        craze = smoothstep(0.972, 0.992, ridge) * 0.09             # hairline crazing in the glaze
        pin = smoothstep(0.88, 0.93, fbm(n, seed + 6, base=tiles * 56, octaves=1)) * 0.22     # pinholes
        face_col = face_col - craze - pin
    arris = 1.0 - smoothstep(0.0, 0.05, -sd)                      # right at the tile edge: chipped, a little darker
    chips = smoothstep(0.66, 0.74, grit) * arris
    face_col = face_col - 0.12 * chips
    grout_col = (0.60 + 0.30 * (sand - 0.5)) * (0.70 + 0.30 * smoothstep(0.0, grout * 0.7, np.maximum(sd, 0.0)))    # darker where the joint meets the tile (ambient occlusion baked in)
    tint_grout = np.array([1.00, 0.97, 0.92])
    colour = face[..., None] * face_col[..., None] * np.ones(3) + (1.0 - face)[..., None] * grout_col[..., None] * tint_grout
    colour = colour * (0.78 + 0.22 * smoothstep(0.0, 0.5, height))[..., None]          # cavity: the joint bottom reads darker than its own colour
    slope = depth_m / (tile_m / (n / tiles))                      # metres of height per metre across one pixel: the steepness of one full 0..1 step per pixel
    return np.clip(colour, 0.0, 1.4), height, normals_from_height(height, slope=slope, tile=True)
