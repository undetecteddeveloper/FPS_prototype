import random

import pytest

from fps.core.recoil import CameraRecoil, GunKick
from fps.core.spring import burst_peak_ratio
from fps.weapon_data import M4, M4_PATTERN, GunKickData, RecoilData

PATTERN_UP = sum(u for u, _ in M4_PATTERN)
PATTERN_RIGHT = sum(r for _, r in M4_PATTERN)


def spray(rec, shots=30, fps=60, settle=0.0):
    """Bắn `shots` phát liên tục (750 phát/phút) rồi chạy tiếp `settle` giây.
    Trả về (lên, phải) tích luỹ SAU MỖI KHUNG, và tích luỹ tại thời điểm từng phát nổ."""
    dt = 1.0 / fps
    up = right = 0.0
    at_shot = []
    next_shot = 0.0
    fired = 0
    trace = []
    for i in range(round((shots * 0.08 + settle) * fps) + 1):
        t = i * dt
        while fired < shots and next_shot <= t + 1e-9:
            at_shot.append((up, right))
            rec.on_shot()
            fired += 1
            next_shot += 0.08
        du, dr = rec.step(dt)
        up += du
        right += dr
        trace.append((up, right))
    return trace, at_shot


def test_pattern_has_30_steps_mostly_up_and_drifting_right():
    assert len(M4_PATTERN) == 30
    assert all(u > 0 for u, _ in M4_PATTERN)
    assert PATTERN_UP == pytest.approx(8.4, abs=0.6)
    assert 0.5 < PATTERN_RIGHT < 3.0
    assert max(abs(r) for _, r in M4_PATTERN) < min(u for u, _ in M4_PATTERN)     # chủ yếu lên, không chủ yếu ngang


def test_no_noise_no_recovery_total_equals_pattern():
    d = RecoilData(pattern=M4_PATTERN, noise=0.0, recovery=0.0)
    trace, _ = spray(CameraRecoil(d), settle=1.0)
    assert trace[-1][0] == pytest.approx(PATTERN_UP, abs=1e-3)
    assert trace[-1][1] == pytest.approx(PATTERN_RIGHT, abs=1e-3)


def test_each_shot_adds_its_own_pattern_step():
    d = RecoilData(pattern=M4_PATTERN, noise=0.0, recovery=0.0)
    _, at_shot = spray(CameraRecoil(d), settle=0.5)
    # cú giật của phát k-1 đã áp gần hết lúc phát k nổ (cách 80 ms, hằng số thời gian 25 ms nên ~96%, cộng đuôi cú trước)
    for k in range(2, 30):
        step_up = at_shot[k][0] - at_shot[k - 1][0]
        assert step_up == pytest.approx(M4_PATTERN[k - 1][0], rel=0.05)


def test_same_pattern_every_time_apart_from_noise():
    runs = [spray(CameraRecoil(M4.recoil, random.Random(seed)), settle=0.0)[1] for seed in (1, 2, 3, 4)]
    ups = [r[-1][0] for r in runs]
    rights = [r[-1][1] for r in runs]
    assert max(ups) - min(ups) > 1e-6                                      # có nhiễu thật
    expected_up = PATTERN_UP * 0.96                                        # còn một chút cú giật chưa áp vào phát cuối
    assert all(u == pytest.approx(expected_up, rel=0.06) for u in ups)     # nhiễu ±10% độc lập triệt tiêu dần
    for r in runs:                                                         # mọi lần đều đi cùng hướng: lên đều, trôi phải
        assert all(b[0] >= a[0] for a, b in zip(r, r[1:]))
    assert all(x > 0 for x in rights)


def test_noise_stays_within_ten_percent_per_step():
    rec = CameraRecoil(RecoilData(pattern=((1.0, 1.0),), noise=0.10, recovery=0.0), random.Random(7))
    seen = []
    for _ in range(300):
        rec.pending = [0.0, 0.0]
        rec.on_shot()
        seen.append(tuple(rec.pending))
        rec.step(1.0)
    ups = [s[0] for s in seen]
    assert min(ups) >= 0.9 - 1e-9 and max(ups) <= 1.1 + 1e-9
    assert max(ups) - min(ups) > 0.15                                      # thật sự phân bố gần hết biên
    assert sum(ups) / len(ups) == pytest.approx(1.0, abs=0.02)


