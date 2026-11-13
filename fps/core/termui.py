"""G20: text-mode UI maths, pure Python (no Ursina; tests/test_termui.py). Used by the boot splash (game/boot.py) and the graphics panel (game/graphics_panel.py).

Why it exists: a terminal look only reads as "professional" when every glyph sits on one grid. Everything here is in INTEGER PIXELS (origin top-left, y down) and a monospace
CELL GRID (`Grid`: `cw` px per column, `lh` px per row). The game layer converts a pixel to an Ursina UI unit with `px_to_ui_*` (window height = 1.0) and picks the Text
scale so one glyph advance is exactly `cw` px (`Grid.text_scale`), so a column is never a fraction of a pixel and nothing "swims" between rows.

Contents: Grid + rectangles + layouts of the panel and the splash, fixed-width text helpers, the typewriter, and `BootSeq` (the splash script: real load stages, then the
fixed finale). Times are passed in by the caller (seconds), so the whole sequence is deterministic and testable.
"""
import math
from dataclasses import dataclass

TEXT_SIZE = 0.025                 # Ursina Text.size: height of one em at Text scale 1, in UI units (window height = 1)
CONSOLAS_EM = 0.55                # advance width / em of Consolas (measured in G20: 0.01375 UI at scale 1 = 0.55 x 0.025)
BLOCK = '█'
SHADE = '░'
DOT = '●'


# ------------------------------------------------------------------ grid and rectangles
@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def overlaps(self, o: 'Rect') -> bool:
        return self.x < o.right and o.x < self.right and self.y < o.bottom and o.y < self.bottom

    def inside(self, width: int, height: int) -> bool:
        return self.x >= 0 and self.y >= 0 and self.right <= width and self.bottom <= height

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom


@dataclass(frozen=True)
class Grid:
    cw: int                        # column width, px (one glyph advance)
    lh: int                        # row height, px
    height: int                    # window height, px (the UI unit)
    em_ratio: float = CONSOLAS_EM  # glyph advance / em of the font

    @property
    def text_scale(self) -> float:
        """Ursina `Text(scale=...)` that makes one glyph advance exactly `cw` px."""
        return self.cw / (self.em_ratio * TEXT_SIZE * self.height)

    @property
    def em_px(self) -> float:
        return self.cw / self.em_ratio

    def cols(self, width: int) -> int:
        return width // self.cw

    def rows(self, height: int) -> int:
        return height // self.lh


def make_grid(height: int, em_ratio: float = CONSOLAS_EM, em_div: float = 40.0, leading: float = 2.1) -> Grid:
    """The cell grid for a window `height` px tall: an em of height/em_div px, a column of whole pixels, a row of `leading` columns (2.1 x 0.55 em = 1.16 em, the font's own spacing)."""
    em = height / em_div
    cw = max(6, int(round(em_ratio * em)))
    return Grid(cw, max(int(round(cw * leading)), cw * 2), int(height), em_ratio)


def centered_x(x: int, width: int, text_len: int, cw: int) -> int:
    """Left edge (px) of a text of `text_len` columns centred in [x, x + width): to the pixel, not to the column (a 19-column title in 60 columns would be a whole column off-centre)."""
    return x + (width - text_len * cw) // 2


def px_to_ui_x(px: float, width: int, height: int) -> float:
    return (px - width / 2.0) / height


def px_to_ui_y(py: float, height: int) -> float:
    return (height / 2.0 - py) / height


def ui_to_px(x: float, y: float, width: int, height: int) -> tuple:
    return x * height + width / 2.0, height / 2.0 - y * height


CAP_CENTER_EM = 0.45              # measured in G20 (Consolas in Ursina, 720p / 768p / 1080p: 0.440 / 0.450 / 0.458): the CAPITALS' vertical centre, below the top of the Text


def text_origin_y(row_y: int, grid: Grid) -> int:
    """y (px) of the TOP of a Text so that its capitals are vertically centred in the row [row_y, row_y + lh): the menu and the log are upper case, so this is what "centred" looks like."""
    return int(round(row_y + grid.lh / 2.0 - CAP_CENTER_EM * grid.em_px))


