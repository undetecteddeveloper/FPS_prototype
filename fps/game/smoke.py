"""Draws the gunpowder smoke simulated by core/smoke.py: ONE dynamic mesh for the whole pool (one draw call), camera-facing quads expanded in assets/shaders/smoke.vert.

Kept light for integrated graphics (Intel UHD 620): at most CAPACITY puffs; no textures (the soft edge and the wisps are a few maths in the fragment shader);
the vertex data is rebuilt in one Python array and copied to the GPU in one call, only while some smoke is alive. Fill rate is the real cost of smoke
(big transparent quads stacked on top of each other), so a puff that covers a large part of the view (close to the eye, or grown big) fades out by its
angular size (`FILL_FADE`), and the fragment shader discards nearly transparent pixels.
Puffs are sorted back to front on the CPU every frame so the alpha blending stacks correctly.
"""
import math
from array import array

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, InternalName,
                          OmniBoundingVolume, TransparencyAttrib, Vec2, Vec3, Vec4)
from ursina import application, camera

from fps.core.smoke import SmokeSim, thin_items
from fps.game.shaders import load_glsl, prepare
from fps.weapon_data import SMOKE_SIMPLE_KEEP, LookData, SmokeData

CAPACITY = 128                   # puffs: M4 full auto (12.5 shots/s x 7 puffs x ~1 s) stays just under it; the oldest puff is reused past it
FILL_FADE = (0.45, 0.9)          # radius / distance: a puff fades out between these angular sizes (it would cover a big part of the screen)
FLOATS = 8                       # per vertex: centre xyz, corner xy, radius, alpha, seed
CORNERS = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))


def _format() -> GeomVertexFormat:
    a = GeomVertexArrayFormat()
    a.add_column(InternalName.get_vertex(), 3, Geom.NT_float32, Geom.C_point)
    a.add_column(InternalName.make('corner'), 2, Geom.NT_float32, Geom.C_other)
    a.add_column(InternalName.make('puff'), 3, Geom.NT_float32, Geom.C_other)
    return GeomVertexFormat.register_format(GeomVertexFormat(a))


class GunSmoke:
    def __init__(self, look: LookData, light, capacity: int = CAPACITY):
        self.look = look
        self.light = light
        self.capacity = capacity
        self.sim = SmokeSim(capacity)
        self.vdata = GeomVertexData('smoke', _format(), Geom.UH_dynamic)
        self.vdata.set_num_rows(capacity * 4)
        prim = GeomTriangles(Geom.UH_static)
        for i in range(capacity):
            a = i * 4
            prim.add_vertices(a, a + 1, a + 2)
            prim.add_vertices(a, a + 2, a + 3)
        prim.close_primitive()
        geom = Geom(self.vdata)
        geom.add_primitive(prim)
        node = GeomNode('gun_smoke')
        node.add_geom(geom)
        node.set_bounds(OmniBoundingVolume())        # vertices are expanded in the shader: never cull
        node.set_final(True)
        self.root = application.base.render.attach_new_node(node)
        r = self.root
        self.shaders = {False: load_glsl('smoke'), True: load_glsl('smoke', defines=('SMOKE_LITE',))}    # G13: full / simple (F2 'Khói súng')
        for sh in self.shaders.values():
            prepare(sh)
        self.simple = False
        r.set_shader(self.shaders[False], 2)
        r.set_transparency(TransparencyAttrib.M_alpha)
        r.set_depth_write(False)
        r.set_two_sided(True)
        r.set_bin('transparent', 10)
        r.set_light_off()
        light.bind(r)                                # sun / sky / exposure / camera position, shared with the world and the gun
        r.set_shader_input('smoke_right', light.view_x)
        r.set_shader_input('smoke_up', light.view_y)
        self._zeros = array('f', bytes(4 * FLOATS * 4 * capacity))
        self._drawn = 0                              # puffs written last frame (so the slots they used are cleared once)
        self._color = SmokeData().color
        r.set_shader_input('smoke_color', Vec3(*self._color))
        self._apply_look()
        self._write([])

    def set_simple(self, simple: bool):
        """G13: F2 'Khói súng' (simple on level Low). Both builds were compiled and drawn at start-up (Game.warm_shader_builds)."""
        if simple != self.simple:
            self.simple = simple
            self.root.set_shader(self.shaders[simple], 2)

    def _apply_look(self):
        lk = self.look
        self.root.set_shader_input('smoke_fog', Vec4(*lk.fog_color, lk.fog_density))
        self.root.set_shader_input('smoke_fill', Vec2(*FILL_FADE))

    def emit(self, data, origin, direction, port=None, port_dir=None):
        self.sim.emit(data, origin, direction, port, port_dir)
        self._color = data.color

    def update(self, dt: float):
        """Every frame, AFTER FrameLight.set_camera (the billboards face this frame's camera)."""
        sim = self.sim
        if sim.count == 0 and self._drawn == 0:
            return
        sim.step(dt, self.look.wind, 0.0)
        self._apply_look()
        self._write(sim.draw_items())

    def _write(self, items: list):
        if self.simple:
            items = thin_items(items, SMOKE_SIMPLE_KEEP)
        cx, cy, cz = camera.world_position
        if len(items) > 1:                           # back to front
            items.sort(key=lambda p: -((p[0] - cx) ** 2 + (p[1] - cy) ** 2 + (p[2] - cz) ** 2))
        buf = []
        ext = buf.extend
        for x, y, z, rad, alpha, seed in items:
            for u, v in CORNERS:
                ext((x, y, z, u, v, rad, alpha, seed))
        data = array('f', buf)
        n = len(items)
        if n < self._drawn:                          # clear the slots used last frame and not this one (zero radius = nothing drawn)
            data.extend(self._zeros[: (self._drawn - n) * 4 * FLOATS])
        self._drawn = n
        if len(data) == 0:
            return
        handle = self.vdata.modify_array_handle(0)
        if len(data) * 4 == handle.get_data_size_bytes():
            handle.copy_data_from(data)
        else:                                        # partial write: only the first slots changed
            handle.copy_subdata_from(0, len(data) * 4, data)
        self.root.set_shader_input('smoke_color', Vec3(*self._color))

    def destroy(self):
        self.root.remove_node()
