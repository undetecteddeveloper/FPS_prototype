import math
import random

import pytest

from fps.core.movement import MoveState
from fps.core.spread import Accuracy, angle_between, crosshair_gap, random_in_cone
from fps.weapon_data import AccuracyData

S = MoveState


def acc():
    return Accuracy(AccuracyData())


def test_base_spread_per_state_matches_the_brief():
    a = acc()
    assert a.angle(S.IDLE) == 2.0
    assert a.angle(S.WALK) == 3.5
    assert a.angle(S.AIR) == 6.0
    assert a.angle(S.CROUCH_IDLE) == pytest.approx(1.4)             # 2,0 x 0,7
    assert a.angle(S.CROUCH_WALK) == pytest.approx(2.45)            # 3,5 x 0,7
    assert a.angle(S.IDLE, 1.0) == pytest.approx(0.1)               # ADS đứng yên


def test_moving_is_wider_than_standing_and_ads_is_tightest():
    a = acc()
    assert a.angle(S.IDLE) < a.angle(S.WALK) < a.angle(S.SPRINT) < a.angle(S.AIR)
    assert a.angle(S.CROUCH_IDLE) < a.angle(S.IDLE)
    assert a.angle(S.IDLE, 1.0) < a.angle(S.CROUCH_IDLE) < a.angle(S.IDLE)
    assert a.angle(S.WALK, 1.0) < a.angle(S.IDLE)                   # ngắm khi đi vẫn chặt hơn đứng hông
    assert a.angle(S.AIR, 1.0) == a.angle(S.AIR)                    # nhảy: ngắm không giúp gì


def test_ads_amount_blends_between_hip_and_ads():
    a = acc()
    assert a.angle(S.IDLE, 0.5) == pytest.approx((2.0 + 0.1) / 2)
    values = [a.angle(S.IDLE, k / 10) for k in range(11)]
    assert values == sorted(values, reverse=True)


def test_bloom_adds_per_shot_and_caps():
    a = acc()
    for n in range(1, 40):
        a.on_shot()
        assert a.bloom == pytest.approx(min(0.25 * n, 4.0))
    assert a.angle(S.IDLE) == pytest.approx(2.0 + 4.0)


def test_bloom_does_not_recover_during_sustained_fire_but_does_after():
    a = acc()
    for _ in range(10):                                            # 750 phát/phút = 0,08 s giữa các phát
        a.on_shot()
        a.update(0.08)
    assert a.bloom == pytest.approx(2.5)                           # 10 x 0,25: không bị hồi giữa các nhịp
    a.update(0.07)                                                 # phát cuối đã cách 0,08 s; thêm 0,07 s = đúng 0,15 s chờ
    assert a.bloom == pytest.approx(2.5, abs=1e-9)
    a.update(0.1)
    assert a.bloom == pytest.approx(2.5 - 0.6)                     # 6 độ/giây
    a.update(5.0)
    assert a.bloom == 0.0                                          # không âm


@pytest.mark.parametrize('fps', [30, 60, 240])
def test_bloom_recovery_does_not_depend_on_fps(fps):
    a = acc()
    a.bloom = 4.0
    a.since_shot = 0.0
    for _ in range(round(0.5 * fps)):                              # 0,5 s: chờ 0,15 s rồi hồi 0,35 s x 6 độ/s = 2,1 độ
        a.update(1 / fps)
    assert a.bloom == pytest.approx(4.0 - 6.0 * 0.35, abs=1e-6)


def test_ads_hides_almost_all_bloom():
    a = acc()
    for _ in range(30):
        a.on_shot()
    assert a.angle(S.IDLE, 1.0) == pytest.approx(0.1 + 4.0 * 0.05)
    assert a.angle(S.IDLE, 1.0) < 0.5
    assert a.angle(S.IDLE, 0.0) == pytest.approx(6.0)              # thả ADS thì bloom lộ ra lại


def test_random_in_cone_stays_inside_and_is_uniform_on_the_disc():
    rng = random.Random(5)
    d = (0.0, 0.0, 1.0)
    half = 4.0
    offs = [angle_between(d, random_in_cone(d, half, rng)) for _ in range(20000)]
    assert max(offs) <= half + 1e-9
    assert sum(offs) / len(offs) == pytest.approx(half * 2 / 3, rel=0.02)     # đĩa đều: bán kính TB = 2/3 R
    inner = sum(o <= half / 2 for o in offs) / len(offs)
    assert inner == pytest.approx(0.25, abs=0.015)                            # nửa bán kính = 1/4 diện tích


def test_random_in_cone_is_centered_for_any_direction():
    rng = random.Random(9)
    for d in ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, -1.0, 0.0),
              (0.6, 0.0, 0.8), (math.sqrt(0.5), math.sqrt(0.5), 0.0)):
        pts = [random_in_cone(d, 5.0, rng) for _ in range(8000)]
        assert all(abs(math.sqrt(sum(c * c for c in p)) - 1.0) < 1e-9 for p in pts)
        mean = [sum(p[i] for p in pts) / len(pts) for i in range(3)]
        n = math.sqrt(sum(c * c for c in mean))
        assert angle_between(d, tuple(c / n for c in mean)) < 0.2             # không lệch về phía nào (sai số mẫu ~0,03°)


def test_angle_between_is_accurate_for_tiny_angles():
    a = (0.0, 0.0, 1.0)
    for deg in (0.001, 0.01, 0.1, 1.0, 45.0, 90.0, 179.0):
        r = math.radians(deg)
        assert angle_between(a, (math.sin(r), 0.0, math.cos(r))) == pytest.approx(deg, rel=1e-9)
    assert angle_between(a, a) == 0.0


def test_zero_angle_gives_exactly_the_aim_direction():
    d = (0.0, 0.6, 0.8)
    assert random_in_cone(d, 0.0, random.Random(1)) == d


def test_crosshair_gap_matches_perspective_projection():
    hfov, aspect = 80.0, 16 / 9
    vtan = math.tan(math.radians(hfov / 2)) / aspect
    assert crosshair_gap(0.0, vtan) == 0.0
    # tia lệch lên 2° chiếu lên màn hình ở độ cao: y_ndc = tan(2°)/vtan, y_ui = y_ndc/2
    assert crosshair_gap(2.0, vtan) == pytest.approx(0.5 * math.tan(math.radians(2)) / vtan)
    assert 0.03 < crosshair_gap(2.0, vtan) < 0.045
    gaps = [crosshair_gap(a, vtan) for a in (0, 1, 2, 4, 6, 10)]
    assert gaps == sorted(gaps)
