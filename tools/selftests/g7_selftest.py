"""G7: Bodycam style with the real game (driven via held_keys, measured, screenshots): bullets follow the barrel, random kick, gun drift, no HUD, lighting with correct logic (reads the real pixels),
lens, exposure, cost does not grow with the number of bullet holes, borderless fullscreen window.

Run: .venv\\Scripts\\python.exe -X utf8 tools\\with_game_lock.py .venv\\Scripts\\python.exe -X utf8 tools\\selftests\\g7_selftest.py
"""
import math
import statistics
import subprocess
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename, PNMImage, Point2, Point3  # noqa: E402
from ursina import Entity, Text, application, camera, held_keys, mouse, scene, window  # noqa: E402

from fps.app import desktop_size  # noqa: E402
from fps.core.freeaim import barrel_view_dir, view_to_world  # noqa: E402
from fps.core.movement import aim_direction  # noqa: E402
from fps.core.spread import angle_between  # noqa: E402

game = create_game(vsync=False, size=(1280, 720), sound=False, draw=False, moving_targets=False)
player, combat, viewmodel, light, lens = game.player, game.combat, game.viewmodel, game.light, game.lens
gun, look, lens_data = game.params.gun, game.params.look, game.params.lens
mouse.locked = False
combat.require_locked_mouse = False
combat.rng.seed(20240131)
results = []
shots = []
_orig_fire = combat._fire


def _logged_fire(origin, direction, age):
    shots.append((origin, direction))
    return _orig_fire(origin, direction, age)


combat._fire = _logged_fire
_orig_source = combat.aim_source
at_shot = {}                  # captured right when the bullet direction is taken, before this shot kicks the gun and camera


def _source():
    at_shot['barrel'] = barrel_screen()
    at_shot['view'] = aim_direction(player.yaw, player.pitch)
    at_shot['yaw_pitch'] = (player.yaw, player.pitch)
    return _orig_source()


combat.aim_source = _source


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def place(pos=(0, 0, 0), yaw=0.0, pitch=0.0):
    player.position = pos
    player.yaw, player.pitch = yaw, pitch
    player.vx = player.vz = player.vy = 0.0
    player.on_ground = True
    player._apply_view()
    player.free_look.reset()
    player.free_look.scale = 1.0
    for k in ('w', 'a', 's', 'd', 'shift', 'control', 'space', 'left mouse', 'right mouse'):
        held_keys[k] = 0


def calm_drift():
    combat.free_aim.spring.x = [0.0, 0.0]
    combat.free_aim.spring.v = [0.0, 0.0]


def grab() -> PNMImage:
    img = PNMImage()
    application.base.win.get_screenshot(img)
    return img


def lum(img, x, y) -> float:
    c = img.get_xel(x, y)
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def mean_rect(img, x0, y0, x1, y1, step=3) -> float:
    w, h = img.get_x_size(), img.get_y_size()
    vals = [lum(img, int(x * (w - 1)), int(y * (h - 1))) for x in frange(x0, x1, step / w) for y in frange(y0, y1, step / h)]
    return sum(vals) / len(vals)


def frange(a, b, step):
    v = a
    while v < b:
        yield v
        v += step


def snap(name):
    application.base.win.save_screenshot(Filename.from_os_specific(str(ROOT / 'shots' / f'g7_{name}.png')))


