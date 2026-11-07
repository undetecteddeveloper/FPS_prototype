"""The pool hall in the game: the room mesh built from core/poolmap.py, lit by the baked lightmap, plus the water, the handrails and everything the rest of the game needs to know about the map
(bullet boxes, terrain for the player, spawn point).

First run (or a changed sun / map number): the light is baked on the CPU (core/lightbake.py, numpy, ~tens of seconds) and the room is captured once for the water's reflection
(game/pool_capture.py); both land in assets/maps/pool/ with a hash in meta.json, so later runs only load two PNGs.
"""
import json
import time
from pathlib import Path

from panda3d.core import (Filename, Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, GeomVertexWriter, InternalName, Texture, Vec4)
from PIL import Image
from ursina import Entity

from fps.core.exposure import target_exposure
from fps.core.poolmap import AmbientGrid, PoolMap, bake_key, build_map, colliders, lightmap_uv, pack_atlas, probe_uv, rail_meshes, reflect_key, solid_boxes, walk_tops
from fps.core.terrain import Terrain
from fps.game.shaders import load_glsl
from fps.game.water import WaterSurface
from fps.weapon_data import GameParams, MapData

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
        self.water = WaterSurface(self.pm, params.water)
        self.world = {'floor': None, 'colliders': colliders(self.pm) + [self.water.collider()], 'pool': self}
        self.reflection = None

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
        hx, hz = self.data.room_x / 2.0, self.data.room_z / 2.0
        return Terrain(walk_tops(self.pm), solid_boxes(self.pm), (-hx + radius, hx - radius, -hz + radius, hz - radius))

    def sun_blocked(self, point, sun_dir) -> bool:
        """Whether the sun is hidden from `point` by the room (used for the light on the gun). Pure Python, ~40 boxes."""
        from fps.core.ballistics import first_hit
        far = tuple(point[i] + sun_dir[i] * 200.0 for i in range(3))
        return first_hit(point, far, self.world['colliders'][:-1], ground_y=None) is not None       # [:-1]: the water box is not an occluder

    def local_ambient(self, x: float, z: float) -> tuple:
        """((r, g, b) up, (r, g, b) down): the ambient light for the gun at floor position (x, z) (baked: `ambient.json`)."""
        return self.ambient.sample(x, z)

    def update(self, dt: float):
        self.water.update(dt)

    def apply_params(self):
        self.water.apply_params()
