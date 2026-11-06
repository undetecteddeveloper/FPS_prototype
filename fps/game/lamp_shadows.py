"""Bóng thật của các đèn trần: mỗi đèn một cubemap 5 mặt (bỏ mặt hướng lên trần), mọi mặt của mọi đèn xếp thành các ô
trong MỘT kết cấu độ sâu (atlas, xem core/room.py). shaders/world.frag lấy mẫu atlas này bằng so sánh độ sâu phần cứng
(sampler2DShadow) + 4 mẫu PCF.

Đèn và tường đứng yên nên atlas chỉ VẼ MỘT LẦN lúc khởi động (115 mặt, vài ms), sau đó buffer tắt: mỗi khung chỉ còn chi
phí lấy mẫu trong shader. Vật thể di chuyển (bia chạy ở G6) gọi `refresh(z_min, z_max)` để vẽ lại riêng các đèn gần đó
trong khung kế tiếp.

Chỉ vật thể được đánh dấu `add_caster` mới đổ bóng (tường, cột, dầm, bia, cột mốc, bờ đất); sàn, trần, đèn, lỗ đạn, súng
thì không. Camera bóng vẽ MẶT SAU của vật thể (cull ngược) nên mặt được chiếu sáng so với mặt sau của chính nó: hết "acne".
"""
from panda3d.core import (BitMask32, Camera, ColorWriteAttrib, CullFaceAttrib, FrameBufferProperties, GraphicsOutput,
                          GraphicsPipe, LMatrix4f, NodePath, PerspectiveLens, PTA_LMatrix4f, SamplerState, Shader,
                          Texture, Vec3, WindowProperties)
from ursina import application

from fps.core.room import FACE_COUNT, FACES, atlas_grid, face_fov, tile_index, tile_rect
from fps.game.shaders import SHADER_DIR

SHADOW_MASK = BitMask32.bit(7)       # camera bóng chỉ thấy các nút có bit này (show_through); camera chính không bị ảnh hưởng
GUARD_PX = 2                         # viền mỗi bên của một mặt (điểm ảnh) cho 4 mẫu PCF ở mép
NEAR = 0.05


def _depth_shader() -> Shader:
    vert = (SHADER_DIR / 'shadow_depth.vert').read_text(encoding='utf-8')
    frag = (SHADER_DIR / 'shadow_depth.frag').read_text(encoding='utf-8')
    return Shader.make(Shader.SL_GLSL, vert, frag)


def _face_up(direction):
    return (0, 0, 1) if direction[1] != 0 else (0, 1, 0)


