"""G0 step 2: do the non-skinned gun parts (Bolt, Mag1, Trigger...) move with the animation?
Sets the pose with pose(clip, frame), then reads each node's position in the actor's coordinate system. Opens no window."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding='utf-8')

from panda3d.core import Filename, loadPrcFileData

loadPrcFileData('', 'window-type none')
loadPrcFileData('', 'audio-library-name null')

from direct.actor.Actor import Actor
from direct.showbase.ShowBase import ShowBase

from fps.game import gltf_patch

gltf_patch.apply()
base = ShowBase()
actor = Actor(Filename.from_os_specific(str((Path(__file__).resolve().parents[2] / 'assets' / 'guns' / 'm4_-_fps_weapon_animations_pack_v.1.glb'))))

PARTS = ['Bolt', 'BoltCatch', 'Trigger', 'Mag1', 'Mag2', 'Main', 'FPS_Camera_j_01']
nodes = {}
for p in PARTS:
    # non-skinned gun parts: the intermediate '<mesh>-parent' node is updated by the joint every frame
    np_ = actor.find(f'**/{p}_M4_D_0-parent')
    if np_.isEmpty():
        np_ = actor.exposeJoint(None, 'modelRoot', p)
    nodes[p] = np_
    print(p, 'tìm thấy' if not np_.isEmpty() else 'KHÔNG THẤY', np_.getName())


bundle = actor.getPartBundle('modelRoot')


def snapshot(clip, frame):
    actor.pose(clip, frame)
    bundle.force_update()  # actor.update() is not enough: skip it if the frame changes within the same clip
    return {p: tuple(round(v, 2) for v in n.getPos(actor)) for p, n in nodes.items()}


# real frame ranges (cue seconds * 30). Records the evidence: each part's position at the start, middle and end of the clip.
CLIPS = {  # VALID frame ranges: frame N of a clip with N frames is clamped to 0, so use the last frame N-1
    'Reload':       (1, 110),
    'Reload_Empty': (111, 224),
    'Fire':         (226, 249),
    'Holster':      (251, 268),
    'Draw':         (269, 299),
}
for clip, (a, b) in CLIPS.items():
    print(f'\n== {clip}: khung {a}..{b} ({(b - a) / 30:.2f}s)')
    for f in (a, (a + b) // 2, b):
        snap = snapshot(clip, f)
        print(f'  f{f}:', {k: snap[k] for k in ('Bolt', 'Mag1', 'Trigger')})

# total distance travelled by each part in each clip
print('\nTổng quãng đường (đơn vị model) trong từng clip:')
for clip, (a, b) in CLIPS.items():
    prev = None
    dist = {p: 0.0 for p in PARTS}
    for f in range(a, b + 1):
        snap = snapshot(clip, f)
        if prev:
            for p in PARTS:
                d = sum((snap[p][i] - prev[p][i]) ** 2 for i in range(3)) ** 0.5
                dist[p] += d
        prev = snap
    print(f'  {clip}:', {k: round(v, 1) for k, v in dist.items()})
