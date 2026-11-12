"""G14 weapon collision, 'High Ready' (core/weaponcol.py): the probe, the raise amount, the pose that keeps the hands in the frame, the trigger / aim lock."""
import math

import pytest

from fps.core.sway import Sway, SwayInput, apply_pose
from fps.core.movement import MoveState
from fps.core.weaponcol import WallReady, probe_distance, reach_of, solids_in_range, wall_target
from fps.weapon_data import GLOCK, GUNS, M4, GameParams, WallData


class _Owner:
    is_water = False


def wall_ahead(z0, thick=0.4):
    """A big wall box across the view whose face is at z = z0 (yaw 0 looks along +z)."""
    return [((-20.0, -5.0, z0), (20.0, 8.0, z0 + thick), _Owner())]


def test_reach_is_the_eye_to_muzzle_distance_of_the_hip_pose():
    assert 0.74 < reach_of(M4) < 0.82
    assert 0.55 < reach_of(GLOCK) < 0.66
    assert reach_of(M4) > reach_of(GLOCK)


def test_wall_target_is_zero_far_one_close_and_linear_between():
    reach, clear, full = 0.78, 1.12, 0.45
    assert wall_target(3.0, reach, clear, full) == 0.0
    assert wall_target(reach * clear, reach, clear, full) == 0.0
    assert wall_target(reach * full, reach, clear, full) == 1.0 and wall_target(0.1, reach, clear, full) == 1.0
    mid = (reach * clear + reach * full) / 2.0
    assert wall_target(mid, reach, clear, full) == pytest.approx(0.5)
    ds = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]
    vals = [wall_target(d, reach, clear, full) for d in ds]
    assert vals == sorted(vals)                                             # the closer the wall, the higher the gun


def test_body_radius_is_always_inside_the_full_raise_for_the_rifle():
    """The body stops 0.30 m from a wall: facing it head on the M4 is fully raised (the user: the closer, the higher)."""
    d = WallData()
    for gun in (M4, GLOCK, GUNS['m1014']):
        assert wall_target(0.30, reach_of(gun), d.clear_ratio, d.full_ratio) == 1.0       # the closest a wall gets (body radius 0.30 m): every gun fully up


def test_probe_distance_hits_the_wall_ahead_and_ignores_water_and_far_walls():
    eye = (0.0, 1.6, 0.0)
    assert probe_distance(eye, 0.0, 0.0, wall_ahead(0.5), 1.0) == pytest.approx(0.5, abs=1e-6)
    assert probe_distance(eye, 0.0, 0.0, wall_ahead(3.0), 1.0) == 1.0           # beyond the probe range: nothing
    assert probe_distance(eye, 180.0, 0.0, wall_ahead(0.5), 1.0) == 1.0         # looking away from it
    water = _Owner()
    water.is_water = True
    sea = [((-20.0, 1.0, -20.0), (20.0, 1.2, 20.0), water)]
    assert probe_distance(eye, 0.0, 30.0, sea, 2.0) == 2.0                      # the water surface is not a wall


def test_probe_distance_sees_an_oblique_wall_and_a_corner_with_the_side_rays():
    eye = (0.0, 1.6, 0.0)
    corner = [((0.15, -5.0, 0.0), (5.0, 8.0, 5.0), _Owner())]                    # a wall to the right whose near edge is 0.15 m off the view line
    assert probe_distance(eye, 0.0, 0.0, corner, 1.0, side_angle=0.0) == 1.0     # the centre ray alone misses it
    assert probe_distance(eye, 0.0, 0.0, corner, 1.0, side_angle=18.0) < 1.0     # the side ray finds it
    oblique = wall_ahead(0.4)
    assert probe_distance(eye, 60.0, 0.0, oblique, 2.0, side_angle=0.0) == pytest.approx(0.4 / math.cos(math.radians(60.0)), abs=1e-3)   # an oblique view: the slant distance
    # with the side rays the nearest part of the wall inside the cone counts (the ray turned toward the wall normal is shorter)
    assert probe_distance(eye, 60.0, 0.0, oblique, 2.0, side_angle=18.0) == pytest.approx(0.4 / math.cos(math.radians(42.0)), abs=1e-3)


