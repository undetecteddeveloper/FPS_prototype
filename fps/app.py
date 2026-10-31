"""Dựng và chạy game: `Game` gom các phần, `create_game()` dùng chung cho main.py và các công cụ kiểm tra."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # gốc dự án (chứa guns/, sounds/)

from fps.game import gltf_patch  # noqa: E402  (phải nạp trước Ursina)

gltf_patch.apply()

import ursina  # noqa: E402
from panda3d.core import Filename, loadPrcFileData  # noqa: E402
from ursina import Entity, Ursina, application, mouse, time, window  # noqa: E402

from fps.game.combat import Combat  # noqa: E402
from fps.game.gun_audio import GunAudio  # noqa: E402
from fps.game.hud import Hud, setup_fonts  # noqa: E402
from fps.game.player import Player  # noqa: E402
from fps.game.shooting_range import WALK_BOUNDS, build_range  # noqa: E402
from fps.core.sway import Sway, ads_target_for  # noqa: E402
from fps.game.targets import build_targets  # noqa: E402
from fps.game.viewmodel import Viewmodel  # noqa: E402
from fps.weapon_data import GameParams  # noqa: E402


class Game(Entity):
    """Gom các phần lại và chạy vòng lặp mỗi khung hình."""

    def __init__(self, params: GameParams, quit_after: float = 0.0, sound: bool = True):
        super().__init__()
        self.params = params
        self.quit_after = quit_after
        self._age = 0.0
        self.world = build_range()
        self.targets = build_targets(params.feedback)
        self.player = Player(params.player, WALK_BOUNDS, params.gun)
        self.audio = GunAudio(params.gun, ROOT) if sound and params.gun.shot_sound else None
        self.combat = Combat(params, self.player, self.targets, self.world['colliders'], audio=self.audio)
        self.sway = Sway(params.gun.sway, ads_target_for(params.gun))
        self.viewmodel = Viewmodel(params.gun, ROOT)
        self.hud = Hud(params.gun.credit)

    def update(self):
        # thứ tự cố định: người chơi (nhìn/đi) -> bắn (dùng hướng nhìn vừa cập nhật) -> sway -> súng -> HUD
        dt = time.dt
        self.player.tick()
        self.combat.update(min(dt, 0.05))
        sway_pose = self.sway.update(min(dt, 0.05), self.player.sway_input())
        self.viewmodel.update(self.combat.gun_kick.pose, sway_pose)
        self.hud.update(dt, self.combat)
        self._age += time.dt
        if self.quit_after and self._age >= self.quit_after:
            application.quit()

    def input(self, key):
        if key == 'escape':
            mouse.locked = not mouse.locked
        elif key == 'left mouse down':
            self.combat.pressed = True
        elif key == 'b':
            self.combat.weapon.toggle_mode()
        elif key == 'r':
            self.combat.weapon.refill()       # tạm thời: reload có animation làm ở G5


def create_game(vsync: bool = True, size=(1280, 720), fullscreen: bool = False, quit_after: float = 0.0,
                sound: bool = True) -> Game:
    # Ursina(vsync=False) một mình không tắt được vsync; phải đặt thẳng cấu hình Panda
    loadPrcFileData('', f'sync-video {int(vsync)}')
    icon = Path(ursina.__file__).parent / 'textures' / 'ursina.ico'   # tuyệt đối, nếu không Ursina tìm trong thư mục game
    app = Ursina(title='FPS prototype', icon=Filename.from_os_specific(str(icon)), vsync=vsync, borderless=False, fullscreen=fullscreen, size=size,
                 development_mode=False)
    application.asset_folder = ROOT
    window.fps_counter.enabled = False
    setup_fonts()
    game = Game(GameParams(), quit_after, sound)
    game.app = app
    return game


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--novsync', action='store_true')
    ap.add_argument('--size', default='1280x720')
    ap.add_argument('--fullscreen', action='store_true')
    ap.add_argument('--quit-after', type=float, default=0.0)
    ap.add_argument('--mute', action='store_true', help='tắt tiếng súng')
    args = ap.parse_args(argv)
    w, h = (int(v) for v in args.size.lower().split('x'))
    game = create_game(vsync=not args.novsync, size=(w, h), fullscreen=args.fullscreen,
                       quit_after=args.quit_after, sound=not args.mute)
    game.app.run()


if __name__ == '__main__':
    main()