# ------------------------------------------------------------------ fixed-width text
def fit(text: str, width: int, align: str = '<', cut: str = '..') -> str:
    """Exactly `width` characters: padded, or cut with `cut` at the end when too long (a long label never pushes the value column)."""
    if len(text) > width:
        text = text[:max(width - len(cut), 0)] + cut[:width]
    return text.ljust(width) if align == '<' else text.rjust(width) if align == '>' else text.center(width)


def dotted(left: str, status: str, width: int, fill: str = '.') -> str:
    """`left ........ status` in exactly `width` characters (status flush right)."""
    room = width - len(left) - len(status) - 2
    if room < 1:
        left = left[:max(width - len(status) - 3, 0)]
        room = max(width - len(left) - len(status) - 2, 1)
    return f'{left} {fill * room} {status}'


def bar(frac: float, width: int) -> str:
    """A progress bar of `width` cells: `█████░░░░░`."""
    n = int(round(min(max(frac, 0.0), 1.0) * width))
    return BLOCK * n + SHADE * (width - n)


def clock(seconds: float) -> str:
    s = int(max(seconds, 0.0))
    return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


def typed(text: str, elapsed: float, cps: float) -> str:
    """The first characters of `text` after `elapsed` s at `cps` characters / s (cps <= 0: the whole line at once)."""
    if cps <= 0.0:
        return text
    return text[:max(int(elapsed * cps), 0)]


def blink(t: float, hz: float = 1.0, duty: float = 0.6) -> bool:
    """On for `duty` of each period."""
    return (t * hz) % 1.0 < duty


def flicker(t: float, amount: float = 0.025) -> float:
    """CRT brightness factor in [1 - amount, 1]: two slow sines, never a flash."""
    return 1.0 - amount * (0.5 + 0.5 * math.sin(t * 37.1) * math.sin(t * 11.3 + 1.3))


# ------------------------------------------------------------------ panel layout (graphics panel)
PANEL_COLS = 60                   # text columns inside the panel
MARKER_COLS = 2                   # '> ' before a label
VALUE_COLS = 12                   # the value block: arrow, space, value (8), space, arrow
PAD_COLS = 2                      # panel padding left / right, in columns


@dataclass(frozen=True)
class PanelLayout:
    grid: Grid
    width: int
    height: int
    panel: Rect
    text_x: int                   # x of text column 0
    header: Rect
    rule_top: Rect
    options: tuple                # one Rect per option row, full text width
    rule_bottom: Rect
    footer: Rect
    value_col: int                # first column of the value block

    def col_x(self, col: int) -> int:
        return self.text_x + col * self.grid.cw

    def row_at(self, px: float, py: float):
        """Index of the option row under a pixel, or None."""
        for i, r in enumerate(self.options):
            if r.contains(px, py):
                return i
        return None


