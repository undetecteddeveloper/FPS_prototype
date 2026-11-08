"""Debug panel (F1): sliders that edit every parameter live, the bullet-spread cone, save / load / reset.

The Ursina-free data and logic live in `fps/core/params.py` (ParamStore: builds sliders from weapon_data, saves / loads JSON) and
`fps/core/param_meta.py` (Vietnamese labels, hints, slider ranges). This module only draws and handles the mouse:

- Left panel: 11 groups (tabs), each with a scrollable list of rows (mouse wheel or drag the scrollbar). Only `ROWS` item rows exist,
  reassigned as the list scrolls, so a long group costs no more objects than a short one. Left-drag a slider / click a toggle, right-click resets to default.
- Right card: the spread cone cross-section at a 25 m target (a ring per state, the current ring including bloom, dots for the recent shots), bloom bar.
  Angles come from the `Accuracy` (spread.py) of Combat; they are not recomputed here.
- Built LAZILY on the first open; when closed `root.enabled = False` and `Game.update` calls nothing (cost ~0).
- Mouse hits use rectangle tests in UI coordinates (not Ursina colliders); the pointer comes from `self.pointer` so selftests can simulate it.
"""
import math

from ursina import Entity, camera, color, mouse, window
from ursina.models.procedural.circle import Circle

from fps.core.movement import MoveState
from fps.core.params import ParamSpec, format_number, format_value
from fps.core.spread import ring_radius, shot_offset
from fps.game.hud import UiText

ROWS = 12                      # number of item rows (longer lists scroll)
ROW_H = 0.0535
PANEL_W = 0.66
CARD_W = 0.40
CONE_DISTANCE = 25.0           # m: the cone cross-section is drawn at this target distance
CONE_VIEW = 5.0                # m: radius of the drawn disc (fixed, so dragging a slider really changes the rings instead of rescaling them)
DOT_COUNT = 40

# depth layers (negative z = closer to the camera; HUD at z = 0)
Z_BG, Z_WIDGET, Z_FILL, Z_HANDLE, Z_TEXT = -0.10, -0.12, -0.13, -0.14, -0.16

BG = color.rgba(0.040, 0.047, 0.062, 0.95)
CARD_BG = color.rgba(0.040, 0.047, 0.062, 0.88)
LINE = color.rgba(1, 1, 1, 0.10)
TRACK = color.rgba(1, 1, 1, 0.16)
ACCENT = color.rgb(0.36, 0.76, 1.0)
ACCENT_DIM = color.rgba(0.36, 0.76, 1.0, 0.55)
AMBER = color.rgb(1.0, 0.78, 0.36)
ORANGE = color.rgb(1.0, 0.62, 0.42)
WHITE = color.rgba(1, 1, 1, 0.94)
FAINT = color.rgba(1, 1, 1, 0.52)
BUTTON = color.rgba(1, 1, 1, 0.09)
BUTTON_HOVER = color.rgba(1, 1, 1, 0.18)
TAB_ACTIVE = color.rgba(0.36, 0.76, 1.0, 0.28)

# (name, state, ads) of the rings on the cone; distinct colours so each ring can be matched to its state
CONE_STATES = (
    ('Đứng', MoveState.IDLE, 0.0, color.rgb(0.55, 0.85, 1.0)),
    ('Đi', MoveState.WALK, 0.0, color.rgb(0.55, 1.0, 0.7)),
    ('Chạy', MoveState.SPRINT, 0.0, color.rgb(1.0, 0.85, 0.45)),
    ('Nhảy', MoveState.AIR, 0.0, color.rgb(1.0, 0.55, 0.45)),
    ('Ngồi', MoveState.CROUCH_IDLE, 0.0, color.rgb(0.75, 0.6, 1.0)),
    ('Ngắm', MoveState.IDLE, 1.0, color.rgb(1.0, 1.0, 1.0)),
    ('Ngắm đi', MoveState.WALK, 1.0, color.rgb(0.8, 0.8, 0.8)),
)
STATE_ROW = {MoveState.IDLE: 0, MoveState.WALK: 1, MoveState.SPRINT: 2, MoveState.AIR: 3, MoveState.CROUCH_IDLE: 4, MoveState.CROUCH_WALK: 4}
ADS_ROW = {True: 6, False: 5}


