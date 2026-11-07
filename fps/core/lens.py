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


def frame_shake(pose: tuple, hfov_deg: float, aspect: float, pos_ref: float) -> tuple:
    """Turns a camera shake pose into a move of the whole lens frame (image + vignette + distortion centre), for `lens_shake` in lens.frag.

    pose = (x right, y up, z forward, pitch up, yaw right, roll right) in metres and degrees: the shake the CAMERA would have had.
    Returns (dx, dy, roll): how far the image content moves, in the shader's p units (p.x in [-1, 1] across the width,
    p.y in [-1, 1] across the height), and the CCW rotation of the content in radians.
    - yaw right a -> content moves left: dx = -tan(a) / tan(hfov / 2).
    - pitch up b -> content moves down: dy = -tan(b) / tan(vfov / 2), tan(vfov / 2) = tan(hfov / 2) / aspect.
    - x, y become equivalent angles atan(x / pos_ref), atan(y / pos_ref) (a point `pos_ref` metres ahead); z is ignored.
    - roll right -> the right side of the screen goes up, i.e. the content turns CCW by roll.
    """
    x, y, _z, pitch_up, yaw_right, roll_right = pose
    yaw = math.radians(yaw_right)
    pitch = math.radians(pitch_up)
    if pos_ref > 0.0:
        yaw += math.atan(x / pos_ref)
        pitch += math.atan(y / pos_ref)
    th = math.tan(math.radians(hfov_deg) / 2.0)
    tv = th / aspect
    return -math.tan(yaw) / th, -math.tan(pitch) / tv, math.radians(roll_right)
