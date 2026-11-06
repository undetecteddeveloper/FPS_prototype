"""Pure math for shot effects (no ursina import, so it can be tested without a window): muzzle flash and tracer.

A tracer is a bright streak `length` long that trails the real bullet's head. Since the bullet starts at the EYE, the streak must appear to leave the MUZZLE,
so the streak carries an offset `offset` (muzzle - eye) at firing; this offset fades with the distance travelled (`convergence`):
the streak head always lies on the real bullet path once it is far away, while right after firing it sits at the muzzle.
"""
import math

from fps.core.movement import smoothstep


def flash_envelope(age: float, life: float) -> float:
    """Flash intensity 1 -> 0 by age (s): bright right at the shot, fades fast toward the end."""
    if life <= 0 or age < 0 or age >= life:
        return 0.0
    return (1.0 - age / life) ** 1.5


def convergence(distance: float, blend_distance: float) -> float:
    """1 at the muzzle (0 m travelled) -> 0 once `blend_distance` m are travelled: the remaining eye-muzzle offset of the tracer streak."""
    if blend_distance <= 0:
        return 0.0
    return 1.0 - smoothstep(distance / blend_distance)


def is_traced(shot_number: int, every: int) -> bool:
    """Shot number `shot_number` (counted from 1) gets a tracer or not: the first shot, then once every `every` shots."""
    return every > 0 and (shot_number - 1) % every == 0


def ribbon_width(distance: float, base_width: float, min_pixels: float, fov_deg: float, screen_width_px: float) -> float:
    """Width (m) of the streak at `distance` m: not thinner than `min_pixels` screen pixels, since below 1 pixel the streak flickers."""
    one_pixel = distance * math.radians(fov_deg) / screen_width_px
    return max(base_width, min_pixels * one_pixel)


def lens_ratio(world_fov_deg: float, view_fov_deg: float) -> float:
    """Multiplier for the horizontal/vertical offset of the muzzle (measured in the gun scene, with its own FOV), so the streak in the world (different FOV)
    sits at the same screen spot where the muzzle is."""
    return math.tan(math.radians(world_fov_deg) / 2) / math.tan(math.radians(view_fov_deg) / 2)


class Tracer:
    """State of one streak. Each frame: while the bullet flies, `follow`; when it hits or expires, `end` (once); then `advance`."""

    def __init__(self, offset: tuple, length: float, blend_distance: float, speed: float):
        self.offset = offset
        self.length = length
        self.blend = blend_distance
        self.speed = speed                     # m/s: the tail catches up with the head once the bullet has hit
        self.head = (0.0, 0.0, 0.0)
        self.direction = (0.0, 0.0, 1.0)
        self.head_s = 0.0                      # distance the head has travelled from the eye
        self.tail_s = 0.0
        self.ended = False
        self.done = False

    def follow(self, head: tuple, direction: tuple, travelled: float):
        self.head, self.direction, self.head_s = head, direction, travelled
        self.tail_s = max(0.0, travelled - self.length)

    def end(self, end_pos: tuple, direction: tuple, travelled: float):
        """Bullet is gone (hit or expired): the head stays at the end point; the tail runs up to it."""
        self.follow(end_pos, direction, travelled)
        self.ended = True

    def advance(self, dt: float):
        if self.ended:
            self.tail_s += self.speed * dt
            if self.tail_s >= self.head_s:
                self.done = True

    def endpoints(self) -> tuple:
        """(tail, head) in world coordinates, with the remaining eye-muzzle offset added at each end."""
        d = self.direction
        back = self.head_s - self.tail_s
        tail = [self.head[i] - d[i] * back + self.offset[i] * convergence(self.tail_s, self.blend) for i in range(3)]
        head = [self.head[i] + self.offset[i] * convergence(self.head_s, self.blend) for i in range(3)]
        return tuple(tail), tuple(head)
