"""Dựng và chạy game: `Game` gom các phần, `create_game()` dùng chung cho main.py và các công cụ kiểm tra."""
import argparse
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # gốc dự án (chứa guns/, sounds/)

from fps.game import gltf_patch  # noqa: E402  (phải nạp trước Ursina)

gltf_patch.apply()

import ursina  # noqa: E402
from panda3d.core import Filename, loadPrcFileData  # noqa: E402
from ursina import Entity, Ursina, application, mouse, time, window  # noqa: E402

from fps.core.params import ParamStore  # noqa: E402
from fps.core.shake import Shake  # noqa: E402
from fps.game.camera_shake import ShakeView  # noqa: E402
from fps.game.combat import Combat  # noqa: E402
from fps.game.debug_panel import DebugPanel  # noqa: E402
from fps.game.effects import Effects  # noqa: E402
from fps.game.foley import Foley  # noqa: E402
from fps.game.gun_audio import GunAudio  # noqa: E402
from fps.game.hud import Hud, setup_fonts  # noqa: E402
from fps.game.look import WorldLook  # noqa: E402
from fps.game.player import Player  # noqa: E402
from fps.game.shooting_range import WALK_BOUNDS, build_range  # noqa: E402
from fps.core.sway import Sway, ads_target_for  # noqa: E402
from fps.game.targets import build_targets  # noqa: E402
from fps.game.viewmodel import Viewmodel  # noqa: E402
from fps.weapon_data import M4, GameParams  # noqa: E402

USER_PARAMS = ROOT / 'user_params.json'      # thông số người dùng lưu từ bảng debug (F1); gitignore


class Game(Entity):
    """Gom các phần lại và chạy vòng lặp mỗi khung hình."""

    def __init__(self, params: GameParams, quit_after: float = 0.0, sound: bool = True, draw: bool = True,
                 effects: bool = True, look: bool = True, shake: bool = True, moving_targets: bool = True,
                 user_params: bool = False):
        super().__init__()
        self.params = params
        # bảng thông số sống (G6): chụp mặc định NGAY, rồi (nếu được yêu cầu) nạp user_params.json TRƯỚC khi dựng các phần, để cả những số chỉ
        # đọc một lúc dựng (đạn trong băng, bán kính đèn...) có hiệu lực. Mọi module giữ cùng các đối tượng dataclass của `params`.
        self.params_store = ParamStore(params)
        self.params_report = self.params_store.load(USER_PARAMS) if user_params and USER_PARAMS.exists() else None
        if self.params_report is not None:
            print(f'[thông số] {USER_PARAMS.name}: {self.params_report.message}')
        self.quit_after = quit_after
        self._age = 0.0
        self._draw_pending = draw         # rút súng ở khung đầu tiên (không phải lúc dựng: nạp mô hình làm khung đầu rất dài)
        self.world = build_range(params.look)
        self.targets = build_targets(params.feedback, moving=moving_targets)       # moving_targets=False: mọi bia đứng yên (selftest đo độ rơi)
        self.player = Player(params.player, WALK_BOUNDS, params.gun)
        self.audio = GunAudio(params.gun, ROOT) if sound and params.gun.shot_sound else None
        self.foley = Foley(params.audio, params.gun, self.player, ROOT) if sound else None    # nạp đạn, bước chân (tắt cùng cờ sound / --mute)
        self.viewmodel = Viewmodel(params.gun, ROOT)
        self.fx = Effects(params.gun, self.viewmodel) if effects else None
        self.shake = Shake(params.gun.shake) if shake else None                # rung thuần hình ảnh (không đổi hướng đạn)
        self.shake_view = ShakeView(self.shake) if shake else None
        self.combat = Combat(params, self.player, self.targets, self.world['colliders'], audio=self.audio, fx=self.fx, shake=self.shake)
        self.look = WorldLook(params.look, self.world, self.targets, self.combat.decals) if look else None
        self.sway = Sway(params.gun.sway, ads_target_for(params.gun))
        self.hud = Hud(params.gun.credit)
        self.debug = DebugPanel(self, self.params_store, USER_PARAMS)         # bảng F1: dựng lười ở lần mở đầu tiên, đóng thì không tốn gì
        self.params_store.subscribe(self._on_params_changed)

    def _on_params_changed(self, specs):
        """Số vừa đổi ở bảng debug. Hầu hết module đọc thẳng dataclass mỗi lần dùng nên không cần làm gì; chỗ nào đã đẩy số vào GPU / bộ nhớ
        đệm lúc dựng thì đẩy lại ở đây."""
        paths = {s.path for s in specs}
        if 'look' in paths and self.look:
            self.look.apply_params()
        if 'gun.view_light' in paths:
            self.viewmodel.apply_light()
        if any(s.id == 'gun.ads_eye_relief' for s in specs):
            self.sway.ads_target = ads_target_for(self.params.gun)

    def update(self):
        # thứ tự cố định: người chơi (nhìn/đi) -> bắn + nạp (dùng hướng nhìn vừa cập nhật) -> animation tay -> sway -> súng -> HUD
        dt = time.dt
        self.player.tick()
        if self.look:
            self.look.update()
        self.combat.update(min(dt, 0.05), dt)
        if self._draw_pending:
            self._draw_pending = False
            self.combat.handling.start_draw()
        for event in self.combat.handling.drain():
            self.viewmodel.on_event(event)
            if self.foley:
                self.foley.on_handling_event(event)
        if self.foley:
            self.foley.update(dt)
        self.viewmodel.animate(dt, self.combat.weapon.mag == 0)
        sway_pose = self.sway.update(min(dt, 0.05), self.player.sway_input())
        shake_pose = self.shake_view.apply(self.player.ads_amount) if self.shake_view else None    # camera thế giới rung + tư thế rung của súng
        self.viewmodel.update(self.combat.gun_kick.pose, sway_pose, *((shake_pose,) if shake_pose else ()))
        self.hud.update(dt, self.combat)
        if self.debug.is_open:
            self.debug.update(dt)
        self._age += time.dt
        if self.quit_after and self._age >= self.quit_after:
            application.quit()

    def input(self, key):
        if key == 'f1':
            self.debug.toggle()
        elif self.debug.is_open:                  # bảng debug mở: chuột là của bảng, không bắn / nạp / đổi chế độ
            if key == 'escape':
                self.debug.hide()
            else:
                self.debug.on_input(key)
        elif key == 'escape':
            mouse.locked = not mouse.locked
        elif key == 'left mouse down':
            self.combat.pressed = True
        elif key == 'b':
            self.combat.weapon.toggle_mode()
        elif key == 'r':
            self.combat.request_reload()


