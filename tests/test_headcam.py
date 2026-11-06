"""Camera đầu (core/headcam.py): nhún / lắc theo bước, rung tay, nhảy và chạm đất, liếc súng khi nạp. Toán thuần, không mở cửa sổ."""
import math
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fps.core.headcam import HeadCam, ReloadState, footfall, glance_weight, reload_state
from fps.core.movement import MoveState
from fps.core.sway import SwayInput
from fps.weapon_data import M4, HeadCamData

WALK, SPRINT = 4.5, 6.8
RELOAD, EMPTY = M4.clips['reload'], M4.clips['reload_empty']


def still(look=(0.0, 0.0), ads=0.0, state=MoveState.IDLE, speed=0.0, landed=0.0, jumped=0.0):
    return SwayInput(state, speed, ads, 0.0, look, 0.0, landed, jumped)


def quiet(**changes) -> HeadCamData:
    """Không trôi lúc đứng yên: đo từng phần cho rõ."""
    return replace(HeadCamData(), idle_pitch=0.0, idle_yaw=0.0, idle_roll=0.0, idle_y=0.0, **changes)


def run_head(head, inp, seconds=1.0, phase=0.0, lateral=0.0, forward=0.0, fps=120):
    for _ in range(round(seconds * fps)):
        head.update(1.0 / fps, inp, phase, lateral, forward)


def stride_rate(speed, sprint):
    """Pha bước chân như Sway (rad/s) theo số mặc định."""
    s = M4.sway
    rate = s.bob_sprint_rate if sprint else s.bob_rate
    return 2.0 * math.pi * speed * rate / s.bob_stride


def walk_samples(d, state, speed, seconds=4.0, fps=120, ads=0.0):
    """Đi / chạy đều với pha tăng như Sway; trả các tư thế camera sau 1,5 s đầu (biên độ đã ổn định)."""
    head = HeadCam(d)
    w = stride_rate(speed, state is MoveState.SPRINT)
    out = []
    for i in range(round(seconds * fps)):
        t = i / fps
        head.update(1.0 / fps, still(state=state, speed=speed, ads=ads), (w * t) % (2 * math.pi))
        if t > 1.5:
            out.append(head.camera_pose())
    return out


def spread(poses, axis):
    values = [p[axis] for p in poses]
    return max(values) - min(values)


# --- thân người (giữ nguyên hành vi cũ) ---
def test_turning_right_rolls_the_camera_and_the_body_arrives_late():
    d = HeadCamData()
    head = HeadCam(d)
    inp = still(look=(100.0 / 120.0, 0.0))                  # 100 độ/s
    head.update(1 / 120, inp, 0.0)
    first = head.camera_pose()[5]
    run_head(head, inp)
    settled = head.camera_pose()[5]
    assert settled == pytest.approx(min(100 * d.turn_roll, d.turn_roll_max), abs=d.idle_roll + 0.05)
    assert abs(first) < abs(settled)


def test_roll_from_turning_is_limited():
    d = HeadCamData()
    head = HeadCam(d)
    run_head(head, still(look=(3000.0 / 120.0, 0.0)))
    assert abs(head.camera_pose()[5]) <= d.turn_roll_max + d.idle_roll + 0.1


def test_strafing_rolls_toward_the_movement():
    head = HeadCam(HeadCamData())
    run_head(head, still(state=MoveState.WALK, speed=4.0), lateral=4.0)
    assert head.camera_pose()[5] > 1.0


def test_standing_still_drifts_slowly():
    d = HeadCamData()
    head = HeadCam(d)
    values = []
    for _ in range(1200):
        head.update(1 / 120, still(), 0.0)
        values.append(head.camera_pose()[4])
    assert 0.05 < max(values) - min(values) <= 2 * d.idle_yaw
    assert max(abs(b - a) for a, b in zip(values, values[1:])) < 0.01


# --- bước chân ---
def test_footfall_wave_bottoms_out_when_the_foot_lands_and_averages_zero():
    for sharp in (0.0, 0.6, 1.0):
        values = [footfall(2 * math.pi * i / 3600, sharp) for i in range(3600)]
        assert sum(values) / len(values) == pytest.approx(0.0, abs=1e-3)
        assert min(values) == pytest.approx(-1.0, abs=1e-6)
        assert footfall(0.75 * math.pi, sharp) == pytest.approx(-1.0)
        assert footfall(1.75 * math.pi, sharp) == pytest.approx(-1.0)
    assert footfall(1.0, 0.0) == pytest.approx(math.sin(2.0))                   # sharp 0 = đúng hình sin cũ (cùng pha bob của súng)


