"""Bố cục biển khoảng cách treo trần (toán thuần, không import ursina, pytest được).

Mỗi mốc khoảng cách có một CẶP biển (trái và phải làn) quay mặt về phía người bắn (-z), treo ngay trước mốc (cách `z_offset`
về phía người bắn) nên không đè lên dầm trần ở đúng mốc đó. Biển xa to dần (chữ xa vẫn nhìn được) nhưng bị trần chặn nên chữ
ở 200 m chỉ cao ~1,5 m. Mép dưới biển luôn cao hơn đỉnh bia lớn nhất để biển không che bia và bia chạy đi lọt dưới biển.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SignLayout:
    bottom: float = 3.0           # m: mép dưới của mọi biển (bia lớn nhất, 200 m, cao 2,86 m)
    ceiling: float = 5.5          # m: trần phòng; biển có đỉnh chạm gần trần thì gắn thẳng vào trần, không cần cột treo
    top_margin: float = 0.05      # m: khe giữa đỉnh biển và trần khi biển cao tối đa
    height_base: float = 0.70     # m: chiều cao biển ở 0 m
    height_per_m: float = 0.0070  # m/m: biển xa to thêm
    aspect: float = 3.0           # rộng / cao
    thickness: float = 0.06
    z_offset: float = 0.40        # m: biển nằm trước mốc bấy nhiêu (phía người bắn)
    rod_half: float = 0.015       # m: nửa tiết diện cột treo
    # x của TÂM biển (trị tuyệt đối; hai biển ở +x và -x). Nhìn từ vạch bắn các biển 100/150/200 m cùng chen trong vài độ quanh trục làn
    # nên x được chọn (tìm ngẫu nhiên) để biển gần che biển xa ít nhất: tối đa ~8% diện tích (test_signs.test_signs_do_not_hide_each_other)
    x: tuple = ((10, 4.3), (25, 4.8), (50, 6.0), (100, 9.0), (150, 8.3), (200, 5.1))

    @property
    def max_height(self) -> float:
        return self.ceiling - self.top_margin - self.bottom


def sign_height(layout: SignLayout, distance: float) -> float:
    return min(layout.height_base + layout.height_per_m * distance, layout.max_height)


def sign_center_x(layout: SignLayout, distance: float) -> float:
    table = dict(layout.x)
    if distance in table:
        return table[distance]
    return table[min(table, key=lambda d: abs(d - distance))]


def sign_rect(layout: SignLayout, distance: float, side: int = 1) -> dict:
    """Hộp của biển ở mốc `distance`, phía `side` (+1 phải, -1 trái): toạ độ thế giới.
    Trả về dict: cx, cy, cz, w, h, lo (x, y, z min), hi."""
    h = sign_height(layout, distance)
    w = h * layout.aspect
    cx = side * sign_center_x(layout, distance)
    cy = layout.bottom + h / 2
    cz = distance - layout.z_offset
    t = layout.thickness / 2
    return {'cx': cx, 'cy': cy, 'cz': cz, 'w': w, 'h': h,
            'lo': (cx - w / 2, cy - h / 2, cz - t), 'hi': (cx + w / 2, cy + h / 2, cz + t)}


def rod_xs(rect: dict) -> tuple:
    """x của hai cột treo biển: gần hai đầu biển."""
    return rect['cx'] - rect['w'] * 0.4, rect['cx'] + rect['w'] * 0.4


def angular_rect(rect: dict, eye=(0.0, 1.62, 0.0)) -> tuple:
    """Hình chiếu góc của mặt trước biển lên màn nhìn từ `eye` theo +z: (x0, x1, y0, y1) theo tan góc ngang / dọc."""
    z = rect['cz'] - eye[2]                                              # độ dày biển bỏ qua
    return ((rect['lo'][0] - eye[0]) / z, (rect['hi'][0] - eye[0]) / z, (rect['lo'][1] - eye[1]) / z, (rect['hi'][1] - eye[1]) / z)


def overlap_fraction(near: dict, far: dict, eye=(0.0, 1.62, 0.0)) -> float:
    """Phần diện tích (theo góc nhìn từ `eye`) của biển XA bị biển GẦN che."""
    a, b = angular_rect(near, eye), angular_rect(far, eye)
    ox = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    oy = max(0.0, min(a[3], b[3]) - max(a[2], b[2]))
    area = (b[1] - b[0]) * (b[3] - b[2])
    return ox * oy / area if area > 0 else 0.0
