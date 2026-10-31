"""G3: recoil (camera + súng) và độ tản (spread/bloom/tâm ngắm) bằng game thật.

Điều khiển qua đúng đường của game (held_keys, combat.pressed). Đo:
  - mẫu recoil 30 phát: đúng hướng, đúng độ lớn, lặp lại giống nhau (trừ nhiễu), hồi 30% sau khi ngừng bắn
  - độ tản hông theo trạng thái (đứng/ngồi/đi/chạy/nhảy) và khi ngắm: đo từ hướng đạn thật so với hướng nhìn
  - bloom cộng dồn và hồi; tâm ngắm động khớp phép chiếu thật của camera; kick súng thấy được trên màn hình
Ảnh vào shots\\g3_*.png.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\g3_selftest.py        (thoát mã 1 nếu có mục trượt)
"""
import math
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename, Point2, Point3  # noqa: E402
from ursina import Entity, application, camera, held_keys, mouse, time  # noqa: E402

from fps.game.hud import CROSSHAIR_LEN  # noqa: E402
from fps.core.movement import MoveState, aim_direction  # noqa: E402
from fps.core.recoil import CameraRecoil, GunKick  # noqa: E402
from fps.core.spread import angle_between, crosshair_gap  # noqa: E402
from fps.weapon_data import M4_PATTERN  # noqa: E402

game = create_game(vsync=False)
player, combat, hud, viewmodel = game.player, game.combat, game.hud, game.viewmodel
gun = game.params.gun
acc = gun.accuracy
mouse.locked = False                      # không giữ con trỏ của người dùng
combat.require_locked_mouse = False       # cho phép bắn dù chuột không bị bắt (chỉ trong bài kiểm tra)
combat.rng.seed(20240131)                 # lặp lại được (nhưng nhịp khung hình vẫn đổi chút kết quả)

results = []
frame_dts = []
frame_phase = []
phase = {'name': 'khởi động'}
skip = {'next': False}
S = MoveState

shots_log = []                            # ShotInfo của mọi phát (chụp ngay trước khi đạn sinh ra)
_orig_fire = combat._fire


def _logged_fire(origin, direction, age):
    shots_log.append(combat.last_shot)
    return _orig_fire(origin, direction, age)


combat._fire = _logged_fire


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def shot(name):
    out = ROOT / 'shots' / f'g3_{name}.png'
    out.parent.mkdir(exist_ok=True)
    application.base.win.saveScreenshot(Filename.from_os_specific(str(out)))
    skip['next'] = True
    print('ĐÃ CHỤP', out.name)


def view_angles(d):
    """(lên, phải) độ của vector hướng."""
    return math.degrees(math.asin(max(-1.0, min(1.0, d[1])))), math.degrees(math.atan2(d[0], d[2]))


