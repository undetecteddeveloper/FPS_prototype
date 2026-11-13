"""G19 guards on the STORED bakes (assets/maps/**): they must belong to the current geometry, and every room must sit in its light band (no glare, no black hole).

The first one caught nothing in G19 only because it did not exist: after the project was copied between machines, floors 3-5 held lightmaps that no longer matched the
code (the game would have re-baked them for a minute at start-up, or shown the wrong light). The second replaces judging rooms by screenshots, whose brightness depends
on the camera's auto-exposure at the moment of the shot.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from fps.core.backrooms import build_stage, floor_key, stage_count
from fps.core.poolmap import reflect_key
from fps.game.backrooms import stage_dir
from fps.weapon_data import GameParams, LookData

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location('room_light_report', ROOT / 'tools' / 'measure' / 'room_light_report.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('stage', range(stage_count()))
def test_stored_bake_matches_the_code(stage):
    fm = build_stage(stage)
    meta = json.loads((ROOT / stage_dir(stage) / 'meta.json').read_text(encoding='utf-8'))
    assert meta.get('key') == floor_key(fm, LookData()), (
        f'stage {stage}: the stored lightmap is stale: run .venv\\Scripts\\python.exe -X utf8 tools\\build\\bake_backrooms.py and commit assets/maps')


@pytest.mark.parametrize('stage', range(stage_count()))
def test_stored_reflection_matches_the_bake(stage):
    """A stage whose stored reflection image is stale makes the game CAPTURE it when the stage is built: measured 12/11/2026, a 5.7 s freeze at the moment of the floor swap
    (in the hidden check it ate the whole 12 s walk-in window of backrooms_check, and failed it only on runs right after a re-bake).
    After changing a floor or the look: bake (tools/build/bake_backrooms.py), run backrooms_check once (it visits every stage and stores the reflections), commit assets/maps."""
    fm = build_stage(stage)
    meta = json.loads((ROOT / stage_dir(stage) / 'meta.json').read_text(encoding='utf-8'))
    p = GameParams()
    assert meta.get('reflect') == reflect_key(fm.data, p.look, p.lens), f'stage {stage}: the stored reflection is stale or missing'
    assert (ROOT / stage_dir(stage) / 'reflect.png').exists()


@pytest.mark.parametrize('stage', range(1, stage_count()))
def test_every_room_is_in_its_light_band(stage):
    tool = _tool()
    bad = []
    for name, kind, median, p90, n in tool.report(stage):
        lo, hi = tool.BANDS.get(kind, (0.0, 9.0))
        if not lo <= median <= hi:
            bad.append(f'{name} ({kind}) median {median:.2f} not in {lo}-{hi}')
    assert not bad, bad
