"""Head camera: head and body motion projected onto the image (pure math, no ursina import).

IMAGE ONLY, like Shake: the result is a pose applied to the world camera; it does not touch `player.yaw/pitch`, `aim_ray()` or the bullet direction.
Pose = (x right, y up, z forward, pitch up, yaw right, roll right), metres and degrees. Two parts:

1. Motion of the person (multiplied by `ads_multiplier` when aiming; the gun follows with `gun_follow`, sign flipped):
   - body: tilts with turns and sideways movement, dips when moving forward (`body_*` spring, so the body lags);
   - footsteps: IN PHASE with `Sway.phase` (the step sound plays when the phase passes 3 pi / 4, the bottom of the bob). The bob uses a 'landing' wave
     (`footfall`): sharp trough like a stamp, round crest; `step_sharp` sets the sharpness. Walking and sprinting have separate amplitude sets, blended by
     `sprint_mix` (glides in and out of sprint); sprinting adds a forward lean `sprint_lean`. Bodycam-style: walking bobs ~2 cm and tilts ~1 degree;
     sprinting rolls left and right ~2.6 degrees with the footfall rhythm;
   - hand tremor: smooth high-frequency noise (two octaves of `smooth_noise`), rising with speed, strongest while sprinting. The noise clock
     integrates the frequency (phase), so switching walk <-> sprint does not make the noise jump;
   - jumping / falling / landing: separate `jolt_*` spring (fast; it bounces because zeta < 0.5). Jump start: an upward kick + lift; in the air: slow sway;
     landing: pushed down by fall speed (pitch down + y down + random roll), then bounces back once. The old landing nod lived
     in the body spring (omega 7, as slow as a nod), so it never produced a real jolt;
   - slow drift and breathing while standing still.
2. Gaze while reloading (`glance_*` + `gaze_*`, does NOT multiply aim; core/gaze.py): the glance window opens `glance_in_delay` after the reload starts and closes
   `glance_out_lead` seconds BEFORE `Clip.settle` (as the Viewmodel's reload view fades out). Inside it the gaze jumps (saccades: minimum-jerk, slight overshoot) between the
   points the hands work on (`gaze_target`, from Viewmodel.gaze_point) and rests on each; the first dip takes ~`glance_in_time`, the look back up `glance_out_time`
   (`glance_cancel_time` when the reload is cancelled). Small nod when the magazine seats. The mouse still turns normally during the glance.
   Gun: the hand holds the gun against the body, so when the head tilts down the gun barely moves in the world; on screen the gun rises toward the centre of the frame:
   the glance uses `glance_follow` (~1, pivoting about the eye like the camera) instead of the `gun_follow` 0.55 of normal motion.
"""
import math
from dataclasses import dataclass

from fps.core.gaze import ReloadGaze
from fps.core.movement import MoveState, smoothstep
from fps.core.shake import smooth_noise
from fps.core.spring import Spring, impulse_gain
from fps.core.sway import MOVING_ON_GROUND, SwayInput
from fps.weapon_data import Clip, HeadCamData, is_reload_key

ZERO = (0.0,) * 6


@dataclass(frozen=True)
class ReloadState:
    """Snapshot of the running reload clip for one frame: `t` = seconds OF THE CLIP (Handling.t, already multiplied by speed), `speed` = ReloadData.speed."""
    clip: Clip
    t: float
    speed: float = 1.0
    first: bool = True          # tube guns chain one-round cycles: the glance opens only in the FIRST cycle and closes only in the LAST (a magazine gun is always both)
    last: bool = True

    def real(self, clip_seconds: float) -> float:
        return clip_seconds / max(self.speed, 1e-3)

    @property
    def elapsed(self) -> float:
        """Real seconds since reloading began."""
        return self.real(self.t)

    @property
    def settle_time(self) -> float:
        """Real seconds until the gun, magazine and bolt are in place (Clip.settle; if missing, the end of the clip)."""
        c = self.clip
        return self.real(((c.settle if c.settle is not None else c.end) - c.start) / 30.0)

    @property
    def swap_time(self):
        return None if self.clip.swap_time is None else self.real(self.clip.swap_time)

    @property
    def swap_times(self) -> tuple:
        """Real seconds of every moment a round goes in (one for a magazine, several for the M1014's long empty reload)."""
        return tuple(self.real(t) for t in self.clip.swap_times)

    @property
    def end_time(self) -> float:
        return self.real(self.clip.duration)


