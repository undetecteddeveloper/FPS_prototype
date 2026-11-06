"""Camera đội đầu: chuyển động của đầu và thân lên ảnh (toán thuần, không import ursina).

CHỈ HÌNH ẢNH như Shake: kết quả là tư thế đặt lên camera thế giới, không đụng `player.yaw/pitch`, `aim_ray()` hay hướng đạn.
Tư thế = (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải), mét và độ. Gồm hai phần:

1. Chuyển động của người (nhân `ads_multiplier` khi ngắm, súng đi theo `gun_follow` đảo dấu):
   - thân: nghiêng theo cú xoay và khi đi ngang, cúi khi đi tới (lò xo `body_*` nên thân đến trễ);
   - bước chân: CÙNG PHA `Sway.phase` (tiếng bước chân phát khi pha qua 3 pi / 4, đúng đáy của nhún). Nhún dùng sóng "chạm đất"
     (`footfall`): đáy nhọn như cú dậm, đỉnh tròn, `step_sharp` chỉnh độ nhọn. Đi và chạy nước rút có bộ biên độ riêng, trộn theo
     `sprint_mix` (trượt mượt khi vào / ra chạy); chạy thêm chúi tới `sprint_lean`. Kiểu quay bodycam: đi nhún ~2 cm, nghiêng ~1 độ;
     chạy nghiêng trái phải ~2,6 độ theo nhịp chân;
   - rung tay: nhiễu mượt tần số cao (hai quãng tám của `smooth_noise`) tăng theo tốc độ, mạnh nhất khi chạy nước rút. Đồng hồ nhiễu
     tích phân theo tần số (pha), nên đổi tần số đi <-> chạy không làm nhiễu nhảy;
   - nhảy / rơi / chạm đất: lò xo `jolt_*` riêng (nhanh, nảy lại vì zeta < 0,5). Bật nhảy: xung ngóc lên + nhấc; trên không: lắc chậm;
     chạm đất: dằn xuống theo tốc độ rơi (pitch xuống + y xuống + nghiêng ngẫu nhiên), nảy lại một nhịp. Gật chạm đất trước đây nằm
     trong lò xo thân (omega 7, chậm như gật đầu) nên không ra cú dằn;
   - trôi chậm và thở lúc đứng yên.
2. Liếc súng khi nạp (`glance_*`, KHÔNG nhân ngắm): đầu cúi nhìn băng đạn rồi ngẩng lên. Đường cong là hàm THUẦN của thời gian clip
   (`Handling.t`), nên độc lập FPS và khớp đúng clip ở mọi `ReloadData.speed`: vào sau `glance_in_delay` trong `glance_in_time`, giữ (trôi
   nhẹ + gật nhỏ lúc băng vào chỗ), bắt đầu ngẩng `glance_out_lead` giây TRƯỚC `Clip.settle` (cùng lúc góc nhìn nạp của Viewmodel tắt dần)
   và về hẳn sau `glance_out_time`, tức trước khi súng sẵn sàng bắn ~0,5 s. Nạp cạn có `settle` muộn hơn nên tự giữ lâu hơn.
   Huỷ nạp: trượt từ chỗ đang đứng về 0 trong `glance_cancel_time` (smoothstep). Chuột vẫn quay bình thường trong lúc liếc.
   Súng: tay giữ súng theo thân, nên khi đầu cúi thì súng gần như đứng yên trong thế giới, tức trên màn hình súng đi LÊN về giữa khung:
   phần liếc dùng `glance_follow` (~1, xoay quanh mắt như camera) thay cho `gun_follow` 0,55 của chuyển động thường.
"""
import math
from dataclasses import dataclass

from fps.core.movement import MoveState, smoothstep
from fps.core.shake import smooth_noise
from fps.core.spring import Spring, impulse_gain
from fps.core.sway import MOVING_ON_GROUND, SwayInput
from fps.weapon_data import Clip, HeadCamData

RELOAD_KEYS = ('reload', 'reload_empty')
ZERO = (0.0,) * 6


