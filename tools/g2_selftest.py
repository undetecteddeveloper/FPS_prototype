"""G2: bắn bằng game thật. Điều khiển qua đúng đường chuột/phím của game (held_keys, combat.pressed),
đo nhịp bắn, độ rơi của đạn ở từng bia, đếm đạn, hit marker, lỗ đạn; chụp ảnh vào shots\\g2_*.png.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\g2_selftest.py        (thoát mã 1 nếu có mục trượt)
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

from fps.core.ballistics import GROUND, drop_at_distance  # noqa: E402
from fps.game.targets import Target  # noqa: E402

game = create_game(vsync=False, sound=False, draw=False, moving_targets=False)     # G6: bia chạy làm đo thay đổi theo giờ; đo trên bia đứng yên
player, combat = game.player, game.combat
gun = game.params.gun
mouse.locked = False                      # không giữ con trỏ của người dùng
combat.require_locked_mouse = False       # cho phép bắn dù chuột không bị bắt (chỉ trong bài kiểm tra)
# G3 thêm độ tản và recoil. G2 đo độ rơi của đạn nên tắt độ tản (g3_selftest.py kiểm tra riêng phần đó)
for _name in ('stand', 'walk', 'sprint', 'air', 'ads', 'ads_move', 'bloom_per_shot'):
    setattr(gun.accuracy, _name, 0.0)

results = []
frame_dts = []
frame_phase = []
phase = {'name': 'khởi động'}
skip = {'next': False}


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def shot(name):
    out = ROOT / 'shots' / f'g2_{name}.png'
    out.parent.mkdir(exist_ok=True)
    application.base.win.saveScreenshot(Filename.from_os_specific(str(out)))
    skip['next'] = True
    print('ĐÃ CHỤP', out.name)


def aim(yaw, pitch):
    player.position = (0, 0, 0)
    player.vx = player.vz = 0.0
    player.yaw, player.pitch = yaw % 360, pitch
    player.rotation_y = player.yaw
    player.camera_pivot.rotation_x = pitch


def yaw_to(target: Target) -> float:
    return math.degrees(math.atan2(target.root.x, target.root.z))


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.last = None

    def update(self):
        now = pytime.perf_counter()
        if self.last is not None and not skip['next']:
            frame_dts.append(now - self.last)
            frame_phase.append(phase['name'])
        skip['next'] = False
        self.last = now
        try:
            next(self.gen)
        except StopIteration:
            report()
            sys.exit(0 if all(r[3] for r in results) else 1)

    def wait(self, seconds):
        t = 0.0
        while t < seconds:
            yield
            t += min(time.dt, 0.05)

    def reset(self, auto=False, mag=30):
        held_keys['left mouse'] = 0
        combat.bullets.clear()
        combat.last_impact = None
        combat.weapon.auto = auto
        combat.weapon.mag = mag
        combat.weapon.reserve = gun.reserve
        combat.weapon.cooldown = 0.0

    def fire_single(self):
        """Một lần bóp cò (chế độ bắn đơn) rồi chờ đạn bay tới."""
        self.reset(auto=False)
        combat.pressed = True
        yield
        yield from self.wait(0.9)          # đạn tới 200 m mất 0,4 s

    def run(self):
        yield from self.wait(0.6)
        frame_dts.clear()
        shot('hud')
        check('ban đầu: đạn trong băng / dự trữ', f'{combat.weapon.mag}/{combat.weapon.reserve}', f'{gun.magazine}/{gun.reserve}',
              (combat.weapon.mag, combat.weapon.reserve) == (gun.magazine, gun.reserve))
        check('ban đầu: chế độ tự động', combat.weapon.auto, True, combat.weapon.auto is True)
        check('số bia', len(game.targets), 6, len(game.targets) == 6)

        # --- độ rơi của đạn ở từng bia: bắn ngang tầm mắt ---
        phase['name'] = 'độ rơi từng bia'
        eye = game.params.player.eye_height_stand
        holes_before = combat.decals.count
        for t in game.targets:
            aim(yaw_to(t), 0.0)
            yield from self.fire_single()
            imp = combat.last_impact
            hit_target = imp is not None and imp.owner is t
            check(f'trúng bia {t.distance:.0f} m', hit_target, True, hit_target)
            if not hit_target:
                continue
            horiz = math.hypot(imp.point[0], imp.point[2])
            drop = eye - imp.point[1]
            expected = drop_at_distance(horiz, gun.muzzle_velocity, gun.bullet_gravity)
            check(f'  độ rơi ở {t.distance:.0f} m (m)', round(drop, 4), round(expected, 4), abs(drop - expected) < 0.002)
            if t.distance == 150:
                check('  ĐỀ BÀI: rơi ~0,45 m ở 150 m (±20%)', round(drop, 3), '0,36..0,54', 0.45 * 0.8 <= drop <= 0.45 * 1.2)
                shot('target_150')
        check('mỗi phát trúng bia để lại một lỗ đạn', combat.decals.count - holes_before, len(game.targets),
              combat.decals.count - holes_before == len(game.targets))

        # --- hit marker và khoảng cách bia vừa trúng ---
        phase['name'] = 'hit marker'
        t25 = game.targets[1]
        aim(yaw_to(t25), 0.0)
        self.reset(auto=False)
        combat.pressed = True
        for _ in range(3):
            yield
        yield from self.wait(0.12)         # đạn tới 25 m mất 50 ms; marker kéo dài 150 ms
        check('hit marker bật khi trúng bia', round(combat.hit_marker_left, 3), '> 0', combat.hit_marker_left > 0)
        check('khoảng cách bia vừa trúng (m)', round(combat.last_hit_distance or 0, 1), '~25', abs((combat.last_hit_distance or 0) - 25) < 1)
        check('bia nháy màu khi trúng', round(t25.flash_left, 3), '> 0', t25.flash_left > 0)
        shot('hit_marker_25')
        yield from self.wait(0.5)
        check('hit marker tắt sau 0,15 s', round(combat.hit_marker_left, 3), 0, combat.hit_marker_left == 0)

        # --- bắn trượt: lên trần (phòng tập kín, không còn trời) ---
        phase['name'] = 'bắn trượt'
        aim(0, -25)
        marker_before = combat.target_hits
        yield from self.fire_single()
        yield from self.wait(2.3)
        imp = combat.last_impact
        ceiling_ok = imp is not None and not isinstance(imp.owner, Target) and imp.normal == (0.0, -1.0, 0.0)
        check('bắn lên trần: trúng trần (pháp tuyến -y)', imp.normal if imp else None, (0.0, -1.0, 0.0), ceiling_ok)
        check('bắn lên trần: không có hit marker', combat.hit_marker_left == 0 and combat.target_hits == marker_before, True,
              combat.hit_marker_left == 0 and combat.target_hits == marker_before)
        check('đạn lạc bị xoá sau khi hết hạn bay', len(combat.bullets), 0, len(combat.bullets) == 0)

        # --- đất và bờ đất ---
        phase['name'] = 'đất/bờ đất'
        aim(0, 45)
        holes = combat.decals.count
        yield from self.fire_single()
        imp = combat.last_impact
        check('bắn xuống đất: trúng mặt đất', imp is not None and imp.owner is GROUND, True, imp is not None and imp.owner is GROUND)
        check('  lỗ đạn trên đất', combat.decals.count - holes, 1, combat.decals.count - holes == 1)
        check('  bắn đất không bật hit marker', combat.hit_marker_left, 0, combat.hit_marker_left == 0)
        shot('ground_hit')
        aim(-90, 2)                        # tường trái cách ~12 m: chúc 10 độ như trước thì chạm sàn ở 9 m
        yield from self.fire_single()
        imp = combat.last_impact
        ok = imp is not None and imp.owner not in (GROUND,) and not isinstance(imp.owner, Target) and imp.normal == (1.0, 0.0, 0.0)
        check('bắn sang bên trái: trúng tường (pháp tuyến +x)', imp.normal if imp else None, (1.0, 0.0, 0.0), ok)

        # --- bắn đơn: một lần bóp một phát ---
        phase['name'] = 'bắn đơn'
        aim(0, -25)
        self.reset(auto=False)
        held_keys['left mouse'] = 1
        yield from self.wait(0.5)
        check('bắn đơn: giữ chuột không bóp mới thì không bắn', combat.weapon.mag, 30,
              combat.weapon.mag == 30)
        combat.pressed = True
        yield
        yield from self.wait(0.1)
        check('bắn đơn: bóp một lần = một phát', combat.weapon.mag, 29, combat.weapon.mag == 29)
        held_keys['left mouse'] = 0

        # --- nhịp bắn tự động, đo bằng đồng hồ thật ---
        phase['name'] = 'nhịp bắn tự động'
        aim(0, -25)
        self.reset(auto=True, mag=5000)
        n0 = len(combat.weapon.shot_times)
        t0 = pytime.perf_counter()
        held_keys['left mouse'] = 1
        yield from self.wait(4.0)
        held_keys['left mouse'] = 0
        wall = pytime.perf_counter() - t0
        times = list(combat.weapon.shot_times)[n0:]
        gaps = [b - a for a, b in zip(times, times[1:])]
        rpm_sim = 60.0 / (sum(gaps) / len(gaps))
        rpm_wall = len(times) / wall * 60.0
        check('nhịp bắn theo đồng hồ game (phát/phút)', round(rpm_sim, 1), gun.rpm, abs(rpm_sim - gun.rpm) < 1.0)
        check('nhịp bắn theo đồng hồ thật (phát/phút)', round(rpm_wall, 1), gun.rpm, abs(rpm_wall - gun.rpm) < gun.rpm * 0.03)
        check('khoảng cách giữa các phát đều (lệch tối đa, s)', round(max(gaps) - min(gaps), 6), '< 0,001', max(gaps) - min(gaps) < 0.001)
        yield from self.wait(3.2)

        # --- đếm đạn: hết băng thì dừng; R nạp lại từ dự trữ ---
        phase['name'] = 'hết băng'
        aim(0, -25)
        self.reset(auto=True, mag=30)
        fired0 = combat.shots_fired
        held_keys['left mouse'] = 1
        yield from self.wait(3.5)
        check('bắn hết băng 30 viên: đúng 30 phát', combat.shots_fired - fired0, 30, combat.shots_fired - fired0 == 30)
        check('băng hết, giữ chuột vẫn không bắn thêm', combat.weapon.mag, 0, combat.weapon.mag == 0)
        held_keys['left mouse'] = 0
        combat.handling.cancel()                      # giữ cò khi băng cạn đã tự nạp (G5): ở đây chỉ kiểm phép đếm đạn
        taken = combat.weapon.load_magazine()
        check('nạp lại: lấy 30 từ dự trữ', f'{combat.weapon.mag}/{combat.weapon.reserve} (lấy {taken})', f'30/{gun.reserve - 30} (lấy 30)',
              (combat.weapon.mag, combat.weapon.reserve, taken) == (30, gun.reserve - 30, 30))
        yield from self.wait(3.2)

        # --- cảnh chụp: loạt đạn vào bia 50 m, và 150 m ---
        phase['name'] = 'cảnh chụp'
        t50, t150 = game.targets[2], game.targets[4]
        aim(yaw_to(t50), 0.0)
        self.reset(auto=True)
        held_keys['left mouse'] = 1
        yield from self.wait(0.9)
        held_keys['left mouse'] = 0
        yield from self.wait(0.5)
        shot('burst_50')

        aim(yaw_to(t150), 0.0)
        yield from self.wait(0.3)
        shot('view_150')

        # --- lỗ đạn không phình mãi ---
        phase['name'] = 'lỗ đạn tối đa'
        aim(yaw_to(t25), 0.0)
        for _ in range(3):
            self.reset(auto=True, mag=500)
            held_keys['left mouse'] = 1
            yield from self.wait(1.0)
        held_keys['left mouse'] = 0
        check('số lỗ đạn bị chặn ở mức tối đa', combat.decals.count, game.params.feedback.max_holes,
              combat.decals.count <= game.params.feedback.max_holes)
        yield from self.wait(1.0)


def report():
    print('\n=== KIỂM TRA G2 ===')
    print(f"{'mục':58s} {'đo được':>20s} {'mong đợi':>18s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:58s} {str(got):>20s} {str(expected):>18s}  {"ĐẠT" if ok else "TRƯỢT"}')
    dts = sorted(frame_dts)
    n = len(dts)
    print(f'\nFPS (vsync tắt, 1280x720, gồm cả lúc bắn liên thanh): {n} khung, trung bình {n / sum(dts):.0f}, '
          f'thấp nhất {1 / dts[-1]:.0f}, 1% thấp nhất {1 / dts[int(n * 0.99)]:.0f}')
    worst = sorted(zip(frame_dts, frame_phase), reverse=True)[:6]
    print('khung chậm nhất: ' + ', '.join(f'{dt * 1000:.0f} ms ({ph})' for dt, ph in worst))
    print(f'{sum(r[3] for r in results)}/{len(results)} mục đạt')


Script()
game.app.run()
