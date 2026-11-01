import math
from dataclasses import replace

import pytest

from fps.core.movement import MoveState, smoothstep, target_speed
from fps.core.sway import Sway, SwayInput, ads_pose, apply_pose
from fps.weapon_data import M4, PlayerParams, SwayData

S = MoveState
D = SwayData()
NO_BREATH = replace(D, breath_x=0.0, breath_y=0.0, breath_pitch=0.0, breath_yaw=0.0)


def inp(state=S.IDLE, speed=0.0, ads=0.0, sprint=0.0, look=(0.0, 0.0), eye_dy=0.0, landed=0.0):
    return SwayInput(state, speed, ads, sprint, look, eye_dy, landed)


def run(sway, seconds, fps, make_input):
    dt = 1.0 / fps
    return [sway.update(dt, make_input(i * dt)) for i in range(round(seconds * fps))]


# --- ADS: đường ngắm trùng trục nhìn ---
def test_ads_pose_puts_the_sight_line_on_the_view_axis():
    rear, front = M4.ads_sights
    pose = ads_pose(rear, front, 0.18)
    r = apply_pose(rear, pose)
    f = apply_pose(front, pose)
    assert r == pytest.approx((0.0, 0.0, 0.18), abs=1e-9)         # vòng sau ở giữa, cách mắt 18 cm
    assert (f[0], f[1]) == pytest.approx((0.0, 0.0), abs=1e-9)    # cột trước cũng ở giữa: nhìn qua vòng thấy cột đúng tâm
    assert f[2] > r[2]


@pytest.mark.parametrize('rear,front', [
    ((0.07, -0.01, 0.15), (0.07, -0.005, 0.56)),
    ((0.10, -0.03, 0.10), (0.02, 0.01, 0.70)),                    # đường ngắm chếch cả hai phương
    ((-0.05, 0.02, 0.20), (0.04, -0.04, 0.50)),
])
def test_ads_pose_is_general(rear, front):
    pose = ads_pose(rear, front, 0.25)
    r, f = apply_pose(rear, pose), apply_pose(front, pose)
    assert (r[0], r[1], r[2]) == pytest.approx((0.0, 0.0, 0.25), abs=1e-9)
    assert (f[0], f[1]) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_m4_ads_pose_is_a_small_correction_not_a_wild_swing():
    pose = ads_pose(*M4.ads_sights, M4.ads_eye_relief)
    assert abs(pose[0] + 0.0678) < 0.002                          # dịch trái ~6,8 cm
    assert abs(pose[3]) < 1.0 and abs(pose[4]) < 1.0              # xoay dưới 1 độ


def test_smoothstep_shape():
    assert (smoothstep(0), smoothstep(1), smoothstep(0.5)) == (0.0, 1.0, 0.5)
    assert smoothstep(-1) == 0.0 and smoothstep(2) == 1.0
    assert smoothstep(0.1) < 0.1 and smoothstep(0.9) > 0.9        # êm hai đầu
    v = [smoothstep(i / 100) for i in range(101)]
    assert v == sorted(v)


def test_ads_speed_blends_with_progress():
    p = PlayerParams()
    full = target_speed(S.WALK, p, 1.0)
    assert full == pytest.approx(p.walk_speed * p.ads_speed_multiplier)
    assert target_speed(S.WALK, p, 0.0) == p.walk_speed
    assert full < target_speed(S.WALK, p, 0.5) < p.walk_speed
    assert target_speed(S.WALK, p, True) == full                  # bool vẫn dùng được


def test_sway_goes_to_the_ads_pose_and_back():
    pose = ads_pose(*M4.ads_sights, M4.ads_eye_relief)
    sw = Sway(NO_BREATH, pose)
    at_hip = sw.update(1 / 60, inp(ads=0.0))
    at_ads = sw.update(1 / 60, inp(ads=1.0))
    assert at_hip == pytest.approx((0,) * 6, abs=1e-9)
    assert at_ads == pytest.approx(pose, abs=1e-9)
    half = sw.update(1 / 60, inp(ads=0.5))
    assert half == pytest.approx(tuple(c * 0.5 for c in pose), abs=1e-9)   # smoothstep(0,5) = 0,5


# --- thở ---
def breath_trace(sway, seconds=12.0, fps=60, **kw):
    return run(sway, seconds, fps, lambda t: inp(**kw))


