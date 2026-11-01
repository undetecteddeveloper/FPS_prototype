"""Bảng debug (G6): sinh thanh trượt từ weapon_data, lưu / nạp JSON, đổi số sống. Không mở cửa sổ."""
import copy
import json
import math
import random

import pytest

from fps.core import param_meta
from fps.core.params import ParamStore, all_field_ids, auto_range, decimals_for, format_value, nice_step
from fps.core.recoil import CameraRecoil
from fps.core.spread import ring_radius, shot_offset, angle_between
from fps.core.movement import aim_direction
from fps.core.weapon import Weapon
from fps.weapon_data import GameParams, M4


def fresh() -> GameParams:
    """GameParams độc lập với M4 toàn cục (store ghi thẳng vào đối tượng, không làm bẩn M4 của test khác)."""
    return GameParams(gun=copy.deepcopy(M4))


@pytest.fixture
def store():
    return ParamStore(fresh())


# --- sinh thanh trượt ---
def test_every_field_is_on_the_panel_or_excluded_with_a_reason():
    on_panel = {s.path + '.' + s.attr for s in ParamStore(fresh()).specs}
    covered = on_panel | set(param_meta.EXCLUDED)
    missing = sorted(all_field_ids(fresh()) - covered)
    assert not missing, f'trường chưa có trên bảng debug cũng chưa ghi vào EXCLUDED (param_meta.py): {missing}'
    stale = sorted(set(param_meta.EXCLUDED) - all_field_ids(fresh()))
    assert not stale, f'EXCLUDED có trường không còn tồn tại: {stale}'
    assert not (on_panel & set(param_meta.EXCLUDED))


def test_every_meta_entry_is_used_and_every_field_listed_once():
    listed = [f for _, _, sections in param_meta.GROUPS for _, ids in sections for f in ids]
    assert len(listed) == len(set(listed)), 'một trường nằm ở hai chỗ'
    assert set(listed) == set(param_meta.META), 'META và GROUPS lệch nhau'


def test_every_slider_has_label_hint_and_a_sane_range(store):
    ids = set()
    for s in store.specs:
        assert s.id not in ids
        ids.add(s.id)
        assert s.label.strip(), s.id
        if s.kind in ('float', 'int'):
            assert s.hint.strip(), f'{s.id} chưa có chú thích'
            assert s.lo < s.hi, s.id
            assert s.lo <= s.default <= s.hi, f'{s.id}: mặc định {s.default} nằm ngoài {s.lo}..{s.hi}'
            assert s.step > 0 and (s.hi - s.lo) / s.step >= 4, s.id
        if s.kind == 'int':
            assert isinstance(s.default, int) and not isinstance(s.default, bool)
        if s.kind == 'float':
            assert isinstance(s.default, float)
    assert len(store.specs) > 150


def test_label_and_hint_fit_the_panel_width(store):
    # panel rộng ~0,66 đơn vị UI: nhãn <= 30 ký tự (cột nhãn), chú thích <= 66 ký tự (một dòng)
    for s in store.specs:
        assert len(s.label) <= 32, f'{s.id}: nhãn quá dài ({len(s.label)}): {s.label}'
        assert len(s.hint) <= 70, f'{s.id}: chú thích quá dài ({len(s.hint)}): {s.hint}'


def test_groups_cover_the_requested_topics(store):
    titles = [g.title for g in store.groups]
    for need in ('Bắn', 'Giật', 'Độ tản', 'Ngắm', 'Sway', 'Rung', 'Âm lượng', 'Nạp đạn', 'Ánh sáng'):
        assert need in titles
    assert all(g.specs for g in store.groups)


def test_tuple_components_become_separate_sliders(store):
    comps = [s for s in store.specs if s.path == 'gun.kick' and s.attr == 'peak']
    assert [s.index for s in comps] == list(range(6))
    assert [s.default for s in comps] == list(M4.kick.peak)
    assert comps[0].id == 'gun.kick.peak[0]'


def test_restart_and_advanced_flags(store):
    assert store.by_id['gun.magazine'].restart and store.by_id['gun.reserve'].restart
    assert not store.by_id['gun.rpm'].restart
    assert store.by_id['gun.recoil.kick_time'].advanced and not store.by_id['gun.recoil.up_scale'].advanced
    sections = store.group_by_key['recoil'].sections(show_advanced=False)
    assert all(not s.advanced for _, specs in sections for s in specs)
    assert sum(len(sp) for _, sp in store.group_by_key['recoil'].sections(True)) > sum(len(sp) for _, sp in sections)


