"""G3: recoil (camera + gun) and spread (spread/bloom/aim point) with the real game.

Drive through the game's own path (held_keys, combat.pressed). Measures:
  - 30-shot recoil pattern: correct direction, correct size, repeats the same (except for noise), recovers 30% after firing stops
  - hip spread by state (stand/crouch/walk/run/jump) and when aiming: measured from the real bullet direction against the view direction
  - bloom accumulates and recovers; the dynamic aim point matches the real camera projection; gun kick is visible on screen
Screenshots go to shots\\g3_*.png.

Run:  .venv\\Scripts\\python.exe -X utf8 tools\\selftests\\g3_selftest.py        (exits with code 1 if any item fails)
"""
import math
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename, Point2, Point3  # noqa: E402
from ursina import Entity, application, camera, held_keys, mouse, time  # noqa: E402

from fps.game.hud import CROSSHAIR_LEN  # noqa: E402
from fps.core.movement import MoveState, aim_direction  # noqa: E402
from fps.core.recoil import CameraRecoil, GunKick  # noqa: E402
from fps.core.spread import angle_between, crosshair_gap  # noqa: E402
from fps.core.spring import burst_peak_ratio  # noqa: E402

game = create_game(vsync=False, sound=False, draw=False, shake=False, moving_targets=False, hud=True, free_aim=False)     # still targets (G6); camera shake (G6) moves camera.forward / the gun position off the aim ray: off when measuring recoil / aim point
player, combat, hud, viewmodel = game.player, game.combat, game.hud, game.viewmodel
gun = game.params.gun
acc = gun.accuracy
# This test measures the MECHANISMS of spread, the aim point and the kick applied to the camera (all kept as they are, tunable with F1): it uses a parameter set with a clear cone and sends the whole recoil kick into the camera at an even rhythm.
# The default behaviour (bullets follow the barrel, random kick, gun drift) is checked in tools/selftests/g7_selftest.py.
acc.stand, acc.walk, acc.sprint, acc.air, acc.crouch_multiplier = 2.0, 3.5, 4.5, 6.0, 0.7
acc.ads, acc.ads_move, acc.bloom_per_shot = 0.1, 0.6, 0.25
gun.recoil.up, gun.recoil.up_noise, gun.recoil.right_bias, gun.recoil.right_noise, gun.recoil.right_walk = 0.35, 0.035, 0.10, 0.01, 0.0
gun.recoil.camera_share, gun.recoil.ads_scale = 1.0, 1.0
M4_PATTERN = ((0.35, 0.10),) * 30
mouse.locked = False                      # do not grab the user's cursor
combat.require_locked_mouse = False       # allow firing even when the mouse is not captured (test only)
combat.rng.seed(20240131)                 # repeatable (though the frame timing still changes the result slightly)
# this test measures spread in the sprint state, so it must be able to fire from the running pose; sprint-to-fire is checked in g4_selftest.py
game.params.player.sprint_blocks_fire = False

results = []
frame_dts = []
frame_phase = []
phase = {'name': 'khởi động'}
skip = {'next': False}
S = MoveState

shots_log = []                            # ShotInfo of every shot (captured just before the bullet is spawned)
_orig_fire = combat._fire


def _logged_fire(origin, direction, age):
    shots_log.append(combat.last_shot)
    return _orig_fire(origin, direction, age)


combat._fire = _logged_fire


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def shot(name, prefix='g3_'):
    out = ROOT / 'shots' / f'{prefix}{name}.png'
    out.parent.mkdir(exist_ok=True)
    application.base.win.saveScreenshot(Filename.from_os_specific(str(out)))
    skip['next'] = True
    print('ĐÃ CHỤP', out.name)


def view_angles(d):
    """(up, right) angles of the direction vector, in degrees."""
    return math.degrees(math.asin(max(-1.0, min(1.0, d[1])))), math.degrees(math.atan2(d[0], d[2]))


