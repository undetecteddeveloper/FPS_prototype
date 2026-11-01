"""Lò xo giảm chấn nhiều thành phần (toán thuần, không import ursina).

Dùng nghiệm CHÍNH XÁC của dao động tắt dần cho mỗi bước dt, nên ổn định ở mọi FPS và mọi dt
(không cần chia bước nhỏ như Euler). Kick súng (recoil.py) dùng nó; sway chuột ở G4 cũng sẽ dùng.
"""
import math

ZETA_MAX = 0.999   # <1: công thức dưới là dao động tắt dần; lò xo giảm chấn quá mức không có ích cho cảm giác súng


def clamp_zeta(zeta: float) -> float:
    return min(max(zeta, 0.05), ZETA_MAX)


class Spring:
    """n thành phần độc lập, cùng tần số riêng `omega` (rad/s) và tỉ số giảm chấn `zeta`. Về 0 khi yên."""

    def __init__(self, n: int, omega: float, zeta: float):
        self.omega = omega
        self.zeta = zeta
        self.x = [0.0] * n
        self.v = [0.0] * n

    def kick(self, impulses):
        """Cộng thẳng vào vận tốc (xung)."""
        for i, dv in enumerate(impulses):
            self.v[i] += dv

    def step(self, dt: float):
        zeta = clamp_zeta(self.zeta)
        a = zeta * self.omega
        wd = self.omega * math.sqrt(1.0 - zeta * zeta)
        decay = math.exp(-a * dt)
        c, s = math.cos(wd * dt), math.sin(wd * dt)
        for i in range(len(self.x)):
            x0, v0 = self.x[i], self.v[i]
            b = (v0 + a * x0) / wd
            self.x[i] = decay * (x0 * c + b * s)
            self.v[i] = decay * (v0 * c - (a * b + wd * x0) * s)


def impulse_gain(omega: float, zeta: float) -> float:
    """Xung vận tốc cần cho độ lệch đỉnh bằng 1 (khi lò xo đang yên). Nhân với độ lệch đỉnh mong muốn."""
    zeta = clamp_zeta(zeta)
    a = zeta * omega
    wd = omega * math.sqrt(1.0 - zeta * zeta)
    t_peak = math.atan2(wd, a) / wd
    return wd / (math.exp(-a * t_peak) * math.sin(wd * t_peak))


def burst_peak_ratio(omega: float, zeta: float, shots: int, interval: float) -> float:
    """Đỉnh của `shots` xung GIỐNG NHAU cách nhau `interval` giây, chia cho đỉnh của MỘT xung (hệ tuyến tính nên không phụ thuộc độ lớn xung).

    Công thức đóng, độc lập với `Spring.step`: đáp ứng một xung h(t) = e^(-a t) sin(wd t) chuẩn hoá cho đỉnh = 1, cộng chồng các bản dịch
    thời gian. Dùng để test và selftest suy ra "cả băng lùi bao nhiêu lần một phát" từ lò xo thay vì chép số cứng."""
    zeta = clamp_zeta(zeta)
    a = zeta * omega
    wd = omega * math.sqrt(1.0 - zeta * zeta)
    t_peak = math.atan2(wd, a) / wd
    norm = math.exp(-a * t_peak) * math.sin(wd * t_peak)
    step = 0.0005
    best = 0.0
    for k in range(int(((shots - 1) * interval + 3.0 * t_peak) / step)):
        t = k * step
        total = sum(math.exp(-a * (t - i * interval)) * math.sin(wd * (t - i * interval)) for i in range(shots) if t > i * interval)
        best = max(best, total / norm)
    return best
