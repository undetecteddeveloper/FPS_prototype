"""Benelli M1014 (9/11/2026): the shotgun's data, its tube-magazine reload logic (pure: no window), the pattern / drag maths and the converted model.
The real-game side (pellets from Combat, the reload sound once per shell, the click that interrupts the reload) is tools/measure/m1014_check.py."""
import dataclasses
import json
import math
import random
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from fps.core.ballistics import advance
from fps.core.handling import Handling, Phase
from fps.core.headcam import ReloadState, glance_weight
from fps.core.spread import angle_between, random_in_cone
from fps.core.weapon import Weapon
from fps.weapon_data import GLOCK, GUNS, M1014, M4, AudioData, Clip, HeadCamData, ReloadData, SoundCue, is_reload_key

ROOT = Path(__file__).resolve().parent.parent
GLB = ROOT / M1014.glb
FPS = 30.0


# the engine still supports a tube gun that chains one-shell cycles and alternates two hand paths (the M1014 itself now uses the long clip for 6 rounds or fewer and ONE cycle for 7):
# this variant is the old setup, so the chain logic stays tested
CHAIN = dataclasses.replace(M1014, reload_full_max=-1, clips={**M1014.clips, 'reload_alt': Clip('Rig|M4_ReloadOne_type1', 0, 44, swap=21, settle=41)})


def make(mag=2, reserve=20, gun=None, **reload_kw):
    gun = gun or M1014
    gun = dataclasses.replace(gun, reload=ReloadData(**reload_kw)) if reload_kw else gun
    w = Weapon(gun)
    w.mag, w.reserve = mag, reserve
    return Handling(gun, w), w


def run(h, seconds, fps=60.0):
    for _ in range(round(seconds * fps)):
        h.update(1.0 / fps)


# --- the data ---
def test_the_m1014_is_registered_and_is_a_semi_auto_tube_shotgun():
    assert GUNS['m1014'] is M1014
    assert M1014.shell_reload and not M1014.selective_fire and not M1014.full_auto
    assert M1014.pellets == 9 and M1014.magazine == 8 and M1014.reserve >= 24
    assert 0.0 < M1014.pellet_spread < 5.0 and M1014.bullet_drag > 0.0 and 300.0 < M1014.muzzle_velocity < 500.0
    assert M4.pellets == 1 and M4.bullet_drag == 0.0 and M4.selective_fire and not M4.shell_reload          # the other guns keep their behaviour
    assert 'Cransh' in M1014.credit and 'CC BY' in M1014.credit                                             # the pack's licence asks for the author's name


def test_every_clip_is_inside_its_animation_and_every_swap_frame_inside_its_clip():
    for key, clip in M1014.clips.items():
        assert clip.start <= clip.end, key
        if clip.settle is not None:
            assert clip.start < clip.settle <= clip.end, key
        frames = clip.swaps or (() if clip.swap is None else (clip.swap,))
        assert all(clip.start < f <= (clip.settle or clip.end) for f in frames), key            # a round goes in before the hands are back
    assert M1014.clips['reload_empty'].swaps and len(M1014.clips['reload_empty'].swaps) == M1014.magazine
    assert M1014.clips['reload'].swap and 'reload_alt' not in M1014.clips and M1014.clips['reload'].anim.endswith('ReloadOne_type2') and M1014.clips['reload_empty'].anim.endswith('ReloadFull_type1')
    tail = M1014.clips['reload_empty'].tail
    assert tail and M1014.clips['reload_empty'].swaps[-2] < tail < M1014.clips['reload_empty'].swaps[-1]       # the jump lands after the last shell and before the bolt closes
    assert sorted(M1014.clips['reload_empty'].swaps) == list(M1014.clips['reload_empty'].swaps)


def test_the_cue_table_follows_the_clips_and_every_sound_has_a_file_and_an_underwater_twin():
    files = {**AudioData().sound_files, **M1014.sound_files}
    for key, cues in M1014.sound_cues.items():
        clip = M1014.clips[key]
        frames = [c.frame for c in cues]
        assert frames == sorted(frames), key
        assert all(clip.start <= f <= clip.end for f in frames), key
        for c in cues:
            group = files.get(c.sound, c.sound)
            found = sorted((ROOT / AudioData.folder).glob(f'{group}_*.wav'))
            assert found, f'{c.sound}: no file {group}_*.wav'
            assert (ROOT / 'assets' / 'sounds' / 'foley_under' / found[0].name).exists(), found[0].name
    assert set(M1014.sound_cues) == {'reload', 'reload_empty'}                                    # no draw / holster sounds (user, 9/11/2026)
    slider = [c for c in M1014.sound_cues['reload_empty'] if c.sound == 'm1014_slider']
    assert len(slider) == 1 and slider[0].frame >= M1014.clips['reload_empty'].tail      # not skipped by the jump