def test_steps_bob_in_step_with_the_gun_phase():
    d = HeadCamData()
    head = HeadCam(d)
    run_head(head, still(state=MoveState.WALK, speed=WALK))
    head.update(1 / 120, still(state=MoveState.WALK, speed=WALK), math.pi / 4)
    high = head.camera_pose()[1]
    head.update(1 / 120, still(state=MoveState.WALK, speed=WALK), 3 * math.pi / 4)    # chân chạm đất (tiếng bước chân)
    low = head.camera_pose()[1]
    assert high - low > 1.5 * d.step_y


def test_walking_is_clearly_visible_but_not_dizzy():
    poses = walk_samples(HeadCamData(), MoveState.WALK, WALK)
    assert 0.025 < spread(poses, 1) < 0.06                 # nhún 2,5-6 cm đỉnh-đỉnh
    assert 1.5 < spread(poses, 5) < 4.0                     # nghiêng ±~1 độ
    assert spread(poses, 3) < 3.5


def test_sprinting_shakes_harder_than_walking_and_leans_forward():
    walk = walk_samples(HeadCamData(), MoveState.WALK, WALK)
    run = walk_samples(HeadCamData(), MoveState.SPRINT, SPRINT)
    assert spread(run, 5) > 1.8 * spread(walk, 5)          # nghiêng trái phải theo nhịp chân
    assert spread(run, 1) > 1.3 * spread(walk, 1)
    assert 4.0 < spread(run, 5) < 7.5                       # ~ ±2,6 độ
    mean_pitch = sum(p[3] for p in run) / len(run)
    assert mean_pitch < -0.8 * HeadCamData().sprint_lean   # chúi tới


def test_crouch_walk_is_gentler():
    walk = walk_samples(HeadCamData(), MoveState.WALK, 2.2)
    crouch = walk_samples(HeadCamData(), MoveState.CROUCH_WALK, 2.2)
    assert spread(crouch, 1) < 0.75 * spread(walk, 1)


def hand_shake(state, speed, seconds=3.0, fps=240):
    """Độ lệch chuẩn của pitch khi pha bước giữ nguyên (chỉ còn rung tay): đo riêng lớp tần số cao."""
    head = HeadCam(quiet())
    values = []
    for i in range(round(seconds * fps)):
        head.update(1.0 / fps, still(state=state, speed=speed), 0.3)
        if i / fps > 1.0:
            values.append(head.camera_pose()[3])
    mean = sum(values) / len(values)
    jumps = max(abs(b - a) for a, b in zip(values, values[1:]))
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)), jumps


def test_hand_shake_grows_with_speed_and_is_strongest_when_sprinting():
    idle, _ = hand_shake(MoveState.IDLE, 0.0)
    walk, _ = hand_shake(MoveState.WALK, WALK)
    run, jumps = hand_shake(MoveState.SPRINT, SPRINT)
    assert idle < 1e-6
    assert walk > 0.02
    assert run > 2.0 * walk
    assert jumps < 0.1                                      # mượt: không nhảy cục giữa hai khung 240 FPS


# --- nhảy và chạm đất ---
def test_jump_kicks_up_at_takeoff():
    d = quiet()
    head = HeadCam(d)
    run_head(head, still(), seconds=0.2)
    head.update(1 / 120, still(state=MoveState.AIR, jumped=d.land_reference_speed), 0.0)
    peak = 0.0
    for _ in range(40):
        head.update(1 / 120, still(state=MoveState.AIR), 0.0)
        peak = max(peak, head.camera_pose()[3])
    assert peak > 0.8 * d.jump_pitch


def test_landing_slams_down_bounces_back_and_settles():
    d = quiet()
    head = HeadCam(d)
    run_head(head, still(), seconds=0.2)
    head.update(1 / 120, still(landed=d.land_reference_speed), 0.0)
    pitches, ys = [], []
    for _ in range(60):
        head.update(1 / 120, still(), 0.0)
        pitches.append(head.camera_pose()[3])
        ys.append(head.camera_pose()[1])
    low = min(pitches)
    assert low < -0.85 * d.land_pitch
    assert min(ys) < -0.85 * d.land_y
    assert pitches.index(low) < 25                          # dằn trong ~0,2 s đầu
    assert max(pitches[pitches.index(low):]) > 0.1 * d.land_pitch   # nảy lại
    run_head(head, still(), seconds=1.5)
    assert abs(head.camera_pose()[3]) < 0.05


def test_harder_landing_slams_harder():
    def low(speed):
        d = quiet()
        head = HeadCam(d)
        head.update(1 / 120, still(landed=speed), 0.0)
        out = 0.0
        for _ in range(60):
            head.update(1 / 120, still(), 0.0)
            out = min(out, head.camera_pose()[3])
        return out
    assert low(3.0) > 0.6 * low(6.4)
    assert low(30.0) > -HeadCamData().land_pitch * HeadCamData().land_max * 1.05      # rơi rất cao vẫn có trần


