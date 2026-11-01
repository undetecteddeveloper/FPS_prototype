"""Bia và lỗ đạn. Bia có hộp va chạm AABB tính từ vị trí hiện tại.

Bia chạy (G6) đi ngang làn (trục x) giữa hai biên (`MOVERS`, toán ở core/patrol.py). `Target.update(dt)` do `Combat.update` gọi ở ĐẦU
khung, trước khi đạn đi; bia ghi lại x đầu khung và x cuối khung (`x_start`, `x_end`) để đạn dò va chạm với hộp ở đúng thời điểm
của từng bước nhỏ (`Combat._advance`), không phải ở cuối khung.

Lỗ đạn là `quad` dán lên mặt trúng, tái dùng vòng tròn trong một bể cố định (không phình ra mãi). Lỗ gắn vào `target.root`
nên bia chạy mang lỗ theo.
"""
from dataclasses import dataclass

from PIL import Image, ImageDraw
from ursina import Entity, Texture, color, lerp, scene

from fps.core.ballistics import decal_rotation, hole_size
from fps.core.patrol import Patrol, phase_start
from fps.weapon_data import FeedbackParams

TARGET_THICKNESS = 0.06
TARGET_BASE_WIDTH = 0.6
TARGET_WIDTH_PER_M = 0.008      # bia xa to dần để còn nhìn thấy
TARGET_MIN_HEIGHT = 1.9         # cao cỡ một người, luôn phủ tầm mắt (1,62 m)
TARGET_ASPECT = 1.3             # cao = rộng * 1.3 khi bia đủ to
# (khoảng cách m: lệch ngang m). Xen kẽ hai bên để bia gần không che bia xa.
LAYOUT = {10: -3.0, 25: 3.0, 50: -3.0, 100: 3.0, 150: 0.0, 200: -4.0}   # 200 m lệch trái: bia 150 m ở x=0 sẽ che


@dataclass(frozen=True)
class MoverSpec:
    """Bia ở khoảng cách này chạy ngang làn (thay vì đứng yên ở x của LAYOUT)."""
    speed: float            # m/s
    pause: float = 0.35     # s nghỉ ở mỗi đầu trước khi quay lại
    phase: float = 0.0      # 0..1: điểm xuất phát trong vòng đi-về (để các bia chạy không đi cùng nhịp)


# Gần chậm, xa nhanh (xa thì góc quay của bia nhỏ nên dễ ngắm đón hơn). 10/50/150 m đứng yên: 150 m là bia đo độ rơi (đề bài ~0,45 m).
# Bia 25 m chạy ở z = 25 giống cột mốc và biển, nên biên x chặn theo PATROL_EDGE_X (cột mốc ở |x| = 8,35).
MOVERS = {25: MoverSpec(1.5, phase=0.15), 100: MoverSpec(3.0, phase=0.60), 200: MoverSpec(4.0, phase=0.35)}
PATROL_EDGE_X = 8.0     # mép ngoài của bia chạy không vượt quá |x| này (vạch sơn của làn; cột mốc ở 8,35 và tường ở 12)

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


def _hole_texture() -> Texture:
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2
    d.ellipse([c - 30, c - 30, c + 30, c + 30], fill=(25, 20, 15, 90))     # quầng khói mờ
    d.ellipse([c - 17, c - 17, c + 17, c + 17], fill=(15, 12, 10, 190))
    d.ellipse([c - 9, c - 9, c + 9, c + 9], fill=(5, 5, 5, 255))
    return Texture(img, filtering='mipmap')


