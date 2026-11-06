"""Ống kính, phơi sáng, ánh sáng đèn trần: toán thuần. Các công thức này khớp từng dòng với assets/shaders/light_common.glsl và assets/shaders/lens.frag.
(Camera đầu: tests/test_headcam.py.)"""
import math
from pathlib import Path

import pytest

from fps.core import exposure, lens
from fps.core.exposure import AutoExposure, glare, lamp_reach, light_at, target_exposure
from fps.weapon_data import M4, LensData, LookData

ROOT = Path(__file__).resolve().parent.parent
ASPECT = 16 / 9


# --- ống kính ---
def test_centre_stays_put_and_horizontal_edge_maps_to_edge():
    assert lens.distort(0.0, 0.0, 0.25, ASPECT) == (0.0, 0.0)
    assert lens.distort(1.0, 0.0, 0.25, ASPECT)[0] == pytest.approx(1.0)
    assert lens.distort(-1.0, 0.0, 0.25, ASPECT)[0] == pytest.approx(-1.0)


def test_zero_distortion_is_identity():
    assert lens.distort(0.7, -0.4, 0.0, ASPECT) == pytest.approx((0.7, -0.4))


def test_centre_is_magnified_by_one_plus_k():
    k = LensData().fisheye
    x, _ = lens.distort(0.01, 0.0, k, ASPECT)
    assert 0.01 / x == pytest.approx(1.0 + k, rel=1e-3)


def test_warp_is_monotonic_along_the_radius():
    """Không gập ảnh: đi ra rìa thì điểm lấy mẫu cũng đi ra rìa."""
    for k in (0.1, 0.25, 0.6):
        last = -1.0
        for i in range(1, 200):
            x, _ = lens.distort(i / 100.0, 0.0, k, ASPECT)
            assert x > last
            last = x


def test_samples_outside_the_image_are_hidden_by_the_vignette():
    """Gần góc khung, ống kính đọc ra ngoài ảnh: chỗ lệch ra đáng kể (> 3%) phải gần đen, kẻo lộ vệt kéo dài ở mép. Sát mép lệch rất ít nên không thấy."""
    d = LensData()
    worst = 0.0
    for i in range(0, 201):
        for j in range(0, 201):
            x, y = i / 100.0 - 1.0, j / 100.0 - 1.0
            sx, sy = lens.distort(x, y, d.fisheye, ASPECT)
            if abs(sx) > 1.03 or abs(sy) > 1.03:
                r = math.sqrt(x * x + (y / ASPECT) ** 2)
                worst = max(worst, lens.vignette(r, d.vignette_start, d.vignette_end))
    assert worst < 0.12


def test_vignette_keeps_the_centre_and_blackens_the_corner():
    d = LensData()
    assert lens.vignette(0.0, d.vignette_start, d.vignette_end) == 1.0
    assert lens.vignette(math.sqrt(1 + 1 / ASPECT ** 2), d.vignette_start, d.vignette_end) == 0.0


def test_aiming_zooms_the_centre_slightly_as_decided():
    """Đã chốt: ngắm phóng RẤT NHẸ, khoảng 10-15% (tính cả ống kính bớt méo)."""
    d = LensData()
    fov = 96.0
    hip = lens.center_scale(fov, d.fisheye, fov)
    ads = lens.center_scale(M4.ads_fov, d.fisheye_ads, fov)
    assert 1.10 <= ads / hip <= 1.15


def test_centre_of_the_lens_looks_like_a_normal_fov():
    assert 75 < lens.equivalent_center_fov(96.0, LensData().fisheye) < 90


def test_shader_uses_the_same_formula():
    src = (ROOT / 'assets' / 'shaders' / 'lens.frag').read_text(encoding='utf-8')
    assert 'float f = (1.0 + k * r2) / (1.0 + k);' in src
    assert 'vec2 q = vec2(p.x, p.y / lens_warp.x);' in src