def gun_center():
    """Tâm thân súng (nút Main, không skin nên đi theo `sway`) trong hệ camera vẽ súng: (x phải, y lên, z ra trước).
    Không dùng cả actor: hộp bao của tay kéo dài ra sau lưng camera nên tâm của nó gần như không dịch khi súng xoay."""
    lo, hi = viewmodel.actor.find('**/Main_M4_D_0-parent').get_tight_bounds(viewmodel.cam_np)
    return tuple(float((lo[i] + hi[i]) / 2) for i in range(3))


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.last = None
        self.means = {}                   # tên điều kiện -> góc lệch trung bình đo được

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

    # --- đưa mọi thứ về trạng thái đầu ---
    def reset_state(self, auto=True, mag=30, pitch=0.0, ads=0.0):
        for k in ('w', 'a', 's', 'd', 'shift', 'control', 'space', 'left mouse'):
            held_keys[k] = 0
        player.position = (0, 0, 0)
        player.vx = player.vz = player.vy = 0.0
        player.on_ground = True
        player.yaw, player.pitch = 0.0, pitch
        player._apply_view()
        player.ads, player.ads_amount = ads > 0, ads
        combat.recoil = CameraRecoil(gun.recoil, combat.rng)
        combat.gun_kick = GunKick(gun.kick, combat.rng)
        combat.accuracy.bloom = 0.0
        combat.accuracy.since_shot = 1e9
        combat.bullets.clear()
        combat.weapon.auto = auto
        combat.weapon.mag = mag
        combat.weapon.reserve = 150
        combat.weapon.cooldown = 0.0

    def spray(self, track=None):
        """Bóp cò bắn hết băng 30 viên (đúng nhịp thật). `track` gọi mỗi khung."""
        self.reset_state(auto=True, mag=30)
        shots_log.clear()
        yield from self.wait(0.05)
        held_keys['left mouse'] = 1
        while combat.weapon.mag > 0:
            yield
            if track:
                track()
        held_keys['left mouse'] = 0

    def expected_cumulative(self, k, index):
        """Góc tích luỹ mong đợi (không nhiễu) lúc phát thứ k nổ, của thành phần `index` (0 = lên, 1 = phải)."""
        dt_shot, tau = 60.0 / gun.rpm, gun.recoil.kick_time
        return sum(M4_PATTERN[j][index] * (1.0 - math.exp(-(k - j) * dt_shot / tau)) for j in range(k))

    def measure_spread(self, name, keys, state, ads=0.0, seconds=1.0, lead=0.5, jump=False):
        """Bắn nhanh (4 ms một phát, tắt bloom) lên trời ở trạng thái `state`; trả về danh sách góc lệch (độ)."""
        self.reset_state(auto=True, mag=100000, pitch=-25.0, ads=ads)
        shots_log.clear()
        for k in keys:
            held_keys[k] = 1
        if jump:
            yield
            yield
            held_keys['space'] = 0
        else:
            yield from self.wait(lead)
        in_state = player.state is state
        held_keys['left mouse'] = 1
        yield from self.wait(seconds)
        held_keys['left mouse'] = 0
        for k in keys:
            held_keys[k] = 0
        samples = [angle_between(s.view_dir, s.direction) for s in shots_log if s.state is state]
        cfg = combat.accuracy.base(state, ads)
        n = len(samples)
        mean = sum(samples) / n if n else 0.0
        top = max(samples) if samples else 0.0
        check(f'{name}: đang đúng trạng thái {state.value}', in_state, True, in_state)
        check(f'{name}: đủ mẫu (>= 100)', n, '>= 100', n >= 100)
        check(f'{name}: góc lệch trung bình (độ), nền {cfg:.2f}', round(mean, 3), f'{2 / 3 * cfg:.3f} +-12%',
              abs(mean - 2 / 3 * cfg) <= 0.12 * 2 / 3 * cfg)
        check(f'{name}: mọi phát nằm trong hình nón', round(top, 3), f'<= {cfg:.3f}', top <= cfg + 1e-6)
        self.means[name] = mean
        yield from self.wait(0.8 if jump else 0.3)

    def run(self):
        yield from self.wait(0.6)
        frame_dts.clear()
        frame_phase.clear()

        # --- A. dấu của kick súng trên màn hình ---
        phase['name'] = 'kick tĩnh'
        self.reset_state()
        viewmodel.update((0, 0, 0, 0, 0, 0))
        x0, y0, z0 = gun_center()
        viewmodel.update((0, 0, -0.02, 0, 0, 0))
        _, _, z1 = gun_center()
        check('kick lùi (z âm): súng lại gần mắt', round((z1 - z0) * 1000, 1), '-20 mm', abs((z1 - z0) + 0.02) < 0.002)
        viewmodel.update((0, 0, 0, 5.0, 0, 0))
        _, y1, _ = gun_center()
        check('pitch ngóc lên 5 độ: thân súng lên cao hơn (mm)', round((y1 - y0) * 1000, 1), '> 10', y1 - y0 > 0.010)
        viewmodel.update((0, 0, 0, 0, 5.0, 0))
        x1, _, _ = gun_center()
        check('yaw phải 5 độ: thân súng sang phải (mm)', round((x1 - x0) * 1000, 1), '> 10', x1 - x0 > 0.010)
        viewmodel.update((0, 0, 0, 0, 0, 5.0))
        x2, y2, _ = gun_center()
        # thân súng nằm dưới-phải trục nhìn; nghiêng phải (cùng chiều kim đồng hồ) kéo nó xuống và sang trái
        check('roll phải 5 độ: thân súng (dưới-phải) đi xuống và sang trái (mm)',
              f'{(x2 - x0) * 1000:.1f}, {(y2 - y0) * 1000:.1f}', '< 0, < 0', x2 - x0 < 0 and y2 - y0 < 0)
        viewmodel.update((0, 0, 0, 0, 0, 0))

        # --- B. mẫu recoil: hai loạt đạn hông, đứng yên, KHÔNG kéo chuột bù ---
        runs = []
        pitch_trace = []
        for i in range(2):
            phase['name'] = f'loạt {i + 1}'
            self.reset_state()
            pitch_trace.clear()
            yield from self.spray(track=lambda: pitch_trace.append(player.pitch))
            angles = [view_angles(s.view_dir) for s in shots_log]
            up0, right0 = angles[0]
            runs.append([(a - up0, b - right0) for a, b in angles])
            if i == 0:
                t = 0.0
                while t < 1.5:               # ghi cả đoạn sau khi ngừng bắn để bắt đúng đỉnh trước khi hồi
                    yield
                    t += min(time.dt, 0.05)
                    pitch_trace.append(player.pitch)
                peak_pitch = min(pitch_trace)
                rise = 0.0 - peak_pitch      # reset_state đặt pitch = 0
                back = player.pitch - peak_pitch
                check('hồi sau khi ngừng bắn (phần của cú giật)', round(back / rise, 3), f'{gun.recoil.recovery} +-0.03',
                      abs(back / rise - gun.recoil.recovery) < 0.03)
                check('camera thật sự bị kéo lên sau cả băng (độ)', round(rise, 2), '> 6', rise > 6)
            else:
                yield from self.wait(1.0)

        n = len(runs[0])
        check('bắn đủ 30 phát mỗi loạt', (len(runs[0]), len(runs[1])), (30, 30), len(runs[0]) == len(runs[1]) == 30)
        for i, run in enumerate(runs):
            ups = [r[0] for r in run]
            rights = [r[1] for r in run]
            check(f'loạt {i + 1}: góc nhìn chỉ đi lên (đơn điệu)', '', '', all(b >= a - 1e-9 for a, b in zip(ups, ups[1:])))
            exp_up = [self.expected_cumulative(k, 0) for k in range(n)]
            exp_right = [self.expected_cumulative(k, 1) for k in range(n)]
            err_up = max(abs(u - e) - (0.06 * e + 0.05) for u, e in zip(ups, exp_up))
            err_right = max(abs(r - e) - (0.06 * e + 0.12) for r, e in zip(rights, exp_right))
            check(f'loạt {i + 1}: lên đúng mẫu (độ lúc phát 30)', round(ups[-1], 2), f'{exp_up[-1]:.2f} +-6%', err_up <= 0)
            check(f'loạt {i + 1}: ngang đúng mẫu (độ lúc phát 30)', round(rights[-1], 2), f'{exp_right[-1]:.2f}', err_right <= 0)
            check(f'loạt {i + 1}: trôi sang phải', round(rights[-1], 2), '> 0', rights[-1] > 0)
        diff = max(abs(a[0] - b[0]) for a, b in zip(*runs))
        diff_r = max(abs(a[1] - b[1]) for a, b in zip(*runs))
        exp_total = self.expected_cumulative(29, 0)
        check('hai loạt KHÔNG giống hệt nhau (có nhiễu, độ)', round(max(diff, diff_r), 3), '> 0.001', max(diff, diff_r) > 0.001)
        check('nhưng lệch nhau vừa phải (<= 12% mẫu + 0,1 độ)', round(diff, 3), f'<= {0.12 * exp_total + 0.1:.2f}',
              diff <= 0.12 * exp_total + 0.1)
        print('MẪU (lên, phải) tại phát 1/5/10/15/20/25/30, loạt 1:',
              [(round(runs[0][k][0], 2), round(runs[0][k][1], 2)) for k in (0, 4, 9, 14, 19, 24, 29)])
        print('                                             loạt 2:',
              [(round(runs[1][k][0], 2), round(runs[1][k][1], 2)) for k in (0, 4, 9, 14, 19, 24, 29)])

        # --- C. bloom với số thật: hông, đứng ---
        phase['name'] = 'bloom'
        self.reset_state()
        shots_log.clear()
        yield from self.wait(0.05)
        held_keys['left mouse'] = 1
        while combat.weapon.mag > 0:
            yield
        held_keys['left mouse'] = 0
        spreads = [s.spread for s in shots_log]
        expected = [acc.stand + min(acc.bloom_per_shot * k, acc.bloom_max) for k in range(30)]
        check('phát đầu tản đúng nền đứng (độ)', round(spreads[0], 3), acc.stand, abs(spreads[0] - acc.stand) < 1e-9)
        check('bloom +0,25 độ mỗi phát, trần 4 độ', round(spreads[-1], 3), acc.stand + acc.bloom_max,
              all(abs(a - b) < 1e-9 for a, b in zip(spreads, expected)))
        check('tâm ngắm (spread_now) cuối loạt (độ)', round(combat.spread_now, 2), acc.stand + acc.bloom_max,
              abs(combat.spread_now - (acc.stand + acc.bloom_max)) < 0.15)
        yield from self.wait(0.5)
        want = acc.bloom_max - acc.bloom_recovery * (0.5 - acc.bloom_recovery_delay)
        check('0,5 s sau khi ngừng: bloom còn (độ)', round(combat.accuracy.bloom, 2), f'{want:.2f} +-0.3', abs(combat.accuracy.bloom - want) < 0.3)
        yield from self.wait(0.7)
        check('1,2 s sau khi ngừng: bloom về 0', round(combat.accuracy.bloom, 3), 0, combat.accuracy.bloom == 0)
        check('tản về nền đứng', round(combat.spread_now, 3), acc.stand, abs(combat.spread_now - acc.stand) < 1e-9)

        # ngắm: nền 0,1 độ và bloom gần như không tác dụng
        for ads, label in ((1.0, 'ADS hẳn'), (0.5, 'ADS nửa chừng')):
            self.reset_state(ads=ads)
            shots_log.clear()
            yield from self.wait(0.05)
            held_keys['left mouse'] = 1
            while combat.weapon.mag > 0:
                yield
            held_keys['left mouse'] = 0
            first, last = shots_log[0].spread, shots_log[-1].spread
            if ads == 1.0:
                check(f'{label}: phát đầu tản (độ)', round(first, 3), acc.ads, abs(first - acc.ads) < 1e-9)
                check(f'{label}: phát 30 vẫn rất chặt (độ)', round(last, 3), f'<= {acc.ads + acc.ads_bloom_multiplier * acc.bloom_max:.2f}',
                      last <= acc.ads + acc.ads_bloom_multiplier * acc.bloom_max + 1e-9)
            else:
                mid = (acc.stand + acc.ads) / 2
                check(f'{label}: phát đầu tản theo mức ADS hiện tại (độ)', round(first, 3), mid, abs(first - mid) < 1e-9)
            yield from self.wait(1.0)

        # --- D. độ tản theo trạng thái, đo từ hướng đạn thật (tắt bloom, bắn nhanh) ---
        phase['name'] = 'đo độ tản'
        saved = (acc.bloom_per_shot, combat.weapon.interval, gun.bullet_lifetime)
        acc.bloom_per_shot = 0.0
        combat.weapon.interval = 0.004
        gun.bullet_lifetime = 0.2
        yield from self.measure_spread('đứng', [], S.IDLE)
        yield from self.measure_spread('ngồi', ['control'], S.CROUCH_IDLE)
        yield from self.measure_spread('đi', ['w'], S.WALK)
        yield from self.measure_spread('đi ngồi', ['w', 'control'], S.CROUCH_WALK)
        yield from self.measure_spread('chạy nước rút', ['w', 'shift'], S.SPRINT)
        yield from self.measure_spread('nhảy', ['space'], S.AIR, seconds=0.5, jump=True)
        yield from self.measure_spread('ADS đứng yên', [], S.IDLE, ads=1.0)
        yield from self.measure_spread('ADS đi', ['w'], S.WALK, ads=1.0)
        acc.bloom_per_shot, combat.weapon.interval, gun.bullet_lifetime = saved

        m = self.means
        check('ĐỀ BÀI: hông đi/chạy tản rộng hơn đứng (đi / đứng)', round(m['đi'] / m['đứng'], 2), '1.5 .. 2.0', 1.5 <= m['đi'] / m['đứng'] <= 2.0)
        check('ĐỀ BÀI: hông chạy tản rộng hơn đứng (chạy / đứng)', round(m['chạy nước rút'] / m['đứng'], 2), '1.9 .. 2.6',
              1.9 <= m['chạy nước rút'] / m['đứng'] <= 2.6)
        check('ngồi chặt hơn đứng', round(m['ngồi'] / m['đứng'], 2), '~0.7', 0.6 <= m['ngồi'] / m['đứng'] <= 0.8)
        check('nhảy rộng nhất', round(m['nhảy'] / m['đứng'], 2), '~3', m['nhảy'] > m['chạy nước rút'] > m['đi'] > m['đứng'])
        check('ĐỀ BÀI: ADS đứng yên ≈ không tản (độ)', round(m['ADS đứng yên'], 3), '< 0.1', m['ADS đứng yên'] < 0.1)
        check('ADS chặt hơn hông (cấu hình 20 lần; đo >= 15)', round(m['đứng'] / m['ADS đứng yên'], 1), '>= 15',
              m['đứng'] / m['ADS đứng yên'] >= 15)

        # --- E. tâm ngắm động khớp phép chiếu thật của camera thế giới ---
        phase['name'] = 'tâm ngắm'
        self.reset_state()
        yield from self.wait(0.4)

        def gap_on_screen():
            return abs(hud.crosshair[0][0].x) - CROSSHAIR_LEN / 2

        def projected(angle):
            out = Point2()
            camera.lens.project(Point3(0, math.tan(math.radians(angle)), 1), out)
            return out.y * 0.5

        check('tâm ngắm đứng khớp phép chiếu (đơn vị UI)', round(gap_on_screen(), 4), round(projected(acc.stand), 4),
              abs(gap_on_screen() - projected(acc.stand)) < 0.0015)
        vtan = math.tan(math.radians(game.params.player.fov / 2)) / camera.lens.get_aspect_ratio()
        check('hàm crosshair_gap khớp phép chiếu thật', round(crosshair_gap(acc.stand, vtan), 4), round(projected(acc.stand), 4),
              abs(crosshair_gap(acc.stand, vtan) - projected(acc.stand)) < 1e-4)
        shot('crosshair_idle')
        gap_idle = gap_on_screen()

        held_keys['w'] = 1
        yield from self.wait(0.6)
        gap_walk = gap_on_screen()
        check('tâm ngắm giãn ra khi đi', round(gap_walk, 4), f'> {gap_idle:.4f}', gap_walk > gap_idle * 1.5)
        check('  khớp phép chiếu của góc đi', round(gap_walk, 4), round(projected(acc.walk), 4), abs(gap_walk - projected(acc.walk)) < 0.0015)
        shot('crosshair_walk')
        held_keys['shift'] = 1
        yield from self.wait(0.6)
        gap_sprint = gap_on_screen()
        check('tâm ngắm giãn nữa khi chạy', round(gap_sprint, 4), f'> {gap_walk:.4f}', gap_sprint > gap_walk)
        held_keys['w'] = held_keys['shift'] = 0
        yield from self.wait(0.5)
        held_keys['control'] = 1
        yield from self.wait(0.5)
        gap_crouch = gap_on_screen()
        check('tâm ngắm co lại khi ngồi', round(gap_crouch, 4), f'< {gap_idle:.4f}', gap_crouch < gap_idle)
        held_keys['control'] = 0
        yield from self.wait(0.5)

        player.ads, player.ads_amount = True, 1.0
        yield from self.wait(0.3)
        alpha_ads = hud.crosshair[0][0].color.a
        check('tâm ngắm ẩn khi ngắm (ADS)', round(alpha_ads, 3), 0, alpha_ads == 0)
        shot('ads_no_crosshair')
        player.ads, player.ads_amount = False, 0.0
        yield from self.wait(0.3)

        # --- F. loạt thứ ba: ảnh giữa loạt, kick súng thấy được, camera = hướng bắn ---
        phase['name'] = 'loạt 3'
        self.reset_state()
        yield from self.wait(0.3)
        rest = gun_center()
        kick_z = []
        kick_y = []
        gun_z = []
        shot_taken = {'mid': False}

        def track():
            kick_z.append(combat.gun_kick.pose[2])
            kick_y.append(combat.gun_kick.pose[1])
            gun_z.append(gun_center()[2])
            if combat.weapon.mag == 15 and not shot_taken['mid']:
                shot_taken['mid'] = True
                shot('spray_mid')

        yield from self.spray(track=track)
        phase['name'] = 'loạt 3 sau'
        yield from self.wait(0.15)
        shot('spray_end')
        peak_back = min(kick_z)
        check('kick súng lùi lại trong loạt (mm)', round(peak_back * 1000, 1), f'<= -{abs(gun.kick.peak[2]) * 1000 * 0.8:.0f}',
              peak_back <= -abs(gun.kick.peak[2]) * 0.8)
        check('kick súng chưa vượt 4x một phát đơn', round(peak_back * 1000, 1), f'>= -{abs(gun.kick.peak[2]) * 4000:.0f}',
              peak_back >= -abs(gun.kick.peak[2]) * 4)
        check('trên màn hình súng thật sự lại gần mắt hơn khi bắn (mm)', round((min(gun_z) - rest[2]) * 1000, 1), '< -5',
              min(gun_z) - rest[2] < -0.005)
        d_world = tuple(camera.forward)
        d_expected = aim_direction(player.yaw, player.pitch)
        check('camera thế giới khớp tia ngắm sau recoil (độ lệch)', round(angle_between(d_world, d_expected), 4), '< 0.01',
              angle_between(d_world, d_expected) < 0.01)
        yield from self.wait(0.6)
        settled = max(abs(v) for v in combat.gun_kick.pose[:3])
        check('0,75 s sau khi ngừng: kick súng đã yên (mm)', round(settled * 1000, 3), '< 1', settled < 0.001)
        phase['name'] = 'xong'
        yield from self.wait(0.3)


