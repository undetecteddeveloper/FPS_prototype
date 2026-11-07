"""Lens, exposure and sun light: pure maths. These formulas match assets/shaders/light_common.glsl and assets/shaders/lens.frag line by line.
(Head camera: tests/test_headcam.py.)"""
import math
from pathlib import Path

import pytest

from fps.core import lens
from fps.core.exposure import light_at, sun_vector, target_exposure
from fps.weapon_data import M4, LensData, LookData

ROOT = Path(__file__).resolve().parent.parent
ASPECT = 16 / 9


# --- lens ---
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
    """No folding of the image: as we move out to the edge, the sample point also moves out to the edge."""
    for k in (0.1, 0.25, 0.6):
        last = -1.0
        for i in range(1, 200):
            x, _ = lens.distort(i / 100.0, 0.0, k, ASPECT)
            assert x > last
            last = x


def test_samples_outside_the_image_are_hidden_by_the_vignette():
    """Near the frame corners the lens samples outside the image: spots displaced noticeably (> 3%) must be nearly black, or a smeared streak shows at the edge. Right at the edge the displacement is tiny, so it is not seen."""
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
    """Decided: aiming zooms VERY slightly, about 10-15% (counting the lens distortion being reduced)."""
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


# --- light ---
LOOK = LookData()
LENS = LensData()
SHADERS = ROOT / 'assets' / 'shaders'


def test_sun_vector_is_unit_length():
    assert math.sqrt(sum(c * c for c in sun_vector(LOOK))) == pytest.approx(1.0)
    assert sun_vector(LookData(sun_dir=(0.0, 5.0, 0.0))) == pytest.approx((0.0, 1.0, 0.0))


def test_surface_facing_the_sun_gets_more_than_one_facing_away():
    toward = sun_vector(LOOK)
    away = tuple(-c for c in toward)
    assert light_at(LOOK, toward) > light_at(LOOK, away) > 0.0          # facing away still gets the ambient light


def test_sun_off_leaves_only_the_ambient_light():
    dark = LookData(sun_color=(0.0, 0.0, 0.0))
    assert light_at(dark) == pytest.approx(0.299 * dark.ambient_up[0] + 0.587 * dark.ambient_up[1] + 0.114 * dark.ambient_up[2])


def test_gun_and_world_share_one_light_source():
    """The gun has no light of its own: both shaders load the same light file and use the same helpers."""
    vm = (SHADERS / 'viewmodel.frag').read_text(encoding='utf-8')
    world = (SHADERS / 'world.frag').read_text(encoding='utf-8')
    assert '#include "light_common.glsl"' in vm and '#include "light_common.glsl"' in world
    for word in ('look_sun_dir', 'look_sun_color', 'ambient_at(', 'tonemap(', 'flash_light('):
        assert word in vm and word in world, word


def test_python_ambient_blend_matches_the_shader_text():
    src = (SHADERS / 'light_common.glsl').read_text(encoding='utf-8')
    assert 'mix(look_ambient_down, look_ambient_up, n.y * 0.5 + 0.5)' in src


# --- exposure ---
def test_exposure_stays_within_limits():
    for look in (LOOK, LookData(sun_color=(0.0, 0.0, 0.0)), LookData(sun_color=(9.0, 9.0, 9.0))):
        assert LENS.exposure_min <= target_exposure(LENS, look) <= LENS.exposure_max


def test_darker_scene_opens_the_exposure():
    dim = LookData(sun_color=(0.2, 0.2, 0.2), ambient_up=(0.05, 0.05, 0.05))
    assert target_exposure(LENS, dim) > target_exposure(LENS, LOOK)


def test_fixed_exposure_when_auto_is_off():
    d = LensData(auto_exposure=0.0)
    assert target_exposure(d, LOOK) == pytest.approx(1.0)
    assert target_exposure(d, LookData(sun_color=(0.1, 0.1, 0.1))) == pytest.approx(1.0)