def _tint(ui: UiText, col):
    """Set the text colour ONLY when it changes: each colour set makes Panda's TextNode rebuild the glyphs (~0.3 ms), so never do it every frame."""
    if getattr(ui, '_tint_cache', None) != col:
        ui._tint_cache = col
        ui.main.color = col


def _quad(parent, x0, y0, x1, y1, col, z=Z_WIDGET) -> Entity:
    return Entity(parent=parent, model='quad', color=col, position=((x0 + x1) / 2, (y0 + y1) / 2, z), scale=(x1 - x0, y1 - y0))


def _set_rect(e: Entity, x0, y0, x1, y1):
    e.x, e.y = (x0 + x1) / 2, (y0 + y1) / 2
    e.scale = (max(x1 - x0, 1e-5), max(y1 - y0, 1e-5))


class _Button:
    """Rectangular button: clicking it calls `callback`."""

    def __init__(self, panel, x0, y0, x1, y1, label, callback, scale=0.85):
        self.rect = (x0, y0, x1, y1)
        self.callback = callback
        self.bg = _quad(panel.root, x0, y0, x1, y1, BUTTON)
        self.text = UiText(label, ((x0 + x1) / 2, (y0 + y1) / 2), origin=(0, 0), scale=scale, tint=WHITE, shadow=False,
                           parent=panel.root, z=Z_TEXT)
        self.active = False
        self.hover = False
        self.enabled = True

    def set_enabled(self, value: bool):
        self.enabled = value
        self.bg.enabled = value
        self.text.enabled = value

    def contains(self, x, y) -> bool:
        x0, y0, x1, y1 = self.rect
        return self.enabled and x0 <= x <= x1 and y0 <= y <= y1

    def style(self, hover: bool = None, active: bool = None):
        if hover is not None:
            self.hover = hover
        if active is not None:
            self.active = active
        col = TAB_ACTIVE if self.active else (BUTTON_HOVER if self.hover else BUTTON)
        if col != getattr(self, '_col', None):
            self._col = col
            self.bg.color = col


