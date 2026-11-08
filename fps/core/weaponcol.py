"""Weapon collision, "High Ready" (G14; pure maths, tests/test_weaponcol.py): standing too close to a wall, the gun is raised to point at the ceiling, the more the closer the wall;
firing and aiming are locked while it is raised (reloading still works).

The probe: short rays from the eye along the VIEW direction (not the gun's: the raised gun would point away from the wall and the probe would let go of it, then lower it, and so on)
and two more a few degrees to each side. The nearest solid box gives `dist`; the gun's reach is the eye -> muzzle distance of the hip pose. A wall farther than `clear_ratio` x reach
leaves the gun alone; closer than `full_ratio` x reach the gun is fully raised; in between the raise grows linearly (the smooth curve is applied in Sway).
The raise amount is smoothed (in / out times) and gives a 'blocked' flag with a little hysteresis (so the trigger does not flicker at the threshold).
"""
import math

from fps.core.ballistics import first_hit
from fps.core.movement import aim_direction, step_toward


def reach_of(gun) -> float:
    """Eye -> muzzle distance of the gun at rest (hip pose: muzzle + hip_offset + the rest pose shift), metres."""
    m, h, r = gun.muzzle, gun.hip_offset, gun.sway.rest_pose
    return math.sqrt(sum((m[i] + h[i] + r[i]) ** 2 for i in range(3)))


def wall_target(dist: float, reach: float, clear_ratio: float, full_ratio: float) -> float:
    """0 when the nearest solid is `clear_ratio` x reach or farther, 1 at `full_ratio` x reach or closer, linear between."""
    clear, full = reach * clear_ratio, reach * full_ratio
    if dist >= clear:
        return 0.0
    if dist <= full or clear <= full:
        return 1.0
    return (clear - dist) / (clear - full)


def solids_in_range(boxes: list, origin: tuple, radius: float) -> list:
    """The boxes [(lo, hi, owner)] whose bounds come within `radius` of `origin` (cheap pre-filter before the ray casts); water is not a wall."""
    ox, oy, oz = origin
    out = []
    for b in boxes:
        lo, hi, owner = b
        if getattr(owner, 'is_water', False):
            continue
        if lo[0] - radius <= ox <= hi[0] + radius and lo[1] - radius <= oy <= hi[1] + radius and lo[2] - radius <= oz <= hi[2] + radius:
            out.append(b)
    return out


def probe_distance(origin: tuple, yaw: float, pitch: float, boxes: list, max_dist: float, side_angle: float = 18.0) -> float:
    """Distance (m) to the nearest solid along the view direction and `side_angle` degrees to each side; `max_dist` when nothing is in range."""
    near = solids_in_range(boxes, origin, max_dist)
    if not near:
        return max_dist
    best = max_dist
    for off in (0.0, -side_angle, side_angle):
        d = aim_direction(yaw + off, pitch)
        p1 = (origin[0] + d[0] * max_dist, origin[1] + d[1] * max_dist, origin[2] + d[2] * max_dist)
        hit = first_hit(origin, p1, near, ground_y=None)
        if hit is not None:
            best = min(best, hit.t * max_dist)
    return best


class WallReady:
    """The smoothed raise amount (0 gun down .. 1 fully raised) and the 'blocked' flag. `d` = WallData."""

    def __init__(self, data):
        self.d = data
        self.amount = 0.0
        self.target = 0.0
        self.distance = math.inf
        self.blocked = False

    def update(self, dt: float, dist: float, reach: float) -> float:
        d = self.d
        self.distance = dist
        self.target = wall_target(dist, reach, d.clear_ratio, d.full_ratio)
        time = d.in_time if self.target > self.amount else d.out_time
        self.amount = step_toward(self.amount, self.target, 1.0 / max(time, 1e-3), dt)
        if self.blocked:
            self.blocked = self.amount > d.block_at - d.block_hysteresis
        else:
            self.blocked = self.amount >= d.block_at
        return self.amount

    def reset(self):
        self.amount = self.target = 0.0
        self.distance = math.inf
        self.blocked = False