# --- đèn ---
LOOK = LookData()


def test_three_lamps_are_enough_per_pixel():
    """Mỗi điểm ảnh chỉ xét 3 đèn: cốt lõi của việc tối ưu shader."""
    assert lamp_reach(LOOK) == 1
    assert lamp_reach(LookData(lamp_radius=20.0)) == 2


def lamp_z(i=2):
    return LOOK.lamp_z0 + i * LOOK.lamp_spacing


def test_floor_under_a_lamp_is_much_brighter_than_between_lamps():
    z = lamp_z()
    under, gap = light_at(LOOK, (0.0, 0.0, z)), light_at(LOOK, (0.0, 0.0, z + LOOK.lamp_spacing / 2))
    assert under > 2.5 * gap > 0


def test_light_falls_off_with_distance_from_the_lamp():
    z = lamp_z()
    values = [light_at(LOOK, (x, 0.0, z)) for x in (0.0, 2.0, 4.0, 7.0, 11.0)]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_nothing_above_the_lamp_gets_direct_light():
    """Chóa đèn che phía trên: trần không nhận ánh sáng trực tiếp."""
    assert light_at(LOOK, (0.0, LOOK.lamp_y + 0.5, lamp_z()), (0.0, -1.0, 0.0)) == 0.0


def test_surface_facing_away_gets_nothing():
    assert light_at(LOOK, (0.0, 0.0, lamp_z()), (0.0, -1.0, 0.0)) == 0.0


def test_a_surface_facing_the_lamp_gets_more_than_one_facing_sideways():
    p = (3.0, 1.0, lamp_z())
    to_lamp = (-3.0, LOOK.lamp_y - 1.0, 0.0)
    n = math.hypot(*to_lamp)
    assert light_at(LOOK, p, (to_lamp[0] / n, to_lamp[1] / n, 0.0)) > light_at(LOOK, p, (1.0, 0.0, 0.0))


def test_past_the_last_lamp_only_real_lamps_count():
    far = LOOK.lamp_z0 + LOOK.lamp_count * LOOK.lamp_spacing + LOOK.lamp_radius + 1
    assert light_at(LOOK, (0.0, 0.0, far)) == 0.0


def test_bulb_is_brighter_than_anything_it_lights():
    """Lỗi cũ: bóng đèn chỉ sáng hơn sàn ngay dưới nó ~25%, trông như tờ giấy trắng."""
    floor_max = max(light_at(LOOK, (0.0, 0.0, lamp_z() + dz)) for dz in (0.0, 1.0, 2.0))
    bulb = LOOK.lamp_emissive
    assert bulb > 2.0 * floor_max * 0.47        # 0,47 = màu viên gạch trong world.frag


def test_gun_and_world_share_one_light_source():
    """Súng không có đèn riêng: shader súng không còn mặt trời, và cả hai shader cùng nạp một file ánh sáng."""
    vm = (ROOT / 'assets' / 'shaders' / 'viewmodel.frag').read_text(encoding='utf-8')
    world = (ROOT / 'assets' / 'shaders' / 'world.frag').read_text(encoding='utf-8')
    assert '#include "light_common.glsl"' in vm and '#include "light_common.glsl"' in world
    for word in ('sun_dir', 'sun_color', 'sky_color', 'ground_color'):
        assert word not in vm
    assert 'tonemap(' in vm and 'tonemap(' in world
    assert 'gather_lamps(' in vm and 'gather_lamps(' in world
    assert 'flash_light(' in vm and 'flash_light(' in world


def test_bounce_light_scales_with_the_lamps():
    """Lỗi cũ: giảm đèn 12 lần mà ảnh chỉ tối đi 14% vì ánh dội là số cố định. Đèn tắt thì ánh dội phải mất."""
    src = (ROOT / 'assets' / 'shaders' / 'light_common.glsl').read_text(encoding='utf-8')
    assert 'bounce += look_lamp2.w * win * win' in src


