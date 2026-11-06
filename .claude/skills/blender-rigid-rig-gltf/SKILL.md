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

## VERIFIED IN PROJECT (G8 Glock, 2026-11-06, Blender 5.1.2 + panda3d-gltf 1.3.0 via gltf_patch; experiment: tools/build/blender/glock_anim.py + tests/test_glock_anim.py)
- Rigid parts: `parent_set(type='BONE', keep_transform=True)` -> Panda exposes node `<ObjName>-parent` that follows the bone (same as M4). Parenting is evaluated at the CURRENT pose: reset pose first, or the part jumps (cost me a debugging loop).
- Name meshes `<Part>_<Gun>_D_0` to mimic the M4 lookup (`Mag2_M4_D_0-parent`).
- Several clips: one Action per clip, `export_animation_mode='ACTIONS'` -> one glTF animation per action, Panda names = action names. Works.
- glTF exporter writes the BIND pose for every bone that has no keyframes -> hands fell back to the T-pose. KEY EVERY BONE in every clip (loc + quat). Panda tests that only look at gun parts do not catch it: also assert hand joint positions (`actor.exposeJoint`).
- `export_optimize_animation_size=False` or trailing identical frames are trimmed and clip lengths change (some clips still came out 1 frame shorter, so read numFrames from Panda, do not assume).
- Blender 5.x layered actions: no `action.fcurves`; iterate `layers[].strips[].channelbags[].fcurves`.
- Panda frame quirk (same as M4 note): pose(clip, 0) shows frame 1; frame N wraps to 0. Author frame 0 = copy of the first pose, usable range 1..numFrames-1, add one trailing hold frame.
- Iterating `bpy.data.actions` while renaming loops forever: use `list(...)`.
- The imported M4 armature has a weird bind pose (shoulder bones at origin, bone length 1.46 m): Blender IK and numeric solves FAIL (diverge/rod-like arms). Reliable approach: keep the M4 hand pose as the base and animate only rigid world transforms of the pose bones: desired armature-space matrix -> `basis = (parent.matrix @ rest_rel).inverted() @ desired`.
- Pose-bone `location` units are the armature's local units (cm for the M4 rig); world = arm.matrix_world (scale 0.01).
