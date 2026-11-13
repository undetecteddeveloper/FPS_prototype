"""G20: the boot splash, in the style of a US-military field terminal: green phosphor on black, a classification banner top and bottom, a log whose lines are the REAL load
steps of the game (map, light bake, player, weapons, shaders), then a fixed ending (operator check, real storage / power / time, controls, REC armed).

How it runs: `create_game(splash=True)` builds this right after the window opens. While the game builds (one long Python call) the build announces each step with `stage()`,
which draws a frame (the screen cannot animate between steps: the thread is busy). When the build is done `load_done()` schedules the ending, and `Game.update` calls
`update(dt)` each frame: the typewriter, the sounds, then the CRT switching off and a fade into the game. Any key / click skips the ending (not while loading, and not in the first
0.4 s after: keys pressed during the load arrive in the first frame). The script and the layout are fps/core/termui.py (pure, tested); the look is fps/game/theme.py.

States: hold (the ending runs, the game waits) -> off (the picture collapses to a line) -> fade (the game runs, a black cover fades out) -> gone.
"""
import ctypes
import shutil
import time as pytime
from pathlib import Path

import numpy as np
from panda3d.core import Texture as PandaTexture
from ursina import Entity, Texture, application, camera, color, destroy, window

from fps.core import termui as T
from fps.core.easing import bezier
from fps.game import theme
from fps.game.theme import BLACK, BRIGHT, DIM, INK, PHOSPHOR, RED, AMBER, TermText, rect
from fps.game.ui_audio import UiAudio

ACTIVE = None                         # the screen being shown: the light bake (game/pool.py `_BakeScreen`) reports its progress here
TURN_ON_S = 0.34                      # the picture opens from a line
OFF_S = 0.20                          # ... and collapses to one
FADE_S = 0.70                         # the black cover over the game fades out
MAX_STEP = 0.1                        # s: the most one frame may advance the splash clock
EASE_OUT = (0.20, 0.90, 0.30, 1.00)
EASE_IN = (0.60, 0.00, 0.90, 0.40)
SCAN_ALPHA = 0.20                     # darkness of one scanline
VIGNETTE_MAX = 0.55
BANNER = 'UNCLASSIFIED // TRAINING SIMULATION - NOT A REAL SYSTEM'
KIND_COLOR = {'log': DIM, 'ok': PHOSPHOR, 'head': BRIGHT, 'dim': DIM, 'key': BRIGHT, 'warn': AMBER, 'err': RED, 'blank': PHOSPHOR, 'rec': RED}
CUE_SOUND = {'ok': 'ok', 'blip': 'blip', 'relay': 'relay', 'rec': 'rec_start'}
PROGRESS_BAR_COLS = T.BLOCK_COLS - 12         # 'LOAD [' + bar + '] 100%'


class _Power(ctypes.Structure):
    _fields_ = [('ACLineStatus', ctypes.c_ubyte), ('BatteryFlag', ctypes.c_ubyte), ('BatteryLifePercent', ctypes.c_ubyte), ('SystemStatusFlag', ctypes.c_ubyte),
                ('BatteryLifeTime', ctypes.c_ulong), ('BatteryFullLifeTime', ctypes.c_ulong)]


def gather_facts(root: Path, sound: bool) -> dict:
    """The REAL values the ending prints (local only: nothing leaves the machine): clock, free disk, power source / battery, audio."""
    facts = {'time': pytime.strftime('%Y-%m-%d %H:%M:%S'), 'audio': 'ON' if sound else 'MUTED  (--mute)'}
    try:
        facts['storage'] = f'{shutil.disk_usage(root).free / 1e9:.1f} GB FREE'
    except OSError:
        facts['storage'] = 'UNKNOWN'
    try:
        s = _Power()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
            pct = s.BatteryLifePercent if s.BatteryLifePercent <= 100 else None           # 255 = unknown (a desktop with no battery)
            if s.ACLineStatus == 1:
                facts['power'] = 'AC' + (f'  BATTERY {pct}%' if pct is not None else '')
            elif s.ACLineStatus == 0:
                facts['power'] = 'BATTERY' + (f'  {pct}%' if pct is not None else '')
    except (AttributeError, OSError):
        pass
    facts.setdefault('power', 'NOMINAL')
    return facts


