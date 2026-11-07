"""The caustic pass (G11, math: core/caustics.py; shaders: assets/shaders/caustics.*): every frame the light mesh is drawn additively into a float texture over the pool plan,
after the wave simulation passes; water.frag reads it where the refracted view ray hits the bottom or a wall.

The mesh costs almost nothing to build: ONE triangle strip (a row of `cols` columns) drawn `rows` times with instancing (gl_InstanceID = row), so switching quality
(F2) only rebuilds a small strip and the texture. Per-frame values are PTA arrays edited in place (no per-frame `set_shader_input`).
"""
from panda3d.core import (Camera, ColorBlendAttrib, FrameBufferProperties, Geom, GeomNode, GeomTristrips, GeomVertexData, GeomVertexFormat, GeomVertexWriter, GraphicsOutput,
                          GraphicsPipe, NodePath, OmniBoundingVolume, OrthographicLens, PTA_LVecBase4f, Texture, Vec3, Vec4, WindowProperties)
from ursina import application

from fps.core.caustics import texture_size
from fps.game.shaders import load_glsl
from fps.game.water_sim import SORT as SIM_SORT

SORT = SIM_SORT + 5                # after the two simulation passes, before the lens buffers and the window
PEAK = 60.0                        # the brightest value one fragment writes (a nearly degenerate triangle would write a spike)


class CausticPass:
    def __init__(self, rect: tuple, dom: tuple, cols: int, rows: int, tex_long: int, water_y: float, ramp: tuple, sun: tuple, shared: dict):
        """rect = pool (light mesh covers it), dom = texture domain (core/caustics.domain), cols x rows = light mesh, tex_long = texels on the long side of the texture.
        `shared` = shader inputs owned by the water (wave tables, simulation textures, clock PTA)."""
        self.rect, self.dom = rect, dom
        self.cols, self.rows = cols, rows
        self.size = texture_size(dom, tex_long)
        self.texture = Texture('caustics')
        self.texture.setup_2d_texture(self.size[0], self.size[1], Texture.T_half_float, Texture.F_r16)    # 16 bit is plenty for a brightness (unlike the sim: core/watersim.py)
        self.texture.set_clear_color((1, 0, 0, 0))
        self.texture.set_wrap_u(Texture.WM_clamp)
        self.texture.set_wrap_v(Texture.WM_clamp)
        self.texture.set_minfilter(Texture.FT_linear_mipmap_linear)       # far away the cells average out to 1 instead of shimmering
        self.texture.set_magfilter(Texture.FT_linear)
        self.texture.set_anisotropic_degree(4)
        base = application.base
        fbp = FrameBufferProperties()
        fbp.set_rgba_bits(16, 0, 0, 0)
        fbp.set_float_color(True)
        fbp.set_depth_bits(0)
        wp = WindowProperties.size(*self.size)
        self.buffer = base.graphicsEngine.make_output(base.pipe, 'caustics', SORT, fbp, wp, GraphicsPipe.BF_refuse_window | GraphicsPipe.BF_resizeable,
                                                      base.win.get_gsg(), base.win)
        if self.buffer is None:
            raise RuntimeError('không tạo được buffer caustics (card đồ hoạ không hỗ trợ texture số thực?)')
        self.buffer.add_render_texture(self.texture, GraphicsOutput.RTM_bind_or_copy)
        self.buffer.set_clear_color_active(True)
        self.buffer.set_clear_color((0, 0, 0, 0))
        self.buffer.set_clear_depth_active(False)
        self.scene = NodePath('caustics_scene')
        lens = OrthographicLens()
        lens.set_film_size(2, 2)
        lens.set_near_far(-1, 1)
        cam = self.scene.attach_new_node(Camera('caustics_cam', lens))
        region = self.buffer.make_display_region()
        region.set_camera(cam)
        region.set_clear_color_active(False)
        region.set_clear_depth_active(False)
        self.node = self.scene.attach_new_node(self._strip(cols))
        self.node.node().set_bounds(OmniBoundingVolume())             # the shader places every vertex itself: never cull
        self.node.node().set_final(True)
        self.node.set_instance_count(rows - 1)
        self.node.set_two_sided(True)                                  # a fold turns a triangle over: it must still add its light
        self.node.set_depth_test(False)
        self.node.set_depth_write(False)
        self.node.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_one, ColorBlendAttrib.O_one))
        self.node.set_shader(load_glsl('caustics'))
        x0, x1, z0, z1 = rect
        n = self.node
        n.set_shader_input('caus_grid', Vec4(x0, z0, (x1 - x0) / (cols - 1), (z1 - z0) / (rows - 1)))
        n.set_shader_input('caus_domain', Vec4(*dom))
        texel = (dom[1] - dom[0]) / self.size[0] * (dom[3] - dom[2]) / self.size[1]
        n.set_shader_input('caus_texel', Vec4(texel, PEAK, 0, 0))
        n.set_shader_input('caus_sun', Vec3(*sun))
        n.set_shader_input('water_rect', Vec4(*rect))
        n.set_shader_input('water_ramp', Vec4(*ramp))
        self.water_y = water_y
        for name, value in shared.items():
            n.set_shader_input(name, value)
        self.enabled = True

    @staticmethod
    def _strip(cols: int) -> GeomNode:
        """One row of the light mesh: 2 x cols vertices (column, 0 / 1) as a triangle strip; the shader turns them into world points."""
        vdata = GeomVertexData('caustics_row', GeomVertexFormat.get_v3(), Geom.UH_static)
        vdata.set_num_rows(2 * cols)
        w = GeomVertexWriter(vdata, 'vertex')
        for i in range(cols):
            w.add_data3(i, 0, 0)
            w.add_data3(i, 1, 0)
        prim = GeomTristrips(Geom.UH_static)
        prim.add_consecutive_vertices(0, 2 * cols)
        prim.close_primitive()
        geom = Geom(vdata)
        geom.add_primitive(prim)
        node = GeomNode('caustics_row')
        node.add_geom(geom)
        return node

    def set_input(self, name: str, value):
        self.node.set_shader_input(name, value)

    def set_enabled(self, on: bool):
        self.enabled = on
        self.buffer.set_active(on)

    def destroy(self):
        application.base.graphicsEngine.remove_window(self.buffer)
        self.scene.remove_node()
