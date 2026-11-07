"""G8: the Glock in the real game - semi-auto fire, slide cycle clip, last round locks the slide, both reload types, aiming (sights on the view axis),
pistol sounds, and the weapon switch M4 <-> Glock (keys 1 / 2, rounds remembered per gun).

Drives the game through its own paths (held_keys, combat.pressed, game.input). Screenshots go to shots\\g8_*.png.

Run:  .venv\\Scripts\\python.exe -X utf8 tools\\selftests\\g8_selftest.py        (exits with code 1 if any item fails)
"""
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Point3, Vec3  # noqa: E402
from ursina import Entity, held_keys, mouse  # noqa: E402

from fps.core.handling import Phase  # noqa: E402
from fps.weapon_data import GLOCK, M4  # noqa: E402

game = create_game(vsync=False, sound=True, draw=False, moving_targets=False, free_aim=False, gun='glock')
mouse.locked = False
game.combat.require_locked_mouse = False
game.combat.rng.seed(3)
results = []


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def c():
    return game.combat


def vm():
    return game.viewmodel


def bolt_offset():
    """Slide position relative to the gun frame (cm)."""
    a = vm().actor
    ref = a.find('**/Main_G17_D_0-parent')
    return a.find('**/Bolt_G17_D_0-parent').getPos(ref)


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        try:
            next(self.gen)
        except StopIteration:
            self.finish()

    def sec(self, seconds):
        t0 = pytime.time()
        while pytime.time() - t0 < seconds:
            yield

    def until(self, cond, timeout):
        t0 = pytime.time()
        while not cond() and pytime.time() - t0 < timeout:
            yield

    def pull(self):
        c().pressed = True
        yield

    def run(self):
        yield from self.sec(1.0)
        w = c().weapon
        check('đang cầm Glock 17, bán tự động, 17 + 85 viên', (game.gun_name, game.params.gun.name, w.mag, w.reserve, w.auto), "('glock', 'Glock 17', 17, 85, False)",
              game.gun_name == 'glock' and game.params.gun.name == 'Glock 17' and (w.mag, w.reserve, w.auto) == (17, 85, False))
        check('có đủ 8 clip trong glb', sorted(vm().actor.getAnimNames()), sorted(k.anim for k in GLOCK.clips.values()),
              sorted(vm().actor.getAnimNames()) == sorted(k.anim for k in GLOCK.clips.values()))

        # --- draw ---
        c().handling.start_draw()
        yield
        check('rút súng: chưa bắn được', c().handling.can_fire, False, not c().handling.can_fire)
        t0 = pytime.time()
        yield from self.until(lambda: c().handling.can_fire, 3.0)
        t_draw = pytime.time() - t0
        want = GLOCK.clips['draw'].duration / GLOCK.reload.draw_speed
        check('thời gian rút súng (s)', round(t_draw, 2), f'{want:.2f} +-0.15', abs(t_draw - want) < 0.15)

        # --- semi-auto fire ---
        w = c().weapon
        before = w.mag
        held_keys['left mouse'] = 1
        yield from self.sec(0.6)
        held_keys['left mouse'] = 0
        check('giữ cò không nhả đạn liên thanh (bán tự động)', before - w.mag, '0', before - w.mag == 0)
        yield from self.pull()
        yield from self.sec(0.05)
        check('một lần bấm = một viên', before - w.mag, '1', before - w.mag == 1)
        check('clip bắn đang chạy', vm().clip_key, "'fire'", vm().clip_key == 'fire')
        yield from self.sec(0.05)
        slide_back = bolt_offset().length()
        yield from self.sec(0.5)
        check('clip bắn xong, trở về tư thế sẵn sàng', vm().clip_key, 'None', vm().clip_key is None)
        yield from self.sec(0.2)
        ready_slide = Vec3(bolt_offset())
        check('slide về chỗ sau khi bắn', round((ready_slide - Vec3(bolt_offset())).length(), 3), '< 0.2 cm', (ready_slide - Vec3(bolt_offset())).length() < 0.2)
        # two quick pulls: the 420 rpm limit (0.143 s) lets only one through
        m = w.mag
        c().pressed = True
        yield
        c().pressed = True
        yield
        yield from self.sec(0.05)
        check('hai lần bấm sát nhau: giới hạn nhịp 420 viên/phút', m - w.mag, '1', m - w.mag == 1)
        yield from self.sec(0.4)

        # --- last round locks the slide ---
        w.mag = 1
        yield from self.pull()
        yield from self.sec(0.7)
        locked = Vec3(bolt_offset())
        w.mag = 17
        check('hết đạn: slide kẹt mở sau viên cuối', round(vm()._empty, 2), '1.0', vm()._empty == 1.0)
        w.mag = 0
        yield from self.sec(0.2)
        check('slide khoá mở lệch khỏi chỗ đóng > 2 cm', round((locked - ready_slide).length(), 2), '> 2', (locked - ready_slide).length() > 2.0)

        # --- reload with the slide locked (empty magazine) ---
        n_beforehand = game.foley.counts['pistol_mag_seat'] if game.foley else 0
        c().request_reload()
        yield
        check('hết đạn: dùng clip nạp cạn', c().handling.key, "'reload_empty'", c().handling.key == 'reload_empty')
        check('băng đạn phụ hiện trong lúc nạp', not vm().reload_props[0].is_hidden(), 'True', not vm().reload_props[0].is_hidden())
        swap_t = GLOCK.clips['reload_empty'].swap_time / GLOCK.reload.speed
        yield from self.sec(swap_t - 0.3)
        check('trước khi băng vào chỗ vẫn 0 viên', w.mag, '0', w.mag == 0)
        yield from self.sec(0.6)
        check('băng vào chỗ: đủ 17 viên', w.mag, '17', w.mag == 17)
        yield from self.until(lambda: not c().handling.busy, 4.0)
        yield from self.sec(0.2)
        check('nạp xong: slide đã nhả về chỗ đóng', round((Vec3(bolt_offset()) - ready_slide).length(), 2), '< 0.3 cm', (Vec3(bolt_offset()) - ready_slide).length() < 0.3)
        check('băng đạn phụ ẩn sau khi nạp', vm().reload_props[0].is_hidden(), 'True', vm().reload_props[0].is_hidden())
        if game.foley:
            check('có phát tiếng cắm băng và nhả slide', (game.foley.counts['pistol_mag_seat'] - n_beforehand, game.foley.counts['pistol_slide_release']), '(1, >=1)',
                  game.foley.counts['pistol_mag_seat'] - n_beforehand >= 1 and game.foley.counts['pistol_slide_release'] >= 1)

        # --- reload with rounds left ---
        w.mag, w.reserve = 9, 40
        c().request_reload()
        yield
        check('còn đạn: dùng clip nạp thường', c().handling.key, "'reload'", c().handling.key == 'reload')
        yield from self.until(lambda: not c().handling.busy, 4.0)
        check('nạp thường: đầy băng, trừ đúng dự trữ', (w.mag, w.reserve), '(17, 32)', (w.mag, w.reserve) == (17, 32))

        # --- aiming: both sights on the view axis ---
        held_keys['right mouse'] = 1
        yield from self.sec(1.0)
        g, v = game.params.gun, vm()
        pts = []
        for p in g.ads_sights:
            q = v.cam_np.get_relative_point(v.sway, Point3(*(a + b for a, b in zip(p, g.hip_offset))))
            pts.append((round(float(q[0]), 4), round(float(q[1]), 4), round(float(q[2]), 4)))
        check('ngắm: ADS đầy đủ', round(game.player.ads_amount, 2), '1.0', game.player.ads_amount >= 0.99)
        check('ngắm: đuôi và đầu ruồi nằm trên trục nhìn (x, y lệch < 6 mm)', pts, '|x|,|y| < 0.006', all(abs(q[0]) < 0.006 and abs(q[1]) < 0.006 for q in pts))
        check('ngắm: khoảng cách mắt - ruồi sau khớp ads_eye_relief', pts[0][2], f'{g.ads_eye_relief} +-0.02', abs(pts[0][2] - g.ads_eye_relief) < 0.02)
        held_keys['right mouse'] = 0
        yield from self.sec(0.4)

        # --- weapon switch ---
        w.mag, w.reserve = 12, 50
        game.input('1')
        yield
        check('đang đổi súng: chưa bắn được, clip cất súng', (c().handling.key, c().handling.can_fire), "('holster', False)", c().handling.key == 'holster' and not c().handling.can_fire)
        yield from self.until(lambda: game.gun_name == 'm4' and c().handling.can_fire, 8.0)
        check('đổi sang M4 xong', (game.gun_name, game.params.gun.name), "('m4', 'M4')", game.gun_name == 'm4' and game.params.gun.name == 'M4')
        w = c().weapon
        check('M4 còn nguyên 30 + 600 viên', (w.mag, w.reserve), '(30, 600)', (w.mag, w.reserve) == (30, 600))
        check('M4: viewmodel là súng M4', vm().gun.name, "'M4'", vm().gun.name == 'M4')
        game.input('2')
        yield
        yield from self.until(lambda: game.gun_name == 'glock' and c().handling.can_fire, 8.0)
        w = c().weapon
        check('quay lại Glock: nhớ 12 + 50 viên', (game.gun_name, w.mag, w.reserve), "('glock', 12, 50)", (game.gun_name, w.mag, w.reserve) == ('glock', 12, 50))
        game.input('1')
        yield
        game.input('2')                              # pressed while the holster clip is running: ignored
        yield from self.sec(0.3)
        check('đang cất súng: bấm phím khác bị bỏ qua', game._pending_gun, "'m4'", game._pending_gun == 'm4')
        yield from self.until(lambda: game.gun_name == 'm4' and c().handling.can_fire, 8.0)
        yield from self.sec(0.3)
        game.input('2')
        yield from self.until(lambda: game.gun_name == 'glock' and c().handling.can_fire, 8.0)
        check('sau nhiều lần đổi vẫn bắn được', c().handling.can_fire, 'True', c().handling.can_fire)

    def finish(self):
        width = max(len(r[0]) for r in results)
        failed = 0
        for name, got, expected, ok in results:
            print(f'{"ĐẠT" if ok else "TRƯỢT"}  {name.ljust(width)}  được: {got}  mong đợi: {expected}')
            failed += 0 if ok else 1
        print(f'\n{len(results) - failed}/{len(results)} mục đạt')
        sys.exit(1 if failed else 0)


Script()
game.app.run()
