"""Real shadows of the ceiling lamps: each lamp has a 5-face cubemap (the face pointing up at the ceiling is dropped); all faces of all lamps are laid out as tiles
in ONE depth texture (the atlas, see core/room.py). assets/shaders/world.frag samples this atlas with hardware depth comparison
(sampler2DShadow) + 4 PCF samples.

Lamps and walls are still, so the atlas is DRAWN ONCE at startup (115 faces, a few ms), after which the buffer is turned off: each frame then only pays the
shader sampling cost. Moving objects (the moving targets in G6) call `refresh(z_min, z_max)` to redraw only the nearby lamps in the next frame.

Only objects marked with `add_caster` cast shadows (walls, columns, beams, targets, markers, the terrain bank); the floor, ceiling, lamps, bullet holes and the gun do not.
The shadow cameras draw the BACK faces of objects (inverted cull), so a surface is lit relative to its own back side: no "acne".
"""
from panda3d.core import (BitMask32, Camera, ColorWriteAttrib, CullFaceAttrib, FrameBufferProperties, GraphicsOutput,
                          GraphicsPipe, LMatrix4f, NodePath, PerspectiveLens, PTA_LMatrix4f, SamplerState, Shader,
                          Texture, Vec3, WindowProperties)
from ursina import application

from fps.core.room import FACE_COUNT, FACES, atlas_grid, face_fov, tile_index, tile_rect
from fps.game.shaders import SHADER_DIR

SHADOW_MASK = BitMask32.bit(7)       # shadow cameras only see nodes with this bit (show_through); the main camera is not affected
GUARD_PX = 2                         # border on each side of a face (pixels) for the 4 PCF samples at the edge
NEAR = 0.05


def _depth_shader() -> Shader:
    vert = (SHADER_DIR / 'shadow_depth.vert').read_text(encoding='utf-8')
    frag = (SHADER_DIR / 'shadow_depth.frag').read_text(encoding='utf-8')
    return Shader.make(Shader.SL_GLSL, vert, frag)


def _face_up(direction):
    return (0, 0, 1) if direction[1] != 0 else (0, 1, 0)


