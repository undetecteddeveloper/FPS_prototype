"""Wet footprints on the deck (pure Python; tests/test_footprints.py). Drawn by room.frag from a small uniform array (x, z, t0, packed yaw + strength).

After the player leaves the water his feet stay wet for `feet_dry` seconds (getting drier); every `print_spacing` metres walked on dry deck a print is left, alternately left and
right of his path, as wet as his feet are then. A print dries out over `print_life` seconds (the shader fades it by age). The trail is a ring buffer: the oldest print is reused.
"""
import math

SLOTS = 24
FOOT_OFFSET = 0.11          # m: a foot is this far left / right of the walking line


class FootprintTrail:
    def __init__(self, slots: int = SLOTS):
        self.slots = slots
        self.prints = [(0.0, 0.0, -1e6, 0.0)] * slots       # (x, z, t0, yaw + strength packed: yaw rad in [0, 2pi) + floor(strength*100)*10)
        self.next = 0
        self.wet = 0.0                                      # how wet the feet are (1 just out of the water .. 0 dry)
        self.walked = 0.0
        self.left = True
        self.count = 0

    def update(self, t: float, x: float, z: float, dx: float, dz: float, in_water: bool, on_deck: bool, feet_dry: float, spacing: float) -> list:
        """Call every frame with the move (dx, dz) of this frame. Returns the prints added [(x, z, t0, yaw, strength)]."""
        moved = math.hypot(dx, dz)
        if in_water:
            self.wet = 1.0
            self.walked = 0.0
            return []
        if self.wet <= 0.0 or not on_deck:
            return []
        out = []
        self.walked += moved
        if moved > 1e-6 and self.walked >= spacing:
            self.walked = 0.0 if self.walked > 2.0 * spacing else self.walked - spacing
            yaw = math.atan2(dx, dz)                          # 0 = walking +z (north)
            side = FOOT_OFFSET if self.left else -FOOT_OFFSET
            px, pz = x - math.cos(yaw) * side, z + math.sin(yaw) * side        # left of the heading
            self.left = not self.left
            p = (px, pz, t, yaw % (2.0 * math.pi), self.wet)
            self.prints[self.next] = pack(*p)
            self.next = (self.next + 1) % self.slots
            self.count += 1
            out.append(p)
        return out

    def dry(self, dt: float, feet_dry: float):
        if self.wet > 0.0:
            self.wet = max(0.0, self.wet - dt / max(feet_dry, 1e-3))


def pack(x: float, z: float, t0: float, yaw: float, strength: float) -> tuple:
    """The vec4 the shader reads: w = yaw (0..2pi) + 10 * round(strength * 100)."""
    return (x, z, t0, yaw + 10.0 * round(min(max(strength, 0.0), 1.0) * 100))


def unpack(w: float) -> tuple:
    """(yaw, strength) from the packed w (mirror of room.frag)."""
    s = math.floor(w / 10.0)
    return w - s * 10.0, s / 100.0
