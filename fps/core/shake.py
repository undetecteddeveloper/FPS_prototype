"""Camera shake: lớp rung THUẦN HÌNH ẢNH đặt lên trên recoil camera (toán thuần, không import ursina).

KHÔNG đổi hướng đạn: kết quả chỉ là một tư thế (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải; mét và độ)
mà game áp lên camera thế giới (nút con riêng của `camera`, không đụng `player.yaw/pitch`) và, đảo dấu, lên súng.

Ba nguồn cộng lại:
- BẮN, CÚ GIẬT TỪNG PHÁT (kiểu Bodycam, người dùng chọn "giật cục từng phát, sấy mạnh gấp đôi"): mỗi phát là MỘT xung vào lò xo
  giảm chấn 6 trục `fire_omega` / `fire_zeta` (nghiệm chính xác của `core/spring.py`, độ lệch đỉnh tính bằng `impulse_gain`).
  Độ lệch đỉnh của phát = độ mạnh ngẫu nhiên x (`fire_bias` + `fire_spread` x số ngẫu nhiên có dấu từng trục): pitch luôn ngóc lên,
  yaw / roll dấu ngẫu nhiên, z lùi về sau, x / y rung nhẹ. Độ mạnh = 1 ± `strength_var` (số mũ `strength_shape` < 1 đẩy về hai đầu nên
  có phát mạnh hẳn, phát nhẹ hẳn). Lò xo tắt sau ~0,1 s nên từng phát tách bạch; nhịp 0,08 s chưa tắt hẳn nên loạt dài dồn lên vừa phải.
  Bản cũ (trauma^2,3 nhân nhiễu mượt) làm phát lẻ chỉ còn ~6% biên độ và mọi phát trông giống nhau: đã bỏ.
- BẮN, ĐỘ NÓNG CỦA LOẠT (`heat` 0..1): mỗi phát cộng 1 / `heat_shots`; ngừng quá `heat_hold` giây thì nguội `heat_cool` /s (giữ lại
  khi đang sấy vì nhịp 0,08 s < `heat_hold`; bắn từng phát chậm thì không bao giờ nóng). Cú giật của phát nhân 1 + `heat_boost` x heat
  (đọc TRƯỚC khi phát cộng nhiệt, nên phát lẻ đúng 1 lần). Thêm run tay nền = heat x `tremor_amp` x nhiễu mượt nhanh `tremor_freq`.
  Cả băng 30 viên: đỉnh ~2 lần phát lẻ (pytest đo). Ngừng bắn: lò xo về ~0 sau ~0,3 s, run tay tắt khi heat về 0 (hold + 1 / cool ~0,45 s).
- NẠP: xung lò xo ngắn tại các mốc khung của clip (băng rút ra, băng vào chỗ, nhả bolt), không rung suốt clip. Lò xo riêng `spring`.

Súng đi theo thế giới (đảo dấu, `gun_follow`) và TRỄ `gun_delay`: phần giật của súng là một lò xo thứ hai nhận đúng các xung đó muộn
`gun_delay` giây (không phải lấy mẫu lại lịch sử). Mọi số ngẫu nhiên băm theo (seed, trục, số thứ tự phát) nên chỉ phụ thuộc thứ tự
phát và thời gian: cùng seed cho cùng đường cong ở mọi FPS, không dùng chung `combat.rng` (không đổi chuỗi ngẫu nhiên của đạn).
"""
import math
from collections import deque

from fps.core.movement import smoothstep
from fps.core.spring import Spring, impulse_gain
from fps.weapon_data import ShakeData

_MASK = (1 << 64) - 1
_EPS_X, _EPS_V = 1e-6, 1e-4      # lò xo dưới mức này (mét / độ) thì coi như yên, đặt đúng 0 (tắt hẳn chứ không lơ lửng 1e-9 mãi)


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


def signed_pow(u: float, shape: float) -> float:
    """Giữ dấu, độ lớn |u|^shape: shape < 1 đẩy số đều trong [-1, 1] ra hai đầu (ít giá trị gần 0), shape > 1 dồn vào giữa."""
    return math.copysign(abs(u) ** shape, u) if u else 0.0


_AX_STRENGTH = 10                # trục băm: độ mạnh của phát
_AX_DIR = 20                     # 20..25: hướng từng trục của phát
_AX_TREMOR = 40                  # 40..45: nhiễu run tay
_AX_BEAT = 99                    # dấu của mốc nạp


def _settle(spring: Spring):
    if all(abs(x) < _EPS_X for x in spring.x) and all(abs(v) < _EPS_V for v in spring.v):
        spring.x = [0.0] * len(spring.x)
        spring.v = [0.0] * len(spring.v)


