"""Build and run the game: `Game` gathers the parts; `create_game()` is shared by main.py and the test tools."""
import argparse
import copy
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # project root (contains assets/)

from fps.game import gltf_patch  # noqa: E402  (must load before Ursina)

gltf_patch.apply()

import ursina  # noqa: E402
from panda3d.core import Filename, loadPrcFileData  # noqa: E402
from ursina import Entity, Ursina, application, camera, held_keys, mouse, scene, time, window  # noqa: E402

from fps.core.exposure import sun_vector, target_exposure  # noqa: E402
from fps.core.focus import FocusGuard  # noqa: E402
from fps.core.freeaim import barrel_view_dir, view_to_world  # noqa: E402
from fps.core.memplan import plan as memory_plan  # noqa: E402
from fps.core.headcam import HeadCam, reload_state  # noqa: E402
from fps.core.movement import aim_direction  # noqa: E402
from fps.core.params import ParamStore  # noqa: E402
from fps.core.shake import Shake  # noqa: E402
from fps.core.weaponcol import WallReady, probe_distance, reach_of  # noqa: E402
from fps.game.camera_shake import ShakeView  # noqa: E402
from fps.game.combat import Combat  # noqa: E402
from fps.game.debug_panel import DebugPanel  # noqa: E402
from fps.game.effects import Effects  # noqa: E402
from fps.game.foley import Foley  # noqa: E402
from fps.game.frame_light import FrameLight  # noqa: E402
from fps.game.gun_audio import GunAudio  # noqa: E402
from fps.game.hud import Hud, Notice, setup_fonts  # noqa: E402
from fps.game.boot import BootScreen  # noqa: E402
from fps.game.ui_audio import UiAudio  # noqa: E402
from fps.core.graphics import GraphicsSettings, clamp_level, from_json, preset_of, resolve, settings_for, to_json  # noqa: E402
from fps.game.graphics_panel import GraphicsPanel  # noqa: E402
from fps.core.safeio import write_text_atomic_background  # noqa: E402
from fps.core.screen import FALLBACK as FALLBACK_SIZE, parse_size, primary_size  # noqa: E402
from fps.game.lens import Lens  # noqa: E402
from fps.game.look import WorldLook  # noqa: E402
from fps.game.player import Player  # noqa: E402
from fps.game.shaders import load_glsl  # noqa: E402
from fps.game.smoke import GunSmoke  # noqa: E402
from fps.game import sysmem  # noqa: E402
from fps.game.splash import WaterSplash  # noqa: E402
from fps.core.splash import Wake  # noqa: E402
from fps.core.footprints import FootprintTrail  # noqa: E402
from fps.game.dust import DustMotes  # noqa: E402
from fps.game.ground import WALK_BOUNDS, build_ground  # noqa: E402
from fps.game.pool import PoolHall  # noqa: E402
from fps.game.backrooms import NOTICE_GLYPHS, Level  # noqa: E402
from fps.core.level import WON  # noqa: E402
from fps.game.underwater import Underwater, UnderwaterAudio  # noqa: E402
from fps.core.sway import Sway, ads_target_for  # noqa: E402
from fps.game.viewmodel import Viewmodel  # noqa: E402
from fps.weapon_data import GUNS, M4, GameParams, GraphicsData  # noqa: E402

USER_PARAMS = ROOT / 'user_params.json'      # user parameters saved from the debug panel (F1); gitignored
USER_GRAPHICS = ROOT / 'user_graphics.json'  # graphics settings saved by the F2 panel; gitignored
CRASH_LOG = ROOT / 'logs' / 'crash.log'      # Python stack of a native crash + the memory the run started with (fps/game/sysmem.py); gitignored
# Panda STREAMS a sound file bigger than this (audio-preload-threshold, default 1 MB): the main thread refills a 3 s queue every frame, so a long main-thread stall starves it.
# The looping room tone (2 MB) is the biggest sound; kept in memory it loops inside OpenAL and no stall of the game can interrupt it (tests/test_memplan.py checks the sizes).
AUDIO_PRELOAD_BYTES = 16_000_000
# G19: the check / measuring tools build the game WITHOUT a window by default (an offscreen buffer: everything runs and draws, screenshots work, nothing pops up
# or grabs the mouse while the user works). `--show` on a tool's command line brings the window back; it is taken out of sys.argv here, before the tool parses
# its own arguments. Tools that need a real window (true FPS, Alt+Tab / minimise checks) pass hidden=False; main.py (the game) always shows it.
SHOW_WINDOW = '--show' in sys.argv
if SHOW_WINDOW:
    sys.argv = [a for a in sys.argv if a != '--show']
STARTUP_WATCHDOG_S = 150.0                   # a start-up slower than this is written to the crash log with the place it is stuck at (a normal one takes 2-3 s; a light bake ~60 s)


def prune_scene_entities():
    """Remove from `scene.entities` every entity with no `update` / `input` (it is still drawn normally).

    Each Ursina frame walks this whole list in Python (checks parent, checks enabled...), and entities using the default shader also call `set_shader_input` to push the camera position;
    measured at 3-5 ms per frame, and changing shader inputs also makes Panda regroup the draw state. The ground slab needs none of that."""
    def keep(e):
        return callable(getattr(e, 'update', None)) or callable(getattr(e, 'input', None)) or getattr(e, 'scripts', None)
    scene.entities = [e for e in scene.entities if keep(e)]


class GunKit:
    """Everything built per gun: its data, viewmodel (glb + skeleton + shaders), effects, shot sound and Foley. Game keeps one per gun and parks the ones not in hand,
    so a weapon switch rebuilds nothing (rebuilding froze the game 0.5-1.7 s per switch: Python skeleton build in gltf_patch, normal-map decoding, sounds)."""
    __slots__ = ('gun', 'viewmodel', 'fx', 'audio', 'foley')

    def __init__(self, gun, viewmodel, fx, audio, foley):
        self.gun, self.viewmodel, self.fx, self.audio, self.foley = gun, viewmodel, fx, audio, foley


