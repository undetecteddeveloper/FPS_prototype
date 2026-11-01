"""Toán thuần của phòng tập kín: kích thước, hộp của tường/cột/dầm/trần, vị trí đèn trần, bố cục bản đồ bóng của đèn.
Không import ursina (pytest được). Hệ trục như Ursina: y lên, làn bắn dọc +z, người chơi đứng ở z = 0.

Bóng thật của đèn điểm: mỗi đèn một "cubemap" 5 mặt (+x, -x, -y, +z, -z; đèn treo dưới trần nên bỏ mặt hướng lên),
xếp thành các ô trong MỘT kết cấu độ sâu (atlas). Shader chọn mặt theo trục lớn nhất của vector đèn -> điểm (`cube_face`),
rồi chọn ô theo (đèn, mặt) (`tile_rect`). Mỗi mặt vẽ với góc nhìn rộng hơn 90 độ một chút (`face_fov`) để 4 mẫu PCF ở mép
mặt vẫn nằm trong ô của nó.
"""
import math
from dataclasses import dataclass

from fps.core.ballistics import BoxGroup

FACES = ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0))   # hướng nhìn của 5 mặt
FACE_COUNT = len(FACES)


@dataclass(frozen=True)
class RoomLayout:
    """Kích thước phòng (m). Mặt TRONG của tường ở x = ±half_width, z = z_back, z = z_end; trần ở y = height."""
    half_width: float = 12.0
    z_back: float = -20.0
    z_end: float = 216.0
    height: float = 5.5
    wall_thickness: float = 0.5
    pillar_z0: float = -10.0          # cột trụ áp tường hai bên, cách đều; dầm trần nối hai cột đối diện
    pillar_spacing: float = 10.0
    pillar_width: float = 0.6         # dọc z
    pillar_depth: float = 0.35        # nhô ra khỏi tường
    beam_width: float = 0.4
    beam_depth: float = 0.45          # thò xuống dưới trần
    walk_margin: float = 1.2          # người chơi cách mặt tường ít nhất bấy nhiêu (cột nhô 0,35 m)


def pillar_zs(room: RoomLayout) -> list:
    zs, z = [], room.pillar_z0
    while z < room.z_end - room.pillar_width:
        if z > room.z_back + room.pillar_width:
            zs.append(z)
        z += room.pillar_spacing
    return zs


def wall_boxes(room: RoomLayout) -> list:
    """(lo, hi) của 4 tường, dày `wall_thickness` ra phía ngoài, cao hết tới trên mặt trần; góc phòng kín."""
    w, t, h = room.half_width, room.wall_thickness, room.height + room.wall_thickness
    z0, z1 = room.z_back - t, room.z_end + t
    return [((-w - t, 0.0, z0), (-w, h, z1)),                 # trái
            ((w, 0.0, z0), (w + t, h, z1)),                   # phải
            ((-w - t, 0.0, z0), (w + t, h, room.z_back)),     # sau lưng người chơi
            ((-w - t, 0.0, room.z_end), (w + t, h, z1))]      # cuối làn


def ceiling_box(room: RoomLayout) -> tuple:
    w, t = room.half_width + room.wall_thickness, room.wall_thickness
    return (-w, room.height, room.z_back - t), (w, room.height + t, room.z_end + t)


def pillar_boxes(room: RoomLayout) -> list:
    w, d, hw = room.half_width, room.pillar_depth, room.pillar_width / 2
    out = []
    for z in pillar_zs(room):
        out.append(((-w, 0.0, z - hw), (-w + d, room.height, z + hw)))
        out.append(((w - d, 0.0, z - hw), (w, room.height, z + hw)))
    return out


def beam_boxes(room: RoomLayout) -> list:
    w, hw = room.half_width, room.beam_width / 2
    return [((-w, room.height - room.beam_depth, z - hw), (w, room.height, z + hw)) for z in pillar_zs(room)]


