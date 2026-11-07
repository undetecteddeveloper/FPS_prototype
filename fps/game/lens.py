"""Head-camera lens: the world + gun are drawn into one texture, then `assets/shaders/lens.frag` draws it once to the window; text and the F1 panel are drawn afterwards, so they are not distorted.

Because the lens is applied to the COMPOSITED image, the gun and the world distort identically: wherever the front sight points on screen, the bullet still goes there.
Not using Ursina's `camera.shader` (FXAA on that path breaks the image when the gun has its own drawing region); the gun's drawing region is moved to the same buffer here.

G13, 3D resolution below 100% (F2 'Độ phân giải 3D', 75% on Thấp): the scene buffer AND the lens pass run at that share of the window (the lens pass costs per
pixel too: 2.8 ms at 1080p on the Iris Xe), then `blit.frag` stretches the result over the window. At 100% the lens draws straight to the window as before.
The lens has two builds compiled at start-up: the full one and LENS_DRY (no film / drops / waterline band), picked every frame by `set_wet`.
"""
import math
from direct.filter.FilterManager import FilterManager
from panda3d.core import FrameBufferProperties, PTA_LVecBase3f, PTA_LVecBase4f, SamplerState, Texture, Vec3, Vec4
from ursina import application, window

from fps.core.movement import smoothstep
from fps.core.underwater import band_visible
from fps.game.shaders import load_glsl, prepare
from fps.weapon_data import LensData


DROP_SLOTS = 12          # wet-lens drops the shader loops over (lens.frag `lens_drops`)


