"""The pool's wave simulation on the GPU (math: core/watersim.py; pass: assets/shaders/water_sim.frag).

Two float textures A / B hold the height field (r = now, g = one step ago). Two offscreen buffers each draw one fullscreen card: pass AB reads A and writes B, pass BA the reverse.
Every frame `SimClock` says how many fixed steps to run (0-2); `update` switches on that many passes and orders them (`set_sort`) so the first one always reads the latest texture.
Which texture is the latest is told to the water shader through a PTA value (edited in place: a per-frame `set_shader_input` would change the draw state).
Impulses (bullets, feet) are queued on the CPU and applied by the first pass of the frame (a PTA array of vec4 + a per-pass flag).
"""
from panda3d.core import (Camera, CardMaker, FrameBufferProperties, GraphicsOutput, GraphicsPipe, NodePath, OrthographicLens, PTA_LVecBase4f, Texture, Vec4, WindowProperties)
from ursina import application

from fps.core.watersim import SimClock, coefficient, damping
from fps.game.shaders import load_glsl

IMPULSE_SLOTS = 16
SORT = -60                      # before every other buffer (the lens buffers, the window)


class WaterSim:
    def __init__(self, rect: tuple, cols: int, rows: int, speed: float, life: float):
        self.rect = rect                                       # (x0, x1, z0, z1) of the pool
        self.cols, self.rows = cols, rows
        self.cell = min((rect[1] - rect[0]) / cols, (rect[3] - rect[2]) / rows)
        self.clock = SimClock()
        self.queue = []                                        # [(x, z, radius, amount)] waiting for the next pass
        self.latest = 0                                        # 0 = texture A holds the newest state, 1 = B
        self.drawn = 0                                         # same, but only counting passes already rendered (see `drawn_texture`)
        self.pick = PTA_LVecBase4f.empty_array(1)              # for the water shader: x = latest (0 / 1), y = cell size, zw unused
        self.impulses = PTA_LVecBase4f.empty_array(IMPULSE_SLOTS)
        self.textures = [self._texture('water_sim_a'), self._texture('water_sim_b')]
        base = application.base
        shader = load_glsl('water_sim', defines=(f'IMPULSE_SLOTS {IMPULSE_SLOTS}',))
        self.passes = []                                       # [(buffer, card, params PTA)] pass 0 reads A writes B, pass 1 reads B writes A
        for src in (0, 1):
            dst = 1 - src
            buf = self._buffer(base, f'water_sim_{src}{dst}', self.textures[dst])
            scene = NodePath(f'water_sim_scene_{src}')
            lens = OrthographicLens()
            lens.set_film_size(2, 2)
            lens.set_near_far(-1, 1)
            cam = scene.attach_new_node(Camera(f'water_sim_cam_{src}', lens))
            region = buf.make_display_region()
            region.set_camera(cam)
            region.set_clear_color_active(False)
            region.set_clear_depth_active(False)
            cm = CardMaker('water_sim_card')
            cm.set_frame(-1, 1, -1, 1)
            card = scene.attach_new_node(cm.generate())
            card.set_depth_test(False)
            card.set_depth_write(False)
            card.set_shader(shader)
            params = PTA_LVecBase4f.empty_array(1)
            card.set_shader_input('sim_prev', self.textures[src])
            card.set_shader_input('sim_params', params)
            card.set_shader_input('sim_rect', Vec4(*rect))
            card.set_shader_input('sim_impulses', self.impulses)
            buf.set_active(False)
            self.passes.append((buf, card, params, scene))
        self.set_physics(speed, life)
        self._reset = 2                                        # the first two passes write zeros (the textures start undefined)
        self.enabled = True

    def _texture(self, name: str) -> Texture:
        t = Texture(name)
        t.setup_2d_texture(self.cols, self.rows, Texture.T_float, Texture.F_rgba32)
        t.set_clear_color((0, 0, 0, 0))
        t.set_wrap_u(Texture.WM_clamp)
        t.set_wrap_v(Texture.WM_clamp)
        t.set_minfilter(Texture.FT_linear)
        t.set_magfilter(Texture.FT_linear)
        return t

    def _buffer(self, base, name: str, tex: Texture):
        fbp = FrameBufferProperties()
        fbp.set_rgba_bits(32, 32, 32, 32)
        fbp.set_float_color(True)
        fbp.set_depth_bits(0)
        wp = WindowProperties.size(self.cols, self.rows)
        buf = base.graphicsEngine.make_output(base.pipe, name, SORT, fbp, wp, GraphicsPipe.BF_refuse_window | GraphicsPipe.BF_resizeable,
                                              base.win.get_gsg(), base.win)
        if buf is None:
            raise RuntimeError('không tạo được buffer mô phỏng nước (card đồ hoạ không hỗ trợ texture số thực?)')
        buf.add_render_texture(tex, GraphicsOutput.RTM_bind_or_copy)
        buf.set_clear_color_active(False)
        buf.set_clear_depth_active(False)
        return buf

    def set_physics(self, speed: float, life: float):
        self.coef, self.damp = coefficient(speed, self.cell), damping(life)
        self.pick.set_element(0, Vec4(self.latest, self.cell, 0, 0))

    def push(self, x: float, z: float, radius: float, amount: float):
        """Queue a push of the water surface (amount < 0: a dip). Dropped when the queue is full (16 per frame is far more than a full-auto burst needs)."""
        if self.enabled and len(self.queue) < IMPULSE_SLOTS:
            self.queue.append((x, z, radius, amount))

    @property
    def latest_texture(self) -> Texture:
        return self.textures[self.latest]

    @property
    def drawn_texture(self) -> Texture:
        """The newest texture the GPU has already DRAWN (for a readback): `latest` may name a pass scheduled this frame that only runs at render time."""
        return self.textures[self.drawn]

    def update(self, dt: float):
        """Before the frame is drawn: switch on 0-2 passes, first one reading the latest texture."""
        self.drawn = self.latest                               # the passes scheduled last frame have been rendered by now
        n = self.clock.steps(dt) if self.enabled else 0
        for buf, *_ in self.passes:
            buf.set_active(False)
        for k in range(n):
            src = self.latest
            buf, card, params, _ = self.passes[src]
            buf.set_active(True)
            buf.set_sort(SORT + k)
            apply = k == 0 and bool(self.queue)
            if apply:
                for i in range(IMPULSE_SLOTS):
                    self.impulses.set_element(i, Vec4(*self.queue[i]) if i < len(self.queue) else Vec4(0, 0, 0, 0))
                self.queue = []
            reset = 1.0 if self._reset > 0 else 0.0
            self._reset = max(self._reset - 1, 0)
            params.set_element(0, Vec4(self.coef, self.damp, 1.0 if apply else 0.0, reset))
            self.latest = 1 - src
        self.pick.set_element(0, Vec4(self.latest, self.cell, 0, 0))

    def set_enabled(self, on: bool):
        """Quality 'low': no passes at all (the water falls back to the analytic rings). Switching back on starts from still water."""
        if on and not self.enabled:
            self._reset = 2
            self.queue = []
        self.enabled = on

    def destroy(self):
        engine = application.base.graphicsEngine
        for buf, card, params, scene in self.passes:
            engine.remove_window(buf)
            scene.remove_node()
