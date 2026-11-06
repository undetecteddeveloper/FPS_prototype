"""Shot effects: muzzle flash (inside the gun view) and tracers (in the world).

Flash: a star facing the camera + two crossed planes along the barrel, additive blend, plus a point light that lights the gun and hands
(pushed into the gun shader via `Viewmodel.set_flash_light`). Attached to the `sway` node so it follows the gun's kick, sway and aim.
Tracer: a light streak trailing the real bullet (same position, same drop), starting at the muzzle and converging on the bullet path from the eye.
Textures are built in code at startup (no external assets). Values live in weapon_data.FlashData / TracerData; the maths is in core/fx.py.
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


# --- textures built in code ---
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
    """Muzzle-flash star: hot white core, orange halo, six long rays and four short rays at offset angles."""
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
    """Flame along the barrel: v = 0 at the muzzle, v = 1 at the tip; wide at the base, tapering."""
    def pixel(x, y):
        u, t = (x + 0.5) / w * 2 - 1, 1 - (y + 0.5) / h
        width = 0.62 * (1 - t) ** 0.55 + 0.05
        a = math.exp(-((u / width) ** 2) * 2.4) * (1 - t) ** 1.2
        return (255, int(255 * (0.90 - 0.4 * t)), int(255 * (0.62 - 0.5 * t)), int(255 * min(a, 1.0)))
    return _gl_texture(_rgba_image(w, h, pixel))


def glow_texture(head_color, size: int = 64):
    """Bright dot at the tracer head: hot white core, soft halo."""
    def pixel(x, y):
        u, v = (x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1
        r = math.hypot(u, v)
        a = (math.exp(-(r / 0.30) ** 2) + 0.35 * math.exp(-(r / 0.65) ** 2)) * (1.0 - smoothstep((r - 0.8) / 0.2))
        return (*(int(255 * c) for c in head_color), int(255 * min(a, 1.0)))
    return _gl_texture(_rgba_image(size, size, pixel))


def tracer_texture(head_color, tail_color, w: int = 64, h: int = 16):
    """Tracer streak: u = 0 at the tail (dim, orange) -> u = 1 at the head (bright, hot white); v is the soft cross-section."""
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
    """Additive blend, no depth write, no lights, no shader: the glowing effect is stacked on top of the scene."""
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


# --- muzzle flash ---
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

        # CardMaker builds the card in the local XY plane (x = horizontal, y = vertical, normal +z) because Ursina uses y-up; the barrel axis is +z.
        # Cards are placed with an explicit matrix (row 0 = image of the horizontal axis, row 1 = image of the vertical axis, row 2 = normal):
        #   star: plane perpendicular to the barrel axis (the player looks down the barrel from behind), rotates around the barrel axis
        #   two planes along the barrel: both contain the barrel axis, 90 degrees apart
        self.star = _card(self.root, 'star', (-0.5, 0.5, -0.5, 0.5), star_texture())
        flame = flame_texture()
        self.flames = [_card(self.root, f'flame{i}', (-0.5, 0.5, 0.0, 1.0), flame) for i in range(2)]   # along: 0 at the muzzle .. 1 at the tip
        self._roll = 0.0
        self.root.hide()

        self.age = None                                    # None = off
        self._fresh = False
        self._size = 1.0
        self.fired = 0                                     # number of flashes (for checks)

    @property
    def active(self) -> bool:
        return self.age is not None

    def fire(self, ads_amount: float):
        d = self.data
        ads = 1.0 + (d.ads_scale - 1.0) * smoothstep(ads_amount)
        self._size = ads * (1.0 + self.rng.uniform(-d.size_jitter, d.size_jitter))
        self._roll = self.rng.uniform(0, 2 * math.pi)
        self.age = 0.0
        self._fresh = True                                 # flash frame: draw full intensity, age not yet subtracted
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
        # card 0: wide along (c, sn, 0); card 1: wide along (-sn, c, 0); both long along +z (barrel axis)
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
        self.gun = gun                                     # bullet speed is read back on every streak spawn (the debug panel can change muzzle_velocity while running)
        d = self.data
        self.root = application.base.render.attach_new_node('tracers')
        _additive(self.root)
        tex = tracer_texture(d.head_color, d.tail_color)
        glow_tex = glow_texture(d.glow_color)
        self.free = []                                     # [(streak, glow dot)]
        for i in range(d.pool):
            node = _card(self.root, f'tracer{i}', (0.0, 1.0, -0.5, 0.5), tex)
            glow = _card(self.root, f'glow{i}', (-0.5, 0.5, -0.5, 0.5), glow_tex)
            node.hide()
            glow.hide()
            self.free.append((node, glow))
        self.active = []
        self._right = self._up = Vec3(0, 0, 0)
        self.spawned = 0                                   # number of tracers spawned (for checks)

    def spawn(self, bullet, offset: tuple) -> bool:
        if not self.free:
            return False
        d = self.data
        tracer = fx.Tracer(offset, d.length, d.blend_distance, self.gun.muzzle_velocity)
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
        # glow dot always faces the camera: explicit matrix (Panda's billboard made the first frame slow, 40-70 ms)
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
        if across.length() < 1e-4:                         # looking along the streak: pick any perpendicular direction
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
    """Combat's bridge: each shot calls `on_shot`, each frame calls `update`."""

    def __init__(self, gun: GunData, viewmodel, rng: random.Random = None):
        self.gun = gun
        self.vm = viewmodel
        self.flash = MuzzleFlash(viewmodel, gun, rng or random.Random())
        self.tracers = Tracers(gun)
        self.burst = 0                                     # which shot of the current burst this is
        self._rest = 1e9                                   # seconds since the last shot
        self._warm_up()

    def _warm_up(self):
        """Draw every effect (tiny, nearly transparent) for the first few frames so textures and draw state reach the GPU as the game starts.
        Without this the FIRST shot makes two consecutive frames slow, 25-40 ms (and since bullets move per frame, the hit point is off by a few mm).
        `prepare_scene` is not enough: hidden nodes are skipped."""
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
        """Muzzle position relative to the eye, in world coordinates. Measured in the gun scene (its own FOV), so it is multiplied by the lens factor so that
        the streak's start point lies exactly where the muzzle appears on screen."""
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
