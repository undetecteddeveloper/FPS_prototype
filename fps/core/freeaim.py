"""Gun not glued to the screen centre; bullets fly along the barrel (pure math, no ursina import).

- `FreeLook`: the MOUSE CONTROLS THE GUN FIRST. Inside the free zone only the gun turns; the screen stays still. Near the edge of the zone the screen starts turning gradually, and at the edge it turns fully. Head and body slowly
  turn to follow the gun (the gun keeps its world direction; only the picture catches up), so aim does not drift. Aiming / sprinting / reloading shrink the zone and the screen turns to compensate.
- `FreeAim`: the gun-pose part from recoil (a slow spring, so shots pile up and then settle by themselves); the rest pose changes after each turn / burst (it does not return to exactly one
  point); slow drift when standing still; hand tremor that follows the stress level (firing a lot shakes; it is clearly visible while reloading).
- `barrel_view_dir`: bullet direction in camera space, taken from the real gun pose now shown on screen. The gun is drawn by its own camera (its FOV differs from the world), so the direction
  is converted through the convergence point on screen: the bullet reaches exactly where the barrel axis points on screen (the lens is applied after compositing, so it does not shift this).

Pose = (x right, y up, z forward, pitch up, yaw right, roll right), metres and degrees, as everywhere else.
"""
import math
import random

from fps.core.movement import smoothstep
from fps.core.shake import smooth_noise
from fps.core.spring import Spring, impulse_gain
from fps.core.sway import apply_pose
from fps.weapon_data import FreeAimData

ZERO_POSE = (0.0,) * 6


def barrel_view_dir(pose: tuple, sights: tuple, view_fov: float, world_fov: float) -> tuple:
    """Bullet direction (x right, y up, z forward; unit vector) in the world camera frame. `pose` = the gun pose being drawn; only its rotation part has an effect;
    `sights` = (rear sight ring centre, front post top) at rest, which define the gun's aiming axis."""
    rear, front = sights
    axis = (front[0] - rear[0], front[1] - rear[1], front[2] - rear[2])
    x, y, z = apply_pose(axis, (0.0, 0.0, 0.0, pose[3], pose[4], pose[5]))
    if z <= 1e-6:                                # barrel points behind the camera: impossible in the game, kept for numerical safety
        return (0.0, 0.0, 1.0)
    k = math.tan(math.radians(view_fov) / 2.0)
    w = math.tan(math.radians(world_fov) / 2.0)
    sx, sy = x / z / k * w, y / z / k * w        # same point on screen, converted from the gun's lens to the world lens
    n = math.sqrt(sx * sx + sy * sy + 1.0)
    return (sx / n, sy / n, 1.0 / n)


def view_to_world(yaw_deg: float, pitch_deg: float, local: tuple) -> tuple:
    """Convert a direction from the camera frame to the world. Same convention as movement.aim_direction (positive pitch = looking down)."""
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    sy, cy, sp, cp = math.sin(yaw), math.cos(yaw), math.sin(pitch), math.cos(pitch)
    forward = (sy * cp, -sp, cy * cp)
    right = (cy, 0.0, -sy)
    up = (sy * sp, cp, cy * sp)
    x, y, z = local
    return tuple(right[i] * x + up[i] * y + forward[i] * z for i in range(3))


