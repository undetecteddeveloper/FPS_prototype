"""The rear and front sight must stay on one line through the eye however far the mouse has pushed the gun off the screen centre (user report 7/11/2026), and the Glock's front sight must be
inside its rear notch. Pure math: the same poses the viewmodel applies (child node = gun pose, parent node = aim pose)."""
import math

import pytest

from fps.core.freeaim import barrel_view_dir
from fps.core.sway import aim_translation_weight, apply_chain, apply_pose, ads_target_for
from fps.weapon_data import GLOCK, GUNS, M4


def angle_between(a, b) -> float:
    """Degrees between two vectors; atan2 of |a x b| and a . b stays exact for almost parallel vectors (acos of 'almost 1' loses ~1e-6 degrees even in doubles)."""
    cross = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    return math.degrees(math.atan2(math.sqrt(sum(c * c for c in cross)), sum(x * y for x, y in zip(a, b))))


def sights_at_rest(gun):
    return [tuple(c + h for c, h in zip(p, gun.hip_offset)) for p in gun.ads_sights]


AIMS = [(0.0, 0.0, 0.0), (1.5, 0.9, 0.3), (3.0, 1.8, 0.7), (-6.0, -3.6, -1.3), (10.0, 6.0, 2.2), (-15.0, 9.0, -3.3), (15.0, -9.0, 3.3)]    # (yaw right, pitch up, roll): inside the free zone


@pytest.mark.parametrize('name', sorted(GUNS))
@pytest.mark.parametrize('yaw,pitch,roll', AIMS)
def test_sights_stay_on_the_eye_line_when_the_gun_is_pushed_off_centre(name, yaw, pitch, roll):
    gun = GUNS[name]
    base = ads_target_for(gun)
    rear, front = sights_at_rest(gun)
    aim = (0.0, 0.0, 0.0, pitch, yaw, roll)                      # the aim pose turns the whole gun about the eye; its shift is faded out while aiming
    r = apply_chain(rear, base, aim)
    f = apply_chain(front, base, aim)
    assert angle_between(r, f) < 1e-6, f'{name}: sights {angle_between(r, f):.4f} deg apart'


def test_the_old_way_of_summing_poses_pulled_the_m4_sights_apart():
    """Documents the bug: angles AND shifts added together (the ADS shift not turned with the gun). If this ever stops being > 1 degree the test above is no longer proving anything."""
    base = ads_target_for(M4)
    rear, front = sights_at_rest(M4)
    yaw = 10.0
    summed = tuple(b + a for b, a in zip(base, (yaw * 0.0016, 0.6 * yaw * 0.0016, 0.0, 0.6 * yaw, yaw, yaw * 0.22)))
    assert angle_between(apply_pose(rear, summed), apply_pose(front, summed)) > 1.0


def test_aim_shift_weight_is_all_at_the_hip_and_none_when_aimed():
    assert aim_translation_weight(0.0) == 1.0 and aim_translation_weight(1.0) == 0.0
    values = [aim_translation_weight(i / 10) for i in range(11)]
    assert all(a >= b for a, b in zip(values, values[1:]))


@pytest.mark.parametrize('name', sorted(GUNS))
def test_bullet_goes_where_the_front_sight_is_seen(name):
    """For an aimed gun the barrel axis after the base pose and the aim rotation is the direction from the eye to the front sight (the line passes through the eye)."""
    gun = GUNS[name]
    base = ads_target_for(gun)
    rear, front = sights_at_rest(gun)
    for yaw, pitch, roll in AIMS:
        aim = (0.0, 0.0, 0.0, pitch, yaw, roll)
        d = barrel_view_dir(base, gun.ads_sights, 90.0, 90.0, then=aim)
        to_front = apply_chain(front, base, aim)
        assert angle_between(d, to_front) < 1e-4                        # degrees: float rounding only, a pixel is ~0.07 degrees


def test_barrel_view_dir_without_then_is_unchanged():
    d1 = barrel_view_dir((0, 0, 0, 3.0, 5.0, 1.0), M4.ads_sights, 74.0, 96.0)
    d2 = barrel_view_dir((0, 0, 0, 3.0, 5.0, 1.0), M4.ads_sights, 74.0, 96.0, then=(0, 0, 0, 0, 0, 0))
    assert d1 == pytest.approx(d2)


def test_glock_line_of_sight_passes_through_the_rear_notch_so_the_front_post_shows():
    """Measured on the model (tools/measure/g8_measure.py, 7/11/2026): rear blades top y = -0.0191, notch floor y = -0.0214, front post top y = -0.0199. The rear aiming point must lie in the notch."""
    notch_floor, blade_top, post_top = -0.0214, -0.0191, -0.0199
    rear, front = GLOCK.ads_sights
    assert notch_floor + 0.0004 < rear[1] < blade_top - 0.0004, 'the line of sight would run through the slide (front sight hidden) or over the blades'
    assert notch_floor < front[1] < blade_top + 0.001 and abs(front[1] - post_top) < 1e-4
    assert abs(rear[0] - front[0]) < 5e-4                              # notch and post on the same vertical plane
    # the eye line from the rear point to the front post stays above the flat top of the slide (y = -0.0275) the whole way
    assert min(rear[1], front[1]) > -0.0275 + 0.005


def test_m4_rear_aperture_and_front_post_share_the_same_vertical_plane():
    rear, front = M4.ads_sights
    assert abs(rear[0] - front[0]) < 5e-4
