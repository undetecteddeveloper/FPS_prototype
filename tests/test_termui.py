"""G20: text-mode UI maths (fps/core/termui.py): the cell grid, the panel and splash layouts at many window sizes, fixed-width text, and the splash script."""
import re

import pytest

from fps.core import termui as T

SIZES = [(1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1080), (2560, 1440), (3840, 2160), (1024, 576), (1280, 800)]
N_OPTIONS = 16


# ------------------------------------------------------------------ grid
@pytest.mark.parametrize('w,h', SIZES)
def test_the_grid_is_whole_pixels_and_the_text_scale_hits_the_column_exactly(w, h):
    g = T.make_grid(h)
    assert isinstance(g.cw, int) and isinstance(g.lh, int)
    assert g.lh >= 2 * g.cw                                    # a row is never tighter than two columns
    assert g.text_scale * g.em_ratio * T.TEXT_SIZE * h == pytest.approx(g.cw, abs=1e-9)    # Ursina draws one glyph advance = cw px exactly


def test_the_grid_grows_with_the_window():
    assert T.make_grid(1080).cw > T.make_grid(720).cw > T.make_grid(480).cw


def test_pixel_and_ui_units_round_trip():
    for w, h in SIZES:
        for px, py in ((0, 0), (w / 2, h / 2), (w - 1, h - 1), (123, 456)):
            x, y = T.px_to_ui_x(px, w, h), T.px_to_ui_y(py, h)
            assert T.ui_to_px(x, y, w, h) == pytest.approx((px, py))
    assert T.px_to_ui_x(960, 1920, 1080) == 0.0 and T.px_to_ui_y(540, 1080) == 0.0     # the middle of the window is the UI origin


# ------------------------------------------------------------------ fixed-width text
def test_fit_is_always_exactly_the_width():
    for text in ('', 'A', 'ABCDEFGH', 'A' * 50):
        for align in '<>^':
            assert len(T.fit(text, 12, align)) == 12
    assert T.fit('SURFACE DETAIL (TILES, IMPACTS)', 12) == 'SURFACE DE..'
    assert T.fit('ON', 6, '>') == '    ON'


def test_dotted_puts_the_status_flush_right_in_exactly_the_width():
    for status in (T.STATUS_OK, T.STATUS_PENDING, 'RECON-1  AUTHORIZED'):
        line = T.dotted('LOAD GEOMETRY', status, 74)
        assert len(line) == 74 and line.endswith(status) and line.startswith('LOAD GEOMETRY ')
    assert len(T.dotted('X' * 90, T.STATUS_OK, 74)) <= 74 + len(T.STATUS_OK)      # an over-long label is cut, it never pushes the status out


def test_progress_bar_and_clock():
    assert T.bar(0.0, 10) == T.SHADE * 10 and T.bar(1.0, 10) == T.BLOCK * 10 and T.bar(0.5, 10) == T.BLOCK * 5 + T.SHADE * 5
    assert len(T.bar(0.37, 20)) == 20 and T.bar(-3, 4) == T.SHADE * 4 and T.bar(9, 4) == T.BLOCK * 4
    assert T.clock(0) == '00:00:00' and T.clock(3725) == '01:02:05' and T.clock(-4) == '00:00:00'


def test_typewriter_reveals_from_the_left_at_the_given_speed():
    assert T.typed('HELLO', 0.0, 10.0) == '' and T.typed('HELLO', 0.25, 10.0) == 'HE' and T.typed('HELLO', 9.0, 10.0) == 'HELLO'
    assert T.typed('HELLO', 0.0, 0.0) == 'HELLO'               # cps 0 = the whole line


def test_blink_duty_and_flicker_range():
    on = sum(T.blink(i / 1000.0, 1.0, 0.6) for i in range(1000))
    assert 590 <= on <= 610
    values = [T.flicker(i * 0.013) for i in range(5000)]
    assert max(values) <= 1.0 and min(values) >= 1.0 - 0.025 - 1e-9          # never a flash: at most 2.5% dimmer


