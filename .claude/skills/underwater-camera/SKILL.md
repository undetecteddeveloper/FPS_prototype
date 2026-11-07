---
name: underwater-camera
description: Camera UNDER and AT the water surface in this Ursina-Panda3D pool project - underwater optics (Snell's window 97 deg, total internal reflection, per-colour absorption / turbid fog), the action-camera (GoPro / bodycam) underwater look (magnification, edge warp), the half-in-half-out split frame (waterline on the lens port, meniscus), the wet lens after surfacing (water film sliding down + droplets that refract like small lenses, drying), muffled audio (lowpass in Panda: FMOD only). Use when touching core/underwater.py, core/wetlens.py, underwater.glsl, basin.frag, lens.frag water parts, or the underwater audio. Builds on pool-water-sim and interior-water-light.
---

# Underwater camera, split frame, wet lens (researched 2026-11-07, G12)

Tool versions: Panda3D 1.10.16 (pip wheel ships p3openal_audio AND p3fmod_audio + fmodex64.dll), Ursina 8.3, Intel Iris-Xe class GPU.

## 1. Optics under the surface
- Critical angle water->air = asin(1/1.333) = 48.6 deg; looking up, the whole sky/room is squeezed into a cone of ~97 deg ("Snell's window"); outside it the surface is a MIRROR of the
  pool (total internal reflection, TIR). Waves widen / break the window edge (Lynch 2015: up to ~122 deg with waves). https://en.wikipedia.org/wiki/Snell%27s_window ,
  https://spark.iop.org/snells-window , https://opg.optica.org/spotlight/summary.cfm?id=301426 - high - unverified.
- Shader: GLSL `refract(I, N, eta)` returns vec3(0) on TIR. For a view ray going UP hitting the surface from below use N = -n_surface (pointing down into the water) and eta = 1.333.
  Inside the window mix transmitted (room) and reflected by Fresnel; Schlick with cos of the angle on the AIR side (cos_t) is the correct choice when n1 > n2. Derivation - high.
- Absorption of pure water (Pope & Fry 1997, values from memory, roughly): blue 450 nm ~0.01 /m, green 550 nm ~0.06 /m, red 650 nm ~0.35 /m, 700 nm ~0.6 /m.
  https://omlc.org/spectra/water/abs/ - medium (numbers from memory, trend confirmed by the search: minimum near 420 nm, red >> green). Pool water also SCATTERS (chlorine, particles):
  a game look "murky a few metres away" needs an extra grey-blue in-scattering term far stronger than pure-water absorption (own choice; no canonical number found - tune by eye).
- Underwater fog model used here: col = surf * exp(-(absorb_rgb + turbid) * d) + fog_rgb * (1 - exp(-(turbid + mean absorb) * d)). Own design - unverified.

## 2. Action camera underwater (GoPro / bodycam)
- FLAT port: refraction at the port narrows the field of view by about the index of water (1.33x magnification: things look closer / bigger) and adds pincushion / radial
  distortion + chromatic aberration at the edges; a DOME port keeps the FOV. INON: "divide by 1.33" for apparent distance. https://isprs-archives.copernicus.org/articles/XLII-2-W3/481/2017/isprs-archives-XLII-2-W3-481-2017.pdf ,
  https://www.hydroflex.com/flat-and-dome-lens-ports - medium - unverified. Game: zoom ~1.2-1.33 + extra edge warp when the port is fully under.
- Split ("over-under") shots: the waterline is where the water touches the PORT; with a small port the band of eye heights giving a split is small (a dome makes it bigger).
  https://www.telesinstore.com/blogs/news/how-to-shoot-half-underwater-gopro-photos - low (retailer) - unverified.
- Crest (Unity ocean): underwater = full-screen effect between transparent and post passes, a screen-space MASK of under-water pixels, a "meniscus" line where the lens meets the water,
  double-sided ocean material for the underside. https://crest.readthedocs.io/en/4.17/user/underwater.html - medium - unverified.

## 3. Split frame design used here (own; status unverified until G12 shots)
- The lens PORT is a small rectangle at the eye (half height `port_half`); a render pixel at ndc (x, y) maps to the port point eye + right * x * aspect * h + up * y * h. The pixel
  is WET when that point is below the water height at the eye (+ a meniscus wobble). This is a straight line in render space; the lens fisheye bends it (real GoPro waterlines bend too).
- Every world shader (room, water, basin, gun) evaluates the same line from gl_FragCoord (shared include), so the boundary is consistent; the lens pass evaluates it at the
  render uv it samples. Wet pixels get the underwater fog / colour; dry pixels with the eye below the surface see the room via the captured cube atlas.
- One render, no second camera: the cost is a few ALU per pixel plus the basin mesh (hidden while no pixel is wet).

## 4. Wet lens (rain-on-glass family)
- Common screen-space method: drops = SDF mask (circle + tear tail), a normal from the mask gradient offsets the screen lookup (refraction), blur where water covers the glass,
  static drops + slow trails + fast drops. https://godotshaders.com/shader/rain-on-glass/ , https://godotshaders.com/?p=13124 (MIT) - medium - unverified.
- Pitfall (Unreal forum): refract ONLY inside drops (mask), never the whole pane, or screen-space smears appear when the camera turns.
  https://forums.unrealengine.com/t/strange-refraction-mapping/1327633 - medium.
- Here (lens.frag; data from core/wetlens.py, pure and FPS independent because every drop is a closed-form function of time since surfacing): a film sheet whose top edge falls
  (gravity-like ease) over ~1 s, a dozen drops as uniforms (x, y, radius, alpha): spherical-cap normal -> sample offset ~ magnifying lens, flipped image inside is NOT needed at this size.

## 5. Muffled audio in Panda
- `AudioManager.configure_filters(FilterProperties)` (lowpass, highpass, echo, reverb...) is implemented ONLY by the FMOD backend; OpenAL returns False.
  https://docs.panda3d.org/1.7/python/DSP_Effects , https://www.panda3d.org/reference/cxx/classFilterProperties.html - medium.
  verified-in-project 2026-11-07 (scratch script: create_AudioManager with audio-library-name p3openal_audio -> configure_filters False; p3fmod_audio -> True, sounds load).
- Without FMOD: pre-filter copies of the sounds (one-pole / biquad lowpass on the WAV samples at load) and switch / crossfade copies. Typical game cutoff when submerged ~500-1000 Hz
  (no canonical number found; forum practice) - low.
- ElevenLabs sound effects price (help centre): API 100 credits per generation with auto duration, 20 credits / s when the duration is set (max 30 s); the web app 40 / s and 4 takes.
  https://help.elevenlabs.io/hc/en-us/articles/25735337678481 - medium - unverified (the Composio call does not report credits).

## Verified in this project (G12, 2026-11-07; docs/notes/pool-hall.md G12)
- Port-line split (one render, every shader evaluates `port_h` from gl_FragCoord, the lens from its sampled render uv): one consistent waterline, bent by the fisheye. verified-in-project (shots g9_uw_half*_g12).
- PITFALL: eye 2 cm above the water -> the default 0.1 m near plane clips the surface right in front: a second, straight boundary appears. Fix: near plane 0.01 m while the eye is within 0.3 m of the surface. verified-in-project.
- Basin as real geometry (22 quads + ramp) under the water node inherits its shader inputs (child node); shaded by the SAME shade_basin as the refracted view from above -> both views agree. Hidden while no pixel is wet; drawn hidden 3 frames at start so its shader compiles then. verified-in-project.
- Underside: refract(dir, -n, 1.333) inside Snell's window -> captured room atlas; vec3(0) outside -> reflect + trace_basin from the surface (TIR mirror of the pool). Looks right in uw_up. verified-in-project.
- Cost: under the water 222-236 FPS, looking up 193, split 251-254 vs ~185 standing on the deck (M4 / Glock, High, 1366x768, AC): cheaper than the deck view (the basin replaces the room + shafts). verified-in-project (g8_perf).
- Wet-lens drops: pulling the sample toward the drop centre (magnifier) reads as opaque brown bubbles; sample = centre - k * offset with k ~2-3 (inverted, minified, like a real bead) reads as water. verified-in-project (shots surfaced_late).
- Film: a hard edge where the offset starts leaves a seam; ramp the film in over ~5 % of the frame below an uneven edge. verified-in-project.
- Underwater fog in DISPLAY space (after the tone curve) mixes consistently with the already tone-mapped room atlas; fog colour (0.07, 0.30, 0.40), turbidity 0.32 /m looked right; 0.03/0.17/0.24 + 0.42 was too dark. verified-in-project (shots), tuning open for the user.
