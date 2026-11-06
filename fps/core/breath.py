"""Tiếng thở của nhân vật khi đứng yên: một hơi thở mỗi chu kỳ thở của sway (toán thuần, không import ursina).

Sway thở theo Lissajous tần số `SwayData.breath_freq` (ngang một nhịp, dọc hai nhịp mỗi chu kỳ). Mỗi chu kỳ này phát MỘT tiếng thở (một lần hít + một lần thở ra),
bắt đầu đúng lúc súng bắt đầu nhô lên ở nhịp dọc đầu tiên (pha sin(2w + 0,6) = 0, tức w = -0,3 rad), nên tiếng thở và sự nhấp nhô của súng + camera cùng một đồng hồ.
Chỉ phát khi đứng yên (bob chiếm chỗ thì thôi), đang trên mặt đất; ngắm thì nhỏ lại (nín thở ngắm). Đã bắt đầu một hơi thì để nó thở hết, không cắt giữa chừng.
"""
import math

from fps.core.movement import smoothstep
from fps.weapon_data import AudioData, SwayData

SWAY_BREATH_OFFSET = 0.6          # rad: số cộng vào pha dọc trong Sway._breath (sin(2w + 0,6))


class Breathing:
    def __init__(self, audio: AudioData, sway: SwayData):
        self.a = audio
        self.s = sway
        self._cycle = None            # chu kỳ thở (số nguyên) đã xét lần trước

    def reset(self):
        self._cycle = None

    def cycle_index(self, clock: float) -> int:
        """Chu kỳ thở thứ mấy lúc `clock` (giây của Sway): đổi số ở lúc hít vào bắt đầu."""
        # hơi thở bắt đầu ở w = -SWAY_BREATH_OFFSET / 2 (súng bắt đầu nhô lên)
        return math.floor(clock * self.s.breath_freq + SWAY_BREATH_OFFSET / (4.0 * math.pi))

    def update(self, clock: float, bob_amount: float, ads: float, grounded: bool = True):
        """Gọi mỗi khung SAU Sway.update với `Sway.clock`, `Sway.bob_amount`, `player.ads_amount`.
        Trả về âm lượng (0..1) nếu một hơi thở bắt đầu trong khung này, ngược lại None."""
        n = self.cycle_index(clock)
        if self._cycle is None:
            self._cycle = n                          # lần đầu: chờ tới hơi thở kế, không phát ngay giữa chu kỳ
            return None
        if n == self._cycle:
            return None
        self._cycle = n
        a = self.a
        idle = 1.0 - min(max(bob_amount, 0.0), 1.0)
        if not grounded or idle < a.breath_min_idle:
            return None
        hold = 1.0 - (1.0 - a.breath_ads_scale) * smoothstep(min(max(ads, 0.0), 1.0))
        return a.breath_volume * idle * hold
