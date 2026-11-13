r"""G20: the boot splash and the graphics panel in the REAL game (hidden by default: an offscreen buffer, no window), with the layout measured on real screenshots.

Splash: every real load step is announced and ends [ OK ]; the game is held while it runs (the gun has not been drawn); a key during the first 0.4 s after the load does not skip it;
Esc does not open the panel under it; a later key skips the ending; the splash hands over (boot gone, the draw clip starts, the room tone starts when sound is on).
Panel: Esc opens it (frees the mouse, blocks firing), the layout is measured in the screenshot (all four panel corners land on the exact pixel of `panel_layout`; the selection bar spans
exactly its row; every label's first capital is vertically centred in its row to 1.5 px; no value starts outside its column and no arrow shows on an unselected row), a value change
works, Esc closes (captures the mouse, saves), opening costs no frame over 50 ms and the open panel adds little to the frame time. Shots: shots\g20_*.png.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\ui_check.py [--size 1920x1080] [--sound] [--show]
(exit code = number of failures)
"""
import argparse
import sys
import tempfile
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')
import fps.app as app_mod  # noqa: E402
app_mod.USER_GRAPHICS = Path(tempfile.gettempdir()) / 'fps_ui_check_graphics.json'       # never touch the player's own settings
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from main import create_game  # noqa: E402
from panda3d.core import Filename  # noqa: E402
from ursina import Entity, application, mouse, time  # noqa: E402

import fps.game.boot as boot_mod  # noqa: E402
from fps.core import termui as T  # noqa: E402
from fps.core.graphics import OPTIONS  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--size', default='1280x720')
ap.add_argument('--sound', action='store_true', help='load the real UI sounds (needs an audio device)')
ap.add_argument('--map', default='pool')
args = ap.parse_args()
W, H = (int(v) for v in args.size.lower().split('x'))
SHOTS = ROOT / 'shots'
SHOTS.mkdir(exist_ok=True)
fails = []
EXPECTED_STAGES = ('OPEN DISPLAY', 'LOAD ENVIRONMENT MAP', 'INIT PLAYER / PHYSICS', 'INIT AUDIO SUBSYSTEM', 'LOAD WEAPON SYSTEMS', 'INIT RENDER PIPELINE', 'COMPILE SHADERS',
                   'PRELOAD WEAPON KITS', 'WARM SHADER BUILDS')


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
    if not ok:
        fails.append(name)


def snap(name) -> Path:
    path = SHOTS / f'g20_{W}_{name}.png'
    application.base.win.save_screenshot(Filename.from_os_specific(str(path)))
    return path


# a shot in the middle of the load (the build is one long call: hook the stage announcement)
_orig_stage = boot_mod.BootScreen.stage
mid_load = {}


def _stage(self, label, progress=None):
    _orig_stage(self, label, progress)
    if label.startswith('LOAD WEAPON') and 'path' not in mid_load:
        mid_load['path'] = snap('splash_load')


boot_mod.BootScreen.stage = _stage
t_build = pytime.time()
game = create_game(vsync=False, size=(W, H), sound=args.sound, draw=True, map_name=args.map, splash=True)
print(f'build with splash: {pytime.time() - t_build:.1f} s  ({W}x{H})')
boot = game.boot


def ink(img, x0, y0, x1, y1, light=True, thr=140):
    """Pixels of the text colour inside a pixel box (light on dark): boolean array."""
    px = img[max(y0, 0):y1, max(x0, 0):x1].astype(int)
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    return (g > thr) & (r < 140) & (b < 140) if light else (g < 120)