def test_solids_in_range_prefilters_by_distance():
    eye = (0.0, 1.6, 0.0)
    near, far = wall_ahead(0.5)[0], ((-1.0, 0.0, 30.0), (1.0, 3.0, 31.0), _Owner())
    assert solids_in_range([near, far], eye, 1.0) == [near]


def test_raise_amount_follows_the_in_and_out_times_and_is_frame_rate_independent():
    d = WallData()
    reach = reach_of(M4)
    for fps in (30, 60, 144):
        w = WallReady(d)
        t = 0.0
        while w.amount < 1.0 and t < 2.0:
            w.update(1.0 / fps, 0.3, reach)
            t += 1.0 / fps
        assert d.in_time - 1.0 / fps - 1e-6 <= t <= d.in_time + 1.0 / fps + 1e-6
        t = 0.0
        while w.amount > 0.0 and t < 3.0:
            w.update(1.0 / fps, 5.0, reach)
            t += 1.0 / fps
        assert d.out_time - 1.0 / fps - 1e-6 <= t <= d.out_time + 1.0 / fps + 1e-6


def test_block_flag_has_hysteresis_so_the_trigger_does_not_flicker():
    d = WallData()
    w = WallReady(d)
    reach = reach_of(M4)
    seen = []
    # a distance that settles at a raise between block_at - hysteresis and block_at
    mid = reach * (d.clear_ratio - (d.clear_ratio - d.full_ratio) * (d.block_at - d.block_hysteresis / 2.0))
    for _ in range(120):
        w.update(1 / 60, 0.3, reach)
    assert w.blocked
    for _ in range(300):
        w.update(1 / 60, mid, reach)
        seen.append(w.blocked)
    assert all(seen)                                                         # stays locked inside the hysteresis band
    for _ in range(300):
        w.update(1 / 60, 5.0, reach)
    assert not w.blocked
    for _ in range(300):
        w.update(1 / 60, mid, reach)
    assert not w.blocked                                                     # and does not lock again inside the band when coming from above


@pytest.mark.parametrize('key', ['m4', 'glock', 'm1014'])
def test_wall_pose_points_the_barrel_up_and_keeps_the_receiver_where_the_hands_rest(key):
    """The pitch turns the gun about the EYE: without the shift the receiver (and the hands with it) would fly out of the top of the frame.
    `hip_offset` is part of the model's position inside the turned node, so it turns with the gun (Glock: 0.15 m farther out, hence its own shift)."""
    g = GUNS[key]
    rest, wall = g.sway.rest_pose, g.sway.wall_pose
    total = tuple(a + b for a, b in zip(rest, wall))
    hip = g.hip_offset
    rear, front = g.ads_sights
    shift = lambda p: tuple(p[i] + hip[i] for i in range(3))
    r0, f0 = apply_pose(shift(rear), rest), apply_pose(shift(front), rest)
    r1, f1 = apply_pose(shift(rear), total), apply_pose(shift(front), total)
    m1 = apply_pose(shift(g.muzzle), total)
    axis = (f1[0] - r1[0], f1[1] - r1[1], f1[2] - r1[2])
    pitch_up = math.degrees(math.atan2(axis[1], math.hypot(axis[0], axis[2])))
    assert pitch_up > 55.0                                                   # the barrel points steeply up
    f_axis = (f0[0] - r0[0], f0[1] - r0[1], f0[2] - r0[2])
    assert abs(math.degrees(math.atan2(f_axis[1], f_axis[2]))) < 5.0         # (at rest it points straight ahead)
    assert math.dist(r1, r0) < 0.07                                          # the receiver / hands stay within 7 cm of where they rest: same place on the screen
    assert r1[2] > 0.05 and m1[1] > r1[1] + 0.1                              # in front of the eye, the muzzle clearly above the receiver
    assert abs(math.degrees(math.atan2(r1[1], r1[2])) - math.degrees(math.atan2(r0[1], r0[2]))) < 20.0


