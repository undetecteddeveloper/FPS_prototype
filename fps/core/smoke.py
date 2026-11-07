"""Pure maths for gunpowder smoke (no ursina / panda import, tested by tests/test_smoke.py). Drawing: fps/game/smoke.py.

Model (world frame, y up, metres, seconds); every number comes from weapon_data.SmokeData, read at EMIT time and stored per puff (the F1 panel can change it any time):
- Velocity relative to the air decays exponentially: dv/dt = -drag * (v - air) + rise * up, air = wind + drift. With `air` held for one step the step is solved
  EXACTLY (terminal speed v_inf = air + rise/drag * up; e = exp(-drag dt)), so 30 and 120 steps per second give the same path except for the drift sampling.
- Drift (turbulence): a smooth per-puff wind made of one sine per axis with a random frequency and phase, sampled at the middle of the step (never per-frame jitter).
- Radius = size + growth * sqrt(age / life) (the cloud swells fast first, then slowly). Alpha: 30 ms fade-in, then (1 - age/life)^1.5, exactly 0 at the end of life.
- Ground y = ground_y: the centre never goes below ground_y + GROUND_LIFT * radius; the downward speed hitting the ground turns into outward horizontal speed
  (`ground_spread` share, along the horizontal velocity, or a random heading if there is none) and the vertical speed becomes 0.
- One shot = `puffs` muzzle puffs spread from full speed (the jet that shoots ahead) down to CORE_SPEED of it (the slow core that stays near the muzzle),
  each jittered by speed_jitter and pointed inside `cone` around the barrel, plus `port_puffs` small slow ones out of the ejection port.
"""
import math
import random

FADE_IN = 0.03                  # s: alpha rises 0 -> 1 this fast (a puff never pops in at full opacity)
FADE_POWER = 1.5                # fade-out curve: (1 - age/life)^FADE_POWER
GROUND_LIFT = 0.35              # the centre stays this share of the radius above the ground (a resting puff looks like it sits on the ground)
CORE_SPEED = 0.25               # the last muzzle puff of a shot moves at this share of `speed` (the first one at the full speed)
SPAWN_STEP = 0.015              # m: puff k of a shot starts k * SPAWN_STEP ahead of the muzzle, so the puffs do not all start on one point
PORT_CONE = 25.0                # deg: spread of the port puffs around port_dir
PORT_GROWTH = 0.5               # port puffs grow by this share of `growth`
DRIFT_FREQ = (1.5, 4.0)         # rad/s: range of the drift sine frequency per axis
DRIFT_UP = 0.5                  # the vertical drift is this share of the horizontal one

# indices into one puff record (a plain list: fastest access in CPython)
_PX, _PY, _PZ, _VX, _VY, _VZ, _AGE, _LIFE, _K, _RISE, _TURB, _R0, _GROW, _OPAC, _SPREAD, _F1, _F2, _F3, _P1, _P2, _P3, _HEAD, _R, _A, _SEED = range(25)


def _norm(v) -> tuple:
    x, y, z = v
    n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-9:
        return 0.0, 0.0, 1.0
    return x / n, y / n, z / n


def _basis(d) -> tuple:
    """Two unit axes perpendicular to the unit vector d."""
    dx, dy, dz = d
    ax = (0.0, 1.0, 0.0) if abs(dy) < 0.9 else (1.0, 0.0, 0.0)
    ux, uy, uz = _norm((ax[1] * dz - ax[2] * dy, ax[2] * dx - ax[0] * dz, ax[0] * dy - ax[1] * dx))
    return (ux, uy, uz), (dy * uz - dz * uy, dz * ux - dx * uz, dx * uy - dy * ux)


def cone_direction(d, cone_deg: float, rng: random.Random) -> tuple:
    """A random unit vector within `cone_deg` of the unit vector d (uniform over the cone's cross-section)."""
    if cone_deg <= 0:
        return d
    (ux, uy, uz), (vx, vy, vz) = _basis(d)
    theta = math.radians(cone_deg) * math.sqrt(rng.random())
    phi = rng.random() * 2.0 * math.pi
    s, c = math.sin(theta), math.cos(theta)
    a, b = s * math.cos(phi), s * math.sin(phi)
    return _norm((d[0] * c + ux * a + vx * b, d[1] * c + uy * a + vy * b, d[2] * c + uz * a + vz * b))


