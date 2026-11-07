"""Draws the water droplets simulated by core/splash.py: ONE dynamic mesh (one draw call), quads built and stretched along the velocity in assets/shaders/splash.vert.
The same pattern as game/smoke.py (vertex data rebuilt in one Python array, only while drops are alive). Drops that fall back make tiny pushes in the wave simulation.
"""
from array import array

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, InternalName, OmniBoundingVolume, TransparencyAttrib,
                          Vec4)
from ursina import application

from fps.core.splash import SplashSim
from fps.game.shaders import load_glsl
from fps.weapon_data import SplashData

CAPACITY = 384
FLOATS = 10                      # per vertex: centre xyz, corner xy, velocity xyz, radius, alpha
CORNERS = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
FALL_PUSH = (-0.0012, 0.03)      # a drop falling back: a tiny dip (m, radius m) in the wave simulation
FALL_PUSHES_PER_FRAME = 4        # at most this many per frame (the sim takes 16 pushes per frame; bullets and feet come first)


def _format() -> GeomVertexFormat:
    a = GeomVertexArrayFormat()
    a.add_column(InternalName.get_vertex(), 3, Geom.NT_float32, Geom.C_point)
    a.add_column(InternalName.make('corner'), 2, Geom.NT_float32, Geom.C_other)
    a.add_column(InternalName.make('drop'), 3, Geom.NT_float32, Geom.C_other)
    a.add_column(InternalName.make('look'), 2, Geom.NT_float32, Geom.C_other)
    return GeomVertexFormat.register_format(GeomVertexFormat(a))


class WaterSplash:
    def __init__(self, data: SplashData, light, surface_y: float, capacity: int = CAPACITY):
        self.d = data
        self.surface_y = surface_y
        self.capacity = capacity
        self.share = 1.0                                       # graphics level: share of the drops drawn (0 = none)
        self.sim = SplashSim(capacity)
        self.water = None                                      # WaterSurface, for the tiny pushes of falling drops
        self.vdata = GeomVertexData('splash', _format(), Geom.UH_dynamic)
        self.vdata.set_num_rows(capacity * 4)
        prim = GeomTriangles(Geom.UH_static)
        for i in range(capacity):
            a = i * 4
            prim.add_vertices(a, a + 1, a + 2)
            prim.add_vertices(a, a + 2, a + 3)
        prim.close_primitive()
        geom = Geom(self.vdata)
        geom.add_primitive(prim)
        node = GeomNode('water_splash')
        node.add_geom(geom)
        node.set_bounds(OmniBoundingVolume())
        node.set_final(True)
        self.root = application.base.render.attach_new_node(node)
        r = self.root
        r.set_shader(load_glsl('splash'), 2)
        r.set_transparency(TransparencyAttrib.M_alpha)
        r.set_depth_write(False)
        r.set_two_sided(True)
        r.set_bin('transparent', 12)
        r.set_light_off()
        light.bind(r)
        r.set_shader_input('look_fog', Vec4(0, 0, 0, 0))
        self._zeros = array('f', bytes(4 * FLOATS * 4 * capacity))
        self._drawn = 0
        self._write([])

    def _count(self, n: int) -> int:
        return int(round(n * self.share))

    def bullet(self, point):
        d = self.d
        self.sim.burst((point[0], self.surface_y, point[2]), self._count(d.bullet_drops), d.bullet_speed, d.speed_jitter, d.bullet_cone, d.drop_size, d.drop_life)

    def land(self, x: float, z: float, speed: float = 1.0):
        d = self.d
        self.sim.burst((x, self.surface_y, z), self._count(d.land_drops * min(max(speed, 0.4), 1.5)), d.land_speed, d.speed_jitter, d.land_cone, d.drop_size * 1.3, d.drop_life)

    def wade(self, x: float, z: float, running: bool):
        d = self.d
        n = self._count(d.wade_drops * (2 if running else 1))
        self.sim.burst((x, self.surface_y, z), n, 1.3 if running else 0.9, d.speed_jitter, 55.0, d.drop_size, d.drop_life * 0.6)

    def update(self, dt: float):
        sim = self.sim
        if sim.count == 0 and self._drawn == 0:
            return
        fell = sim.step(dt, self.d.gravity, self.d.drag, self.surface_y)
        if self.water is not None:
            for x, _, z in fell[:FALL_PUSHES_PER_FRAME]:
                self.water.push(x, z, FALL_PUSH[1], FALL_PUSH[0])
        self._write(sim.draw_items())

    def _write(self, items: list):
        buf = []
        ext = buf.extend
        for x, y, z, vx, vy, vz, rad, a in items:
            for u, v in CORNERS:
                ext((x, y, z, u, v, vx, vy, vz, rad, a))
        data = array('f', buf)
        n = len(items)
        if n < self._drawn:
            data.extend(self._zeros[: (self._drawn - n) * 4 * FLOATS])
        self._drawn = n
        if len(data) == 0:
            return
        handle = self.vdata.modify_array_handle(0)
        if len(data) * 4 == handle.get_data_size_bytes():
            handle.copy_data_from(data)
        else:
            handle.copy_subdata_from(0, len(data) * 4, data)
