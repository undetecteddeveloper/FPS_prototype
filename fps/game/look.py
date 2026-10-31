"""Giao diện hình ảnh: shader thế giới (ánh sáng, sương mù, chi tiết mặt đất) và lớp tối góc màn hình.

Shader thế giới nằm ở shaders/world.vert|frag (khung theo unlit_with_fog_shader của Ursina). Áp lên mọi vật thể của trường bắn,
bia và lỗ đạn bằng cách đặt `Entity.shader`; vật thể giao diện và bầu trời giữ shader mặc định của Ursina.
Số liệu ở weapon_data.LookData.
"""
import math
import random

from panda3d.core import PTA_LVecBase3f, SamplerState, Vec3
from PIL import Image
from ursina import Entity, Shader, Texture, application, camera, color, window
from ursina.vec2 import Vec2

from fps.game.shaders import SHADER_DIR
from fps.weapon_data import LookData


def noise_texture(size: int = 128, cells: int = 8, seed: int = 11) -> Texture:
    """Nhiễu giá trị liền mạch (lát gạch không thấy mép), một kênh sáng, nội suy mượt: để phủ lên mặt đất thay vì ô lưới lặp."""
    rng = random.Random(seed)
    lattice = [[rng.random() for _ in range(cells)] for _ in range(cells)]

    def smooth(t):
        return t * t * (3 - 2 * t)

    def value(x, y):
        gx, gy = x / size * cells, y / size * cells
        x0, y0 = int(gx) % cells, int(gy) % cells
        x1, y1 = (x0 + 1) % cells, (y0 + 1) % cells
        fx, fy = smooth(gx - int(gx)), smooth(gy - int(gy))
        top = lattice[y0][x0] * (1 - fx) + lattice[y0][x1] * fx
        bottom = lattice[y1][x0] * (1 - fx) + lattice[y1][x1] * fx
        return top * (1 - fy) + bottom * fy

    img = Image.new('L', (size, size))
    img.putdata([int(255 * (0.65 * value(x, y) + 0.35 * value(x * 2.3 + 13, y * 2.3 + 7))) for y in range(size) for x in range(size)])
    tex = Texture(img, filtering='mipmap')
    tex._texture.set_wrap_u(SamplerState.WM_repeat)
    tex._texture.set_wrap_v(SamplerState.WM_repeat)
    return tex


def vignette_texture(size: int = 128) -> Texture:
    """Tối dần từ giữa ra góc (alpha 0 ở giữa), để phủ lên cả màn hình."""
    img = Image.new('RGBA', (size, size))
    px = []
    for y in range(size):
        for x in range(size):
            u, v = (x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1
            r = min(math.hypot(u, v) / math.sqrt(2), 1.0)          # 0 giữa .. 1 ở góc
            a = max(0.0, (r - 0.35) / 0.65) ** 1.8
            px.append((0, 0, 0, int(255 * a)))
    img.putdata(px)
    return Texture(img)


class WorldLook:
    def __init__(self, params: LookData, world: dict, targets: list, decals):
        self.p = params
        self.shader = self._make_shader()
        render = application.base.render
        norm = math.sqrt(sum(c * c for c in params.sun_dir))
        render.set_shader_input('look_sun_dir', Vec3(*(c / norm for c in params.sun_dir)))
        render.set_shader_input('look_sun_color', Vec3(*params.sun_color))
        render.set_shader_input('look_sky_color', Vec3(*params.sky_color))
        render.set_shader_input('look_ground_color', Vec3(*params.ground_color))
        render.set_shader_input('look_fog', (*params.fog_color, params.fog_density))
        render.set_shader_input('look_detail_strength', float(params.detail_strength))
        render.set_shader_input('look_detail_tex', noise_texture()._texture)
        # vị trí camera đổi mỗi khung: mảng PTA sửa tại chỗ, không gọi lại set_shader_input (đổi trạng thái vẽ của cả thế giới mỗi khung)
        self._camera_pos = PTA_LVecBase3f.empty_array(1)
        self._camera_pos.set_element(0, Vec3(0, 1.6, 0))
        render.set_shader_input('look_camera_pos', self._camera_pos)

        entities = [world['lane'], *world['grass'], *world['stripes'], *world['posts'], *world['berms']]
        entities += [t.plate for t in targets]
        entities += list(decals.items)
        for e in entities:
            e.shader = self.shader

        self.vignette = None
        if params.vignette > 0:
            self.vignette = Entity(parent=camera.ui, model='quad', texture=vignette_texture(), z=1,
                                   scale=(window.aspect_ratio, 1), color=color.rgba(1, 1, 1, params.vignette))   # tối ở góc = vignette

    @staticmethod
    def _make_shader() -> Shader:
        vert = (SHADER_DIR / 'world.vert').read_text(encoding='utf-8')
        frag = (SHADER_DIR / 'world.frag').read_text(encoding='utf-8')
        return Shader(name='fps_world', language=Shader.GLSL, vertex=vert, fragment=frag,
                      default_input={'texture_scale': Vec2(1, 1), 'texture_offset': Vec2(0.0, 0.0)})

    def update(self):
        """Mỗi khung: vị trí camera cho sương mù và độ mờ dần của chi tiết."""
        self._camera_pos.set_element(0, Vec3(*camera.world_position))