def panel_boxes(room: RoomLayout, y0: float = 1.6, y1: float = 4.3, thickness: float = 0.06, gap: float = 0.9) -> list:
    """Tấm tiêu âm trên hai tường bên, cách một ô (giữa hai cột) có một tấm: [(lo, hi)]."""
    zs = pillar_zs(room)
    w = room.half_width
    out = []
    for i in range(0, len(zs) - 1, 2):
        z0, z1 = zs[i] + room.pillar_width / 2 + gap, zs[i + 1] - room.pillar_width / 2 - gap
        out.append(((-w, y0, z0), (-w + thickness, y1, z1)))
        out.append(((w - thickness, y0, z0), (w, y1, z1)))
    return out


def walk_bounds(room: RoomLayout, z_min: float, z_max: float) -> tuple:
    """(x_min, x_max, z_min, z_max) cho `movement.clamp_to_bounds`: trong phòng, cách tường `walk_margin`."""
    x = room.half_width - room.walk_margin
    return (-x, x, max(z_min, room.z_back + room.walk_margin), min(z_max, room.z_end - room.walk_margin))


def grouped(boxes: list, owner, chunk: float) -> list:
    """Gom các hộp nhỏ (cột, dầm) theo từng đoạn `chunk` mét dọc z thành `BoxGroup`; trả về các mục cho `first_hit`."""
    buckets = {}
    for lo, hi in boxes:
        side = 0 if lo[0] + hi[0] < 0 else 1
        buckets.setdefault((side, math.floor((lo[2] + hi[2]) / 2 / chunk)), []).append((lo, hi, owner))
    return [BoxGroup(v).entry() for _, v in sorted(buckets.items())]


# --- đèn trần ---
def lamp_positions(x: float, y: float, z0: float, spacing: float, count: int) -> list:
    return [(x, y, z0 + i * spacing) for i in range(count)]


def nearest_lamp(z: float, z0: float, spacing: float, count: int) -> int:
    """Chỉ số đèn gần nhất theo z (giống shader: shader xét đèn này và hai đèn mỗi bên)."""
    return min(max(int(math.floor((z - z0) / spacing + 0.5)), 0), count - 1)


def cube_face(v) -> int:
    """Mặt cubemap chứa vector đèn -> điểm `v`: chỉ số trong FACES, hoặc None nếu thuộc mặt hướng lên (không vẽ: đèn sát trần)."""
    ax, ay, az = abs(v[0]), abs(v[1]), abs(v[2])
    if ax >= ay and ax >= az:
        return 0 if v[0] > 0 else 1
    if ay >= az:
        return None if v[1] > 0 else 2
    return 3 if v[2] > 0 else 4


def atlas_grid(tiles: int) -> tuple:
    """(cột, hàng) gần vuông đủ chứa `tiles` ô."""
    cols = math.ceil(math.sqrt(tiles))
    return cols, math.ceil(tiles / cols)


def tile_index(lamp: int, face: int) -> int:
    return lamp * FACE_COUNT + face


def tile_rect(index: int, cols: int, rows: int) -> tuple:
    """(trái, phải, dưới, trên) của ô trong atlas, toạ độ 0..1 kiểu DisplayRegion của Panda (0 = dưới).
    Shader dùng đúng công thức này: cột = index mod cols, hàng = index div cols."""
    c, r = index % cols, index // cols
    return c / cols, (c + 1) / cols, r / rows, (r + 1) / rows


def face_fov(tile_px: int, guard_px: float) -> float:
    """Góc nhìn (độ) của một mặt sao cho đúng 90 độ rơi vào `tile_px - 2*guard_px` điểm ảnh giữa ô:
    viền `guard_px` điểm ảnh mỗi bên chứa phần tràn ra của mặt bên cạnh, mẫu PCF ở mép không lấn sang ô khác."""
    return 2.0 * math.degrees(math.atan(tile_px / (tile_px - 2.0 * guard_px)))
