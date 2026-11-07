"""Build and run the game: `Game` gathers the parts; `create_game()` is shared by main.py and the test tools."""
import argparse
import copy
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # project root (contains assets/)

from fps.game import gltf_patch  # noqa: E402  (must load before Ursina)

gltf_patch.apply()

import ursina  # noqa: E402
from panda3d.core import Filename, loadPrcFileData  # noqa: E402
from ursina import Entity, Ursina, application, camera, mouse, scene, time, window  # noqa: E402

from fps.core.exposure import target_exposure  # noqa: E402
from fps.core.freeaim import barrel_view_dir, view_to_world  # noqa: E402
from fps.core.headcam import HeadCam, reload_state  # noqa: E402
from fps.core.movement import aim_direction  # noqa: E402
from fps.core.params import ParamStore  # noqa: E402
from fps.core.shake import Shake  # noqa: E402
from fps.game.camera_shake import ShakeView  # noqa: E402
from fps.game.combat import Combat  # noqa: E402
from fps.game.debug_panel import DebugPanel  # noqa: E402
from fps.game.effects import Effects  # noqa: E402
from fps.game.foley import Foley  # noqa: E402
from fps.game.frame_light import FrameLight  # noqa: E402
from fps.game.gun_audio import GunAudio  # noqa: E402
from fps.game.hud import Hud, setup_fonts  # noqa: E402
from fps.game.lens import Lens  # noqa: E402
from fps.game.look import WorldLook  # noqa: E402
from fps.game.player import Player  # noqa: E402
from fps.game.smoke import GunSmoke  # noqa: E402
from fps.game.ground import WALK_BOUNDS, build_ground  # noqa: E402
from fps.core.sway import Sway, ads_target_for  # noqa: E402
from fps.game.viewmodel import Viewmodel  # noqa: E402
from fps.weapon_data import GUNS, M4, GameParams  # noqa: E402

USER_PARAMS = ROOT / 'user_params.json'      # user parameters saved from the debug panel (F1); gitignored


def prune_scene_entities():
    """Remove from `scene.entities` every entity with no `update` / `input` (it is still drawn normally).

    Each Ursina frame walks this whole list in Python (checks parent, checks enabled...), and entities using the default shader also call `set_shader_input` to push the camera position;
    measured at 3-5 ms per frame, and changing shader inputs also makes Panda regroup the draw state. The ground slab needs none of that."""
    def keep(e):
        return callable(getattr(e, 'update', None)) or callable(getattr(e, 'input', None)) or getattr(e, 'scripts', None)
    scene.entities = [e for e in scene.entities if keep(e)]


