"""The graphics panel (G10; restyled G20, opened with Esc): the choices of core/graphics.OPTIONS (overall preset, anti-aliasing, each water / light effect, FPS counter).
Every change applies at once (Game.apply_graphics); closing saves user_graphics.json.

G20 look: green phosphor on black like the boot splash, but quiet - a body-camera status strip on top (REC dot, recording time, title, FPS), one row per option, a reverse-video
selection bar, a key hint at the bottom. Every position comes from the cell grid of fps/core/termui.py (`panel_layout`), in whole pixels: the labels share one left edge, the values
one column, the arrows fixed cells, so nothing moves when a value changes. Motion: the panel opens from a line like a CRT (0.16 s) and closes the same way (0.11 s), the selection
bar slides to the row, a changed value flashes the bar. Sounds: open, close, row move, value change (assets/sounds/ui).

Keys while open: up / down choose a row, left / right change it (not WASD: those still walk), Esc closes. Mouse: the row under the pointer is selected, left click = next choice,
right click = previous, wheel = move. Opening frees the mouse and blocks firing / aiming (player.ui_open); closing captures it again.
Built the first time it opens (and again if the window size changed); while closed it is disabled and `Game.update` does not call it (`visible` is False).
"""
from ursina import Entity, camera, color, destroy, mouse, scene

from fps.core import termui as T
from fps.core.easing import bezier
from fps.core.graphics import OPTIONS, choice_text, cycle
from fps.game import theme
from fps.game.theme import BAR, BRIGHT, DIM, INK, PHOSPHOR, RED, TermText, move_rect, rect

TITLE = 'VIDEO CONFIGURATION'
HINT = '↑↓ SELECT   ←→ CHANGE   CLICK L/R   ESC CLOSE'
OPEN_S, CLOSE_S = 0.16, 0.11
EASE = (0.20, 0.90, 0.30, 1.00)
SLIDE_RATE = 34.0                                   # 1/s: the selection bar follows the chosen row (a jump of more than 3 rows snaps)
FLASH_S = 0.12                                      # a changed value lights the bar this long
QUIET = ('OFF', 'FLAT', 'SIMPLE')                   # value texts drawn dim: the feature is off / simplified
BODY = color.rgba(0.0, 0.035, 0.0, 0.94)
EDGE = color.rgba(0.20, 1.0, 0.20, 0.40)
DOT_OFF = color.rgba(RED.r, RED.g, RED.b, 0.25)


def _descendants(e) -> list:
    out = [e]
    for c in e.children:
        out.extend(_descendants(c))
    return out


