---
name: blender-lowpoly-bake
description: Reduce an AI-generated million-triangle mesh (Prism/Meshy glb) to a game low-poly in Blender 5.1 via bpy - decimate, UV unwrap, bake normal/base color from high to low, split a fused mesh into parts. Use when preparing any generated 3D asset for this project.
---
# Low-poly + bake (Blender 5.1, MCP blender-lab, 2026-11-06)
All claims below start `unverified` unless marked; upgrade after the G8 glock experiment.

## Pipeline
1. Keep the original as HIGH (hidden, never decimate it). Duplicate -> LOW.
2. LOW: Decimate modifier `type='COLLAPSE'`, `ratio=target_tris/high_tris` (docs.blender.org/api/dev/bpy.types.DecimateModifier.html, 2026-11-06, high, unverified). 1.43M -> ~8k = ratio ~0.0056: do it in 2-3 stages (e.g. 0.05 then 0.1) to keep silhouette; PLANAR mode (`angle_limit`) first helps flat slide faces.
   `bpy.ops.object.modifier_apply` needs the object active+selected (older API `scene.objects.active` no longer exists).
3. UV: Smart UV Project or manual seams on LOW; non-overlapping, one island set, 1 texture atlas.
4. Bake (Cycles only, Eevee cannot): select HIGH, then LOW active, `bpy.ops.object.bake(type='NORMAL'|'DIFFUSE'|'ROUGHNESS', use_selected_to_active=True, cage_extrusion=..., max_ray_distance=..., margin=...)`. Target = Image Texture node (selected, not connected) in LOW's material. Rays go outward from LOW; extrusion just big enough to enclose HIGH; too big -> ghost detail (blender manual / strayspark tutorial, 2026-11-06, medium, unverified). Avoid Edge Split on LOW (breaks normals).
5. Texture budget for this project: 1024x1024 (or 512 for small parts), JPEG base color, normal PNG; Intel UHD 620 is the reference machine.
## Splitting a fused mesh into parts (slide/mag/trigger)
- `bmesh.ops.bisect_plane(bm, geom=..., plane_co, plane_no, clear_inner/outer)` (API, no source read yet - low) or Edit Mode Knife/Bisect + `bpy.ops.mesh.separate(type='LOOSE'|'SELECTED')`.
- AI meshes have NO interior (no mag well, no chamber): separated parts leave holes -> cap with `bmesh.ops.holes_fill` / build simple inner geometry; hide seams with the slide travel stays small.
## Pitfalls
- Decimate ratio is a triangle ratio; read `len(mesh.polygons)` after triangulating to verify.
- Run Blender code via execute_blender_code returning `result` dict; do not print.
