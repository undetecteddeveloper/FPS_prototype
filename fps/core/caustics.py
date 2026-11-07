"""Sun caustics on the pool bottom (G11): pure math of the light-mesh pass (game/caustics.py, assets/shaders/caustics.*), and the small ripples it shares with water.frag.

Why a mesh: the light that lands at a floor point is the SUM over every surface point whose refracted sun ray lands there. Bright lines are the folds of that surface -> floor map,
so they close into a network of rounded cells (G10 evaluated 1 / |det J| at the surface point and painted it straight below: open tangled threads). Method of Evan Wallace's
WebGL Water: a grid of triangles covers the water; every vertex is refracted through the waved surface and dropped onto the floor (`land`), and the same vertex on FLAT water
along the flat refracted ray gives the reference (`land_flat`). Drawn additively into a texture at the landed position, a triangle's brightness is its flat area / landed area,
so flat water gives exactly 1 everywhere, on the sloping bottom too (its n.l is in the shading).

The ripples: a NARROW band of travelling sines (wavelengths `BAND` x `size`, golden-angle directions, random phases and speeds, capillary-gravity dispersion), heights weighted by
wavelength^2 so every wave curves the surface about as much: even cells about `size` across. `height` = rms height of the sum (m).
The low sun (~7 deg) enters steeply sideways (~48 deg from vertical): the cells are stretched along the sun, the pattern lands up to ~2 m west of where the light came in.
"""
import math
import random

G = 9.81
TENSION = 7.2e-5            # m^3/s^2: surface tension / density of water (capillary term of the dispersion)
ETA = 1.0 / 1.333           # air -> water
N_WAVES = 16                # also the size of the shader arrays (pool_waves.glsl)
BAND = (1.6, 0.6)           # longest and shortest wavelength, in multiples of `size`
DIR0 = 0.4                  # rad: direction of the first wave; the next ones turn by the golden angle
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))
_rng = random.Random(7)
PHASES = tuple(_rng.uniform(0.0, 2.0 * math.pi) for _ in range(N_WAVES))
SPEEDS = tuple(_rng.uniform(0.8, 1.25) for _ in range(N_WAVES))      # per-wave factor on the phase speed: no two waves move in step
del _rng


def wave_table(size: float, height: float, speed: float) -> list:
    """[(dir x, dir z, k (rad/m), amplitude (m), omega (rad/s), phase)] of the ripples. size = middle wavelength (m), height = rms height of the sum (m), speed = factor on the dispersion."""
    n = N_WAVES
    lo, hi = BAND
    lams = [size * lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]
    weights = [lam * lam for lam in lams]
    norm = height / math.sqrt(sum(w * w for w in weights) / 2.0) if height > 0 else 0.0
    out = []
    for i, lam in enumerate(lams):
        k = 2.0 * math.pi / lam
        angle = DIR0 + i * GOLDEN
        omega = math.sqrt(G * k + TENSION * k ** 3) * SPEEDS[i] * speed
        out.append((math.cos(angle), math.sin(angle), k, weights[i] * norm, omega, PHASES[i]))
    return out


def pack(table: list) -> tuple:
    """Two lists of 4-tuples for the shader arrays: wave_a = (dir x, dir z, k, amplitude), wave_b = (omega, phase, 0, 0)."""
    return [w[:4] for w in table], [(w[4], w[5], 0.0, 0.0) for w in table]


def surface(x: float, z: float, t: float, table: list) -> tuple:
    """(h, dh/dx, dh/dz) of the ripples at (x, z), time t (mirror of pool_wave in pool_waves.glsl)."""
    h = gx = gz = 0.0
    for dx, dz, k, a, omega, phase in table:
        arg = k * (x * dx + z * dz) - omega * t + phase
        h += a * math.sin(arg)
        c = a * k * math.cos(arg)
        gx += c * dx
        gz += c * dz
    return h, gx, gz


def _norm(v):
    s = math.sqrt(sum(c * c for c in v))
    return tuple(c / s for c in v)


def refract(d: tuple, n: tuple, eta: float = ETA) -> tuple:
    """GLSL refract(): d and n unit vectors, d pointing into the surface. Total reflection -> (0, 0, 0) (never happens from air into water)."""
    cosi = -sum(a * b for a, b in zip(d, n))
    k = 1.0 - eta * eta * (1.0 - cosi * cosi)
    if k < 0.0:
        return (0.0, 0.0, 0.0)
    f = eta * cosi - math.sqrt(k)
    return tuple(eta * a + f * b for a, b in zip(d, n))


