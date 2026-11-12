"""G18: drawing the swarm (capsules) and the door leaves of the Backrooms level. The behaviour is in core/enemies.py; this only mirrors it on screen every frame.

Every enemy / door is one small node with the enemy shader; its per-frame numbers (hit flash, wind-up glow, the baked ambient light where it stands) live in PTA arrays
edited in place, so nothing calls `set_shader_input` per frame (that changes the draw state of the scene graph, see frame_light.py).
"""
from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, PTA_LVecBase4f, Vec4
from ursina import application

from fps.core.backrooms import door_box
from fps.core.enemies import capsule_mesh
from fps.game.shaders import load_glsl, prepare

DOOR_COLOR = (0.70, 0.71, 0.68)        # a tiled leaf a little darker than the walls


def _geom(name: str, verts, norms, tris) -> GeomNode:
    vdata = GeomVertexData(name, GeomVertexFormat.get_v3n3(), Geom.UH_static)
    vdata.set_num_rows(len(verts))
    wv, wn = GeomVertexWriter(vdata, 'vertex'), GeomVertexWriter(vdata, 'normal')
    for p, n in zip(verts, norms):
        wv.add_data3(*p)
        wn.add_data3(*n)
    prim = GeomTriangles(Geom.UH_static)
    for a, b, c in tris:
        prim.add_vertices(a, b, c)
    geom = Geom(vdata)
    geom.add_primitive(prim)
    node = GeomNode(name)
    node.add_geom(geom)
    return node


def box_geom(name: str, size: tuple) -> GeomNode:
    """A box from (0, 0, 0) to `size`, flat normals."""
    sx, sy, sz = size
    faces = (((1, 0, 0), [(sx, 0, 0), (sx, sy, 0), (sx, sy, sz), (sx, 0, sz)]), ((-1, 0, 0), [(0, 0, 0), (0, 0, sz), (0, sy, sz), (0, sy, 0)]),
             ((0, 1, 0), [(0, sy, 0), (0, sy, sz), (sx, sy, sz), (sx, sy, 0)]), ((0, -1, 0), [(0, 0, 0), (sx, 0, 0), (sx, 0, sz), (0, 0, sz)]),
             ((0, 0, 1), [(0, 0, sz), (sx, 0, sz), (sx, sy, sz), (0, sy, sz)]), ((0, 0, -1), [(0, 0, 0), (0, sy, 0), (sx, sy, 0), (sx, 0, 0)]))
    verts, norms, tris = [], [], []
    for n, quad in faces:
        b = len(verts)
        verts += quad
        norms += [n] * 4
        tris += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    return _geom(name, verts, norms, tris)


class _Body:
    """One drawn object: a plain Panda node (transform) holding a GeomNode with the enemy shader and its PTA inputs.
    G19: not an Ursina Entity: its position / rotation setters convert through Vec3 and read the rotation back (~37 000 getter calls in a 15 s fight)."""

    def __init__(self, geom: GeomNode, color: tuple, eyes: bool, shape: tuple, shader):
        self.root = application.base.render.attach_new_node('enemy_body')
        self.node = self.root.attach_new_node(geom)
        n = self.node
        n.set_two_sided(True)
        n.set_shader(shader, 2)
        n.set_shader_input('enemy_color', Vec4(*color, 1.0 if eyes else 0.0))
        n.set_shader_input('enemy_shape', Vec4(*shape))
        self.state = PTA_LVecBase4f.empty_array(1)
        self.amb_up = PTA_LVecBase4f.empty_array(1)
        self.amb_down = PTA_LVecBase4f.empty_array(1)
        self.state.set_element(0, Vec4(0, 0, 1, 0))
        n.set_shader_input('enemy_state', self.state)
        n.set_shader_input('enemy_amb_up', self.amb_up)
        n.set_shader_input('enemy_amb_down', self.amb_down)

    def place(self, x: float, y: float, z: float, yaw: float = 0.0, pitch: float = 0.0):
        """Ursina's convention (y up, rotation_y = yaw, rotation_x = pitch forward) in one Panda call: Entity.rotation sets Hpr(-ry, -rx, rz)."""
        self.root.set_pos_hpr(x, y, z, -yaw, -pitch, 0.0)

    def light(self, up: tuple, down: tuple):
        self.amb_up.set_element(0, Vec4(*up, 0))
        self.amb_down.set_element(0, Vec4(*down, 0))

    def destroy(self):
        self.root.remove_node()


class SwarmView:
    def __init__(self, data):
        self.shader = load_glsl('enemy')
        prepare(self.shader)
        self.geoms = {}
        for name in ('normal', 'runner', 'brute'):
            k = getattr(data, name)
            self.geoms[name] = (_geom(f'capsule_{name}', *capsule_mesh(k.radius, k.height)), k)
        self.bodies = {}                       # enemy id -> _Body

    def update(self, swarm, ambient):
        """Mirror the swarm: new enemies get a body, removed ones lose it. `ambient(x, z)` -> (up, down) baked light."""
        seen = set()
        for e in swarm.enemies:
            seen.add(e.id)
            b = self.bodies.get(e.id)
            if b is None:
                geom, k = self.geoms[e.kind_name]
                b = self.bodies[e.id] = _Body(geom.make_copy(), e.kind.color, True, (k.radius, k.height, k.height * 0.86, 0.0), self.shader)
            sink = max(0.0, e.dead_t - 0.6) * 0.5 if not e.alive else 0.0
            b.place(e.x, e.y - sink, e.z, e.yaw, 12.0 * e.lean + 88.0 * e.fall * e.fall)
            visible = 1.0 if e.alive else max(0.0, 1.0 - max(0.0, e.dead_t - 0.9) / max(swarm.d.corpse_time - 0.9, 0.1))
            glow = e.lean if e.alive else 0.0
            b.state.set_element(0, Vec4(e.flash, glow, visible, 0))
            up, down = ambient(e.x, e.z)
            b.light(up, down)
        for gone in [i for i in self.bodies if i not in seen]:
            self.bodies.pop(gone).destroy()

    def clear(self):
        for b in self.bodies.values():
            b.destroy()
        self.bodies = {}


class DoorView:
    """The four door leaves of a floor; `update(amounts)` slides them (core/backrooms.door_box)."""

    def __init__(self, doors: list, ambient):
        shader = load_glsl('enemy')
        self.doors = doors
        self.bodies = []
        for dr in doors:
            size = tuple(dr.hi[i] - dr.lo[i] for i in range(3))
            b = _Body(box_geom(f'door_{dr.name}', size), DOOR_COLOR, False, (0, 0, 0, 0), shader)
            b.place(*dr.lo)
            mid = ((dr.lo[0] + dr.hi[0]) / 2, (dr.lo[2] + dr.hi[2]) / 2)
            _, down = ambient(*mid)
            b.light(down, down)                 # a vertical leaf: the up-facing value holds the panels' direct light from above (a door under a panel glowed white)
            self.bodies.append(b)

    def update(self, amounts: dict):
        """amounts: door name -> opening 0..1."""
        for dr, b in zip(self.doors, self.bodies):
            lo, _ = door_box(dr, amounts.get(dr.name, 0.0))
            b.place(*lo)

    def destroy(self):
        for b in self.bodies:
            b.destroy()
        self.bodies = []
