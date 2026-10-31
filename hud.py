"""HUD. G1: FPS, tâm ngắm tĩnh, dòng ghi công, gợi ý phím. G3 đổi tâm ngắm thành động, G6 thêm đạn/hit marker."""
from ursina import Entity, Text, camera, color, window

CROSSHAIR_GAP = 0.012
CROSSHAIR_LEN = 0.014
CROSSHAIR_THICK = 0.0025


class Hud:
    def __init__(self, credit: str):
        ui = camera.ui
        self.fps_text = Text(parent=ui, text='', origin=(-0.5, 0.5), position=window.top_left + (0.01, -0.01),
                             scale=1.0, color=color.white)
        self.hint = Text(parent=ui, text='Esc: nhả chuột / bắt chuột   WASD đi   Shift chạy   Ctrl hoặc C ngồi   Space nhảy',
                         origin=(-0.5, -0.5), position=window.bottom_left + (0.01, 0.03), scale=0.8,
                         color=color.rgba(255, 255, 255, 170))
        self.credit = Text(parent=ui, text=credit, origin=(-0.5, -0.5), position=window.bottom_left + (0.01, 0.005),
                           scale=0.7, color=color.rgba(255, 255, 255, 120))

        self.crosshair = []
        for dx, dy, w, h in (
            (-(CROSSHAIR_GAP + CROSSHAIR_LEN / 2), 0, CROSSHAIR_LEN, CROSSHAIR_THICK),
            (CROSSHAIR_GAP + CROSSHAIR_LEN / 2, 0, CROSSHAIR_LEN, CROSSHAIR_THICK),
            (0, CROSSHAIR_GAP + CROSSHAIR_LEN / 2, CROSSHAIR_THICK, CROSSHAIR_LEN),
            (0, -(CROSSHAIR_GAP + CROSSHAIR_LEN / 2), CROSSHAIR_THICK, CROSSHAIR_LEN),
        ):
            self.crosshair.append(Entity(parent=ui, model='quad', color=color.rgba(255, 255, 255, 220),
                                         position=(dx, dy), scale=(w, h)))

        self._frames = 0
        self._elapsed = 0.0

    def update(self, dt: float):
        self._frames += 1
        self._elapsed += dt
        if self._elapsed >= 0.25:
            self.fps_text.text = f'{self._frames / self._elapsed:.0f} FPS'
            self._frames = 0
            self._elapsed = 0.0