class Game(Entity):
    """Gathers the parts and runs the per-frame loop."""

    def __init__(self, params: GameParams, quit_after: float = 0.0, sound: bool = True, draw: bool = True,
                 effects: bool = True, look: bool = True, shake: bool = True,
                 user_params: bool = False, hud: bool = False, lens: bool = True, free_aim: bool = True, gun_name: str = 'm4',
                 map_name: str = 'pool', rebake: bool = False, low_memory: bool = False, boot=None, ui_audio=None):
        super().__init__()
        self.boot = boot                              # G20: the boot splash (game/boot.py) while it holds the game; None = no splash (tools, --no-splash)
        self._boot_handed = False                     # the hand-over from the splash to the game happened (ambience started)
        self.ui_audio = ui_audio if ui_audio is not None else UiAudio(ROOT, enabled=sound)      # G20: sounds of the splash and the graphics panel
        self.params = params
        self.low_memory = low_memory                  # the machine is short of virtual memory (fps/core/memplan.py): no MSAA, the second gun is built on the first switch
        self._aa_cap = 0 if low_memory else None      # MSAA samples allowed while the user has not touched the anti-aliasing row himself (None = no cap)
        self.map_name = map_name                      # 'pool' = the pool hall (G9); 'flat' = the old white slab (kept to compare FPS); 'backrooms' = the 5-floor level (G18)
        look = look or map_name in ('pool', 'backrooms')     # the pool hall is drawn by shaders that WorldLook feeds
        self.root = ROOT
        self.level = None                             # G18: the Backrooms level (fps/game/backrooms.py)
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
        self.params_store = ParamStore(params, gun_key=gun_name)       # gun sliders belong to the gun in hand (per-gun defaults, 8/11/2026)
        self.params_report = self.params_store.load(USER_PARAMS) if user_params and USER_PARAMS.exists() else None
        if self.params_report is not None:
            print(f'[thông số] {USER_PARAMS.name}: {self.params_report.message}')
        self.quit_after = quit_after
        self._age = 0.0
        self._draw_pending = draw         # draw the gun on the first frame (not during build: loading the model makes the first frame very long)
        self.pool = None
        self.shake = None                             # (built below; the Backrooms level reads it when a strike lands)
        self._stage('LOAD ENVIRONMENT MAP', 0.10)
        if map_name in ('pool', 'backrooms'):
            # G19: one run: the pool hall (stage 0, the default map) -> its north-bank stairs -> the Backrooms floors; --map backrooms starts at floor 1
            self.level = Level(self, sound=sound, rebake=rebake, start=0 if map_name == 'pool' else 1)
            self.pool = self.level.hall
            self.world = self.pool.world
            self._stage('INIT PLAYER / PHYSICS', 0.40)
            sx, sy, sz, syaw = self.level.start_pose()
            self.player = Player(params.player, WALK_BOUNDS, params.gun, self.level.current.terrain, (sx, sy, sz))
            self.player.yaw = syaw
            self.player._apply_view()
        else:
            self.world = build_ground(params.look.ground_color)
            self.player = Player(params.player, WALK_BOUNDS, params.gun)
        self._sun_share = 1.0                         # smoothed share of the sun reaching the player (lights the gun); 1 on the open slab
        self._stage('INIT AUDIO SUBSYSTEM', 0.45)
        self.audio = GunAudio(params.gun, ROOT) if sound and params.gun.shot_sound else None
        self.foley = Foley(params.audio, params.gun, self.player, ROOT) if sound else None    # reload, footsteps (off with the sound flag / --mute)
        if not free_aim:
            params.gun.free_aim.barrel_aim = False
        self.light = FrameLight(params.look, params.gun)                       # one shared light source for the world and the gun
        self.wake = Wake()                                                     # G10: the walking body pushes the water
        self.trail = FootprintTrail()                                          # G10: wet footprints after leaving the pool
        self._feet = (self.player.x, self.player.z)
        self.dust = DustMotes(params.look, self.light, self.pool) if self.pool and effects else None    # G10: dust glinting in the sun beams
        self.ambience = None                                                   # G10: looping room tone of the pool hall (only once the user approved the file)
        if self.pool and sound:
            amb = ROOT / params.audio.ambience_file
            if amb.exists():
                self.ambience = application.base.loader.load_sfx(Filename.from_os_specific(str(amb)))
                self.ambience.set_loop(True)
                self.ambience.set_volume(params.audio.ambience_volume)
                if self.boot is None:                 # G20: with the splash up the room tone starts when the game does (`_start_ambience`)
                    self.ambience.play()
        if self.pool:
            x0, x1, z0, z1, wy = self.pool.pm.water
            self.player.water = (x0, x1, z0, z1, wy, self.pool.data.wade_depth)
            self.player.splash = params.splash
            if effects:
                self.pool.attach_splash(WaterSplash(params.splash, self.light, wy))
        self._stage('LOAD WEAPON SYSTEMS', 0.58)
        self.viewmodel = Viewmodel(params.gun, ROOT, self.light)
        if draw:
            self.viewmodel.hide_until_draw()          # the first frames (window opening, shader warm-up) show no gun; it appears with the draw clip
        self.smoke = GunSmoke(params.look, self.light) if effects else None        # gunpowder smoke: one world-space pool shared by both guns
        self.fx = Effects(params.gun, self.viewmodel, smoke=self.smoke) if effects else None
        self.shake = Shake(params.gun.shake) if shake else None                # purely visual shake (does not change bullet direction)
        self.head = HeadCam(params.gun.head) if shake else None               # head + body motion on the image: uses the `shake` flag because it is also purely visual camera motion
        self.shake_view = ShakeView(self.shake, self.head, params.lens) if shake else None      # all of it moves the LENS FRAME, not the world camera
        self.combat = Combat(params, self.player, self.world['colliders'], audio=self.audio, fx=self.fx, shake=self.shake)
        self.combat.aim_source = self._barrel_direction
        self.combat.targets = self.level                                       # G18: bullets hit the enemy capsules (None elsewhere)
        self._shots_heard = 0                                                  # G18: shots already reported to the swarm (hearing)
        self.wall_ready = WallReady(params.gun.wall)                           # G14 High Ready: the gun rises when a wall is close, firing / aiming locked meanwhile
        self._wall_reach = reach_of(params.gun)
        self._wall_solids = self.combat.box_index             # G18: the probe asks the grid for the boxes near the eye
        self.combat.foley = self.foley
        self.combat.viewmodel = self.viewmodel
        self.look = WorldLook(params.look, self.world, self.combat.decals, self.light) if look else None
        if self.pool:
            self.combat.decals.bind_room(self.pool.lightmap, self.pool.e_max, self.pool.lightmap_at)     # a bullet hole takes the baked light of the wall it sits on
            self.pool.prepare_reflection(self.light, force=rebake)       # needs the shader inputs WorldLook just put on render; before the lens takes over the screen
            self.pool.bind_reflection(self.viewmodel.root)               # the gun's metal mirrors the same captured room (G10)
        # graphics settings (F2 panel): the user's file if there is one (and user params are wanted), else the default level
        self.gfx = settings_for(params.graphics.level)
        if user_params and USER_GRAPHICS.exists():
            try:
                self.gfx = from_json(USER_GRAPHICS.read_text(encoding='utf-8-sig'))     # -sig: a file re-saved by Notepad starts with a BOM
            except (OSError, ValueError) as e:
                print(f'[đồ hoạ] không đọc được {USER_GRAPHICS.name}: {e}')
        self.underwater = Underwater(params.underwater, params.water, self.pool, self.light) if self.pool else None   # G12: the camera at / under the surface
        self._dust_under = False                                              # dust motes hidden because the eye is under the water
        self.under_audio = UnderwaterAudio(params.audio, ROOT, self.ambience) if self.underwater and sound else None
        self._stage('INIT RENDER PIPELINE', 0.72)
        self.lens = Lens(params.lens, self.viewmodel, samples=self._capped_aa(self.gfx.aa), light=self.light, scale=resolve(self.gfx).render_scale) if lens else None
        self.sway = Sway(params.gun.sway, ads_target_for(params.gun))
        self.hud = Hud(params.gun.credit) if hud else None                    # Bodycam style: nothing on screen; only the selftest turns it on to read numbers
        self.debug = DebugPanel(self, self.params_store, USER_PARAMS)         # F1 panel: built lazily the first time it opens; costs nothing while closed
        self.params_store.subscribe(self._on_params_changed)
        self._kits = {gun_name: GunKit(params.gun, self.viewmodel, self.fx, self.audio, self.foley)}     # gun key -> GunKit; `preload_guns` adds the others
        self.notice = Notice(warm=NOTICE_GLYPHS if self.level else '')        # a short line top-centre (e.g. the settings saved; G18 floor / win / death lines)
        self.notice_low = Notice((0.0, -0.40), 0.85, params.underwater.no_fire_text + (' Còn 0123456789' if self.level else ''))   # G12: a small line at the bottom ("Không thể bắn ở đây")
        self.combat.on_blocked = self._on_blocked
        self.graphics_level = None
        self.gfx_panel = GraphicsPanel(self)                                  # F2: graphics options, built the first time it opens
        self.focus = FocusGuard()                                             # G16: Alt+Tab / minimise -> free the mouse, let go of keys, mute
        if self.level is not None:
            self.level.current.view.update(self.level.current.swarm, self.pool.local_ambient)     # the capsules exist before the shader warm-up draws a frame
            if self.level.floor_title():
                self.notice.show(self.level.floor_title(), 3.5)
        self._muted = None                                                    # [(AudioManager, volume before)] while the window is in the background
        self.apply_graphics(self.gfx)

    def _stage(self, label: str, progress: float = None):
        """G20: announce a real load step to the boot splash (it draws one frame); nothing without a splash."""
        if self.boot is not None:
            self.boot.stage(label, progress)

    def _start_ambience(self):
        if self.ambience is not None:
            self.ambience.play()

    # --- graphics (G10): the graphics panel (Esc, G20) edits `self.gfx`; switching changes uniforms and buffers only (no shader recompiles); anti-aliasing rebuilds the lens buffer ---
    def apply_graphics(self, s: GraphicsSettings, announce: bool = False):
        if self._aa_cap is not None and s.aa != self.gfx.aa:      # the user chose an anti-aliasing level himself: that wins over the low-memory cap
            self._aa_cap = None
        self.gfx = s
        g = resolve(s)
        p = preset_of(s)
        self.graphics_level = p if p is not None else -1                     # preset index, -1 = custom (tools read it)
        if self.pool:
            self.pool.set_level(g)
        for kit in self._kits.values():
            kit.viewmodel.set_env(g.gun_env and self.pool is not None)
        if self.dust:
            self.dust.set_enabled(g.dust and not self._dust_under)
        if self.smoke:
            self.smoke.set_simple(g.smoke_simple)
        if self.underwater:
            self.underwater.set_level(g)
        self.combat.decals.set_level(g.surface)                   # surface detail: bullet holes (and the tiles of the pool hall)
        self._set_lens(self._capped_aa(s.aa), g.render_scale)     # G13: 3D resolution (75% on Thấp)
        window.fps_counter.enabled = s.show_fps
        if announce:
            self.notice.show(f'Đồ hoạ: {g.name}')

    def set_graphics(self, i: int, announce: bool = True):
        """Apply preset `i` (0 Thấp / 1 Vừa / 2 Cao), keeping anti-aliasing and the FPS counter (tools use this)."""
        self.apply_graphics(settings_for(clamp_level(i), keep=self.gfx), announce)

    def _capped_aa(self, samples: int) -> int:
        return samples if self._aa_cap is None else min(samples, self._aa_cap)

    def _set_lens(self, samples: int, scale: float):
        """Rebuild the lens buffers with `samples` MSAA samples (0 = off) at `scale` x the window (G13). The guns' drawing regions move to the new scene buffer
        (a parked gun stays switched off). A few ms, only when one of the two changes."""
        if self.lens is None or (self.lens.samples == samples and self.lens.scale == scale):
            return
        win = application.base.win
        vms = [k.viewmodel for k in self._kits.values()]
        for vm in vms:
            vm.move_to_output(win)
        data = self.lens.d
        self.lens.destroy()
        self.lens = Lens(data, None, samples=samples, light=self.light, scale=scale)
        for vm in vms:
            vm.move_to_output(self.lens.scene_buffer)

    def warm_shader_builds(self):
        """G13: draw one frame with every alternative build (lite / view / dry lens / blit) in place, then put back the builds in use. The driver compiles a
        shader at its first draw; without this, the first dip under the water or the first split frame stalled 50-150 ms. The pictures of these frames are
        the same as the normal ones (the builds differ only in code that is not taken), and the gun is still hidden (its draw clip has not started)."""
        engine = application.base.graphicsEngine
        slots = []                                       # (node, [builds], priority, build in use)
        if self.pool:
            w = self.pool.water
            slots.append((w.node, list(w.shaders.values()), 1, w.shaders[w._build]))
            slots.append((self.pool.node, list(self.pool.room_shaders.values()), 1, self.pool.room_shaders[self.pool.room_lite]))
        if self.underwater:
            u = self.underwater
            slots.append((u.basin, list(u.basin_shaders.values()), 2, u.basin_shaders[u.basin_lite]))
            u.basin.show()
        if self.smoke:
            sm = self.smoke
            slots.append((sm.root, list(sm.shaders.values()), 2, sm.shaders[sm.simple]))
        if self.lens:
            ln = self.lens
            if ln.quad is ln.window_quad:                 # 100%: the blit (used below 100%) is warmed on the window quad too, reading the scene texture
                ln.window_quad.set_shader_input('blit_src', ln.scene)
                slots.append((ln.quad, list(ln.shaders.values()) + [load_glsl('blit')], 0, ln.shaders[ln.dry]))
            else:
                slots.append((ln.quad, list(ln.shaders.values()), 0, ln.shaders[ln.dry]))
        rounds = max((len(s[1]) for s in slots), default=0)
        try:
            for i in range(rounds):
                for node, builds, prio, _ in slots:
                    node.set_shader(builds[min(i, len(builds) - 1)], prio)
                engine.render_frame()
        finally:
            for node, _, prio, used in slots:
                node.set_shader(used, prio)
        self.combat.decals.warm(engine, camera.world_position, camera.forward)       # the bullet-hole shader: drawn once (invisible hole), or the first shot stalls

    def save_graphics(self):
        # G16: atomic (a crash mid-save keeps the old file whole) and off the frame (the temp file + rename took 30-70 ms on this drive: a hitch on closing F2)
        self.graphics_save = write_text_atomic_background(USER_GRAPHICS, to_json(self.gfx), on_error=lambda e: print(f'[đồ hoạ] không lưu được {USER_GRAPHICS.name}: {e}'))

    # --- weapon switch (keys 1 / 2): holster clip of the gun in hand -> rebuild the gun-dependent parts -> draw clip of the new gun ---
    def request_gun(self, name: str):
        h = self.combat.handling
        # `_draw_pending`: the gun in hand has not been drawn yet (game start / a gun built during the switch): putting it away now would holster a gun never shown
        if name == self.gun_name or name not in GUNS or self._pending_gun or self._draw_pending or h.busy:
            return
        self._pending_gun = name
        h.start_holster()

    def _merge_audio(self, gun):
        cues, files = self._audio_defaults
        a = self.params.audio
        a.cues = dict(gun.sound_cues) if gun.sound_cues is not None else dict(cues)
        a.sound_files = {**files, **(gun.sound_files or {})}

    def _build_kit(self, name: str) -> GunKit:
        """Build a gun's parts (0.5-1.7 s: glb + skeleton, normal maps, sounds), warm its shaders on the GPU, and park it. Leaves `params.audio` merged for that gun."""
        gun = copy.deepcopy(GUNS[name])
        self.params_store.register_gun(name, gun)       # the panel numbers saved for this gun go in BEFORE its parts read them
        if not self._free_aim:
            gun.free_aim.barrel_aim = False
        self._merge_audio(gun)                          # Foley loads the sound banks its gun's cues name
        vm = Viewmodel(gun, ROOT, self.light)
        vm.hide_until_draw()                            # until its draw clip starts, the gun must not show its idle pose (a switch always draws)
        if self.pool:
            self.pool.bind_reflection(vm.root)
            vm.set_env(resolve(self.gfx).gun_env)
        fx = Effects(gun, vm, smoke=self.smoke) if self._effects else None
        if self.lens:
            vm.move_to_output(self.lens.scene_buffer)
        audio = GunAudio(gun, ROOT) if self._sound and gun.shot_sound else None
        foley = Foley(self.params.audio, gun, self.player, ROOT) if self._sound else None
        vm.prewarm()                                    # compile its shaders and upload its textures now (window sits these frames out), not in the first frames of its draw
        vm.park()
        if fx:
            fx.park()
        kit = self._kits[name] = GunKit(gun, vm, fx, audio, foley)
        return kit

    def preload_guns(self):
        """Build every other gun at start-up (create_game calls it; ~1.7 s for the Glock, 0.5 s for the M4), so no weapon switch ever loads anything."""
        for name in GUNS:
            if name not in self._kits:
                self._build_kit(name)
        self._merge_audio(self.params.gun)              # building merged the audio of the last kit: back to the gun in hand

    def _apply_gun(self, name: str):
        """Swap the gun in hand (the holster clip just finished) and start the new gun's draw clip in the same frame. Rounds are remembered per gun; world, bullets in flight
        and holes stay. Each gun's parts are built once (`preload_guns`) and parked while another gun is in hand, so a switch costs well under a frame."""
        w = self.combat.weapon
        self._ammo[self.gun_name] = (w.mag, w.reserve, w.auto)
        self.viewmodel.park()
        if self.fx:
            self.fx.park()
        kit = self._kits.get(name)
        built_now = kit is None
        if built_now:                                   # not preloaded (a tool that built the game without create_game): one long frame
            kit = self._build_kit(name)
        gun = kit.gun
        self.params.gun = gun
        self.params_store.set_gun(name, gun)            # F1 sliders, defaults and reset now follow this gun
        self._merge_audio(gun)
        self.player.set_gun(gun)
        self.wall_ready.d = gun.wall                   # G14: the raise amount carries over (a gun swap beside a wall keeps it up); the new gun's reach and numbers apply
        self._wall_reach = reach_of(gun)
        self.light.gun = gun
        kit.viewmodel.overscan = self.viewmodel.overscan     # this frame's value (Game.update set it on the old gun already): no one-frame FOV pop
        self.viewmodel, self.fx, self.audio, self.foley = kit.viewmodel, kit.fx, kit.audio, kit.foley
        self.viewmodel.unpark()
        # numbers pushed to the GPU at build / on change (gun light, muzzle flash on the world): a gun loaded from the file while parked was never pushed
        self._on_params_changed([s for s in self.params_store.specs if s.path in ('gun.view_light', 'gun.flash')])
        if self.foley:
            self.foley.resume()
        if self.shake is not None:                      # keep the running shake / head state (rebuilding it would jolt the lens frame mid-switch): only swap the data
            self.shake.d = gun.shake
            self.head.d = self.head.gaze.d = gun.head
        self.combat.set_gun(gun, self.audio, self.fx, self.shake, self.viewmodel, self.foley, self._ammo.get(name))
        self.combat.aim_source = self._barrel_direction
        self.sway.d = gun.sway                          # same for the sway state (lag, bob phase): the new gun comes up where the old one was going
        if hasattr(self.sway.lag, 'd'):
            self.sway.lag.d = gun.sway
        self.sway.ads_target = ads_target_for(gun)
        self.gun_name, self._pending_gun = name, None
        if built_now:
            self._draw_pending = True                   # the build frame was long: the draw waits for the next normal frame so it is not skipped
        else:
            self.combat.handling.start_draw()           # no gap where the new gun is "ready" but not drawn (a click there fired a hidden gun, a key holstered it)

    def _on_handling_event(self, event: tuple):
        self.viewmodel.on_event(event)
        if self.foley:
            self.foley.on_handling_event(event)

    def _on_params_changed(self, specs):
        """Numbers just changed on the debug panel. Most modules read the dataclass directly on each use, so they need nothing; anything that pushed numbers to the GPU / a buffer at build time
        is pushed again here."""
        paths = {s.path for s in specs}
        if 'look' in paths and self.look:
            self.look.apply_params()
        if 'gun.view_light' in paths:
            self.viewmodel.apply_light()
        if 'gun.flash' in paths:
            self.viewmodel.apply_light()
            if self.look:
                self.look.apply_params()
        if ('water' in paths or 'splash' in paths or 'look' in paths) and self.pool:
            self.pool.apply_params()
        if 'look' in paths and self.dust:
            self.dust.apply_params()
        if 'audio' in paths and self.ambience and not (self.under_audio and self.under_audio.tone):
            self.ambience.set_volume(self.params.audio.ambience_volume)      # (with an underwater tone, UnderwaterAudio sets it every frame)
        if 'lens' in paths and self.lens:
            self.lens.apply_params()
        if ('underwater' in paths or 'water' in paths) and self.underwater:
            self.underwater.apply_params()
        if any(s.id == 'gun.ads_eye_relief' for s in specs):
            self.sway.ads_target = ads_target_for(self.params.gun)

    # --- G18 Backrooms: floor swap / restart (the level says when; this rewires everything that holds the old floor) ---
    def _enter_floor(self, old, offset=None):
        """The level's current floor changed (halfway up the stairs: `offset` moves the player to the same spot of the same corridor; restart: None = the start
        pose). Rewires the player, bullets, bullet holes, water extras, underwater, dust and reflections, then frees the old floor."""
        lvl, p, params = self.level, self.player, self.params
        new = lvl.current
        hall = new.hall
        if offset is not None:
            p.x, p.y, p.z = p.x + offset[0], p.y + offset[1], p.z + offset[2]
        else:
            sx, sy, sz, syaw = lvl.start_pose()
            p.x, p.y, p.z = sx, sy, sz
            p.vx = p.vz = p.vy = 0.0
            p.yaw, p.pitch = syaw, 0.0
            p._apply_view()
            p.on_ground = True
        p.terrain = new.terrain
        x0, x1, z0, z1, wy = hall.pm.water
        p.water = (x0, x1, z0, z1, wy, hall.data.wade_depth)
        self._feet = (p.x, p.z)
        self.wake, self.trail = Wake(), FootprintTrail()
        self.pool, self.world = hall, hall.world
        c = self.combat
        c.set_static_boxes(hall.world['colliders'])
        c.dynamic_boxes, c.bullets = [], []
        c.decals.clear()
        c.decals.bind_room(hall.lightmap, hall.e_max, hall.lightmap_at)
        self._wall_solids = c.box_index
        if self.look:
            self.look.world = self.world
        if self._effects:
            hall.attach_splash(WaterSplash(params.splash, self.light, wy))
        old.hall.node.hide()                                 # the reflection capture (first visit of a floor) must see only the new floor
        old.hall.water.node.hide()
        old.door_view_hide(True)
        hall.prepare_reflection(self.light)
        for kit in self._kits.values():
            hall.bind_reflection(kit.viewmodel.root)
        if self.underwater:
            self.underwater = Underwater(params.underwater, params.water, hall, self.light)
        if self.dust:
            self.dust.root.remove_node()
            self.dust = DustMotes(params.look, self.light, hall)
        old.destroy()
        self.apply_graphics(self.gfx)
        self._refill_ammo()
        new.view.update(new.swarm, hall.local_ambient)
        if self.look is not None and new.k >= 1:
            self.look.sky.entity.hide()                       # the sky quads stand behind the pool hall's windows: nothing to see through on a floor
        self.notice.show(lvl.floor_title(), 3.5)

    def _refill_ammo(self):
        """G18: every floor starts with full magazines and reserves (all guns)."""
        w, g = self.combat.weapon, self.params.gun
        w.mag, w.reserve = g.magazine, g.reserve
        self._ammo = {}

    def _restart_level(self):
        old = self.level.restart()
        self.player.frozen, self.player.slump = False, 0.0
        self._enter_floor(old, None)

    def _on_blocked(self, reason: str = 'water'):
        """The trigger was pulled where it cannot fire: a small line at the bottom of the screen."""
        if reason == 'wall':
            w = self.params.gun.wall
            self.notice_low.show(w.blocked_text, w.blocked_time)
        else:
            u = self.params.underwater
            self.notice_low.show(u.no_fire_text, u.no_fire_time)

    def _update_wall(self, dt: float):
        """G14, after the player moved: probe the walls ahead of the eye, raise / lower the gun (High Ready), lock the trigger and the aim button meanwhile."""
        p, w = self.player, self.params.gun.wall
        reach = self._wall_reach
        eye = p.aim_ray()[0]
        dist = probe_distance(eye, p.yaw, p.pitch, self._wall_solids, reach * w.clear_ratio + 0.05, w.side_angle)
        self.wall_ready.update(min(dt, 0.05), dist, reach)
        p.wall_amount = self.wall_ready.amount
        p.wall_blocked = self.combat.wall_blocked = self.wall_ready.blocked

    def _water_feet(self):
        """G10, after the player moved: a landing in the water splashes, walking in it pushes waves (and kicks up a few drops)."""
        p, water, splash, s = self.player, self.pool.water, self.pool.splash, self.params.splash
        dx, dz = p.x - self._feet[0], p.z - self._feet[1]
        moved = math.hypot(dx, dz)
        self._feet = (p.x, p.z)
        if moved > 3.0:                                   # a teleport (tools), not a walk
            moved = dx = dz = 0.0
        depth = p.water_depth
        on_deck = p.on_ground and abs(p.y) < 0.01 and depth <= 0.0
        if self.trail.update(self.pool._clock, p.x, p.z, dx, dz, depth > 0.05, on_deck, s.feet_dry, s.print_spacing):
            slot = (self.trail.next - 1) % self.trail.slots
            self.pool.add_print(slot, self.trail.prints[slot])
        self.trail.dry(time.dt, s.feet_dry)
        if p.landed > 0.0 and depth > 0.0:
            k = min(p.landed / 4.0, 1.5)
            water.push(p.x, p.z, s.land_radius, s.land_push * k)
            if splash:
                splash.land(p.x, p.z, k)
        for x, z, radius, amount in self.wake.update(p.x, p.z, moved, depth if p.on_ground else 0.0, p.speed, s.wake_spacing, s.wake_push, s.wake_radius, p.water[5]):
            water.push(x, z, radius, amount)
            if splash and p.speed > 0.5:
                splash.wade(x, z, p.sprinting)

    def _update_focus(self, dt: float):
        """G16 (D1), first thing in the frame: the window went to the background -> mouse freed, every held key let go (a key released while another
        window had focus never reaches the game: W stayed held and he walked on), sound off. Back in front -> sound on, the mouse captured again only
        if it was, and the activating click does not fire (core/focus.py)."""
        win = application.base.win
        if win is None:
            return
        if not hasattr(win, 'get_properties'):              # G19: an offscreen buffer (hidden checks) has no focus to lose
            return
        props = win.get_properties()
        event = self.focus.update(dt, props.get_foreground() and not props.get_minimized(), mouse.locked)
        if event == 'lost':
            mouse.locked = False
            self._release_inputs()
            self._mute(True)
        elif event == 'gained':
            self._release_inputs()
            self._mute(False)
            if self.focus.take_lock_before() and not (self.debug.is_open or self.gfx_panel.is_open):
                mouse.locked = True                      # Ursina zeroes the mouse movement of the frame the lock comes back: no view jump
        if self.focus.guarding:
            held_keys['left mouse'] = held_keys['right mouse'] = 0
            self.combat.pressed = False

    def _release_inputs(self):
        for k in list(held_keys.keys()):
            held_keys[k] = 0
        self.combat.pressed = False

    def _mute(self, on: bool):
        base = application.base
        managers = [m for m in list(getattr(base, 'sfxManagerList', None) or []) + [getattr(base, 'musicManager', None)] if m is not None]
        if on and self._muted is None:
            self._muted = [(m, m.get_volume()) for m in managers]
            for m in managers:
                m.set_volume(0.0)
        elif not on and self._muted is not None:
            for m, v in self._muted:
                m.set_volume(v)
            self._muted = None

    def _barrel_direction(self) -> tuple:
        """Bullet direction: follows the gun barrel as it points on screen. `barrel_pose` is from the previous frame (the gun is drawn after firing), so it is off by at most one spring frame, which is not visible."""
        gun, p = self.params.gun, self.player
        if not gun.free_aim.barrel_aim or gun.ads_sights is None:
            return aim_direction(p.yaw, p.pitch)
        vm = self.viewmodel
        return view_to_world(p.yaw, p.pitch, barrel_view_dir(vm.base_pose, gun.ads_sights, vm.current_fov, camera.fov, then=vm.aim_pose))

    def update(self):
        over = max(self.params.lens.overscan, 0.0) if self.lens else 0.0      # world and gun are drawn this much wider; the lens crops the middle (no black band when the frame swims)
        self.player.overscan = self.viewmodel.overscan = over
        # fixed order: player (look/move) -> wall probe (High Ready, G14) -> fire + reload (uses the view direction just updated) -> hand animation -> sway -> head + shake (-> lens frame) -> gun -> light, lens
        dt = time.dt
        self._update_focus(dt)
        if self.boot is not None:                        # G20: the boot splash holds the game (hold / off), then fades out over the running game (fade)
            state = self.boot.update(dt)
            if state in ('fade', 'gone') and not self._boot_handed:
                self._boot_handed = True
                self._start_ambience()
            if state == 'gone':
                self.boot = None
            elif self.boot.holding:
                self._age += dt
                if self.quit_after and self._age >= self.quit_after:
                    application.quit()
                return
        self.player.tick()
        self._update_wall(dt)
        if self.level is not None:                       # G18: doors, the swarm, health, progress (after the player moved, before the shots of this frame)
            for event in self.level.update(dt):
                if event == 'swap':
                    old, offset = self.level.take_next()
                    self._enter_floor(old, offset)
                elif event == 'restart':
                    self._restart_level()
        if self.pool:
            self._water_feet()
        if self.look:
            self.look.update(dt)
        if self.pool:
            self.pool.update(dt)
        if self.dust:
            self.dust.update(dt)
        if self.underwater:
            self.combat.underwater = self.underwater.eye_under          # last frame's camera (the camera moves after shooting): one frame late at most
        self.combat.update(min(dt, 0.05), dt)
        if self.level is not None and self.combat.shots_fired != self._shots_heard:    # G18: the swarm hears the shots
            self._shots_heard = self.combat.shots_fired
            self.level.on_gunshot(self.player.x, self.player.z)
        if self._draw_pending and dt < 0.1:          # wait for the first normal frame: the long build frame must not count toward the draw time
            self._draw_pending = False
            if not self.combat.handling.start_draw():
                self.viewmodel.reveal()              # the draw could not start (a clip is running): never leave the gun hidden
        for event in self.combat.handling.drain():
            self._on_handling_event(event)
            if event[0] == 'done' and event[1] == 'holster' and self._pending_gun:
                self._apply_gun(self._pending_gun)
                for e in self.combat.handling.drain():       # the new gun's draw 'start': posed this same frame
                    self._on_handling_event(e)
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
                frame = self.shake_view.frame_offset(p.ads_amount, p.view_fov, window.aspect_ratio, self.lens.current_fisheye(p.ads_amount))
        self.viewmodel.update(self.combat.gun_kick.pose, sway_pose, aim=(self.combat.free_aim.pose(self.player.ads_amount), self.player.free_look.pose()))
        cam_pos, forward = camera.world_position, camera.forward
        self.light.set_camera(cam_pos, camera.right, camera.up, forward)
        if self.pool:                                    # the gun is lit by the sun only where the sun reaches the player; fades over ~0.15 s so stepping into a beam does not pop
            target = 0.0 if self.pool.sun_blocked((cam_pos[0], cam_pos[1], cam_pos[2]), sun_vector(self.params.look)) else 1.0
            self._sun_share += (target - self._sun_share) * min(1.0, dt * 6.0)
            up, down = self.pool.local_ambient(cam_pos[0], cam_pos[2])      # the room's baked ambient light at his spot: the gun goes dark where the room is dark
            self.light.set_local_light(self._sun_share, up, down)
        self.light.set_exposure(target_exposure(self.params.lens, self.params.look))
        if self.underwater:
            win = application.base.win
            size = self.lens.buffer_size if self.lens else (win.get_x_size(), win.get_y_size())     # gl_FragCoord counts pixels of the buffer the world is drawn into
            self.underwater.update(dt, cam_pos, camera.right, camera.up, window.aspect_ratio, size, self.player.speed)
            under = self.underwater.all_wet
            if self.dust and under != self._dust_under:
                self._dust_under = under
                self.dust.set_enabled(resolve(self.gfx).dust and not under)
            if self.lens:
                self.lens.set_water(*self.underwater.lens_inputs())
            if self.under_audio:
                self.under_audio.update(dt, self.underwater.eye_under)
            if self.foley:
                self.foley.under = self.underwater.eye_under                 # the foley plays its muffled twins while the head is under
        if self.smoke:
            self.smoke.update(min(dt, 0.1))                 # after set_camera: the puffs face this frame's camera
        if self.lens:
            if self.level is not None:
                self.lens.set_hurt(*self.level.hurt_inputs())
            self.lens.update(dt, self.player.ads_amount, inp.look[0], frame)
        if self.hud:
            self.hud.update(dt, self.combat)
        self.notice.update(dt)
        self.notice_low.update(dt)
        if self.gfx_panel.visible:                       # G20: the graphics panel animates (open / close), reads the pointer, shows the FPS
            self.gfx_panel.update(dt)
        if self.debug.is_open:
            self.debug.update(dt)
        self._age += time.dt
        if self.quit_after and self._age >= self.quit_after:
            application.quit()

    def input(self, key):
        if self.boot is not None and self.boot.holding:     # G20: while the splash runs every key / click only skips its ending
            self.boot.on_input(key)
            return
        if key == 'escape' and not self.debug.is_open:      # G20: Esc opens / closes the graphics panel (it frees / captures the mouse itself; F1's own Esc closes F1)
            self.gfx_panel.toggle()
        elif self.gfx_panel.is_open:              # graphics panel open: keys and the mouse belong to it
            self.gfx_panel.on_input(key)
        elif key == 'f1':
            self.debug.toggle()
        elif self.debug.is_open:                  # debug panel open: the mouse belongs to the panel: no firing / reloading / mode change
            if key == 'escape':
                self.debug.hide()
            else:
                self.debug.on_input(key)
        elif key == 'enter' and self.level is not None and self.level.state.phase == WON:
            self.notice.show('', 0.01)
            self._restart_level()
        elif key == 'e' and self.level is not None:          # G19: the lift button
            self.level.press_e = True
        elif key == 'left mouse down':
            if not self.focus.guarding:                  # the click that brought the window back to the front is not a shot (G16)
                self.combat.pressed = True
        elif key == 'b':
            self.combat.weapon.toggle_mode()
        elif key == 'r':
            self.combat.request_reload()
        elif key == '1':
            self.request_gun('m4')
        elif key == '2':
            self.request_gun('glock')
        elif key == '3':
            self.request_gun('m1014')


