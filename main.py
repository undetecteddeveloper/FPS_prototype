"""FPS prototype. Chạy: .venv\\Scripts\\python.exe main.py   (hoặc bấm đúp run.bat)

Tuỳ chọn: --novsync (đo FPS thật), --size 1280x720, --fullscreen, --quit-after 5 (tự thoát sau 5 giây, để kiểm tra)
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import gltf_patch  # noqa: E402  (phải nạp trước Ursina)

gltf_patch.apply()

import ursina  # noqa: E402
from panda3d.core import Filename, loadPrcFileData  # noqa: E402
from ursina import Entity, Ursina, application, mouse, window  # noqa: E402

from hud import Hud  # noqa: E402
from player import Player  # noqa: E402
from shooting_range import WALK_BOUNDS, build_range  # noqa: E402
from viewmodel import Viewmodel  # noqa: E402
from weapon_data import GameParams  # noqa: E402


class Game(Entity):
    """Gom các phần lại và chạy vòng lặp mỗi khung hình."""

    def __init__(self, params: GameParams, quit_after: float = 0.0):
        super().__init__()
        self.params = params
        self.quit_after = quit_after
        self._age = 0.0
        self.world = build_range()
        self.player = Player(params.player, WALK_BOUNDS)
        self.viewmodel = Viewmodel(params.gun, ROOT)
        self.hud = Hud(params.gun.credit)

    def update(self):
        from ursina import time
        self.viewmodel.update()
        self.hud.update(time.dt)
        self._age += time.dt
        if self.quit_after and self._age >= self.quit_after:
            application.quit()

    def input(self, key):
        if key == 'escape':
            mouse.locked = not mouse.locked


def create_game(vsync: bool = True, size=(1280, 720), fullscreen: bool = False, quit_after: float = 0.0) -> Game:
    # Ursina(vsync=False) một mình không tắt được vsync; phải đặt thẳng cấu hình Panda
    loadPrcFileData('', f'sync-video {int(vsync)}')
    icon = Path(ursina.__file__).parent / 'textures' / 'ursina.ico'   # tuyệt đối, nếu không Ursina tìm trong thư mục game
    app = Ursina(title='FPS prototype', icon=Filename.from_os_specific(str(icon)), vsync=vsync, borderless=False, fullscreen=fullscreen, size=size,
                 development_mode=False)
    application.asset_folder = ROOT
    window.fps_counter.enabled = False
    game = Game(GameParams(), quit_after)
    game.app = app
    return game


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--novsync', action='store_true')
    ap.add_argument('--size', default='1280x720')
    ap.add_argument('--fullscreen', action='store_true')
    ap.add_argument('--quit-after', type=float, default=0.0)
    args = ap.parse_args(argv)
    w, h = (int(v) for v in args.size.lower().split('x'))
    game = create_game(vsync=not args.novsync, size=(w, h), fullscreen=args.fullscreen,
                       quit_after=args.quit_after)
    game.app.run()


if __name__ == '__main__':
    main()
