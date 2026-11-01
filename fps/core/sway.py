"""Súng đung đưa trên màn hình (toán thuần, không import ursina).

Gồm: thở lúc đứng yên, lag theo chuột, bob theo bước chân, tư thế chạy nước rút, quán tính theo chuyển động dọc
của camera (nhảy, ngồi, rơi) + cú nhún khi chạm đất, và tư thế ADS đưa mắt ngắm vào giữa màn hình.

Mọi tư thế là (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải), mét và độ, cùng quy ước với
`GunKick.pose`; `Viewmodel.update` cộng chúng lại rồi đặt lên nút `sway`. Trạng thái di chuyển đọc từ MoveState.
"""
import math
from dataclasses import dataclass

from fps.core.movement import MoveState, smoothstep
from fps.core.spring import Spring, impulse_gain
from fps.weapon_data import GunData, SwayData

ZERO_POSE = (0.0,) * 6
MOVING_ON_GROUND = (MoveState.WALK, MoveState.SPRINT, MoveState.CROUCH_WALK)


@dataclass
class SwayInput:
    """Ảnh chụp chuyển động của người chơi cho một khung hình."""
    state: MoveState
    speed: float                  # tốc độ ngang, m/s
    ads_amount: float             # 0 hông .. 1 ngắm hẳn (tiến độ tuyến tính; đường cong êm áp ở đây)
    sprint_amount: float          # 0 .. 1, tương tự
    look: tuple = (0.0, 0.0)      # (yaw sang phải, pitch lên) độ mà CHUỘT vừa quay trong khung này
    eye_dy: float = 0.0           # camera đi lên (+) / xuống (-) bao nhiêu mét trong khung này
    landed: float = 0.0           # tốc độ chạm đất (m/s) nếu vừa chạm đất, ngược lại 0


# --- tư thế ADS ---
def apply_pose(point: tuple, pose: tuple) -> tuple:
    """Áp tư thế lên một điểm, đúng thứ tự của Panda (roll, rồi pitch, rồi heading), roll theo chiều kim đồng hồ."""
    x, y, z = point
    tx, ty, tz, pitch_up, yaw_right, roll_right = pose
    r, p, h = math.radians(roll_right), math.radians(pitch_up), math.radians(yaw_right)
    x, y = x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r)
    y, z = y * math.cos(p) + z * math.sin(p), -y * math.sin(p) + z * math.cos(p)
    x, z = x * math.cos(h) + z * math.sin(h), -x * math.sin(h) + z * math.cos(h)
    return x + tx, y + ty, z + tz


def ads_pose(rear: tuple, front: tuple, eye_relief: float) -> tuple:
    """Tư thế đưa đường ngắm (tâm vòng sau -> đỉnh cột trước) trùng trục nhìn của camera, vòng sau cách mắt `eye_relief`.
    Xoay quanh mắt cho đường ngắm song song trục z, rồi tịnh tiến cho vòng sau nằm trên trục."""
    dx, dy, dz = front[0] - rear[0], front[1] - rear[1], front[2] - rear[2]
    pitch_up = -math.degrees(math.atan2(dy, dz))                       # đường ngắm chếch lên thì chúc nòng xuống
    dz1 = math.hypot(dy, dz)
    yaw_right = -math.degrees(math.atan2(dx, dz1))
    turned = apply_pose(rear, (0.0, 0.0, 0.0, pitch_up, yaw_right, 0.0))
    return (-turned[0], -turned[1], eye_relief - turned[2], pitch_up, yaw_right, 0.0)


def ads_target_for(gun: GunData) -> tuple:
    """Tư thế ADS của một khẩu súng, tính từ hai điểm ngắm đo trên mô hình (không có thì không dịch gì)."""
    if gun.ads_sights is None:
        return ZERO_POSE
    rear, front = ([c + h for c, h in zip(point, gun.hip_offset)] for point in gun.ads_sights)
    return ads_pose(tuple(rear), tuple(front), gun.ads_eye_relief)


def _add(total: list, pose, scale: float = 1.0):
    for i in range(6):
        total[i] += pose[i] * scale


