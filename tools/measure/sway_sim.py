"""Mô phỏng sway lag theo chuột (toán thuần, KHÔNG mở cửa sổ): so TRƯỚC (lò xo vị trí + kẹp cứng) với SAU (MouseLag).

Các kịch bản xoay chuột in: lệch cực đại (độ), quá đà (% của cực đại, ngược dấu), thời gian ổn định (s, tới khi |lệch| < 10%
cực đại hoặc 0,05 độ rồi ở yên), kèm roll/dịch ngang tương ứng ở cực đại.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\measure\\sway_sim.py
"""
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from fps.core.movement import MoveState  # noqa: E402
from fps.core.spring import Spring  # noqa: E402
from fps.core.sway import Sway, SwayInput  # noqa: E402
from fps.weapon_data import SwayData  # noqa: E402


@dataclass
class Legacy:
    """Cách cũ (trước khi có MouseLag): mỗi khung cộng -góc quay * gain vào VỊ TRÍ lò xo (kẹp cứng ±max), lò xo zeta 0,7."""
    gain: float = 0.35
    max: float = 4.0
    omega: float = 13.0
    zeta: float = 0.7
    roll: float = 0.4

    def __post_init__(self):
        self.spring = Spring(2, self.omega, self.zeta)

    def update(self, dt, look):
        s = self.spring
        for i in (0, 1):
            s.x[i] = max(-self.max, min(self.max, s.x[i] - look[i] * self.gain))
        s.step(dt)
        return s.x[0], s.x[0] * self.roll


class New:
    def __init__(self, data=None):
        self.sway = Sway(data or SwayData(breath_x=0, breath_y=0, breath_pitch=0, breath_yaw=0))

    def update(self, dt, look):
        pose = self.sway.update(dt, SwayInput(MoveState.IDLE, 0.0, 0.0, 0.0, look))
        return pose[4], pose[5]


def run(model, rate_dps, move_s, fps, total_s=2.0, pattern=None):
    """Quay yaw đều `rate_dps` trong `move_s` giây rồi dừng. `pattern(t)` (nếu có) cho vận tốc theo thời gian. Trả [(t, yaw, roll)]."""
    dt = 1.0 / fps
    out = []
    for i in range(round(total_s * fps)):
        t = i * dt
        v = pattern(t) if pattern else (rate_dps if t < move_s else 0.0)
        yaw, roll = model.update(dt, (v * dt, 0.0))
        out.append((t + dt, yaw, roll))
    return out


def metrics(trace, move_end):
    sign = -1.0 if max(abs(y) for _, y, _ in trace) and min(y for _, y, _ in trace) < -max(y for _, y, _ in trace) else 1.0
    peak_i = max(range(len(trace)), key=lambda i: sign * trace[i][1])
    peak = sign * trace[peak_i][1]
    after = [(t, sign * y) for t, y, _ in trace if t >= trace[peak_i][0]]
    over = max(0.0, -min(y for _, y in after))                    # đoạn ngược dấu sau cực đại
    thresh = max(0.1 * peak, 0.05)
    settle = None
    for t, y in reversed([(t, sign * y) for t, y, _ in trace]):
        if abs(y) > thresh:
            settle = t - move_end
            break
    return peak, 100.0 * over / peak if peak else 0.0, max(0.0, settle if settle is not None else 0.0), trace[peak_i][2]


SCENARIOS = [
    ('flick 120 độ/s x 0,15 s', 120, 0.15, None),
    ('flick 240 độ/s x 0,15 s', 240, 0.15, None),
    ('flick 400 độ/s x 0,10 s', 400, 0.10, None),
    ('flick 900 độ/s x 0,10 s', 900, 0.10, None),
    ('xoay chậm 20 độ/s x 1,5 s', 20, 1.5, None),
    ('xoay vừa 60 độ/s x 1,0 s', 60, 1.0, None),
    ('xoay chậm 10 độ/s x 1,5 s (ngắm)', 10, 1.5, None),
]


def report(label, model_factory, fps=144):
    print(f'\n== {label} ({fps} FPS) ==')
    print(f'{"kịch bản":<34}{"lệch cực đại":>13}{"quá đà %":>10}{"ổn định s":>11}{"roll@đỉnh":>11}')
    for name, rate, dur, pat in SCENARIOS:
        tr = run(model_factory(), rate, dur, fps, total_s=dur + 1.5, pattern=pat)
        peak, over, settle, roll = metrics(tr, dur)
        print(f'{name:<34}{peak:>12.2f}°{over:>9.1f}%{settle:>10.2f}s{abs(roll):>10.2f}°')
    # qua lại: +240 độ/s 0,15 s, nghỉ 0,1 s, -240 độ/s 0,15 s
    pat = lambda t: 240 if t < 0.15 else (-240 if 0.25 <= t < 0.40 else 0.0)  # noqa: E731
    tr = run(model_factory(), 0, 0, fps, total_s=1.9, pattern=pat)
    ys = [y for _, y, _ in tr]
    print(f'{"qua lại ±240 độ/s":<34}  yaw trong [{min(ys):.2f}°, {max(ys):.2f}°]')


if __name__ == '__main__':
    report('TRƯỚC: lò xo vị trí + kẹp cứng', lambda: Legacy())
    report('SAU: MouseLag (hệ bậc hai theo vận tốc + nén mềm)', lambda: New())
    print('\nĐộc lập FPS (flick 240 độ/s x 0,15 s), lệch cực đại SAU:')
    for fps in (30, 60, 144, 500, 1000):
        tr = run(New(), 240, 0.15, fps, total_s=1.5)
        peak, over, settle, _ = metrics(tr, 0.15)
        print(f'  {fps:>5} FPS: {peak:.3f}°  quá đà {over:.1f}%  ổn định {settle:.2f}s')
