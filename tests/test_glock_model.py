"""Glock 17 pack (assets/guns/glock17.glb) loads through gltf_patch: both skins on one Character, gun parts driven by the animation, clips match weapon_data."""
import math
from pathlib import Path

import pytest
from panda3d.core import Filename, loadPrcFileData

from fps.game import gltf_patch
from fps.weapon_data import GLOCK

GLB = Path(__file__).resolve().parent.parent / GLOCK.glb
NUM_FRAMES = {'Reload': 85, 'ReloadEmpty': 198, 'Fire': 106, 'Holster': 212, 'Draw': 246, 'Idle': 85}


@pytest.fixture(scope='module')
def actor():
    gltf_patch.apply()
    loadPrcFileData('', 'window-type none')
    loadPrcFileData('', 'audio-library-name null')
    from direct.actor.Actor import Actor
    from direct.showbase.ShowBase import ShowBase
    import builtins
    getattr(builtins, 'base', None) or ShowBase()
    return Actor(Filename.from_os_specific(str(GLB)))


def pose(actor, clip, frame):
    actor.pose(clip, frame)
    actor.getPartBundle('modelRoot').force_update()


def joint_pos(actor, name):
    p = actor.exposeJoint(None, 'modelRoot', name).getPos(actor)
    return (p[0], p[1], p[2])


def test_clips_and_frame_counts(actor):
    assert set(actor.getAnimNames()) == set(NUM_FRAMES)
    for clip, n in NUM_FRAMES.items():
        ctl = actor.getAnimControl(clip)
        assert ctl.getNumFrames() == n
        assert ctl.getFrameRate() == pytest.approx(30.0)


def test_clip_ranges_in_weapon_data_fit_inside_the_file(actor):
    """A clip of N frames wraps frame N to 0: the last usable frame is N - 1."""
    for key, clip in GLOCK.clips.items():
        assert 1 <= clip.start < clip.end <= NUM_FRAMES[clip.anim] - 1, key
    for anim, frame in (GLOCK.ready_pose, GLOCK.locked_pose):
        assert 0 <= frame <= NUM_FRAMES[anim] - 1


def test_both_skins_load_and_meshes_are_present(actor):
    names = {n.get_name() for n in actor.find_all_matches('**/+GeomNode')}
    for want in ('Hand_Mesh_Hand_D_0', 'Hand_Mesh_Glove_D_0', 'Main_Glock_D_0', 'Slide_Glock_D_0', 'Mag1_Glock_D_0', 'Mag2_Glock_D_0'):
        assert want in names, want


def test_eye_joint_exists_and_the_gun_is_in_front_of_it(actor):
    """Old bug: the gun parts were not joints, so they never moved and the eye joint was missing (the file's animation root is above the skin)."""
    pose(actor, *GLOCK.ready_pose)
    eye = joint_pos(actor, GLOCK.eye_joint)
    slide = joint_pos(actor, 'Slide_j_00')
    assert eye[2] > 140 and 5 < math.dist(eye, slide) < 40          # cm, Z up: the eye is ~153 cm up, the slide 10-30 cm away


def test_slide_is_locked_back_in_reload_empty_and_forward_in_ready_pose(actor):
    def slide_back(anim, frame):
        pose(actor, anim, frame)
        return joint_pos(actor, 'Slide_j_00')[1] - joint_pos(actor, 'Main_j_050')[1]
    ready, locked = slide_back(*GLOCK.ready_pose), slide_back(*GLOCK.locked_pose)
    assert locked - ready > 3.0                                      # cm: the locked slide sits at least 3 cm further back (Panda +y = backward here)


def test_the_pack_alternates_two_magazines_between_its_clips(actor):
    """Mag2 is seated in the ready pose (Mag1 parked far away); the locked-slide pose and the start of both reload clips seat Mag1 instead.
    Viewmodel._update_mags draws only the seated one, so GunData.mag_nodes must list them in that order."""
    def to_main(anim, frame, mag):
        pose(actor, anim, frame)
        return math.dist(joint_pos(actor, mag), joint_pos(actor, 'Main_j_050'))
    assert to_main(*GLOCK.ready_pose, 'Mag2') < 6 < 30 < to_main(*GLOCK.ready_pose, 'Mag1')
    for anim, frame in (GLOCK.locked_pose, ('Reload', 1)):
        assert to_main(anim, frame, 'Mag1') < 8 and to_main(anim, frame, 'Mag2') > 30, (anim, frame)


def test_the_new_magazine_seats_at_swap_in_both_reload_clips(actor):
    for key in ('reload', 'reload_empty'):
        clip = GLOCK.clips[key]
        pose(actor, clip.anim, clip.swap)
        assert math.dist(joint_pos(actor, 'Mag2'), joint_pos(actor, 'Main_j_050')) < 6, key


def test_magazine_node_globs_each_match_a_magazine_and_its_round(actor):
    for glob in GLOCK.mag_nodes:
        assert len(list(actor.find_all_matches('**/' + glob))) == 2, glob
