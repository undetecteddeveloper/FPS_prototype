"""Dust motes glinting in the sun beams (graphics level High): one static mesh of COUNT camera-facing quads; every position is computed in assets/shaders/dust.vert from a random
seed and the clock, so the CPU does nothing per frame except one clock value. Additive blending, no depth write."""
import random
from array import array

from panda3d.core import (ColorBlendAttrib, Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, InternalName, OmniBoundingVolume,
                          PTA_LVecBase4f, Vec4)
from ursina import application

from fps.game.shaders import load_glsl
from fps.weapon_data import LookData

COUNT = 600
CORNERS = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))


def _format() -> GeomVertexFormat:
    a = GeomVertexArrayFormat()
    a.add_column(InternalName.get_vertex(), 3, Geom.NT_float32, Geom.C_point)
    a.add_column(InternalName.make('corner'), 2, Geom.NT_float32, Geom.C_other)
    a.add_column(InternalName.make('seed'), 4, Geom.NT_float32, Geom.C_other)
    return GeomVertexFormat.register_format(GeomVertexFormat(a))


class DustMotes:
    def __init__(self, look: LookData, light, pool, count: int = COUNT, seed: int = 7):
        self.look = look
        rng = random.Random(seed)
        vdata = GeomVertexData('dust', _format(), Geom.UH_static)
        vdata.set_num_rows(count * 4)
        buf = []
        for _ in range(count):
            s = (rng.random(), rng.random(), rng.random(), rng.random())
            for u, v in CORNERS:
                buf.extend((0.0, 0.0, 0.0, u, v, *s))
        vdata.modify_array_handle(0).copy_data_from(array('f', buf))
        prim = GeomTriangles(Geom.UH_static)
        for i in range(count):
            a = i * 4
            prim.add_vertices(a, a + 1, a + 2)
            prim.add_vertices(a, a + 2, a + 3)
        geom = Geom(vdata)
        geom.add_primitive(prim)
        node = GeomNode('dust_motes')
        node.add_geom(geom)
        node.set_bounds(OmniBoundingVolume())
        node.set_final(True)
        self.root = application.base.render.attach_new_node(node)
        r = self.root
        r.set_shader(load_glsl('dust'), 2)
        r.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_one, ColorBlendAttrib.O_one))
        r.set_depth_write(False)
        r.set_two_sided(True)
        r.set_bin('fixed', 45)
        r.set_light_off()
        light.bind(r)
        r.set_shader_input('dust_right', light.view_x)
        r.set_shader_input('dust_up', light.view_y)
        pool._bind_sun(r)                                       # window holes for sun_visible
        self.params = PTA_LVecBase4f.empty_array(1)
        r.set_shader_input('dust_params', self.params)
        self.clock = 0.0
        self.apply_params()

    def apply_params(self):
        lk = self.look
        self.params.set_element(0, Vec4(lk.dust_size, lk.dust_brightness, lk.dust_box, self.clock))

    def set_enabled(self, on: bool):
        self.root.show() if on else self.root.hide()

    def update(self, dt: float):
        self.clock += dt
        lk = self.look
        self.params.set_element(0, Vec4(lk.dust_size, lk.dust_brightness, lk.dust_box, self.clock))
