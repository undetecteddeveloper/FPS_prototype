"""Camera shake: an IMAGE-ONLY shake layered on top of the recoil camera (pure math, no ursina import).

It does NOT change the bullet direction: the result is only a pose (x right, y up, z forward, pitch up, yaw right, roll right; metres and degrees)
that the game applies to the world camera (the camera's own child node, not `player.yaw/pitch`) and, sign-flipped, to the gun.

Three sources add together:
- FIRING, KICK PER SHOT (Bodycam-style; the user chose 'punchy kick per shot, twice as strong when sustained'): each shot is ONE impulse into the
  6-axis damped spring `fire_omega` / `fire_zeta` (exact solution of `core/spring.py`, peak deviation via `impulse_gain`).
  Peak deviation of a shot = random strength x (`fire_bias` + `fire_spread` x a signed random number per axis): pitch always up,
  yaw / roll signs random, z kicks back, x / y jitter slightly. Strength = 1 ± `strength_var` (exponent `strength_shape` < 1 pushes values to the extremes, so
  there are clearly strong shots and clearly weak ones). The spring dies out in ~0.1 s, so each shot stays distinct; the 0.08 s interval has not fully died, so long bursts pile up moderately.
  The old model (trauma^2.3 times smooth noise) left single shots at only ~6% amplitude and every shot looked alike: removed.
- FIRING, BURST HEAT (`heat` 0..1): each shot adds 1 / `heat_shots`; after more than `heat_hold` seconds without firing it cools at `heat_cool` /s (held
  while firing, because the 0.08 s interval < `heat_hold`; firing one shot at a time never gets hot). A shot's kick is multiplied by 1 + `heat_boost` x heat
  (read BEFORE the shot adds heat, so a lone shot is exactly 1x). Plus a base hand tremor = heat x `tremor_amp` x fast smooth noise `tremor_freq`.
  Whole 30-round magazine: peak ~2x a lone shot (pytest measures this). After firing stops: spring back to ~0 after ~0.3 s; tremor ends when heat reaches 0 (hold + 1 / cool ~0.45 s).
- RELOADING: short spring impulses at the clip's frame marks (magazine out, magazine seated, bolt released), not shaking through the whole clip. Its own spring `spring`.

The gun follows the world (sign-flipped, `gun_follow`) and LAGS by `gun_delay`: the gun's kick is a second spring that receives the same impulses late, by
`gun_delay` seconds (not by resampling history). All random numbers are hashed from (seed, axis, shot number), so they depend only on the order of
shots and on time: the same seed gives the same curve at any FPS; it does not share `combat.rng` (so the bullet random sequence does not change).
"""
import math
from collections import deque

from fps.core.movement import smoothstep
from fps.core.spring import Spring, impulse_gain
from fps.weapon_data import ShakeData

_MASK = (1 << 64) - 1
_EPS_X, _EPS_V = 1e-6, 1e-4      # springs below this level (metres / degrees) count as at rest and are set to exactly 0 (fully off, not hovering at 1e-9 forever)


def hash_unit(seed: int, axis: int, i: int) -> float:
    """Deterministic pseudo-random number in [-1, 1] from (seed, axis, cell index) (splitmix64)."""
    x = (i * 0x9E3779B97F4A7C15 + axis * 0xBF58476D1CE4E5B9 + seed * 0x94D049BB133111EB + 0x2545F4914F6CDD1D) & _MASK
    x ^= x >> 30
    x = (x * 0xBF58476D1CE4E5B9) & _MASK
    x ^= x >> 27
    x = (x * 0x94D049BB133111EB) & _MASK
    x ^= x >> 31
    return x / _MASK * 2.0 - 1.0


def smooth_noise(seed: int, axis: int, u: float) -> float:
    """Smooth 1D value noise (5th-order interpolation between two cell values), always in [-1, 1], continuous in the 1st and 2nd derivatives."""
    i = math.floor(u)
    f = u - i
    s = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)
    a, b = hash_unit(seed, axis, i), hash_unit(seed, axis, i + 1)
    return a + (b - a) * s


def signed_pow(u: float, shape: float) -> float:
    """Keeps the sign, magnitude |u|^shape: shape < 1 pushes numbers evenly spread in [-1, 1] out to the extremes (few near 0); shape > 1 bunches them toward the middle."""
    return math.copysign(abs(u) ** shape, u) if u else 0.0


_AX_STRENGTH = 10                # hash axis: shot strength
_AX_DIR = 20                     # 20..25: direction of each axis of the shot
_AX_TREMOR = 40                  # 40..45: hand tremor noise
_AX_BEAT = 99                    # sign of a reload mark


