"""Hiệu ứng bắn: tia lửa đầu nòng (trong cảnh súng) và tracer (trong thế giới).

Tia lửa: ngôi sao hướng về camera + hai tấm chéo dọc nòng, trộn cộng (additive), kèm một đèn điểm chiếu sáng súng và tay
(đẩy vào shader của súng qua `Viewmodel.set_flash_light`). Gắn vào nút `sway` nên đi theo kick, sway, ngắm của súng.
Tracer: vệt sáng bám sau viên đạn thật (cùng vị trí, cùng độ rơi), xuất phát từ miệng nòng rồi hội tụ về đường đạn từ mắt.
Texture dựng bằng mã lúc khởi động (không tải tài nguyên ngoài). Số liệu ở weapon_data.FlashData / TracerData; toán ở core/fx.py.
"""
import math
import random

from panda3d.core import CardMaker, ColorBlendAttrib, Mat4, NodePath, SamplerState, Vec3
from PIL import Image
from ursina import Texture, application, camera, window

from fps.core import fx
from fps.core.movement import smoothstep
from fps.weapon_data import GunData

BIN_FIXED = 'fixed'


# --- texture dựng bằng mã ---
def _rgba_image(w: int, h: int, pixel) -> Image.Image:
    img = Image.new('RGBA', (w, h))
    img.putdata([pixel(x, y) for y in range(h) for x in range(w)])
    return img


def _gl_texture(img: Image.Image) -> NodePath:
    tex = Texture(img)
    t = tex._texture
    t.set_wrap_u(SamplerState.WM_clamp)
    t.set_wrap_v(SamplerState.WM_clamp)
    return t


def star_texture(size: int = 128):
    """Ngôi sao chớp nòng: lõi trắng nóng, quầng cam, sáu tia dài và bốn tia ngắn lệch góc."""
    def pixel(x, y):
        u, v = (x + 0.5) / size * 2 - 1, (size - y - 0.5) / size * 2 - 1
        r, th = math.hypot(u, v), math.atan2(v, u)
        core = math.exp(-(r / 0.20) ** 2)
        halo = 0.38 * math.exp(-(r / 0.52) ** 2)
        long_rays = abs(math.cos(3 * th + 0.35)) ** 40 * (1 - min(r, 1)) ** 1.5
        short_rays = abs(math.cos(2 * th + 0.8)) ** 60 * (1 - min(r, 1)) ** 2 * 0.55
        edge = 1.0 - smoothstep((r - 0.80) / 0.20)
        a = min(1.0, core + halo + long_rays * 0.95 + short_rays) * edge
        return (255, int(255 * (0.92 - 0.30 * r)), int(255 * (0.70 - 0.55 * r)), int(255 * a))
    return _gl_texture(_rgba_image(size, size, pixel))


def flame_texture(w: int = 48, h: int = 128):
    """Ngọn lửa dọc nòng: v = 0 ở miệng nòng, v = 1 ở chóp; rộng ở gốc, thon dần."""
    def pixel(x, y):
        u, t = (x + 0.5) / w * 2 - 1, 1 - (y + 0.5) / h
        width = 0.62 * (1 - t) ** 0.55 + 0.05
        a = math.exp(-((u / width) ** 2) * 2.4) * (1 - t) ** 1.2
        return (255, int(255 * (0.90 - 0.4 * t)), int(255 * (0.62 - 0.5 * t)), int(255 * min(a, 1.0)))
    return _gl_texture(_rgba_image(w, h, pixel))