class Game(Entity):
    """Gathers the parts and runs the per-frame loop."""

    def __init__(self, params: GameParams, quit_after: float = 0.0, sound: bool = True, draw: bool = True,
                 effects: bool = True, look: bool = True, shake: bool = True,
                 user_params: bool = False, hud: bool = False, lens: bool = True, free_aim: bool = True, gun_name: str = 'm4'):
        super().__init__()
        self.params = params
        self.gun_name = gun_name                      # key in GUNS of the gun in hand
        self._audio_defaults = (dict(params.audio.cues), dict(params.audio.sound_files))     # M4 sound beats / files: restored when switching back to a gun without its own
        self._sound, self._effects, self._shake_on, self._free_aim = sound, effects, shake, free_aim
        self._ammo = {}                               # gun key -> (mag, reserve, auto) while another gun is in hand
        self._pending_gun = None                      # gun key waiting for the holster clip to finish
        if params.gun.sound_cues is not None:         # per-gun sound beats / files (the Glock's pistol sounds)
            params.audio.cues = dict(params.gun.sound_cues)
        if params.gun.sound_files:
            params.audio.sound_files = {**params.audio.sound_files, **params.gun.sound_files}
        # live parameter store (G6): defaults are snapshotted FIRST, then (if requested) user_params.json is loaded BEFORE the parts are built, so even numbers read only once at build time
        # (rounds in the magazine...) take effect. Every module keeps the same dataclass objects as `params`.
        self.params_store = ParamStore(params)
        self.params_report = self.params_store.load(USER_PARAMS) if user_params and USER_PARAMS.exists() else None
        if self.params_report is not None:
            print(f'[thông số] {USER_PARAMS.name}: {self.params_report.message}')
        self.quit_after = quit_after
        self._age = 0.0
        self._draw_pending = draw         # draw the gun on the first frame (not during build: loading the model makes the first frame very long)
        self.world = build_ground(params.look.ground_color)
        self.player = Player(params.player, WALK_BOUNDS, params.gun)
        self.audio = GunAudio(params.gun, ROOT) if sound and params.gun.shot_sound else None
        self.foley = Foley(params.audio, params.gun, self.player, ROOT) if sound else None    # reload, footsteps (off with the sound flag / --mute)
        if not free_aim:
            params.gun.free_aim.barrel_aim = False
        self.light = FrameLight(params.look, params.gun)                       # one shared light source for the world and the gun
        self.viewmodel = Viewmodel(params.gun, ROOT, self.light)
        self.smoke = GunSmoke(params.look, self.light) if effects else None        # gunpowder smoke: one world-space pool shared by both guns
        self.fx = Effects(params.gun, self.viewmodel, smoke=self.smoke) if effects else None
        self.shake = Shake(params.gun.shake) if shake else None                # purely visual shake (does not change bullet direction)
        self.head = HeadCam(params.gun.head) if shake else None               # head + body motion on the image: uses the `shake` flag because it is also purely visual camera motion
        self.shake_view = ShakeView(self.shake, self.head, params.lens) if shake else None      # all of it moves the LENS FRAME, not the world camera
        self.combat = Combat(params, self.player, self.world['colliders'], audio=self.audio, fx=self.fx, shake=self.shake)
        self.combat.aim_source = self._barrel_direction
        self.combat.foley = self.foley
        self.combat.viewmodel = self.viewmodel
        self.look = WorldLook(params.look, self.world, self.combat.decals, self.light) if look else None
        self.lens = Lens(params.lens, self.viewmodel) if lens else None
        self.sway = Sway(params.gun.sway, ads_target_for(params.gun))
        self.hud = Hud(params.gun.credit) if hud else None                    # Bodycam style: nothing on screen; only the selftest turns it on to read numbers
        self.debug = DebugPanel(self, self.params_store, USER_PARAMS)         # F1 panel: built lazily the first time it opens; costs nothing while closed
        self.params_store.subscribe(self._on_params_changed)

    # --- weapon switch (keys 1 / 2): holster clip of the gun in hand -> rebuild the gun-dependent parts -> draw clip of the new gun ---
    def request_gun(self, name: str):
        h = self.combat.handling
        if name == self.gun_name or name not in GUNS or self._pending_gun or h.busy:
            return
        self._pending_gun = name
        h.start_holster()

    def _merge_audio(self, gun):
        cues, files = self._audio_defaults
        a = self.params.audio
        a.cues = dict(gun.sound_cues) if gun.sound_cues is not None else dict(cues)
        a.sound_files = {**files, **(gun.sound_files or {})}

    def _apply_gun(self, name: str):
        """Swap the gun in hand. Rounds are remembered per gun; world, bullets in flight and holes stay. Loading the model takes ~1 s (one long frame): the draw clip waits for the next normal frame."""
        w = self.combat.weapon
        self._ammo[self.gun_name] = (w.mag, w.reserve, w.auto)
        gun = copy.deepcopy(GUNS[name])
        if not self._free_aim:
            gun.free_aim.barrel_aim = False
        self.params.gun = gun
        self._merge_audio(gun)
        self.player.set_gun(gun)
        self.light.gun = gun
        old_vm, old_fx = self.viewmodel, self.fx
        self.viewmodel = Viewmodel(gun, ROOT, self.light)
        self.fx = Effects(gun, self.viewmodel, smoke=self.smoke) if self._effects else None
        if self.lens:
            self.viewmodel.move_to_output(self.lens.manager.buffers[-1])
        if self.shake is not None:                      # keep the running shake / head state (rebuilding it would jolt the lens frame mid-switch): only swap the data
            self.shake.d = gun.shake
            self.head.d = self.head.gaze.d = gun.head
        self.audio = GunAudio(gun, ROOT) if self._sound and gun.shot_sound else None
        self.foley = Foley(self.params.audio, gun, self.player, ROOT) if self._sound else None
        self.combat.set_gun(gun, self.audio, self.fx, self.shake, self.viewmodel, self.foley, self._ammo.get(name))
        self.combat.aim_source = self._barrel_direction
        self.sway.d = gun.sway                          # same for the sway state (lag, bob phase): the new gun comes up where the old one was going
        if hasattr(self.sway.lag, 'd'):
            self.sway.lag.d = gun.sway
        self.sway.ads_target = ads_target_for(gun)
        old_vm.destroy()
        if old_fx:
            old_fx.destroy()
        self.viewmodel.prewarm()                        # compile the new gun's shaders now, not in the first frames of the draw
        self.gun_name, self._pending_gun = name, None
        self._draw_pending = True

    def _on_params_changed(self, specs):
        """Numbers just changed on the debug panel. Most modules read the dataclass directly on each use, so they need nothing; anything that pushed numbers to the GPU / a buffer at build time
        is pushed again here."""
        paths = {s.path for s in specs}
        if 'look' in paths and self.look:
            self.look.apply_params()
        if 'gun.view_light' in paths:
            self.viewmodel.apply_light()
        if 'gun.flash' in paths and self.look:
            self.look.apply_params()
        if 'lens' in paths and self.lens:
            self.lens.apply_params()
        if any(s.id == 'gun.ads_eye_relief' for s in specs):
            self.sway.ads_target = ads_target_for(self.params.gun)

    def _barrel_direction(self) -> tuple:
        """Bullet direction: follows the gun barrel as it points on screen. `barrel_pose` is from the previous frame (the gun is drawn after firing), so it is off by at most one spring frame, which is not visible."""
        gun, p = self.params.gun, self.player
        if not gun.free_aim.barrel_aim or gun.ads_sights is None:
            return aim_direction(p.yaw, p.pitch)
        return view_to_world(p.yaw, p.pitch, barrel_view_dir(self.viewmodel.barrel_pose, gun.ads_sights, self.viewmodel.current_fov, camera.fov))

    def update(self):
        # fixed order: player (look/move) -> fire + reload (uses the view direction just updated) -> hand animation -> sway -> head + shake (-> lens frame) -> gun -> light, lens
        dt = time.dt
        self.player.tick()
        if self.look:
            self.look.update(dt)
        self.combat.update(min(dt, 0.05), dt)
        if self._draw_pending and dt < 0.1:          # wait for the first normal frame: the long build frame must not count toward the draw time
            self._draw_pending = False
            self.combat.handling.start_draw()
        for event in self.combat.handling.drain():
            self.viewmodel.on_event(event)
            if self.foley:
                self.foley.on_handling_event(event)
            if event[0] == 'done' and event[1] == 'holster' and self._pending_gun:
                self._apply_gun(self._pending_gun)
                break
        self.viewmodel.animate(dt, self.combat.weapon.mag == 0, self.player.ads_amount)
        step = min(dt, 0.05)
        inp = self.player.sway_input()
        sway_pose = self.sway.update(step, inp)
        if self.foley:
            self.foley.update(dt, self.sway.phase)       # after sway: footsteps play exactly when the gun reaches the lowest point of the bob
        frame = (0.0, 0.0, 0.0)
        if self.shake_view:
            p = self.player
            cy, sy = math.cos(math.radians(p.yaw)), math.sin(math.radians(p.yaw))
            rs = reload_state(self.combat.handling)
            gaze = self.viewmodel.gaze_angles(self.params.gun.head.gaze_hand_weight) if rs is not None else None
            # after combat (this frame's Handling.t) and after sway (footstep phase): reload gaze + bob / jump / landing
            self.head.update(step, inp, self.sway.phase, p.vx * cy - p.vz * sy, p.vx * sy + p.vz * cy, rs, gaze)
            if self.lens:
                frame = self.shake_view.frame_offset(p.ads_amount, camera.fov, window.aspect_ratio, self.lens.current_fisheye(p.ads_amount))
        self.viewmodel.update(self.combat.gun_kick.pose, sway_pose, self.combat.free_aim.pose(self.player.ads_amount), self.player.free_look.pose())
        cam_pos, forward = camera.world_position, camera.forward
        self.light.set_camera(cam_pos, camera.right, camera.up, forward)
        self.light.set_exposure(target_exposure(self.params.lens, self.params.look))
        if self.smoke:
            self.smoke.update(min(dt, 0.1))                 # after set_camera: the puffs face this frame's camera
        if self.lens:
            self.lens.update(dt, self.player.ads_amount, inp.look[0], frame)
        if self.hud:
            self.hud.update(dt, self.combat)
        if self.debug.is_open:
            self.debug.update(dt)
        self._age += time.dt
        if self.quit_after and self._age >= self.quit_after:
            application.quit()

    def input(self, key):
        if key == 'f1':
            self.debug.toggle()
        elif self.debug.is_open:                  # debug panel open: the mouse belongs to the panel: no firing / reloading / mode change
            if key == 'escape':
                self.debug.hide()
            else:
                self.debug.on_input(key)
        elif key == 'escape':
            mouse.locked = not mouse.locked
        elif key == 'left mouse down':
            self.combat.pressed = True
        elif key == 'b':
            self.combat.weapon.toggle_mode()
        elif key == 'r':
            self.combat.request_reload()
        elif key == '1':
            self.request_gun('m4')
        elif key == '2':
            self.request_gun('glock')


