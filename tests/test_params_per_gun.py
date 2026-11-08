"""8/11/2026: the F1 panel edits the gun IN HAND with that gun's own defaults; the file keeps each gun apart; reset touches only the gun in hand."""
import copy
import json

from fps.core.params import ParamStore
from fps.weapon_data import GUNS, GameParams


def make():
    """A store like Game builds it: M4 in hand, the Glock built later (a separate live copy)."""
    params = GameParams(gun=copy.deepcopy(GUNS['m4']))
    store = ParamStore(params, gun_key='m4')
    glock = copy.deepcopy(GUNS['glock'])
    store.register_gun('glock', glock)
    return params, store, glock


def switch(params, store, key, gun):
    params.gun = gun
    store.set_gun(key, gun)


def test_glock_in_hand_shows_its_own_numbers_as_defaults():
    params, store, glock = make()
    m4 = params.gun
    switch(params, store, 'glock', glock)
    rpm = store.by_id['gun.rpm']
    assert store.get(rpm) == GUNS['glock'].rpm and store.default_of(rpm) == GUNS['glock'].rpm
    assert store.changed_specs() == []                       # before: every Glock number that differs from the M4 counted as "changed"
    switch(params, store, 'm4', m4)
    assert store.default_of(rpm) == GUNS['m4'].rpm and store.changed_specs() == []


def test_editing_the_glock_does_not_touch_the_m4_and_saves_apart(tmp_path):
    params, store, glock = make()
    m4 = params.gun
    store.set(store.by_id['gun.rpm'], 800.0)                 # on the M4
    store.set(store.by_id['player.fov'], 100.0)              # shared
    switch(params, store, 'glock', glock)
    store.set(store.by_id['gun.rpm'], 500.0)                 # on the Glock
    assert m4.rpm == 800.0 and glock.rpm == 500.0
    path = tmp_path / 'p.json'
    assert store.save(path).ok
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['values'] == {'player.fov': 100.0}
    assert data['guns'] == {'m4': {'gun.rpm': 800.0}, 'glock': {'gun.rpm': 500.0}}

    # a new game starts with the M4 in hand; the Glock is built later and gets its numbers then
    p2 = GameParams(gun=copy.deepcopy(GUNS['m4']))
    s2 = ParamStore(p2, gun_key='m4')
    rep = s2.load(path)
    assert rep.ok and rep.applied == 3 and not rep.ignored
    assert p2.gun.rpm == 800.0 and p2.player.fov == 100.0
    g2 = copy.deepcopy(GUNS['glock'])
    s2.register_gun('glock', g2)
    assert g2.rpm == 500.0


def test_reset_all_only_resets_the_gun_in_hand():
    params, store, glock = make()
    m4 = params.gun
    store.set(store.by_id['gun.rpm'], 800.0)
    store.set(store.by_id['player.fov'], 100.0)
    switch(params, store, 'glock', glock)
    store.set(store.by_id['gun.rpm'], 500.0)
    assert store.reset_all() == 1
    assert glock.rpm == GUNS['glock'].rpm                    # back to the GLOCK's default, not the M4's
    assert m4.rpm == 800.0 and params.player.fov == 100.0     # the other gun and the shared numbers stay


def test_reset_one_slider_goes_to_the_glock_default():
    params, store, glock = make()
    switch(params, store, 'glock', glock)
    spec = store.by_id['gun.accuracy.stand']
    store.set(spec, 3.0)
    assert store.reset(spec) and glock.accuracy.stand == GUNS['glock'].accuracy.stand


def test_version_1_file_goes_to_the_m4(tmp_path):
    params, store, glock = make()
    path = tmp_path / 'old.json'
    path.write_text(json.dumps({'version': 1, 'values': {'gun.rpm': 777.0, 'player.fov': 95.0}}), encoding='utf-8')
    rep = store.load(path)
    assert rep.ok and rep.applied == 2
    assert params.gun.rpm == 777.0 and params.player.fov == 95.0 and glock.rpm == GUNS['glock'].rpm


def test_bad_gun_sections_are_skipped_not_fatal():
    params, store, glock = make()
    rep = store.apply_dict({'version': 2, 'values': {}, 'guns': {'ak47': {'gun.rpm': 600}, 'glock': {'player.fov': 80, 'gun.rpm': 'x', 'gun.ads_time': 0.3}}})
    assert rep.ok and rep.applied == 1 and len(rep.ignored) == 3
    assert glock.ads_time == 0.3
    assert not store.apply_dict({'version': 2, 'values': {}, 'guns': [1]}).ok


def test_load_resets_every_gun_before_applying(tmp_path):
    params, store, glock = make()
    switch(params, store, 'glock', glock)
    store.set(store.by_id['gun.rpm'], 500.0)
    path = tmp_path / 'm4only.json'
    path.write_text(json.dumps({'version': 2, 'values': {}, 'guns': {'m4': {'gun.rpm': 810.0}}}), encoding='utf-8')
    assert store.load(path).ok
    assert glock.rpm == GUNS['glock'].rpm