def panel_layout(width: int, height: int, n_options: int, grid: Grid = None, em_ratio: float = CONSOLAS_EM) -> PanelLayout:
    """The panel centred in the window. Grows with the window height; when it would not fit, the grid shrinks (never overflows)."""
    div = 40.0
    while True:
        g = grid or make_grid(height, em_ratio=em_ratio, em_div=div)
        pad_x, pad_y, gap = PAD_COLS * g.cw, g.lh // 2, g.lh // 2
        pw = PANEL_COLS * g.cw + 2 * pad_x
        ph = pad_y * 2 + g.lh * (n_options + 2) + gap * 2
        if grid is not None or (pw <= width * 0.96 and ph <= height * 0.94) or div >= 90:
            break
        div += 2.0
    x, y = (width - pw) // 2, (height - ph) // 2
    tx = x + pad_x
    inner = PANEL_COLS * g.cw
    thick = max(1, g.cw // 8)
    cy = y + pad_y
    header = Rect(tx, cy, inner, g.lh)
    cy += g.lh
    rule_top = Rect(tx, cy + (gap - thick) // 2, inner, thick)
    cy += gap
    options = tuple(Rect(tx, cy + i * g.lh, inner, g.lh) for i in range(n_options))
    cy += n_options * g.lh
    rule_bottom = Rect(tx, cy + (gap - thick) // 2, inner, thick)
    cy += gap
    footer = Rect(tx, cy, inner, g.lh)
    return PanelLayout(g, width, height, Rect(x, y, pw, ph), tx, header, rule_top, options, rule_bottom, footer, PANEL_COLS - VALUE_COLS)


def value_field(text: str, selected: bool) -> str:
    """The VALUE_COLS-wide value block: the arrows sit at fixed columns (0 and last), the value always starts at column 2, so a changing value never moves anything."""
    body = fit(text, VALUE_COLS - 4)
    return f'◄ {body} ►' if selected else f'  {body}  '


def option_line(label: str, marker: bool, value: str, selected: bool, label_cols: int = PANEL_COLS - VALUE_COLS - MARKER_COLS) -> tuple:
    """(marker + label, value block): two strings of fixed width; the layout puts the second at `value_col`."""
    return ('> ' if marker else '  ') + fit(label, label_cols), value_field(value, selected)


# ------------------------------------------------------------------ splash layout
BLOCK_COLS = 84                   # width of the log block in columns


@dataclass(frozen=True)
class SplashLayout:
    grid: Grid
    width: int
    height: int
    block_cols: int
    x0: int                       # x of column 0 of the block (block centred)
    top: Rect                     # classification banner, full width
    bottom: Rect
    head_y: int                   # y of the first header row
    head_rows: int
    log_y: int                    # y of the first log row
    log_rows: int
    bar_y: int                    # y of the progress row
    hint_y: int                   # y of the key hint row (just above the bottom banner)

    def col_x(self, col: int) -> int:
        return self.x0 + col * self.grid.cw

    def row_y(self, i: int) -> int:
        return self.log_y + i * self.grid.lh


def splash_layout(width: int, height: int, grid: Grid = None) -> SplashLayout:
    g = grid or make_grid(height, em_div=42.0)
    cols = min(BLOCK_COLS, max(g.cols(width) - 4, 40))
    x0 = (width - cols * g.cw) // 2
    top = Rect(0, 0, width, g.lh)
    bottom = Rect(0, height - g.lh, width, g.lh)                  # flush with the bottom edge like the top banner is with the top (a grid from the top would leave a black gap)
    hint_y = bottom.y - g.lh - g.lh // 2                           # bottom-up: banner, half a row, hint, half a row, progress bar
    bar_y = hint_y - g.lh - g.lh // 2
    head_y, head_rows = g.lh * 2, 4
    log_y = head_y + g.lh * head_rows + g.lh // 2
    log_rows = max((bar_y - g.lh // 2 - log_y) // g.lh, 4)
    return SplashLayout(g, width, height, cols, x0, top, bottom, head_y, head_rows, log_y, log_rows, bar_y, hint_y)


# ------------------------------------------------------------------ splash script
STATUS_PENDING = '[ .... ]'
STATUS_OK = '[  OK  ]'
STATUS_WARN = '[ WARN ]'
STATUS_FAIL = '[ FAIL ]'
STAMP_COLS = 10                   # '[ 12.345] '
FINALE_HOLD = 0.9                 # s the finished screen stays before the hand-over to the game
SKIP_HOLD = 0.3
KEY_GRACE = 0.4                   # s after the load ends in which a key does not skip (keys pressed while loading arrive in the first frame)
LOAD_LINE_CPS = 0.0               # load stage lines appear whole (the thread is busy loading; a half-typed line would freeze on screen)
FINALE_CPS = 150.0


@dataclass
class TermLine:
    text: str
    kind: str = 'log'             # log | head | dim | ok | warn | err | key | blank | rec
    born: float = 0.0             # s the line starts to appear
    cps: float = 0.0              # typing speed (0 = whole)
    cue: str = ''                 # sound to play when the line appears
    pending: bool = False         # a stage line still waiting for its status
    label: str = ''               # stage label (to rebuild the line when it finishes)
    stamp: str = ''
    cued: bool = False


def banner_lines(build: str, unit: str) -> tuple:
    """The four header rows of the splash."""
    return ('FIELD TERMINAL // BODY-WORN CAMERA INTERFACE',
            f'UNIT {unit}    BUILD {build}',
            'CLASSIFICATION: UNCLASSIFIED // TRAINING SIMULATION',
            'ALL ACTIVITY IS RECORDED')


CONTROL_CELL = 18                 # width of one cell of the controls table, in columns
CONTROL_ROWS = (
    ('W A S D  MOVE', 'SHIFT  SPRINT', 'CTRL / C  CROUCH', 'SPACE  JUMP'),
    ('MOUSE  AIM', 'L-CLICK  FIRE', 'R-CLICK  SIGHTS', 'R  RELOAD'),
    ('1 2 3  WEAPON', 'B  FIRE MODE', 'E  ACTION', 'F1  PARAMETERS'),
)


def finale_script(facts: dict) -> list:
    """The fixed ending: (offset s, kind, text, cps, cue, stamped). `facts` carries the real values read by the game layer (storage, power, time, audio...).
    `stamped` lines get the same `[ 12.345] ` time stamp as the load lines (so the status column is one column for the whole screen); table rows are indented under the messages."""
    w = BLOCK_COLS - STAMP_COLS
    table = [(1.86 + 0.14 * i, 'dim', ''.join(fit(c, CONTROL_CELL) for c in row).rstrip(), FINALE_CPS, '', False) for i, row in enumerate(CONTROL_ROWS)]
    return [
        (0.00, 'blank', '', 0.0, '', False),
        (0.05, 'head', '>> FIELD CHECK', FINALE_CPS, 'blip', False),
        (0.28, 'ok', dotted('VERIFY OPERATOR ID', 'RECON-1  AUTHORIZED', w), FINALE_CPS, 'ok', True),
        (0.50, 'ok', dotted('OPTICS CALIBRATION', 'NOMINAL', w), FINALE_CPS, 'ok', True),
        (0.72, 'ok', dotted('TIME BASE', facts.get('time', 'LOCKED'), w), FINALE_CPS, 'ok', True),
        (0.94, 'ok', dotted('STORAGE', facts.get('storage', 'NOMINAL'), w), FINALE_CPS, 'ok', True),
        (1.16, 'ok', dotted('POWER', facts.get('power', 'NOMINAL'), w), FINALE_CPS, 'ok', True),
        (1.38, 'ok', dotted('AUDIO', facts.get('audio', 'ON'), w), FINALE_CPS, 'ok', True),
        (1.62, 'blank', '', 0.0, '', False),
        (1.66, 'head', '>> CONTROLS', FINALE_CPS, 'blip', False),
        *table,
        (2.28, 'key', 'ESC  VIDEO CONFIGURATION', FINALE_CPS, '', False),
        (2.62, 'blank', '', 0.0, '', False),
        (2.66, 'ok', dotted('RECORDING', 'ARMED', w), FINALE_CPS, 'relay', True),
        (3.16, 'rec', f'{DOT} REC', 0.0, 'rec', False),
    ]


def finale_length(script: list) -> float:
    last = max(row[0] + (len(row[2]) / row[3] if row[3] > 0 else 0.0) for row in script)
    return last + FINALE_HOLD


class BootSeq:
    """The splash timeline. Phase `load`: the game announces each real step (`stage`), the previous one gets its status; `load_done` starts the fixed finale
    (`finale_script`); `skip` fast-forwards it; `done` says when to hand over to the game. Nothing here touches Ursina."""

    def __init__(self, t0: float = 0.0, build: str = '2026.11.12', unit: str = 'BWC-07'):
        self.t0 = t0
        self.build, self.unit = build, unit
        self.lines = []
        self.phase = 'load'               # load | finale | done
        self.progress = 0.0               # 0..1 of the load bar
        self.finale_end = None            # s: when the finale ends (hand-over time)
        self.finale_start = None
        self.skipped = False
        self._chars_seen = 0

    # --- load phase ---
    def stage(self, label: str, t: float, progress: float = None):
        """A real load step starts: the pending one finishes OK, a new pending line appears."""
        self._finish_pending(t, STATUS_OK)
        self.lines.append(TermLine('', 'log', t, LOAD_LINE_CPS, '', True, label, f'[{max(t - self.t0, 0.0):7.3f}] '))
        self._rebuild(self.lines[-1])
        if progress is not None:
            self.progress = min(max(progress, 0.0), 1.0)

    def note(self, text: str, t: float, kind: str = 'dim'):
        self.lines.append(TermLine(text, kind, t, 0.0))

    def retitle(self, label: str, progress: float = None):
        """The running stage reports more detail (the light bake: `LIGHT BAKE 42%`): its line is rebuilt in place, same width, same stamp."""
        for ln in self.lines:
            if ln.pending:
                ln.label = label
                self._rebuild(ln)
        if progress is not None:
            self.progress = min(max(progress, 0.0), 1.0)

    def warn(self, text: str, t: float):
        self._finish_pending(t, STATUS_OK)
        self.lines.append(TermLine(text, 'warn', t, 0.0))

    def _finish_pending(self, t: float, status: str):
        for ln in self.lines:
            if ln.pending:
                ln.pending = False
                ln.cue = ln.cue or 'ok'
                ln.cued = False
                ln.born = t
                self._rebuild(ln, status)

    def _rebuild(self, ln: TermLine, status: str = STATUS_PENDING):
        ln.text = dotted(ln.stamp + ln.label, status, BLOCK_COLS)
        ln.kind = 'ok' if status == STATUS_OK else 'warn' if status == STATUS_WARN else 'err' if status == STATUS_FAIL else 'log'

    def load_done(self, t: float, facts: dict):
        """The game is built: finish the last stage and schedule the fixed finale."""
        self._finish_pending(t, STATUS_OK)
        self.progress = 1.0
        self.phase = 'finale'
        self.finale_start = t
        script = finale_script(facts)
        for off, kind, text, cps, cue, stamped in script:
            born = t + off
            if stamped:
                text = f'[{max(born - self.t0, 0.0):7.3f}] ' + text
            elif kind in ('dim', 'key'):
                text = ' ' * STAMP_COLS + text                 # table rows start under the messages
            self.lines.append(TermLine(text, kind, born, cps, cue))
        self.finale_end = t + finale_length(script)

    # --- finale ---
    def can_skip(self, t: float) -> bool:
        return self.phase == 'finale' and self.finale_start is not None and t - self.finale_start >= KEY_GRACE and not self.skipped

    def skip(self, t: float) -> bool:
        """Show the rest at once and finish in SKIP_HOLD s. False when a skip is not allowed now (still loading, or too soon after the load: queued keys)."""
        if not self.can_skip(t):
            return False
        self.skipped = True
        for ln in self.lines:
            if ln.born > t:
                ln.born = t
            ln.cps = 0.0
        self.finale_end = t + SKIP_HOLD
        return True

    def update(self, t: float):
        if self.phase == 'finale' and self.finale_end is not None and t >= self.finale_end:
            self.phase = 'done'

    @property
    def done(self) -> bool:
        return self.phase == 'done'

    # --- what to draw / play ---
    def visible(self, t: float, rows: int) -> list:
        """The last `rows` lines born by `t`, typed so far: [(text, kind, finished typing)]."""
        out = []
        for ln in self.lines:
            if ln.born > t:
                continue
            shown = typed(ln.text, t - ln.born, ln.cps)
            out.append((shown, ln.kind, len(shown) >= len(ln.text)))
        return out[-rows:]

    def total_chars(self, t: float) -> int:
        """Characters typed so far over all lines (the game ticks a key sound as it grows)."""
        n = 0
        for ln in self.lines:
            if ln.born <= t and ln.cps > 0.0:
                n += len(typed(ln.text, t - ln.born, ln.cps))
        return n

    def poll_cues(self, t: float) -> list:
        """Sound cues of the lines born since the last call (each once)."""
        out = []
        for ln in self.lines:
            if ln.born <= t and ln.cue and not ln.cued and not ln.pending:
                ln.cued = True
                out.append(ln.cue)
        return out

    def hint(self, t: float) -> str:
        if self.phase == 'load':
            return ''
        return 'ANY KEY: CONTINUE' if self.phase == 'finale' else ''
