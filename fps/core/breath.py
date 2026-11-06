"""Breathing sound: one breath per breathing cycle of the sway (pure math, no ursina import).

Sway breathes along a Lissajous curve at `SwayData.breath_freq` (horizontal: one cycle; vertical: two cycles per period). Each period plays ONE breath (one inhale + one exhale),
starting exactly when the gun starts rising on the first vertical cycle (phase sin(2w + 0.6) = 0, i.e. w = -0.3 rad), so the breath sound and the gun + camera bob share one clock.
Plays only when standing still (a bob that takes over stops it) and while on the ground; quieter when aiming (breath held). A breath already started is played to its end, never cut mid-way.
"""
import math

from fps.core.movement import smoothstep
from fps.weapon_data import AudioData, SwayData

SWAY_BREATH_OFFSET = 0.6          # rad: added to the vertical phase in Sway._breath (sin(2w + 0.6))


class Breathing:
    def __init__(self, audio: AudioData, sway: SwayData):
        self.a = audio
        self.s = sway
        self._cycle = None            # last breath cycle number (integer) checked

    def reset(self):
        self._cycle = None

    def cycle_index(self, clock: float) -> int:
        """Which breath cycle is current at `clock` (seconds of Sway): the number changes at the start of an inhale."""
        # breath starts at w = -SWAY_BREATH_OFFSET / 2 (gun starts rising)
        return math.floor(clock * self.s.breath_freq + SWAY_BREATH_OFFSET / (4.0 * math.pi))

    def update(self, clock: float, bob_amount: float, ads: float, grounded: bool = True):
        """Call every frame AFTER Sway.update with `Sway.clock`, `Sway.bob_amount`, `player.ads_amount`.
        Returns the volume (0..1) if a breath starts in this frame, otherwise None."""
        n = self.cycle_index(clock)
        if self._cycle is None:
            self._cycle = n                          # first call: wait for the next breath; do not start mid-cycle
            return None
        if n == self._cycle:
            return None
        self._cycle = n
        a = self.a
        idle = 1.0 - min(max(bob_amount, 0.0), 1.0)
        if not grounded or idle < a.breath_min_idle:
            return None
        hold = 1.0 - (1.0 - a.breath_ads_scale) * smoothstep(min(max(ads, 0.0), 1.0))
        return a.breath_volume * idle * hold