def test_breathing_is_small_periodic_and_zero_mean():
    tr = breath_trace(Sway(D))
    xs = [p[0] for p in tr]
    assert max(xs) == pytest.approx(D.breath_x, rel=0.02) and min(xs) == pytest.approx(-D.breath_x, rel=0.02)
    assert sum(xs) / len(xs) == pytest.approx(0.0, abs=2e-4)
    assert max(abs(p[3]) for p in tr) <= D.breath_pitch + 1e-9
    # chu kỳ 1 / 0,28 Hz: sau đúng một chu kỳ về cùng giá trị
    sw = Sway(D)
    period = 1.0 / D.breath_freq
    a = sw.update(0.0, inp())
    sw.clock = 0.0
    sw2 = Sway(D)
    sw2.clock = period
    assert sw2.update(0.0, inp())[0] == pytest.approx(a[0], abs=1e-9)


def test_ads_calms_everything_to_the_configured_fraction():
    hip = breath_trace(Sway(D), ads=0.0)
    ads = breath_trace(Sway(D), ads=1.0)
    ratio = (max(p[0] for p in ads) - min(p[0] for p in ads)) / (max(p[0] for p in hip) - min(p[0] for p in hip))
    assert ratio == pytest.approx(D.ads_multiplier, rel=0.02)


# --- lag theo chuột ---
def test_mouse_lag_trails_the_turn_and_springs_back():
    sw = Sway(NO_BREATH)
    first = sw.update(1 / 60, inp(look=(5.0, 0.0)))               # quay phải 5 độ
    assert first[4] == pytest.approx(-5.0 * D.lag_gain, rel=0.1)  # súng lệch TRÁI
    assert first[5] < 0                                           # kèm nghiêng
    up = Sway(NO_BREATH).update(1 / 60, inp(look=(0.0, 5.0)))
    assert up[3] < 0                                              # ngẩng lên thì súng trễ xuống
    tr = run(sw, 1.5, 60, lambda t: inp())
    assert abs(tr[-1][4]) < 1e-3 and abs(tr[-1][3]) < 1e-3        # về giữa


def test_mouse_lag_is_clamped():
    sw = Sway(NO_BREATH)
    p = sw.update(1 / 60, inp(look=(90.0, 0.0)))
    assert abs(p[4]) <= D.lag_max + 1e-9


@pytest.mark.parametrize('fps', [30, 60, 144, 500])
def test_mouse_lag_return_does_not_depend_on_fps(fps):
    sw = Sway(NO_BREATH)
    sw.update(1 / fps, inp(look=(5.0, 0.0)))
    tr = run(sw, 0.3, fps, lambda t: inp())
    assert abs(tr[-1][4]) < 0.35                                   # từ 1,75 độ còn dưới 0,35 độ sau 0,3 s
    ref = Sway(NO_BREATH)
    ref.update(1 / 1000, inp(look=(5.0, 0.0)))
    ref_tr = run(ref, 0.3, 1000, lambda t: inp())
    assert tr[-1][4] == pytest.approx(ref_tr[-1][4], abs=0.12)


