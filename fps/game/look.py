"""Giao diện hình ảnh: shader thế giới (đèn trần, bóng, vân vật liệu, AO giả, bụi trong phòng) và lớp tối góc màn hình.

Shader thế giới nằm ở shaders/world.vert|frag (khung theo unlit_with_fog_shader của Ursina). Áp lên mọi vật thể của trường bắn,
bia và lỗ đạn bằng cách đặt `Entity.shader`; vật liệu chọn bằng đầu vào `look_material` của từng Entity. Vật thể giao diện giữ
shader mặc định của Ursina. Số liệu ở weapon_data.LookData; kích thước phòng ở core/room.RoomLayout.

Bóng (`LookData.shadows`): True = bóng thật của mọi đèn trần (lamp_shadows.py, vẽ một lần lúc khởi động), 'fake' = vệt tối
mềm dưới bia và cột mốc, False = không bóng. AO giả (chân tường, quanh cột, dưới trần) có ở cả ba chế độ.
"""
import math
import random

from panda3d.core import (ColorBlendAttrib, LMatrix4f, PTA_LMatrix4f, TransparencyAttrib, PTA_LVecBase3f, SamplerState, Texture as PandaTexture, Vec3, Vec4)
from PIL import Image
from ursina import Entity, Shader, Texture, application, camera, color, window
from ursina.vec2 import Vec2

from fps.core.room import FACE_COUNT
from fps.game.shaders import SHADER_DIR
from fps.weapon_data import LookData

MATERIALS = {'floor': 1.0, 'walls': 2.0, 'pillars': 3.0, 'ceiling': 4.0, 'lamp_glow': 5.0, 'lamp_shades': 0.0}
SHADOW_MODES = {False: 0.0, True: 1.0, 'fake': 2.0}


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


