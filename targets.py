"""Bia và lỗ đạn. Bia có hộp va chạm AABB tính từ vị trí hiện tại (bia chạy ở G6 chỉ cần đổi vị trí).

Lỗ đạn là `quad` dán lên mặt trúng, tái dùng vòng tròn trong một bể cố định (không phình ra mãi).
"""
from PIL import Image, ImageDraw
from ursina import Entity, Texture, color, lerp, scene

from ballistics import decal_rotation, hole_size
from weapon_data import FeedbackParams

TARGET_THICKNESS = 0.06
TARGET_BASE_WIDTH = 0.6
TARGET_WIDTH_PER_M = 0.008      # bia xa to dần để còn nhìn thấy
TARGET_MIN_HEIGHT = 1.9         # cao cỡ một người, luôn phủ tầm mắt (1,62 m)
TARGET_ASPECT = 1.3             # cao = rộng * 1.3 khi bia đủ to
# (khoảng cách m: lệch ngang m). Xen kẽ hai bên để bia gần không che bia xa.
LAYOUT = {10: -3.0, 25: 3.0, 50: -3.0, 100: 3.0, 150: 0.0, 200: -4.0}   # 200 m lệch trái: bia 150 m ở x=0 sẽ che

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
    def __init__(self, distance: float, x: float, texture: Texture, flash_duration: float):
        self.distance = distance
        self.width, self.height = target_size(distance)
        self.flash_duration = flash_duration
        self.flash_left = 0.0
        # root không scale để lỗ đạn gắn vào đó không bị méo
        self.root = Entity(position=(x, 0, distance))
        self.plate = Entity(parent=self.root, model='cube', texture=texture, y=self.height / 2,
                            scale=(self.width, self.height, TARGET_THICKNESS))

    def aabb(self) -> tuple:
        x, y, z = self.root.position
        return ((x - self.width / 2, y, z - TARGET_THICKNESS / 2),
                (x + self.width / 2, y + self.height, z + TARGET_THICKNESS / 2))

    def flash(self):
        self.flash_left = self.flash_duration

    def update(self, dt: float):
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


def build_targets(params: FeedbackParams) -> list:
    texture = _target_texture()
    return [Target(float(d), x, texture, params.target_flash_duration) for d, x in LAYOUT.items()]
