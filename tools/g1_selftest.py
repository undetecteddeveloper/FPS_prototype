"""G1: mở game thật, điều khiển người chơi bằng đúng đường phím của game (held_keys), đo và chụp ảnh.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\g1_selftest.py
Ảnh ra thư mục shots\\g1_*.png. Kết thúc in bảng KIỂM TRA; thoát mã 1 nếu có mục trượt.
"""
import math
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename  # noqa: E402
from ursina import Entity, application, held_keys, mouse, time  # noqa: E402

from movement import MoveState  # noqa: E402

game = create_game(vsync=False)
player = game.player
p = game.params.player
mouse.locked = False   # không giữ con trỏ của người dùng; hướng nhìn điều khiển bằng player.look()

results = []   # (tên, đo được, mong đợi, đạt)
frame_dts = []
skip = {'next': False}   # khung ngay sau khi lưu ảnh chứa thời gian ghi PNG, không tính vào FPS


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def shot(name):
    out = ROOT / 'shots' / f'g1_{name}.png'
    out.parent.mkdir(exist_ok=True)
    application.base.win.saveScreenshot(Filename.from_os_specific(str(out)))
    skip['next'] = True
    print('ĐÃ CHỤP', out.name)


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.last = None

    def update(self):
        now = pytime.perf_counter()
        if self.last is not None and not skip['next']:
            frame_dts.append(now - self.last)
        skip['next'] = False
        self.last = now
        try:
            next(self.gen)
        except StopIteration:
            report()
            sys.exit(0 if all(r[3] for r in results) else 1)

    # --- tiện ích dạng generator: mỗi yield = một khung hình ---
    def wait(self, seconds):
        t = 0.0
        while t < seconds:
            yield
            t += min(time.dt, 0.05)

    def release(self):
        for k in ('w', 'a', 's', 'd', 'shift', 'control', 'space'):
            held_keys[k] = 0

    def run(self):
        yield from self.wait(0.6)
        frame_dts.clear()

        # --- đứng yên ở vạch bắn, nhìn thẳng làn ---
        yield from self.wait(0.3)
        shot('start')
        check('vị trí đầu', (round(player.x, 2), round(player.y, 2), round(player.z, 2)), (0, 0, 0),
              (player.x, player.y, player.z) == (0, 0, 0))
        check('trạng thái đầu', player.state.value, 'idle', player.state is MoveState.IDLE)
        check('chiều cao mắt đứng', round(player.eye_height, 3), p.eye_height_stand, player.eye_height == p.eye_height_stand)

        # --- đi bộ 1 s ---
        z0 = player.z
        held_keys['w'] = 1
        yield from self.wait(1.0)
        walk_speed = player.speed
        walk_state = player.state
        shot('walk')
        check('tốc độ đi', round(walk_speed, 2), p.walk_speed, abs(walk_speed - p.walk_speed) < 0.05)
        check('trạng thái đi', walk_state.value, 'walk', walk_state is MoveState.WALK)
        check('đi tiến về +z', round(player.z - z0, 2), '> 3', player.z - z0 > 3)

        # --- chạy nước rút ---
        held_keys['shift'] = 1
        yield from self.wait(1.0)
        check('tốc độ chạy', round(player.speed, 2), p.sprint_speed, abs(player.speed - p.sprint_speed) < 0.05)
        check('trạng thái chạy', player.state.value, 'sprint', player.state is MoveState.SPRINT)
        held_keys['shift'] = 0

        # --- dừng, rồi ngồi ---
        held_keys['w'] = 0
        yield from self.wait(0.6)
        check('đứng yên sau khi thả phím', round(player.speed, 3), 0, player.speed == 0)
        held_keys['control'] = 1
        yield from self.wait(0.5)
        shot('crouch')
        check('chiều cao mắt ngồi', round(player.eye_height, 3), p.eye_height_crouch, abs(player.eye_height - p.eye_height_crouch) < 1e-6)
        check('trạng thái ngồi', player.state.value, 'crouch_idle', player.state is MoveState.CROUCH_IDLE)
        held_keys['w'] = 1
        yield from self.wait(0.8)
        check('tốc độ đi khi ngồi', round(player.speed, 2), p.crouch_speed, abs(player.speed - p.crouch_speed) < 0.05)
        check('trạng thái đi khi ngồi', player.state.value, 'crouch_walk', player.state is MoveState.CROUCH_WALK)
        held_keys['w'] = 0
        held_keys['control'] = 0
        yield from self.wait(0.6)
        check('đứng lên lại', round(player.eye_height, 3), p.eye_height_stand, abs(player.eye_height - p.eye_height_stand) < 1e-6)

        # --- nhảy ---
        apex = 0.0
        saw_air = False
        held_keys['space'] = 1
        for _ in range(3):
            yield
        held_keys['space'] = 0
        t = 0.0
        while t < 2.0:
            yield
            t += min(time.dt, 0.05)
            apex = max(apex, player.y)
            saw_air = saw_air or player.state is MoveState.AIR
            if player.on_ground and t > 0.1:
                break
        expected_apex = p.jump_speed ** 2 / (2 * p.gravity)
        check('độ cao nhảy (m)', round(apex, 3), round(expected_apex, 3), abs(apex - expected_apex) < 0.06)
        check('có trạng thái AIR khi nhảy', saw_air, True, saw_air)
        check('hạ cánh xuống đất', round(player.y, 3), 0, player.on_ground and player.y == 0)

        # --- nhìn quanh ---
        player.look(0.1, 0.0)
        check('chuột phải 0.1 chiều cao => yaw (độ)', round(player.yaw, 2), p.mouse_sensitivity * 0.1,
              abs(player.yaw - p.mouse_sensitivity * 0.1) < 1e-6)
        player.look(-0.1, 0.0)
        player.look(0.0, 5.0)
        check('ngẩng quá cao bị chặn ở (độ)', round(player.pitch, 1), -p.pitch_limit, player.pitch == -p.pitch_limit)
        player.look(0.0, -5.0)
        check('cúi quá thấp bị chặn ở (độ)', round(player.pitch, 1), p.pitch_limit, player.pitch == p.pitch_limit)
        player.look(0.0, 5.0)
        player.look(0.0, -0.0)
        player.pitch = 0.0
        player.camera_pivot.rotation_x = 0.0
        # quay sang phải 90 độ rồi đi tiến phải đi về +x
        player.yaw = 90.0
        player.rotation_y = 90.0
        x0 = player.x
        held_keys['w'] = 1
        yield from self.wait(0.4)
        held_keys['w'] = 0
        check('yaw 90 đi tiến về +x', round(player.x - x0, 2), '> 1', player.x - x0 > 1 and abs(player.z) < 20)
        player.yaw = 0.0
        player.rotation_y = 0.0
        yield from self.wait(0.4)

        # --- giới hạn làn ---
        held_keys['s'] = 1
        yield from self.wait(9.0)
        held_keys['s'] = 0
        check('chặn ở đầu làn (z)', round(player.z, 2), player.walk_bounds[2],
              abs(player.z - player.walk_bounds[2]) < 1e-6)
        held_keys['d'] = 1
        yield from self.wait(4.0)
        held_keys['d'] = 0
        check('chặn ở mép làn phải (x)', round(player.x, 2), player.walk_bounds[1], abs(player.x - player.walk_bounds[1]) < 1e-6)
        held_keys['a'] = 1
        yield from self.wait(5.0)
        held_keys['a'] = 0
        check('chặn ở mép làn trái (x)', round(player.x, 2), player.walk_bounds[0], abs(player.x - player.walk_bounds[0]) < 1e-6)

        # --- ảnh: nhìn dọc làn từ đầu làn, rồi nhìn xéo ---
        player.position = (0, 0, 0)
        player.vx = player.vz = 0.0
        player.yaw = 0.0
        player.rotation_y = 0.0
        yield from self.wait(0.3)
        shot('lane_start')
        player.look(0.0, 0.0)
        player.yaw = 25.0
        player.rotation_y = 25.0
        yield from self.wait(0.3)
        shot('lane_angle')
        player.yaw = 0.0
        player.rotation_y = 0.0
        player.position = (0, 0, 140)
        yield from self.wait(0.3)
        shot('lane_far')


def report():
    print('\n=== KIỂM TRA G1 ===')
    print(f"{'mục':44s} {'đo được':>18s} {'mong đợi':>14s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:44s} {str(got):>18s} {str(expected):>14s}  {"ĐẠT" if ok else "TRƯỢT"}')
    dts = sorted(frame_dts)
    n = len(dts)
    print(f'\nFPS (vsync tắt, 1280x720, toàn bộ kịch bản): {n} khung, trung bình {n / sum(dts):.0f}, '
          f'thấp nhất {1 / dts[-1]:.0f}, 1% thấp nhất {1 / dts[int(n * 0.99)]:.0f}')
    print(f"{sum(r[3] for r in results)}/{len(results)} mục đạt")


Script()
game.app.run()
