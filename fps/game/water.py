"""The pool water: one flat quad drawn by assets/shaders/water.*, the waves (G10: GPU simulation, game/water_sim.py; graphics level Low: the G9 analytic rings), and the box bullets hit.

Per-frame values live in PTA arrays edited in place (calling `set_shader_input` every frame would change the draw state of the whole scene graph, like in frame_light.py).
`is_water` / `splash` are what Combat looks for on the owner of a hit box: a bullet that lands on the water makes a wave (and a sound once there is one), not a bullet hole.
"""
import struct

from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, PTA_LVecBase3f, PTA_LVecBase4f, Texture, Vec3, Vec4
from ursina import Entity

from fps.core import caustics
from fps.core.cubemap import TAN_HALF, basis
from fps.core.graphics import CAUSTIC_SIZES, lite_water, water_flags
from fps.core.poolmap import AmbientGrid, PoolMap, basin_boxes
from fps.core.waves import RippleBuffer
from fps.game.shaders import load_glsl, prepare
from fps.game.caustics import CausticPass
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

    def __init__(self, pm: PoolMap, params: WaterData, ambient: AmbientGrid = None, sun: tuple = (0.0, 1.0, 0.0)):
        self.pm, self.p = pm, params
        self.sun = sun
        self.clock = 0.0
        self.ripples = RippleBuffer(params.ripple_slots)
        self.on_splash = None                       # callable(point, distance) set by Game once the water has a sound
        self.on_bullet = None                       # callable(point): the droplets thrown up (game/splash.py), set by PoolHall.attach_splash
        x0, x1, z0, z1, y = pm.water
        self.rect = (x0, x1, z0, z1)
        self.y = y
        self.sim = None                             # WaterSim, built by `set_level` when the graphics level asks for one
        self._sim_size = (0, 0)
        self.caustics = None                        # CausticPass (G11), built by `set_level`
        self._caustic_size = 0
        self.entity = Entity(add_to_scene_entities=False)
        self.node = self.entity.attach_new_node(self._quad(x0 - MARGIN, x1 + MARGIN, z0 - MARGIN, z1 + MARGIN, y))
        self.node.set_two_sided(True)
        defines = (f'RING_SLOTS {params.ripple_slots}', f'STEP_SLOTS {STEP_SLOTS}')
        # G13: the full build; on Low (core/graphics.py lite_water) the lite build, plus two lite builds for a frame known to be all dry / all under (`set_view`)
        self.shaders = {(False, 'any'): load_glsl('water', defines=defines)}
        for view, extra in (('any', ()), ('dry', ('VIEW_DRY',)), ('under', ('VIEW_UNDER',))):
            self.shaders[(True, view)] = load_glsl('water', defines=defines + ('POOL_LITE',) + extra)
        for sh in self.shaders.values():
            prepare(sh)
        self.lite = False
        self.view = 'any'
        self._build = (False, 'any')
        self.node.set_shader(self.shaders[self._build], 1)
        self._live = 0                              # G13: rings still spreading; packed first in `rings_pta`, their count in water_time.y (the shader loops over those only)
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
        n.set_shader_input('cube_params', Vec4(TAN_HALF, 0, 0, 0))
        self.placeholder = Texture('water_reflect_placeholder')
        self.placeholder.setup_2d_texture(1, 1, Texture.T_unsigned_byte, Texture.F_rgb)
        self.placeholder.set_ram_image(bytes([60, 70, 80]))
        n.set_shader_input('water_reflect', self.placeholder)
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
        self._still = still
        # G11: the small ripples shared by this shader and the caustic pass (pool_waves.glsl), and the caustic texture (a 1 x 1 'flat light' until a level builds the pass)
        self.wave_a, self.wave_b = PTA_LVecBase4f.empty_array(caustics.N_WAVES), PTA_LVecBase4f.empty_array(caustics.N_WAVES)
        n.set_shader_input('wave_a', self.wave_a)
        n.set_shader_input('wave_b', self.wave_b)
        self.caus_params = PTA_LVecBase4f.empty_array(1)          # water level, weight of the simulated waves, clock, -
        self.caus_sim_on = PTA_LVecBase4f.empty_array(1)
        self.ramp = (r[2], r[3], r[4], r[5])
        self.domain = caustics.domain(self.rect, sun, y - blo[1] + 0.1)
        self.flat_caustic = Texture('caustics_flat')
        self.flat_caustic.setup_2d_texture(1, 1, Texture.T_float, Texture.F_r32)
        self.flat_caustic.set_ram_image(struct.pack('<f', 1.0))
        n.set_shader_input('water_caus_tex', self.flat_caustic)
        n.set_shader_input('water_caus_domain', Vec4(*self.domain))
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
        self.lite = lite_water(g)
        self._pick_build()
        if g.sim_cols == 0:                         # Low: the sim only stops (its buffers stay: removing them stalled the switch frame to 71 ms)
            if self.sim is not None:
                self.sim.set_enabled(False)
            self._set_caustics(g)
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
        self._set_caustics(g)

    def set_view(self, view: str):
        """G13, every frame from game/underwater.py: 'dry' (no pixel can look through the water), 'under' (every pixel does and the eye is below the surface
        plane) or 'any'. Only the lite build has view-specific twins; all were compiled at start-up, so switching costs nothing."""
        if view != self.view:
            self.view = view
            self._pick_build()

    def _pick_build(self):
        build = (True, self.view) if self.lite else (False, 'any')
        if build != self._build:
            self._build = build
            self.node.set_shader(self.shaders[build], 1)

    def _set_caustics(self, g: GraphicsLevel):
        """Build / resize / stop the caustic pass (only useful when the bottom is seen)."""
        want = g.caustics if g.refraction else 0
        if want == 0:
            if self.caustics is not None:
                self.caustics.set_enabled(False)
            self._sync_caustic_inputs()
            return
        if self.caustics is not None and want != self._caustic_size:
            self.caustics.destroy()
            self.caustics = None
        if self.caustics is None:
            cols, rows, tex_long = CAUSTIC_SIZES[want]
            self.caustics = CausticPass(self.rect, self.domain, cols, rows, tex_long, self.y, self.ramp, self.sun, self._caustic_shared())
            self._caustic_size = want
        self.caustics.set_enabled(True)
        self._sync_caustic_inputs()

    def _caustic_shared(self) -> dict:
        sim_on = self.sim is not None and self.sim.enabled
        return {'wave_a': self.wave_a, 'wave_b': self.wave_b, 'caus_params': self.caus_params, 'caus_sim_on': self.caus_sim_on,
                'water_sim_a': self.sim.textures[0] if sim_on else self._still, 'water_sim_b': self.sim.textures[1] if sim_on else self._still,
                'water_sim_pick': self.sim.pick if sim_on else self._still_pick}

    def _sync_caustic_inputs(self):
        """The simulation textures the pass reads, and which caustic texture the water reads (flat light when the pass is off)."""
        sim_on = self.sim is not None and self.sim.enabled
        self.caus_sim_on.set_element(0, Vec4(1.0 if sim_on else 0.0, 0, 0, 0))
        on = self.caustics is not None and self.caustics.enabled
        if self.caustics is not None:
            for name, value in self._caustic_shared().items():
                self.caustics.set_input(name, value)
        self.node.set_shader_input('water_caus_tex', self.caustics.texture if on else self.flat_caustic)

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
        n.set_shader_input('water_caustic', Vec4(p.caustic_strength, p.caustic_ambient, p.caustic_wall, p.caustic_peak))
        n.set_shader_input('water_caustic2', Vec4(p.caustic_white, p.wave_bend, p.wave_mirror, 0.0))
        n.set_shader_input('water_glint', Vec4(p.glint_strength, p.glint_power, p.sim_slope, 0.0))
        wa, wb = caustics.pack(caustics.wave_table(p.wave_size, p.wave_height, p.wave_speed))
        for i in range(caustics.N_WAVES):
            self.wave_a.set_element(i, Vec4(*wa[i]))
            self.wave_b.set_element(i, Vec4(*wb[i]))
        self.caus_params.set_element(0, Vec4(self.y, p.caustic_sim, self.clock, 0.0))
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
        self._push_rings()
        self.push(point[0], point[2], self.p.bullet_radius, self.p.bullet_push * amp)
        if self.on_bullet:
            self.on_bullet(point)
        if self.on_splash:
            self.on_splash(point, distance)

    def _push_rings(self):
        """The live rings first (same values as before), then empty slots; their count goes to the shader with the clock."""
        life = self.p.impact_life
        live = [r for r in self.ripples.packed() if 0.0 <= self.clock - r[2] < life]
        for i in range(self.p.ripple_slots):
            self.rings_pta.set_element(i, Vec4(*live[i]) if i < len(live) else Vec4(0, 0, -1e6, 0))
        self._live = len(live)

    def update(self, dt: float):
        self.clock += dt
        if self.ripples.alive(self.clock, self.p.impact_life) != self._live:        # a ring died out (or F1 changed the ring life)
            self._push_rings()
        self.time_pta.set_element(0, Vec3(self.clock, float(self._live), 0))
        self.caus_params.set_element(0, Vec4(self.y, self.p.caustic_sim, self.clock, 0.0))
        if self.sim is not None:
            self.sim.update(dt)
