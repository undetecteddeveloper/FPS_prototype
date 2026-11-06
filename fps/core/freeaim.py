"""Súng không dính vào giữa màn hình, đạn bay theo nòng (toán thuần, không import ursina).

- `FreeLook`: CHUỘT ĐIỀU KHIỂN SÚNG TRƯỚC. Trong vùng tự do chỉ súng quay, màn hình đứng yên; tới gần mép vùng thì màn hình quay dần, tới mép thì quay hẳn. Đầu và thân từ từ
  quay theo súng (súng giữ nguyên hướng trong thế giới, chỉ khung hình đuổi theo), nên ngắm không bị trôi. Ngắm / chạy / nạp làm vùng co lại và màn hình quay bù.
- `FreeAim`: phần tư thế súng do giật (lò xo chậm nên các phát dồn lên rồi tự về), tư thế nghỉ đổi sau mỗi cú xoay / loạt đạn (không về đúng một toạ
  độ), trôi chậm lúc đứng yên, và run tay theo mức căng thẳng (bắn nhiều thì run, lúc nạp đạn thấy rõ).
- `barrel_view_dir`: hướng đạn trong hệ camera, lấy từ tư thế súng thật đang hiện trên màn hình. Súng vẽ bằng camera riêng (FOV khác thế giới), nên hướng
  được quy đổi qua điểm tụ trên màn hình: đạn tới đúng chỗ mà trục nòng đang chỉ vào, nhìn trên màn hình (ống kính vẽ sau khi ghép ảnh nên không làm lệch).

Tư thế = (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải), mét và độ, như mọi nơi khác.
"""
import math
import random

from fps.core.movement import smoothstep
from fps.core.shake import smooth_noise
from fps.core.spring import Spring, impulse_gain
from fps.core.sway import apply_pose
from fps.weapon_data import FreeAimData

ZERO_POSE = (0.0,) * 6


def barrel_view_dir(pose: tuple, sights: tuple, view_fov: float, world_fov: float) -> tuple:
    """Hướng đạn (x phải, y lên, z ra trước; đơn vị) trong hệ camera thế giới. `pose` = tư thế súng đang vẽ, chỉ phần xoay có tác dụng;
    `sights` = (tâm vòng ngắm sau, đỉnh cột trước) lúc nghỉ, định nghĩa trục ngắm của súng."""
    rear, front = sights
    axis = (front[0] - rear[0], front[1] - rear[1], front[2] - rear[2])
    x, y, z = apply_pose(axis, (0.0, 0.0, 0.0, pose[3], pose[4], pose[5]))
    if z <= 1e-6:                                # nòng quay ra sau camera: không thể có trong game, giữ an toàn số học
        return (0.0, 0.0, 1.0)
    k = math.tan(math.radians(view_fov) / 2.0)
    w = math.tan(math.radians(world_fov) / 2.0)
    sx, sy = x / z / k * w, y / z / k * w        # cùng một điểm trên màn hình, đổi từ ống kính súng sang ống kính thế giới
    n = math.sqrt(sx * sx + sy * sy + 1.0)
    return (sx / n, sy / n, 1.0 / n)


def view_to_world(yaw_deg: float, pitch_deg: float, local: tuple) -> tuple:
    """Đổi hướng trong hệ camera sang thế giới. Cùng quy ước với movement.aim_direction (pitch dương = cúi xuống)."""
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    sy, cy, sp, cp = math.sin(yaw), math.cos(yaw), math.sin(pitch), math.cos(pitch)
    forward = (sy * cp, -sp, cy * cp)
    right = (cy, 0.0, -sy)
    up = (sy * sp, cp, cy * sp)
    x, y, z = local
    return tuple(right[i] * x + up[i] * y + forward[i] * z for i in range(3))


