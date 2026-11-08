"""Glock 17 sounds (user's recordings, 8/11/2026): the built files exist, their main transient sits where weapon_data.GLOCK_SOUND_CUES expects it, and that moment is the frame of the
matching event in the animation (measured on the glb: tools/build/prep_glock_audio.py explains how the files are cut)."""
import math
import wave
from pathlib import Path

import numpy as np
import pytest
from panda3d.core import Filename, loadPrcFileData

from fps.game import gltf_patch
from fps.weapon_data import GLOCK, AudioData

ROOT = Path(__file__).resolve().parent.parent
FPS = 30.0
ANCHOR_LEVEL = 0.40            # same rule as tools/build/prep_glock_audio.py: the first sample above 40% of the peak is the transient
FRAME_TOLERANCE = 0.08         # frames (2.7 ms): the files are cut on whole frames, so this only absorbs rounding

# the beats the user supplied: logical sound name -> (frame of the visible event in each clip). The release is the CLACK of the magazine sliding free, the magout the old magazine coming clear,
# the seat the new magazine drawn seated (Clip.swap). The release file also holds a soft click ~4.7 frames before its clack (the button press).
EVENTS = {
    'reload': {'glock_release': 26, 'glock_magout': 29, 'glock_seat': 45},
    'reload_empty': {'glock_release': 132, 'glock_magout': 135, 'glock_seat': 151},
}
SLIDE_RELEASE_FRAME = 164


def read(path: Path) -> tuple:
    with wave.open(str(path), 'rb') as w:
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype='<i2').astype(np.float64) / 32768.0
    return rate, x.reshape(-1, ch)


def anchor(path: Path) -> float:
    rate, x = read(path)
    m = np.abs(x).max(axis=1)
    return float(np.argmax(m >= ANCHOR_LEVEL * m.max())) / rate


def file_of(sound: str) -> Path:
    group = GLOCK.sound_files.get(sound, sound)
    files = sorted((ROOT / AudioData.folder).glob(f'{group}_*.wav'))
    assert files, f'no file for {sound}'
    return files[0]


# --- files and cue table ---
def test_every_glock_cue_is_sorted_inside_its_clip_and_has_a_file_and_an_underwater_twin():
    for key, cues in GLOCK.sound_cues.items():
        clip = GLOCK.clips[key]
        frames = [c.frame for c in cues]
        assert frames == sorted(frames), key
        assert all(clip.start <= f <= clip.end for f in frames), key
        for c in cues:
            f = file_of(c.sound)
            assert (ROOT / 'assets' / 'sounds' / 'foley_under' / f.name).exists(), f.name


def test_the_old_magazine_slide_in_cue_is_gone_and_the_new_beats_replace_the_three_old_ones():
    for key in ('reload', 'reload_empty'):
        names = [c.sound for c in GLOCK.sound_cues[key]]
        assert names[:3] == ['glock_release', 'glock_magout', 'glock_seat'], key
        assert not any(n in names for n in ('pistol_mag_release', 'pistol_mag_drop', 'pistol_mag_in', 'pistol_mag_seat')), key
    assert [c.sound for c in GLOCK.sound_cues['reload_empty']][-1] == 'glock_slide'
    assert [c.sound for c in GLOCK.sound_cues['reload']] == ['glock_release', 'glock_magout', 'glock_seat']


def test_the_seat_event_is_the_swap_frame():
    for key in ('reload', 'reload_empty'):
        assert EVENTS[key]['glock_seat'] == GLOCK.clips[key].swap


@pytest.mark.parametrize('key', ['reload', 'reload_empty'])
def test_cue_frame_plus_file_lead_lands_the_transient_on_the_animation_event(key):
    """Real time of the transient = (cue frame - clip.start) / 30 + the transient's place in the file; it must equal the event frame (same clip clock)."""
    for cue in GLOCK.sound_cues[key]:
        if cue.sound not in EVENTS[key]:
            continue
        hit = cue.frame + anchor(file_of(cue.sound)) * FPS
        assert hit == pytest.approx(EVENTS[key][cue.sound], abs=FRAME_TOLERANCE), (key, cue.sound, hit)


def test_the_slide_release_file_starts_on_its_impact_and_has_only_one_beat():
    """The old sound had a second, extra beat ~0.34 s after the release (user report 8/11/2026): it is cut off."""
    cue = next(c for c in GLOCK.sound_cues['reload_empty'] if c.sound == 'glock_slide')
    assert cue.frame == SLIDE_RELEASE_FRAME
    path = file_of('glock_slide')
    assert anchor(path) * FPS < 0.5
    rate, x = read(path)
    m = np.abs(x).max(axis=1)
    assert x.shape[0] / rate <= 0.25
    assert m[int(0.15 * rate):].max() < 0.10 * m.max()                 # nothing but silence after the release snap


