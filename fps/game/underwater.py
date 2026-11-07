"""G12: the camera at and under the water surface, wired to Panda. The math is in core/underwater.py (waterline on the lens port) and core/wetlens.py (wet lens).

Every frame (Game.update, after the camera got its final position): where the waterline crosses the lens port -> the underwater.glsl inputs that every world shader,
the gun and the lens read; the basin mesh (core/poolmap.py `basin_faces`) is drawn only while some pixel looks through the water; under the water the trigger is refused
and the dust motes are hidden; the zoom of the flat port blends in; after surfacing the lens drains (film + drops).
"""
from ursina import camera
from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, Vec4

from fps.core import underwater as uw
from fps.core.wetlens import WetLens
from fps.game.lens import DROP_SLOTS
from fps.core.graphics import lite_basin
from fps.game.shaders import load_glsl, prepare
from fps.core.poolmap import basin_faces, ramp_quad
from fps.weapon_data import GraphicsLevel, UnderwaterData, WaterData

SHARE_GRID = 12          # grid size of the wet-share count (it only drives the zoom and the wet lens)
NEAR_DEFAULT = 0.1       # Ursina's camera near plane (m)
NEAR_CLOSE = 0.01        # ... while the eye is within NEAR_RANGE of the water surface
NEAR_RANGE = 0.3


def basin_node(pm) -> GeomNode:
    """One mesh of the pool basin under the water (world coordinates, flat normals toward the water)."""
    quads = []
    for f in basin_faces(pm):
        quads.append(([f.point(u, v) for u, v in ((f.u0, f.v0), (f.u1, f.v0), (f.u1, f.v1), (f.u0, f.v1))], f.normal))
    rq = ramp_quad(pm)
    if rq is not None:
        quads.append(rq)
    vdata = GeomVertexData('basin', GeomVertexFormat.get_v3n3(), Geom.UH_static)
    vdata.set_num_rows(4 * len(quads))
    wv, wn = GeomVertexWriter(vdata, 'vertex'), GeomVertexWriter(vdata, 'normal')
    prim = GeomTriangles(Geom.UH_static)
    for i, (corners, n) in enumerate(quads):
        for c in corners:
            wv.add_data3(*c)
            wn.add_data3(*n)
        b = 4 * i
        prim.add_vertices(b, b + 1, b + 2)
        prim.add_vertices(b, b + 2, b + 3)
    geom = Geom(vdata)
    geom.add_primitive(prim)
    node = GeomNode('pool_basin')
    node.add_geom(geom)
    return node


