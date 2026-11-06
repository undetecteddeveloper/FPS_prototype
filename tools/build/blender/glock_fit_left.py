"""Blender script: fit the LEFT hand of the Glock viewmodel (run inside Blender via the blender-lab MCP).

Prerequisite: glock_anim.py constants LEFT_ROT_DEG = 0, LEFT_SHIFT = 0 and the scene rebuilt (glock_export.run_all) so the
action 'Idle' holds the baseline (left palm under the magazine floorplate). Then:

    ns = {}; exec(open('.../glock_fit_left.py').read(), ns); print(ns['fit']())

fit() returns the best (yaw, pitch, roll) about the palm, the shift (m) and the curl factors (fingers, index, thumb) to
paste into glock_anim.py. Cost terms (all measured against the Glock meshes with a BVH signed distance):
  - joint inside the gun or inside a right-hand finger,
  - gap of the finger pads (middle/ring/pinky <= 3 mm, weight 2, index and thumb <= 2 mm: they must touch the gun),
  - thumb tip points forward, palm on the gun's LEFT side and at the same depth as the right palm,
  - palm ~1.8 cm from the frame, wrist not inside the gun, elbow behind and below the wrist.
Reference pose: standard 'thumbs forward' two-hand grip (skill fps-pistol-animation).
"""
import itertools
import math
import random

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

IDX = {'Thumb': 6, 'Index': 10, 'Middle': 14, 'Ring': 18, 'Pinky': 22}
RAD = {'Thumb': 0.011, 'Index': 0.009, 'Middle': 0.0095, 'Ring': 0.009, 'Pinky': 0.008}


