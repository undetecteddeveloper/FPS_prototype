"""Toán thuần của đạn: bay có độ rơi, va chạm đoạn thẳng với hộp và mặt đất. Không import ursina.

Hệ trục như Ursina (y lên). Mỗi khung hình đạn đi một đoạn; ta dò va chạm trên CẢ ĐOẠN vừa bay
(swept) chứ không chỉ tại điểm cuối, nên đạn 500 m/s (8 m mỗi khung ở 60 FPS) không xuyên qua bia mỏng.
"""
import math
from dataclasses import dataclass

GROUND = 'ground'   # owner của va chạm với mặt đất


@dataclass(frozen=True)
class Hit:
    t: float          # 0..1: vị trí trên đoạn p0 -> p1
    point: tuple
    normal: tuple
    owner: object     # đối tượng của hộp bị trúng, hoặc GROUND


def advance(pos, vel, gravity, dt):
    """Đi tiếp dt giây. Công thức chính xác cho trọng lực không đổi nên không phụ thuộc FPS."""
    x, y, z = pos
    vx, vy, vz = vel
    return ((x + vx * dt, y + vy * dt - 0.5 * gravity * dt * dt, z + vz * dt),
            (vx, vy - gravity * dt, vz))


def drop_at_distance(distance, speed, gravity):
    """Độ rơi (m) sau khi bay ngang `distance` mét với tốc độ ngang `speed`."""
    t = distance / speed
    return 0.5 * gravity * t * t


def segment_vs_aabb(p0, p1, lo, hi):
    """Điểm vào đầu tiên của đoạn p0 -> p1 vào hộp [lo, hi]: (t, pháp tuyến) hoặc None.
    Điểm xuất phát nằm trong hộp thì coi là không trúng (đạn đã ở trong, vụ trúng đã được tính trước đó)."""
    tmin, tmax = 0.0, 1.0
    normal = None
    for axis in range(3):
        d = p1[axis] - p0[axis]
        if abs(d) < 1e-12:
            if p0[axis] < lo[axis] or p0[axis] > hi[axis]:
                return None
            continue
        t1 = (lo[axis] - p0[axis]) / d
        t2 = (hi[axis] - p0[axis]) / d
        sign = -1.0 if d > 0 else 1.0       # đi vào qua mặt "lo" khi d > 0: pháp tuyến hướng ngược trục
        if t1 > t2:
            t1, t2 = t2, t1
        if t1 >= tmin:
            tmin = t1
            normal = tuple(sign if i == axis else 0.0 for i in range(3))
        tmax = min(tmax, t2)
        if tmin > tmax:
            return None
    if normal is None:
        return None
    return tmin, normal


def segment_vs_ground(p0, p1, ground_y=0.0):
    """Đoạn đi từ trên mặt đất xuống tới hoặc dưới mặt đất: t hoặc None."""
    if p0[1] > ground_y >= p1[1]:
        return (p0[1] - ground_y) / (p0[1] - p1[1])
    return None


def first_hit(p0, p1, boxes, ground_y=0.0):
    """Va chạm sớm nhất của đoạn p0 -> p1 với danh sách boxes [(lo, hi, owner)] và mặt đất; hoặc None."""
    best = None
    for lo, hi, owner in boxes:
        r = segment_vs_aabb(p0, p1, lo, hi)
        if r and (best is None or r[0] < best.t):
            best = Hit(r[0], _lerp(p0, p1, r[0]), r[1], owner)
    if ground_y is not None:
        t = segment_vs_ground(p0, p1, ground_y)
        if t is not None and (best is None or t < best.t):
            best = Hit(t, _lerp(p0, p1, t), (0.0, 1.0, 0.0), GROUND)
    return best


def distance_between(a, b):
    return math.dist(a, b)


def hole_size(distance, base, per_meter):
    """Cỡ lỗ đạn vẽ ra (m): lỗ thật quá nhỏ để thấy từ xa, nên to dần theo khoảng cách."""
    return base + per_meter * distance


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def decal_rotation(normal):
    """Góc xoay (rx, ry, rz) độ của Ursina để một `quad` (mặt trước nhìn về -z) quay mặt ra theo pháp tuyến
    song song với trục. Mặt phẳng nằm ngang quay quanh x; mặt đứng quay quanh y."""
    nx, ny, nz = normal
    if ny > 0.5:
        return (90.0, 0.0, 0.0)
    if ny < -0.5:
        return (-90.0, 0.0, 0.0)
    if nz < -0.5:
        return (0.0, 0.0, 0.0)
    if nz > 0.5:
        return (0.0, 180.0, 0.0)
    if nx < -0.5:
        return (0.0, 90.0, 0.0)
    return (0.0, -90.0, 0.0)
