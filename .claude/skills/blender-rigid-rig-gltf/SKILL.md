---
name: blender-rigid-rig-gltf
description: Rigging rigid mechanical parts (slide, magazine, trigger) to bones and exporting multi-clip animation from Blender 5.1 to glb for panda3d-gltf in this project. Use when authoring or exporting a gun viewmodel with hands.
---
# Rigid rig + glTF export (Blender 5.1, panda3d-gltf 1.3.0 + this project's gltf_patch, 2026-11-06)
## Project conventions (verified-in-project via M4 notes in CLAUDE.md)
- Model in cm, face -Z, put under Entity(scale=0.01, rotation_y=180). Rigid parts follow bone parent node and are NOT skinned; only hands skin. One glb holds all clips on one timeline at 30 fps; code plays `Clip(name, from_frame, to_frame)`; frame N of a clip with N frames wraps to 0 -> use N-1 as end.
- Panda3D loader needs `gltf_patch.apply()` first; run tests/test_gltf_load.py-style checks for every new glb.
## Blender side
- Rigid part: parent to bone with `parent_type='BONE'` (not vertex weights) so the exporter writes it as a child node of the joint (assumption, unverified - check the M4 glb node tree).
- Several actions: each action in its own NLA track, export with "Group by NLA Track" (default); same-named tracks merge into one glTF clip (discourse.panda3d.org/t/28158, discourse.threejs.org/t/26431; 2026-11-06; medium; unverified). Alternative: one long action with frame ranges = the M4 way (recommended here, matches `Clip`).
- Export: `bpy.ops.export_scene.gltf(filepath, export_format='GLB', export_animations=True, export_force_sampling=True, export_apply=False)`; check names in current docs before use.
- Knowledge gap: how rigid bone-parented meshes export is undocumented in my searches -> test with a 1-bone cube first.
