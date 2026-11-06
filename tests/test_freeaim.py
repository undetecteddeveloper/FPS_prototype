"""Bullets follow the barrel + free-drifting gun: pure maths."""
import math

import pytest

from fps.core.freeaim import FreeAim, FreeLook, barrel_view_dir, view_to_world
from fps.core.movement import aim_direction
from fps.core.sway import Sway, SwayInput, ads_target_for
from fps.core.movement import MoveState
from fps.weapon_data import M4, FreeAimData, SwayData

SIGHTS = M4.ads_sights
ZERO = (0.0,) * 6


def pose(pitch=0.0, yaw=0.0, roll=0.0):
    return (0.0, 0.0, 0.0, pitch, yaw, roll)


def test_resting_barrel_points_almost_exactly_at_screen_centre():
    x, y, z = barrel_view_dir(ZERO, SIGHTS, 92.0, 96.0)
    assert math.degrees(math.atan2(math.hypot(x, y), z)) < 0.15


def test_ads_pose_lines_the_barrel_up_with_the_view_axis():
    """Fully aimed, gun not drifting: the bullet goes exactly to the middle of the screen even though the two cameras have different FOV."""
    x, y, z = barrel_view_dir(ads_target_for(M4), SIGHTS, M4.ads_view_fov, M4.ads_fov)
    assert math.degrees(math.atan2(math.hypot(x, y), z)) < 1e-6


@pytest.mark.parametrize('axis,sign', [('pitch', 1), ('pitch', -1), ('yaw', 1), ('yaw', -1)])
def test_barrel_direction_follows_the_gun(axis, sign):
    p = pose(pitch=sign * 3.0) if axis == 'pitch' else pose(yaw=sign * 3.0)
    x, y, z = barrel_view_dir(p, SIGHTS, 96.0, 96.0)
    if axis == 'pitch':
        assert y * sign > 0.04
    else:
        assert x * sign > 0.04
    assert z > 0.99
    assert math.sqrt(x * x + y * y + z * z) == pytest.approx(1.0)


def test_same_fov_means_same_angle():
    axis = (SIGHTS[1][0] - SIGHTS[0][0], SIGHTS[1][1] - SIGHTS[0][1], SIGHTS[1][2] - SIGHTS[0][2])
    base = math.atan2(axis[1], axis[2])
    _, y, z = barrel_view_dir(pose(pitch=4.0), SIGHTS, 80.0, 80.0)
    assert math.atan2(y, z) == pytest.approx(math.radians(4.0) + base, abs=1e-6)


@pytest.mark.parametrize('view,world', [(92.0, 96.0), (66.0, 84.5), (75.0, 96.0)])
def test_bullet_lands_where_the_barrel_points_on_screen(view, world):
    """The barrel-axis convergence point on screen (through the gun lens) must coincide with the projected bullet direction (through the world lens)."""
    p = pose(pitch=2.5, yaw=-3.0)
    x, y, z = barrel_view_dir(p, SIGHTS, world, world)                   # the true barrel direction, lens unchanged
    sx, sy = x / z / math.tan(math.radians(view) / 2), y / z / math.tan(math.radians(view) / 2)
    bx, by, bz = barrel_view_dir(p, SIGHTS, view, world)
    wx, wy = bx / bz / math.tan(math.radians(world) / 2), by / bz / math.tan(math.radians(world) / 2)
    assert (wx, wy) == pytest.approx((sx, sy), abs=1e-9)


@pytest.mark.parametrize('yaw,pitch', [(0, 0), (35, 10), (200, -40), (-120, 60)])
def test_view_to_world_matches_aim_direction(yaw, pitch):
    assert view_to_world(yaw, pitch, (0.0, 0.0, 1.0)) == pytest.approx(aim_direction(yaw, pitch))


def test_view_to_world_axes_are_right_handed_for_the_player():
    """Looking along +z: right is +x, up is +y (Ursina's frame)."""
    assert view_to_world(0, 0, (1.0, 0.0, 0.0)) == pytest.approx((1.0, 0.0, 0.0))
    assert view_to_world(0, 0, (0.0, 1.0, 0.0)) == pytest.approx((0.0, 1.0, 0.0))
    # looking up 30 degrees (negative pitch): the camera's "up" tilts backward
    up = view_to_world(0, -30, (0.0, 1.0, 0.0))
    assert up[2] < 0 and up[1] > 0