def reload_state(handling) -> ReloadState:
    """Read `core.handling.Handling`: ReloadState while reloading (draw does not count), otherwise None."""
    if handling is None or not is_reload_key(handling.key):
        return None
    return ReloadState(handling.clip, handling.t, handling.speed, getattr(handling, 'first', True), getattr(handling, 'last', True))


def glance_weight(d: HeadCamData, rs: ReloadState) -> float:
    """0..1 amount of glancing down at the gun, by reload progress (pure function of the clip time)."""
    t = rs.elapsed
    if not rs.first:
        w_in = 1.0                                          # a later cycle of a tube-gun chain: the head is already down
    else:
        w_in = smoothstep((t - d.glance_in_delay) / d.glance_in_time) if d.glance_in_time > 0 else float(t >= d.glance_in_delay)
    back = rs.settle_time - d.glance_out_lead
    if not rs.last:
        w_out = 1.0                                         # and stays down until the last cycle
    else:
        w_out = 1.0 - smoothstep((t - back) / d.glance_out_time) if d.glance_out_time > 0 else float(t < back)
    return max(0.0, min(w_in, w_out))


def footfall(phase: float, sharp: float) -> float:
    """Footstep wave: two steps per phase cycle, TROUGH = -1 exactly when the foot plants (phases 3 pi / 4 and 7 pi / 4, as the gun bob),
    mean 0. `sharp` 0 = sine (same as sin 2 phase), 1 = |sin| (sharp trough like a stamp, round and lower crest)."""
    n = 2.0 - min(max(sharp, 0.0), 1.0)
    c = abs(math.sin(phase - 0.75 * math.pi))
    mean = math.gamma((n + 1.0) / 2.0) / (math.sqrt(math.pi) * math.gamma(n / 2.0 + 1.0))     # mean of |sin|^n
    return (c ** n - mean) / mean


def _lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


