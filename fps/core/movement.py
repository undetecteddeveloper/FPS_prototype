"""Toán thuần của di chuyển (không import ursina, nên test được không cần cửa sổ).

Hệ trục như Ursina: y lên, z ra trước. yaw = 0 nhìn về +z, yaw = 90 nhìn về +x.
Trạng thái di chuyển là NGUỒN DUY NHẤT cho tốc độ, spread và sway.
"""
import math
from enum import Enum

from fps.weapon_data import PlayerParams


class MoveState(Enum):
    IDLE = 'idle'
    WALK = 'walk'
    SPRINT = 'sprint'
    CROUCH_IDLE = 'crouch_idle'
    CROUCH_WALK = 'crouch_walk'
    AIR = 'air'


def wants_sprint(sprint_key: bool, forward: float, ads: bool) -> bool:
    """Chạy nước rút chỉ khi tiến về phía trước và không ngắm."""
    return sprint_key and forward > 0 and not ads


def resolve_state(on_ground: bool, crouching: bool, sprinting: bool, moving: bool) -> MoveState:
    if not on_ground:
        return MoveState.AIR
    if sprinting and moving:
        return MoveState.SPRINT
    if crouching:
        return MoveState.CROUCH_WALK if moving else MoveState.CROUCH_IDLE
    return MoveState.WALK if moving else MoveState.IDLE


def target_speed(state: MoveState, p: PlayerParams, ads=0.0) -> float:
    """Tốc độ mặt đất mà trạng thái này hướng tới. Trên không: giữ đà, nên không có tốc độ mục tiêu.
    `ads`: 0..1 (hoặc bool); đang vào ADS thì tốc độ giảm dần theo."""
    base = {
        MoveState.IDLE: p.walk_speed,
        MoveState.WALK: p.walk_speed,
        MoveState.SPRINT: p.sprint_speed,
        MoveState.CROUCH_IDLE: p.crouch_speed,
        MoveState.CROUCH_WALK: p.crouch_speed,
        MoveState.AIR: p.walk_speed,
    }[state]
    return base * (1.0 + (p.ads_speed_multiplier - 1.0) * float(ads))


def wish_direction(forward: float, strafe: float, yaw_deg: float) -> tuple:
    """Hướng muốn đi trong thế giới (đã chuẩn hoá, tối đa độ dài 1) từ phím và góc nhìn."""
    length = math.hypot(forward, strafe)
    if length < 1e-9:
        return 0.0, 0.0
    if length > 1.0:
        forward, strafe = forward / length, strafe / length
    yaw = math.radians(yaw_deg)
    fx, fz = math.sin(yaw), math.cos(yaw)
    rx, rz = math.cos(yaw), -math.sin(yaw)
    return fx * forward + rx * strafe, fz * forward + rz * strafe


def step_horizontal_velocity(vx: float, vz: float, wish: tuple, speed: float, accel: float, dt: float) -> tuple:
    """Kéo vận tốc ngang về wish * speed, mỗi bước đổi tối đa accel * dt."""
    tx, tz = wish[0] * speed, wish[1] * speed
    dx, dz = tx - vx, tz - vz
    dist = math.hypot(dx, dz)
    max_change = accel * dt
    if dist <= max_change or dist < 1e-12:
        return tx, tz
    k = max_change / dist
    return vx + dx * k, vz + dz * k


def step_vertical(y: float, vy: float, gravity: float, dt: float, ground_y: float = 0.0) -> tuple:
    """Rơi tự do, công thức chính xác cho trọng lực không đổi (độ cao nhảy không phụ thuộc FPS).
    Trả về (y, vy, đang_trên_đất)."""
    y += vy * dt - 0.5 * gravity * dt * dt
    vy -= gravity * dt
    if y <= ground_y:
        return ground_y, 0.0, True
    return y, vy, False


def smoothstep(x: float) -> float:
    """Đường cong êm 0..1 (đạo hàm 0 ở hai đầu): dùng để vào/ra ADS và tư thế chạy không bị khựng đầu cuối."""
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def step_toward(current: float, target: float, rate: float, dt: float) -> float:
    delta = target - current
    step = rate * dt
    if abs(delta) <= step:
        return target
    return current + math.copysign(step, delta)


def clamp_to_bounds(x: float, z: float, bounds: tuple) -> tuple:
    """bounds = (x_min, x_max, z_min, z_max)."""
    return min(max(x, bounds[0]), bounds[1]), min(max(z, bounds[2]), bounds[3])


def apply_look(yaw: float, pitch: float, dx: float, dy: float, degrees_per_unit: float, pitch_limit: float) -> tuple:
    """dx, dy = chuột đi bao nhiêu (đơn vị: chiều cao cửa sổ = 1). Chuột lên (dy > 0) thì ngẩng lên (pitch giảm,
    vì rotation_x dương của Ursina là cúi xuống)."""
    yaw = (yaw + dx * degrees_per_unit) % 360.0
    pitch = min(max(pitch - dy * degrees_per_unit, -pitch_limit), pitch_limit)
    return yaw, pitch


def aim_direction(yaw_deg: float, pitch_deg: float) -> tuple:
    """Vector hướng nhìn đơn vị. pitch dương = cúi xuống (như rotation_x của Ursina)."""
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    cp = math.cos(pitch)
    return math.sin(yaw) * cp, -math.sin(pitch), math.cos(yaw) * cp
