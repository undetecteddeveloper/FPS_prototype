"""Bullet holes live 1.5 s (core/holes.py): a ring of slots, fade at the end, nothing depends on the frame rate."""
import pytest

from fps.core.holes import CLOCK_WRAP, HoleRing, fade_alpha, wrapped_age
from fps.weapon_data import FeedbackParams

FB = FeedbackParams()


def test_default_life_is_one_and_a_half_seconds_and_the_ring_holds_a_full_auto_burst():
    assert FB.hole_life == pytest.approx(1.5)
    assert 0.0 < FB.hole_fade < FB.hole_life
    assert FB.max_holes >= 12.5 * FB.hole_life * 2          # the M4 fires 750 RPM = 12.5 shots/s: twice what can be alive at once


def test_a_hole_dies_after_exactly_its_life_at_any_frame_rate():
    for fps in (30, 60, 144, 240):
        ring = HoleRing(8, FB.hole_life)
        ring.add()
        dead_at = None
        t = 0.0
        while t < 3.0 and dead_at is None:
            t += 1.0 / fps
            if ring.advance(1.0 / fps):
                dead_at = t
        assert dead_at == pytest.approx(FB.hole_life, abs=1.5 / fps)


def test_dead_slots_are_reported_once_and_freed():
    ring = HoleRing(4, 1.0)
    a = ring.add()
    ring.advance(0.5)
    b = ring.add()
    assert ring.live == 2
    assert ring.advance(0.55) == [a]                          # the first one is 1.05 s old, the second 0.55 s
    assert ring.live == 1 and ring.slots[a] is None and ring.slots[b] is not None
    assert ring.advance(0.5) == [b]
    assert ring.live == 0 and ring.advance(5.0) == []


def test_a_full_ring_reuses_the_oldest_slot_and_keeps_counting():
    ring = HoleRing(3, 10.0)
    slots = [ring.add() for _ in range(5)]
    assert slots == [0, 1, 2, 0, 1]
    assert ring.live == 3 and ring.added == 5
    ring.advance(11.0)
    assert ring.live == 0


def test_replaced_hole_is_not_reported_dead_twice():
    ring = HoleRing(2, 1.0)
    ring.add()
    ring.add()
    ring.add()                                                # slot 0 replaced at clock 0 (the old hole is gone, the new one has the same birth)
    dead = ring.advance(1.0)
    assert sorted(dead) == [0, 1] and ring.live == 0


def test_fade_curve_is_one_then_smoothly_zero():
    life, fade = 1.5, 0.4
    assert fade_alpha(0.0, life, fade) == 1.0 and fade_alpha(life - fade, life, fade) == 1.0
    assert fade_alpha(life, life, fade) == 0.0 and fade_alpha(life + 1.0, life, fade) == 0.0
    mid = fade_alpha(life - fade / 2, life, fade)
    assert mid == pytest.approx(0.5)
    xs = [fade_alpha(life - fade + fade * i / 20, life, fade) for i in range(21)]
    assert all(a >= b for a, b in zip(xs, xs[1:]))
    assert fade_alpha(1.4, 1.5, 0.0) == 1.0                   # no fade: a hole just stops


def test_age_on_the_wrapped_clocks_survives_the_wrap():
    assert wrapped_age(10.0, 8.5) == pytest.approx(1.5)
    assert wrapped_age(0.5, CLOCK_WRAP - 1.0) == pytest.approx(1.5)      # the clock wrapped between the birth and now
    ring = HoleRing(2, 1.5)
    ring.advance(CLOCK_WRAP - 0.2)
    ring.add()
    ring.advance(0.5)
    assert wrapped_age(ring.clock_wrapped(), ring.birth_wrapped(0)) == pytest.approx(0.5, abs=1e-6)


def test_clear_frees_everything():
    ring = HoleRing(4, 5.0)
    [ring.add() for _ in range(3)]
    assert sorted(ring.clear()) == [0, 1, 2]
    assert ring.live == 0 and ring.add() == 3


# ------------------------------------------------------------------ which wall a hole sits on (its baked light) + the F2 row
def test_face_at_finds_the_wall_face_and_its_lightmap_point():
    from fps.core.poolmap import UV_AXES, build_map, face_at, lightmap_uv, pack_atlas
    from fps.weapon_data import MapData
    d = MapData()
    pm = build_map(d)
    faces = pm.exposed_faces()
    atlas = pack_atlas(faces, d.texel)
    point, normal = (-d.room_x / 2, 1.5, 0.0), (1.0, 0.0, 0.0)             # a bullet on the west wall, the wall faces +x
    i = face_at(faces, point, normal)
    assert i is not None and faces[i].axis == 0 and faces[i].sign == 1
    ua, va = UV_AXES[0]
    u, v = lightmap_uv(faces[i], atlas.faces[i], atlas, point[ua], point[va])
    assert 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0
    assert face_at(faces, (0.0, 50.0, 0.0), (0.0, -1.0, 0.0)) is None      # nothing there
    assert face_at(faces, point, (-1.0, 0.0, 0.0)) is None                  # the wrong side of the same plane


def test_graphics_surface_row_and_old_files():
    import json
    from fps.core.graphics import OPTIONS, from_json, resolve, settings_for, to_json
    assert 'surface' in [f for f, _, _ in OPTIONS]
    low, mid, high = (resolve(settings_for(i)).surface for i in range(3))
    assert (low, mid, high) == (0, 1, 2)
    raw = json.loads(to_json(settings_for(0)))
    del raw['graphics']['surface']                                          # a file saved before the row existed keeps its preset whole
    assert from_json(json.dumps(raw)).surface == 0
