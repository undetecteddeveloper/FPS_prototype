"""Ống kính camera đội đầu: thế giới + súng vẽ vào một kết cấu, rồi `assets/shaders/lens.frag` vẽ một lần ra cửa sổ; chữ và bảng F1 vẽ sau, không bị méo.

Vì ống kính áp lên ảnh ĐÃ GHÉP nên súng và thế giới méo như nhau: đầu ruồi đang chỉ vào đâu trên màn hình thì đạn vẫn tới đó.
Không dùng `camera.shader` của Ursina (FXAA theo đường đó làm hỏng ảnh khi có vùng vẽ súng riêng); vùng vẽ súng được chuyển sang cùng buffer ở đây.
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
        self.t = 0.0
        self.turn = 0.0                                     # tốc độ xoay đã làm mượt (độ/s)
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
        """Loé sáng đọc mipmap của ảnh: chỉ tạo mipmap khi cần vì tốn thời gian mỗi khung."""
        if wanted == self._mipmaps:
            return
        self._mipmaps = wanted
        self.scene.set_minfilter(SamplerState.FT_linear_mipmap_linear if wanted else SamplerState.FT_linear)

    def current_fisheye(self, ads: float) -> float:
        d = self.d
        return d.fisheye + (d.fisheye_ads - d.fisheye) * smoothstep(min(max(ads, 0.0), 1.0))

    def update(self, dt: float, ads: float, yaw_step: float):
        """`yaw_step` = độ chuột quay ngang trong khung này (cho màn trập cuộn và nhoè khi xoay)."""
        self.t += dt
        if dt > 0.0:
            self.turn += (yaw_step / dt - self.turn) * min(dt / 0.04, 1.0)
        self.frame.set_element(0, Vec3(self.current_fisheye(ads), self.t % 1000.0, self.turn))

    def destroy(self):
        self.manager.cleanup()