def test_auto_range_and_nice_step():
    assert auto_range(2.0, 'float') == (0.0, 6.0)
    assert auto_range(-0.5, 'float') == (-1.5, 0.0)
    assert auto_range(0.0, 'float') == (-1.0, 1.0)
    assert auto_range(0, 'int') == (-1.0, 1.0) or auto_range(0, 'int')[1] >= 1.0
    assert nice_step(0, 6) == pytest.approx(0.1)
    assert nice_step(0, 1500) == pytest.approx(20)
    assert decimals_for(0.0005) == 4 and decimals_for(0.05) == 2 and decimals_for(1) == 0 and decimals_for(0.1) == 1


def test_format_value_uses_vietnamese_decimal_comma(store):
    assert format_value(store.by_id['gun.accuracy.stand'], 2.0) == '2,00'
    assert format_value(store.by_id['gun.rpm'], 750.0) == '750'
    assert format_value(store.by_id['gun.magazine'], 30) == '30'
    assert format_value(store.by_id['player.sprint_blocks_fire'], True) == 'Bật'
    assert format_value(store.by_id['look.shadows'], True) == 'Thật'
    assert format_value(store.by_id['look.shadows'], 'fake') == 'Giả'
    assert format_value(store.by_id['look.shadows'], False) == 'Tắt'


# --- đặt giá trị ---
def test_set_writes_into_the_live_object(store):
    gun = store.root.gun
    assert store.set(store.by_id['gun.rpm'], 900)
    assert gun.rpm == 900.0 and isinstance(gun.rpm, float)
    assert not store.set(store.by_id['gun.rpm'], 900)                  # không đổi thì False
    store.set(store.by_id['gun.kick.peak[2]'], -0.05)
    assert gun.kick.peak == (0.0, 0.004, -0.05, 1.6, 0.0, 0.0) and isinstance(gun.kick.peak, tuple)
    store.set(store.by_id['gun.tracer.every'], 5.0)
    assert gun.tracer.every == 5 and isinstance(gun.tracer.every, int)
    store.set(store.by_id['player.sprint_blocks_fire'], False)
    assert store.root.player.sprint_blocks_fire is False
    store.set(store.by_id['look.shadows'], 'fake')
    assert store.root.look.shadows == 'fake'


def test_set_clamps_to_range_and_rejects_wrong_types(store):
    s = store.by_id['gun.rpm']
    store.set(s, 99999)
    assert store.root.gun.rpm == s.hi
    store.set(s, -5)
    assert store.root.gun.rpm == s.lo
    for bad in ('900', None, float('nan'), float('inf'), True, [1]):
        with pytest.raises(ValueError):
            store.set(s, bad)
    with pytest.raises(ValueError):
        store.set(store.by_id['player.sprint_blocks_fire'], 1)         # 1 không phải bool
    with pytest.raises(ValueError):
        store.set(store.by_id['look.shadows'], 1)                       # 1 == True nhưng không phải lựa chọn True
    with pytest.raises(ValueError):
        store.set(store.by_id['look.shadows'], 'real')
    with pytest.raises(ValueError):
        store.set(store.by_id['gun.tracer.every'], 2.5)
    assert store.root.gun.rpm == s.lo                                   # lỗi không làm đổi gì


def test_listeners_get_one_call_per_batch(store):
    calls = []
    store.subscribe(lambda specs: calls.append([s.id for s in specs]))
    store.set(store.by_id['gun.rpm'], 800)
    store.set(store.by_id['gun.rpm'], 800)                              # không đổi: không gọi
    assert calls == [['gun.rpm']]
    store.set(store.by_id['gun.ads_time'], 0.3)
    calls.clear()
    assert store.reset_all() == 2
    assert len(calls) == 1 and sorted(calls[0]) == ['gun.ads_time', 'gun.rpm']


def test_reset_one_group_and_all(store):
    store.set(store.by_id['gun.rpm'], 800)
    store.set(store.by_id['gun.recoil.up_scale'], 2.0)
    store.set(store.by_id['gun.kick.peak[3]'], 3.0)
    assert len(store.changed_specs()) == 3
    assert store.reset_group('recoil') == 2
    assert store.root.gun.rpm == 800 and store.root.gun.recoil.up_scale == 1.0 and store.root.gun.kick.peak == M4.kick.peak
    assert store.reset(store.by_id['gun.rpm'])
    assert not store.changed_specs()
    assert store.root.gun.rpm == M4.rpm


