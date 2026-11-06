from dataclasses import replace

import pytest

from fps.core.movement import MoveState, smoothstep, target_speed
from fps.core.sway import Sway, SwayInput, ads_pose, apply_pose
from fps.weapon_data import M4, PlayerParams, SwayData

S = MoveState
D = SwayData(rest_pose=(0.0,) * 6)      # measure each component separately; the normal holding pose is checked in test_freeaim
NO_BREATH = replace(D, breath_x=0.0, breath_y=0.0, breath_pitch=0.0, breath_yaw=0.0)


def inp(state=S.IDLE, speed=0.0, ads=0.0, sprint=0.0, look=(0.0, 0.0), eye_dy=0.0, landed=0.0):
    return SwayInput(state, speed, ads, sprint, look, eye_dy, landed)


def run(sway, seconds, fps, make_input):
    dt = 1.0 / fps
    return [sway.update(dt, make_input(i * dt)) for i in range(round(seconds * fps))]


# --- ADS: sight line on the view axis ---
def test_ads_pose_puts_the_sight_line_on_the_view_axis():
    rear, front = M4.ads_sights
    pose = ads_pose(rear, front, 0.18)
    r = apply_pose(rear, pose)
    f = apply_pose(front, pose)
    assert r == pytest.approx((0.0, 0.0, 0.18), abs=1e-9)         # rear ring centred, 18 cm from the eye
    assert (f[0], f[1]) == pytest.approx((0.0, 0.0), abs=1e-9)    # front post also centred: looking through the ring, the post is exactly at the centre
    assert f[2] > r[2]


@pytest.mark.parametrize('rear,front', [
    ((0.07, -0.01, 0.15), (0.07, -0.005, 0.56)),
    ((0.10, -0.03, 0.10), (0.02, 0.01, 0.70)),                    # sight line tilted in both directions
    ((-0.05, 0.02, 0.20), (0.04, -0.04, 0.50)),
])
def test_ads_pose_is_general(rear, front):
    pose = ads_pose(rear, front, 0.25)
    r, f = apply_pose(rear, pose), apply_pose(front, pose)
    assert (r[0], r[1], r[2]) == pytest.approx((0.0, 0.0, 0.25), abs=1e-9)
    assert (f[0], f[1]) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_m4_ads_pose_is_a_small_correction_not_a_wild_swing():
    pose = ads_pose(*M4.ads_sights, M4.ads_eye_relief)
    assert abs(pose[0] + 0.0678) < 0.002                          # shifted left ~6.8 cm
    assert abs(pose[3]) < 1.0 and abs(pose[4]) < 1.0              # rotated less than 1 degree


def test_smoothstep_shape():
    assert (smoothstep(0), smoothstep(1), smoothstep(0.5)) == (0.0, 1.0, 0.5)
    assert smoothstep(-1) == 0.0 and smoothstep(2) == 1.0
    assert smoothstep(0.1) < 0.1 and smoothstep(0.9) > 0.9        # smooth at both ends
    v = [smoothstep(i / 100) for i in range(101)]
    assert v == sorted(v)


def test_ads_speed_blends_with_progress():
    p = PlayerParams()
    full = target_speed(S.WALK, p, 1.0)
    assert full == pytest.approx(p.walk_speed * p.ads_speed_multiplier)
    assert target_speed(S.WALK, p, 0.0) == p.walk_speed
    assert full < target_speed(S.WALK, p, 0.5) < p.walk_speed
    assert target_speed(S.WALK, p, True) == full                  # a bool still works


def test_sway_goes_to_the_ads_pose_and_back():
    pose = ads_pose(*M4.ads_sights, M4.ads_eye_relief)
    sw = Sway(NO_BREATH, pose)
    at_hip = sw.update(1 / 60, inp(ads=0.0))
    at_ads = sw.update(1 / 60, inp(ads=1.0))
    assert at_hip == pytest.approx((0,) * 6, abs=1e-9)
    assert at_ads == pytest.approx(pose, abs=1e-9)
    half = sw.update(1 / 60, inp(ads=0.5))
    assert half == pytest.approx(tuple(c * 0.5 for c in pose), abs=1e-9)   # smoothstep(0.5) = 0.5


# --- breathing ---
def breath_trace(sway, seconds=12.0, fps=60, **kw):
    return run(sway, seconds, fps, lambda t: inp(**kw))


def test_breathing_is_small_periodic_and_zero_mean():
    tr = breath_trace(Sway(D))
    xs = [p[0] for p in tr]
    assert max(xs) == pytest.approx(D.breath_x, rel=0.02) and min(xs) == pytest.approx(-D.breath_x, rel=0.02)
    assert sum(xs) / len(xs) == pytest.approx(0.0, abs=2e-4)
    assert max(abs(p[3]) for p in tr) <= D.breath_pitch + 1e-9
    # period 1 / 0.28 Hz: after exactly one period it returns to the same value
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


