"""Visual side of the world: shaders (ceiling lamps, shadows, material texture, fake AO, dust in the room), lamp halos, and shadows of moving targets.

The world shader is in assets/shaders/world.vert|frag (based on Ursina's unlit_with_fog_shader); the lighting shared with the gun is in assets/shaders/light_common.glsl + frame_light.py. Applied to every object of the range,
targets and bullet holes by setting `Entity.shader`; the material is picked by the `look_material` input of each Entity. UI objects keep
Ursina's default shader. Values in weapon_data.LookData; room dimensions in core/room.RoomLayout.

Shadows (`LookData.shadows`): True = real shadows from every ceiling lamp (lamp_shadows.py, drawn once at startup), 'fake' = soft dark blobs
under targets and markers, False = no shadows. Fake AO (wall bases, around columns, under the ceiling) is present in all three modes.
"""
import math
import random

from panda3d.core import (ColorBlendAttrib, OmniBoundingVolume, TransparencyAttrib, SamplerState, Vec2 as PandaVec2, Vec4)
from PIL import Image
from ursina import Entity, Mesh, Shader, Texture, application, color, time, window
from ursina.vec2 import Vec2

from fps.game.frame_light import FrameLight
from fps.game.shaders import load_glsl, read_source
from fps.weapon_data import LookData

MATERIALS = {'floor': 1.0, 'walls': 2.0, 'pillars': 3.0, 'ceiling': 4.0, 'lamp_glow': 5.0, 'lamp_shades': 0.0,
             'signs': 6.0, 'sign_rods': 0.0}      # 6 = distance signs (text glows faintly)


def noise_texture(size: int = 128, cells: int = 8, seed: int = 11) -> Texture:
    """Seamless value noise (tiles with no visible seam), one bright channel, smoothly interpolated: laid over the ground instead of a repeating grid of tiles."""
    rng = random.Random(seed)
    lattice = [[rng.random() for _ in range(cells)] for _ in range(cells)]

    def smooth(t):
        return t * t * (3 - 2 * t)

    def value(x, y):
        gx, gy = x / size * cells, y / size * cells
        x0, y0 = int(gx) % cells, int(gy) % cells
        x1, y1 = (x0 + 1) % cells, (y0 + 1) % cells
        fx, fy = smooth(gx - int(gx)), smooth(gy - int(gy))
        top = lattice[y0][x0] * (1 - fx) + lattice[y0][x1] * fx
        bottom = lattice[y1][x0] * (1 - fx) + lattice[y1][x1] * fx
        return top * (1 - fy) + bottom * fy

    img = Image.new('L', (size, size))
    img.putdata([int(255 * (0.65 * value(x, y) + 0.35 * value(x * 2.3 + 13, y * 2.3 + 7))) for y in range(size) for x in range(size)])
    tex = Texture(img, filtering='mipmap')
    tex._texture.set_wrap_u(SamplerState.WM_repeat)
    tex._texture.set_wrap_v(SamplerState.WM_repeat)
    return tex