def _overlay_textures():
    """(scanlines, vignette): small RGBA textures made with numpy at start-up."""
    period = 3
    scan = np.zeros((period, 1, 4), dtype=np.uint8)
    scan[period - 1, 0, 3] = int(SCAN_ALPHA * 255)                       # one dark row in every `period`
    n = 128
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot((xx - n / 2 + 0.5) / (n / 2), (yy - n / 2 + 0.5) / (n / 2))
    alpha = np.clip(((r - 0.55) / 0.85) ** 2, 0.0, 1.0) * VIGNETTE_MAX
    vig = np.zeros((n, n, 4), dtype=np.uint8)
    vig[..., 3] = (alpha * 255).astype(np.uint8)
    from PIL import Image
    t_scan, t_vig = Texture(Image.fromarray(scan, 'RGBA')), Texture(Image.fromarray(vig, 'RGBA'))
    t_scan.filtering = None                                              # nearest: a scanline stays one crisp pixel row
    t_scan._texture.set_wrap_v(PandaTexture.WM_repeat)                    # the whole effect is this texture repeating down the screen
    return t_scan, t_vig, period


class BootScreen:
    def __init__(self, root: Path, sound: bool = True, audio: UiAudio = None, quiet: bool = False):
        global ACTIVE
        self.root_dir = Path(root)
        self.sound = sound
        self.audio = audio or UiAudio(self.root_dir, enabled=sound)
        self.quiet = quiet                                  # tools: no turn-on animation loop
        window.update_aspect_ratio()                        # the UI lens only gets its size on Ursina's first frame: before it, text is ~20x too big
        self.W, self.H = theme.window_pixels()
        self.win = (self.W, self.H)
        font = theme.ensure_mono_font()
        self.font = font
        grid = T.make_grid(self.H, em_ratio=theme.em_ratio(font), em_div=42.0)
        self.L = L = T.splash_layout(self.W, self.H, grid)
        self.seq = T.BootSeq(0.0)
        self.t_start = pytime.perf_counter()
        self._loaded_at = None                              # the load time (s) once the build is done; the clock then runs on frame times, not on the wall clock
        self._extra = 0.0
        self.state = 'hold'
        self.t_off = self.t_fade = 0.0
        self._chars = 0
        self._last_bake = 0.0
        self._build(L, font)
        ACTIVE = self
        self.audio.play('boot_degauss')
        self.audio.loop('boot_hum')
        self._turn_on()

    # ------------------------------------------------------------ build
    def _build(self, L: T.SplashLayout, font):
        W, H, win = self.W, self.H, self.win
        ui = camera.ui
        self.cover = rect(ui, T.Rect(0, 0, W, H), win, BLACK, z=theme.Z_COVER)           # opaque black: nothing of the game shows through
        self.root = Entity(parent=ui)                                                     # the picture itself (squashed by the CRT on / off)
        r = self.root
        # reverse-video classification banners, top and bottom
        self.banners = []
        for band in (L.top, L.bottom):
            rect(r, band, win, theme.BAR)
            text = TermText(r, L.grid, win, (W - len(BANNER) * L.grid.cw) // 2, band.y, INK, 0.0, font)
            text.set(BANNER)
            self.banners.append(text)
        # header + the rule under it
        self.header = []
        for i, line in enumerate(T.banner_lines('2026.11.12', 'BWC-07')):
            row = TermText(r, L.grid, win, L.x0, L.head_y + i * L.grid.lh, BRIGHT if i == 0 else DIM, 0.20 if i == 0 else 0.0, font)
            row.set(line)
            self.header.append(row)
        thick = max(1, L.grid.cw // 8)
        rect(r, T.Rect(L.x0, L.head_y + L.head_rows * L.grid.lh + L.grid.lh // 4 - thick // 2, L.block_cols * L.grid.cw, thick), win, color.rgba(0.20, 1.0, 0.20, 0.55))   # in the gap under the header, not through its last row
        # the log
        self.log = [TermText(r, L.grid, win, L.x0, L.row_y(i), PHOSPHOR, 0.0, font) for i in range(L.log_rows)]
        # progress bar, session clock, key hint
        self.bar = TermText(r, L.grid, win, L.x0, L.bar_y, PHOSPHOR, 0.18, font)
        self.clock = TermText(r, L.grid, win, L.x0, L.hint_y, DIM, 0.0, font)
        self.hint = TermText(r, L.grid, win, L.x0 + (T.BLOCK_COLS - len('ANY KEY: CONTINUE')) * L.grid.cw, L.hint_y, BRIGHT, 0.18, font)
        # CRT: scanlines, vignette, a flicker veil, and the bright line of the turn-on
        t_scan, t_vig, period = _overlay_textures()
        self.scan = Entity(parent=ui, model='quad', texture=t_scan, z=theme.Z_FX, scale=(W / H, 1), color=color.white)
        self.scan.texture_scale = (1, H / period)
        self.vig = Entity(parent=ui, model='quad', texture=t_vig, z=theme.Z_FX - 0.01, scale=(W / H, 1), color=color.white)
        self.veil = rect(ui, T.Rect(0, 0, W, H), win, color.rgba(0, 0, 0, 0.0), z=theme.Z_FX - 0.02)
        self.line = rect(ui, T.Rect(0, H // 2 - 1, W, 2), win, color.rgba(0.72, 1.0, 0.72, 0.0), z=theme.Z_FX - 0.03)
        self.root.scale_y = 0.004
        self.parts = (self.root, self.scan, self.vig, self.veil, self.line)

    def _turn_on(self):
        """The picture opens from a bright line (the CRT warming up): ~0.34 s of frames drawn right here, before the long load starts."""
        if self.quiet:
            self.root.scale_y = 1.0
            self._frame()
            return
        ease = bezier(EASE_OUT)
        t0 = pytime.perf_counter()
        while True:
            u = (pytime.perf_counter() - t0) / TURN_ON_S
            self.root.scale_y = max(ease(min(u, 1.0)), 0.004)
            self.line.color = color.rgba(0.72, 1.0, 0.72, max(0.0, 1.0 - u * 1.6))
            self._frame()
            if u >= 1.0:
                break
            pytime.sleep(0.004)
        self.line.color = color.rgba(0.72, 1.0, 0.72, 0.0)

    # ------------------------------------------------------------ time and frames
    def now(self) -> float:
        """Splash time (s). While loading it is the wall clock (the log shows real durations). After the load it advances by the frame times that `update` hands in, each capped
        (`MAX_STEP`): the first frame of the running game can take seconds, and the ending must not be consumed in that one frame (the player would see it flash by)."""
        if self._loaded_at is None:
            return pytime.perf_counter() - self.t_start
        return self._loaded_at + self._extra

    def _frame(self):
        """Draw one frame of the splash ONLY. The build calls this in the middle of building: the 3D scene is half made then (a shader input a later step sets is missing:
        Panda raises 'Shader input look_camera_pos is not present'), so its root is hidden for the draw. Drawing also pumps the window's messages."""
        t = self.now()
        self._cues(t)
        self._draw(t)
        base = application.base
        base.render.hide()
        try:
            base.graphicsEngine.render_frame()
        finally:
            base.render.show()

    def _cues(self, t: float):
        for cue in self.seq.poll_cues(t):
            self.audio.play(CUE_SOUND.get(cue, cue))
        n = self.seq.total_chars(t)
        if n != self._chars:
            self._chars = n
            self.audio.tick(t)

    def _draw(self, t: float):
        seq, L = self.seq, self.L
        rows = seq.visible(t, L.log_rows)
        cursor = seq.phase == 'finale' and T.blink(t, 1.8, 0.6)
        for i, row in enumerate(self.log):
            if i >= len(rows):
                row.set('')
                continue
            text, kind, finished = rows[i]
            tint = KIND_COLOR.get(kind, PHOSPHOR)
            if kind == 'rec' and not T.blink(t, 1.2, 0.65):
                tint = color.rgba(RED.r, RED.g, RED.b, 0.25)
            if i == len(rows) - 1 and cursor and finished and kind != 'rec':
                text += T.BLOCK                                          # the block cursor after the last line
            row.set(text, tint)
        p = seq.progress
        self.bar.set(f'LOAD [{T.bar(p, PROGRESS_BAR_COLS)}] {int(round(p * 100)):3d}%')
        self.clock.set(f'SESSION {T.clock(t)}')
        hint = seq.hint(t)
        self.hint.set(hint if hint and T.blink(t, 1.2, 0.7) else '')
        self.veil.color = color.rgba(0, 0, 0, 1.0 - T.flicker(t, 0.03))

    # ------------------------------------------------------------ what the build calls
    def stage(self, label: str, progress: float = None):
        """A real load step starts (the previous one gets its OK) and one frame is drawn."""
        self.seq.stage(label, self.now(), progress)
        self._frame()

    def bake(self, label: str, share: float):
        """The light bake reports (0..1); at most a redraw every 0.2 s (drawing also pumps the window's messages: no 'Not responding')."""
        now = self.now()
        if share > 0.0 and now - self._last_bake < 0.2:
            return
        self._last_bake = now
        self.seq.retitle(f'LIGHT BAKE  {label}  {share * 100:3.0f}%')
        self._frame()

    def load_done(self, facts: dict = None):
        self._loaded_at = self.now()
        self._extra = 0.0
        self.seq.load_done(self._loaded_at, facts or gather_facts(self.root_dir, self.sound))
        self._frame()

    # ------------------------------------------------------------ per frame (Game.update), input
    def update(self, dt: float) -> str:
        """Advance the splash one frame; returns the state (hold / off: the game waits; fade: the game runs; gone)."""
        self._extra += min(max(dt, 0.0), MAX_STEP)
        t = self.now()
        if self.state == 'hold':
            self.seq.update(t)
            self._cues(t)
            self._draw(t)
            if self.seq.done:
                self.state, self.t_off = 'off', t
        elif self.state == 'off':
            u = min((t - self.t_off) / OFF_S, 1.0)
            self.root.scale_y = max(1.0 - bezier(EASE_IN)(u), 0.004)
            self.line.color = color.rgba(0.72, 1.0, 0.72, min(u * 1.5, 1.0) * (1.0 - u))
            self.audio.set_volume('boot_hum', 0.22 * (1.0 - u))
            self._draw(t)
            if u >= 1.0:
                self.state, self.t_fade = 'fade', t
                self.audio.stop('boot_hum')
                for part in (self.root, self.scan, self.vig, self.veil, self.line):
                    part.enabled = False
        elif self.state == 'fade':
            a = 1.0 - (t - self.t_fade) / FADE_S
            if a <= 0.0:
                self.destroy()
            else:
                self.cover.color = color.rgba(0, 0, 0, a)
        return self.state

    def on_input(self, key: str) -> bool:
        """A key / click: skips the ending when that is allowed (see termui.BootSeq.skip). True = skipped."""
        if self.state != 'hold' or key.endswith(' up') or key in ('mouse move', 'mouse x', 'mouse y'):
            return False
        return self.seq.skip(self.now())

    @property
    def holding(self) -> bool:
        return self.state in ('hold', 'off')

    def destroy(self):
        global ACTIVE
        self.state = 'gone'
        if ACTIVE is self:
            ACTIVE = None
        self.audio.stop('boot_hum')
        for e in (self.cover, *self.parts):
            try:
                destroy(e)
            except Exception:                              # already gone with its parent
                pass


def report_bake(label: str, share: float) -> bool:
    """Called by the light bake: True when the splash showed it (the bake then draws nothing of its own)."""
    if ACTIVE is None:
        return False
    ACTIVE.bake(label, share)
    return True
