"""The pool water: one flat quad drawn by assets/shaders/water.*, the waves (G10: GPU simulation, game/water_sim.py; graphics level Low: the G9 analytic rings), and the box bullets hit.

Per-frame values live in PTA arrays edited in place (calling `set_shader_input` every frame would change the draw state of the whole scene graph, like in frame_light.py).
`is_water` / `splash` are what Combat looks for on the owner of a hit box: a bullet that lands on the water makes a wave (and a sound once there is one), not a bullet hole.
"""
import struct

from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, PTA_LVecBase3f, PTA_LVecBase4f, Texture, Vec3, Vec4
from ursina import Entity

from fps.core.cubemap import TAN_HALF, basis
from fps.core.graphics import water_flags
from fps.core.poolmap import AmbientGrid, PoolMap, basin_boxes
from fps.core.waves import RippleBuffer
from fps.game.shaders import load_glsl
from fps.game.water_sim import WaterSim
from fps.weapon_data import GraphicsLevel, WaterData

MARGIN = 0.01          # the quad reaches this far under the pool wall (hidden inside the deck box)
STEP_SLOTS = 8         # step boxes the refracted ray is traced against (the map has 6)


def grid_texture(name: str, grid: list) -> Texture:
    """[nz][nx][r, g, b] floats -> a small float texture (row 0 = z0), linear filtering."""
    nz, nx = len(grid), len(grid[0])
    tex = Texture(name)
    tex.setup_2d_texture(nx, nz, Texture.T_float, Texture.F_rgb32)
    data = b''.join(struct.pack('<3f', *grid[j][i][::-1]) for j in range(nz) for i in range(nx))      # Panda stores BGR
    tex.set_ram_image(data)
    tex.set_wrap_u(Texture.WM_clamp)
    tex.set_wrap_v(Texture.WM_clamp)
    tex.set_minfilter(Texture.FT_linear)
    tex.set_magfilter(Texture.FT_linear)
    return tex


