"""Blender script (run inside Blender 5.1 via the blender-lab MCP, NOT with the game's Python).

Builds the Glock clips on the M4 hand rig. Pose strategy: both arms keep the M4 'Fire' start pose (right hand grips,
left hand cups under the grip); motion = a rigid world transform applied to gun root + both shoulders, plus extra
per-part motion (slide, trigger, magazines, left arm). Every frame is evaluated here and keyed (no constraints,
so the glb holds plain FK keys).

Scene assumptions (set up interactively, see assets/review/glock/README.md):
  armature 'Object_4' (M4 rig, gun meshes replaced by Frame/Slide/Trigger/Mag/MagSpare parented to bones),
  'M4_src_arm' (re-import of the M4 glb, used only as the source of the hand pose at frame 226 of action 'Fire').
World axes: -Y forward (muzzle), +X = gun's left, +Z up. Units: metres.
"""
import math

import bpy
from mathutils import Matrix, Vector

ARM = bpy.data.objects['Object_4']
W = ARM.matrix_world
WI = W.inverted()
P = ARM.pose.bones
FPS = 30

GUN_ROOT = 'Main_j_049'
RIGID = ['Main_j_049', 'RightArm_03', 'LeftArm_026']          # move together with the gun
PARTS = ['Bolt_j_052', 'Trigger_j_054', 'Mag1_j_050', 'Mag2_j_051']
LEFT = 'LeftArm_026'
KEYED = RIGID + PARTS
FOLLOW_ARM = ['RightArm_03']

# geometry in gun-local metres (gun origin = G0 below), measured from the model
GRIP_MID = Vector((0, 0.055, -0.025))                          # rotation pivot (inside the right hand)
TRIGGER_PIV = Vector((0, 0.0056, 0.024))
MAG_AXIS = Vector((0, 0.19, -0.98)).normalized()               # magazine travel direction when it comes out
SLIDE_TRAVEL = 0.026

BASE = {}                                                      # basis of non-gun bones at the M4 pose
REST_R = Matrix.Rotation(math.radians(5.0), 3, 'X')          # the gun is placed pitched 5 deg in the rest pose (see place_glock)


def smooth(t):
    return t * t * (3 - 2 * t)


def interp(keys, f):
    """keys: list of (frame, value or tuple). Smoothstep between neighbours, hold outside."""
    if f <= keys[0][0]:
        return keys[0][1]
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f <= f1:
            t = smooth((f - f0) / max(1e-9, (f1 - f0)))
            if isinstance(v0, tuple):
                return tuple(a + (b - a) * t for a, b in zip(v0, v1))
            return v0 + (v1 - v0) * t
    return keys[-1][1]


def set_basis_from_arm_matrix(pb, m_arm):
    """Set pose bone so that its armature-space pose matrix equals m_arm (parent must already be posed)."""
    if pb.parent:
        rest_rel = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
        pm = pb.parent.matrix @ rest_rel
    else:
        pm = pb.bone.matrix_local
    pb.matrix_basis = pm.inverted() @ m_arm


def apply_world(pb, xw):
    """Apply a world-space transform xw to a posed bone."""
    set_basis_from_arm_matrix(pb, WI @ xw @ W @ pb.matrix)


def rot_about(axis, deg, pivot):
    return Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-pivot)


def reset_driven():
    for n in PARTS + [GUN_ROOT]:
        pb = P[n]
        pb.rotation_mode = 'QUATERNION'
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.scale = (1, 1, 1)
    for n in ('RightArm_03', 'LeftArm_026'):
        pb = P[n]
        pb.location, pb.rotation_quaternion = BASE[n]


def capture_base():
    for n in ('RightArm_03', 'LeftArm_026'):
        BASE[n] = (P[n].location.copy(), P[n].rotation_quaternion.copy())


def g0_world():
    """Gun origin in world at rest = Main bone head."""
    return W @ P[GUN_ROOT].bone.head_local


