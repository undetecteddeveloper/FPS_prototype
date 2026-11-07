"""Sun and sky light computed on the CPU (same formula as assets/shaders/light_common.glsl, without the muzzle flash) and the camera's exposure.

The scene is one flat ground under one sun, so the exposure does not change with where the player stands: it only depends on the light values in `LookData`.
"""
import math

from fps.weapon_data import LensData, LookData


def _luma(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def sun_vector(look: LookData) -> tuple:
    """Unit vector toward the sun."""
    x, y, z = look.sun_dir
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    return (x / n, y / n, z / n)


def light_at(look: LookData, normal: tuple = (0.0, 1.0, 0.0)) -> float:
    """Brightness (luma) of the light on a surface with unit normal `normal`: sky/ground ambient plus the sun. Same blend as `ambient_at` and the sun term of the shaders."""
    k = normal[1] * 0.5 + 0.5
    ambient = [d + (u - d) * k for d, u in zip(look.ambient_down, look.ambient_up)]
    s = sun_vector(look)
    ndl = max(s[0] * normal[0] + s[1] * normal[1] + s[2] * normal[2], 0.0)
    return _luma(ambient) + _luma(look.sun_color) * ndl


def target_exposure(lens: LensData, look: LookData) -> float:
    """Exposure the camera wants for this light: measured over a sphere (average of an upward face and a vertical face), so it does not depend on the view direction."""
    scene = 0.65 * light_at(look) + 0.35 * light_at(look, (0.0, 0.0, 1.0))
    ideal = lens.exposure_key / max(scene, 0.02)
    # auto_exposure = 0: fixed at 1; = 1: full compensation; in between: interpolate in log so the ratio is even
    value = math.exp(math.log(ideal) * lens.auto_exposure)
    return min(max(value, lens.exposure_min), lens.exposure_max)
