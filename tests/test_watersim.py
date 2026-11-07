import math

import pytest

from fps.core.watersim import MAX_COURANT, STEP, SimClock, coefficient, courant, damping, energy, impulse, push, step


def grid(n, m, value=0.0):
    return [[value] * m for _ in range(n)]


def pulse(n, m, ci, cj, amount=0.01, radius=2.0):
    return [[impulse(i, j, ci, cj, radius, amount) for i in range(m)] for j in range(n)]


def run(h, hp, steps, coef, damp):
    for _ in range(steps):
        h, hp = step(h, hp, coef, damp)
    return h, hp


def test_courant_is_capped_so_the_scheme_stays_stable():
    assert courant(1.0, 0.05) == pytest.approx(1.0 / 120.0 / 0.05)
    assert coefficient(1000.0, 0.01) == pytest.approx(MAX_COURANT ** 2)
    assert MAX_COURANT < 1.0 / math.sqrt(2.0)


def test_a_pulse_spreads_and_never_blows_up_even_at_the_capped_speed():
    h = pulse(40, 40, 20, 20)
    h, hp = run(h, [row[:] for row in h], 400, coefficient(1e6, 0.05), damping(3.0))
    assert max(abs(v) for row in h for v in row) < 0.01


def test_energy_decays_with_damping_and_holds_without():
    h0 = pulse(30, 30, 15, 15)
    e0 = energy(h0, h0)
    h, hp = run(h0, [r[:] for r in h0], 300, coefficient(1.0, 0.05), damping(1.0))
    assert energy(h, hp) < 0.2 * e0
    h, hp = run(h0, [r[:] for r in h0], 300, coefficient(1.0, 0.05), 1.0)
    assert energy(h, hp) > 0.3 * e0                    # undamped: the wave keeps going (a little numeric loss only)


def test_the_wave_front_moves_at_the_set_speed():
    speed, cell = 1.0, 0.05
    n = 121
    h = [[impulse(i, 0, 10, 0, 1.5, 0.01) for i in range(n)]]      # a 1D line (one row): the crest travels along it
    hp = [r[:] for r in h]
    h, hp = run(h, hp, 120, coefficient(speed, cell), 1.0)        # 1 s
    row = h[0]
    crest = max(range(15, n), key=lambda i: row[i])              # the right-going half (the start splits into two halves)
    assert (crest - 10) * cell == pytest.approx(speed * 120 * STEP, abs=0.1)


def test_the_pool_wall_reflects_the_wave_back():
    n = 80
    h = [[impulse(i, 0, 60, 0, 1.5, 0.01) for i in range(n)]]
    hp = [r[:] for r in h]
    coef = coefficient(1.0, 0.05)
    h, hp = run(h, hp, 60, coef, 1.0)                              # the right-going half reaches the wall at 79 after ~19 cells / 0.48 s
    h, hp = run(h, hp, 120, coef, 1.0)
    row = h[0]
    assert max(row[40:70]) > 0.002                               # it came back toward the start


def test_a_push_is_a_displacement_not_a_kick():
    """Added to both time levels the push never grows past its own size; added to `now` only it would act as a velocity and keep growing (measured on the GPU: 1 cm -> 9 cm)."""
    n = 41
    h, hp = push(grid(n, n), grid(n, n), lambda i, j: impulse(i, j, 20, 20, 2.0, -0.01))
    coef, damp = coefficient(1.0, 0.05), damping(3.0)
    deepest = 0.0
    for _ in range(200):
        h, hp = step(h, hp, coef, damp)
        deepest = max(deepest, max(abs(v) for row in h for v in row))
    assert deepest <= 0.0101


def test_the_clock_runs_fixed_steps_and_drops_long_frames():
    c = SimClock()
    assert sum(c.steps(1 / 60) for _ in range(60)) == 120          # 60 FPS: 2 steps per frame
    c = SimClock()
    assert sum(c.steps(1 / 240) for _ in range(240)) == 120        # 240 FPS: same steps per second
    c = SimClock()
    assert c.steps(1.5) == 2 and c.acc <= STEP                     # a hitch: two steps, the rest is dropped (slow motion, not an explosion)
