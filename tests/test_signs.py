import itertools

import pytest

from fps.core.room import RoomLayout, beam_boxes
from fps.core.signs import (SignLayout, angular_rect, overlap_fraction, rod_xs, sign_center_x, sign_height, sign_rect)

L = SignLayout()
ROOM = RoomLayout()
MARKS = (10, 25, 50, 100, 150, 200)


def test_signs_grow_with_distance_and_stop_under_the_ceiling():
    heights = [sign_height(L, d) for d in MARKS]
    assert heights == sorted(heights)
    assert max(heights) <= L.max_height + 1e-9
    assert sign_rect(L, 200)['hi'][1] <= ROOM.height - L.top_margin + 1e-9


@pytest.mark.parametrize('d', MARKS)
@pytest.mark.parametrize('side', (-1, 1))
def test_sign_fits_inside_the_room_and_above_targets(d, side):
    r = sign_rect(L, d, side)
    assert r['lo'][1] == L.bottom
    assert ROOM.half_width - ROOM.pillar_depth > max(abs(r['lo'][0]), abs(r['hi'][0]))          # không đụng cột/tường
    assert r['lo'][1] > 2.86 + 0.1          # cao hơn bia lớn nhất (200 m: 2,86 m) nên bia chạy đi lọt dưới biển
    assert r['cz'] < d                      # trước mốc, không chạm bia ở đúng mốc


@pytest.mark.parametrize('d', MARKS)
def test_sign_does_not_touch_the_beam_at_its_mark(d):
    r = sign_rect(L, d, 1)
    for lo, hi in beam_boxes(ROOM):
        z_overlap = min(r['hi'][2], hi[2]) - max(r['lo'][2], lo[2])
        y_overlap = min(r['hi'][1], hi[1]) - max(r['lo'][1], lo[1])
        assert not (z_overlap > 0 and y_overlap > 0)


def test_signs_mirror_left_and_right():
    for d in MARKS:
        a, b = sign_rect(L, d, -1), sign_rect(L, d, 1)
        assert a['cx'] == -b['cx'] and a['w'] == b['w'] and a['cy'] == b['cy']
        assert sign_center_x(L, d) > 0


def test_rods_stay_on_the_board():
    r = sign_rect(L, 50, 1)
    x0, x1 = rod_xs(r)
    assert r['lo'][0] < x0 < x1 < r['hi'][0]


def test_signs_do_not_hide_each_other_from_the_firing_line():
    """Nhìn từ vạch bắn (mắt 1,62 m), biển gần che tối đa 10% diện tích một biển xa."""
    worst = 0.0
    for near, far in itertools.combinations(MARKS, 2):
        for side in (-1, 1):
            worst = max(worst, overlap_fraction(sign_rect(L, near, side), sign_rect(L, far, side)))
    assert worst < 0.10


def test_angular_rect_shrinks_with_distance():
    a = angular_rect(sign_rect(L, 25, 1))
    b = angular_rect(sign_rect(L, 100, 1))
    assert (a[1] - a[0]) > (b[1] - b[0]) * 0.5 and a[0] > 0 and b[0] > 0