@dataclass(frozen=True)
class ReloadState:
    """Ảnh chụp clip nạp đang chạy cho một khung: `t` = giây CỦA CLIP (Handling.t, đã nhân tốc độ), `speed` = ReloadData.speed."""
    clip: Clip
    t: float
    speed: float = 1.0

    def real(self, clip_seconds: float) -> float:
        return clip_seconds / max(self.speed, 1e-3)

    @property
    def elapsed(self) -> float:
        """Giây thật kể từ lúc bắt đầu nạp."""
        return self.real(self.t)

    @property
    def settle_time(self) -> float:
        """Giây thật tới lúc súng, băng, bolt đã về chỗ (Clip.settle; thiếu thì hết clip)."""
        c = self.clip
        return self.real(((c.settle if c.settle is not None else c.end) - c.start) / 30.0)

    @property
    def swap_time(self):
        return None if self.clip.swap is None else self.real(self.clip.swap_time)

    @property
    def end_time(self) -> float:
        return self.real(self.clip.duration)


def reload_state(handling) -> ReloadState:
    """Đọc `core.handling.Handling`: ReloadState khi đang nạp (không tính rút súng), ngược lại None."""
    if handling is None or handling.key not in RELOAD_KEYS:
        return None
    return ReloadState(handling.clip, handling.t, handling.speed)


def glance_weight(d: HeadCamData, rs: ReloadState) -> float:
    """0..1 mức liếc xuống súng theo tiến độ nạp (hàm thuần của thời gian clip)."""
    t = rs.elapsed
    w_in = smoothstep((t - d.glance_in_delay) / d.glance_in_time) if d.glance_in_time > 0 else float(t >= d.glance_in_delay)
    back = rs.settle_time - d.glance_out_lead
    w_out = 1.0 - smoothstep((t - back) / d.glance_out_time) if d.glance_out_time > 0 else float(t < back)
    return max(0.0, min(w_in, w_out))


def footfall(phase: float, sharp: float) -> float:
    """Sóng nhún theo bước, hai bước mỗi chu kỳ pha, ĐÁY = -1 đúng lúc chân chạm đất (pha 3 pi / 4 và 7 pi / 4, như bob của súng),
    trung bình 0. `sharp` 0 = hình sin (bằng sin 2 pha), 1 = |sin| (đáy nhọn như cú dậm, đỉnh tròn và thấp hơn)."""
    n = 2.0 - min(max(sharp, 0.0), 1.0)
    c = abs(math.sin(phase - 0.75 * math.pi))
    mean = math.gamma((n + 1.0) / 2.0) / (math.sqrt(math.pi) * math.gamma(n / 2.0 + 1.0))     # trung bình của |sin|^n
    return (c ** n - mean) / mean


def _lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