class LampShadows:
    def __init__(self, lamps: list, radius: float, face_size: int):
        base = application.base
        render = base.render
        self.lamps = lamps
        self.radius = radius
        self.face_size = face_size
        self.cols, self.rows = atlas_grid(len(lamps) * FACE_COUNT)
        width, height = self.cols * face_size, self.rows * face_size

        fbp = FrameBufferProperties()
        fbp.set_depth_bits(24)
        fbp.set_rgb_color(False)
        fbp.set_rgba_bits(0, 0, 0, 0)
        self.buffer = base.graphicsEngine.make_output(
            base.pipe, 'lamp_shadows', -10, fbp, WindowProperties.size(width, height), GraphicsPipe.BF_refuse_window,
            base.win.get_gsg(), base.win)
        if self.buffer is None:
            raise RuntimeError('không tạo được buffer cho bản đồ bóng')
        self.texture = Texture('lamp_shadow_atlas')
        self.buffer.add_render_texture(self.texture, GraphicsOutput.RTM_bind_or_copy, GraphicsOutput.RTP_depth)
        self.texture.set_minfilter(SamplerState.FT_shadow)          # so sánh độ sâu phần cứng (sampler2DShadow), có lọc song tuyến
        self.texture.set_magfilter(SamplerState.FT_shadow)
        self.texture.set_wrap_u(SamplerState.WM_clamp)
        self.texture.set_wrap_v(SamplerState.WM_clamp)
        self.buffer.disable_clears()                                 # mỗi ô tự xoá (vẽ lại vài đèn không xoá các đèn khác)
        self.atlas_size = (width, height)

        # trạng thái chung của mọi camera bóng: shader chỉ ghi độ sâu, không ghi màu, vẽ mặt sau; đè mọi shader/thuộc tính của vật thể
        holder = NodePath('shadow_state')
        holder.set_shader(_depth_shader(), 1000)
        holder.set_attrib(ColorWriteAttrib.make(ColorWriteAttrib.C_off), 1000)
        holder.set_attrib(CullFaceAttrib.make_reverse(), 1000)
        holder.set_texture_off(1000)
        state = holder.get_state()

        self.lens = PerspectiveLens()
        fov = face_fov(face_size, GUARD_PX)
        self.lens.set_fov(fov, fov)
        self.lens.set_near_far(NEAR, radius + 1.0)

        render.hide(SHADOW_MASK)                                     # mặc định không đổ bóng; add_caster bật lại
        self.rig = render.attach_new_node('lamp_shadow_rig')
        self.regions = []                                            # [lamp] -> [display region của từng mặt]
        for i, pos in enumerate(lamps):
            regs = []
            for f, d in enumerate(FACES):
                cam = Camera(f'lamp{i}_face{f}', self.lens)
                cam.set_camera_mask(SHADOW_MASK)
                cam.set_initial_state(state)
                cam_np = self.rig.attach_new_node(cam)
                cam_np.set_pos(Vec3(*pos))
                cam_np.look_at(Vec3(*(p + c for p, c in zip(pos, d))), Vec3(*_face_up(d)))
                l, r, b, t = tile_rect(tile_index(i, f), self.cols, self.rows)
                dr = self.buffer.make_display_region(l, r, b, t)
                dr.set_camera(cam_np)
                dr.set_clear_depth_active(True)
                dr.set_clear_depth(1.0)
                regs.append(dr)
            self.regions.append(regs)

        # ma trận "vector đèn -> điểm (thế giới)" sang clip của từng mặt: chung cho mọi đèn (chỉ khác vị trí)
        self.face_mats = PTA_LMatrix4f.empty_array(FACE_COUNT)
        probe = NodePath('probe')
        proj = self.lens.get_projection_mat()
        for f, d in enumerate(FACES):
            probe.set_pos(0, 0, 0)
            probe.look_at(Vec3(*d), Vec3(*_face_up(d)))
            view = LMatrix4f(probe.get_mat())
            view.invert_in_place()
            self.face_mats[f] = view * proj
        self._frames_left = 2                                         # vẽ ở khung đầu (thêm một khung cho chắc) rồi tắt
        self.render_count = 0

    @staticmethod
    def add_caster(nodepath):
        nodepath.show_through(SHADOW_MASK)

    def lamps_near(self, z_min: float, z_max: float, reach: float = None) -> list:
        """Chỉ số các đèn mà vùng chiếu (bán kính `reach`, mặc định `radius`) chạm đoạn [z_min, z_max]."""
        reach = self.radius if reach is None else reach
        return [i for i, (_, _, z) in enumerate(self.lamps) if z + reach >= z_min and z - reach <= z_max]

    def refresh(self, z_min: float = None, z_max: float = None, reach: float = None):
        """Vẽ lại ngay trong khung này (gọi trong phần update, TRƯỚC khi vẽ) các đèn mà vùng chiếu chạm đoạn [z_min, z_max];
        không truyền gì thì vẽ lại tất cả. `reach` < bán kính đèn thì bỏ qua các đèn ở rìa, nơi ánh sáng gần như tắt.
        Chỉ vẽ MỘT khung (gọi liên tiếp mỗi khung thì vẽ mỗi khung)."""
        self.refresh_lamps(range(len(self.lamps)) if z_min is None else self.lamps_near(z_min, z_max, reach))

    def refresh_lamps(self, indices):
        """Như `refresh` nhưng theo chỉ số đèn (gộp nhiều đoạn z: gọi với hợp các `lamps_near`)."""
        wanted = set(indices)
        for i in range(len(self.lamps)):
            for dr in self.regions[i]:
                dr.set_active(i in wanted)
        self.buffer.set_active(True)
        self.render_count += 1
        self._frames_left = 0                # khung này vẽ rồi; khung sau `update` tự tắt buffer (trừ khi lại có refresh)

    def refresh_faces(self, faces: dict):
        """Như `refresh_lamps` nhưng chỉ các mặt được kể tên: {chỉ số đèn: [mặt, ...]}."""
        for i in range(len(self.lamps)):
            wanted = faces.get(i, ())
            for f, dr in enumerate(self.regions[i]):
                dr.set_active(f in wanted)
        self.buffer.set_active(True)
        self.render_count += 1
        self._frames_left = 0

    def render_lamps_now(self, indices):
        """Vẽ các đèn này NGAY (lúc dựng game), rồi tắt buffer: để vẽ bù những vật thêm vào atlas sau `render_now`."""
        self.refresh_lamps(indices)
        engine = application.base.graphicsEngine
        engine.render_frame()
        engine.render_frame()
        self._frames_left = 0
        self.buffer.set_active(False)

    def render_now(self):
        """Vẽ atlas NGAY (lúc dựng game, trước vòng lặp) rồi tắt buffer: khung đầu của game không phải gánh ~0,5 s vẽ
        115 mặt + dịch shader (khung đó rơi vào lúc rút súng và làm clip rút súng nhảy cóc)."""
        engine = application.base.graphicsEngine
        engine.render_frame()
        engine.render_frame()
        self.render_count += 1
        self._frames_left = 0
        self.buffer.set_active(False)

    def update(self):
        """Gọi mỗi khung (trước khi vẽ). Tắt buffer khi đã vẽ xong lượt được yêu cầu."""
        if self._frames_left > 0:
            self._frames_left -= 1
            self.render_count += 1
        elif self.buffer.is_active():
            self.buffer.set_active(False)

    def shader_inputs(self) -> dict:
        w, h = self.atlas_size
        return {'look_shadow_atlas': self.texture, 'look_face_mat': self.face_mats,
                'look_shadow_grid': (float(self.cols), float(self.rows), 1.0 / w, 1.0 / h)}
