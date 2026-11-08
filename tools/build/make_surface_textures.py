"""Builds the procedural surface textures into assets/textures/ (numpy; run when the look changes, commit the PNGs: the game does not need numpy).

Run: .venv\\Scripts\\python.exe -X utf8 tools\\build\\make_surface_textures.py [--only holes,tiles] [--preview DIR]
  holes  -> bullet_hole_color.png (RGBA atlas 2 x 2) + bullet_hole_relief.png (R height, G / B normal x / y)
  tiles  -> tile_floor_* (2 x 2 tiles of 30 cm) and tile_wall_* (4 x 4 mosaic tiles of 10 cm; the pool basin uses it too): *_color.png (RGB, the tile colour MULTIPLIER / TILE_GAIN)
            + *_relief.png (R height, G / B normal x / y)
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


TILE_GAIN = 1.25          # the colour PNGs hold colour / TILE_GAIN (a tile face is ~1.0 and 8 bits stop at 1.0); the shaders multiply it back (room.frag, basin_common.glsl)
TILE_SPECS = {
    'floor': dict(n=512, tiles=2, tile_m=0.30, grout=0.035, seed=21, depth_m=st.TILE_DEPTH_FLOOR),
    'wall': dict(n=512, tiles=4, tile_m=0.10, grout=0.05, seed=22, depth_m=st.TILE_DEPTH_WALL),
}


def build_tiles(preview: Path):
    for kind, spec in TILE_SPECS.items():
        colour, height, nxy = st.tile_texture(kind=kind, **spec)
        rgb = st.to_u8(colour / TILE_GAIN)
        save(f'tile_{kind}_color.png', rgb)
        save(f'tile_{kind}_relief.png', st.pack_relief(height, nxy))
        lum = (colour * np.array([0.2126, 0.7152, 0.0722])).sum(axis=2)
        print(f'  {kind}: độ sáng trung bình {lum.mean():.3f} (nhân màu gạch; bản vẽ bằng công thức cũ ~0,914), mạch vữa {(height < 0.3).mean() * 100:.1f}% diện tích')
        if preview:
            albedo = np.array([0.80, 0.75, 0.64])
            tile = np.clip(colour * albedo, 0, 1)
            sheet = np.tile(tile, (2, 2, 1))
            Image.fromarray((sheet * 255).astype(np.uint8), 'RGB').save(preview / f'tile_{kind}_color.png')
            Image.fromarray((np.tile(height, (2, 2)) * 255).astype(np.uint8), 'L').save(preview / f'tile_{kind}_height.png')
            # a crude look with a raking light from the left: n . l with the relief normals, to judge the depth
            light = np.array([0.7, 0.2, 0.68])
            nz = np.sqrt(np.clip(1.0 - nxy[..., 0] ** 2 - nxy[..., 1] ** 2, 0, 1))
            shade = np.clip(nxy[..., 0] * light[0] + nxy[..., 1] * light[1] + nz * light[2], 0, 1)
            Image.fromarray((np.tile(shade * tile.mean(axis=2) * 1.3, (2, 2)).clip(0, 1) * 255).astype(np.uint8), 'L').save(preview / f'tile_{kind}_raking.png')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='holes,tiles')
    ap.add_argument('--preview', default='')
    args = ap.parse_args()
    only = set(filter(None, args.only.split(',')))
    preview = Path(args.preview) if args.preview else None
    if preview:
        preview.mkdir(parents=True, exist_ok=True)
    if 'holes' in only:
        build_holes(preview)
    if 'tiles' in only:
        build_tiles(preview)


if __name__ == '__main__':
    main()
