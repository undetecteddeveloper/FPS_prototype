"""Viewmodel gun sway on screen (pure math, no ursina import).

Includes: breathing while standing still, mouse lag, bob with footsteps, the sprint pose, inertia on vertical camera motion
(jump, crouch, fall) plus the landing bump, and the ADS pose that brings the sight to the centre of the screen.

Every pose is (x right, y up, z forward, pitch up, yaw right, roll right), metres and degrees, same convention as
`GunKick.pose`; `Viewmodel.update` adds them together and sets them on the `sway` node. Movement state is read from MoveState.
"""
import math
from dataclasses import dataclass

from fps.core.movement import MoveState, smoothstep
from fps.core.spring import Spring, impulse_gain
from fps.weapon_data import GunData, SwayData

ZERO_POSE = (0.0,) * 6
MOVING_ON_GROUND = (MoveState.WALK, MoveState.SPRINT, MoveState.CROUCH_WALK)


@dataclass
class SwayInput:
    """Snapshot of the player's motion for one frame."""
    state: MoveState
    speed: float                  # horizontal speed, m/s
    ads_amount: float             # 0 hip .. 1 fully aimed (linear progress; the smooth curve is applied here)
    sprint_amount: float          # 0 .. 1, similar
    look: tuple = (0.0, 0.0)      # (yaw right, pitch up) degrees the MOUSE turned during this frame
    eye_dy: float = 0.0           # camera moved up (+) / down (-) by this many metres in this frame
    landed: float = 0.0           # landing speed (m/s) if it landed this frame, otherwise 0
    jumped: float = 0.0           # launch speed (m/s) if it jumped this frame, otherwise 0 (head cam: impulse on launch)


# --- ADS pose ---
def apply_pose(point: tuple, pose: tuple) -> tuple:
    """Apply a pose to a point, in Panda's order (roll, then pitch, then heading), roll clockwise."""
    x, y, z = point
    tx, ty, tz, pitch_up, yaw_right, roll_right = pose
    r, p, h = math.radians(roll_right), math.radians(pitch_up), math.radians(yaw_right)
    x, y = x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r)
    y, z = y * math.cos(p) + z * math.sin(p), -y * math.sin(p) + z * math.cos(p)
    x, z = x * math.cos(h) + z * math.sin(h), -x * math.sin(h) + z * math.cos(h)
    return x + tx, y + ty, z + tz


def apply_chain(point: tuple, *poses: tuple) -> tuple:
    """Apply poses like nested nodes: the first is the innermost (the gun's own pose), the last the outermost (the aim pose that turns the whole gun about the eye).
    Each pose rotates about the origin (the eye) and then translates, so a translation of an inner pose is turned by the outer rotation too."""
    for pose in poses:
        point = apply_pose(point, pose)
    return point


def aim_translation_weight(ads_progress: float) -> float:
    """How much of the aim pose's SHIFT (hand offset, rest drift) is kept: all of it at the hip, none when fully aimed. A shift moves the rear and the front sight by the same distance,
    which seen from the eye pulls them apart (parallax); the rotation about the eye never does, so it is always kept."""
    return 1.0 - smoothstep(ads_progress)


def ads_pose(rear: tuple, front: tuple, eye_relief: float) -> tuple:
    """Pose that brings the sight line (rear ring centre -> front post top) onto the camera's view axis, with the rear ring `eye_relief` from the eye.
    Rotates about the eye so the sight line is parallel to the z axis, then translates so the rear ring lies on the axis."""
    dx, dy, dz = front[0] - rear[0], front[1] - rear[1], front[2] - rear[2]
    pitch_up = -math.degrees(math.atan2(dy, dz))                       # sight line tilted up -> pitch the barrel down
    dz1 = math.hypot(dy, dz)
    yaw_right = -math.degrees(math.atan2(dx, dz1))
    turned = apply_pose(rear, (0.0, 0.0, 0.0, pitch_up, yaw_right, 0.0))
    return (-turned[0], -turned[1], eye_relief - turned[2], pitch_up, yaw_right, 0.0)