def test_defaults_are_snapshotted_before_changes_and_m4_stays_clean():
    params = fresh()
    store = ParamStore(params)
    store.set(store.by_id['gun.rpm'], 1000)
    assert M4.rpm == 750.0                                              # M4 toàn cục không bị bẩn (deepcopy)
    assert store.by_id['gun.rpm'].default == 750.0


# --- lưu / nạp ---
def test_save_load_roundtrip(tmp_path, store):
    for sid, v in (('gun.rpm', 820), ('gun.kick.peak[1]', 0.01), ('gun.tracer.every', 4), ('player.sprint_blocks_fire', False),
                   ('look.shadows', 'fake'), ('look.lamp_color[1]', 0.5), ('gun.recoil.right_scale', -0.5)):
        store.set(store.by_id[sid], v)
    want = {s.id: store.get(s) for s in store.specs}
    path = tmp_path / 'user_params.json'
    assert store.save(path).ok
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['version'] == 1 and set(data['values']) == {s.id for s in store.changed_specs()}   # chỉ ghi số khác mặc định
    other = ParamStore(fresh())
    rep = other.load(path)
    assert rep.ok and rep.applied == 7 and not rep.ignored
    assert {s.id: other.get(s) for s in other.specs} == want
    assert other.root.look.shadows == 'fake' and other.root.gun.kick.peak[1] == 0.01 and other.root.gun.tracer.every == 4
    assert isinstance(other.root.gun.kick.peak, tuple) and isinstance(other.root.gun.tracer.every, int)


def test_load_resets_everything_not_in_the_file(tmp_path, store):
    store.set(store.by_id['gun.rpm'], 800)
    assert store.save(tmp_path / 'a.json').ok
    store.reset_all()
    store.set(store.by_id['gun.ads_time'], 0.5)                          # đổi thứ không có trong file
    assert store.load(tmp_path / 'a.json').ok
    assert store.root.gun.rpm == 800 and store.root.gun.ads_time == M4.ads_time


def test_save_changed_then_load_restores(tmp_path, store):
    path = tmp_path / 'p.json'
    store.set(store.by_id['gun.accuracy.stand'], 1.0)
    store.save(path)
    store.set(store.by_id['gun.accuracy.stand'], 5.0)
    store.set(store.by_id['gun.rpm'], 1200)
    store.load(path)
    assert store.root.gun.accuracy.stand == 1.0 and store.root.gun.rpm == M4.rpm


def test_missing_keys_keep_defaults(store):
    rep = store.apply_dict({'version': 1, 'values': {'gun.rpm': 900}})
    assert rep.ok and rep.applied == 1
    assert store.root.gun.rpm == 900 and store.root.gun.ads_time == M4.ads_time


def test_unknown_keys_are_ignored_and_reported(store):
    rep = store.apply_dict({'version': 1, 'values': {'gun.rpm': 900, 'gun.laser_beam': 1, 'xyz': 3}})
    assert rep.ok and rep.applied == 1
    assert {k for k, _ in rep.ignored} == {'gun.laser_beam', 'xyz'}
    assert store.root.gun.rpm == 900


def test_wrong_types_are_ignored_not_fatal(store):
    rep = store.apply_dict({'version': 1, 'values': {
        'gun.rpm': 'nhanh', 'gun.ads_time': None, 'player.sprint_blocks_fire': 'yes', 'gun.kick.peak[1]': [1, 2],
        'gun.tracer.every': 2.5, 'look.shadows': 'maybe', 'gun.accuracy.stand': float('nan'), 'gun.muzzle_velocity': 650}})
    assert rep.ok and rep.applied == 1 and len(rep.ignored) == 7
    assert store.root.gun.muzzle_velocity == 650 and store.root.gun.rpm == M4.rpm


def test_out_of_range_values_are_clamped(store):
    store.apply_dict({'values': {'gun.rpm': 10 ** 9, 'gun.ads_time': 0.0}})
    assert store.root.gun.rpm == store.by_id['gun.rpm'].hi
    assert store.root.gun.ads_time == store.by_id['gun.ads_time'].lo > 0


