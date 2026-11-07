---
name: gpu-perf-intel
description: Measuring and cutting GPU / CPU frame cost in this Ursina-Panda3D game on Intel integrated graphics (Iris Xe here, UHD 620 as the weak target) - OpenGL timestamp queries through ctypes inside Panda draw callbacks, the measurement artefacts (DWM hold, vsync down-clocking, driver blocking the CPU, screenshot readback), the weak-machine estimate, render scale through FilterManager, compile-time shader variants (lite / view / dry builds) and why they must be DRAWN once at start-up, Ursina's hidden full-screen overlay and M_dual transparency, Intel GLSL / render-target rules. Use before any performance work, when a scene is slow, when adding a full-screen pass, a quality level or a shader variant, or when touching tools/measure/gpu_timer.py, weak_pc.py, g8_perf.py, fps/game/lens.py buffer sizes, Game.warm_shader_builds.
---

# GPU / CPU performance on Intel iGPU (researched + measured 2026-11-07, G13; Panda3D 1.10.16, Ursina 8.3.0, Python 3.13)

Project notes with the numbers: `docs/notes/performance.md`. Status words: verified-in-project (experiment named) / unverified.

## 1. Measure first: tools in this project
- `tools/measure/gpu_timer.py`: every DisplayRegion gets `set_draw_callback(cb)`; cb does `glQueryCounter(q0, GL_TIMESTAMP)`, `cbdata.upcall()`, `glQueryCounter(q1)`.
  Read results >= 6 frames later, only when `GL_QUERY_RESULT_AVAILABLE` (reading early stalls). GL functions via `ctypes.WinDLL('opengl32').wglGetProcAddress`
  (returns 0/1/2/3/-1 on failure); the GL context is current inside a draw callback (single-threaded pipeline). Labels `<output>#<dr index>:<camera name>`.
  Re-hook every frame: outputs made later (lens rebuilt on an F2 change) appear in the engine list one frame late; frames missing passes are dropped by g8_perf.
  Sources: https://wikis.khronos.org/opengl/GlQueryCounter ; https://developer.download.nvidia.com/opengl/specs/GL_ARB_timer_query.txt ;
  https://discourse.panda3d.org/t/panda-draw-callbacks/5460 (DR callback must call `cbdata.upcall()`). high. verified-in-project (g8_perf --passes).
- CPU time = Python tasks before igLoop (task sort -1000 .. 49) + cull callbacks + draw submission; flip excluded. Measure it in a 640x360 window.
- `tools/measure/weak_pc.py`: GPU run at screen size (borderless, vsync off) + CPU run at 640x360, weak frame = max(4 x GPU, 2 x CPU). Pass: avg >= 60, p99 -> >= 50 FPS.
  Ratio Iris Xe 96EU / UHD 620: Time Spy 1282 vs 361 (~3.5x), G3D 2593 vs 1040 (~2.5x): https://nanoreview.net/ru/gpu-compare/intel-uhd-graphics-620-vs-intel-iris-xe-graphics-g7-96eu ,
  https://www.videocardbenchmark.net/compare/Intel-Iris-Xe-vs-Intel-UHD-Graphics-620/4265vs3805 - medium. x4 is deliberately conservative (user chose it).
- A/B INSIDE ONE PROCESS (alternate two setups every 2 s, median per setup): absolute numbers drift +-20% run to run (heat, CPU/GPU sharing 15 W).
  Shader variants can be swapped live with `node.set_shader(Shader.make(...), prio)` built from `read_source` text edits. verified-in-project (scratch ab_*.py).
- "Same picture" proof: render the SAME frame twice in one process (engine.render_frame() x2, no task update in between) with new vs HEAD shaders
  (`git show HEAD:assets/shaders/...` into a folder, expand includes from there), compare pixels. Screenshots from two separate runs differ by head / zoom state.
  Panda paths: `PNMImage.read/write` need `Filename.from_os_specific` on Windows (a plain 'C:/...' string silently fails).

