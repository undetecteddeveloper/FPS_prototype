"""Hands + gun as seen from the player's eyes.

The gun lives in its OWN scene graph, drawn by its own camera (a second display region, depth cleared):
  - the gun's FOV is independent of the world FOV (ADS narrows the world FOV without distorting the gun, G4),
  - the gun never clips into walls / targets,
  - the world's 200 m depth range is not spoiled by the gun's 1 cm near plane.

Node chain: root -> sway -> rig -> actor.   `sway` receives the gun kick, sway, bob, sprint pose and ADS (summed in `update`);
`rig` only aligns the model so that FPS_Camera sits at the camera origin.
"""
from pathlib import Path

from direct.actor.Actor import Actor
from panda3d.core import (Camera, Filename, NodePath, PerspectiveLens, PNMImage, Point3, SamplerState, ShaderAttrib, Texture, Vec3, Vec4)
from ursina import application, window

from fps.core.movement import smoothstep, step_toward
from fps.game.frame_light import FrameLight
from fps.game.gltf_maps import read_normal_maps
from fps.game.shaders import load_glsl
from fps.weapon_data import GunData, LookData

MATERIALS = ('Hand_D', 'Glove_D', 'M4_D', 'Bullet5_56x45mm_D')
# multiplied into the gloss / focus / reflection of ViewLightData per material. The asset gives the gun body specular 0, so the gun's numbers are set by hand
# (gloss, focus, reflection, colour multiplier); the glove in the file is too light-coloured, a tactical glove is usually darker
MATERIAL_SCALE = {'M4_D': (1.0, 1.0, 1.0, 1.0), 'Glove_D': (0.22, 0.4, 0.35, 0.42), 'Hand_D': (0.08, 0.3, 0.15, 1.0), 'Bullet5_56x45mm_D': (1.5, 1.6, 1.4, 1.0)}