SOURCE_SHOT = ROOT / 'assets' / 'sounds' / 'source' / 'glock' / 'single_gunshot_of_glock17-1794096011065.wav'


def test_gunshot_is_the_recorded_blast_not_the_hum_before_it():
    """First build (8/11/2026) cut inside the 0.45 s hum that precedes the blast in the source and so contained no gunshot at all: the test checked only 'starts at once', which hum satisfies."""
    assert len(GLOCK.shot_sound) == 1
    rate, x = read(ROOT / GLOCK.shot_sound[0])
    src_rate, src = read(SOURCE_SHOT)
    assert rate == src_rate and x.shape[1] == 2 and 0.45 < x.shape[0] / rate <= 0.56
    m = np.abs(x).max(axis=1)
    assert m.argmax() < 0.04 * rate                                    # the loudest sample (the blast) is right at the start
    assert m.max() == pytest.approx(0.95, abs=0.01) and np.abs(x[-1]).max() < 0.01        # no clipping, no click at the end
    # it IS the source, from the blast on (a gain and the fade at the end are the only changes): the loudest sample sits at the same place in both
    offset = int(np.abs(src).max(axis=1).argmax()) - int(m.argmax())
    n = int(0.2 * rate)
    seg = src[offset:offset + n, 0]
    assert np.corrcoef(seg, x[:n, 0])[0, 1] > 0.999

    def high(sig):                                                     # share of the energy above 6 kHz: the broken build had 28 dB less of it than the recording
        spec = np.abs(np.fft.rfft(sig * np.hanning(sig.size))) ** 2
        return spec[np.fft.rfftfreq(sig.size, 1.0 / rate) > 6000].sum() / spec.sum()
    assert high(x[:n, 0]) == pytest.approx(high(seg), rel=0.05)


# --- the animation events themselves (the frames EVENTS and the cue comments rely on) ---
@pytest.fixture(scope='module')
def actor():
    gltf_patch.apply()
    loadPrcFileData('', 'window-type none')
    loadPrcFileData('', 'audio-library-name null')
    from direct.actor.Actor import Actor
    from direct.showbase.ShowBase import ShowBase
    import builtins
    getattr(builtins, 'base', None) or ShowBase()
    return Actor(Filename.from_os_specific(str(ROOT / GLOCK.glb)))


def series(actor, key):
    """{frame: (old magazine travel from its start pose (cm), new magazine distance to the gun (cm), slide step since the previous frame (cm))} for a whole clip."""
    clip = GLOCK.clips[key]

    def rel(name):
        return actor.exposeJoint(None, 'modelRoot', name).getPos(actor) - actor.exposeJoint(None, 'modelRoot', 'Main_j_050').getPos(actor)

    out, start, prev = {}, None, None
    for f in range(clip.start, clip.end + 1):
        actor.pose(clip.anim, f)
        actor.getPartBundle('modelRoot').force_update()
        mag1, mag2, slide = rel('Mag1_j_052'), rel('Mag2_j_055'), rel('Slide_j_00')
        start = start if start is not None else mag1
        out[f] = ((mag1 - start).length(), mag2.length(), (slide - prev).length() if prev is not None else 0.0)
        prev = slide
    return out


def first(s, test):
    return next(f for f in sorted(s) if test(s[f]))


@pytest.mark.parametrize('key', ['reload', 'reload_empty'])
def test_release_clack_magout_and_seat_match_the_magazine_motion(actor, key):
    s = series(actor, key)
    ev = EVENTS[key]
    moving = first(s, lambda v: v[0] >= 4.2)            # the old magazine starts to slide out: the button press just before
    well = first(s, lambda v: v[0] >= 6.0)
    clear = first(s, lambda v: v[0] >= 12.0)
    out = first(s, lambda v: v[0] >= 17.0)              # fully pulled out: it stops
    assert well <= ev['glock_release'] <= clear, (key, well, clear)                         # the clack falls while the magazine slides out of the well
    click = ev['glock_release'] - 4.7                                                       # the soft click inside the release file
    assert abs(click - moving) <= 2.0, (key, click, moving)
    assert abs(ev['glock_magout'] - out) <= 1, (key, out)
    seated = first(s, lambda v: v[1] < 6.5)
    assert seated - 1 <= ev['glock_seat'] <= seated + 1, (key, seated)                      # the new magazine bottoms out at the swap frame (+-1)
    assert s[ev['glock_seat'] - 3][1] > 10.0                                                # ... after being clearly outside the gun a moment before


def test_the_slide_jumps_forward_on_the_slide_release_frame(actor):
    s = series(actor, 'reload_empty')
    assert first(s, lambda v: v[2] > 3.0) == SLIDE_RELEASE_FRAME
    assert math.isclose(max(v[2] for v in s.values()), s[SLIDE_RELEASE_FRAME][2])