def test_shake_beats_land_on_the_shell_frames():
    for key in ('reload', 'reload_empty'):
        clip = M1014.clips[key]
        frames = [f for f, kind in M1014.shake.reload_beats[key] if kind == 'seat']
        assert frames == list(clip.swaps or (clip.swap,))[:len(frames)], key


# --- the sound files: ONLY the first beat of the user's reload recording, one clack per shell ---
def read(path: Path) -> tuple:
    with wave.open(str(path), 'rb') as w:
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype='<i2').astype(np.float64) / 32768.0
    return rate, x.reshape(-1, ch)


SOURCE = ROOT / 'assets' / 'sounds' / 'source' / 'm1014'


def test_the_shell_sound_is_the_first_beat_only_and_its_clack_sits_where_the_cues_expect_it():
    rate, x = read(ROOT / 'assets' / 'sounds' / 'foley' / 'm1014_shell_0.wav')
    src_rate, src = read(SOURCE / 'Beneli_M1014_reload_sound.wav')
    assert rate == src_rate and x.shape[1] == 1
    assert 0.15 < x.shape[0] / rate < 0.4                                    # one beat (0.24 s), not the whole 2 s recording with its second beat
    m = np.abs(x[:, 0])
    assert m.max() == pytest.approx(0.90, abs=0.01) and m[-1] < 0.01 and m[0] < 0.01          # normalised, faded in and out: no click
    t_clack = float(np.argmax(m >= 0.40 * m.max())) / rate
    assert t_clack * FPS == pytest.approx(4.0, abs=0.1)                      # the clack 4 whole frames after the start: M1014_SOUND_CUES counts on it
    # it is the first beat of the source: the clack of the file sits at ~0.58 s of the recording, the second beat (1.17 s on) is not in the file
    mono = src.mean(axis=1)
    window = np.abs(mono[int(0.40 * rate):int(1.00 * rate)])                 # the same rule as tools/build/prep_m1014_audio.py: the first sample above 40% of the window's peak
    anchor = 0.40 + float(np.argmax(window >= 0.40 * window.max())) / rate
    start = int(round((anchor - 4 / FPS) * rate))
    seg = mono[start:start + x.shape[0]]
    assert np.corrcoef(seg, x[:, 0])[0, 1] > 0.95
    assert float(np.abs(mono[int(1.0 * rate):int(1.5 * rate)]).max()) > 0.2   # (the source does have a second, loud beat: the file left it out)


def test_each_shell_cue_lands_the_clack_one_frame_before_the_shell_seats():
    for key in ('reload', 'reload_empty'):
        clip = M1014.clips[key]
        swaps = list(clip.swaps or (clip.swap,))
        shell_cues = [c.frame for c in M1014.sound_cues[key] if c.sound == 'm1014_shell']
        expect = [f - 5 for f in (swaps[:-1] if key == 'reload_empty' else swaps)]       # the last round of the long clip is the bolt closing on the chamber: no shell sound
        assert shell_cues == expect, key
        for c in shell_cues:
            assert c + 4 + 1 in swaps                                        # the file's clack (4 frames in) + 1 frame = the shell is seated


def test_the_slider_sound_is_the_users_file_cut_to_the_slam_and_lands_when_the_bolt_closes():
    rate, x = read(ROOT / 'assets' / 'sounds' / 'foley' / 'm1014_slider_0.wav')
    src_rate, src = read(SOURCE / 'Benelli_M1014_slider.wav')
    assert rate == src_rate and x.shape[1] == 1 and 0.4 < x.shape[0] / rate < 0.8       # the click, the slam and the tail; the extra sound at 1.75 s is not in it
    m = np.abs(x[:, 0])
    assert m.max() == pytest.approx(0.90, abs=0.01) and m[-1] < 0.01
    slam = float(np.argmax(m >= 0.40 * m.max())) / rate
    assert slam * FPS == pytest.approx(10.0, abs=0.1)
    cue = next(c for c in M1014.sound_cues['reload_empty'] if c.sound == 'm1014_slider')
    assert cue.frame + 10 == 187                                                      # the slider is home at frame 187 of ReloadFull (-0.8 at 186, -0.3 at 189)


