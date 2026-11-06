"""Lamp light computed on the CPU (same formula as assets/shaders/light_common.glsl, without shadows) and the camera's automatic exposure.

Exposure is based on the brightness measured right where the camera stands and looks, not read back from the GPU (reading images is very slow on integrated graphics):
moving into a dark spot opens slowly; moving into a bright spot, or looking straight at a lamp, closes faster.
"""
import math

from fps.weapon_data import LensData, LookData


def _smoothstep(a: float, b: float, x: float) -> float:
    if a == b:
        return 1.0 if x >= b else 0.0
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def lamp_attenuation(look: LookData, d2: float, cos_down: float) -> float:
    """Illuminance of one lamp at a point sqrt(d2) metres away; `cos_down` = cos of the angle between the vertical and the lamp-to-point line.
    Same formula as `lamp_att` in light_common.glsl."""
    d = math.sqrt(d2)
    if d >= look.lamp_radius or cos_down <= 0.0:
        return 0.0
    x = d / look.lamp_radius
    win = 1.0 - x * x * x * x
    cone = look.lamp_side + (1.0 - look.lamp_side) * _smoothstep(math.cos(math.radians(look.lamp_cone_outer)),
                                                                 math.cos(math.radians(look.lamp_cone)), cos_down)
    return look.lamp_intensity * cone * win * win / (1.0 + d2 / (look.lamp_ref * look.lamp_ref))


def nearest_lamps(look: LookData, z: float) -> list:
    """Indices of the lamps that can light a point at coordinate z, nearest first."""
    reach = lamp_reach(look)
    kc = math.floor((z - look.lamp_z0) / look.lamp_spacing + 0.5)
    out = [kc + j for j in sorted(range(-reach, reach + 1), key=abs)]
    return [k for k in out if 0 <= k < look.lamp_count]


def lamp_reach(look: LookData) -> int:
    """Number of lamps to check on each side so that no lamp's light is cut off (each pixel costs 2 * reach + 1 lamps)."""
    return max(1, math.ceil((look.lamp_radius - look.lamp_spacing / 2.0) / look.lamp_spacing))


def light_at(look: LookData, pos: tuple, normal: tuple = (0.0, 1.0, 0.0)) -> float:
    """Total direct illuminance (not multiplied by lamp colour, no shadows) on a surface with normal `normal` at `pos`."""
    total = 0.0
    for k in nearest_lamps(look, pos[2]):
        lx, ly, lz = look.lamp_x - pos[0], look.lamp_y - pos[1], look.lamp_z0 + k * look.lamp_spacing - pos[2]
        d2 = lx * lx + ly * ly + lz * lz
        if d2 < 1e-6:
            continue
        d = math.sqrt(d2)
        ndl = (lx * normal[0] + ly * normal[1] + lz * normal[2]) / d
        if ndl > 0.0:
            total += lamp_attenuation(look, d2, ly / d) * ndl
    return total


def glare(look: LookData, pos: tuple, forward: tuple) -> float:
    """Near lamp in view: 0 (no lamp visible) .. ~1 (looking straight at a near lamp)."""
    total = 0.0
    for k in nearest_lamps(look, pos[2]):
        lx, ly, lz = look.lamp_x - pos[0], look.lamp_y - pos[1], look.lamp_z0 + k * look.lamp_spacing - pos[2]
        d2 = max(lx * lx + ly * ly + lz * lz, 1e-6)
        d = math.sqrt(d2)
        c = (lx * forward[0] + ly * forward[1] + lz * forward[2]) / d
        if c > 0.0:
            total += c ** 10 * 12.0 / (4.0 + d2)
    return min(total, 1.5)


def target_exposure(lens: LensData, look: LookData, pos: tuple, forward: tuple) -> float:
    """Exposure the camera wants at this spot. Measured over a sphere (average of the upward and the vertical faces) so it does not depend on the view direction, plus the lamp glare."""
    scene = 0.65 * light_at(look, pos) + 0.35 * light_at(look, pos, (forward[0], 0.0, forward[2]))
    scene += lens.lamp_glare * glare(look, pos, forward)
    ideal = lens.exposure_key / max(scene, 0.02)
    # auto_exposure = 0: fixed at 1; = 1: full compensation; in between: interpolate in log so the ratio is even
    value = math.exp(math.log(ideal) * lens.auto_exposure)
    return min(max(value, lens.exposure_min), lens.exposure_max)


class AutoExposure:
    def __init__(self, lens: LensData, look: LookData):
        self.lens, self.look = lens, look
        self.value = None

    def update(self, dt: float, pos: tuple, forward: tuple) -> float:
        target = target_exposure(self.lens, self.look, pos, forward)
        if self.value is None:
            self.value = target                                 # first frame: skip the slow fade-in from a meaningless value
        else:
            tau = self.lens.exposure_up_time if target > self.value else self.lens.exposure_down_time
            k = 1.0 - math.exp(-dt / tau) if tau > 0 else 1.0
            self.value = math.exp(math.log(self.value) + (math.log(target) - math.log(self.value)) * k)
        return self.value