class LampShadows:
    def __init__(self, lamps: list, radius: float, face_size: int):
        base = application.base
        render = base.render
        self.lamps = lamps
        self.radius = radius
        self.face_size = face_size
        self.cols, self.rows = atlas_grid(len(lamps) * FACE_COUNT)
        width, height = self.cols * face_size, self.rows * face_size

        fbp = FrameBufferProperties()
        fbp.set_depth_bits(24)
        fbp.set_rgb_color(False)
        fbp.set_rgba_bits(0, 0, 0, 0)
        self.buffer = base.graphicsEngine.make_output(
            base.pipe, 'lamp_shadows', -10, fbp, WindowProperties.size(width, height), GraphicsPipe.BF_refuse_window,
            base.win.get_gsg(), base.win)
        if self.buffer is None:
            raise RuntimeError('không tạo được buffer cho bản đồ bóng')
        self.texture = Texture('lamp_shadow_atlas')
        self.buffer.add_render_texture(self.texture, GraphicsOutput.RTM_bind_or_copy, GraphicsOutput.RTP_depth)
        self.texture.set_minfilter(SamplerState.FT_shadow)          # hardware depth comparison (sampler2DShadow), with bilinear filtering
        self.texture.set_magfilter(SamplerState.FT_shadow)
        self.texture.set_wrap_u(SamplerState.WM_clamp)
        self.texture.set_wrap_v(SamplerState.WM_clamp)
        self.buffer.disable_clears()                                 # each tile clears itself (redrawing a few lamps does not clear the others)
        self.atlas_size = (width, height)

        # shared state of every shadow camera: the shader writes depth only (no colour) and draws back faces; it overrides every shader / attribute of the object
        holder = NodePath('shadow_state')
        holder.set_shader(_depth_shader(), 1000)
        holder.set_attrib(ColorWriteAttrib.make(ColorWriteAttrib.C_off), 1000)
        holder.set_attrib(CullFaceAttrib.make_reverse(), 1000)
        holder.set_texture_off(1000)
        state = holder.get_state()

        self.lens = PerspectiveLens()
        fov = face_fov(face_size, GUARD_PX)
        self.lens.set_fov(fov, fov)
        self.lens.set_near_far(NEAR, radius + 1.0)

        render.hide(SHADOW_MASK)                                     # no shadows by default; add_caster turns them back on
        self.rig = render.attach_new_node('lamp_shadow_rig')
        self.regions = []                                            # [lamp] -> [display region of each face]
        for i, pos in enumerate(lamps):
            regs = []
            for f, d in enumerate(FACES):
                cam = Camera(f'lamp{i}_face{f}', self.lens)
                cam.set_camera_mask(SHADOW_MASK)
                cam.set_initial_state(state)
                cam_np = self.rig.attach_new_node(cam)
                cam_np.set_pos(Vec3(*pos))
                cam_np.look_at(Vec3(*(p + c for p, c in zip(pos, d))), Vec3(*_face_up(d)))
                l, r, b, t = tile_rect(tile_index(i, f), self.cols, self.rows)
                dr = self.buffer.make_display_region(l, r, b, t)
                dr.set_camera(cam_np)
                dr.set_clear_depth_active(True)
                dr.set_clear_depth(1.0)
                regs.append(dr)
            self.regions.append(regs)

        # matrix "lamp-to-point vector (world)" to each face's clip space: shared by all lamps (only the position differs)
        self.face_mats = PTA_LMatrix4f.empty_array(FACE_COUNT)
        probe = NodePath('probe')
        proj = self.lens.get_projection_mat()
        for f, d in enumerate(FACES):
            probe.set_pos(0, 0, 0)
            probe.look_at(Vec3(*d), Vec3(*_face_up(d)))
            view = LMatrix4f(probe.get_mat())
            view.invert_in_place()
            self.face_mats[f] = view * proj
        self._frames_left = 2                                         # draw on the first frame (one extra frame to be safe), then turn off
        self.render_count = 0

    @staticmethod
    def add_caster(nodepath):
        nodepath.show_through(SHADOW_MASK)

    def lamps_near(self, z_min: float, z_max: float, reach: float = None) -> list:
        """Indices of the lamps whose light area (radius `reach`, default `radius`) touches the segment [z_min, z_max]."""
        reach = self.radius if reach is None else reach
        return [i for i, (_, _, z) in enumerate(self.lamps) if z + reach >= z_min and z - reach <= z_max]

    def refresh(self, z_min: float = None, z_max: float = None, reach: float = None):
        """Redraw right now, in this frame (call it in the update phase, BEFORE drawing), the lamps whose light area touches [z_min, z_max];
        with no arguments, redraw them all. `reach` < lamp radius skips the lamps at the edge, where the light is almost off.
        Draws ONE frame only (calling it every frame means drawing every frame)."""
        self.refresh_lamps(range(len(self.lamps)) if z_min is None else self.lamps_near(z_min, z_max, reach))

    def refresh_lamps(self, indices):
        """Like `refresh` but selected by lamp index (to merge several z ranges: call with the union of several `lamps_near` results)."""
        wanted = set(indices)
        for i in range(len(self.lamps)):
            for dr in self.regions[i]:
                dr.set_active(i in wanted)
        self.buffer.set_active(True)
        self.render_count += 1
        self._frames_left = 0                # this frame is drawn; the next frame's `update` turns the buffer off (unless refresh is called again)

    def refresh_faces(self, faces: dict):
        """Like `refresh_lamps` but only the named faces: {lamp index: [face, ...]}."""
        for i in range(len(self.lamps)):
            wanted = faces.get(i, ())
            for f, dr in enumerate(self.regions[i]):
                dr.set_active(f in wanted)
        self.buffer.set_active(True)
        self.render_count += 1
        self._frames_left = 0

    def render_lamps_now(self, indices):
        """Draw these lamps RIGHT NOW (while the game is being built), then turn the buffer off: to catch up on objects added to the atlas after `render_now`."""
        self.refresh_lamps(indices)
        engine = application.base.graphicsEngine
        engine.render_frame()
        engine.render_frame()
        self._frames_left = 0
        self.buffer.set_active(False)

    def render_now(self):
        """Draw the atlas RIGHT NOW (while the game is being built, before the loop), then turn the buffer off: the game's first frame does not
        have to pay ~0.5 s to draw 115 faces plus the shader compile (that frame landed during the draw-gun animation and made its clip jump)."""
        engine = application.base.graphicsEngine
        engine.render_frame()
        engine.render_frame()
        self.render_count += 1
        self._frames_left = 0
        self.buffer.set_active(False)

    def update(self):
        """Called every frame (before drawing). Turns the buffer off once the requested pass has been drawn."""
        if self._frames_left > 0:
            self._frames_left -= 1
            self.render_count += 1
        elif self.buffer.is_active():
            self.buffer.set_active(False)

    def shader_inputs(self) -> dict:
        w, h = self.atlas_size
        return {'look_shadow_atlas': self.texture, 'look_face_mat': self.face_mats,
                'look_shadow_grid': (float(self.cols), float(self.rows), 1.0 / w, 1.0 / h)}