# ------------------------------------------------------------------ panel layout
@pytest.mark.parametrize('w,h', SIZES)
def test_panel_fits_and_is_centred(w, h):
    L = T.panel_layout(w, h, N_OPTIONS)
    assert L.panel.inside(w, h)
    assert abs(L.panel.x - (w - L.panel.right)) <= 1 and abs(L.panel.y - (h - L.panel.bottom)) <= 1      # equal margins (an odd leftover pixel is the only difference)


@pytest.mark.parametrize('w,h', SIZES)
def test_panel_rows_share_one_pitch_one_left_edge_and_one_width(w, h):
    L = T.panel_layout(w, h, N_OPTIONS)
    g = L.grid
    assert len(L.options) == N_OPTIONS
    assert all(r.h == g.lh and r.x == L.text_x and r.w == T.PANEL_COLS * g.cw for r in L.options)
    assert [b.y - a.y for a, b in zip(L.options, L.options[1:])] == [g.lh] * (N_OPTIONS - 1)           # one row pitch, no drift
    for r in (L.header, L.footer, L.rule_top, L.rule_bottom):
        assert r.x == L.text_x and r.w == T.PANEL_COLS * g.cw
    blocks = [L.header, L.rule_top, *L.options, L.rule_bottom, L.footer]
    for a, b in zip(blocks, blocks[1:]):
        assert not a.overlaps(b) and a.bottom <= b.y                                                   # in order, nothing overlaps
    inner = L.panel
    assert all(r.x >= inner.x + g.cw and r.right <= inner.right - g.cw for r in blocks)               # padding on both sides is the same
    assert L.text_x - inner.x == inner.right - (L.text_x + T.PANEL_COLS * g.cw)
    assert L.header.y - inner.y == inner.bottom - L.footer.bottom                                      # top and bottom padding equal


@pytest.mark.parametrize('w,h', SIZES)
def test_the_value_column_is_flush_with_the_right_edge(w, h):
    L = T.panel_layout(w, h, N_OPTIONS)
    right = L.col_x(L.value_col) + T.VALUE_COLS * L.grid.cw
    assert right == L.text_x + T.PANEL_COLS * L.grid.cw                    # the value block ends exactly at the text edge
    assert L.value_col == T.PANEL_COLS - T.VALUE_COLS


def test_row_lookup_matches_the_rectangles():
    L = T.panel_layout(1920, 1080, N_OPTIONS)
    for i, r in enumerate(L.options):
        assert L.row_at(r.x + 1, r.y) == i and L.row_at(r.right - 1, r.bottom - 1) == i
    assert L.row_at(L.options[0].x, L.options[0].y - 1) is None and L.row_at(L.panel.x - 5, L.options[3].y) is None


def test_option_lines_keep_fixed_columns_whatever_the_text():
    cols = T.PANEL_COLS - T.VALUE_COLS
    for label in ('FPS COUNTER', 'SURFACE DETAIL (TILES, IMPACTS)', 'X' * 80):
        for selected in (False, True):
            left, right = T.option_line(label, selected, 'HIGH', selected)
            assert len(left) == cols and len(right) == T.VALUE_COLS
    for value in ('ON', 'OFF', 'HIGH', 'SIMPLE', 'CUSTOM', '100%'):
        sel = T.value_field(value, True)
        idle = T.value_field(value, False)
        assert sel.index(value) == idle.index(value) == 2                    # the value starts in the same column selected or not: nothing moves when the cursor arrives
        assert sel[0] == '◄' and sel[-1] == '►' and idle.strip() == value


# ------------------------------------------------------------------ splash layout
@pytest.mark.parametrize('w,h', SIZES)
def test_splash_layout_is_centred_and_fits(w, h):
    L = T.splash_layout(w, h)
    g = L.grid
    assert L.top.w == w and L.bottom.w == w and L.top.y == 0 and L.bottom.bottom == h              # both banners are flush with the screen edges
    assert abs(L.x0 - (w - (L.x0 + L.block_cols * g.cw))) <= 1              # the block is centred
    assert L.log_rows >= 8
    last = L.row_y(L.log_rows - 1) + g.lh
    assert L.head_y + L.head_rows * g.lh <= L.log_y and last <= L.bar_y and L.bar_y + g.lh <= L.hint_y and L.hint_y + g.lh <= L.bottom.y
    assert L.block_cols * g.cw <= w and all(L.row_y(i + 1) - L.row_y(i) == g.lh for i in range(L.log_rows - 1))


