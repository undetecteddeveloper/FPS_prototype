"""Rút súng và nạp đạn thuần (không import ursina, nên test được không cần cửa sổ).

Máy trạng thái ba pha: READY (bắn được) -> DRAW (rút súng lúc vào game) / RELOAD (đang nạp) -> READY.
Thời gian chạy theo clip của file glb (khung 30 fps) nhân `speed`. Số đạn chỉ đổi đúng khung `Clip.swap`
(băng mới vào chỗ), không phải đầu clip: huỷ trước mốc đó thì đạn y nguyên, huỷ sau thì băng đã nạp rồi.

Phần hình ảnh (phát clip, trộn tư thế khi huỷ) nằm ở `game/viewmodel.py`, nhận các sự kiện qua `drain()`:
  ('start', key, speed)   bắt đầu phát clip `key` (khoá của GunData.clips)
  ('swap', key)           băng mới vào chỗ (đạn đã cập nhật)
  ('done', key)           clip chạy hết
  ('cancel', key, frame)  bị huỷ giữa chừng ở khung `frame` của clip
"""
from enum import Enum

from fps.core.weapon import Weapon
from fps.weapon_data import GunData

FPS = 30.0


class Phase(Enum):
    READY = 'ready'
    DRAW = 'draw'
    RELOAD = 'reload'


class Handling:
    def __init__(self, gun: GunData, weapon: Weapon):
        self.gun = gun
        self.weapon = weapon
        self.phase = Phase.READY
        self.key = None             # khoá clip đang chạy ('draw', 'reload', 'reload_empty')
        self.t = 0.0                # giây CỦA CLIP (đã nhân speed) kể từ đầu clip
        self.swapped = False
        self.loaded = 0             # số viên nạp ở lần thay băng gần nhất
        self.events = []

    # --- đọc ---
    @property
    def clip(self):
        return self.gun.clips[self.key] if self.key else None

    @property
    def busy(self) -> bool:
        return self.phase is not Phase.READY

    @property
    def can_fire(self) -> bool:
        return self.phase is Phase.READY

    @property
    def speed(self) -> float:
        r = self.gun.reload
        return r.draw_speed if self.phase is Phase.DRAW else r.speed

    @property
    def progress(self) -> float:
        """0..1 tiến độ clip đang chạy (0 khi rảnh)."""
        if not self.busy:
            return 0.0
        return min(self.t / self.clip.duration, 1.0)

    @property
    def frame(self) -> float:
        """Khung hiện tại (số thực) trên dòng thời gian chung của file; None khi rảnh."""
        if not self.busy:
            return None
        return min(self.clip.start + self.t * FPS, float(self.clip.end))

    @property
    def remaining(self) -> float:
        """Còn bao nhiêu giây thật nữa thì xong."""
        if not self.busy:
            return 0.0
        return max(self.clip.duration - self.t, 0.0) / self.speed

    # --- lệnh ---
    def start_draw(self) -> bool:
        if self.busy:
            return False
        self._start(Phase.DRAW, 'draw')
        return True

    def start_reload(self) -> bool:
        """Bắt đầu nạp nếu được: đang rảnh, băng chưa đầy, còn dự trữ. Băng cạn dùng clip Reload_Empty."""
        if self.busy or not self.weapon.can_reload:
            return False
        self._start(Phase.RELOAD, 'reload_empty' if self.weapon.mag == 0 else 'reload')
        return True

    def cancel(self) -> bool:
        """Huỷ reload đang chạy (không huỷ được Draw). Đạn đã nạp ở mốc thay băng thì giữ nguyên."""
        if self.phase is not Phase.RELOAD:
            return False
        self.events.append(('cancel', self.key, self.frame))
        self._finish()
        return True

    def _start(self, phase: Phase, key: str):
        self.phase, self.key, self.t, self.swapped = phase, key, 0.0, False
        self.events.append(('start', key, self.speed))

    def _finish(self):
        self.phase, self.key, self.t = Phase.READY, None, 0.0

    # --- mỗi khung ---
    def update(self, dt: float):
        """`dt` là thời gian thật của khung (không cắt ở 50 ms): hình ảnh chạy theo đồng hồ Panda nên logic cũng theo đó."""
        if not self.busy:
            return
        self.t += dt * self.speed
        clip = self.clip
        if not self.swapped and clip.swap is not None and self.t >= clip.swap_time:
            self.swapped = True
            self.loaded = self.weapon.load_magazine()
            self.events.append(('swap', self.key))
        if self.t >= clip.duration:
            self.events.append(('done', self.key))
            self._finish()

    def drain(self) -> list:
        out, self.events = self.events, []
        return out
