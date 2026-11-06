import wave

import pytest

from tools.build import prep_foley as pf

ALL = [(name, i) for name, (variants, _, _) in pf.SOUNDS.items() for i in range(variants)]


@pytest.fixture(scope='module')
def rendered():
    return {key: pf.render(*key) for key in ALL}


def test_every_group_has_enough_variants():
    for name in ('step_walk', 'step_run'):
        assert pf.SOUNDS[name][0] >= 4                                  # 4-6 variants per footstep type
    assert pf.SOUNDS['land'][0] >= 3


def test_render_is_deterministic():
    assert pf.render('step_walk', 0) == pf.render('step_walk', 0)
    assert pf.render('bolt_release', 1) == pf.render('bolt_release', 1)


def test_variants_really_differ(rendered):
    for name, (variants, _, _) in pf.SOUNDS.items():
        waves = [rendered[(name, i)] for i in range(variants)]
        n = min(len(w) for w in waves)
        for i in range(variants):
            for j in range(i + 1, variants):
                diff = sum(abs(a - b) for a, b in zip(waves[i][:n], waves[j][:n])) / n
                assert diff > 0.01, (name, i, j)


def test_no_clipping_no_pop_no_dead_air(rendered):
    for (name, i), x in rendered.items():
        peak = max(abs(v) for v in x)
        target = pf.SOUNDS[name][2]
        assert peak == pytest.approx(target, abs=0.002), (name, i)
        assert peak < 0.98                                              # leaves headroom below full scale
        assert abs(x[0]) < 1e-3 and abs(x[-1]) < 1e-3, (name, i)       # starts and ends at 0: no pop
        assert abs(sum(x) / len(x)) < 0.01 * peak, (name, i)            # no DC offset
        assert 0.04 < len(x) / pf.RATE < 0.7, (name, i)                 # reasonable length (not silent, not dragged out)
        rms = (sum(v * v for v in x) / len(x)) ** 0.5
        assert rms > 0.02, (name, i)                                    # not an almost-silent sound


def test_tail_decays_before_the_fade(rendered):
    """The last 10 ms fades out from an already low level, not cut off mid-way while still loud."""
    fade = pf.n_of(pf.FADE_OUT)
    for (name, i), x in rendered.items():
        peak = max(abs(v) for v in x)
        assert max(abs(v) for v in x[-fade - pf.n_of(0.004):-fade]) < 0.12 * peak, (name, i)   # below -18 dB


def test_attack_is_sharp(rendered):
    """Metal and heel strikes have a sharp attack: the peak lies within the first 25 ms (except scrapes that start with friction)."""
    for (name, i), x in rendered.items():
        if name in ('mag_out', 'mag_in', 'draw_a', 'jump'):
            continue
        at = max(range(len(x)), key=lambda k: abs(x[k]))
        assert at / pf.RATE < 0.025, (name, i, at / pf.RATE)


def test_files_match_the_standard_of_the_gun_shot(tmp_path):
    paths = pf.build_all(tmp_path)
    assert len(paths) == len(ALL)
    with wave.open(str(pf.ROOT / 'assets' / 'sounds' / 'm4_shot.wav'), 'rb') as ref:
        want = (ref.getnchannels(), ref.getsampwidth(), ref.getframerate(), ref.getcomptype())
    for p in paths:
        with wave.open(str(p), 'rb') as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype()) == want, p.name


def test_committed_files_are_up_to_date():
    """assets/sounds/foley/*.wav must be exactly the current output of tools/build/prep_foley.py (after changing the formula, re-run and commit)."""
    for name, i in ALL:
        path = pf.ROOT / 'assets' / 'sounds' / 'foley' / f'{name}_{i}.wav'
        assert path.exists(), f'thiếu {path.name}: chạy tools\\build\\prep_foley.py'
        x, fmt = pf.read_mono(path)
        want = pf.render(name, i)
        assert len(x) == len(want), path.name
        assert max(abs(a - b) for a, b in zip(x, want)) < 2.0 / 32768, path.name
