"""G0: loads the M4 with Actor through gltf_patch, no window opened. The axes here are Z-up (Panda default),
units in cm: z = height, negative y = forward."""
import math
from pathlib import Path

import pytest
from panda3d.core import Filename, GeomVertexReader, Thread, loadPrcFileData

from fps.game import gltf_patch
from fps.weapon_data import M4

GLB = Path(__file__).resolve().parent.parent / M4.glb

# valid frame range of each clip, taken from weapon_data (the single source), not copied here
FRAMES = {clip.anim: (clip.start, clip.end) for clip in M4.clips.values()}
NUM_FRAMES = {'Draw': 300, 'Reload': 111, 'Fire': 250, 'Reload_Empty': 225, 'Holster': 269}


@pytest.fixture(scope='module')
def actor():
    gltf_patch.apply()
    loadPrcFileData('', 'window-type none')
    loadPrcFileData('', 'audio-library-name null')
    from direct.actor.Actor import Actor
    from direct.showbase.ShowBase import ShowBase
    ShowBase()
    return Actor(Filename.from_os_specific(str(GLB)))


def pose(actor, clip, frame):
    actor.pose(clip, frame)
    actor.getPartBundle('modelRoot').force_update()


def part(actor, name):
    return actor.find(f'**/{name}_M4_D_0-parent')


def pos(node, actor):
    p = node.getPos(actor)
    return (p[0], p[1], p[2])


def dist(a, b):
    return math.dist(a, b)


def test_clips_and_frame_counts(actor):
    assert set(actor.getAnimNames()) == set(NUM_FRAMES)
    for clip, n in NUM_FRAMES.items():
        ctl = actor.getAnimControl(clip)
        assert ctl.getNumFrames() == n
        assert ctl.getFrameRate() == pytest.approx(30.0)


def test_hands_are_in_ready_pose_not_t_pose_or_scaled(actor):
    """Old bug: the hands were in a T-pose (|x| ~ 94), or 100x too big, or fell through the floor."""
    pose(actor, 'Draw', 299)
    for name in ('Hand_Mesh_Hand_D_0', 'Hand_Mesh_Glove_D_0'):
        geom = actor.find(f'**/{name}').node().get_geom(0)
        animated = geom.get_vertex_data().animate_vertices(True, Thread.get_current_thread())
        reader = GeomVertexReader(animated, 'vertex')
        pts = []
        while not reader.is_at_end():
            pts.append(reader.get_data3())
        xs, ys, zs = ([p[i] for p in pts] for i in range(3))
        assert max(abs(x) for x in xs) < 60, name   # a T-pose would be ~94
        assert 100 < min(zs) and max(zs) < 165, name  # chest/eye height, not the floor (0) or 100x
        assert max(ys) - min(ys) < 90, name


def test_gun_body_sits_at_chest_height(actor):
    pose(actor, 'Draw', 299)
    lo, hi = part(actor, 'Main').getTightBounds(actor)
    center_z = (lo[2] + hi[2]) / 2
    assert 135 < center_z < 150  # gun body ~ height 142 cm; a doubled offset would give ~0 or ~290
    assert hi[1] - lo[1] > 70     # length ~86 cm (along y)


def test_bolt_moves_during_fire(actor):
    bolt = part(actor, 'Bolt')
    pose(actor, 'Fire', FRAMES['Fire'][0])
    start = pos(bolt, actor)
    far = 0.0
    for f in range(FRAMES['Fire'][0], FRAMES['Fire'][1] + 1):
        pose(actor, 'Fire', f)
        far = max(far, dist(pos(bolt, actor), start))
    assert far > 1.5  # cm


def test_magazine_leaves_gun_during_reload(actor):
    mag = part(actor, 'Mag1')
    pose(actor, 'Reload', FRAMES['Reload'][0])
    start = pos(mag, actor)
    far = 0.0
    for f in range(FRAMES['Reload'][0], FRAMES['Reload'][1] + 1, 5):
        pose(actor, 'Reload', f)
        far = max(far, dist(pos(mag, actor), start))
    assert far > 15  # cm; the old magazine leaves the gun
    pose(actor, 'Reload', FRAMES['Reload'][1])
    assert dist(pos(mag, actor), start) < 3  # and returns to its place at the end of the clip


def test_every_mesh_has_a_color_texture(actor):
    """Old bug: only the normal map was left, so the mesh drew as flat blue."""
    from panda3d.core import TextureAttrib
    for gn in actor.find_all_matches('**/+GeomNode'):
        state = gn.node().get_geom_state(0)
        attrib = state.get_attrib(TextureAttrib)
        assert attrib is not None and attrib.get_num_on_stages() == 1
        assert attrib.get_on_stage(0).get_name() == 'Base Color'


def test_clip_table_matches_the_file(actor):
    """The clip table in weapon_data must lie within the real frame count of the animation (frame N wraps to 0)."""
    for clip in M4.clips.values():
        n = actor.getAnimControl(clip.anim).getNumFrames()
        assert 0 <= clip.start < clip.end <= n - 1, clip
    # the clip spans do not overlap on the shared timeline
    spans = sorted((c.start, c.end) for c in M4.clips.values())
    for (_, end), (start, _) in zip(spans, spans[1:]):
        assert end < start
