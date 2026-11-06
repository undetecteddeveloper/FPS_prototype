"""G8 stage 2: the Glock viewmodel glb (hands + gun + clips) loads through gltf_patch and the parts move as designed.

Frame convention (same quirk as the M4 pack, see tools/build/blender/glock_anim.py): Panda frame 0 repeats frame 1 and
frame N wraps to 0, so the usable range of a clip is 1 .. numFrames-1. Authored clip time t is Panda frame t+1.
"""
import math
from pathlib import Path

import pytest
from panda3d.core import Filename, loadPrcFileData

from fps.game import gltf_patch

GLB = Path(__file__).resolve().parent.parent / 'assets/review/glock/animation/glock_viewmodel.glb'
FRAMES = {'Idle': 61, 'IdleEmpty': 61, 'Fire': 12, 'FireLast': 12, 'Draw': 31, 'Holster': 25, 'Reload': 74, 'ReloadEmpty': 90}


@pytest.fixture(scope='module')
def actor():
    if not GLB.exists():
        pytest.skip('glock_viewmodel.glb not built')
    gltf_patch.apply()
    loadPrcFileData('', 'window-type none')
    loadPrcFileData('', 'audio-library-name null')
    from direct.actor.Actor import Actor
    from direct.showbase.ShowBase import ShowBase
    import builtins
    getattr(builtins, 'base', None) or ShowBase()
    return Actor(Filename.from_os_specific(str(GLB)))


def pos(actor, part, clip, frame, rel=True):
    """Part position in cm; relative to the gun frame (Main) so the whole-gun tilt/kick does not matter."""
    actor.pose(clip, frame)
    actor.getPartBundle('modelRoot').force_update()
    ref = actor.find('**/Main_G17_D_0-parent') if rel and part != 'Main' else actor
    p = actor.find(f'**/{part}_G17_D_0-parent').getPos(ref)
    return (p[0], p[1], p[2])


def angle(actor, part, clip, frame):
    """Rotation of a part relative to the gun frame, in degrees (for parts that pivot in place, like the trigger)."""
    actor.pose(clip, frame)
    actor.getPartBundle('modelRoot').force_update()
    ref = actor.find('**/Main_G17_D_0-parent')
    return actor.find(f'**/{part}_G17_D_0-parent').getQuat(ref).getAngle()


def test_clips_and_fps(actor):
    assert set(actor.getAnimNames()) == set(FRAMES)
    for clip, n in FRAMES.items():
        ctl = actor.getAnimControl(clip)
        assert ctl.getFrameRate() == pytest.approx(30.0)
        assert ctl.getNumFrames() == n, clip


def test_parts_are_nodes(actor):
    for part in ('Main', 'Bolt', 'Mag1', 'Mag2', 'Trigger'):
        assert not actor.find(f'**/{part}_G17_D_0-parent').isEmpty(), part


def test_fire_cycles_slide_and_trigger(actor):
    rest = pos(actor, 'Bolt', 'Fire', 1)
    back = pos(actor, 'Bolt', 'Fire', 2)
    assert math.dist(back, rest) == pytest.approx(2.6, abs=0.3)    # cm; moves along the bone's own axis, so use distance
    assert math.dist(pos(actor, 'Bolt', 'Fire', 10), rest) < 0.2   # slide is forward again
    assert abs(angle(actor, 'Trigger', 'Fire', 4) - angle(actor, 'Trigger', 'Fire', 1)) > 8   # trigger pulled (~12 deg)


def test_fire_last_keeps_slide_back(actor):
    rest = pos(actor, 'Bolt', 'Fire', 1)
    assert math.dist(pos(actor, 'Bolt', 'FireLast', 11), rest) > 2.0


def test_idle_empty_has_slide_locked(actor):
    assert math.dist(pos(actor, 'Bolt', 'IdleEmpty', 1), pos(actor, 'Bolt', 'Idle', 1)) > 2.0


@pytest.mark.parametrize('clip,last', [('Reload', 73), ('ReloadEmpty', 89)])
def test_reload_swaps_magazine(actor, clip, last):
    seated = pos(actor, 'Mag1', clip, 1)
    assert math.dist(pos(actor, 'Mag1', clip, 31), seated) > 100   # old magazine is gone (far below)
    assert math.dist(pos(actor, 'Mag1', clip, last), seated) < 0.3  # a magazine is seated again at the end
    assert math.dist(pos(actor, 'Mag2', clip, 57), seated) < 0.5    # the new one sits in the well
    assert math.dist(pos(actor, 'Mag2', clip, 1), seated) > 100    # spare magazine starts out of view


def test_reload_empty_releases_slide(actor):
    closed = pos(actor, 'Bolt', 'Idle', 1)
    assert math.dist(pos(actor, 'Bolt', 'ReloadEmpty', 1), closed) > 2.0    # starts locked back
    assert math.dist(pos(actor, 'Bolt', 'ReloadEmpty', 61), closed) > 2.0   # still locked while the magazine goes in
    assert math.dist(pos(actor, 'Bolt', 'ReloadEmpty', 81), closed) < 0.3   # released


def test_draw_and_holster_end_at_ready_pose(actor):
    ready = pos(actor, 'Main', 'Idle', 1)
    assert math.dist(pos(actor, 'Main', 'Draw', 30), ready) < 1.0
    assert math.dist(pos(actor, 'Main', 'Holster', 1), pos(actor, 'Main', 'Holster', 24)) > 10   # lowered by > 10 cm


def hand_pos(actor, joint, clip, frame):
    """Hand joint position in the gun frame (cm). Guards the 'unkeyed bones fall back to the T-pose' export bug."""
    node = actor.exposeJoint(None, 'modelRoot', joint)
    actor.pose(clip, frame)
    actor.getPartBundle('modelRoot').force_update()
    p = node.getPos(actor.find('**/Main_G17_D_0-parent'))
    return (p[0], p[1], p[2])


def test_hands_hold_the_gun_not_t_pose(actor):
    r = hand_pos(actor, 'RightHand_05', 'Idle', 1)
    assert math.dist(r, (0, 0, 0)) < 30            # T-pose would put the wrist ~70 cm to the side
    assert math.dist(hand_pos(actor, 'LeftHand_028', 'Idle', 1), (0, 0, 0)) < 40


def test_right_hand_rigid_with_gun_left_hand_moves_in_reload(actor):
    r0 = hand_pos(actor, 'RightHand_05', 'Fire', 1)
    assert math.dist(r0, hand_pos(actor, 'RightHand_05', 'Fire', 2)) < 0.5      # kick moves gun and hand together
    l0 = hand_pos(actor, 'LeftHand_028', 'Reload', 1)
    assert math.dist(l0, hand_pos(actor, 'LeftHand_028', 'Reload', 25)) > 10    # left hand goes down for the spare magazine
