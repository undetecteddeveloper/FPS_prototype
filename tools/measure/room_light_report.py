r"""G19: median irradiance per ROOM from the stored lightmaps (no window, no game: numpy + Pillow). Independent of the camera's auto-exposure, which makes screenshots
taken right after a teleport useless for comparing rooms.

Reference: the old floor-1 hall of G18, the lighting the user called best (12/11/2026): median irradiance 0.28. A 'lit' room should land near it, 'dim' lower, 'dark' /
'red' much lower. The panels themselves (glowing boxes) are left out.

Run: .venv\Scripts\python.exe -X utf8 tools\measure\room_light_report.py [--stage N]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from fps.core.backrooms import build_stage, stage_count  # noqa: E402
from fps.core.poolmap import UV_AXES, pack_atlas  # noqa: E402
from fps.game.backrooms import stage_dir  # noqa: E402
from fps.game.pool import rail_probes  # noqa: E402

REFERENCE = 0.28
BANDS = {'lit': (0.22, 0.34), 'dim': (0.08, 0.28), 'dark': (0.05, 0.16), 'red': (0.05, 0.20), 'cabin': (0.10, 0.50), 'sun': (0.0, 9.0)}


def room_of(fm, p):
    for name, lo, hi, kind in fm.airs:
        if all(lo[i] - 0.06 <= p[i] <= hi[i] + 0.06 for i in range(3)):
            return name, kind
    return 'other', 'other'


def report(k: int):
    fm = build_stage(k)
    d = fm.data
    faces = fm.exposed_faces()
    atlas = pack_atlas(faces, d.texel, n_probes=len(rail_probes(d)))
    img = np.asarray(Image.open(ROOT / stage_dir(k) / 'lightmap.png').convert('RGB')).astype(float) / 255.0
    grey = (img ** 2).mean(axis=2) * d.lightmap_max
    per = {}
    for f, pl in zip(faces, atlas.faces):
        if fm.boxes[f.box].emit is not None:
            continue
        ua, va = UV_AXES[f.axis]
        c = f.point((f.u0 + f.u1) / 2.0, (f.v0 + f.v1) / 2.0)
        c = tuple(c[i] + (0.05 * f.sign if i == f.axis else 0.0) for i in range(3))
        name, kind = room_of(fm, c)
        per.setdefault((name, kind), []).append(grey[pl.y:pl.y + pl.h, pl.x:pl.x + pl.w].ravel())
    rows = []
    for (name, kind), parts in per.items():
        v = np.concatenate(parts)
        rows.append((name, kind, float(np.median(v)), float(np.percentile(v, 90)), v.size))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', type=int, default=-1)
    args = ap.parse_args()
    bad = 0
    print(f'mốc tầng 1 cũ (G18): trung vị {REFERENCE}')
    for k in range(stage_count()):
        if args.stage >= 0 and k != args.stage:
            continue
        for name, kind, med, p90, n in sorted(report(k), key=lambda r: r[0]):
            lo, hi = BANDS.get(kind, (0.0, 9.0))
            ok = lo <= med <= hi
            bad += not ok
            print(f'  tầng {k} {name:8s} {kind:6s} trung vị {med:5.2f}  p90 {p90:5.2f}  ({n:6d} texel)  dải {lo:.2f}-{hi:.2f}  {"ok" if ok else "NGOÀI DẢI"}')
    print(f'KẾT QUẢ: {"QUA" if not bad else f"{bad} phòng ngoài dải"}')
    return bad


if __name__ == '__main__':
    sys.exit(main())
