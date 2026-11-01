import dataclasses

import pytest

from fps.core.shake import Shake, hash_unit, smooth_noise
from fps.weapon_data import M4

D = M4.shake
SHOT_INTERVAL = 60.0 / M4.rpm


def burst_trace(shots, fps, seed=None, ads=0.0, settle=0.0, data=D):
    """Bắn `shots` phát liên tục (750 phát/phút) ở `fps`, theo đúng thứ tự của Combat: on_shot(tuổi) của khung rồi update(dt).
    Trả về ([(thời gian cuối khung, trauma, camera_pose)] mỗi khung, Shake)."""
    sh = Shake(data, seed)
    dt = 1.0 / fps
    out = []
    fired = 0
    frames = round((shots * SHOT_INTERVAL + settle) * fps) + 1
    for i in range(1, frames + 1):
        t1 = i * dt
        while fired < shots and fired * SHOT_INTERVAL <= t1 + 1e-9:
            sh.on_shot(max(0.0, t1 - fired * SHOT_INTERVAL))
            fired += 1
        sh.update(dt)
        out.append((t1, sh.trauma, sh.camera_pose(ads)))
    return out, sh


def test_noise_is_bounded_deterministic_and_smooth():
    vals = [smooth_noise(7, a, u / 50.0) for a in range(6) for u in range(-500, 500)]
    assert max(abs(v) for v in vals) <= 1.0 + 1e-12
    assert max(abs(v) for v in vals) > 0.9                      # dùng hết dải
    assert smooth_noise(7, 2, 3.37) == smooth_noise(7, 2, 3.37)
    assert smooth_noise(7, 2, 3.37) != smooth_noise(8, 2, 3.37)    # seed khác -> đường khác
    assert smooth_noise(7, 2, 3.37) != smooth_noise(7, 3, 3.37)    # trục khác -> đường khác
    # mượt: bước 1/1000 ô đổi không quá ~0,01 (không phải nhiễu trắng)
    steps = [abs(smooth_noise(7, 0, (k + 1) / 1000.0) - smooth_noise(7, 0, k / 1000.0)) for k in range(5000)]
    assert max(steps) < 0.01
    assert hash_unit(1, 0, -5) == hash_unit(1, 0, -5)


def test_single_shot_dies_exactly_on_time():
    sh = Shake(D)
    sh.on_shot()
    sh.update(0.0)
    assert sh.trauma == pytest.approx(D.fire_trauma)
    life = D.fire_trauma / D.fire_decay
    dt = 1.0 / 240
    t = 0.0
    while t < life - 2 * dt:
        sh.update(dt)
        t += dt
    assert sh.trauma > 0 and sh.active
    for _ in range(4):
        sh.update(dt)
    assert sh.trauma == 0.0
    assert sh.camera_pose() == (0.0,) * 6
    assert not sh.active


def test_single_shot_is_a_light_touch_and_burst_is_bigger():
    sh = Shake(D)
    sh.on_shot()
    sh.update(0.0)
    single = sh.amplitude
    trace, _ = burst_trace(30, 240)
    assert single < 0.15
    assert max(tr ** D.power for _, tr, _ in trace) > 4 * single


@pytest.mark.parametrize('fps', [30, 60, 144, 1000])
def test_burst_trauma_is_clamped_and_pose_within_ceiling(fps):
    trace, _ = burst_trace(60, fps, settle=0.5)       # hai băng liền
    cap = D.fire_max_trauma
    assert max(tr for _, tr, _ in trace) == pytest.approx(cap)      # có chạm trần
    assert all(tr <= cap + 1e-12 for _, tr, _ in trace)
    ceiling = cap ** D.power
    for _, _, pose in trace:
        for v, amp in zip(pose, D.fire_amp):
            assert abs(v) <= amp * ceiling * D.fire_scale + 1e-12      # trần thật = biên độ x fire_scale
    # trần tuyệt đối, đủ "vừa phải": roll < 0,6 độ, pitch/yaw < 0,3 độ, dịch < 2 mm
    assert max(abs(p[5]) for _, _, p in trace) < 0.6
    assert max(abs(p[3]) for _, _, p in trace) < 0.3 and max(abs(p[4]) for _, _, p in trace) < 0.3
    assert max(abs(p[i]) for _, _, p in trace for i in range(3)) < 0.002


def max_abs_per_axis(trace):
    return [max(abs(p[i]) for _, _, p in trace) for i in range(6)]