def glow_texture(head_color, size: int = 64):
    """Chấm sáng ở đầu tracer: lõi trắng nóng, quầng mềm."""
    def pixel(x, y):
        u, v = (x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1
        r = math.hypot(u, v)
        a = (math.exp(-(r / 0.30) ** 2) + 0.35 * math.exp(-(r / 0.65) ** 2)) * (1.0 - smoothstep((r - 0.8) / 0.2))
        return (*(int(255 * c) for c in head_color), int(255 * min(a, 1.0)))
    return _gl_texture(_rgba_image(size, size, pixel))


def tracer_texture(head_color, tail_color, w: int = 64, h: int = 16):
    """Vệt tracer: u = 0 ở đuôi (mờ, cam) -> u = 1 ở đầu (sáng, trắng nóng); v là mặt cắt mềm."""
    def pixel(x, y):
        u, v = (x + 0.5) / w, (y + 0.5) / h * 2 - 1
        body = (0.12 + 0.88 * u ** 1.6) * math.exp(-(v ** 2) * 4.5)
        glint = math.exp(-(((1 - u) / 0.05) ** 2)) * math.exp(-(v ** 2) * 2.5)
        a = min(1.0, body + glint)
        k = u ** 1.5
        rgb = [int(255 * (tail_color[i] + (head_color[i] - tail_color[i]) * k)) for i in range(3)]
        return (*rgb, int(255 * a))
    return _gl_texture(_rgba_image(w, h, pixel))


def _additive(node: NodePath):
    """Trộn cộng, không ghi độ sâu, không đèn, không shader: hiệu ứng sáng chồng lên cảnh."""
    node.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha, ColorBlendAttrib.O_one))
    node.set_depth_write(False)
    node.set_light_off()
    node.set_shader_off()
    node.set_two_sided(True)
    node.set_bin(BIN_FIXED, 40)


def _card(parent: NodePath, name: str, frame: tuple, texture) -> NodePath:
    cm = CardMaker(name)
    cm.set_frame(*frame)
    np_ = parent.attach_new_node(cm.generate())
    np_.set_texture(texture)
    return np_


# --- tia lửa đầu nòng ---
class MuzzleFlash:
    def __init__(self, viewmodel, gun: GunData, rng: random.Random):
        self.vm = viewmodel
        self.data = gun.flash
        self.rng = rng
        mx, my, mz = (a + b for a, b in zip(gun.muzzle, gun.hip_offset))
        self.muzzle = viewmodel.sway.attach_new_node('muzzle')
        self.muzzle.set_pos(mx, my, mz)
        self.root = self.muzzle.attach_new_node('muzzle_flash')
        self.root.set_pos(0, 0, self.data.forward)
        _additive(self.root)

        # CardMaker dựng thẻ trong mặt phẳng XY cục bộ (x = ngang, y = dọc, pháp tuyến +z) vì Ursina dùng hệ y-up; trục nòng là +z.
        # Thẻ được đặt bằng ma trận tường minh (hàng 0 = ảnh của trục ngang, hàng 1 = ảnh của trục dọc, hàng 2 = pháp tuyến):
        #   ngôi sao: mặt phẳng vuông góc trục nòng (người chơi nhìn dọc trục nòng từ phía sau), quay quanh trục nòng
        #   hai tấm dọc nòng: cùng chứa trục nòng, lệch nhau 90 độ
        self.star = _card(self.root, 'star', (-0.5, 0.5, -0.5, 0.5), star_texture())
        flame = flame_texture()
        self.flames = [_card(self.root, f'flame{i}', (-0.5, 0.5, 0.0, 1.0), flame) for i in range(2)]   # dọc: 0 ở nòng .. 1 ở chóp
        self._roll = 0.0
        self.root.hide()

        self.age = None                                    # None = đang tắt
        self._fresh = False
        self._size = 1.0
        self.fired = 0                                     # số lần chớp (cho kiểm tra)

    @property
    def active(self) -> bool:
        return self.age is not None

    def fire(self, ads_amount: float):
        d = self.data
        ads = 1.0 + (d.ads_scale - 1.0) * smoothstep(ads_amount)
        self._size = ads * (1.0 + self.rng.uniform(-d.size_jitter, d.size_jitter))
        self._roll = self.rng.uniform(0, 2 * math.pi)
        self.age = 0.0
        self._fresh = True                                 # khung chớp: vẽ cường độ đầy đủ, chưa trừ tuổi
        self.fired += 1
        self.root.show()

    def update(self, dt: float):
        d = self.data
        if self.age is None:
            return
        if self._fresh:
            self._fresh = False
        else:
            self.age += dt
        k = fx.flash_envelope(self.age, d.life)
        if k <= 0.0:
            self.age = None
            self.root.hide()
            self.vm.set_flash_light(self.muzzle.get_pos(self.vm.cam_np), (0, 0, 0))
            return
        r, g, b = d.color
        for n in (self.star, *self.flames):
            n.set_color_scale(r, g, b, k)
        shrink = 1.0 - 0.3 * (self.age / d.life)
        size = d.size * self._size * shrink
        c, sn = math.cos(self._roll), math.sin(self._roll)
        self.star.set_mat(Mat4(c * size, sn * size, 0, 0, -sn * size, c * size, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1))
        w = d.width * self._size * shrink
        length = d.length * self._size * (0.6 + 0.4 * k)
        # thẻ 0: rộng theo (c, sn, 0); thẻ 1: rộng theo (-sn, c, 0); cả hai dài theo +z (trục nòng)
        self.flames[0].set_mat(Mat4(c * w, sn * w, 0, 0, 0, 0, length, 0, -sn, c, 0, 0, 0, 0, 0, 1))
        self.flames[1].set_mat(Mat4(-sn * w, c * w, 0, 0, 0, 0, length, 0, -c, -sn, 0, 0, 0, 0, 0, 1))
        light = tuple(ch * d.light_power * k for ch in d.light_color)
        self.vm.set_flash_light(self.muzzle.get_pos(self.vm.cam_np) + Vec3(0, 0, d.forward), light)