class _Row:
    """One list row: a section header, or a slider / toggle."""

    def __init__(self, panel, i):
        self.panel, self.i = panel, i
        self.y_top = panel.rows_top - i * ROW_H
        x0, tx0, tx1 = panel.x0 + 0.018, panel.track_x0, panel.track_x1
        yc = self.y_top - 0.0155
        self.item = None
        self.cache = None
        self.label = UiText('', (x0, yc), origin=(-0.5, 0), scale=0.85, tint=WHITE, shadow=False, parent=panel.root, z=Z_TEXT)
        self.hint = UiText('', (x0, self.y_top - 0.0395), origin=(-0.5, 0), scale=0.75, tint=FAINT, shadow=False, parent=panel.root, z=Z_TEXT)
        self.value = UiText('', (panel.value_x, yc), origin=(0.5, 0), scale=0.85, tint=WHITE, shadow=False, parent=panel.root, z=Z_TEXT)
        self.track = _quad(panel.root, tx0, yc - 0.0025, tx1, yc + 0.0025, TRACK)
        self.fill = _quad(panel.root, tx0, yc - 0.0025, tx0 + 0.001, yc + 0.0025, ACCENT_DIM, Z_FILL)
        self.tick = _quad(panel.root, tx0, yc - 0.008, tx0 + 0.0015, yc + 0.008, color.rgba(1, 1, 1, 0.42), Z_FILL)
        self.handle = _quad(panel.root, tx0, yc - 0.011, tx0 + 0.007, yc + 0.011, WHITE, Z_HANDLE)
        self.toggle = _quad(panel.root, tx0, yc - 0.012, tx1, yc + 0.012, BUTTON, Z_WIDGET)
        self.mark = _quad(panel.root, panel.x0 + 0.004, self.y_top - 0.040, panel.x0 + 0.0075, self.y_top - 0.004, AMBER, Z_FILL)
        self.rule = _quad(panel.root, x0, self.y_top - 0.0415, panel.x1 - 0.03, self.y_top - 0.0405, LINE)
        self.yc = yc
        self.bind(None)

    def bind(self, item):
        self.item = item
        self.cache = None
        header = isinstance(item, tuple)
        spec = item if isinstance(item, ParamSpec) else None
        slider = spec is not None and spec.kind in ('float', 'int')
        toggle = spec is not None and not slider
        for e in (self.track, self.fill, self.tick, self.handle):
            e.enabled = slider
        self.toggle.enabled = toggle
        self.mark.enabled = False
        self.rule.enabled = header
        self.value.enabled = spec is not None
        self.hint.enabled = spec is not None
        self.label.enabled = item is not None
        if header:
            self.label.text = item[1]
            _tint(self.label, ACCENT)
            self.label.main.y = self.y_top - 0.027
        elif spec is not None:
            self.label.main.y = self.yc
            self.label.text = spec.label
            _tint(self.label, WHITE)
            self.hint.text = spec.hint + ('  ·  cần khởi động lại' if spec.restart else '')
            _tint(self.hint, ORANGE if spec.restart else FAINT)
            self.refresh()

    def frac(self, spec, v) -> float:
        return 0.0 if spec.hi == spec.lo else min(max((v - spec.lo) / (spec.hi - spec.lo), 0.0), 1.0)

    def refresh(self):
        spec = self.item
        if not isinstance(spec, ParamSpec):
            return
        store, p = self.panel.store, self.panel
        v = store.get(spec)
        default = store.default_of(spec)               # the gun IN HAND's number for gun sliders
        changed = not store.is_default(spec)
        key = (v, changed, default)
        if key == self.cache:
            return
        self.cache = key
        self.value.text = format_value(spec, v)
        _tint(self.value, AMBER if changed else WHITE)
        self.mark.enabled = changed
        tx0, tx1 = p.track_x0, p.track_x1
        if spec.kind in ('float', 'int'):
            x = tx0 + (tx1 - tx0) * self.frac(spec, v)
            _set_rect(self.fill, tx0, self.yc - 0.0025, x, self.yc + 0.0025)
            self.handle.x = x
            self.fill.color = AMBER if changed else ACCENT_DIM
            self.tick.x = tx0 + (tx1 - tx0) * self.frac(spec, default)
            self.tick.enabled = changed
        else:
            on = bool(v) if spec.kind == 'bool' else v is not False
            self.toggle.color = color.rgba(0.36, 0.76, 1.0, 0.45) if on else BUTTON