@pytest.mark.parametrize('fps', [60, 240])
def test_fire_scale_multiplies_every_fire_amplitude_by_exactly_the_ratio(fps):
    """fire_scale 1,2 so với 1,0: mọi trục của camera và của súng lớn đúng 1,2 lần ở mọi khung (không bị trần trauma cắt: trần kẹp trauma, không kẹp biên độ)."""
    base = dataclasses.replace(D, fire_scale=1.0)
    assert D.fire_scale == pytest.approx(1.2)
    a, sa = burst_trace(30, fps, data=base, settle=0.3)
    b, sb = burst_trace(30, fps, data=D, settle=0.3)
    for (_, _, pa), (_, _, pb) in zip(a, b):
        for x, y in zip(pa, pb):
            assert y == pytest.approx(x * 1.2, abs=1e-12)
    for ma, mb in zip(max_abs_per_axis(a), max_abs_per_axis(b)):
        assert mb / ma == pytest.approx(1.2, rel=1e-9)
    # phần súng đi theo cũng nhân 1,2
    ga, gb = Shake(base), Shake(D)
    for sh in (ga, gb):
        for _ in range(12):
            sh.on_shot(0.0)
            sh.update(1 / 120)
    for x, y in zip(ga.gun_pose(), gb.gun_pose()):
        assert y == pytest.approx(x * 1.2, abs=1e-12)


def test_fire_scale_does_not_touch_reload_beats():
    base = dataclasses.replace(D, fire_scale=1.0)
    for kind in D.beat_peaks:
        poses = []
        for data in (base, D):
            sh = Shake(data)
            sh.on_beat(kind)
            sh.update(0.0)
            row = []
            for _ in range(40):
                sh.update(1 / 240)
                row.append(sh.camera_pose())
            poses.append(row)
        assert poses[0] == poses[1]


def test_shake_dies_after_burst_ends():
    trace, sh = burst_trace(30, 120, settle=1.0)
    assert sh.trauma == 0.0 and not sh.active
    assert trace[-1][2] == (0.0,) * 6


@pytest.mark.parametrize('fps', [30, 60, 120, 240, 1000])
def test_trauma_and_pose_independent_of_fps_when_not_clamped(fps):
    """3 phát cách nhau 0,25 s (không chạm trần), thời điểm KHÔNG trùng ranh giới khung: trauma và tư thế tại 0,9 s
    phải như nhau ở mọi FPS (phát có tuổi trong khung)."""
    def run(f):
        sh = Shake(D)
        dt = 1.0 / f
        times = [0.1037, 0.3537, 0.6037]
        for i in range(1, round(0.9 * f) + 1):
            t1 = i * dt
            for ts in times:
                if t1 - dt < ts <= t1:
                    sh.on_shot(t1 - ts)
            sh.update(dt)
        return sh
    ref, got = run(100000), run(fps)
    assert got.t == pytest.approx(0.9)
    assert got.trauma == pytest.approx(ref.trauma, abs=1e-3)
    for a, b in zip(got.camera_pose(), ref.camera_pose()):
        assert a == pytest.approx(b, abs=1e-3 * max(abs(b), 1e-3) + 1e-6)


@pytest.mark.parametrize('fps', [30, 60, 120, 240])
def test_burst_clamped_close_across_fps(fps):
    ref, _ = burst_trace(30, 1000, settle=0.3)
    got, _ = burst_trace(30, fps, settle=0.3)
    ref_by_t = {round(t, 4): tr for t, tr, _ in ref}
    errs = [abs(tr - ref_by_t[round(t, 4)]) for t, tr, _ in got if round(t, 4) in ref_by_t]
    assert errs and max(errs) < 0.03      # phát có tuổi trong khung nên chỉ lệch nhỏ (làm tròn nhịp bắn vào khung)


def test_same_seed_repeats_and_other_seed_differs():
    a, _ = burst_trace(10, 120, seed=5)
    b, _ = burst_trace(10, 120, seed=5)
    c, _ = burst_trace(10, 120, seed=6)
    assert [p for _, _, p in a] == [p for _, _, p in b]
    assert [p for _, _, p in a] != [p for _, _, p in c]


def test_ads_reduces_the_shake_to_the_configured_fraction():
    hip, _ = burst_trace(20, 120)
    ads, _ = burst_trace(20, 120, ads=1.0)
    for (_, _, h), (_, _, a) in zip(hip, ads):
        for x, y in zip(h, a):
            assert y == pytest.approx(x * D.ads_multiplier, abs=1e-12)
    half, _ = burst_trace(20, 120, ads=0.5)
    mid = D.ads_multiplier + (1 - D.ads_multiplier) * 0.5          # smoothstep(0,5) = 0,5
    peak_hip = max(abs(p[5]) for _, _, p in hip)
    assert max(abs(p[5]) for _, _, p in half) == pytest.approx(peak_hip * mid, rel=1e-6)


def test_disabled_shake_is_silent():
    sh = Shake(D)
    sh.enabled = False
    sh.on_shot()
    sh.on_beat('seat')
    sh.watch_reload('reload', 100.0)
    sh.update(0.016)
    assert sh.camera_pose() == (0.0,) * 6 and sh.gun_pose() == (0.0,) * 6 and not sh.active