def blob_texture(size: int = 64) -> Texture:
    """Vệt tối mềm (bóng giả): alpha giảm dần từ giữa ra mép."""
    img = Image.new('RGBA', (size, size))
    px = []
    for y in range(size):
        for x in range(size):
            r = min(math.hypot((x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1), 1.0)
            px.append((0, 0, 0, int(255 * 0.75 * (1 - r * r) ** 2)))
    img.putdata(px)
    return Texture(img, filtering='mipmap')


def halo_texture(size: int = 64) -> Texture:
    """Quầng sáng mờ quanh bóng đèn: trắng, alpha giảm nhanh từ tâm (cộng sáng)."""
    img = Image.new('RGBA', (size, size))
    px = []
    for y in range(size):
        for x in range(size):
            r = min(math.hypot((x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1), 1.0)
            a = (1 - r) ** 2.2 * (1 - r * r)
            px.append((255, 255, 255, int(255 * a)))
    img.putdata(px)
    return Texture(img, filtering='mipmap')


def _dummy_shadow_texture() -> PandaTexture:
    """Atlas 1x1 (độ sâu = 1, không che gì) để sampler2DShadow luôn có kết cấu hợp lệ khi tắt bóng thật."""
    tex = PandaTexture('no_shadow')
    tex.setup_2d_texture(1, 1, PandaTexture.T_float, PandaTexture.F_depth_component32)
    tex.set_ram_image(b'\x00\x00\x80\x3f')
    tex.set_minfilter(SamplerState.FT_shadow)
    tex.set_magfilter(SamplerState.FT_shadow)
    return tex


class WorldLook:
    def __init__(self, params: LookData, world: dict, targets: list, decals):
        self.p = params
        self.world = world
        self.targets = targets
        self.shader = self._make_shader()
        self.shadows = None                 # LampShadows khi bật bóng thật
        self.blobs = []
        render = application.base.render
        room = world['room']

        render.set_shader_input('look_fog', (*params.fog_color, params.fog_density))
        render.set_shader_input('look_detail_strength', float(params.detail_strength))
        render.set_shader_input('look_detail_tex', noise_texture()._texture)
        render.set_shader_input('look_material', 0.0)
        render.set_shader_input('look_lamp', Vec4(params.lamp_x, params.lamp_y, params.lamp_z0, params.lamp_spacing))
        render.set_shader_input('look_lamp2', Vec4(float(params.lamp_count), params.lamp_radius, params.lamp_ref,
                                                   params.lamp_intensity))
        render.set_shader_input('look_lamp_color', Vec3(*params.lamp_color))
        render.set_shader_input('look_lamp_cone', Vec3(math.cos(math.radians(params.lamp_cone)),
                                                       math.cos(math.radians(params.lamp_cone_outer)), params.lamp_side))
        render.set_shader_input('look_ambient_up', Vec3(*params.ambient_up))
        render.set_shader_input('look_ambient_down', Vec3(*params.ambient_down))
        render.set_shader_input('look_bounce', Vec3(*params.bounce_color))
        render.set_shader_input('look_room', Vec4(room.half_width, room.z_back, room.z_end, room.height))
        render.set_shader_input('look_pillar', Vec4(room.pillar_z0, room.pillar_spacing, room.pillar_width / 2,
                                                    room.pillar_depth))
        render.set_shader_input('look_exposure', float(params.exposure))
        # vị trí camera đổi mỗi khung: mảng PTA sửa tại chỗ, không gọi lại set_shader_input (đổi trạng thái vẽ của cả thế giới mỗi khung)
        self._camera_pos = PTA_LVecBase3f.empty_array(1)
        self._camera_pos.set_element(0, Vec3(0, 1.6, 0))
        render.set_shader_input('look_camera_pos', self._camera_pos)
        self._no_shadow_tex = _dummy_shadow_texture()
        self._identity_mats = PTA_LMatrix4f.empty_array(FACE_COUNT)
        for i in range(FACE_COUNT):
            self._identity_mats[i] = LMatrix4f.ident_mat()

        entities = [world[k] for k in MATERIALS]
        entities += [*world['stripes'], *world['posts'], *world['berms']]
        entities += [t.plate for t in targets]
        entities += list(decals.items)
        for e in entities:
            e.shader = self.shader
        for key, mat in MATERIALS.items():
            world[key].set_shader_input('look_material', mat)

        self._make_blobs(world, targets)
        self.halos = self._make_halos(world['lamps'], params) if params.lamp_halo > 0 else []
        self.mode = None
        self.set_shadow_mode(params.shadows)

        window.color = color.rgb(*params.fog_color)        # không có trời: nền (nếu lọt ra) cùng màu bụi trong phòng
        self.vignette = None
        if params.vignette > 0:
            self.vignette = Entity(parent=camera.ui, model='quad', texture=vignette_texture(), z=1,
                                   scale=(window.aspect_ratio, 1), color=color.rgba(1, 1, 1, params.vignette))   # tối ở góc = vignette
        # vẽ trước lúc dựng: dịch shader thế giới + vẽ atlas bóng không rơi vào khung đầu của game
        if self.shadows:
            self.shadows.render_now()
        else:
            application.base.graphicsEngine.render_frame()

    @staticmethod
    def _make_shader() -> Shader:
        vert = (SHADER_DIR / 'world.vert').read_text(encoding='utf-8')
        frag = (SHADER_DIR / 'world.frag').read_text(encoding='utf-8')
        return Shader(name='fps_world', language=Shader.GLSL, vertex=vert, fragment=frag,
                      default_input={'texture_scale': Vec2(1, 1), 'texture_offset': Vec2(0.0, 0.0)})

    def _make_blobs(self, world, targets):
        tex = blob_texture()
        spots = [(t.root.x, t.root.z, t.width * 1.6, 1.8) for t in targets]
        spots += [(e.x, e.z, 0.9, 1.3) for e in world['posts']]
        for x, z, sx, sz in spots:
            b = Entity(model='plane', texture=tex, position=(x, 0.002, z), scale=(sx, 1, sz), color=color.white, enabled=False,
                       shader=self.shader)
            b.set_transparency(TransparencyAttrib.M_alpha)
            b.set_depth_write(False)
            b.set_depth_offset(1)
            b.set_bin('transparent', 0)
            self.blobs.append(b)

    @staticmethod
    def _make_halos(lamps, params) -> list:
        """Một thẻ luôn quay về camera ở mỗi bóng đèn, trộn cộng, không ghi độ sâu (chóa đèn vẫn che được nó)."""
        tex = halo_texture()
        tint = color.rgba(*params.lamp_color, params.lamp_halo)
        out = []
        for x, y, z in lamps:
            e = Entity(model='quad', texture=tex, position=(x, y - 0.08, z), scale=1.6, color=tint, billboard=True)
            e.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha, ColorBlendAttrib.O_one))
            e.set_depth_write(False)
            e.set_bin('fixed', 5)
            out.append(e)
        return out

    def set_shadow_mode(self, mode):
        """True / 'fake' / False; đổi được lúc đang chạy (bóng thật dựng lần đầu khi cần)."""
        if mode is True and self.shadows is None:
            from fps.game.lamp_shadows import LampShadows
            self.shadows = LampShadows(self.world['lamps'], self.p.lamp_radius, self.p.shadow_face_size)
            for e in self.world['shadow_casters']:
                LampShadows.add_caster(e)
            for t in self.targets:
                LampShadows.add_caster(t.plate)
        render = application.base.render
        if mode is True:
            for k, v in self.shadows.shader_inputs().items():
                render.set_shader_input(k, v)
        else:
            render.set_shader_input('look_shadow_atlas', self._no_shadow_tex)
            render.set_shader_input('look_face_mat', self._identity_mats)
            render.set_shader_input('look_shadow_grid', Vec4(1, 1, 1, 1))
        bias_a, bias_b = self.p.shadow_bias
        render.set_shader_input('look_shadow', Vec4(SHADOW_MODES[mode], bias_a, bias_b, self.p.lamp_emissive))
        for b in self.blobs:
            b.enabled = mode == 'fake'
        self.mode = mode

    def update(self):
        """Mỗi khung: vị trí camera cho bụi trong phòng và độ mờ dần của chi tiết; tắt buffer bóng khi đã vẽ xong."""
        self._camera_pos.set_element(0, Vec3(*camera.world_position))
        if self.shadows:
            self.shadows.update()
