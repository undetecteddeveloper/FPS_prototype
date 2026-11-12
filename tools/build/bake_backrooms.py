r"""G18: bake the light of the Backrooms floors (no window needed) into assets/maps/backrooms/floorN/ (lightmap.png, ambient.json, meta.json).

The game bakes a stale floor by itself when the level starts, but that takes tens of seconds per floor: run this after changing a floor (`weapon_data.BACKROOMS`) or the bake code,
then commit the files. The water reflection of each floor is captured by the game the first time it builds that floor (two frames).

Run: .venv\Scripts\python.exe -X utf8 tools\build\bake_backrooms.py [--floor N] [--force]
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from fps.game import gltf_patch  # noqa: E402

gltf_patch.apply()

from fps.core.backrooms import build_floor, floor_key  # noqa: E402
from fps.game.backrooms import floor_dir  # noqa: E402
from fps.game.pool import bake_map, rail_probes, store_bake  # noqa: E402
from fps.weapon_data import BACKROOMS, LookData  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--floor', type=int, default=-1, help='chỉ nướng tầng này (0..4)')
    ap.add_argument('--force', action='store_true', help='nướng cả tầng còn mới')
    args = ap.parse_args()
    look = LookData()
    for k in range(len(BACKROOMS)):
        if args.floor >= 0 and k != args.floor:
            continue
        fm = build_floor(k)
        key = floor_key(fm, look)
        folder = ROOT / floor_dir(k)
        try:
            stored = json.loads((folder / 'meta.json').read_text(encoding='utf-8')).get('key')
        except (OSError, ValueError):
            stored = None
        if stored == key and not args.force:
            print(f'tầng {k + 1} ({fm.spec.name}): còn mới, bỏ qua')
            continue
        t0 = time.time()
        last = [0.0]

        def progress(done, total):
            if time.time() - last[0] > 5.0:
                last[0] = time.time()
                print(f'   {done}/{total}', flush=True)
        res = bake_map(fm, look, rail_probes(fm.data), progress)
        store_bake(folder, key, res)
        print(f'tầng {k + 1} ({fm.spec.name}): {len(fm.exposed_faces())} mặt, {res.stats["rays"]:,} tia, ảnh {res.rgb.shape[1]}x{res.rgb.shape[0]}, '
              f'{time.time() - t0:.1f} s', flush=True)


if __name__ == '__main__':
    main()
