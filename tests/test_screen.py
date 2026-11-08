"""G16 (D2, D3): window size from the command line and the primary monitor."""
from types import SimpleNamespace as M

import pytest

from fps.core.screen import FALLBACK, parse_size, primary_size


@pytest.mark.parametrize('text, size', [('1280x720', (1280, 720)), ('1920X1080', (1920, 1080)), (' 800 * 600 ', (800, 600))])
def test_good_sizes(text, size):
    assert parse_size(text) == size


@pytest.mark.parametrize('text', ['', '1280', '1280x', 'x720', 'axb', '1280x720x2', '-1280x720', '1280.5x720', '10x10', '99999x720'])
def test_bad_sizes_raise_a_readable_value_error(text):
    with pytest.raises(ValueError) as e:
        parse_size(text)
    assert 'cỡ cửa sổ' in str(e.value)


def test_primary_monitor_wins():
    ms = [M(width=1280, height=1024, is_primary=False), M(width=1920, height=1080, is_primary=True)]
    assert primary_size(ms) == (1920, 1080)


def test_no_primary_takes_the_first_sane_one():
    assert primary_size([M(width=0, height=0, is_primary=False), M(width=2560, height=1440)]) == (2560, 1440)


@pytest.mark.parametrize('ms', [None, [], [M(width=0, height=0, is_primary=True)], [M(width='?', height=None)], [object()]])
def test_nothing_usable_falls_back(ms):
    assert primary_size(ms) == FALLBACK