def test_the_gunshot_starts_on_the_blast_and_keeps_its_tail():
    rate, x = read(ROOT / M1014.shot_sound[0])
    m = np.abs(x).max(axis=1)
    assert x.shape[1] == 2 and 0.6 < x.shape[0] / rate < 0.95
    assert m.argmax() < 0.04 * rate                                         # the loudest sample is right at the start (the source has 1.14 s of near silence first)
    assert m.max() == pytest.approx(0.95, abs=0.01) and np.abs(x[-1]).max() < 0.01
    src_rate, src = read(SOURCE / 'Benelli_M1014_fire_sound.wav')
    offset = int(np.abs(src).max(axis=1).argmax()) - int(m.argmax())
    n = int(0.2 * rate)
    assert np.corrcoef(src[offset:offset + n, 0], x[:n, 0])[0, 1] > 0.999    # it IS the source from the blast on
    assert M1014.shot_pool * 60.0 / M1014.rpm >= x.shape[0] / rate - 0.01    # the rotation of playback copies outlasts the sound: a new shot never cuts the previous one


# --- the tube-magazine reload ---
def test_a_weapon_loads_one_round_at_a_time_from_the_reserve():
    w = Weapon(M1014)
    w.mag, w.reserve = 7, 1
    assert w.load_shell() == 1 and (w.mag, w.reserve) == (8, 0)
    assert w.load_shell() == 0                                               # full (and no reserve either)
    w.mag, w.reserve = 3, 0
    assert w.load_shell() == 0 and w.mag == 3                                # nothing left to load


def test_the_b_key_does_nothing_on_a_semi_only_gun_and_still_toggles_on_the_others():
    w = Weapon(M1014)
    w.toggle_mode()
    assert w.auto is False
    w = Weapon(M4)
    auto = w.auto
    w.toggle_mode()
    assert w.auto is not auto


def test_reload_chains_one_shell_cycles_until_the_tube_is_full():
    h, w = make(mag=2, reserve=20, gun=CHAIN)
    assert h.start_reload() and h.key == 'reload'
    run(h, 20.0)
    events = h.drain()
    kinds = [e[0] for e in events]
    assert w.mag == 8 and w.reserve == 14                                    # six shells, one per cycle
    assert kinds.count('swap') == 6 and kinds.count('chain') == 5 and kinds.count('start') == 6
    assert kinds[-1] == 'ready' and 'done' not in kinds[:-1] and kinds[:-1].count('ready') == 0   # no 'ready' in between: the gun never counts as ready mid-chain
    starts = [e for e in events if e[0] == 'start']
    assert [s[1] for s in starts] == ['reload', 'reload_alt'] * 3            # the two hand paths alternate
    assert [s[3] for s in starts] == [True] * 5 + [False]                    # every start says whether another cycle follows
    assert not h.busy


def test_the_first_and_last_cycle_flags_follow_the_chain():
    h, w = make(mag=5, reserve=20, gun=CHAIN, speed=1.0)
    h.start_reload()
    assert h.first and not h.last                                            # 5 -> 8 needs three cycles
    run(h, M1014.clips['reload'].settle_time + 0.05)                         # the second cycle has begun
    assert h.cycle == 1 and not h.first and not h.last
    run(h, 12.0)
    assert not h.busy
    h2, _ = make(mag=7, reserve=20, gun=CHAIN)
    h2.start_reload()
    assert h2.first and h2.last                                              # a single shell: both


def test_each_round_counts_at_its_own_frame_and_cancelling_keeps_the_ones_already_in():
    h, w = make(mag=7, reserve=20, speed=1.0)
    h.start_reload()
    run(h, M1014.clips['reload'].swap_time - 0.05)
    assert w.mag == 7                                                        # the shell has not gone in yet
    run(h, 0.1)
    assert w.mag == 8 and w.reserve == 19
    assert h.cancel() and w.mag == 8 and not h.busy                          # the round that is in stays


