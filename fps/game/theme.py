"""G20: the look of the terminal UI on the Ursina side: the phosphor palette, the monospace font, one row of text on the pixel grid (with its glow), and pixel-exact rectangles.
The maths (grid, layouts, fixed-width text) is in fps/core/termui.py; skill `phosphor-terminal-ui` has the reasons.

Colour rule: ONE hue. Meaning comes from brightness and shape (bars, markers, brackets); amber is only a warning, red only the REC dot and errors.
"""
import os
from pathlib import Path

from ursina import Entity, Text, application, color

from fps.core import termui as T

PHOSPHOR = color.rgb(0.20, 1.00, 0.20)       # P1 phosphor ~ #33FF33 (the normal level)
BRIGHT = color.rgb(0.72, 1.00, 0.72)         # headers, the selected row's value
DIM = color.rgb(0.12, 0.66, 0.12)            # labels at rest, hints (still ~6:1 against black)
INK = color.rgb(0.0, 0.07, 0.0)              # text on a phosphor bar (reverse video)
AMBER = color.rgb(1.00, 0.69, 0.00)          # a warning (P3 amber ~ #FFB000)
RED = color.rgb(1.00, 0.23, 0.19)            # the REC dot, an error
BLACK = color.rgb(0.0, 0.0, 0.0)
BAR = color.rgba(0.20, 1.00, 0.20, 0.92)     # the selected row / a banner

Z_COVER, Z_BAR, Z_GLOW, Z_TEXT, Z_FX = 0.5, -0.10, -0.19, -0.20, -0.90     # depth layers: higher z = farther; the screen effects sit in front of the text

FONTS = ('consola.ttf', 'lucon.ttf', 'cour.ttf')        # monospace fonts of Windows, in order of preference
_em_cache = {}


def ensure_mono_font():
    """The file name of a monospace font Windows has (None: use Ursina's default font; the layout then only approximates the grid)."""
    fonts = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
    for name in FONTS:
        if (fonts / name).exists():
            application.fonts_folder = fonts
            return name
    return None


def em_ratio(font) -> float:
    """Glyph advance / em of `font`, measured once with a throw-away Text (Consolas 0.55, Lucida Console / Courier 0.6)."""
    if font not in _em_cache:
        probe = Text(text='M' * 20, font=font, enabled=False) if font else Text(text='M' * 20, enabled=False)
        _em_cache[font] = probe.width / 20.0 / Text.size if probe.width else T.CONSOLAS_EM
        from ursina import destroy
        destroy(probe)
    return _em_cache[font]


class TermText:
    """One row of terminal text on the pixel grid. `x` is the left edge of column 0 and `row_y` the top of the row, both in integer window pixels; the capitals are centred in the
    row. `glow` > 0 adds two copies one pixel to each side at that alpha (a horizontal phosphor bloom that stays symmetric: it never looks like a misregistered double).
    `set` rebuilds the glyphs only when the text or the colour changed (a Panda TextNode rebuild costs ~0.3 ms)."""

    def __init__(self, parent, grid: T.Grid, window: tuple, x: int, row_y: int, tint=PHOSPHOR, glow: float = 0.0, font=None, z: float = Z_TEXT):
        self.grid, self.W, self.H = grid, window[0], window[1]
        self.tint = tint
        self._text = ''
        self._font = font
        top = T.text_origin_y(row_y, grid)
        offsets = [0] if glow <= 0.0 else [-1, 1, 0]
        self.copies = []
        for dx in offsets:
            main = dx == 0
            col = tint if main else color.rgba(tint.r, tint.g, tint.b, glow * tint.a)
            kwargs = {'font': font} if font else {}
            t = Text(parent=parent, text='', origin=(-0.5, 0.5), scale=grid.text_scale, color=col,
                     position=(T.px_to_ui_x(x + dx, self.W, self.H), T.px_to_ui_y(top, self.H), z if main else Z_GLOW), **kwargs)
            self.copies.append((t, main))
        self.glow = glow
        self.x0, self.row_y = x, row_y

    @property
    def text(self) -> str:
        return self._text

    def set(self, text: str, tint=None):
        if text != self._text:
            self._text = text
            for t, _ in self.copies:
                t.text = text
        if tint is not None and tint != self.tint:
            self.tint = tint
            for t, main in self.copies:
                t.color = tint if main else color.rgba(tint.r, tint.g, tint.b, self.glow * tint.a)

    @property
    def enabled(self) -> bool:
        return self.copies[0][0].enabled

    @enabled.setter
    def enabled(self, value: bool):
        for t, _ in self.copies:
            t.enabled = value

    def width_px(self) -> int:
        return len(self._text) * self.grid.cw


def rect(parent, r: T.Rect, window: tuple, col, z: float = Z_BAR) -> Entity:
    """A quad that covers the pixel rectangle `r` exactly (edges on pixel boundaries: no half-covered pixels)."""
    W, H = window
    e = Entity(parent=parent, model='quad', color=col, z=z,
               position=(T.px_to_ui_x(r.x + r.w / 2.0, W, H), T.px_to_ui_y(r.y + r.h / 2.0, H)), scale=(r.w / H, r.h / H))
    return e


def move_rect(e: Entity, r: T.Rect, window: tuple):
    W, H = window
    e.position = (T.px_to_ui_x(r.x + r.w / 2.0, W, H), T.px_to_ui_y(r.y + r.h / 2.0, H), e.z)
    e.scale = (r.w / H, r.h / H)


def window_pixels() -> tuple:
    """The real size of the window / buffer in pixels (what the screen is drawn at)."""
    win = application.base.win
    return int(win.get_x_size()), int(win.get_y_size())
