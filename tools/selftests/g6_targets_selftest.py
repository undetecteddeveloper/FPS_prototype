"""G6: moving targets + distance signs, with the real game.

Measures:
  - layout: 3 moving targets (25 / 100 / 200 m: 1.5 / 3 / 4 m/s) + 3 standing targets; the running lanes do not touch columns / walls / signs / markers;
    a moving target does not hide a standing target for more than ~1/6 of the time (seen from the firing line)
  - motion: correct speed when running with real frames, touches both edges then turns around, rests at each end, position does NOT depend on FPS
  - firing: shots with lead hit the moving target exactly where calculated (error < 1 cm), shots without lead miss; hit/miss is decided at the target edge
    identical at 20 / 60 / 240 FPS (the target box is swept in small steps, not taken at the end-of-frame position); a full-auto burst into the crossing target
  - feedback: bullet holes follow the moving target, hit marker, colour flash, HUD distance
  - shadows: the real shadow of a moving target is redrawn (and stops when the target stands still), the shadow moves with the target (compare floor brightness in two shots)
  - signs: all 6 distances x 2 sides, the text really is in the texture, the correct number is readable from the firing line (matched against a real screenshot)
  - interleaved FPS: still / running + real shadows / running + fake shadows / running + no shadows, in one run
Screenshots go to shots\\targets_*.png.

Run (through the lock):  .venv\\Scripts\\python.exe -X utf8 tools\\with_game_lock.py .venv\\Scripts\\python.exe -X utf8 tools\\selftests\\g6_targets_selftest.py
(exits with code 1 if any item fails)
"""
import math
import statistics
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from fps.core.lens import equivalent_center_fov  # noqa: E402
from panda3d.core import Filename, Point2, Point3  # noqa: E402
from PIL import Image  # noqa: E402
from ursina import Entity, application, camera, held_keys, mouse, time, window  # noqa: E402

from fps.core.ballistics import BoxGroup  # noqa: E402
from fps.core.signs import SignLayout, sign_rect  # noqa: E402
from fps.game.shooting_range import DISTANCE_MARKS, aabb_of  # noqa: E402
from fps.game.targets import LAYOUT, MOVERS, PATROL_EDGE_X, TARGET_THICKNESS, build_targets  # noqa: E402

game = create_game(vsync=False, sound=False, draw=False, hud=True, free_aim=False, lens=False)          # moving targets ON (the real game's default)
player, combat, look = game.player, game.combat, game.look
gun = game.params.gun
# even kick, upward only: this test measures hit accuracy against moving targets, not the kick
gun.recoil.up, gun.recoil.up_noise, gun.recoil.right_bias, gun.recoil.right_noise, gun.recoil.right_walk, gun.recoil.camera_share = 0.33, 0.03, 0.03, 0.0, 0.0, 1.0
mouse.locked = False
combat.require_locked_mouse = False
for _name in ('stand', 'walk', 'sprint', 'air', 'ads', 'ads_move', 'bloom_per_shot'):      # measures bullet direction, so spread is off (as in g2)
    setattr(gun.accuracy, _name, 0.0)

results = []
skip = {'next': False}
EYE = (0.0, game.params.player.eye_height_stand, 0.0)


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


def shot(name):
    out = ROOT / 'shots' / f'targets_{name}.png'
    out.parent.mkdir(exist_ok=True)
    application.base.win.saveScreenshot(Filename.from_os_specific(str(out)))
    skip['next'] = True
    print('ĐÃ CHỤP', out.name)
    return out


def target(distance):
    return next(t for t in game.targets if t.distance == distance)


MOVING = [t for t in game.targets if t.patrol is not None]
STANDING = [t for t in game.targets if t.patrol is None]


def aim(yaw, pitch=0.0):
    player.position = (0, 0, 0)
    player.vx = player.vz = 0.0
    player.yaw, player.pitch = yaw % 360, pitch
    player.rotation_y = player.yaw
    player.camera_pivot.rotation_x = pitch
    player._apply_view()


def snapshot(t):
    p = t.patrol
    return (p.x, p.direction, p.wait, t.root.x, t.x_start, t.x_end, t.motion_enabled)


def restore(t, s):
    p = t.patrol
    p.x, p.direction, p.wait, t.root.x, t.x_start, t.x_end, t.motion_enabled = s