def fit(seed=41, n_random=60000, n_refine=30000, start=None):
    random.seed(seed)
    arm = bpy.data.objects['Object_4']
    W = arm.matrix_world
    P = arm.pose.bones
    arm.animation_data.action = bpy.data.actions['Idle']
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    gun = []
    for n in ('Main_G17_D_0', 'Mag1_G17_D_0', 'Bolt_G17_D_0'):
        o = bpy.data.objects[n]
        gun.append((BVHTree.FromObject(o, dg), o.matrix_world.inverted(), o.matrix_world.to_3x3()))

    def sdgun(p):
        best = 9.9
        for bvh, mi, m3 in gun:
            q = mi @ p
            loc, nor, _, _ = bvh.find_nearest(q)
            if loc is None:
                continue
            best = min(best, (1 if (q - loc).dot(nor) >= 0 else -1) * (m3 @ (q - loc)).length)
        return best

    def ks(f):
        return (1, 2, 3, 4) if f == 'Thumb' else (1, 2, 3)

    r_pts = [W @ P[f'RightHand{f}{k}_0{i0 + k - 1}'].head for f, i0 in IDX.items() for k in (1, 2, 3)]
    r_palm = (W @ P['RightHand_05'].head + W @ P['RightHandMiddle1_014'].head) / 2

    def lname(f, k):
        return f'LeftHand{f}{k}_0{IDX[f] + k - 1 + 23}'

    q_right = {(f, k): P[f'RightHand{f}{k}_0{IDX[f] + k - 1}'].rotation_quaternion.copy()
               for f in IDX if f != 'Thumb' for k in (1, 2, 3)}
    q_left0 = {(f, k): P[lname(f, k)].rotation_quaternion.copy() for f in IDX for k in ks(f)}

    def scale_q(q, k):
        ax, an = q.to_axis_angle()
        return Quaternion(ax, an * k)

    def pts_for(cf, ci, ct):
        for f in ('Middle', 'Ring', 'Pinky'):
            for k in (1, 2, 3):
                P[lname(f, k)].rotation_quaternion = scale_q(q_right[(f, k)], cf)
        for k in (1, 2, 3):
            P[lname('Index', k)].rotation_quaternion = scale_q(q_right[('Index', k)], ci)
        for k in (1, 2, 3, 4):
            P[lname('Thumb', k)].rotation_quaternion = scale_q(q_left0[('Thumb', k)], ct)
        bpy.context.view_layer.update()
        return ([(f, k, W @ P[lname(f, k)].head) for f in IDX for k in ks(f)],
                (W @ P['LeftHand_028'].head + W @ P['LeftHandMiddle1_037'].head) / 2,
                W @ P['LeftHand_028'].head, W @ P['LeftForeArm_027'].head)

    combos = list(itertools.product((1.0, 1.4, 1.8, 2.2), (1.0, 1.5, 2.0), (0.0, 0.5, 1.0, 1.5, 2.0)))
    data = {c: pts_for(*c) for c in combos}
    for (f, k), q in q_left0.items():
        P[lname(f, k)].rotation_quaternion = q
    gx = -0.082

    def cost(prm, detail=False):
        yaw, pitch, roll, dx, dy, dz, ci_ = prm
        pts, palm, wrist, elbow = data[combos[ci_]]
        rot = (Matrix.Rotation(math.radians(yaw), 3, 'Z') @ Matrix.Rotation(math.radians(pitch), 3, 'X')
               @ Matrix.Rotation(math.radians(roll), 3, 'Y'))
        sh = Vector((dx, dy, dz))

        def tr(p):
            return palm + rot @ (p - palm) + sh

        c = 0.0
        t3, sds = {}, {}
        for f, k, p in pts:
            p = tr(p)
            t3[(f, k)] = p
            r = RAD[f] * (0.8 if k == 4 else 1.0)
            s = sdgun(p)
            sds[(f, k)] = s
            c += max(0, r - s) ** 2 * (3e4 if f == 'Thumb' else 1e4)
            dmin = min((p - q).length for q in r_pts)
            c += max(0, r + 0.009 - dmin) ** 2 * 1e4
            near = min(s - r, dmin - r - 0.009)
            if f in ('Middle', 'Ring', 'Pinky') and k in (2, 3) and near > 0.003:
                c += 2.0 * (near - 0.003) ** 2 * 1e4
            if f == 'Index' and near > 0.002:
                c += 4.0 * (near - 0.002) ** 2 * 1e4
            if f == 'Thumb' and k in (2, 3, 4) and s - r > 0.002:
                c += 4.0 * (s - r - 0.002) ** 2 * 1e4
        c += max(0, t3[('Thumb', 4)].y - t3[('Thumb', 1)].y + 0.04) ** 2 * 1e4 * 0.5   # thumb tip well forward of its base
        pc = tr(palm)
        sp = sdgun(pc)
        c += 2 * (sp - 0.018) ** 2 * 1e4
        c += max(0, (gx + 0.02) - pc.x) ** 2 * 1e4 * 2
        c += ((pc.y - r_palm.y) - 0.005) ** 2 * 1e4 * 3
        we = tr(wrist)
        c += max(0, 0.03 - sdgun(we)) ** 2 * 1e4
        el = tr(elbow)
        c += max(0, (we.y + 0.12) - el.y) ** 2 * 1e4 * 0.3
        c += max(0, el.z - (we.z + 0.03)) ** 2 * 1e4 * 0.3
        c += max(0, (we.x - 0.03) - el.x) ** 2 * 1e4 * 0.2
        if not detail:
            return c
        gap = lambda f, k: round((sds[(f, k)] - RAD[f] * (0.8 if k == 4 else 1.0)) * 100, 1)
        return c, {'palm_dy_vs_right_cm': round((pc.y - r_palm.y) * 100, 1), 'palm_sd_cm': round(sp * 100, 1),
                   'thumb_gap_cm': [gap('Thumb', k) for k in (2, 3, 4)], 'index_gap_cm': [gap('Index', k) for k in (1, 2, 3)],
                   'mid_ring_pinky_gap_cm': {f'{f}{k}': gap(f, k) for f in ('Middle', 'Ring', 'Pinky') for k in (2, 3)},
                   'thumb_tip_forward_cm': round((t3[('Thumb', 1)].y - t3[('Thumb', 4)].y) * 100, 1),
                   'elbow_rel_wrist_cm': [round(v * 100, 1) for v in (el - we)]}

    def rnd():
        return (random.uniform(-100, 100), random.uniform(-100, 100), random.uniform(-110, 110),
                random.uniform(-0.08, 0.08), random.uniform(-0.08, 0.08), random.uniform(-0.06, 0.08),
                random.randrange(len(combos)))

    best = None
    if start:
        best = (cost(start), start)
    for _ in range(n_random):
        pr = rnd()
        c = cost(pr)
        if best is None or c < best[0]:
            best = (c, pr)
    c, pr = best
    for _ in range(n_refine):
        q = list(pr)
        j = random.randrange(6)
        q[j] += random.gauss(0, (6, 6, 6, 0.006, 0.006, 0.005)[j])
        if random.random() < 0.06:
            q[6] = random.randrange(len(combos))
        cc = cost(tuple(q))
        if cc < c:
            c, pr = cc, tuple(q)
    c, info = cost(pr, True)
    cf, ci, ct = combos[pr[6]]
    return {'cost': round(c, 2), 'LEFT_ROT_DEG': tuple(round(x, 1) for x in pr[:3]),
            'LEFT_SHIFT': tuple(round(x, 4) for x in pr[3:6]), 'LEFT_CURL': cf, 'LEFT_INDEX_CURL': ci,
            'LEFT_THUMB_CURL': ct, 'info': info}