class GraphicsPanel:
    def __init__(self, game):
        self.game = game
        self.is_open = False                         # the panel owns the keys / mouse
        self.visible = False                         # drawn: also while it closes
        self.row = 0
        self._built = False
        self._size = None
        self._anim = 0.0
        self._bar_y = 0.0
        self._shown_row = -1                         # the row whose colours are inverted (follows the bar, not the key press)
        self._flash = 0.0
        self._flash_on = False
        self._ptr = None
        self._fps_frames, self._fps_time = 0, 0.0
        self.t = 0.0

    # ------------------------------------------------------------ build
    def _build(self):
        if self._built:                                   # the window size changed since the last build
            destroy(self.root)
        W, H = theme.window_pixels()
        self._size = self.win = (W, H)
        font = theme.ensure_mono_font()
        self.L = L = T.panel_layout(W, H, len(OPTIONS), em_ratio=theme.em_ratio(font))
        g, win, P = L.grid, self.win, L.panel
        self.root = r = Entity(parent=camera.ui, enabled=False)
        rect(r, P, win, BODY, z=-0.05)
        th = max(1, g.cw // 8)
        for edge in (T.Rect(P.x, P.y, P.w, th), T.Rect(P.x, P.bottom - th, P.w, th), T.Rect(P.x, P.y, th, P.h), T.Rect(P.right - th, P.y, th, P.h)):
            rect(r, edge, win, EDGE, z=-0.06)
        arm, thick = g.cw * 2, max(2, th * 2)                  # corner brackets, in the phosphor colour
        for cx, cy, sx, sy in ((P.x, P.y, 1, 1), (P.right, P.y, -1, 1), (P.x, P.bottom, 1, -1), (P.right, P.bottom, -1, -1)):
            rect(r, T.Rect(cx if sx > 0 else cx - arm, cy if sy > 0 else cy - thick, arm, thick), win, PHOSPHOR, z=-0.07)
            rect(r, T.Rect(cx if sx > 0 else cx - thick, cy if sy > 0 else cy - arm, thick, arm), win, PHOSPHOR, z=-0.07)
        rect(r, L.rule_top, win, EDGE, z=-0.06)
        rect(r, L.rule_bottom, win, EDGE, z=-0.06)
        self.bar = rect(r, self._bar_rect(0), win, BAR, z=theme.Z_BAR)
        # status strip: REC dot, REC, recording time | title | FPS
        hy = L.header.y
        self.dot = TermText(r, g, win, L.col_x(0), hy, RED, 0.0, font)
        self.dot.set(T.DOT)
        TermText(r, g, win, L.col_x(2), hy, BRIGHT, 0.0, font).set('REC')
        self.clock = TermText(r, g, win, L.col_x(6), hy, PHOSPHOR, 0.0, font)
        TermText(r, g, win, T.centered_x(L.text_x, L.header.w, len(TITLE), g.cw), hy, BRIGHT, 0.22, font).set(TITLE)
        self.fps = TermText(r, g, win, L.col_x(T.PANEL_COLS - 7), hy, DIM, 0.0, font)
        self.fps.set('FPS ---')
        self.clock.set(T.clock(self.game._age))
        # one row per option: marker + label at column 0, the value block at the value column
        self.labels = [TermText(r, g, win, L.col_x(0), rc.y, PHOSPHOR, 0.0, font) for rc in L.options]
        self.values = [TermText(r, g, win, L.col_x(L.value_col), rc.y, PHOSPHOR, 0.0, font) for rc in L.options]
        TermText(r, g, win, T.centered_x(L.text_x, L.footer.w, len(HINT), g.cw), L.footer.y, DIM, 0.0, font).set(HINT)
        mine = set(map(id, _descendants(r)))
        scene.entities = [e for e in scene.entities if id(e) not in mine]       # none of them updates: keep them out of Ursina's per-frame walk (like prune_scene_entities)
        self._built = True
        self._shown_row = -1
        self._bar_y = float(L.options[self.row].y)

    def _bar_rect(self, y: int) -> T.Rect:
        L = self.L
        return T.Rect(L.text_x - L.grid.cw, int(y), T.PANEL_COLS * L.grid.cw + 2 * L.grid.cw, L.grid.lh)      # one column wider than the text on each side

    # ------------------------------------------------------------ what is shown
    def _refresh(self, visual_row: int = None):
        """Texts and colours of every row. `visual_row` is the row the bar is over (it lags the chosen row while the bar slides)."""
        v = self.row if visual_row is None else visual_row
        s = self.game.gfx
        self._shown_row = v
        for i, (field, label, _choices) in enumerate(OPTIONS):
            sel = i == v
            value = choice_text(s, field)
            left, block = T.option_line(label, sel, value, sel)
            self.labels[i].set(left, INK if sel else PHOSPHOR)
            self.values[i].set(block, INK if sel else (DIM if value in QUIET else PHOSPHOR))

    def _pointer_px(self) -> tuple:
        return T.ui_to_px(mouse.x, mouse.y, self.win[0], self.win[1])

    def _row_at(self, px: float, py: float):
        """The option row under a pixel: the hit area is the whole panel width (not only the text)."""
        L = self.L
        if not (L.panel.x <= px < L.panel.right):
            return None
        for i, rc in enumerate(L.options):
            if rc.y <= py < rc.bottom:
                return i
        return None

    def prebuild(self):
        """Build the panel now, hidden (create_game calls it while loading): building ~40 text rows takes ~0.8 s, which would freeze the game at the first Esc."""
        if not self._built:
            self._build()

    # ------------------------------------------------------------ open / close
    def toggle(self):
        self.hide() if self.is_open else self.show()

    def show(self):
        if self.is_open:
            return
        if not self._built or self._size != theme.window_pixels():
            self._build()
        self.is_open = True
        self.visible = True
        self.root.enabled = True
        g = self.game
        g.player.ui_open = True
        g.combat.pressed = False
        mouse.locked = False
        self._ptr = self._pointer_px()                 # the row under the pointer is only picked once the pointer MOVES
        self._refresh()
        self.game.ui_audio.play('ui_open')

    def hide(self):
        if not self.is_open:
            return
        self.is_open = False
        g = self.game
        g.player.ui_open = False
        g.combat.pressed = False
        mouse.position = (0, 0)                     # centre the pointer before locking: no big camera turn from where the pointer was
        mouse.prev_x = mouse.prev_y = 0
        mouse.locked = True
        g.save_graphics()
        g.ui_audio.play('ui_close')

    # ------------------------------------------------------------ input
    def change(self, step: int, row: int = None):
        if row is not None:
            self.row = row
        field = OPTIONS[self.row][0]
        self.game.apply_graphics(cycle(self.game.gfx, field, step))
        self._flash = FLASH_S
        self._refresh(self._shown_row if self._shown_row >= 0 else self.row)
        self.game.ui_audio.play('ui_change')

    def _move(self, step: int):
        self.row = (self.row + step) % len(OPTIONS)
        self.game.ui_audio.play('ui_move', rate=1.0 + 0.03 * (self.row % 4))

    def on_input(self, key: str):
        if key == 'escape':
            self.hide()
        elif key in ('up arrow', 'up arrow hold', 'scroll up'):
            self._move(-1)
        elif key in ('down arrow', 'down arrow hold', 'scroll down'):
            self._move(1)
        elif key in ('right arrow', 'enter'):
            self.change(1)
        elif key == 'left arrow':
            self.change(-1)
        elif key in ('left mouse down', 'right mouse down'):
            row = self._row_at(*self._pointer_px())
            if row is not None:
                self.change(1 if key == 'left mouse down' else -1, row)

    # ------------------------------------------------------------ per frame (Game.update while visible)
    def update(self, dt: float):
        if not self._built:
            return
        self.t += dt
        L = self.L
        ease = bezier(EASE)
        if self.is_open:
            self._anim = min(self._anim + dt / OPEN_S, 1.0)
        else:
            self._anim = max(self._anim - dt / CLOSE_S, 0.0)
        self.root.scale_y = max(ease(self._anim), 0.02)
        if not self.is_open and self._anim <= 0.0:
            self.root.enabled = False
            self.visible = False
            return
        if not self.is_open:
            return
        # pointer: the row under it is chosen once the pointer moves
        ptr = self._pointer_px()
        if ptr != self._ptr:
            self._ptr = ptr
            row = self._row_at(*ptr)
            if row is not None and row != self.row:
                self.row = row
                self._move(0)
        # the selection bar slides to the chosen row; the inverted colours follow the bar
        target = L.options[self.row].y
        d = target - self._bar_y
        if abs(d) > 3 * L.grid.lh or abs(d) < 0.5:
            self._bar_y = float(target)
        else:
            self._bar_y += d * min(1.0, dt * SLIDE_RATE)
        move_rect(self.bar, self._bar_rect(round(self._bar_y)), self.win)
        visual = min(max(int(round((self._bar_y - L.options[0].y) / L.grid.lh)), 0), len(OPTIONS) - 1)
        if visual != self._shown_row:
            self._refresh(visual)
        # a changed value flashes the bar
        self._flash = max(self._flash - dt, 0.0)
        on = self._flash > 0.0
        if on != self._flash_on:
            self._flash_on = on
            self.bar.color = BRIGHT if on else BAR
        # status strip: the REC dot blinks, the recording time runs, the FPS refreshes four times a second
        self.dot.set(T.DOT, RED if T.blink(self.t, 1.0, 0.6) else DOT_OFF)
        self.clock.set(T.clock(self.game._age))
        self._fps_frames += 1
        self._fps_time += dt
        if self._fps_time >= 0.25:
            self.fps.set(f'FPS {min(int(round(self._fps_frames / self._fps_time)), 999):>3}')
            self._fps_frames, self._fps_time = 0, 0.0
