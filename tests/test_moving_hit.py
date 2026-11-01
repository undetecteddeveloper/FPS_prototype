"""Đạn dò va chạm với hộp (bia) đang chuyển động trong lúc đạn đi: chính xác với chuyển động đều, không lệch tốc độ x dt."""
import pytest

from fps.core.ballistics import advance, moving_hit, segment_vs_aabb, segment_vs_moving_aabb

LO, HI = (-0.5, 0.0, 9.97), (0.5, 2.0, 10.03)          # bia rộng 1 m, mỏng, ở z = 10, đầu bước ở x = 0
V = 500.0


def bullet_segment(dt, x_aim=0.0):
    return (x_aim, 1.0, 0.0), (x_aim, 1.0, V * dt)


def test_zero_displacement_is_the_static_test():
    p0, p1 = bullet_segment(0.03)
    assert segment_vs_moving_aabb(p0, p1, LO, HI, (0, 0, 0)) == segment_vs_aabb(p0, p1, LO, HI)


def test_box_moving_into_the_line_of_fire_is_hit_at_the_right_time():
    # bia đi sang phải 4 m/s; bước 0,03 s: bia dịch 0,12 m. Đạn nhắm x = 0,56: lệch ra ngoài mép (0,5) lúc đầu bước,
    # nhưng lúc đạn tới z = 10 (t = 0,02 s) bia đã ở x = 0,08 nên mép phải ở 0,58 -> TRÚNG
    dt, v = 0.03, 4.0
    p0, p1 = bullet_segment(dt, 0.56)
    assert segment_vs_aabb(p0, p1, LO, HI) is None                       # nếu bia đứng yên ở vị trí đầu bước thì trượt
    h = moving_hit(p0, p1, LO, HI, (v * dt, 0, 0), 'bia')
    assert h is not None and h.owner == 'bia'
    assert h.t == pytest.approx(9.97 / (V * dt), abs=1e-6)               # mặt trước bia ở z = 9,97
    assert h.point[2] == pytest.approx(9.97, abs=1e-3)                    # điểm trúng là chỗ viên đạn đang ở


def test_box_moving_away_misses():
    dt, v = 0.03, 4.0
    p0, p1 = bullet_segment(dt, 0.45)                                    # đứng yên thì trúng (0,45 < 0,5)
    assert segment_vs_aabb(p0, p1, LO, HI) is not None
    # bia đi sang trái: lúc đạn tới, mép phải ở 0,5 - 0,08 = 0,42 < 0,45 -> trượt
    assert moving_hit(p0, p1, LO, HI, (-v * dt, 0, 0), 'bia') is None


@pytest.mark.parametrize('dt', [1 / 240, 1 / 120, 1 / 60, 1 / 30, 1 / 20])
def test_edge_decision_is_the_same_at_any_step_length(dt):
    """Bia 4 m/s, đạn bay thẳng tới z = 10 (0,02 s). Mép phải của bia lúc đạn tới là 0,5 + 4 * 0,02 = 0,58 m:
    nhắm 0,57 phải trúng, nhắm 0,59 phải trượt, dù bước (khung) dài bao nhiêu. (Lấy vị trí cuối bước sẽ sai tới 4 * dt.)"""
    v = 4.0
    t_fly = 10.0 / V
    for aim, expect_hit in ((0.57, True), (0.59, False)):
        pos, t, hit = (aim, 1.0, 0.0), 0.0, None
        while hit is None and t < 0.1:
            new_pos, _ = advance(pos, (0, 0, V), 0.0, dt)
            lo = (LO[0] + v * t, LO[1], LO[2])
            hi = (HI[0] + v * t, HI[1], HI[2])
            hit = moving_hit(pos, new_pos, lo, hi, (v * dt, 0, 0), 'bia')
            pos, t = new_pos, t + dt
        assert (hit is not None) == expect_hit, (aim, dt)
        if hit:
            assert hit.point[2] == pytest.approx(9.97, abs=1e-6)
            assert t - dt + hit.t * dt == pytest.approx(t_fly - 0.03 / V, abs=1e-6)
