"""The pool hall in the game: the room mesh built from core/poolmap.py, lit by the baked lightmap, plus the water, the handrails and everything the rest of the game needs to know about the map
(bullet boxes, terrain for the player, spawn point).

First run (or a changed sun / map number): the light is baked on the CPU (core/lightbake.py, numpy, ~tens of seconds) and the room is captured once for the water's reflection
(game/pool_capture.py); both land in assets/maps/pool/ with a hash in meta.json, so later runs only load two PNGs.
"""
import json
import time
from pathlib import Path

from panda3d.core import (Filename, Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, GeomVertexWriter, InternalName, PTA_LVecBase4f,
                          Texture, Vec4)
from PIL import Image
from ursina import Entity

from fps.core.exposure import target_exposure
from fps.core.poolmap import (AmbientGrid, PoolMap, bake_key, build_map, colliders, lightmap_uv, pack_atlas, probe_uv, rail_meshes, pool_terrain, reflect_key,
                              window_rects)
from fps.core.terrain import Terrain
from fps.game.shaders import load_glsl
from fps.game.water import WaterSurface
from fps.weapon_data import GameParams, GraphicsLevel, MapData

ASSET_DIR = 'assets/maps/pool'


def _vertex_format():
    arr = GeomVertexArrayFormat()
    arr.add_column(InternalName.get_vertex(), 3, Geom.NT_float32, Geom.C_point)
    arr.add_column(InternalName.get_color(), 4, Geom.NT_float32, Geom.C_color)
    arr.add_column(InternalName.get_texcoord(), 2, Geom.NT_float32, Geom.C_texcoord)
    arr.add_column(InternalName.make('lightmap'), 2, Geom.NT_float32, Geom.C_other)     # a custom column read by name (`in vec2 lightmap` in room.vert): Panda feeds p3d_MultiTexCoord1 from texcoord 0 when no second stage exists
    fmt = GeomVertexFormat()
    fmt.add_array(arr)
    return GeomVertexFormat.register_format(fmt)