def panel_checks(path: Path, L: T.PanelLayout, selected: int):
    img = np.asarray(Image.open(path).convert('RGB'))
    g, P = L.grid, L.panel
    # 1. the four corner brackets start on the exact pixel of the layout
    def bracket(x, y):
        r, gg, b = (int(v) for v in img[y, x])
        return gg > 225 and r < 90 and b < 90
    corners = {'top-left': ((P.x, P.y), (P.x - 1, P.y)), 'top-right': ((P.right - 1, P.y), (P.right, P.y)),
               'bottom-left': ((P.x, P.bottom - 1), (P.x - 1, P.bottom - 1)), 'bottom-right': ((P.right - 1, P.bottom - 1), (P.right, P.bottom - 1))}
    for name, (inside, outside) in corners.items():
        check(f'panel corner {name} is on the exact pixel', bracket(*inside) and not bracket(*outside), f'{inside}')
    # 2. the selection bar spans exactly its row (the bar is one column wider than the text on each side)
    row = L.options[selected]
    bar_x0, bar_x1 = L.text_x - g.cw, L.text_x + T.PANEL_COLS * g.cw + g.cw
    band = img[row.y + 2:row.bottom - 2, :].astype(int)
    lit = (band[..., 1] > 200) & (band[..., 0] < 110) & (band[..., 2] < 110)
    xs = np.where(lit.any(axis=0))[0]
    check('selection bar spans its row horizontally, to the pixel', len(xs) > 0 and xs.min() == bar_x0 and xs.max() == bar_x1 - 1, f'x {xs.min() if len(xs) else None}..{xs.max() if len(xs) else None}, want {bar_x0}..{bar_x1 - 1}')
    col = img[:, bar_x0 + 1].astype(int)
    ys = np.where((col[:, 1] > 200) & (col[:, 0] < 110) & (col[:, 2] < 110))[0]
    ys = ys[(ys >= row.y - 3) & (ys <= row.bottom + 3)]
    check('selection bar spans its row vertically, to the pixel', len(ys) > 0 and ys.min() == row.y and ys.max() == row.bottom - 1, f'y {ys.min() if len(ys) else None}..{ys.max() if len(ys) else None}, want {row.y}..{row.bottom - 1}')
    # 3. first capital of every unselected label: vertically centred in its row; the label never reaches the value column
    worst, reach = 0.0, 0
    for i, rc in enumerate(L.options):
        if i == selected:
            continue
        cell = ink(img, L.col_x(2), rc.y, L.col_x(3), rc.bottom)                # exactly the row: the bar of a neighbouring selected row must not count
        ys = np.where(cell.any(axis=1))[0]
        if len(ys):
            centre = (ys.min() + ys.max() + 1) / 2.0 + rc.y
            worst = max(worst, abs(centre - (rc.y + g.lh / 2.0)))
        label_ink = ink(img, L.text_x, rc.y, L.col_x(L.value_col), rc.bottom)
        xs = np.where(label_ink.any(axis=0))[0]
        reach = max(reach, (xs.max() + L.text_x) if len(xs) else 0)
    check('every label starts with a capital centred in its row (within 1.5 px)', worst <= 1.5, f'worst {worst:.2f} px')
    check('no label reaches the value column', reach < L.col_x(L.value_col), f'reach x={reach}, value column x={L.col_x(L.value_col)}')
    # 4. values: nothing in the two arrow cells of an unselected row, the text starts in the third cell, close to its left edge
    bad_arrows, worst_left = 0, 0.0
    for i, rc in enumerate(L.options):
        if i == selected:
            continue
        arrows = ink(img, L.col_x(L.value_col), rc.y, L.col_x(L.value_col + 2), rc.bottom)
        bad_arrows += int(arrows.any())
        cell = ink(img, L.col_x(L.value_col + 2) - g.cw, rc.y, L.col_x(L.value_col + 3), rc.bottom)
        xs = np.where(cell.any(axis=0))[0]
        if len(xs):
            worst_left = max(worst_left, xs.min() + L.col_x(L.value_col + 2) - g.cw - L.col_x(L.value_col + 2))
    check('no arrow shows on an unselected row', bad_arrows == 0, f'{bad_arrows} rows')
    check('every value starts in its column (ink within half a cell of the left edge)', worst_left <= 0.5 * g.cw, f'worst {worst_left:.1f} px of {g.cw}')
    # 5. the title and the hint are centred to a pixel
    for name, rc in (('title', L.header), ('hint', L.footer)):
        skip = 14 * g.cw if name == 'title' else 0                                   # the title sits between the clock (columns 6-13) and the FPS (columns 53-59)
        c = ink(img, L.text_x + skip, rc.y, L.text_x + T.PANEL_COLS * g.cw - skip, rc.bottom, thr=140 if name == 'title' else 70)
        xs = np.where(c.any(axis=0))[0]
        if len(xs):
            left = xs.min() + skip
            right = T.PANEL_COLS * g.cw - (xs.max() + 1 + skip)
            check(f'{name} is centred in the panel (gaps within 2 px)', abs(left - right) <= 2 + g.cw // 6, f'left gap {left}, right gap {right}')


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.dts = []

    def update(self):
        self.dts.append(time.dt)
        try:
            next(self.gen)
        except StopIteration:
            sys.exit(len(fails))

    def wait(self, n):
        for _ in range(n):
            yield

    def sec(self, seconds):
        t = pytime.time()
        while pytime.time() - t < seconds:
            yield

    def run(self):
        p = game.player
        panel = game.gfx_panel
        # ------------------------------------------------------------ the splash
        labels = [ln.label for ln in boot.seq.lines if ln.label]
        for want in EXPECTED_STAGES:
            check(f'splash announces the real step "{want}"', any(lb.startswith(want) for lb in labels))
        stage_lines = [ln for ln in boot.seq.lines if ln.label]
        check('every announced step ended [ OK ]', all(not ln.pending and ln.text.endswith(T.STATUS_OK) for ln in stage_lines), f'{sum(ln.pending for ln in stage_lines)} pending')
        check('the splash was drawn during the load (a shot exists)', 'path' in mid_load)
        check('the game is held while the splash runs (the gun has not been drawn yet)', game._draw_pending and boot.state == 'hold')
        yield from self.wait(2)
        since_load = boot.now() - boot.seq.finale_start
        if since_load < T.KEY_GRACE:                                  # keys queued during the load reach the game in its first frames: they must not skip
            game.input('space')
            check('a key in the first 0.4 s after the load does not skip the ending', not boot.seq.skipped, f'{since_load:.2f} s after the load')
            game.input('escape')
            check('Esc under the splash does not open the graphics panel', not panel.is_open)
        else:
            print(f'(note: {since_load:.2f} s passed before the first frame: the grace check is covered by tests/test_termui.py)')
        yield from self.sec(0.5)
        snap('splash_finale_a')
        yield from self.sec(1.1)
        snap('splash_finale_b')
        while boot.seq.finale_end - boot.now() > 0.7 and boot.state == 'hold':
            yield
        snap('splash_finale_c')
        check('the first key after the grace skips the ending', (game.input('space') or True) and boot.seq.skipped)
        yield from self.wait(5)
        snap('splash_off')
        check('Esc did not open the panel under the splash either', not panel.is_open)
        t_wait = pytime.time()
        while game.boot is not None and pytime.time() - t_wait < 8.0:
            yield
        check('the splash hands over to the game (boot gone)', game.boot is None and game._boot_handed, f'{pytime.time() - t_wait:.1f} s after the skip')
        yield from self.sec(0.6)
        check('the gun draw clip started after the hand-over', not game._draw_pending)
        yield from self.sec(1.5)
        # ------------------------------------------------------------ the panel
        p.x, p.y, p.z, p.yaw, p.pitch = 3.0, 0.0, -8.0, 75.0, 0.0
        p._apply_view()
        yield from self.wait(30)
        base_dts = []
        self.dts.clear()
        yield from self.wait(60)
        base_dts = list(self.dts)
        check('Esc is not capturing / releasing the mouse by itself any more: the mouse is locked in play', mouse.locked)
        self.dts.clear()
        game.input('escape')
        yield from self.wait(60)
        open_dts = list(self.dts)
        t0 = pytime.perf_counter()
        for _ in range(300):
            panel.update(0.016)
        per_update = (pytime.perf_counter() - t0) / 300 * 1000
        check('the panel update costs under 0.5 ms (Python side)', per_update < 0.5, f'{per_update:.3f} ms')
        L = panel.L
        check('Esc opens the panel, frees the mouse and blocks firing', panel.is_open and p.ui_open and not mouse.locked)
        check('the open animation finished (the panel is full size)', panel._anim >= 1.0 and abs(panel.root.scale_y - 1.0) < 1e-6)
        snap('panel_open')
        panel_checks(snap('panel_a'), L, panel.row)
        # a value change, a different row selected: the same measurements again
        panel.on_input('down arrow')
        panel.on_input('down arrow')
        panel.on_input('down arrow')
        yield from self.wait(30)
        before = game.gfx.sim
        game.input('left arrow')
        yield from self.wait(10)
        check('left / right change the chosen row and apply at once', game.gfx.sim != before and panel.row == 3, f'sim {before} -> {game.gfx.sim}')
        snap('panel_change')
        yield from self.sec(0.4)                                      # the bar flashes 0.12 s after a change: measure it at rest
        panel_checks(snap('panel_b'), L, panel.row)
        # the pointer picks a row once it moves
        rc = L.options[9]
        x, y = T.px_to_ui_x(rc.x + 40, W, H), T.px_to_ui_y(rc.y + rc.h / 2, H)
        mouse.x, mouse.y = x, y
        yield from self.wait(5)
        check('the row under the pointer is chosen', panel.row == 9, f'row {panel.row}')
        field9 = OPTIONS[9][0]
        before9 = getattr(game.gfx, field9)
        game.input('left mouse down')
        yield from self.wait(3)
        check('a left click changes the row under the pointer', getattr(game.gfx, field9) != before9, f'{field9}: {before9} -> {getattr(game.gfx, field9)}')
        yield from self.sec(0.4)
        panel_checks(snap('panel_c'), L, panel.row)
        # closing. The screenshot + numpy analysis above ran INSIDE a frame: its time lands in the next frame's dt, so let a few frames pass before timing
        yield from self.wait(5)
        self.dts.clear()
        game.input('escape')
        yield from self.wait(3)
        check('Esc closes the panel at once (the game has the mouse again)', not panel.is_open and not p.ui_open and mouse.locked)
        yield from self.sec(0.3)                                      # real time: the animation runs on dt, and hidden frames are ~1 ms
        check('... and it is gone after its 0.11 s close animation', not panel.visible and not panel.root.enabled)
        close_dts = list(self.dts)
        worst = max(open_dts + close_dts)
        i_open = int(np.argmax(open_dts)) if open_dts else -1
        check('opening and closing never make a frame slower than 50 ms', worst < 0.05,
              f'worst {worst * 1000:.1f} ms; opening: worst {max(open_dts) * 1000:.1f} ms at frame {i_open}, closing: worst {max(close_dts) * 1000:.1f} ms')
        mean_base, mean_open = np.mean(base_dts[10:]) * 1000, np.mean(open_dts[30:]) * 1000
        check('the open panel adds under 3 ms to the frame', mean_open <= mean_base + 3.0, f'{mean_base:.2f} ms closed, {mean_open:.2f} ms open')
        game.graphics_save.join(5)
        check('closing saved the graphics file (to the temp file, not the player\'s)', app_mod.USER_GRAPHICS.exists())
        print(f'rows: {len(OPTIONS)}, grid {L.grid.cw}x{L.grid.lh} px, panel {L.panel.w}x{L.panel.h} at ({L.panel.x}, {L.panel.y})')


Script()
game.app.run()