def test_pattern_restarts_after_a_pause_but_not_in_a_burst():
    d = RecoilData(pattern=((1.0, 0.0), (2.0, 0.0), (3.0, 0.0)), noise=0.0, recovery=0.0)
    rec = CameraRecoil(d)
    for _ in range(2):
        rec.on_shot()
        rec.step(0.1)                                                      # 0,1 s: còn trong loạt
    assert rec.index == 2
    rec.step(0.5)                                                          # nghỉ 0,5 s > 0,35 s
    rec.on_shot()
    assert rec.index == 1 and rec.pending[0] == pytest.approx(1.0)         # lại từ bước đầu


def test_past_the_end_of_the_pattern_holds_the_last_step():
    d = RecoilData(pattern=((1.0, 0.0), (2.0, 0.5)), noise=0.0)
    rec = CameraRecoil(d)
    for _ in range(5):
        rec.on_shot()
        rec.step(0.05)
    assert rec.index == 5
    rec.pending = [0.0, 0.0]
    rec.on_shot()
    assert rec.pending == [2.0, 0.5]


def test_recovery_gives_back_the_configured_fraction():
    for fraction in (0.0, 0.3, 0.5, 1.0):
        d = RecoilData(pattern=M4_PATTERN, noise=0.0, recovery=fraction)
        trace, _ = spray(CameraRecoil(d), settle=3.0)
        assert trace[-1][0] == pytest.approx(PATTERN_UP * (1 - fraction), abs=0.02), fraction
        assert trace[-1][1] == pytest.approx(PATTERN_RIGHT * (1 - fraction), abs=0.02), fraction


def test_recovery_only_starts_after_the_delay_and_is_gradual():
    d = RecoilData(pattern=M4_PATTERN, noise=0.0, recovery=0.3)
    rec = CameraRecoil(d)
    for _ in range(10):
        rec.on_shot()
        rec.step(0.08)
    total = 0.0
    for _ in range(3):                                                     # phát cuối đã cách 0,08 s; thêm 30 ms = 110 ms < 120 ms
        total += rec.step(0.01)[0]
    assert total >= 0                                                      # chưa hồi: chỉ còn nốt phần cú giật chưa áp
    got = []
    for _ in range(100):                                                   # rồi hồi từ từ, không nhảy
        got.append(rec.step(0.01)[0])
    assert min(got) < 0 and max(abs(g) for g in got) < 0.3


def test_firing_again_cancels_the_recovery():
    d = RecoilData(pattern=M4_PATTERN, noise=0.0, recovery=0.5)
    rec = CameraRecoil(d)
    for _ in range(5):
        rec.on_shot()
        rec.step(0.08)
    for _ in range(5):                                                     # 0,25 s: đã bắt đầu hồi nhưng còn dở
        rec.step(0.05)
    assert rec.rec[0] > 0
    rec.on_shot()
    assert rec.rec == [0.0, 0.0]


@pytest.mark.parametrize('fps', [30, 60, 144, 500])
def test_total_recoil_does_not_depend_on_fps(fps):
    d = RecoilData(pattern=M4_PATTERN, noise=0.0, recovery=0.3)
    trace, _ = spray(CameraRecoil(d), fps=fps, settle=3.0)
    assert trace[-1][0] == pytest.approx(PATTERN_UP * 0.7, abs=0.03)


