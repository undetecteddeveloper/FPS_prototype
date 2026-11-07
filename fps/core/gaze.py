"""Where the head camera looks while reloading (pure math, no ursina import).

A person reloading does not tilt the head down on a fixed curve: the gaze moves between the things the hands work on (the old magazine leaving, the new one
coming up, the magazine well, the slide) and rests on each for a while. `ReloadGaze` models that as a chain of HEAD glances (slow: a head moves 3-4x slower than an eye):
  - a glance moves from the current gaze to a new fixation point along a cubic-bezier curve (core/easing.py, like CSS cubic-bezier): `gaze_enter_ease` for the first dip,
    `gaze_glance_ease` between points (small settle overshoot), `gaze_leave_ease` for the look back up; its duration grows with its amplitude (`gaze_time` + `gaze_time_per_deg` x degrees);
  - between saccades the gaze HOLDS: it creeps slowly toward the moving target (`gaze_pursuit`, eyes following the hand) and drifts a little;
  - a new saccade starts once the target has moved more than `gaze_threshold` degrees away from the fixation AND the gaze has rested at least a random
    dwell time (`gaze_dwell_min` .. `gaze_dwell_max`);
  - every reload draws its own depth, side offset and durations (+- `gaze_jitter`), so two reloads never trace the same path.
The target comes from the viewmodel (the point between the left hand and the gun, see Viewmodel.gaze_point); without one, the gaze dips to (-glance_pitch, glance_yaw).
Angles are (pitch up, yaw right) in degrees relative to the straight-ahead view; negative pitch = looking down.
"""
import math
import random

from fps.core.easing import bezier

SUBSTEP = 1.0 / 240.0          # s: the gaze is integrated in steps no longer than this, so 30 and 240 FPS trace the same path
DEPTH_JITTER = 0.6             # the per-reload depth varies by this share of gaze_jitter (the tempo by the full gaze_jitter)

from fps.core.shake import smooth_noise
from fps.weapon_data import HeadCamData


def min_jerk(u: float) -> float:
    """Minimum-jerk position profile 0 -> 1 for u in [0, 1]: zero speed and acceleration at both ends (10u^3 - 15u^4 + 6u^5)."""
    u = min(max(u, 0.0), 1.0)
    return u * u * u * (10.0 + u * (-15.0 + 6.0 * u))


def _soft(x: float, knee: float, limit: float) -> float:
    """x >= 0 unchanged up to `knee`, then compressed smoothly (tanh) so it approaches `limit` but never passes it."""
    if x <= knee or limit <= knee:
        return min(x, limit) if limit > 0 else 0.0
    span = limit - knee
    return knee + span * math.tanh((x - knee) / span)