def spray(fa, shots=30, up=0.5, right=0.0, fps=120):
    peak = 0.0
    for i in range(round(shots * 0.08 * fps)):
        if i % round(0.08 * fps) == 0:
            fa.on_shot(up, right)
        fa.update(1.0 / fps)
        peak = max(peak, fa.drift[0])
    return peak


def test_recoil_drift_builds_up_during_a_burst_then_returns():
    d = FreeAimData()
    fa = FreeAim(d)
    fa.on_shot(0.5, 0.0)
    single = 0.0
    for _ in range(120):
        fa.update(1 / 120)
        single = max(single, fa.drift[0])
    assert single == pytest.approx(0.5, rel=0.02)
    fa = FreeAim(d)
    peak = spray(fa)
    assert peak > 3 * single                                              # the shots build up: the gun drifts well away from the centre
    for _ in range(240):
        fa.update(1 / 120)
    assert abs(fa.drift[0]) < 0.05 and abs(fa.drift[1]) < 0.05            # after firing stops, it returns


def test_drift_is_soft_limited():
    d = FreeAimData(drift_max=4.0)
    fa = FreeAim(d)
    for _ in range(200):
        fa.on_shot(2.0, 0.0)
        fa.update(0.01)
    assert 3.5 < fa.drift[0] <= 4.0


def test_rest_pose_changes_after_a_fast_turn_but_not_while_still():
    fa = FreeAim(FreeAimData())
    for _ in range(240):
        fa.update(1 / 120, 0.0)
    assert fa.rest_changes == 0
    for _ in range(30):
        fa.update(1 / 120, 200.0)                                         # fast turn
    assert fa.rest_changes == 0                                           # no change until it stops
    fa.update(1 / 120, 0.0)
    assert fa.rest_changes == 1
    before = list(fa.rest)
    for _ in range(240):
        fa.update(1 / 120, 0.0)
    assert fa.rest != before and fa.rest == pytest.approx(fa.rest_target, abs=0.05)


def test_rest_pose_changes_after_a_burst():
    fa = FreeAim(FreeAimData())
    fa.on_shot(0.5, 0.0)
    for _ in range(60):
        fa.update(1 / 120)
    assert fa.rest_changes == 1


def test_rest_pose_stays_inside_its_limits_and_differs_each_time():
    d = FreeAimData()
    fa = FreeAim(d)
    seen = set()
    for _ in range(50):
        fa._pick_rest()
        t = fa.rest_target
        assert abs(t[3]) <= d.rest_pitch and abs(t[4]) <= d.rest_yaw and abs(t[5]) <= d.rest_roll
        seen.add(round(t[4], 3))
    assert len(seen) > 40


def test_idle_drift_is_slow_and_small():
    d = FreeAimData()
    fa = FreeAim(d)
    trace = []
    for _ in range(1200):
        fa.update(1 / 120)
        trace.append(fa.pose()[4])
    assert max(abs(v) for v in trace) <= d.idle_yaw + 1e-9
    assert max(trace) - min(trace) > 0.1                                  # really drifts
    assert max(abs(b - a) for a, b in zip(trace, trace[1:])) < 0.02       # no jerky motion


def test_ads_calms_the_rest_pose_but_not_the_recoil():
    d = FreeAimData()
    fa = FreeAim(d)
    fa.rest = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
    fa.t = 0.0
    hip, ads = fa.pose(0.0), fa.pose(1.0)
    assert ads[4] == pytest.approx(hip[4] * d.ads_scale, abs=1e-6)
    fa.spring.x = [2.0, 0.0]
    fa.rest = [0.0] * 6
    fa.stress = 0.0
    assert abs(fa.pose(1.0)[3] - fa.drift[0]) < d.idle_pitch * d.ads_scale + 1e-6      # the kick part stays the same when aiming
    assert fa.drift[0] > 1.5


