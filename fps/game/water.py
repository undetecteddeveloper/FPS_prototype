"""The pool water: one flat quad drawn by assets/shaders/water.*, the rings where bullets landed, and the box bullets hit.

Rings live in a PTA array edited in place (calling `set_shader_input` every frame would change the draw state of the whole scene graph, like in frame_light.py).
`is_water` / `splash` are what Combat looks for on the owner of a hit box: a bullet that lands on the water makes a ring (and a sound once there is one), not a bullet hole.
"""
from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, PTA_LVecBase3f, PTA_LVecBase4f, Texture, Vec3, Vec4
from ursina import Entity

from fps.core.cubemap import TAN_HALF, basis
from fps.core.poolmap import PoolMap
from fps.core.waves import RippleBuffer
from fps.game.shaders import load_glsl
from fps.weapon_data import WaterData

MARGIN = 0.01          # the quad reaches this far under the pool wall (hidden inside the deck box)


class WaterSurface:
    is_water = True

    def __init__(self, pm: PoolMap, params: WaterData):
        self.pm, self.p = pm, params
        self.clock = 0.0
        self.ripples = RippleBuffer(params.ripple_slots)
        self.on_splash = None                       # callable(point, distance) set by Game once the water has a sound
        x0, x1, z0, z1, y = pm.water
        self.rect = (x0, x1, z0, z1)
        self.y = y
        self.entity = Entity(add_to_scene_entities=False)
        self.node = self.entity.attach_new_node(self._quad(x0 - MARGIN, x1 + MARGIN, z0 - MARGIN, z1 + MARGIN, y))
        self.node.set_two_sided(True)
        self.node.set_shader(load_glsl('water', defines=(f'RING_SLOTS {params.ripple_slots}',)), 1)
        self.time_pta = PTA_LVecBase3f.empty_array(1)
        self.time_pta.set_element(0, Vec3(0, 0, 0))
        self.rings_pta = PTA_LVecBase4f.empty_array(params.ripple_slots)
        for i in range(params.ripple_slots):
            self.rings_pta.set_element(i, Vec4(0, 0, -1e6, 0))
        self.axes_pta = PTA_LVecBase3f.empty_array(18)
        for f in range(6):
            right, up, forward = basis(f)
            for j, vec in enumerate((forward, right, up)):
                self.axes_pta.set_element(f * 3 + j, Vec3(*vec))
        n = self.node
        n.set_shader_input('water_time', self.time_pta)
        n.set_shader_input('water_rings', self.rings_pta)
        n.set_shader_input('water_axes', self.axes_pta)
        n.set_shader_input('water_rect', Vec4(x0, x1, z0, z1))
        d = pm.data
        lo, hi = pm.interior
        n.set_shader_input('water_box_lo', Vec4(lo[0], lo[1], lo[2], 0))
        n.set_shader_input('water_box_hi', Vec4(hi[0], hi[1], hi[2], 0))
        n.set_shader_input('water_probe', Vec4(d.probe[0], d.probe[1], d.probe[2], 0))
        placeholder = Texture('water_reflect_placeholder')
        placeholder.setup_2d_texture(1, 1, Texture.T_unsigned_byte, Texture.F_rgb)
        placeholder.set_ram_image(bytes([60, 70, 80]))
        n.set_shader_input('water_reflect', placeholder)
        self.apply_params()

    @staticmethod
    def _quad(x0, x1, z0, z1, y) -> GeomNode:
        vdata = GeomVertexData('water', GeomVertexFormat.get_v3(), Geom.UH_static)
        vdata.set_num_rows(4)
        w = GeomVertexWriter(vdata, 'vertex')
        for x, z in ((x0, z0), (x1, z0), (x1, z1), (x0, z1)):
            w.add_data3(x, y, z)
        prim = GeomTriangles(Geom.UH_static)
        prim.add_vertices(0, 2, 1)
        prim.add_vertices(0, 3, 2)
        geom = Geom(vdata)
        geom.add_primitive(prim)
        node = GeomNode('water')
        node.add_geom(geom)
        return node

    def set_reflection(self, texture: Texture):
        texture.set_wrap_u(Texture.WM_clamp)
        texture.set_wrap_v(Texture.WM_clamp)
        texture.set_minfilter(Texture.FT_linear)
        texture.set_magfilter(Texture.FT_linear)
        self.node.set_shader_input('water_reflect', texture)

    def apply_params(self):
        """Pushes the WaterData numbers (F1 panel) to the shader."""
        p, n = self.p, self.node
        n.set_shader_input('water_look', Vec4(p.ripple_strength, p.ripple_scale, p.ripple_speed, p.reflect_strength))
        n.set_shader_input('water_deep', Vec4(*p.deep_color, p.fresnel_f0))
        n.set_shader_input('water_shallow', Vec4(*p.shallow_color, p.shallow_width))
        n.set_shader_input('water_impact', Vec4(p.impact_speed, p.impact_wavelength, p.impact_width, p.impact_life))
        n.set_shader_input('water_impact2', Vec4(p.impact_strength, p.impact_reach, TAN_HALF, 0.0))

    def collider(self) -> tuple:
        """(lo, hi, owner): a thin box just under the surface, so a bullet coming from above hits its top face at the water level."""
        x0, x1, z0, z1 = self.rect
        return (x0, self.y - 0.02, z0), (x1, self.y, z1), self

    def splash(self, point, distance: float, amp: float = 1.0):
        """A bullet landed at `point`: start a ring there (and call the sound hook)."""
        self.ripples.add(point[0], point[2], self.clock, amp)
        for i, ring in enumerate(self.ripples.packed()):
            self.rings_pta.set_element(i, Vec4(*ring))
        if self.on_splash:
            self.on_splash(point, distance)

    def update(self, dt: float):
        self.clock += dt
        self.time_pta.set_element(0, Vec3(self.clock, 0, 0))