def desktop_size() -> tuple:
    """Real resolution of the primary monitor; 1280x720 if it cannot be read (screeninfo raises on some remote / headless sessions)."""
    try:
        from screeninfo import get_monitors
        monitors = get_monitors()
    except Exception as e:
        print(f'[màn hình] không đọc được độ phân giải ({e}), dùng {FALLBACK_SIZE[0]}x{FALLBACK_SIZE[1]}')
        monitors = []
    return primary_size(monitors)


class _ArgParser(argparse.ArgumentParser):
    """A wrong argument is shown in a message box too: the windowed exe has no console, so argparse's usual stderr line would be invisible."""

    def error(self, message):
        sysmem.show_error('Tham số không hợp lệ', f'{message}\n\n{self.format_usage()}')
        self.exit(2)


def create_game(vsync: bool = True, size=(1280, 720), fullscreen: bool = False, quit_after: float = 0.0,
                sound: bool = True, draw: bool = True, effects: bool = True, look: bool = True, shake: bool = True,
                user_params: bool = False, hud: bool = False, lens: bool = True, free_aim: bool = True,
                borderless: bool = False, gun: str = 'm4', map_name: str = 'pool', rebake: bool = False, low_memory: bool = False,
                frame_cap: float = 0.0, hidden: bool = None, splash: bool = False) -> Game:
    """`hidden`: None = no window unless the tool was started with --show (see SHOW_WINDOW); False = a real window; True = never.
    `splash`: G20 boot splash (game/boot.py) over the build and a fixed ending; only main() turns it on (the tools never see it)."""
    if hidden is None:
        hidden = not SHOW_WINDOW
    # Ursina(vsync=False) alone does not turn vsync off; the Panda config must be set directly
    loadPrcFileData('', f'sync-video {int(vsync)}')
    # Panda cleans its state cache with a job every frame (~0.5 ms here); when off, states are freed by reference counting instead
    loadPrcFileData('', 'garbage-collect-states 0')
    loadPrcFileData('', f'audio-preload-threshold {AUDIO_PRELOAD_BYTES}')       # see AUDIO_PRELOAD_BYTES
    icon = Path(ursina.__file__).parent / 'textures' / 'ursina.ico'   # absolute path; otherwise Ursina looks in the game folder
    if hidden:
        loadPrcFileData('', f'win-size {size[0]} {size[1]}')        # the offscreen buffer takes this size
    app = Ursina(title='FPS prototype', icon=Filename.from_os_specific(str(icon)), vsync=vsync, borderless=borderless, fullscreen=fullscreen, size=size,
                 development_mode=False, window_type='offscreen' if hidden else 'onscreen')
    if frame_cap > 0.0 and not vsync:
        set_frame_cap(frame_cap)
    if hidden:
        _offscreen_mouse()
    api = app.pipe.get_interface_name() if getattr(app, 'pipe', None) is not None else ''
    if api != 'OpenGL':
        # G16: when the OpenGL window does not open (old / missing driver, or the window closed while it was opening), Panda silently falls back to
        # Direct3D 9 or software rendering, where none of the GLSL shaders run: the game went on with a broken picture and no word about it
        raise RuntimeError(f'không mở được cửa sổ OpenGL (Panda chuyển sang "{api or "không có"}"). Cần card đồ hoạ / driver hỗ trợ OpenGL 3.3: '
                           f'cập nhật driver card đồ hoạ rồi mở lại. (Cũng xảy ra nếu cửa sổ bị đóng đúng lúc đang mở.)')
    application.asset_folder = ROOT
    window.fps_counter.enabled = False
    # Ursina's camera.overlay is a full-screen alpha-blended quad (color.clear) kept for fades this game never uses: it blended the whole window
    # every frame for no visible change (G13, measured 1.6-3.3 ms GPU at 1080p on the Iris Xe; tools/measure/g8_perf.py --passes)
    camera.overlay.enabled = False
    # G18: Ursina casts a picking ray into the UI and into the whole scene every frame (hover / click on colliders). Nothing in this game uses it: the F1 / F2 panels hit-test
    # mouse.x / mouse.y themselves. `update_step` is compared with a counter that is never reset, so a huge value skips the picking for good (mouse movement is still read).
    mouse.update_step = 1 << 62
    setup_fonts()
    ui_audio = UiAudio(ROOT, enabled=sound)
    boot = None
    if splash:                                       # G20: the splash is the first thing on screen; the build below reports each real step to it
        boot = BootScreen(ROOT, sound=sound, audio=ui_audio, quiet=hidden)
        boot.stage(f'OPEN DISPLAY  {boot.W}x{boot.H}  {api.upper()}', 0.04)
    # a copy of the gun: the debug panel writes straight into the gun data, so the shared GunData must not be dirtied (tests, measuring tools)
    game = Game(GameParams(gun=copy.deepcopy(GUNS[gun])), quit_after, sound, draw, effects, look, shake=shake,
                user_params=user_params, hud=hud, lens=lens, free_aim=free_aim, gun_name=gun, map_name=map_name, rebake=rebake, low_memory=low_memory,
                boot=boot, ui_audio=ui_audio)
    game.app = app
    prune_scene_entities()
    # dry-run renders at build time: compiling shaders (lens, gun) and uploading normal maps to the GPU do not land in the game's first frame. Without it the first frame takes ~1 s and the 1 s draw clip is skipped entirely
    game._stage('COMPILE SHADERS', 0.80)
    game.viewmodel.prewarm()
    if not low_memory:              # (low memory: built on the first switch instead, `_apply_gun`: one long frame, but 0.12 GB less commit at start-up)
        game._stage('PRELOAD WEAPON KITS', 0.86)
        game.preload_guns()         # the other gun too: a weapon switch then loads nothing (it used to freeze the game 0.5-1.7 s)
    game._stage('WARM SHADER BUILDS', 0.94)
    game.warm_shader_builds()       # G13: every lite / view / dry build drawn once now, not in the middle of play
    game._stage('BUILD INTERFACE', 0.97)
    game.gfx_panel.prebuild()       # G20: ~40 text rows (0.8 s): built now, hidden, so the first Esc does not freeze the game
    if boot is not None:
        boot.load_done()            # the fixed ending starts now; Game.update runs it
    return game


