"""G4: ADS, sway (thở, lag chuột, bob), chạy nước rút (tư thế + trễ sprint-to-fire), ngồi/nhảy bằng game thật.

Điều khiển qua đúng đường phím của game (held_keys, combat.pressed, player.look). Đo:
  - ADS: thời gian vào/ra, FOV, tốc độ đi, độ nhạy chuột, đường ngắm (vòng sau + cột trước) trùng tâm màn hình theo phép chiếu thật
  - sway: biên độ thở và ADS còn ~20%, nhịp bob theo quãng đường, lag ngược hướng chuột, quán tính khi nhảy/ngồi, nhún khi chạm đất
  - chạy: tư thế hạ súng, bóp cò khi đang chạy thì trễ ~0,25 s mới bắn, bắn đơn không mất cú bóp
Ảnh vào shots\\g4_*.png.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\g4_selftest.py        (thoát mã 1 nếu có mục trượt)
"""
import math
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename, GeomVertexReader, Point2, Point3  # noqa: E402
from PIL import Image  # noqa: E402
from ursina import Entity, application, camera, held_keys, mouse, time, window  # noqa: E402

from fps.core.movement import MoveState  # noqa: E402
from fps.core.recoil import CameraRecoil, GunKick  # noqa: E402
from fps.core.sway import ads_target_for  # noqa: E402

game = create_game(vsync=False, sound=False, draw=False, moving_targets=False)     # G6: bia chạy làm đo thay đổi theo giờ; đo trên bia đứng yên
player, combat, viewmodel = game.player, game.combat, game.viewmodel
gun = game.params.gun
pp = game.params.player
sw = gun.sway
mouse.locked = False                      # không giữ con trỏ của người dùng
combat.require_locked_mouse = False       # cho phép bắn dù chuột không bị bắt (chỉ trong bài kiểm tra)
combat.rng.seed(7)
S = MoveState

results = []
frame_dts = []
frame_phase = []
phase = {'name': 'khởi động'}
skip = {'next': False}

# ghi lại tư thế mà Game.update đưa cho viewmodel: (kick súng, sway)
last = {'poses': ((0,) * 6, (0,) * 6)}
_orig_vm_update = viewmodel.update


def _vm_update(*poses):
    last['poses'] = poses
    return _orig_vm_update(*poses)


viewmodel.update = _vm_update


def sway_pose():
    return last['poses'][1]


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def shot(name, crop=None):
    out = ROOT / 'shots' / f'g4_{name}.png'
    out.parent.mkdir(exist_ok=True)
    application.base.win.saveScreenshot(Filename.from_os_specific(str(out)))
    if crop:
        c = Image.open(out).crop(crop)
        c.resize((c.width * 3, c.height * 3), Image.LANCZOS).save(ROOT / 'shots' / f'g4_{name}_zoom.png')
    skip['next'] = True
    print('ĐÃ CHỤP', out.name)


def gather_sight_points():
    """Mọi đỉnh thân súng trong hệ rig (cố định) kèm toạ độ lúc nghỉ trong hệ camera, để chọn vòng sau / cột trước."""
    rest = viewmodel.rig.get_mat(viewmodel.sway)
    pts = []
    for gnp in viewmodel.actor.find('**/Main_M4_D_0-parent').find_all_matches('**/+GeomNode'):
        mat = gnp.get_mat(viewmodel.rig)
        node = gnp.node()
        for i in range(node.get_num_geoms()):
            rd = GeomVertexReader(node.get_geom(i).get_vertex_data(), 'vertex')
            while not rd.is_at_end():
                p_rig = mat.xform_point(rd.get_data3())
                pts.append((p_rig, rest.xform_point(p_rig)))
    return pts


def project_px(point):
    """Điểm trong hệ camera súng -> pixel so với tâm màn hình (x phải, y lên)."""
    out = Point2()
    viewmodel.lens.project(Point3(*point), out)
    w, h = window.size
    return out.x * w / 2, out.y * h / 2