def test_gun_pose_opposes_world_and_follows_partially():
    _, sh = burst_trace(12, 120)
    cam_peak = gun_peak = 0.0
    opposed = same = 0
    for _ in range(300):
        sh.on_shot(0.0)
        sh.update(1 / 120)
        cam, gun = sh.camera_pose()[5], sh.gun_pose()[5]
        cam_peak, gun_peak = max(cam_peak, abs(cam)), max(gun_peak, abs(gun))
        if abs(cam) > 0.1:
            opposed += cam * gun < 0
            same += cam * gun > 0
    assert opposed > 5 * max(same, 1)                    # đảo dấu: camera nghiêng phải thì thế giới (và súng theo nó) nghiêng trái
    assert gun_peak == pytest.approx(cam_peak * D.gun_follow, rel=0.15)     # súng rung ít hơn thế giới


# --- nạp đạn ---
def feed_reload(sh, key, fps, speed=1.0, cancel_at=None):
    """Chạy clip `key` từ khung đầu theo `fps` như Combat (watch_reload rồi update). Trả về các mốc nổ ở lần chạy này: [(đồng hồ, loại)]."""
    clip = M4.clips[key]
    dt = 1.0 / fps
    t = 0.0
    start_count = sh.beat_count
    while True:
        t += dt * speed
        frame = min(clip.start + t * 30.0, clip.end)
        if cancel_at is not None and frame >= cancel_at:
            sh.watch_reload(None, None)
            sh.update(dt)
            break
        sh.watch_reload(key, frame, 30.0 * speed)
        sh.update(dt)
        if frame >= clip.end:
            sh.watch_reload(None, None)
            break
    n = sh.beat_count - start_count
    return list(sh.beat_log)[len(sh.beat_log) - n:] if n else []


@pytest.mark.parametrize('fps', [30, 60, 144, 1000])
@pytest.mark.parametrize('speed', [1.0, 1.5])
def test_reload_beats_fire_once_each_at_their_frames(fps, speed):
    for key, beats in D.reload_beats.items():
        sh = Shake(D)
        t0 = sh.t
        fired = feed_reload(sh, key, fps, speed)
        assert [k for _, k in fired] == [kind for _, kind in beats]
        clip = M4.clips[key]
        for (clock, _), (f_beat, _) in zip(fired, beats):
            # đồng hồ thật lúc nổ = (khung mốc - khung đầu) / 30 / tốc độ, đúng ở mọi FPS nhờ tuổi trong khung
            assert clock - t0 == pytest.approx((f_beat - clip.start) / 30.0 / speed, abs=1.5e-3 + 1e-3 / fps)


def test_reload_beats_match_clip_swap_frame():
    for key in ('reload', 'reload_empty'):
        clip = M4.clips[key]
        seat = [f for f, kind in D.reload_beats[key] if kind == 'seat']
        assert seat == [clip.swap]                       # băng mới vào chỗ đúng khung thay băng của Handling
        assert all(clip.start < f < clip.end for f, _ in D.reload_beats[key])
        assert [f for f, _ in D.reload_beats[key]] == sorted(f for f, _ in D.reload_beats[key])


def test_cancel_drops_beats_not_reached():
    sh = Shake(D)
    fired = feed_reload(sh, 'reload_empty', 60, cancel_at=180.0)      # sau mốc 172, trước bolt 190
    assert [k for _, k in fired] == ['mag_out', 'seat']
    sh.update(1.0)
    assert sh.beat_count == 2                                         # bolt không nổ muộn sau khi huỷ
    fired2 = feed_reload(sh, 'reload_empty', 60)                      # nạp lại từ đầu thì đủ mốc lại
    assert [k for _, k in fired2] == ['mag_out', 'seat', 'bolt']


def test_no_beats_while_idle_or_during_draw():
    sh = Shake(D)
    for f in range(0, 400, 7):
        sh.watch_reload(None, None)
        sh.watch_reload('draw', 269 + f / 10.0)
        sh.update(0.016)
    assert sh.beat_count == 0


def test_reload_beat_is_short_and_light():
    for kind in D.beat_peaks:
        sh = Shake(D)
        sh.on_beat(kind)
        sh.update(0.0)
        peak = 0.0
        quiet_after = None
        dt = 1 / 240
        t = 0.0
        while t < 0.6:
            sh.update(dt)
            t += dt
            pose = sh.camera_pose()
            m = max(abs(pose[3]), abs(pose[4]), abs(pose[5]))
            peak = max(peak, m)
            if quiet_after is None and m < 0.02 and t > 0.05:
                quiet_after = t
        assert 0.05 <= peak <= 0.3, kind                 # nhẹ (độ)
        assert quiet_after is not None and quiet_after < 0.4, kind       # tắt nhanh, không rung suốt
        assert sh.trauma == 0.0                          # mốc nạp không đụng trauma của bắn


@pytest.mark.parametrize('fps', [30, 60, 240])
def test_beat_spring_independent_of_fps(fps):
    def run(f):
        sh = Shake(D)
        dt = 1.0 / f
        for i in range(1, round(0.6 * f) + 1):
            if i == round(0.3 * f):
                sh.on_beat('bolt', 0.0)
            sh.update(dt)
        return sh
    ref, got = run(1000), run(fps)
    for a, b in zip(got.camera_pose(), ref.camera_pose()):
        assert a == pytest.approx(b, abs=1e-9)