class Lens:
    def __init__(self, data: LensData, viewmodel=None, samples: int = 0, light=None, scale: float = 1.0):
        """`samples` = MSAA samples of the scene buffer (0 / 2 / 4; graphics panel F2): world AND gun are drawn into it, so both get the anti-aliasing.
        `scale` = share of the window size the 3D image is drawn at (G13, F2 'Độ phân giải 3D'); below 1 the lens pass gets its own buffer of that size and a blit."""
        self.d = data
        self.samples = samples
        self.scale = scale
        base = application.base
        self.manager = FilterManager(base.win, base.cam)
        self.scene = Texture('lens_scene')
        fbprops = None
        if samples > 0:
            fbprops = FrameBufferProperties()
            fbprops.set_multisamples(samples)
        self.window_quad = self.manager.renderSceneInto(colortex=self.scene, fbprops=fbprops)
        if self.window_quad is None:
            raise RuntimeError('không tạo được buffer cho ống kính')
        self.scene_buffer = self.manager.buffers[0]          # world + gun are drawn here (later buffers belong to the lens)
        self.scene.set_wrap_u(SamplerState.WM_clamp)
        self.scene.set_wrap_v(SamplerState.WM_clamp)
        self.scene.set_magfilter(SamplerState.FT_linear)
        if scale < 1.0:
            self.manager.sizes[0] = (scale, 1, 1)
            self.out = Texture('lens_out')
            self.quad = self.manager.renderQuadInto('lens-pass', mul=scale, colortex=self.out)     # the lens pass, at the 3D resolution
            if self.quad is None:
                raise RuntimeError('không tạo được buffer cho ống kính')
            self.manager.resizeBuffers()
            self.out.set_wrap_u(SamplerState.WM_clamp)
            self.out.set_wrap_v(SamplerState.WM_clamp)
            self.out.set_minfilter(SamplerState.FT_linear)
            self.out.set_magfilter(SamplerState.FT_linear)
            self.window_quad.set_shader(load_glsl('blit'))
            self.window_quad.set_shader_input('blit_src', self.out)
        else:
            self.out = None
            self.quad = self.window_quad
        self._mipmaps = None
        self.shaders = {False: load_glsl('lens'), True: load_glsl('lens', defines=('LENS_DRY',))}
        for sh in self.shaders.values():
            prepare(sh)                                     # compiled at the next frame: switching builds while playing never compiles
        self.dry = True
        self.quad.set_shader(self.shaders[True])
        self.quad.set_shader_input('lens_scene', self.scene)
        self.quad.set_shader_input('lens_lod', Vec4(math.log2(scale), 0.0, 0.0, 0.0))
        self.frame = PTA_LVecBase3f.empty_array(1)
        self.frame.set_element(0, Vec3(data.fisheye, 0.0, 0.0))
        self.quad.set_shader_input('lens_frame', self.frame)
        self.shake = PTA_LVecBase3f.empty_array(1)          # frame shake (dx, dy, roll), written in place every frame like lens_frame
        self.shake.set_element(0, Vec3(0.0, 0.0, 0.0))
        self.quad.set_shader_input('lens_shake', self.shake)
        self.t = 0.0
        self.turn = 0.0                                     # smoothed turn speed (deg/s)
        # G12: under the water (zoom, extra warp) and the wet lens after surfacing (core/wetlens.py): written in place by `set_wet`
        self.film = PTA_LVecBase4f.empty_array(1)           # film edge y, film strength, film blur, zoom (1 = none)
        self.wet = PTA_LVecBase4f.empty_array(1)            # drop refraction, meniscus thickness (m), -, -
        self.drops = PTA_LVecBase4f.empty_array(DROP_SLOTS)
        self.film.set_element(0, Vec4(-1.0, 0.0, 0.0, 1.0))
        self.wet.set_element(0, Vec4(0, 0, 0, 0))
        for i in range(DROP_SLOTS):
            self.drops.set_element(i, Vec4(0, 0, 0, 0))
        self.quad.set_shader_input('lens_film', self.film)
        self.quad.set_shader_input('lens_wet', self.wet)
        self.quad.set_shader_input('lens_drops', self.drops)
        self.extra_fisheye = 0.0
        if light is not None:
            light.bind_under(self.quad)                     # the same waterline as the world shaders (underwater.glsl)
        self.apply_params()
        if viewmodel is not None:
            viewmodel.move_to_output(self.scene_buffer)

    @property
    def buffer_size(self) -> tuple:
        """Pixel size of the scene buffer (what gl_FragCoord counts in the world and gun shaders)."""
        b = self.scene_buffer
        return b.get_x_size(), b.get_y_size()

    def apply_params(self):
        d, q = self.d, self.quad
        q.set_shader_input('lens_warp', Vec4(window.aspect_ratio, d.chroma, d.smear, d.smear_start))
        q.set_shader_input('lens_motion', Vec4(d.smear_motion, d.rolling_shutter, 1.15, 1.0 + max(d.overscan, 0.0)))
        q.set_shader_input('lens_vig', Vec4(d.vignette_start, d.vignette_end, d.fringe, d.noise))
        q.set_shader_input('lens_grade', Vec4(d.contrast, d.saturation, d.bloom, d.bloom_threshold))
        q.set_shader_input('lens_tint', Vec3(*d.tint))
        self._set_bloom(d.bloom > 0.0)

    def _set_bloom(self, wanted: bool):
        """Highlight bloom reads the image's mipmaps: only create mipmaps when needed, since they cost time every frame."""
        if wanted == self._mipmaps:
            return
        self._mipmaps = wanted
        self.scene.set_minfilter(SamplerState.FT_linear_mipmap_linear if wanted else SamplerState.FT_linear)

    def current_fisheye(self, ads: float) -> float:
        d = self.d
        return d.fisheye + (d.fisheye_ads - d.fisheye) * smoothstep(min(max(ads, 0.0), 1.0)) + self.extra_fisheye

    def set_wet(self, film_edge: float, film_strength: float, film_blur: float, zoom: float, extra_fisheye: float, drops: list, refract: float, meniscus: float,
                line: tuple = None, amp: float = 0.0):
        """G12, once per frame before `update`: drops = [(x, y, r, alpha)] (core/wetlens.py WetLens.packed); `line`, `amp` = this frame's waterline on the port
        (core/underwater.py): the meniscus band is drawn only when it can be in view. The dry build is used whenever nothing wet can show (G13)."""
        self.extra_fisheye = extra_fisheye
        live = [dr for dr in drops[:DROP_SLOTS] if dr[2] > 0.0]          # the shader loops over the first `count` slots only
        self.film.set_element(0, Vec4(film_edge, film_strength, film_blur, zoom))
        self.wet.set_element(0, Vec4(refract, meniscus, float(len(live)), 0.0))
        for i in range(DROP_SLOTS):
            self.drops.set_element(i, Vec4(*live[i]) if i < len(live) else Vec4(0, 0, 0, 0))
        dry = film_strength <= 0.0 and not live and not (meniscus > 0.0 and line is not None and band_visible(line, meniscus, amp))
        if dry != self.dry:
            self.dry = dry
            self.quad.set_shader(self.shaders[dry])

    def update(self, dt: float, ads: float, yaw_step: float, shake: tuple = (0.0, 0.0, 0.0)):
        """`yaw_step` = degrees of horizontal mouse turn in this frame (for rolling shutter and blur when turning).
        `shake` = core.lens.frame_shake(...) result (dx, dy, roll): moves and tilts the whole lens frame on the screen; zero = no shake."""
        self.t += dt
        if dt > 0.0:
            self.turn += (yaw_step / dt - self.turn) * min(dt / 0.04, 1.0)
        self.frame.set_element(0, Vec3(self.current_fisheye(ads), self.t % 1000.0, self.turn))
        self.shake.set_element(0, Vec3(*shake))

    def destroy(self):
        self.manager.cleanup()