# ------------------------------------------------------------------ boot sequence
def _seq():
    s = T.BootSeq(t0=0.0)
    s.stage('INIT DISPLAY', 0.10, 0.1)
    s.stage('LOAD GEOMETRY', 0.40, 0.3)
    s.stage('COMPILE SHADERS', 1.20, 0.8)
    return s


def test_load_lines_have_the_block_width_and_the_status_column_never_moves():
    s = _seq()
    s.load_done(2.0, {'time': '2026-11-12 14:07:31', 'storage': '58.2 GB FREE', 'power': 'AC', 'audio': 'ON'})
    dotted_lines = [ln for ln in s.lines if re.search(r' \.{3,} ', ln.text)]
    assert len(dotted_lines) >= 8                                                # 3 load stages + the finale's check lines + RECORDING
    for ln in dotted_lines:
        assert len(ln.text) == T.BLOCK_COLS, ln.text                             # every dotted line, load or finale, ends in the same column (flush right)
    statuses = [ln.text.rindex(T.STATUS_OK) for ln in s.lines if ln.text.endswith(T.STATUS_OK)]
    assert len(statuses) == 3 and len(set(statuses)) == 1                        # the three load stages: one status column
    assert sum(1 for ln in dotted_lines if ln.born >= 2.0) >= 6                  # the finale's own lines are among them (checked above: same width, flush right)


def test_a_stage_stays_pending_until_the_next_one_starts():
    s = T.BootSeq()
    s.stage('INIT DISPLAY', 0.1)
    assert s.lines[0].text.endswith(T.STATUS_PENDING) and s.lines[0].pending
    s.stage('LOAD GEOMETRY', 0.5)
    assert s.lines[0].text.endswith(T.STATUS_OK) and not s.lines[0].pending and s.lines[1].pending


def test_cues_fire_once_each_and_in_time_order():
    s = _seq()
    s.load_done(2.0, {})
    assert s.poll_cues(1.0).count('ok') == 1                                    # at 1.0 s only the first stage has finished (the second finishes at 1.2 s)
    first = s.poll_cues(1.3)
    assert first.count('ok') == 1                                               # now the second one
    assert s.poll_cues(1.0) == []                                               # nothing is repeated
    later = s.poll_cues(2.0 + 5.0)
    assert later[0] == 'ok' and later[1] == 'blip' and later[-1] == 'rec' and 'relay' in later and later.count('ok') >= 6      # stage 3 finishes first (2.00 s), then the finale
    assert s.poll_cues(100.0) == []


def test_the_finale_is_short_and_ends_by_itself():
    s = _seq()
    s.load_done(2.0, {})
    assert 3.0 < s.finale_end - 2.0 < 5.0                                        # the user chose a short ending
    s.update(s.finale_end - 0.01)
    assert not s.done
    s.update(s.finale_end)
    assert s.done


def test_lines_type_out_and_the_count_of_characters_only_grows():
    s = _seq()
    s.load_done(2.0, {})
    totals = [s.total_chars(2.0 + i * 0.05) for i in range(100)]
    assert totals == sorted(totals) and totals[0] == 0 and totals[-1] > 200
    early = s.visible(2.3, 40)
    assert any(not finished for _, _, finished in early)                         # a line is mid-typing at 0.3 s


def test_keys_pressed_while_loading_do_not_skip_the_finale():
    s = _seq()
    assert not s.skip(0.5)                                                       # still loading
    s.load_done(2.0, {})
    assert not s.skip(2.1) and not s.can_skip(2.1)                               # keys queued during the load reach the game in its first frame: ignored
    assert s.can_skip(2.0 + T.KEY_GRACE + 0.01)


