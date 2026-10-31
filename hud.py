"""HUD: FPS, tâm ngắm, số đạn, chế độ bắn, hit marker, khoảng cách bia vừa trúng, ghi công.

Font: Segoe UI Semilight có sẵn trong Windows (đủ dấu tiếng Việt), mảnh và sắc hơn OpenSans mặc định của
Ursina. Mỗi dòng chữ có một bản sao đen dịch 1 px làm bóng để đọc được trên nền trời sáng.
Không có font đó thì giữ font mặc định.
"""
import os
from pathlib import Path

from ursina import Entity, Text, application, camera, color, window

FONT_FILE = 'segoeuisl.ttf'
SHADOW_ALPHA = 0.55
CROSSHAIR_GAP = 0.012
CROSSHAIR_LEN = 0.014
CROSSHAIR_THICK = 0.0025


def setup_fonts():
    """Gọi sau khi tạo cửa sổ. Độ phân giải font khớp cỡ chữ trên màn hình (nhân 2 cho mịn), thay vì
    1080p của Ursina: chữ vẽ nhỏ lại ~3 lần nên bị nhoè."""
    fonts = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
    if (fonts / FONT_FILE).exists():
        application.fonts_folder = fonts
        Text.default_font = FONT_FILE
    Text.default_resolution = Text.size * window.size[1] * 2


class UiText:
    """Chữ có bóng. `text` và `color` đặt cho cả hai bản."""

    def __init__(self, text='', position=(0, 0), origin=(-0.5, 0.5), scale=1.0, tint=color.white, shadow=True):
        px = 1.3 / window.size[1]
        self.shadow = None
        if shadow:
            self.shadow = Text(parent=camera.ui, text=text, origin=origin, scale=scale, z=0.001,
                               position=(position[0] + px, position[1] - px),
                               color=color.rgba(0, 0, 0, SHADOW_ALPHA * tint.a))
        self.main = Text(parent=camera.ui, text=text, origin=origin, scale=scale, position=position, color=tint)
        self._text = text
        self.tint = tint

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        if value != self._text:       # đổi chữ dựng lại cả mảng glyph nên chỉ làm khi thật sự đổi
            self._text = value
            self.main.text = value
            if self.shadow:
                self.shadow.text = value

    def set_alpha(self, a: float):
        self.main.color = color.rgba(self.tint.r, self.tint.g, self.tint.b, a * self.tint.a)
        if self.shadow:
            self.shadow.color = color.rgba(0, 0, 0, a * SHADOW_ALPHA * self.tint.a)


class Hud:
    def __init__(self, credit: str):
        ui = camera.ui
        tl, bl, br = window.top_left, window.bottom_left, window.bottom_right
        faint = color.rgba(1, 1, 1, 0.75)
        self.fps_text = UiText('', tl + (0.012, -0.010), scale=0.95)
        self.hint = UiText('Esc: nhả / bắt chuột   WASD đi   Shift chạy   Ctrl/C ngồi   Space nhảy   '
                           'Chuột trái bắn   B đổi chế độ   R nạp đạn',
                           bl + (0.012, 0.034), origin=(-0.5, -0.5), scale=0.85, tint=faint)
        self.credit = UiText(credit, bl + (0.012, 0.008), origin=(-0.5, -0.5), scale=0.75,
                             tint=color.rgba(1, 1, 1, 0.5))

        self.ammo = UiText('', br + (-0.02, 0.012), origin=(0.5, -0.5), scale=1.0)
        self.mode = UiText('', br + (-0.022, 0.085), origin=(0.5, -0.5), scale=0.95, tint=faint)

        self.crosshair = []
        for dx, dy, w, h in (
            (-(CROSSHAIR_GAP + CROSSHAIR_LEN / 2), 0, CROSSHAIR_LEN, CROSSHAIR_THICK),
            (CROSSHAIR_GAP + CROSSHAIR_LEN / 2, 0, CROSSHAIR_LEN, CROSSHAIR_THICK),
            (0, CROSSHAIR_GAP + CROSSHAIR_LEN / 2, CROSSHAIR_THICK, CROSSHAIR_LEN),
            (0, -(CROSSHAIR_GAP + CROSSHAIR_LEN / 2), CROSSHAIR_THICK, CROSSHAIR_LEN),
        ):
            self.crosshair.append(Entity(parent=ui, model='quad', color=color.rgba(1, 1, 1, 0.85),
                                         position=(dx, dy), scale=(w, h)))

        # hit marker: bốn vạch chéo quanh tâm
        self.hit_marker = []
        d = 0.020
        for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            self.hit_marker.append(Entity(parent=ui, model='quad', color=color.rgba(1, 1, 1, 0), z=-0.001,
                                          position=(sx * d, sy * d), scale=(0.016, 0.003),
                                          rotation_z=45 if sx * sy > 0 else -45))
        self.last_hit = UiText('', (0, -0.07), origin=(0, 0), scale=1.15)

        self._frames = 0
        self._elapsed = 0.0

    def update(self, dt: float, combat):
        self._frames += 1
        self._elapsed += dt
        if self._elapsed >= 0.25:
            self.fps_text.text = f'{self._frames / self._elapsed:.0f} FPS'
            self._frames = 0
            self._elapsed = 0.0

        w = combat.weapon
        self.ammo.text = f'<scale:2.6>{w.mag}<scale:1.2>  /  {w.reserve}'
        self.ammo.main.color = color.rgb(1, 0.45, 0.4) if w.mag <= 5 else color.white
        self.mode.text = 'TỰ ĐỘNG' if w.auto else 'BẮN ĐƠN'

        a = combat.hit_marker_alpha
        for e in self.hit_marker:
            e.color = color.rgba(1, 1, 1, a)

        if combat.last_hit_left > 0:
            self.last_hit.text = f'{combat.last_hit_distance:.0f} m'
            self.last_hit.set_alpha(min(1.0, combat.last_hit_left / 0.5))
        else:
            self.last_hit.text = ''
