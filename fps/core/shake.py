"""Camera shake: lớp rung THUẦN HÌNH ẢNH đặt lên trên recoil camera (toán thuần, không import ursina).

KHÔNG đổi hướng đạn: kết quả chỉ là một tư thế (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải; mét và độ)
mà game áp lên camera thế giới (nút con riêng của `camera`, không đụng `player.yaw/pitch`) và, đảo dấu, lên súng.

Hai nguồn cộng lại:
- BẮN: mô hình "trauma". Mỗi phát cộng `fire_trauma` (kẹp ở `fire_max_trauma`), trauma tắt dần TUYẾN TÍNH (về đúng 0 sau
  trauma / fire_decay giây), biên độ = trauma^power nhân nhiễu mượt theo thời gian. Phát lẻ chỉ rung khẽ, loạt dài rung dần lên
  rồi chững ở trần (750 phát/phút: mỗi nhịp cộng 0,22, tắt 0,16, nên lên trần sau ~9 phát).
- NẠP: xung lò xo ngắn tại các mốc khung của clip (băng rút ra, băng vào chỗ, nhả bolt), không rung suốt clip.
Nhiễu là nhiễu giá trị băm theo (seed, trục, ô) nên chỉ phụ thuộc thời gian: cùng seed cho cùng đường cong ở mọi FPS và lặp lại được.
"""
import math
from collections import deque

from fps.core.movement import smoothstep
from fps.core.spring import Spring, impulse_gain
from fps.weapon_data import ShakeData

_MASK = (1 << 64) - 1


def hash_unit(seed: int, axis: int, i: int) -> float:
    """Số giả ngẫu nhiên xác định trong [-1, 1] từ (seed, trục, chỉ số ô) (splitmix64)."""
    x = (i * 0x9E3779B97F4A7C15 + axis * 0xBF58476D1CE4E5B9 + seed * 0x94D049BB133111EB + 0x2545F4914F6CDD1D) & _MASK
    x ^= x >> 30
    x = (x * 0xBF58476D1CE4E5B9) & _MASK
    x ^= x >> 27
    x = (x * 0x94D049BB133111EB) & _MASK
    x ^= x >> 31
    return x / _MASK * 2.0 - 1.0


def smooth_noise(seed: int, axis: int, u: float) -> float:
    """Nhiễu giá trị 1D mượt (nội suy bậc 5 giữa hai giá trị ô), luôn trong [-1, 1], liên tục cả đạo hàm bậc 1 và 2."""
    i = math.floor(u)
    f = u - i
    s = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)
    a, b = hash_unit(seed, axis, i), hash_unit(seed, axis, i + 1)
    return a + (b - a) * s


