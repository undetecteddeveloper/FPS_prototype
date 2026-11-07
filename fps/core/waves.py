"""Water surface ripples (pure Python; tests/test_waves.py). The GLSL in assets/shaders/water.frag is a line-by-line mirror of `ambient_slope` and `ring_slope`.

The water is a flat quad: nothing is displaced, only the SLOPE of the surface is computed and the shader tilts the normal by it (which bends the reflection).
Every function takes the ABSOLUTE time `t`, never a per-frame increment, so 30 and 240 FPS draw the same ripples.
- ambient: a few travelling sine waves in different directions and sizes (faint, always there);
- ring: a bullet makes an expanding packet of crests: radial slope = amp x strength x envelope(r - speed t) x cos(k (r - speed t)) x spreading x fade-out.
"""
import math
from dataclasses import dataclass

from fps.weapon_data import WaterData

# (direction angle rad, wavelength m, slope weight, speed factor)
AMBIENT = ((0.35, 2.10, 1.00, 1.0), (1.90, 1.30, 0.80, 0.8), (-0.90, 0.70, 0.60, 1.2), (2.70, 0.42, 0.45, 1.5), (-2.20, 0.27, 0.30, 1.8))
GRAVITY = 9.81


def ambient_slope(x: float, z: float, t: float, w: WaterData) -> tuple:
    """(dh/dx, dh/dz) of the always-present ripples at the point (x, z) at time t. The peak tilt of the sum is at most `ripple_strength`."""
    total_weight = sum(a[2] for a in AMBIENT)
    sx = sz = 0.0
    for angle, wavelength, weight, speed in AMBIENT:
        k = 2.0 * math.pi / (wavelength * w.ripple_scale)
        omega = w.ripple_speed * speed * math.sqrt(GRAVITY * k) * 0.35        # deep-water-like dispersion: longer waves travel faster
        dx, dz = math.cos(angle), math.sin(angle)
        s = w.ripple_strength * weight / total_weight * math.cos(k * (x * dx + z * dz) - omega * t)
        sx += s * dx
        sz += s * dz
    return sx, sz


def ring_slope(x: float, z: float, t: float, ring: tuple, w: WaterData) -> tuple:
    """Slope of one bullet ring `(x0, z0, t0, amp)` at (x, z); zero before it starts and after `impact_life`."""
    x0, z0, t0, amp = ring
    age = t - t0
    if age < 0.0 or age >= w.impact_life:
        return 0.0, 0.0
    dx, dz = x - x0, z - z0
    r = math.hypot(dx, dz)
    q = (r - w.impact_speed * age) / w.impact_width
    k = 2.0 * math.pi / w.impact_wavelength
    fade = (1.0 - age / w.impact_life) ** 2
    s = amp * w.impact_strength * math.exp(-q * q) * math.cos(k * (r - w.impact_speed * age)) * math.exp(-r / w.impact_reach) * fade
    s *= r / (r + 0.05)                                                        # no direction at the very centre: let it vanish there
    if r < 1e-6:
        return 0.0, 0.0
    return s * dx / r, s * dz / r


def surface_slope(x: float, z: float, t: float, rings, w: WaterData) -> tuple:
    sx, sz = ambient_slope(x, z, t, w)
    for ring in rings:
        rx, rz = ring_slope(x, z, t, ring, w)
        sx += rx
        sz += rz
    return sx, sz


def surface_normal(x: float, z: float, t: float, rings, w: WaterData) -> tuple:
    sx, sz = surface_slope(x, z, t, rings, w)
    n = math.sqrt(sx * sx + 1.0 + sz * sz)
    return -sx / n, 1.0 / n, -sz / n


class RippleBuffer:
    """The rings alive on the water: a ring buffer of `slots` entries (a burst of fire reuses the oldest ring). `packed()` is what the shader's uniform array holds."""

    def __init__(self, slots: int):
        self.slots = slots
        self.rings = [(0.0, 0.0, -1e6, 0.0)] * slots
        self.next = 0

    def add(self, x: float, z: float, t: float, amp: float = 1.0) -> int:
        i = self.next
        self.rings[i] = (float(x), float(z), float(t), float(amp))
        self.next = (self.next + 1) % self.slots
        return i

    def alive(self, t: float, life: float) -> int:
        return sum(1 for r in self.rings if 0.0 <= t - r[2] < life)

    def packed(self) -> list:
        return list(self.rings)
