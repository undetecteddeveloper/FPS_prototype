import pytest

from fps.core.weapon import Weapon
from fps.weapon_data import M4


def run(w, seconds, fps, held=True):
    """Simulates `seconds` seconds at `fps`; returns the absolute time of each shot."""
    dt = 1.0 / fps
    shots = []
    for i in range(round(seconds * fps)):
        for age in w.update(dt, held, False):
            shots.append((i + 1) * dt - age)
    return shots


@pytest.mark.parametrize('fps', [30, 60, 90, 144, 240, 1000])
def test_full_auto_rate_is_the_rpm_at_any_fps(fps):
    w = Weapon(M4)
    w.mag = 10000
    shots = run(w, 10.0, fps)
    assert len(shots) == pytest.approx(125, abs=1)         # 750 rounds/min = 12.5 rounds/s
    gaps = [b - a for a, b in zip(shots, shots[1:])]
    assert sum(gaps) / len(gaps) == pytest.approx(0.08, abs=1e-6)
    assert max(gaps) - min(gaps) < 1e-6                     # even, not skewed by the frame rate


def test_first_shot_is_immediate_not_a_frame_early():
    w = Weapon(M4)
    assert w.update(1 / 60, True, False) == [0.0]


def test_several_shots_in_one_slow_frame_are_ordered_in_time():
    w = Weapon(M4)
    w.update(1 / 60, True, False)
    ages = w.update(0.25, True, False)                      # 250 ms frame: should give 3 shots
    assert len(ages) == 3
    assert ages == sorted(ages, reverse=True)               # the oldest shot has the largest age
    assert all(0 <= a < 0.25 for a in ages)


def test_ammo_counts_down_and_stops_when_empty():
    w = Weapon(M4)
    shots = run(w, 5.0, 60)
    assert len(shots) == M4.magazine and w.mag == 0 and w.reserve == M4.reserve   # magazine emptied, reserve untouched
    assert w.update(1 / 60, True, False) == []              # out of ammo: no more shots possible


def test_trigger_released_does_not_bank_shots():
    w = Weapon(M4)
    w.mag = 100
    run(w, 2.0, 60, held=False)
    assert w.mag == 100
    assert len(w.update(1 / 60, True, False)) == 1          # after a long rest, one press still gives only one shot


def test_cannot_beat_rpm_by_tapping():
    w = Weapon(M4)
    w.mag = 100
    dt = 1 / 240
    fired = 0
    for i in range(240):                                    # press and release continuously, 1 second
        fired += len(w.update(dt, i % 2 == 0, False))
    assert fired <= 13


def test_single_fire_one_shot_per_press():
    w = Weapon(M4)
    w.toggle_mode()
    assert w.auto is False
    assert len(w.update(1 / 60, True, False)) == 0           # holding the trigger without a new press: no shot
    assert len(w.update(1 / 60, True, True)) == 1
    assert len(w.update(1 / 60, True, False)) == 0
    for _ in range(10):
        w.update(1 / 60, True, False)
    assert len(w.update(1 / 60, True, True)) == 1            # cooldown over, press again: fires again


def test_single_fire_respects_rpm():
    w = Weapon(M4)
    w.toggle_mode()
    assert len(w.update(1 / 240, False, True)) == 1
    assert len(w.update(1 / 240, False, True)) == 0          # pressed again after 4 ms: the rate interval has not elapsed yet


def test_load_magazine_takes_from_reserve():
    w = Weapon(M4)
    run(w, 1.0, 60)
    fired = M4.magazine - w.mag
    assert fired > 0
    assert w.can_reload
    assert w.load_magazine() == fired
    assert w.mag == M4.magazine and w.reserve == M4.reserve - fired
    assert not w.can_reload                                 # magazine is full now
    w.reserve = 5
    w.mag = 0
    assert w.load_magazine() == 5 and w.mag == 5 and w.reserve == 0
    assert w.load_magazine() == 0


def test_out_of_ammo_only_when_both_are_empty():
    w = Weapon(M4)
    w.mag, w.reserve = 0, 3
    assert not w.out_of_ammo and w.can_reload
    w.reserve = 0
    assert w.out_of_ammo and not w.can_reload
