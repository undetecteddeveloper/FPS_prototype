"""Blender script: export the Glock viewmodel (hands + gun + all clips) to a glb for panda3d-gltf.

Run inside Blender after glock_anim.build_all(). Output path is the first argument of export().
Key setting: export_optimize_animation_size=False, otherwise the exporter trims identical trailing frames and the
clip lengths change (Panda then reports different frame counts than the ones we keyed).
"""
import bpy


# mesh datablock names must contain the material name: game/viewmodel.py finds the material of a Panda GeomNode by name
# (the M4 file does the same: 'Main_M4_D_0' contains 'M4_D')
MESH_NAMES = {'Main_G17_D_0': 'Frame_Glock_Frame', 'Bolt_G17_D_0': 'Slide_Glock_Slide', 'Trigger_G17_D_0': 'Trigger_Glock_Black',
              'Mag1_G17_D_0': 'Mag_Glock_Black', 'Mag2_G17_D_0': 'MagSpare_Glock_Black'}


def export(path):
    for obj_name, mesh_name in MESH_NAMES.items():
        bpy.data.objects[obj_name].data.name = mesh_name
    arm = bpy.data.objects['Object_4']
    keep = set()

    def add_chain(o):
        while o:
            keep.add(o.name)
            o = o.parent

    for o in bpy.data.objects:
        if (o.type in ('MESH', 'EMPTY') and o.parent == arm) or o.name.endswith('_G17_D_0'):
            add_chain(o)
    add_chain(arm)
    bpy.ops.object.select_all(action='DESELECT')
    for n in keep:
        bpy.data.objects[n].hide_viewport = False
        bpy.data.objects[n].select_set(True)
    for a in bpy.data.actions:
        a.use_fake_user = True
    arm.animation_data.action = None
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', use_selection=True, export_animations=True,
        export_animation_mode='ACTIONS', export_skins=True, export_yup=True, export_apply=False,
        export_optimize_animation_size=False, export_force_sampling=True)


M4_GLB = 'E:/ursina projects/FPS_prototype/assets/guns/m4_-_fps_weapon_animations_pack_v.1.glb'
CODE = 'E:/ursina projects/FPS_prototype/tools/build/blender/glock_anim.py'


def run_all(out_path):
    """Re-import the M4 as hand-pose source, rebuild every clip, drop the source, export. Returns clip lengths."""
    sc = bpy.context.scene
    sc.render.fps = 30
    sc.frame_start, sc.frame_end = 0, 100
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    col = bpy.data.collections.new('M4_pose_src')
    sc.collection.children.link(col)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children['M4_pose_src']
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.gltf(filepath=M4_GLB)
    new = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before]
    src = [o for o in new if o.type == 'ARMATURE'][0]
    src.name = 'M4_src_arm'
    for o in new:
        if o.type == 'MESH':
            o.hide_viewport = True
            o.hide_render = True
    for a in list(bpy.data.actions):          # list(): renaming while iterating the live collection loops forever
        a.name = 'M4_' + a.name
    src.animation_data_create()
    src.animation_data.action = bpy.data.actions['M4_Fire']
    ns = {}
    exec(open(CODE, encoding='utf-8').read(), ns)
    ns['init']()
    sizes = ns['build_all']()
    for o in list(col.all_objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(col)
    for a in list(bpy.data.actions):
        if a.name.startswith('M4_'):
            bpy.data.actions.remove(a)
    export(out_path)
    return sizes
