"""Bullet holes merged into one mesh: one draw call for the whole pool, instead of one Entity (one draw call) per hole.

All holes share one mesh of `capacity` quads (4 vertices each). Every hole lives `FeedbackParams.hole_life` seconds (1.5 s, core/holes.py `HoleRing`): the shader fades it out over the last
`hole_fade` seconds, then its quad is collapsed (4 coincident vertices draw nothing) and, once no hole is alive, the whole mesh is hidden. The mesh is re-uploaded only when a hole is
born or dies. The look (a crater with cracks, sunk in by parallax) is in assets/shaders/decal.frag and the atlas tools/build/make_surface_textures.py builds.
"""
import math
import random

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, GeomVertexWriter, InternalName,
                          OmniBoundingVolume, PTA_LVecBase4f, SamplerState, Texture as PandaTexture, TransparencyAttrib, Vec4)
from PIL import Image
from ursina import Entity, application, scene

from fps.core.ballistics import hole_size
from fps.core.holes import HoleRing
from fps.game.shaders import load_glsl, prepare
from fps.game.surface_tex import flat_relief, read_texture, white
from fps.weapon_data import FeedbackParams

WHITE = (1.0, 1.0, 1.0, 1.0)
CELLS = 2                         # the atlas is CELLS x CELLS different holes (decal.frag CELLS; tools/build/surface_textures.py bullet_hole_atlas)
DEPTH = 0.16                      # deepest point of a hole as a share of the decal's width (tools/build/surface_textures.py HOLE_DEPTH: the relief's normals assume the same number)
PARALLAX_STEPS = 12


def _basis(normal: tuple) -> tuple:
    """Two axes lying on the hit surface, perpendicular to the normal."""
    nx, ny, nz = normal
    ax = (0.0, 1.0, 0.0) if abs(ny) < 0.9 else (1.0, 0.0, 0.0)
    ux, uy, uz = ax[1] * nz - ax[2] * ny, ax[2] * nx - ax[0] * nz, ax[0] * ny - ax[1] * nx
    n = math.sqrt(ux * ux + uy * uy + uz * uz) or 1.0
    ux, uy, uz = ux / n, uy / n, uz / n
    return (ux, uy, uz), (ny * uz - nz * uy, nz * ux - nx * uz, nx * uy - ny * ux)


def _vertex_format():
    arr = GeomVertexArrayFormat()
    arr.add_column(InternalName.get_vertex(), 3, Geom.NT_float32, Geom.C_point)
    arr.add_column(InternalName.get_color(), 4, Geom.NT_float32, Geom.C_color)
    arr.add_column(InternalName.get_texcoord(), 2, Geom.NT_float32, Geom.C_texcoord)
    arr.add_column(InternalName.make('lightmap'), 2, Geom.NT_float32, Geom.C_other)       # where the wall's baked light is (-1, -1 = none); read by name in decal.vert
    arr.add_column(InternalName.make('hole'), 4, Geom.NT_float32, Geom.C_other)           # birth clock, atlas cell, decal width (m), -
    fmt = GeomVertexFormat()
    fmt.add_array(arr)
    return GeomVertexFormat.register_format(fmt)


