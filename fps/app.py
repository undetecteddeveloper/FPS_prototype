"""Dựng và chạy game: `Game` gom các phần, `create_game()` dùng chung cho main.py và các công cụ kiểm tra."""
import argparse
import copy
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # gốc dự án (chứa assets/)

from fps.game import gltf_patch  # noqa: E402  (phải nạp trước Ursina)

gltf_patch.apply()

import ursina  # noqa: E402
from panda3d.core import Filename, loadPrcFileData  # noqa: E402
from ursina import Entity, Ursina, application, camera, mouse, scene, time, window  # noqa: E402

from fps.core.exposure import AutoExposure  # noqa: E402
from fps.core.freeaim import barrel_view_dir, view_to_world  # noqa: E402
from fps.core.headcam import HeadCam, reload_state  # noqa: E402
from fps.core.movement import aim_direction  # noqa: E402
from fps.core.params import ParamStore  # noqa: E402
from fps.core.shake import Shake  # noqa: E402
from fps.game.camera_shake import ShakeView  # noqa: E402
from fps.game.combat import Combat  # noqa: E402
from fps.game.debug_panel import DebugPanel  # noqa: E402
from fps.game.effects import Effects  # noqa: E402
from fps.game.foley import Foley  # noqa: E402
from fps.game.frame_light import FrameLight  # noqa: E402
from fps.game.gun_audio import GunAudio  # noqa: E402
from fps.game.hud import Hud, setup_fonts  # noqa: E402
from fps.game.lens import Lens  # noqa: E402
from fps.game.look import WorldLook  # noqa: E402
from fps.game.player import Player  # noqa: E402
from fps.game.shooting_range import WALK_BOUNDS, build_range  # noqa: E402
from fps.core.sway import Sway, ads_target_for  # noqa: E402
from fps.game.targets import build_targets  # noqa: E402
from fps.game.viewmodel import Viewmodel  # noqa: E402
from fps.weapon_data import M4, GameParams  # noqa: E402

USER_PARAMS = ROOT / 'user_params.json'      # thông số người dùng lưu từ bảng debug (F1); gitignore


def prune_scene_entities():
    """Bỏ khỏi `scene.entities` mọi vật thể không có `update` / `input` (vẫn được vẽ bình thường).

    Mỗi khung Ursina duyệt cả danh sách này bằng Python (kiểm cha mẹ, kiểm enabled...) và với vật dùng shader mặc định còn gọi `set_shader_input` đẩy vị trí
    camera; đo được 3-5 ms mỗi khung, và việc đổi đầu vào shader còn làm Panda ghép lại trạng thái vẽ. Phòng + bia + biển không cần gì trong số đó."""
    def keep(e):
        return callable(getattr(e, 'update', None)) or callable(getattr(e, 'input', None)) or getattr(e, 'scripts', None)
    scene.entities = [e for e in scene.entities if keep(e)]


class Game(Entity):
    """Gom các phần lại và chạy vòng lặp mỗi khung hình."""

    def __init__(self, params: GameParams, quit_after: float = 0.0, sound: bool = True, draw: bool = True,
                 effects: bool = True, look: bool = True, shake: bool = True, moving_targets: bool = True,
                 user_params: bool = False, hud: bool = False, lens: bool = True, free_aim: bool = True):
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
        if not free_aim:
            params.gun.free_aim.barrel_aim = False
        self.light = FrameLight(params.look, params.gun)                       # một nguồn sáng chung cho thế giới và súng
        self.exposure = AutoExposure(params.lens, params.look)
        self.viewmodel = Viewmodel(params.gun, ROOT, self.light)
        self.fx = Effects(params.gun, self.viewmodel) if effects else None
        self.shake = Shake(params.gun.shake) if shake else None                # rung thuần hình ảnh (không đổi hướng đạn)
        self.head = HeadCam(params.gun.head) if shake else None               # đầu + thân lên ảnh: cùng cờ `shake` vì cùng là chuyển động thuần hình ảnh của camera
        self.shake_view = ShakeView(self.shake, self.head) if shake else None
        self.combat = Combat(params, self.player, self.targets, self.world['colliders'], audio=self.audio, fx=self.fx, shake=self.shake)
        self.combat.aim_source = self._barrel_direction
        self.combat.foley = self.foley
        self.look = WorldLook(params.look, self.world, self.targets, self.combat.decals, self.light) if look else None
        self.lens = Lens(params.lens, self.viewmodel) if lens else None
        self.sway = Sway(params.gun.sway, ads_target_for(params.gun))
        self.hud = Hud(params.gun.credit) if hud else None                    # kiểu Bodycam: không có gì trên màn hình; chỉ selftest bật để đọc số
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
        if 'gun.flash' in paths and self.look:
            self.look.apply_params()
        if 'lens' in paths and self.lens:
            self.lens.apply_params()
        if any(s.id == 'gun.ads_eye_relief' for s in specs):
            self.sway.ads_target = ads_target_for(self.params.gun)

    def _barrel_direction(self) -> tuple:
        """Hướng đạn: theo nòng súng đang chỉ trên màn hình. `barrel_pose` là của khung trước (súng vẽ sau khi bắn), lệch tối đa một khung của lò xo, không thấy được."""
        gun, p = self.params.gun, self.player
        if not gun.free_aim.barrel_aim or gun.ads_sights is None:
            return aim_direction(p.yaw, p.pitch)
        return view_to_world(p.yaw, p.pitch, barrel_view_dir(self.viewmodel.barrel_pose, gun.ads_sights, self.viewmodel.current_fov, camera.fov))

    def update(self):
        # thứ tự cố định: người chơi (nhìn/đi) -> bắn + nạp (dùng hướng nhìn vừa cập nhật) -> animation tay -> sway -> đầu + rung -> súng -> ánh sáng, ống kính
        dt = time.dt
        self.player.tick()
        if self.look:
            self.look.update()
        self.combat.update(min(dt, 0.05), dt)
        if self._draw_pending and dt < 0.1:          # chờ tới khung bình thường đầu tiên: khung dựng dài không được tính vào thời gian rút súng
            self._draw_pending = False
            self.combat.handling.start_draw()
        for event in self.combat.handling.drain():
            self.viewmodel.on_event(event)
            if self.foley:
                self.foley.on_handling_event(event)
        self.viewmodel.animate(dt, self.combat.weapon.mag == 0, self.player.ads_amount)
        step = min(dt, 0.05)
        inp = self.player.sway_input()
        sway_pose = self.sway.update(step, inp)
        if self.foley:
            self.foley.update(dt, self.sway.phase, self.sway, self.player.ads_amount)       # sau sway: bước chân phát đúng lúc súng chạm điểm thấp nhất của bob; tiếng thở theo đồng hồ thở của sway
        visual = ()
        if self.shake_view:
            p = self.player
            cy, sy = math.cos(math.radians(p.yaw)), math.sin(math.radians(p.yaw))
            # sau combat (Handling.t của khung này) và sau sway (pha bước chân): liếc súng khi nạp + nhún / nhảy / chạm đất
            self.head.update(step, inp, self.sway.phase, p.vx * cy - p.vz * sy, p.vx * sy + p.vz * cy, reload_state(self.combat.handling))
            visual = (self.shake_view.apply(p.ads_amount),)                         # camera thế giới rung + tư thế đi theo của súng
        reloading = self.combat.handling.key is not None
        self.viewmodel.update(self.combat.gun_kick.pose, sway_pose, self.combat.free_aim.pose(self.player.ads_amount, reloading), self.player.free_look.pose(), visual=visual)
        cam_pos, forward = camera.world_position, camera.forward
        self.light.set_camera(cam_pos, camera.right, camera.up, forward)
        self.light.set_exposure(self.exposure.update(dt, tuple(cam_pos), tuple(forward)))
        if self.lens:
            self.lens.update(dt, self.player.ads_amount, inp.look[0])
        if self.hud:
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