class PoolHall:
    def __init__(self, params: GameParams, root: Path, data: MapData = None, force_bake: bool = False, log=print):
        self.params, self.root, self.log = params, root, log
        self.data = data or MapData()
        d = self.data
        self.pm: PoolMap = build_map(d)
        self.faces = self.pm.exposed_faces()
        pz, hz = d.pool_z / 2.0, d.room_z / 2.0
        mid_rails = sum(d.north_steps_x) / 2.0
        self.probes = [((mid_rails, 0.6, pz + 0.3), (0.0, 1.0, 0.0))]            # one patch of baked light for the handrails (they have no UV of their own)
        self.atlas = pack_atlas(self.faces, d.texel, n_probes=len(self.probes))
        self.key = bake_key(d, params.look)
        self.dir = root / ASSET_DIR
        self.spawn = (0.0, 0.0, -(pz + (hz - pz) / 2.0))                            # the middle of the south bank, looking north along the pool
        self.lightmap, self.e_max = self._load_or_bake(force_bake)
        self.ambient = AmbientGrid(json.loads((self.dir / 'ambient.json').read_text(encoding='utf-8')))
        self.entity = Entity(add_to_scene_entities=False)
        self.node = self.entity.attach_new_node(self._build_mesh())
        self.node.set_two_sided(True)
        self.node.set_shader(load_glsl('room'), 1)
        self.node.set_shader_input('room_lightmap', self.lightmap)
        self.node.set_shader_input('room_params', Vec4(self.e_max, 0, 0, 0))
        self.water = WaterSurface(self.pm, params.water, self.ambient)
        self._bind_sun_windows()
        self.world = {'floor': None, 'colliders': colliders(self.pm) + [self.water.collider()], 'pool': self}
        self.reflection = None
        self._reflect_nodes = []
        # G10 wet deck + wet footprints (room.frag): flags per graphics level, footprints in a PTA ring (Game adds them)
        self.room_quality = PTA_LVecBase4f.empty_array(1)                 # all 0 until set_level: the reflection capture must not see a wet floor mirroring a placeholder
        self.prints = PTA_LVecBase4f.empty_array(24)
        for i in range(24):
            self.prints.set_element(i, Vec4(0, 0, -1e6, 0))
        x0, x1, z0, z1, _ = self.pm.water
        n = self.node
        n.set_shader_input('room_quality', self.room_quality)
        n.set_shader_input('room_prints', self.prints)
        n.set_shader_input('room_pool', Vec4(x0, x1, z0, z1))
        self._push_wet()
        self.bind_reflection(self.node)

    # ------------------------------------------------------------------ light and reflection files
    def _meta(self) -> dict:
        try:
            return json.loads((self.dir / 'meta.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def _write_meta(self, **changes):
        meta = {**self._meta(), **changes}
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / 'meta.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')

    @staticmethod
    def _read_texture(path: Path, name: str) -> Texture:
        tex = Texture(name)
        if not tex.read(Filename.from_os_specific(str(path))):
            raise RuntimeError(f'không đọc được {path}')
        tex.set_wrap_u(Texture.WM_clamp)
        tex.set_wrap_v(Texture.WM_clamp)
        tex.set_minfilter(Texture.FT_linear)              # no mipmaps: faces of the atlas sit next to each other
        tex.set_magfilter(Texture.FT_linear)
        return tex

    def _load_or_bake(self, force: bool) -> tuple:
        png, meta = self.dir / 'lightmap.png', self._meta()
        if force or meta.get('key') != self.key or not png.exists():
            self.bake_light()
            meta = self._meta()
        return self._read_texture(png, 'room_lightmap'), float(meta['e_max'])

    def bake_light(self):
        """CPU bake (needs numpy) -> assets/maps/pool/lightmap.png. Invalidates the stored reflection (the room just changed)."""
        from fps.core.lightbake import bake
        t0 = time.time()
        self.log(f'[map] đang tính ánh sáng cho phòng hồ bơi (lần đầu hoặc sau khi đổi nắng / map), vài chục giây...')
        last = [0.0]

        def progress(done, total):
            if time.time() - last[0] > 5.0:
                last[0] = time.time()
                self.log(f'[map]   {done}/{total}')

        res = bake(self.pm, self.params.look, probes=self.probes, progress=progress)
        self.dir.mkdir(parents=True, exist_ok=True)
        Image.fromarray(res.rgb, 'RGB').save(self.dir / 'lightmap.png')
        (self.dir / 'ambient.json').write_text(json.dumps(res.ambient, separators=(',', ':')), encoding='utf-8')
        self._write_meta(key=self.key, e_max=res.e_max, reflect=None, stats=res.stats)
        self.log(f'[map] xong sau {time.time() - t0:.1f} s ({res.stats["rays"]:,} tia, ảnh {res.rgb.shape[1]}x{res.rgb.shape[0]})')

    def prepare_reflection(self, light, force: bool = False):
        """Load (or capture) the room image the water mirrors. Needs the world shader inputs on `render` (WorldLook sets them), so Game calls this right after building the look."""
        png = self.dir / 'reflect.png'
        key = reflect_key(self.data, self.params.look, self.params.lens)
        if force or self._meta().get('reflect') != key or not png.exists():
            from fps.game.pool_capture import capture_reflection
            self.water.node.hide()
            light.set_exposure(target_exposure(self.params.lens, self.params.look))
            capture_reflection(self, light, png)
            self.water.node.show()
            self._write_meta(reflect=key)
        self.reflection = self._read_texture(png, 'water_reflect')
        self.water.set_reflection(self.reflection)
        for n in self._reflect_nodes:
            n.set_shader_input('water_reflect', self.reflection)

    def bind_reflection(self, node):
        """Give a node the inputs of cube_reflect.glsl (the room's wet floor, the gun): the same atlas and box as the water. Nodes bound before the capture get it when it loads."""
        w = self.water.node
        for name in ('water_axes', 'water_box_lo', 'water_box_hi', 'water_probe', 'cube_params'):
            node.set_shader_input(w.get_shader_input(name))
        node.set_shader_input('water_reflect', self.reflection if self.reflection is not None else self.water.placeholder)
        if node not in self._reflect_nodes:
            self._reflect_nodes.append(node)

    # ------------------------------------------------------------------ mesh
    def _build_mesh(self) -> GeomNode:
        d, atlas = self.data, self.atlas
        verts = []                                                                  # (position, albedo + tile, metric uv, lightmap uv)
        tris = []
        for f, place in zip(self.faces, atlas.faces):
            box = self.pm.boxes[f.box]
            rgba = (*box.albedo, box.tile)
            base = len(verts)
            for u, v in ((f.u0, f.v0), (f.u1, f.v0), (f.u1, f.v1), (f.u0, f.v1)):
                verts.append((f.point(u, v), rgba, (u, v), lightmap_uv(f, place, atlas, u, v)))
            tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
        rail_rgba = (*d.rail_albedo, 0.0)
        luv = probe_uv(atlas.probes[0], atlas)
        for rv, rt in rail_meshes(self.pm):
            base = len(verts)
            verts += [(p, rail_rgba, (0.0, 0.0), luv) for p in rv]
            tris += [(base + a, base + b, base + c) for a, b, c in rt]
        vdata = GeomVertexData('pool', _vertex_format(), Geom.UH_static)
        vdata.set_num_rows(len(verts))
        wv, wc = GeomVertexWriter(vdata, 'vertex'), GeomVertexWriter(vdata, 'color')
        w0, w1 = GeomVertexWriter(vdata, 'texcoord'), GeomVertexWriter(vdata, 'lightmap')
        for p, c, uv0, uv1 in verts:
            wv.add_data3(*p)
            wc.add_data4(*c)
            w0.add_data2(*uv0)
            w1.add_data2(*uv1)
        prim = GeomTriangles(Geom.UH_static)
        for a, b, c in tris:
            prim.add_vertices(a, b, c)
        geom = Geom(vdata)
        geom.add_primitive(prim)
        node = GeomNode('pool_room')
        node.add_geom(geom)
        self.triangles = len(tris) + 2                                              # + the water quad
        self.draw_calls = 2                                                         # the room (with the handrails) and the water
        return node

    # ------------------------------------------------------------------ for the rest of the game
    def terrain(self, radius: float) -> Terrain:
        return pool_terrain(self.pm, radius)

    def sun_blocked(self, point, sun_dir) -> bool:
        """Whether the sun is hidden from `point` by the room (used for the light on the gun). Pure Python, ~40 boxes."""
        from fps.core.ballistics import first_hit
        far = tuple(point[i] + sun_dir[i] * 200.0 for i in range(3))
        return first_hit(point, far, self.world['colliders'][:-1], ground_y=None) is not None       # [:-1]: the water box is not an occluder

    def local_ambient(self, x: float, z: float) -> tuple:
        """((r, g, b) up, (r, g, b) down): the ambient light for the gun at floor position (x, z) (baked: `ambient.json`)."""
        return self.ambient.sample(x, z)

    # ------------------------------------------------------------------ G10: sun through the windows, shafts, graphics level
    def _bind_sun_windows(self):
        """Inputs of sun_window.glsl on the room and the water: the window holes, and the shaft numbers (a PTA: its clock changes every frame)."""
        rects, wall = window_rects(self.data)
        wins = PTA_LVecBase4f.empty_array(4)
        for i in range(4):
            wins.set_element(i, Vec4(*rects[i]) if i < len(rects) else Vec4(0, 0, 0, 0))
        self.shaft = PTA_LVecBase4f.empty_array(1)
        self.shaft2 = PTA_LVecBase4f.empty_array(1)
        self._shaft_steps = 0
        self._clock = 0.0
        self._sun_inputs = (wins, Vec4(wall[0], wall[1], min(len(rects), 4), 0.03))
        for n in (self.node, self.water.node):
            self._bind_sun(n)
        self.splash = None
        self._push_shaft()

    def _bind_sun(self, n):
        wins, wall = self._sun_inputs
        n.set_shader_input('look_windows', wins)
        n.set_shader_input('look_window_wall', wall)
        n.set_shader_input('look_shaft', self.shaft)
        n.set_shader_input('look_shaft2', self.shaft2)

    def attach_splash(self, splash):
        """Game builds the droplets once the shared light exists (game/splash.py)."""
        self.splash = splash
        splash.water = self.water
        self._bind_sun(splash.root)
        self.water.on_bullet = splash.bullet

    def _push_shaft(self):
        look = self.params.look
        self.shaft.set_element(0, Vec4(look.shaft_density, look.shaft_anisotropy, self._shaft_steps, look.shaft_dust))
        self.shaft2.set_element(0, Vec4(look.shaft_range, self._clock, 0, 0))

    def _push_wet(self):
        s = self.params.splash
        self.node.set_shader_input('room_wet', Vec4(s.puddles, s.puddle_scale, s.wet_reach, s.wet_reflect))
        self.node.set_shader_input('room_wet2', Vec4(s.wet_darken, s.print_life, 0, 0))

    def add_print(self, slot: int, packed: tuple):
        """A wet footprint (core/footprints.py pack) into ring slot `slot`; its t0 is on the shaft clock (look_shaft2.y), which the shader ages it by."""
        x, z, _, w = packed
        self.prints.set_element(slot, Vec4(x, z, self._clock, w))

    def set_level(self, g: GraphicsLevel):
        """Graphics level (F2): everything the map draws."""
        self.room_quality.set_element(0, Vec4(1.0 if g.wet else 0.0, 0, 0, 0))
        self._shaft_steps = g.shaft_steps
        self.water.set_level(g)
        if self.splash:
            self.splash.share = g.splash
        self._push_shaft()

    def update(self, dt: float):
        self._clock += dt
        self.shaft2.set_element(0, Vec4(self.params.look.shaft_range, self._clock, 0, 0))
        if self.splash:
            self.splash.update(min(dt, 0.05))           # before the water: falling drops push the sim this frame
        self.water.update(dt)

    def apply_params(self):
        self.water.apply_params()
        self._push_shaft()
        self._push_wet()
