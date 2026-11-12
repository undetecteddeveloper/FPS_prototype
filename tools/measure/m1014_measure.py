r"""Benelli M1014: measures the model in the camera frame (x right, y up, z forward; ready pose, hip_offset NOT applied) and prints the values to paste into M1014 in weapon_data.py
(ads_sights, muzzle, smoke.ejection_port). The M1014 file is one skinned mesh per material (the gun body, the hands...), so every number comes from the ANIMATED vertices
(GeomVertexData.animate_vertices), unlike g8_measure.py / g4_ads_align.py where the gun parts are rigid nodes.

  rear sight : the ghost ring on the receiver: the highest vertices (in the camera's y) of the rear part of the body mesh; the point is the centre of the box of the topmost 4 mm
  front sight: the highest vertices of the front part (the front post on the muzzle end); point = centre x, highest vertex
  muzzle     : the front-most vertices of the barrel (centre of the box of the last 5 mm)
  extents    : bounding boxes of every mesh, to see where the gun and the hands sit relative to the eye

Run:  .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\m1014_measure.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

import numpy as np  # noqa: E402  (a measuring tool: the game itself never imports numpy)
from main import create_game  # noqa: E402
from panda3d.core import GeomVertexReader, Thread  # noqa: E402
from ursina import mouse  # noqa: E402

game = create_game(vsync=False, draw=False, sound=False, effects=False, look=False, gun='m1014')
mouse.locked = False
vm, gun = game.viewmodel, game.params.gun
vm.hold_ready_pose()
hx, hy, hz = gun.hip_offset
to_cam = vm.actor.get_mat(vm.cam_np)             # actor space -> camera space (the skinned vertices are in the actor's space)


def points(geom_np) -> np.ndarray:
    out = []
    node = geom_np.node()
    for i in range(node.get_num_geoms()):
        data = node.get_geom(i).get_vertex_data().animate_vertices(True, Thread.get_current_thread())
        reader = GeomVertexReader(data, 'vertex')
        while not reader.is_at_end():
            p = to_cam.xform_point(reader.get_data3())
            out.append((p[0] - hx, p[1] - hy, p[2] - hz))          # hip_offset is part of the rig's position: take it out (the table values are 'hip_offset NOT included')
    return np.array(out)


meshes = {g.get_name(): points(g) for g in vm.actor.find_all_matches('**/+GeomNode')}
for name, p in meshes.items():
    print(f'{name[:46]:46s} x {p[:, 0].min():7.3f}..{p[:, 0].max():7.3f}  y {p[:, 1].min():7.3f}..{p[:, 1].max():7.3f}  z {p[:, 2].min():7.3f}..{p[:, 2].max():7.3f}')
body = next(p for n, p in meshes.items() if n.endswith('TTI_Benelli_M4_0_TTI_Benelli_M4_0'))
zmin, zmax = body[:, 2].min(), body[:, 2].max()
print(f'\nthân súng: dài {zmax - zmin:.3f} m, từ z {zmin:.3f} tới {zmax:.3f}; cao nhất y {body[:, 1].max():.3f}')
# the stock end is the part nearest to the eye; the rear sight stands on the receiver, a little ahead of it
for lo_frac, hi_frac, label in ((0.30, 0.50, 'ghost ring (30-50% chiều dài)'), (0.35, 0.55, '35-55%'), (0.40, 0.60, '40-60%')):
    sel = body[(body[:, 2] >= zmin + lo_frac * (zmax - zmin)) & (body[:, 2] <= zmin + hi_frac * (zmax - zmin))]
    top = sel[:, 1].max()
    best = sel[sel[:, 1] >= top - 0.004]
    print(f'  {label}: đỉnh y {top:.4f}, tâm x {best[:, 0].mean():.4f} z {best[:, 2].mean():.4f} ({len(best)} đỉnh)')
front_sel = body[body[:, 2] >= zmax - 0.06]
top = front_sel[:, 1].max()
best = front_sel[front_sel[:, 1] >= top - 0.003]
print(f'  đầu ruồi (6 cm cuối): đỉnh y {top:.4f}, tâm x {best[:, 0].mean():.4f} z {best[:, 2].mean():.4f}')
tip = body[body[:, 2] >= zmax - 0.005]
print(f'  miệng nòng: tâm x {(tip[:, 0].min() + tip[:, 0].max()) / 2:.4f} y {(tip[:, 1].min() + tip[:, 1].max()) / 2:.4f} z {zmax:.4f}')
print('\nhồ sơ nóc thân súng (cao nhất y mỗi lát 4 cm theo z) và cạnh phải nhất x:')
for z0 in np.arange(zmin, zmax, 0.04):
    sl = body[(body[:, 2] >= z0) & (body[:, 2] < z0 + 0.04)]
    if len(sl):
        print(f'  z {z0:6.3f}: nóc y {sl[:, 1].max():7.4f}  đáy y {sl[:, 1].min():7.4f}  x {sl[:, 0].min():7.4f}..{sl[:, 0].max():7.4f}')
right = body[body[:, 0] >= body[:, 0].max() - 0.004]
print(f'cạnh phải (x >= {body[:, 0].max() - 0.004:.3f}): z {right[:, 2].min():.3f}..{right[:, 2].max():.3f}, y {right[:, 1].min():.3f}..{right[:, 1].max():.3f}')
for z_lo, z_hi, label in ((-0.43, -0.28, 'ghost ring'), (0.12, 0.27, 'ruồi')):
    sl = body[(body[:, 2] >= z_lo) & (body[:, 2] <= z_hi)]
    top = sl[:, 1].max()
    best = sl[sl[:, 1] >= top - 0.003]
    print(f'{label}: đỉnh y {top:.4f}; x {best[:, 0].min():.4f}..{best[:, 0].max():.4f}; z {best[:, 2].min():.4f}..{best[:, 2].max():.4f}')
for z_lo, z_hi, label in ((-0.356, -0.338, 'ghost ring, nhìn dọc nòng (x ngang, y đứng)'), (0.222, 0.238, 'ruồi, nhìn dọc nòng')):
    sl = body[(body[:, 2] >= z_lo) & (body[:, 2] <= z_hi) & (body[:, 1] > body[:, 1].max() - 0.03)]
    print(f'\n{label}: {len(sl)} đỉnh; mỗi ô 1 mm; y từ {sl[:, 1].max():.4f} xuống')
    x0, y1 = sl[:, 0].min(), sl[:, 1].max()
    cols, rows = int((sl[:, 0].max() - x0) / 0.001) + 1, int((y1 - sl[:, 1].min()) / 0.001) + 1
    grid = [[' '] * cols for _ in range(rows)]
    for px, py, _pz in sl:
        grid[int((y1 - py) / 0.001)][int((px - x0) / 0.001)] = '#'
    for r, row in enumerate(grid):
        print(f'  y {y1 - r * 0.001:7.4f} |' + ''.join(row))
    print(f'  x từ {x0:.4f} (mỗi cột 1 mm)')
def scatter(name: str, pts: np.ndarray, ax_h: int, ax_v: int, box: tuple, px_per_mm: int = 12):
    """PNG of the vertices in `box` = (lo, hi) per axis, looking along the third axis: horizontal axis ax_h, vertical axis ax_v (up = larger); a 1 mm grid."""
    from PIL import Image, ImageDraw
    lo, hi = box
    sel = pts[np.all((pts >= lo) & (pts <= hi), axis=1)]
    w, h = int((hi[ax_h] - lo[ax_h]) * 1000 * px_per_mm), int((hi[ax_v] - lo[ax_v]) * 1000 * px_per_mm)
    img = Image.new('RGB', (w, h), (20, 20, 20))
    d = ImageDraw.Draw(img)
    for k in range(0, int((hi[ax_h] - lo[ax_h]) * 1000) + 1):
        d.line([(k * px_per_mm, 0), (k * px_per_mm, h)], fill=(60, 60, 60) if k % 5 else (110, 110, 110))
    for k in range(0, int((hi[ax_v] - lo[ax_v]) * 1000) + 1):
        d.line([(0, k * px_per_mm), (w, k * px_per_mm)], fill=(60, 60, 60) if k % 5 else (110, 110, 110))
    for p in sel:
        x, y = (p[ax_h] - lo[ax_h]) * 1000 * px_per_mm, h - (p[ax_v] - lo[ax_v]) * 1000 * px_per_mm
        d.rectangle((x - 1, y - 1, x + 1, y + 1), fill=(255, 220, 60))
    path = ROOT / 'shots' / f'm1014_{name}.png'
    path.parent.mkdir(exist_ok=True)
    img.save(path)
    print(f'{path.name}: {len(sel)} đỉnh, ô lưới 1 mm, gốc ({lo[ax_h]:.4f}, {lo[ax_v]:.4f}), 12 px / mm')


# the rear sight seen from behind (x right, y up) and from the side (z forward, y up); the front sight likewise
scatter('rear_back', body, 0, 1, (np.array([0.0, -0.285, -0.40]), np.array([0.045, -0.240, -0.28])))
scatter('rear_side', body, 2, 1, (np.array([0.0, -0.285, -0.42]), np.array([0.045, -0.240, -0.25])), 8)
scatter('front_back', body, 0, 1, (np.array([0.0, -0.285, 0.18]), np.array([0.045, -0.240, 0.28])))
scatter('front_side', body, 2, 1, (np.array([0.0, -0.285, 0.15]), np.array([0.045, -0.240, 0.29])), 8)
print(f'\nhiện tại: ads_sights={gun.ads_sights}, muzzle={gun.muzzle}, hip_offset={gun.hip_offset}, eye_joint={gun.eye_joint}')
sys.stdout.flush()
os._exit(0)                                       # the window is still open: a normal interpreter shutdown crashed natively now and then