def test_an_empty_gun_with_a_full_reserve_plays_the_long_clip_and_loads_all_eight():
    h, w = make(mag=0, reserve=32)
    h.start_reload()
    assert h.key == 'reload_empty'
    run(h, 20.0)
    kinds = [e[0] for e in h.drain()]
    assert w.mag == 8 and w.reserve == 24 and kinds.count('swap') == 8 and kinds[-1] == 'ready' and 'chain' not in kinds


def test_the_clip_is_chosen_by_the_rounds_left_seven_uses_type2_six_or_fewer_the_long_clip():
    """The user's rule (9/11/2026): one shot fired (7 left) -> ReloadOne_type2; more shots fired (6 or fewer) or empty -> ReloadFull_type1."""
    for mag, key in ((7, 'reload'), (6, 'reload_empty'), (5, 'reload_empty'), (3, 'reload_empty'), (1, 'reload_empty'), (0, 'reload_empty')):
        h, _ = make(mag=mag, reserve=20)
        assert h.start_reload() and h.key == key, mag
    h, w = make(mag=7, reserve=20)
    h.start_reload()
    run(h, 20.0)
    kinds = [e[0] for e in h.drain()]
    assert w.mag == 8 and kinds == ['start', 'swap', 'ready']               # one shell, one clip, no chain


def test_a_partly_empty_gun_stops_the_long_clip_when_it_is_full_and_skips_the_shells_it_does_not_need():
    h, w = make(mag=3, reserve=20, speed=1.0)
    h.start_reload()
    run(h, 30.0)
    events = h.drain()
    kinds = [e[0] for e in events]
    assert (w.mag, w.reserve) == (8, 15) and not h.busy                      # 5 shells needed
    seek = next(e for e in events if e[0] == 'seek')
    assert seek[1] == 'reload_empty' and seek[2] == M1014.clips['reload_empty'].tail
    assert kinds.count('seek') == 1 and kinds[-1] == 'ready'
    clip = M1014.clips['reload_empty']
    # the reload took 5 shells + the closing of the bolt, not the whole 7: it ended well before the full clip's length
    full, _ = make(mag=0, reserve=20, speed=1.0)
    full.start_reload()
    t_full = t_part = 0.0
    while full.busy and t_full < 30:
        full.update(1 / 60)
        t_full += 1 / 60
    h2, _ = make(mag=3, reserve=20, speed=1.0)
    h2.start_reload()
    while h2.busy and t_part < 30:
        h2.update(1 / 60)
        t_part += 1 / 60
    assert t_part < t_full - 1.5, (t_part, t_full)


def test_an_empty_gun_with_a_short_reserve_loads_what_there_is_and_closes_the_bolt():
    h, w = make(mag=0, reserve=3, speed=1.0)
    h.start_reload()
    assert h.key == 'reload_empty'
    run(h, 30.0)
    kinds = [e[0] for e in h.drain()]
    assert (w.mag, w.reserve) == (3, 0) and not h.busy and 'seek' in kinds


def test_a_full_gun_or_an_empty_reserve_does_not_start_a_reload():
    h, _ = make(mag=8, reserve=20)
    assert not h.start_reload()
    h, _ = make(mag=3, reserve=0)
    assert not h.start_reload()


def test_a_magazine_gun_still_emits_the_old_three_item_start_event():
    from fps.core.handling import Handling as H
    w = Weapon(M4)
    w.mag = 5
    h = H(M4, w)
    h.start_reload()
    assert h.drain()[0] == ('start', 'reload', 1.0)


def test_the_reload_keys_are_recognised():
    assert all(is_reload_key(k) for k in ('reload', 'reload_alt', 'reload_empty')) and not any(is_reload_key(k) for k in (None, 'draw', 'fire', 'holster', 'fire_last'))


# --- the head's glance holds across the chain ---
def test_the_glance_opens_in_the_first_cycle_and_closes_in_the_last_only():
    d = HeadCamData()
    clip = M1014.clips['reload']
    settle = (clip.settle - clip.start) / FPS
    mid_cycle = ReloadState(clip, settle + 0.2, 1.0, first=False, last=False)
    assert glance_weight(d, mid_cycle) == pytest.approx(1.0)                 # a later cycle: the head is already down and stays there
    assert glance_weight(d, ReloadState(clip, 0.0, 1.0, first=False, last=False)) == pytest.approx(1.0)
    only = ReloadState(clip, 0.0, 1.0)
    assert glance_weight(d, only) == 0.0                                     # first cycle: starts from 0
    late = ReloadState(clip, settle + 0.3, 1.0, first=False, last=True)
    assert glance_weight(d, late) < 1.0                                      # the last cycle lets the head come up