def create_game(vsync: bool = True, size=(1280, 720), fullscreen: bool = False, quit_after: float = 0.0,
                sound: bool = True, draw: bool = True, effects: bool = True, look: bool = True, shake: bool = True,
                moving_targets: bool = True, user_params: bool = False) -> Game:
    # Ursina(vsync=False) một mình không tắt được vsync; phải đặt thẳng cấu hình Panda
    loadPrcFileData('', f'sync-video {int(vsync)}')
    icon = Path(ursina.__file__).parent / 'textures' / 'ursina.ico'   # tuyệt đối, nếu không Ursina tìm trong thư mục game
    app = Ursina(title='FPS prototype', icon=Filename.from_os_specific(str(icon)), vsync=vsync, borderless=False, fullscreen=fullscreen, size=size,
                 development_mode=False)
    application.asset_folder = ROOT
    window.fps_counter.enabled = False
    setup_fonts()
    # bản sao của M4: bảng debug ghi thẳng vào dữ liệu súng, không được làm bẩn M4 dùng chung (test, công cụ đo)
    game = Game(GameParams(gun=copy.deepcopy(M4)), quit_after, sound, draw, effects, look, shake=shake, moving_targets=moving_targets,
                user_params=user_params)
    game.app = app
    return game


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--novsync', action='store_true')
    ap.add_argument('--size', default='1280x720')
    ap.add_argument('--fullscreen', action='store_true')
    ap.add_argument('--quit-after', type=float, default=0.0)
    ap.add_argument('--mute', action='store_true', help='tắt tiếng súng')
    ap.add_argument('--defaults', action='store_true', help='bỏ qua user_params.json, chạy bằng thông số mặc định')
    args = ap.parse_args(argv)
    w, h = (int(v) for v in args.size.lower().split('x'))
    game = create_game(vsync=not args.novsync, size=(w, h), fullscreen=args.fullscreen,
                       quit_after=args.quit_after, sound=not args.mute, user_params=not args.defaults)
    game.app.run()


if __name__ == '__main__':
    main()