def test_airborne_sways_gently():
    d = quiet()
    head = HeadCam(d)
    values = []
    for i in range(240):
        head.update(1 / 120, still(state=MoveState.AIR), 0.0)
        if i > 60:
            values.append(head.camera_pose()[5])
    assert 0.05 < max(values) - min(values) < 4 * d.air_sway


# --- liếc súng khi nạp ---
def stub_handling(key, clip, t, speed=1.0):
    return SimpleNamespace(key=key, clip=clip, t=t, speed=speed)


def test_reload_state_reads_only_reloads():
    assert reload_state(None) is None
    assert reload_state(stub_handling(None, None, 0.0)) is None
    assert reload_state(stub_handling('draw', M4.clips['draw'], 0.2)) is None
    rs = reload_state(stub_handling('reload', RELOAD, 1.5, 1.5))
    assert rs.elapsed == pytest.approx(1.0)
    assert rs.settle_time == pytest.approx((RELOAD.settle - RELOAD.start) / 30.0 / 1.5)


def run_reload(head, clip, fps=120, speed=1.0, until=None, inp=None, cancel_at=None, after=0.0):
    """Chạy một lần nạp như Handling (t tính theo clip), rồi `after` giây không nạp. Trả [(giây, camera pose, glance)]."""
    inp = inp or still()
    out, t, real = [], 0.0, 0.0
    end = clip.duration if until is None else until
    while t < end:
        if cancel_at is not None and real >= cancel_at:
            break
        t += speed / fps
        real += 1.0 / fps
        rs = ReloadState(clip, t, speed) if t < clip.duration else None
        head.update(1.0 / fps, inp, 0.0, reload=rs)
        out.append((real, head.camera_pose(), head.glance))
    for _ in range(round(after * fps)):
        real += 1.0 / fps
        head.update(1.0 / fps, inp, 0.0, reload=None)
        out.append((real, head.camera_pose(), head.glance))
    return out


def test_glance_looks_down_at_the_gun_mid_reload_and_returns_before_ready():
    d = quiet()
    for clip in (RELOAD, EMPTY):
        rows = run_reload(HeadCam(d), clip)
        rs = ReloadState(clip, 0.0)
        mid = [r for r in rows if 0.6 < r[0] < rs.settle_time - d.glance_out_lead - 0.05]
        assert all(g == pytest.approx(1.0) for _, _, g in mid)
        assert max(p[3] for _, p, _ in mid) < -0.85 * d.glance_pitch
        assert min(p[3] for _, p, _ in mid) > -1.2 * d.glance_pitch
        assert all(p[4] > 0 for _, p, _ in mid)                 # quay về phía súng (bên phải)
        # đã ngẩng hẳn TRƯỚC khi súng sẵn sàng bắn (hết clip)
        late = [r for r in rows if r[0] >= clip.duration - 0.3]
        assert late and all(g == 0.0 for _, _, g in late)
        assert all(abs(p[3]) < 0.3 for _, p, _ in late)
        # vào mượt trong ~0,3-0,4 s
        start = [g for t, _, g in rows if t <= d.glance_in_delay + d.glance_in_time + 0.01]
        assert start[0] < 0.05 and start[-1] == pytest.approx(1.0, abs=0.01)
        assert max(abs(b - a) for (_, _, a), (_, _, b) in zip(rows, rows[1:])) < 0.06   # không giật


def test_empty_reload_holds_the_glance_longer():
    def released(clip):
        rows = run_reload(HeadCam(quiet()), clip)
        return next(t for t, _, g in rows if t > 1.0 and g < 0.5)
    assert released(EMPTY) > released(RELOAD) + 0.15


def test_glance_follows_reload_speed():
    d = HeadCamData()
    fast = ReloadState(RELOAD, 0.0, 1.5)
    assert glance_weight(d, ReloadState(RELOAD, (fast.settle_time + d.glance_out_time) * 1.5, 1.5)) == 0.0
    assert glance_weight(d, ReloadState(RELOAD, 1.0 * 1.5, 1.5)) == pytest.approx(1.0)


def test_cancel_returns_smoothly_within_a_quarter_second():
    d = quiet()
    head = HeadCam(d)
    rows = run_reload(head, RELOAD, cancel_at=1.2, after=0.4)    # trước mốc băng vào chỗ (2,0 s)
    i = next(k for k, r in enumerate(rows) if r[0] > 1.2)
    assert rows[i - 1][2] == pytest.approx(1.0)
    assert rows[i][2] > 0.9                                    # không bật về ngay
    back = [r for r in rows if r[0] >= 1.2 + 0.25]
    assert all(g == 0.0 for _, _, g in back)
    assert all(abs(p[3]) < 0.3 for _, p, _ in back)


