"""G16 C1-C2: atomic writes, and settings files of any shape never break the start."""
import pytest

from fps.core.safeio import write_bytes_atomic, write_text_atomic


def test_write_replaces_and_leaves_no_temp(tmp_path):
    p = tmp_path / 'a.json'
    write_text_atomic(p, 'một')
    write_text_atomic(p, 'hai')
    assert p.read_text(encoding='utf-8') == 'hai'
    assert [f.name for f in p.parent.iterdir()] == ['a.json']


def test_failed_write_keeps_old_file(tmp_path, monkeypatch):
    p = tmp_path / 'a.bin'
    write_bytes_atomic(p, b'old')

    def boom(src, dst):
        raise OSError('disk full')
    monkeypatch.setattr('fps.core.safeio.os.replace', boom)
    with pytest.raises(OSError):
        write_bytes_atomic(p, b'new')
    assert p.read_bytes() == b'old'
    assert [f.name for f in tmp_path.iterdir()] == ['a.bin']


@pytest.mark.parametrize('text', ['', '[]', '[1, 2]', '"x"', '42', 'null', '{"graphics": []}', '{"graphics": 5}', '{"graphics": null}',
                                  '{"graphics', '﻿{"graphics": {}}'])
def test_graphics_file_of_any_shape_raises_value_error_or_loads(text):
    from fps.core.graphics import GraphicsSettings, from_json
    try:
        s = from_json(text)
    except ValueError:
        return                                  # the game catches ValueError and keeps its defaults
    assert isinstance(s, GraphicsSettings)


@pytest.mark.parametrize('values', [{'aa': [4]}, {'aa': {'x': 1}}, {'aa': True}, {'show_fps': 1}, {'scale': float('nan')}, {'scale': 7}, {'scale': -1}, {'dust': 'yes'}])
def test_graphics_values_of_wrong_type_fall_back(values):
    import json
    from fps.core.graphics import GraphicsSettings, from_json
    s = from_json(json.dumps({'graphics': values}))
    d = GraphicsSettings()
    for k in values:
        assert getattr(s, k) == getattr(d, k) or getattr(s, k) is getattr(d, k)


def test_params_save_is_atomic(tmp_path, monkeypatch):
    from fps.core.params import ParamStore
    from fps.weapon_data import GameParams
    store = ParamStore(GameParams())
    p = tmp_path / 'user_params.json'
    assert store.save(p).ok
    before = p.read_text(encoding='utf-8')

    def boom(src, dst):
        raise OSError('disk full')
    monkeypatch.setattr('fps.core.safeio.os.replace', boom)
    assert not store.save(p).ok
    assert p.read_text(encoding='utf-8') == before