def test_bad_files_do_not_crash_or_change_anything(tmp_path, store):
    store.set(store.by_id['gun.rpm'], 800)
    for name, text in (('empty.json', ''), ('junk.json', '{{{ không phải json'), ('list.json', '[1, 2]'),
                       ('novalues.json', '{"version": 1}'), ('badvalues.json', '{"values": [1]}'), ('str.json', '"x"')):
        path = tmp_path / name
        path.write_text(text, encoding='utf-8')
        rep = store.load(path)
        assert not rep.ok and 'giữ nguyên' in rep.message, name
        assert store.root.gun.rpm == 800, name
    rep = store.load(tmp_path / 'khong_co.json')
    assert not rep.ok and store.root.gun.rpm == 800
    (tmp_path / 'bin.json').write_bytes(b'\xff\xfe\x00bad')
    assert not store.load(tmp_path / 'bin.json').ok and store.root.gun.rpm == 800


def test_save_into_missing_folder_reports_instead_of_raising(tmp_path, store):
    rep = store.save(tmp_path / 'khong_co_thu_muc' / 'x.json')
    assert not rep.ok and 'không ghi được' in rep.message


def test_saved_file_is_utf8_json_with_plain_values(tmp_path, store):
    store.set(store.by_id['look.shadows'], 'fake')
    store.set(store.by_id['player.sprint_blocks_fire'], False)
    path = tmp_path / 'x.json'
    store.save(path)
    values = json.loads(path.read_text(encoding='utf-8'))['values']
    assert values == {'look.shadows': 'fake', 'player.sprint_blocks_fire': False}


# --- số sống: các module phải ĐỌC lại số mỗi lần dùng ---
def test_weapon_follows_rpm_changes_live():
    gun = copy.deepcopy(M4)
    w = Weapon(gun)
    w.mag = 10 ** 6
    shots = 0
    for _ in range(60):
        shots += len(w.update(1 / 60, True, False))
    assert shots == pytest.approx(12.5, abs=1)
    gun.rpm = 1500.0
    shots = 0
    for _ in range(60):
        shots += len(w.update(1 / 60, True, False))
    assert shots == pytest.approx(25, abs=1)


def test_camera_recoil_scales_pattern():
    gun = copy.deepcopy(M4)
    a = CameraRecoil(gun.recoil, random.Random(1))
    gun.recoil.noise = 0.0
    a.on_shot()
    up1, right1 = a.pending
    gun.recoil.up_scale, gun.recoil.right_scale = 2.0, -1.0
    b = CameraRecoil(gun.recoil, random.Random(1))
    b.on_shot()
    assert b.pending[0] == pytest.approx(up1 * 2.0) and b.pending[1] == pytest.approx(-right1)
    gun.recoil.up_scale = 0.0
    c = CameraRecoil(gun.recoil, random.Random(1))
    c.on_shot()
    assert c.pending[0] == 0.0


# --- hình nón ---
def test_ring_radius():
    assert ring_radius(0.0, 25.0) == 0.0
    assert ring_radius(2.0, 25.0) == pytest.approx(25 * math.tan(math.radians(2.0)))
    assert ring_radius(10.0, 50.0) == pytest.approx(2 * ring_radius(10.0, 25.0))


@pytest.mark.parametrize('yaw,pitch', [(0, 0), (30, 10), (200, -40), (90, 60)])
def test_shot_offset_matches_the_angle_between(yaw, pitch):
    view = aim_direction(yaw, pitch)
    right, up = shot_offset(view, aim_direction(yaw + 0.5, pitch))
    assert right == pytest.approx(0.5 * math.cos(math.radians(pitch)), abs=0.02) and abs(up) < 0.02
    right, up = shot_offset(view, aim_direction(yaw, pitch - 0.8))             # pitch nhỏ đi = nhìn lên
    assert up == pytest.approx(0.8, abs=0.02) and abs(right) < 0.02
    right, up = shot_offset(view, aim_direction(yaw - 0.3, pitch + 0.4))
    assert math.hypot(right, up) == pytest.approx(angle_between(view, aim_direction(yaw - 0.3, pitch + 0.4)), abs=0.02)
    assert right < 0 and up < 0
    assert shot_offset(view, view) == pytest.approx((0.0, 0.0), abs=1e-6)