class FreeLook:
    """Chia cú xoay chuột giữa súng và màn hình. `offset` = (yaw phải, pitch lên), độ: súng lệch khỏi giữa màn hình bao nhiêu (mục tiêu của tay);
    `shown` = chỗ súng đang ở, đi theo `offset` qua lò xo của tay. Mọi phần chuột không đi vào `offset` đều quay màn hình, nên tổng góc luôn khớp chuột: hướng súng trong
    thế giới = hướng nhìn + offset, đúng bằng tổng chuột đã quay."""

    def __init__(self, data: FreeAimData):
        self.d = data
        self.offset = [0.0, 0.0]
        self.spring = Spring(2, data.hand_omega, data.hand_zeta)     # sai lệch của `shown` so với `offset`
        self.scale = 1.0                                             # vùng hiện tại so với vùng đầy đủ (co / giãn mượt)

    def reset(self):
        self.offset = [0.0, 0.0]
        self.spring.x = [0.0, 0.0]
        self.spring.v = [0.0, 0.0]

    @property
    def shown(self) -> tuple:
        return (self.offset[0] + self.spring.x[0], self.offset[1] + self.spring.x[1])

    def _axes(self) -> tuple:
        return max(self.d.zone_yaw * self.scale, 1e-6), max(self.d.zone_pitch * self.scale, 1e-6)

    def radius(self) -> float:
        """0 giữa vùng .. 1 ở mép."""
        a, b = self._axes()
        return math.hypot(self.offset[0] / a, self.offset[1] / b)

    def _clamp(self) -> tuple:
        """Đưa `offset` vào trong elip; trả phần thừa cho màn hình (súng giữ nguyên hướng trong thế giới)."""
        r = self.radius()
        if r <= 1.0:
            return 0.0, 0.0
        extra = (self.offset[0] * (1.0 - 1.0 / r), self.offset[1] * (1.0 - 1.0 / r))
        self.offset[0] -= extra[0]
        self.offset[1] -= extra[1]
        return extra

    def apply(self, yaw: float, up: float) -> tuple:
        """Chuột vừa quay (yaw phải, pitch lên), độ. Trả phần màn hình phải quay. Đi ra phía mép: gần mép thì màn hình nhận dần; đi vào trong: chỉ súng di chuyển (rà tâm chính xác được)."""
        d = self.d
        if not d.barrel_aim:
            return yaw, up
        cam = [0.0, 0.0]
        total = math.hypot(yaw, up)
        if total > 0.0:
            # chia nhỏ để cú vẩy chuột lớn trong một khung vẫn đi qua vùng mềm đúng như nhiều khung nhỏ
            steps = max(1, min(16, math.ceil(total / 0.5)))
            sy, su = yaw / steps, up / steps
            for _ in range(steps):
                r = self.radius()
                outward = sy * self.offset[0] + su * self.offset[1] > 0.0
                t = (r - d.zone_soft) / max(1.0 - d.zone_soft, 1e-6) if outward else 0.0
                t = min(max(t, 0.0), 1.0)
                share = t * t * (3.0 - 2.0 * t)
                cam[0] += sy * share
                cam[1] += su * share
                self.offset[0] += sy * (1.0 - share)
                self.offset[1] += su * (1.0 - share)
                ex = self._clamp()
                cam[0] += ex[0]
                cam[1] += ex[1]
        return cam[0], cam[1]

    def step(self, dt: float, ads: float = 0.0, sprint: float = 0.0, reloading: bool = False, moving: bool = False) -> tuple:
        """Mỗi khung. Trả phần màn hình phải quay do vùng co lại và do đầu / thân đuổi theo súng; phần đó được trừ khỏi `offset` nên súng giữ nguyên hướng trong thế giới."""
        d = self.d
        if dt <= 0.0:
            return 0.0, 0.0
        target = 0.0 if not d.barrel_aim else 1.0
        target *= 1.0 + (d.zone_ads - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))
        target *= 1.0 + (d.zone_sprint - 1.0) * smoothstep(min(max(sprint, 0.0), 1.0))
        if reloading:
            target *= d.zone_reload
        k = 1.0 - math.exp(-dt / d.zone_blend) if d.zone_blend > 0 else 1.0
        self.scale += (target - self.scale) * k
        if target == 0.0 and self.scale < 1e-3:
            self.scale = 0.0
        cam = list(self._clamp())
        rate = d.recenter_move if moving else d.recenter_idle
        back = 1.0 - math.exp(-dt * rate)
        for i in (0, 1):
            v = self.offset[i] * back
            self.offset[i] -= v
            cam[i] += v
        # lò xo của tay bám `offset`: sai lệch = shown - offset. `offset` đổi thì `shown` chưa đổi kịp
        sp = self.spring
        sp.omega, sp.zeta = d.hand_omega, d.hand_zeta
        sp.step(dt)
        return cam[0], cam[1]

    def track(self, before: tuple):
        """Gọi sau mọi thay đổi `offset` của khung, với `before` = `offset` lúc đầu khung: phần chênh chuyển vào lò xo để súng trên màn hình đi liên tục."""
        self.spring.x[0] -= self.offset[0] - before[0]
        self.spring.x[1] -= self.offset[1] - before[1]

    def pose(self) -> tuple:
        """Tư thế cộng vào súng. Xoay quanh mắt đã đưa súng đi theo cung; thêm dịch và nghiêng nhẹ cho giống tay đưa súng."""
        d = self.d
        yaw, up = self.shown
        return (yaw * d.offset_shift, up * d.offset_shift, 0.0, up, yaw, yaw * d.offset_roll)