def ads_target_for(gun: GunData) -> tuple:
    """ADS pose for a gun, computed from its two sight points measured on the model (no points -> no shift)."""
    if gun.ads_sights is None:
        return ZERO_POSE
    rear, front = ([c + h for c, h in zip(point, gun.hip_offset)] for point in gun.ads_sights)
    return ads_pose(tuple(rear), tuple(front), gun.ads_eye_relief)


def _add(total: list, pose, scale: float = 1.0):
    for i in range(6):
        total[i] += pose[i] * scale


class MouseLag:
    """The gun lags behind when the mouse turns (lag follows the angular VELOCITY). Pure math, exact solution for each dt.

    The gun tracks the view angle through a second-order system (frequency `lag_omega`, damping `lag_zeta`): g'' + 2ζω g' + ω² g = ω² x + r·2ζω x',
    x = view angle, g = gun angle, r = `lag_follow`. The screen sees the error e = g - x, so
        e'' + 2ζω e' + ω² e = -x'' - (1-r)·2ζω x'.
    each frame x' (= ve) is treated as constant: the gun's velocity is continuous (e' jumps by -Δve), and a constant force moves the equilibrium point to
    e_eq = -(1-r)·2ζ·ve/ω, then solved exactly like `Spring.step` (no Euler, stable at any FPS). The system is linear: when the mouse
    stops the gun catches up, overshoots (ζ<1), then wobbles back to where it was; the overshoot is set by `lag_zeta`.

    Non-linearity sits ONLY at the INPUT (the velocity after smoothing with `lag_smooth`, so a 1000 Hz mouse with quantised counts does not distort it):
      - soft dead zone `lag_deadzone`: slow turns while aiming precisely barely move the gun;
      - soft tanh compression toward `lag_max / lag_gain` (deg/s): very fast turns are not cut off flat (a hard clamp feels stiff) but approach the limit.
    Normalised: at a constant turn speed ve (linear region) the gun lags by `lag_gain * ve` degrees, independent of omega / zeta.
    """

    def __init__(self, data: SwayData):
        self.d = data
        self.v_smooth = [0.0, 0.0]           # smoothed turn velocity (deg/s): (yaw right, pitch up)
        self.v_in = [0.0, 0.0]               # velocity after the dead zone + soft compression
        self.spring = Spring(2, data.lag_omega, data.lag_zeta)     # x = e - e_eq (deg), v = e' (deg/s)
        self.e_eq = [0.0, 0.0]               # equilibrium point of e this frame; e = spring.x + e_eq

    def shape(self, v: float) -> float:
        """Raw turn velocity (deg/s) -> velocity fed to the spring: soft dead zone, then tanh compression."""
        d = self.d
        knee = v * abs(v) / (abs(v) + d.lag_deadzone) if d.lag_deadzone > 0 else v
        vmax = d.lag_max / d.lag_gain if d.lag_gain > 0 else 0.0
        return vmax * math.tanh(knee / vmax) if vmax > 0 else 0.0

    def update(self, dt: float, look: tuple) -> tuple:
        """`look` = (yaw right, pitch up) degrees the mouse turned this frame. Returns the DISPLAYED (yaw offset, pitch offset), degrees
        (negative = gun lags left / down)."""
        d = self.d
        if dt <= 0.0:
            return self.output()
        k = 1.0 - math.exp(-dt / d.lag_smooth) if d.lag_smooth > 0 else 1.0
        sp = self.spring
        sp.omega, sp.zeta = d.lag_omega, d.lag_zeta
        zeta = min(max(sp.zeta, 0.05), 0.999)
        for i in (0, 1):
            self.v_smooth[i] += (look[i] / dt - self.v_smooth[i]) * k
            ve = self.shape(self.v_smooth[i])
            sp.v[i] -= ve - self.v_in[i]                          # the gun's velocity stays continuous when the view velocity changes
            self.v_in[i] = ve
            eq = -(1.0 - d.lag_follow) * 2.0 * zeta * ve / sp.omega
            sp.x[i] += self.e_eq[i] - eq                           # sp.x = u = e - e_eq: change the equilibrium while e stays the same
            self.e_eq[i] = eq
        sp.step(dt)
        return self.output()

    def output(self) -> tuple:
        d = self.d
        norm = d.lag_gain * d.lag_omega / (2.0 * min(max(d.lag_zeta, 0.05), 0.999))
        e = [self.spring.x[i] + self.e_eq[i] for i in (0, 1)]
        return (e[0] * norm, e[1] * norm * d.lag_pitch_scale)


