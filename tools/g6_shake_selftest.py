"""G6: camera shake (bắn + nạp) bằng game thật.

Đo:
  - dấu của camera thế giới và súng trên màn hình (phép chiếu thật)
  - rung khi bắn liên thanh một băng 30 viên: độ nghiêng (roll), độ lệch hướng nhìn (pitch/yaw), dịch chuyển, độ dịch theo điểm ảnh; trần; tắt đúng hạn
  - rung khi nạp (còn đạn / băng cạn): mốc nổ đúng khung của clip (băng vào chỗ trùng lúc đạn đổi), nhẹ, không rung suốt clip, huỷ nạp bỏ mốc chưa tới
  - rung CHỈ LÀ HÌNH ẢNH: chạy cùng một kịch bản bắn (cùng seed, bước dt cố định) với rung bật và tắt, tia ngắm / hướng đạn / điểm trúng phải GIỐNG HỆT
  - ngắm (ADS) giảm rung còn đúng tỉ lệ cấu hình
Ảnh vào shots\\shake_*.png.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\g6_shake_selftest.py        (thoát mã 1 nếu có mục trượt)
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
from ursina import Entity, application, camera, held_keys, mouse, time, window  # noqa: E402

from fps.core.movement import aim_direction  # noqa: E402
from fps.core.recoil import CameraRecoil, GunKick  # noqa: E402
from fps.core.spread import angle_between  # noqa: E402

game = create_game(vsync=False, sound=False, draw=False)
player, combat, viewmodel = game.player, game.combat, game.viewmodel
shake = game.shake
gun = game.params.gun
D = gun.shake
mouse.locked = False
combat.require_locked_mouse = False

results = []
skip = {'next': False}
S_SEED = 20240601


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def shot(name):
    out = ROOT / 'shots' / f'shake_{name}.png'
    out.parent.mkdir(exist_ok=True)
    application.base.win.saveScreenshot(Filename.from_os_specific(str(out)))
    skip['next'] = True
    print('ĐÃ CHỤP', out.name)


def screen_px(p):
    """Điểm thế giới -> pixel so với tâm màn hình (x phải, y lên), theo camera thế giới hiện tại."""
    out = Point2()
    camera.lens.project(camera.getRelativePoint(application.base.render, Point3(*p)), out)
    return out.x * window.size[0] / 2, out.y * window.size[1] / 2


def probe_point():
    """Điểm cách mắt 50 m, lệch 30 độ phải / 15 độ lên so với tia ngắm: gần góc màn hình nên thấy cả roll lẫn pitch/yaw."""
    origin, view = player.aim_ray()
    yaw, pitch = player.yaw + 30.0, player.pitch - 15.0
    d = aim_direction(yaw, pitch)
    return tuple(origin[i] + d[i] * 50.0 for i in range(3))


def shake_metrics():
    """Độ lệch của camera thế giới do rung (so với tia ngắm của người chơi): (roll độ, lệch hướng nhìn độ, dịch mm, lệch điểm ảnh)."""
    rot, pos = tuple(camera.rotation), tuple(camera.position)
    p = probe_point()
    with_shake = screen_px(p)
    camera.rotation, camera.position = (0, 0, 0), (0, 0, 0)
    without = screen_px(p)
    camera.rotation, camera.position = rot, pos
    dev = angle_between(tuple(camera.forward), aim_direction(player.yaw, player.pitch))
    return (abs(rot[2]), dev, math.sqrt(sum(c * c for c in pos)) * 1000.0,
            math.hypot(with_shake[0] - without[0], with_shake[1] - without[1]))


def gun_center():
    lo, hi = viewmodel.actor.find('**/Main_M4_D_0-parent').get_tight_bounds(viewmodel.cam_np)
    return tuple(float((lo[i] + hi[i]) / 2) for i in range(3))


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
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

    def reset_state(self, mag=30, ads=0.0, auto=True):
        for k in ('w', 'a', 's', 'd', 'shift', 'control', 'space', 'left mouse', 'right mouse'):
            held_keys[k] = 0
        player.position = (0, 0, 0)
        player.vx = player.vz = player.vy = 0.0
        player.on_ground = True
        player.yaw, player.pitch = 0.0, 0.0
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
        combat.pressed = False
        shake.reset()
        shake.t = 0.0                  # cùng đồng hồ nhiễu cho mọi lượt đo: so sánh bật/tắt, hông/ngắm công bằng
        shake.enabled = True
        shake.beat_log.clear()

    # --- bài đo bằng khung hình thật ---
    def real_spray(self, ads=0.0):
        """Bắn hết băng 30 viên bằng khung thật rồi chờ rung tắt; trả về danh sách số đo mỗi khung."""
        self.reset_state(ads=ads)
        combat.rng.seed(S_SEED)
        yield from self.wait(0.05)
        samples = []
        held_keys['left mouse'] = 1
        while combat.weapon.mag > 0:
            yield
            samples.append((combat.weapon.mag, shake.trauma) + shake_metrics())
        held_keys['left mouse'] = 0
        for _ in range(60):                       # ~1 s sau loạt cuối
            yield
            samples.append((0, shake.trauma) + shake_metrics())
        self.spray_samples = samples

    def reload_run(self, mag, label, cancel_after_frame=None):
        """Nạp bằng khung thật; ghi số đo mỗi khung. Trả về (mẫu, thời gian bắt đầu)."""
        self.reset_state(mag=mag)
        yield from self.wait(0.3)
        shake.beat_log.clear()
        samples = []
        mags = []
        t0 = pytime.perf_counter()
        combat.request_reload()
        cancelled = False
        while True:
            yield
            now = pytime.perf_counter() - t0
            h = combat.handling
            samples.append((now,) + shake_metrics())
            mags.append((shake.t, combat.weapon.mag))
            if cancel_after_frame and not cancelled and h.frame and h.frame >= cancel_after_frame:
                h.cancel()
                cancelled = True
            if not h.busy and now > 0.2:
                break
            if now > 8:
                break
        yield from self.wait(0.5)
        return samples, mags

    # --- kịch bản xác định (bước dt cố định, không qua cửa sổ) để so rung bật / tắt ---
    def deterministic_pass(self, shake_on, ads=0.0):
        self.reset_state(ads=ads)
        shake.enabled = shake_on
        combat.rng.seed(S_SEED)
        combat.recoil = CameraRecoil(gun.recoil, combat.rng)
        combat.gun_kick = GunKick(gun.kick, combat.rng)
        rays, views, impacts, rolls, gun_off = [], [], [], [], []
        hits0 = combat.target_hits
        orig_hit = combat._on_hit

        def logged_hit(bullet, hit):
            impacts.append(tuple(hit.point))
            return orig_hit(bullet, hit)

        combat._on_hit = logged_hit
        shots_log = []
        orig_fire = combat._fire

        def logged(origin, direction, age):
            shots_log.append((combat.last_shot.view_dir, combat.last_shot.direction, origin))
            return orig_fire(origin, direction, age)

        combat._fire = logged
        dt = 1.0 / 120.0
        try:
            held_keys['left mouse'] = 1
            for i in range(240):                             # 2 s: băng 30 viên (2,4 s ở 750 phát/phút) bắn khoảng 25 viên
                combat.update(dt, dt)
                pose = game.shake_view.apply(player.ads_amount)
                rays.append(player.aim_ray())
                views.append((player.yaw, player.pitch))
                rolls.append(abs(camera.rotation_z))
                viewmodel.update(combat.gun_kick.pose, pose)
                if i % 6 == 0:
                    gun_off.append(gun_center())
            held_keys['left mouse'] = 0
            for i in range(400):                             # chờ đạn bay hết
                combat.update(dt, dt)
                if not combat.bullets:
                    break
        finally:
            combat._fire = orig_fire
            combat._on_hit = orig_hit
            held_keys['left mouse'] = 0
        return dict(rays=rays, views=views, shots=shots_log, impacts=impacts, rolls=rolls, gun=gun_off, hits=combat.target_hits - hits0)

    def run(self):
        yield from self.wait(0.6)

        # --- A. dấu: camera thế giới và súng trên màn hình ---
        self.reset_state()
        yield from self.wait(0.1)
        far = (4.0, player.camera_pivot.y + 0.0, 12.0)           # phía phải, ngang tầm mắt
        base = screen_px(far)
        base_center = screen_px((0.0, player.camera_pivot.y, 12.0))
        viewmodel.update((0.0,) * 6)           # tư thế súng trần (không sway), làm gốc so sánh
        gun0 = gun_center()

        def set_pose(i, v):
            shake.spring.x = [0.0] * 6
            shake.spring.x[i] = v
            return game.shake_view.apply(0.0)

        gp = set_pose(5, 0.5)
        p = screen_px(far)
        check('roll phải +0,5 độ: điểm bên phải màn hình đi LÊN', round(p[1] - base[1], 1), '> 0', p[1] - base[1] > 2)
        gp = set_pose(3, 0.5)
        p = screen_px((0.0, player.camera_pivot.y, 12.0))
        check('pitch ngóc +0,5 độ: điểm giữa đi XUỐNG', round(p[1] - base_center[1], 1), '< 0', p[1] - base_center[1] < -2)
        viewmodel.update(gp)
        gun_pitch_dy = gun_center()[1] - gun0[1]
        check('  súng cũng đi xuống (theo thế giới, ít hơn)', round(gun_pitch_dy * 1000, 2), '< 0 (mm)', gun_pitch_dy < -0.0001)
        gp = set_pose(4, 0.5)
        p = screen_px((0.0, player.camera_pivot.y, 12.0))
        check('yaw phải +0,5 độ: điểm giữa đi sang TRÁI', round(p[0] - base_center[0], 1), '< 0', p[0] - base_center[0] < -2)
        viewmodel.update(gp)
        gun_yaw_dx = gun_center()[0] - gun0[0]
        check('  súng cũng sang trái (theo thế giới, ít hơn)', round(gun_yaw_dx * 1000, 2), '< 0 (mm)', gun_yaw_dx < -0.0001)
        gp = set_pose(0, 0.002)
        p = screen_px((0.0, player.camera_pivot.y, 12.0))
        check('dịch camera +2 mm sang phải: điểm giữa sang trái', round(p[0] - base_center[0], 2), '< 0', p[0] - base_center[0] < -0.01)
        shake.reset()
        viewmodel.update((0.0,) * 6)
        game.shake_view.apply(0.0)
        check('hết rung: camera về đúng (0,0,0)', (tuple(camera.position), tuple(camera.rotation)), '0', not any(camera.position) and not any(camera.rotation))
        g = gun_center()
        check('hết rung: súng về chỗ cũ (mm)', round(max(abs(a - b) for a, b in zip(g, gun0)) * 1000, 3), '< 0.01',
              max(abs(a - b) for a, b in zip(g, gun0)) < 1e-5)

        # --- B. bắn một băng ---
        yield from self.real_spray()
        s = self.spray_samples
        firing = [x for x in s if x[0] > 0]
        roll_max = max(x[2] for x in s)
        dev_max = max(x[3] for x in s)
        mm_max = max(x[4] for x in s)
        px_max = max(x[5] for x in s)
        tr_max = max(x[1] for x in s)
        cap = D.fire_max_trauma
        print(f'BẮN (một băng 30 viên, hông): roll tối đa {roll_max:.3f} độ, lệch hướng nhìn tối đa {dev_max:.3f} độ, dịch tối đa {mm_max:.2f} mm, '
              f'điểm ảnh lệch tối đa {px_max:.1f} px (điểm gần góc màn hình), trauma tối đa {tr_max:.2f}')
        ceiling = cap ** D.power
        check('bắn: trauma lên sát trần mà không vượt (đo cuối khung)', round(tr_max, 3), f'{cap - D.fire_decay * 0.04:.2f} .. {cap}',
              cap - D.fire_decay * 0.04 <= tr_max <= cap + 1e-9)
        check('bắn: roll nhìn thấy được (độ)', round(roll_max, 3), '>= 0.15', roll_max >= 0.15)
        check('bắn: roll vừa phải (độ)', round(roll_max, 3), f'<= {D.fire_amp[5] * ceiling + 0.02:.2f}', roll_max <= D.fire_amp[5] * ceiling + 0.02)
        check('bắn: lệch hướng nhìn (pitch/yaw) vừa phải (độ)', round(dev_max, 3), '<= 0.3', dev_max <= 0.3)
        check('bắn: dịch chuyển vừa phải (mm)', round(mm_max, 2), '<= 2.5', mm_max <= 2.5)
        check('bắn: dịch trên màn hình vừa phải (px)', round(px_max, 1), '2 .. 14', 2 <= px_max <= 14)
        late = [x for x in firing if x[0] <= 10]
        early = [x for x in firing if x[0] >= 25]
        check('bắn: rung dựng dần (10 viên cuối > 3 viên đầu)', f'{max(x[2] for x in late):.2f} vs {max(x[2] for x in early):.2f}', 'lớn hơn',
              max(x[2] for x in late) > max(x[2] for x in early))
        tail = s[-30:]
        check('bắn: ~0,5 s sau loạt cuối rung đã tắt hẳn', round(max(x[2] for x in tail), 4), '0', max(x[2] + x[3] + x[4] for x in tail) < 0.01)
        check('bắn: camera về đúng 0 (độ)', tuple(round(c, 6) for c in camera.rotation), '(0,0,0)', not any(camera.rotation))
        yield from self.wait(0.3)

        # ảnh giữa loạt
        self.reset_state()
        combat.rng.seed(S_SEED)
        yield from self.wait(0.1)
        held_keys['left mouse'] = 1
        while combat.weapon.mag > 12:
            yield
        shot('spray_mid')
        while combat.weapon.mag > 0:
            yield
        held_keys['left mouse'] = 0
        yield from self.wait(1.0)

        # ảnh phóng đại (x8) để kiểm bằng mắt rằng cả thế giới và súng cùng rung đúng hướng
        saved_amp = D.fire_amp
        D.fire_amp = tuple(c * 8 for c in saved_amp)
        self.reset_state()
        combat.rng.seed(S_SEED)
        yield from self.wait(0.1)
        held_keys['left mouse'] = 1
        while combat.weapon.mag > 12:
            yield
        shot('spray_mid_x8')
        while combat.weapon.mag > 0:
            yield
        held_keys['left mouse'] = 0
        D.fire_amp = saved_amp
        yield from self.wait(1.0)

        # --- C. ngắm (ADS) ---
        res_hip = self.deterministic_pass(True, ads=0.0)
        res_ads = self.deterministic_pass(True, ads=1.0)
        roll_hip, roll_ads = max(res_hip['rolls']), max(res_ads['rolls'])
        check('ADS: rung còn đúng tỉ lệ cấu hình', round(roll_ads / roll_hip, 3), D.ads_multiplier, abs(roll_ads / roll_hip - D.ads_multiplier) < 0.02)
        yield from self.wait(0.5)

        # --- D. nạp đạn ---
        for key, mag, label in (('reload', 20, 'reload'), ('reload_empty', 0, 'reload_empty')):
            samples, mags = yield from self.reload_run(mag, label)
            clip = gun.clips[key]
            beats = list(shake.beat_log)
            expected = D.reload_beats[key]
            check(f'nạp {key}: đủ {len(expected)} mốc, đúng thứ tự', [k for _, k in beats], [k for _, k in expected],
                  [k for _, k in beats] == [k for _, k in expected])
            roll = max(x[1] for x in samples)
            dev = max(x[2] for x in samples)
            mm = max(x[3] for x in samples)
            px = max(x[4] for x in samples)
            total = clip.duration / gun.reload.speed
            noisy = sum(1 for x in samples if x[1] > 0.02 or x[2] > 0.02) / max(len(samples), 1)
            print(f'NẠP {key}: roll tối đa {roll:.3f} độ, lệch hướng nhìn tối đa {dev:.3f} độ, dịch tối đa {mm:.2f} mm, điểm ảnh lệch tối đa {px:.1f} px, '
                  f'rung > 0,02 độ trong {noisy * 100:.0f}% số khung (clip {total:.2f} s)')
            check(f'nạp {key}: rung nhẹ (độ)', round(max(roll, dev), 3), '0.05 .. 0.35', 0.05 <= max(roll, dev) <= 0.35)
            check(f'nạp {key}: dịch nhẹ (mm)', round(mm, 2), '<= 2.5', mm <= 2.5)
            check(f'nạp {key}: không rung suốt clip (khung có rung > 0,02 độ)', f'{noisy * 100:.0f}%', '<= 35%', noisy <= 0.35)
            # mốc 'seat' trùng lúc băng đổi đạn: thời điểm đạn đổi (mags) so với đồng hồ của mốc
            seat_t = next(t for t, k in beats if k == 'seat')
            swapped_at = next((t for t, m in mags if m != mag), None)
            gap = None if swapped_at is None else swapped_at - seat_t
            check(f'nạp {key}: đạn đổi cùng khung với mốc băng vào chỗ (s)', None if gap is None else round(gap, 3), '0 .. 0.06',
                  gap is not None and -0.005 <= gap <= 0.06)
            if key == 'reload':
                check('  băng đầy sau nạp', combat.weapon.mag, gun.magazine, combat.weapon.mag == gun.magazine)
            yield from self.wait(0.4)

        # ảnh đúng lúc băng vào chỗ (nạp băng cạn, mốc 'seat' = khung 172)
        self.reset_state(mag=0)
        yield from self.wait(0.3)
        combat.request_reload()
        while not any(k == 'seat' for _, k in shake.beat_log):
            yield
        for _ in range(2):
            yield
        shot('reload_seat')
        yield from self.wait(0.3)
        combat.handling.cancel()
        yield from self.wait(0.3)

        # huỷ nạp bỏ mốc chưa tới: huỷ ngay sau 'seat' (khung 172) và trước 'bolt' (190)
        samples, mags = yield from self.reload_run(0, 'cancel', cancel_after_frame=176.0)
        kinds = [k for _, k in shake.beat_log]
        check('huỷ nạp sau mốc băng vào chỗ: bolt không nổ', kinds, "['mag_out', 'seat']", kinds == ['mag_out', 'seat'])
        yield from self.wait(0.3)

        # --- E. rung chỉ là hình ảnh: cùng kịch bản, rung bật / tắt ---
        on = self.deterministic_pass(True)
        off = self.deterministic_pass(False)
        n_shots = len(on['shots'])
        check('kịch bản xác định: bắn được cả loạt', n_shots, '>= 20', n_shots >= 20 and n_shots == len(off['shots']))
        check('rung có thật trong lần rung BẬT (roll tối đa, độ)', round(max(on['rolls']), 3), '>= 0.15', max(on['rolls']) >= 0.15)
        check('rung TẮT: camera không lệch (roll, độ)', max(off['rolls']), 0, max(off['rolls']) == 0)
        check('tia ngắm (gốc + hướng) giống hệt mỗi bước', on['rays'] == off['rays'], True, on['rays'] == off['rays'])
        check('yaw/pitch của người chơi giống hệt mỗi bước', on['views'] == off['views'], True, on['views'] == off['views'])
        check('hướng nhìn + hướng đạn + gốc đạn của từng phát giống hệt', on['shots'] == off['shots'], True, on['shots'] == off['shots'])
        same_hits = on['impacts'] == off['impacts']
        check('điểm trúng của mọi viên giống hệt', f'{len(on["impacts"])} điểm', 'giống hệt', same_hits and len(on['impacts']) > 5)
        check('số lần trúng bia như nhau', (on['hits'], off['hits']), 'bằng nhau', on['hits'] == off['hits'])
        gun_dev = max(max(abs(a - b) for a, b in zip(g1, g0)) for g1, g0 in zip(on['gun'], off['gun']))
        print(f'SÚNG trên màn hình: lệch tối đa do rung {gun_dev * 1000:.2f} mm (thân súng, hệ camera vẽ súng)')
        check('súng có rung theo (mm)', round(gun_dev * 1000, 2), '> 0.2', gun_dev * 1000 > 0.2)
        check('  nhưng nhẹ (mm)', round(gun_dev * 1000, 2), '<= 6', gun_dev * 1000 <= 6)

        # --- F. tia ngắm đọc từ Player không phụ thuộc camera đang rung ---
        self.reset_state()
        player.yaw, player.pitch = 33.0, -12.0
        player._apply_view()
        before = player.aim_ray()
        shake.spring.x = [0.003, 0.003, 0.003, 0.5, 0.5, 0.5]
        game.shake_view.apply(0.0)
        after = player.aim_ray()
        check('aim_ray không đổi khi camera đang rung mạnh', before == after, True, before == after)
        shake.reset()
        game.shake_view.apply(0.0)
        yield from self.wait(0.2)


def report():
    print('\n=== KIỂM TRA G6 (camera shake) ===')
    print(f"{'mục':70s} {'đo được':>22s} {'mong đợi':>22s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:70s} {str(got):>22s} {str(expected):>22s}  {"ĐẠT" if ok else "TRƯỢT"}')
    print(f'{sum(r[3] for r in results)}/{len(results)} mục đạt')


Script()
game.app.run()
