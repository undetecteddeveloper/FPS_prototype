"""Cubic-bezier easing, like CSS `cubic-bezier(x1, y1, x2, y2)` (pure math, no ursina import). See .claude/skills/camera-easing-bezier.

The curve runs from (0, 0) to (1, 1) with control points P1 = (x1, y1), P2 = (x2, y2); x = time progress, y = output progress. x1 and x2 are clamped to [0, 1]
(the curve must move forward in time); y1 / y2 may leave [0, 1] to overshoot or anticipate. Solving x(t) = u: Newton-Raphson from a sampled guess, bisection as fallback
(the method browsers use).
"""

NEWTON_STEPS = 8
EPS = 1e-7
SAMPLES = 11


class CubicBezier:
    def __init__(self, x1: float, y1: float, x2: float, y2: float):
        x1, x2 = min(max(x1, 0.0), 1.0), min(max(x2, 0.0), 1.0)
        self.points = (x1, y1, x2, y2)
        self.cx = 3.0 * x1
        self.bx = 3.0 * (x2 - x1) - self.cx
        self.ax = 1.0 - self.cx - self.bx
        self.cy = 3.0 * y1
        self.by = 3.0 * (y2 - y1) - self.cy
        self.ay = 1.0 - self.cy - self.by
        self._table = [self._x(i / (SAMPLES - 1)) for i in range(SAMPLES)]

    def _x(self, t: float) -> float:
        return ((self.ax * t + self.bx) * t + self.cx) * t

    def _y(self, t: float) -> float:
        return ((self.ay * t + self.by) * t + self.cy) * t

    def _dx(self, t: float) -> float:
        return (3.0 * self.ax * t + 2.0 * self.bx) * t + self.cx

    def solve_t(self, u: float) -> float:
        """Curve parameter t where x(t) = u (u in [0, 1])."""
        table = self._table
        k = 0
        while k < SAMPLES - 2 and table[k + 1] <= u:
            k += 1
        span = table[k + 1] - table[k]
        t = (k + ((u - table[k]) / span if span > 1e-12 else 0.0)) / (SAMPLES - 1)
        for _ in range(NEWTON_STEPS):
            err = self._x(t) - u
            if abs(err) < EPS:
                return t
            d = self._dx(t)
            if abs(d) < 1e-6:
                break
            t -= err / d
            if t < 0.0 or t > 1.0:
                break
        lo, hi = 0.0, 1.0
        t = min(max(t, 0.0), 1.0)
        for _ in range(60):                            # bisection fallback: x(t) is monotonic because x1, x2 are in [0, 1]
            x = self._x(t)
            if abs(x - u) < EPS:
                break
            if x < u:
                lo = t
            else:
                hi = t
            t = 0.5 * (lo + hi)
        return t

    def __call__(self, u: float) -> float:
        """Eased progress for time progress u (clamped to [0, 1]); 0 -> 0, 1 -> 1."""
        if u <= 0.0:
            return 0.0
        if u >= 1.0:
            return 1.0
        return self._y(self.solve_t(u))


_CACHE = {}


def bezier(points: tuple) -> CubicBezier:
    """Shared curve object for a (x1, y1, x2, y2) tuple (the F1 panel can change the tuple at any time: a new tuple builds a new curve)."""
    key = tuple(float(v) for v in points)
    curve = _CACHE.get(key)
    if curve is None:
        if len(_CACHE) > 64:
            _CACHE.clear()
        curve = _CACHE[key] = CubicBezier(*key)
    return curve