class Target:
    def __init__(self, distance: float, x: float, texture: Texture, flash_duration: float, patrol: Patrol = None):
        self.distance = distance
        self.width, self.height = target_size(distance)
        self.flash_duration = flash_duration
        self.flash_left = 0.0
        self.patrol = patrol                # None: bia đứng yên
        self.motion_enabled = True          # False: bia chạy đứng im tại chỗ (để đo / chụp ảnh)
        if patrol is not None:
            x = patrol.x
        self.x_start = self.x_end = x       # x của tâm bia ở đầu / cuối khung vừa qua (đứng yên thì bằng nhau)
        # root không scale để lỗ đạn gắn vào đó không bị méo
        self.root = Entity(position=(x, 0, distance))
        self.plate = Entity(parent=self.root, model='cube', texture=texture, y=self.height / 2,
                            scale=(self.width, self.height, TARGET_THICKNESS))

    @property
    def moving(self) -> bool:
        return self.patrol is not None and self.motion_enabled

    def x_at(self, f: float) -> float:
        """x của tâm bia ở phần f (0..1) của khung vừa qua: nội suy giữa đầu và cuối khung."""
        return self.x_start + (self.x_end - self.x_start) * f

    def aabb(self) -> tuple:
        """Hộp va chạm ở vị trí HIỆN TẠI (cuối khung)."""
        return self.aabb_at_x(self.root.x)

    def aabb_at_x(self, x: float) -> tuple:
        y, z = self.root.y, self.root.z
        return ((x - self.width / 2, y, z - TARGET_THICKNESS / 2),
                (x + self.width / 2, y + self.height, z + TARGET_THICKNESS / 2))

    def sweep_aabb(self) -> tuple:
        """Hộp bao toàn bộ khoảng bia chạy đi qua (bia đứng yên: giống `aabb`)."""
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


class HoleDecals:
    def __init__(self, params: FeedbackParams):
        self.params = params
        self.texture = _hole_texture()
        # tạo sẵn cả bể lúc khởi động (tạo vật thể giữa lúc bắn gây khựng ~10 ms mỗi lần)
        self.items = [Entity(model='quad', texture=self.texture, enabled=False) for _ in range(params.max_holes)]
        self.next = 0
        self.used = 0

    def add(self, point, normal, distance: float, parent=None, tint=None):
        fb = self.params
        e = self.items[self.next]
        self.next = (self.next + 1) % len(self.items)
        self.used = min(self.used + 1, len(self.items))
        e.parent = scene                 # lỗ cũ được tái dùng có thể đang gắn vào một bia
        # nhích ra khỏi mặt phẳng: ở xa độ phân giải độ sâu thô (~1 cm ở 150 m) nên nhích theo khoảng cách
        offset = 0.02 + 0.0002 * distance
        e.position = tuple(p + n * offset for p, n in zip(point, normal))
        e.rotation = decal_rotation(normal)
        e.scale = hole_size(distance, fb.hole_base_size, fb.hole_size_per_meter)
        e.color = tint or color.white
        e.set_depth_offset(2)
        e.enabled = True
        if parent is not None:
            e.world_parent = parent      # giữ nguyên toạ độ thế giới, từ giờ đi theo `parent`
        return e

    @property
    def count(self) -> int:
        return self.used


def make_patrol(distance: float, spec: MoverSpec) -> Patrol:
    """Bia chạy giữa hai biên sao cho mép ngoài của bia dừng ở PATROL_EDGE_X; xuất phát theo `spec.phase`."""
    half = target_size(distance)[0] / 2
    lo, hi = -(PATROL_EDGE_X - half), PATROL_EDGE_X - half
    x, direction = phase_start(lo, hi, spec.phase)
    return Patrol(lo, hi, spec.speed, spec.pause, x, direction)


def build_targets(params: FeedbackParams, moving: bool = True) -> list:
    """Thứ tự theo LAYOUT. `moving=False`: mọi bia đứng yên ở x của LAYOUT (các selftest đo độ rơi cần vậy)."""
    texture = _target_texture()
    out = []
    for d, x in LAYOUT.items():
        spec = MOVERS.get(d) if moving else None
        out.append(Target(float(d), x, texture, params.target_flash_duration, make_patrol(d, spec) if spec else None))
    return out
