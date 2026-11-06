"""Giao diện hình ảnh của thế giới: shader (đèn trần, bóng, vân vật liệu, AO giả, bụi trong phòng), quầng đèn, bóng của bia chạy.

Shader thế giới nằm ở shaders/world.vert|frag (khung theo unlit_with_fog_shader của Ursina); phần ánh sáng dùng chung với súng ở shaders/light_common.glsl + frame_light.py. Áp lên mọi vật thể của trường bắn,
bia và lỗ đạn bằng cách đặt `Entity.shader`; vật liệu chọn bằng đầu vào `look_material` của từng Entity. Vật thể giao diện giữ
shader mặc định của Ursina. Số liệu ở weapon_data.LookData; kích thước phòng ở core/room.RoomLayout.

Bóng (`LookData.shadows`): True = bóng thật của mọi đèn trần (lamp_shadows.py, vẽ một lần lúc khởi động), 'fake' = vệt tối
mềm dưới bia và cột mốc, False = không bóng. AO giả (chân tường, quanh cột, dưới trần) có ở cả ba chế độ.
"""
import math
import random

from panda3d.core import (ColorBlendAttrib, OmniBoundingVolume, TransparencyAttrib, SamplerState, Vec2 as PandaVec2, Vec4)
from PIL import Image
from ursina import Entity, Mesh, Shader, Texture, application, color, time, window
from ursina.vec2 import Vec2

from fps.game.frame_light import FrameLight
from fps.game.shaders import load_glsl, read_source
from fps.weapon_data import LookData

MATERIALS = {'floor': 1.0, 'walls': 2.0, 'pillars': 3.0, 'ceiling': 4.0, 'lamp_glow': 5.0, 'lamp_shades': 0.0,
             'signs': 6.0, 'sign_rods': 0.0}      # 6 = biển khoảng cách (có chữ phát sáng nhẹ)


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


