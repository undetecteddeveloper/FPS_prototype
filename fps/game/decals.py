"""Lỗ đạn gộp thành mesh: một lần vẽ cho cả bể, thay vì một Entity (một lần vẽ) cho mỗi lỗ. Bể 200 Entity làm FPS tụt dần theo số phát đã bắn.

Mỗi chủ nhân một mesh: lỗ trên tường / sàn / bia đứng yên chung một mesh; mỗi bia chạy một mesh riêng gắn vào `target.root` nên lỗ đi theo bia. Mỗi lỗ là 4 đỉnh;
hết chỗ thì tái dùng lỗ cũ nhất (vòng tròn). Lỗ chưa dùng là 4 đỉnh trùng nhau nên không vẽ gì. Mesh chỉ đẩy lại lên GPU khi có lỗ mới.
"""
import math

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, OmniBoundingVolume,
                          TransparencyAttrib)
from ursina import Entity, scene

from fps.core.ballistics import hole_size
from fps.weapon_data import FeedbackParams

WHITE = (1.0, 1.0, 1.0, 1.0)


def _basis(normal: tuple) -> tuple:
    """Hai trục nằm trên mặt trúng, vuông góc với pháp tuyến."""
    nx, ny, nz = normal
    ax = (0.0, 1.0, 0.0) if abs(ny) < 0.9 else (1.0, 0.0, 0.0)
    ux, uy, uz = ax[1] * nz - ax[2] * ny, ax[2] * nx - ax[0] * nz, ax[0] * ny - ax[1] * nx
    n = math.sqrt(ux * ux + uy * uy + uz * uz) or 1.0
    ux, uy, uz = ux / n, uy / n, uz / n
    return (ux, uy, uz), (ny * uz - nz * uy, nz * ux - nx * uz, nx * uy - ny * ux)


class _Batch:
    """Một mesh `capacity` lỗ, đặt dưới `parent`."""

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
        self.entity.set_transparency(TransparencyAttrib.M_alpha)
        self.entity.set_depth_write(False)
        self.entity.set_depth_offset(2)
        self.entity.set_two_sided(True)
        self.entity.set_bin('transparent', 0)
        node.set_bounds(OmniBoundingVolume())       # đỉnh đổi lúc chạy: không để hộp bao cũ làm mất lỗ mới; mesh nhỏ nên khỏi cần cắt
        node.set_final(True)
        self.geom = geom

    def write(self, center: tuple, normal: tuple, size: float, tint: tuple):
        """Ghi một lỗ vào ô kế tiếp. `center` trong hệ của `parent`."""
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


class HoleDecals:
    def __init__(self, params: FeedbackParams, texture, mover_capacity: int = 48):
        self.params = params
        self.texture = texture
        self.mover_capacity = mover_capacity
        self.static = _Batch(params.max_holes, scene, texture)
        self.by_owner = {}                 # target.root -> _Batch
        self.used = 0
        self.last_position = None          # lỗ vừa đặt, toạ độ thế giới (cho kiểm tra)
        self.last_local = None             # lỗ vừa đặt, so với vật nó gắn vào
        self.last_parent = None
        self.last_size = 0.0

    @property
    def entities(self) -> list:
        """Các Entity mang mesh, để gán shader thế giới."""
        return [self.static.entity, *(b.entity for b in self.by_owner.values())]

    def prepare_owner(self, parent):
        """Tạo sẵn mesh cho một bia chạy lúc dựng game: tạo giữa lúc bắn sẽ khựng."""
        batch = _Batch(self.mover_capacity, parent, self.texture)
        self.by_owner[parent] = batch
        return batch

    def add(self, point, normal, distance: float, parent=None, tint=None):
        """`parent` = target.root nếu lỗ phải đi theo một vật chạy."""
        fb = self.params
        offset = 0.02 + 0.0002 * distance      # nhích ra khỏi mặt phẳng: ở xa độ phân giải độ sâu thô (~1 cm ở 150 m)
        world = tuple(p + n * offset for p, n in zip(point, normal))
        size = hole_size(distance, fb.hole_base_size, fb.hole_size_per_meter)
        rgba = (tint.r, tint.g, tint.b, tint.a) if tint is not None else WHITE
        batch = self.by_owner.get(parent) if parent is not None else None
        if batch is not None:
            root = parent.world_position
            local = (world[0] - root[0], world[1] - root[1], world[2] - root[2])
            batch.write(local, normal, size, rgba)
        else:
            batch = self.static
            batch.write(world, normal, size, rgba)
        self.used = min(self.used + 1, self.params.max_holes)
        self.last_position = world
        self.last_local = tuple(a - b for a, b in zip(world, parent.world_position)) if parent is not None else world
        self.last_size = size
        self.last_parent = parent
        return batch

    @property
    def count(self) -> int:
        return self.used