def pose_frame(prm, g0):
    """prm keys: gun=(tx,ty,tz,pitch_up,yaw,roll) slide trig mag1 mag2 (m along MAG_AXIS, plus lateral) left=(dx,dy,dz)."""
    reset_driven()
    bpy.context.view_layer.update()
    tx, ty, tz, pitch_up, yaw, roll = prm['gun']
    piv = g0 + REST_R @ GRIP_MID
    rg = (Matrix.Rotation(math.radians(-pitch_up), 4, 'X') @ Matrix.Rotation(math.radians(yaw), 4, 'Z')
          @ Matrix.Rotation(math.radians(roll), 4, 'Y'))
    delta = Matrix.Translation(Vector((tx, ty, tz))) @ Matrix.Translation(piv) @ rg @ Matrix.Translation(-piv)
    r3 = rg.to_3x3() @ REST_R
    for n in RIGID:
        apply_world(P[n], delta)
        bpy.context.view_layer.update()
    # left arm extra motion (follows gun rotation)
    lx, ly, lz = prm.get('left', (0, 0, 0))
    if lx or ly or lz:
        apply_world(P[LEFT], Matrix.Translation(r3 @ Vector((lx, ly, lz))))
        bpy.context.view_layer.update()
    # parts
    def local_to_world(v):
        return delta @ (g0 + REST_R @ v)

    s = prm.get('slide', 0.0)
    if s:
        apply_world(P['Bolt_j_052'], Matrix.Translation(r3 @ Vector((0, s, 0))))
    t = prm.get('trig', 0.0)
    if t:
        p = local_to_world(TRIGGER_PIV)
        axis = r3 @ Vector((1, 0, 0))
        apply_world(P['Trigger_j_054'], Matrix.Translation(p) @ Matrix.Rotation(math.radians(t), 4, axis) @ Matrix.Translation(-p))
    for key, bn in (('mag1', 'Mag1_j_050'), ('mag2', 'Mag2_j_051')):
        d = prm.get(key, 0.0)
        if d:
            v = MAG_AXIS * d if not isinstance(d, tuple) else MAG_AXIS * d[0] + Vector((d[1], 0, 0))
            apply_world(P[bn], Matrix.Translation(r3 @ v))
    bpy.context.view_layer.update()


def key_frame(f):
    # EVERY bone is keyed: the glTF exporter writes the bind pose (T-pose arms) for bones without keys, so the
    # static M4 hand pose must be keyed too, or the hands appear in the T-pose in the game.
    for pb in ARM.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.keyframe_insert('location', frame=f, group=pb.name)
        pb.keyframe_insert('rotation_quaternion', frame=f, group=pb.name)


def iter_fcurves(act):
    """Blender 5.x layered actions: fcurves live in channelbags of the strips."""
    if hasattr(act, 'fcurves'):
        yield from act.fcurves
        return
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                yield from cb.fcurves


def build_clip(name, nframes, table, loop=False):
    """table: dict of channel -> keys [(frame, value)...]; channel names as in pose_frame."""
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    ARM.animation_data_create()
    ARM.animation_data.action = act
    act.use_fake_user = True
    g0 = g0_world_cache
    # Panda quirk (same as the M4 pack): frame 0 of a clip is NOT usable (pose(0) shows frame 1) and frame N wraps to 0.
    # So frame 0 duplicates the first pose, table time t lives at file frame t+1, and one hold frame closes the clip:
    # usable range = 1 .. numFrames-1.
    for f in range(nframes + 2):
        prm = {}
        for ch, keys in table.items():
            prm[ch] = interp(keys, max(f - 1, 0))
        prm.setdefault('gun', (0, 0, 0, 0, 0, 0))
        pose_frame(prm, g0)
        key_frame(f)
    for fc in iter_fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    return act


g0_world_cache = None


def init(src_arm_name='M4_src_arm', src_frame=226):
    """Copy the M4 hand pose, remember it as the base pose."""
    global g0_world_cache
    src = bpy.data.objects[src_arm_name]
    src.animation_data_create()
    src.animation_data.action = bpy.data.actions.get('M4_Fire') or src.animation_data.action
    bpy.context.scene.frame_set(src_frame)
    bpy.context.view_layer.update()
    skip = ('Main_j', 'Mag1_j', 'Mag2_j', 'Bolt_j', 'BoltCatch_j', 'Trigger_j')
    for b in ARM.pose.bones:
        if b.name.startswith(skip):
            continue
        s = src.pose.bones[b.name]
        b.rotation_mode = 'QUATERNION'
        b.location = s.location
        b.rotation_quaternion = s.rotation_quaternion
        b.scale = s.scale
    bpy.context.view_layer.update()
    capture_base()
    g0_world_cache = g0_world()


