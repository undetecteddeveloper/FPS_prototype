"""Toán của ống kính mắt cá, đúng công thức của shaders/lens.frag (toán thuần, để pytest kiểm được).

Toạ độ màn hình p trong [-1, 1]^2. Đo bán kính theo đơn vị nửa bề ngang: q = (p.x, p.y / tỉ lệ khung), r^2 = dot(q, q).
Ảnh ra lấy mẫu ảnh vào tại p * f(r), f = (1 + k r^2) / (1 + k): mép ngang (r = 1) khớp đúng mép ảnh, giữa khung phóng (1 + k) lần, gần góc khung vượt ra
ngoài ảnh vào (chỗ đó do `vignette` che đen).
"""
import math


def warp_factor(r2: float, k: float) -> float:
    return (1.0 + k * r2) / (1.0 + k)


def distort(x: float, y: float, k: float, aspect: float) -> tuple:
    """Điểm (x, y) trên ảnh ra lấy mẫu ở đâu trên ảnh vào."""
    qy = y / aspect
    f = warp_factor(x * x + qy * qy, k)
    return x * f, y * f


def center_scale(fov_deg: float, k: float, reference_fov_deg: float) -> float:
    """Giữa khung phóng bao nhiêu lần so với ảnh phẳng ở FOV `reference_fov_deg`."""
    return (1.0 + k) * math.tan(math.radians(reference_fov_deg) / 2.0) / math.tan(math.radians(fov_deg) / 2.0)


def equivalent_center_fov(fov_deg: float, k: float) -> float:
    """FOV ngang của ảnh phẳng có cùng độ phóng với giữa khung qua ống kính."""
    return 2.0 * math.degrees(math.atan(math.tan(math.radians(fov_deg) / 2.0) / (1.0 + k)))


def vignette(r: float, start: float, end: float) -> float:
    """1 = giữ nguyên, 0 = đen; smoothstep ngược từ `start` tới `end`."""
    t = min(max((r - start) / max(end - start, 1e-6), 0.0), 1.0)
    return 1.0 - t * t * (3.0 - 2.0 * t)