# --- bob ---
def bob_y(state, speed, seconds=3.0, fps=120, data=NO_BREATH):
    sw = Sway(data)
    tr = run(sw, seconds, fps, lambda t: inp(state=state, speed=speed))
    return [p[1] for p in tr[len(tr) // 3:]], [p[3] for p in tr[len(tr) // 3:]]


def crossings(v):
    return sum(1 for a, b in zip(v, v[1:]) if a < 0 <= b)


def test_bob_cadence_follows_distance_not_time():
    # y bob có hai nhịp mỗi chu kỳ chân: tần số = 2 * tốc độ * bob_rate / bước chân
    for state, speed, rate in ((S.WALK, 4.5, D.bob_rate), (S.WALK, 6.8, D.bob_rate), (S.SPRINT, 6.8, D.bob_sprint_rate)):
        y, _ = bob_y(state, speed, seconds=12.0)
        seconds = len(y) / 120
        assert crossings(y) / seconds == pytest.approx(2 * speed * rate / D.bob_stride, rel=0.08)
    # cùng quãng đường 9 m, tốc độ khác nhau, cùng số nhịp
    counts = []
    for speed in (3.0, 4.5):
        y, _ = bob_y(S.WALK, speed, seconds=9.0 / speed * 1.5)
        counts.append(crossings(y) / (len(y) / 120) * (9.0 / speed))
    assert counts[0] == pytest.approx(counts[1], rel=0.1)


def test_bob_amplitude_by_state():
    def amp(state, speed):
        y, _ = bob_y(state, speed)
        return max(y)
    walk, sprint, crouch = amp(S.WALK, 4.5), amp(S.SPRINT, 6.8), amp(S.CROUCH_WALK, 2.2)
    assert walk == pytest.approx(D.bob_y, rel=0.05)
    assert sprint == pytest.approx(D.bob_y * D.bob_sprint_multiplier, rel=0.05)
    assert crouch == pytest.approx(D.bob_y * D.bob_crouch_multiplier, rel=0.05)
    assert amp(S.IDLE, 0.0) == 0.0 and amp(S.AIR, 4.5) == 0.0     # đứng yên hoặc trên không: không bob


def test_bob_fades_out_smoothly_when_stopping_without_a_jump():
    sw = Sway(NO_BREATH)
    run(sw, 1.0, 120, lambda t: inp(state=S.WALK, speed=4.5))
    prev = sw.update(1 / 120, inp(state=S.WALK, speed=4.5))
    tr = run(sw, 0.6, 120, lambda t: inp(state=S.IDLE, speed=0.0))
    steps = [abs(b[1] - a[1]) for a, b in zip([prev] + tr, tr)]
    assert max(steps) < D.bob_y * 0.2                              # không nhảy cục
    assert max(abs(p[1]) for p in tr[-20:]) < D.bob_y * 0.02       # 0,6 s sau đã gần như yên


def test_breathing_gives_way_to_bob_while_walking():
    sw = Sway(D)
    run(sw, 1.0, 60, lambda t: inp(state=S.WALK, speed=4.5))
    peak = max(abs(sw._breath(inp())[0]) for sw.clock in [i * 0.1 for i in range(100)])
    assert peak <= D.breath_x * 0.2 * 1.001                        # biên độ thở chỉ còn 20% khi bob đã đầy


# --- chạy nước rút ---
def test_sprint_pose_blends_in_and_ads_removes_it():
    sw = Sway(NO_BREATH)
    full = sw.update(1 / 60, inp(sprint=1.0))
    assert full == pytest.approx(D.sprint_pose, abs=1e-9)
    assert sw.update(1 / 60, inp(sprint=0.0)) == pytest.approx((0,) * 6, abs=1e-9)
    half = sw.update(1 / 60, inp(sprint=0.5))
    assert half == pytest.approx(tuple(c * 0.5 for c in D.sprint_pose), abs=1e-9)
    ads = sw.update(1 / 60, inp(sprint=1.0, ads=1.0))
    assert ads == pytest.approx((0,) * 6, abs=1e-9)                # ADS: không còn tư thế chạy (ads_target mặc định = 0)


def test_sprint_pose_lowers_and_tilts_the_barrel_down():
    x, y, z, pitch_up, yaw_right, roll = D.sprint_pose
    assert y < -0.01 and pitch_up < -3 and yaw_right < -10         # hạ xuống, chúc nòng xuống, chếch sang trái
    assert abs(y) < 0.06 and abs(pitch_up) < 15                    # nhưng không quá tay: súng phải còn nằm trong khung hình


# --- quán tính dọc và chạm đất ---
def test_gun_lags_below_when_the_camera_rises_and_above_when_it_drops():
    up = Sway(NO_BREATH).update(1 / 60, inp(eye_dy=0.1))
    down = Sway(NO_BREATH).update(1 / 60, inp(eye_dy=-0.1))
    assert up[1] < 0 < down[1]


def test_vertical_lag_is_clamped():
    sw = Sway(NO_BREATH)
    for _ in range(100):
        p = sw.update(1 / 60, inp(eye_dy=1.0))
    assert p[1] >= -D.vlag_max - 1e-9


def test_landing_dips_the_gun_in_proportion_to_impact_then_settles():
    def dip(speed):
        sw = Sway(NO_BREATH)
        tr = [sw.update(1 / 240, inp(landed=speed))] + run(sw, 1.0, 240, lambda t: inp())
        return min(p[1] for p in tr), min(p[2] for p in tr), tr[-1]
    soft, soft_z, _ = dip(2.0)
    hard, hard_z, last = dip(6.4)
    assert hard < soft < 0 and hard_z < soft_z < 0
    assert hard == pytest.approx(D.land_peak[1], rel=0.05)         # đúng độ lệch đỉnh cấu hình ở tốc độ tham chiếu
    assert last == pytest.approx((0,) * 6, abs=2e-3)               # mét và độ: 1 s sau đã yên


def test_everything_returns_to_rest_when_inputs_stop():
    sw = Sway(NO_BREATH)
    run(sw, 2.0, 60, lambda t: inp(state=S.WALK, speed=4.5, look=(3.0, 1.0), eye_dy=0.01, landed=0.0))
    tr = run(sw, 2.0, 60, lambda t: inp())
    assert tr[-1] == pytest.approx((0,) * 6, abs=1e-3)
