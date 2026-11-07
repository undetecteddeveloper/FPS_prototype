"""Pure math of the pool's wave simulation (tests/test_watersim.py). The GPU pass assets/shaders/water_sim.frag is a line-by-line mirror of `step` and `impulse`.

The water is a height field h on a grid over the pool (metres above the rest level). The damped wave equation, finite differences, two time levels per cell:
    h_new = h + (h - h_prev) * damp + coef * (h_left + h_right + h_down + h_up - 4 h)
`coef` = (speed * dt / cell)^2, stable only when speed * dt / cell <= 1 / sqrt(2) (2D CFL), so the Courant number is capped at MAX_COURANT.
Out-of-grid neighbours are CLAMPED to the edge cell: zero slope at the border = a reflecting pool wall (waves bounce back).
The step is FIXED (STEP seconds) and run at most MAX_STEPS times per frame (`SimClock`): the waves do not depend on the frame rate; a very slow frame gives slow-motion waves, never an explosion.
"""
import math

STEP = 1.0 / 120.0          # s: one simulation step
MAX_STEPS = 2               # steps per frame at most (the GPU has two ping-pong passes)
MAX_COURANT = 0.65          # below 1 / sqrt(2) = 0.707 with a margin


def courant(speed: float, cell: float, dt: float = STEP) -> float:
    return speed * dt / cell


def coefficient(speed: float, cell: float, dt: float = STEP) -> float:
    """(speed dt / cell)^2, with the Courant number capped so the scheme stays stable however fine the grid or fast the waves."""
    c = min(courant(speed, cell, dt), MAX_COURANT)
    return c * c


def damping(life: float, dt: float = STEP) -> float:
    """Per-step factor on the velocity term: a wave left alone loses 1/e of its amplitude in about `life` seconds."""
    return math.exp(-dt / max(life, 1e-3))


def impulse(x: float, z: float, cx: float, cz: float, radius: float, amount: float) -> float:
    """Height added at (x, z) by a push of `amount` metres centred on (cx, cz) (Gaussian of radius `radius`). Negative = a dip (a bullet, a foot pushing water away)."""
    d2 = (x - cx) ** 2 + (z - cz) ** 2
    return amount * math.exp(-d2 / max(radius * radius, 1e-8))


def push(h: list, hp: list, field) -> tuple:
    """Add a displacement `field(i, j)` to BOTH time levels (no velocity of its own: added to `now` only, it kept accelerating and a 1 cm push grew to 9 cm). The GPU adds it after the step."""
    return ([[v + field(i, j) for i, v in enumerate(row)] for j, row in enumerate(h)],
            [[v + field(i, j) for i, v in enumerate(row)] for j, row in enumerate(hp)])


def step(h: list, hp: list, coef: float, damp: float) -> tuple:
    """One step on grids h, hp ([row][col], same size). Returns (h_new, h): the new pair (current, previous)."""
    rows, cols = len(h), len(h[0])
    out = []
    for j in range(rows):
        jm, jp = max(j - 1, 0), min(j + 1, rows - 1)
        row, up, down, prev = h[j], h[jp], h[jm], hp[j]
        new = []
        for i in range(cols):
            im, ip = max(i - 1, 0), min(i + 1, cols - 1)
            c = row[i]
            lap = row[im] + row[ip] + down[i] + up[i] - 4.0 * c
            new.append(c + (c - prev[i]) * damp + coef * lap)
        out.append(new)
    return out, h


def energy(h: list, hp: list) -> float:
    """Sum of squared velocity + squared height (a stand-in for the wave energy, used by the tests to check it decays)."""
    return sum((a - b) ** 2 + a * a for ra, rb in zip(h, hp) for a, b in zip(ra, rb))


class SimClock:
    """How many fixed steps the current frame runs. The accumulator never holds more than one step: a long frame is dropped, not caught up."""

    def __init__(self, step: float = STEP, max_steps: int = MAX_STEPS):
        self.step, self.max_steps = step, max_steps
        self.acc = 0.0
        self.total = 0                         # steps run so far

    def steps(self, dt: float) -> int:
        self.acc += max(dt, 0.0)
        n = min(int(self.acc / self.step + 1e-9), self.max_steps)
        self.acc -= n * self.step
        self.acc = min(self.acc, self.step)
        self.total += n
        return n
