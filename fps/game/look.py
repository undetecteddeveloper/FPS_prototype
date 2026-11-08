"""Visual side of the world: the ground shader (sun, noise, haze), the sky with clouds (sky.py) and the lighting shared with the gun.

The world shader is in assets/shaders/world.vert|frag (based on Ursina's unlit_with_fog_shader); the lighting shared with the gun is in assets/shaders/light_common.glsl + frame_light.py.
It is applied to the ground and the bullet holes by setting `Entity.shader`; the material is picked by the `look_material` input of each Entity. UI objects keep
Ursina's default shader. Values in weapon_data.LookData.
"""
import random

from panda3d.core import SamplerState, Vec2 as PandaVec2, Vec4
from PIL import Image
from ursina import Shader, Texture, application, color, window
from ursina.vec2 import Vec2

from fps.game.frame_light import FrameLight
from fps.game.shaders import read_source
from fps.game.sky import Sky
from fps.weapon_data import LookData

GROUND_MATERIAL = 1.0


def noise_texture(size: int = 128, cells: int = 8, seed: int = 11) -> Texture:
    """Seamless value noise (tiles with no visible seam), one bright channel, smoothly interpolated: laid over the ground instead of a repeating grid of tiles."""
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


class WorldLook:
    def __init__(self, params: LookData, world: dict, decals, light: FrameLight):
        self.p = params
        self.world = world
        self.light = light
        self.shader = self._make_shader()
        pool = world.get('pool')
        self.sky = Sky(holes=pool.sky_holes() if pool is not None else None)      # indoors the sky is only seen through the window holes (G13)
        render = application.base.render

        render.set_shader_input('look_fog', (*params.fog_color, params.fog_density))
        render.set_shader_input('look_detail_strength', float(params.detail_strength))
        render.set_shader_input('look_detail_tex', noise_texture()._texture)
        render.set_shader_input('look_material', 0.0)
        self._push_flash(render)
        self._push_grid(render)
        light.bind(render)

        floor = world.get('floor')                      # the flat map has one slab; the pool hall brings its own shaders (room, water) and has none
        if floor is not None:                           # the bullet holes have their own shader (decal.frag: relief, the wall's baked light)
            floor.shader = self.shader
        if floor is not None:
            floor.set_shader_input('look_material', GROUND_MATERIAL)

        window.color = color.rgb(*params.fog_color)        # the sky: the background behind the far edge of the ground gets the same colour as the haze
        application.base.graphicsEngine.render_frame()     # compile the world shader now, not in the first frame of the game

    def _push_grid(self, node):
        p = self.p
        node.set_shader_input('look_grid', Vec4(p.grid_strength, max(p.grid_spacing, 0.1), float(max(p.grid_major, 1)), p.grid_width))

    def _push_flash(self, node):
        flash = self.light.gun.flash
        node.set_shader_input('look_flash_world', PandaVec2(flash.world_power / max(flash.light_power, 0.01), flash.world_falloff))

    @staticmethod
    def _make_shader() -> Shader:
        vert, frag = read_source('world.vert'), read_source('world.frag')
        return Shader(name='fps_world', language=Shader.GLSL, vertex=vert, fragment=frag,
                      default_input={'texture_scale': Vec2(1, 1), 'texture_offset': Vec2(0.0, 0.0)})

    def update(self, dt: float):
        """Every frame: the clouds drift."""
        self.sky.update(dt)

    def apply_params(self):
        """Debug panel: pushes the LookData values (sun, sky, haze, colour grade) back into the shader under the same input names as at build time."""
        p, render = self.p, application.base.render
        render.set_shader_input('look_fog', (*p.fog_color, p.fog_density))
        render.set_shader_input('look_detail_strength', float(p.detail_strength))
        self._push_flash(render)
        self._push_grid(render)
        self.light.apply_params()
        if self.world.get('floor') is not None:
            self.world['floor'].color = color.rgb(*p.ground_color)
        window.color = color.rgb(*p.fog_color)