def puff_alpha(age: float, life: float, opacity: float) -> float:
    """Opacity of one puff by age: fast fade-in, then a smooth fade to exactly 0 at `life`."""
    if life <= 0 or age < 0 or age >= life:
        return 0.0
    return opacity * min(1.0, age / FADE_IN) * (1.0 - age / life) ** FADE_POWER


def puff_radius(age: float, life: float, size: float, growth: float) -> float:
    if life <= 0:
        return size
    return size + growth * math.sqrt(min(max(age / life, 0.0), 1.0))


class SmokeSim:
    """A fixed pool of puffs. When full, the oldest puff (the one born first) is reused."""

    def __init__(self, capacity: int = 256, rng: random.Random = None):
        self.capacity = max(int(capacity), 1)
        self.rng = rng or random.Random()
        self._slots = [None] * self.capacity        # puff records, None = never used
        self._live = []                             # slot indices of the alive puffs
        self._alive = [False] * self.capacity
        self._next = 0                              # write pointer: slots fill in birth order, so this one is always the oldest

    # --- emitting ---
    def _spawn(self, data, pos, vel, size: float, growth: float, opacity: float, life: float):
        rng = self.rng
        i = self._next
        self._next = (i + 1) % self.capacity
        f_lo, f_hi = DRIFT_FREQ
        rec = [pos[0], pos[1], pos[2], vel[0], vel[1], vel[2], 0.0, life,
               max(float(data.drag), 0.0), float(data.rise), float(data.turbulence), size, growth, opacity, float(data.ground_spread),
               rng.uniform(f_lo, f_hi), rng.uniform(f_lo, f_hi), rng.uniform(f_lo, f_hi),
               rng.random() * 6.2832, rng.random() * 6.2832, rng.random() * 6.2832,
               rng.random() * 6.2832, size, 0.0, rng.random()]
        self._slots[i] = rec
        if not self._alive[i]:
            self._alive[i] = True
            self._live.append(i)

    def _life(self, data) -> float:
        return max(float(data.life) * (1.0 + self.rng.uniform(-1.0, 1.0) * float(data.life_jitter)), 0.05)

    def emit(self, data, origin: tuple, direction: tuple, port: tuple = None, port_dir: tuple = None) -> None:
        """origin/port: world points; direction/port_dir: world unit vectors. Spawns data.puffs muzzle puffs (+ data.port_puffs at the port if port is not None).
        When full, the OLDEST puffs are reused."""
        rng = self.rng
        d = _norm(direction)
        n = max(int(data.puffs), 0)
        for k in range(n):
            share = k / (n - 1) if n > 1 else 0.0
            speed = float(data.speed) * (1.0 - (1.0 - CORE_SPEED) * share) * (1.0 + rng.uniform(-1.0, 1.0) * float(data.speed_jitter))
            u = cone_direction(d, float(data.cone), rng)
            pos = (origin[0] + d[0] * SPAWN_STEP * k, origin[1] + d[1] * SPAWN_STEP * k, origin[2] + d[2] * SPAWN_STEP * k)
            size = float(data.size) * rng.uniform(0.8, 1.2)
            self._spawn(data, pos, (u[0] * speed, u[1] * speed, u[2] * speed), size, float(data.growth), float(data.opacity), self._life(data))
        if port is None:
            return
        pd = _norm(port_dir if port_dir is not None else (0.0, 1.0, 0.0))
        for _ in range(max(int(data.port_puffs), 0)):
            speed = float(data.port_speed) * (1.0 + rng.uniform(-1.0, 1.0) * float(data.speed_jitter))
            u = cone_direction(pd, PORT_CONE, rng)
            size = float(data.port_size) * rng.uniform(0.8, 1.2)
            self._spawn(data, tuple(port), (u[0] * speed, u[1] * speed, u[2] * speed), size, float(data.growth) * PORT_GROWTH,
                        float(data.port_opacity), self._life(data))

    # --- simulation ---
    def step(self, dt: float, wind: tuple, ground_y: float = 0.0) -> None:
        """Advance every alive puff by dt seconds (exact exponential drag per step, see the module docstring)."""
        if dt <= 0 or not self._live:
            return
        wx, wy, wz = wind
        slots, alive = self._slots, self._alive
        decay = {}                                  # drag -> (e, (1 - e)/drag): usually one value for the whole pool
        keep = []
        sqrt, sin, exp = math.sqrt, math.sin, math.exp
        for i in self._live:
            p = slots[i]
            age = p[_AGE]
            mid = age + 0.5 * dt
            t = p[_TURB]
            ax = wx + t * sin(p[_F1] * mid + p[_P1])
            ay = wy + t * DRIFT_UP * sin(p[_F2] * mid + p[_P2])
            az = wz + t * sin(p[_F3] * mid + p[_P3])
            k = p[_K]
            vx, vy, vz = p[_VX], p[_VY], p[_VZ]
            if k > 1e-6:
                ed = decay.get(k)
                if ed is None:
                    e = exp(-k * dt)
                    ed = decay[k] = (e, (1.0 - e) / k)
                e, g = ed
                ay += p[_RISE] / k                  # terminal velocity
                rx, ry, rz = vx - ax, vy - ay, vz - az
                px = p[_PX] + ax * dt + rx * g
                py = p[_PY] + ay * dt + ry * g
                pz = p[_PZ] + az * dt + rz * g
                vx, vy, vz = ax + rx * e, ay + ry * e, az + rz * e
            else:                                   # no air drag: constant acceleration (the drift has no effect without drag)
                r = p[_RISE]
                px = p[_PX] + vx * dt
                py = p[_PY] + vy * dt + 0.5 * r * dt * dt
                pz = p[_PZ] + vz * dt
                vy += r * dt
            age += dt
            life = p[_LIFE]
            if age >= life:
                alive[i] = False
                continue
            u = age / life
            radius = p[_R0] + p[_GROW] * sqrt(u)
            floor = ground_y + GROUND_LIFT * radius
            if py < floor:
                py = floor
                if vy < 0.0:
                    push = -vy * p[_SPREAD]
                    h = sqrt(vx * vx + vz * vz)
                    if h > 1e-4:
                        vx += vx / h * push
                        vz += vz / h * push
                    else:
                        vx += math.cos(p[_HEAD]) * push
                        vz += math.sin(p[_HEAD]) * push
                    vy = 0.0
            p[_PX], p[_PY], p[_PZ], p[_VX], p[_VY], p[_VZ], p[_AGE] = px, py, pz, vx, vy, vz, age
            p[_R] = radius
            p[_A] = p[_OPAC] * min(1.0, age / FADE_IN) * (1.0 - u) ** FADE_POWER
            keep.append(i)
        self._live = keep

    # --- reading ---
    @property
    def count(self) -> int:
        """Number of alive puffs."""
        return len(self._live)

    def particles(self):
        """Alive puffs as (pos tuple, radius, alpha)."""
        slots = self._slots
        for i in self._live:
            p = slots[i]
            yield (p[_PX], p[_PY], p[_PZ]), p[_R], p[_A]

    def draw_items(self):
        """Alive puffs as flat tuples (x, y, z, radius, alpha, seed 0..1) for the renderer (seed: a stable random number per puff, for its noise pattern)."""
        slots = self._slots
        return [(p[_PX], p[_PY], p[_PZ], p[_R], p[_A], p[_SEED]) for p in (slots[i] for i in self._live)]

    def velocities(self):
        """Alive puffs' velocities (for tests and tools)."""
        slots = self._slots
        for i in self._live:
            p = slots[i]
            yield p[_VX], p[_VY], p[_VZ]

    def ages(self):
        slots = self._slots
        for i in self._live:
            yield slots[i][_AGE]

    def clear(self):
        for i in self._live:
            self._alive[i] = False
        self._live = []
