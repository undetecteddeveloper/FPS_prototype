---
name: pyinstaller-packaging
description: Packaging this Ursina-Panda3D game as a Windows exe folder + zip with PyInstaller 6 (tools/build/build_exe.py) - onedir with contents_directory '.', collecting Panda's DLLs / plugins / Config.prc, the panda3d-gltf entry point, why gltf_patch needs the gltf .py sources shipped, which assets go in, the light-bake key check, how to test a build like a friend's machine. Use when touching tools/build/build_exe.py, requirements-build.txt, adding a package / asset folder the game reads at run time, or when a packaged build fails to start.
---

# Packaging the game as an exe (learned 2026-11-07, G15)

Versions: PyInstaller 6.16.0 + hooks-contrib 2026.9, Python 3.13.17, Panda3D 1.10.16, Ursina 8.3.0, panda3d-gltf 1.3.0.

## Choices
- onedir + zip, NOT onefile: onefile unpacks ~190 MB to %TEMP% at every start (5-15 s) and is flagged by Defender / SmartScreen more often.
- `--contents-directory .`: everything sits next to the exe, with the source layout (`<dist>\fps\app.pyc`), so `ROOT = Path(__file__).parent.parent`
  in fps/app.py and `SHADER_DIR` in fps/game/shaders.py resolve to the folder exactly as from source. No `sys.frozen` code in the game.
- `--windowed` for the shipped build (sys.stdout / sys.stderr are None: `print` is a no-op, `print(file=sys.stderr)` too; an unhandled exception shows
  PyInstaller's traceback dialog). `--console` variant for testing: Panda warnings + Ursina prints visible.
- The folder must be writable: logs\crash.log, user_*.json, a re-bake of assets\maps\pool are written next to the exe.

## What has to be collected (and why)
- `--collect-all panda3d`: DLLs, plugins (`libpandagl`, `libp3openal_audio`) and `panda3d\etc\Config.prc` (it names `load-display pandagl` and
  `audio-library-name`; without it: "No graphics pipe is available"). Lands at `<dist>\panda3d\etc\Config.prc` and is found there.
- `--collect-data ursina --collect-submodules ursina`: Ursina's textures / fonts / icon (`ursina\textures\ursina.ico` is the window icon).
- `--copy-metadata panda3d-gltf --collect-submodules gltf`: Panda finds the .glb loader through the package's entry points (dist-info metadata).
- **The gltf package's .py SOURCES** (copied by build_exe.py into `<dist>\gltf\`): `gltf_patch._make_build_animation_skeleton` calls
  `inspect.getsource` on a panda3d-gltf method and rewrites it. Bytecode only -> `OSError: could not get source code` at import (first build failed
  exactly so). PyInstaller 6's frozen importer serves `get_source` from a .py next to the module.
- numpy is picked up from the lazy import in `PoolHall.bake_light` (needed only if the bake key mismatches on the friend's machine).
- Excluded: pytest, tkinter, IPython, matplotlib, pygltflib (tools only).
- Harmless build noise: SyntaxWarning "invalid escape sequence" from f-strings with `\` in foley.py / ursina, the Blender message from Ursina.

## Assets
- Shipped: every `GUNS[*].glb`, assets/shaders, assets/maps/pool (baked light + reflection, tracked in git), assets/sounds minus `source/`,
  `candidates/` and the unused Tranquil file; CREDITS.txt, tools/build/HUONG_DAN.txt (controls, requirements, what to send back on a crash).
- Not shipped: assets/review, user_*.json, logs (the script refuses if they show up in the folder).
- Bake check before packing: `bake_key(MapData(), GameParams().look)` and `reflect_key(...)` must equal assets/maps/pool/meta.json, else a friend's
  first start bakes ~60 s. Fix: run the game once with `--defaults --rebake`, rebuild.
- Licences: CREDITS.txt marks several files "CHƯA RÕ" (Glock model, M4 shot, ambience, conditional sound pack). Sending the zip = distributing them:
  the user verifies before sending.

## Testing a build like a friend's machine
1. Unzip to a scratch folder whose path has spaces, outside the project.
2. PATH = `C:\Windows\System32;C:\Windows` only, no PYTHONPATH / VIRTUAL_ENV; run with working directory != exe folder.
3. `FPS_prototype.exe --window --size 1280x720 --quit-after 10` -> exit 0, `logs\crash.log` header next to the exe, lightmap.png hash unchanged
   (no re-bake); also a run with no arguments (borderless fullscreen, screeninfo path). Screenshot once to see the room and the gun.
4. Not tested here: another GPU vendor, a machine without the VC++ runtime (PyInstaller ships the vcruntime DLLs Python needs), Windows 10.
Sizes (G15): folder 192 MB, zip 88 MB, build ~90 s.