def _offscreen_mouse():
    """G19 hidden checks: Ursina's mouse.locked setter asks the window to confine / hide the cursor, which an offscreen buffer cannot do. Keep only the flag
    (the game reads it to decide whether the mouse belongs to the view)."""
    from ursina.mouse import Mouse

    def _set(self, value):
        self._locked = value
    Mouse.locked = property(lambda self: getattr(self, '_locked', False), _set)
    # the pointer position is read from the window (base.win.get_pointer): keep a stored one instead (0, 0 = the middle; tools may set it)
    from ursina import Vec3
    Mouse.x = property(lambda self: getattr(self, '_off_x', 0.0), lambda self, v: setattr(self, '_off_x', float(v)))
    Mouse.y = property(lambda self: getattr(self, '_off_y', 0.0), lambda self, v: setattr(self, '_off_y', float(v)))
    Mouse.position = property(lambda self: Vec3(self.x, self.y, 0.0), lambda self, v: (setattr(self, '_off_x', float(v[0])), setattr(self, '_off_y', float(v[1]))))


def set_frame_cap(fps: float):
    """G19: cap the frame rate with Panda's clock (it sleeps the rest of each frame). The 'clock-mode' config is read when panda3d is imported, so it is set at run
    time. The Windows timer is raised to 1 ms for the run, otherwise every sleep is rounded up to a 15.6 ms tick (a 120 cap ran at ~64 with jitter)."""
    from panda3d.core import ClockObject
    if sys.platform == 'win32':
        import atexit
        import ctypes
        winmm = ctypes.windll.winmm
        if winmm.timeBeginPeriod(1) == 0:
            atexit.register(winmm.timeEndPeriod, 1)
    clock = ClockObject.get_global_clock()
    clock.set_mode(ClockObject.M_limited)
    clock.set_frame_rate(float(fps))