def gun_center():
    """Centre of the gun body (Main node, not skinned so it follows `sway`) in the gun-render camera frame: (x right, y up, z forward).
    Do not use the whole actor: the arm's bounding box extends behind the camera, so its centre barely moves when the gun rotates."""
    lo, hi = viewmodel.actor.find('**/Main_M4_D_0-parent').get_tight_bounds(viewmodel.cam_np)
    return tuple(float((lo[i] + hi[i]) / 2) for i in range(3))


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.last = None
        self.means = {}                   # condition name -> measured mean angular offset

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

    # --- reset everything to the initial state ---
    def reset_state(self, auto=True, mag=30, pitch=0.0, ads=0.0):
        for k in ('w', 'a', 's', 'd', 'shift', 'control', 'space', 'left mouse', 'right mouse'):
            held_keys[k] = 0
        held_keys['right mouse'] = 1 if ads > 0 else 0       # aim through the game's own key path
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
        """Pull the trigger and fire the full 30-round magazine (real rate). `track` is called every frame."""
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
        """Expected accumulated angle (no noise) when shot k fires, for component `index` (0 = up, 1 = right)."""
        dt_shot, tau = 60.0 / gun.rpm, gun.recoil.kick_time
        return sum(M4_PATTERN[j][index] * (1.0 - math.exp(-(k - j) * dt_shot / tau)) for j in range(k))

    def measure_spread(self, name, keys, state, ads=0.0, seconds=1.0, lead=0.5, jump=False):
        """Fast fire (4 ms per shot, bloom off) straight up in state `state`; returns the list of angular offsets (degrees)."""
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

        # --- A. sign of the gun kick on screen ---
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
        # the gun body sits below-right of the view axis; rolling right (clockwise) pulls it down and to the left
        check('roll phải 5 độ: thân súng (dưới-phải) đi xuống và sang trái (mm)',
              f'{(x2 - x0) * 1000:.1f}, {(y2 - y0) * 1000:.1f}', '< 0, < 0', x2 - x0 < 0 and y2 - y0 < 0)
        viewmodel.update((0, 0, 0, 0, 0, 0))

        # --- B. recoil pattern: two hip-fire bursts, standing still, mouse NOT corrected ---
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
                while t < 1.5:               # record the stretch after firing stops so the peak before recovery is caught
                    yield
                    t += min(time.dt, 0.05)
                    pitch_trace.append(player.pitch)
                peak_pitch = min(pitch_trace)
                rise = 0.0 - peak_pitch      # reset_state sets pitch = 0
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

        # --- C. bloom with real numbers: hip, standing ---
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

        # aiming: base 0.1 degrees and bloom has almost no effect
        saved_ads_time = gun.ads_time
        for ads, label in ((1.0, 'ADS hẳn'), (0.5, 'ADS nửa chừng')):
            gun.ads_time = saved_ads_time if ads == 1.0 else 1e6      # halfway: freeze the ADS progress to measure exactly the 0.5 level
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
                check(f'{label}: phát đầu tản theo mức ADS hiện tại (độ)', round(first, 3), mid, abs(first - mid) < 1e-5)       # freezing ADS with a very large ads_time still creeps ~1e-8 per frame
            yield from self.wait(1.0)
        gun.ads_time = saved_ads_time

        # --- D. spread by state, measured from the real bullet direction (bloom off, fast fire) ---
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

        # --- E. dynamic aim point matches the real projection of the world camera ---
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

        held_keys['right mouse'] = 1
        yield from self.wait(0.6)
        alpha_ads = hud.crosshair[0][0].color.a
        check('tâm ngắm ẩn khi ngắm (ADS)', round(alpha_ads, 3), 0, alpha_ads == 0)
        shot('ads_no_crosshair')
        held_keys['right mouse'] = 0
        yield from self.wait(0.6)

        # --- F. third burst: mid-burst screenshot, gun kick visible, camera = firing direction ---
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
        back = gun.kick.back_peak
        check('kick súng lùi lại trong loạt (mm)', round(peak_back * 1000, 1), f'<= {back * 1300:.0f}', peak_back <= back * 1.3)
        check('kick súng lùi không quá 2x một phát đơn (đẩy lùi có trần)', round(peak_back * 1000, 1), f'>= {back * 2000:.0f}',
              peak_back >= back * 2)
        check('trên màn hình súng thật sự lại gần mắt hơn khi bắn (mm)', round((min(gun_z) - rest[2]) * 1000, 1), '< -25',
              min(gun_z) - rest[2] < -0.025)
        d_world = tuple(camera.forward)
        d_expected = aim_direction(player.yaw, player.pitch)
        check('camera thế giới khớp tia ngắm sau recoil (độ lệch)', round(angle_between(d_world, d_expected), 4), '< 0.01',
              angle_between(d_world, d_expected) < 0.01)
        yield from self.wait(0.6)
        settled = max(abs(v) for v in combat.gun_kick.pose[:3])
        check('0,75 s sau khi ngừng: kick súng đã yên (mm)', round(settled * 1000, 3), '< 1', settled < 0.001)
        # --- G. push-back (z of the gun kick): one shot, full magazine, return to rest, ADS; camera/bullets unchanged ---
        phase['name'] = 'đẩy lùi'
        pb = gun.kick.back_peak
        # how far the whole 30-round magazine pushes back per shot: derived from the push-back spring (closed-form), not hard-coded; expected full-magazine peak = pb * ratio
        burst_ratio = burst_peak_ratio(gun.kick.back_omega, gun.kick.back_zeta, 30, 60.0 / gun.rpm)
        burst_exp = pb * burst_ratio
        print(f'ĐẨY LÙI kỳ vọng từ cấu hình: một phát {pb * 1000:.1f} mm, cả băng x{burst_ratio:.2f} = {burst_exp * 1000:.1f} mm, '
              f'ngắm x{gun.kick.back_ads_scale}')

        # G1. single shot: peak = back_peak, on screen it pushes back exactly that much, then returns to rest
        self.reset_state(auto=False, mag=30)
        yield from self.wait(0.4)
        rest1 = gun_center()
        combat.rng.seed(1357)
        one_z, one_scr = [], []
        t_one, last_one = 0.0, 0.0
        combat.pressed = True
        while t_one < 1.5:
            yield
            t_one += min(time.dt, 0.05)
            z = combat.gun_kick.pose[2]
            one_z.append(z)
            one_scr.append(gun_center()[2] - rest1[2])
            if abs(z) >= 0.001:
                last_one = t_one
        single = min(one_z)
        check('đẩy lùi MỘT phát: đỉnh = back_peak (mm)', round(single * 1000, 1), f'{pb * 1000:.0f} +-25%', abs(single - pb) <= 0.25 * abs(pb))
        check('  trên màn hình thân súng lùi đúng chừng đó (mm)', round(min(one_scr) * 1000, 1), f'{pb * 1000:.0f} +-30%',
              abs(min(one_scr) - pb) <= 0.30 * abs(pb))
        check('  về chỗ cũ (|z| < 1 mm) sau phát đơn (s)', round(last_one, 2), '<= 0.6', last_one <= 0.6)
        print(f'ĐẨY LÙI một phát: đỉnh {single * 1000:.1f} mm, về chỗ (< 1 mm) sau {last_one:.2f} s')

        # G2. full 30-round hip-fire magazine: peak = back_peak x spring ratio; after firing stops it returns to rest within the measured time
        self.reset_state(auto=True, mag=30)
        yield from self.wait(0.4)
        rest2 = gun_center()
        cam_rest = tuple(camera.world_position)
        combat.rng.seed(2468)
        z_hip, scr_hip, cam_dev, scr_x_hip = [], [], [], []

        def track_hip():
            z_hip.append(combat.gun_kick.pose[2])
            c = gun_center()
            scr_hip.append(c[2] - rest2[2])
            scr_x_hip.append(c[0] - rest2[0])
            cam_dev.append(max(abs(a - b) for a, b in zip(tuple(camera.world_position), cam_rest)))
            if combat.weapon.mag == 2 and not shot_taken.get('hip'):
                shot_taken['hip'] = True
                shot('hip_late', prefix='kick_')

        yield from self.spray(track=track_hip)
        t_stop, last_big = 0.0, 0.0
        while t_stop < 1.5:                                     # spray returns right away when ammo runs out: measure the time to return to rest after the last shot
            yield
            t_stop += min(time.dt, 0.05)
            track_hip()
            if abs(combat.gun_kick.pose[2]) >= 0.001:
                last_big = t_stop
        burst = min(z_hip)
        # bounds keep the old ratio against the expected value (old: -35 .. -65 around ~-51 mm => x0.7 .. x1.3; screen x0.7 .. x1.4; horizontal x0.4 .. x2)
        check('đẩy lùi cả băng 30 viên hông: đỉnh = back_peak x tỉ lệ lò xo (mm)', round(burst * 1000, 1),
              f'{burst_exp * 1300:.0f} .. {burst_exp * 700:.0f}', burst_exp * 1.3 <= burst <= burst_exp * 0.7)
        check('  nhiều hơn một phát đơn nhưng có trần (x so với phát đơn)', round(burst / single, 2),
              f'{0.75 * burst_ratio:.2f} .. {1.17 * burst_ratio:.2f} (mô hình {burst_ratio:.2f})', 0.75 * burst_ratio <= burst / single <= 1.17 * burst_ratio)
        check('  trên màn hình thân súng lùi cùng cỡ (mm)', round(min(scr_hip) * 1000, 1), f'{burst_exp * 1400:.0f} .. {burst_exp * 700:.0f}',
              burst_exp * 1.4 <= min(scr_hip) <= burst_exp * 0.7)
        x_exp = gun.kick.back_x_ratio * burst_exp                       # horizontal shift with the push-back (negative: to the left)
        check('  hông: thân súng nhích vào giữa (sang trái) cùng lúc (mm)', round(min(scr_x_hip) * 1000, 1),
              f'{x_exp * 2000:.0f} .. {x_exp * 400:.0f}', x_exp * 2.0 <= min(scr_x_hip) <= x_exp * 0.4)
        check('  ngừng bắn: về chỗ cũ (|z| < 1 mm) sau (s)', round(last_big, 2), '<= 0.7', last_big <= 0.7)
        check('  camera thế giới KHÔNG lùi (độ lệch vị trí, mm)', round(max(cam_dev) * 1000, 4), '< 0.01', max(cam_dev) < 1e-5)
        print(f'ĐẨY LÙI cả băng (hông): đỉnh {burst * 1000:.1f} mm ({burst / single:.2f}x một phát), trên màn hình {min(scr_hip) * 1000:.1f} mm, '
              f'về chỗ sau {last_big:.2f} s kể từ phát cuối')
        yield from self.wait(0.6)

        # G3. ADS: full-magazine peak = back_ads_scale x hip (< 1 pushes back less than hip, > 1 pushes back more)
        self.reset_state(auto=True, mag=30, ads=1.0)
        yield from self.wait(0.5)
        rest3 = gun_center()
        combat.rng.seed(2468)
        z_ads, scr_ads = [], []

        def track_ads():
            z_ads.append(combat.gun_kick.pose[2])
            scr_ads.append(gun_center()[2] - rest3[2])
            if combat.weapon.mag == 2 and not shot_taken.get('ads'):
                shot_taken['ads'] = True
                shot('ads_late', prefix='kick_')

        shots_log.clear()                                       # not self.spray: it resets to hip via reset_state
        held_keys['left mouse'] = 1
        while combat.weapon.mag > 0:
            yield
            track_ads()
        held_keys['left mouse'] = 0
        yield from self.wait(0.02)
        shot('ads_end', prefix='kick_')
        ratio = min(z_ads) / burst
        check('đẩy lùi khi ngắm hẳn = back_ads_scale x hông (tỉ lệ đỉnh cả băng)', round(ratio, 2), f'{gun.kick.back_ads_scale} +-0.12',
              abs(ratio - gun.kick.back_ads_scale) <= 0.12)
        check('  vẫn thấy được khi ngắm (mm)', round(min(scr_ads) * 1000, 1), '< -10', min(scr_ads) < -0.010)
        print(f'ĐẨY LÙI khi ngắm: đỉnh {min(z_ads) * 1000:.1f} mm ({ratio:.2f} so với hông), trên màn hình {min(scr_ads) * 1000:.1f} mm')
        held_keys['right mouse'] = 0
        yield from self.wait(0.8)

        # G4. only the viewmodel pushes back: same fixed-dt script, push-back on / off -> aim ray, view angle, bullet direction and muzzle origin IDENTICAL
        def det_pass(back_peak):
            self.reset_state(auto=True, mag=30)
            saved_peak = gun.kick.back_peak
            gun.kick.back_peak = back_peak
            combat.rng.seed(97531)
            combat.recoil = CameraRecoil(gun.recoil, combat.rng)
            combat.gun_kick = GunKick(gun.kick, combat.rng)
            rays, views, fired = [], [], []
            orig = combat._fire

            def logged(origin, direction, age):
                fired.append((combat.last_shot.view_dir, direction, origin))
                return orig(origin, direction, age)

            combat._fire = logged
            try:
                held_keys['left mouse'] = 1
                for _ in range(200):
                    combat.update(1 / 120, 1 / 120)
                    rays.append(player.aim_ray())
                    views.append((player.yaw, player.pitch))
            finally:
                held_keys['left mouse'] = 0
                combat._fire = orig
                gun.kick.back_peak = saved_peak
            return rays, views, fired

        on = det_pass(pb)
        off = det_pass(0.0)
        check('đẩy lùi BẬT / TẮT: tia ngắm (gốc + hướng) giống hệt mỗi bước', on[0] == off[0], True, on[0] == off[0])
        check('  góc nhìn của người chơi giống hệt', on[1] == off[1], True, on[1] == off[1])
        check('  hướng nhìn + hướng đạn + gốc đạn của từng phát giống hệt', on[2] == off[2] and len(on[2]) > 15, True,
              on[2] == off[2] and len(on[2]) > 15)
        yield from self.wait(0.3)

        phase['name'] = 'xong'
        yield from self.wait(0.3)


def report():
    print('\n=== KIỂM TRA G3 ===')
    print(f"{'mục':64s} {'đo được':>16s} {'mong đợi':>22s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:64s} {str(got):>16s} {str(expected):>22s}  {"ĐẠT" if ok else "TRƯỢT"}')
    # exclude the segments that slow the frame rate themselves: the spread measurement (250 shots/s) and burst 3 (measures the gun bounding box every frame)
    pairs = [(dt, ph) for dt, ph in zip(frame_dts, frame_phase) if ph not in ('đo độ tản', 'loạt 3', 'đẩy lùi')]
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
