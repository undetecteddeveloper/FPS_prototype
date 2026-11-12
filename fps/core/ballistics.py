"""Pure bullet math: flight with drop, segment collision with boxes and the ground. No ursina import.

Axes as in Ursina (y up). Each frame the bullet travels one segment; collision is tested over the WHOLE swept segment
(not just the end point), so a 500 m/s bullet (8 m per frame at 60 FPS) does not pass through a thin target.
"""
import math
from dataclasses import dataclass

GROUND = 'ground'   # owner of the ground collision


@dataclass(frozen=True)
class Hit:
    t: float          # 0..1: position along the segment p0 -> p1
    point: tuple
    normal: tuple
    owner: object     # object of the box that was hit, or GROUND


def advance(pos, vel, gravity, dt, drag: float = 0.0):
    """Advance dt seconds. Exact formula for constant gravity (and, with `drag` > 0, linear air drag: the velocity relaxes toward the terminal fall speed (0, -g / drag, 0)
    as exp(-drag t)), so it does not depend on FPS. drag = 0 is the plain ballistic arc."""
    x, y, z = pos
    vx, vy, vz = vel
    if drag > 1e-9:
        decay = math.exp(-drag * dt)
        along = (1.0 - decay) / drag                  # integral of exp(-drag t) over dt: how far the initial velocity carries
        vt = -gravity / drag                          # terminal vertical velocity
        return ((x + vx * along, y + vt * dt + (vy - vt) * along, z + vz * along),
                (vx * decay, vt + (vy - vt) * decay, vz * decay))
    return ((x + vx * dt, y + vy * dt - 0.5 * gravity * dt * dt, z + vz * dt),
            (vx, vy - gravity * dt, vz))


def drop_at_distance(distance, speed, gravity):
    """Drop (m) after flying `distance` metres horizontally at horizontal speed `speed`."""
    t = distance / speed
    return 0.5 * gravity * t * t


def segment_vs_aabb(p0, p1, lo, hi):
    """First entry point of segment p0 -> p1 into box [lo, hi]: (t, normal) or None.
    A start point inside the box counts as no hit (the bullet is already inside; the hit was computed earlier)."""
    tmin, tmax = 0.0, 1.0
    normal = None
    for axis in range(3):
        d = p1[axis] - p0[axis]
        if abs(d) < 1e-12:
            if p0[axis] < lo[axis] or p0[axis] > hi[axis]:
                return None
            continue
        t1 = (lo[axis] - p0[axis]) / d
        t2 = (hi[axis] - p0[axis]) / d
        sign = -1.0 if d > 0 else 1.0       # entering through the 'lo' face when d > 0: the normal points against the axis
        if t1 > t2:
            t1, t2 = t2, t1
        if t1 >= tmin:
            tmin = t1
            normal = tuple(sign if i == axis else 0.0 for i in range(3))
        tmax = min(tmax, t2)
        if tmin > tmax:
            return None
    if normal is None:
        return None
    return tmin, normal


def segment_vs_moving_aabb(p0, p1, lo, hi, displacement):
    """Like `segment_vs_aabb`, but the box [lo, hi] (position at the START of the segment) moves uniformly by `displacement` while the bullet travels p0 -> p1.
    Exact (no approximation): in the box frame the bullet goes from p0 to p1 - displacement, with the same parameter t; both reach that point at the same moment.
    The real hit point (world coordinates) is still the interpolation p0 -> p1 at t."""
    rel_end = (p1[0] - displacement[0], p1[1] - displacement[1], p1[2] - displacement[2])
    return segment_vs_aabb(p0, rel_end, lo, hi)


def segment_vs_ground(p0, p1, ground_y=0.0):
    """Segment going from above the ground to at or below it: t, or None."""
    if p0[1] > ground_y >= p1[1]:
        return (p0[1] - ground_y) / (p0[1] - p1[1])
    return None


class BoxGroup:
    """Several boxes grouped under one bounding box (e.g. a row of columns along a wall): `first_hit` tests each sub-box only when the segment touches
    the bounding box, so dozens of columns do not slow every step of every bullet. Pass as a list of boxes made with `group.entry()`."""

    def __init__(self, boxes):
        self.boxes = list(boxes)                       # [(lo, hi, owner)]
        self.lo = tuple(min(b[0][i] for b in self.boxes) for i in range(3))
        self.hi = tuple(max(b[1][i] for b in self.boxes) for i in range(3))

    def entry(self) -> tuple:
        return self.lo, self.hi, self


def segment_touches_aabb(p0, p1, lo, hi):
    """Whether any point of segment p0 -> p1 lies inside the box (including when it starts inside)."""
    tmin, tmax = 0.0, 1.0
    for axis in range(3):
        d = p1[axis] - p0[axis]
        if abs(d) < 1e-12:
            if p0[axis] < lo[axis] or p0[axis] > hi[axis]:
                return False
            continue
        t1 = (lo[axis] - p0[axis]) / d
        t2 = (hi[axis] - p0[axis]) / d
        if t1 > t2:
            t1, t2 = t2, t1
        tmin, tmax = max(tmin, t1), min(tmax, t2)
        if tmin > tmax:
            return False
    return True


def first_hit(p0, p1, boxes, ground_y=0.0):
    """Earliest collision of segment p0 -> p1 with the list of boxes [(lo, hi, owner)] and the ground; or None.
    owner being a `BoxGroup` means (lo, hi) is the group's bounding box; sub-boxes are tested only when the segment touches the bounding box."""
    best = None
    for lo, hi, owner in boxes:
        if isinstance(owner, BoxGroup):
            if segment_touches_aabb(p0, p1, lo, hi):
                h = first_hit(p0, p1, owner.boxes, ground_y=None)
                if h and (best is None or h.t < best.t):
                    best = h
            continue
        r = segment_vs_aabb(p0, p1, lo, hi)
        if r and (best is None or r[0] < best.t):
            best = Hit(r[0], _lerp(p0, p1, r[0]), r[1], owner)
    if ground_y is not None:
        t = segment_vs_ground(p0, p1, ground_y)
        if t is not None and (best is None or t < best.t):
            best = Hit(t, _lerp(p0, p1, t), (0.0, 1.0, 0.0), GROUND)
    return best


def moving_hit(p0, p1, lo, hi, displacement, owner):
    """`Hit` with a moving box (see `segment_vs_moving_aabb`), or None. `point` is where the bullet is when it hits."""
    r = segment_vs_moving_aabb(p0, p1, lo, hi, displacement)
    return Hit(r[0], _lerp(p0, p1, r[0]), r[1], owner) if r else None


def distance_between(a, b):
    return math.dist(a, b)


def hole_size(distance, base, per_meter):
    """Bullet hole size drawn (m): a real hole is too small to see from afar, so it grows with distance."""
    return base + per_meter * distance


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def decal_rotation(normal):
    """Rotation (rx, ry, rz) in degrees for Ursina so that a `quad` (front face looking toward -z) turns its face out along the normal
    parallel to the axis. A horizontal plane rotates about x; a vertical plane rotates about y."""
    nx, ny, nz = normal
    if ny > 0.5:
        return (90.0, 0.0, 0.0)
    if ny < -0.5:
        return (-90.0, 0.0, 0.0)
    if nz < -0.5:
        return (0.0, 0.0, 0.0)
    if nz > 0.5:
        return (0.0, 180.0, 0.0)
    if nx < -0.5:
        return (0.0, 90.0, 0.0)
    return (0.0, -90.0, 0.0)