def oscillation(timed):
    """timed = [(t, giá trị)]. Trả về (tần số Hz, biên độ nửa đỉnh-đỉnh). Tần số = (số chu kỳ) / (khoảng giữa lần cắt lên
    qua trung bình đầu và cuối), cắt nội suy giữa hai khung nên không lệch ±1 chu kỳ ở cửa sổ ngắn."""
    mean = sum(v for _, v in timed) / len(timed)
    crossings = []
    for (t0, v0), (t1, v1) in zip(timed, timed[1:]):
        if v0 - mean < 0 <= v1 - mean:
            crossings.append(t0 + (t1 - t0) * (mean - v0) / (v1 - v0))
    vals = [v - mean for _, v in timed]
    freq = (len(crossings) - 1) / (crossings[-1] - crossings[0]) if len(crossings) > 1 else 0.0
    return freq, (max(vals) - min(vals)) / 2


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

    def until(self, cond, timeout=3.0):
        """Chờ tới khi cond() đúng; trả về số giây của game đã trôi (hoặc None nếu quá hạn)."""
        t = 0.0
        while not cond() and t < timeout:
            yield
            t += min(time.dt, 0.05)
        return t if cond() else None

    def sample(self, seconds, getter):
        """Lấy giá trị `getter()` mỗi khung trong `seconds` giây của game."""
        out = []
        t = 0.0
        while t < seconds:
            yield
            t += min(time.dt, 0.05)
            out.append(getter())
        return out

    def sample_timed(self, seconds, getter):
        """Như sample, nhưng trả về [(giây của game kể từ lúc bắt đầu, giá trị)]."""
        out = []
        t = 0.0
        while t < seconds:
            yield
            t += min(time.dt, 0.05)
            out.append((t, getter()))
        return out

    def flick(self, rate, seconds, axis=0, after=1.0, shot_name=None):
        """Quay chuột đều `rate` độ/s (độ nhìn thực, đã bù độ nhạy ADS) trong `seconds`, rồi dừng; ghi tư thế sway mỗi khung
        trong `seconds + after`. Trả [(giây, tư thế sway)]. Có `shot_name` thì chụp ảnh đúng lúc súng bị bỏ lại xa nhất (yaw)."""
        sens = pp.mouse_sensitivity * (1.0 + (pp.ads_look_multiplier - 1.0) * (player.ads_amount * player.ads_amount * (3 - 2 * player.ads_amount)))
        rec, t, low, shot_done = [], 0.0, 0.0, shot_name is None
        while t < seconds + after:
            dt = min(time.dt, 0.05)
            if t < seconds:
                v = rate * dt / sens
                player.look(v if axis == 0 else 0.0, v if axis == 1 else 0.0)
            yield
            t += dt
            pose = sway_pose()
            rec.append((t, pose))
            low = min(low, pose[4])
            if not shot_done and low < -0.8 and pose[4] > low + 0.05:
                shot(shot_name)
                shot_done = True
        return rec

    def reset_state(self, auto=True, mag=30):
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
        combat.bullets.clear()
        combat.pressed = False
        combat.weapon.auto = auto
        combat.weapon.mag = mag
        combat.weapon.reserve = 150
        combat.weapon.cooldown = 0.0

    def run(self):
        yield from self.wait(0.6)
        frame_dts.clear()
        frame_phase.clear()

        # --- A. ADS: thời gian, FOV, tốc độ, độ nhạy ---
        phase['name'] = 'ADS'
        self.reset_state()
        yield from self.wait(0.3)
        check('hông: FOV thế giới (độ)', round(camera.fov, 2), pp.fov, abs(camera.fov - pp.fov) < 0.01)
        held_keys['right mouse'] = 1
        t_in = yield from self.until(lambda: player.ads_amount >= 1.0)
        check('thời gian vào ADS (s)', None if t_in is None else round(t_in, 3), f'{gun.ads_time} +-0.05',
              t_in is not None and abs(t_in - gun.ads_time) < 0.05)
        yield from self.wait(0.1)
        check('ADS hẳn: FOV thế giới hạ (độ)', round(camera.fov, 2), gun.ads_fov, abs(camera.fov - gun.ads_fov) < 0.01)
        yaw0 = player.yaw
        player.look(0.1, 0.0)
        check('ADS hẳn: chuột chậm lại (độ quay khi chuột đi 0,1)', round(player.yaw - yaw0, 3),
              round(0.1 * pp.mouse_sensitivity * pp.ads_look_multiplier, 3),
              abs((player.yaw - yaw0) - 0.1 * pp.mouse_sensitivity * pp.ads_look_multiplier) < 0.01)
        held_keys['right mouse'] = 0
        t_out = yield from self.until(lambda: player.ads_amount <= 0.0)
        check('thời gian ra khỏi ADS (s)', None if t_out is None else round(t_out, 3), f'{gun.ads_time} +-0.05',
              t_out is not None and abs(t_out - gun.ads_time) < 0.05)
        yield from self.wait(0.1)
        check('hông lại: FOV về (độ)', round(camera.fov, 2), pp.fov, abs(camera.fov - pp.fov) < 0.01)
        yaw0 = player.yaw
        player.look(0.1, 0.0)
        check('hông lại: độ nhạy chuột về (độ quay khi chuột đi 0,1)', round(player.yaw - yaw0, 3), round(0.1 * pp.mouse_sensitivity, 3),
              abs((player.yaw - yaw0) - 0.1 * pp.mouse_sensitivity) < 0.01)

        # nửa chừng: FOV nằm giữa
        player.look(-0.1, 0.0)
        held_keys['right mouse'] = 1
        yield from self.until(lambda: player.ads_amount >= 0.5)
        check('đang vào ADS: FOV nằm giữa hông và ngắm', round(camera.fov, 1), f'({gun.ads_fov}, {pp.fov})',
              gun.ads_fov < camera.fov < pp.fov)
        yield from self.wait(0.4)

        # tốc độ đi khi ngắm
        held_keys['w'] = 1
        yield from self.wait(1.0)
        check('ADS: tốc độ đi (m/s)', round(player.speed, 2), round(pp.walk_speed * pp.ads_speed_multiplier, 2),
              abs(player.speed - pp.walk_speed * pp.ads_speed_multiplier) < 0.1)
        held_keys['right mouse'] = 0
        yield from self.wait(0.8)
        check('thả ngắm: tốc độ đi về (m/s)', round(player.speed, 2), pp.walk_speed, abs(player.speed - pp.walk_speed) < 0.1)

        # ngắm cắt chạy nước rút
        held_keys['shift'] = 1
        yield from self.wait(0.6)
        check('đang chạy nước rút', player.state.value, 'sprint', player.state is S.SPRINT)
        held_keys['right mouse'] = 1
        yield from self.wait(0.4)
        check('bấm ngắm khi đang chạy: thôi chạy', player.state.value, 'walk', player.state is S.WALK)
        held_keys['right mouse'] = 0
        held_keys['w'] = held_keys['shift'] = 0

        # --- B. đường ngắm trùng tâm màn hình (phép chiếu thật) ---
        phase['name'] = 'căn đường ngắm'
        self.reset_state()
        pts = gather_sight_points()

        def sights():
            m = viewmodel.rig.get_mat(viewmodel.cam_np)
            ring = [m.xform_point(r) for r, rest in pts if 0.14 <= rest[2] <= 0.17 and rest[1] >= -0.0135]
            post = [m.xform_point(r) for r, rest in pts if 0.55 <= rest[2] <= 0.58 and rest[1] >= -0.0095 and abs(rest[0] - 0.0678) < 0.0015]
            lo = [min(p[i] for p in ring) for i in range(3)]
            hi = [max(p[i] for p in ring) for i in range(3)]
            ring_c = tuple((lo[i] + hi[i]) / 2 for i in range(3))
            tip = max(post, key=lambda p: p[1])
            return ring_c, tuple(tip)

        yield from self.wait(0.3)                          # để viewmodel rời tư thế của phần trước (reset không chạy khung nào)
        ring_c, tip = sights()
        rx, ry = project_px(ring_c)
        check('hông: vòng ngắm sau lệch phải so với tâm (px)', f'{rx:.0f}, {ry:.0f}', '> 100', rx > 100)
        held_keys['right mouse'] = 1
        yield from self.wait(0.7)
        ring_c, tip = sights()
        rx, ry = project_px(ring_c)
        tx, ty = project_px(tip)
        check('ADS: tâm vòng ngắm sau trùng tâm màn hình (px)', f'{rx:.1f}, {ry:.1f}', '< 6', math.hypot(rx, ry) < 6)
        check('ADS: đỉnh cột ngắm trước trùng tâm màn hình (px)', f'{tx:.1f}, {ty:.1f}', '< 6', math.hypot(tx, ty) < 6)
        check('ADS: vòng sau cách mắt (m)', round(ring_c[2], 3), gun.ads_eye_relief, abs(ring_c[2] - gun.ads_eye_relief) < 0.01)
        shot('ads', crop=(440, 240, 840, 480))
        held_keys['right mouse'] = 0
        yield from self.wait(0.5)

        # --- C. sway: thở ---
        phase['name'] = 'thở'
        self.reset_state()
        yield from self.wait(0.5)
        xs = yield from self.sample(5.0, lambda: sway_pose()[0])
        ptp = max(xs) - min(xs)
        check('thở khi đứng: biên độ ngang (mm, đỉnh-đỉnh)', round(ptp * 1000, 2), f'{2 * sw.breath_x * 1000:.2f} +-15%',
              abs(ptp - 2 * sw.breath_x) < 0.15 * 2 * sw.breath_x)
        held_keys['right mouse'] = 1
        yield from self.wait(0.6)
        xs_ads = yield from self.sample(5.0, lambda: sway_pose()[0])
        ptp_ads = max(xs_ads) - min(xs_ads)
        check('ADS: thở còn ~20%', round(ptp_ads / ptp, 3), f'{sw.ads_multiplier} +-0.05', abs(ptp_ads / ptp - sw.ads_multiplier) < 0.05)
        held_keys['right mouse'] = 0
        yield from self.wait(0.4)

        # --- D. bob theo bước chân ---
        phase['name'] = 'bob'
        bob = {}
        for name, keys, state, speed in (('đi', ['w'], S.WALK, pp.walk_speed), ('chạy', ['w', 'shift'], S.SPRINT, pp.sprint_speed),
                                         ('đi ngồi', ['w', 'control'], S.CROUCH_WALK, pp.crouch_speed)):
            self.reset_state()
            for k in keys:
                held_keys[k] = 1
            yield from self.wait(1.2)
            ys = yield from self.sample_timed(4.0, lambda: sway_pose()[1])
            freq, amp = oscillation(ys)
            bob[name] = (freq, amp)
            rate = sw.bob_sprint_rate if state is S.SPRINT else sw.bob_rate
            expect = 2 * speed * rate / sw.bob_stride
            check(f'bob khi {name}: nhịp (lần/s) theo quãng đường', round(freq, 2), f'{expect:.2f} +-10%', abs(freq - expect) < 0.1 * expect)
            for k in keys:
                held_keys[k] = 0
            yield from self.wait(0.3)
        check('bob chạy mạnh hơn đi', round(bob['chạy'][1] / bob['đi'][1], 2), f'~{sw.bob_sprint_multiplier}',
              abs(bob['chạy'][1] / bob['đi'][1] - sw.bob_sprint_multiplier) < 0.35)
        check('bob ngồi đi nhẹ hơn đi', round(bob['đi ngồi'][1] / bob['đi'][1], 2), f'~{sw.bob_crouch_multiplier}',
              abs(bob['đi ngồi'][1] / bob['đi'][1] - sw.bob_crouch_multiplier) < 0.2)
        self.reset_state()
        held_keys['w'] = 1
        yield from self.wait(1.0)
        held_keys['w'] = 0
        yield from self.wait(0.8)
        ys = yield from self.sample(1.0, lambda: sway_pose()[1])
        check('dừng đi: bob tắt hẳn', round((max(ys) - min(ys)) * 1000, 2), f'< {sw.breath_y * 2 * 1000 * 1.2:.1f} mm (còn mỗi thở)',
              (max(ys) - min(ys)) < sw.breath_y * 2 * 1.2)
        self.reset_state()
        held_keys['w'] = 1
        yield from self.wait(1.2)
        shot('walk')
        held_keys['w'] = 0

        # --- E. lag theo chuột (MouseLag: hệ bậc hai theo vận tốc quay, nén mềm) ---
        phase['name'] = 'lag chuột'
        self.reset_state()
        yield from self.wait(0.8)
        rec = yield from self.flick(240, 0.15, after=1.0)               # 36 độ trong 0,15 s: cú flick vừa
        yaws, pitches, rolls = ([p[i] for _, p in rec] for i in (4, 3, 5))
        peak = -min(yaws)
        check('flick phải 240 độ/s: súng bị bỏ lại bên trái (độ)', round(peak, 2), f'4.5 .. {sw.lag_max * 1.4:.1f}', 4.5 <= peak <= sw.lag_max * 1.4)
        check('  kèm nghiêng trái cùng chiều (độ)', round(min(rolls), 2), f'~{-peak * sw.lag_roll:.2f}', min(rolls) < -peak * sw.lag_roll * 0.7)
        t_peak = min(rec, key=lambda r: r[1][4])[0]
        over = max(yaws)
        check('  dừng chuột: quá đà sang phải rồi lắc về (độ)', round(over, 2), f'{0.04 * peak:.2f} .. {0.3 * peak:.2f}', 0.04 * peak <= over <= 0.3 * peak)
        t_settle = max((t for t, p in rec if abs(p[4]) > max(0.1 * peak, 0.05)), default=0.0) - 0.15
        check('  ổn định sau khi dừng chuột (s)', round(t_settle, 2), '<= 0.5', t_settle <= 0.5)
        check('  rồi súng về giữa (độ)', round(yaws[-1], 3), '< 0.15', abs(yaws[-1]) < 0.15)
        rec2 = yield from self.flick(60, 1.0, after=0.6)                # xoay chậm 60 độ/s
        peak2 = -min(p[4] for _, p in rec2)
        check('xoay chậm 60 độ/s: súng lệch nhẹ (độ)', round(peak2, 2), f'1 .. {peak * 0.6:.1f}', 1.0 <= peak2 <= peak * 0.6)
        rec3 = yield from self.flick(10, 1.0, after=0.6)                # rà tâm chậm 10 độ/s
        peak3 = -min(p[4] for _, p in rec3)
        check('rà tâm chậm 10 độ/s: gần như không lệch (độ)', round(peak3, 3), '< 0.25', peak3 < 0.25)
        rec4 = yield from self.flick(240, 0.15, axis=1, after=1.0)      # ngẩng lên
        check('ngẩng lên: súng trễ xuống (độ)', round(min(p[3] for _, p in rec4), 2), '< -2', min(p[3] for _, p in rec4) < -2.0)
        check('  kèm dịch xuống (m)', round(min(p[1] for _, p in rec4), 4), '< -0.003', min(p[1] for _, p in rec4) < -0.003)
        player.yaw, player.pitch = 0.0, 0.0                               # các cú flick đã xoay camera: về hướng thẳng cho ảnh chụp
        player._apply_view()
        yield from self.wait(0.3)
        # ảnh ở đỉnh một cú flick mạnh (hông), rồi lúc ngắm
        yield from self.flick(600, 0.1, after=0.8, shot_name='sway_hip')
        held_keys['right mouse'] = 1
        yield from self.until(lambda: player.ads_amount >= 1.0)
        yield from self.wait(0.4)
        rec5 = yield from self.flick(240, 0.15, after=1.0)
        peak5 = -min(p[4] for _, p in rec5)
        check('ngắm (ADS): lệch còn ~20% (độ)', round(peak5, 2), f'{peak * sw.ads_multiplier:.2f} +-30%', abs(peak5 - peak * sw.ads_multiplier) < 0.3 * peak * sw.ads_multiplier)
        yield from self.flick(600, 0.1, after=0.8, shot_name='sway_ads')
        held_keys['right mouse'] = 0
        yield from self.wait(0.5)

        # --- F. nhảy, chạm đất, ngồi ---
        phase['name'] = 'nhảy/ngồi'
        self.reset_state()
        yield from self.wait(0.5)
        track = {'landed': 0.0, 'dip': 0.0, 'y_low': 0.0, 'y_high': 0.0}

        def watch():
            track['landed'] = max(track['landed'], player.landed)
            track['dip'] = min(track['dip'], player.camera_pivot.y - player.eye_height)
            track['y_low'] = min(track['y_low'], sway_pose()[1])
            track['y_high'] = max(track['y_high'], sway_pose()[1])

        held_keys['space'] = 1
        yield
        yield
        held_keys['space'] = 0
        yield from self.sample(1.6, watch)
        check('chạm đất: tốc độ rơi (m/s)', round(track['landed'], 2), f'~{pp.jump_speed}', abs(track['landed'] - pp.jump_speed) < 0.6)
        check('chạm đất: camera nhún xuống (m)', round(track['dip'], 4), f'~{-pp.land_dip_per_speed * pp.jump_speed:.3f}',
              track['dip'] < -0.015 and track['dip'] > -0.08)
        check('nhảy/rơi: súng lệch theo quán tính, có giới hạn (m)', f'{track["y_low"]:.4f} .. {track["y_high"]:.4f}', '',
              track['y_low'] < -0.004 and track['y_low'] > -(sw.vlag_max + abs(sw.land_peak[1]) * 2 + 0.02))
        yield from self.wait(0.8)
        check('rồi camera về chỗ cũ (m)', round(player.camera_pivot.y - player.eye_height, 4), 0,
              abs(player.camera_pivot.y - player.eye_height) < 0.002)
        check('hạ cánh đứng trên đất', player.on_ground and player.state is S.IDLE, True, player.on_ground and player.state is S.IDLE)

        track.update(y_low=0.0, y_high=0.0)
        held_keys['control'] = 1
        yield from self.sample(0.5, watch)
        check('ngồi xuống: súng trễ lên theo quán tính (m)', round(track['y_high'], 4), '> 0.002', track['y_high'] > 0.002)
        check('ngồi xuống: mắt hạ (m)', round(player.eye_height, 3), pp.eye_height_crouch, abs(player.eye_height - pp.eye_height_crouch) < 1e-6)
        shot('crouch')
        track.update(y_low=0.0, y_high=0.0)
        held_keys['control'] = 0
        yield from self.sample(0.5, watch)
        check('đứng lên: súng trễ xuống theo quán tính (m)', round(track['y_low'], 4), '< -0.002', track['y_low'] < -0.002)
        yield from self.wait(0.6)

        # --- G. chạy nước rút: tư thế ---
        phase['name'] = 'chạy'
        self.reset_state()
        held_keys['w'] = held_keys['shift'] = 1
        t_sprint = yield from self.until(lambda: player.sprint_amount >= 1.0)
        check('vào tư thế chạy (s)', None if t_sprint is None else round(t_sprint, 3), f'{gun.sprint_in_time} +-0.06',
              t_sprint is not None and abs(t_sprint - gun.sprint_in_time) < 0.06)
        yield from self.wait(0.5)
        pose = sway_pose()
        check('chạy: súng hạ xuống (m)', round(pose[1], 3), f'~{sw.sprint_pose[1]}', pose[1] < sw.sprint_pose[1] * 0.25)
        check('chạy: nòng chúc xuống và chếch trái (độ)', f'{pose[3]:.1f}, {pose[4]:.1f}', f'< 0, < 0', pose[3] < -2 and pose[4] < -8)
        shot('sprint')
        held_keys['w'] = held_keys['shift'] = 0
        yield from self.wait(0.5)

        # --- H. sprint-to-fire ---
        phase['name'] = 'sprint-to-fire'

        def first_shot_delay(label, auto=True, press_event=False, timeout=1.0):
            self.reset_state(auto=auto)
            held_keys['w'] = held_keys['shift'] = 1
            yield from self.until(lambda: player.sprint_amount >= 1.0)
            yield from self.wait(0.3)
            fired0 = combat.shots_fired
            held_keys['left mouse'] = 1
            if press_event:
                combat.pressed = True
            t = yield from self.until(lambda: combat.shots_fired > fired0, timeout)
            state_at_shot = player.state
            held_keys['left mouse'] = 0
            held_keys['w'] = held_keys['shift'] = 0
            return t, state_at_shot, combat.shots_fired - fired0

        t, state, n = yield from first_shot_delay('tự động')
        check('bóp cò khi đang chạy: phát đầu trễ (s)', None if t is None else round(t, 3), f'{gun.sprint_out_time} +-0.07',
              t is not None and abs(t - gun.sprint_out_time) < 0.07)
        check('  lúc bắn đã thôi chạy (đi bộ)', state.value, 'walk', state is S.WALK)
        yield from self.wait(0.6)
        t, state, n = yield from first_shot_delay('bắn đơn', auto=False, press_event=True)
        check('bắn đơn: cú bóp lúc đang chạy không mất, bắn sau ~0,25 s (s)', None if t is None else round(t, 3),
              f'{gun.sprint_out_time} +-0.07', t is not None and abs(t - gun.sprint_out_time) < 0.07)
        yield from self.wait(0.5)
        check('  và chỉ một phát (đạn còn lại)', combat.weapon.mag, 29, combat.weapon.mag == 29)

        # đứng yên: bắn tức thì
        self.reset_state()
        yield from self.wait(0.3)
        fired0 = combat.shots_fired
        held_keys['left mouse'] = 1
        t = yield from self.until(lambda: combat.shots_fired > fired0, 0.5)
        held_keys['left mouse'] = 0
        check('đứng yên: bóp cò là bắn ngay (s)', None if t is None else round(t, 3), '< 0.05', t is not None and t < 0.05)

        # cho phép bắn từ tư thế chạy (tuỳ chọn)
        pp.sprint_blocks_fire = False
        t, state, n = yield from first_shot_delay('không chặn')
        pp.sprint_blocks_fire = True
        check('sprint_blocks_fire = False: bắn ngay từ tư thế chạy (s)', None if t is None else round(t, 3), '< 0.05', t is not None and t < 0.05)
        check('  vẫn đang chạy lúc bắn', state.value, 'sprint', state is S.SPRINT)
        yield from self.wait(0.6)

        # thả cò mà còn giữ Shift + W thì chạy lại
        self.reset_state()
        held_keys['w'] = held_keys['shift'] = 1
        yield from self.until(lambda: player.sprint_amount >= 1.0)
        fired_before = combat.shots_fired
        held_keys['left mouse'] = 1
        yield from self.until(lambda: combat.shots_fired > fired_before)
        yield from self.wait(0.2)
        held_keys['left mouse'] = 0
        t_back = yield from self.until(lambda: player.sprint_amount >= 1.0, 1.0)
        check('thả cò, còn giữ Shift + W: chạy lại', None if t_back is None else round(t_back, 3), '< 0.6',
              t_back is not None and t_back < 0.6)
        held_keys['w'] = held_keys['shift'] = 0
        yield from self.wait(0.5)

        # --- I. bắn khi đang vào ADS: độ tản theo mức ADS hiện tại ---
        phase['name'] = 'bắn lúc vào ADS'
        self.reset_state(auto=False)
        held_keys['right mouse'] = 1
        yield from self.until(lambda: player.ads_amount >= 0.4)
        fired_before = combat.shots_fired
        combat.pressed = True
        held_keys['left mouse'] = 1
        yield
        held_keys['left mouse'] = 0
        check('phát bắn lúc đang vào ADS: có bắn', combat.shots_fired - fired_before, 1, combat.shots_fired - fired_before == 1)
        ads_at_shot = player.ads_amount
        spread = combat.last_shot.spread
        expect = combat.accuracy.base(S.IDLE, ads_at_shot)
        check('phát bắn lúc đang vào ADS: tản theo mức hiện tại (độ)', round(spread, 3), f'{expect:.2f} +-0.15 (ADS {ads_at_shot:.2f})',
              abs(spread - expect) < 0.15 and gun.accuracy.ads < spread < gun.accuracy.stand)
        held_keys['right mouse'] = 0
        yield from self.wait(0.5)

        # --- J. cảnh tổng hợp ---
        phase['name'] = 'xong'
        self.reset_state()
        yield from self.wait(0.3)
        pose = sway_pose()
        check('hông, đứng: súng nằm gần chỗ cũ (mm, độ)', f'{max(abs(c) for c in pose[:3]) * 1000:.1f} mm, {max(abs(c) for c in pose[3:]):.2f} độ',
              '< 4 mm, < 0.5', max(abs(c) for c in pose[:3]) < 0.004 and max(abs(c) for c in pose[3:]) < 0.5)
        shot('hip')


