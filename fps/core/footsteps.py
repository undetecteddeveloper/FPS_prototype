"""Bước chân, nhảy, chạm đất (thuần, không import ursina, nên test được không cần cửa sổ).

Nhịp bước tính theo QUÃNG ĐƯỜNG đi được khi đang chạm đất (pha 0..1 tăng `quãng / sải`), nên đúng nhịp ở mọi tốc độ và mọi FPS;
không đọc pha bob của Sway (bob chỉnh riêng). Trên không: im. Chạm đất: một tiếng 'bịch' to theo tốc độ rơi (thay cho bước kế tiếp).
Nhảy lên: một tiếng đế nhỏ. Dừng hẳn: không phát thêm, và bước đầu tiên sau khi đứng yên đến sớm (`step_start_phase`).

Hàm `update` trả về danh sách `FootEvent`; việc chọn file và phát nằm ở game/foley.py.
"""
import random
from dataclasses import dataclass

from fps.weapon_data import AudioData


@dataclass(frozen=True)
class FootEvent:
    kind: str          # 'step' | 'land' | 'jump'
    foot: int          # 0 trái, 1 phải (luân phiên)
    gain: float        # âm lượng đã gồm ngẫu nhiên (nhân với 1 = đầy)
    pitch: float       # tỉ lệ tốc độ phát (1 = nguyên)
    run: bool = False  # bước chạy nước rút (dùng nhóm tiếng 'step_run')


def pick_variant(rng: random.Random, count: int, last: int = None) -> int:
    """Chọn một biến thể trong `count`, không trùng biến thể vừa dùng (nếu có thể)."""
    if count <= 1:
        return 0
    k = rng.randrange(count - 1) if last is not None and 0 <= last < count else rng.randrange(count)
    return k + 1 if last is not None and 0 <= last < count and k >= last else k


class Footsteps:
    def __init__(self, audio: AudioData, rng: random.Random = None):
        self.a = audio
        self.rng = rng or random.Random()
        self.phase = audio.step_start_phase
        self.foot = 0
        self._was_on_ground = True

    def _vary(self, base_gain: float, foot: int, variation_pitch: float = None) -> tuple:
        a, rng = self.a, self.rng
        gain = base_gain * (1.0 + rng.uniform(-a.step_volume_variation, a.step_volume_variation))
        v = a.step_pitch_variation if variation_pitch is None else variation_pitch
        pitch = 1.0 + rng.uniform(-v, v) + (a.foot_pitch if foot else -a.foot_pitch)
        return gain, pitch

    def update(self, dt: float, moved: float, on_ground: bool, vy: float, landed: float, sprinting: bool, crouching: bool) -> list:
        """Một khung. `moved`: quãng đường ngang vừa đi (m); `vy`: tốc độ đứng sau bước vật lý; `landed`: tốc độ chạm đất (m/s) nếu khung này vừa chạm đất."""
        a = self.a
        events = []
        if self._was_on_ground and not on_ground and vy > 0.0:
            gain, pitch = self._vary(a.jump_volume, self.foot)
            events.append(FootEvent('jump', self.foot, gain, pitch))
        self._was_on_ground = on_ground

        if landed >= a.land_min_speed:
            lo, hi = a.land_gain_range
            level = min(max(landed / a.land_reference_speed, lo), hi)
            gain, pitch = self._vary(a.land_volume * level, self.foot, a.step_pitch_variation)
            events.append(FootEvent('land', self.foot, gain, pitch))
            self.phase = a.step_start_phase
        elif on_ground:
            speed = moved / dt if dt > 0 else 0.0
            if speed < a.step_min_speed:
                self.phase = a.step_start_phase        # đứng yên: không phát, và bước đầu tiên sau đó đến sớm
            else:
                if crouching:
                    stride, mult = a.step_stride_crouch, a.step_crouch_multiplier
                elif sprinting:
                    stride, mult = a.step_stride_sprint, a.step_sprint_multiplier
                else:
                    stride, mult = a.step_stride_walk, 1.0
                self.phase += moved / stride
                emitted = 0
                while self.phase >= 1.0 and emitted < 2:      # tối đa 2 bước mỗi khung (khung treo dài không xả cả loạt)
                    self.phase -= 1.0
                    gain, pitch = self._vary(a.step_volume * mult, self.foot)
                    events.append(FootEvent('step', self.foot, gain, pitch, run=sprinting and not crouching))
                    self.foot ^= 1
                    emitted += 1
                self.phase = min(self.phase, 1.0)
        return events
