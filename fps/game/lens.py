"""Head-camera lens: the world + gun are drawn into one texture, then `assets/shaders/lens.frag` draws it once to the window; text and the F1 panel are drawn afterwards, so they are not distorted.

Because the lens is applied to the COMPOSITED image, the gun and the world distort identically: wherever the front sight points on screen, the bullet still goes there.
Not using Ursina's `camera.shader` (FXAA on that path breaks the image when the gun has its own drawing region); the gun's drawing region is moved to the same buffer here.
"""
from direct.filter.FilterManager import FilterManager
from panda3d.core import PTA_LVecBase3f, SamplerState, Texture, Vec3, Vec4
from ursina import application, window

from fps.core.movement import smoothstep
from fps.game.shaders import load_glsl
from fps.weapon_data import LensData


class Lens:
    def __init__(self, data: LensData, viewmodel=None):
        self.d = data
        base = application.base
        self.manager = FilterManager(base.win, base.cam)
        self.scene = Texture('lens_scene')
        self.quad = self.manager.renderSceneInto(colortex=self.scene)
        if self.quad is None:
            raise RuntimeError('không tạo được buffer cho ống kính')
        self.scene.set_wrap_u(SamplerState.WM_clamp)
        self.scene.set_wrap_v(SamplerState.WM_clamp)
        self.scene.set_magfilter(SamplerState.FT_linear)
        self._mipmaps = None
        self.quad.set_shader(load_glsl('lens'))
        self.quad.set_shader_input('lens_scene', self.scene)
        self.frame = PTA_LVecBase3f.empty_array(1)
        self.frame.set_element(0, Vec3(data.fisheye, 0.0, 0.0))
        self.quad.set_shader_input('lens_frame', self.frame)
        self.shake = PTA_LVecBase3f.empty_array(1)          # frame shake (dx, dy, roll), written in place every frame like lens_frame
        self.shake.set_element(0, Vec3(0.0, 0.0, 0.0))
        self.quad.set_shader_input('lens_shake', self.shake)
        self.t = 0.0
        self.turn = 0.0                                     # smoothed turn speed (deg/s)
        self.apply_params()
        if viewmodel is not None:
            viewmodel.move_to_output(self.manager.buffers[-1])

    def apply_params(self):
        d, q = self.d, self.quad
        q.set_shader_input('lens_warp', Vec4(window.aspect_ratio, d.chroma, d.smear, d.smear_start))
        q.set_shader_input('lens_motion', Vec4(d.smear_motion, d.rolling_shutter, 1.15, 0.0))
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
        return d.fisheye + (d.fisheye_ads - d.fisheye) * smoothstep(min(max(ads, 0.0), 1.0))

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
