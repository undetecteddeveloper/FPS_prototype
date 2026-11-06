"""G5: reads the reload animation to find the MAGAZINE-SWAP CUES: which frame the old magazine leaves the rifle, the new magazine seats, and the bolt runs.
Sets the pose with pose(clip, frame), then measures the bounding-box centre of each part relative to the rifle body (Main), against the ready pose (end of Draw).
Opens no window.

Run:  .venv\\Scripts\\python.exe -X utf8 tools\\measure\\g5_reload_probe.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from panda3d.core import Filename, loadPrcFileData

loadPrcFileData('', 'window-type none')
loadPrcFileData('', 'audio-library-name null')

from direct.actor.Actor import Actor
from direct.showbase.ShowBase import ShowBase

from fps.game import gltf_patch

gltf_patch.apply()
base = ShowBase()
actor = Actor(Filename.from_os_specific(str(ROOT / 'assets' / 'guns' / 'm4_-_fps_weapon_animations_pack_v.1.glb')))
bundle = actor.getPartBundle('modelRoot')

from fps.weapon_data import M4  # noqa: E402

NAMES = {
    'Main': 'Main_M4_D_0-parent',
    'Mag1': 'Mag1_M4_D_0-parent',
    'Mag2': 'Mag2_M4_D_0-parent',
    'Bolt': 'Bolt_M4_D_0-parent',
    'Catch': 'BoltCatch_M4_D_0-parent',
}
nodes = {k: actor.find(f'**/{v}') for k, v in NAMES.items()}
bullets = list(actor.find_all_matches('**/Bullet5_56x45mm_Bullet5_56x45mm_D_0-parent'))
for i, b in enumerate(bullets):
    nodes[f'Bul{i}'] = b


def center(np_):
    lo, hi = np_.get_tight_bounds(actor)
    return (lo + hi) / 2


def snap(clip, frame):
    actor.pose(clip, frame)
    bundle.force_update()
    c = {k: center(n) for k, n in nodes.items()}
    main = c['Main']
    return {k: (v - main) * 1.0 for k, v in c.items()}      # centre relative to the rifle body, in cm


ready = snap('Draw', M4.clips['draw'].end)
print('Tư thế sẵn sàng (cm so với thân súng):')
for k, v in ready.items():
    print(f'  {k:5s} {v.x:7.2f} {v.y:7.2f} {v.z:7.2f}')


def dist(a, b):
    return (a - b).length()


for key in ('reload', 'reload_empty'):
    clip = M4.clips[key]
    print(f'\n== {key}: khung {clip.start}..{clip.end} ({clip.duration:.2f}s). Cột: khung | Mag1 cách chỗ cũ | Mag2 cách chỗ băng | Bolt cách chỗ cũ | Catch | Bul0 | Bul1  (cm)')
    first_far = None
    seated2 = None
    for f in range(clip.start, clip.end + 1):
        s = snap(clip.anim, f)
        d1 = dist(s['Mag1'], ready['Mag1'])
        d2 = dist(s['Mag2'], ready['Mag1'])           # magazine seat = Mag1's position in the ready pose
        db = dist(s['Bolt'], ready['Bolt'])
        dc = dist(s['Catch'], ready['Catch'])
        dbul = [dist(s[k], ready['Mag1']) for k in ('Bul0', 'Bul1') if k in s]
        if first_far is None and d1 > 3:
            first_far = f
        print(f'  f{f:3d} t={(f - clip.start) / 30:4.2f}s  mag1 {d1:6.1f}  mag2 {d2:6.1f}  bolt {db:5.1f}  catch {dc:5.1f}  bul {" ".join(f"{x:6.1f}" for x in dbul)}')
    print(f'  băng cũ rời chỗ (> 3 cm) lần đầu ở khung {first_far}')
    end = snap(clip.anim, clip.end)
    print('  cuối clip so với tư thế sẵn sàng (cm): ' + ', '.join(f'{k} {dist(end[k], ready[k]):.2f}' for k in ('Main', 'Mag1', 'Bolt', 'Catch')))

# hand fit: does the end of each clip match the ready pose?
from panda3d.core import Mat4  # noqa: E402

joints = [j for j in actor.getJoints()]


def joint_mats(clip, frame):
    actor.pose(clip, frame)
    bundle.force_update()
    out = {}
    for j in joints:
        np_ = actor.exposeJoint(None, 'modelRoot', j.getName())
        out[j.getName()] = Mat4(np_.getMat(actor))
    return out


ref = joint_mats('Draw', M4.clips['draw'].end)
print('\nKhác biệt khớp (vị trí lớn nhất, cm) so với tư thế sẵn sàng:')
for key in ('reload', 'reload_empty', 'fire', 'holster'):
    clip = M4.clips[key]
    for label, f in (('đầu', clip.start), ('cuối', clip.end)):
        m = joint_mats(clip.anim, f)
        worst = max((m[n].getRow3(3) - ref[n].getRow3(3)).length() for n in ref)
        print(f'  {key:13s} {label:5s} khung {f}: {worst:.2f} cm')