class DebugPanel:
    def __init__(self, game, store, preset_path):
        self.game = game
        self.store = store
        self.path = preset_path
        self.is_open = False
        self.manage_mouse = True
        self.pointer = lambda: (mouse.x, mouse.y)        # selftest replaces this with a function returning fake coordinates
        self.group = store.groups[0].key
        self.show_advanced = False
        self.offset = 0
        self.items = []
        self._drag = None                                 # ('slider', spec) or ('scroll',)
        self._built = False
        self._hidden_hud = []
        self._fps_frames, self._fps_time = 0, 0.0
        self.message = ''
        self.shots_seen = 0
        self.dots = []

    # --- build (lazy: on the first open) ---
    def _build(self):
        a = window.aspect_ratio
        self.x0, self.x1 = -a / 2, -a / 2 + PANEL_W
        self.rows_top = 0.5 - 0.072 - 2 * 0.038 - 0.062
        self.track_x0, self.track_x1 = self.x0 + 0.325, self.x0 + 0.515
        self.value_x = self.x1 - 0.055
        self.rows_bottom = self.rows_top - ROWS * ROW_H
        self.root = Entity(parent=camera.ui, enabled=False)
        r = self.root
        x0, x1 = self.x0, self.x1

        _quad(r, x0, -0.5, x1, 0.5, BG, Z_BG)
        _quad(r, x1, -0.5, x1 + 0.0015, 0.5, color.rgba(0.36, 0.76, 1.0, 0.35), Z_BG)
        self.title = UiText('BẢNG CHỈNH THÔNG SỐ', (x0 + 0.018, 0.5 - 0.026), origin=(-0.5, 0), scale=1.05, tint=WHITE, shadow=False, parent=r, z=Z_TEXT)
        self.fps_text = UiText('', (x1 - 0.018, 0.5 - 0.026), origin=(0.5, 0), scale=0.85, tint=FAINT, shadow=False, parent=r, z=Z_TEXT)
        UiText('Kéo thanh để chỉnh  ·  chuột phải: về mặc định  ·  lăn chuột: cuộn  ·  F1 / Esc: đóng',
               (x0 + 0.018, 0.5 - 0.054), origin=(-0.5, 0), scale=0.75, tint=FAINT, shadow=False, parent=r, z=Z_TEXT)

        # the game has no HUD: key hints and the credit are shown here, bottom-right of the screen
        br = window.bottom_right
        UiText('R nạp đạn   ·   B đổi chế độ bắn   ·   Esc nhả chuột   ·   Alt+F4 thoát game', br + (-0.02, 0.040), origin=(0.5, -0.5), scale=0.8, tint=FAINT, parent=r, z=Z_TEXT)
        self.credit = UiText(self.game.params.gun.credit, br + (-0.02, 0.014), origin=(0.5, -0.5), scale=0.75, tint=FAINT, parent=r, z=Z_TEXT)

        # group tabs: two rows
        self.tabs = []
        per_row = 6
        tab_w = (PANEL_W - 0.036) / per_row
        for n, g in enumerate(self.store.groups):
            row, col = divmod(n, per_row)
            tx = x0 + 0.018 + col * tab_w
            ty = 0.5 - 0.072 - row * 0.038
            b = _Button(self, tx + 0.002, ty - 0.034, tx + tab_w - 0.002, ty, g.title, lambda k=g.key: self.select_group(k))
            b.key = g.key
            self.tabs.append(b)

        # group name row + group buttons
        ay = self.rows_top + 0.026
        self.group_title = UiText('', (x0 + 0.018, ay), origin=(-0.5, 0), scale=1.0, tint=WHITE, shadow=False, parent=r, z=Z_TEXT)
        self.group_count = UiText('', (x0 + 0.16, ay), origin=(-0.5, 0), scale=0.75, tint=FAINT, shadow=False, parent=r, z=Z_TEXT)
        self.btn_advanced = _Button(self, x1 - 0.30, ay - 0.0145, x1 - 0.165, ay + 0.0145, '', self.toggle_advanced, 0.75)
        self.btn_reset_group = _Button(self, x1 - 0.158, ay - 0.0145, x1 - 0.03, ay + 0.0145, 'Đặt lại nhóm này', self.reset_group, 0.75)

        # row list + scrollbar
        self.rows = [_Row(self, i) for i in range(ROWS)]
        self.hover_bar = _quad(r, x0 + 0.01, 0, x1 - 0.026, 0, color.rgba(1, 1, 1, 0.05), Z_BG - 0.005)
        self.hover_bar.enabled = False
        self.scroll_x0, self.scroll_x1 = x1 - 0.020, x1 - 0.012
        self.scroll_track = _quad(r, self.scroll_x0, self.rows_bottom, self.scroll_x1, self.rows_top, LINE)
        self.scroll_thumb = _quad(r, self.scroll_x0, self.rows_bottom, self.scroll_x1, self.rows_top, color.rgba(1, 1, 1, 0.34), Z_FILL)

        # panel footer
        fy = self.rows_bottom - 0.014
        bw = (PANEL_W - 0.036 - 0.012) / 3
        names = (('Lưu', self.save), ('Nạp', self.load), ('Mặc định súng này', self.reset_all))
        self.footer = []
        for n, (text, fn) in enumerate(names):
            bx = x0 + 0.018 + n * (bw + 0.006)
            self.footer.append(_Button(self, bx, fy - 0.036, bx + bw, fy, text, fn, 0.9))
        self.status = UiText('', (x0 + 0.018, fy - 0.062), origin=(-0.5, 0), scale=0.8, tint=FAINT, shadow=False, parent=r, z=Z_TEXT)
        self.note = UiText('Mục "cần khởi động lại": bấm Lưu rồi chạy lại game.',
                           (x0 + 0.018, fy - 0.088), origin=(-0.5, 0), scale=0.75, tint=FAINT, shadow=False, parent=r, z=Z_TEXT)

        self._build_cone()
        self.buttons = self.tabs + [self.btn_advanced, self.btn_reset_group] + self.footer
        self._built = True
        self.select_group(self.group, force=True)

    def _build_cone(self):
        a = window.aspect_ratio
        self.cx1 = a / 2 - 0.012
        self.cx0 = self.cx1 - CARD_W
        r = self.root
        top = 0.5 - 0.012
        card_bottom = -0.205
        _quad(r, self.cx0, card_bottom, self.cx1, top, CARD_BG, Z_BG)
        mid = (self.cx0 + self.cx1) / 2
        UiText('Hình nón tản đạn', (self.cx0 + 0.016, top - 0.026), origin=(-0.5, 0), scale=1.0, tint=WHITE, shadow=False, parent=r, z=Z_TEXT)
        UiText(f'Mặt cắt tại bia {CONE_DISTANCE:.0f} m, mỗi vòng xám = 1 m', (self.cx0 + 0.016, top - 0.052), origin=(-0.5, 0),
               scale=0.75, tint=FAINT, shadow=False, parent=r, z=Z_TEXT)
        self.cone_r = 0.145                               # disc radius on screen (UI)
        self.cone_cx, self.cone_cy = mid, top - 0.075 - self.cone_r - 0.004
        self.cone_k = self.cone_r / CONE_VIEW             # UI units per metre
        ring = Circle(64, mode='line', thickness=1)
        disk = Circle(48)
        for m in range(1, int(CONE_VIEW) + 1):
            Entity(parent=r, model=ring, position=(self.cone_cx, self.cone_cy, Z_WIDGET), scale=2 * m * self.cone_k,
                   color=color.rgba(1, 1, 1, 0.16 if m == int(CONE_VIEW) else 0.07))
        for dx, dy in ((1, 0), (0, 1)):                   # horizontal / vertical axis
            _quad(r, self.cone_cx - self.cone_r * dx - 0.0005 * dy, self.cone_cy - self.cone_r * dy - 0.0005 * dx,
                  self.cone_cx + self.cone_r * dx + 0.0005 * dy, self.cone_cy + self.cone_r * dy + 0.0005 * dx, color.rgba(1, 1, 1, 0.07))
        self.cur_fill = Entity(parent=r, model=disk, position=(self.cone_cx, self.cone_cy, Z_WIDGET - 0.005), color=color.rgba(1, 1, 1, 0.12))
        self.cur_ring = Entity(parent=r, model=Circle(64, mode='line', thickness=2.5), position=(self.cone_cx, self.cone_cy, Z_FILL - 0.005),
                               color=color.rgba(1, 1, 1, 0.95))
        self.state_rings = []
        for name, state, ads, col in CONE_STATES:
            self.state_rings.append(Entity(parent=r, model=Circle(64, mode='line', thickness=1.2),
                                           position=(self.cone_cx, self.cone_cy, Z_FILL), color=color.rgba(col.r, col.g, col.b, 0.85)))
        self.dots = []
        for _ in range(DOT_COUNT):
            d = _quad(r, 0, 0, 0.006, 0.006, color.rgba(1, 0.55, 0.3, 0.0), Z_HANDLE - 0.005)
            d.enabled = False
            self.dots.append(d)
        self.dot_next = 0

        # legend: swatch + name (left) + angle / metres (right)
        y = self.cone_cy - self.cone_r - 0.030
        self.legend = []
        for name, state, ads, col in CONE_STATES:
            sw = _quad(r, self.cx0 + 0.016, y - 0.005, self.cx0 + 0.030, y + 0.005, col, Z_WIDGET)
            nm = UiText(name, (self.cx0 + 0.042, y), origin=(-0.5, 0), scale=0.85, tint=WHITE, shadow=False, parent=r, z=Z_TEXT)
            vl = UiText('', (self.cx1 - 0.016, y), origin=(0.5, 0), scale=0.85, tint=WHITE, shadow=False, parent=r, z=Z_TEXT)
            self.legend.append((sw, nm, vl))
            y -= 0.0275
        y -= 0.006
        UiText('Bloom', (self.cx0 + 0.016, y), origin=(-0.5, 0), scale=0.85, tint=WHITE, shadow=False, parent=r, z=Z_TEXT)
        self.bloom_x0, self.bloom_x1 = self.cx0 + 0.085, self.cx1 - 0.135
        _quad(r, self.bloom_x0, y - 0.003, self.bloom_x1, y + 0.003, TRACK)
        self.bloom_fill = _quad(r, self.bloom_x0, y - 0.003, self.bloom_x0 + 0.001, y + 0.003, AMBER, Z_FILL)
        self.bloom_text = UiText('', (self.cx1 - 0.016, y), origin=(0.5, 0), scale=0.85, tint=WHITE, shadow=False, parent=r, z=Z_TEXT)
        y -= 0.034
        self.now_text = UiText('', (self.cx0 + 0.016, y), origin=(-0.5, 0), scale=0.9, tint=WHITE, shadow=False, parent=r, z=Z_TEXT)
        y -= 0.026
        self.now_sub = UiText('', (self.cx0 + 0.016, y), origin=(-0.5, 0), scale=0.75, tint=FAINT, shadow=False, parent=r, z=Z_TEXT)

    # --- open / close ---
    def toggle(self):
        self.hide() if self.is_open else self.show()

    def show(self):
        if self.is_open:
            return
        if not self._built:
            self._build()
        self.is_open = True
        self.root.enabled = True
        g = self.game
        g.player.ui_open = True
        g.combat.pressed = False
        if self.manage_mouse:
            mouse.locked = False
        hud = g.hud                                        # text in the bottom / left corners sits under the panel: hide it so it does not show through the background
        self._hidden_hud = [t for t in (hud.fps_text, hud.hint, hud.credit) if t.enabled] if hud else []
        for t in self._hidden_hud:
            t.enabled = False
        gun = g.params.gun                                 # the panel edits the gun in hand (its own defaults): say which one
        self.title.text = f'BẢNG CHỈNH THÔNG SỐ  ·  {gun.name}'
        self.credit.text = gun.credit
        self._refresh_all()

    def hide(self):
        if not self.is_open:
            return
        self.is_open = False
        self._drag = None
        self.root.enabled = False
        g = self.game
        g.player.ui_open = False
        g.combat.pressed = False
        if self.manage_mouse:
            mouse.position = (0, 0)                        # centre the pointer before locking, so the jump from the slider position does not turn into a large camera turn
            mouse.prev_x = mouse.prev_y = 0
            mouse.locked = True
        for t in self._hidden_hud:
            t.enabled = True
        self._hidden_hud = []

    # --- button actions ---
    def select_group(self, key: str, force: bool = False):
        if key == self.group and not force:
            return
        self.group = key
        self.offset = 0
        self._rebuild_items()
        self._refresh_all()

    def toggle_advanced(self):
        self.show_advanced = not self.show_advanced
        self.offset = 0
        self._rebuild_items()
        self._refresh_all()

    def reset_group(self):
        n = self.store.reset_group(self.group)
        self._say(f'Đã đặt lại {n} thanh của nhóm này về mặc định.' if n else 'Nhóm này đang ở mặc định rồi.', ok=True)
        self._refresh_all()

    def reset_all(self):
        n = self.store.reset_all()
        name = self.game.params.gun.name
        self._say(f'Đã đặt lại {n} thanh của {name} về mặc định.' if n else f'Mọi thanh của {name} đang ở mặc định rồi.', ok=True)
        self._refresh_all()

    def save(self):
        rep = self.store.save(self.path)
        self._say(rep.message[0].upper() + rep.message[1:] + '.', ok=rep.ok)

    def load(self):
        rep = self.store.load(self.path)
        self._say(rep.message[0].upper() + rep.message[1:] + '.', ok=rep.ok)
        self._refresh_all()

    def _say(self, text: str, ok: bool):
        self.message = text
        self.status.text = text
        _tint(self.status, color.rgb(0.55, 0.95, 0.6) if ok else color.rgb(1.0, 0.5, 0.45))

    # --- list ---
    def _rebuild_items(self):
        g = self.store.group_by_key[self.group]
        self.items = []
        for title, specs in g.sections(self.show_advanced):
            self.items.append(('header', title))
            self.items.extend(specs)

    def _bind_rows(self):
        self.offset = max(0, min(self.offset, len(self.items) - ROWS))
        for i, row in enumerate(self.rows):
            n = self.offset + i
            row.bind(self.items[n] if n < len(self.items) else None)
        self._update_scrollbar()

    def _update_scrollbar(self):
        total = len(self.items)
        h = self.rows_top - self.rows_bottom
        self.scroll_track.enabled = self.scroll_thumb.enabled = total > ROWS
        if total > ROWS:
            thumb = max(h * ROWS / total, 0.04)
            top = self.rows_top - (h - thumb) * self.offset / (total - ROWS)
            _set_rect(self.scroll_thumb, self.scroll_x0, top - thumb, self.scroll_x1, top)

    def _refresh_all(self):
        if not self._built:
            return
        g = self.store.group_by_key[self.group]
        self._bind_rows()
        self.group_title.text = g.title
        hidden = sum(1 for s in g.specs if s.advanced)
        self.btn_advanced.set_enabled(hidden > 0)
        self.btn_advanced.text.text = 'Ẩn nâng cao' if self.show_advanced else f'Nâng cao (+{hidden})'
        self._update_counts()
        for b in self.tabs:
            b.style(active=b.key == self.group)

    def _update_counts(self):
        """One pass over all sliders: changed-slider count per group -> dot on its tab, and the changed-count line (UI label) for the group being viewed."""
        counts = {g.key: 0 for g in self.store.groups}
        for s in self.store.changed_specs():
            counts[s.group] += 1
        for b, g in zip(self.tabs, self.store.groups):
            b.text.text = g.title + (' •' if counts[g.key] else '')
        n = counts[self.group]
        self.group_count.text = f'{len(self.store.group_by_key[self.group].specs)} thanh' + (f' · {n} đã đổi' if n else '')
        _tint(self.group_count, AMBER if n else FAINT)

    # --- mouse ---
    def _row_at(self, x, y):
        if not (self.x0 <= x <= self.x1 - 0.026 and self.rows_bottom <= y <= self.rows_top):
            return None
        i = int((self.rows_top - y) / ROW_H)
        return self.rows[i] if 0 <= i < ROWS else None

    def _set_from_x(self, spec: ParamSpec, x: float):
        t = min(max((x - self.track_x0) / (self.track_x1 - self.track_x0), 0.0), 1.0)
        v = spec.lo + t * (spec.hi - spec.lo)
        v = spec.lo + round((v - spec.lo) / spec.step) * spec.step
        v = int(round(v)) if spec.kind == 'int' else round(v, spec.decimals + 2)
        self.store.set(spec, v)

    def press(self, x: float, y: float):
        """Left mouse press at (x, y) UI coordinates."""
        for b in self.buttons:
            if b.contains(x, y):
                b.callback()
                return
        if self.scroll_track.enabled and self.scroll_x0 - 0.012 <= x <= self.scroll_x1 + 0.012 and self.rows_bottom <= y <= self.rows_top:
            self._drag = ('scroll',)
            self._scroll_to_y(y)
            return
        row = self._row_at(x, y)
        if row is None or not isinstance(row.item, ParamSpec):
            return
        spec = row.item
        if spec.kind in ('float', 'int'):
            if self.track_x0 - 0.02 <= x <= self.track_x1 + 0.02 and y >= row.y_top - 0.034:
                self._drag = ('slider', spec)
                self._set_from_x(spec, x)
        elif spec.kind == 'bool':
            self.store.set(spec, not self.store.get(spec))
        else:                                             # pick one of a few: cycle through the choices
            values = [c for c, _ in spec.choices]
            cur = self.store.get(spec)
            idx = next((i for i, c in enumerate(values) if c == cur and type(c) is type(cur)), -1)
            self.store.set(spec, values[(idx + 1) % len(values)])
        self._refresh_all()

    def release(self):
        self._drag = None

    def right_click(self, x: float, y: float):
        row = self._row_at(x, y)
        if row is not None and isinstance(row.item, ParamSpec) and self.store.reset(row.item):
            self._refresh_all()

    def scroll(self, steps: int):
        old = self.offset
        self.offset = max(0, min(self.offset + steps, max(0, len(self.items) - ROWS)))
        if self.offset != old:
            self._bind_rows()

    def _scroll_to_y(self, y: float):
        total = len(self.items)
        if total <= ROWS:
            return
        t = min(max((self.rows_top - y) / (self.rows_top - self.rows_bottom), 0.0), 1.0)
        self.offset = round(t * (total - ROWS))
        self._bind_rows()

    def on_input(self, key: str) -> bool:
        """Game.input forwards keys / mouse here while the panel is open. Returns True if handled."""
        if not self.is_open:
            return False
        if key == 'left mouse down':
            self.press(*self.pointer())
        elif key == 'left mouse up':
            self.release()
        elif key == 'right mouse down':
            self.right_click(*self.pointer())
        elif key == 'scroll up':
            self.scroll(-2)
        elif key == 'scroll down':
            self.scroll(2)
        else:
            return False
        return True

    # --- per frame (only while open) ---
    def update(self, dt: float):
        x, y = self.pointer()
        if self._drag:
            if self._drag[0] == 'slider':
                self._set_from_x(self._drag[1], x)
            else:
                self._scroll_to_y(y)
        for b in self.buttons:
            b.style(hover=b.contains(x, y))
        row = self._row_at(x, y)
        if row is not None and row.item is not None:
            self.hover_bar.enabled = True
            _set_rect(self.hover_bar, self.x0 + 0.01, row.y_top - ROW_H, self.x1 - 0.026, row.y_top)
        else:
            self.hover_bar.enabled = False
        for row in self.rows:
            row.refresh()
        self._update_counts()
        self._fps_frames += 1
        self._fps_time += dt
        if self._fps_time >= 0.25:
            self.fps_text.text = f'{self._fps_frames / self._fps_time:.0f} FPS'
            self._fps_frames, self._fps_time = 0, 0.0
        self._update_cone(dt)

    # --- cone ---
    def _update_cone(self, dt: float):
        game = self.game
        combat, player = game.combat, game.player
        acc = combat.accuracy
        k = self.cone_k
        active = ADS_ROW[player.state in (MoveState.WALK, MoveState.CROUCH_WALK)] if player.ads_amount > 0.5 else STATE_ROW[player.state]
        for i, (name, state, ads, col) in enumerate(CONE_STATES):
            angle = acc.base(state, ads)
            radius_m = ring_radius(angle, CONE_DISTANCE)
            d = 2 * min(radius_m, CONE_VIEW * 1.02) * k
            self.state_rings[i].scale = max(d, 0.004)
            sw, nm, vl = self.legend[i]
            vl.text = f'{format_number(angle, 2)}°  ·  {format_number(radius_m, 1)} m'
            on = i == active
            _tint(nm, WHITE if on else FAINT)
            _tint(vl, WHITE if on else FAINT)
            sw.scale = (0.014, 0.010 if not on else 0.014)
        spread = combat.spread_now
        radius_m = ring_radius(spread, CONE_DISTANCE)
        d = 2 * min(radius_m, CONE_VIEW * 1.02) * k
        self.cur_ring.scale = max(d, 0.004)
        self.cur_fill.scale = max(d, 0.004)
        bloom = acc.bloom
        top = max(acc.d.bloom_max, 1e-6)
        _set_rect(self.bloom_fill, self.bloom_x0, self.bloom_fill.y - 0.003, self.bloom_x0 + (self.bloom_x1 - self.bloom_x0) * min(bloom / top, 1.0),
                  self.bloom_fill.y + 0.003)
        self.bloom_text.text = f'{format_number(bloom, 2)}° / {format_number(acc.d.bloom_max, 1)}°'
        self.now_text.text = f'Hiện tại {format_number(spread, 2)}°  →  ±{format_number(radius_m, 1)} m'
        self.now_sub.text = 'đã gồm bloom; chấm cam = phát vừa bắn'

        if combat.shots_fired != self.shots_seen and combat.last_shot is not None:
            self.shots_seen = combat.shots_fired
            right, up = shot_offset(combat.last_shot.view_dir, combat.last_shot.direction)
            px = CONE_DISTANCE * math.tan(math.radians(right)) * k
            py = CONE_DISTANCE * math.tan(math.radians(up)) * k
            dot = self.dots[self.dot_next]
            self.dot_next = (self.dot_next + 1) % DOT_COUNT
            dot.enabled = True
            dot.x, dot.y = self.cone_cx + min(max(px, -self.cone_r), self.cone_r), self.cone_cy + min(max(py, -self.cone_r), self.cone_r)
            dot.age = 0.0
        for dot in self.dots:
            if dot.enabled:
                dot.age += dt
                a = max(0.0, 1.0 - dot.age / 6.0)
                dot.color = color.rgba(1.0, 0.55, 0.3, 0.95 * a)
                if a <= 0:
                    dot.enabled = False
