r"""Build the Windows demo folder + zip to send to friends (G15, docs/sessions/G15.md).

Run:  .venv\Scripts\python.exe -X utf8 tools\build\build_exe.py [--console] [--no-zip]
      (needs PyInstaller: .venv\Scripts\pip install -r requirements-build.txt)

Output: build\FPS_prototype\FPS_prototype.exe (one folder, every file next to the exe) and build\FPS_prototype_demo_<date>.zip.
`contents_directory='.'` keeps the source layout inside the folder (fps\app.pyc sits in <folder>\fps), so `ROOT` in fps/app.py and SHADER_DIR in
fps/game/shaders.py resolve to the folder exactly as they resolve to the project when run from source: no frozen-only path code in the game.
The folder must stay writable (logs\crash.log, user_params.json, user_graphics.json and a re-bake of assets\maps\pool are written next to the exe).

Checks before packing: the stored light bake and reflection match the DEFAULT numbers (a friend has no user_params.json; a mismatch would make the first
start bake for ~60 s), and every gun's glb exists. `--console` builds a variant with a console window (prints, Panda warnings) for testing.
"""
import argparse
import datetime
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

NAME = 'FPS_prototype'
BUILD = ROOT / 'build'
README = ROOT / 'tools' / 'build' / 'HUONG_DAN.txt'
# what the game reads at run time (assets/review and the sound sources are not shipped)
ASSET_DIRS = ('assets/shaders', 'assets/maps/pool', 'assets/maps/backrooms', 'assets/sounds', 'assets/textures')     # G18: + the Backrooms floors (sounds/enemy is inside sounds)
SKIP = ('assets/sounds/source', 'assets/sounds/candidates', 'assets/sounds/Tranquil_indoor_swim_wide')   # path prefixes left out (sources, an unused file)
EXCLUDE_MODULES = ('pytest', '_pytest', 'tkinter', 'IPython', 'matplotlib', 'pygltflib')


def check_bake() -> list:
    """Problems that would make a friend's first start slow or broken (empty = fine). G19: the run has 6 stages (the pool hall + 5 Backrooms floors): each needs its stored
    lightmap AND reflection to match the code, or the game bakes for a minute at start-up / freezes ~6 s at a floor swap to capture the reflection."""
    import json
    from fps.core.backrooms import build_stage, floor_key, stage_count
    from fps.core.poolmap import reflect_key
    from fps.game.backrooms import stage_dir
    from fps.weapon_data import GUNS, GameParams
    problems = []
    p = GameParams()
    for k in range(stage_count()):
        fm = build_stage(k)
        folder = ROOT / stage_dir(k)
        try:
            meta = json.loads((folder / 'meta.json').read_text(encoding='utf-8'))
        except (OSError, ValueError) as e:
            problems.append(f'không đọc được {folder / "meta.json"}: {e}')
            continue
        if meta.get('key') != floor_key(fm, p.look):
            problems.append(f'màn {k}: ánh sáng nướng không khớp mã (chạy tools/build/bake_backrooms.py rồi dựng lại)')
        if meta.get('reflect') != reflect_key(fm.data, p.look, p.lens):
            problems.append(f'màn {k}: ảnh phản chiếu không khớp mã (chạy tools/measure/backrooms_check.py một lần rồi dựng lại)')
        for f in ('lightmap.png', 'reflect.png', 'ambient.json'):
            if not (folder / f).exists():
                problems.append(f'thiếu {stage_dir(k)}/{f}')
    for key, gun in GUNS.items():
        if not (ROOT / gun.glb).exists():
            problems.append(f'thiếu model súng {key}: {gun.glb}')
    return problems


def run_pyinstaller(console: bool):
    import PyInstaller.__main__
    import ursina
    icon = Path(ursina.__file__).parent / 'textures' / 'ursina.ico'
    args = [str(ROOT / 'main.py'), '--noconfirm', '--clean', '--onedir', '--name', NAME,
            '--contents-directory', '.',
            '--distpath', str(BUILD), '--workpath', str(BUILD / 'work'), '--specpath', str(BUILD / 'work'),
            '--icon', str(icon),
            '--collect-all', 'panda3d',              # DLLs + plugins (pandagl, p3openal_audio) + etc/Config.prc
            '--collect-data', 'ursina', '--collect-submodules', 'ursina',
            '--collect-submodules', 'gltf', '--copy-metadata', 'panda3d-gltf',     # the .glb loader is registered through package entry points
            '--console' if console else '--windowed']
    for m in EXCLUDE_MODULES:
        args += ['--exclude-module', m]
    PyInstaller.__main__.run(args)


def copy_assets(dist: Path):
    from fps.weapon_data import GUNS
    files = [ROOT / gun.glb for gun in GUNS.values()]
    for d in ASSET_DIRS:
        files += [f for f in (ROOT / d).rglob('*') if f.is_file()]
    n = size = 0
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if rel.startswith(SKIP) or '__pycache__' in rel:
            continue
        out = dist / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
        n += 1
        size += f.stat().st_size
    # fps/game/gltf_patch.py rewrites a function of panda3d-gltf from its SOURCE (inspect.getsource); a frozen module only has bytecode, so the
    # package's .py files ship next to it (PyInstaller's importer serves get_source from them)
    import gltf
    src = Path(gltf.__file__).parent
    for f in src.glob('*.py'):
        (dist / 'gltf').mkdir(exist_ok=True)
        shutil.copy2(f, dist / 'gltf' / f.name)
    shutil.copy2(ROOT / 'CREDITS.txt', dist / 'CREDITS.txt')
    shutil.copy2(README, dist / 'HUONG_DAN.txt')
    print(f'[dựng] đã chép {n} file tài nguyên ({size / 2 ** 20:.1f} MB)')


def make_zip(dist: Path) -> Path:
    out = BUILD / f'{NAME}_demo_{datetime.date.today():%Y%m%d}.zip'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(dist.rglob('*')):
            if f.is_file():
                z.write(f, Path(NAME) / f.relative_to(dist))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--console', action='store_true', help='bản có cửa sổ console (để kiểm, thấy chữ in ra)')
    ap.add_argument('--no-zip', action='store_true')
    args = ap.parse_args()
    problems = check_bake()
    if problems:
        for p in problems:
            print(f'[dựng] LỖI: {p}')
        return 1
    dist = BUILD / NAME
    if dist.exists():
        shutil.rmtree(dist)                  # build\ is a generated folder (gitignored): always rebuilt from scratch
    run_pyinstaller(args.console)
    exe = dist / f'{NAME}.exe'
    if not exe.exists():
        print(f'[dựng] LỖI: PyInstaller không tạo ra {exe}')
        return 1
    copy_assets(dist)
    stray = [p.name for p in dist.glob('user_*.json')] + [p.name for p in dist.glob('logs')]
    if stray:
        print(f'[dựng] LỖI: có file của máy này trong bản dựng: {stray}')
        return 1
    total = sum(f.stat().st_size for f in dist.rglob('*') if f.is_file())
    print(f'[dựng] {exe} ({total / 2 ** 20:.0f} MB cả thư mục)')
    if not args.no_zip:
        z = make_zip(dist)
        print(f'[dựng] zip: {z} ({z.stat().st_size / 2 ** 20:.0f} MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
