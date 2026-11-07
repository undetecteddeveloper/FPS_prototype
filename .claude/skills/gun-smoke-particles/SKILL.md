---
name: gun-smoke-particles
description: Gunpowder smoke / soft particle billboards in this Ursina-Panda3D project - real muzzle smoke behaviour, frame-rate independent puff physics (exponential drag, buoyancy, wind, ground spread), one-draw-call dynamic Geom pool, camera-facing billboards expanded in the vertex shader, soft edges against the ground plane. Use when touching fps/core/smoke.py, fps/game/smoke.py, assets/shaders/smoke.*, or adding any other particle effect (dust, steam, sparks).
---

# Gun smoke particles (researched 2026-11-07)

## Real muzzle smoke (what to imitate)
- Muzzle flow = under-expanded supersonic jet inside a blast wave, with vortex rings; it is NOT homogeneous, unburned powder grains ride in it.
  Source: ULB thesis (Moumen) https://difusion.ulb.ac.be/vufind/Record/ULB-DIPOT:oai:dipot.ulb.ac.be:2013/361540/TOC - medium - unverified.
- The propellant gas leaves as a self-similar turbulent vortex ring that travels forward and slows down quickly (strong drag), widening as it goes.
  Source: Comiskey & Yarin, J. Fluid Mech. https://www.cambridge.org/core/journals/journal-of-fluid-mechanics/article/selfsimilar-turbulent-vortex-rings-interaction-of-propellant-gases-with-blood-backspatter-and-the-transport-of-gunshot-residue/81F43FB54E7FF28A0230667CD559D60F - medium - unverified.
- Game consequence: a fast puff along the barrel braked within ~0.1-0.2 s (drag 5-10 /s), a slower core cloud near the muzzle, swelling ~ sqrt(age),
  then slow buoyant rise + wind drift, faded out in ~1 s. Muzzle flash (primary + secondary a few ms later) is a separate effect.
  Source: SMPTE 1962 high-speed photography of muzzle flash https://journal.smpte.org/periodicals/Journal%20of%20the%20SMPTE/71/1A/103/07308845.pdf - low (abstract only) - unverified.

## Physics that stays frame-rate independent
- Linear drag toward an air velocity w with constant acceleration a: dv/dt = -k (v - w) + a. Terminal v_inf = w + a / k.
  Exact step: e = exp(-k dt); x += v_inf dt + (v - v_inf)(1 - e)/k; v = v_inf + (v - v_inf) e. (Derivation, high confidence.) verified-in-project: tests/test_smoke.py 30 vs 120 Hz.
- Turbulence: a smooth per-puff drift (sum of sines with random phase/frequency) added to the wind, sampled at mid-step. Never per-frame random jitter (that depends on the frame rate).
- Ground plane y = g: clamp centre to g + c*radius, turn the downward speed into outward horizontal speed (ground_spread share), vertical speed 0.

## Drawing (Panda3D 1.10.16 + Ursina 8.3, coordinate-system y-up-left)
- One GeomVertexData (UH_dynamic) with 4 rows per puff + one static GeomTriangles = one draw call. Dead slots = radius 0 (degenerate quads).
- Fast update: build all floats in a Python `array('f')`, then `vdata.modify_array_handle(0).copy_data_from(arr)` once per frame. Source: Panda API https://docs.panda3d.org/1.10/python/reference/panda3d.core.GeomVertexArrayDataHandle and forum https://discourse.panda3d.org/t/dynamic-per-update-alteration-of-geometry/30457 - high - verified-in-project (fps/game/smoke.py).
  Panda must know the data changed (modify_* invalidates caches); do not recreate GeomVertexData every frame (forum https://discourse.panda3d.org/t/using-geomvertexarraydatahandle-set-data-directly/3646, medium).
- Billboards: pass the centre as `p3d_Vertex`, the corner (+-1,+-1) and radius in custom columns; expand with the world camera axes (FrameLight.view_x / view_y PTA arrays, same as viewmodel.frag) so no Panda coordinate-system conversion is involved.
- Alpha blend, depth test on, depth write off, 'transparent' bin, two-sided, OmniBoundingVolume + set_final (vertices move in the shader). Sort puffs back-to-front on the CPU (cheap for < 300).
- Soft particles: the general method fades alpha by (scene depth - fragment depth) using a copied depth texture (NVIDIA 2007 https://developer.download.nvidia.com/whitepapers/2007/SDK10/SoftParticles_hi.pdf ; https://keaukraine.medium.com/implementing-soft-particles-in-webgl-and-opengl-es-b968d61133b0 - depth must be linearised - high).
  Here the only solid the smoke meets is the flat ground, so fade analytically by the fragment's world height above y = 0 (no depth texture). verified-in-project (smoke.frag).
- Use camera-facing quads, not point sprites, for large smoke (keaukraine, medium).
