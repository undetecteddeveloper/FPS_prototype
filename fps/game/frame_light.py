"""A single source of light for both the world and the gun: the lamp count (changes when the F1 panel changes) and the values that change every frame (camera, exposure, flash).

Per-frame values go through PTA arrays edited in place: calling `set_shader_input` every frame would change the draw state of the whole scene graph.
`bind` is called for `render` (the world) and the root node of the gun scene, so the two sides can never drift apart.
"""
import math

from panda3d.core import (LMatrix4f, PTA_LMatrix4f, PTA_LVecBase3f, SamplerState, Texture as PandaTexture, Vec3, Vec4)

from fps.core.exposure import lamp_reach
from fps.core.room import FACE_COUNT
from fps.weapon_data import GunData, LookData

SHADOW_MODES = {False: 0.0, True: 1.0, 'fake': 2.0}


def _dummy_shadow_texture() -> PandaTexture:
    """1x1 atlas (depth = 1, occludes nothing) so sampler2DShadow always has a valid texture when real shadows are off."""
    tex = PandaTexture('no_shadow')
    tex.setup_2d_texture(1, 1, PandaTexture.T_float, PandaTexture.F_depth_component32)
    tex.set_ram_image(b'\x00\x00\x80\x3f')
    tex.set_minfilter(SamplerState.FT_shadow)
    tex.set_magfilter(SamplerState.FT_shadow)
    return tex


class FrameLight:
    def __init__(self, look: LookData, gun: GunData):
        self.look, self.gun = look, gun
        self.nodes = []
        self.camera_pos = PTA_LVecBase3f.empty_array(1)
        self.frame = PTA_LVecBase3f.empty_array(1)                 # x = exposure
        self.view_x = PTA_LVecBase3f.empty_array(1)
        self.view_y = PTA_LVecBase3f.empty_array(1)
        self.view_z = PTA_LVecBase3f.empty_array(1)
        self.flash_pos = PTA_LVecBase3f.empty_array(1)
        self.flash_color = PTA_LVecBase3f.empty_array(1)
        self.camera_pos.set_element(0, Vec3(0, 1.68, 0))
        self.frame.set_element(0, Vec3(1, 0, 0))
        self.view_x.set_element(0, Vec3(1, 0, 0))
        self.view_y.set_element(0, Vec3(0, 1, 0))
        self.view_z.set_element(0, Vec3(0, 0, 1))
        self.flash_pos.set_element(0, Vec3(0, 0, 0))
        self.flash_color.set_element(0, Vec3(0, 0, 0))
        self.flash_on = False
        self.exposure = 1.0
        self._no_shadow_tex = _dummy_shadow_texture()
        self._identity_mats = PTA_LMatrix4f.empty_array(FACE_COUNT)
        for i in range(FACE_COUNT):
            self._identity_mats[i] = LMatrix4f.ident_mat()
        self.shadow_inputs = None                                  # None = no shadow map; dict from LampShadows.shader_inputs()
        self.shadow_mode = False
        self.radius = look.lamp_radius                             # radius baked into the shadow map

    def bind(self, node):
        """Puts all light inputs on one node (PTA arrays: the node keeps a reference, so this only has to run once)."""
        self.nodes.append(node)
        node.set_shader_input('look_camera_pos', self.camera_pos)
        node.set_shader_input('look_frame', self.frame)
        node.set_shader_input('look_flash_pos', self.flash_pos)
        node.set_shader_input('look_flash_color', self.flash_color)
        self._push_static(node)
        self._push_shadow(node)

    def _static(self) -> dict:
        p = self.look
        return {
            'look_lamp': Vec4(p.lamp_x, p.lamp_y, p.lamp_z0, p.lamp_spacing),
            'look_lamp2': Vec4(float(p.lamp_count), self.radius, p.lamp_ref, p.lamp_intensity),
            'look_lamp_color': Vec3(*p.lamp_color),
            'look_lamp_cone': Vec3(math.cos(math.radians(p.lamp_cone)), math.cos(math.radians(p.lamp_cone_outer)), p.lamp_side),
            'look_ambient_up': Vec3(*p.ambient_up),
            'look_ambient_down': Vec3(*p.ambient_down),
            'look_bounce': Vec3(*p.bounce_color),
            'look_shadow_lod': Vec4(p.shadow_soft_distance, p.shadow_max_distance, float(lamp_reach(p)), 0.0),
        }

    def _push_static(self, node):
        for key, value in self._static().items():
            node.set_shader_input(key, value)

    def _push_shadow(self, node):
        p = self.look
        if self.shadow_mode is True and self.shadow_inputs:
            for key, value in self.shadow_inputs.items():
                node.set_shader_input(key, value)
        else:
            node.set_shader_input('look_shadow_atlas', self._no_shadow_tex)
            node.set_shader_input('look_face_mat', self._identity_mats)
            node.set_shader_input('look_shadow_grid', Vec4(1, 1, 1, 1))
        bias_a, bias_b = p.shadow_bias
        node.set_shader_input('look_shadow', Vec4(SHADOW_MODES[self.shadow_mode], bias_a, bias_b, p.lamp_emissive))

    def set_shadows(self, mode, inputs: dict = None):
        self.shadow_mode = mode
        if inputs is not None:
            self.shadow_inputs = inputs
        for node in self.nodes:
            self._push_shadow(node)

    def apply_params(self):
        """The F1 panel changed a light value: push it to every node."""
        for node in self.nodes:
            self._push_static(node)
            self._push_shadow(node)

    # --- per frame ---
    def set_camera(self, pos, right, up, forward):
        self.camera_pos.set_element(0, Vec3(*pos))
        self.view_x.set_element(0, Vec3(*right))
        self.view_y.set_element(0, Vec3(*up))
        self.view_z.set_element(0, Vec3(*forward))

    def set_exposure(self, value: float):
        self.exposure = value
        self.frame.set_element(0, Vec3(value * self.look.exposure, 0, 0))

    def set_flash(self, view_pos, color):
        """Muzzle flash: `view_pos` in camera space (x right, y up, z forward), `color` black = off. Shared by the gun and the world."""
        cam = self.camera_pos[0]
        x, y, z = self.view_x[0], self.view_y[0], self.view_z[0]
        self.flash_pos.set_element(0, Vec3(cam + x * view_pos[0] + y * view_pos[1] + z * view_pos[2]))
        self.flash_color.set_element(0, Vec3(*color))
        self.flash_on = any(c > 0.0 for c in color)
