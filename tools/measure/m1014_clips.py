r"""Benelli M1014: reads the animation file's parts frame by frame to find the moments the sounds and the round counting are tied to (weapon_data.M1014: Clip.swap / Clip.swaps, M1014_SOUND_CUES).
Opens no window. For each clip prints, every `--step` frames, the position of the slider (bolt), the loader, the hand-held shell and the left hand RELATIVE TO the gun body (`Main_054`),
in model units as (forward, up, right) of the gun, plus the body's own place. The hand-held shell reaches its final spot in the loading port (it stops moving, close to the body) when a round goes in.

  ReloadOne_type1: shell fetched 0-12, at the port 12-21, pushed in by 21 (Shell-Main settles near (-0.6, -0.5, 0.5)); type2: pushed in by 27
  ReloadFull: slider back (-5.2) the whole clip; shells in at 21 48 72 96 123 147 171; the slider closes at 186 (-5.2 -> -0.3)
  Fire_LastRoundCheck: slider stays at -5.3 after frame 3 (the bolt locked open); Fire: the slider goes back at 3 and is home by 6

Run:  .venv\Scripts\python.exe -X utf8 tools\measure\m1014_clips.py [--step 3] [Rig|M4_ReloadOne_type1 ...]       (no clip names: all of them)
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from panda3d.core import Filename, loadPrcFileData  # noqa: E402

loadPrcFileData('', 'window-type none')
loadPrcFileData('', 'audio-library-name null')

from direct.actor.Actor import Actor  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402

from fps.game import gltf_patch  # noqa: E402
from fps.weapon_data import M1014  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('clips', nargs='*')
ap.add_argument('--step', type=int, default=3)
args = ap.parse_args()

gltf_patch.apply()
base = ShowBase()
actor = Actor(Filename.from_os_specific(str(ROOT / M1014.glb)))
bundle = actor.getPartBundle('modelRoot')
JOINTS = ['Main_054', 'Slider_055', 'Load_056', 'Shell_058', M1014.hand_joint]
nodes = {n: actor.exposeJoint(None, 'modelRoot', n) for n in JOINTS}
UNIT = 0.088          # the Panda skeleton is the pack's units x 0.088 (see docs/notes/m1014.md)


def rel(a: str, b: str) -> tuple:
    """Position of joint a relative to joint b in the gun's own axes: forward = -Z, up = -Y, right = -X of the Panda actor frame (before Viewmodel's model_hpr)."""
    d = nodes[a].getPos(actor) - nodes[b].getPos(actor)
    return (-d.z / UNIT, -d.y / UNIT, -d.x / UNIT)


for anim in args.clips or [a for a in actor.getAnimNames() if a not in ('Rig|M4_Walk', 'Rig|M4_Run')]:
    n = actor.getAnimControl(anim).getNumFrames()
    print(f'\n== {anim}: {n} frames')
    print('frame | slider-Main (fwd up right) | loader-Main | shell-Main | handL-Main | Main (abs)')
    for f in list(range(0, n, args.step)) + [n - 1]:
        actor.pose(anim, f)
        bundle.force_update()
        cols = [rel(j, 'Main_054') for j in ('Slider_055', 'Load_056', 'Shell_058', M1014.hand_joint)]
        m = nodes['Main_054'].getPos(actor)
        print(f'{f:4d} | ' + ' | '.join('%5.1f %5.1f %5.1f' % c for c in cols) + ' | %5.1f %5.1f %5.1f' % (-m.z / UNIT, -m.y / UNIT, -m.x / UNIT))