def flat_ray(sun: tuple) -> tuple:
    """The sunlight refracted by flat water (sun = unit vector TOWARD the sun)."""
    return refract(tuple(-c for c in _norm(sun)), (0.0, 1.0, 0.0))


def bottom_y(z: float, ramp: tuple) -> float:
    """Pool bottom height at z (ramp = (z0, z1, y at z0, y at z1)): shallow shelf, slope, deep floor; continued past the walls (the texture domain reaches beyond them)."""
    z0, z1, y0, y1 = ramp
    k = min(max((z - z0) / (z1 - z0), 0.0), 1.0)
    return y0 + (y1 - y0) * k


def drop(p: tuple, r: tuple, ramp: tuple, iterations: int = 3) -> tuple:
    """(x, z) where the ray p + s r (r going down) meets the bottom. The bottom only changes with z and slowly: a few fixed-point steps (mirror of caustics.vert)."""
    s = (p[1] - bottom_y(p[2], ramp)) / max(-r[1], 1e-4)
    for _ in range(iterations):
        s = (p[1] - bottom_y(p[2] + s * r[2], ramp)) / max(-r[1], 1e-4)
    return p[0] + s * r[0], p[2] + s * r[2]


def land(x: float, z: float, h: float, gx: float, gz: float, sun: tuple, water_y: float, ramp: tuple) -> tuple:
    """Floor point (x, z) reached by the sunlight that crosses the waved surface at (x, z): height h, slope (gx, gz)."""
    n = _norm((-gx, 1.0, -gz))
    r = refract(tuple(-c for c in _norm(sun)), n)
    return drop((x, water_y + h, z), r, ramp)


def land_flat(x: float, z: float, sun: tuple, water_y: float, ramp: tuple) -> tuple:
    """Same, for flat water: the reference the brightness is measured against."""
    return drop((x, water_y, z), flat_ray(sun), ramp)


def domain(rect: tuple, sun: tuple, deepest: float, pad: float = 0.3) -> tuple:
    """(x0, x1, z0, z1) of the caustic texture: the pool plan widened toward where the light travels (it lands beyond the pool walls; the walls look the pattern up there).
    `deepest` = most water depth (m)."""
    r = flat_ray(sun)
    reach_x, reach_z = r[0] / -r[1] * deepest, r[2] / -r[1] * deepest
    x0, x1, z0, z1 = rect
    return (x0 + min(reach_x, 0.0) - pad, x1 + max(reach_x, 0.0) + pad, z0 + min(reach_z, 0.0) - pad, z1 + max(reach_z, 0.0) + pad)


def texture_size(dom: tuple, long_side: int) -> tuple:
    """(width, height) in texels for `dom`, the longer side `long_side`, the other rounded to a multiple of 16 (texels as square as possible)."""
    wx, wz = dom[1] - dom[0], dom[3] - dom[2]
    if wz >= wx:
        return max(16, int(round(long_side * wx / wz / 16.0)) * 16), long_side
    return long_side, max(16, int(round(long_side * wz / wx / 16.0)) * 16)


def brightness_grid(table: list, t: float, sun: tuple, water_y: float, ramp: tuple, x0: float, z0: float, size: float, n: int, bins: int, margin: float = 0.5) -> list:
    """CPU reference of the pass for tests: n x n photons over the square (x0, z0, size), each carrying its flat landed area, binned where they land (bins x bins over the
    square inset by `margin`, in FLAT-landed coordinates). Returns [bins][bins] brightness, 1 = flat water. Slow (pure Python): small n only."""
    step = size / n
    fx0, fz0 = land_flat(x0, z0, sun, water_y, ramp)
    cell = (size - 2 * margin) / bins
    grid = [[0.0] * bins for _ in range(bins)]
    for i in range(n):
        for j in range(n):
            x, z = x0 + (i + 0.5) * step, z0 + (j + 0.5) * step
            h, gx, gz = surface(x, z, t, table)
            lx, lz = land(x, z, h, gx, gz, sun, water_y, ramp)
            u, v = math.floor((lx - fx0 - margin) / cell), math.floor((lz - fz0 - margin) / cell)
            if 0 <= u < bins and 0 <= v < bins:
                grid[u][v] += step * step
    return [[c / (cell * cell) for c in row] for row in grid]
