---
name: pool-water-sim
description: Clear pool water in this Ursina-Panda3D project - GPU height-field wave simulation (ping-pong buffers in Panda), analytic refraction into a box-built pool (see the tiled bottom distorted by waves, no extra render pass), caustics, an analytic "sun through the windows" test reused for caustics and volumetric sun shafts, wet floor / puddles / wet footprints, runtime graphics quality levels switched by a hotkey. Use when touching water.py / water.frag / water_sim / room.frag wetness or shafts, or adding any GPU simulation or quality setting. Builds on interior-water-light (baked light, cubemap reflection).
---

# Clear pool water + wave sim + shafts (researched 2026-11-06)

Search summaries read 2026-11-06 (pages not opened one by one) -> medium confidence at best. Status `unverified` until an experiment is named. Panda3D 1.10.16, Ursina 8.3, Intel UHD 620.
Companion: `.claude/skills/interior-water-light/SKILL.md` (bake, box-projected cubemap, Fresnel, UHD 620 budget).

## 1. Height-field wave simulation on the GPU
- Model: damped 2D wave equation on a grid, finite differences, two time levels stored per texel (h, h_prev) because it is second order in time; new = h + (h - h_prev) * damp + (c dt / dx)^2 * laplacian(h).
  Stable only if c dt / dx <= 1/sqrt(2) (2D CFL; derivation, high). Damping factor per step and a clamp of h are the usual controls (sources give no canonical constant).
  https://hugodaniel.com/pages/pngine/docs/samples/wave-simulation/ , https://docs.nvidia.com/gameworks/content/gameworkslibrary/graphicssamples/opengl_samples/computewatersurfacesample.htm , https://apps.amandaghassaei.com/gpu-io/examples/wave2d/ - medium - unverified.
- Ping-pong: two render targets alternate, the previous result is the input of the next pass (D3D9-era write-up, NVIDIA sample) - medium. Boundaries: clamp/mirror the sample coordinates -> zero normal derivative = REFLECTING wall (nmarchand73 demo) - medium - unverified.
- Interaction: write displacements (impulses) into the texture; they spread into ripples - medium.
- Panda: `win.make_texture_buffer(name, w, h, tex, to_ram=False, fbp)` makes an offscreen buffer bound to a texture; power-of-two sizes advised; on weak hardware it may fall back to a PARASITE buffer, which only works if copied right after drawing -> ask for a real offscreen buffer (`GraphicsPipe.BF_refuse_window`) and float format via FrameBufferProperties(float_color, rgba_bits 32 - 16 is too coarse, see Verified). https://docs.panda3d.org/1.9/cpp/programming/render-to-texture/low-level-render-to-texture - medium - unverified.
  Own design (no Panda ping-pong sample found): two buffers, each an orthographic camera over a fullscreen card in its own scene; card A reads texture B and writes A, card B the reverse. Per frame enable 0-2 of them (`set_active`) and order them with `set_sort` so they always start from the latest texture.
- Frame-rate independence: fixed sim step (e.g. 1/120 s) with an accumulator; at most 2 steps per frame (slower frames give slow-motion waves rather than instability).

## 2. Refraction into a box pool (see the bottom without rendering it)
- Evan Wallace "WebGL Water" (2011, MIT; Medium article 2016): at the surface refract the view ray (Snell, eta = 1/1.333), intersect it with the pool AABB with the slab test (exit point from inside), shade the hit wall / floor; caustics by projecting refracted light rays onto the floor; breaks down for strong refraction.
  https://medium.com/@evanwallace/rendering-realtime-caustics-in-webgl-2a99a29a0b2c , https://github.com/jeantimex/threejs-water/wiki , https://medium.com/@martinRenou/real-time-rendering-of-water-caustics-59cda1d74aa - medium - unverified.
- Here the basin also has steps (boxes): exit of the basin box + nearest ENTRY of each step box (same slab test) -> nearest hit, the axis of the hit gives the face normal. Shading of the hit: tile pattern from metric coords, light from the baked ambient grid at (x, z) + analytic corner darkening + caustics.