def place(t, x, direction=1.0):
    """Place the moving target at x, moving along `direction`, currently running (no rest)."""
    t.motion_enabled = True
    t.patrol.reset(x, direction)
    t.root.x = t.x_start = t.x_end = x


def park_others(t, x=7.0):
    """Freeze every other moving target and move it to the right (x = 7) so they do not block the bullet path aimed at target `t`."""
    for m in MOVING:
        if m is not t:
            m.motion_enabled = False
            m.patrol.reset(x, 1.0)
            m.root.x = m.x_start = m.x_end = x


def freeze(on=True):
    for t in MOVING:
        t.motion_enabled = not on


def reset_combat(auto=False, mag=30):
    held_keys['left mouse'] = 0
    combat.bullets.clear()
    combat.last_impact = None
    combat.weapon.auto = auto
    combat.weapon.mag = mag
    combat.weapon.reserve = 150
    combat.weapon.cooldown = 0.0
    combat.pressed = False


def boxes_overlap(a, b):
    return all(a[0][i] < b[1][i] and b[0][i] < a[1][i] for i in range(3))


def static_boxes():
    out = []
    for lo, hi, owner in game.world['colliders']:
        if isinstance(owner, BoxGroup):
            out.extend((blo, bhi) for blo, bhi, _ in owner.boxes)
        else:
            out.append((lo, hi))
    out += list(game.world['post_boxes'])
    out += [(r['lo'], r['hi']) for _, _, r in game.world['sign_rects']]
    return out


def screen_px(p):
    out = Point2()
    camera.lens.project(camera.getRelativePoint(application.base.render, Point3(*p)), out)
    return (out.x + 1) / 2 * window.size[0], (1 - out.y) / 2 * window.size[1]      # image pixels (origin top-left)