# --- tracer ---
class _Streak:
    __slots__ = ('tracer', 'bullet', 'node', 'glow')

    def __init__(self, tracer, bullet, node, glow):
        self.tracer, self.bullet, self.node, self.glow = tracer, bullet, node, glow


class Tracers:
    def __init__(self, gun: GunData):
        self.data = gun.tracer
        self.speed = gun.muzzle_velocity
        d = self.data
        self.root = application.base.render.attach_new_node('tracers')
        _additive(self.root)
        tex = tracer_texture(d.head_color, d.tail_color)
        glow_tex = glow_texture(d.glow_color)
        self.free = []                                     # [(vệt, chấm sáng)]
        for i in range(d.pool):
            node = _card(self.root, f'tracer{i}', (0.0, 1.0, -0.5, 0.5), tex)
            glow = _card(self.root, f'glow{i}', (-0.5, 0.5, -0.5, 0.5), glow_tex)
            node.hide()
            glow.hide()
            self.free.append((node, glow))
        self.active = []
        self._right = self._up = Vec3(0, 0, 0)
        self.spawned = 0                                   # số tracer đã sinh (cho kiểm tra)

    def spawn(self, bullet, offset: tuple) -> bool:
        if not self.free:
            return False
        d = self.data
        tracer = fx.Tracer(offset, d.length, d.blend_distance, self.speed)
        self.active.append(_Streak(tracer, bullet, *self.free.pop()))
        self.spawned += 1
        return True

    def update(self, dt: float):
        if not self.active:
            return
        d = self.data
        cam = Vec3(*camera.world_position)
        self._right, self._up = Vec3(*camera.right), Vec3(*camera.up)
        fov, width_px = camera.fov, window.size[0]
        keep = []
        for s in self.active:
            b, t = s.bullet, s.tracer
            speed = math.sqrt(sum(c * c for c in b.vel)) or 1.0
            direction = tuple(c / speed for c in b.vel)
            here = b.pos if b.alive else b.end_pos
            travelled = math.dist(b.origin, here)
            if b.alive and travelled <= d.max_range:
                t.follow(b.pos, direction, travelled)
            elif not t.ended:
                t.end(here, direction, travelled)
            t.advance(dt)
            if t.done:
                s.node.hide()
                s.glow.hide()
                self.free.append((s.node, s.glow))
                continue
            keep.append(s)
            self._place(s, cam, fov, width_px)
        self.active = keep

    def _place(self, streak: _Streak, cam: Vec3, fov: float, width_px: float):
        d = self.data
        node, glow = streak.node, streak.glow
        tail, head = (Vec3(*p) for p in streak.tracer.endpoints())
        # chấm sáng luôn hướng về camera: ma trận tường minh (billboard của Panda làm khung đầu tiên chậm 40-70 ms)
        size = fx.ribbon_width((cam - head).length(), 0.0, d.glow_pixels, fov, width_px)
        r, u = self._right * size, self._up * size
        glow.set_mat(Mat4(r.x, r.y, r.z, 0, u.x, u.y, u.z, 0, 0, 0, 1, 0, head.x, head.y, head.z, 1))
        glow.set_color_scale(1, 1, 1, d.intensity * (0.0 if streak.tracer.ended else 1.0))
        glow.show()
        axis = head - tail
        length = axis.length()
        if length < 1e-3:
            node.hide()
            return
        ux = axis / length
        view = cam - (head + tail) * 0.5
        across = view.cross(ux)
        if across.length() < 1e-4:                         # nhìn dọc theo vệt: chọn tuỳ ý một hướng vuông góc
            across = Vec3(0, 1, 0).cross(ux)
        across.normalize()
        normal = ux.cross(across)
        width = fx.ribbon_width(view.length(), d.width, d.min_pixels, fov, width_px)
        node.set_mat(Mat4(ux.x * length, ux.y * length, ux.z * length, 0,
                          across.x * width, across.y * width, across.z * width, 0,
                          normal.x, normal.y, normal.z, 0,
                          tail.x, tail.y, tail.z, 1))
        node.set_color_scale(1, 1, 1, d.intensity)
        node.show()