def gun_pixels(with_gun: PNMImage, without: PNMImage) -> list:
    """Pixels that contain the gun: the two images (gun shown / gun hidden) differ there."""
    w, h = with_gun.get_x_size(), with_gun.get_y_size()
    return [(x, y) for x in range(0, w, 3) for y in range(h // 3, h, 3) if abs(lum(with_gun, x, y) - lum(without, x, y)) > 0.03]


def barrel_screen() -> tuple:
    """Convergence point of the barrel axis on screen, computed through the GUN's lens, in NDC units."""
    x, y, z = barrel_view_dir(viewmodel.barrel_pose, gun.ads_sights, 90.0, 90.0)      # real direction of the barrel
    k = math.tan(math.radians(viewmodel.current_fov) / 2)
    return x / z / k, y / z / k * window.aspect_ratio


def world_to_screen(direction: tuple, yaw_pitch: tuple = None) -> tuple:
    """World direction -> NDC through the world lens, using the player's view angle (no shake)."""
    yaw, pitch = yaw_pitch or (player.yaw, player.pitch)
    f = aim_direction(yaw, pitch)
    r = view_to_world(yaw, pitch, (1.0, 0.0, 0.0))
    u = view_to_world(yaw, pitch, (0.0, 1.0, 0.0))
    dz = sum(a * b for a, b in zip(direction, f))
    dx = sum(a * b for a, b in zip(direction, r))
    dy = sum(a * b for a, b in zip(direction, u))
    k = math.tan(math.radians(camera.fov) / 2)
    return dx / dz / k, dy / dz / k * window.aspect_ratio


def muzzle_ndc():
    """Muzzle on screen: the gun tip must stay inside the frame (the gun body extending past the bottom edge is normal)."""
    out = Point2()
    viewmodel.lens.project(Point3(game.fx.flash.muzzle.get_pos(viewmodel.cam_np)), out)
    return out.x, out.y


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

    def wait(self, n):
        for _ in range(n):
            yield

    def burst(self, mag=30):
        combat.weapon.mag = mag
        combat.weapon.cooldown = 0.0
        shots.clear()
        held_keys['left mouse'] = 1
        while combat.weapon.mag > 0:
            yield
        held_keys['left mouse'] = 0

    def run(self):
        yield from self.wait(60)

        # --- A. nothing on screen ---
        check('không có HUD', game.hud, None, game.hud is None)
        texts = [e for e in scene.entities if isinstance(e, Text) and e.enabled]
        check('không có chữ nào trên màn hình khi chơi', len(texts), 0, not texts)
        check('vòng lặp chỉ còn vật có update / input', len(scene.entities), '< 30', len(scene.entities) < 30)

        # --- B. bullets follow the barrel ---
        place()
        yield from self.wait(10)
        calm_drift()
        fa = combat.free_aim
        d = gun.free_aim
        saved_rest = (d.rest_yaw, d.rest_pitch, d.rest_roll, d.rest_pos)
        fa.rest = [0.0, 0.0, 0.0, 2.5, -3.0, 0.0]          # the gun is clearly off: up 2.5 degrees, left 3 degrees
        fa.rest_target = list(fa.rest)
        yield from self.wait(3)
        combat.weapon.mag = 30
        combat.weapon.cooldown = 0.0
        shots.clear()
        combat.pressed = True
        combat.weapon.auto = False
        yield
        yield
        combat.weapon.auto = True
        check('súng lệch thì có phát bắn', len(shots), '>= 1', len(shots) >= 1)
        origin, direction = shots[0]
        bx, by = at_shot['barrel']
        sx, sy = world_to_screen(direction, at_shot['yaw_pitch'])
        px = window.size[0] / 2
        err = math.hypot(sx - bx, (sy - by) / window.aspect_ratio) * px
        check('đạn tới đúng chỗ nòng chỉ trên màn hình (px)', round(err, 1), '< 3', err < 3)      # includes 0.03 degrees of mechanical spread (~0.5 px)
        off = angle_between(at_shot['view'], direction)
        check('đạn KHÔNG ra giữa màn hình khi súng lệch (độ)', round(off, 2), '> 2', off > 2)
        check('súng lệch trái thì đạn sang trái', round(direction[0], 3), '< 0', direction[0] < 0)
        check('súng lệch lên thì đạn lên', round(direction[1], 3), '> 0', direction[1] > 0)
        fa.rest = [0.0] * 6
        fa.rest_target = [0.0] * 6

        # fully aimed: the sight line returns to centre, bullets go to the exact centre (except a very small drift)
        d.rest_yaw, d.rest_pitch, d.rest_roll, d.rest_pos = 0.0, 0.0, 0.0, 0.0
        place()
        held_keys['right mouse'] = 1
        yield from self.wait(45)
        calm_drift()
        yield from self.wait(5)
        check('ngắm hẳn', round(player.ads_amount, 2), 1.0, player.ads_amount >= 1.0)
        check('ngắm: FOV súng đổi', round(viewmodel.current_fov, 1), gun.ads_view_fov, abs(viewmodel.current_fov - gun.ads_view_fov) < 0.2)
        direction = view_to_world(player.yaw, player.pitch, barrel_view_dir(viewmodel.barrel_pose, gun.ads_sights, viewmodel.current_fov, camera.fov))
        off = angle_between(aim_direction(player.yaw, player.pitch), direction)
        check('ngắm: nòng gần đúng giữa màn hình (độ)', round(off, 3), '< 1', off < 1.0)
        # the projected point of the front sight (through the gun lens) must coincide with the projected bullet direction (through the world lens)
        _, front = gun.ads_sights
        node = viewmodel.sway.attach_new_node('front_probe')
        node.set_pos(front[0], front[1], front[2])
        p = node.get_pos(viewmodel.cam_np)
        node.remove_node()
        out = Point2()
        viewmodel.lens.project(Point3(p), out)
        sx, sy = world_to_screen(direction)
        err = math.hypot(out.x - sx, (out.y - sy)) * window.size[0] / 2
        check('ngắm: đầu ruồi trùng điểm đạn tới trên màn hình (px)', round(err, 1), '< 8', err < 8)
        snap('ads')
        held_keys['right mouse'] = 0
        d.rest_yaw, d.rest_pitch, d.rest_roll, d.rest_pos = saved_rest
        yield from self.wait(30)

        # with bullets-follow-barrel off, bullets go to the centre
        d.barrel_aim = False
        place()
        fa.rest = [0.0, 0.0, 0.0, 2.5, -3.0, 0.0]
        fa.rest_target = list(fa.rest)
        yield from self.wait(3)
        combat.weapon.mag = 30
        combat.weapon.cooldown = 0.0
        shots.clear()
        combat.pressed = True
        combat.weapon.auto = False
        yield
        yield
        combat.weapon.auto = True
        off = angle_between(at_shot['view'], shots[0][1])
        check('tắt ở F1: đạn ra giữa màn hình (độ)', round(off, 3), '< 0.05', off < 0.05)
        d.barrel_aim = True
        fa.rest = [0.0] * 6
        fa.rest_target = [0.0] * 6
        yield from self.wait(30)

        # --- C. random kick: two different bursts, gun drifts and camera is pushed ---
        place(pitch=-8.0)
        yield from self.wait(5)
        peak_drift = 0.0
        combat.weapon.mag = 30
        shots.clear()
        pitch0 = player.pitch
        held_keys['left mouse'] = 1
        while combat.weapon.mag > 0:
            yield
            peak_drift = max(peak_drift, combat.free_aim.drift[0])
        held_keys['left mouse'] = 0
        trace_a = [s[1] for s in shots]
        climb = pitch0 - player.pitch
        check('cả loạt: đủ 30 phát', len(trace_a), 30, len(trace_a) == 30)
        check('súng trôi lên khỏi tâm (độ)', round(peak_drift, 2), '> 2', peak_drift > 2)
        check('camera cũng bị đẩy lên (độ)', round(climb, 2), '> 3', climb > 3)
        rise = trace_a[-1][1] - trace_a[0][1]
        check('đạn cuối loạt cao hơn đạn đầu', round(rise, 3), '> 0.05', rise > 0.05)
        yield from self.wait(90)
        check('ngừng bắn: súng về chỗ (độ)', round(combat.free_aim.drift[0], 2), '< 0.3', abs(combat.free_aim.drift[0]) < 0.3)
        place(pitch=-8.0)
        yield from self.wait(5)
        yield from self.burst()
        trace_b = [s[1] for s in shots]
        spread = max(angle_between(a, b) for a, b in zip(trace_a, trace_b))
        check('hai loạt đi khác đường: không có mẫu cố định (độ)', round(spread, 2), '> 0.5', spread > 0.5)
        yield from self.wait(60)
        before = combat.free_aim.rest_changes
        check('ngừng bắn: súng đổi tư thế nghỉ', before, '>= 1', before >= 1)

        # --- D. mouse moves the gun first, the screen turns later ---
        fl = player.free_look
        fa_d = gun.free_aim
        place()
        yield from self.wait(10)
        sens = game.params.player.mouse_sensitivity
        yaw0, pitch0 = player.yaw, player.pitch
        for _ in range(20):
            player.look(4.0 / 20 / sens, 0.0)               # mouse right 4 degrees in total, slowly
            yield
        yield from self.wait(25)                            # wait for the hand to bring the gun into place
        moved = (player.yaw - yaw0 + 180) % 360 - 180
        check('chuột trong vùng: màn hình gần như đứng yên (độ, gồm đầu đuổi theo chậm)', round(moved, 2), '< 0.6', abs(moved) < 0.6)
        check('chuột trong vùng: nòng súng quay theo chuột (độ)', round(viewmodel.barrel_pose[4], 2), '> 3', viewmodel.barrel_pose[4] > 3.0)
        world = (player.yaw + fl.offset[0] - yaw0 + 180) % 360 - 180
        check('hướng súng trong thế giới đúng bằng tổng chuột (độ, gồm nốt phần hồi giật của loạt trước)', round(world, 3), 4.0, abs(world - 4.0) < 0.05)
        snap('free_right')
        for _ in range(20):
            player.look(0.0, 3.0 / 20 / sens)               # mouse up 3 degrees
            yield
        yield from self.wait(25)
        check('chuột lên: nòng ngóc lên, màn hình gần như không ngẩng (độ)', (round(viewmodel.barrel_pose[3], 2), round(player.pitch - pitch0, 2)), '> 2, nhỏ',
              viewmodel.barrel_pose[3] > 2.0 and abs(player.pitch - pitch0) < 0.5)
        # bullets go to where the gun is offset, not to the centre
        combat.weapon.mag = 30
        combat.weapon.cooldown = 0.0
        shots.clear()
        combat.pressed = True
        combat.weapon.auto = False
        yield
        yield
        combat.weapon.auto = True
        off = angle_between(at_shot['view'], shots[0][1])
        check('súng lệch theo chuột thì đạn lệch theo (độ)', round(off, 2), '> 3', off > 3)
        # head catches up: gun keeps its world direction, gun slowly returns to the centre of the frame
        total = (player.yaw + fl.offset[0], player.pitch - fl.offset[1])
        before_off = fl.radius()
        yield from self.wait(180)
        after = (player.yaw + fl.offset[0], player.pitch - fl.offset[1])
        recoil_moved = abs(combat.recoil.burst[0]) + abs(combat.recoil.burst[1])
        check('đầu đuổi theo súng: súng về dần giữa khung', (round(before_off, 2), round(fl.radius(), 2)), 'giảm', fl.radius() < before_off * 0.75)
        check('  nhưng súng giữ nguyên hướng trong thế giới (độ)', round(abs(after[0] - total[0]) + abs(after[1] - total[1]), 2), '< 0.6', abs(after[0] - total[0]) + abs(after[1] - total[1]) < 0.6 + recoil_moved)
        # outside the zone: screen turns, gun stops at the edge
        place()
        yield from self.wait(5)
        yaw0 = player.yaw
        for _ in range(60):
            player.look(1.0 / sens, 0.0)                     # 60 deg/s
            yield
        moved = (player.yaw - yaw0 + 180) % 360 - 180
        world = (player.yaw + fl.offset[0] - yaw0 + 180) % 360 - 180
        check('vượt mép vùng: màn hình quay theo (độ)', round(moved, 1), '> 35', moved > 35)
        check('  súng dừng trong vùng tự do', round(fl.radius(), 3), '<= 1', fl.radius() <= 1.0 + 1e-6)
        check('  không mất cú xoay nào của chuột (độ)', round(world, 2), 60.0, abs(world - 60.0) < 0.5 + (fl.d.recenter_idle * 0))
        before = combat.free_aim.rest_changes
        # very fast turn: the body arrives late, the gun is dragged back opposite the turn even though it is at the edge
        lead_slow = viewmodel.barrel_pose[4]
        rolls, leads = [], []
        for _ in range(20):
            player.look(6.0 / sens, 0.0)                     # 360 deg/s at 60 FPS
            yield
            leads.append(viewmodel.barrel_pose[4])
            rolls.append(camera.rotation_z)
        check('xoay rất nhanh: súng tụt lại so với lúc xoay chậm (độ)', (round(lead_slow, 1), round(min(leads), 1)), 'giảm > 3', lead_slow - min(leads) > 3)
        check('xoay nhanh: camera nghiêng theo (độ)', round(max(rolls), 2), '> 0.3', max(rolls) > 0.3)
        want = aim_direction(player.yaw, player.pitch)
        got = (math.sin(math.radians(player.yaw)) * math.cos(math.radians(player.pitch)), -math.sin(math.radians(player.pitch)),
               math.cos(math.radians(player.yaw)) * math.cos(math.radians(player.pitch)))
        check('rung / nghiêng camera không đổi góc nhìn của người chơi', round(angle_between(want, got), 4), 0, angle_between(want, got) < 1e-6)
        yield from self.wait(90)
        check('dừng xoay: đổi tư thế nghỉ', combat.free_aim.rest_changes, f'> {before}', combat.free_aim.rest_changes > before)
        # aim while the gun is offset: the sight moves toward the centre, the aim point in the world does not jump
        place()
        yield from self.wait(5)
        for _ in range(20):
            player.look(8.0 / 20 / sens, 0.0)
            yield
        yield from self.wait(25)
        aim_world = player.yaw + fl.offset[0]
        off_hip = fl.offset[0]
        held_keys['right mouse'] = 1
        yield from self.wait(120)
        check('ngắm: súng về gần giữa khung (độ lệch)', (round(off_hip, 2), round(fl.offset[0], 2)), f'<= {fa_d.zone_yaw * fa_d.zone_ads:.1f}', abs(fl.offset[0]) <= fa_d.zone_yaw * fa_d.zone_ads + 0.05)
        check('  điểm ngắm trong thế giới không nhảy (độ)', round(player.yaw + fl.offset[0] - aim_world, 3), '< 0.05', abs(player.yaw + fl.offset[0] - aim_world) < 0.05)
        held_keys['right mouse'] = 0
        yield from self.wait(30)
        # off in F1: mouse turns the screen directly
        place()
        fa_d.barrel_aim = False
        yield from self.wait(30)
        yaw0 = player.yaw
        player.look(2.0 / sens, 0.0)
        check('tắt ở F1: chuột quay thẳng màn hình (độ)', round(player.yaw - yaw0, 3), 2.0, abs(player.yaw - yaw0 - 2.0) < 1e-3)
        fa_d.barrel_aim = True
        place()
        yield from self.wait(30)

        # --- E. gun stays in frame in every pose ---
        place()
        yield from self.wait(30)
        x, y = muzzle_ndc()
        check('hông: đầu súng trong khung, nửa dưới (NDC)', (round(x, 2), round(y, 2)), '|x|<1, -1<y<0', abs(x) < 1 and -1 < y < 0)
        snap('hip')
        place((0, 0, 30))
        held_keys['w'], held_keys['shift'] = 1, 1
        yield from self.wait(40)
        x2, y2 = muzzle_ndc()
        check('chạy: đầu súng còn trong khung (NDC)', (round(x2, 2), round(y2, 2)), '|x|<1, y>-1', abs(x2) < 1 and y2 > -1)
        check('chạy: đầu súng hạ thấp hơn lúc thường', round(y2 - y, 2), '< 0', y2 < y)
        snap('sprint')
        place()
        yield from self.wait(30)

        # --- F. lighting with correct logic: read real pixels. Noise, flare and auto-exposure off so the comparison is valid ---
        saved = (lens_data.noise, lens_data.bloom, lens_data.auto_exposure)
        lens_data.noise, lens_data.bloom, lens_data.auto_exposure = 0.0, 0.0, 0.0
        lens.apply_params()
        game.exposure.value = None
        z_lamp = look.lamp_z0 + 3 * look.lamp_spacing
        fa.rest = [0.0] * 6
        fa.rest_target = [0.0] * 6

        # which screen spots are the gun: measured once under the lamp (gun clearly visible), then the same points are read in both places. The gun stays still on screen because shake and drift are off.
        place((0.0, 0.0, z_lamp - 0.8))
        yield from self.wait(8)
        a = grab()
        viewmodel.actor.hide()
        yield from self.wait(3)
        b = grab()
        viewmodel.actor.show()
        mask = gun_pixels(a, b)
        check(f'đo được súng ({len(mask)} điểm)', len(mask), '> 500', len(mask) > 500)
        under_lamp = sum(lum(a, x, y) for x, y in mask) / len(mask)
        place((10.5, 0.0, z_lamp + 5.0))
        yield from self.wait(8)
        c = grab()
        in_gap = sum(lum(c, x, y) for x, y in mask) / len(mask)
        ratio = under_lamp / max(in_gap, 1e-4)
        check('súng sáng hơn khi đứng dưới đèn, tối đi ở khoảng tối (lần)', (round(under_lamp, 3), round(in_gap, 3), round(ratio, 1)), '> 1.8', ratio > 1.8)
        # a lamp on the right makes the right half of the gun brighter, a lamp on the left the opposite: the lamp is fixed to the room, not to the camera (old bug: the gun looked identical everywhere)
        mid = sorted(x for x, _ in mask)[len(mask) // 2]
        left_px, right_px = [p for p in mask if p[0] < mid], [p for p in mask if p[0] >= mid]

        def side_ratio(img):
            return (sum(lum(img, x, y) for x, y in right_px) / len(right_px)) / max(sum(lum(img, x, y) for x, y in left_px) / len(left_px), 1e-4)
        place((-2.6, 0.0, z_lamp), 0.0, 0.0)                 # lamp to the player's right
        yield from self.wait(8)
        lamp_right = side_ratio(grab())
        place((2.6, 0.0, z_lamp), 0.0, 0.0)                  # lamp to the left
        yield from self.wait(8)
        lamp_left = side_ratio(grab())
        check('đèn đổi bên thì mặt sáng của súng đổi bên (phải / trái)', (round(lamp_right, 3), round(lamp_left, 3)), 'đèn phải > đèn trái x 1,05', lamp_right > lamp_left * 1.05)

        # floor under the lamp is much brighter than the floor in the dark area
        place((0.0, 0.0, z_lamp - 6.0))
        yield from self.wait(5)
        viewmodel.actor.hide()
        player.pitch = 40.0
        player._apply_view()
        yield from self.wait(5)
        pool = mean_rect(grab(), 0.45, 0.45, 0.55, 0.55)
        place((0.0, 0.0, z_lamp - 5.0 + look.lamp_spacing * 0.0), 0.0, 90.0)
        player.z = z_lamp + 5.0
        player._apply_view()
        yield from self.wait(5)
        gap = mean_rect(grab(), 0.45, 0.45, 0.55, 0.55)
        place((0.0, 0.0, z_lamp), 0.0, 89.0)
        yield from self.wait(5)
        under = mean_rect(grab(), 0.45, 0.45, 0.55, 0.55)
        check('sàn dưới đèn sáng hơn sàn giữa hai đèn (lần)', round(under / max(gap, 1e-4), 2), '> 1.5', under > 1.5 * gap)

        # the brightest lamp in the frame
        place((0.0, 0.0, z_lamp - 3.5), 0.0, -math.degrees(math.atan2(look.lamp_y - player.eye_height, 3.5)) + 0.5)
        yield from self.wait(5)
        img = grab()
        w, h = img.get_x_size(), img.get_y_size()
        brightest = max(lum(img, x, y) for x in range(w // 2 - 40, w // 2 + 40, 2) for y in range(h // 2 - 50, h // 2 + 50, 2))
        check('bóng đèn gần như cháy trắng', round(brightest, 2), '> 0.9', brightest > 0.9)
        check('bóng đèn sáng hơn sàn dưới nó', (round(brightest, 2), round(under, 2)), 'hơn', brightest > under + 0.03)

        # muzzle flash lights the real wall (standing close to the wall in the dark area)
        place((9.0, 0.0, z_lamp + 5.0), 90.0, 0.0)
        yield from self.wait(5)
        light.set_flash((0.0, 0.0, 0.7), (0.0, 0.0, 0.0))
        yield from self.wait(2)
        off_lum = mean_rect(grab(), 0.40, 0.25, 0.60, 0.45)
        light.set_flash((0.0, 0.0, 0.7), tuple(c * gun.flash.light_power for c in gun.flash.light_color))
        yield
        yield
        on_lum = mean_rect(grab(), 0.40, 0.25, 0.60, 0.45)
        light.set_flash((0.0, 0.0, 0.7), (0.0, 0.0, 0.0))
        check('tia lửa làm tường sáng lên (độ sáng)', (round(off_lum, 3), round(on_lum, 3)), 'tăng > 0.04', on_lum - off_lum > 0.04)
        viewmodel.actor.show()

        lens_data.noise, lens_data.bloom, lens_data.auto_exposure = saved
        lens.apply_params()

        # --- G. lens ---
        place()
        yield from self.wait(5)
        check('súng vẽ vào cùng buffer với thế giới', viewmodel.output == lens.manager.buffers[-1], True, viewmodel.output == lens.manager.buffers[-1])
        img = grab()
        w, h = img.get_x_size(), img.get_y_size()
        corners = max(lum(img, x, y) for x, y in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)))
        center = mean_rect(img, 0.35, 0.55, 0.65, 0.75)
        check('góc khung đen', round(corners, 3), '< 0.06', corners < 0.06)
        check('giữa khung có hình', round(center, 3), '> 0.05', center > 0.05)
        held_keys['right mouse'] = 1
        yield from self.wait(40)
        k_ads = lens.frame[0][0]
        held_keys['right mouse'] = 0
        yield from self.wait(40)
        k_hip = lens.frame[0][0]
        check('ngắm thì méo bớt', (round(k_ads, 3), round(k_hip, 3)), (lens_data.fisheye_ads, lens_data.fisheye),
              abs(k_ads - lens_data.fisheye_ads) < 1e-3 and abs(k_hip - lens_data.fisheye) < 1e-3)

        # --- H. auto exposure ---
        game.exposure.value = None
        place((0.0, 0.0, z_lamp))
        yield from self.wait(5)
        bright = light.exposure
        place((10.5, 0.0, z_lamp + 5.0))
        yield
        yield
        just_after = light.exposure
        yield from self.wait(240)
        dark = light.exposure
        check('vào chỗ tối: phơi sáng tăng', (round(bright, 2), round(dark, 2)), 'tăng > 15%', dark > bright * 1.15)
        check('và tăng dần, không nhảy ngay', round(just_after, 2), f'< {dark:.2f}', just_after < bright + (dark - bright) * 0.3)

        # --- I. cost does not grow with the number of bullet holes ---
        place()
        yield from self.wait(20)
        frames = []
        last = pytime.perf_counter()
        for _ in range(120):
            yield
            now = pytime.perf_counter()
            frames.append(now - last)
            last = now
        before_ms = statistics.median(frames) * 1000
        for i in range(game.params.feedback.max_holes):
            combat.decals.add((-4.0 + i % 20 * 0.4, 0.6 + (i // 20) * 0.3, 10.0), (0.0, 0.0, -1.0), 10.0)
        yield from self.wait(10)
        frames.clear()
        last = pytime.perf_counter()
        for _ in range(120):
            yield
            now = pytime.perf_counter()
            frames.append(now - last)
            last = now
        after_ms = statistics.median(frames) * 1000
        check('200 lỗ đạn vẫn chỉ một lần vẽ', len(combat.decals.entities), 1, len(combat.decals.entities) == 1)
        check('200 lỗ đạn không làm chậm khung (ms)', (round(before_ms, 2), round(after_ms, 2)), f'tăng < 1.5', after_ms - before_ms < 1.5)
        snap('holes')

        # --- J. borderless fullscreen window (its own process, same path as main.py) ---
        code = ('import sys; sys.path.insert(0, r"%s"); sys.stdout.reconfigure(encoding="utf-8")\n'
                'from main import create_game\n'
                'from fps.app import desktop_size\n'
                'from ursina import application\n'
                'g = create_game(vsync=True, size=desktop_size(), borderless=True, sound=False, draw=False, quit_after=1.5)\n'
                'p = application.base.win.get_properties()\n'
                'print("KICHTHUOC", p.get_x_size(), p.get_y_size(), p.get_undecorated(), p.get_x_origin(), p.get_y_origin())\n'
                'g.app.run()\n' % ROOT)
        line = ''
        for _ in range(2):
            proc = subprocess.run([sys.executable, '-X', 'utf8', '-c', code], capture_output=True, encoding='utf-8', errors='replace', timeout=120, cwd=ROOT)
            line = next((ln for ln in proc.stdout.splitlines() if ln.startswith('KICHTHUOC')), f'          mã thoát {proc.returncode}')
            if line.startswith('KICHTHUOC'):
                break
        parts = line.split()
        want_w, want_h = desktop_size()
        ok = len(parts) == 6 and int(parts[1]) == want_w and int(parts[2]) == want_h and parts[3] == 'True' and int(parts[4]) == 0 and int(parts[5]) == 0
        check('main: cửa sổ không viền phủ kín màn hình', line[10:], f'{want_w} {want_h} True 0 0', ok)


def report():
    wn = max(len(str(r[0])) for r in results)
    for name, got, expected, ok in results:
        print(f'{str(name):{wn}s} {str(got):>32s} {str(expected):>26s}  {"ĐẠT" if ok else "TRƯỢT"}')
    print(f'{sum(1 for r in results if r[3])}/{len(results)} mục đạt')


Script()
game.app.run()