def report():
    print('\n=== KIỂM TRA G4 ===')
    print(f"{'mục':68s} {'đo được':>22s} {'mong đợi':>26s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:68s} {str(got):>22s} {str(expected):>26s}  {"ĐẠT" if ok else "TRƯỢT"}')
    # loại phần tự làm chậm khung: quét hàng nghìn đỉnh để căn đường ngắm
    pairs = [(dt, ph) for dt, ph in zip(frame_dts, frame_phase) if ph != 'căn đường ngắm']
    dts = sorted(dt for dt, _ in pairs)
    n = len(dts)
    avg = n / sum(dts)
    low1 = 1 / dts[int(n * 0.99)]
    print(f'\nFPS (vsync tắt, 1280x720, toàn bộ kịch bản): {n} khung, trung bình {avg:.0f}, 1% thấp nhất {low1:.0f}, '
          f'khung chậm nhất {dts[-1] * 1000:.0f} ms')
    worst = sorted(pairs, reverse=True)[:5]
    print('khung chậm nhất: ' + ', '.join(f'{dt * 1000:.0f} ms ({ph})' for dt, ph in worst))
    results.append(('FPS trung bình >= 60', round(avg), '>= 60', avg >= 60))
    print(f'{sum(r[3] for r in results)}/{len(results)} mục đạt')


Script()
game.app.run()