def test_stress_rises_with_shots_decays_and_shakes_harder_while_reloading():
    d = FreeAimData()
    fa = FreeAim(d)
    assert fa.stress == 0.0
    for _ in range(10):
        fa.on_shot(0.0, 0.0)
    assert fa.stress == pytest.approx(10 * d.stress_per_shot)
    sway_normal, sway_reload = [], []
    for _ in range(600):
        fa.t += 1 / 240
        sway_normal.append(fa.pose(0.0, False)[5])
        sway_reload.append(fa.pose(0.0, True)[5])
    spread = lambda v: max(v) - min(v)
    assert spread(sway_reload) > spread(sway_normal) * 1.2
    fa.stress = 0.5
    fa.update(1.0)
    assert fa.stress == pytest.approx(0.5 - d.stress_decay)


def test_free_aim_randomness_does_not_touch_other_generators():
    """Same seed, same result: the selftest is repeatable."""
    a, b = FreeAim(FreeAimData()), FreeAim(FreeAimData())
    for fa in (a, b):
        fa.on_shot(0.5, 0.1)
        for _ in range(100):
            fa.update(1 / 60, 90.0)
        fa.update(1 / 60, 0.0)
    assert a.pose() == b.pose()


def test_rest_pose_blends_out_when_aiming():
    data = SwayData()
    sway = Sway(data, ads_target_for(M4))
    inp = SwayInput(MoveState.IDLE, 0.0, 0.0, 0.0)
    hip = sway.update(1 / 60, inp)
    assert hip[1] == pytest.approx(data.rest_pose[1], abs=0.01)          # gun is low at the hip
    sway2 = Sway(data, ads_target_for(M4))
    ads = sway2.update(1 / 60, SwayInput(MoveState.IDLE, 0.0, 1.0, 0.0))
    target = ads_target_for(M4)
    assert ads[0] == pytest.approx(target[0], abs=0.002)                 # aiming returns to exactly the aim pose
    assert ads[1] == pytest.approx(target[1], abs=0.002)


# --- mouse drives the gun first ---
def mouse(fl, yaw, up=0.0, steps=1):
    cam = [0.0, 0.0]
    for _ in range(steps):
        a, b = fl.apply(yaw / steps, up / steps)
        cam[0] += a
        cam[1] += b
    return cam


def test_inside_the_zone_only_the_gun_moves():
    fl = FreeLook(FreeAimData())
    cam = mouse(fl, 4.0, 2.0, steps=10)
    assert cam == [0.0, 0.0]
    assert fl.offset == pytest.approx([4.0, 2.0])


def test_every_mouse_degree_is_accounted_for():
    """Total mouse = screen turn + gun offset: no turn is ever lost or added, even for very hard flicks."""
    fl = FreeLook(FreeAimData())
    for yaw, up in ((3.0, 1.0), (40.0, -7.0), (-90.0, 12.0), (1.0, 1.0)):
        before = list(fl.offset)
        cam = mouse(fl, yaw, up)
        assert cam[0] + fl.offset[0] - before[0] == pytest.approx(yaw)
        assert cam[1] + fl.offset[1] - before[1] == pytest.approx(up)


def test_the_gun_stays_inside_the_ellipse_and_the_screen_takes_the_rest():
    d = FreeAimData()
    fl = FreeLook(d)
    cam = mouse(fl, 100.0, steps=100)
    assert fl.radius() <= 1.0 + 1e-9
    assert fl.offset[0] == pytest.approx(d.zone_yaw, abs=0.2)
    assert cam[0] == pytest.approx(100.0 - fl.offset[0])
    fl = FreeLook(d)
    mouse(fl, 0.0, 100.0, steps=100)
    assert fl.offset[1] == pytest.approx(d.zone_pitch, abs=0.2)     # the vertical zone is narrower than the horizontal one
    fl = FreeLook(d)
    mouse(fl, 80.0, 80.0, steps=100)
    assert fl.radius() <= 1.0 + 1e-9


def test_screen_starts_turning_gradually_near_the_edge():
    d = FreeAimData()
    fl = FreeLook(d)
    shares = []
    for _ in range(200):
        a, _ = fl.apply(0.1, 0.0)
        shares.append(a / 0.1)
    assert shares[0] == 0.0
    assert shares[-1] > 0.85
    assert all(b >= a - 1e-6 for a, b in zip(shares, shares[1:]))   # increases gradually, no jump
    assert max(b - a for a, b in zip(shares, shares[1:])) < 0.15