# --- the pattern and the drag ---
def test_pellets_stay_in_the_cone_and_a_bias_pulls_them_toward_the_middle():
    rng = random.Random(3)
    aim = (0.0, 0.0, 1.0)
    flat = [angle_between(random_in_cone(aim, 2.0, rng), aim) for _ in range(4000)]
    biased = [angle_between(random_in_cone(aim, 2.0, rng, 0.6), aim) for _ in range(4000)]
    assert max(flat) <= 2.0 + 1e-6 and max(biased) <= 2.0 + 1e-6
    assert np.mean(flat) == pytest.approx(2.0 * 2 / 3, abs=0.05)             # a uniform disc: the mean radius is 2/3 of the edge
    assert np.mean(biased) < np.mean(flat) - 0.15
    assert random_in_cone(aim, 0.0, rng, 0.6) == aim


def test_drag_slows_the_pellet_like_exp_and_does_not_depend_on_the_frame_rate():
    def fly(fps, seconds=0.5, drag=1.8):
        pos, vel = (0.0, 10.0, 0.0), (0.0, 0.0, 400.0)
        for _ in range(round(seconds * fps)):
            pos, vel = advance(pos, vel, 9.81, 1.0 / fps, drag)
        return pos, vel
    (p60, v60), (p240, v240) = fly(60), fly(240)
    assert v60[2] == pytest.approx(400.0 * math.exp(-1.8 * 0.5), rel=1e-9)
    assert p60 == pytest.approx(p240, rel=1e-9) and v60 == pytest.approx(v240, rel=1e-9)
    assert p60[2] == pytest.approx(400.0 * (1.0 - math.exp(-0.9)) / 1.8, rel=1e-9)       # the distance the drag lets it cover
    assert advance((0, 0, 0), (1, 2, 3), 9.81, 0.1, 0.0) == advance((0, 0, 0), (1, 2, 3), 9.81, 0.1)    # no drag: the plain arc of every other gun
    pos, vel = (0.0, 100.0, 0.0), (0.0, 0.0, 0.0)
    for _ in range(60 * 30):
        pos, vel = advance(pos, vel, 9.81, 1 / 60, 1.8)
    assert vel[1] == pytest.approx(-9.81 / 1.8, rel=1e-3)                                  # falls at the terminal speed


# --- the F1 panel ---
def test_the_shotgun_numbers_sit_in_the_shared_tabs_not_a_tab_of_their_own():
    from fps.core.params import ParamStore
    from fps.weapon_data import GameParams
    store = ParamStore(GameParams(gun=dataclasses.replace(M1014)), gun_key='m1014')
    assert 'shotgun' not in store.group_by_key                                # the user wanted the same tabs as the M4 and the Glock (9/11/2026)
    for sid in ('gun.pellets', 'gun.pellet_spread', 'gun.pellet_center_bias', 'gun.pellet_tracers', 'gun.bullet_drag'):
        assert store.by_id[sid].group == 'fire', sid
    assert store.by_id['gun.reload.interrupt_fire'].group == 'reload'
    assert store.get(store.by_id['gun.pellets']) == 9 and store.get(store.by_id['gun.pellet_spread']) == M1014.pellet_spread
    assert store.is_default(store.by_id['gun.pellets'])
    store.set(store.by_id['gun.pellets'], 12)
    assert store.get(store.by_id['gun.pellets']) == 12 and not store.is_default(store.by_id['gun.pellets'])
    assert store.reset(store.by_id['gun.pellets']) and store.get(store.by_id['gun.pellets']) == 9


def test_a_shotgun_has_no_aim_and_the_m4_hands_are_drawn_without_the_pack_normal_maps():
    assert not M1014.can_ads and M4.can_ads and GLOCK.can_ads
    assert set(M4.flat_normal) == {'Hand_D', 'Glove_D'} and not GLOCK.flat_normal and not M1014.flat_normal


