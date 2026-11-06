"""Moving-target motion: walks evenly between two bounds, turning around (pausing briefly at each end). Pure math, no ursina import.

State is (position, direction, pause time left); `advance(dt)` spends the time exactly, so the result does NOT depend on how the frames are split:
one 50 ms step gives the same position as 50 steps of 1 ms (even when one step covers several turnarounds).
"""
from dataclasses import dataclass


@dataclass
class Patrol:
    lo: float                # left bound (smallest x of the target's CENTRE)
    hi: float                # right bound
    speed: float             # m/s
    pause: float = 0.0       # s pause at each end before turning back
    x: float = 0.0
    direction: float = 1.0   # +1 to the right (x increases), -1 to the left
    wait: float = 0.0        # s of pause left at the current end

    def __post_init__(self):
        if not self.lo < self.hi:
            raise ValueError('biên trái phải nhỏ hơn biên phải')
        self.x = min(max(self.x, self.lo), self.hi)

    @property
    def velocity(self) -> float:
        """Instantaneous velocity (m/s, signed): 0 while pausing at an end."""
        return 0.0 if self.wait > 0.0 else self.speed * self.direction

    @property
    def span(self) -> float:
        return self.hi - self.lo

    @property
    def period(self) -> float:
        """One back-and-forth cycle (s), including both pauses."""
        return 2.0 * (self.span / self.speed + self.pause)

    def advance(self, dt: float) -> float:
        """Advance `dt` seconds; return the new x of the target's centre."""
        left = dt
        # each loop either uses up the time or reaches an end (then turns + pauses): finite even for a very large dt
        while left > 1e-12:
            if self.wait > 0.0:
                used = min(self.wait, left)
                self.wait -= used
                left -= used
                continue
            if self.speed <= 0.0:
                break
            end = self.hi if self.direction > 0 else self.lo
            reach = abs(end - self.x) / self.speed          # time to reach the end
            if left < reach:
                self.x += self.direction * self.speed * left
                break
            self.x = end
            left -= reach
            self.direction = -self.direction
            self.wait = self.pause
        return self.x

    def reset(self, x: float, direction: float = 1.0):
        self.x = min(max(x, self.lo), self.hi)
        self.direction = 1.0 if direction >= 0 else -1.0
        self.wait = 0.0


def phase_start(lo: float, hi: float, phase: float) -> tuple:
    """Start point (x, direction) for phase 0..1 of a back-and-forth cycle with no pauses, so moving targets are not in sync with each other."""
    phase = phase % 1.0
    span = hi - lo
    if phase < 0.5:
        return lo + span * phase * 2.0, 1.0
    return hi - span * (phase - 0.5) * 2.0, -1.0