class ReloadGaze:
    def __init__(self, data: HeadCamData, seed: int = 0):
        self.d = data
        self.rng = random.Random(seed)
        self.seed = seed
        self.t = 0.0
        self.pitch = self.yaw = 0.0           # current gaze (degrees)
        self._from = (0.0, 0.0)
        self._goal = (0.0, 0.0)
        self._move_t = 0.0
        self._move_T = 0.0                    # 0 = not moving (holding)
        self._hold = 0.0                      # seconds resting on the current fixation
        self._dwell = 0.0                     # how long this rest must last before the next saccade
        self._active = False
        self._depth = 1.0                     # per-reload scale of the dip
        self._side = 0.0                      # per-reload side offset (deg)
        self._speed = 1.0                     # per-reload duration scale
        self.saccades = 0                     # number of saccades started (for tests)
        self._curve = bezier(data.gaze_glance_ease)

    @property
    def moving(self) -> bool:
        return self._move_T > 0.0

    def _jitter(self) -> float:
        return self.rng.uniform(-1.0, 1.0) * self.d.gaze_jitter

    def _aim(self, target) -> tuple:
        d = self.d
        if target is None:
            pitch, yaw = -d.glance_pitch, d.glance_yaw
        else:
            pitch, yaw = target
        pitch = pitch * self._depth
        yaw = yaw + self._side
        # soft limits (tanh): a hand far below still reads as 'further down' than the gun, instead of every target pinning at the limit
        pitch = -_soft(-pitch, d.glance_pitch, d.glance_pitch * 1.25) if pitch < 0.0 else min(pitch, 2.0)
        yaw = math.copysign(_soft(abs(yaw), 0.6 * d.gaze_max_yaw, d.gaze_max_yaw), yaw)
        return pitch, yaw

    def _saccade(self, goal: tuple, duration: float = None, overshoot: bool = True, ease: tuple = None):
        d = self.d
        self._curve = bezier(ease if ease is not None else d.gaze_glance_ease)
        err = (goal[0] - self.pitch, goal[1] - self.yaw)
        amp = math.hypot(*err)
        over = d.gaze_overshoot * self.rng.uniform(0.3, 1.0) if overshoot else 0.0
        self._from = (self.pitch, self.yaw)
        self._goal = (goal[0] + err[0] * over, goal[1] + err[1] * over)
        if duration is None:
            duration = (d.gaze_time + d.gaze_time_per_deg * amp) * self._speed
        self._move_T = max(duration, 1e-3)
        self._move_t = 0.0
        self._hold = 0.0
        self._dwell = self.rng.uniform(d.gaze_dwell_min, max(d.gaze_dwell_min, d.gaze_dwell_max))
        self.saccades += 1

    def update(self, dt: float, active: bool, target: tuple = None, enter_time: float = None, leave_time: float = None, since: float = 0.0) -> tuple:
        """Advance by dt. `active` = the reload glance window is open; `target` = (pitch, yaw) of the point to look at, or None.
        `enter_time` / `leave_time`: duration of the first dip / of the look back up (None = by amplitude).
        `since`: when `active` just changed, how many seconds before the END of this frame it really changed (so the move starts on time at any FPS).
        Returns (pitch, yaw) in degrees, drift included."""
        d = self.d
        if dt <= 0.0:
            return self.pitch, self.yaw
        self.t += dt
        lead = dt - min(max(since, 0.0), dt)                  # part of this frame that passed BEFORE the change
        if active and not self._active:                       # a new reload: its own depth / side / tempo, then the first dip
            self._depth = 1.0 + self._jitter() * DEPTH_JITTER
            self._side = self.rng.uniform(-1.0, 1.0) * d.gaze_jitter * 8.0
            self._speed = 1.0 + self._jitter()
            self._active = True
            self._saccade(self._aim(target), enter_time, overshoot=False, ease=d.gaze_enter_ease)
            self._move_t = -lead
        elif not active and self._active:                     # finished or cancelled: one look straight back up, landing exactly on 0
            self._active = False
            self._saccade((0.0, 0.0), leave_time, overshoot=False, ease=d.gaze_leave_ease)
            self._move_t = -lead
        aim = self._aim(target) if self._active else (0.0, 0.0)
        n = max(1, math.ceil(dt / SUBSTEP - 1e-9))
        for _ in range(n):
            self._step(dt / n, aim)

        return self._output()

    def _step(self, h: float, aim: tuple):
        d = self.d
        if self.moving:
            self._move_t += h
            u = self._move_t / self._move_T
            k = self._curve(u)
            self.pitch = self._from[0] + (self._goal[0] - self._from[0]) * k
            self.yaw = self._from[1] + (self._goal[1] - self._from[1]) * k
            if u >= 1.0:
                self._move_T = 0.0
            return
        self._hold += h
        if self._active and self._hold >= self._dwell and math.hypot(aim[0] - self.pitch, aim[1] - self.yaw) > d.gaze_threshold:
            self._saccade(aim)
            return
        # rest: creep toward the (moving) target, eyes following the hand; back at rest (not reloading) it settles quickly on exactly 0
        rate = d.gaze_pursuit if self._active else 12.0
        k = 1.0 - math.exp(-rate * h)
        self.pitch += (aim[0] - self.pitch) * k
        self.yaw += (aim[1] - self.yaw) * k
        if not self._active and abs(self.pitch) < 1e-4 and abs(self.yaw) < 1e-4:
            self.pitch = self.yaw = 0.0

    def engaged(self) -> float:
        """0 (straight ahead) .. 1 (fully down at this reload's dip depth)."""
        full = -self._aim(None)[0]                      # this reload's normal dip (depth jitter and soft limit included)
        return min(max(-self.pitch / max(full, 1e-3), 0.0), 1.0)

    def _output(self) -> tuple:
        d = self.d
        engaged = self.engaged()
        v = self.t * d.glance_drift_freq
        return (self.pitch + engaged * d.glance_drift * smooth_noise(d.seed, 70, v),
                self.yaw + engaged * d.glance_drift * smooth_noise(d.seed, 71, v))