def _moving(spring: Spring) -> bool:
    return any(x or v for x, v in zip(spring.x, spring.v))


class Shake:
    def __init__(self, data: ShakeData, seed: int = None):
        self.d = data
        self.seed = data.seed if seed is None else seed
        self.enabled = True
        self.t = 0.0                         # đồng hồ của lớp rung (giây), tiến theo dt thật
        self.heat = 0.0                      # độ nóng của loạt, 0..1
        self.since_shot = 1e9                # giây từ phát gần nhất (cho heat_hold)
        self.shot_count = 0                  # số thứ tự phát: chỉ số băm của số ngẫu nhiên
        self.spring = Spring(6, data.beat_omega, data.beat_zeta)     # xung NẠP (giữ tên `spring`: selftest đặt thẳng spring.x)
        self.fire = Spring(6, data.fire_omega, data.fire_zeta)       # cú giật từng phát của camera
        self.gun_fire = Spring(6, data.fire_omega, data.fire_zeta)   # cùng các xung, muộn gun_delay, cho súng
        self._gun_kicks = []                 # (đồng hồ đến hạn, xung) chờ đưa vào gun_fire
        self.shot_log = deque(maxlen=64)     # (đồng hồ, độ mạnh, hệ số nóng, độ lệch đỉnh 6 trục) các phát đã nổ, cho kiểm tra
        self.beat_log = deque(maxlen=64)     # (đồng hồ, loại mốc) các xung nạp đã nổ, cho kiểm tra
        self.beat_count = 0
        self._events = []                    # (tuổi trong khung, None = phát bắn | loại mốc nạp, hệ số)
        self._reload_key = None
        self._reload_prev = None             # khung đã xét lần trước của clip nạp đang chạy

    @property
    def trauma(self) -> float:
        """Tên cũ (mô hình trauma đã bỏ), giữ cho selftest / bảng đọc: nay là độ nóng của loạt."""
        return self.heat

    def reset(self):
        """Về trạng thái yên (đồng hồ và số thứ tự phát giữ nguyên, nên nhiễu / độ mạnh không lặp lại từ đầu)."""
        self.heat = 0.0
        self.since_shot = 1e9
        for s in (self.spring, self.fire, self.gun_fire):
            s.x = [0.0] * 6
            s.v = [0.0] * 6
        self._gun_kicks.clear()
        self._events.clear()
        self._reload_key = self._reload_prev = None

    # --- sự kiện (xếp hàng, xử lý theo đúng thứ tự thời gian trong `update`) ---
    def on_shot(self, age: float = 0.0, scale: float = 1.0):
        """Một phát bắn. `age` = phát này nổ cách cuối khung bao lâu (như `Weapon.update` trả về). `scale` nhân riêng cú giật
        của phát này (ví dụ theo tư thế); không đổi độ nóng."""
        if self.enabled:
            self._events.append((age, None, scale))

    def on_beat(self, kind: str, age: float = 0.0):
        """Một mốc của clip nạp ('mag_out' / 'seat' / 'bolt'): xung lò xo ngắn."""
        if self.enabled:
            self._events.append((age, kind, 1.0))

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
        sign = 1.0 if hash_unit(self.seed, _AX_BEAT, self.beat_count) >= 0 else -1.0
        self.beat_count += 1
        gain = impulse_gain(d.beat_omega, d.beat_zeta)
        flip = (1.0, 1.0, 1.0, 1.0, sign, sign)       # đổi dấu yaw và roll cho đỡ lặp
        self.spring.kick([p * g * gain for p, g in zip(peak, flip)])
        self.beat_log.append((self.t, kind))

    def shot_peak(self, n: int, heat: float = 0.0, scale: float = 1.0) -> tuple:
        """Độ lệch đỉnh (6 trục, mét và độ) của phát thứ `n` nếu nổ khi lò xo đang yên với độ nóng `heat`; kèm (độ mạnh, hệ số nóng)."""
        d = self.d
        strength = max(0.0, 1.0 + d.strength_var * signed_pow(hash_unit(self.seed, _AX_STRENGTH, n), d.strength_shape))
        boost = 1.0 + d.heat_boost * heat
        k = strength * boost * scale * d.fire_scale
        peak = tuple(k * (b + s * signed_pow(hash_unit(self.seed, _AX_DIR + i, n), d.direction_shape))
                     for i, (b, s) in enumerate(zip(d.fire_bias, d.fire_spread)))
        return peak, strength, boost

    def _apply_shot(self, scale: float):
        d = self.d
        n = self.shot_count
        self.shot_count += 1
        peak, strength, boost = self.shot_peak(n, self.heat, scale)
        gain = impulse_gain(d.fire_omega, d.fire_zeta)
        impulse = [p * gain for p in peak]
        self.fire.kick(impulse)
        self._gun_kicks.append((self.t + max(d.gun_delay, 0.0), impulse))
        self._gun_kicks.sort(key=lambda e: e[0])
        self.heat = min(1.0, self.heat + 1.0 / max(d.heat_shots, 1e-6))
        self.since_shot = 0.0
        self.shot_log.append((self.t, strength, boost, peak))

    # --- mỗi khung ---
    def _step(self, h: float):
        """Tiến h giây không có sự kiện: nguội (chỉ phần thời gian quá heat_hold), ba lò xo theo nghiệm chính xác."""
        if h <= 0.0:
            return
        d = self.d
        self.t += h
        cooling = max(0.0, self.since_shot + h - max(self.since_shot, d.heat_hold))
        self.since_shot += h
        if cooling > 0.0 and self.heat > 0.0:
            self.heat = max(0.0, self.heat - d.heat_cool * cooling)
        self.spring.omega, self.spring.zeta = d.beat_omega, d.beat_zeta
        for s in (self.fire, self.gun_fire):
            s.omega, s.zeta = d.fire_omega, d.fire_zeta
        for s in (self.spring, self.fire, self.gun_fire):
            if _moving(s):
                s.step(h)
                _settle(s)

    def _advance(self, h: float):
        """Tiến h giây; các xung trễ của súng đến hạn trong khoảng này được đưa vào đúng thời điểm."""
        end = self.t + max(h, 0.0)
        while self._gun_kicks and self._gun_kicks[0][0] <= end:
            due, impulse = self._gun_kicks.pop(0)
            self._step(due - self.t)
            self.gun_fire.kick(impulse)
        self._step(end - self.t)

    def update(self, dt: float):
        """Tiến `dt` giây, xử lý các sự kiện đã xếp theo đúng thời điểm của chúng trong khung (cũ nhất trước): kết quả chỉ phụ thuộc
        thời gian, không phụ thuộc cách chia khung. Gọi SAU các sự kiện của khung."""
        events = sorted(self._events, key=lambda e: -e[0])
        self._events.clear()
        left = dt
        for age, kind, scale in events:
            age = min(max(age, 0.0), left)
            self._advance(left - age)
            left = age
            if kind is None:
                self._apply_shot(scale)
            else:
                self._apply_beat(kind)
        self._advance(left)

    # --- đọc ---
    @property
    def amplitude(self) -> float:
        """Mức rung bắn chuẩn hoá: độ lệch lớn nhất hiện tại của camera so với độ lệch đỉnh danh định của một phát lẻ
        (bias + spread của trục đó; ~1 ở đỉnh phát lẻ mạnh, ~2 lúc sấy cả băng). Không tính run tay."""
        d = self.d
        ref = [abs(b) + abs(s) for b, s in zip(d.fire_bias, d.fire_spread)]
        return max((abs(x) / r for x, r in zip(self.fire.x, ref) if r > 0), default=0.0)

    @property
    def active(self) -> bool:
        return (self.heat > 0 or bool(self._gun_kicks)
                or _moving(self.spring) or _moving(self.fire) or _moving(self.gun_fire))

    def _tremor(self, delay: float) -> tuple:
        d = self.d
        e = self.heat * d.fire_scale
        if e <= 0:
            return (0.0,) * 6
        u = (self.t - delay) * d.tremor_freq
        return tuple(e * amp * smooth_noise(self.seed, _AX_TREMOR + axis, u) for axis, amp in enumerate(d.tremor_amp))

    def _ads_scale(self, ads: float) -> float:
        return 1.0 + (self.d.ads_multiplier - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))

    def camera_pose(self, ads: float = 0.0) -> tuple:
        """Tư thế rung của camera thế giới: (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải), mét và độ.
        `ads` 0 hông .. 1 ngắm hẳn (giảm còn `ads_multiplier`)."""
        k = self._ads_scale(ads)
        tremor = self._tremor(0.0)
        return tuple(k * (f + r + s) for f, r, s in zip(self.fire.x, tremor, self.spring.x))

    def gun_pose(self, ads: float = 0.0) -> tuple:
        """Tư thế cộng thêm cho SÚNG trên màn hình. Camera lệch +p thì thế giới lệch -p trên màn hình; súng đi theo `gun_follow`
        phần của chuyển động thế giới đó (đảo dấu), và trễ `gun_delay` giây nên không dính chặt với thế giới."""
        d = self.d
        k = self._ads_scale(ads) * d.gun_follow
        tremor = self._tremor(d.gun_delay)
        return tuple(-k * (f + r + s) for f, r, s in zip(self.gun_fire.x, tremor, self.spring.x))
