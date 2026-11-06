"""Fisheye lens math, exactly the formula in assets/shaders/lens.frag (pure math, so pytest can check it).

Screen coordinates p in [-1, 1]^2. Radius measured in units of half the width: q = (p.x, p.y / frame aspect), r^2 = dot(q, q).
The output image samples the input at p * f(r), f = (1 + k r^2) / (1 + k): the horizontal edge (r = 1) matches the image edge exactly, the centre of the frame is magnified (1 + k) times, and near the corners it reaches outside
the input image (the vignette blacks that out).
"""
import math


def warp_factor(r2: float, k: float) -> float:
    return (1.0 + k * r2) / (1.0 + k)


def distort(x: float, y: float, k: float, aspect: float) -> tuple:
    """Where on the input image the output point (x, y) samples from."""
    qy = y / aspect
    f = warp_factor(x * x + qy * qy, k)
    return x * f, y * f


def center_scale(fov_deg: float, k: float, reference_fov_deg: float) -> float:
    """How many times the centre of the frame is magnified vs. a flat image at FOV `reference_fov_deg`."""
    return (1.0 + k) * math.tan(math.radians(reference_fov_deg) / 2.0) / math.tan(math.radians(fov_deg) / 2.0)


def equivalent_center_fov(fov_deg: float, k: float) -> float:
    """Horizontal FOV of a flat image with the same magnification as the centre of the frame through the lens."""
    return 2.0 * math.degrees(math.atan(math.tan(math.radians(fov_deg) / 2.0) / (1.0 + k)))


def vignette(r: float, start: float, end: float) -> float:
    """1 = unchanged, 0 = black; inverse smoothstep from `start` to `end`."""
    t = min(max((r - start) / max(end - start, 1e-6), 0.0), 1.0)
    return 1.0 - t * t * (3.0 - 2.0 * t)