class FreeAim:
    def __init__(self, data: FreeAimData, seed: int = 41):
        self.d = data
        self.seed = seed
        self.rng = random.Random(seed)            # riêng: không làm đổi chuỗi ngẫu nhiên của đạn
        self.spring = Spring(2, data.drift_omega, data.drift_zeta)      # (pitch lên, yaw phải) do giật, độ
        self.t = 0.0
        self.stress = 0.0                         # 0..1
        self.rest = [0.0] * 6                     # tư thế nghỉ hiện tại
        self.rest_target = [0.0] * 6
        self._turned = False                      # đang có cú xoay nhanh: chọn tư thế nghỉ mới khi dừng
        self._since_shot = 1e9
        self.rest_changes = 0                     # số lần đổi tư thế nghỉ (cho kiểm tra)

    def on_shot(self, up: float, right: float):
        """Phần cú giật làm súng trôi (độ): độ lệch đỉnh của MỘT phát; bắn liên tục thì dồn lên."""
        d = self.d
        gain = impulse_gain(d.drift_omega, d.drift_zeta)
        self.spring.omega, self.spring.zeta = d.drift_omega, d.drift_zeta
        self.spring.kick([up * gain, right * gain])
        self.stress = min(1.0, self.stress + d.stress_per_shot)
        self._since_shot = 0.0

    def _pick_rest(self):
        d, r = self.d, self.rng
        self.rest_target = [r.uniform(-d.rest_pos, d.rest_pos), r.uniform(-d.rest_pos, d.rest_pos), 0.0,
                            r.uniform(-d.rest_pitch, d.rest_pitch), r.uniform(-d.rest_yaw, d.rest_yaw), r.uniform(-d.rest_roll, d.rest_roll)]
        self.rest_changes += 1

    def update(self, dt: float, turn_rate: float = 0.0):
        """`turn_rate` = độ lớn tốc độ xoay chuột (độ/s). Dừng sau cú xoay nhanh, hoặc ngừng bắn, thì súng dừng ở một tư thế khác lần trước."""
        if dt <= 0.0:
            return
        d = self.d
        self.t += dt
        self.spring.omega, self.spring.zeta = d.drift_omega, d.drift_zeta
        self.spring.step(dt)
        self.stress = max(0.0, self.stress - d.stress_decay * dt)
        before = self._since_shot
        self._since_shot += dt
        if before <= 0.25 < self._since_shot:     # vừa ngừng loạt đạn
            self._pick_rest()
        if turn_rate > d.rest_turn_threshold:
            self._turned = True
        elif self._turned and turn_rate < d.rest_turn_threshold * 0.25:
            self._turned = False
            self._pick_rest()
        k = 1.0 - math.exp(-dt / d.rest_time) if d.rest_time > 0 else 1.0
        for i in range(6):
            self.rest[i] += (self.rest_target[i] - self.rest[i]) * k

    @property
    def drift(self) -> tuple:
        """(pitch lên, yaw phải) độ trôi hiện tại do giật, đã nén mềm tới `drift_max`."""
        m = self.d.drift_max
        return tuple(m * math.tanh(v / m) if m > 0 else 0.0 for v in self.spring.x)

    def pose(self, ads: float = 0.0, reloading: bool = False) -> tuple:
        """Tư thế cộng vào súng. `ads` 0 hông .. 1 ngắm hẳn (tiến độ thô): tư thế nghỉ và trôi chậm nhỏ lại, phần giật giữ nguyên."""
        d = self.d
        calm = 1.0 + (d.ads_scale - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))
        u = self.t * d.idle_freq
        pitch_up, yaw_right = self.drift
        px = self.rest[0] * calm
        py = self.rest[1] * calm
        pitch = pitch_up + calm * (self.rest[3] + d.idle_pitch * smooth_noise(self.seed, 0, u))
        yaw = yaw_right + calm * (self.rest[4] + d.idle_yaw * smooth_noise(self.seed, 1, u))
        roll = calm * (self.rest[5] + d.idle_roll * smooth_noise(self.seed, 2, u))
        shake = self.stress * (d.tremor_reload if reloading else 1.0)
        if shake > 0.0:
            v = self.t * d.tremor_freq
            pitch += shake * d.tremor_angle * smooth_noise(self.seed, 3, v)
            yaw += shake * d.tremor_angle * smooth_noise(self.seed, 4, v)
            roll += shake * d.tremor_angle * smooth_noise(self.seed, 5, v)
            px += shake * d.tremor_pos * smooth_noise(self.seed, 6, v)
            py += shake * d.tremor_pos * smooth_noise(self.seed, 7, v)
        return (px, py, 0.0, pitch, yaw, roll)
