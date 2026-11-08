"""Window focus (pure Python; tests/test_focus.py). G16 (D1), the user's choice: when the game window loses the foreground (Alt+Tab, minimised, another
window clicked) the game keeps running but frees the mouse, lets go of every held key and goes silent; when it comes back the mouse is captured again
only if it was captured before, the view does not jump, and the click that brought the window back does not fire a shot.

`FocusGuard.update(dt, foreground)` is called once per frame with the window's state and returns 'lost', 'gained' or None; Game does the Panda side."""

CLICK_GUARD_S = 0.35          # after regaining focus, mouse buttons are ignored this long (the activating click lands in the game)


class FocusGuard:
    def __init__(self, click_guard: float = CLICK_GUARD_S):
        self.click_guard = click_guard
        self.focused = True               # the window starts in front (Panda opens it focused)
        self.guard_left = 0.0             # seconds of the click guard still to run
        self.lock_before = None           # was the mouse captured when focus was lost (None while focused)
        self.lost_count = 0

    @property
    def guarding(self) -> bool:
        """Mouse buttons must be ignored now (unfocused, or just refocused)."""
        return not self.focused or self.guard_left > 0.0

    def update(self, dt: float, foreground: bool, mouse_locked: bool = False):
        self.guard_left = max(0.0, self.guard_left - max(dt, 0.0))
        if self.focused and not foreground:
            self.focused = False
            self.lock_before = bool(mouse_locked)
            self.lost_count += 1
            return 'lost'
        if not self.focused and foreground:
            self.focused = True
            self.guard_left = self.click_guard
            return 'gained'
        return None

    def take_lock_before(self) -> bool:
        """The mouse capture to restore on 'gained' (read once)."""
        v, self.lock_before = bool(self.lock_before), None
        return v
