"""G5: rút súng (Draw), nạp đạn hai kiểu, huỷ nạp, logic đạn, bằng game thật.

Điều khiển qua đúng đường phím của game (held_keys, game.input('r'), combat.pressed). Đo:
  - Draw: không bắn được cho tới khi xong (~1 s), tay đi từ dưới lên tới đúng tư thế sẵn sàng
  - Reload (còn đạn) và Reload_Empty (băng cạn): thời lượng, đạn chỉ đổi đúng lúc băng mới vào chỗ (so với vị trí băng thật
    trên màn hình), không bắn / không ngắm được trong lúc nạp, tay trở về tư thế sẵn sàng, bolt khoá sau khi băng cạn
  - huỷ: chạy nước rút cắt nạp trước / sau mốc thay băng (đạn y nguyên / đã nạp), trượt êm về tư thế sẵn sàng; tuỳ chọn tắt
  - biên: băng đầy, hết dự trữ, nạp dở dang, bấm R lúc chạy, bắn đơn bấm cò khi cạn, tổng số đạn không đổi
Ảnh vào shots\\g5_*.png.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\selftests\\g5_selftest.py        (thoát mã 1 nếu có mục trượt)
"""
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
import math  # noqa: E402

from panda3d.core import Filename, Point2, Point3  # noqa: E402
from ursina import Entity, application, camera, held_keys, mouse, time, window  # noqa: E402

from fps.core.handling import Phase  # noqa: E402
from fps.core.movement import MoveState  # noqa: E402
from fps.core.recoil import CameraRecoil, GunKick  # noqa: E402

game = create_game(vsync=False, sound=False, draw=True, moving_targets=False, hud=True, free_aim=False)
player, combat, viewmodel, hud = game.player, game.combat, game.viewmodel, game.hud
handling, weapon = combat.handling, combat.weapon
gun = game.params.gun
rl = gun.reload
mouse.locked = False
combat.require_locked_mouse = False
combat.rng.seed(7)

results = []
frame_dts = []
skip = {'next': False}
clips = gun.clips


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def shot(name):
    out = ROOT / 'shots' / f'g5_{name}.png'
    out.parent.mkdir(exist_ok=True)
    application.base.win.saveScreenshot(Filename.from_os_specific(str(out)))
    skip['next'] = True
    print('ĐÃ CHỤP', out.name)


def center(name):
    lo, hi = viewmodel.actor.find(f'**/{name}_M4_D_0-parent').get_tight_bounds(viewmodel.actor)
    return (lo + hi) / 2


def rel(name):
    """Tâm phần súng so với thân súng (cm, hệ actor): không phụ thuộc cả súng đang bị nâng hay hạ."""
    return center(name) - center('Main')


READY = {}      # tư thế sẵn sàng: đo sau khi Draw xong


def main_y():
    """Độ cao (m) của thân súng so với mắt, trong hệ camera vẽ súng: lúc rút súng thấp hơn nhiều so với tư thế sẵn sàng."""
    lo, hi = viewmodel.actor.find('**/Main_M4_D_0-parent').get_tight_bounds(viewmodel.cam_np)
    return (lo.y + hi.y) / 2


def flash_level() -> float:
    """Độ sáng đèn tia lửa mà shader của súng đang nhận (kênh lớn nhất)."""
    v = viewmodel.light.flash_color.get_element(0)              # mảng PTA mà shader của súng đọc
    return max(v[0], v[1], v[2])


def project_view(p):
    """Điểm trong hệ cảnh súng (x phải, y lên, z ra trước) -> pixel so với tâm màn hình, theo ống kính của súng."""
    out = Point2()
    viewmodel.lens.project(Point3(*p), out)
    w, h = window.size
    return out.x * w / 2, out.y * h / 2


def project_world(p):
    """Điểm thế giới -> pixel so với tâm màn hình, theo camera thế giới."""
    out = Point2()
    camera.lens.project(camera.getRelativePoint(application.base.render, Point3(*p)), out)
    w, h = window.size
    return out.x * w / 2, out.y * h / 2


def gap(name):
    """Khoảng cách (cm) của phần súng so với chỗ của nó ở tư thế sẵn sàng."""
    return (rel(name) - READY[name]).length()