def _size_arg(text: str) -> tuple:
    try:
        return parse_size(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def main(argv=None):
    ap = _ArgParser()
    ap.add_argument('--novsync', action='store_true', help='không vsync, không giới hạn khung (đo FPS)')
    ap.add_argument('--vsync', action='store_true', help='bật vsync như trước G19 (mặc định: không vsync, giới hạn 120 khung / s: mượt hơn khi đánh nhau)')
    ap.add_argument('--window', action='store_true', help='chạy trong cửa sổ thường (mặc định: lấp đầy màn hình)')
    ap.add_argument('--size', default='1280x720', type=_size_arg, help='cỡ cửa sổ khi dùng --window, ví dụ 1280x720')
    ap.add_argument('--quit-after', type=float, default=0.0)
    ap.add_argument('--mute', action='store_true', help='tắt tiếng súng')
    ap.add_argument('--gun', default='m4', choices=sorted(GUNS), help='súng dùng khi khởi động (m4 / glock / m1014)')
    ap.add_argument('--defaults', action='store_true', help='bỏ qua user_params.json, chạy bằng thông số mặc định')
    ap.add_argument('--map', default='pool', choices=('pool', 'flat', 'backrooms'),
                    help='pool = phòng hồ bơi, cầu thang bờ bắc lên Backrooms (mặc định); backrooms = vào thẳng tầng 1; flat = nền trắng phẳng cũ (để so FPS)')
    ap.add_argument('--no-splash', action='store_true', help='bỏ màn splash mở đầu (G20) và vào thẳng game')
    ap.add_argument('--rebake', action='store_true', help='nướng lại ánh sáng và chụp lại phản chiếu của phòng hồ bơi (thường game tự làm khi cần)')
    ap.add_argument('--low-memory', action='store_true', help='ép chế độ giảm tải (tắt khử răng cưa, nạp súng thứ hai muộn); thường game tự chọn khi máy thiếu bộ nhớ ảo')
    args = ap.parse_args(argv)
    # BEFORE the window exists: how much virtual memory is free decides how much to build (fps/core/memplan.py), and a native crash from now on leaves logs/crash.log
    free_mb, limit_mb = sysmem.free_commit_mb(), sysmem.commit_limit_mb()
    mem = memory_plan(free_mb, force_reduced=args.low_memory)
    sysmem.install_crash_log(CRASH_LOG, sysmem.header_line(sys.argv, free_mb, limit_mb, mem.mode))
    if mem.mode == 'critical':
        sysmem.show_error('Không đủ bộ nhớ để mở game', mem.message)
        sys.exit(1)
    # default: a borderless window covering the whole screen. Exclusive fullscreen with vsync drops straight to 30 FPS whenever one frame is late; this does not
    size = args.size if args.window else desktop_size()
    sysmem.start_watchdog(STARTUP_WATCHDOG_S)
    try:
        cap = 0.0 if (args.vsync or args.novsync) else GraphicsData().frame_cap
        game = create_game(hidden=False, vsync=args.vsync, frame_cap=cap, size=size, borderless=not args.window,
                           quit_after=args.quit_after, sound=not args.mute, user_params=not args.defaults, gun=args.gun, map_name=args.map, rebake=args.rebake, low_memory=mem.low_memory,
                           splash=not args.no_splash)
    except Exception as e:                       # G16 (A3): a missing file, a GPU that cannot make a buffer, a shader that does not compile...
        sysmem.stop_watchdog()
        if _window_closed():                     # the player closed the window while it was loading: the build then fails on the missing window; that is a quit
            print(f'[thoát] cửa sổ bị đóng khi game đang mở ({type(e).__name__})')
            sys.exit(0)
        _fatal('Game không mở được', e)
    sysmem.stop_watchdog()
    if mem.message:
        print(f'[bộ nhớ] {mem.message}')
        if mem.notice:
            game.notice.show(mem.notice, seconds=10.0)
    try:
        game.app.run()                           # an exception in a frame or an input handler comes out of Panda's task loop here
    except Exception as e:
        _fatal('Game gặp lỗi và phải đóng', e)


def _window_closed() -> bool:
    """The main window existed and has been closed (by the player: X / Alt+F4). False when no window was ever made (the error is then a real one)."""
    base = getattr(application, 'base', None)
    if base is None:
        return False
    win = getattr(base, 'win', None)
    if win is None:
        return True
    try:
        return win.is_closed() or not win.get_properties().get_open()
    except Exception:
        return True


def _fatal(title: str, exc: BaseException):
    """Log + message box, then exit 1. The game window is closed first: borderless full-screen it would cover the box, and it holds the mouse."""
    try:
        base = getattr(application, 'base', None)
        if base is not None and base.win is not None:
            base.closeWindow(base.win)
    except Exception:                            # the window may be what broke: the message matters more
        pass
    sysmem.report_exception(title, exc)
    sys.exit(1)


if __name__ == '__main__':
    main()