class FreeLook:
    """Split the mouse turn between the gun and the screen. `offset` = (yaw right, pitch up), degrees: how far the gun is off the screen centre (the hand's target);
    `shown` = where the gun is now; it follows `offset` through the hand spring. Any part of the mouse movement that does not go into `offset` turns the screen, so the total angle always matches the mouse: the gun's direction
    in the world = view direction + offset, exactly the total mouse turn."""

    def __init__(self, data: FreeAimData):
        self.d = data
        self.offset = [0.0, 0.0]
        self.spring = Spring(2, data.hand_omega, data.hand_zeta)     # error of `shown` relative to `offset`
        self.scale = 1.0                                             # current zone relative to the full zone (smooth shrink / grow)

    def reset(self):
        self.offset = [0.0, 0.0]
        self.spring.x = [0.0, 0.0]
        self.spring.v = [0.0, 0.0]

    @property
    def shown(self) -> tuple:
        return (self.offset[0] + self.spring.x[0], self.offset[1] + self.spring.x[1])

    def _axes(self) -> tuple:
        return max(self.d.zone_yaw * self.scale, 1e-6), max(self.d.zone_pitch * self.scale, 1e-6)

    def radius(self) -> float:
        """0 at the centre of the zone .. 1 at the edge."""
        a, b = self._axes()
        return math.hypot(self.offset[0] / a, self.offset[1] / b)

    def _clamp(self) -> tuple:
        """Push `offset` inside the ellipse; return the excess to the screen (the gun keeps its world direction)."""
        r = self.radius()
        if r <= 1.0:
            return 0.0, 0.0
        extra = (self.offset[0] * (1.0 - 1.0 / r), self.offset[1] * (1.0 - 1.0 / r))
        self.offset[0] -= extra[0]
        self.offset[1] -= extra[1]
        return extra

    def apply(self, yaw: float, up: float) -> tuple:
        """Mouse just turned (yaw right, pitch up), degrees. Returns the part the screen must turn. Moving toward the edge: near the edge the screen takes over gradually; moving inward: only the gun moves (so fine centring is possible)."""
        d = self.d
        if not d.barrel_aim:
            return yaw, up
        cam = [0.0, 0.0]
        total = math.hypot(yaw, up)
        if total > 0.0:
            # split into smaller steps, so a large mouse flick within one frame passes through the soft zone the same as many small steps
            steps = max(1, min(16, math.ceil(total / 0.5)))
            sy, su = yaw / steps, up / steps
            for _ in range(steps):
                r = self.radius()
                outward = sy * self.offset[0] + su * self.offset[1] > 0.0
                t = (r - d.zone_soft) / max(1.0 - d.zone_soft, 1e-6) if outward else 0.0
                t = min(max(t, 0.0), 1.0)
                share = t * t * (3.0 - 2.0 * t)
                cam[0] += sy * share
                cam[1] += su * share
                self.offset[0] += sy * (1.0 - share)
                self.offset[1] += su * (1.0 - share)
                ex = self._clamp()
                cam[0] += ex[0]
                cam[1] += ex[1]
        return cam[0], cam[1]

    def step(self, dt: float, ads: float = 0.0, sprint: float = 0.0, reloading: bool = False, moving: bool = False) -> tuple:
        """Each frame. Returns the part the screen must turn, due to the zone shrinking and the head / body following the gun; that part is subtracted from `offset` so the gun keeps its world direction."""
        d = self.d
        if dt <= 0.0:
            return 0.0, 0.0
        target = 0.0 if not d.barrel_aim else 1.0
        target *= 1.0 + (d.zone_ads - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))
        target *= 1.0 + (d.zone_sprint - 1.0) * smoothstep(min(max(sprint, 0.0), 1.0))
        if reloading:
            target *= d.zone_reload
        k = 1.0 - math.exp(-dt / d.zone_blend) if d.zone_blend > 0 else 1.0
        self.scale += (target - self.scale) * k
        if target == 0.0 and self.scale < 1e-3:
            self.scale = 0.0
        cam = list(self._clamp())
        rate = d.recenter_move if moving else d.recenter_idle
        back = 1.0 - math.exp(-dt * rate)
        for i in (0, 1):
            v = self.offset[i] * back
            self.offset[i] -= v
            cam[i] += v
        # hand spring follows `offset`: error = shown - offset. When `offset` changes, `shown` has not caught up yet
        sp = self.spring
        sp.omega, sp.zeta = d.hand_omega, d.hand_zeta
        sp.step(dt)
        return cam[0], cam[1]

    def track(self, before: tuple):
        """Call after every change of `offset` in the frame, with `before` = `offset` at the start of the frame: the difference is fed into the spring so the gun moves smoothly on screen."""
        self.spring.x[0] -= self.offset[0] - before[0]
        self.spring.x[1] -= self.offset[1] - before[1]

    def pose(self) -> tuple:
        """Pose added to the gun. The rotation about the eye already moves the gun along an arc; add a slight shift and tilt to mimic the hand."""
        d = self.d
        yaw, up = self.shown
        return (yaw * d.offset_shift, up * d.offset_shift, 0.0, up, yaw, yaw * d.offset_roll)


