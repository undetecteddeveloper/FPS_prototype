"""G5: đo vị trí miệng nòng từ đỉnh mô hình (hệ camera súng, tư thế nghỉ) để đặt tia lửa đầu nòng và điểm xuất phát của tracer.

Miệng nòng = tâm hộp bao (ngang, dọc) của các đỉnh nằm trong `TIP_DEPTH` mét cuối cùng của thân súng theo trục z (ra trước);
z = đỉnh xa nhất. Hướng nòng lấy từ trục của lát đó so với lát lùi lại `AXIS_BACK` mét (nòng M4 gần như song song trục z).
Kết quả dán vào GunData.muzzle (weapon_data.py).

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\measure\\g5_muzzle_align.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import GeomVertexReader  # noqa: E402
from ursina import mouse  # noqa: E402

TIP_DEPTH = 0.012
AXIS_BACK = (0.05, 0.08)           # lát dùng để ước lượng hướng nòng: lùi 5..8 cm so với đầu

game = create_game(vsync=False, draw=False, sound=False)
mouse.locked = False
vm = game.viewmodel
gun = game.params.gun
points = []
for geom_np in vm.actor.find('**/Main_M4_D_0-parent').find_all_matches('**/+GeomNode'):
    mat = geom_np.get_mat(vm.cam_np)
    node = geom_np.node()
    for i in range(node.get_num_geoms()):
        reader = GeomVertexReader(node.get_geom(i).get_vertex_data(), 'vertex')
        while not reader.is_at_end():
            p = mat.xform_point(reader.get_data3())
            points.append((float(p[0]), float(p[1]), float(p[2])))

zmax = max(p[2] for p in points)


def slab_center(z_lo, z_hi):
    sel = [p for p in points if z_lo <= p[2] <= z_hi]
    lo = [min(p[i] for p in sel) for i in range(3)]
    hi = [max(p[i] for p in sel) for i in range(3)]
    return tuple((lo[i] + hi[i]) / 2 for i in range(3)), tuple(hi[i] - lo[i] for i in range(3)), len(sel)


tip, size, n = slab_center(zmax - TIP_DEPTH, zmax)
back, _, _ = slab_center(zmax - AXIS_BACK[1], zmax - AXIS_BACK[0])
dz = tip[2] - back[2]
axis = ((tip[0] - back[0]) / dz, (tip[1] - back[1]) / dz, 1.0)
print(f'đầu súng z = {zmax:.4f} m ({n} đỉnh trong {TIP_DEPTH * 1000:.0f} mm cuối)')
print(f'miệng nòng: ({tip[0]:.4f}, {tip[1]:.4f}, {zmax:.4f}); đường kính ngang {size[0] * 1000:.1f} mm, dọc {size[1] * 1000:.1f} mm')
print(f'hướng nòng so với trục z: x {axis[0]:+.4f}, y {axis[1]:+.4f} (mỗi mét đi tới)')
print(f'GunData.muzzle hiện tại: {gun.muzzle}')
sys.exit(0)