def test_new_reload_during_the_return_does_not_snap():
    d = quiet()
    head = HeadCam(d)
    run_reload(head, RELOAD, cancel_at=1.0)
    head.update(1 / 120, still(), 0.0, reload=None)
    before = head.glance
    head.update(1 / 120, still(), 0.0, reload=ReloadState(RELOAD, 1 / 120))
    assert head.glance == pytest.approx(before, abs=0.05)


def test_magazine_seating_gives_a_small_nod():
    d = quiet(glance_drift=0.0)
    a, b = HeadCam(d), HeadCam(replace(d, glance_seat_nod=0.0))
    swap = RELOAD.swap_time
    rows_a = run_reload(a, RELOAD, until=swap + 0.25)
    rows_b = run_reload(b, RELOAD, until=swap + 0.25)
    dip = min(pa[3] - pb[3] for (t, pa, _), (_, pb, _) in zip(rows_a, rows_b) if t > swap)
    assert -1.3 * d.glance_seat_nod < dip < -0.6 * d.glance_seat_nod


def test_gun_rises_with_the_glance_and_follows_normal_motion_partly():
    d = quiet(glance_drift=0.0)
    head = HeadCam(d)
    run_reload(head, RELOAD, until=1.2)
    cam, gun, glance = head.camera_pose(), head.gun_pose(), head.glance_pose()
    move = head.move_pose()
    for c, g, q, m in zip(cam, gun, glance, move):
        assert c == pytest.approx(q + m)
        assert g == pytest.approx(-q * d.glance_follow - m * d.gun_follow)
    assert gun[3] > 0.85 * d.glance_pitch                      # súng ngóc lên = đi lên giữa khung khi đầu cúi


def test_glance_is_not_reduced_by_aiming_but_movement_is():
    d = HeadCamData()
    a, b = HeadCam(d), HeadCam(d)
    run_reload(a, RELOAD, until=1.2, inp=still(ads=0.0))
    run_reload(b, RELOAD, until=1.2, inp=still(ads=1.0))
    assert b.glance_pose() == a.glance_pose()
    hip = walk_samples(HeadCamData(), MoveState.WALK, WALK)
    ads = walk_samples(HeadCamData(), MoveState.WALK, WALK, ads=1.0)
    assert spread(ads, 5) == pytest.approx(spread(hip, 5) * d.ads_multiplier, rel=0.02)


# --- độc lập FPS ---
def scripted(fps):
    """Đi 1 s -> chạy 1 s -> nhảy, 0,5 s trên không, chạm đất -> đứng nạp 1,5 s. Trả tư thế camera ở vài mốc thời gian."""
    head = HeadCam(HeadCamData())

    def at(seconds):                                         # khung bắt đầu đúng lúc `seconds` (so sánh số nguyên, khỏi lệch float)
        return round(seconds * fps)
    marks = {at(m) - 1: m for m in (0.9, 1.9, 2.1, 2.5 + 2 / 30, 2.7, 3.4, 4.0)}     # tư thế SAU khung i ứng với thời điểm (i + 1) / fps
    out, phase, reload_t = {}, 0.0, 0.0
    dt = 1.0 / fps
    for i in range(at(4.2)):
        if i < at(1.0):
            inp, speed, sprint = still(state=MoveState.WALK, speed=WALK), WALK, False
        elif i < at(2.0):
            inp, speed, sprint = still(state=MoveState.SPRINT, speed=SPRINT), SPRINT, True
        elif i < at(2.5):
            inp, speed, sprint = still(state=MoveState.AIR, speed=SPRINT, jumped=6.4 if i == at(2.0) else 0.0), 0.0, False
        else:
            inp, speed, sprint = still(landed=6.4 if i == at(2.5) else 0.0), 0.0, False
        phase = (phase + stride_rate(speed, sprint) * dt) % (2 * math.pi)
        rs = None
        if i >= at(2.6):
            reload_t += dt
            rs = ReloadState(RELOAD, reload_t)
        head.update(dt, inp, phase, 0.0, speed * 0.9, reload=rs)
        if i in marks:
            out[marks[i]] = head.camera_pose()
    return out


def test_head_motion_is_frame_rate_independent():
    a, b = scripted(30), scripted(240)
    for m in a:
        for axis, tol in ((0, 0.001), (1, 0.001), (3, 0.15), (4, 0.15), (5, 0.15)):     # đo được: lệch < 0,07 độ, < 0,1 mm
            assert a[m][axis] == pytest.approx(b[m][axis], abs=tol), (m, axis)


def test_turning_roll_is_frame_rate_independent():
    results = []
    for fps in (30, 240):
        head = HeadCam(HeadCamData())
        for _ in range(fps):
            head.update(1.0 / fps, still(look=(100.0 / fps, 0.0)), 0.0)
        results.append(head.camera_pose()[5])
    assert results[0] == pytest.approx(results[1], abs=0.05)
