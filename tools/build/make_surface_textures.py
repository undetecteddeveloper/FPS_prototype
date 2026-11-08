"""Builds the procedural surface textures into assets/textures/ (numpy; run when the look changes, commit the PNGs: the game does not need numpy).

Run: .venv\\Scripts\\python.exe -X utf8 tools\\build\\make_surface_textures.py [--only holes,tiles] [--preview DIR]
  holes  -> bullet_hole_color.png (RGBA atlas 2 x 2) + bullet_hole_relief.png (R height, G / B normal x / y)
--preview DIR also writes contact sheets there to look at (colour over a tile-like backdrop, relief height).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'build'))
sys.stdout.reconfigure(encoding='utf-8')

import surface_textures as st  # noqa: E402

OUT = ROOT / 'assets' / 'textures'


def save(name: str, arr: np.ndarray):
    OUT.mkdir(parents=True, exist_ok=True)
    mode = 'RGBA' if arr.shape[2] == 4 else 'RGB'
    Image.fromarray(arr, mode).save(OUT / name, optimize=True)
    print(f'đã ghi assets/textures/{name} {arr.shape[1]}x{arr.shape[0]} ({(OUT / name).stat().st_size / 1024:.0f} KB)')


def build_holes(preview: Path):
    color, relief = st.bullet_hole_atlas()
    save('bullet_hole_color.png', color)
    save('bullet_hole_relief.png', relief)
    if preview:
        back = np.zeros(color.shape[:2] + (3,), np.float64)
        back[...] = (0.93, 0.90, 0.82)                       # a glazed ivory wall tile
        a = color[..., 3:4] / 255.0
        comp = back * (1.0 - a) + (color[..., :3] / 255.0) * a
        Image.fromarray((comp * 255).astype(np.uint8), 'RGB').save(preview / 'hole_color_on_tile.png')
        Image.fromarray(relief[..., 0], 'L').save(preview / 'hole_height.png')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='holes')
    ap.add_argument('--preview', default='')
    args = ap.parse_args()
    only = set(filter(None, args.only.split(',')))
    preview = Path(args.preview) if args.preview else None
    if preview:
        preview.mkdir(parents=True, exist_ok=True)
    if 'holes' in only:
        build_holes(preview)


if __name__ == '__main__':
    main()
