"""Footsteps, jumps, landings (pure, no ursina import, so it can be tested without a window).

Step timing is LOCKED to the gun sway: when the Sway bob phase is passed in (`bob_phase`), each time the phase crosses the foot-plant point (`step_bob_phase`, plus pi:
two steps per bob cycle; the gun is at its lowest then) one sound plays. So changing `bob_rate` / `bob_stride` changes the step rate with it, at any FPS.
Without a bob phase (test, fallback) it is computed from the DISTANCE travelled (phase 0..1 increases by `distance / stride`). In the air: silent. Landing: one loud 'thud' scaled by fall speed (replaces the next step).
Jumping up: one small sole sound. Stopping completely: nothing more is played, and the first step after standing still comes early (`step_start_phase`).

The `update` method returns a list of `FootEvent`; choosing the file and playing it is in game/foley.py.
"""
import math
import random
from dataclasses import dataclass

from fps.weapon_data import AudioData


@dataclass(frozen=True)
class FootEvent:
    kind: str          # 'step' | 'land' | 'jump'
    foot: int          # 0 left, 1 right (alternating)
    gain: float        # volume including randomness (multiply by 1 = full)
    pitch: float       # playback-rate ratio (1 = normal)
    run: bool = False  # sprint step (uses the 'step_run' sound group)


def pick_variant(rng: random.Random, count: int, last: int = None) -> int:
    """Pick one variant out of `count`, not the one just used (if possible)."""
    if count <= 1:
        return 0
    k = rng.randrange(count - 1) if last is not None and 0 <= last < count else rng.randrange(count)
    return k + 1 if last is not None and 0 <= last < count and k >= last else k


class Footsteps:
    def __init__(self, audio: AudioData, rng: random.Random = None):
        self.a = audio
        self.rng = rng or random.Random()
        self.phase = audio.step_start_phase
        self.foot = 0
        self._was_on_ground = True
        self._bob_last = None          # bob phase of the previous frame (None: none yet)

    def _vary(self, base_gain: float, foot: int, variation_pitch: float = None) -> tuple:
        a, rng = self.a, self.rng
        gain = base_gain * (1.0 + rng.uniform(-a.step_volume_variation, a.step_volume_variation))
        v = a.step_pitch_variation if variation_pitch is None else variation_pitch
        pitch = 1.0 + rng.uniform(-v, v) + (a.foot_pitch if foot else -a.foot_pitch)
        return gain, pitch

    def _bob_steps(self, last, phase: float, sprinting: bool, crouching: bool) -> list:
        """Bob-phase crossings of the foot-plant point during this frame (the phase goes from `last` to `phase`, always forward). Foot 0 at step_bob_phase, foot 1 plus pi."""
        a = self.a
        if last is None or phase is None:
            return []
        delta = (phase - last) % (2.0 * math.pi)
        if delta <= 0.0:
            return []
        hits = []
        for foot, target in ((0, a.step_bob_phase), (1, a.step_bob_phase + math.pi)):
            d = (target - last) % (2.0 * math.pi)
            if 0.0 < d <= delta:
                hits.append((d, foot))
        if crouching:
            mult = a.step_crouch_multiplier
        elif sprinting:
            mult = a.step_sprint_multiplier
        else:
            mult = 1.0
        events = []
        for _, foot in sorted(hits)[:2]:          # at most 2 steps per frame (a long hang does not fire a whole burst)
            gain, pitch = self._vary(a.step_volume * mult, foot)
            events.append(FootEvent('step', foot, gain, pitch, run=sprinting and not crouching))
            self.foot = foot ^ 1
        return events

    def update(self, dt: float, moved: float, on_ground: bool, vy: float, landed: float, sprinting: bool, crouching: bool,
               bob_phase: float = None) -> list:
        """One frame. `moved`: horizontal distance just travelled (m); `vy`: vertical speed after the physics step; `landed`: landing speed (m/s) if this frame just landed;
        `bob_phase`: Sway.phase of this frame (rad); if given, step timing follows the bob phase instead of distance."""
        a = self.a
        events = []
        bob_last, self._bob_last = self._bob_last, bob_phase
        if self._was_on_ground and not on_ground and vy > 0.0:
            gain, pitch = self._vary(a.jump_volume, self.foot)
            events.append(FootEvent('jump', self.foot, gain, pitch))
        self._was_on_ground = on_ground

        if landed >= a.land_min_speed:
            lo, hi = a.land_gain_range
            level = min(max(landed / a.land_reference_speed, lo), hi)
            gain, pitch = self._vary(a.land_volume * level, self.foot, a.step_pitch_variation)
            events.append(FootEvent('land', self.foot, gain, pitch))
            self.phase = a.step_start_phase
        elif on_ground:
            speed = moved / dt if dt > 0 else 0.0
            if speed < a.step_min_speed:
                self.phase = a.step_start_phase        # standing still: no sound, and the first step after it comes early
            elif bob_phase is not None:
                events += self._bob_steps(bob_last, bob_phase, sprinting, crouching)
            else:
                if crouching:
                    stride, mult = a.step_stride_crouch, a.step_crouch_multiplier
                elif sprinting:
                    stride, mult = a.step_stride_sprint, a.step_sprint_multiplier
                else:
                    stride, mult = a.step_stride_walk, 1.0
                self.phase += moved / stride
                emitted = 0
                while self.phase >= 1.0 and emitted < 2:      # at most 2 steps per frame (a long hang does not fire a whole burst)
                    self.phase -= 1.0
                    gain, pitch = self._vary(a.step_volume * mult, self.foot)
                    events.append(FootEvent('step', self.foot, gain, pitch, run=sprinting and not crouching))
                    self.foot ^= 1
                    emitted += 1
                self.phase = min(self.phase, 1.0)
        return events