def report():
    print('\n=== KIỂM TRA G3 ===')
    print(f"{'mục':64s} {'đo được':>16s} {'mong đợi':>22s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:64s} {str(got):>16s} {str(expected):>22s}  {"ĐẠT" if ok else "TRƯỢT"}')
    # loại các đoạn tự làm chậm khung: đo độ tản (250 phát/giây) và loạt 3 (đo hộp bao súng mỗi khung)
    pairs = [(dt, ph) for dt, ph in zip(frame_dts, frame_phase) if ph not in ('đo độ tản', 'loạt 3')]
    dts = sorted(dt for dt, _ in pairs)
    n = len(dts)
    avg = n / sum(dts)
    low1 = 1 / dts[int(n * 0.99)]
    print(f'\nFPS (vsync tắt, 1280x720, gồm hai loạt bắn thật liên thanh; trừ phần tự làm chậm khung): '
          f'{n} khung, trung bình {avg:.0f}, 1% thấp nhất {low1:.0f}, khung chậm nhất {dts[-1] * 1000:.0f} ms')
    worst = sorted(pairs, reverse=True)[:5]
    print('khung chậm nhất: ' + ', '.join(f'{dt * 1000:.0f} ms ({ph})' for dt, ph in worst))
    results.append(('FPS trung bình >= 60', round(avg), '>= 60', avg >= 60))
    print(f'{sum(r[3] for r in results)}/{len(results)} mục đạt')


Script()
game.app.run()
