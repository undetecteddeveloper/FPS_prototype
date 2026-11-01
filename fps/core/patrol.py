"""Chuyển động của bia chạy: đi đều giữa hai biên, quay đầu (nghỉ một chút ở mỗi đầu). Toán thuần, không import ursina.

Trạng thái là (vị trí, chiều, thời gian nghỉ còn lại) và `advance(dt)` tiêu thời gian chính xác nên kết quả KHÔNG phụ thuộc cách
chia khung hình: đi một bước 50 ms cho đúng vị trí như đi 50 bước 1 ms (kể cả khi một bước dài qua nhiều lần quay đầu).
"""
from dataclasses import dataclass


@dataclass
class Patrol:
    lo: float                # biên trái (x nhỏ nhất của TÂM bia)
    hi: float                # biên phải
    speed: float             # m/s
    pause: float = 0.0       # s nghỉ ở mỗi đầu trước khi quay lại
    x: float = 0.0
    direction: float = 1.0   # +1 sang phải (x tăng), -1 sang trái
    wait: float = 0.0        # s nghỉ còn lại ở đầu hiện tại

    def __post_init__(self):
        if not self.lo < self.hi:
            raise ValueError('biên trái phải nhỏ hơn biên phải')
        self.x = min(max(self.x, self.lo), self.hi)

    @property
    def velocity(self) -> float:
        """Vận tốc tức thời (m/s, có dấu): 0 khi đang nghỉ ở đầu."""
        return 0.0 if self.wait > 0.0 else self.speed * self.direction

    @property
    def span(self) -> float:
        return self.hi - self.lo

    @property
    def period(self) -> float:
        """Một vòng đi-về (s), kể cả hai lần nghỉ."""
        return 2.0 * (self.span / self.speed + self.pause)

    def advance(self, dt: float) -> float:
        """Đi tiếp `dt` giây; trả về x mới của tâm bia."""
        left = dt
        # mỗi vòng lặp hoặc tiêu hết thời gian, hoặc chạm một đầu (rồi quay + nghỉ): hữu hạn kể cả khi dt rất lớn
        while left > 1e-12:
            if self.wait > 0.0:
                used = min(self.wait, left)
                self.wait -= used
                left -= used
                continue
            if self.speed <= 0.0:
                break
            end = self.hi if self.direction > 0 else self.lo
            reach = abs(end - self.x) / self.speed          # thời gian tới đầu
            if left < reach:
                self.x += self.direction * self.speed * left
                break
            self.x = end
            left -= reach
            self.direction = -self.direction
            self.wait = self.pause
        return self.x

    def reset(self, x: float, direction: float = 1.0):
        self.x = min(max(x, self.lo), self.hi)
        self.direction = 1.0 if direction >= 0 else -1.0
        self.wait = 0.0


def phase_start(lo: float, hi: float, phase: float) -> tuple:
    """Điểm xuất phát (x, chiều) ứng với pha 0..1 của một vòng đi-về không nghỉ: để các bia chạy không đồng bộ với nhau."""
    phase = phase % 1.0
    span = hi - lo
    if phase < 0.5:
        return lo + span * phase * 2.0, 1.0
    return hi - span * (phase - 0.5) * 2.0, -1.0
