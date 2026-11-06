"""HUD (chỉ để kiểm tra: `create_game(hud=True)`; game thật KHÔNG có HUD kiểu Bodycam, xem Game trong app.py): FPS, tâm ngắm động, số đạn, chế độ bắn, hit marker, khoảng cách bia vừa trúng, ghi công.

Font: Segoe UI Semilight có sẵn trong Windows (đủ dấu tiếng Việt), mảnh và sắc hơn OpenSans mặc định của
Ursina. Mỗi dòng chữ có một bản sao đen dịch 1 px làm bóng để đọc được trên nền trời sáng.
Không có font đó thì giữ font mặc định.
"""
import math
import os
from pathlib import Path

from ursina import Entity, Text, application, camera, color, window

from fps.core.handling import Phase
from fps.core.spread import crosshair_gap

FONT_FILE = 'segoeuisl.ttf'
LOW_AMMO = 5                  # băng còn ngần này viên trở xuống thì số đạn đỏ và nhắc nạp
RELOAD_BAR_WIDTH = 0.16       # đơn vị UI
SHADOW_ALPHA = 0.55
CROSSHAIR_MIN_GAP = 0.008     # đơn vị UI (chiều cao cửa sổ = 1)
CROSSHAIR_LEN = 0.014
CROSSHAIR_THICK = 0.0025
CROSSHAIR_ALPHA = 0.85
CROSSHAIR_SMOOTH = 25.0       # 1/s: vạch trượt về khoảng mới, không giật khi đổi trạng thái


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

    def __init__(self, text='', position=(0, 0), origin=(-0.5, 0.5), scale=1.0, tint=color.white, shadow=True, parent=None, z=0.0):
        px = 1.3 / window.size[1]
        parent = parent or camera.ui
        self.shadow = None
        if shadow:
            self.shadow = Text(parent=parent, text=text, origin=origin, scale=scale, z=z + 0.001,
                               position=(position[0] + px, position[1] - px),
                               color=color.rgba(0, 0, 0, SHADOW_ALPHA * tint.a))
        self.main = Text(parent=parent, text=text, origin=origin, scale=scale, position=position, color=tint, z=z)
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

    @property
    def enabled(self) -> bool:
        return self.main.enabled

    @enabled.setter
    def enabled(self, value: bool):
        self.main.enabled = value
        if self.shadow:
            self.shadow.enabled = value

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
        self.hint = UiText('R nạp đạn    B đổi chế độ bắn    F1 bảng chỉnh thông số    Esc nhả chuột',
                           bl + (0.012, 0.032), origin=(-0.5, -0.5), scale=0.75, tint=color.rgba(1, 1, 1, 0.45))
        self.credit = UiText(credit, bl + (0.012, 0.008), origin=(-0.5, -0.5), scale=0.75,
                             tint=color.rgba(1, 1, 1, 0.5))

        self.ammo = UiText('', br + (-0.02, 0.012), origin=(0.5, -0.5), scale=1.0)
        self.mode = UiText('', br + (-0.022, 0.085), origin=(0.5, -0.5), scale=0.95, tint=faint)
        # nhắc nạp đạn / hết đạn, và thanh tiến độ nạp
        self.prompt = UiText('', br + (-0.022, 0.126), origin=(0.5, -0.5), scale=0.95)
        bar_x = br.x - 0.022
        self.reload_bar_back = Entity(parent=ui, model='quad', origin=(0.5, 0), color=color.rgba(1, 1, 1, 0),
                                      position=(bar_x, br.y + 0.119), scale=(RELOAD_BAR_WIDTH, 0.004))
        self.reload_bar = Entity(parent=ui, model='quad', origin=(0.5, 0), color=color.rgba(1, 1, 1, 0), z=-0.001,
                                 position=(bar_x, br.y + 0.119), scale=(0.0001, 0.004))

        # tâm ngắm động: bốn vạch dạt ra theo độ tản; ẩn dần khi ngắm (ADS)
        self.gap = CROSSHAIR_MIN_GAP
        self.crosshair = []     # (entity, hướng x, hướng y)
        for ux, uy in ((-1, 0), (1, 0), (0, 1), (0, -1)):
            w, h = (CROSSHAIR_LEN, CROSSHAIR_THICK) if ux else (CROSSHAIR_THICK, CROSSHAIR_LEN)
            self.crosshair.append((Entity(parent=ui, model='quad', color=color.rgba(1, 1, 1, CROSSHAIR_ALPHA),
                                          scale=(w, h)), ux, uy))
        self._update_crosshair(1.0, 2.0, 0.0, snap=True)

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

    def _update_crosshair(self, dt: float, spread: float, ads_amount: float, snap: bool = False):
        vfov_half_tan = math.tan(math.radians(camera.fov / 2)) / window.aspect_ratio     # FOV hiện tại (ngắm làm nó hẹp lại)
        target = max(CROSSHAIR_MIN_GAP, crosshair_gap(spread, vfov_half_tan))
        self.gap = target if snap else self.gap + (target - self.gap) * (1.0 - math.exp(-dt * CROSSHAIR_SMOOTH))
        tint = color.rgba(1, 1, 1, CROSSHAIR_ALPHA * (1.0 - ads_amount))
        for entity, ux, uy in self.crosshair:
            d = self.gap + CROSSHAIR_LEN / 2
            entity.position = (ux * d, uy * d)
            entity.color = tint

    def update(self, dt: float, combat):
        self._frames += 1
        self._elapsed += dt
        if self._elapsed >= 0.25:
            self.fps_text.text = f'{self._frames / self._elapsed:.0f} FPS'
            self._frames = 0
            self._elapsed = 0.0

        w = combat.weapon
        h = combat.handling
        self.ammo.text = f'<scale:2.6>{w.mag}<scale:1.2>  /  {w.reserve}'
        self.ammo.main.color = color.rgb(1, 0.45, 0.4) if w.mag <= LOW_AMMO else color.white
        self.mode.text = 'TỰ ĐỘNG' if w.auto else 'BẮN ĐƠN'

        reloading = h.phase is Phase.RELOAD
        if reloading:
            self.prompt.text, tint = 'ĐANG NẠP ĐẠN', color.white
        elif w.out_of_ammo:
            self.prompt.text, tint = 'HẾT ĐẠN', color.rgb(1, 0.4, 0.35)
        elif w.mag == 0:
            self.prompt.text, tint = 'BẤM R ĐỂ NẠP ĐẠN', color.rgb(1, 0.7, 0.3)
        elif w.mag <= LOW_AMMO and w.can_reload:
            self.prompt.text, tint = 'R  NẠP ĐẠN', color.rgb(1, 0.85, 0.5)
        else:
            self.prompt.text, tint = '', color.white
        self.prompt.main.color = tint
        self.reload_bar_back.color = color.rgba(1, 1, 1, 0.25 if reloading else 0)
        self.reload_bar.color = color.rgba(1, 1, 1, 0.9 if reloading else 0)
        self.reload_bar.scale_x = max(RELOAD_BAR_WIDTH * h.progress, 0.0001)

        self._update_crosshair(dt, combat.spread_now, combat.player.ads_amount)

        a = combat.hit_marker_alpha
        for e in self.hit_marker:
            e.color = color.rgba(1, 1, 1, a)

        if combat.last_hit_left > 0:
            self.last_hit.text = f'{combat.last_hit_distance:.0f} m'
            self.last_hit.set_alpha(min(1.0, combat.last_hit_left / 0.5))
        else:
            self.last_hit.text = ''