## 3. Caustics
- Physically: concave crests focus light -> brightness ~ 1 / (area change) ~ 1 - k * depth * laplacian(h) (own derivation, first order; high for the sign, low for the look).
- WHY real pool caustics are a CLOSED network of rounded cells: every bright line is a fold of the surface->floor map, and the light that lands at a floor point is the SUM over all
  surface points whose refracted ray lands there. Evaluating 1/|det J| at the surface point and painting it straight below (G10 version) gives OPEN tangled threads with loose ends,
  not cells (verified-in-project by eye, shots g9_*_g11before vs the user's photos, 2026-11-07). A BROAD wave spectrum (1.4 -> 0.13 m) adds cells of every size: use a NARROW band
  (one octave and a bit) for even cells; cell size ~ the dominant wavelength. Low sun -> oblique refracted beam -> cells stretched along the sun. Own reasoning + photos - medium.
- Wallace's method (WebGL Water, MIT, https://madebyevan.com/webgl-water/renderer.js read 2026-11-07 - high for the code; the Medium article could not be fetched):
  - Draw the WATER SURFACE MESH (plane, detail 200) into a caustic texture (1024 x 1024) each frame, after the sim step; clear first.
  - Vertex: normal from the sim; `ray = refract(-light, normal, 1/1.333)`; `oldPos` = vertex on the FLAT surface projected along the flat refracted light, `newPos` = displaced vertex
    projected along `ray` (exit point of the pool box, then onto the floor plane along the flat refracted light); `gl_Position = newPos.xz` mapped to clip space.
  - Fragment: `oldArea = length(dFdx(oldPos)) * length(dFdy(oldPos)); newArea = length(dFdx(newPos)) * length(dFdy(newPos)); out = oldArea / newArea * 0.2` (flat water = 0.2).
    Exact determinant form: |det(dFdx(old.xz), dFdy(old.xz))| / |det(dFdx(new.xz), dFdy(new.xz))| (own; = area ratio of the triangle, works per 2x2 pixel quad).
  - Shading looks the texture up at `point.xz - point.y * refractedLight.xz / refractedLight.y` (the floor point a flat ray through `point` would reach): the SAME projection for floor
    and walls, so walls get the pattern too. Extras: rim shadow of the pool edge (sigmoid), sphere blob shadow in the green channel.
  - Not in the code: blending setup / texture format (in lightgl). Overlapping (folded) triangles must ADD: additive blend (ONE, ONE), two-sided (a fold flips the winding).
- Here (G11): flat reference = the same vertex on the flat surface with the flat refracted sun, so a sloping bottom gives exactly 1 on flat water (its n.l is in the shading already).
  The texture domain is the pool plan widened DOWNSTREAM of the sun (light travelling west lands beyond the west wall): walls look up the continued flat ray there.

## 4. Sun through the windows, analytic (caustics, shafts, wet glints)
- The sun is fixed and the only openings are rectangular holes in the east wall (x = hx .. hx + w): a point p sees the sun iff the ray p + s * sun hits the wall planes inside a window rectangle (test both wall faces for the reveal). Exact for this map up to columns (west side, never between the sun and the room). Own derivation, high.
- Volumetric shafts WITHOUT a post pass: in each surface shader march from the camera to the fragment N steps (8-16) and add density * phase * sun_visible(sample). Screen-space radial blur (GPU Gems 3 ch.13) and shadow-map shafts were the alternatives; neither needed here. https://github.com/robcupisz/LightShafts (1-1.5 ms at 1080p on GTX580 for its method) - medium. Dust: modulate density by slow 3D noise; specks as a small particle pool. Unverified cost on UHD 620 -> MEASURE.

## 5. Wet surfaces (Lagarde, "Observe rainy world")
- Wet = diffuse DARKER (and slightly more saturated), specular brighter / smoother; on dark albedo a puddle is almost a mirror. Puddle layer: roughness ~0.02-0.1, IOR 1.33 (F0 0.02). Porous materials need a separate darkening term.
  https://www.fxguide.com/?p=43362 , https://docs.unity3d.com/Packages/com.unity.shadergraph@14.0/manual/Shader-Graph-Sample-Production-Ready-Weather.html , https://godotshaders.com/shader/rain-puddles-v1/ - medium - unverified.
- Here: wetness mask = noise puddles (more near the pool edge) + wet footprints (uniform ring buffer, fading); wet -> albedo x ~0.6, box-projected room reflection x Fresnel (reuse the water's 3 x 2 atlas).

## 6. Quality levels switched live
- Switch by UNIFORMS (loop counts, on/off weights), not by recompiling shaders (a recompile = a hitch on the switch frame); GPU sim buffers are disabled with `set_active(False)` on Low. Own design.

## Verified in this project
- 2026-11-06, experiment `sim_gpu_check.py` (scratchpad; 64x128 grid, game/water_sim.py vs core/watersim.py, readback with `graphicsEngine.extract_texture_data`), Intel Graphics (Core 7 150U, Iris Xe class; NOT UHD 620 as older notes said):
  - The two-buffer ping-pong with `make_output(..., BF_refuse_window, gsg, win)` + `add_render_texture(RTM_bind_or_copy)`, 0-2 passes per frame chosen by `set_active` + `set_sort`, `texelFetch` with clamped neighbours: GPU == CPU to 0.0000 mm after 37 and 74 steps. status: verified-in-project.
  - HALF FLOAT (F_rgba16, 16-bit fbp) is NOT enough: 15-58 % error after 40-75 steps (the leapfrog takes differences of nearly equal numbers). Use F_rgba32 + rgba bits 32. verified-in-project.
  - A push added to the CURRENT height only acts as a velocity kick and keeps growing (1 cm -> 9 cm). Add it to both time levels (pure displacement). verified-in-project.
  - Reading the texture inside `update` AFTER scheduling this frame's passes gives the state of 1-2 steps earlier than counted (the passes run at render time). Timing pitfall for any readback test.
    Fix in code: `WaterSim.drawn_texture` (latest as of the start of update). A readback also stalls the GPU: the NEXT frame measures 60-75 ms (looked like an F2 hitch; it was the test).
- 2026-11-07, G10 in the game (docs/notes/pool-hall.md G10):
  - Analytic sun-through-windows test agrees with a ray cast against every room box at > 99.5 % of 3 000 random points (tests/test_graphics.py). verified-in-project.
  - Refraction traced in water.frag against the basin box (from inside) + step boxes (entry) + ONE sloping plane limited to a z range: correct-looking bottom, steps, slope (pool_shots deep/slope/wade); centre contrast looking down 0.17-0.19 vs 0.004 for the dark mirror (pool_check). verified-in-project.
  - Lighting the never-baked bottom with the baked ambient grid uploaded as a small float texture (BGR order for F_rgb32 ram images) looks consistent with the room. verified-in-project (shots).
  - The iterative caustic net TILES visibly (rows of identical scales). Product of two nets (second one rotated 37 deg, scaled 1.37) + a slow sine warp of the coordinates hides it. verified-in-project (shots g10b vs g10c).
  - Live quality switch by uniforms + `set_active` on buffers: <= 2 ms per switch, next frames <= 10 ms. Destroying the sim buffers is NOT needed for Low (keep them, stop the passes). verified-in-project (pool_check).
  - Cost (M4, 1366x768, vsync off, ON BATTERY): High (sim 256x512, refraction, caustics, glint, 16 shaft steps) standing 126 FPS vs Low 157 -> ~1.5 ms; worst firing scene 74.8 min. verified-in-project (g8_perf --level).
  - SHAFTS: marching 16 steps x 4 windows per pixel cost 7 ms/frame (A/B in one process, all other effects < 0.5 ms each). Replaced by the EXACT lit length: the projection
    along the sun onto a wall plane is linear in the point, so each window cuts one interval out of the view ray (4 x linear clips); only dust noise is sampled (1-3 per piece).
    ~1 ms; matches a 1 cm march within 3 cm (tests/test_graphics.py). Whole High level 4.1-4.9 ms/frame. verified-in-project. GENERAL LESSON: if the light volume is analytic, integrate it, do not march.
  - GLSL name clash: `noise2` is a BUILT-IN (returns vec2): defining `float noise2(vec2)` fails with "overloaded functions must have the same return type". verified-in-project.
  - gl_FragCoord is fragment-only: a shared include used by vertex shaders must guard fragment-only functions (`#define SUN_WINDOW_VERTEX`). verified-in-project.
  - Ursina Text ignores alpha 0 (the "invisible" warm-up text showed). Hide with `enabled = False`. verified-in-project.
  - Dust motes fully on the GPU: static mesh of seeds, position = wrap(seed * box + drift(t)) around the eye, glow = sun_visible(pos); quads of unlit motes collapsed in the vertex shader. ~0 CPU. verified-in-project.
  - Tests at uncapped FPS (400+): wait by TIME or event, never by frame count (a 1.2 m fall is 0.5 s, 60 frames were 0.15 s). verified-in-project.
  - MSAA through FilterManager: `renderSceneInto(colortex=..., fbprops=FrameBufferProperties().set_multisamples(n))` gives a real multisample buffer resolved into the texture
    (checked: `buffer.get_fb_properties().get_multisamples()` == 2 / 4). Changing it at runtime = cleanup the FilterManager and build a new one; first MSAA build ~400 ms hitch, later ~27 ms.
    Cost here: 2x +1.5 ms, 4x +3.3 ms. Display regions moved to another output must keep their active flag (parked guns). verified-in-project (tools/measure/graphics_panel_check.py).
  - Ursina `Text`: '<' starts a markup tag ("< Cao >" -> IndexError in align). verified-in-project.
  - First second after start sometimes ~30 FPS at Mid/High, ramping down to normal frame time (GPU clock ramp?). Not reproducible every run; dry-run warm frames did not reliably help. OPEN.
- 2026-11-07, G11 caustics by the light mesh (docs/notes/pool-hall.md):
  - Wallace's area-ratio pass ported to Panda: ONE triangle strip + `set_instance_count(rows - 1)` (gl_InstanceID = row) -> building / switching costs nothing; OmniBoundingVolume + final
    (the shader places vertices); ColorBlendAttrib M_add ONE ONE, two-sided, no depth; buffer clears itself; sort after the sim passes. Closed rounded cells like the photos. verified-in-project (shots g9_*_g11).
  - Light conserved (CPU reference binning photons, mean 1.01) and flat water = exactly 1. NOTE: bin with math.floor, not int() (int truncates negatives into bin 0). verified-in-project (tests).
  - Narrow band 16 waves, 0.56-0.21 m, rms 3 mm, low 7 deg sun: soft at 0.5 m, closed cells at 1 m, crossing bands at 2 m depth. verified-in-project (numpy proto + shots).
  - Cost on Iris-Xe class, AC: +0.5-1.3 ms (384x768 mesh, 2048 R16F tex) and +0.5-0.6 ms (256x512, 1024); R16F vs R32F made no measurable difference; mesh/texture size matter little
    (fixed cost of one more pass dominates). A/B PITFALL: switching a level off and on does NOT rebuild a pass of the same index - destroy it to test other sizes; the first 4 s after
    start are slow whatever is on (warm-up): never compare against the first block. verified-in-project.