def desktop_size() -> tuple:
    """Độ phân giải thật của màn hình chính."""
    from screeninfo import get_monitors
    monitors = get_monitors()
    primary = next((m for m in monitors if m.is_primary), monitors[0])
    return primary.width, primary.height


def create_game(vsync: bool = True, size=(1280, 720), fullscreen: bool = False, quit_after: float = 0.0,
                sound: bool = True, draw: bool = True, effects: bool = True, look: bool = True, shake: bool = True,
                moving_targets: bool = True, user_params: bool = False, hud: bool = False, lens: bool = True, free_aim: bool = True,
                borderless: bool = False) -> Game:
    # Ursina(vsync=False) một mình không tắt được vsync; phải đặt thẳng cấu hình Panda
    loadPrcFileData('', f'sync-video {int(vsync)}')
    # Panda dọn bộ nhớ đệm trạng thái bằng một việc chạy mỗi khung (~0,5 ms ở đây); tắt thì trạng thái tự giải phóng theo đếm tham chiếu
    loadPrcFileData('', 'garbage-collect-states 0')
    icon = Path(ursina.__file__).parent / 'textures' / 'ursina.ico'   # tuyệt đối, nếu không Ursina tìm trong thư mục game
    app = Ursina(title='FPS prototype', icon=Filename.from_os_specific(str(icon)), vsync=vsync, borderless=borderless, fullscreen=fullscreen, size=size,
                 development_mode=False)
    application.asset_folder = ROOT
    window.fps_counter.enabled = False
    setup_fonts()
    # bản sao của M4: bảng debug ghi thẳng vào dữ liệu súng, không được làm bẩn M4 dùng chung (test, công cụ đo)
    game = Game(GameParams(gun=copy.deepcopy(M4)), quit_after, sound, draw, effects, look, shake=shake, moving_targets=moving_targets,
                user_params=user_params, hud=hud, lens=lens, free_aim=free_aim)
    game.app = app
    prune_scene_entities()
    # vẽ thử lúc dựng: dịch shader (ống kính, súng) và tải normal map lên GPU không rơi vào khung đầu của game. Không làm thì khung đầu dài ~1 s và clip rút súng 1 s bị nhảy qua hết
    for _ in range(2):
        application.base.graphicsEngine.render_frame()
    return game


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--novsync', action='store_true')
    ap.add_argument('--window', action='store_true', help='chạy trong cửa sổ thường (mặc định: lấp đầy màn hình)')
    ap.add_argument('--size', default='1280x720', help='cỡ cửa sổ khi dùng --window')
    ap.add_argument('--quit-after', type=float, default=0.0)
    ap.add_argument('--mute', action='store_true', help='tắt tiếng súng')
    ap.add_argument('--defaults', action='store_true', help='bỏ qua user_params.json, chạy bằng thông số mặc định')
    args = ap.parse_args(argv)
    # mặc định: cửa sổ không viền phủ kín màn hình. Toàn màn hình độc quyền kèm vsync sẽ tụt thẳng xuống 30 FPS mỗi khi một khung trễ; cách này thì không
    size = tuple(int(v) for v in args.size.lower().split('x')) if args.window else desktop_size()
    game = create_game(vsync=not args.novsync, size=size, borderless=not args.window,
                       quit_after=args.quit_after, sound=not args.mute, user_params=not args.defaults)
    game.app.run()


if __name__ == '__main__':
    main()
