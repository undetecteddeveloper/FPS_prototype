"""The camera at and under the water surface (pure Python; tests/test_underwater.py). Mirrors assets/shaders/underwater.glsl line by line.

The lens has a small PORT (the glass in front of the sensor): a render pixel at ndc (x, y) looks through the port point
    eye + right * (x * aspect * port_half) + up * (y * port_half),
so the pixel is WET (sees the underwater world) when that point is below the water at the eye. Its height above the water is linear in (x, y):
    h(x, y) = c + a x + b y (+ a small wobble of the lapping water),  a = port_half * aspect * right.y,  b = port_half * up.y,  c = eye.y - surface.
The world camera never rolls (shake moves the lens frame instead), so right.y = 0 and the waterline is a horizontal line in the rendered image at y = -c / b;
looking straight down (up.y = 0) the whole port is at one height: all wet or all dry. Every shader and the lens evaluate the same h, so the split agrees everywhere.
"""
import math

from fps.core.waves import AMBIENT, GRAVITY
from fps.weapon_data import UnderwaterData, WaterData

WOBBLE = ((9.0, 2.6, 0.6), (21.0, -3.9, 0.4))     # (spatial frequency per ndc unit, angular speed rad/s, weight) of the lapping waterline: same table as underwater.glsl


def ambient_height(x: float, z: float, t: float, w: WaterData) -> float:
    """Height (m) of the always-present ripples at (x, z): the integral of core/waves.py `ambient_slope` (its slope is exactly that function)."""
    total = sum(a[2] for a in AMBIENT)
    h = 0.0
    for angle, wavelength, weight, speed in AMBIENT:
        k = 2.0 * math.pi / (wavelength * w.ripple_scale)
        omega = w.ripple_speed * speed * math.sqrt(GRAVITY * k) * 0.35
        h += w.ripple_strength * weight / total * math.sin(k * (x * math.cos(angle) + z * math.sin(angle)) - omega * t) / k
    return h


def surface_y(x: float, z: float, t: float, water_y: float, w: WaterData) -> float:
    """The water height at (x, z): the still level plus the ambient ripples (the simulated waves live on the GPU and are not read back)."""
    return water_y + ambient_height(x, z, t, w)


def in_pool(x: float, z: float, rect: tuple) -> bool:
    return rect[0] <= x <= rect[1] and rect[2] <= z <= rect[3]


def port_line(eye_y: float, surface: float, right_y: float, up_y: float, aspect: float, port_half: float) -> tuple:
    """(a, b, c) of h(x, y) = c + a x + b y: metres of the port point above the water for the render pixel at ndc (x, y)."""
    return port_half * aspect * right_y, port_half * up_y, eye_y - surface


def wobble(x: float, t: float, amp: float) -> float:
    """The lapping water raises / lowers the waterline along the port (metres); x = ndc along the line."""
    return amp * sum(wt * math.sin(f * x + s * t) for f, s, wt in WOBBLE)


def port_height(line: tuple, x: float, y: float, t: float = 0.0, amp: float = 0.0) -> float:
    a, b, c = line
    return c + a * x + b * y - wobble(x, t, amp)


def is_wet(line: tuple, x: float, y: float, t: float = 0.0, amp: float = 0.0) -> bool:
    return port_height(line, x, y, t, amp) < 0.0


def coverage(line: tuple, amp: float = 0.0) -> tuple:
    """(any pixel can be wet, every pixel is wet) over the whole render [-1, 1]^2, with the wobble margin. h is linear, so its extremes are at the corners."""
    a, b, c = line
    corners = [c + a * x + b * y for x in (-1.0, 1.0) for y in (-1.0, 1.0)]
    margin = abs(amp) * sum(w for _, _, w in WOBBLE)
    return min(corners) - margin < 0.0, max(corners) + margin < 0.0


def band_visible(line: tuple, half_width: float, amp: float = 0.0, reach: float = 1.25) -> bool:
    """G13: can some point of [-reach, reach]^2 have |h| < half_width (the meniscus band of lens.frag around the waterline), wobble included?
    The lens reads the render a little past [-1, 1] (fisheye corners), hence `reach`. False = the lens can use its dry build."""
    a, b, c = line
    lo = c - (abs(a) + abs(b)) * reach
    hi = c + (abs(a) + abs(b)) * reach
    margin = abs(amp) * sum(w for _, _, w in WOBBLE) + half_width
    return lo - margin < 0.0 < hi + margin


def waterline_y(line: tuple):
    """ndc y of the waterline in the rendered image (no roll: a horizontal line); None when the port is level (looking straight down / up)."""
    a, b, c = line
    if abs(b) < 1e-9:
        return None
    return -c / b


def fog(color: tuple, distance: float, d: UnderwaterData, absorption: tuple) -> tuple:
    """Display-space underwater fog (mirror of underwater.glsl `under_fog`): per channel T = exp(-(absorb * scale + turbidity) * d); out = color * T + fog_color * (1 - T)."""
    out = []
    for ch in range(3):
        t = math.exp(-(absorption[ch] * d.absorb_scale + d.turbidity) * max(distance, 0.0))
        out.append(color[ch] * t + d.fog_color[ch] * (1.0 - t))
    return tuple(out)


def step_toward(v: float, target: float, seconds: float, dt: float) -> float:
    """Linear blend toward `target` taking `seconds` for a full 0 -> 1 swing (frame-rate independent)."""
    if seconds <= 0.0:
        return target
    s = dt / seconds
    return min(v + s, target) if target > v else max(v - s, target)
