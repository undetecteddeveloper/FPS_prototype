"""Ánh sáng đèn trần tính trên CPU (cùng công thức với assets/shaders/light_common.glsl, không tính bóng) và phơi sáng tự động của camera.

Phơi sáng dựa trên độ sáng đo được ngay tại chỗ camera đứng và hướng nhìn, không đọc ngược ảnh từ GPU (đọc ảnh rất chậm trên chip đồ hoạ tích hợp):
vào chỗ tối thì mở dần (chậm), ra chỗ sáng hoặc nhìn thẳng vào đèn thì khép nhanh hơn.
"""
import math

from fps.weapon_data import LensData, LookData


def _smoothstep(a: float, b: float, x: float) -> float:
    if a == b:
        return 1.0 if x >= b else 0.0
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def lamp_attenuation(look: LookData, d2: float, cos_down: float) -> float:
    """Độ rọi của một đèn tới một điểm cách đèn sqrt(d2) mét; `cos_down` = cos góc giữa phương thẳng đứng và đường đèn -> điểm.
    Công thức y hệt `lamp_att` trong light_common.glsl."""
    d = math.sqrt(d2)
    if d >= look.lamp_radius or cos_down <= 0.0:
        return 0.0
    x = d / look.lamp_radius
    win = 1.0 - x * x * x * x
    cone = look.lamp_side + (1.0 - look.lamp_side) * _smoothstep(math.cos(math.radians(look.lamp_cone_outer)),
                                                                 math.cos(math.radians(look.lamp_cone)), cos_down)
    return look.lamp_intensity * cone * win * win / (1.0 + d2 / (look.lamp_ref * look.lamp_ref))


def nearest_lamps(look: LookData, z: float) -> list:
    """Chỉ số các đèn có thể chiếu tới điểm có toạ độ z, gần nhất trước."""
    reach = lamp_reach(look)
    kc = math.floor((z - look.lamp_z0) / look.lamp_spacing + 0.5)
    out = [kc + j for j in sorted(range(-reach, reach + 1), key=abs)]
    return [k for k in out if 0 <= k < look.lamp_count]


def lamp_reach(look: LookData) -> int:
    """Số đèn mỗi bên cần xét để không cắt ánh sáng của đèn nào (mỗi điểm ảnh tốn 2 * reach + 1 đèn)."""
    return max(1, math.ceil((look.lamp_radius - look.lamp_spacing / 2.0) / look.lamp_spacing))


def light_at(look: LookData, pos: tuple, normal: tuple = (0.0, 1.0, 0.0)) -> float:
    """Tổng độ rọi trực tiếp (chưa nhân màu đèn, không tính bóng) lên một mặt có pháp tuyến `normal` tại `pos`."""
    total = 0.0
    for k in nearest_lamps(look, pos[2]):
        lx, ly, lz = look.lamp_x - pos[0], look.lamp_y - pos[1], look.lamp_z0 + k * look.lamp_spacing - pos[2]
        d2 = lx * lx + ly * ly + lz * lz
        if d2 < 1e-6:
            continue
        d = math.sqrt(d2)
        ndl = (lx * normal[0] + ly * normal[1] + lz * normal[2]) / d
        if ndl > 0.0:
            total += lamp_attenuation(look, d2, ly / d) * ndl
    return total


def glare(look: LookData, pos: tuple, forward: tuple) -> float:
    """Đèn gần trong khung hình: 0 (không thấy đèn nào) .. ~1 (nhìn thẳng vào đèn gần)."""
    total = 0.0
    for k in nearest_lamps(look, pos[2]):
        lx, ly, lz = look.lamp_x - pos[0], look.lamp_y - pos[1], look.lamp_z0 + k * look.lamp_spacing - pos[2]
        d2 = max(lx * lx + ly * ly + lz * lz, 1e-6)
        d = math.sqrt(d2)
        c = (lx * forward[0] + ly * forward[1] + lz * forward[2]) / d
        if c > 0.0:
            total += c ** 10 * 12.0 / (4.0 + d2)
    return min(total, 1.5)


def target_exposure(lens: LensData, look: LookData, pos: tuple, forward: tuple) -> float:
    """Phơi sáng mà camera muốn ở chỗ này. Đo trên mặt cầu (trung bình mặt ngửa lên và các mặt đứng) để không lệ thuộc hướng nhìn, cộng thêm phần loá đèn."""
    scene = 0.65 * light_at(look, pos) + 0.35 * light_at(look, pos, (forward[0], 0.0, forward[2]))
    scene += lens.lamp_glare * glare(look, pos, forward)
    ideal = lens.exposure_key / max(scene, 0.02)
    # auto_exposure = 0: cố định ở 1; = 1: bù hoàn toàn; ở giữa: nội suy theo log để tỉ lệ đều
    value = math.exp(math.log(ideal) * lens.auto_exposure)
    return min(max(value, lens.exposure_min), lens.exposure_max)


class AutoExposure:
    def __init__(self, lens: LensData, look: LookData):
        self.lens, self.look = lens, look
        self.value = None

    def update(self, dt: float, pos: tuple, forward: tuple) -> float:
        target = target_exposure(self.lens, self.look, pos, forward)
        if self.value is None:
            self.value = target                                 # khung đầu: khỏi mở dần từ một số vô nghĩa
        else:
            tau = self.lens.exposure_up_time if target > self.value else self.lens.exposure_down_time
            k = 1.0 - math.exp(-dt / tau) if tau > 0 else 1.0
            self.value = math.exp(math.log(self.value) + (math.log(target) - math.log(self.value)) * k)
        return self.value
