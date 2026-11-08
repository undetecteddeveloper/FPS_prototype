---
name: interior-water-light
description: Building a static interior map (tiled pool hall) with baked sun patches, a glossy reflective water plane and bullet-impact ripples, within the budget of an Intel UHD 620 in this Ursina-Panda3D project. Covers planar reflection vs box-projected cubemap, CPU lightmap baking of hard-edged sun patches + bounce, analytic per-fragment sun test, Fresnel/absorption water look, damped ring ripples, GPU budget notes. Use when touching ground.py/world.frag, adding a map, water, lightmaps, or reflections.
---

# Interior map: baked sun + reflective water (researched 2026-11-07)

All "source" lines were read as WEB SEARCH SUMMARIES on 2026-11-07 (pages not opened one by one) -> confidence medium at best. Status is `unverified` until an experiment in this project is named.
Tool versions: Panda3D 1.10.16, Ursina 8.3, Intel UHD 620 (8 GB shared RAM), project gate >= 60 FPS (M4 smoke worst case measured 94-100 FPS on 2026-11-07 => ~6 ms spare).

## Reference look (user image, 2026-11-07)
Indoor pool hall, small square tiles on walls + ceiling, column + stairs, one window opening to sky, golden low sun making HARD-EDGED patches on walls (soft penumbra), dark mirror-like water with soft ripples,
teal tint where shallow, steel handrails reflected. Sun is FIXED (user choice). Colour grade between Bodycam and the photo (user choice "o giua").

## Lighting without a shadow map (sun is static -> bake)
- BAKE on CPU (numpy), once, cache to disk keyed by hash(geometry + sun + params). Because the map is built from AABBs by our own code, every face gets a lightmap rect; texel -> ray toward sun (jittered over the sun disc for penumbra) vs. all boxes.
  Cost at runtime: one texture fetch. Source (general technique): lightmaps suit static interiors, direct light can be baked too - https://docs.godotengine.org/es/4.4/tutorials/3d/global_illumination/using_lightmap_gi.html - medium - unverified.
- Faces need their OWN texels (no shared pixels) in a second UV set; glTF has no lightmap slot, the engine attaches the image itself - https://discourse.threejs.org/t/why-do-ao-and-lightmap-need-a-second-set-of-uvs/4178/10 , https://forum.babylonjs.com/t/lightmaps-shadowmaps-tiled-textures/30450/3 - medium - unverified.
  We build geometry in Python so we can write UV2 (atlas rect per face) ourselves; no glb needed.
- Bounce (the golden glow on walls next to a patch): cosine-weighted hemisphere rays per texel, gather previous-pass direct light at hit points, 1-2 bounces, low-res (e.g. 0.25 m texels) is enough. https://therealmjp.github.io/posts/sg-series-part-6-step-into-the-baking-lab - medium - unverified.
- ALTERNATIVE (only if sun must move): per-fragment ray vs a short list of occluder boxes; supports translucent occluders, no shadow map. https://binary-studio.com/blog/2022/05/25/analytical-shadows-still-too-early/ - low (summary only) - unverified. ALU cost on UHD 620 unknown.
- Slab ray-AABB test (vectorised numpy): t1=(lo-o)/d, t2=(hi-o)/d, tmin=max(min(t1,t2)), tmax=min(max(t1,t2)); hit if tmax>=max(tmin,0). Derivation, high confidence.

## Reflection on the water (flat plane at y = water_y)
Three options, cheapest first. Which one is used is a product decision (does the water mirror smoke / tracers / the moving gun?).
1. BOX-PROJECTED CUBEMAP (parallax-corrected): capture the room ONCE from a probe above the water (6 renders at load), in the water shader intersect the reflected ray with the room AABB and sample the cube along (hit - probe).
   Accurate where the box matches the walls; misplaced for objects near the water (column, ladder) and no moving things. Box a little bigger than the room; fragment must be inside the box. Lagarde & Zanuttini SIGGRAPH 2012;
   https://developer.valvesoftware.com/wiki/Parallax_Corrected_Cubemaps , https://frostbone25.github.io/p/adventures-box-projected-reflections - medium - unverified.
2. PLANAR reflection each frame, half or quarter resolution: second camera = main camera matrix * reflection matrix of the plane, render to `make_texture_buffer`, sample with projective coordinates in the water shader.
   Pitfalls: (a) the plane's reflection matrix has scale (1,1,-1) -> reset scale to (1,1,1) on the camera after set_mat (forum report); (b) custom GLSL shaders must implement clip planes themselves (Panda manual: `p3d_ClipPlane[]` view-space planes) -> simplest is to hide everything below the water with a camera mask and a split of the pool basin into above / below parts;
   (c) mirrored view flips triangle winding -> cull flipped. https://discourse.panda3d.org/t/water-plane-reflection-glsl/13907 , https://discourse.panda3d.org/t/reflectionmap-question/13093 , https://www.panda3d.org/manual/index.php/Clip_Planes - medium - unverified.