class WorldLook:
    def __init__(self, params: LookData, world: dict, targets: list, decals, light: FrameLight):
        self.p = params
        self.world = world
        self.targets = targets
        self.light = light
        self.shader = self._make_shader()
        self.shadows = None                 # LampShadows khi bật bóng thật
        self.blobs = []
        self.mover_blobs = []               # (bia chạy, vệt tối giả của nó): vệt đi theo bia
        self.movers = [t for t in targets if t.patrol is not None]
        self._mover_next = 0                # bia chạy kế tiếp được vẽ lại bóng
        self._mover_clock = 0.0
        self._mover_drawn_x = {}            # x của bia lúc vẽ bóng gần nhất: bia đứng im thì khỏi vẽ lại
        self.mover_shadow_refreshes = 0     # số lần vẽ lại bóng bia chạy (để đo)
        self._ready = False                 # False trong lúc dựng
        render = application.base.render
        room = world['room']

        render.set_shader_input('look_fog', (*params.fog_color, params.fog_density))
        render.set_shader_input('look_detail_strength', float(params.detail_strength))
        render.set_shader_input('look_detail_tex', noise_texture()._texture)
        render.set_shader_input('look_material', 0.0)
        render.set_shader_input('look_room', Vec4(room.half_width, room.z_back, room.z_end, room.height))
        render.set_shader_input('look_pillar', Vec4(room.pillar_z0, room.pillar_spacing, room.pillar_width / 2,
                                                    room.pillar_depth))
        self._push_flash(render)
        light.bind(render)

        entities = [world[k] for k in MATERIALS]
        entities += [*world['stripes'], *world['posts'], *world['berms']]
        entities += [t.plate for t in targets]
        entities += decals.entities
        for e in entities:
            e.shader = self.shader
        for key, mat in MATERIALS.items():
            world[key].set_shader_input('look_material', mat)

        self._make_blobs(world, targets)
        self.halos = self._make_halos(world['lamps'], params) if params.lamp_halo > 0 else None
        self.mode = None
        self.set_shadow_mode(params.shadows)

        window.color = color.rgb(*params.fog_color)        # không có trời: nền (nếu lọt ra) cùng màu bụi trong phòng
        # vẽ trước lúc dựng: dịch shader thế giới + vẽ atlas bóng không rơi vào khung đầu của game
        if self.shadows:
            self.shadows.render_now()
            # bia chạy vào atlas SAU lần vẽ đầu (để không để lại bóng ma ở chỗ xuất phát trên các đèn xa), rồi vẽ riêng các đèn gần chúng
            for t in self.movers:
                self.shadows.add_caster(t.plate)
            near = set()
            for t in self.movers:
                near.update(self._lamps_near_mover(t))
                self._mover_drawn_x[t] = t.root.x
            if near:
                self.shadows.render_lamps_now(near)
        else:
            application.base.graphicsEngine.render_frame()
        self._ready = True

    def _push_flash(self, node):
        flash = self.light.gun.flash
        node.set_shader_input('look_flash_world', PandaVec2(flash.world_power / max(flash.light_power, 0.01), flash.world_falloff))

    @staticmethod
    def _make_shader() -> Shader:
        vert, frag = read_source('world.vert'), read_source('world.frag')
        return Shader(name='fps_world', language=Shader.GLSL, vertex=vert, fragment=frag,
                      default_input={'texture_scale': Vec2(1, 1), 'texture_offset': Vec2(0.0, 0.0)})

    def _make_blobs(self, world, targets):
        tex = blob_texture()
        spots = [(t.root.x, t.root.z, t.width * 1.6, 1.8) for t in targets]
        spots += [(x, z, 0.9, 1.3) for x, z in world['post_spots']]
        for x, z, sx, sz in spots:
            b = Entity(model='plane', texture=tex, position=(x, 0.002, z), scale=(sx, 1, sz), color=color.white, enabled=False,
                       shader=self.shader)
            b.set_transparency(TransparencyAttrib.M_alpha)
            b.set_depth_write(False)
            b.set_depth_offset(1)
            b.set_bin('transparent', 0)
            self.blobs.append(b)
        for t, b in zip(targets, self.blobs):             # spots bắt đầu bằng các bia, cùng thứ tự
            if t.patrol is not None:
                self.mover_blobs.append((t, b))

    @staticmethod
    def _make_halos(lamps, params) -> Entity:
        """Quầng sáng của mọi bóng đèn trong MỘT lần vẽ: mỗi thẻ có 4 đỉnh nằm ở tâm đèn, shaders/halo.vert bung ra quay về camera. Trộn cộng, không ghi độ sâu."""
        verts, uvs, tris = [], [], []
        for x, y, z in lamps:
            n = len(verts)
            verts += [(x, y - 0.08, z)] * 4
            uvs += [(0, 0), (1, 0), (1, 1), (0, 1)]
            tris += [n, n + 1, n + 2, n, n + 2, n + 3]
        e = Entity(model=Mesh(vertices=verts, uvs=uvs, triangles=tris, static=True), texture=halo_texture(), add_to_scene_entities=False)
        e.setShader(load_glsl('halo'), 1)
        e.set_shader_input('halo_size', 1.6)
        e.set_shader_input('halo_color', Vec4(*params.lamp_color, params.lamp_halo))
        e.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha, ColorBlendAttrib.O_one))
        e.set_depth_write(False)
        e.set_two_sided(True)
        e.set_bin('fixed', 5)
        e.node().set_bounds(OmniBoundingVolume())
        e.node().set_final(True)
        return e

    def set_shadow_mode(self, mode):
        """True / 'fake' / False; đổi được lúc đang chạy (bóng thật dựng lần đầu khi cần)."""
        if mode is True and self.shadows is None:
            from fps.game.lamp_shadows import LampShadows
            self.shadows = LampShadows(self.world['lamps'], self.p.lamp_radius, self.p.shadow_face_size)
            for e in self.world['shadow_casters']:
                LampShadows.add_caster(e)
            for t in self.targets:
                if self._ready or t.patrol is None:          # lúc dựng: bia chạy vào atlas sau lần vẽ đầu (xem cuối __init__)
                    LampShadows.add_caster(t.plate)
        if mode is True:
            self._mover_drawn_x.clear()                      # atlas có thể giữ bóng cũ của bia chạy: vẽ lại ở các lượt kế tiếp
            self.light.radius = self.shadows.radius          # bán kính đã nướng vào bản đồ bóng
            self.light.set_shadows(mode, self.shadows.shader_inputs())
        else:
            self.light.set_shadows(mode)
        for b in self.blobs:
            b.enabled = mode == 'fake'
        self.mode = mode

    def apply_params(self):
        """Bảng debug (G6): đẩy lại các số ánh sáng của `LookData` có hiệu lực TỨC THÌ (đèn, tông màu, bụi, bóng, tối góc...) vào shader
        với đúng tên đầu vào như lúc dựng. Không đụng vị trí / số đèn và cỡ bản đồ bóng (nướng lúc dựng: cần khởi động lại)."""
        p, render = self.p, application.base.render
        render.set_shader_input('look_fog', (*p.fog_color, p.fog_density))
        render.set_shader_input('look_detail_strength', float(p.detail_strength))
        self._push_flash(render)
        self.set_shadow_mode(p.shadows)                      # cũng đẩy lại look_shadow (chống sọc bóng, độ chói bóng đèn)
        self.light.apply_params()
        window.color = color.rgb(*p.fog_color)
        if self.halos is not None:
            self.halos.set_shader_input('halo_color', Vec4(*p.lamp_color, p.lamp_halo))

    def _lamps_near_mover(self, target) -> list:
        """Các đèn cần vẽ lại bóng khi bia chạy đổi chỗ: đèn cách bia dọc z trong `mover_shadow_reach` x bán kính đèn."""
        z = target.root.z
        return self.shadows.lamps_near(z, z, self.p.mover_shadow_reach * self.shadows.radius)

    def _faces_for_mover(self, target, old_x: float) -> dict:
        """Đèn -> các mặt cubemap có thể nhìn thấy bia (ở chỗ cũ hoặc chỗ mới): chỉ vẽ lại những mặt đó, rẻ hơn hẳn vẽ cả 5 mặt."""
        half = target.width / 2.0
        x0, x1 = min(old_x, target.root.x) - half, max(old_x, target.root.x) + half
        z = target.root.z
        out = {}
        for i in self._lamps_near_mover(target):
            lx, _, lz = self.shadows.lamps[i]
            faces = [2]                                      # -y: luôn có, bia đứng dưới đèn
            if x1 > lx:
                faces.append(0)                              # +x
            if x0 < lx:
                faces.append(1)                              # -x
            if z + 0.1 > lz:
                faces.append(3)                              # +z
            if z - 0.1 < lz:
                faces.append(4)                              # -z
            out[i] = faces
        return out

    def _tick_movers(self):
        """Bóng thật của bia chạy: đèn và tường đứng yên nên atlas chỉ vẽ một lần, còn bia chạy thì cứ 1/(hz x số bia) giây vẽ lại
        riêng các đèn gần MỘT bia (lần lượt từng bia). Gọi từ `update` (trước khi vẽ), nên atlas vẽ ở đúng khung đó."""
        if self.mode is not True or not self.movers or self.p.mover_shadow_hz <= 0:
            return
        self._mover_clock += time.dt
        interval = 1.0 / (self.p.mover_shadow_hz * len(self.movers))
        if self._mover_clock < interval:
            return
        self._mover_clock = min(self._mover_clock - interval, interval)
        for _ in range(len(self.movers)):                    # bia kế tiếp CÓ đổi chỗ từ lần vẽ trước
            t = self.movers[self._mover_next % len(self.movers)]
            self._mover_next += 1
            old = self._mover_drawn_x.get(t)
            if old is None or abs(t.root.x - old) > 1e-4:
                self._mover_drawn_x[t] = t.root.x
                self.shadows.refresh_faces(self._faces_for_mover(t, t.root.x if old is None else old))
                self.mover_shadow_refreshes += 1
                return

    def update(self):
        """Mỗi khung: tắt buffer bóng khi đã vẽ xong; bóng của bia chạy (thật: vẽ lại đèn gần; giả: vệt tối đi theo bia)."""
        if self.shadows:
            self.shadows.update()
            self._tick_movers()
        if self.mode == 'fake':
            for t, b in self.mover_blobs:
                b.x = t.root.x
