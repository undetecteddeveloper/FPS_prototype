"""Độ tản đạn (toán thuần, không import ursina).

Góc tản = nửa góc của hình nón quanh hướng nhìn = nền theo trạng thái + bloom cộng dồn theo từng phát.
Nền đọc từ MoveState của người chơi (nguồn duy nhất); `ads_amount` (0 hông .. 1 ngắm hẳn) nội suy giữa nền hông và nền ngắm,
nên phát bắn lúc đang vào ADS tản theo mức hiện tại của ADS.
"""
import math

from movement import MoveState
from weapon_data import AccuracyData

MOVING = (MoveState.WALK, MoveState.CROUCH_WALK, MoveState.SPRINT)
CROUCHING = (MoveState.CROUCH_IDLE, MoveState.CROUCH_WALK)


class Accuracy:
    def __init__(self, data: AccuracyData):
        self.d = data
        self.bloom = 0.0
        self.since_shot = 1e9             # s kể từ phát cuối

    def hip_base(self, state: MoveState) -> float:
        d = self.d
        base = {MoveState.IDLE: d.stand, MoveState.WALK: d.walk, MoveState.SPRINT: d.sprint,
                MoveState.CROUCH_IDLE: d.stand, MoveState.CROUCH_WALK: d.walk, MoveState.AIR: d.air}[state]
        return base * d.crouch_multiplier if state in CROUCHING else base

    def ads_base(self, state: MoveState) -> float:
        d = self.d
        if state is MoveState.AIR:
            return d.air                  # nhảy thì ngắm cũng không chính xác hơn
        base = d.ads_move if state in MOVING else d.ads
        return base * d.crouch_multiplier if state in CROUCHING else base

    def base(self, state: MoveState, ads_amount: float = 0.0) -> float:
        hip, ads = self.hip_base(state), self.ads_base(state)
        return hip + (ads - hip) * ads_amount

    def angle(self, state: MoveState, ads_amount: float = 0.0) -> float:
        """Nửa góc hình nón (độ) hiện tại."""
        d = self.d
        bloom_effect = 1.0 + (d.ads_bloom_multiplier - 1.0) * ads_amount
        return self.base(state, ads_amount) + self.bloom * bloom_effect

    def on_shot(self):
        self.bloom = min(self.bloom + self.d.bloom_per_shot, self.d.bloom_max)
        self.since_shot = 0.0

    def update(self, dt: float):
        d = self.d
        recovering = min(dt, max(0.0, self.since_shot + dt - d.bloom_recovery_delay))   # chỉ phần dt sau thời gian chờ
        self.since_shot += dt
        self.bloom = max(0.0, self.bloom - d.bloom_recovery * recovering)


def random_in_cone(direction: tuple, half_angle_deg: float, rng) -> tuple:
    """Hướng ngẫu nhiên đều trên đĩa tròn bán kính `half_angle_deg` quanh `direction` (vector đơn vị)."""
    if half_angle_deg <= 0:
        return direction
    dx, dy, dz = direction
    ux, uy, uz = (0.0, 1.0, 0.0) if abs(dy) < 0.9 else (1.0, 0.0, 0.0)
    rx, ry, rz = uy * dz - uz * dy, uz * dx - ux * dz, ux * dy - uy * dx      # right = up x d
    rn = math.sqrt(rx * rx + ry * ry + rz * rz)
    rx, ry, rz = rx / rn, ry / rn, rz / rn
    vx, vy, vz = dy * rz - dz * ry, dz * rx - dx * rz, dx * ry - dy * rx      # up' = d x right
    off = math.tan(math.radians(half_angle_deg) * math.sqrt(rng.random()))    # sqrt: đều theo diện tích đĩa
    phi = 2.0 * math.pi * rng.random()
    c, s = math.cos(phi) * off, math.sin(phi) * off
    x, y, z = dx + rx * c + vx * s, dy + ry * c + vy * s, dz + rz * c + vz * s
    n = math.sqrt(x * x + y * y + z * z)
    return x / n, y / n, z / n


def angle_between(a: tuple, b: tuple) -> float:
    """Góc (độ) giữa hai vector. Dùng atan2(|tích có hướng|, tích vô hướng) vì acos mất chính xác ở góc nhỏ:
    dot = 1 - 1e-8 do làm tròn float32 đã cho sai ~0,01 độ."""
    cx, cy, cz = a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]
    return math.degrees(math.atan2(math.sqrt(cx * cx + cy * cy + cz * cz), a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))


def crosshair_gap(angle_deg: float, vfov_half_tan: float) -> float:
    """Khoảng từ tâm màn hình tới mép trong vạch tâm ngắm (đơn vị UI: chiều cao cửa sổ = 1) để vạch nằm đúng
    trên rìa hình nón tản. vfov_half_tan = tan(nửa FOV dọc) của camera thế giới."""
    return 0.5 * math.tan(math.radians(angle_deg)) / vfov_half_tan
