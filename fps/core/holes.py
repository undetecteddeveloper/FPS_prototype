"""Bullet-hole bookkeeping (pure Python; tests/test_holes.py): a ring of decal slots where every hole lives `life` seconds, fades out over the last `fade` seconds, then its slot is freed.

Why holes die so fast (user's choice, 8/11/2026: 1.5 s): a hole is a few triangles, but while any hole is alive the decal mesh is drawn with a parallax shader, and a long-lived pool
of 200 of them cost draw time and uploads for nothing: with a short life the mesh is hidden most of the time and the ring stays small.
Time is a number of seconds on `HoleRing.clock`; the shader gets `clock % CLOCK_WRAP` and each hole's birth the same way, so it can find the age with `mod` and stay exact in a long session.
"""
from collections import deque

CLOCK_WRAP = 4096.0        # seconds: float32 keeps ~1 ms resolution below this (decal.frag `age`)


def fade_alpha(age: float, life: float, fade: float) -> float:
    """Opacity multiplier of a hole `age` s old: 1 until `life - fade`, then a smoothstep to 0 at `life` (mirror of decal.frag)."""
    if age >= life:
        return 0.0
    if fade <= 0.0 or age <= life - fade:
        return 1.0
    t = (age - (life - fade)) / fade
    return 1.0 - t * t * (3.0 - 2.0 * t)


def wrapped_age(clock: float, birth: float) -> float:
    """Age on the wrapped clocks the shader sees (both given as values already taken modulo CLOCK_WRAP)."""
    return (clock - birth) % CLOCK_WRAP


class HoleRing:
    """`capacity` slots, filled in order; the oldest slot is reused when all are alive. `life` = seconds a hole stays."""

    def __init__(self, capacity: int, life: float):
        self.capacity = max(int(capacity), 1)
        self.life = float(life)
        self.clock = 0.0
        self.next = 0
        self.added = 0                                    # holes made since the start (never goes down: checks count with it)
        self.slots = [None] * self.capacity               # birth clock of the hole in each slot, None = free
        self.order = deque()                              # (slot, birth) oldest first

    @property
    def live(self) -> int:
        return len(self.order)

    def advance(self, dt: float) -> list:
        """Move the clock; returns the slots whose hole just died (the caller collapses their mesh)."""
        self.clock += max(dt, 0.0)
        dead = []
        while self.order and self.clock - self.order[0][1] >= self.life:
            slot, birth = self.order.popleft()
            if self.slots[slot] == birth:
                self.slots[slot] = None
                dead.append(slot)
        return dead

    def add(self) -> int:
        """Take the next slot (the oldest hole is replaced when the ring is full); returns it."""
        slot = self.next
        if self.slots[slot] is not None:                  # full ring: the slot's old hole is the oldest one, at the front of `order`
            old = self.order.popleft()
            assert old[0] == slot
        self.slots[slot] = self.clock
        self.order.append((slot, self.clock))
        self.next = (slot + 1) % self.capacity
        self.added += 1
        return slot

    def birth_wrapped(self, slot: int) -> float:
        return (self.slots[slot] if self.slots[slot] is not None else 0.0) % CLOCK_WRAP

    def clock_wrapped(self) -> float:
        return self.clock % CLOCK_WRAP

    def clear(self) -> list:
        """Kill every hole; returns the slots that were alive."""
        dead = [s for s, _ in self.order]
        self.order.clear()
        self.slots = [None] * self.capacity
        return dead
