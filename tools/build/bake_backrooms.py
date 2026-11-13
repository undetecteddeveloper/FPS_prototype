r"""G18 / G19: bake the light of every stage of the run (no window needed): stage 0 = the pool hall (sun + its stair corridor panels) into assets/maps/pool/,
stages 1-5 = the Backrooms floors into assets/maps/backrooms/floorN/ (lightmap.png, ambient.json, meta.json).

The game bakes a stale stage by itself when the run starts, but that takes a minute or more per stage: run this after changing a floor (`weapon_data.BACKROOMS`),
the pool hall or the bake code, then commit the files. Each stage's water reflection is captured by the game the first time it builds that stage (two frames).

Run: .venv\Scripts\python.exe -X utf8 tools\build\bake_backrooms.py [--stage N] [--force]
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

from fps.core.backrooms import build_stage, floor_key, stage_count  # noqa: E402
from fps.game.backrooms import stage_dir  # noqa: E402
from fps.game.pool import bake_map, rail_probes, store_bake  # noqa: E402
from fps.weapon_data import LookData  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', type=int, default=-1, help='chỉ nướng màn này (0 = phòng hồ, 1..5 = tầng)')
    ap.add_argument('--force', action='store_true', help='nướng cả màn còn mới')
    args = ap.parse_args()
    look = LookData()
    for k in range(stage_count()):
        if args.stage >= 0 and k != args.stage:
            continue
        fm = build_stage(k)
        key = floor_key(fm, look)
        folder = ROOT / stage_dir(k)
        name = 'phòng hồ' if k == 0 else f'tầng {k} ({fm.spec.name})'
        try:
            stored = json.loads((folder / 'meta.json').read_text(encoding='utf-8')).get('key')
        except (OSError, ValueError):
            stored = None
        if stored == key and not args.force:
            print(f'{name}: còn mới, bỏ qua')
            continue
        t0 = time.time()
        last = [0.0]

        def progress(done, total):
            if time.time() - last[0] > 10.0:
                last[0] = time.time()
                print(f'   {done}/{total}', flush=True)
        res = bake_map(fm, look, rail_probes(fm.data), progress)
        store_bake(folder, key, res)
        print(f'{name}: {len(fm.exposed_faces())} mặt, {res.stats["rays"]:,} tia, ảnh {res.rgb.shape[1]}x{res.rgb.shape[0]}, {time.time() - t0:.1f} s', flush=True)


if __name__ == '__main__':
    main()