# --- mouse lag: second-order system driven by turn rate (core/sway.py MouseLag) ---
def flick(rate, seconds=0.15, fps=144, data=NO_BREATH, ads=0.0, total=1.5, axis=0, pattern=None):
    """Turns at a steady `rate` deg/s for `seconds`, then stops. Returns [(t, pose)]."""
    sw = Sway(data)
    dt = 1.0 / fps
    out = []
    for i in range(round(total * fps)):
        t = i * dt
        v = pattern(t) if pattern else (rate if t < seconds else 0.0)
        look = (v * dt, 0.0) if axis == 0 else (0.0, v * dt)
        out.append((t + dt, sw.update(dt, inp(ads=ads, look=look))))
    return out


def lag_stats(trace, end, axis=4):
    """(maximum offset, overshoot % of the maximum, settling time s after the mouse stops), signed: turning right gives a negative offset."""
    ys = [p[axis] for _, p in trace]
    sign = -1.0 if min(ys) < -max(ys) else 1.0
    ys = [sign * y for y in ys]
    peak_i = max(range(len(ys)), key=lambda i: ys[i])
    peak = ys[peak_i]
    over = max(0.0, -min(ys[peak_i:]))
    thresh = max(0.1 * peak, 0.05)
    last_big = max((t for (t, _), y in zip(trace, ys) if abs(y) > thresh), default=end)
    return peak, 100.0 * over / peak, max(0.0, last_big - end)


def test_mouse_lag_trails_the_turn_with_roll_and_shift():
    tr = flick(240)
    pose = min((p for _, p in tr), key=lambda p: p[4])             # when the gun is left furthest behind
    assert pose[4] < -3.0                                         # turn right: the barrel is left behind on the LEFT
    assert pose[5] < 0 and pose[0] < 0                            # roll left + shift left, same direction
    assert abs(pose[5]) == pytest.approx(abs(pose[4]) * D.lag_roll, rel=0.01)
    up = flick(240, axis=1)
    assert min(p[3] for _, p in up) < -2.0                        # look up, the gun lags downward
    assert min(p[1] for _, p in up) < 0
    left = flick(-240)
    assert max(p[4] for _, p in left) > 3.0                       # turn left: left behind on the RIGHT


def test_mouse_lag_grows_with_turn_speed_and_is_soft_clamped_not_flat():
    peaks = [lag_stats(flick(r), 0.15)[0] for r in (30, 60, 120, 240, 480, 960, 1920)]
    assert all(b > a for a, b in zip(peaks, peaks[1:]))           # monotonically increasing, NOT flattened at one level
    assert peaks[3] > 1.5 * 3.9                                   # a medium flick is clearly more than the old hard-clamp level (~3.9 deg)
    assert peaks[-1] < D.lag_max * 1.4                            # but it approaches a limit (peak overshoot at most ~1.3 x lag_max)
    assert peaks[-1] - peaks[-2] < 0.5 * (peaks[3] - peaks[2])    # curving off: each doubling of speed adds less and less


def test_mouse_lag_overshoots_a_little_and_settles_fast():
    peak, over, settle = lag_stats(flick(240), 0.15)
    assert 5.0 <= over <= 25.0                                    # the gun catches up, overshoots a bit, then shakes back
    assert 0.1 <= settle <= 0.5
    after = flick(240, total=3.0)[-1][1]
    assert after == pytest.approx((0,) * 6, abs=1e-3)             # finally returns fully to the centre


def test_small_slow_turns_barely_move_the_gun():
    assert lag_stats(flick(10, 1.0), 1.0)[0] < 0.5                # slow centring: under half a degree (the gun is heavier than the CoD version, on purpose)
    assert lag_stats(flick(20, 1.0), 1.0)[0] < 1.3
    assert lag_stats(flick(500, 0.02), 0.02)[0] < 0.6 * lag_stats(flick(240), 0.15)[0]   # a short 10 deg jerk lags clearly less than a 36 deg turn


@pytest.mark.parametrize('fps', [30, 60, 144, 500, 1000])
def test_mouse_lag_does_not_depend_on_fps(fps):
    ref = lag_stats(flick(240, fps=1000), 0.15)
    got = lag_stats(flick(240, fps=fps), 0.15)
    assert got[0] == pytest.approx(ref[0], rel=0.09)              # slow spring + 33 ms frame: the peak falls between two frames
    assert got[1] == pytest.approx(ref[1], abs=4.0)
    assert got[2] == pytest.approx(ref[2], abs=0.05)


def test_mouse_lag_ignores_how_the_mouse_counts_are_quantized():
    # same 36 deg in 0.15 s: discrete mouse counts bunched into a few frames (125 Hz mouse at 1000 FPS) vs an even turn
    smooth = lag_stats(flick(240, fps=1000), 0.15)[0]
    sw = Sway(NO_BREATH)
    trace = []
    for i in range(1500):
        look = (36.0 / 18 if i < 150 and i % 8 == 0 else 0.0, 0.0)   # 18 pulses, 2 deg each, 8 ms apart
        trace.append(((i + 1) / 1000, sw.update(1 / 1000, inp(look=look))))
    assert lag_stats(trace, 0.15)[0] == pytest.approx(smooth, rel=0.2)


