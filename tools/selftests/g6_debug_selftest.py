"""G6: bảng debug (F1) và HUD bằng game thật.

Điều khiển qua đúng đường của game (game.input('f1'), con trỏ giả qua panel.pointer, held_keys). Đo:
  - F1 mở / đóng (cả Esc): chuột nhả / khoá, không bắn / ngắm / nạp / đổi chế độ khi bảng mở, bảng đóng thì không có update nào chạy
  - mở lúc đang nạp / đang rút súng không làm hỏng trạng thái
  - kéo thanh bằng chuột: giá trị theo con trỏ, nhả chuột thì dừng; chuột phải về mặc định; công tắc bật/tắt; ô chọn (bóng đổ)
  - đổi thanh thì hành vi ĐỔI THẬT, đo lại: nhịp bắn (rpm), thời gian vào ngắm, độ giật lên, nhịp bob, âm lượng tiếng súng, thời gian nạp,
    độ sáng đèn (đầu vào shader + ảnh chụp), ánh sáng trên súng, khoảng cách mắt-điểm ngắm, tốc độ tracer, độ tản (hình nón)
  - lưu -> đổi -> nạp phục hồi; nạp file hỏng không crash; đặt lại nhóm / tất cả / từng thanh
  - nạp thông số lúc khởi động (cả số "cần khởi động lại": đạn trong băng)
  - hình nón: vòng từng trạng thái đúng theo spread.py, vòng hiện tại gồm bloom, chấm phát vừa bắn
  - HUD đủ phần tử: số đạn, chế độ bắn, ĐANG NẠP / HẾT ĐẠN, FPS, khoảng cách bia vừa trúng (rồi mờ), gợi ý phím, ghi công
Ảnh vào shots\\debug_*.png (bảng) và shots\\hud_*.png (HUD).

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\with_game_lock.py .venv\\Scripts\\python.exe -X utf8 tools\\selftests\\g6_debug_selftest.py   (thoát mã 1 nếu có mục trượt)
"""
import json
import math
import statistics
import sys
import tempfile
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

import fps.app as appmod  # noqa: E402

# số liệu "cần khởi động lại" (đạn trong băng) phải có hiệu lực khi nạp lúc khởi động: file tạm, KHÔNG đụng user_params.json thật
TMP = Path(tempfile.mkdtemp(prefix='fps_params_'))
STARTUP = TMP / 'startup.json'
STARTUP.write_text(json.dumps({'version': 1, 'values': {'gun.magazine': 20, 'gun.reserve': 90, 'gun.rpm': 800.0, 'gun.khong_co': 1,
                                                        'gun.ads_time': 'nhanh'}}), encoding='utf-8')
appmod.USER_PARAMS = STARTUP

from main import create_game  # noqa: E402
from panda3d.core import Filename  # noqa: E402
from PIL import Image, ImageStat  # noqa: E402
from ursina import Entity, Text, application, camera, held_keys, mouse, time  # noqa: E402

from fps.core.handling import Phase  # noqa: E402
from fps.core.movement import MoveState  # noqa: E402
from fps.core.recoil import CameraRecoil, GunKick  # noqa: E402
from fps.core.spread import angle_between, ring_radius  # noqa: E402
from fps.game import debug_panel as dp  # noqa: E402

game = create_game(vsync=False, sound=True, draw=False, moving_targets=False, user_params=True, hud=True, free_aim=False)
player, combat, viewmodel, hud = game.player, game.combat, game.viewmodel, game.hud
store, panel = game.params_store, game.debug
weapon, handling = combat.weapon, combat.handling
gun = game.params.gun
mouse.locked = False
combat.require_locked_mouse = False
combat.rng.seed(11)
render = application.base.render

results = []
skip = {'next': False}
POINTER = {'xy': (0.0, 0.0)}
panel.pointer = lambda: POINTER['xy']
panel.path = TMP / 'preset.json'                   # lưu / nạp thử vào file tạm


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def shot(prefix, name):
    out = ROOT / 'shots' / f'{prefix}_{name}.png'
    out.parent.mkdir(exist_ok=True)
    application.base.win.saveScreenshot(Filename.from_os_specific(str(out)))
    skip['next'] = True
    print('ĐÃ CHỤP', out.name)
    return out


def brightness(path, box) -> float:
    img = Image.open(path).convert('L').crop(box)
    return ImageStat.Stat(img).mean[0]


def spec(sid):
    return store.by_id[sid]