class Viewmodel:
    def __init__(self, gun: GunData, project_root: Path, light: FrameLight = None):
        self.gun = gun
        self.light = light or FrameLight(LookData(), gun)
        self.project_root = project_root
        self.ads = 0.0                                # 0 hip .. 1 fully aimed (set in `animate`)
        self.barrel_pose = (0.0,) * 6                 # actual gun pose (without image shake): the bullet direction is read from here
        base = application.base

        self.root = NodePath('viewmodel_root')      # not attached to render: the main camera does not see it
        self.sway = self.root.attach_new_node('viewmodel_sway')
        self.rig = self.sway.attach_new_node('viewmodel_rig')

        self.actor = Actor(Filename.from_os_specific(str(project_root / gun.glb)))
        self.actor.reparent_to(self.rig)
        self._bundle = self.actor.getPartBundle('modelRoot')
        self.actor.setBlend(frameBlend=True)         # clip is 30 fps but the screen is 60+ Hz: interpolate between two frames for smoothness

        self.clip_key = None                          # clip currently playing (key of GunData.clips) or None
        self._fade = None                             # fading from the still pose of the cancelled clip back to the ready pose
        self._empty = 0.0                             # 0 bolt closed .. 1 bolt locked back (empty magazine)
        self._view = 0.0                              # 0 .. 1 separate view for the reload clip (wide FOV, gun raised)
        self._fov = None

        # the file is in cm and faces -z: convert to metres and turn 180 degrees so it looks toward +z
        self.rig.set_scale(gun.model_scale)
        self.rig.set_h(180)
        self.hold_ready_pose()

        # translate so that FPS_Camera sits exactly at the origin (= the camera position used to draw the gun)
        eye_joint = self.actor.exposeJoint(None, 'modelRoot', gun.eye_joint)
        eye = self.sway.get_relative_point(eye_joint, Point3(0, 0, 0))
        self.rig.set_pos(-eye + Vec3(*gun.hip_offset))

        self._set_up_shading()
        self._set_up_camera(base)
        self._hide_reload_props()

    # --- build ---
    def _set_up_shading(self):
        """Own shader for the gun + hands, skeleton skinning on the GPU, light taken from FrameLight (shared with the world).

        CPU skinning (Panda's default) recomputes the 2 875 hand vertices every frame, ~1.3 ms; because the 30 fps clip is interpolated for smoothness on a 60+ Hz screen,
        the skeleton changes EVERY frame and FPS drops clearly while reloading. Meshes with skinning (a transform_blend column) use the ENABLE_SKINNING variant
        + the F_hardware_skinning flag; rigid meshes (gun body, magazine attached to a joint) use the non-skinned variant."""
        static = ShaderAttrib.make(load_glsl('viewmodel'))
        skinned = ShaderAttrib.make(load_glsl('viewmodel', ('ENABLE_SKINNING',))).set_flag(ShaderAttrib.F_hardware_skinning, True)
        self.root.set_attrib(static)
        self.skinned_vertices = 0
        self.material_nodes = {}                     # material name -> [GeomNode]
        for geom_np in self.actor.find_all_matches('**/+GeomNode'):
            node = geom_np.node()
            for i in range(node.get_num_geoms()):
                vd = node.get_geom(i).get_vertex_data()
                if vd.get_format().has_column('transform_blend'):
                    self.skinned_vertices += vd.get_num_rows()
                    geom_np.set_attrib(skinned)
                    break
            for name in MATERIALS:
                if name in geom_np.get_name():
                    self.material_nodes.setdefault(name, []).append(geom_np)
                    break
        r = self.root
        self.light.bind(r)
        r.set_shader_input('vm_view_x', self.light.view_x)
        r.set_shader_input('vm_view_y', self.light.view_y)
        r.set_shader_input('vm_view_z', self.light.view_z)
        r.set_shader_input('vm_flash_falloff', float(self.gun.flash.light_attenuation[2]))
        flat = Texture('flat_normal')
        flat.setup_2d_texture(1, 1, Texture.T_unsigned_byte, Texture.F_rgb)
        flat.set_ram_image(bytes((255, 128, 128)))                # BGR order: flat normal
        r.set_shader_input('vm_normal_tex', flat)
        self.normal_maps = read_normal_maps(self.project_root / self.gun.glb)
        for name, nodes in self.material_nodes.items():
            tex = self.normal_maps.get(name)
            if tex is not None:
                for np_ in nodes:
                    np_.set_shader_input('vm_normal_tex', tex)
        self.apply_light()

    def apply_light(self):
        """Push the `GunData.view_light` material into the gun shader (at build time, and every time the debug panel changes a value; only a few uniforms change)."""
        light = self.gun.view_light
        self.root.set_shader_input('vm_mat', Vec4(light.specular, light.gloss, light.env, light.normal_strength))
        self.root.set_shader_input('vm_sleeve', Vec4(*light.sleeve_color, 0.0))
        self.root.set_shader_input('vm_albedo', float(light.albedo))
        for name, nodes in self.material_nodes.items():
            sp, gl, en, al = MATERIAL_SCALE.get(name, (1.0, 1.0, 1.0, 1.0))
            for np_ in nodes:
                np_.set_shader_input('vm_mat', Vec4(light.specular * sp, light.gloss * gl, light.env * en, light.normal_strength))
                np_.set_shader_input('vm_albedo', float(light.albedo * al))
                np_.set_shader_input('vm_sleeve', Vec4(*light.sleeve_color, 1.0 if name == 'Hand_D' else 0.0))

    def set_flash_light(self, view_pos, color, falloff: float = None):
        """Muzzle flash light. `view_pos` in the gun-scene frame (x right, y up, z forward); `color` black = off. Lights both the gun and the world (FrameLight)."""
        self.light.set_flash(view_pos, color)

    def _set_up_camera(self, base):
        self.lens = PerspectiveLens()
        self.lens.set_near_far(0.01, 20.0)
        self._aspect = None
        self._sync_lens()
        cam_node = Camera('viewmodel_cam')
        cam_node.set_lens(self.lens)
        self.cam_np = self.root.attach_new_node(cam_node)

        self.output = base.win
        self.region = self._make_region(base.win)

    def _make_region(self, output):
        region = output.make_display_region()
        region.set_sort(5)                           # after the world (0), before the UI (20)
        region.set_clear_depth_active(True)
        region.set_clear_depth(1.0)
        region.set_clear_color_active(False)
        region.set_camera(self.cam_np)
        return region

    def move_to_output(self, output):
        """Draw the gun into another buffer (the lens draws the composited image of the world + gun)."""
        self.output.remove_display_region(self.region)
        self.output = output
        self.region = self._make_region(output)

    @property
    def current_fov(self) -> float:
        """Horizontal FOV the gun camera currently uses (changes when reloading)."""
        return self._fov

    def _sync_lens(self):
        g, r = self.gun, self.gun.reload
        base_fov = g.view_fov + (g.ads_view_fov - g.view_fov) * smoothstep(self.ads)
        fov = base_fov + (r.view_fov - base_fov) * smoothstep(self._view)
        aspect = window.aspect_ratio
        if aspect != self._aspect or fov != self._fov:
            self._aspect, self._fov = aspect, fov
            self.lens.set_aspect_ratio(aspect)
            self.lens.set_fov(fov)                   # FOV ngang

    def _hide_reload_props(self):
        """Mag2 and its bullet exist only in the reload clip; outside reloading they hover below the gun."""
        self.reload_props = []
        mag2 = self.actor.find('**/Mag2_M4_D_0-parent')
        if mag2.is_empty():
            return
        center = self._center(mag2)
        bullets = list(self.actor.find_all_matches('**/Bullet5_56x45mm_Bullet5_56x45mm_D_0-parent'))
        # two bullets share a name: the one that follows Mag2 is the one nearest to Mag2
        bullets.sort(key=lambda b: (self._center(b) - center).length())
        self.reload_props = [mag2] + bullets[:1]
        self.set_reload_props_visible(False)

    def _center(self, node):
        lo, hi = node.get_tight_bounds(self.actor)
        return (lo + hi) / 2

    # --- animation: still pose, playing a clip, cancelling ---
    def _ready_frame(self) -> tuple:
        """(anim, frame) of the ready pose = last frame of Draw (bolt closed)."""
        clip = self.gun.clips['draw']
        return clip.anim, clip.end

    def _locked_frame(self) -> tuple:
        """(anim, frame) of the empty-magazine pose: the first frame of Reload_Empty, where the rear bolt is locked (the other joints match the ready pose)."""
        clip = self.gun.clips['reload_empty']
        return clip.anim, clip.start

    def hold_ready_pose(self):
        """Stand still in the ready pose, bolt closed. Blending off: each pose that is set is the only pose."""
        self.clip_key, self._fade, self._empty = None, None, 0.0
        self.actor.disableBlend()
        self.actor.pose(*self._ready_frame())
        self._bundle.force_update()

    def set_reload_props_visible(self, visible: bool):
        for node in self.reload_props:
            node.show() if visible else node.hide()

    def on_event(self, event: tuple):
        """Event from core.handling.Handling: ('start', key, speed) / ('swap', key) / ('done', key) / ('cancel', key, frame)."""
        name = event[0]
        if name == 'start':
            self._play(event[1], event[2])
        elif name == 'done':
            self.hold_ready_pose()
        elif name == 'cancel':
            self._begin_fade(event[1])

    def _play(self, key: str, speed: float):
        clip = self.gun.clips[key]
        self.hold_ready_pose()                            # clear any blend / fade still running before playing (a play is the only pose)
        self.actor.play(clip.anim, fromFrame=clip.start, toFrame=clip.end)
        self.actor.setPlayRate(speed, clip.anim)
        self.clip_key = key

    def _begin_fade(self, key: str):
        """Cancel the clip: freeze at the current frame, then slide back to the ready pose over `reload.cancel_blend` seconds."""
        anim = self.gun.clips[key].anim
        self.actor.stop(anim)
        self.actor.enableBlend()
        self.actor.setControlEffect(anim, 1.0)
        ready_anim, ready_frame = self._ready_frame()
        self.actor.pose(ready_anim, ready_frame)
        self.actor.setControlEffect(ready_anim, 0.0)
        self._fade = {'anim': anim, 't': 0.0}
        self.clip_key = None

    def _reload_view_wanted(self) -> bool:
        """Reloading and not yet at `Clip.settle` minus the blend time: the reload view (wide FOV, gun raised) must be switched OFF by the time the gun is back in place,
        not wait for the clip to end (the last part is only the fingers folding back; if the gun stays raised with nothing happening, it looks misplaced)."""
        if self.clip_key not in ('reload', 'reload_empty'):
            return False
        clip = self.gun.clips[self.clip_key]
        settle = clip.settle if clip.settle is not None else clip.end
        left = (settle - self.actor.getCurrentFrame(clip.anim)) / 30.0 / max(self.gun.reload.speed, 1e-3)
        return left > self.gun.reload.view_blend

    def animate(self, dt: float, magazine_empty: bool, ads: float = 0.0):
        """Every frame (before `update`): progress of the cancel slide, and the rear bolt locking / releasing with an empty / loaded magazine."""
        r = self.gun.reload
        self.ads = ads
        self._view = step_toward(self._view, 1.0 if self._reload_view_wanted() else 0.0, 1.0 / max(r.view_blend, 1e-3), dt)
        if self._fade:
            f = self._fade
            f['t'] += dt
            w = smoothstep(f['t'] / r.cancel_blend) if r.cancel_blend > 0 else 1.0
            ready_anim = self._ready_frame()[0]
            self.actor.setControlEffect(f['anim'], 1.0 - w)
            self.actor.setControlEffect(ready_anim, w)
            if w >= 1.0:
                self.hold_ready_pose()
            return
        if self.clip_key:
            return                                        # the clip runs on the Panda clock by itself
        target = 1.0 if magazine_empty else 0.0
        if self._empty == target:
            return
        self._empty = step_toward(self._empty, target, 1.0 / max(r.bolt_lock_blend, 1e-3), dt)
        ready, locked = self._ready_frame(), self._locked_frame()
        if self._empty <= 0.0 or self._empty >= 1.0:
            self.actor.disableBlend()
            self.actor.pose(*(locked if self._empty >= 1.0 else ready))
        else:
            self.actor.enableBlend()
            self.actor.pose(*ready)
            self.actor.pose(*locked)
            self.actor.setControlEffect(ready[0], 1.0 - self._empty)
            self.actor.setControlEffect(locked[0], self._empty)
        self._bundle.force_update()

    def update(self, *poses: tuple, visual: tuple = ()):
        """Each pose = (x right, y up, z forward, pitch up, yaw right, roll right), metres and degrees: gun kick
        (GunKick.pose), sway/ADS/sprint (Sway.update), free drift (FreeAim.pose). They are summed and set on the `sway` node; this sum is `barrel_pose`, the source of the bullet direction.
        `visual`: image-ONLY poses (camera shake, gun following the head); they do not enter `barrel_pose`, so they never change the bullet direction.

        SIGN TRAP (measured with tools/selftests/g3_selftest.py): the raw `set_hpr` of a node in this gun graph differs from Ursina's `Entity.rotation`
        in the world: positive h turns the gun to the LEFT, positive p tilts the barrel UP, positive r leans it RIGHT."""
        self._sync_lens()
        k = smoothstep(self._view)
        if k > 0.0:
            poses = poses + (tuple(c * k for c in self.gun.reload.view_pose),)
        self.barrel_pose = tuple(sum(c) for c in zip(*poses)) if poses else (0.0,) * 6
        x, y, z, pitch_up, yaw_right, roll_right = (sum(c) for c in zip(self.barrel_pose, *visual))
        self.sway.set_pos_hpr(x, y, z, -yaw_right, pitch_up, roll_right)

    def destroy(self):
        self.output.remove_display_region(self.region)
        self.actor.cleanup()
        self.actor.remove_node()
        self.root.remove_node()
