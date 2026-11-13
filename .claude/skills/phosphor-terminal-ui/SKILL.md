---
name: phosphor-terminal-ui
description: Green-phosphor military-terminal look (boot splash, CLI log, settings panel) in this Ursina/Panda3D project - phosphor colour values, brightness-level palette instead of many hues, CRT cues (glow, scanlines, flicker) kept cheap, real bodycam burn-in overlay facts (Axon watermark), and the layout rules that avoid sub-pixel misalignment (monospace cell grid, integer-pixel snapping, fixed-width fields). Use when touching fps/core/termui.py, fps/game/boot.py, fps/game/theme.py, fps/game/graphics_panel.py or adding any text-mode UI.
---

# Phosphor terminal UI (researched 2026-11-12, G20)

Decisions (user, 2026-11-12): splash = real loading log + fixed finale, green phosphor on black, English military terms. In-game UI = NO HUD; only the F2 graphics panel is restyled (same phosphor green), opened with Esc. F1 untouched.

## Colour (status: unverified unless marked)
- P1 phosphor green ~ `#33FF33` (525 nm); P24 `#66FF66`; P3 amber `#FFB000`. Source: community wavelength->hex table https://publish.obsidian.md/xybre/permalink/e397c38e-aa6f-45eb-831f-f02a3836abc4 (read 2026-11-12). Confidence: medium (derived estimate; the author notes several RGB conversion methods).
- Contrast for VDT text: 10:1 to 18:1 (FHWA human-factors review https://www.fhwa.dot.gov/publications/research/safety/03065/03.cfm, read 2026-11-12). Confidence: medium. Black background + full-green text is far above; the DIM level (labels, hints) still has to stay >= ~4.5:1 against the panel background.
- MIL-STD-1472 character-height / colour-coding tables were NOT reachable by search (only "visual displays shall be legible under all anticipated viewing conditions"; the standard says it has not had a thorough technical review since the late 1980s). Do not cite numbers from it.
- Design rule chosen here: ONE hue (green), meaning carried by BRIGHTNESS + SHAPE (marker bar, tick, brackets), not by extra hues. Amber `#FFB000` only for a warning / "restart needed", red `#FF3B30` only for the REC dot and errors. Reason: all-green UIs lose "changed vs default" if that is encoded by hue.

## Bodycam burn-in facts
- Axon Body 3: "Watermark: adds a permanent overlay with date, time, and camera serial number to the upper-right corner of videos" (https://www.axon.com/help/axon-body-3/cameras-and-sensors/body/settings.htm, read 2026-11-12). Confidence: high. Serial printed on the back of the camera. Serial string structure and the timestamp format are NOT documented in the sources found; a fan-made FiveM script claims ISO-8601 (unverified, low). The REC indicator is an LED, no on-screen description was found.
- So the in-game "bodycam" cues are our own design: red REC dot + elapsed time + a FICTIONAL unit / serial (never a real agency, brand or person).

## Layout rules (avoid subtle misalignment)
1. Work in a monospace CELL GRID: column width `cw` and row height `lh` are integer pixels measured from the real font at the real window height; every x / y is `col * cw`, `row * lh` from an integer-pixel origin.
2. Right-aligned fields are computed (`x = right - len(text) * cw`), never eyeballed; numbers use fixed-width fields (`f'{v:>5}'`) so digits changing never shifts a neighbour.
3. Snap every position to whole pixels: `round(v * H) / H` (UI height = 1.0 in Ursina). A text origin at a fractional pixel gives uneven stroke weight.
4. Same left margin, same right margin, same row pitch in every panel; margins are multiples of `cw`.
5. Verify with a screenshot, not by reading numbers: tools/measure/ui_check.py (G20) measures real glyph pixels.

## CRT cues, cheap
- Glow = a second copy of the text 1 px away at ~25% alpha (Panda text cannot blur).
- Scanlines + vignette = ONE full-screen quad with a small tiled texture, alpha ~0.12; only while the splash is up (a full-screen alpha quad costs 1.6-3.3 ms GPU at 1080p on this Iris Xe, see gpu-perf-intel).
- Flicker amplitude <= 3% of brightness, slow (a few Hz); never flash the whole screen.

## Verified in this project (G20, 2026-11-12; status `verified-in-project`)
Experiments: scratch probes `font_probe` / `probe3` (hidden Panda buffer, screenshot + numpy), then `tools/measure/ui_check.py` (65 checks) and `tests/test_termui.py` (68).
- Consolas through Ursina `Text`: glyph advance = **0.55 em** (`Text.width` of 20 'M' = 0.275 at ANY scale: it is unscaled; real width = width x scale). With `Grid.text_scale` the measured stem-to-stem step is exactly `cw` (10.000 px at 720p; 15 / 11 px at 1080p / 768p, +-0.05 px from anti-aliasing).
- Capital letters' vertical centre sits **0.45 em** below the top of the Text when `origin=(-0.5, 0.5)` (measured 0.440 / 0.450 / 0.458 em at 720p / 768p / 1080p). Left bearing of 'H' ~1-2 px.
- Consolas HAS: `█ ░ ▒ ▓ ● ◄ ► ↑ ↓ ← → · • ° ± ×` and the Vietnamese letters (Pillow glyph test). Box-drawing `─ │ ┌ ┐` render misplaced / clipped through Ursina: draw rules as quads.
- UI built before Ursina's first frame needs `window.update_aspect_ratio()` first (else text ~20x too big; the UI lens only gets its size from the first-frame event).
- A frame drawn in the middle of `Game.__init__` (to animate the splash) also draws the half-built 3D scene: Panda raises `Shader input look_camera_pos is not present`. Fix: `base.render.hide()` around `graphicsEngine.render_frame()`.
- Creating ~40 `Text` rows costs ~0.8 s (first glyphs of a font page): build the panel while loading, not at the first key press.
- Hidden-buffer frames are ~1 ms: wait for animations in wall-clock time, never in frame counts; a PNG decode + numpy analysis inside an `update` shows up as a 0.9 s frame in the NEXT dt.
- Screenshots of the hidden buffer show UI exactly as drawn; layout checks on them are reliable (corners to the pixel, bar +-0 px, cap centre +-0.5 px at 720p / +-1.0 px at 1080p).

## Pitfalls (carried from this project)
- Ursina `Text` reads `<` as markup start: use other glyphs for arrows / brackets, or escape.
- Setting a Text colour rebuilds its glyphs (~0.3 ms): set only on change.
- Entities with no `update` / `input` must be removed from `scene.entities` (see graphics_panel.py) or Ursina walks them every frame.