def blob_texture(size: int = 64) -> Texture:
    """Soft dark blob (fake shadow): alpha falls off from the centre to the edge."""
    img = Image.new('RGBA', (size, size))
    px = []
    for y in range(size):
        for x in range(size):
            r = min(math.hypot((x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1), 1.0)
            px.append((0, 0, 0, int(255 * 0.75 * (1 - r * r) ** 2)))
    img.putdata(px)
    return Texture(img, filtering='mipmap')


def halo_texture(size: int = 64) -> Texture:
    """Faint glow around a lamp bulb: white, alpha falls off quickly from the centre (additive)."""
    img = Image.new('RGBA', (size, size))
    px = []
    for y in range(size):
        for x in range(size):
            r = min(math.hypot((x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1), 1.0)
            a = (1 - r) ** 2.2 * (1 - r * r)
            px.append((255, 255, 255, int(255 * a)))
    img.putdata(px)
    return Texture(img, filtering='mipmap')


class WorldLook:
    def __init__(self, params: LookData, world: dict, targets: list, decals, light: FrameLight):
        self.p = params
        self.world = world
        self.targets = targets
        self.light = light
        self.shader = self._make_shader()
        self.shadows = None                 # LampShadows when real shadows are on
        self.blobs = []
        self.mover_blobs = []               # (moving target, its fake blob): the blob follows the target
        self.movers = [t for t in targets if t.patrol is not None]
        self._mover_next = 0                # next moving target whose shadow is redrawn
        self._mover_clock = 0.0
        self._mover_drawn_x = {}            # x of the target when its shadow was last drawn: a still target need not be redrawn
        self.mover_shadow_refreshes = 0     # number of moving-target shadow redraws (for measurement)
        self._ready = False                 # False while building
        render = application.base.render
        room = world['room']

        render.set_shader_input('look_fog', (*params.fog_color, params.fog_density))
        render.set_shader_input('look_detail_strength', float(params.detail_strength))
        render.set_shader_input('look_detail_tex', noise_texture()._texture)
        render.set_shader_input('look_material', 0.0)
        render.set_shader_input('look_room', Vec4(room.half_width, room.z_back, room.z_end, room.height))
        render.set_shader_input('look_pillar', Vec4(room.pillar_z0, room.pillar_spacing, room.pillar_width / 2,
                                                    room.pillar_depth))
        self._push_flash(render)
        light.bind(render)

        entities = [world[k] for k in MATERIALS]
        entities += [*world['stripes'], *world['posts'], *world['berms']]
        entities += [t.plate for t in targets]
        entities += decals.entities
        for e in entities:
            e.shader = self.shader
        for key, mat in MATERIALS.items():
            world[key].set_shader_input('look_material', mat)

        self._make_blobs(world, targets)
        self.halos = self._make_halos(world['lamps'], params) if params.lamp_halo > 0 else None
        self.mode = None
        self.set_shadow_mode(params.shadows)

        window.color = color.rgb(*params.fog_color)        # no sky: the background (if it shows through) gets the same colour as the dust in the room
        # draw before the game starts: compile the world shader and draw the shadow atlas so they do not land on the game's first frame
        if self.shadows:
            self.shadows.render_now()
            # moving targets go into the atlas AFTER the first draw (so no ghost shadows are left at the start position on distant lamps), then the lamps near them are drawn separately
            for t in self.movers:
                self.shadows.add_caster(t.plate)
            near = set()
            for t in self.movers:
                near.update(self._lamps_near_mover(t))
                self._mover_drawn_x[t] = t.root.x
            if near:
                self.shadows.render_lamps_now(near)
        else:
            application.base.graphicsEngine.render_frame()
        self._ready = True

    def _push_flash(self, node):
        flash = self.light.gun.flash
        node.set_shader_input('look_flash_world', PandaVec2(flash.world_power / max(flash.light_power, 0.01), flash.world_falloff))

    @staticmethod
    def _make_shader() -> Shader:
        vert, frag = read_source('world.vert'), read_source('world.frag')
        return Shader(name='fps_world', language=Shader.GLSL, vertex=vert, fragment=frag,
                      default_input={'texture_scale': Vec2(1, 1), 'texture_offset': Vec2(0.0, 0.0)})

    def _make_blobs(self, world, targets):
        tex = blob_texture()
        spots = [(t.root.x, t.root.z, t.width * 1.6, 1.8) for t in targets]
        spots += [(x, z, 0.9, 1.3) for x, z in world['post_spots']]
        for x, z, sx, sz in spots:
            b = Entity(model='plane', texture=tex, position=(x, 0.002, z), scale=(sx, 1, sz), color=color.white, enabled=False,
                       shader=self.shader)
            b.set_transparency(TransparencyAttrib.M_alpha)
            b.set_depth_write(False)
            b.set_depth_offset(1)
            b.set_bin('transparent', 0)
            self.blobs.append(b)
        for t, b in zip(targets, self.blobs):             # the spots start with the targets, in the same order
            if t.patrol is not None:
                self.mover_blobs.append((t, b))

    @staticmethod
    def _make_halos(lamps, params) -> Entity:
        """Halos of every lamp bulb in ONE draw call: each card has 4 vertices at the lamp centre; assets/shaders/halo.vert expands them to face the camera. Additive blend, no depth write."""
        verts, uvs, tris = [], [], []
        for x, y, z in lamps:
            n = len(verts)
            verts += [(x, y - 0.08, z)] * 4
            uvs += [(0, 0), (1, 0), (1, 1), (0, 1)]
            tris += [n, n + 1, n + 2, n, n + 2, n + 3]
        e = Entity(model=Mesh(vertices=verts, uvs=uvs, triangles=tris, static=True), texture=halo_texture(), add_to_scene_entities=False)
        e.setShader(load_glsl('halo'), 1)
        e.set_shader_input('halo_size', 1.6)
        e.set_shader_input('halo_color', Vec4(*params.lamp_color, params.lamp_halo))
        e.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha, ColorBlendAttrib.O_one))
        e.set_depth_write(False)
        e.set_two_sided(True)
        e.set_bin('fixed', 5)
        e.node().set_bounds(OmniBoundingVolume())
        e.node().set_final(True)
        return e

    def set_shadow_mode(self, mode):
        """True / 'fake' / False; can be changed while running (real shadows are built the first time they are needed)."""
        if mode is True and self.shadows is None:
            from fps.game.lamp_shadows import LampShadows
            self.shadows = LampShadows(self.world['lamps'], self.p.lamp_radius, self.p.shadow_face_size)
            for e in self.world['shadow_casters']:
                LampShadows.add_caster(e)
            for t in self.targets:
                if self._ready or t.patrol is None:          # while building: moving targets go into the atlas after the first draw (see end of __init__)
                    LampShadows.add_caster(t.plate)
        if mode is True:
            self._mover_drawn_x.clear()                      # the atlas may keep an old shadow of a moving target: redraw it in the following passes
            self.light.radius = self.shadows.radius          # radius baked into the shadow map
            self.light.set_shadows(mode, self.shadows.shader_inputs())
        else:
            self.light.set_shadows(mode)
        for b in self.blobs:
            b.enabled = mode == 'fake'
        self.mode = mode

    def apply_params(self):
        """Debug panel (G6): pushes the LookData light values that take effect IMMEDIATELY (lamps, colour grade, dust, shadows, corner darkening...) back into the shader
        under the same input names as at build time. Does not touch the lamp positions / count or the shadow map size (baked at build time: needs a restart)."""
        p, render = self.p, application.base.render
        render.set_shader_input('look_fog', (*p.fog_color, p.fog_density))
        render.set_shader_input('look_detail_strength', float(p.detail_strength))
        self._push_flash(render)
        self.set_shadow_mode(p.shadows)                      # also pushes look_shadow again (shadow stripe / brightness of the lamp shadows)
        self.light.apply_params()
        window.color = color.rgb(*p.fog_color)
        if self.halos is not None:
            self.halos.set_shader_input('halo_color', Vec4(*p.lamp_color, p.lamp_halo))

    def _lamps_near_mover(self, target) -> list:
        """Lamps whose shadow must be redrawn when a moving target changes position: lamps within `mover_shadow_reach` x lamp radius of the target along z."""
        z = target.root.z
        return self.shadows.lamps_near(z, z, self.p.mover_shadow_reach * self.shadows.radius)

    def _faces_for_mover(self, target, old_x: float) -> dict:
        """Lamp -> cubemap faces that can see the target (at the old or the new position): only those faces are redrawn, much cheaper than all 5."""
        half = target.width / 2.0
        x0, x1 = min(old_x, target.root.x) - half, max(old_x, target.root.x) + half
        z = target.root.z
        out = {}
        for i in self._lamps_near_mover(target):
            lx, _, lz = self.shadows.lamps[i]
            faces = [2]                                      # -y: always, the target stands under the lamp
            if x1 > lx:
                faces.append(0)                              # +x
            if x0 < lx:
                faces.append(1)                              # -x
            if z + 0.1 > lz:
                faces.append(3)                              # +z
            if z - 0.1 < lz:
                faces.append(4)                              # -z
            out[i] = faces
        return out

    def _tick_movers(self):
        """Real shadows of moving targets: the lamps and walls are still, so the atlas is drawn once; moving targets instead get their nearby lamps
        redrawn every 1/(hz x number of targets) seconds, one target at a time (taking turns). Called from `update` (before drawing), so the atlas is drawn in that same frame."""
        if self.mode is not True or not self.movers or self.p.mover_shadow_hz <= 0:
            return
        self._mover_clock += time.dt
        interval = 1.0 / (self.p.mover_shadow_hz * len(self.movers))
        if self._mover_clock < interval:
            return
        self._mover_clock = min(self._mover_clock - interval, interval)
        for _ in range(len(self.movers)):                    # next target that HAS moved since the last draw
            t = self.movers[self._mover_next % len(self.movers)]
            self._mover_next += 1
            old = self._mover_drawn_x.get(t)
            if old is None or abs(t.root.x - old) > 1e-4:
                self._mover_drawn_x[t] = t.root.x
                self.shadows.refresh_faces(self._faces_for_mover(t, t.root.x if old is None else old))
                self.mover_shadow_refreshes += 1
                return

    def update(self):
        """Every frame: turn the shadow buffer off once drawing is done; shadows of moving targets (real: redraw nearby lamps; fake: a dark blob follows the target)."""
        if self.shadows:
            self.shadows.update()
            self._tick_movers()
        if self.mode == 'fake':
            for t, b in self.mover_blobs:
                b.x = t.root.x