def test_gun_kick_returns_to_rest_and_peaks_near_the_setting():
    kick = GunKick(GunKickData(random=(0, 0, 0, 0, 0, 0), back_random=0.0), random.Random(1))
    kick.on_shot()
    zs, pitches = [], []
    for _ in range(120):
        kick.update(1 / 240)
        zs.append(kick.pose[2])
        pitches.append(kick.pose[3])
    d = GunKickData()
    assert min(zs) == pytest.approx(d.back_peak, rel=0.01)                 # lùi về sau (z âm)
    assert max(pitches) == pytest.approx(d.peak[3], rel=0.01)
    for _ in range(240):
        kick.update(1 / 60)
    assert all(abs(v) < 1e-6 for v in kick.pose)


def test_gun_kick_is_smaller_and_faster_than_camera_recoil():
    d = GunKickData()
    assert abs(d.back_peak) < 0.05 and d.peak[3] < M4_PATTERN[0][0] * 6
    kick = GunKick(d, random.Random(1))
    kick.on_shot()
    t = 0.0
    while t < 2.0:
        kick.update(1 / 240)
        t += 1 / 240
        if max(abs(v) for v in kick.pose[:3]) < 0.05 * max(abs(d.back_peak), abs(d.peak[1])) and t > 0.05:
            break
    assert t < 0.8


# --- đẩy lùi (z) ---
def burst_z(shots, fps, ads=0.0, settle=1.0, rpm=750.0, seed=3, data=None):
    """Bắn `shots` phát liên tục ở `fps` như Combat (tuổi của phát trong khung). Trả về [(thời gian, z)] mỗi khung."""
    kick = GunKick(data or GunKickData(), random.Random(seed))
    interval, dt = 60.0 / rpm, 1.0 / fps
    out, fired = [], 0
    for i in range(1, round((shots * interval + settle) * fps) + 1):
        t1 = i * dt
        while fired < shots and fired * interval <= t1 + 1e-9:
            kick.on_shot(ads, max(0.0, t1 - fired * interval))
            fired += 1
        kick.update(dt)
        out.append((t1, kick.pose[2]))
    return out


NO_RANDOM = GunKickData(random=(0, 0, 0, 0, 0, 0), back_random=0.0)


def test_pushback_single_shot_peaks_at_back_peak_toward_the_eye():
    z = min(v for _, v in burst_z(1, 480, data=NO_RANDOM))
    assert z == pytest.approx(NO_RANDOM.back_peak, rel=0.03)
    assert z < 0                                       # âm = về phía mắt
    assert 0.02 <= abs(z) <= 0.06                      # cỡ vài cm (không thành 0 hay nửa mét nếu ai gõ nhầm đơn vị)


def test_pushback_burst_builds_up_and_saturates():
    trace = burst_z(30, 480, data=NO_RANDOM)
    peak = min(v for _, v in trace)
    ratio = peak / NO_RANDOM.back_peak                 # cả băng so với một phát (hệ tuyến tính: không phụ thuộc back_peak)
    assert 1.17 <= ratio <= 2.17                       # trước đây 5 cm +-30% của 3 cm: cùng biên, tính theo tỉ lệ
    model = burst_peak_ratio(NO_RANDOM.back_omega, NO_RANDOM.back_zeta, 30, 60.0 / 750.0)
    assert ratio == pytest.approx(model, rel=0.02)     # khớp công thức đóng của lò xo (cộng chồng 30 xung cách 0,08 s), độc lập với Spring.step
    assert peak < NO_RANDOM.back_peak * 1.3            # nhiều hơn rõ rệt một phát đơn
    # bão hoà: 30 phát không lùi xa hơn 15 phát quá nhiều (không tăng vô hạn)
    half = min(v for t, v in trace if t <= 15 * 0.08)
    assert peak >= half * 1.15
    # bắn hai băng liền cũng không vượt: lò xo tắt dần nên dồn lên có trần
    assert min(v for _, v in burst_z(90, 480, data=NO_RANDOM)) >= peak * 1.1


def test_pushback_settles_after_the_burst_in_measurable_time():
    trace = burst_z(30, 480, data=NO_RANDOM, settle=1.5)
    last = 30 * 0.08
    settled = next(t for t, v in trace if t > last and all(abs(w) < 0.001 for u, w in trace if u >= t))
    assert 0.1 < settled - last < 0.6
    assert all(abs(v) < 1e-5 for _, v in trace[-20:])