class HeadCam:
    def __init__(self, data: HeadCamData):
        self.d = data
        self.t = 0.0
        self.body = Spring(3, data.body_omega, data.body_zeta)     # (roll, pitch, yaw trễ): thân đến trễ, không nhảy theo chuột
        self.jolt = Spring(6, data.jolt_omega, data.jolt_zeta)     # xung nhảy / chạm đất / gật lúc băng vào chỗ, cả 6 thành phần tư thế
        self.step_amount = 0.0           # 0..1 biên độ bước chân (theo tốc độ, ngồi nhỏ hơn)
        self.sprint_mix = 0.0            # 0 đi .. 1 chạy nước rút (trộn bộ biên độ)
        self.jitter_amount = 0.0         # 0..1 rung tay
        self.air = 0.0                   # 0..1 đang trên không
        self.phase = 0.0
        self.glance = 0.0                # 0..1 mức liếc súng khi nạp
        self._jit_u = 0.0                # pha của nhiễu rung tay (tích phân tần số)
        self._events = 0                 # đếm xung để lấy số ngẫu nhiên xác định
        self._reloading = False
        self._release_from = 0.0
        self._release_t = 1e9
        self._last_elapsed = -1.0
        self._pose = ZERO
        self._glance_pose = ZERO
        self._ads = 0.0

    def _random(self) -> float:
        """Số trong [-1, 1], xác định theo seed (nhiễu tại điểm nguyên = giá trị ô)."""
        self._events += 1
        return smooth_noise(self.d.seed, 60, float(self._events))

    def update(self, dt: float, inp: SwayInput, phase: float, lateral: float = 0.0, forward: float = 0.0, reload: ReloadState = None):
        """`phase` = Sway.phase (pha bước chân); `lateral` / `forward` = vận tốc theo hệ người chơi (m/s, phải / tới);
        `reload` = reload_state(combat.handling) của khung này (None khi không nạp)."""
        if dt <= 0.0:
            return
        d = self.d
        self.t += dt
        self.phase = phase
        self._ads = smoothstep(min(max(inp.ads_amount, 0.0), 1.0))

        # --- thân: nghiêng theo cú xoay / đi ngang, cúi khi đi tới ---
        turn = inp.look[0] / dt                                     # độ/s, dương = quay phải
        roll_target = max(-d.turn_roll_max, min(d.turn_roll_max, turn * d.turn_roll)) + lateral * d.strafe_roll
        pitch_target = -forward * d.move_pitch                      # đi tới thì hơi cúi
        yaw_target = -turn * d.turn_yaw_lag                         # khung hình trễ nhẹ sau cú xoay
        sp = self.body
        sp.omega, sp.zeta = d.body_omega, d.body_zeta
        targets = (roll_target, pitch_target, yaw_target)
        for i, target in enumerate(targets):                       # bám mục tiêu qua lò xo: sai số quanh mục tiêu, bước, đưa lại
            sp.x[i] -= target
        sp.step(dt)
        for i, target in enumerate(targets):
            sp.x[i] += target

        # --- nhảy / chạm đất / gật lúc băng vào chỗ: xung vào lò xo nhanh ---
        jo = self.jolt
        jo.omega, jo.zeta = d.jolt_omega, d.jolt_zeta
        gain = impulse_gain(d.jolt_omega, d.jolt_zeta)
        if inp.jumped > 0:
            k = gain * min(inp.jumped / d.land_reference_speed, d.land_max)
            jo.kick([0.0, d.jump_y * k, 0.0, d.jump_pitch * k, 0.0, d.jump_roll * self._random() * k])
        if inp.landed > 0:
            k = gain * min(inp.landed / d.land_reference_speed, d.land_max)
            jo.kick([0.0, -d.land_y * k, 0.0, -d.land_pitch * k, 0.3 * d.land_roll * self._random() * k, d.land_roll * self._random() * k])
        self._update_glance(dt, reload, gain)
        jo.step(dt)

        # --- bước chân, rung tay, trên không: mức trượt mượt (dừng đột ngột không giật) ---
        moving = inp.state in MOVING_ON_GROUND
        sprinting = inp.state is MoveState.SPRINT
        speed_k = min(1.0, inp.speed / d.step_min_speed) if moving else 0.0
        crouch_k = d.step_crouch if inp.state is MoveState.CROUCH_WALK else 1.0
        blend = 1.0 - math.exp(-dt * d.step_blend)
        self.step_amount += (speed_k * crouch_k - self.step_amount) * blend
        self.sprint_mix += ((1.0 if sprinting else 0.0) - self.sprint_mix) * (1.0 - math.exp(-dt * d.sprint_blend))
        jit_target = speed_k * crouch_k * (1.0 if sprinting else d.jitter_walk)
        self.jitter_amount += (jit_target - self.jitter_amount) * blend
        self.air += ((1.0 if inp.state is MoveState.AIR else 0.0) - self.air) * (1.0 - math.exp(-dt * 6.0))
        self._jit_u += dt * _lerp(d.jitter_freq_walk, d.jitter_freq, self.sprint_mix)

        a, s, ph = self.step_amount, self.sprint_mix, phase
        fall = footfall(ph, d.step_sharp)
        nod = footfall(ph + 0.2, d.step_sharp)                      # gật trễ sau nhún một chút
        x = a * _lerp(d.step_x, d.sprint_x, s) * math.sin(ph)
        y = a * _lerp(d.step_y, d.sprint_y, s) * fall
        pitch = a * _lerp(d.step_pitch, d.sprint_pitch, s) * nod - a * s * d.sprint_lean
        yaw = a * _lerp(d.step_yaw, d.sprint_yaw, s) * math.cos(ph)
        roll = a * _lerp(d.step_roll, d.sprint_roll, s) * math.sin(ph)

        j, u, seed = self.jitter_amount, self._jit_u, d.seed

        def shiver(axis):
            return 0.7 * smooth_noise(seed, axis, u) + 0.3 * smooth_noise(seed, axis + 1, 2.7 * u + 17.0)
        x += j * d.jitter_pos * shiver(30)
        y += j * d.jitter_pos * shiver(32)
        pitch += j * d.jitter_angle * shiver(34)
        yaw += j * d.jitter_angle * 0.8 * shiver(36)
        roll += j * d.jitter_angle * 1.2 * shiver(38)

        if self.air > 1e-4:
            v = self.t * d.air_freq
            pitch += self.air * d.air_sway * smooth_noise(seed, 50, v)
            roll += self.air * d.air_sway * 1.4 * smooth_noise(seed, 51, v)

        # trôi chậm + thở lúc đứng yên (nhỏ dần khi bước chân chiếm chỗ)
        idle = max(0.0, 1.0 - 0.7 * min(a, 1.0))
        v = self.t * d.idle_freq
        y += idle * d.idle_y * smooth_noise(seed, 0, v * 1.4)
        pitch += idle * d.idle_pitch * smooth_noise(seed, 1, v)
        yaw += idle * d.idle_yaw * smooth_noise(seed, 2, v)
        roll += idle * d.idle_roll * smooth_noise(seed, 3, v)

        jx = jo.x
        self._pose = (x + jx[0], y + jx[1], jx[2], pitch + sp.x[1] + jx[3], yaw + sp.x[2] + jx[4], roll + sp.x[0] + jx[5])

    def _update_glance(self, dt: float, rs: ReloadState, gain: float):
        d = self.d
        reloading = rs is not None
        if self._reloading and not reloading:                       # vừa xong hoặc bị huỷ: trượt về từ chỗ đang đứng
            self._release_from, self._release_t = self.glance, 0.0
        if reloading and not self._reloading:
            self._last_elapsed = -1.0
        self._reloading = reloading
        self._release_t += dt
        cancel = d.glance_cancel_time
        w = self._release_from * (1.0 - smoothstep(self._release_t / cancel)) if cancel > 0 else 0.0
        if reloading:
            w = max(w, glance_weight(d, rs))                         # nạp lại ngay khi đang trượt về: không giật
            swap, now = rs.swap_time, rs.elapsed
            if swap is not None and self._last_elapsed < swap <= now:
                self.jolt.kick([0.0, 0.0, 0.0, -d.glance_seat_nod * gain * w, 0.0, 0.0])    # băng vào chỗ: gật nhỏ
            self._last_elapsed = now
        self.glance = w
        if w <= 0.0:
            self._glance_pose = ZERO
            return
        v = self.t * d.glance_drift_freq
        drift_p = d.glance_drift * smooth_noise(d.seed, 70, v)
        drift_y = d.glance_drift * smooth_noise(d.seed, 71, v)
        self._glance_pose = (0.0, d.glance_y * w, d.glance_z * w, (-d.glance_pitch + drift_p) * w, (d.glance_yaw + drift_y) * w, d.glance_roll * w)

    def _scale(self) -> float:
        return 1.0 + (self.d.ads_multiplier - 1.0) * self._ads

    def move_pose(self) -> tuple:
        """Chỉ phần chuyển động của người (đã nhân ngắm), không gồm liếc súng."""
        k = self._scale()
        return tuple(c * k for c in self._pose)

    def glance_pose(self) -> tuple:
        return self._glance_pose

    def camera_pose(self) -> tuple:
        return tuple(m + g for m, g in zip(self.move_pose(), self._glance_pose))

    def gun_pose(self) -> tuple:
        """Camera lệch +p thì thế giới lệch -p trên màn hình; súng nối với thân nên đi theo một phần chuyển động đó (đảo dấu).
        Phần liếc đi theo `glance_follow` (~1: súng đứng yên trong thế giới, nên trên màn hình đi lên giữa khung)."""
        f, g = self.d.gun_follow, self.d.glance_follow
        return tuple(-m * f - q * g for m, q in zip(self.move_pose(), self._glance_pose))
