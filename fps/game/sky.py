"""Sky with drifting clouds, coloured by assets/shaders/sky.frag from the view direction.

Open map: one sphere around the camera (sky.vert applies only the camera rotation, so it never needs to follow the player), drawn right AFTER the opaque bin and
depth-tested LESS_EQUAL against the far plane where sky.vert puts it (z = w): it shades only the pixels nothing else covered.
Pool hall (G13): the sky can only be seen through the window holes, so instead of the sphere it is a few quads just outside those holes (sky_window.vert
gives the same view direction per pixel: same picture). The full-screen sphere cost ~0.22 ms per frame at 1440 x 810 on the Iris Xe even when only the
holes passed the depth test (it used to be drawn first without any depth test, under Ursina's M_dual transparency: its cloud shader ran on every pixel).
The only per-frame input is the clock that moves the clouds.
"""
from panda3d.core import (CullBinManager, DepthTestAttrib, Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, OmniBoundingVolume,
                          RenderAttrib, TransparencyAttrib)
from ursina import Entity

from fps.game.shaders import load_glsl

CLOUD_CLOCK_SPEED = 1.0          # multiplies the drift of the clouds (1 = a slow drift: a full noise tile takes ~3 minutes)
SKY_BIN = 'sky_after_opaque'
SKY_BIN_SORT = 25                # Panda's default bins: opaque 20, transparent 30 (smoke, splashes, decals still blend over the sky)
HOLE_OUT = 0.05                  # m: the sky quads stand this far outside the outer wall face...
HOLE_GROW = 0.05                 # ...and reach this far past each hole edge (hidden by the wall; no gap at a grazing view)


def sky_bin() -> str:
    mgr = CullBinManager.get_global_ptr()
    if mgr.find_bin(SKY_BIN) < 0:
        mgr.add_bin(SKY_BIN, CullBinManager.BT_unsorted, SKY_BIN_SORT)
    return SKY_BIN


def hole_quads(rects, wall_out: float) -> GeomNode:
    """One quad per window hole (z0, z1, y0, y1) in the plane x = wall_out + HOLE_OUT, facing west into the room (world coordinates)."""
    vdata = GeomVertexData('sky_holes', GeomVertexFormat.get_v3(), Geom.UH_static)
    vdata.set_num_rows(4 * len(rects))
    w = GeomVertexWriter(vdata, 'vertex')
    prim = GeomTriangles(Geom.UH_static)
    x = wall_out + HOLE_OUT
    for i, (z0, z1, y0, y1) in enumerate(rects):
        z0, z1, y0, y1 = z0 - HOLE_GROW, z1 + HOLE_GROW, y0 - HOLE_GROW, y1 + HOLE_GROW
        for z, y in ((z0, y0), (z1, y0), (z1, y1), (z0, y1)):
            w.add_data3(x, y, z)
        prim.add_vertices(4 * i, 4 * i + 1, 4 * i + 2)
        prim.add_vertices(4 * i, 4 * i + 2, 4 * i + 3)
    geom = Geom(vdata)
    geom.add_primitive(prim)
    node = GeomNode('sky_holes')
    node.add_geom(geom)
    return node


class Sky:
    def __init__(self, holes: tuple = None):
        """`holes` = (window rects, x of the outer wall face) of an indoor map: the sky is drawn only behind those holes."""
        if holes is None:
            self.entity = Entity(model='sphere', scale=10.0, add_to_scene_entities=False)
            e = self.entity
            e.setShader(load_glsl('sky'), 1)
            e.set_attrib(DepthTestAttrib.make(RenderAttrib.M_less_equal))     # passes only where the depth buffer still holds the clear value (far plane)
            e.model.set_transparency(TransparencyAttrib.M_none)  # Ursina puts M_dual on every model node: two passes with an alpha test (no early depth rejection)
            for geom in e.find_all_matches('**/+GeomNode'):         # the vertex shader moves it: never cull it
                geom.node().set_bounds(OmniBoundingVolume())
                geom.node().set_final(True)
        else:
            rects, wall_out = holes
            self.entity = Entity(add_to_scene_entities=False)
            e = self.entity
            e.attach_new_node(hole_quads(rects, wall_out))
            e.setShader(load_glsl('sky_window', frag='sky'), 1)
        e.set_two_sided(True)
        e.set_depth_write(False)
        e.set_light_off()
        e.set_bin(sky_bin(), 0)
        self.clock = 0.0
        e.set_shader_input('sky_time', 0.0)

    def update(self, dt: float):
        self.clock += dt * CLOUD_CLOCK_SPEED
        self.entity.set_shader_input('sky_time', float(self.clock))