def swap_in(samples, want, loaded):
    """Đạn đổi thành `loaded` ở mẫu đầu tiên có mag == loaded: thời điểm mong đợi phải nằm giữa mẫu đó và mẫu ngay trước
    (khung treo vì chụp ảnh làm hai mẫu cách xa nhau, nên không so từng mẫu với mốc)."""
    for prev, cur in zip(samples, samples[1:]):
        if cur[1] == loaded and prev[1] != loaded:
            return prev[0] - 0.03 <= want <= cur[0] + 0.03
    return False


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

    # đồng hồ THẬT của tiến trình (clip nạp đạn chạy theo đồng hồ Panda, không cắt ở 50 ms)
    def wait(self, seconds):
        t0 = pytime.perf_counter()
        while pytime.perf_counter() - t0 < seconds:
            yield

    def until(self, cond, timeout=6.0):
        """Chờ tới khi cond() đúng; trả về số giây thật đã chờ (None nếu quá hạn)."""
        t0 = pytime.perf_counter()
        while not cond() and pytime.perf_counter() - t0 < timeout:
            yield
        return pytime.perf_counter() - t0 if cond() else None

    def sample(self, seconds, getter):
        """[(giây thật kể từ lúc bắt đầu, getter())] mỗi khung trong `seconds` giây."""
        out = []
        t0 = pytime.perf_counter()
        while pytime.perf_counter() - t0 < seconds:
            yield
            out.append((pytime.perf_counter() - t0, getter()))
        return out

    def reset_state(self, auto=True, mag=30, reserve=150):
        for k in ('w', 'a', 's', 'd', 'shift', 'control', 'space', 'left mouse', 'right mouse'):
            held_keys[k] = 0
        player.position = (0, 0, 0)
        player.vx = player.vz = player.vy = 0.0
        player.on_ground = True
        player.yaw, player.pitch = 0.0, 0.0
        player._apply_view()
        player.ads_amount = player.sprint_amount = 0.0
        combat.recoil = CameraRecoil(gun.recoil, combat.rng)
        combat.gun_kick = GunKick(gun.kick, combat.rng)
        combat.accuracy.bloom = 0.0
        combat.accuracy.since_shot = 1e9
        for b in combat.bullets:                                # bỏ đạn đang bay: báo cho tracer đang bám theo là đạn đã hết
            b.alive, b.end_pos = False, b.pos
        combat.bullets.clear()
        combat.pressed = False
        combat.reload_requested = False
        weapon.auto = auto
        weapon.mag = mag
        weapon.reserve = reserve
        weapon.cooldown = 0.0
        if handling.phase is Phase.RELOAD:
            handling.cancel()
        game.viewmodel.hold_ready_pose()
        handling.drain()

    def press_r(self):
        """Bấm R rồi chờ một khung để Combat xử lý."""
        game.input('r')
        yield

    def run(self):
        # --- A. rút súng ---
        yield from self.until(lambda: handling.phase is Phase.DRAW, 3.0)
        t_draw0 = pytime.perf_counter()
        check('vào game: đang rút súng (Draw)', handling.phase.value, 'draw', handling.phase is Phase.DRAW)
        combat.require_locked_mouse = False
        weapon.mag = 20                                         # để thử bấm R khi đang rút súng (băng chưa đầy)
        low_track = yield from self.sample(0.12, main_y)         # lúc đầu súng nằm thấp dưới màn hình rồi nhô lên
        low = min(v for _, v in low_track)
        shot('draw_start')
        held_keys['left mouse'] = 1
        yield from self.press_r()
        yield from self.wait(0.3)
        check('đang rút súng: giữ cò không bắn', combat.shots_fired, 0, combat.shots_fired == 0)
        check('đang rút súng: bấm R không nạp', handling.phase.value, 'draw', handling.phase is Phase.DRAW)
        check('đang rút súng: không ngắm được', player.ads_blocked, True, player.ads_blocked)
        t_end = yield from self.until(lambda: handling.phase is Phase.READY, 3.0)
        t_draw = pytime.perf_counter() - t_draw0
        check('thời gian rút súng (s)', round(t_draw, 3), f'{clips["draw"].duration / rl.draw_speed:.2f} +-0.12',
              abs(t_draw - clips['draw'].duration / rl.draw_speed) < 0.12)
        t_shot = yield from self.until(lambda: combat.shots_fired > 0, 1.0)
        held_keys['left mouse'] = 0
        check('xong rút súng: bắn được ngay', None if t_shot is None else round(t_shot, 3), '< 0.1',
              t_shot is not None and t_shot < 0.1)
        yield from self.wait(0.4)
        for p in ('Mag1', 'Bolt', 'BoltCatch', 'Trigger'):
            READY[p] = rel(p)
        check('rút súng xong: tay về đúng tư thế sẵn sàng (Mag1, cm)', round(gap('Mag1'), 2), '< 0.5', gap('Mag1') < 0.5)
        check('lúc bắt đầu rút súng, súng nằm thấp hơn tư thế sẵn sàng (m)', round(main_y() - low, 2), '> 0.05', main_y() - low > 0.05)

        # --- B. nạp khi còn đạn (Reload) ---
        self.reset_state(mag=17)
        yield from self.wait(0.3)
        total = weapon.mag + weapon.reserve
        held_keys['right mouse'] = 1                            # giữ ngắm: nạp phải kéo súng ra khỏi ADS
        yield from self.until(lambda: player.ads_amount >= 1.0)
        shots0 = combat.shots_fired
        t0 = pytime.perf_counter()
        yield from self.press_r()
        track = {'max_gap': 0.0, 'min_ads_late': 1.0, 'bolt_max': 0.0}

        def watch():
            track['max_gap'] = max(track['max_gap'], gap('Mag1'))
            track['bolt_max'] = max(track['bolt_max'], gap('Bolt'))
            return (weapon.mag, handling.phase is Phase.RELOAD, gap('Mag1'), player.ads_amount, handling.key, combat.shots_fired)

        t = yield from self.until(lambda: handling.phase is Phase.RELOAD, 1.0)
        check('bấm R khi còn đạn: bắt đầu nạp bằng clip Reload', handling.key, 'reload', handling.key == 'reload')
        samples = []
        shot_times = {0.5: 'reload_a', 1.2: 'reload_b', 1.7: 'reload_c', 2.3: 'reload_d'}
        t_rel = pytime.perf_counter()
        held_keys['left mouse'] = 1                             # bóp cò suốt lúc nạp: không được bắn
        pending = sorted(shot_times)
        while pytime.perf_counter() - t_rel < 6.0:
            yield
            if handling.phase is not Phase.RELOAD:
                break                                           # khung này nạp xong: cò đang giữ sẽ bắn (đúng ý), không tính vào "trong lúc nạp"
            now = pytime.perf_counter() - t_rel
            samples.append((now,) + watch())
            if handling.remaining < 0.1:
                held_keys['left mouse'] = 0                     # nhả cò sát cuối để phát đầu sau khi nạp xong không lẫn vào số đạn
            if pending and now >= pending[0]:
                shot(shot_times[pending.pop(0)])
        held_keys['left mouse'] = 0
        total_time = pytime.perf_counter() - t_rel
        swap_t = next((s[0] for s in samples if s[1] == 30), None)
        want_swap = clips['reload'].swap_time / rl.speed
        want_total = clips['reload'].duration / rl.speed
        check('Reload: thời gian cả clip (s)', round(total_time, 3), f'{want_total:.2f} +-0.1', abs(total_time - want_total) < 0.1)
        check('Reload: đạn đổi đúng lúc băng mới vào chỗ (s)', None if swap_t is None else round(swap_t, 3),
              f'{want_swap:.2f}, trong khoảng hai mẫu liền kề', swap_in(samples, want_swap, 30))
        check('Reload: trước đó đạn y nguyên', {s[1] for s in samples if s[0] < want_swap - 0.1}, '{17}',
              {s[1] for s in samples if s[0] < want_swap - 0.1} == {17})
        check('Reload: nạp xong 30 / dự trữ', f'{weapon.mag}/{weapon.reserve}', f'30/{total - 30}',
              (weapon.mag, weapon.reserve) == (30, total - 30))
        near = [s[3] for s in samples if swap_t and abs(s[0] - swap_t) < 0.12]
        check('Reload: lúc đạn đổi băng nằm sát chỗ cũ trên màn hình (cm)', round(min(near), 1) if near else None, '< 6',
              bool(near) and min(near) < 6)
        check('Reload: giữa chừng băng cũ đưa ra xa chỗ (cm)', round(track['max_gap'], 1), '> 25', track['max_gap'] > 25)
        check('Reload: bóp cò suốt lúc nạp, không bắn phát nào', samples[-1][6] - shots0, 0, samples[-1][6] == shots0)
        ads_during = [s[4] for s in samples if s[0] > 0.4]
        check('Reload: đang giữ ngắm nhưng bị kéo ra khỏi ADS (ads_amount lớn nhất sau 0,4 s)', round(max(ads_during), 3), '0',
              max(ads_during) < 0.01)
        yield from self.wait(0.15)
        check('Reload xong: tay về tư thế sẵn sàng (Mag1, Bolt, cm)', f'{gap("Mag1"):.2f}, {gap("Bolt"):.2f}', '< 1', gap('Mag1') < 1 and gap('Bolt') < 1)
        t_back = yield from self.until(lambda: player.ads_amount >= 1.0, 1.0)
        check('Reload xong, còn giữ ngắm: vào ADS lại', None if t_back is None else round(t_back, 3), '< 0.5',
              t_back is not None and t_back < 0.5)
        held_keys['right mouse'] = 0
        yield from self.wait(0.4)
        # chuyển động mượt: chia khung theo nội suy 30 fps -> 100+ Hz
        self.reset_state(mag=17)
        yield from self.wait(0.3)
        yield from self.press_r()
        yield from self.wait(1.0)                               # tới đoạn băng cũ đang kéo đi nhanh (~1,0 s)
        pos = yield from self.sample(0.5, lambda: tuple(center('Mag1')))
        moved = sum(1 for a, b in zip(pos, pos[1:]) if sum((x - y) ** 2 for x, y in zip(a[1], b[1])) ** 0.5 > 1e-3)
        frac = moved / (len(pos) - 1)
        check('animation: tay/băng đổi vị trí ở hầu hết các khung hình (nội suy, không giật 30 fps)', f'{frac:.0%} của {len(pos)} khung', '> 85%', frac > 0.85)
        yield from self.until(lambda: handling.phase is Phase.READY, 5.0)
        yield from self.wait(0.2)

        # --- C. nạp khi băng cạn (Reload_Empty), tự nạp khi giữ cò ---
        self.reset_state(auto=True, mag=30)
        yield from self.wait(0.3)
        total = weapon.mag + weapon.reserve
        shots0 = combat.shots_fired
        held_keys['left mouse'] = 1
        yield from self.until(lambda: handling.phase is Phase.RELOAD, 5.0)
        check('bắn hết băng: đúng 30 phát', combat.shots_fired - shots0, 30, combat.shots_fired - shots0 == 30)
        check('băng cạn, còn giữ cò: tự nạp bằng Reload_Empty', handling.key, 'reload_empty', handling.key == 'reload_empty')
        t_rel = pytime.perf_counter()
        samples = []
        locked_gap = None
        shot_after = None
        while pytime.perf_counter() - t_rel < 6.0:
            yield
            if handling.phase is not Phase.RELOAD:
                break
            now = pytime.perf_counter() - t_rel
            samples.append((now, weapon.mag, gap('Mag1'), gap('Bolt'), combat.shots_fired, weapon.reserve))
            if now < 0.1 and locked_gap is None:
                locked_gap = gap('Bolt')
            if now > 2.9 and shot_after is None:
                shot_after = 0
                shot('empty_bolt_closing')
        total_time = pytime.perf_counter() - t_rel
        swap_t = next((s[0] for s in samples if s[1] == 30), None)
        want_swap = clips['reload_empty'].swap_time / rl.speed
        want_total = clips['reload_empty'].duration / rl.speed
        check('Reload_Empty: thời gian cả clip (s)', round(total_time, 3), f'{want_total:.2f} +-0.1', abs(total_time - want_total) < 0.1)
        check('Reload_Empty: đạn đổi đúng lúc băng mới vào chỗ (s)', None if swap_t is None else round(swap_t, 3),
              f'{want_swap:.2f}, trong khoảng hai mẫu liền kề', swap_in(samples, want_swap, 30))
        near = [s[2] for s in samples if swap_t and abs(s[0] - swap_t) < 0.12]
        check('Reload_Empty: lúc đạn đổi băng nằm sát chỗ cũ (cm)', round(min(near), 1) if near else None, '< 6', bool(near) and min(near) < 6)
        check('Reload_Empty: bolt khoá sau từ đầu (lệch so với đóng, cm)', None if locked_gap is None else round(locked_gap, 1), '> 4',
              locked_gap is not None and locked_gap > 4)
        check('Reload_Empty: không bắn trong lúc nạp dù giữ cò', samples[-1][4] - samples[0][4], 0, samples[-1][4] == samples[0][4])
        last = samples[-1]
        check('Reload_Empty: nạp xong 30 / dự trữ (mẫu cuối trước khi bắn tiếp)', f'{last[1]}/{last[5]}', f'30/{total - 60}',
              (last[1], last[5]) == (30, total - 60))
        shots1 = combat.shots_fired
        t_fire = yield from self.until(lambda: combat.shots_fired > shots1, 1.0)
        check('nạp xong, còn giữ cò: bắn tiếp ngay (s)', None if t_fire is None else round(t_fire, 3), '< 0.1', t_fire is not None and t_fire < 0.1)
        held_keys['left mouse'] = 0
        yield from self.wait(0.5)
        check('Reload_Empty xong: bolt đóng (cm)', round(gap('Bolt'), 2), '< 1', gap('Bolt') < 1)

        # bolt khoá sau ngay khi bắn phát cuối, trước khi nạp
        self.reset_state(auto=False, mag=1)
        yield from self.wait(0.3)
        shots0 = combat.shots_fired
        combat.pressed = True
        held_keys['left mouse'] = 1
        yield
        held_keys['left mouse'] = 0
        yield from self.wait(0.25)
        check('bắn phát cuối: bolt khoá sau (cm)', round(gap('Bolt'), 1), '> 4', gap('Bolt') > 4)
        check('  và chưa tự nạp khi chưa bấm gì', handling.phase.value, 'ready', handling.phase is Phase.READY)
        shot('bolt_locked')
        # bắn đơn: bấm cò khi băng cạn thì nạp, không bắn
        shots0 = combat.shots_fired
        combat.pressed = True
        held_keys['left mouse'] = 1
        yield
        held_keys['left mouse'] = 0
        yield from self.wait(0.2)
        check('bắn đơn, băng cạn: bấm cò thì nạp (Reload_Empty), không bắn', f'{handling.key}, bắn {combat.shots_fired - shots0}',
              'reload_empty, bắn 0', handling.key == 'reload_empty' and combat.shots_fired == shots0)
        yield from self.until(lambda: handling.phase is Phase.READY, 6.0)
        yield from self.wait(0.2)

        # --- D. huỷ nạp bằng chạy nước rút ---
        self.reset_state(mag=12)
        yield from self.wait(0.3)
        yield from self.press_r()
        yield from self.wait(1.0)
        check('đang nạp ở 1,0 s', handling.phase.value, 'reload', handling.phase is Phase.RELOAD)
        held_keys['w'] = held_keys['shift'] = 1
        t_cancel = yield from self.until(lambda: handling.phase is Phase.READY, 0.6)
        check('chạy nước rút cắt nạp (s)', None if t_cancel is None else round(t_cancel, 3), '< 0.15', t_cancel is not None and t_cancel < 0.15)
        check('huỷ trước mốc thay băng: đạn y nguyên', f'{weapon.mag}/{weapon.reserve}', '12/150', (weapon.mag, weapon.reserve) == (12, 150))
        yield from self.wait(0.06)
        shot('cancel_fade')
        yield from self.wait(0.45)
        held_keys['w'] = held_keys['shift'] = 0
        yield from self.wait(0.5)
        check('sau huỷ: không còn trượt / clip dở', (viewmodel.clip_key, viewmodel._fade), '(None, None)',
              viewmodel.clip_key is None and viewmodel._fade is None)
        check('sau huỷ: tay về tư thế sẵn sàng (Mag1, Bolt, cm)', f'{gap("Mag1"):.2f}, {gap("Bolt"):.2f}', '< 1', gap('Mag1') < 1 and gap('Bolt') < 1)
        check('huỷ: không tự nạp tiếp', f'{weapon.mag}/{weapon.reserve}', '12/150', (weapon.mag, weapon.reserve) == (12, 150))
        # R lúc đang chạy: bị bỏ qua
        held_keys['w'] = held_keys['shift'] = 1
        yield from self.until(lambda: player.sprint_amount >= 1.0)
        yield from self.press_r()
        yield from self.wait(0.3)
        check('bấm R khi đang chạy: không nạp', handling.phase.value, 'ready', handling.phase is Phase.READY)
        held_keys['w'] = held_keys['shift'] = 0
        yield from self.until(lambda: player.sprint_amount <= 0.0, 1.0)
        yield from self.press_r()
        yield from self.wait(0.2)
        check('thôi chạy rồi bấm R: nạp', handling.phase.value, 'reload', handling.phase is Phase.RELOAD)
        yield from self.until(lambda: handling.phase is Phase.READY, 6.0)

        # huỷ sau mốc thay băng: đạn đã nạp
        self.reset_state(mag=12)
        yield from self.wait(0.3)
        yield from self.press_r()
        yield from self.until(lambda: weapon.mag == 30, 4.0)
        yield from self.wait(0.15)
        check('đang nạp, băng mới đã vào', handling.phase.value, 'reload', handling.phase is Phase.RELOAD)
        held_keys['w'] = held_keys['shift'] = 1
        yield from self.until(lambda: handling.phase is Phase.READY, 0.6)
        check('huỷ sau mốc thay băng: đạn đã nạp rồi', f'{weapon.mag}/{weapon.reserve}', '30/132', (weapon.mag, weapon.reserve) == (30, 132))
        held_keys['w'] = held_keys['shift'] = 0
        yield from self.wait(0.7)
        check('  và tay về tư thế sẵn sàng (cm)', round(gap('Mag1'), 2), '< 1', gap('Mag1') < 1)

        # huỷ khi băng cạn (Reload_Empty) trước mốc thay băng: băng vẫn cạn, bolt lại khoá sau
        self.reset_state(mag=0)
        yield from self.wait(0.3)
        yield from self.press_r()
        yield from self.wait(1.0)
        held_keys['w'] = held_keys['shift'] = 1
        yield from self.until(lambda: handling.phase is Phase.READY, 0.6)
        held_keys['w'] = held_keys['shift'] = 0
        yield from self.wait(0.8)
        check('huỷ Reload_Empty trước mốc: băng vẫn cạn', f'{weapon.mag}/{weapon.reserve}', '0/150', (weapon.mag, weapon.reserve) == (0, 150))
        check('  và bolt khoá sau trở lại (cm)', round(gap('Bolt'), 1), '> 4', gap('Bolt') > 4)

        # tuỳ chọn: sprint_cancels = False thì nạp tiếp
        rl.sprint_cancels = False
        self.reset_state(mag=12)
        yield from self.wait(0.3)
        yield from self.press_r()
        yield from self.wait(0.5)
        held_keys['w'] = held_keys['shift'] = 1
        yield from self.wait(0.5)
        check('sprint_cancels = False: chạy không cắt nạp', handling.phase.value, 'reload', handling.phase is Phase.RELOAD)
        yield from self.until(lambda: handling.phase is Phase.READY, 6.0)
        check('  nạp tiếp tới hết', f'{weapon.mag}/{weapon.reserve}', '30/132', (weapon.mag, weapon.reserve) == (30, 132))
        held_keys['w'] = held_keys['shift'] = 0
        rl.sprint_cancels = True
        yield from self.wait(0.5)

        # --- E. biên của logic đạn ---
        self.reset_state(mag=30)
        yield from self.wait(0.3)
        yield from self.press_r()
        yield from self.wait(0.2)
        check('băng đầy: bấm R không nạp', handling.phase.value, 'ready', handling.phase is Phase.READY)

        self.reset_state(mag=10, reserve=0)
        yield from self.wait(0.3)
        yield from self.press_r()
        yield from self.wait(0.2)
        check('hết dự trữ: bấm R không nạp', handling.phase.value, 'ready', handling.phase is Phase.READY)

        self.reset_state(mag=0, reserve=0)
        yield from self.wait(0.3)
        shots0 = combat.shots_fired
        held_keys['left mouse'] = 1
        combat.pressed = True
        yield from self.wait(0.4)
        check('hết sạch đạn: bóp cò không bắn, không nạp', f'bắn {combat.shots_fired - shots0}, {handling.phase.value}', 'bắn 0, ready',
              combat.shots_fired == shots0 and handling.phase is Phase.READY)
        check('  HUD báo hết đạn', hud.prompt.text, 'HẾT ĐẠN', hud.prompt.text == 'HẾT ĐẠN')
        held_keys['left mouse'] = 0

        self.reset_state(mag=0, reserve=7)
        yield from self.wait(0.3)
        yield from self.press_r()
        yield from self.until(lambda: handling.phase is Phase.READY, 6.0)
        check('dự trữ ít hơn băng: nạp phần có', f'{weapon.mag}/{weapon.reserve}', '7/0', (weapon.mag, weapon.reserve) == (7, 0))

        self.reset_state(mag=5)
        yield from self.wait(0.3)
        check('còn ít đạn: HUD nhắc nạp', hud.prompt.text, 'R  NẠP ĐẠN', hud.prompt.text == 'R  NẠP ĐẠN')
        yield from self.press_r()
        yield from self.wait(0.2)
        self.press_r()                                          # bấm R nữa khi đang nạp: bỏ qua
        yield from self.wait(0.3)
        check('đang nạp, bấm R nữa không bắt đầu lại', round(handling.progress, 2), '> 0.1 (không về 0)', handling.progress > 0.1)
        yield from self.until(lambda: handling.phase is Phase.READY, 6.0)

        # tổng số đạn: bắn, nạp, huỷ lung tung vẫn bảo toàn
        self.reset_state(auto=True, mag=30)
        yield from self.wait(0.3)
        total = weapon.mag + weapon.reserve
        fired0 = combat.shots_fired
        for _ in range(3):
            held_keys['left mouse'] = 1
            yield from self.wait(0.6)
            held_keys['left mouse'] = 0
            yield from self.press_r()
            yield from self.wait(1.0)
            held_keys['w'] = held_keys['shift'] = 1
            yield from self.wait(0.4)
            held_keys['w'] = held_keys['shift'] = 0
            yield from self.until(lambda: player.sprint_amount <= 0.0, 1.0)
            yield from self.press_r()
            yield from self.until(lambda: handling.phase is Phase.READY, 6.0)
        fired = combat.shots_fired - fired0
        check('bảo toàn đạn: đã bắn + còn lại = ban đầu', f'{fired} + {weapon.mag + weapon.reserve}', total, fired + weapon.mag + weapon.reserve == total)

        # --- F. tia lửa đầu nòng và tracer ---
        fx = game.fx
        self.reset_state(auto=True, mag=30)
        yield from self.wait(0.4)
        fx.tracers.spawned = fx.flash.fired = 0
        probe = {}
        orig_on_shot = fx.on_shot

        def hooked(bullet, ads):
            muzzle_px = project_view(fx.flash.muzzle.get_pos(viewmodel.cam_np))
            orig_on_shot(bullet, ads)
            if 'start' not in probe and fx.tracers.active and fx.tracers.active[-1].bullet is bullet:
                tr = fx.tracers.active[-1].tracer
                start = tuple(bullet.origin[i] + tr.offset[i] for i in range(3))
                probe['start'] = (project_world(start), muzzle_px)
        fx.on_shot = hooked
        light_seen = {'max': 0.0}
        orig_set_light = viewmodel.set_flash_light

        def watch_light(pos, color, *rest):
            light_seen['max'] = max(light_seen['max'], max(color))
            return orig_set_light(pos, color, *rest)
        viewmodel.set_flash_light = watch_light
        shots0 = combat.shots_fired
        held_keys['left mouse'] = 1
        yield from self.until(lambda: combat.shots_fired > shots0, 1.0)
        yield
        check('tia lửa: hiện ngay khung sau phát bắn', fx.flash.active, True, fx.flash.active)
        shot('flash')
        yield from self.wait(0.5)
        held_keys['left mouse'] = 0
        viewmodel.set_flash_light = orig_set_light
        check('  đèn tia lửa sáng lên (màu đèn lớn nhất shader súng nhận)', round(light_seen['max'], 2), '> 0.3', light_seen['max'] > 0.3)
        shots = combat.shots_fired - shots0
        traced = fx.tracers.spawned
        check('mỗi phát một lần chớp', f'{fx.flash.fired} / {shots} phát', 'bằng nhau', fx.flash.fired == shots)
        want = sum(1 for i in range(1, shots + 1) if (i - 1) % gun.tracer.every == 0)
        check(f'tracer: cứ {gun.tracer.every} phát một vệt, phát đầu có', f'{traced} / {shots} phát', want, traced == want)
        (start_px, muzzle_px) = probe['start']
        d_px = math.hypot(start_px[0] - muzzle_px[0], start_px[1] - muzzle_px[1])
        check('tracer: điểm xuất phát trùng miệng nòng trên màn hình (px)', f'{d_px:.1f}', '< 4', d_px < 4)
        yield from self.wait(0.15)
        check('tia lửa tắt khi hết phát (không kẹt)', (fx.flash.active, fx.flash.root.is_hidden()), '(False, True)',
              not fx.flash.active and fx.flash.root.is_hidden())
        check('  đèn tia lửa tắt', round(flash_level(), 3), 0,
              flash_level() < 0.01)

        # vệt bám đúng viên đạn thật
        self.reset_state(auto=False, mag=30)
        yield from self.wait(0.3)
        shots0 = combat.shots_fired
        fx.tracers.spawned = 0
        combat.pressed = True
        held_keys['left mouse'] = 1
        yield
        held_keys['left mouse'] = 0
        yield from self.until(lambda: any(st.tracer.head_s > 40 for st in fx.tracers.active), 1.0)
        st = next((x for x in fx.tracers.active if x.tracer.head_s > 40), None)
        if st:
            tail, head = st.tracer.endpoints()
            off = math.dist(head, st.bullet.pos)
            length = math.dist(head, tail)
            check('tracer: đầu vệt nằm trên viên đạn thật khi đã đi xa (m)', round(off, 4), '< 0.01', off < 0.01)
            check('  vệt dài đúng bằng cấu hình (m)', round(length, 2), f'{gun.tracer.length}', abs(length - gun.tracer.length) < 0.05)
        else:
            check('tracer: có vệt đang bay', None, 'có', False)
        yield from self.until(lambda: not fx.tracers.active, 3.5)
        check('mọi vệt được trả về bể sau khi đạn trúng / hết hạn', f'{len(fx.tracers.active)} đang bay, {len(fx.tracers.free)} rảnh',
              f'0, {gun.tracer.pool}', not fx.tracers.active and len(fx.tracers.free) == gun.tracer.pool)

        # ngắm: tia lửa nhỏ lại; tắt tracer bằng every = 0
        sizes = {}
        for label, ads_on in (('hông', False), ('ngắm', True)):
            vals = []
            self.reset_state(auto=False, mag=30)
            if ads_on:
                held_keys['right mouse'] = 1
                yield from self.until(lambda: player.ads_amount >= 1.0, 1.0)
            for _ in range(12):
                combat.pressed = True
                held_keys['left mouse'] = 1
                yield
                held_keys['left mouse'] = 0
                vals.append(fx.flash._size)
                yield from self.wait(0.1)
            sizes[label] = sum(vals) / len(vals)
            held_keys['right mouse'] = 0
            yield from self.wait(0.3)
        check('ngắm: tia lửa nhỏ lại (cỡ trung bình ngắm / hông)', round(sizes['ngắm'] / sizes['hông'], 2), f'~{gun.flash.ads_scale} +-0.12',
              abs(sizes['ngắm'] / sizes['hông'] - gun.flash.ads_scale) < 0.12)
        every0 = gun.tracer.every
        gun.tracer.every = 0
        self.reset_state(auto=True, mag=30)
        fx.tracers.spawned = 0
        held_keys['left mouse'] = 1
        yield from self.wait(0.4)
        held_keys['left mouse'] = 0
        check('every = 0: không có tracer', fx.tracers.spawned, 0, fx.tracers.spawned == 0)
        gun.tracer.every = every0
        fx.on_shot = orig_on_shot
        yield from self.wait(0.5)

        # --- cảnh tổng ---
        self.reset_state()
        yield from self.wait(0.4)
        shot('ready')


def report():
    print('\n=== KIỂM TRA G5 ===')
    print(f"{'mục':76s} {'đo được':>26s} {'mong đợi':>22s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:76s} {str(got):>26s} {str(expected):>22s}  {"ĐẠT" if ok else "TRƯỢT"}')
    dts = sorted(frame_dts)
    n = len(dts)
    avg = n / sum(dts)
    low1 = 1 / dts[int(n * 0.99)]
    print(f'\nFPS (vsync tắt, 1280x720, toàn bộ kịch bản): {n} khung, trung bình {avg:.0f}, 1% thấp nhất {low1:.0f}, '
          f'khung chậm nhất {dts[-1] * 1000:.0f} ms')
    results.append(('FPS trung bình >= 60', round(avg), '>= 60', avg >= 60))
    print(f'{sum(r[3] for r in results)}/{len(results)} mục đạt')


Script()
game.app.run()
