"""Window size from the command line and the primary monitor (pure Python; tests/test_screen.py). G16 (D2, D3): a mistyped `--size` is a clear
message, not a traceback; a monitor list that cannot be read falls back to a size that always works instead of ending the start."""

FALLBACK = (1280, 720)
MIN_SIDE, MAX_SIDE = 320, 7680


def parse_size(text: str) -> tuple:
    """'1280x720' (also 'X', '*', spaces) -> (1280, 720). Raises ValueError with a Vietnamese message."""
    t = str(text).lower().replace('*', 'x').replace(' ', '')
    parts = t.split('x')
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError(f'cỡ cửa sổ "{text}" không đúng dạng RỘNGxCAO (ví dụ 1280x720)')
    w, h = int(parts[0]), int(parts[1])
    if not (MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= h <= MAX_SIDE):
        raise ValueError(f'cỡ cửa sổ {w}x{h} ngoài khoảng {MIN_SIDE}-{MAX_SIDE} điểm ảnh mỗi chiều')
    return w, h


def primary_size(monitors) -> tuple:
    """(width, height) of the primary monitor in a list of objects with width / height / is_primary (screeninfo's Monitor); the first sane one
    when none is marked primary; FALLBACK when the list is empty or holds nothing usable."""
    good = []
    for m in monitors or ():
        try:
            w, h = int(m.width), int(m.height)
        except (AttributeError, TypeError, ValueError):
            continue
        if w >= MIN_SIDE and h >= MIN_SIDE:
            good.append((bool(getattr(m, 'is_primary', False)), w, h))
    if not good:
        return FALLBACK
    primary = next((g for g in good if g[0]), good[0])
    return primary[1], primary[2]
