"""F2: the graphics options panel (G10, user request 7/11/2026): the basic choices of core/graphics.OPTIONS (overall level, anti-aliasing 2x / 4x, each water / light effect,
FPS counter). Every change applies at once (Game.apply_graphics); closing saves user_graphics.json.

Keys while open: up / down arrows choose a row, left / right change it, F2 or Esc closes (not WASD: those still walk). Mouse: left click on a row = next choice, right click = previous.
Built the first time it opens; while closed it is disabled (costs nothing). Like the F1 panel it unlocks the mouse and blocks firing / aiming (player.ui_open).
"""
from ursina import Entity, Text, camera, color, mouse, scene

from fps.core.graphics import OPTIONS, choice_text, cycle

ROW_H = 0.046
WIDTH = 0.80
TITLE = 'Đồ hoạ'
HINT = '↑ ↓ chọn dòng    ← → đổi    chuột trái / phải: đổi    F2 / Esc: đóng'


class GraphicsPanel:
    def __init__(self, game):
        self.game = game
        self.is_open = False
        self.row = 0
        self._built = False

    def _build(self):
        n = len(OPTIONS)
        self.height = 0.15 + n * ROW_H
        self.top = self.height / 2
        self.root = Entity(parent=camera.ui, enabled=False, z=-5)
        Entity(parent=self.root, model='quad', color=color.rgba(0.04, 0.05, 0.06, 0.86), scale=(WIDTH, self.height), z=0.02)
        Text(parent=self.root, text=TITLE, position=(-WIDTH / 2 + 0.03, self.top - 0.03), origin=(-0.5, 0.5), scale=1.25, color=color.white)
        Text(parent=self.root, text=HINT, position=(0, -self.top + 0.035), origin=(0, 0), scale=0.72, color=color.rgba(1, 1, 1, 0.6))
        self.highlight = Entity(parent=self.root, model='quad', color=color.rgba(1.0, 0.78, 0.35, 0.18), scale=(WIDTH - 0.03, ROW_H * 0.92), z=0.01)
        self.labels, self.values = [], []
        for i, (_field, label, _choices) in enumerate(OPTIONS):
            y = self._row_y(i)
            self.labels.append(Text(parent=self.root, text=label, position=(-WIDTH / 2 + 0.04, y), origin=(-0.5, 0), scale=0.95, color=color.rgba(1, 1, 1, 0.9)))
            self.values.append(Text(parent=self.root, text='', position=(WIDTH / 2 - 0.05, y), origin=(0.5, 0), scale=0.95, color=color.white))
        mine = {self.root, *self.root.children, *(c for ch in self.root.children for c in getattr(ch, 'children', []))}
        scene.entities = [e for e in scene.entities if e not in mine]          # none of them updates: keep them out of Ursina's per-frame walk (like prune_scene_entities)
        self._built = True

    def _row_y(self, i: int) -> float:
        return self.top - 0.095 - i * ROW_H

    def _refresh(self):
        s = self.game.gfx
        for i, (field, _label, _choices) in enumerate(OPTIONS):
            self.values[i].text = f'‹  {choice_text(s, field)}  ›'          # not < >: Ursina's Text reads '<' as the start of a markup tag
            self.values[i].color = color.rgb(1.0, 0.85, 0.5) if i == self.row else color.white
        self.highlight.y = self._row_y(self.row)

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
        mouse.locked = False
        self._refresh()

    def hide(self):
        if not self.is_open:
            return
        self.is_open = False
        self.root.enabled = False
        g = self.game
        g.player.ui_open = False
        g.combat.pressed = False
        mouse.position = (0, 0)                     # centre the pointer before locking: no big camera turn from where the pointer was
        mouse.prev_x = mouse.prev_y = 0
        mouse.locked = True
        g.save_graphics()

    # --- input ---
    def change(self, step: int, row: int = None):
        if row is not None:
            self.row = row
        field = OPTIONS[self.row][0]
        self.game.apply_graphics(cycle(self.game.gfx, field, step))
        self._refresh()

    def _row_at(self, y: float):
        for i in range(len(OPTIONS)):
            if abs(y - self._row_y(i)) <= ROW_H / 2:
                return i
        return None

    def on_input(self, key: str):
        if key in ('escape', 'f2'):
            self.hide()
        elif key in ('up arrow', 'up arrow hold'):
            self.row = (self.row - 1) % len(OPTIONS)
            self._refresh()
        elif key in ('down arrow', 'down arrow hold'):
            self.row = (self.row + 1) % len(OPTIONS)
            self._refresh()
        elif key in ('right arrow', 'enter'):
            self.change(1)
        elif key == 'left arrow':
            self.change(-1)
        elif key in ('left mouse down', 'right mouse down') and abs(mouse.x) <= WIDTH / 2:
            row = self._row_at(mouse.y)
            if row is not None:
                self.change(1 if key == 'left mouse down' else -1, row)
        elif key == 'scroll up':
            self.row = (self.row - 1) % len(OPTIONS)
            self._refresh()
        elif key == 'scroll down':
            self.row = (self.row + 1) % len(OPTIONS)
            self._refresh()