class Sway:
    def __init__(self, data: SwayData, ads_target: tuple = ZERO_POSE):
        self.d = data
        self.ads_target = ads_target
        self.clock = 0.0
        self.phase = 0.0                           # footstep phase (rad)
        self.bob_amount = 0.0                      # bob amplitude, sliding toward its target
        self.lag = MouseLag(data)                                 # (yaw right, pitch up)
        self.jolt = Spring(6, data.jolt_omega, data.jolt_zeta)    # vertical inertia + landing bump

    def update(self, dt: float, inp: SwayInput) -> tuple:
        d = self.d
        ads = smoothstep(inp.ads_amount)
        sprint = smoothstep(inp.sprint_amount) * (1.0 - ads)
        calm = 1.0 + (d.ads_multiplier - 1.0) * ads            # when aiming, breathing, lag, bob and inertia still get ads_multiplier (0.4)
        total = [0.0] * 6
        self.clock += dt

        _add(total, self._bob(dt, inp), calm)
        _add(total, self._breath(inp), calm)
        _add(total, self._lag(dt, inp), calm)
        _add(total, self._jolt(dt, inp), calm)
        _add(total, d.sprint_pose, sprint)
        _add(total, d.rest_pose, 1.0 - ads)
        _add(total, self.ads_target, ads)
        return tuple(total)

    def _breath(self, inp: SwayInput) -> tuple:
        """Lissajous 1:2: one cycle horizontally, two vertically. Shrinks as the bob (walking) takes over."""
        d = self.d
        w = 2.0 * math.pi * d.breath_freq * self.clock
        k = 1.0 - min(self.bob_amount, 1.0) * 0.8
        s1, s2 = math.sin(w), math.sin(2.0 * w + 0.6)
        return (d.breath_x * s1 * k, d.breath_y * s2 * k, 0.0, d.breath_pitch * s2 * k, d.breath_yaw * s1 * k, 0.0)

    def _lag(self, dt: float, inp: SwayInput) -> tuple:
        """Mouse turned right, the gun is left behind (and vice versa), plus a slight tilt and shift; see MouseLag."""
        d = self.d
        yaw, pitch = self.lag.update(dt, inp.look)
        return (yaw * d.lag_shift, pitch * d.lag_shift, 0.0, pitch, yaw, yaw * d.lag_roll)

    def _bob(self, dt: float, inp: SwayInput) -> tuple:
        d = self.d
        moving = inp.state in MOVING_ON_GROUND
        target = 0.0
        if moving:
            target = min(1.0, inp.speed / d.bob_min_speed)
            if inp.state is MoveState.SPRINT:
                target *= d.bob_sprint_multiplier
            elif inp.state is MoveState.CROUCH_WALK:
                target *= d.bob_crouch_multiplier
            rate = d.bob_sprint_rate if inp.state is MoveState.SPRINT else d.bob_rate
            self.phase = (self.phase + 2.0 * math.pi * inp.speed * dt * rate / d.bob_stride) % (2.0 * math.pi)
        self.bob_amount += (target - self.bob_amount) * (1.0 - math.exp(-dt * d.bob_blend))
        a, ph = self.bob_amount, self.phase
        return (a * d.bob_x * math.sin(ph), a * d.bob_y * math.sin(2.0 * ph), 0.0,
                a * d.bob_pitch * math.sin(2.0 * ph + 0.5), 0.0, a * d.bob_roll * math.sin(ph))

    def _jolt(self, dt: float, inp: SwayInput) -> tuple:
        """Camera moves up and the gun lags down (and vice versa); on landing the gun bumps further according to fall speed."""
        d = self.d
        self.jolt.omega, self.jolt.zeta = d.jolt_omega, d.jolt_zeta
        self.jolt.x[1] = max(-d.vlag_max, min(d.vlag_max, self.jolt.x[1] - inp.eye_dy * d.vlag_gain))
        if inp.landed > 0:
            gain = impulse_gain(d.jolt_omega, d.jolt_zeta) * inp.landed / d.land_reference_speed
            self.jolt.kick([p * gain for p in d.land_peak])
        self.jolt.step(dt)
        return tuple(self.jolt.x)
