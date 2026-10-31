import random

import pytest

from fps.core.recoil import CameraRecoil, GunKick
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
    kick = GunKick(GunKickData(random=(0, 0, 0, 0, 0, 0)), random.Random(1))
    kick.on_shot()
    zs, pitches = [], []
    for _ in range(120):
        kick.update(1 / 240)
        zs.append(kick.pose[2])
        pitches.append(kick.pose[3])
    d = GunKickData()
    assert min(zs) == pytest.approx(d.peak[2], rel=0.01)                   # lùi về sau (z âm)
    assert max(pitches) == pytest.approx(d.peak[3], rel=0.01)
    for _ in range(240):
        kick.update(1 / 60)
    assert all(abs(v) < 1e-6 for v in kick.pose)


def test_gun_kick_is_smaller_and_faster_than_camera_recoil():
    d = GunKickData()
    assert abs(d.peak[2]) < 0.05 and d.peak[3] < M4_PATTERN[0][0] * 6
    kick = GunKick(d, random.Random(1))
    kick.on_shot()
    t = 0.0
    while t < 2.0:
        kick.update(1 / 240)
        t += 1 / 240
        if max(abs(v) for v in kick.pose) < 0.05 * max(abs(p) for p in d.peak[:3]) and t > 0.05:
            break
    assert t < 0.6


def test_gun_kick_accumulates_in_sustained_fire_but_stays_bounded():
    kick = GunKick(GunKickData(), random.Random(3))
    worst = 0.0
    for i in range(60 * 3):
        if i % 5 == 0:                                                     # 12 phát/giây ở 60 FPS
            kick.on_shot()
        kick.update(1 / 60)
        worst = max(worst, abs(kick.pose[2]))
    assert worst < 4 * abs(GunKickData().peak[2])