def test_pushback_in_ads_is_back_ads_scale_times_hip():
    s = NO_RANDOM.back_ads_scale
    assert s != 1.0                                   # nếu bằng 1 thì ngắm/hông không khác nhau và test này vô nghĩa
    hip = min(v for _, v in burst_z(30, 480, ads=0.0, data=NO_RANDOM))
    ads = min(v for _, v in burst_z(30, 480, ads=1.0, data=NO_RANDOM))
    assert ads / hip == pytest.approx(s, abs=0.03)
    mid = min(v for _, v in burst_z(30, 480, ads=0.5, data=NO_RANDOM))
    assert mid / hip == pytest.approx(1.0 + (s - 1.0) * 0.5, abs=0.03)    # nửa chừng: nội suy smoothstep(0,5) = 0,5
    assert min(hip, ads) < mid < max(hip, ads)        # nằm giữa hai đầu, bất kể ngắm lùi ít hơn (s < 1) hay nhiều hơn (s > 1) hông


def test_pushback_does_not_touch_the_other_axes_or_the_vertical_kick():
    kick = GunKick(NO_RANDOM, random.Random(1))
    kick.on_shot()
    for _ in range(8):                                # 33 ms: gần đỉnh của lò xo cũ
        kick.update(1 / 240)
    x, y, z, pitch, yaw, roll = kick.pose
    assert (yaw, roll) == (0.0, 0.0)
    assert x == pytest.approx(NO_RANDOM.back_x_ratio * z, rel=1e-9) and x < 0      # kéo vào giữa màn hình: nhích sang TRÁI khi lùi (lúc hông)
    assert y > 0 and pitch > 0 and z < 0              # y/pitch vẫn do lò xo cũ
    only_old = GunKick(GunKickData(random=(0, 0, 0, 0, 0, 0), back_random=0.0, back_peak=0.0), random.Random(1))
    only_old.on_shot()
    for _ in range(8):
        only_old.update(1 / 240)
    assert only_old.pose[1] == pytest.approx(y) and only_old.pose[3] == pytest.approx(pitch) and only_old.pose[2] == 0.0


@pytest.mark.parametrize('fps', [30, 60, 144, 240, 1000])
def test_pushback_burst_peak_is_independent_of_fps(fps):
    ref = min(v for _, v in burst_z(30, 4000, data=NO_RANDOM))
    got = min(v for _, v in burst_z(30, fps, data=NO_RANDOM))
    assert got == pytest.approx(ref, rel=0.05)


@pytest.mark.parametrize('fps', [30, 60, 144, 1000])
def test_pushback_single_shot_curve_is_exact_at_any_dt(fps):
    """Lò xo giải đúng nghiệm: một phát (nổ giữa khung) cho cùng đường cong ở mọi dt, kể cả dt rất lớn."""
    def at(f, t_end=0.4, t_shot=0.0537):
        kick = GunKick(NO_RANDOM, random.Random(1))
        dt = 1.0 / f
        frames = round(t_end * f)
        for i in range(1, frames + 1):
            t1 = i * dt
            if t1 - dt < t_shot <= t1:
                kick.on_shot(0.0, t1 - t_shot)
            kick.update(dt)
        return kick.pose[2]
    assert at(fps) == pytest.approx(at(20000), abs=1.5e-4)


def test_pushback_sideways_pull_is_off_when_aiming_down_sights():
    """Ngắm hẳn: đường ngắm phải giữ trên trục nhìn nên x đi kèm bằng 0; hông thì x = back_x_ratio * z."""
    for ads, expect_x in ((0.0, True), (1.0, False)):
        kick = GunKick(NO_RANDOM, random.Random(1))
        kick.on_shot(ads)
        worst = 0.0
        for _ in range(60):
            kick.update(1 / 240)
            worst = max(worst, abs(kick.pose[0]))
        assert (worst > 0.005) == expect_x