3. Hybrid: cubemap for the room + a cheap extra layer for smoke / tracers drawn into a tiny planar target. Not researched.
- UHD 620 numbers (specs, not our measurement): 3 ROPs, 24 TMUs, 192 shading units, ~3 GPixel/s -> fill-rate bound; my inference: render-target SIZE is the main lever (half-res = 1/4 the pixels). https://www.chipversus.com/hardware/gpu/intel-uhd-graphics-620 , https://nanoreview.net/ru/gpu-compare/intel-uhd-graphics-64eu-vs-intel-uhd-graphics-620 - medium (specs), low (inference) - unverified. MEASURE before choosing.

## Water look
- Fresnel (Schlick): F = F0 + (1 - F0)(1 - n.v)^5, F0 ~ 0.02 for water. Dark water = mostly reflection at grazing angles, very little diffuse; body colour from Beer-Lambert absorption exp(-sigma * depth) toward a dark deep tone, teal where shallow. Derivations high; example shaders https://godotshaders.com/shader/absorption-based-stylized-water/ - medium - unverified.
- Ripples: normal = normalize(-dh/dx, 1, -dh/dz) from a height h. Ambient motion: 2-3 scrolling gradient-noise / sine layers at different scales and directions (cheap, no vertex displacement).
  Surface is a flat quad, so no real vertex waves are needed: perturb the NORMAL only, which tilts the reflection lookup (offset the reflection UV by normal.xz * strength).
- Impact ring (bullet): wave packet h = A * exp(-(r - c t)^2 / w^2) * sin(k (r - c t)) * exp(-r / R) * exp(-t / T); uniform array of vec4 (x, z, t0, amp), 8-16 slots, ring buffer on CPU. Derivation (own) - high for the math, `unverified` for look.
  Reference of the same idea: S&box water tool ripples (two float4 per emitter: centre, start time, strength, wavelength, width) https://sbox.game/redsnail/watertool/source?file=Code%2FWater%2FWaterManager.Ripples.cs - low (not opened) - unverified.
- Frame-rate independence: ripples are functions of absolute time t, never accumulated per frame.

## Tiles (walls / ceiling)
- NOTE 2026-11-08: the pool hall no longer draws tiles this way: room.frag / basin_common.glsl read numpy-built tile textures (colour + relief with real depth, parallax at the High level; docs/notes/surface-detail.md). What follows describes the old formula, still the cheap alternative.
- Procedural in the fragment shader (no texture, no memory): grout lines from `fract(p / tile)`, anti-aliased with `fwidth` exactly like `grid_lines` in world.frag; per-tile brightness jitter from a hash of `floor(p / tile)`. Fade lines to their average coverage when a pixel covers a tile (avoids shimmer). Derivation, high.

## Project integration notes (from reading the code 2026-11-07)
- World shader `world.frag`: normals from derivatives (mesh has no normals), tonemap + fog shared via `light_common.glsl`; world is ONE ground slab (`ground.py`, `WALK_BOUNDS` = rectangle, `step_vertical(ground_y=0)` = flat floor, `first_hit` over AABB boxes).
  A pool map needs: walls as AABB boxes in `colliders` (bullets already stop on boxes), walk collision against boxes (today only a rectangle clamp), and a ground-height function if the pool floor is walkable.
- `prune_scene_entities()` drops entities with no update/input; the lens pipeline renders world + gun into separate buffers: a reflection buffer must be created before/with them and kept off the lens' own cameras.
- Never run two heavy processes at once on this machine (see CLAUDE.md); wrap measurements in `tools\with_game_lock.py`.