def test_python_lamp_formula_matches_the_shader_text():
    src = (ROOT / 'assets' / 'shaders' / 'light_common.glsl').read_text(encoding='utf-8')
    assert 'win * win / (1.0 + d2 / (look_lamp2.z * look_lamp2.z))' in src
    assert 'mix(look_lamp_cone.z, 1.0, smoothstep(look_lamp_cone.y, look_lamp_cone.x, cos_down))' in src


# --- phơi sáng ---
LENS = LensData()
FORWARD = (0.0, 0.0, 1.0)


def test_exposure_opens_in_the_dark_and_closes_under_a_lamp():
    z = lamp_z()
    bright = target_exposure(LENS, LOOK, (0.0, 1.68, z), FORWARD)
    dark = target_exposure(LENS, LOOK, (11.0, 1.68, z + 5.0), FORWARD)
    assert dark > bright * 1.15


def test_looking_into_a_lamp_lowers_exposure():
    z = lamp_z()
    pos = (0.0, 1.68, z - 3.0)
    d = math.sqrt(3.0 ** 2 + (LOOK.lamp_y - 1.68) ** 2)
    toward = (0.0, (LOOK.lamp_y - 1.68) / d, 3.0 / d)
    assert glare(LOOK, pos, toward) > 0.3
    assert glare(LOOK, pos, (0.0, -1.0, 0.0)) == 0.0
    assert target_exposure(LENS, LOOK, pos, toward) < target_exposure(LENS, LOOK, pos, (0.0, -0.3, -0.95))


def test_exposure_stays_within_limits():
    for pos in ((0.0, 1.68, -500.0), (0.0, 4.0, lamp_z()), (11.0, 0.1, lamp_z())):
        value = target_exposure(LENS, LOOK, pos, FORWARD)
        assert LENS.exposure_min <= value <= LENS.exposure_max


def test_fixed_exposure_when_auto_is_off():
    d = LensData(auto_exposure=0.0)
    assert target_exposure(d, LOOK, (0.0, 1.68, lamp_z()), FORWARD) == pytest.approx(1.0)
    assert target_exposure(d, LOOK, (11.0, 1.68, lamp_z() + 5.0), FORWARD) == pytest.approx(1.0)


def test_exposure_adapts_slowly_into_the_dark_and_faster_into_the_light():
    z = lamp_z()
    bright, dark = (0.0, 1.68, z), (11.0, 1.68, z + 5.0)

    def seconds_to_settle(start, end):
        a = AutoExposure(LENS, LOOK)
        a.update(1 / 60, start, FORWARD)
        goal = target_exposure(LENS, LOOK, end, FORWARD)
        t = 0.0
        while abs(math.log(a.value / goal)) > 0.02 and t < 20.0:
            a.update(1 / 60, end, FORWARD)
            t += 1 / 60
        return t
    assert seconds_to_settle(bright, dark) > 1.5 * seconds_to_settle(dark, bright)


def test_exposure_change_is_independent_of_frame_rate():
    z = lamp_z()
    results = []
    for fps in (30, 120):
        a = AutoExposure(LENS, LOOK)
        a.update(1 / fps, (0.0, 1.68, z), FORWARD)
        for _ in range(fps):
            a.update(1 / fps, (11.0, 1.68, z + 5.0), FORWARD)
        results.append(a.value)
    assert results[0] == pytest.approx(results[1], rel=0.01)


def test_first_frame_starts_at_the_target():
    a = AutoExposure(LENS, LOOK)
    assert a.update(1 / 60, (0.0, 1.68, 0.0), FORWARD) == pytest.approx(target_exposure(LENS, LOOK, (0.0, 1.68, 0.0), FORWARD))


def test_exposure_module_formula_constants_exist():
    assert exposure.nearest_lamps(LOOK, lamp_z())[0] == 2