## 2. Measurement artefacts (verified-in-project 2026-11-07)
- vsync ON: CPU and GPU down-clock (frame capped at 60) -> pass times 2-3x larger. Measure costs with vsync OFF; judge real stutter with vsync ON (`g8_perf --vsync`).
- vsync OFF in a big window: ~5% of frames get a CONSTANT +10.5 ms inside the first pass, irregular, gone in a 480x270 window -> queued GPU held by Windows' scheduler / DWM.
- At full size the CPU time of draw submission includes the driver blocking on the full GPU queue (CPU p99 8-12 ms at 1080p vs 2.3 at 720p).
- Python GC was NOT a stutter source: 10 collections in 9 s, none gen2, max 2.4 ms. (`gc.freeze()` is the fix if it ever is: https://docs.python.org/3/library/gc.html#gc.freeze)
- `win.save_screenshot` costs ~340 ms (HEAD too): a tool that snaps right before a switch sees a huge "slow frame". Not a game regression.

## 3. Findings in this game (all verified-in-project, G13)
- Ursina `camera.overlay` (full-screen quad, color.clear, alpha-blended, under camera.ui) cost 1.6-3.3 ms at 1080p for nothing -> disabled in create_game.
- Ursina puts `TransparencyAttrib.M_dual` on every Entity's MODEL node (entity.py `self._model.setTransparency`): two passes + alpha test (no early-Z). Set it on `e.model`, not `e`.
- A full-screen sky sphere costs ~0.22 ms at 1440x810 even depth-tested LEQUAL behind everything (HiZ did not reject it; 'never' test = 0.02). Indoors: quads behind the window holes.
- Render scale: `FilterManager.sizes[i] = (mul, div, align)` + `resizeBuffers()` (buffers are BF_resizeable; re-applied on window-event). Below 100% the LENS PASS also runs at
  scale (`renderQuadInto(mul=scale)`) and `blit.frag` stretches to the window: lens 2.8 ms full-res -> 1.3 + 0.35 blit. Mip-based effects need lod + log2(scale).
  Anything using gl_FragCoord must get the BUFFER size (`underwater.glsl look_under2.zw`). The gun's region must go to `lens.scene_buffer` (buffers[0]), not buffers[-1].
- Uber-shader branches cost even when not taken (register pressure): compile-time variants with the flags as `false` saved 0.5-1 ms (water/basin/room POOL_LITE),
  0.54 ms (water VIEW_UNDER drops the basin-trace branch), 0.6 ms (lens LENS_DRY). Pick per frame in Python; switching = `set_shader`, no recompile.
- Uniform-bounded loops: an EMPTY 12-iteration loop over a uniform array cost 0.4-0.8 ms per frame (rings, lens drops). Pack live entries first + count, `break` early.
- Per-candidate early-out with exact bounds (sun_visible: skip a window whose box+soft edge misses) cut ~0.5 ms; one union box only 0.12 ms (union too big).
- Overdraw of alpha-blended particles dominates firing: M4 full-auto smoke ~2 ms at 1440x810 even with cheap ALU; moving per-puff math to the vertex shader saved 0.04-0.38 ms,
  drawing half the puffs (stable by seed, alpha 1-(1-a)^2) halved it. Fill-fade thresholds did not help (many medium puffs, not a few big ones).
- `Shader.prepare(gsg.get_prepared_objects())` is NOT enough: the Intel driver compiles at the first DRAW (50-150 ms frame). Draw every variant once at start-up
  (`Game.warm_shader_builds`: set each build, `engine.render_frame()`, restore). Also cache `load_glsl` by (name, defines, frag) so rebuilt passes reuse compiled shaders.

## 4. Intel GPU rules (Intel "Developer's Guide for Intel Processor Graphics", 5th gen, read 2026-11-07 via local PDF extract;
https://www.intel.com/content/dam/develop/external/us/en/documents/5th-gen-core-graphics-developer-guide-166010.pdf ; still valid in spirit for Gen9 / Xe, medium)
- Bandwidth is shared with the CPU and is usually the limit: 1 GB read+write per frame at 25 GB/s caps at 25 FPS (p.7). Fewer full-screen passes; fold post work into ONE pass (p.8).
- "Render scenes at a useful resolution, not necessarily full-screen, then upscale; render the UI separately at full resolution" (p.8). verified-in-project (75%: world x0.57).
- Discard alpha==0 pixels instead of blending them to no effect; trim particle quads (p.8).
- MSAA: 2x is native (Gen8+) and cheaper than 4x; prefer CMAA/FXAA (p.9).
- Avoid unneeded clears of colour targets fully overwritten anyway (p.9).
- Constants used for loop bounds / indexing: literal (compile-time) beats uniform; dynamic indexing of uniform arrays defeats push-constant preload (p.11).
- Register pressure: a heavy branch that is rarely taken still costs the whole shader (registers -> SIMD8 instead of SIMD16); split into a separate shader (p.12). verified-in-project (§3).
- Non-power-of-two mipmapped textures are inefficient (p.12). Our NPOT lens buffer mip generation measured only ~0.1 ms (inside the lens pass), not worth replacing.
- Sampler: smaller textures / formats, fewer taps; a 9 -> 1 tap PCF cut its segment 89% (https://www.intel.com/content/www/us/en/docs/gpa/cookbook/2023-1/optimize-sampler.html, high).
- Changing fixed-function states can force shader recompiles = hitches (p.13); this project switches quality by uniforms / prepared+drawn variants only.
