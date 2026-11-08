"""G16 (D1): window focus guard."""
from fps.core.focus import FocusGuard


def test_lost_then_gained_once_each():
    g = FocusGuard(click_guard=0.3)
    assert g.update(0.016, True, True) is None
    assert g.update(0.016, False, True) == 'lost'
    assert g.update(0.016, False, False) is None          # stays lost, no repeat
    assert g.guarding
    assert g.update(0.016, True) == 'gained'
    assert g.update(0.016, True) is None
    assert g.lost_count == 1


def test_mouse_capture_is_restored_only_if_it_was_on():
    g = FocusGuard()
    g.update(0.016, False, mouse_locked=True)
    g.update(0.016, True)
    assert g.take_lock_before() is True
    g.update(0.016, False, mouse_locked=False)            # the player had pressed Esc before Alt+Tab
    g.update(0.016, True)
    assert g.take_lock_before() is False


def test_click_guard_runs_out():
    g = FocusGuard(click_guard=0.3)
    g.update(0.016, False)
    g.update(0.016, True)
    t = 0.0
    while g.guarding:
        g.update(0.05, True)
        t += 0.05
    assert 0.25 <= t <= 0.35


def test_a_long_frame_does_not_break_it():
    g = FocusGuard(click_guard=0.3)
    g.update(5.0, False)
    assert g.update(-1.0, True) == 'gained' and g.guarding
    g.update(5.0, True)
    assert not g.guarding
