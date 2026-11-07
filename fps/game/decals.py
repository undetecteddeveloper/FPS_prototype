"""Bullet holes merged into meshes: one draw call for the whole pool, instead of one Entity (one draw call) per hole. A pool of 200 Entities made FPS drop steadily as shots were fired.

All holes share one mesh. Each hole is 4 vertices;
when full, the oldest hole is reused (circular buffer). Unused holes are 4 coincident vertices, so nothing is drawn. The mesh is re-uploaded to the GPU only when a new hole is added.
"""
import math

from PIL import Image, ImageDraw
from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, OmniBoundingVolume,
                          TransparencyAttrib)
from ursina import Entity, Texture, scene

from fps.core.ballistics import hole_size
from fps.weapon_data import FeedbackParams

WHITE = (1.0, 1.0, 1.0, 1.0)


def _basis(normal: tuple) -> tuple:
    """Two axes lying on the hit surface, perpendicular to the normal."""
    nx, ny, nz = normal
    ax = (0.0, 1.0, 0.0) if abs(ny) < 0.9 else (1.0, 0.0, 0.0)
    ux, uy, uz = ax[1] * nz - ax[2] * ny, ax[2] * nx - ax[0] * nz, ax[0] * ny - ax[1] * nx
    n = math.sqrt(ux * ux + uy * uy + uz * uz) or 1.0
    ux, uy, uz = ux / n, uy / n, uz / n
    return (ux, uy, uz), (ny * uz - nz * uy, nz * ux - nx * uz, nx * uy - ny * ux)


class _Batch:
    """One mesh holding `capacity` holes, placed under `parent`."""

    def __init__(self, capacity: int, parent, texture):
        self.capacity = capacity
        self.next = 0
        fmt = GeomVertexFormat.get_v3c4t2()
        self.vdata = GeomVertexData('decals', fmt, Geom.UH_dynamic)
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
        self.entity.texture = texture
        self.np.set_texture(texture._texture)       # Ursina applies `Entity.texture` only to the entity's model; this mesh is a raw node, so without this the holes sampled a blank white texture
        self.entity.set_transparency(TransparencyAttrib.M_alpha)
        self.entity.set_depth_write(False)
        self.entity.set_depth_offset(2)
        self.entity.set_two_sided(True)
        self.entity.set_bin('transparent', 0)
        node.set_bounds(OmniBoundingVolume())       # vertices change at runtime: do not let a stale bounding box hide new holes; the mesh is small, so no culling is needed
        node.set_final(True)
        self.geom = geom

    def write(self, center: tuple, normal: tuple, size: float, tint: tuple):
        """Write one hole into the next slot. `center` is in the `parent` frame."""
        (ux, uy, uz), (vx, vy, vz) = _basis(normal)
        h = size / 2.0
        row = self.next * 4
        self.next = (self.next + 1) % self.capacity
        vdata = self.geom.modify_vertex_data()
        vw, cw, tw = (GeomVertexWriter(vdata, name) for name in ('vertex', 'color', 'texcoord'))
        for w in (vw, cw, tw):
            w.set_row(row)
        for su, sv, tu, tv in ((-1, -1, 0, 0), (1, -1, 1, 0), (1, 1, 1, 1), (-1, 1, 0, 1)):
            vw.add_data3(center[0] + (su * ux + sv * vx) * h, center[1] + (su * uy + sv * vy) * h, center[2] + (su * uz + sv * vz) * h)
            cw.add_data4(*tint)
            tw.add_data2(tu, tv)


def hole_texture() -> Texture:
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2
    d.ellipse([c - 30, c - 30, c + 30, c + 30], fill=(25, 20, 15, 90))     # faint smoke halo
    d.ellipse([c - 17, c - 17, c + 17, c + 17], fill=(15, 12, 10, 190))
    d.ellipse([c - 9, c - 9, c + 9, c + 9], fill=(5, 5, 5, 255))
    return Texture(img, filtering='mipmap')


class HoleDecals:
    def __init__(self, params: FeedbackParams, texture):
        self.params = params
        self.texture = texture
        self.static = _Batch(params.max_holes, scene, texture)
        self.used = 0
        self.last_position = None          # last hole placed, world coordinates (for checks)
        self.last_size = 0.0

    @property
    def entities(self) -> list:
        """The Entities that carry the meshes, so the world shader can be assigned to them."""
        return [self.static.entity]

    def add(self, point, normal, distance: float, tint=None):
        fb = self.params
        offset = 0.02 + 0.0002 * distance      # nudge off the surface: far away the depth resolution is coarse (~1 cm at 150 m)
        world = tuple(p + n * offset for p, n in zip(point, normal))
        size = hole_size(distance, fb.hole_base_size, fb.hole_size_per_meter)
        rgba = (tint.r, tint.g, tint.b, tint.a) if tint is not None else WHITE
        self.static.write(world, normal, size, rgba)
        self.used = min(self.used + 1, self.params.max_holes)
        self.last_position = world
        self.last_size = size

    @property
    def count(self) -> int:
        return self.used
