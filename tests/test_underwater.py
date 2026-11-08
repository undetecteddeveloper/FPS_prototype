"""G12: the camera at / under the water (core/underwater.py), walking on the deep bottom, the basin mesh, firing under the water, the F2 rows."""
import json
import math

import pytest

from fps.core import underwater as uw
from fps.core.graphics import GraphicsSettings, OPTIONS, cycle, resolve, settings_for
from fps.core.poolmap import basin_faces, build_map, ramp_quad
from fps.core.splash import wade_speed_factor, water_speed_factor
from fps.core.waves import ambient_slope
from fps.weapon_data import MapData, SplashData, UnderwaterData, WaterData

D, U, W, S = MapData(), UnderwaterData(), WaterData(), SplashData()
ASPECT = 16 / 9


def line_for(eye_y, surface, pitch_deg):
    """The world camera never rolls: right is horizontal, up.y = cos(pitch)."""
    return uw.port_line(eye_y, surface, 0.0, math.cos(math.radians(pitch_deg)), ASPECT, U.port_half)


def test_ambient_height_is_the_integral_of_the_ambient_slope():
    h = 1e-4
    for x, z, t in ((0.3, -2.0, 0.0), (4.1, 7.7, 3.3), (-5.0, 1.0, 12.5)):
        dhdx = (uw.ambient_height(x + h, z, t, W) - uw.ambient_height(x - h, z, t, W)) / (2 * h)
        dhdz = (uw.ambient_height(x, z + h, t, W) - uw.ambient_height(x, z - h, t, W)) / (2 * h)
        assert (dhdx, dhdz) == pytest.approx(ambient_slope(x, z, t, W), abs=1e-6)


def test_eye_above_or_under_the_surface_includes_the_waves():
    x, z = 0.5, 5.0
    ts = [i * 0.37 for i in range(200)]
    heights = [uw.surface_y(x, z, t, D.water_y, W) for t in ts]
    assert max(heights) - min(heights) > 1e-3                                        # the level moves
    t_hi = ts[heights.index(max(heights))]
    t_lo = ts[heights.index(min(heights))]
    eye = (max(heights) + min(heights)) / 2                                         # an eye between the crest and the trough: under at one moment, above at the other
    assert uw.port_line(eye, uw.surface_y(x, z, t_hi, D.water_y, W), 0, 1, ASPECT, U.port_half)[2] < 0
    assert uw.port_line(eye, uw.surface_y(x, z, t_lo, D.water_y, W), 0, 1, ASPECT, U.port_half)[2] > 0


def test_waterline_on_screen_follows_eye_height_and_pitch():
    surface = D.water_y
    assert uw.waterline_y(line_for(surface, surface, 0)) == pytest.approx(0.0)         # eye exactly at the water: the line through the middle
    y_low = uw.waterline_y(line_for(surface + 0.02, surface, 0))
    assert y_low == pytest.approx(-0.02 / U.port_half)                                 # eye 2 cm above: the line below the middle, the lower part wet
    assert uw.is_wet(line_for(surface + 0.02, surface, 0), 0.0, -0.9) and not uw.is_wet(line_for(surface + 0.02, surface, 0), 0.0, 0.0)
    y_tilt = uw.waterline_y(line_for(surface + 0.02, surface, 40))
    assert y_tilt == pytest.approx(-0.02 / (U.port_half * math.cos(math.radians(40))))   # looking down tilts the port: the same 2 cm reach further across the frame
    assert y_tilt < y_low
    assert uw.waterline_y(line_for(surface - 0.02, surface, 0)) == pytest.approx(0.4)  # 2 cm under: only the top 30 % is dry


def test_coverage():
    s = D.water_y
    assert uw.coverage(line_for(s + 0.5, s, 0)) == (False, False)                       # well above: nothing wet
    assert uw.coverage(line_for(s - 0.5, s, 0)) == (True, True)                         # well under: everything wet
    any_wet, all_wet = uw.coverage(line_for(s, s, 0))
    assert any_wet and not all_wet
    assert uw.coverage(line_for(s + U.port_half + 0.001, s, 0), amp=0.0) == (False, False)
    assert uw.coverage(line_for(s + U.port_half - 0.001, s, 0), amp=0.005)[0]           # the wobble can lap over the edge: count it


def test_looking_straight_down_the_port_is_all_or_nothing():
    s = D.water_y
    line = line_for(s + 0.01, s, 90)
    assert uw.waterline_y(line) is None and uw.coverage(line) == (False, False)
    assert uw.coverage(line_for(s - 0.01, s, 90)) == (True, True)


def test_fog_halves_and_saturates_with_distance():
    c = (1.0, 1.0, 1.0)
    assert uw.fog(c, 0.0, U, W.absorption) == pytest.approx(c)
    far = uw.fog(c, 40.0, U, W.absorption)
    assert far == pytest.approx(U.fog_color, abs=1e-4)                                 # far away the water is just its colour
    red_mid, blue_mid = uw.fog(c, 2.0, U, W.absorption)[0], uw.fog(c, 2.0, U, W.absorption)[2]
    assert red_mid < blue_mid                                                          # red goes first
    k = W.absorption[2] * U.absorb_scale + U.turbidity
    half = math.log(2) / k
    assert uw.fog((1, 1, 1), half, U, (0, 0, W.absorption[2]))[2] == pytest.approx(0.5 + 0.5 * U.fog_color[2])
    assert 1.0 < half < 4.0                                                            # murky a few metres away


