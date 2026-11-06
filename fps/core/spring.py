"""Multi-component damped spring (pure math, no ursina import).

Uses the EXACT solution of the damped oscillation for each step dt, so it is stable at any FPS and any dt
(no need for small sub-steps as with Euler). The gun kick (recoil.py) uses it; the G4 mouse sway will use it too.
"""
import math

ZETA_MAX = 0.999   # < 1: the formula below is underdamped oscillation; an overdamped spring is no use for gun feel


def clamp_zeta(zeta: float) -> float:
    return min(max(zeta, 0.05), ZETA_MAX)


class Spring:
    """n independent components, same natural frequency `omega` (rad/s) and damping ratio `zeta`. Return to 0 at rest."""

    def __init__(self, n: int, omega: float, zeta: float):
        self.omega = omega
        self.zeta = zeta
        self.x = [0.0] * n
        self.v = [0.0] * n

    def kick(self, impulses):
        """Add directly to the velocity (impulse)."""
        for i, dv in enumerate(impulses):
            self.v[i] += dv

    def step(self, dt: float):
        zeta = clamp_zeta(self.zeta)
        a = zeta * self.omega
        wd = self.omega * math.sqrt(1.0 - zeta * zeta)
        decay = math.exp(-a * dt)
        c, s = math.cos(wd * dt), math.sin(wd * dt)
        for i in range(len(self.x)):
            x0, v0 = self.x[i], self.v[i]
            b = (v0 + a * x0) / wd
            self.x[i] = decay * (x0 * c + b * s)
            self.v[i] = decay * (v0 * c - (a * b + wd * x0) * s)


def impulse_gain(omega: float, zeta: float) -> float:
    """Velocity impulse needed for a peak deviation of 1 (when the spring is at rest). Multiply by the desired peak deviation."""
    zeta = clamp_zeta(zeta)
    a = zeta * omega
    wd = omega * math.sqrt(1.0 - zeta * zeta)
    t_peak = math.atan2(wd, a) / wd
    return wd / (math.exp(-a * t_peak) * math.sin(wd * t_peak))


def burst_peak_ratio(omega: float, zeta: float, shots: int, interval: float) -> float:
    """Peak of `shots` IDENTICAL impulses spaced `interval` seconds apart, divided by the peak of ONE impulse (linear system, so independent of impulse size).

    Closed form, independent of `Spring.step`: the response to one impulse h(t) = e^(-a t) sin(wd t), normalised to peak = 1, superposed with time-shifted copies.
    Used by tests and selftests to derive 'the whole burst pushes back how many times one shot' from the spring, instead of a hard-coded number."""
    zeta = clamp_zeta(zeta)
    a = zeta * omega
    wd = omega * math.sqrt(1.0 - zeta * zeta)
    t_peak = math.atan2(wd, a) / wd
    norm = math.exp(-a * t_peak) * math.sin(wd * t_peak)
    step = 0.0005
    best = 0.0
    for k in range(int(((shots - 1) * interval + 3.0 * t_peak) / step)):
        t = k * step
        total = sum(math.exp(-a * (t - i * interval)) * math.sin(wd * (t - i * interval)) for i in range(shots) if t > i * interval)
        best = max(best, total / norm)
    return best