REST = (0, 0, 0, 0, 0, 0)
DOWN = (0, 0.10, -0.30, -45, 0, 25)      # holstered / lowered pose: back, down, nose-down, rolled


def reload_tables(empty):
    """Shared magazine swap. empty=True: the slide starts locked back and is released after the new magazine is in."""
    tilt = (0, 0.010, -0.005, 8, 0, 18)
    t = {
        'gun': [(0, REST), (8, tilt), (52, tilt), (62, (0, 0.004, 0, 1.5, 0, 3)), (70, REST)],
        'mag1': [(0, 0.0), (10, 0.0), (18, 0.12), (26, 0.5), (27, 3.0), (69, 3.0), (70, 0.0)],
        'mag2': [(0, 3.0), (27, 3.0), (28, 0.22), (36, 0.20), (44, 0.012), (47, -0.004), (50, 0.0)],
        'left': [(0, (0, 0, 0)), (14, (0, 0, 0)), (20, (0, 0, -0.20)), (27, (0, 0, -0.20)), (36, (0, 0, -0.17)),
                 (44, (0, 0, -0.01)), (48, (0, 0, 0.01)), (56, (0, 0, 0))],
    }
    n = 72
    if empty:
        # slide held back, released at f66 (thumb on the slide stop), gun jolts a little
        t['slide'] = [(0, SLIDE_TRAVEL), (64, SLIDE_TRAVEL), (66, 0.0)]
        t['gun'] = [(0, REST), (8, tilt), (64, tilt), (66, (0, 0.008, 0, 2.5, 0, 14)), (74, (0, 0.003, 0, 1, 0, 2)), (84, REST)]
        # same magazine timing, slightly later seat because the empty mag takes longer
        n = 88
        t['mag1'] = [(0, 0.0), (10, 0.0), (18, 0.12), (26, 0.5), (27, 3.0), (n - 2, 3.0), (n - 1, 0.0)]
        t['left'][-1] = (56, (0, 0, 0))
    else:
        t['mag1'][-2:] = [(n - 2, 3.0), (n - 1, 0.0)]
    return n, t


CLIPS = {}


def define_clips():
    global CLIPS
    CLIPS = {
        'Idle': (60, {'gun': [(0, REST), (30, (0, 0.0015, 0.002, 0.4, 0, 0)), (60, REST)]}),
        'IdleEmpty': (60, {'gun': [(0, REST), (30, (0, 0.0015, 0.002, 0.4, 0, 0)), (60, REST)],
                           'slide': [(0, SLIDE_TRAVEL)]}),
        'Fire': (10, {
            'gun': [(0, REST), (1, (0, 0.014, 0.004, 5, 0, 1)), (3, (0, 0.008, 0.002, 3, 0, 0.5)), (9, REST)],
            'slide': [(0, 0.0), (1, SLIDE_TRAVEL), (2, 0.010), (3, 0.0)],
            'trig': [(0, 0.0), (1, 12.0), (5, 12.0), (7, 0.0)]}),
        'FireLast': (10, {
            'gun': [(0, REST), (1, (0, 0.014, 0.004, 5, 0, 1)), (3, (0, 0.008, 0.002, 3, 0, 0.5)), (9, REST)],
            'slide': [(0, 0.0), (1, SLIDE_TRAVEL)],
            'trig': [(0, 0.0), (1, 12.0), (5, 12.0), (7, 0.0)]}),
        'Draw': (30, {'gun': [(0, DOWN), (14, (0, -0.01, 0.008, 3, 0, -2)), (20, (0, 0.004, 0, -1, 0, 0.5)), (29, REST)],
                      'left': [(0, (0, 0, -0.10)), (20, (0, 0, 0))]}),
        'Holster': (24, {'gun': [(0, REST), (14, DOWN), (23, DOWN)], 'left': [(0, (0, 0, 0)), (14, (0, 0, -0.10))]}),
    }
    n, t = reload_tables(False)
    CLIPS['Reload'] = (n, t)
    n, t = reload_tables(True)
    CLIPS['ReloadEmpty'] = (n, t)


def build_all():
    define_clips()
    out = {}
    for name, (n, table) in CLIPS.items():
        build_clip(name, n, table)
        out[name] = n
    return out