def test_sway_blends_in_the_wall_pose_and_it_takes_over_from_aiming_and_sprinting():
    g = M4
    sway = Sway(g.sway, (0.1, 0.0, 0.0, 0.0, 0.0, 0.0))
    idle = lambda ads=0.0, sprint=0.0, wall=0.0: SwayInput(MoveState.IDLE, 0.0, ads, sprint, wall_amount=wall)
    base = sway.update(1 / 60, idle())
    full = sway.update(1 / 60, idle(wall=1.0))
    assert full[3] - base[3] == pytest.approx(g.sway.wall_pose[3], abs=0.6)         # the pitch rises by wall_pose's pitch (the small bob / breath differences aside)
    ads_wall = sway.update(1 / 60, idle(ads=1.0, wall=1.0))
    assert ads_wall[0] == pytest.approx(full[0], abs=0.02)                          # fully raised: the aim pose (x +0.1) no longer applies
    sprint_wall = sway.update(1 / 60, idle(sprint=1.0, wall=1.0))
    assert sprint_wall[3] == pytest.approx(full[3], abs=1.0) and sprint_wall[1] == pytest.approx(full[1], abs=0.01)   # nor the sprint pose
    half = sway.update(1 / 60, idle(wall=0.5))
    assert base[3] < half[3] < full[3]


def test_trigger_is_locked_while_raised_and_the_notice_hook_gets_the_reason(monkeypatch):
    from fps.game import gltf_patch
    gltf_patch.apply()
    from ursina import held_keys
    from fps.game.combat import Combat

    class FakePlayer:
        state, ads_amount, crouching, sprint_amount, ui_open, can_fire, ads_blocked, reloading = MoveState.IDLE, 0.0, False, 0.0, False, True, False, False

        def aim_ray(self):
            return (0.0, 1.6, 0.0), (0.0, 0.0, 1.0)

        def turn_rate(self, dt):
            return 0.0

        def kick_view(self, up, right):
            pass

    c = Combat(GameParams(), FakePlayer(), [])
    c.require_locked_mouse = False
    reasons = []
    c.on_blocked = reasons.append
    monkeypatch.setitem(held_keys, 'left mouse', 1)
    c.wall_blocked = True
    for _ in range(30):
        c.pressed = True
        c.update(1 / 60)
    assert c.shots_fired == 0 and reasons == ['wall'] * 30 and c.blocked_pulls == 30
    c.wall_blocked = False
    c.pressed = True
    for _ in range(5):
        c.update(1 / 60)
    assert c.shots_fired >= 1                                                       # fires again as soon as the gun comes down


def test_reloading_is_not_locked_by_the_wall():
    """The lock is in the trigger path and the aim button only: request_reload does not look at it (user 7/11/2026: 'nạp đạn vẫn được')."""
    import inspect
    from fps.game.combat import Combat
    src = inspect.getsource(Combat.request_reload)
    assert 'wall_blocked' not in src


def test_aim_button_is_ignored_while_the_wall_lock_is_on(monkeypatch):
    from fps.game import gltf_patch
    gltf_patch.apply()
    from ursina import held_keys
    from fps.game.player import Player
    from fps.weapon_data import M4 as GUN, PlayerParams
    bounds = (-9.0, 9.0, -14.0, 14.0)
    p = Player(PlayerParams(), bounds, GUN)
    monkeypatch.setitem(held_keys, 'right mouse', 1)
    assert p.read_keys()['ads'] is True
    p.wall_blocked = True
    assert p.read_keys()['ads'] is False
