"""Hai lớp recoil riêng biệt (toán thuần, không import ursina):

- `CameraRecoil`: sinh cú giật ngẫu nhiên từng phát (không có mẫu cố định). Phần `camera_share` làm LỆCH GÓC NHÌN (cộng vào yaw/pitch của người chơi, người chơi
  phải kéo chuột bù; sau khi ngừng bắn, một phần `recovery` tự hồi về), phần còn lại trả cho `FreeAim` làm súng trôi khỏi tâm.
- `GunKick`: kick của súng trên màn hình, lò xo giảm chấn. Phần xoay của nó cũng đổi hướng nòng, nên cũng đổi hướng đạn.

Góc: "lên" và "phải" dương, tính bằng độ. Mọi số nằm trong weapon_data.RecoilData / GunKickData.
"""
import math
import random

from fps.core.movement import smoothstep
from fps.core.spring import Spring, impulse_gain
from fps.weapon_data import GunKickData, RecoilData


class CameraRecoil:
    def __init__(self, data: RecoilData, rng: random.Random = None):
        self.d = data
        self.rng = rng or random.Random()
        self.clock = 0.0
        self.last_shot = None             # giá trị clock lúc phát cuối
        self.walk = 0.0                   # xu hướng ngang của loạt hiện tại, đi ngẫu nhiên từng phát
        self.pending = [0.0, 0.0]         # (lên, phải) cú giật đã tính nhưng chưa áp vào góc nhìn
        self.burst = [0.0, 0.0]           # tổng ròng của loạt đạn này; hồi sẽ lấy một phần của số này
        self.rec = [0.0, 0.0]             # còn bao nhiêu phải hồi
        self.armed = False                # đã bắn mà chưa tính phần hồi

    def on_shot(self, scale: float = 1.0) -> tuple:
        """Một phát: sinh cú giật ngẫu nhiên, phần `camera_share` xếp hàng vào góc nhìn; trả về (lên, phải) độ, phần còn lại cho súng trôi (`FreeAim.on_shot`).
        `scale` = hệ số tư thế (ngắm, ngồi): xem `posture_scale`."""
        d = self.d
        if self.last_shot is None or self.clock - self.last_shot > d.burst_reset_time:
            self.walk = 0.0
            self.burst = [0.0, 0.0]
        self.walk = min(max(self.walk + self.rng.uniform(-d.right_walk, d.right_walk), -d.right_walk_max), d.right_walk_max)
        up = (d.up + self.rng.uniform(-d.up_noise, d.up_noise)) * d.up_scale * scale
        right = (d.right_bias + self.walk + self.rng.uniform(-d.right_noise, d.right_noise)) * d.right_scale * scale
        share = min(max(d.camera_share, 0.0), 1.0)
        self.pending[0] += up * share
        self.pending[1] += right * share
        self.burst[0] += up * share
        self.burst[1] += right * share
        self.rec = [0.0, 0.0]             # bắn tiếp thì thôi hồi
        self.armed = True
        self.last_shot = self.clock
        return up * (1.0 - share), right * (1.0 - share)

    def posture_scale(self, ads: float, crouching: bool) -> float:
        """Hệ số cú giật theo tư thế: báng tì vai khi ngắm, trọng tâm thấp khi ngồi."""
        d = self.d
        k = 1.0 + (d.ads_scale - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))
        return k * (d.crouch_scale if crouching else 1.0)

    def step(self, dt: float) -> tuple:
        """Trả về (lên, phải) độ cần cộng vào góc nhìn trong khung hình này; âm = đang hồi."""
        d = self.d
        k = 1.0 - math.exp(-dt / d.kick_time) if d.kick_time > 0 else 1.0
        applied = [self.pending[0] * k, self.pending[1] * k]
        self.pending[0] -= applied[0]
        self.pending[1] -= applied[1]

        self.clock += dt
        if self.armed and self.clock - self.last_shot >= d.recovery_delay:
            self.armed = False
            self.rec = [self.burst[0] * d.recovery, self.burst[1] * d.recovery]
        kr = 1.0 - math.exp(-dt / d.recovery_time) if d.recovery_time > 0 else 1.0
        back = [self.rec[0] * kr, self.rec[1] * kr]
        for i in (0, 1):
            self.rec[i] -= back[i]
            self.burst[i] -= back[i]
        return applied[0] - back[0], applied[1] - back[1]


class GunKick:
    """6 thành phần: (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải), mét và độ."""

    def __init__(self, data: GunKickData, rng: random.Random = None):
        self.d = data
        self.rng = rng or random.Random()
        self.spring = Spring(6, data.omega, data.zeta)
        self.back = Spring(2, data.back_omega, data.back_zeta)       # đẩy lùi: [z, x đi kèm]; lò xo riêng, chậm hơn nên các phát dồn lên
        self._pending = []                                           # (tuổi trong khung, xung 6 thành phần, xung đẩy lùi) chờ `update`

    def on_shot(self, ads: float = 0.0, age: float = None):
        """Một phát bắn. `ads` 0 hông .. 1 ngắm hẳn: đẩy lùi nhân với `back_ads_scale` (nội suy smoothstep như các hiệu ứng hình ảnh khác; < 1 lùi ít hơn hông, > 1 lùi nhiều hơn).
        `age` = phát này nổ cách cuối khung bao lâu (như `Weapon.update` trả về): xung được áp đúng thời điểm đó trong `update`, nên
        đỉnh dồn của loạt đúng ở mọi FPS. Bỏ trống = áp ngay (đầu khung)."""
        d = self.d
        gain = impulse_gain(d.omega, d.zeta)
        imp = [(p + self.rng.uniform(-r, r)) * gain for p, r in zip(d.peak, d.random)]
        k = 1.0 + (d.back_ads_scale - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))
        back_z = (d.back_peak + self.rng.uniform(-d.back_random, d.back_random)) * k * impulse_gain(d.back_omega, d.back_zeta)
        back = (back_z, back_z * d.back_x_ratio * (1.0 - smoothstep(min(max(ads, 0.0), 1.0))))     # x chỉ lúc hông: súng ở bên phải mắt, kéo vào gần mắt thì lệch ra rìa; khi ngắm thì đường ngắm phải giữ nguyên trục
        if age is None:
            self.spring.omega, self.spring.zeta = d.omega, d.zeta
            self.back.omega, self.back.zeta = d.back_omega, d.back_zeta
            self.spring.kick(imp)
            self.back.kick(back)
        else:
            self._pending.append((age, imp, back))

    def _step(self, h: float):
        if h <= 0.0:
            return
        d = self.d
        self.spring.omega, self.spring.zeta = d.omega, d.zeta
        self.spring.step(h)
        self.back.omega, self.back.zeta = d.back_omega, d.back_zeta
        self.back.step(h)

    def update(self, dt: float):
        left = dt
        for age, imp, back in sorted(self._pending, key=lambda e: -e[0]):      # cũ nhất trước
            age = min(max(age, 0.0), left)
            self._step(left - age)
            left = age
            self.spring.kick(imp)
            self.back.kick(back)
        self._pending.clear()
        self._step(left)

    @property
    def pose(self) -> tuple:
        x, y, z, pitch, yaw, roll = self.spring.x
        return (x + self.back.x[1], y, z + self.back.x[0], pitch, yaw, roll)
