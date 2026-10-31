"""G4: đo hai điểm ngắm của súng từ đỉnh mô hình (hệ camera, tư thế nghỉ) và in tư thế ADS tính ra.

  - vòng ngắm sau: các đỉnh nằm trong lát z `REAR_Z` cao hơn `REAR_MIN_Y`; tâm = giữa hộp bao của chúng
  - cột ngắm trước: các đỉnh nằm trong lát z `FRONT_Z` cao hơn `FRONT_MIN_Y`; điểm ngắm = giữa hộp bao ngang, đỉnh cao nhất
Kết quả dán vào GunData.ads_sights (weapon_data.py). Lát z/y dưới đây dành cho M4 (xem hộp bao thô khi đổi súng).

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\g4_ads_align.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import GeomVertexReader  # noqa: E402
from ursina import mouse  # noqa: E402

from fps.core.sway import ads_target_for  # noqa: E402

REAR_Z, REAR_MIN_Y = (0.14, 0.17), -0.0135          # vòng ngắm sau của M4: x 0,062..0,073, y -0,0135..-0,0014
FRONT_Z, FRONT_MIN_Y = (0.55, 0.58), -0.0095        # cột ngắm trước, nằm giữa hai cánh che ở x = tâm vòng sau ± 6 mm
FRONT_POST_HALF_WIDTH = 0.0015

game = create_game(vsync=False, draw=False)
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


def bounds(z_range, min_y, x_range=None):
    sel = [p for p in points if z_range[0] <= p[2] <= z_range[1] and p[1] >= min_y
           and (x_range is None or x_range[0] <= p[0] <= x_range[1])]
    lo = [min(p[i] for p in sel) for i in range(3)]
    hi = [max(p[i] for p in sel) for i in range(3)]
    return lo, hi, len(sel)


lo, hi, n = bounds(REAR_Z, REAR_MIN_Y)
rear = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
print(f'vòng sau ({n} đỉnh): tâm ({rear[0]:.4f}, {rear[1]:.4f}, {rear[2]:.4f}); rộng {(hi[0] - lo[0]) * 1000:.1f} mm, cao {(hi[1] - lo[1]) * 1000:.1f} mm')
post_x = (rear[0] - FRONT_POST_HALF_WIDTH, rear[0] + FRONT_POST_HALF_WIDTH)      # chỉ cột giữa, không lấy hai cánh che
lo, hi, n = bounds(FRONT_Z, FRONT_MIN_Y, post_x)
front = ((lo[0] + hi[0]) / 2, hi[1], (lo[2] + hi[2]) / 2)
print(f'cột trước ({n} đỉnh): đỉnh ({front[0]:.4f}, {front[1]:.4f}, {front[2]:.4f})')
print(f'GunData.ads_sights hiện tại: {gun.ads_sights}')
print(f'tư thế ADS đang dùng (x, y, z, pitch lên, yaw phải, roll): {tuple(round(v, 4) for v in ads_target_for(gun))}')
sys.exit(0)