def desktop_size() -> tuple:
    """Real resolution of the primary monitor."""
    from screeninfo import get_monitors
    monitors = get_monitors()
    primary = next((m for m in monitors if m.is_primary), monitors[0])
    return primary.width, primary.height


def create_game(vsync: bool = True, size=(1280, 720), fullscreen: bool = False, quit_after: float = 0.0,
                sound: bool = True, draw: bool = True, effects: bool = True, look: bool = True, shake: bool = True,
                user_params: bool = False, hud: bool = False, lens: bool = True, free_aim: bool = True,
                borderless: bool = False, gun: str = 'm4') -> Game:
    # Ursina(vsync=False) alone does not turn vsync off; the Panda config must be set directly
    loadPrcFileData('', f'sync-video {int(vsync)}')
    # Panda cleans its state cache with a job every frame (~0.5 ms here); when off, states are freed by reference counting instead
    loadPrcFileData('', 'garbage-collect-states 0')
    icon = Path(ursina.__file__).parent / 'textures' / 'ursina.ico'   # absolute path; otherwise Ursina looks in the game folder
    app = Ursina(title='FPS prototype', icon=Filename.from_os_specific(str(icon)), vsync=vsync, borderless=borderless, fullscreen=fullscreen, size=size,
                 development_mode=False)
    application.asset_folder = ROOT
    window.fps_counter.enabled = False
    setup_fonts()
    # a copy of the gun: the debug panel writes straight into the gun data, so the shared GunData must not be dirtied (tests, measuring tools)
    game = Game(GameParams(gun=copy.deepcopy(GUNS[gun])), quit_after, sound, draw, effects, look, shake=shake,
                user_params=user_params, hud=hud, lens=lens, free_aim=free_aim, gun_name=gun)
    game.app = app
    prune_scene_entities()
    # dry-run renders at build time: compiling shaders (lens, gun) and uploading normal maps to the GPU do not land in the game's first frame. Without it the first frame takes ~1 s and the 1 s draw clip is skipped entirely
    game.viewmodel.prewarm()
    return game


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--novsync', action='store_true')
    ap.add_argument('--window', action='store_true', help='chạy trong cửa sổ thường (mặc định: lấp đầy màn hình)')
    ap.add_argument('--size', default='1280x720', help='cỡ cửa sổ khi dùng --window')
    ap.add_argument('--quit-after', type=float, default=0.0)
    ap.add_argument('--mute', action='store_true', help='tắt tiếng súng')
    ap.add_argument('--gun', default='m4', choices=sorted(GUNS), help='súng dùng khi khởi động (m4 / glock)')
    ap.add_argument('--defaults', action='store_true', help='bỏ qua user_params.json, chạy bằng thông số mặc định')
    args = ap.parse_args(argv)
    # default: a borderless window covering the whole screen. Exclusive fullscreen with vsync drops straight to 30 FPS whenever one frame is late; this does not
    size = tuple(int(v) for v in args.size.lower().split('x')) if args.window else desktop_size()
    game = create_game(vsync=not args.novsync, size=size, borderless=not args.window,
                       quit_after=args.quit_after, sound=not args.mute, user_params=not args.defaults, gun=args.gun)
    game.app.run()


if __name__ == '__main__':
    main()