class WaterSurface:
    is_water = True

    def __init__(self, pm: PoolMap, params: WaterData, ambient: AmbientGrid = None):
        self.pm, self.p = pm, params
        self.clock = 0.0
        self.ripples = RippleBuffer(params.ripple_slots)
        self.on_splash = None                       # callable(point, distance) set by Game once the water has a sound
        x0, x1, z0, z1, y = pm.water
        self.rect = (x0, x1, z0, z1)
        self.y = y
        self.sim = None                             # WaterSim, built by `set_level` when the graphics level asks for one
        self._sim_size = (0, 0)
        self.entity = Entity(add_to_scene_entities=False)
        self.node = self.entity.attach_new_node(self._quad(x0 - MARGIN, x1 + MARGIN, z0 - MARGIN, z1 + MARGIN, y))
        self.node.set_two_sided(True)
        self.node.set_shader(load_glsl('water', defines=(f'RING_SLOTS {params.ripple_slots}', f'STEP_SLOTS {STEP_SLOTS}')), 1)
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
        # G10: the basin the refracted ray is traced against, the baked ambient that lights its bottom, the simulation textures (placeholders until a level builds the sim)
        (blo, bhi), steps = basin_boxes(pm)
        n.set_shader_input('water_basin_lo', Vec4(*blo, 0))
        n.set_shader_input('water_basin_hi', Vec4(*bhi, 0))
        r = pm.ramp or (x0, x1, -1.0, 1.0, blo[1], blo[1])
        n.set_shader_input('water_ramp', Vec4(r[2], r[3], r[4], r[5]))
        steps = (steps + [((0, -9, 0), (0, -9, 0))] * STEP_SLOTS)[:STEP_SLOTS]           # unused slots: an empty box far below
        lo_pta, hi_pta = PTA_LVecBase4f.empty_array(STEP_SLOTS), PTA_LVecBase4f.empty_array(STEP_SLOTS)
        for i, (slo, shi) in enumerate(steps):
            lo_pta.set_element(i, Vec4(*slo, 0))
            hi_pta.set_element(i, Vec4(*shi, 0))
        n.set_shader_input('water_steps_lo', lo_pta)
        n.set_shader_input('water_steps_hi', hi_pta)
        if ambient is not None:
            n.set_shader_input('water_amb_up', grid_texture('water_amb_up', ambient.up))
            n.set_shader_input('water_amb_down', grid_texture('water_amb_down', ambient.down))
            n.set_shader_input('water_amb_grid', Vec4(ambient.x0, ambient.z0, ambient.step, 0))
        else:
            flat = grid_texture('water_amb_flat', [[[0.3, 0.3, 0.3]] * 2] * 2)
            n.set_shader_input('water_amb_up', flat)
            n.set_shader_input('water_amb_down', flat)
            n.set_shader_input('water_amb_grid', Vec4(0, 0, 100, 0))
        still = Texture('water_sim_still')
        still.setup_2d_texture(1, 1, Texture.T_float, Texture.F_rgba32)
        still.set_ram_image(bytes(16))
        n.set_shader_input('water_sim_a', still)
        n.set_shader_input('water_sim_b', still)
        self._still_pick = PTA_LVecBase4f.empty_array(1)
        n.set_shader_input('water_sim_pick', self._still_pick)
        self.quality = PTA_LVecBase4f.empty_array(1)
        n.set_shader_input('water_quality', self.quality)
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

    def set_level(self, g: GraphicsLevel):
        """Graphics level (F2): shader flags, and the wave simulation built / resized / switched off. Building a 256 x 512 sim takes a few ms (two float buffers)."""
        self.quality.set_element(0, Vec4(*water_flags(g)))
        if g.sim_cols == 0:                         # Low: the sim only stops (its buffers stay: removing them stalled the switch frame to 71 ms)
            if self.sim is not None:
                self.sim.set_enabled(False)
            return
        size = (g.sim_cols, g.sim_rows)
        if self.sim is not None:
            self.sim.set_enabled(True)
        if size != self._sim_size:
            if self.sim is not None:
                self.sim.destroy()
                self.sim = None
            if g.sim_cols > 0:
                self.sim = WaterSim(self.rect, g.sim_cols, g.sim_rows, self.p.sim_speed, self.p.sim_life)
                n = self.node
                n.set_shader_input('water_sim_a', self.sim.textures[0])
                n.set_shader_input('water_sim_b', self.sim.textures[1])
                n.set_shader_input('water_sim_pick', self.sim.pick)
            self._sim_size = size

    def apply_params(self):
        """Pushes the WaterData numbers (F1 panel) to the shader."""
        p, n = self.p, self.node
        n.set_shader_input('water_look', Vec4(p.ripple_strength, p.ripple_scale, p.ripple_speed, p.reflect_strength))
        n.set_shader_input('water_deep', Vec4(*p.deep_color, p.fresnel_f0))
        n.set_shader_input('water_shallow', Vec4(*p.shallow_color, p.shallow_width))
        n.set_shader_input('water_impact', Vec4(p.impact_speed, p.impact_wavelength, p.impact_width, p.impact_life))
        n.set_shader_input('water_impact2', Vec4(p.impact_strength, p.impact_reach, TAN_HALF, 0.0))
        n.set_shader_input('water_basin', Vec4(*p.basin_color, p.basin_tile))
        n.set_shader_input('water_absorb', Vec4(*p.absorption, p.basin_light))
        n.set_shader_input('water_caustic', Vec4(p.caustic_strength, p.caustic_ambient, p.caustic_scale, p.caustic_speed))
        n.set_shader_input('water_glint', Vec4(p.glint_strength, p.glint_power, p.sim_slope, p.caustic_waves))
        if self.sim is not None:
            self.sim.set_physics(p.sim_speed, p.sim_life)

    def collider(self) -> tuple:
        """(lo, hi, owner): a thin box just under the surface, so a bullet coming from above hits its top face at the water level."""
        x0, x1, z0, z1 = self.rect
        return (x0, self.y - 0.02, z0), (x1, self.y, z1), self

    def push(self, x: float, z: float, radius: float, amount: float):
        """Push the surface (feet, splashes). No-op on graphics level Low (the simulation is stopped)."""
        if self.sim is not None and self.sim.enabled:
            self.sim.push(x, z, radius, amount)

    def splash(self, point, distance: float, amp: float = 1.0):
        """A bullet landed at `point`: a push into the simulation (Mid / High) and a ring (Low draws the rings), and the sound hook."""
        self.ripples.add(point[0], point[2], self.clock, amp)
        for i, ring in enumerate(self.ripples.packed()):
            self.rings_pta.set_element(i, Vec4(*ring))
        self.push(point[0], point[2], self.p.bullet_radius, self.p.bullet_push * amp)
        if self.on_splash:
            self.on_splash(point, distance)

    def update(self, dt: float):
        self.clock += dt
        self.time_pta.set_element(0, Vec3(self.clock, 0, 0))
        if self.sim is not None:
            self.sim.update(dt)