class HeadCam:
    def __init__(self, data: HeadCamData):
        self.d = data
        self.t = 0.0
        self.body = Spring(3, data.body_omega, data.body_zeta)     # (roll, pitch, yaw lagging): the body lags, does not jump with the mouse
        self.jolt = Spring(6, data.jolt_omega, data.jolt_zeta)     # impulse for jump / landing / nod when the magazine seats; all 6 pose components
        self.step_amount = 0.0           # 0..1 footstep amplitude (by speed; smaller when crouching)
        self.sprint_mix = 0.0            # 0 walk .. 1 sprint (blend of the amplitude sets)
        self.jitter_amount = 0.0         # 0..1 rung tay
        self.air = 0.0                   # 0..1 airborne
        self.phase = 0.0
        self.glance = 0.0                # 0..1 reload glance amount
        self._jit_u = 0.0                # phase of the hand-tremor noise (integrated frequency)
        self._events = 0                 # event counter, to get a deterministic random number
        self._reloading = False
        self._release_from = 0.0
        self._release_t = 1e9
        self._last_elapsed = -1.0
        self._pose = ZERO
        self._glance_pose = ZERO
        self._ads = 0.0
        self.gaze = ReloadGaze(data, data.seed)
        self._window = False

    def _random(self) -> float:
        """Value in [-1, 1], deterministic from the seed (noise at integer points = cell value)."""
        self._events += 1
        return smooth_noise(self.d.seed, 60, float(self._events))

    def update(self, dt: float, inp: SwayInput, phase: float, lateral: float = 0.0, forward: float = 0.0, reload: ReloadState = None, gaze_target: tuple = None):
        """`phase` = Sway.phase (footstep phase); `lateral` / `forward` = velocity in the player's frame (m/s, right / forward);
        `reload` = reload_state(combat.handling) for this frame (None when not reloading); `gaze_target` = (pitch, yaw) degrees of the point the hands work on, or None."""
        if dt <= 0.0:
            return
        d = self.d
        self.t += dt
        self.phase = phase
        self._ads = smoothstep(min(max(inp.ads_amount, 0.0), 1.0))

        # --- body: tilts with turns / sideways movement, dips when moving forward ---
        turn = inp.look[0] / dt                                     # deg/s, positive = turning right
        roll_target = max(-d.turn_roll_max, min(d.turn_roll_max, turn * d.turn_roll)) + lateral * d.strafe_roll
        pitch_target = -forward * d.move_pitch                      # dip forward when moving forward
        yaw_target = -turn * d.turn_yaw_lag                         # the picture lags slightly behind a turn
        sp = self.body
        sp.omega, sp.zeta = d.body_omega, d.body_zeta
        targets = (roll_target, pitch_target, yaw_target)
        for i, target in enumerate(targets):                       # track the target through the spring: error around the target, step, feed back
            sp.x[i] -= target
        sp.step(dt)
        for i, target in enumerate(targets):
            sp.x[i] += target

        # --- jump / landing / nod on magazine seat: impulses into the fast spring ---
        jo = self.jolt
        jo.omega, jo.zeta = d.jolt_omega, d.jolt_zeta
        gain = impulse_gain(d.jolt_omega, d.jolt_zeta)
        if inp.jumped > 0:
            k = gain * min(inp.jumped / d.land_reference_speed, d.land_max)
            jo.kick([0.0, d.jump_y * k, 0.0, d.jump_pitch * k, 0.0, d.jump_roll * self._random() * k])
        if inp.landed > 0:
            k = gain * min(inp.landed / d.land_reference_speed, d.land_max)
            jo.kick([0.0, -d.land_y * k, 0.0, -d.land_pitch * k, 0.3 * d.land_roll * self._random() * k, d.land_roll * self._random() * k])
        self._update_glance(dt, reload, gain, gaze_target)
        jo.step(dt)

        # --- footsteps, hand tremor, airborne: smooth intensity changes (stopping abruptly does not jerk) ---
        moving = inp.state in MOVING_ON_GROUND
        sprinting = inp.state is MoveState.SPRINT
        speed_k = min(1.0, inp.speed / d.step_min_speed) if moving else 0.0
        crouch_k = d.step_crouch if inp.state is MoveState.CROUCH_WALK else 1.0
        blend = 1.0 - math.exp(-dt * d.step_blend)
        self.step_amount += (speed_k * crouch_k - self.step_amount) * blend
        self.sprint_mix += ((1.0 if sprinting else 0.0) - self.sprint_mix) * (1.0 - math.exp(-dt * d.sprint_blend))
        jit_target = speed_k * crouch_k * (1.0 if sprinting else d.jitter_walk)
        self.jitter_amount += (jit_target - self.jitter_amount) * blend
        self.air += ((1.0 if inp.state is MoveState.AIR else 0.0) - self.air) * (1.0 - math.exp(-dt * 6.0))
        self._jit_u += dt * _lerp(d.jitter_freq_walk, d.jitter_freq, self.sprint_mix)

        a, s, ph = self.step_amount, self.sprint_mix, phase
        fall = footfall(ph, d.step_sharp)
        nod = footfall(ph + 0.2, d.step_sharp)                      # nod slightly after the bob
        x = a * _lerp(d.step_x, d.sprint_x, s) * math.sin(ph)
        y = a * _lerp(d.step_y, d.sprint_y, s) * fall
        pitch = a * _lerp(d.step_pitch, d.sprint_pitch, s) * nod - a * s * d.sprint_lean
        yaw = a * _lerp(d.step_yaw, d.sprint_yaw, s) * math.cos(ph)
        roll = a * _lerp(d.step_roll, d.sprint_roll, s) * math.sin(ph)

        j, u, seed = self.jitter_amount, self._jit_u, d.seed

        def shiver(axis):
            return 0.7 * smooth_noise(seed, axis, u) + 0.3 * smooth_noise(seed, axis + 1, 2.7 * u + 17.0)
        x += j * d.jitter_pos * shiver(30)
        y += j * d.jitter_pos * shiver(32)
        pitch += j * d.jitter_angle * shiver(34)
        yaw += j * d.jitter_angle * 0.8 * shiver(36)
        roll += j * d.jitter_angle * 1.2 * shiver(38)

        if self.air > 1e-4:
            v = self.t * d.air_freq
            pitch += self.air * d.air_sway * smooth_noise(seed, 50, v)
            roll += self.air * d.air_sway * 1.4 * smooth_noise(seed, 51, v)

        # slow drift + breathing while standing still (shrinks as footsteps take over)
        idle = max(0.0, 1.0 - 0.7 * min(a, 1.0))
        v = self.t * d.idle_freq
        y += idle * d.idle_y * smooth_noise(seed, 0, v * 1.4)
        pitch += idle * d.idle_pitch * smooth_noise(seed, 1, v)
        yaw += idle * d.idle_yaw * smooth_noise(seed, 2, v)
        roll += idle * d.idle_roll * smooth_noise(seed, 3, v)

        jx = jo.x
        self._pose = (x + jx[0], y + jx[1], jx[2], pitch + sp.x[1] + jx[3], yaw + sp.x[2] + jx[4], roll + sp.x[0] + jx[5])

    def _update_glance(self, dt: float, rs: ReloadState, gain: float, target: tuple = None):
        d = self.d
        reloading = rs is not None
        if reloading and not self._reloading:
            self._last_elapsed = -1.0
        cancelled = self._reloading and not reloading and self._window          # reload ended while the gaze was still down: cancelled
        self._reloading = reloading
        open_at = d.glance_in_delay if (not reloading or rs.first) else -1e9           # (a later cycle of a tube-gun chain: the window is already open)
        close_at = ((rs.settle_time - d.glance_out_lead) if rs.last else 1e9) if reloading else 0.0
        window = reloading and open_at <= rs.elapsed < close_at
        since = 0.0
        if window and not self._window:
            since = rs.elapsed - open_at                                     # the window opened this long before the end of the frame
        elif reloading and not window and self._window:
            since = rs.elapsed - close_at
        self._window = window
        leave = d.glance_cancel_time if cancelled else d.glance_out_time
        pitch, yaw = self.gaze.update(dt, window, target, enter_time=d.glance_in_time, leave_time=leave, since=since)
        w = self.gaze.engaged()                                              # how far down the gaze is: drives the small eye shift + roll
        if reloading:
            now = rs.elapsed
            for swap in rs.swap_times:
                if self._last_elapsed < swap <= now:
                    self.jolt.kick([0.0, 0.0, 0.0, -d.glance_seat_nod * gain * max(w, 0.3), 0.0, 0.0])    # magazine seats / a shell goes in: small nod
            self._last_elapsed = now
        self.glance = w
        if w <= 0.0 and abs(pitch) < 1e-4 and abs(yaw) < 1e-4:
            self._glance_pose = ZERO
            return
        self._glance_pose = (0.0, d.glance_y * w, d.glance_z * w, pitch, yaw, d.glance_roll * w)

    def _scale(self) -> float:
        return 1.0 + (self.d.ads_multiplier - 1.0) * self._ads

    def move_pose(self) -> tuple:
        """Only the person's movement part (multiplied by aim), not the reload glance."""
        k = self._scale()
        return tuple(c * k for c in self._pose)

    def glance_pose(self) -> tuple:
        return self._glance_pose

    def camera_pose(self) -> tuple:
        return tuple(m + g for m, g in zip(self.move_pose(), self._glance_pose))

    def gun_pose(self) -> tuple:
        """A camera offset of +p moves the world -p on screen; the gun is attached to the body, so it follows part of that motion (sign flipped).
        The glance part follows `glance_follow` (~1: the gun stays still in the world, so on screen it rises to the centre of the frame)."""
        f, g = self.d.gun_follow, self.d.glance_follow
        return tuple(-m * f - q * g for m, q in zip(self.move_pose(), self._glance_pose))