def test_skip_shows_everything_and_finishes_quickly():
    s = _seq()
    s.load_done(2.0, {})
    t = 2.6
    assert s.skip(t)
    assert not s.skip(t + 0.01)                                                  # only once
    texts = [text for text, _, finished in s.visible(t, 100)]
    assert any(x.endswith('ARMED') for x in texts) and any('REC' in x for x in texts)      # the whole script is on screen at once
    assert all(finished for _, _, finished in s.visible(t, 100))
    assert s.finale_end == pytest.approx(t + T.SKIP_HOLD)
    s.update(t + T.SKIP_HOLD)
    assert s.done


def test_visible_scrolls_to_the_last_rows():
    s = T.BootSeq()
    for i in range(30):
        s.stage(f'STEP {i}', 0.1 * i)
    rows = s.visible(10.0, 12)
    assert len(rows) == 12 and 'STEP 29' in rows[-1][0] and 'STEP 18' in rows[0][0]


def test_the_controls_table_lines_up_in_columns():
    script = T.finale_script({})
    table = [row[2] for row in script if row[1] == 'dim']
    assert len(table) == len(T.CONTROL_ROWS)
    for line, cells in zip(table, T.CONTROL_ROWS):
        for i, cell in enumerate(cells):
            assert line[i * T.CONTROL_CELL:i * T.CONTROL_CELL + len(cell)] == cell      # every cell starts at a multiple of the cell width
        assert len(line) + T.STAMP_COLS <= T.BLOCK_COLS


def test_capitals_are_centred_in_their_row_to_half_a_pixel():
    for w, h in SIZES:
        g = T.make_grid(h)
        for row_y in (0, g.lh * 7, g.lh * 20):
            top = T.text_origin_y(row_y, g)
            cap_centre = top + T.CAP_CENTER_EM * g.em_px
            assert abs(cap_centre - (row_y + g.lh / 2.0)) <= 0.5 + 1e-9


def test_retitle_rebuilds_the_running_stage_in_place():
    s = T.BootSeq()
    s.stage('LOAD MAP', 0.5, 0.2)
    stamp_line = s.lines[0].text[:T.STAMP_COLS]
    s.retitle('LOAD MAP  LIGHT BAKE 42%', 0.3)
    assert s.lines[0].text.startswith(stamp_line + 'LOAD MAP  LIGHT BAKE 42%') and len(s.lines[0].text) == T.BLOCK_COLS and s.progress == 0.3
    s.stage('NEXT', 1.0)
    assert s.lines[0].text.endswith(T.STATUS_OK) and 'LIGHT BAKE 42%' in s.lines[0].text          # it finishes with the detail it last reported


def test_every_graphics_text_fits_the_fixed_panel_columns():
    from fps.core.graphics import CUSTOM_TEXT, OPTIONS
    label_cols = T.PANEL_COLS - T.VALUE_COLS - T.MARKER_COLS
    value_cols = T.VALUE_COLS - 4
    for field, label, choices in OPTIONS:
        assert len(label) <= label_cols - 4, (field, label)                      # the longest label still leaves a gap before the value block
        assert label == label.upper() and '<' not in label and label.isascii()  # upper case; '<' would start an Ursina markup tag
        for _, text in choices:
            assert len(text) <= value_cols and text == text.upper() and '<' not in text, (field, text)
    assert len(CUSTOM_TEXT) <= value_cols


def test_a_narrow_font_still_gets_a_grid_that_fits():
    wide = T.panel_layout(1280, 720, N_OPTIONS, em_ratio=0.60)                    # Lucida Console / Courier are 0.6 em wide: the columns are wider for the same em
    assert wide.panel.inside(1280, 720) and wide.grid.em_ratio == 0.60
    assert wide.grid.text_scale * 0.60 * T.TEXT_SIZE * 720 == pytest.approx(wide.grid.cw)


def test_centred_text_has_equal_gaps_to_the_pixel():
    for w, h in SIZES:
        g = T.make_grid(h)
        L = T.panel_layout(w, h, N_OPTIONS)
        for n in (12, 19, 45, 60):                                              # odd and even lengths in a 60-column strip
            x = T.centered_x(L.text_x, L.header.w, n, L.grid.cw)
            left, right = x - L.text_x, (L.text_x + L.header.w) - (x + n * L.grid.cw)
            assert abs(left - right) <= 1 and left >= 0