class Shake:
    def __init__(self, data: ShakeData, seed: int = None):
        self.d = data
        self.seed = data.seed if seed is None else seed
        self.enabled = True
        self.t = 0.0                         # đồng hồ của lớp rung (giây), tiến theo dt thật
        self.trauma = 0.0                    # 0..fire_max_trauma
        self.spring = Spring(6, data.beat_omega, data.beat_zeta)
        self.beat_log = deque(maxlen=64)     # (đồng hồ, loại mốc) các xung nạp đã nổ, cho kiểm tra
        self.beat_count = 0
        self._events = []                    # (tuổi trong khung, None = phát bắn | loại mốc nạp)
        self._reload_key = None
        self._reload_prev = None             # khung đã xét lần trước của clip nạp đang chạy

    def reset(self):
        """Về trạng thái yên (đồng hồ giữ nguyên, nên nhiễu không lặp lại từ đầu)."""
        self.trauma = 0.0
        self.spring.x = [0.0] * 6
        self.spring.v = [0.0] * 6
        self._events.clear()
        self._reload_key = self._reload_prev = None

    # --- sự kiện (xếp hàng, xử lý theo đúng thứ tự thời gian trong `update`) ---
    def on_shot(self, age: float = 0.0):
        """Một phát bắn. `age` = phát này nổ cách cuối khung bao lâu (như `Weapon.update` trả về)."""
        if self.enabled:
            self._events.append((age, None))

    def on_beat(self, kind: str, age: float = 0.0):
        """Một mốc của clip nạp ('mag_out' / 'seat' / 'bolt'): xung lò xo ngắn."""
        if self.enabled:
            self._events.append((age, kind))

    def watch_reload(self, key, frame, frames_per_second: float = 30.0):
        """Gọi mỗi khung với (`Handling.key`, `Handling.frame`, 30 * tốc độ nạp); key None khi không nạp.
        Xếp các mốc vừa đi qua (kèm tuổi trong khung); huỷ nạp (key về None) thì các mốc chưa tới bị bỏ."""
        if key is None or frame is None:
            self._reload_key = self._reload_prev = None
            return
        if key != self._reload_key:
            self._reload_key, self._reload_prev = key, None
        prev = self._reload_prev
        for f, kind in self.d.reload_beats.get(key, ()):
            if (prev is None or f > prev) and f <= frame:
                self.on_beat(kind, (frame - f) / frames_per_second)
        self._reload_prev = frame

    def _apply_beat(self, kind: str):
        d = self.d
        peak = d.beat_peaks[kind]
        sign = 1.0 if hash_unit(self.seed, 99, self.beat_count) >= 0 else -1.0
        self.beat_count += 1
        gain = impulse_gain(d.beat_omega, d.beat_zeta)
        flip = (1.0, 1.0, 1.0, 1.0, sign, sign)       # đổi dấu yaw và roll cho đỡ lặp
        self.spring.kick([p * g * gain for p, g in zip(peak, flip)])
        self.beat_log.append((self.t, kind))

    # --- mỗi khung ---
    def _advance(self, h: float):
        if h <= 0.0:
            return
        d = self.d
        self.t += h
        self.trauma = max(0.0, self.trauma - d.fire_decay * h)
        self.spring.omega, self.spring.zeta = d.beat_omega, d.beat_zeta
        self.spring.step(h)

    def update(self, dt: float):
        """Tiến `dt` giây, xử lý các sự kiện đã xếp theo đúng thời điểm của chúng trong khung (cũ nhất trước): kết quả chỉ phụ thuộc
        thời gian, không phụ thuộc cách chia khung. Gọi SAU các sự kiện của khung."""
        events = sorted(self._events, key=lambda e: -e[0])
        self._events.clear()
        left = dt
        for age, kind in events:
            age = min(max(age, 0.0), left)
            self._advance(left - age)
            left = age
            if kind is None:
                self.trauma = min(self.d.fire_max_trauma, self.trauma + self.d.fire_trauma)
            else:
                self._apply_beat(kind)
        self._advance(left)

    # --- đọc ---
    @property
    def amplitude(self) -> float:
        """Biên độ chuẩn hoá 0..1 của rung bắn = trauma^power."""
        return self.trauma ** self.d.power if self.trauma > 0 else 0.0

    @property
    def active(self) -> bool:
        return self.trauma > 0 or any(abs(v) > 1e-9 or abs(x) > 1e-9 for v, x in zip(self.spring.v, self.spring.x))

    def _fire_pose(self, delay: float) -> tuple:
        d = self.d
        a = self.amplitude
        if a <= 0:
            return (0.0,) * 6
        u = (self.t - delay) * d.fire_freq
        return tuple(a * amp * smooth_noise(self.seed, axis, u) for axis, amp in enumerate(d.fire_amp))

    def _ads_scale(self, ads: float) -> float:
        return 1.0 + (self.d.ads_multiplier - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))

    def camera_pose(self, ads: float = 0.0) -> tuple:
        """Tư thế rung của camera thế giới: (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải), mét và độ.
        `ads` 0 hông .. 1 ngắm hẳn (giảm còn `ads_multiplier`)."""
        k = self._ads_scale(ads)
        fire = self._fire_pose(0.0)
        return tuple(k * (f + s) for f, s in zip(fire, self.spring.x))

    def gun_pose(self, ads: float = 0.0) -> tuple:
        """Tư thế cộng thêm cho SÚNG trên màn hình. Camera lệch +p thì thế giới lệch -p trên màn hình; súng đi theo `gun_follow`
        phần của chuyển động thế giới đó (đảo dấu), và trễ `gun_delay` giây nên không dính chặt với thế giới."""
        d = self.d
        k = self._ads_scale(ads) * d.gun_follow
        fire = self._fire_pose(d.gun_delay)
        return tuple(-k * (f + s) for f, s in zip(fire, self.spring.x))