# --- the converted model (tools/build/prep_benelli_glb.py) ---
def glb_json() -> dict:
    with open(GLB, 'rb') as f:
        f.read(12)
        n = struct.unpack('<I', f.read(4))[0]
        f.read(4)
        return json.loads(f.read(n))


def test_the_converted_glb_is_small_and_has_no_texture_transform_left():
    data = glb_json()
    assert GLB.stat().st_size < 25_000_000                                  # the 66 MB original with its 4096 x 4096 textures stays out of the game
    assert 'KHR_texture_transform' not in json.dumps(data['materials']) and 'KHR_texture_transform' not in (data.get('extensionsUsed') or [])   # the shader reads raw UVs: the 180 degree rotation is baked into the images
    names = [a['name'] for a in data['animations']]
    for clip in M1014.clips.values():
        assert clip.anim in names, clip.anim
    assert {m['name'] for m in data['materials']} == {'sleeve_st6_generalist', 'glove_hardknuckle', '12gauge', 'TTI_Benelli_M4', 'matchsaverz'}
    # the gun meshes were authored ~82x too large next to the hands: after the conversion their vertices are a few tens of units, like the hands'
    gun = [m for m in data['meshes'] if m['name'].startswith('benelli_m4_')]
    assert len(gun) == 3
    for mesh in gun:
        for prim in mesh['primitives']:
            acc = data['accessors'][prim['attributes']['POSITION']]
            assert max(abs(v) for v in acc['min'] + acc['max']) < 50.0, mesh['name']


@pytest.fixture(scope='module')
def actor():
    from panda3d.core import Filename, loadPrcFileData
    from fps.game import gltf_patch
    gltf_patch.apply()
    loadPrcFileData('', 'window-type none')
    loadPrcFileData('', 'audio-library-name null')
    from direct.actor.Actor import Actor
    from direct.showbase.ShowBase import ShowBase
    import builtins
    getattr(builtins, 'base', None) or ShowBase()
    return Actor(Filename.from_os_specific(str(GLB)))


def test_the_model_loads_with_every_clip_at_the_expected_length(actor):
    expected = {'Rig|M4_Idle': 90, 'Rig|M4_Fire': 20, 'Rig|M4_Fire_LastRoundCheck': 65, 'Rig|M4_ReloadOne_type1': 50, 'Rig|M4_ReloadOne_type2': 57, 'Rig|M4_ReloadFull_type1': 212}
    for anim, frames in expected.items():
        ctl = actor.getAnimControl(anim)
        assert ctl.getNumFrames() == frames and ctl.getFrameRate() == pytest.approx(30.0), anim
    for clip in M1014.clips.values():
        assert clip.end <= actor.getAnimControl(clip.anim).getNumFrames() - 1, clip        # the last valid frame of a clip of N frames is N - 1
    joints = {j.getName() for j in actor.getJoints()}
    assert {M1014.eye_joint, M1014.hand_joint, 'Main_054', 'Slider_055', 'Load_056', 'Shell_058'} <= joints
    assert not actor.find('**/' + M1014.reload_props[0]).is_empty()


def test_the_scaled_gun_is_a_metre_long_and_sits_in_the_hands(actor):
    """The animated vertices of the body in metres (model_scale applied): ~1 m long (a Benelli M4 is 0.89-1.04 m), the front sight near the hands' reach, hands within half a metre of the receiver."""
    from panda3d.core import GeomVertexReader, Thread
    actor.pose('Rig|M4_Idle', 0)
    actor.getPartBundle('modelRoot').force_update()

    def points(name):
        geom = actor.find(f'**/{name}').node().get_geom(0)
        data = geom.get_vertex_data().animate_vertices(True, Thread.get_current_thread())
        r = GeomVertexReader(data, 'vertex')
        out = []
        while not r.is_at_end():
            p = r.get_data3()
            out.append((p[0], p[1], p[2]))
        return np.array(out) * M1014.model_scale

    body = points('benelli_m4_TTI_Benelli_M4_0_TTI_Benelli_M4_0')
    length = body[:, 2].max() - body[:, 2].min()                            # (the skinned file keeps the authoring axes until Viewmodel applies model_hpr: the long axis is z here)
    assert 0.9 < length < 1.1, length
    glove = points('hardknuckle_glove_hardknuckle_0')
    centre = (body.min(axis=0) + body.max(axis=0)) / 2
    assert np.linalg.norm(glove.mean(axis=0) - centre) < 0.5