def texts_on_screen() -> list:
    return [e.text for e in camera.ui.children if isinstance(e, Text) and e.enabled and e.text]


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.last = None
        self.dts = []
        self.update_calls = 0

    def update(self):
        if self.last is not None and not skip['next']:
            self.dts.append(pytime.perf_counter() - self.last)
        skip['next'] = False
        self.last = pytime.perf_counter()
        try:
            next(self.gen)
        except StopIteration:
            report()
            sys.exit(0 if all(r[3] for r in results) else 1)

    def wait(self, seconds, frames=3):
        t, n = 0.0, 0
        while t < seconds or n < frames:
            yield
            t += min(time.dt, 0.05)
            n += 1

    # --- đưa mọi thứ về tình trạng sạch ---
    def reset_state(self, mag=30, ads=0.0, auto=True):
        for k in ('w', 'a', 's', 'd', 'shift', 'control', 'space', 'left mouse', 'right mouse'):
            held_keys[k] = 0
        player.position = (0, 0, 0)
        player.vx = player.vz = player.vy = 0.0
        player.on_ground = True
        player.yaw, player.pitch = 0.0, 0.0
        player._apply_view()
        player.ads, player.ads_amount = ads > 0, ads
        player.sprint_amount = 0.0
        combat.recoil = CameraRecoil(gun.recoil, combat.rng)
        combat.gun_kick = GunKick(gun.kick, combat.rng)
        combat.accuracy.bloom = 0.0
        combat.accuracy.since_shot = 1e9
        combat.bullets.clear()
        weapon.auto = auto
        weapon.mag = mag
        weapon.reserve = 150
        weapon.cooldown = 0.0
        combat.pressed = False
        handling.phase, handling.key, handling.t = Phase.READY, None, 0.0
        handling.events.clear()
        viewmodel.hold_ready_pose()

    # --- con trỏ giả ---
    def row_of(self, s):
        """Chọn nhóm của thanh, cuộn tới nó, trả về hàng hiển thị."""
        panel.select_group(s.group)
        if s.advanced and not panel.show_advanced:
            panel.toggle_advanced()
        n = panel.items.index(s)
        panel.offset = max(0, min(n - 1, len(panel.items) - dp.ROWS))
        panel._bind_rows()
        return next(r for r in panel.rows if r.item is s)

    def track_point(self, s, value):
        row = self.row_of(s)
        frac = (value - s.lo) / (s.hi - s.lo)
        return panel.track_x0 + (panel.track_x1 - panel.track_x0) * frac, row.yc

    def mouse_down(self, x, y):
        POINTER['xy'] = (x, y)
        game.input('left mouse down')

    def mouse_up(self):
        game.input('left mouse up')

    def slide_to(self, sid, value):
        """Kéo thanh bằng chuột giả tới `value` (nhấn tại vị trí rồi nhả); trả về giá trị đã đặt."""
        s = spec(sid)
        x, y = self.track_point(s, value)
        self.mouse_down(x, y)
        yield
        self.mouse_up()
        yield

    def button_center(self, b):
        x0, y0, x1, y1 = b.rect
        return (x0 + x1) / 2, (y0 + y1) / 2

    def click_button(self, b):
        self.mouse_down(*self.button_center(b))
        yield
        self.mouse_up()
        yield

    def open_panel(self):
        if not panel.is_open:
            game.input('f1')
        yield from self.wait(0.15)

    def close_panel(self):
        if panel.is_open:
            game.input('f1')
        mouse.locked = False                      # trả lại con trỏ cho người dùng
        yield from self.wait(0.1)

    # --- đo ---
    def measure_rate(self, seconds=1.2):
        self.reset_state(mag=200)
        weapon.shot_times.clear()
        held_keys['left mouse'] = 1
        yield from self.wait(seconds)
        held_keys['left mouse'] = 0
        t = list(weapon.shot_times)
        gaps = [b - a for a, b in zip(t, t[1:])]
        return 60.0 / (sum(gaps) / len(gaps)) if gaps else 0.0

    def measure_ads_time(self):
        self.reset_state()
        yield from self.wait(0.1)
        held_keys['right mouse'] = 1
        t = 0.0
        while player.ads_amount < 1.0 and t < 3.0:
            yield
            t += time.dt
        held_keys['right mouse'] = 0
        return t

    def measure_recoil(self):
        self.reset_state(mag=3)
        gun.recoil.up_noise = gun.recoil.right_noise = gun.recoil.right_walk = 0.0
        low = 0.0
        held_keys['left mouse'] = 1
        for _ in range(70):
            yield
            low = min(low, player.pitch)
        held_keys['left mouse'] = 0
        return -low

    def measure_bob(self):
        self.reset_state()
        game.sway.phase = 0.0
        game.sway.bob_amount = 0.0
        yield from self.wait(0.1)
        held_keys['w'] = 1
        total, prev = 0.0, game.sway.phase
        t = 0.0
        while t < 1.3:
            yield
            t += time.dt
            ph = game.sway.phase
            total += (ph - prev) % (2 * math.pi)
            prev = ph
        held_keys['w'] = 0
        return total

    def measure_reload(self):
        self.reset_state(mag=10)
        yield from self.wait(0.1)
        combat.request_reload()
        t = 0.0
        yield
        while handling.busy and t < 8:
            yield
            t += time.dt
        return t

    def shoot_one(self):
        self.reset_state(mag=30, auto=False)
        yield from self.wait(0.05)
        combat.pressed = True
        held_keys['left mouse'] = 1
        yield
        held_keys['left mouse'] = 0
        yield

    # =====================================================================================================
    def run(self):
        yield from self.wait(0.6)

        # --- A. nạp thông số lúc khởi động (số "cần khởi động lại" có hiệu lực) ---
        rep = game.params_report
        check('khởi động: nạp user_params (3 giá trị dùng được, 2 mục bị bỏ qua)', (rep.applied, len(rep.ignored)), '(3, 2)',
              rep.ok and rep.applied == 3 and len(rep.ignored) == 2)
        check('khởi động: băng đạn / dự trữ theo file (cần khởi động lại)', (weapon.mag, weapon.mag_size, weapon.reserve), '(20, 20, 90)',
              (weapon.mag, weapon.mag_size, weapon.reserve) == (20, 20, 90))
        check('khởi động: rpm theo file', gun.rpm, '800', gun.rpm == 800.0 and abs(weapon.interval - 60 / 800) < 1e-9)
        from fps.weapon_data import LookData, M4
        check('khởi động: giá trị sai kiểu giữ mặc định (ads_time)', gun.ads_time, f'{M4.ads_time}', gun.ads_time == M4.ads_time)
        check('M4 toàn cục không bị làm bẩn', (M4.rpm, M4.magazine), '(750, 30)', (M4.rpm, M4.magazine) == (750.0, 30))
        store.reset_all()
        weapon.mag_size, weapon.mag, weapon.reserve = gun.magazine, gun.magazine, gun.reserve    # chỉ làm lại phần chép lúc dựng (số liệu đã về mặc định)

        # --- B. F1 mở / đóng, chuột ---
        check('chưa mở F1: bảng chưa dựng, không tốn gì', (panel.is_open, panel._built), '(False, False)', not panel.is_open and not panel._built)
        t0 = pytime.perf_counter()
        game.input('f1')
        build_ms = (pytime.perf_counter() - t0) * 1000
        yield from self.wait(0.2)
        check('F1 mở: bảng hiện, chuột nhả, người chơi báo ui_open', (panel.is_open, panel.root.enabled, mouse.locked, player.ui_open),
              '(T, T, F, T)', panel.is_open and panel.root.enabled and not mouse.locked and player.ui_open)
        print(f'  (dựng bảng lần đầu: {build_ms:.0f} ms)')
        check('lần mở đầu tiên dựng < 800 ms', round(build_ms), '< 800', build_ms < 800)
        shot('debug', 'open_fire')
        yield from self.wait(0.1)

        # bảng mở: bấm chuột / phím không làm gì với súng
        self.reset_state()
        shots0 = combat.shots_fired
        held_keys['left mouse'] = 1
        held_keys['right mouse'] = 1
        game.input('left mouse down')
        game.input('b')
        game.input('r')
        yield from self.wait(0.4)
        keys = player.read_keys()
        check('bảng mở: giữ chuột trái không bắn', combat.shots_fired - shots0, '0', combat.shots_fired == shots0)
        check('bảng mở: giữ chuột phải không ngắm', (keys['ads'], keys['fire'], round(player.ads_amount, 2)), '(F, F, 0)',
              not keys['ads'] and not keys['fire'] and player.ads_amount == 0)
        check('bảng mở: B không đổi chế độ, R không nạp, chuột nhấn không nhớ cò', (weapon.auto, combat.reload_requested, handling.busy, combat.pressed),
              '(T, F, F, F)', weapon.auto and not combat.reload_requested and not handling.busy and not combat.pressed)
        held_keys['left mouse'] = 0
        held_keys['right mouse'] = 0
        game.input('left mouse up')
        yield from self.wait(0.1)

        # đóng bảng: chuột khoá lại, không xoay bất thường
        yaw0, pitch0 = player.yaw, player.pitch
        game.input('f1')
        locked_after_close = mouse.locked
        yield from self.wait(0.2)
        check('F1 đóng: bảng ẩn, chuột khoá lại, ui_open tắt', (panel.is_open, panel.root.enabled, locked_after_close, player.ui_open),
              '(F, F, T, F)', not panel.is_open and not panel.root.enabled and locked_after_close and not player.ui_open)
        check('F1 đóng: không bị xoay bất thường khi khoá chuột (độ)', round(abs(player.yaw - yaw0) % 360 + abs(player.pitch - pitch0), 2), '< 3',
              (abs(player.yaw - yaw0) % 360 < 3 or abs(player.yaw - yaw0) % 360 > 357) and abs(player.pitch - pitch0) < 3)
        mouse.locked = False
        keys = player.read_keys()
        held_keys['left mouse'] = 1
        held_keys['right mouse'] = 1
        keys = player.read_keys()
        check('đóng bảng: chuột trái / phải lại là bắn / ngắm', (keys['fire'], keys['ads']), '(T, T)', keys['fire'] and keys['ads'])
        held_keys['left mouse'] = 0
        held_keys['right mouse'] = 0

        # bảng đóng thì không có update nào chạy
        calls = {'n': 0}
        real_update = panel.update

        def counted(dt):
            calls['n'] += 1
            return real_update(dt)

        panel.update = counted
        yield from self.wait(0.3, frames=30)
        check('bảng đóng: update của bảng chạy 0 lần trong 30 khung', calls['n'], '0', calls['n'] == 0)
        game.input('f1')
        yield from self.wait(0.1, frames=5)
        check('bảng mở: update chạy mỗi khung', calls['n'] >= 5, 'True', calls['n'] >= 5)
        game.input('escape')
        yield from self.wait(0.1)
        mouse.locked = False
        check('Esc khi bảng mở: đóng bảng (không chỉ đổi khoá chuột)', (panel.is_open, panel.root.enabled), '(F, F)', not panel.is_open and not panel.root.enabled)
        panel.update = real_update

        # mở / đóng giữa lúc nạp và rút súng
        self.reset_state(mag=10)
        yield from self.wait(0.1)
        combat.request_reload()
        yield from self.wait(0.5)
        phase_before = handling.phase
        yield from self.open_panel()
        yield from self.wait(0.4)
        yield from self.close_panel()
        yield from self.wait(4.5)
        check('F1 giữa lúc nạp: nạp vẫn chạy tới cùng và đạn đúng', (phase_before.value, handling.phase.value, weapon.mag, weapon.reserve),
              '(reload, ready, 30, 130)', phase_before is Phase.RELOAD and handling.phase is Phase.READY and weapon.mag == 30 and weapon.reserve == 130)
        self.reset_state()
        handling.start_draw()
        yield from self.wait(0.2)
        yield from self.open_panel()
        yield from self.wait(0.3)
        yield from self.close_panel()
        yield from self.wait(1.2)
        check('F1 giữa lúc rút súng: rút súng xong, súng ở tư thế sẵn sàng', handling.phase.value, 'ready', handling.phase is Phase.READY and viewmodel.clip_key is None)

        # --- C. kéo thanh bằng chuột ---
        yield from self.open_panel()
        s = spec('gun.rpm')
        x, y = self.track_point(s, 900)
        self.mouse_down(x, y)
        yield
        check('nhấn lên thanh: giá trị theo con trỏ (rpm 900)', gun.rpm, '900', abs(gun.rpm - 900) <= s.step)
        x2, _ = self.track_point(s, 600)
        POINTER['xy'] = (x2, y)
        yield
        yield
        check('kéo đi tiếp: giá trị bám theo (rpm 600)', gun.rpm, '600', abs(gun.rpm - 600) <= s.step)
        self.mouse_up()
        POINTER['xy'] = (self.track_point(s, 1400)[0], y)
        yield
        yield
        check('nhả chuột: thanh đứng yên dù con trỏ di chuyển tiếp', gun.rpm, '600', abs(gun.rpm - 600) <= s.step)
        self.mouse_down(panel.track_x1 + 0.015, y)               # lố ra ngoài đầu thanh một chút (vẫn trong vùng bắt chuột)
        yield
        self.mouse_up()
        check('nhấn quá đầu thanh: kẹp ở giá trị lớn nhất', gun.rpm, str(s.hi), gun.rpm == s.hi)
        # chuột phải về mặc định
        POINTER['xy'] = (x, y)
        game.input('right mouse down')
        yield
        check('chuột phải trên hàng: về mặc định', gun.rpm, '750', gun.rpm == 750.0 and store.is_default(s))
        # công tắc
        sb = spec('player.sprint_blocks_fire')
        row = self.row_of(sb)
        self.mouse_down((panel.track_x0 + panel.track_x1) / 2, row.yc)
        yield
        self.mouse_up()
        check('bấm công tắc bật/tắt (bóp cò thì thôi chạy)', game.params.player.sprint_blocks_fire, 'False', game.params.player.sprint_blocks_fire is False)
        self.mouse_down((panel.track_x0 + panel.track_x1) / 2, row.yc)
        yield
        self.mouse_up()
        check('bấm lần nữa: bật lại', game.params.player.sprint_blocks_fire, 'True', game.params.player.sprint_blocks_fire is True)
        # ô chọn (bóng đổ): Thật -> Tắt -> Giả -> Thật
        ss = spec('look.shadows')
        row = self.row_of(ss)
        seq = []
        for _ in range(3):
            self.mouse_down((panel.track_x0 + panel.track_x1) / 2, row.yc)
            yield
            self.mouse_up()
            yield from self.wait(0.05)
            seq.append((game.params.look.shadows, game.look.mode))
        check('ô chọn bóng đổ: Tắt -> Giả -> Thật, bóng theo ngay, không lỗi', seq, '[(F,F), (fake,fake), (T,T)]',
              seq == [(False, False), ('fake', 'fake'), (True, True)])
        # cuộn
        panel.select_group('sway')
        panel.toggle_advanced()
        n_items = len(panel.items)
        panel.scroll(5)
        check('con lăn cuộn danh sách dài (Sway + nâng cao)', (n_items > dp.ROWS, panel.offset), '(True, 5)', n_items > dp.ROWS and panel.offset == 5)
        top_item = panel.rows[0].item
        check('  hàng đầu là mục thứ 6 của danh sách', panel.rows[0].item is panel.items[5], 'True', panel.rows[0].item is panel.items[5])
        panel.scroll(-99)
        panel.toggle_advanced()
        # thanh cuộn kéo bằng chuột
        panel.select_group('look')
        panel.toggle_advanced()
        y_mid = (panel.rows_top + panel.rows_bottom) / 2
        self.mouse_down(panel.scroll_x1 - 0.002, y_mid)
        yield
        self.mouse_up()
        check('kéo thanh cuộn tới giữa: danh sách cuộn theo', panel.offset > 0, 'True', panel.offset > 0)
        panel.toggle_advanced()
        panel.select_group('fire')
        yield from self.close_panel()

        # --- D. đổi thanh thì hành vi đổi thật ---
        base_rate = yield from self.measure_rate()
        yield from self.open_panel()
        yield from self.slide_to('gun.rpm', 1200)
        yield from self.close_panel()
        rate = yield from self.measure_rate()
        check('rpm 750 -> 1200: nhịp bắn đo được (phát/phút)', f'{base_rate:.0f} -> {rate:.0f}', '750 -> 1200 (±3%)',
              abs(base_rate - 750) < 25 and abs(rate - 1200) < 40)

        base_ads = yield from self.measure_ads_time()
        yield from self.open_panel()
        yield from self.slide_to('gun.ads_time', 0.5)
        yield from self.close_panel()
        ads = yield from self.measure_ads_time()
        store.reset(spec('gun.ads_time'))
        check(f'ads_time {M4.ads_time} -> 0,5: thời gian vào ngắm đo được (s)', f'{base_ads:.2f} -> {ads:.2f}', f'{M4.ads_time:.2f} -> 0,50',
              abs(base_ads - M4.ads_time) < 0.06 and abs(ads - 0.5) < 0.08)

        yield from self.open_panel()
        yield from self.slide_to('gun.recoil.up_scale', 1.0)
        yield from self.close_panel()
        up1 = yield from self.measure_recoil()
        yield from self.open_panel()
        yield from self.slide_to('gun.recoil.up_scale', 2.0)
        yield from self.close_panel()
        up2 = yield from self.measure_recoil()
        check('up_scale 1 -> 2: độ giật lên của 3 phát tăng gấp đôi (độ)', f'{up1:.2f} -> {up2:.2f}', 'tỉ số 2,0 (±10%)', up1 > 0.3 and abs(up2 / up1 - 2.0) < 0.2)
        yield from self.open_panel()
        yield from self.slide_to('gun.recoil.up_scale', 0.0)
        yield from self.close_panel()
        up0 = yield from self.measure_recoil()
        check('up_scale 0: không giật lên', round(up0, 3), '0', up0 < 0.01)
        gun.recoil.up_noise, gun.recoil.right_noise, gun.recoil.right_walk = M4.recoil.up_noise, M4.recoil.right_noise, M4.recoil.right_walk
        store.reset_group('recoil')

        yield from self.open_panel()
        yield from self.slide_to('gun.sway.bob_rate', 0.4)
        yield from self.close_panel()
        bob_a = yield from self.measure_bob()
        yield from self.open_panel()
        yield from self.slide_to('gun.sway.bob_rate', 0.8)
        yield from self.close_panel()
        bob_b = yield from self.measure_bob()
        check('bob_rate 0,4 -> 0,8: pha bob khi đi 1,3 s tăng gấp đôi (rad)', f'{bob_a:.2f} -> {bob_b:.2f}', 'tỉ số 2,0 (±8%)',
              bob_a > 0.5 and abs(bob_b / bob_a - 2.0) < 0.16)

        yield from self.open_panel()
        yield from self.slide_to('gun.shot_volume', 0.3)
        yield from self.close_panel()
        yield from self.shoot_one()
        sound = game.audio.sounds[(game.audio._next - 1) % len(game.audio.sounds)]
        check('shot_volume 0,8 -> 0,3: âm lượng của tiếng vừa phát', round(sound.get_volume(), 2), '0,30', abs(sound.get_volume() - 0.3) < 0.02)

        yield from self.open_panel()
        yield from self.slide_to('gun.muzzle_velocity', 250)
        yield from self.close_panel()
        yield from self.shoot_one()
        sp = [s_.tracer.speed for s_ in game.fx.tracers.active]
        check('muzzle_velocity 250: tracer sinh ra đi theo tốc độ mới', sp[-1:] , '[250]', bool(sp) and sp[-1] == 250.0)
        store.reset_group('fire')

        yield from self.open_panel()
        yield from self.slide_to('gun.reload.speed', 2.0)
        yield from self.close_panel()
        rl = yield from self.measure_reload()
        check('reload.speed 2,0: nạp (còn đạn) mất ~3,63 / 2 giây', round(rl, 2), '1,82 (±0,15)', abs(rl - 3.63 / 2) < 0.15)
        store.reset_group('reload')

        # ánh sáng: đầu vào shader + ảnh chụp
        self.reset_state()
        yield from self.wait(0.3, frames=6)
        lamp0 = render.get_shader_input('look_lamp2').get_vector()[3]
        box = (700, 150, 1100, 450)
        img_a = shot('debug', 'light_default')
        yield from self.wait(0.1, frames=3)
        yield from self.open_panel()
        yield from self.slide_to('look.lamp_intensity', 0.5)
        yield from self.close_panel()
        yield from self.wait(0.2, frames=6)
        lamp1 = render.get_shader_input('look_lamp2').get_vector()[3]
        img_b = shot('debug', 'light_dim')
        yield from self.wait(0.1, frames=3)
        b_a, b_b = brightness(img_a, box), brightness(img_b, box)
        lamp_default = LookData().lamp_intensity                    # mặc định hiện hành (không chép số cứng)
        check(f'lamp_intensity {lamp_default} -> 0,5: đầu vào shader look_lamp2.w đổi theo', f'{lamp0:.2f} -> {lamp1:.2f}', f'{lamp_default:.2f} -> 0,50',
              abs(lamp0 - lamp_default) < 1e-3 and abs(lamp1 - 0.5) < 1e-3)
        check('  ảnh chụp tối đi thật (độ sáng giữa màn hình)', f'{b_a:.1f} -> {b_b:.1f}', 'giảm > 15%', b_b < b_a * 0.85)
        store.reset_group('look')
        yield from self.wait(0.1, frames=3)
        lamp2 = render.get_shader_input('look_lamp2').get_vector()[3]
        check('đặt lại nhóm Ánh sáng: đèn sáng lại như cũ', round(lamp2, 2), f'{lamp_default:.2f}', abs(lamp2 - lamp_default) < 1e-3)
        spec_default = M4.view_light.specular
        spec_target = 1.0 if abs(spec_default - 1.0) > 0.05 else 0.5          # kéo tới số KHÁC mặc định hiện hành
        yield from self.open_panel()
        yield from self.slide_to('gun.view_light.specular', spec_target)
        yield from self.close_panel()
        spec_in = viewmodel.root.get_shader_input('vm_mat').get_vector()[0]
        check(f'view_light.specular {spec_default} -> {spec_target}: shader của súng nhận số mới', round(spec_in, 2), f'{spec_target:.2f}',
              abs(spec_in - spec_target) < 0.01)
        store.reset_group('look')

        relief0 = game.sway.ads_target[2]
        yield from self.open_panel()
        yield from self.slide_to('gun.ads_eye_relief', 0.30)
        yield from self.close_panel()
        relief1 = game.sway.ads_target[2]
        check('ads_eye_relief 0,18 -> 0,30: tư thế ADS dịch ra sau đúng 0,12 m', round(relief1 - relief0, 3), '0,120', abs((relief1 - relief0) - 0.12) < 0.003)
        store.reset_group('ads')
        yield from self.wait(0.1)

        # --- E. hình nón ---
        self.reset_state()
        yield from self.open_panel()
        yield from self.wait(0.2, frames=4)
        acc = combat.accuracy
        yield from self.slide_to('gun.accuracy.stand', 2.0)                 # mặc định chỉ còn tản cơ khí 0,03 độ: đo từ một số dễ thấy
        yield from self.wait(0.1, frames=3)
        r_stand0 = panel.state_rings[0].scale_x
        yield from self.slide_to('gun.accuracy.stand', 4.0)
        yield from self.wait(0.1, frames=3)
        r_stand1 = panel.state_rings[0].scale_x
        want = ring_radius(4.0, dp.CONE_DISTANCE) / ring_radius(2.0, dp.CONE_DISTANCE)
        check('hình nón: kéo "Đứng yên" 2° -> 4°, vòng Đứng to lên đúng tỉ số tan', f'{r_stand1 / r_stand0:.3f}', f'{want:.3f}', abs(r_stand1 / r_stand0 - want) < 0.01)
        legend = panel.legend[0][2].text
        check('  chú giải ghi góc và mét mới', legend, '4,00° · 1,7 m', '4,00' in legend and '1,7' in legend)
        for i, (name, state, ads_, _c) in enumerate(dp.CONE_STATES):
            expected = 2 * ring_radius(acc.base(state, ads_), dp.CONE_DISTANCE) * panel.cone_k
            got = panel.state_rings[i].scale_x
            if abs(got - max(expected, 0.004)) > 1e-4:
                check(f'  vòng "{name}" theo spread.py', round(got, 4), round(expected, 4), False)
                break
        else:
            check('  mọi vòng trạng thái đúng theo Accuracy.base (spread.py)', len(dp.CONE_STATES), 'tất cả khớp', True)
        acc.bloom = 2.0
        acc.since_shot = 0.0
        yield
        cur_expected = 2 * ring_radius(combat.spread_now, dp.CONE_DISTANCE) * panel.cone_k
        yield
        check('vòng hiện tại gồm bloom (góc đứng 4° + bloom)', round(panel.cur_ring.scale_x, 4), round(2 * ring_radius(combat.spread_now, dp.CONE_DISTANCE) * panel.cone_k, 4),
              abs(panel.cur_ring.scale_x - 2 * ring_radius(combat.spread_now, dp.CONE_DISTANCE) * panel.cone_k) < 1e-4 and combat.spread_now > 4.0)
        # vòng hiện tại bám trạng thái ngắm
        player.ads_amount = 1.0
        player.ads = True
        yield from self.wait(0.05, frames=2)
        check('ngắm hẳn: chú giải đánh dấu hàng "Ngắm"', panel.legend[5][1].main.color.a > 0.9 and panel.legend[0][1].main.color.a < 0.7, 'True',
              panel.legend[5][1].main.color.a > 0.9 and panel.legend[0][1].main.color.a < 0.7)
        player.ads_amount = 0.0
        player.ads = False
        # chấm phát bắn: bắn một phát, chấm nằm đúng chỗ
        self.reset_state(mag=30, auto=False)
        yield from self.wait(0.1, frames=3)
        combat.pressed = True
        held_keys['left mouse'] = 0
        player.ui_open = False                      # panel mở nhưng bắn bằng đường mã (bảng thật chặn chuột; ở đây chỉ đo hình nón)
        yield
        yield
        yield from self.wait(0.1, frames=3)
        used = [d for d in panel.dots if d.enabled]
        ls = combat.last_shot
        if used and ls:
            d = used[-1]
            off = math.hypot(d.x - panel.cone_cx, d.y - panel.cone_cy)
            want_off = ring_radius(angle_between(ls.view_dir, ls.direction), dp.CONE_DISTANCE) * panel.cone_k
            check('chấm phát bắn cách tâm đúng góc lệch thật (UI)', f'{off:.4f}', f'{want_off:.4f}', abs(off - want_off) < 0.004 and off <= panel.cone_r + 1e-6)
        else:
            check('có chấm cho phát vừa bắn', len(used), '>= 1', False)
        player.ui_open = True
        store.reset_group('accuracy')
        panel.select_group('accuracy')
        yield from self.wait(0.2, frames=4)
        shot('debug', 'cone')
        yield from self.wait(0.1, frames=3)

        # --- F. lưu / nạp / đặt lại bằng nút ---
        store.reset_all()
        panel.select_group('fire')
        yield from self.wait(0.1)
        yield from self.slide_to('gun.rpm', 900)
        yield from self.slide_to('gun.accuracy.stand', 1.0)
        yield from self.slide_to('gun.kick.peak[3]', 3.0)
        want = {s_.id: store.get(s_) for s_ in store.specs}
        shot('debug', 'changed')
        yield from self.click_button(panel.footer[0])
        saved = json.loads(panel.path.read_text(encoding='utf-8')) if panel.path.exists() else {}
        check('nút Lưu: ghi đúng 3 giá trị khác mặc định vào file', sorted(saved.get('values', {})), "['gun.accuracy.stand','gun.kick.peak[3]','gun.rpm']",
              sorted(saved.get('values', {})) == ['gun.accuracy.stand', 'gun.kick.peak[3]', 'gun.rpm'])
        check('  thông báo trạng thái ghi "đã lưu 3 giá trị"', panel.message, 'Đã lưu 3 ...', panel.message.startswith('Đã lưu 3'))
        yield from self.slide_to('gun.rpm', 400)
        yield from self.slide_to('gun.ads_time', 0.7)
        store.set(spec('gun.accuracy.stand'), 5.0)
        yield from self.click_button(panel.footer[1])
        got = {s_.id: store.get(s_) for s_ in store.specs}
        check('nút Nạp: phục hồi đúng trạng thái đã lưu (cả số đổi thêm sau khi lưu)', got == want, 'True', got == want)
        check('  thông báo "Đã nạp 3 giá trị"', panel.message, 'Đã nạp 3 ...', panel.message.startswith('Đã nạp 3'))
        panel.select_group('fire')
        yield from self.click_button(panel.btn_reset_group)
        check('nút "Đặt lại nhóm này": nhóm Bắn về mặc định, nhóm khác giữ', (gun.rpm, gun.accuracy.stand), '(750, 1.0)', gun.rpm == 750.0 and gun.accuracy.stand == 1.0)
        yield from self.click_button(panel.footer[2])
        check('nút "Mặc định (tất cả)": mọi thanh về mặc định', (len(store.changed_specs()), gun.accuracy.stand), f'(0, {M4.accuracy.stand})', not store.changed_specs() and gun.accuracy.stand == M4.accuracy.stand)
        # file hỏng
        for text, label in (('{ không phải json', 'JSON hỏng'), ('[1,2,3]', 'sai dạng'), ('', 'rỗng')):
            store.set(spec('gun.rpm'), 800)
            panel.path.write_text(text, encoding='utf-8')
            yield from self.click_button(panel.footer[1])
            check(f'nạp file {label}: không crash, giữ nguyên số hiện tại, báo lỗi', (gun.rpm, 'giữ nguyên' in panel.message), '(800, True)',
                  gun.rpm == 800.0 and 'giữ nguyên' in panel.message)
        panel.path.unlink()
        yield from self.click_button(panel.footer[1])
        check('nạp khi chưa có file: báo "chưa có file", không crash', panel.message, 'Chưa có file...', 'Chưa có file' in panel.message and gun.rpm == 800.0)
        store.reset_all()
        yield from self.wait(0.1)
        yield from self.close_panel()

        # --- G. chi phí ---
        self.reset_state()
        yield from self.wait(0.3)
        n0 = len(self.dts)
        yield from self.wait(1.5, frames=90)
        closed = statistics.median(self.dts[n0:]) * 1000
        yield from self.open_panel()
        yield from self.wait(0.3)
        n1 = len(self.dts)
        yield from self.wait(1.5, frames=90)
        opened = statistics.median(self.dts[n1:]) * 1000
        yield from self.close_panel()
        yield from self.wait(0.3)
        n2 = len(self.dts)
        yield from self.wait(1.5, frames=90)
        closed2 = statistics.median(self.dts[n2:]) * 1000
        print(f'  (khung hình trung vị: đóng {closed:.1f} ms, mở bảng {opened:.1f} ms, đóng lại {closed2:.1f} ms)')
        check('bảng mở: khung hình trung vị <= 1,8 x lúc đóng + 4 ms (máy bận thì cả hai cùng tăng)', f'{closed:.1f} -> {opened:.1f}', 'mở <= 1,8 x đóng + 4', opened <= 1.8 * closed + 4)
        check('bảng đóng lại: khung hình về như trước khi mở (±15%)', f'{closed:.1f} -> {closed2:.1f}', 'chênh < 15%', abs(closed2 - closed) < 0.15 * closed + 0.5)

        # --- H. HUD ---
        yield from self.hud_checks()

    def hud_checks(self):
        self.reset_state()
        yield from self.wait(0.3, frames=5)
        txt = texts_on_screen()
        joined = ' | '.join(txt)
        check('HUD: số đạn trong băng / dự trữ', hud.ammo.text, '30 / 150', '30' in hud.ammo.text and '150' in hud.ammo.text)
        check('HUD: chế độ bắn', hud.mode.text, 'TỰ ĐỘNG', hud.mode.text == 'TỰ ĐỘNG')
        game.input('b')
        yield from self.wait(0.1, frames=3)
        check('HUD: phím B đổi chế độ -> BẮN ĐƠN', hud.mode.text, 'BẮN ĐƠN', hud.mode.text == 'BẮN ĐƠN')
        game.input('b')
        yield from self.wait(0.1, frames=3)
        check('HUD: FPS hiển thị', hud.fps_text.text, '… FPS', hud.fps_text.text.endswith('FPS') and hud.fps_text.text[0].isdigit())
        check('HUD: gợi ý phím (R nạp, B đổi chế độ, F1 bảng chỉnh)', hud.hint.text, 'có R, B, F1', all(k in hud.hint.text for k in ('R ', 'B ', 'F1')))
        check('HUD: ghi công trong game', hud.credit.text, 'M4: BarcodeGames (CC BY 4.0)', hud.credit.text == 'M4: BarcodeGames (CC BY 4.0)')
        check('HUD: mọi chữ là Text của camera.ui (cây Entity)', len(txt), '>= 6', len(txt) >= 6 and 'M4: BarcodeGames (CC BY 4.0)' in joined)
        check('HUD: gợi ý và ghi công mờ (alpha)', (round(hud.hint.main.color.a, 2), round(hud.credit.main.color.a, 2)), 'alpha <= 0,55',
              hud.hint.main.color.a <= 0.55 and hud.credit.main.color.a <= 0.55)
        shot('hud', 'normal')
        yield from self.wait(0.1, frames=3)

        # đang nạp
        weapon.mag = 12
        combat.request_reload()
        yield from self.wait(0.8, frames=6)
        check('HUD: ĐANG NẠP ĐẠN + thanh tiến độ', (hud.prompt.text, hud.reload_bar.color.a > 0.5), "('ĐANG NẠP ĐẠN', True)",
              hud.prompt.text == 'ĐANG NẠP ĐẠN' and hud.reload_bar.color.a > 0.5)
        shot('hud', 'reload')
        yield from self.wait(4.0)
        # hết đạn
        self.reset_state(mag=0)
        weapon.reserve = 0
        yield from self.wait(0.2, frames=4)
        check('HUD: HẾT ĐẠN khi cả băng và dự trữ đều cạn', hud.prompt.text, 'HẾT ĐẠN', hud.prompt.text == 'HẾT ĐẠN')
        check('  số đạn đỏ khi băng cạn', (hud.ammo.main.color.r, hud.ammo.main.color.g < 0.6), '(đỏ, True)', hud.ammo.main.color.g < 0.6)
        shot('hud', 'empty')
        yield from self.wait(0.1, frames=3)
        self.reset_state(mag=0)
        yield from self.wait(0.2, frames=4)
        check('HUD: băng cạn còn dự trữ -> nhắc bấm R', hud.prompt.text, 'BẤM R ĐỂ NẠP ĐẠN', hud.prompt.text == 'BẤM R ĐỂ NẠP ĐẠN')
        # bia vừa trúng
        self.reset_state(mag=30, auto=False)
        gun.accuracy.stand = 0.0
        gun.accuracy.bloom_per_shot = 0.0
        player.yaw = math.degrees(math.atan2(-3.0, 10.0))               # bia 10 m lệch x = -3
        player.pitch = 0.0
        player._apply_view()
        yield from self.wait(0.1, frames=3)
        combat.pressed = True
        held_keys['left mouse'] = 1
        yield
        held_keys['left mouse'] = 0
        yield from self.wait(0.4, frames=6)
        check('HUD: khoảng cách bia vừa trúng (m)', hud.last_hit.text, '10 m', hud.last_hit.text.strip().endswith('m') and abs(float(hud.last_hit.text.split()[0]) - 10.4) < 0.7)
        shot('hud', 'hit')
        yield from self.wait(fb_time() + 0.3)
        check('  rồi mờ hẳn sau vài giây', repr(hud.last_hit.text), "''", hud.last_hit.text == '')
        store.reset_all()


def fb_time() -> float:
    return game.params.feedback.last_hit_display_time


def report():
    print('\n=== KIỂM TRA G6 (bảng debug F1 + HUD) ===')
    print(f"{'mục':78s} {'đo được':>26s} {'mong đợi':>26s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:78s} {str(got):>26s} {str(expected):>26s}  {"ĐẠT" if ok else "TRƯỢT"}')
    print(f'{sum(r[3] for r in results)}/{len(results)} mục đạt')


Script()
game.app.run()
