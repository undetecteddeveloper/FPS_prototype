"""Lock F1-panel values into weapon_data.py: change exactly the right values, keep comments and line-wrap style, and report clearly what cannot be changed."""
import copy
import sys
import types
from pathlib import Path

import fps.weapon_data as wd
from fps.core.bake import Edit, edits_for, format_literal, patch_source
from fps.core.params import ParamStore, resolve
from fps.weapon_data import GameParams

SRC = '''from dataclasses import dataclass, field


@dataclass
class KickData:
    back: float = -0.03          # m: lùi một phát (tiếng Việt: đã đo)
    pair: tuple = (0.0, 1.5)     # hai thành phần
    on: bool = True
    beats: dict = field(default_factory=dict)
    computed: float = 2.0 * 3


@dataclass
class GunData:
    name: str
    kick: KickData = field(default_factory=KickData)
    rpm: float = 750.0
    ads_time: float = 0.19


M4 = GunData(
    name='M4',
    rpm=800.0,
)
'''


def test_format_literal():
    assert format_literal(750.0) == '750.0'
    assert format_literal(0.30000000000000004) == '0.3'
    assert format_literal(-0.036) == '-0.036'
    assert format_literal(30) == '30'
    assert format_literal(False) == 'False'
    assert format_literal((1.0, 2)) == '(1.0, 2)'
    assert format_literal((5.0,)) == '(5.0,)'
    assert format_literal('fake') == "'fake'"


def test_patches_class_field_and_keeps_comment():
    new, fails = patch_source(SRC, [Edit('KickData', 'back', -0.036)])
    assert not fails
    assert '    back: float = -0.036          # m: lùi một phát (tiếng Việt: đã đo)\n' in new


def test_patches_tuple_and_bool():
    new, fails = patch_source(SRC, [Edit('KickData', 'pair', (0.5, 2.25)), Edit('KickData', 'on', False)])
    assert not fails
    assert 'pair: tuple = (0.5, 2.25)     # hai thành phần' in new
    assert 'on: bool = False\n' in new


def test_call_keyword_wins_over_class_default():
    new, fails = patch_source(SRC, [Edit('GunData', 'rpm', 900.0, call='M4')])
    assert not fails
    assert "rpm=900.0,\n)" in new
    assert 'rpm: float = 750.0' in new                      # the class default stays as it is


def test_falls_back_to_class_default_when_call_has_no_keyword():
    new, fails = patch_source(SRC, [Edit('GunData', 'ads_time', 0.2, call='M4')])
    assert not fails
    assert 'ads_time: float = 0.2\n' in new


def test_unpatchable_reported_not_silent():
    new, fails = patch_source(SRC, [Edit('KickData', 'computed', 9.0), Edit('KickData', 'nope', 1.0), Edit('KickData', 'back', 0.1)])
    reasons = {e.attr: why for e, why in fails}
    assert set(reasons) == {'computed', 'nope'}
    assert 'back: float = 0.1 ' in new                       # whatever can be patched is still applied


def test_forbid_when_call_overrides_whole_object():
    src = SRC.replace("rpm=800.0,", "kick=KickData(back=-0.1),")
    _, fails = patch_source(src, [Edit('KickData', 'back', 0.0, forbid_kw=('M4', 'kick'))])
    assert len(fails) == 1 and 'ghi đè' in fails[0][1]


def test_crlf_and_utf8_offsets_preserved():
    crlf = SRC.replace('\n', '\r\n')
    new, fails = patch_source(crlf, [Edit('KickData', 'back', -0.05), Edit('GunData', 'rpm', 1.0, call='M4')])
    assert not fails
    assert new.count('\r\n') == crlf.count('\r\n') and new.count('\n') == new.count('\r\n')
    assert 'back: float = -0.05          # m: lùi một phát (tiếng Việt: đã đo)\r\n' in new


def _changed_value(spec):
    if spec.kind == 'bool':
        return not spec.default
    if spec.kind == 'choice':
        return next(c for c, _ in spec.choices if (type(c), c) != (type(spec.default), spec.default))
    for frac in (0.37, 0.81, 0.12):
        v = spec.lo + (spec.hi - spec.lo) * frac
        v = int(round(v)) if spec.kind == 'int' else float(f'{v:.5g}')
        if v != spec.default:
            return v
    return spec.hi


def test_every_slider_roundtrips_through_real_weapon_data():
    """Change EVERY slider, bake into the real code, reload: every number must come back exactly. Any slider that cannot be baked must be on the intentional-exception list."""
    store = ParamStore(copy.deepcopy(GameParams()))
    for s in store.specs:
        store.set(s, _changed_value(s))
    changed = store.changed_specs()
    assert len(changed) >= len(store.specs) - 3, 'bộ sinh giá trị đổi quá ít thanh'
    text = Path(wd.__file__).read_bytes().decode('utf-8')
    new, fails = patch_source(text, edits_for(store.root, changed))
    assert not fails, [(e.owner, e.attr, why) for e, why in fails]
    mod = types.ModuleType('weapon_data_baked')
    sys.modules['weapon_data_baked'] = mod
    try:
        exec(compile(new, 'weapon_data_baked.py', 'exec'), mod.__dict__)
        baked = mod.GameParams()
    finally:
        del sys.modules['weapon_data_baked']
    for s in changed:
        got = resolve(baked, s.path)
        got = getattr(got, s.attr)
        got = got[s.index] if s.index is not None else got
        assert got == store.get(s) and type(got) is type(store.get(s)), (s.id, got, store.get(s))