def test_walking_under_the_water_is_slower_than_chest_deep_wading():
    chest = wade_speed_factor(D.wade_depth, D.wade_depth, S.wade_slow)
    under = water_speed_factor(2.0, D.wade_depth, S.wade_slow, True, S.under_slow)
    assert under < chest < 1.0
    assert water_speed_factor(0.5, D.wade_depth, S.wade_slow, False, S.under_slow) == wade_speed_factor(0.5, D.wade_depth, S.wade_slow)


def test_basin_mesh_covers_the_pool_under_the_water():
    pm = build_map(D)
    faces = basin_faces(pm)
    x0, x1, z0, z1, wy = pm.water
    floor = sum(f.area for f in faces if f.axis == 1)
    corners, n = ramp_quad(pm)
    assert floor == pytest.approx((x1 - x0) * (z1 - z0) - (x1 - x0) * (D.slope_z[1] - D.slope_z[0]), rel=1e-6)   # every floor / step top, minus what the ramp hides
    assert math.dist(corners[0], corners[3]) > 0 and n[1] > 0.9 and n[2] > 0             # the slope faces up and toward the deep end
    for f in faces:
        c = f.point((f.u0 + f.u1) / 2, (f.v0 + f.v1) / 2)
        assert x0 - 1e-6 <= c[0] <= x1 + 1e-6 and z0 - 1e-6 <= c[2] <= z1 + 1e-6
        assert c[1] < wy
        if f.axis != 1:
            assert f.v1 <= wy - 0.02 + 1e-6                                               # stops where the room's pool wall starts: no coplanar overlap
    deep_wall = [f for f in faces if f.axis == 2 and f.sign == -1]                      # the north wall of the deep end
    assert deep_wall and min(f.v0 for f in deep_wall) == pytest.approx(D.pool_deep)


def test_graphics_rows_for_the_new_effects():
    fields = [f for f, _, _ in OPTIONS]
    assert 'under' in fields and 'wetlens' not in fields                               # the wet lens after surfacing was removed 8/11/2026
    low, high = resolve(settings_for(0)), resolve(settings_for(2))
    assert low.under == 0 and high.under == 1
    assert resolve(cycle(GraphicsSettings(), 'under', 1)).under == 0


def test_a_graphics_file_saved_with_the_removed_wet_lens_row_still_loads():
    """user_graphics.json written before 8/11/2026 holds "wetlens": it is skipped, every other row (and the preset) is kept."""
    from fps.core.graphics import from_json, to_json
    raw = json.loads(to_json(settings_for(1)))
    raw['graphics']['wetlens'] = True
    assert from_json(json.dumps(raw)) == settings_for(1)
    raw['graphics']['wetlens'] = 'not even a bool'
    assert from_json(json.dumps(raw)) == settings_for(1)


def test_no_shot_under_the_water_and_the_notice_hook(monkeypatch):
    from fps.game import gltf_patch
    gltf_patch.apply()
    from ursina import held_keys
    from fps.core.movement import MoveState
    from fps.game.combat import Combat
    from fps.weapon_data import GameParams

    class FakePlayer:
        state, ads_amount, crouching, sprint_amount, ui_open, can_fire, ads_blocked, reloading = MoveState.IDLE, 0.0, False, 0.0, False, True, False, False

        def aim_ray(self):
            return (0.0, -0.4, 9.0), (0.0, 0.0, 1.0)

        def turn_rate(self, dt):
            return 0.0

        def kick_view(self, up, right):
            pass

    c = Combat(GameParams(), FakePlayer(), [])
    c.require_locked_mouse = False
    notices = []
    c.on_blocked = lambda reason='water': notices.append(1)
    monkeypatch.setitem(held_keys, 'left mouse', 1)
    c.underwater = True
    for _ in range(30):
        c.pressed = True
        c.update(1 / 60)
    assert c.shots_fired == 0 and len(notices) == 30 and c.blocked_pulls == 30
    c.underwater = False
    c.pressed = True
    for _ in range(5):
        c.update(1 / 60)
    assert c.shots_fired >= 1                                                           # the same gun fires as soon as the head is out


def test_foley_bank_plays_the_muffled_copy_only_under_the_water():
    import random
    from fps.game import gltf_patch
    gltf_patch.apply()
    from fps.game.foley import _Bank
    normal = [[object(), object()] for _ in range(3)]
    muffled = [[object(), object()] for _ in range(3)]
    bank = _Bank(normal, muffled)
    rng = random.Random(1)
    for _ in range(20):
        v, s = bank.next_sound(rng, under=False)
        assert s in normal[v]
        v, s = bank.next_sound(rng, under=True)
        assert s in muffled[v]
    plain = _Bank(normal)                                                                # no twins (an old install): the normal copy, no error
    v, s = plain.next_sound(rng, under=True)
    assert s in normal[v]


def test_meniscus_band_visible_matches_a_dense_grid():
    """G13: band_visible (the lens may use its dry build when False) never says False where some point of the read area lies inside the band."""
    import random
    from fps.core.underwater import band_visible, port_height
    rnd = random.Random(7)
    reach, half = 1.25, 0.012
    for _ in range(400):
        line = (rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3), rnd.uniform(-0.8, 0.8))
        amp = rnd.choice((0.0, 0.004))
        hit = False
        for i in range(41):
            for j in range(41):
                x, y = -reach + 2 * reach * i / 40, -reach + 2 * reach * j / 40
                for t in (0.0, 0.7, 1.9):
                    if abs(port_height(line, x, y, t, amp)) < half:
                        hit = True
        if hit:
            assert band_visible(line, half, amp, reach), line
    assert not band_visible((0.0, 0.0, 10.0), half)          # on the deck: the line is far away
    assert band_visible((0.1, 0.2, 0.0), half)               # the waterline right across the middle
