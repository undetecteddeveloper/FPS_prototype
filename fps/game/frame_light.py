"""A single source of light for both the world and the gun: the sun and sky values (change when the F1 panel changes) and the values that change every frame (camera, exposure, flash).

Per-frame values go through PTA arrays edited in place: calling `set_shader_input` every frame would change the draw state of the whole scene graph.
`bind` is called for `render` (the world) and the root node of the gun scene, so the two sides can never drift apart.
"""
from panda3d.core import PTA_LVecBase3f, Vec3

from fps.core.exposure import sun_vector
from fps.weapon_data import GunData, LookData


class FrameLight:
    def __init__(self, look: LookData, gun: GunData):
        self.look, self.gun = look, gun
        self.nodes = []
        self.camera_pos = PTA_LVecBase3f.empty_array(1)
        self.frame = PTA_LVecBase3f.empty_array(1)                 # x = exposure, y = share of the sun reaching the player, z = ambient scale (the gun's shade; the world is baked)
        self.view_x = PTA_LVecBase3f.empty_array(1)
        self.view_y = PTA_LVecBase3f.empty_array(1)
        self.view_z = PTA_LVecBase3f.empty_array(1)
        self.flash_pos = PTA_LVecBase3f.empty_array(1)
        self.flash_color = PTA_LVecBase3f.empty_array(1)
        self.camera_pos.set_element(0, Vec3(0, 1.68, 0))
        self.frame.set_element(0, Vec3(1, 1, 1))
        self.sun_visibility = 1.0
        self.ambient_scale = 1.0
        self.view_x.set_element(0, Vec3(1, 0, 0))
        self.view_y.set_element(0, Vec3(0, 1, 0))
        self.view_z.set_element(0, Vec3(0, 0, 1))
        self.flash_pos.set_element(0, Vec3(0, 0, 0))
        self.flash_color.set_element(0, Vec3(0, 0, 0))
        self.flash_on = False
        self.exposure = 1.0

    def bind(self, node):
        """Puts all light inputs on one node (PTA arrays: the node keeps a reference, so this only has to run once)."""
        self.nodes.append(node)
        node.set_shader_input('look_camera_pos', self.camera_pos)
        node.set_shader_input('look_frame', self.frame)
        node.set_shader_input('look_flash_pos', self.flash_pos)
        node.set_shader_input('look_flash_color', self.flash_color)
        self._push_static(node)

    def _static(self) -> dict:
        p = self.look
        return {
            'look_sun_dir': Vec3(*sun_vector(p)),
            'look_sun_color': Vec3(*p.sun_color),
            'look_ambient_up': Vec3(*p.ambient_up),
            'look_ambient_down': Vec3(*p.ambient_down),
        }

    def _push_static(self, node):
        for key, value in self._static().items():
            node.set_shader_input(key, value)

    def apply_params(self):
        """The F1 panel changed a light value: push it to every node."""
        for node in self.nodes:
            self._push_static(node)

    # --- per frame ---
    def set_camera(self, pos, right, up, forward):
        self.camera_pos.set_element(0, Vec3(*pos))
        self.view_x.set_element(0, Vec3(*right))
        self.view_y.set_element(0, Vec3(*up))
        self.view_z.set_element(0, Vec3(*forward))

    def set_exposure(self, value: float):
        self.exposure = value
        self._push_frame()

    def set_local_light(self, sun_visibility: float, ambient_scale: float = 1.0):
        """How much of the sun reaches the player and how bright the ambient light is around him: the gun and hands are lit by this (the world's own light is baked)."""
        self.sun_visibility, self.ambient_scale = sun_visibility, ambient_scale
        self._push_frame()

    def _push_frame(self):
        self.frame.set_element(0, Vec3(self.exposure * self.look.exposure, self.sun_visibility, self.ambient_scale))

    def set_flash(self, view_pos, color):
        """Muzzle flash: `view_pos` in camera space (x right, y up, z forward), `color` black = off. Shared by the gun and the world."""
        cam = self.camera_pos[0]
        x, y, z = self.view_x[0], self.view_y[0], self.view_z[0]
        self.flash_pos.set_element(0, Vec3(cam + x * view_pos[0] + y * view_pos[1] + z * view_pos[2]))
        self.flash_color.set_element(0, Vec3(*color))
        self.flash_on = any(c > 0.0 for c in color)