def _settle(spring: Spring):
    if all(abs(x) < _EPS_X for x in spring.x) and all(abs(v) < _EPS_V for v in spring.v):
        spring.x = [0.0] * len(spring.x)
        spring.v = [0.0] * len(spring.v)


def _moving(spring: Spring) -> bool:
    return any(x or v for x, v in zip(spring.x, spring.v))


class Shake:
    def __init__(self, data: ShakeData, seed: int = None):
        self.d = data
        self.seed = data.seed if seed is None else seed
        self.enabled = True
        self.t = 0.0                         # clock of the shake layer (seconds), advances by the real dt
        self.heat = 0.0                      # burst heat, 0..1
        self.since_shot = 1e9                # seconds since the last shot (for heat_hold)
        self.shot_count = 0                  # shot number: the hash index for random numbers
        self.spring = Spring(6, data.beat_omega, data.beat_zeta)     # RELOAD impulses (name kept as `spring`: selftests set spring.x directly)
        self.fire = Spring(6, data.fire_omega, data.fire_zeta)       # per-shot kick of the camera
        self.gun_fire = Spring(6, data.fire_omega, data.fire_zeta)   # the same impulses, delayed by gun_delay, for the gun
        self._gun_kicks = []                 # (due clock, impulse) waiting to be fed into gun_fire
        self.shot_log = deque(maxlen=64)     # (clock, strength, heat factor, peak deviation of the 6 axes) of shots fired, for tests
        self.beat_log = deque(maxlen=64)     # (clock, mark type) of reload impulses that fired, for tests
        self.beat_count = 0
        self._events = []                    # (age in the frame, None = shot | reload mark type, factor)
        self._reload_key = None
        self._reload_prev = None             # frame last checked of the running reload clip

    @property
    def trauma(self) -> float:
        """Old name (trauma model removed), kept for selftests / readouts: now the burst heat."""
        return self.heat

    def reset(self):
        """Back to rest (clock and shot count are kept, so the noise and strength do not restart from the beginning)."""
        self.heat = 0.0
        self.since_shot = 1e9
        for s in (self.spring, self.fire, self.gun_fire):
            s.x = [0.0] * 6
            s.v = [0.0] * 6
        self._gun_kicks.clear()
        self._events.clear()
        self._reload_key = self._reload_prev = None

    # --- events (queued, handled in time order within `update`) ---
    def on_shot(self, age: float = 0.0, scale: float = 1.0):
        """One shot. `age` = how long before the end of the frame this shot fired (as `Weapon.update` returns it). `scale` multiplies this shot's kick only
        (e.g. by posture); does not change the heat."""
        if self.enabled:
            self._events.append((age, None, scale))

    def on_beat(self, kind: str, age: float = 0.0):
        """One mark of the reload clip ('mag_out' / 'seat' / 'bolt'): short spring impulse."""
        if self.enabled:
            self._events.append((age, kind, 1.0))

    def watch_reload(self, key, frame, frames_per_second: float = 30.0):
        """Called every frame with (`Handling.key`, `Handling.frame`, 30 * reload speed); key None when not reloading.
        Queues the marks passed in this frame (with their age in the frame); cancelling the reload (key back to None) drops the marks not yet reached."""
        if key is None or frame is None:
            self._reload_key = self._reload_prev = None
            return
        if key != self._reload_key:
            self._reload_key, self._reload_prev = key, None
        prev = self._reload_prev
        for f, kind in self.d.reload_beats.get(key, ()):
            if (prev is None or f > prev) and f <= frame:
                self.on_beat(kind, (frame - f) / frames_per_second)
        self._reload_prev = frame

    def _apply_beat(self, kind: str):
        d = self.d
        peak = d.beat_peaks[kind]
        sign = 1.0 if hash_unit(self.seed, _AX_BEAT, self.beat_count) >= 0 else -1.0
        self.beat_count += 1
        gain = impulse_gain(d.beat_omega, d.beat_zeta)
        flip = (1.0, 1.0, 1.0, 1.0, sign, sign)       # flip the yaw and roll signs so it is not repetitive
        self.spring.kick([p * g * gain for p, g in zip(peak, flip)])
        self.beat_log.append((self.t, kind))

    def shot_peak(self, n: int, heat: float = 0.0, scale: float = 1.0) -> tuple:
        """Peak deviation (6 axes, metres and degrees) of the n-th shot if it fires while the spring is at rest with burst heat `heat`; with (strength, heat factor)."""
        d = self.d
        strength = max(0.0, 1.0 + d.strength_var * signed_pow(hash_unit(self.seed, _AX_STRENGTH, n), d.strength_shape))
        boost = 1.0 + d.heat_boost * heat
        k = strength * boost * scale * d.fire_scale
        peak = tuple(k * (b + s * signed_pow(hash_unit(self.seed, _AX_DIR + i, n), d.direction_shape))
                     for i, (b, s) in enumerate(zip(d.fire_bias, d.fire_spread)))
        return peak, strength, boost

    def _apply_shot(self, scale: float):
        d = self.d
        n = self.shot_count
        self.shot_count += 1
        peak, strength, boost = self.shot_peak(n, self.heat, scale)
        gain = impulse_gain(d.fire_omega, d.fire_zeta)
        impulse = [p * gain for p in peak]
        self.fire.kick(impulse)
        self._gun_kicks.append((self.t + max(d.gun_delay, 0.0), impulse))
        self._gun_kicks.sort(key=lambda e: e[0])
        self.heat = min(1.0, self.heat + 1.0 / max(d.heat_shots, 1e-6))
        self.since_shot = 0.0
        self.shot_log.append((self.t, strength, boost, peak))

    # --- every frame ---
    def _step(self, h: float):
        """Advance h seconds with no events: cooling (only the time beyond heat_hold), three springs by exact solution."""
        if h <= 0.0:
            return
        d = self.d
        self.t += h
        cooling = max(0.0, self.since_shot + h - max(self.since_shot, d.heat_hold))
        self.since_shot += h
        if cooling > 0.0 and self.heat > 0.0:
            self.heat = max(0.0, self.heat - d.heat_cool * cooling)
        self.spring.omega, self.spring.zeta = d.beat_omega, d.beat_zeta
        for s in (self.fire, self.gun_fire):
            s.omega, s.zeta = d.fire_omega, d.fire_zeta
        for s in (self.spring, self.fire, self.gun_fire):
            if _moving(s):
                s.step(h)
                _settle(s)

    def _advance(self, h: float):
        """Advance h seconds; the delayed gun impulses due within this span are fed in at the right moment."""
        end = self.t + max(h, 0.0)
        while self._gun_kicks and self._gun_kicks[0][0] <= end:
            due, impulse = self._gun_kicks.pop(0)
            self._step(due - self.t)
            self.gun_fire.kick(impulse)
        self._step(end - self.t)

    def update(self, dt: float):
        """Advance `dt` seconds, handling queued events at their own times within the frame (oldest first): the result depends only on time,
        not on how the frames are split. Call AFTER the frame's events."""
        events = sorted(self._events, key=lambda e: -e[0])
        self._events.clear()
        left = dt
        for age, kind, scale in events:
            age = min(max(age, 0.0), left)
            self._advance(left - age)
            left = age
            if kind is None:
                self._apply_shot(scale)
            else:
                self._apply_beat(kind)
        self._advance(left)

    # --- read ---
    @property
    def amplitude(self) -> float:
        """Normalised shot-shake level: the camera's current largest deviation vs. the nominal peak deviation of a lone shot
        (bias + spread for that axis; ~1 at the peak of a strong lone shot, ~2 when the whole magazine is sustained). Excludes the hand tremor."""
        d = self.d
        ref = [abs(b) + abs(s) for b, s in zip(d.fire_bias, d.fire_spread)]
        return max((abs(x) / r for x, r in zip(self.fire.x, ref) if r > 0), default=0.0)

    @property
    def active(self) -> bool:
        return (self.heat > 0 or bool(self._gun_kicks)
                or _moving(self.spring) or _moving(self.fire) or _moving(self.gun_fire))

    def _tremor(self, delay: float) -> tuple:
        d = self.d
        e = self.heat * d.fire_scale
        if e <= 0:
            return (0.0,) * 6
        u = (self.t - delay) * d.tremor_freq
        return tuple(e * amp * smooth_noise(self.seed, _AX_TREMOR + axis, u) for axis, amp in enumerate(d.tremor_amp))

    def _ads_scale(self, ads: float) -> float:
        return 1.0 + (self.d.ads_multiplier - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))

    def camera_pose(self, ads: float = 0.0) -> tuple:
        """Shake pose of the world camera: (x right, y up, z forward, pitch up, yaw right, roll right), metres and degrees.
        `ads` 0 hip .. 1 fully aimed (reduced to `ads_multiplier`)."""
        k = self._ads_scale(ads)
        tremor = self._tremor(0.0)
        return tuple(k * (f + r + s) for f, r, s in zip(self.fire.x, tremor, self.spring.x))

    def gun_pose(self, ads: float = 0.0) -> tuple:
        """Extra pose for the GUN on screen. A camera offset of +p moves the world -p on screen; the gun follows
        that world motion (sign-flipped), and lags `gun_delay` seconds so it does not stick to the world."""
        d = self.d
        k = self._ads_scale(ads) * d.gun_follow
        tremor = self._tremor(d.gun_delay)
        return tuple(-k * (f + r + s) for f, r, s in zip(self.gun_fire.x, tremor, self.spring.x))