def test_mouse_lag_when_aiming_is_the_configured_fraction():
    hip = lag_stats(flick(240), 0.15)[0]
    ads = lag_stats(flick(240, ads=1.0), 0.15)[0]
    assert ads == pytest.approx(hip * D.ads_multiplier, rel=0.01)
    mid = lag_stats(flick(240, ads=0.5), 0.15)[0]
    assert ads < mid < hip


def test_mouse_lag_follow_one_removes_the_steady_lag():
    follow = replace(NO_BREATH, lag_follow=1.0)
    steady = flick(100, 1.0, data=follow)
    assert abs(steady[130][1][4]) < 0.3                           # steady turn ~0.9 s: almost no offset
    base = flick(100, 1.0)
    assert abs(base[130][1][4]) > 2.0


def test_mouse_lag_flick_pose_keeps_the_gun_inside_sane_bounds():
    worst = [max(abs(c) for _, p in flick(r, 0.1) for c in (p[4], p[3], p[5])) for r in (400, 900, 3000)]
    assert max(worst) < 18.0                                      # degrees: even for frantic mouse jerks

# --- bob ---
def bob_y(state, speed, seconds=3.0, fps=120, data=NO_BREATH):
    sw = Sway(data)
    tr = run(sw, seconds, fps, lambda t: inp(state=state, speed=speed))
    return [p[1] for p in tr[len(tr) // 3:]], [p[3] for p in tr[len(tr) // 3:]]


def crossings(v):
    return sum(1 for a, b in zip(v, v[1:]) if a < 0 <= b)


def test_bob_cadence_follows_distance_not_time():
    # y bob has two beats per footstep cycle: frequency = 2 * speed * bob_rate / stride
    for state, speed, rate in ((S.WALK, 4.5, D.bob_rate), (S.WALK, 6.8, D.bob_rate), (S.SPRINT, 6.8, D.bob_sprint_rate)):
        y, _ = bob_y(state, speed, seconds=12.0)
        seconds = len(y) / 120
        assert crossings(y) / seconds == pytest.approx(2 * speed * rate / D.bob_stride, rel=0.08)
    # the same 9 m at different speeds gives the same number of beats
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
    assert amp(S.IDLE, 0.0) == 0.0 and amp(S.AIR, 4.5) == 0.0     # standing still or airborne: no bob


def test_bob_fades_out_smoothly_when_stopping_without_a_jump():
    sw = Sway(NO_BREATH)
    run(sw, 1.0, 120, lambda t: inp(state=S.WALK, speed=4.5))
    prev = sw.update(1 / 120, inp(state=S.WALK, speed=4.5))
    tr = run(sw, 0.6, 120, lambda t: inp(state=S.IDLE, speed=0.0))
    steps = [abs(b[1] - a[1]) for a, b in zip([prev] + tr, tr)]
    assert max(steps) < D.bob_y * 0.2                              # no lurch
    assert max(abs(p[1]) for p in tr[-20:]) < D.bob_y * 0.02       # 0.6 s later it is nearly still


def test_breathing_gives_way_to_bob_while_walking():
    sw = Sway(D)
    run(sw, 1.0, 60, lambda t: inp(state=S.WALK, speed=4.5))
    peak = max(abs(sw._breath(inp())[0]) for sw.clock in [i * 0.1 for i in range(100)])
    assert peak <= D.breath_x * 0.2 * 1.001                        # breath amplitude is only 20% once the bob is at full strength


# --- sprint ---
def test_sprint_pose_blends_in_and_ads_removes_it():
    sw = Sway(NO_BREATH)
    full = sw.update(1 / 60, inp(sprint=1.0))
    assert full == pytest.approx(D.sprint_pose, abs=1e-9)
    assert sw.update(1 / 60, inp(sprint=0.0)) == pytest.approx((0,) * 6, abs=1e-9)
    half = sw.update(1 / 60, inp(sprint=0.5))
    assert half == pytest.approx(tuple(c * 0.5 for c in D.sprint_pose), abs=1e-9)
    ads = sw.update(1 / 60, inp(sprint=1.0, ads=1.0))
    assert ads == pytest.approx((0,) * 6, abs=1e-9)                # ADS: no sprint pose any more (default ads_target = 0)


def test_sprint_pose_lowers_and_tilts_the_barrel_down():
    x, y, z, pitch_up, yaw_right, roll = D.sprint_pose
    assert y < -0.01 and pitch_up < -3 and yaw_right < -10         # lowered, barrel tipped down, angled to the left
    assert abs(y) < 0.06 and abs(pitch_up) < 15                    # but not too far: the gun must stay in the frame


# --- vertical inertia and landing ---
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
    assert hard == pytest.approx(D.land_peak[1], rel=0.05)         # exactly the configured peak offset at the reference speed
    assert last == pytest.approx((0,) * 6, abs=2e-3)               # metres and degrees: at rest 1 s later


def test_everything_returns_to_rest_when_inputs_stop():
    sw = Sway(NO_BREATH)
    run(sw, 2.0, 60, lambda t: inp(state=S.WALK, speed=4.5, look=(3.0, 1.0), eye_dy=0.01, landed=0.0))
    tr = run(sw, 2.0, 60, lambda t: inp())
    assert tr[-1] == pytest.approx((0,) * 6, abs=1e-3)
