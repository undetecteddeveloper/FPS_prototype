"""Targets and bullet holes. A target has an AABB hit box computed from its current position.

Moving targets (G6) travel sideways across the lane (x axis) between two edges (`MOVERS`, maths in core/patrol.py). `Target.update(dt)` is called by `Combat.update` at the START
of the frame, before the bullets fly; the target records the x at the start and at the end of the frame (`x_start`, `x_end`) so bullets hit-test against the box at the right time
of each small step (`Combat._advance`), not at the end of the frame.

Bullet holes are in game/decals.py.
"""
from dataclasses import dataclass

from PIL import Image, ImageDraw
from ursina import Entity, Texture, color, lerp

from fps.core.patrol import Patrol, phase_start
from fps.weapon_data import FeedbackParams

TARGET_THICKNESS = 0.06
TARGET_BASE_WIDTH = 0.6
TARGET_WIDTH_PER_M = 0.008      # farther targets grow wider so they stay visible
TARGET_MIN_HEIGHT = 1.9         # about the height of a person, always covers eye level (1.62 m)
TARGET_ASPECT = 1.3             # height = width * 1.3 once the target is big enough
# (distance m: horizontal offset m). Alternate sides so a near target does not hide a far one.
LAYOUT = {10: -3.0, 25: 3.0, 50: -3.0, 100: 3.0, 150: 0.0, 200: -4.0}   # 200 m is offset to the left: the 150 m target at x=0 would block it


@dataclass(frozen=True)
class MoverSpec:
    """A target at this distance travels sideways across the lane (instead of standing still at the x of LAYOUT)."""
    speed: float            # m/s
    pause: float = 0.35     # s pause at each end before turning back
    phase: float = 0.0      # 0..1: starting point in the back-and-forth cycle (so the moving targets do not move in step)


# Near ones slow, far ones fast (far away the target's angular speed is small, so it is easier to lead). 10/50/150 m stand still: 150 m is the drop-measurement target (brief: ~0.45 m).
# The 25 m target runs at z = 25 like the markers and signs, so its x limit is set by PATROL_EDGE_X (markers at |x| = 8.35).
MOVERS = {25: MoverSpec(1.5, phase=0.15), 100: MoverSpec(3.0, phase=0.60), 200: MoverSpec(4.0, phase=0.35)}
PATROL_EDGE_X = 8.0     # outer edge of a moving target never goes beyond this |x| (the lane paint; markers at 8.35 and walls at 12)

FLASH_COLOR = color.rgb(1.0, 0.28, 0.22)


def target_size(distance: float) -> tuple:
    width = TARGET_BASE_WIDTH + TARGET_WIDTH_PER_M * distance
    return width, max(TARGET_MIN_HEIGHT, width * TARGET_ASPECT)


def _target_texture() -> Texture:
    size = 256
    img = Image.new('RGB', (size, size), (225, 205, 160))
    d = ImageDraw.Draw(img)
    c = size / 2
    for r, fill in ((120, (205, 180, 130)), (84, (225, 205, 160)), (48, (205, 180, 130))):
        d.ellipse([c - r, c - r, c + r, c + r], fill=fill, outline=(60, 45, 30), width=3)
    d.ellipse([c - 14, c - 14, c + 14, c + 14], fill=(170, 40, 35))
    d.rectangle([0, 0, size - 1, size - 1], outline=(70, 55, 40), width=6)
    tex = Texture(img, filtering='mipmap')
    tex._texture.set_anisotropic_degree(8)
    return tex


def hole_texture() -> Texture:
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2
    d.ellipse([c - 30, c - 30, c + 30, c + 30], fill=(25, 20, 15, 90))     # faint smoke halo
    d.ellipse([c - 17, c - 17, c + 17, c + 17], fill=(15, 12, 10, 190))
    d.ellipse([c - 9, c - 9, c + 9, c + 9], fill=(5, 5, 5, 255))
    return Texture(img, filtering='mipmap')


class Target:
    def __init__(self, distance: float, x: float, texture: Texture, flash_duration: float, patrol: Patrol = None):
        self.distance = distance
        self.width, self.height = target_size(distance)
        self.flash_duration = flash_duration
        self.flash_left = 0.0
        self.patrol = patrol                # None: still target
        self.motion_enabled = True          # False: the moving target stands still in place (for measurement / screenshots)
        if patrol is not None:
            x = patrol.x
        self.x_start = self.x_end = x       # x of the target centre at the start / end of the last frame (equal if still)
        # root has no scale, so bullet holes stuck to it are not distorted
        self.root = Entity(position=(x, 0, distance))
        self.plate = Entity(parent=self.root, model='cube', texture=texture, y=self.height / 2,
                            scale=(self.width, self.height, TARGET_THICKNESS))

    @property
    def moving(self) -> bool:
        return self.patrol is not None and self.motion_enabled

    def x_at(self, f: float) -> float:
        """x of the target centre at fraction f (0..1) of the last frame: interpolated between the start and end of the frame."""
        return self.x_start + (self.x_end - self.x_start) * f

    def aabb(self) -> tuple:
        """Hit box at the CURRENT position (end of frame)."""
        return self.aabb_at_x(self.root.x)

    def aabb_at_x(self, x: float) -> tuple:
        y, z = self.root.y, self.root.z
        return ((x - self.width / 2, y, z - TARGET_THICKNESS / 2),
                (x + self.width / 2, y + self.height, z + TARGET_THICKNESS / 2))

    def sweep_aabb(self) -> tuple:
        """Box enclosing the whole span a moving target travels through (still target: same as `aabb`)."""
        if self.patrol is None:
            return self.aabb()
        lo, _ = self.aabb_at_x(self.patrol.lo)
        _, hi = self.aabb_at_x(self.patrol.hi)
        return lo, hi

    def flash(self):
        self.flash_left = self.flash_duration

    def update(self, dt: float):
        self.x_start = self.root.x
        if self.moving:
            self.root.x = self.patrol.advance(dt)
        self.x_end = self.root.x
        if self.flash_left > 0:
            self.flash_left = max(0.0, self.flash_left - dt)
            self.plate.color = lerp(color.white, FLASH_COLOR, self.flash_left / self.flash_duration)


def make_patrol(distance: float, spec: MoverSpec) -> Patrol:
    """Moving target between two edges, so that its outer edge stops at PATROL_EDGE_X; starts according to `spec.phase`."""
    half = target_size(distance)[0] / 2
    lo, hi = -(PATROL_EDGE_X - half), PATROL_EDGE_X - half
    x, direction = phase_start(lo, hi, spec.phase)
    return Patrol(lo, hi, spec.speed, spec.pause, x, direction)


def build_targets(params: FeedbackParams, moving: bool = True) -> list:
    """In LAYOUT order. `moving=False`: every target stands still at the x of LAYOUT (the drop-measurement selftests need this)."""
    texture = _target_texture()
    out = []
    for d, x in LAYOUT.items():
        spec = MOVERS.get(d) if moving else None
        out.append(Target(float(d), x, texture, params.target_flash_duration, make_patrol(d, spec) if spec else None))
    return out