def _placeholder_color() -> PandaTexture:
    """A plain dark round hole in every cell of a 2 x 2 atlas (used only when assets/textures/bullet_hole_color.png is missing)."""
    cell = 32
    img = Image.new('RGBA', (cell * CELLS, cell * CELLS), (0, 0, 0, 0))
    for i in range(CELLS * CELLS):
        ox, oy = (i % CELLS) * cell, (CELLS - 1 - i // CELLS) * cell
        for r, col in ((14, (60, 55, 50, 120)), (8, (20, 18, 16, 230)), (4, (4, 4, 4, 255))):
            c = cell / 2
            from PIL import ImageDraw
            ImageDraw.Draw(img).ellipse([ox + c - r, oy + c - r, ox + c + r, oy + c + r], fill=col)
    tex = PandaTexture('hole_color_placeholder')
    tex.setup_2d_texture(img.width, img.height, PandaTexture.T_unsigned_byte, PandaTexture.F_rgba)
    tex.set_ram_image_as(img.tobytes(), 'RGBA')
    tex.set_wrap_u(SamplerState.WM_clamp)
    tex.set_wrap_v(SamplerState.WM_clamp)
    return tex


class _Batch:
    """One mesh holding `capacity` holes, placed under `parent`."""

    def __init__(self, capacity: int, parent):
        self.capacity = capacity
        self.vdata = GeomVertexData('decals', _vertex_format(), Geom.UH_dynamic)
        self.vdata.set_num_rows(capacity * 4)
        prim = GeomTriangles(Geom.UH_static)
        for i in range(capacity):
            a = i * 4
            prim.add_vertices(a, a + 1, a + 2)
            prim.add_vertices(a, a + 2, a + 3)
        prim.close_primitive()
        geom = Geom(self.vdata)
        geom.add_primitive(prim)
        node = GeomNode('decals')
        node.add_geom(geom)
        self.entity = Entity(parent=parent, add_to_scene_entities=False)
        self.np = self.entity.attach_new_node(node)
        self.entity.set_transparency(TransparencyAttrib.M_alpha)
        self.entity.set_depth_write(False)
        self.entity.set_depth_offset(2)
        self.entity.set_two_sided(True)
        self.entity.set_bin('transparent', 0)
        node.set_bounds(OmniBoundingVolume())       # vertices change at runtime: do not let a stale bounding box hide new holes; the mesh is small, so no culling is needed
        node.set_final(True)
        self.geom = geom
        self.collapse(range(capacity))

    def _writers(self, vdata):
        return tuple(GeomVertexWriter(vdata, name) for name in ('vertex', 'color', 'texcoord', 'lightmap', 'hole'))

    def collapse(self, slots):
        """Make the quads of `slots` empty (all four corners at one point)."""
        vdata = self.geom.modify_vertex_data()
        vw, cw, tw, lw, hw = self._writers(vdata)
        for slot in slots:
            for w in (vw, cw, tw, lw, hw):
                w.set_row(slot * 4)
            for _ in range(4):
                vw.add_data3(0.0, 0.0, 0.0)
                cw.add_data4(0.0, 0.0, 0.0, 0.0)
                tw.add_data2(0.0, 0.0)
                lw.add_data2(-1.0, -1.0)
                hw.add_data4(0.0, 0.0, 0.0, 0.0)

    def write(self, slot: int, center: tuple, normal: tuple, size: float, tint: tuple, angle: float, cell: int, light_uv: tuple, birth: float):
        """Write one hole into `slot`. `center` is in the `parent` frame; `angle` turns the hole in the surface plane; `cell` picks the atlas cell; `light_uv` = the wall's lightmap point or None."""
        (ux, uy, uz), (vx, vy, vz) = _basis(normal)
        ca, sa = math.cos(angle), math.sin(angle)
        ax, ay = (ca * ux + sa * vx, ca * uy + sa * vy, ca * uz + sa * vz), (-sa * ux + ca * vx, -sa * uy + ca * vy, -sa * uz + ca * vz)
        h = size / 2.0
        vdata = self.geom.modify_vertex_data()
        vw, cw, tw, lw, hw = self._writers(vdata)
        for w in (vw, cw, tw, lw, hw):
            w.set_row(slot * 4)
        ou, ov = (cell % CELLS) / CELLS, (cell // CELLS) / CELLS
        lu, lv = light_uv if light_uv is not None else (-1.0, -1.0)
        for su, sv, tu, tv in ((-1, -1, 0, 0), (1, -1, 1, 0), (1, 1, 1, 1), (-1, 1, 0, 1)):
            vw.add_data3(center[0] + (su * ax[0] + sv * ay[0]) * h, center[1] + (su * ax[1] + sv * ay[1]) * h, center[2] + (su * ax[2] + sv * ay[2]) * h)
            cw.add_data4(*tint)
            tw.add_data2(ou + tu / CELLS, ov + tv / CELLS)
            lw.add_data2(lu, lv)
            hw.add_data4(birth, float(cell), size, 0.0)


class HoleDecals:
    def __init__(self, params: FeedbackParams, rng: random.Random = None):
        self.params = params
        self.rng = rng or random.Random()
        self.ring = HoleRing(params.max_holes, params.hole_life)
        self.static = _Batch(params.max_holes, scene)
        self.entity = self.static.entity
        self.locate = None                  # callable(point, normal) -> (u, v) of the wall's baked light in the room lightmap, or None; Game sets it on the pool map
        self.last_position = None           # last hole placed, world coordinates (for checks)
        self.last_size = 0.0
        self.level = 2
        color = read_texture('hole_color', 'bullet_hole_color.png')
        relief = read_texture('hole_relief', 'bullet_hole_relief.png')
        self.textures_ok = color is not None and relief is not None
        if not self.textures_ok:
            print('[lỗ đạn] thiếu assets/textures/bullet_hole_*.png (chạy tools/build/make_surface_textures.py): dùng lỗ tròn tạm')
        e = self.entity
        e.set_shader_input('hole_color', color if self.textures_ok else _placeholder_color())
        e.set_shader_input('hole_relief', relief if self.textures_ok else flat_relief())
        e.set_shader_input('room_lightmap', white())
        e.set_shader_input('room_params', Vec4(1.0, 0.0, 0.0, 0.0))
        self.time = PTA_LVecBase4f.empty_array(1)
        self.quality = PTA_LVecBase4f.empty_array(1)
        e.set_shader_input('hole_time', self.time)
        e.set_shader_input('hole_quality', self.quality)
        self.shader = load_glsl('decal')
        if getattr(application, 'base', None) is not None:           # the pure tests build a Combat with no window
            prepare(self.shader)
        e.set_shader(self.shader, 2)
        self.set_level(2)
        self._push_time()
        e.hide()                            # nothing to draw until the first hole

    # --- state read by the game and the checks ---
    @property
    def entities(self) -> list:
        return [self.entity]

    @property
    def count(self) -> int:
        """Holes alive now."""
        return self.ring.live

    @property
    def added(self) -> int:
        """Holes made since the start (never goes down, even as holes die)."""
        return self.ring.added

    def bind_room(self, lightmap, e_max: float, locate):
        """The pool hall: holes take the baked light of the wall they sit on (`lightmap` texture, `e_max`, `locate(point, normal)`)."""
        self.entity.set_shader_input('room_lightmap', lightmap)
        self.entity.set_shader_input('room_params', Vec4(e_max, 0.0, 0.0, 0.0))
        self.locate = locate

    def set_level(self, level: int):
        """Graphics 'Chi tiết bề mặt' (F2): 0 colour only, 1 normal map, 2 parallax. Uniforms only: no recompile."""
        self.level = min(max(int(level), 0), 2)
        self.quality.set_element(0, Vec4(float(self.level), DEPTH, 1.0, float(PARALLAX_STEPS)))

    def _push_time(self):
        p = self.params
        self.time.set_element(0, Vec4(self.ring.clock_wrapped(), p.hole_life, p.hole_fade, 0.0))

    # --- life ---
    def add(self, point, normal, distance: float, tint=None):
        fb = self.params
        offset = 0.02 + 0.0002 * distance      # nudge off the surface: far away the depth resolution is coarse (~1 cm at 150 m)
        world = tuple(p + n * offset for p, n in zip(point, normal))
        size = hole_size(distance, fb.hole_base_size, fb.hole_size_per_meter)
        rgba = (tint.r, tint.g, tint.b, tint.a) if tint is not None else WHITE
        light_uv = None
        if self.locate is not None:
            try:
                light_uv = self.locate(point, normal)
            except Exception:                   # a map lookup must never stop a shot
                light_uv = None
        self.ring.life = fb.hole_life
        slot = self.ring.add()
        self.static.write(slot, world, normal, size, rgba, self.rng.uniform(0.0, 2.0 * math.pi), self.rng.randrange(CELLS * CELLS), light_uv, self.ring.birth_wrapped(slot))
        self._push_time()
        self.entity.show()
        self.last_position = world
        self.last_size = size

    def update(self, dt: float):
        """Once per frame (Combat.update): age the holes, collapse the dead ones, hide the mesh when none is left."""
        if self.ring.live == 0:
            self.ring.advance(dt)               # the clock keeps running (the next hole's birth is on it)
            return
        self.ring.life = self.params.hole_life
        dead = self.ring.advance(dt)
        self._push_time()
        if dead:
            self.static.collapse(dead)
            if self.ring.live == 0:
                self.entity.hide()

    def clear(self):
        dead = self.ring.clear()
        if dead:
            self.static.collapse(dead)
        self.entity.hide()

    def warm(self, engine, camera_pos, forward):
        """Draw the decal shader once at start-up (the Intel driver compiles at the first draw: without it the first shot stalls 50-150 ms): an invisible hole in front of the camera."""
        class _Clear:
            r = g = b = 1.0
            a = 0.0
        slot_before = self.ring.added
        n = tuple(-c for c in forward)
        point = tuple(camera_pos[i] + forward[i] * 1.0 for i in range(3))
        self.add(point, n, 1.0, tint=_Clear)
        for _ in range(2):
            engine.render_frame()
        self.clear()
        self.ring.added = slot_before