## Verified in this project (G9, 2026-11-07; the pool hall is live: docs/notes/pool-hall.md)
- CPU bake with numpy: 142 face pieces, 210k texels (8 cm), 384 cosine rays per 0.4 m texel, two passes (the second pass reads the first pass's baked light at the hit spot, so the shade fills in): 36 s, 8.5M rays, 1024x512 atlas.
  One bounce alone left the unlit bank pitch black (0 x gain = 0): TWO passes + a small constant `fill` are needed. A rotation per texel of the sampling spiral shows as blotches on the ceiling; ONE rotation per face (smooth bias) + a 3x3 blur of the indirect grid fixed it. status: verified-in-project (tests/test_lightbake.py, pool_shots.py).
- The sun patches are exactly the windows projected along the sun (test with a point sun: <= 3 wrong points out of ~22,000). With the sun at 11 degrees NO beam reached the west wall (20 m room: the beam drops 4 m); ~7 degrees makes the walls and columns glow gold while the floor stays dim (cos = 0.12): that is the photo's look.
- Panda: `p3d_MultiTexCoord1` receives the SAME data as texcoord 0 when the node has one texture stage -> the lightmap was sampled with metric coordinates (clamped to a black corner). Use a CUSTOM vertex column read by name (`in vec2 lightmap`, `InternalName.make('lightmap')`, `Geom.C_other`). status: verified-in-project.
- PNG read by Panda: the first (top) row is v = 1 (checked with TexturePeeker); `Texture.write` of a buffer round-trips with the same convention, so a 3 x 2 atlas rendered with six display regions (row 0 = bottom) needs no flip.
- Box-projected 3 x 2 atlas (own face table in core/cubemap.py sent as uniforms) instead of Panda's cube texture: no coordinate-convention risk; capture asserts that the real camera axes equal the table (passed first time). A 92 degree face leaves a 1.7% guard band. Reflection: the mirrored windows / patches / columns look right; the handrails next to the north wall line up well enough (they stand 0.35 m from it). status: verified-in-project.
- Cost on Intel UHD 620 (M4, 1366x768, vsync off): standing 138 FPS vs 157 on the old flat map (about 0.9 ms), firing 94.6 vs 100.9, worst scene average 94.6. The room mesh is 720 triangles, 2 draw calls (room + water); the reflection is captured once, not per frame. The planar per-frame option was NOT built (the user chose 'room only, captured once').
- Gun light: `look_frame.y` (share of the sun reaching the player, from a CPU ray vs the boxes, smoothed 0.15 s) and `.z` (ambient scale) feed viewmodel.frag. 88 of 150 eye-height grid points are in the shade, so it discriminates.
- Pre-existing bug found by the new dark walls: the bullet-hole batch never had its texture bound (Ursina applies `Entity.texture` only to the entity's model; the batch is a raw node), so holes were white squares. Fixed with `np.set_texture`.
- The reflection image is tone-mapped with the exposure at capture time: changing exposure / fog needs a recapture (reflect_key includes them; the game recaptures at the next start).

## Pitfalls found by the user's play test (7/11/2026, all verified-in-project; tests named)
- Face derivation from boxes: an INVISIBLE collision box (the window barrier filling the hole) must not count as solid when deciding whether a face touches air, or every face inside the hole disappears and the wall is a paper-thin sheet there. Test only for the face's *existence* is not enough: assert the AREA of sill / lintel / jamb faces (tests/test_poolmap.py `test_every_window_hole_shows_its_full_wall_thickness`).
- Aimed sights: poses summed as 'angles + shifts in one node' break the sight line as soon as an aim rotation is added (the ADS shift is not turned with the gun): M4 sights 0.4 deg apart at 1.5 deg offset, 3.1 deg at 10 deg. Fix = parent node for the aim rotation (rotates the whole gun incl. its ADS shift about the eye). Any rotation about the eye keeps points that are collinear with the eye collinear; a translation does not (parallax). tests/test_sights.py + pool_check.py (probe nodes under the real graph).
- Pistol sights: the rear aiming point must be INSIDE the notch (here 2.3 mm deep); 3.5 mm 'under the blade tops' ran the sight line through the slide. Measure notch floor / blade tops / post top from the vertices, do not guess an offset. A 2 mm front post at 0.5 m eye relief is only a few pixels: 0.38 m reads better.
- Ambient for the gun must come from the room (baked probe grid, up- and down-facing irradiance at gun height), not a constant: a constant 0.27 in a black corner made the rail edges glow white (fresnel x ambient x 6).
- Panda binding: a PTA element read in Python (`pta[0]`) is a live reference; copy it (`tuple(...)`) before comparing two moments.
- Angles between nearly parallel vectors: use atan2(|a x b|, a . b); acos of float32 'almost 1' is off by ~0.02 deg.
- Machine noise: after a heavy bake / pytest the UHD 620 laptop gave 100 FPS and 1%-lows of 3 FPS (stalls); the same scene re-run alone 20 s later gave 132 FPS / 96 low. Never trust one number right after heavy work.

## Still open
- 8-bit gamma-2 lightmap banding on the soft penumbra: not visible in the shots, not measured.
- Planar per-frame reflection cost (smoke / tracers mirrored): not measured.