class Underwater:
    def __init__(self, d: UnderwaterData, water_params: WaterData, pool, light):
        self.d, self.w = d, water_params
        self.pool, self.light = pool, light
        x0, x1, z0, z1, self.water_y = pool.pm.water
        self.rect = (x0, x1, z0, z1)
        self.basin = pool.water.node.attach_new_node(basin_node(pool.pm))       # child of the water node: inherits every water_* input
        self.basin.set_two_sided(True)
        self.basin_shaders = {False: load_glsl('basin'), True: load_glsl('basin', defines=('POOL_LITE',))}    # G13: full / lite (Low) build
        for sh in self.basin_shaders.values():
            prepare(sh)
        self.basin_lite = False
        self.basin.set_shader(self.basin_shaders[False], 2)
        self.warm_frames = 3                 # drawn (behind the water) the first frames so its shader compiles at start, not at the first dip
        self.wetlens = WetLens(d)
        self.full_quality = True
        self.wetlens_on = True
        self.clock = 0.0
        self._near = NEAR_DEFAULT
        self.zoom_mix = 0.0                  # 0 .. 1 blend of the flat-port zoom (fully under)
        # the last frame's state, for the game and the checks
        self.line = (0.0, 0.0, 1.0)
        self.any_wet = self.all_wet = self.eye_under = False
        self.share = 0.0
        self.surface = self.water_y
        self._amp = 0.0
        self.apply_params()

    def apply_params(self):
        d, u = self.d, self.light.under
        a = self.w.absorption
        u['look_under_fog'].set_element(0, Vec4(*d.fog_color, d.turbidity))
        u['look_under_abs'].set_element(0, Vec4(a[0] * d.absorb_scale, a[1] * d.absorb_scale, a[2] * d.absorb_scale, 1.0 if self.eye_under else 0.0))
        u['look_under3'].set_element(0, Vec4(1.0 if self.full_quality else 0.0, d.snell_ripple, d.gun_fog, 0.0))

    def set_level(self, g: GraphicsLevel):
        self.full_quality = g.under > 0
        self.wetlens_on = g.wetlens
        lite = lite_basin(g)
        if lite != self.basin_lite:
            self.basin_lite = lite
            self.basin.set_shader(self.basin_shaders[lite], 2)
        self.apply_params()

    def update(self, dt: float, eye, right, up, aspect: float, buffer_size: tuple, speed: float):
        """`eye`, `right`, `up`: the world camera this frame; `speed` = the player's horizontal speed (the waterline laps more when walking)."""
        d = self.d
        self.clock += dt
        ex, ey, ez = eye
        if uw.in_pool(ex, ez, self.rect):
            self.surface = uw.surface_y(ex, ez, self.clock, self.water_y, self.w)
            self.line = uw.port_line(ey, self.surface, right[1], up[1], aspect, d.port_half)
        else:
            self.surface = self.water_y
            self.line = (0.0, 0.0, 10.0)                                       # on the deck: never wet
        amp = d.wobble + d.wobble_speed * speed
        self._amp = amp
        self.any_wet, self.all_wet = uw.coverage(self.line, amp)
        self.eye_under = self.line[2] < 0.0
        # G13: the water's lite build can drop the branches this frame cannot take (water.frag VIEW_DRY / VIEW_UNDER). 'under' needs the eye below the FLAT
        # quad too (the shader's `below` test), not only below the wavy surface
        self.pool.water.set_view('dry' if not self.any_wet else ('under' if self.all_wet and ey < self.water_y - 1e-3 else 'any'))
        self.share = (1.0 if self.all_wet else uw.wet_share(self.line, SHARE_GRID)) if self.any_wet else 0.0
        a, b, c = self.line
        u = self.light.under
        u['look_under'].set_element(0, Vec4(a, b, c, amp))
        w, h = buffer_size
        u['look_under2'].set_element(0, Vec4(1.0 if self.any_wet else 0.0, self.clock % 1000.0, 2.0 / max(w, 1), 2.0 / max(h, 1)))
        self.apply_params()
        if self.warm_frames > 0:
            self.warm_frames -= 1
        if self.any_wet or self.eye_under or self.warm_frames > 0:
            self.basin.show()
        else:
            self.basin.hide()
        near = NEAR_CLOSE if abs(self.line[2]) < NEAR_RANGE and uw.in_pool(ex, ez, self.rect) else NEAR_DEFAULT
        if near != self._near:                                                 # the eye right at the surface: the default 0.1 m near plane would cut the water away in front
            self._near = near
            camera.clip_plane_near = near
        self.zoom_mix = uw.step_toward(self.zoom_mix, 1.0 if self.all_wet else 0.0, d.zoom_time, dt)
        self.wetlens.update(dt, self.share if self.wetlens_on else 0.0, uw.wet_top(self.line))

    def lens_inputs(self) -> tuple:
        """Arguments of Lens.set_wet for this frame."""
        d, z = self.d, self.zoom_mix
        edge, strength = self.wetlens.film() if self.wetlens_on else (-1.0, 0.0)
        drops = self.wetlens.packed(DROP_SLOTS) if self.wetlens_on else []
        return edge, strength, d.film_blur, 1.0 + (d.zoom - 1.0) * z, d.warp * z, drops, d.drop_refract, d.meniscus, self.line, self._amp


class UnderwaterAudio:
    """The underwater tone cross-faded with the room tone while the eye is under the surface. The tone file is optional (tools/build/prep_underwater.py builds it): without it nothing changes.
    The foley sounds swap to their muffled twins in Foley (`Foley.under`); no low-pass filter at run time (OpenAL cannot; the user chose pre-filtered copies, G12)."""

    def __init__(self, audio, root, room_tone=None):
        from panda3d.core import Filename
        from ursina import application
        self.a, self.room_tone = audio, room_tone
        path = root / audio.under_ambience_file
        self.tone = None
        if path.exists():
            self.tone = application.base.loader.load_sfx(Filename.from_os_specific(str(path)))
            self.tone.set_loop(True)
            self.tone.set_volume(0.0)
            self.tone.play()
        self.mix = 0.0                       # 0 room tone .. 1 underwater tone

    def update(self, dt: float, under: bool):
        a = self.a
        self.mix = uw.step_toward(self.mix, 1.0 if under else 0.0, a.under_fade, dt)
        if self.tone is not None:
            self.tone.set_volume(a.under_ambience_volume * self.mix)
            if self.room_tone is not None:
                self.room_tone.set_volume(a.ambience_volume * (1.0 - self.mix))
