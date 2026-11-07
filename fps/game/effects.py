"""Shot effects: muzzle light, gun smoke and tracers.

Flash: ONLY a short point light at the muzzle that lights the gun, hands and the ground (pushed into the gun shader via `Viewmodel.set_flash_light`); the old
star / flame cards looked fake and were removed. What a shot shows is the gunpowder smoke (game/smoke.py, world space) blown out of the muzzle and the ejection port.
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


# --- muzzle flash: only a short light now (the visible part of a shot is the gun smoke, game/smoke.py) ---
class MuzzleFlash:
    def __init__(self, viewmodel, gun: GunData, rng: random.Random):
        self.vm = viewmodel
        self.data = gun.flash
        self.rng = rng
        mx, my, mz = (a + b for a, b in zip(gun.muzzle, gun.hip_offset))
        self.muzzle = viewmodel.sway.attach_new_node('muzzle')
        self.muzzle.set_pos(mx, my, mz)
        self.age = None                                    # None = off
        self._fresh = False
        self.fired = 0                                     # number of flashes (for checks)

    @property
    def active(self) -> bool:
        return self.age is not None

    def fire(self, ads_amount: float = 0.0):
        self.age = 0.0
        self._fresh = True                                 # flash frame: full intensity, age not yet subtracted
        self.fired += 1

    def update(self, dt: float):
        d = self.data
        if self.age is None:
            return
        if self._fresh:
            self._fresh = False
        else:
            self.age += dt
        k = fx.flash_envelope(self.age, d.life)
        pos = self.muzzle.get_pos(self.vm.cam_np) + Vec3(0, 0, d.forward)
        if k <= 0.0:
            self.age = None
            self.vm.set_flash_light(pos, (0, 0, 0))
            return
        self.vm.set_flash_light(pos, tuple(ch * d.light_power * k for ch in d.light_color))


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

    def __init__(self, gun: GunData, viewmodel, rng: random.Random = None, smoke=None):
        self.gun = gun
        self.vm = viewmodel
        self.flash = MuzzleFlash(viewmodel, gun, rng or random.Random())
        self.smoke = smoke                                 # game.smoke.GunSmoke (shared by both guns, lives in the world) or None
        self.port = None
        if gun.smoke.ejection_port is not None:
            self.port = viewmodel.sway.attach_new_node('ejection_port')
            self.port.set_pos(*(a + b for a, b in zip(gun.smoke.ejection_port, gun.hip_offset)))
        self.tracers = Tracers(gun)
        self.burst = 0                                     # which shot of the current burst this is
        self._rest = 1e9                                   # seconds since the last shot
        self._warm_up()

    def destroy(self):
        """Weapon switch: the tracer pool lives under `render` (the muzzle flash goes away with the old viewmodel)."""
        self.tracers.root.remove_node()

    def _warm_up(self):
        """Draw every effect (tiny, nearly transparent) for the first few frames so textures and draw state reach the GPU as the game starts.
        Without this the FIRST shot makes two consecutive frames slow, 25-40 ms (and since bullets move per frame, the hit point is off by a few mm).
        `prepare_scene` is not enough: hidden nodes are skipped."""
        self._warm = 3
        for node, glow in self.tracers.free:
            for n in (node, glow):
                n.set_mat(Mat4(0.001, 0, 0, 0, 0, 0.001, 0, 0, 0, 0, 0.001, 0, 0, 1.6, 3.0, 1))
                n.set_color_scale(1, 1, 1, 1.0)
                n.show()

    def _end_warm_up(self):
        for node, glow in self.tracers.free:
            node.hide()
            glow.hide()

    def muzzle_offset(self, node=None) -> tuple:
        """Muzzle (or `node`) position relative to the eye, in world coordinates. Measured in the gun scene (its own FOV), so it is multiplied by the lens factor so that
        the point lies exactly where the muzzle appears on screen."""
        p = (node or self.flash.muzzle).get_pos(self.vm.cam_np)
        k = fx.lens_ratio(camera.fov, self.vm.current_fov)
        v = camera.right * (p.x * k) + camera.up * (p.y * k) + camera.forward * p.z
        return (v[0], v[1], v[2])

    def on_shot(self, bullet, ads_amount: float):
        self.burst = 1 if self._rest > self.gun.tracer.burst_reset else self.burst + 1
        self._rest = 0.0
        self.flash.fire(ads_amount)
        muzzle = self.muzzle_offset()
        if self.smoke is not None:
            self._emit_smoke(bullet, muzzle)
        if fx.is_traced(self.burst, self.gun.tracer.every):
            self.tracers.spawn(bullet, muzzle)

    def _emit_smoke(self, bullet, muzzle: tuple):
        """Smoke leaves the muzzle along the bullet's direction, and the ejection port toward the gun's upper right (camera frame -> world)."""
        eye = camera.world_position
        origin = (eye[0] + muzzle[0], eye[1] + muzzle[1], eye[2] + muzzle[2])
        v = bullet.vel
        n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
        port = port_dir = None
        if self.port is not None:
            o = self.muzzle_offset(self.port)
            port = (eye[0] + o[0], eye[1] + o[1], eye[2] + o[2])
            dx, dy, dz = self.gun.smoke.port_dir
            w = camera.right * dx + camera.up * dy + camera.forward * dz
            port_dir = (w[0], w[1], w[2])
        self.smoke.emit(self.gun.smoke, origin, (v[0] / n, v[1] / n, v[2] / n), port, port_dir)

    def update(self, dt: float):
        if self._warm:
            self._warm -= 1
            if not self._warm:
                self._end_warm_up()
        self._rest += dt
        self.flash.update(dt)
        self.tracers.update(dt)
