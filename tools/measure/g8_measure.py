"""G8: measures the Glock's sights and muzzle from the model vertices (camera space, ready pose, hip_offset NOT applied) and prints the values to paste
into GLOCK (ads_sights, muzzle). Same method as g4_ads_align.py / g5_muzzle_align.py, for the Glock slide (node Slide_Glock_D_0-parent).

  rear sight : top vertices of the rear 3.5 cm of the slide; point = centre of their box, in the middle of the notch (the blades are 2.3 mm taller than the notch floor: measured 7/11/2026, see GLOCK in weapon_data.py)
  front sight: top vertices of the front 3.5 cm of the slide; point = centre x, highest vertex
  muzzle     : the vertices of the slide front face; point = centre of their box

Run:  .venv\Scripts\python.exe -X utf8 tools\measure\g8_measure.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import GeomVertexReader  # noqa: E402
from ursina import mouse  # noqa: E402

from fps.core.sway import ads_target_for  # noqa: E402

NOTCH_BELOW_TOP = 0.00115        # m: the aiming point of the rear sight sits this far under the top of the blades = the middle of the 2.3 mm deep notch (0.0035 here hid the front sight behind the slide)

game = create_game(vsync=False, draw=False, sound=False, effects=False, look=False, gun='glock')
mouse.locked = False
vm, gun = game.viewmodel, game.params.gun
pts = []
for geom_np in vm.actor.find('**/Slide_Glock_D_0-parent').find_all_matches('**/+GeomNode'):
    mat = geom_np.get_mat(vm.cam_np)
    node = geom_np.node()
    for i in range(node.get_num_geoms()):
        reader = GeomVertexReader(node.get_geom(i).get_vertex_data(), 'vertex')
        while not reader.is_at_end():
            p = mat.xform_point(reader.get_data3())
            pts.append((float(p[0]), float(p[1]), float(p[2])))
zmin, zmax = min(p[2] for p in pts), max(p[2] for p in pts)
ymax = max(p[1] for p in pts)
print(f'đỉnh slide: {len(pts)}; z (tới trước) {zmin:.4f}..{zmax:.4f} ({(zmax - zmin) * 100:.1f} cm), y cao nhất {ymax:.4f}')


def box(sel):
    lo = [min(p[i] for p in sel) for i in range(3)]
    hi = [max(p[i] for p in sel) for i in range(3)]
    return lo, hi


def top_of(sel_z):
    sl = [p for p in pts if sel_z(p[2])]
    top = max(p[1] for p in sl)
    return [p for p in sl if p[1] >= top - 0.004], top


rear_sel, rear_top = top_of(lambda z: z <= zmin + 0.035)
front_sel, front_top = top_of(lambda z: z >= zmax - 0.035)
print(f'cao nhất: đuôi {rear_top:.4f}, đầu {front_top:.4f}')
lo, hi = box(rear_sel)
rear = ((lo[0] + hi[0]) / 2, hi[1] - NOTCH_BELOW_TOP, (lo[2] + hi[2]) / 2)
lo, hi = box(front_sel)
front = ((lo[0] + hi[0]) / 2, hi[1], (lo[2] + hi[2]) / 2)
face = [p for p in pts if p[2] >= zmax - 0.004]
lo, hi = box(face)
muzzle = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2])
r = lambda t: tuple(round(v, 4) for v in t)
print(f'ads_sights=({r(rear)}, {r(front)}),')
print(f'muzzle={r(muzzle)},')
print(f'hiện tại: ads_sights={gun.ads_sights}, muzzle={gun.muzzle}, hip_offset={gun.hip_offset}')
if gun.ads_sights:
    print(f'tư thế ADS đang dùng: {tuple(round(v, 4) for v in ads_target_for(gun))}')
sys.exit(0)