class Effects:
    """Cầu nối của Combat: mỗi phát bắn gọi `on_shot`, mỗi khung gọi `update`."""

    def __init__(self, gun: GunData, viewmodel, rng: random.Random = None):
        self.gun = gun
        self.vm = viewmodel
        self.flash = MuzzleFlash(viewmodel, gun, rng or random.Random())
        self.tracers = Tracers(gun)
        self.burst = 0                                     # phát thứ mấy của loạt hiện tại
        self._rest = 1e9                                   # giây kể từ phát cuối
        self._warm_up()

    def _warm_up(self):
        """Vẽ thử mọi hiệu ứng (rất nhỏ, gần trong suốt) vài khung đầu để texture và trạng thái vẽ lên GPU ngay lúc vào game.
        Không làm thì phát bắn ĐẦU TIÊN làm hai khung liền chậm 25-40 ms (và vì đạn đi theo từng khung nên điểm trúng lệch vài mm).
        `prepare_scene` không đủ: nút ẩn bị bỏ qua."""
        self._warm = 3
        tiny = Mat4(0.001, 0, 0, 0, 0, 0.001, 0, 0, 0, 0, 0.001, 0, 0, 0, 0, 1)
        self.flash.root.show()
        for n in (self.flash.star, *self.flash.flames):
            n.set_mat(tiny)
            n.set_color_scale(1, 1, 1, 1.0)
        for node, glow in self.tracers.free:
            for n in (node, glow):
                n.set_mat(Mat4(0.001, 0, 0, 0, 0, 0.001, 0, 0, 0, 0, 0.001, 0, 0, 1.6, 3.0, 1))
                n.set_color_scale(1, 1, 1, 1.0)
                n.show()

    def _end_warm_up(self):
        self.flash.root.hide()
        for node, glow in self.tracers.free:
            node.hide()
            glow.hide()

    def muzzle_offset(self) -> tuple:
        """Miệng nòng so với mắt, trong toạ độ thế giới. Đo trong cảnh súng (FOV riêng) nên nhân hệ số ống kính để
        điểm xuất phát của vệt nằm đúng chỗ miệng nòng đang hiện trên màn hình."""
        p = self.flash.muzzle.get_pos(self.vm.cam_np)
        k = fx.lens_ratio(camera.fov, self.vm.current_fov)
        v = camera.right * (p.x * k) + camera.up * (p.y * k) + camera.forward * p.z
        return (v[0], v[1], v[2])

    def on_shot(self, bullet, ads_amount: float):
        self.burst = 1 if self._rest > self.gun.tracer.burst_reset else self.burst + 1
        self._rest = 0.0
        self.flash.fire(ads_amount)
        if fx.is_traced(self.burst, self.gun.tracer.every):
            self.tracers.spawn(bullet, self.muzzle_offset())

    def update(self, dt: float):
        if self._warm:
            self._warm -= 1
            if not self._warm:
                self._end_warm_up()
        self._rest += dt
        self.flash.update(dt)
        self.tracers.update(dt)
