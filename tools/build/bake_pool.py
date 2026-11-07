r"""G9: bake the pool hall's light again and capture the water's reflection again (assets\maps\pool\lightmap.png, reflect.png, meta.json).

The game does this by itself when the stored hash differs from the numbers (MapData, the sun in LookData); run this to force it, e.g. after editing the baker, or to refresh the committed files.
It opens a small window (the reflection is rendered by the GPU).

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\build\bake_pool.py
Commit the three files with the numbers that produced them (use --defaults values: do not leave user_params.json edits in LookData / LensData when baking the files you commit).
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402

t0 = time.time()
game = create_game(vsync=False, size=(640, 360), sound=False, draw=False, map_name='pool', rebake=True)
pool = game.pool
print(f'xong sau {time.time() - t0:.1f} s: {pool.triangles} tam giác, {pool.draw_calls} lần vẽ, ảnh ánh sáng {pool.atlas.width}x{pool.atlas.height}')
print(f'file: {pool.dir}')
