"""Bullet spread (pure math, no ursina import).

Spread angle = half-angle of the cone around the view direction = state-based base + bloom accumulated shot by shot.
The base is read from the player's MoveState (the single source); `ads_amount` (0 hip .. 1 fully aimed) interpolates between the hip base and the aim base,
so a shot fired while entering ADS spreads at the current ADS level.
"""
import math

from fps.core.movement import MoveState
from fps.weapon_data import AccuracyData

MOVING = (MoveState.WALK, MoveState.CROUCH_WALK, MoveState.SPRINT)
CROUCHING = (MoveState.CROUCH_IDLE, MoveState.CROUCH_WALK)


class Accuracy:
    def __init__(self, data: AccuracyData):
        self.d = data
        self.bloom = 0.0
        self.since_shot = 1e9             # s since the last shot

    def hip_base(self, state: MoveState) -> float:
        d = self.d
        base = {MoveState.IDLE: d.stand, MoveState.WALK: d.walk, MoveState.SPRINT: d.sprint,
                MoveState.CROUCH_IDLE: d.stand, MoveState.CROUCH_WALK: d.walk, MoveState.AIR: d.air}[state]
        return base * d.crouch_multiplier if state in CROUCHING else base

    def ads_base(self, state: MoveState) -> float:
        d = self.d
        if state is MoveState.AIR:
            return d.air                  # jumping does not make aiming more accurate either
        base = d.ads_move if state in MOVING else d.ads
        return base * d.crouch_multiplier if state in CROUCHING else base

    def base(self, state: MoveState, ads_amount: float = 0.0) -> float:
        hip, ads = self.hip_base(state), self.ads_base(state)
        return hip + (ads - hip) * ads_amount

    def angle(self, state: MoveState, ads_amount: float = 0.0) -> float:
        """Current half-angle of the cone (degrees)."""
        d = self.d
        bloom_effect = 1.0 + (d.ads_bloom_multiplier - 1.0) * ads_amount
        return self.base(state, ads_amount) + self.bloom * bloom_effect

    def on_shot(self):
        self.bloom = min(self.bloom + self.d.bloom_per_shot, self.d.bloom_max)
        self.since_shot = 0.0

    def update(self, dt: float):
        d = self.d
        recovering = min(dt, max(0.0, self.since_shot + dt - d.bloom_recovery_delay))   # only the part of dt past the delay
        self.since_shot += dt
        self.bloom = max(0.0, self.bloom - d.bloom_recovery * recovering)


def random_in_cone(direction: tuple, half_angle_deg: float, rng) -> tuple:
    """Uniform random direction on a disc of radius `half_angle_deg` around `direction` (unit vector)."""
    if half_angle_deg <= 0:
        return direction
    dx, dy, dz = direction
    ux, uy, uz = (0.0, 1.0, 0.0) if abs(dy) < 0.9 else (1.0, 0.0, 0.0)
    rx, ry, rz = uy * dz - uz * dy, uz * dx - ux * dz, ux * dy - uy * dx      # right = up x d
    rn = math.sqrt(rx * rx + ry * ry + rz * rz)
    rx, ry, rz = rx / rn, ry / rn, rz / rn
    vx, vy, vz = dy * rz - dz * ry, dz * rx - dx * rz, dx * ry - dy * rx      # up' = d x right
    off = math.tan(math.radians(half_angle_deg) * math.sqrt(rng.random()))    # sqrt: uniform by disc area
    phi = 2.0 * math.pi * rng.random()
    c, s = math.cos(phi) * off, math.sin(phi) * off
    x, y, z = dx + rx * c + vx * s, dy + ry * c + vy * s, dz + rz * c + vz * s
    n = math.sqrt(x * x + y * y + z * z)
    return x / n, y / n, z / n


def angle_between(a: tuple, b: tuple) -> float:
    """Angle (degrees) between two vectors. Uses atan2(|cross product|, dot product), because acos loses precision at small angles:
    a float32 rounding of dot = 1 - 1e-8 gave an error of ~0.01 degrees."""
    cx, cy, cz = a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]
    return math.degrees(math.atan2(math.sqrt(cx * cx + cy * cy + cz * cz), a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))


def crosshair_gap(angle_deg: float, vfov_half_tan: float) -> float:
    """Distance from the screen centre to the inner edge of the crosshair tick (UI units: window height = 1), so the tick sits
    on the edge of the spread cone. vfov_half_tan = tan(half the vertical FOV) of the world camera."""
    return 0.5 * math.tan(math.radians(angle_deg)) / vfov_half_tan


def ring_radius(angle_deg: float, distance: float) -> float:
    """Radius (m) of the spread cone of half-angle `angle_deg`, cut by a plane perpendicular at `distance` m (for the illustration in the debug panel)."""
    return distance * math.tan(math.radians(min(angle_deg, 89.0)))


def shot_offset(view_dir: tuple, direction: tuple) -> tuple:
    """Offset (right, up), in degrees, of the bullet direction from the view direction: projects the bullet direction onto the viewer's right / up axes.
    Draws the bullet dot in the debug panel: its position on the cross-section at d metres = d * tan(offset)."""
    vx, vy, vz = view_dir
    if abs(vy) > 0.9999:                                   # looking straight up / down: pick the right axis arbitrarily
        rx, ry, rz = 1.0, 0.0, 0.0
    else:
        rx, ry, rz = vz, 0.0, -vx                          # right = up(0,1,0) x dir, normalised below
        n = math.hypot(rx, rz)
        rx, rz = rx / n, rz / n
    ux, uy, uz = ry * vz - rz * vy, rz * vx - rx * vz, rx * vy - ry * vx   # up = right x dir ... sign flipped so it points +y
    if uy < 0:
        ux, uy, uz = -ux, -uy, -uz
    dx, dy, dz = direction
    fwd = dx * vx + dy * vy + dz * vz
    return (math.degrees(math.atan2(dx * rx + dy * ry + dz * rz, fwd)),
            math.degrees(math.atan2(dx * ux + dy * uy + dz * uz, fwd)))