class FreeAim:
    def __init__(self, data: FreeAimData, seed: int = 41):
        self.d = data
        self.seed = seed
        self.rng = random.Random(seed)            # own RNG: does not change the bullet random sequence
        self.spring = Spring(2, data.drift_omega, data.drift_zeta)      # (pitch up, yaw right) drift from recoil, degrees
        self.t = 0.0
        self.stress = 0.0                         # 0..1
        self.rest = [0.0] * 6                     # current rest pose
        self.rest_target = [0.0] * 6
        self._turned = False                      # a fast turn is in progress: pick a new rest pose when it stops
        self._since_shot = 1e9
        self.rest_changes = 0                     # number of rest-pose changes (for tests)

    def on_shot(self, up: float, right: float):
        """Part of the recoil that makes the gun drift (degrees): peak deviation of ONE shot; continuous fire piles it up."""
        d = self.d
        gain = impulse_gain(d.drift_omega, d.drift_zeta)
        self.spring.omega, self.spring.zeta = d.drift_omega, d.drift_zeta
        self.spring.kick([up * gain, right * gain])
        self.stress = min(1.0, self.stress + d.stress_per_shot)
        self._since_shot = 0.0

    def _pick_rest(self):
        d, r = self.d, self.rng
        self.rest_target = [r.uniform(-d.rest_pos, d.rest_pos), r.uniform(-d.rest_pos, d.rest_pos), 0.0,
                            r.uniform(-d.rest_pitch, d.rest_pitch), r.uniform(-d.rest_yaw, d.rest_yaw), r.uniform(-d.rest_roll, d.rest_roll)]
        self.rest_changes += 1

    def update(self, dt: float, turn_rate: float = 0.0):
        """`turn_rate` = magnitude of the mouse turn speed (deg/s). After a fast turn, or once firing stops, the gun stops at a different pose than last time."""
        if dt <= 0.0:
            return
        d = self.d
        self.t += dt
        self.spring.omega, self.spring.zeta = d.drift_omega, d.drift_zeta
        self.spring.step(dt)
        self.stress = max(0.0, self.stress - d.stress_decay * dt)
        before = self._since_shot
        self._since_shot += dt
        if before <= 0.25 < self._since_shot:     # just stopped a burst
            self._pick_rest()
        if turn_rate > d.rest_turn_threshold:
            self._turned = True
        elif self._turned and turn_rate < d.rest_turn_threshold * 0.25:
            self._turned = False
            self._pick_rest()
        k = 1.0 - math.exp(-dt / d.rest_time) if d.rest_time > 0 else 1.0
        for i in range(6):
            self.rest[i] += (self.rest_target[i] - self.rest[i]) * k

    @property
    def drift(self) -> tuple:
        """(pitch up, yaw right) current drift from recoil, soft-clamped to `drift_max`."""
        m = self.d.drift_max
        return tuple(m * math.tanh(v / m) if m > 0 else 0.0 for v in self.spring.x)

    def pose(self, ads: float = 0.0, reloading: bool = False) -> tuple:
        """Pose added to the gun. `ads` 0 hip .. 1 fully aimed (raw progress): the rest pose and slow drift shrink; the recoil part stays."""
        d = self.d
        calm = 1.0 + (d.ads_scale - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))
        u = self.t * d.idle_freq
        pitch_up, yaw_right = self.drift
        px = self.rest[0] * calm
        py = self.rest[1] * calm
        pitch = pitch_up + calm * (self.rest[3] + d.idle_pitch * smooth_noise(self.seed, 0, u))
        yaw = yaw_right + calm * (self.rest[4] + d.idle_yaw * smooth_noise(self.seed, 1, u))
        roll = calm * (self.rest[5] + d.idle_roll * smooth_noise(self.seed, 2, u))
        shake = self.stress * (d.tremor_reload if reloading else 1.0)
        if shake > 0.0:
            v = self.t * d.tremor_freq
            pitch += shake * d.tremor_angle * smooth_noise(self.seed, 3, v)
            yaw += shake * d.tremor_angle * smooth_noise(self.seed, 4, v)
            roll += shake * d.tremor_angle * smooth_noise(self.seed, 5, v)
            px += shake * d.tremor_pos * smooth_noise(self.seed, 6, v)
            py += shake * d.tremor_pos * smooth_noise(self.seed, 7, v)
        return (px, py, 0.0, pitch, yaw, roll)