def test_moving_back_inside_is_gun_only_even_near_the_edge():
    """Moving back toward the centre the screen stays still: centring is precise even when the gun is at the edge."""
    fl = FreeLook(FreeAimData())
    mouse(fl, 100.0, steps=100)
    cam = mouse(fl, -3.0, steps=10)
    assert cam == [0.0, 0.0]


def test_a_single_big_flick_equals_many_small_moves():
    a, b = FreeLook(FreeAimData()), FreeLook(FreeAimData())
    cam_a = mouse(a, 30.0, 5.0)
    cam_b = mouse(b, 30.0, 5.0, steps=60)
    assert cam_a[0] == pytest.approx(cam_b[0], abs=0.8)
    assert a.offset[0] == pytest.approx(b.offset[0], abs=0.8)


def test_recentering_turns_the_screen_without_moving_the_gun_in_the_world():
    fl = FreeLook(FreeAimData())
    mouse(fl, 8.0, 3.0)
    world = list(fl.offset)
    turned = [0.0, 0.0]
    for _ in range(120):
        c = fl.step(1 / 60)
        turned[0] += c[0]
        turned[1] += c[1]
    assert fl.offset[0] < 8.0 * 0.8
    assert fl.offset[0] + turned[0] == pytest.approx(world[0])
    assert fl.offset[1] + turned[1] == pytest.approx(world[1])


def test_walking_recenters_faster_than_standing():
    still, walking = FreeLook(FreeAimData()), FreeLook(FreeAimData())
    mouse(still, 8.0)
    mouse(walking, 8.0)
    for _ in range(60):
        still.step(1 / 60)
        walking.step(1 / 60, moving=True)
    assert walking.offset[0] < 0.6 * still.offset[0]


def test_recentering_is_frame_rate_independent():
    out = []
    for fps in (30, 240):
        fl = FreeLook(FreeAimData())
        mouse(fl, 8.0)
        for _ in range(fps):
            fl.step(1.0 / fps)
        out.append(fl.offset[0])
    assert out[0] == pytest.approx(out[1], rel=1e-6)


@pytest.mark.parametrize('kw,scale', [({'ads': 1.0}, 'zone_ads'), ({'sprint': 1.0}, 'zone_sprint'), ({'reloading': True}, 'zone_reload')])
def test_zone_shrinks_and_the_screen_compensates(kw, scale):
    d = FreeAimData(recenter_idle=0.0, recenter_move=0.0)
    fl = FreeLook(d)
    mouse(fl, 10.0)
    turned = 0.0
    for _ in range(120):
        turned += fl.step(1 / 60, **kw)[0]
    assert fl.scale == pytest.approx(getattr(d, scale), abs=0.01)
    assert fl.radius() <= 1.0 + 1e-9
    assert fl.offset[0] + turned == pytest.approx(10.0)             # the aim point does not jump


def test_turned_off_means_the_mouse_turns_the_screen_directly():
    d = FreeAimData(barrel_aim=False)
    fl = FreeLook(d)
    assert mouse(fl, 5.0, -2.0) == [5.0, -2.0]
    assert fl.offset == [0.0, 0.0]


def test_hand_spring_makes_the_gun_follow_smoothly():
    fl = FreeLook(FreeAimData())
    before = tuple(fl.offset)
    mouse(fl, 6.0)
    fl.step(1 / 60)
    fl.track(before)
    first = fl.shown[0]
    assert 0.0 <= first < 3.0                                       # not there yet
    last = first
    for _ in range(60):
        before = tuple(fl.offset)
        fl.step(1 / 60)
        fl.track(before)
        assert abs(fl.shown[0] - last) < 2.0                        # no jump
        last = fl.shown[0]
    assert last == pytest.approx(fl.offset[0], abs=0.25)           # the offset is also drifting slowly back to the centre, so the gun lags a little


def test_pose_points_the_gun_where_the_hand_is():
    d = FreeAimData()
    fl = FreeLook(d)
    mouse(fl, 5.0, 2.0)
    fl.spring.x = [0.0, 0.0]
    x, y, z, pitch, yaw, roll = fl.pose()
    assert (yaw, pitch) == pytest.approx((5.0, 2.0))
    assert x > 0 and y > 0 and z == 0.0
    assert roll == pytest.approx(5.0 * d.offset_roll)
