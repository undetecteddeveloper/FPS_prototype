import math

import pytest

from movement import (MoveState, apply_look, clamp_to_bounds, resolve_state, step_horizontal_velocity, step_toward,
                      step_vertical, target_speed, wants_sprint, wish_direction)
from weapon_data import PlayerParams

P = PlayerParams()


@pytest.mark.parametrize('on_ground,crouching,sprinting,moving,expected', [
    (True, False, False, False, MoveState.IDLE),
    (True, False, False, True, MoveState.WALK),
    (True, False, True, True, MoveState.SPRINT),
    (True, True, False, False, MoveState.CROUCH_IDLE),
    (True, True, False, True, MoveState.CROUCH_WALK),
    (False, False, False, True, MoveState.AIR),
    (False, True, True, True, MoveState.AIR),       # trên không thì mọi thứ khác đều thua
    (True, False, True, False, MoveState.IDLE),     # giữ Shift mà đứng yên thì không phải chạy
])
def test_resolve_state(on_ground, crouching, sprinting, moving, expected):
    assert resolve_state(on_ground, crouching, sprinting, moving) is expected


def test_sprint_needs_forward_and_no_ads():
    assert wants_sprint(True, 1.0, False)
    assert not wants_sprint(True, 0.0, False)
    assert not wants_sprint(True, -1.0, False)
    assert not wants_sprint(True, 1.0, True)
    assert not wants_sprint(False, 1.0, False)


def test_speed_order_and_ads_slowdown():
    assert target_speed(MoveState.SPRINT, P) > target_speed(MoveState.WALK, P) > target_speed(MoveState.CROUCH_WALK, P)
    assert target_speed(MoveState.WALK, P, ads=True) == pytest.approx(P.walk_speed * P.ads_speed_multiplier)


def test_wish_direction_follows_yaw():
    assert wish_direction(1, 0, 0) == pytest.approx((0, 1))                 # yaw 0: tiến về +z
    assert wish_direction(1, 0, 90) == pytest.approx((1, 0))                # yaw 90: tiến về +x
    assert wish_direction(0, 1, 0) == pytest.approx((1, 0))                 # sang phải khi nhìn +z là +x
    assert wish_direction(0, 1, 90) == pytest.approx((0, -1))
    assert wish_direction(0, 0, 123) == (0.0, 0.0)


def test_diagonal_is_not_faster():
    x, z = wish_direction(1, 1, 0)
    assert math.hypot(x, z) == pytest.approx(1.0)


def test_velocity_reaches_target_without_overshoot():
    vx = vz = 0.0
    wish = (0.0, 1.0)
    for _ in range(100):
        vx, vz = step_horizontal_velocity(vx, vz, wish, 4.5, 45.0, 1 / 60)
        assert math.hypot(vx, vz) <= 4.5 + 1e-9
    assert (vx, vz) == pytest.approx((0.0, 4.5))


def test_acceleration_is_limited():
    vx, vz = step_horizontal_velocity(0, 0, (0, 1), 4.5, 45.0, 0.01)
    assert math.hypot(vx, vz) == pytest.approx(0.45)


def test_air_control_is_weaker_than_ground():
    ground = step_horizontal_velocity(0, 0, (1, 0), 4.5, P.accel_ground, 1 / 60)
    air = step_horizontal_velocity(0, 0, (1, 0), 4.5, P.accel_air, 1 / 60)
    assert air[0] < ground[0]


def test_jump_height_matches_physics():
    y, vy, grounded = 0.0, P.jump_speed, False
    apex = 0.0
    t = 0.0
    dt = 1 / 240
    while not grounded and t < 5:
        y, vy, grounded = step_vertical(y, vy, P.gravity, dt)
        apex = max(apex, y)
        t += dt
    assert apex == pytest.approx(P.jump_speed ** 2 / (2 * P.gravity), abs=0.01)
    assert grounded and y == 0.0 and vy == 0.0
    assert t == pytest.approx(2 * P.jump_speed / P.gravity, abs=0.02)


def test_standing_on_ground_stays_grounded():
    y, vy, grounded = step_vertical(0.0, 0.0, P.gravity, 1 / 60)
    assert (y, vy, grounded) == (0.0, 0.0, True)


def test_step_toward():
    assert step_toward(1.62, 1.15, 4.0, 0.05) == pytest.approx(1.42)
    assert step_toward(1.62, 1.15, 4.0, 1.0) == 1.15
    assert step_toward(1.15, 1.62, 4.0, 1.0) == 1.62


def test_clamp_to_bounds():
    assert clamp_to_bounds(10, -50, (-7, 7, -15, 198)) == (7, -15)
    assert clamp_to_bounds(1, 2, (-7, 7, -15, 198)) == (1, 2)


def test_look_directions_and_clamp():
    yaw, pitch = apply_look(0, 0, 0.1, 0.0, 45, 89)
    assert yaw == pytest.approx(4.5) and pitch == 0
    yaw, pitch = apply_look(0, 0, 0.0, 0.1, 45, 89)       # chuột lên => ngẩng lên => pitch âm
    assert pitch == pytest.approx(-4.5)
    _, pitch = apply_look(0, 80, 0, -1.0, 45, 89)           # kéo chuột xuống rất mạnh => bị chặn ở 89
    assert pitch == 89
    yaw, _ = apply_look(359, 0, 0.1, 0, 45, 89)
    assert 0 <= yaw < 360


@pytest.mark.parametrize('fps', [30, 60, 144, 240])
def test_jump_apex_does_not_depend_on_fps(fps):
    y, vy, grounded = 0.0, P.jump_speed, False
    apex = 0.0
    for _ in range(fps * 3):
        y, vy, grounded = step_vertical(y, vy, P.gravity, 1 / fps)
        apex = max(apex, y)
        if grounded:
            break
    # sai số nhỏ chỉ do đỉnh rơi giữa hai khung hình
    assert apex == pytest.approx(P.jump_speed ** 2 / (2 * P.gravity), abs=0.06)


def test_aim_direction():
    from movement import aim_direction
    assert aim_direction(0, 0) == pytest.approx((0, 0, 1))
    assert aim_direction(90, 0) == pytest.approx((1, 0, 0))
    assert aim_direction(0, 90) == pytest.approx((0, -1, 0), abs=1e-9)      # cúi xuống
    assert aim_direction(0, -90) == pytest.approx((0, 1, 0), abs=1e-9)      # ngẩng lên
    for yaw, pitch in ((17, 33), (200, -45), (359, 89)):
        assert math.hypot(*aim_direction(yaw, pitch)[:2], aim_direction(yaw, pitch)[2]) == pytest.approx(1.0)