class Sway:
    def __init__(self, data: SwayData, ads_target: tuple = ZERO_POSE):
        self.d = data
        self.ads_target = ads_target
        self.clock = 0.0
        self.phase = 0.0                           # pha bước chân (rad)
        self.bob_amount = 0.0                      # biên độ bob đang trượt về mức mục tiêu
        self.lag = Spring(2, data.lag_omega, data.lag_zeta)       # (yaw phải, pitch lên)
        self.jolt = Spring(6, data.jolt_omega, data.jolt_zeta)    # quán tính dọc + nhún chạm đất

    def update(self, dt: float, inp: SwayInput) -> tuple:
        d = self.d
        ads = smoothstep(inp.ads_amount)
        sprint = smoothstep(inp.sprint_amount) * (1.0 - ads)
        calm = 1.0 + (d.ads_multiplier - 1.0) * ads            # ngắm: thở, lag, bob, quán tính còn ~20%
        total = [0.0] * 6
        self.clock += dt

        _add(total, self._bob(dt, inp), calm)
        _add(total, self._breath(inp), calm)
        _add(total, self._lag(dt, inp), calm)
        _add(total, self._jolt(dt, inp), calm)
        _add(total, d.sprint_pose, sprint)
        _add(total, self.ads_target, ads)
        return tuple(total)

    def _breath(self, inp: SwayInput) -> tuple:
        """Lissajous 1:2: ngang một nhịp, dọc hai nhịp. Nhỏ dần khi bob (đi) chiếm chỗ."""
        d = self.d
        w = 2.0 * math.pi * d.breath_freq * self.clock
        k = 1.0 - min(self.bob_amount, 1.0) * 0.8
        s1, s2 = math.sin(w), math.sin(2.0 * w + 0.6)
        return (d.breath_x * s1 * k, d.breath_y * s2 * k, 0.0, d.breath_pitch * s2 * k, d.breath_yaw * s1 * k, 0.0)

    def _lag(self, dt: float, inp: SwayInput) -> tuple:
        """Chuột quay sang phải thì súng trễ sang trái (và ngược lại); lò xo kéo về."""
        d = self.d
        yaw, pitch = inp.look
        self.lag.omega, self.lag.zeta = d.lag_omega, d.lag_zeta
        self.lag.x[0] = max(-d.lag_max, min(d.lag_max, self.lag.x[0] - yaw * d.lag_gain))
        self.lag.x[1] = max(-d.lag_max, min(d.lag_max, self.lag.x[1] - pitch * d.lag_gain))
        self.lag.step(dt)
        return (0.0, 0.0, 0.0, self.lag.x[1], self.lag.x[0], self.lag.x[0] * d.lag_roll)

    def _bob(self, dt: float, inp: SwayInput) -> tuple:
        d = self.d
        moving = inp.state in MOVING_ON_GROUND
        target = 0.0
        if moving:
            target = min(1.0, inp.speed / d.bob_min_speed)
            if inp.state is MoveState.SPRINT:
                target *= d.bob_sprint_multiplier
            elif inp.state is MoveState.CROUCH_WALK:
                target *= d.bob_crouch_multiplier
            rate = d.bob_sprint_rate if inp.state is MoveState.SPRINT else d.bob_rate
            self.phase = (self.phase + 2.0 * math.pi * inp.speed * dt * rate / d.bob_stride) % (2.0 * math.pi)
        self.bob_amount += (target - self.bob_amount) * (1.0 - math.exp(-dt * d.bob_blend))
        a, ph = self.bob_amount, self.phase
        return (a * d.bob_x * math.sin(ph), a * d.bob_y * math.sin(2.0 * ph), 0.0,
                a * d.bob_pitch * math.sin(2.0 * ph + 0.5), 0.0, a * d.bob_roll * math.sin(ph))

    def _jolt(self, dt: float, inp: SwayInput) -> tuple:
        """Camera đi lên thì súng trễ xuống (và ngược lại); chạm đất thì súng nhún thêm theo tốc độ rơi."""
        d = self.d
        self.jolt.omega, self.jolt.zeta = d.jolt_omega, d.jolt_zeta
        self.jolt.x[1] = max(-d.vlag_max, min(d.vlag_max, self.jolt.x[1] - inp.eye_dy * d.vlag_gain))
        if inp.landed > 0:
            gain = impulse_gain(d.jolt_omega, d.jolt_zeta) * inp.landed / d.land_reference_speed
            self.jolt.kick([p * gain for p in d.land_peak])
        self.jolt.step(dt)
        return tuple(self.jolt.x)