def luma(img):
    return img.convert('L')


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.last = None

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

    def frames(self, n):
        for _ in range(n):
            yield

    # --- fire at a fixed step through the game's own code path (combat.update) ---
    def manual_shot(self, t, dt, offset, x0=-5.0, direction=1.0, stop_on_hit=False):
        """Place moving target `t` at x0, then fire ONE shot aimed so the bullet arrives at the position (target centre when the bullet arrives + `offset`), run `combat.update(dt, dt)`
        until the bullet is spent. Returns a dict: hit (target hit?), local_x of the bullet hole on the target, expected, hit marker..."""
        reset_combat()
        freeze(True)                            # only target `t` runs: other targets must not block the bullet
        park_others(t)
        place(t, x0, direction)
        v = t.patrol.speed * direction
        z_hit = t.distance - TARGET_THICKNESS / 2
        theta = 0.0
        for _ in range(4):                      # iterative solution: flight time depends slightly on the angle
            t_hit = dt + z_hit / (gun.muzzle_velocity * math.cos(theta))      # the first shot fires at the END of the first frame (age 0)
            x_target = x0 + v * t_hit
            theta = math.atan2(x_target + offset, z_hit)
        aim(math.degrees(theta))
        combat.pressed = True
        n_hits, holes = combat.target_hits, combat.decals.count
        info = {'hit': False, 'frames': 0}
        for i in range(int(3.0 / dt)):
            combat.update(dt, dt)
            info['frames'] += 1
            if combat.target_hits > n_hits and not info['hit']:
                info['hit'] = True
                info['marker'] = combat.hit_marker_left
                info['flash'] = t.flash_left
                info['last_hit_distance'] = combat.last_hit_distance
                game.hud.update(dt, combat)
                info['hud_text'] = game.hud.last_hit.text
                info['hud_marker'] = max(e.color.a for e in game.hud.hit_marker)
                if stop_on_hit:
                    break
            if not combat.bullets and i > 2:
                break
        imp = combat.last_impact
        info['owner_is_target'] = imp is not None and imp.owner is t
        info['impact'] = imp
        info['expected_local'] = offset
        if combat.decals.count > holes and info['hit']:
            info['decal'] = combat.decals.last_parent
            info['local_x'] = combat.decals.last_local[0]
        return info

    def run(self):
        yield from self.wait(0.6)

        # --- A. layout ---
        check('có 6 bia: 3 chạy, 3 đứng', (len(MOVING), len(STANDING)), '(3, 3)', (len(MOVING), len(STANDING)) == (3, 3))
        check('bia chạy ở 25 / 100 / 200 m', sorted(t.distance for t in MOVING), '[25, 100, 200]',
              sorted(t.distance for t in MOVING) == [25.0, 100.0, 200.0])
        speeds = {t.distance: t.patrol.speed for t in MOVING}
        check('tốc độ đúng cấu hình (m/s)', speeds, {d: s.speed for d, s in MOVERS.items()},
              speeds == {float(d): s.speed for d, s in MOVERS.items()})
        check('tốc độ trong 1,5 .. 4 m/s, gần chậm hơn xa nhanh hơn', [speeds[d] for d in (25.0, 100.0, 200.0)], 'tăng dần',
              all(1.5 <= s <= 4.0 for s in speeds.values()) and speeds[25.0] < speeds[100.0] < speeds[200.0])
        check('bia đứng yên đúng x của LAYOUT', [(t.distance, t.root.x) for t in STANDING], 'LAYOUT',
              all(t.root.x == LAYOUT[int(t.distance)] for t in STANDING))
        check('mép ngoài bia chạy không vượt vạch sơn làn (m)', [round(max(abs(t.sweep_aabb()[0][0]), abs(t.sweep_aabb()[1][0])), 2) for t in MOVING],
              f'<= {PATROL_EDGE_X}', all(max(abs(t.sweep_aabb()[0][0]), abs(t.sweep_aabb()[1][0])) <= PATROL_EDGE_X + 1e-9 for t in MOVING))
        statics = static_boxes()
        clash = [(t.distance, i) for t in MOVING for i, b in enumerate(statics) if boxes_overlap(t.sweep_aabb(), b)]
        check(f'hành lang bia chạy không chạm cột / tường / dầm / trần / cột mốc / biển ({len(statics)} hộp)', clash, '[]', not clash)
        # a moving target hides a standing target: compare the angular gap seen from the firing line
        worst_full, worst_any = 0.0, 0.0
        for m in MOVING:
            lo, hi = m.patrol.lo, m.patrol.hi
            for s in STANDING:
                if s.distance <= m.distance:
                    continue                                               # only a moving target IN FRONT of a standing target can hide it
                full = any_ = 0
                n = 2000
                s_lo, s_hi = (s.root.x - s.width / 2) / s.distance, (s.root.x + s.width / 2) / s.distance
                for k in range(n):
                    x = lo + (hi - lo) * (k + 0.5) / n
                    m_lo, m_hi = (x - m.width / 2) / m.distance, (x + m.width / 2) / m.distance
                    full += m_lo <= s_lo and m_hi >= s_hi
                    any_ += m_lo < s_hi and m_hi > s_lo
                worst_full, worst_any = max(worst_full, full / n), max(worst_any, any_ / n)
        print(f'CHE: bia chạy che HẲN một bia đứng tối đa {worst_full * 100:.1f}% thời gian, che MỘT PHẦN tối đa {worst_any * 100:.1f}% (nhìn từ vạch bắn)')
        check('bia chạy che hẳn bia đứng phía sau <= 15% thời gian', round(worst_full, 3), '<= 0.15', worst_full <= 0.15)
        check('bia chạy che một phần bia đứng phía sau <= 35% thời gian', round(worst_any, 3), '<= 0.35', worst_any <= 0.35)
        # build_targets(moving=False): all stand still at the x of LAYOUT
        still = build_targets(game.params.feedback, moving=False)
        check('moving=False: mọi bia đứng yên ở x của LAYOUT', [(t.distance, t.root.x, t.patrol) for t in still][:2], 'LAYOUT, không patrol',
              all(t.patrol is None and t.root.x == LAYOUT[int(t.distance)] for t in still) and len(still) == 6)
        for t in still:
            t.root.enabled = False
            t.plate.enabled = False

        # --- B. motion ---
        # B1. speed when running with real frames (long straight stretch, no turnaround)
        saved = {t: snapshot(t) for t in MOVING}
        for t in MOVING:
            speed_ok = []
            place(t, -3.0 if t.patrol.speed < 2 else -4.0, 1.0)
            yield
            xs, dts = [t.root.x], []
            n = 0
            while n < 40:                                                  # ~0.7 s: short enough not to touch an edge (at most 3 m)
                yield
                xs.append(t.root.x)
                dts.append(combat.frame_dt)                                # the dt the target just used
                n += 1
            measured = (xs[-1] - xs[0]) / sum(dts)
            check(f'tốc độ đo bằng khung thật, bia {t.distance:.0f} m (m/s)', round(measured, 3), t.patrol.speed,
                  abs(measured - t.patrol.speed) < 0.03 * t.patrol.speed)
        for t, s in saved.items():
            restore(t, s)

        # B2. touch both edges, turn around, rest: simulated with a fixed step (no window)
        for t in MOVING:
            s0 = snapshot(t)
            p = t.patrol
            place(t, p.lo + 0.5 * p.span, 1.0)
            dt = 1.0 / 60.0
            xs = []
            turns = 0
            last_dir = p.direction
            rest_frames = 0
            max_rest = 0
            for _ in range(int(2.2 * p.period / dt)):
                t.update(dt)
                xs.append(t.root.x)
                if p.direction != last_dir:
                    turns += 1
                    last_dir = p.direction
                if p.wait > 0:
                    rest_frames += 1
                    max_rest = max(max_rest, rest_frames)
                else:
                    rest_frames = 0
            check(f'bia {t.distance:.0f} m chạm đúng hai biên (m)', (round(min(xs), 4), round(max(xs), 4)), (round(p.lo, 4), round(p.hi, 4)),
                  abs(min(xs) - p.lo) < 1e-5 and abs(max(xs) - p.hi) < 1e-5)
            check(f'  quay đầu >= 4 lần trong 2,2 vòng', turns, '>= 4', turns >= 4)
            check(f'  nghỉ ở mỗi đầu đúng {p.pause:.2f} s (+-1 khung)', round(max_rest * dt, 3), p.pause, abs(max_rest * dt - p.pause) <= dt * 1.5)
            check(f'  luôn trong biên', (round(min(xs), 3), round(max(xs), 3)), f'[{p.lo:.2f}, {p.hi:.2f}]', min(xs) >= p.lo - 1e-5 and max(xs) <= p.hi + 1e-5)      # root.x is float32: error ~1e-6
            restore(t, s0)

        # B3. position does not depend on FPS: same time span, steps 1/20, 1/60, 1/144 and an irregular step
        t = target(100)
        s0 = snapshot(t)
        finals = []
        for label, fps in (('20', 20), ('60', 60), ('144', 144), ('240', 240)):
            place(t, 1.0, -1.0)
            for _ in range(round(13.5 * fps)):
                t.update(1.0 / fps)
            finals.append(t.root.x)
        place(t, 1.0, -1.0)
        total, k = 0.0, 0
        while total < 13.5 - 1e-9:
            step = min(0.003 + 0.037 * ((k * 7919) % 100) / 100.0, 13.5 - total)    # 3 .. 40 ms
            t.update(step)
            total += step
            k += 1
        finals.append(t.root.x)
        spread = max(finals) - min(finals)
        check('vị trí sau 13,5 s giống nhau ở 20 / 60 / 144 / 240 FPS và bước thất thường (mm)', round(spread * 1000, 4), '< 0.5', spread < 0.0005)       # root.x is float32
        restore(t, s0)

        # --- C. hitting moving targets ---
        t = target(200)
        v = t.patrol.speed
        infos = {}
        for dt in (1 / 240, 1 / 60, 1 / 20):
            for label, off in (('giữa', 0.0), ('mép trong +1,05', 1.05), ('mép trong -1,05', -1.05), ('ngoài mép +1,15', 1.15), ('ngoài mép -1,15', -1.15)):
                info = self.manual_shot(t, dt, off)
                infos[(dt, label)] = info
        for dt in (1 / 240, 1 / 60, 1 / 20):
            tag = f'{1 / dt:.0f} FPS'
            mid = infos[(dt, 'giữa')]
            check(f'[{tag}] bắn đón đầu vào tâm bia 200 m ({v:.0f} m/s): trúng', mid['hit'] and mid['owner_is_target'], True, mid['hit'] and mid['owner_is_target'])
            if 'local_x' in mid:
                check(f'[{tag}]   lỗ đạn trên bia lệch tâm (cm)', round(mid['local_x'] * 100, 2), '|x| < 1', abs(mid['local_x']) < 0.01)
            for label in ('mép trong +1,05', 'mép trong -1,05'):
                inf = infos[(dt, label)]
                check(f'[{tag}] {label} m (rộng 2,2): TRÚNG', inf['hit'] and inf['owner_is_target'], True, inf['hit'] and inf['owner_is_target'])
                if 'local_x' in inf:
                    exp = inf['expected_local']
                    check(f'[{tag}]   vị trí lỗ trên bia (cm, mong đợi {exp * 100:+.0f})', round(inf['local_x'] * 100, 2), f'{exp * 100:+.0f} +-1.5',
                          abs(inf['local_x'] - exp) < 0.015)
            for label in ('ngoài mép +1,15', 'ngoài mép -1,15'):
                inf = infos[(dt, label)]
                check(f'[{tag}] {label} m: TRƯỢT', not inf['hit'], True, not inf['hit'])
        # without leading it misses (target at 200 m moves 4 m/s, bullet flies 0.4 s -> offset 1.6 m > half width 1.1 m)
        reset_combat()
        freeze(True)
        park_others(t)
        place(t, -5.0, 1.0)
        aim(math.degrees(math.atan2(-5.0, 199.97)))
        combat.pressed = True
        for _ in range(int(2.0 * 60)):
            combat.update(1 / 60, 1 / 60)
            if not combat.bullets:
                break
        imp = combat.last_impact
        check('bắn thẳng vào chỗ bia ĐANG đứng (không đón đầu): trượt bia 200 m', imp is not None and imp.owner is not t, True,
              imp is not None and imp.owner is not t)

        # --- D. feedback (middle hit at 60 FPS) ---
        mid = infos[(1 / 60, 'giữa')]
        check('hit marker bật lúc trúng bia chạy', round(mid['marker'], 3), '> 0', mid['marker'] > 0)
        check('bia chạy nháy màu lúc trúng', round(mid['flash'], 3), '> 0', mid['flash'] > 0)
        imp = mid['impact']
        expect_dist = math.dist(imp.origin, imp.point)
        check('khoảng cách bia vừa trúng (m) = độ dài đường đạn', round(mid['last_hit_distance'], 3), round(expect_dist, 3),
              abs(mid['last_hit_distance'] - expect_dist) < 1e-6)
        check('HUD hiện khoảng cách bia chạy vừa trúng', mid['hud_text'], f'{expect_dist:.0f} m', mid['hud_text'] == f'{expect_dist:.0f} m')
        check('HUD: hit marker hiện (alpha)', round(mid['hud_marker'], 2), '> 0', mid['hud_marker'] > 0)

        # bullet hole follows the target: fire, then let the target run on for 1 s (fixed step) -> the hole moves exactly as much and stays still on the target face
        info = self.manual_shot(t, 1 / 60, 0.4, x0=-5.0, stop_on_hit=True)
        decal = combat.decals.by_owner[t.root].entity                # bullet-hole mesh of this target only
        local0, world0 = decal.position[0], decal.world_position.x
        root0 = t.root.x
        check('lỗ đạn gắn vào target.root (đi theo bia)', decal.parent is t.root, True, decal.parent is t.root)
        for _ in range(60):
            t.update(1 / 60)
        moved = t.root.x - root0
        check('sau 1 s: bia đã đi (m)', round(moved, 3), '~4', abs(moved - 4.0) < 0.05)
        check('  lỗ đạn đi cùng bia (m)', round(decal.world_position.x - world0, 3), round(moved, 3), abs((decal.world_position.x - world0) - moved) < 1e-4)
        check('  toạ độ của lỗ trên bia không đổi (cm)', round((decal.position[0] - local0) * 100, 4), 0, abs(decal.position[0] - local0) < 1e-6)
        combat.bullets.clear()

        # --- E. full-auto burst with real frames into the 25 m target crossing the fixed aim point ---
        t = target(25)
        reset_combat(auto=True)
        combat.weapon.mag = 30
        freeze(True)
        place(t, -1.0, 1.0)
        aim(0.0, 3.0)                       # aim low (chest/belly): recoil slowly pulls the aim point up, but it stays within the 1.9 m tall target body
        holes_before = combat.decals.count
        hits_before = combat.target_hits
        used = []
        marker_seen = hud_text_seen = False
        yield
        held_keys['left mouse'] = 1
        t_end = pytime.perf_counter() + 1.9
        hud_texts = set()
        last_hits = combat.target_hits
        while pytime.perf_counter() < t_end and combat.weapon.mag > 0:
            yield
            if combat.target_hits > last_hits:
                last_hits = combat.target_hits
                if combat.last_impact.owner is t:          # the last bullet of the burst may pass the near target and hit the far one behind
                    used.append((t.root.x, combat.decals.last_local[0]))
            marker_seen = marker_seen or max(e.color.a for e in game.hud.hit_marker) > 0
            if game.hud.last_hit.text:
                hud_texts.add(game.hud.last_hit.text)
            hud_text_seen = hud_text_seen or game.hud.last_hit.text == '25 m'
        held_keys['left mouse'] = 0
        yield from self.wait(0.4)
        n = combat.target_hits - hits_before
        locals_ = [loc for _, loc in used]
        print(f'LIỆT: {n} phát trúng bia 25 m đang chạy; toạ độ lỗ trên bia (cm): ' + ', '.join(f'{x * 100:+.0f}' for x in locals_))
        check('loạt liên thanh vào bia chạy: >= 4 phát trúng', n, '>= 4', n >= 4)
        check('  các lỗ nằm trong bề rộng bia', len(locals_), 'tất cả |x| <= nửa rộng', all(abs(x) <= t.width / 2 + 1e-6 for x in locals_))
        if len(locals_) >= 3:
            drift = locals_[-1] - locals_[0]
            check('  lỗ dạt dần về phía sau bia (bia đi sang phải, ngắm cố định): rải qua bề rộng (cm)', round(drift * 100, 1), '< -15', drift < -0.15)
            inc = sum(1 for a, b in zip(locals_, locals_[1:]) if b < a + 0.04)     # allow for small recoil noise
            check('  thứ tự lỗ giảm dần theo thời gian', f'{inc}/{len(locals_) - 1}', 'gần hết', inc >= len(locals_) - 2)
        check('  hit marker hiện trong loạt', marker_seen, True, marker_seen)
        check('  HUD hiện "25 m"', sorted(hud_texts), "['25 m']", hud_text_seen)
        freeze(True)
        player.position = (0, 0, 15)
        player.yaw, player.pitch = math.degrees(math.atan2(t.root.x, 10.0)), 6.0
        player._apply_view()
        yield from self.frames(6)
        shot('burst')

        # --- F. real shadows of moving targets ---
        restore_state = {m: snapshot(m) for m in MOVING}
        reset_combat()
        t = target(25)
        freeze(False)
        aim(0.0)
        player.position = (0, 0, 6)
        player._apply_view()
        r0 = look.mover_shadow_refreshes
        yield from self.wait(1.5)
        r1 = look.mover_shadow_refreshes
        rate = (r1 - r0) / 1.5
        n_m = len(look.movers)
        expect = look.p.mover_shadow_hz * n_m
        check('bóng bia chạy được vẽ lại khi bia chạy (lần/s tổng, 3 bia)', round(rate, 1), f'~{expect:.0f} (FPS thấp thì ít hơn)',
              0.5 * expect <= rate <= expect * 1.2)
        freeze(True)
        yield from self.frames(40)                      # enough for every target to get its last redraw (6 times/s per target)
        r0 = look.mover_shadow_refreshes
        yield from self.frames(60)
        check('bia đứng yên: bóng không bị vẽ lại', look.mover_shadow_refreshes - r0, 0, look.mover_shadow_refreshes == r0)
        # two shots: 25 m target at x = -2.5 then +2.5; the floor area around where the target first stood must be darker when the target is there
        for m in (target(100), target(200)):
            m.root.x = m.x_start = m.x_end = m.patrol.x = (-6.0 if m.distance == 100 else 6.0)           # push the other two targets away from the frame
        player.position = (0, 0, 12)
        player.yaw, player.pitch = 0.0, 22.0
        player._apply_view()
        pos_a, pos_b = -2.5, 2.5
        floor_pts = [(x, 0.0, z) for x in (pos_a, pos_b) for z in (21.0, 23.5, 26.5, 28.0)]
        imgs = {}
        for label, x in (('a', pos_a), ('b', pos_b)):
            t.root.x = t.x_start = t.x_end = t.patrol.x = x
            look._mover_drawn_x.clear()
            yield from self.frames(25)
            imgs[label] = Image.open(shot(f'mover_shadow_{label}')).convert('L')
        # floor brightness at each point (9x9 window around the projected point) when the target is at A vs at B
        def patch(img, p, r=5):
            x, y = screen_px(p)
            x, y = int(x), int(y)
            box = img.crop((x - r, y - r, x + r + 1, y + r + 1))
            return statistics.mean(box.getdata())
        darker_a = darker_b = 0
        rows = []
        for p in floor_pts:
            a, b = patch(imgs['a'], p), patch(imgs['b'], p)
            rows.append((p[0], p[2], a, b))
        # target at A (x=-2.5): the points at x=-2.5 must be darker than when the target is at B (and vice versa)
        ratio_a = statistics.mean(a / max(b, 1e-6) for x, z, a, b in rows if x == pos_a)
        ratio_b = statistics.mean(b / max(a, 1e-6) for x, z, a, b in rows if x == pos_b)
        print(f'BÓNG: độ sáng sàn quanh bia (tỉ lệ khi bia ở đó / khi bia ở chỗ khác): bên trái {ratio_a:.2f}, bên phải {ratio_b:.2f}')
        check('bóng đi theo bia: sàn quanh vị trí A tối hơn khi bia ở A', round(ratio_a, 3), '< 0.95', ratio_a < 0.95)
        check('bóng đi theo bia: sàn quanh vị trí B tối hơn khi bia ở B', round(ratio_b, 3), '< 0.95', ratio_b < 0.95)
        for m, s in restore_state.items():
            restore(m, s)
        aim(0.0)

        # --- G. distance signs ---
        rects = game.world['sign_rects']
        check('đủ biển: 6 mốc x 2 bên', len(rects), 12, len(rects) == 12 and sorted({d for d, _, _ in rects}) == sorted(DISTANCE_MARKS))
        atlas = game.world['sign_atlas'].pil_image
        cells = game.world['sign_cells']
        H = atlas.size[1]
        refs = {}
        for d in DISTANCE_MARKS:
            u0, u1, v0, v1 = cells[d]
            box = (0, int(round((1 - v1) * H)), atlas.size[0], int(round((1 - v0) * H)))
            cell = atlas.crop(box).convert('L')
            ink = sum(1 for p in cell.getdata() if p > 170) / (cell.size[0] * cell.size[1])
            refs[d] = cell
            check(f'texture biển {d} m: có chữ sáng trên nền tối (tỉ lệ điểm sáng)', round(ink, 3), '0.03 .. 0.30', 0.03 <= ink <= 0.30)
        check('mọi ô chữ khác nhau', len({refs[d].tobytes() for d in DISTANCE_MARKS}), 6, len({refs[d].tobytes() for d in DISTANCE_MARKS}) == 6)
        aim(0.0)
        player.position = (0, 0, 0)
        player._apply_view()
        freeze(True)
        # this test turns the lens off; during play the lens magnifies the centre of the frame (1 + fisheye) times, so it is measured at the centre-frame equivalent FOV, as the player sees it
        saved_fov = game.params.player.fov
        game.params.player.fov = equivalent_center_fov(saved_fov, game.params.lens.fisheye)
        yield from self.frames(8)
        shot('lane')
        full = Image.open(ROOT / 'shots' / 'targets_lane.png').convert('L')
        W_IMG, H_IMG = full.size
        SIZE = (96, 32)

        def norm(img):
            px = list(img.resize(SIZE, Image.LANCZOS).getdata())
            m = statistics.mean(px)
            sd = statistics.pstdev(px) or 1.0
            return [(p - m) / sd for p in px]

        ref_vecs = {d: norm(refs[d]) for d in DISTANCE_MARKS}
        for d in DISTANCE_MARKS:
            r = sign_rect(SignLayout(), d, 1)
            corners = [(r['lo'][0], r['lo'][1], r['lo'][2]), (r['hi'][0], r['lo'][1], r['lo'][2]),
                       (r['lo'][0], r['hi'][1], r['lo'][2]), (r['hi'][0], r['hi'][1], r['lo'][2])]
            px = [screen_px(c) for c in corners]
            x0, x1 = min(p[0] for p in px), max(p[0] for p in px)
            y0, y1 = min(p[1] for p in px), max(p[1] for p in px)
            w_px, h_px = x1 - x0, y1 - y0
            on_screen = x0 >= 0 and x1 <= W_IMG and y0 >= 0 and y1 <= H_IMG
            crop = full.crop((int(x0), int(y0), int(math.ceil(x1)), int(math.ceil(y1))))
            vec = norm(crop)
            scores = {k: sum(a * b for a, b in zip(vec, rv)) / len(vec) for k, rv in ref_vecs.items()}
            best = max(scores, key=scores.get)
            lo_p, hi_p = sorted(crop.getdata())[int(len(crop.getdata()) * 0.05)], sorted(crop.getdata())[int(len(crop.getdata()) * 0.95)]
            print(f'BIỂN {d:3d} m: {w_px:5.1f} x {h_px:4.1f} px trên ảnh 1280x720, tương phản {hi_p - lo_p:3d}/255, khớp mẫu '
                  f'{scores[d]:+.2f} (nhầm gần nhất: {max((v for k, v in scores.items() if k != d)):+.2f})')
            check(f'biển {d} m nằm trong màn hình, rộng >= 12 px', f'{w_px:.0f} x {h_px:.0f}', '>= 12', on_screen and w_px >= 12)
            check(f'  tương phản chữ / nền (0..255)', hi_p - lo_p, '>= 40', hi_p - lo_p >= 40)
            check(f'  nhận ra đúng số bằng so khớp mẫu', f'{best} (điểm {scores[d]:+.2f})', f'{d}', best == d)
        game.params.player.fov = saved_fov
        # close-up screenshot (aiming) for the farthest sign
        player.position = (0, 0, 0)
        player.yaw, player.pitch = 0.0, 3.0
        player._apply_view()
        held_keys['right mouse'] = 1
        yield from self.wait(0.6)
        shot('ads_far')
        held_keys['right mouse'] = 0
        yield from self.wait(0.4)
        aim(0.0)
        player.position = (0, 0, 60)
        player.yaw, player.pitch = 6.0, 3.0
        player._apply_view()
        yield from self.frames(8)
        shot('sign100')
        player.position = (0, 0, 0)
        player.yaw, player.pitch = 25.0, 12.0
        player._apply_view()
        yield from self.frames(8)
        shot('sign10')
        freeze(False)

        # --- H. interleaved FPS ---
        MODES = [('đứng yên + bóng thật', True, True), ('chạy + bóng thật', False, True), ('chạy + bóng giả', False, 'fake'), ('chạy + không bóng', False, False)]
        samples = {m[0]: [] for m in MODES}
        views = [((0, 0, 0), 0.0, 0.0), ((0, 0, 20), 0.0, 3.0), ((0, 0, 100), 10.0, 2.0)]
        rounds = 6
        for r in range(rounds):
            pos, yaw, pitch = views[r % len(views)]
            player.position = pos
            player.yaw, player.pitch = yaw, pitch
            player._apply_view()
            order = MODES if r % 2 == 0 else MODES[::-1]
            for name, frozen, mode in order:
                freeze(frozen)
                look.set_shadow_mode(mode)
                yield from self.frames(15)
                prev = pytime.perf_counter()
                for _ in range(90):
                    yield
                    now = pytime.perf_counter()
                    samples[name].append(now - prev)
                    prev = now
        base = statistics.median(samples[MODES[0][0]])
        print('FPS xen kẽ (vsync tắt, 1280x720):')
        report_fps = {}
        for name, _, _ in MODES:
            d = sorted(samples[name])
            n = len(d)
            med = statistics.median(d)
            report_fps[name] = (med, n / sum(d), 1 / d[int(n * 0.99)])
            print(f'  {name:22s} {n:4d} khung  trung vị {med * 1000:6.2f} ms  trung bình {n / sum(d):5.0f} FPS  1% thấp nhất {1 / d[int(n * 0.99)]:5.0f}  '
                  f'so với đứng yên {100 * (med / base - 1):+5.1f}%')
        look.set_shadow_mode(True)
        freeze(False)
        run_name = MODES[1][0]
        check('chạy + bóng thật: trung bình >= 60 FPS', round(report_fps[run_name][1]), '>= 60', report_fps[run_name][1] >= 60)
        check('chạy + bóng thật: chậm hơn đứng yên <= 15% (trung vị khung)', f'{100 * (report_fps[run_name][0] / base - 1):+.1f}%', '<= +15%',
              report_fps[run_name][0] <= base * 1.15)
        print('số lần vẽ lại bóng bia chạy trong cả bài:', look.mover_shadow_refreshes, '; số lượt vẽ atlas:', look.shadows.render_count)


def report():
    print('\n=== KIỂM TRA G6 (bia chạy + biển khoảng cách) ===')
    print(f"{'mục':92s} {'đo được':>28s} {'mong đợi':>26s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:92s} {str(got):>28s} {str(expected):>26s}  {"ĐẠT" if ok else "TRƯỢT"}')
    print(f'{sum(r[3] for r in results)}/{len(results)} mục đạt')


Script()
game.app.run()
