"""Water splash droplets and wading (pure Python, no ursina; tests/test_splash.py). Drawing: game/splash.py.

Droplets fly ballistically (gravity + a little air drag, solved exactly per step like core/smoke.py) and die when they fall back through the water surface (or after `life`).
A bullet makes a narrow crown of fast drops; a body landing in the water makes a wide, slower one. Every number comes from weapon_data.SplashData.
Wading: the water slows the legs (speed factor by depth) and the moving body pushes the water (a push every `wake_spacing` metres walked).
"""
import math
import random

from fps.core.smoke import cone_direction

# droplet record indices
_PX, _PY, _PZ, _VX, _VY, _VZ, _AGE, _LIFE, _SIZE = range(9)


class SplashSim:
    """A fixed pool of droplets; when full, the oldest is reused."""

    def __init__(self, capacity: int = 384, rng: random.Random = None):
        self.capacity = max(int(capacity), 1)
        self.rng = rng or random.Random()
        self.drops = []
        self.spawned = 0

    def burst(self, point: tuple, count: int, speed: float, speed_jitter: float, cone: float, size: float, life: float, up: tuple = (0.0, 1.0, 0.0)):
        """`count` drops from `point` inside `cone` degrees around `up`, speed `speed` (+- jitter share)."""
        rng = self.rng
        for _ in range(max(int(count), 0)):
            d = cone_direction(up, cone, rng)
            s = speed * (1.0 + rng.uniform(-1.0, 1.0) * speed_jitter)
            drop = [point[0], point[1], point[2], d[0] * s, d[1] * s, d[2] * s, 0.0, life * rng.uniform(0.7, 1.0), size * rng.uniform(0.6, 1.3)]
            if len(self.drops) >= self.capacity:
                self.drops.pop(0)
            self.drops.append(drop)
            self.spawned += 1

    def step(self, dt: float, gravity: float, drag: float, surface_y: float):
        """Advance every drop by dt; a drop that falls below `surface_y` (while moving down) or outlives its life is removed. Returns the points where drops fell back (for tiny rings)."""
        if dt <= 0.0 or not self.drops:
            return []
        fell = []
        keep = []
        if drag > 1e-6:
            e = math.exp(-drag * dt)
            g = (1.0 - e) / drag
            vt = -gravity / drag                     # terminal vertical speed
        for p in self.drops:
            vx, vy, vz = p[_VX], p[_VY], p[_VZ]
            if drag > 1e-6:
                p[_PX] += vx * g
                p[_PZ] += vz * g
                p[_PY] += vt * dt + (vy - vt) * g
                p[_VX], p[_VZ] = vx * e, vz * e
                p[_VY] = vt + (vy - vt) * e
            else:
                p[_PX] += vx * dt
                p[_PZ] += vz * dt
                p[_PY] += vy * dt - 0.5 * gravity * dt * dt
                p[_VY] = vy - gravity * dt
            p[_AGE] += dt
            if p[_PY] < surface_y and p[_VY] < 0.0:
                fell.append((p[_PX], surface_y, p[_PZ]))
                continue
            if p[_AGE] >= p[_LIFE]:
                continue
            keep.append(p)
        self.drops = keep
        return fell

    @property
    def count(self) -> int:
        return len(self.drops)

    def draw_items(self):
        """(x, y, z, vx, vy, vz, size, alpha) per drop; alpha fades over the last 30 % of the life."""
        out = []
        for p in self.drops:
            u = p[_AGE] / p[_LIFE]
            a = 1.0 if u < 0.7 else max(0.0, (1.0 - u) / 0.3)
            out.append((p[_PX], p[_PY], p[_PZ], p[_VX], p[_VY], p[_VZ], p[_SIZE], a))
        return out


# ------------------------------------------------------------------ wading
def water_depth(feet_y: float, surface_y: float) -> float:
    """How deep the feet are under the surface (0 when above it)."""
    return max(surface_y - feet_y, 0.0)


def wade_speed_factor(depth: float, chest: float, slow: float) -> float:
    """Walking speed multiplier in water `depth` deep: 1 on dry ground, `slow` at chest depth (`chest` m), linear between, never below `slow`."""
    if depth <= 0.0 or chest <= 0.0:
        return 1.0
    k = min(depth / chest, 1.0)
    return 1.0 - (1.0 - slow) * k


class Wake:
    """Pushes of the water by a walking body: one every `spacing` metres walked in the water (the first one at once on entering), strength by depth and speed."""

    def __init__(self):
        self.walked = 0.0
        self.was_in = False

    def update(self, x: float, z: float, moved: float, depth: float, speed: float, spacing: float, push: float, radius: float, chest: float) -> list:
        """Returns [(x, z, radius, amount)] for the water simulation."""
        if depth <= 0.0:
            self.was_in = False
            self.walked = 0.0
            return []
        out = []
        if not self.was_in:
            self.walked = spacing                    # entering the water: a push at once
            self.was_in = True
        self.walked += moved
        if self.walked >= spacing and spacing > 0.0:
            self.walked = 0.0 if self.walked > 2.0 * spacing else self.walked - spacing
            k = min(depth / max(chest, 1e-3), 1.0) * min(0.4 + speed / 3.0, 1.5)
            out.append((x, z, radius * (0.7 + 0.6 * min(depth / max(chest, 1e-3), 1.0)), push * k))
        return out
