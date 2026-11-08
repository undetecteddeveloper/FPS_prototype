"""Bakes the numbers tuned on the F1 panel (user_params.json) into the DEFAULTS in fps/weapon_data.py.

Run:  .venv\\Scripts\\python.exe -X utf8 tools\\build\\bake_params.py            prints only the table of changes (writes nothing)
       .venv\\Scripts\\python.exe -X utf8 tools\\build\\bake_params.py --apply    writes to weapon_data.py

With --apply: fixes the exact values (keeps the comments), then reruns in a new process to check EACH number; on any mismatch the old file is restored.
On success: the old user_params.json moves to backups\\user_params.baked.<date-time>.json, and user_params.json keeps only the numbers that could not be baked.
Numbers that cannot be baked automatically (by default, anything that is not a plain literal) are listed and need a manual fix. After baking: run pytest and record the changes in CLAUDE.md / docs/notes.

Per gun (8/11/2026): the file keeps each gun apart. The M4's numbers are baked into the class defaults as before; the Glock's (or any other gun's) are only
PRINTED with the line to add in `GLOCK = GunData(...)` (user choice: Claude edits them by hand) and stay in user_params.json. An M4 bake must not change
another gun: the Glock inherits many class defaults, so after writing, every gun slider of every other gun is compared with before; any difference restores
the old file and lists the fields to pin in that gun's GunData first.
"""
import argparse
import copy
import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from fps.core.bake import edits_for, patch_source  # noqa: E402
from fps.core.params import ParamStore, _GunHolder, format_value, is_gun_spec, resolve  # noqa: E402
from fps.core.safeio import write_text_atomic  # noqa: E402
from fps.weapon_data import GUNS, GameParams  # noqa: E402

TARGET = ROOT / 'fps' / 'weapon_data.py'
CHECK = '''
import json, sys
sys.path.insert(0, sys.argv[1])
from fps.weapon_data import GameParams
from fps.core.params import ParamStore
store = ParamStore(GameParams())
bad = []
for key, want in json.load(sys.stdin).items():
    spec = store.by_id[key]
    got = store.get(spec)
    if not (got == want and type(got) is type(want)):
        bad.append((key, got, want))
others = {}
from fps.weapon_data import GUNS
from fps.core.params import is_gun_spec, _GunHolder
for k, g in GUNS.items():
    if k != 'm4':
        others[k] = {s.id: repr(store._get_from(_GunHolder(g), s)) for s in store.specs if is_gun_spec(s)}
print(json.dumps([bad, others]))
'''


def other_guns_now(store) -> dict:
    """repr of every gun slider of every gun but the M4, as weapon_data has them NOW (to prove an M4 bake left them alone)."""
    from fps.core.params import _GunHolder, is_gun_spec
    return {k: {s.id: repr(store._get_from(_GunHolder(g), s)) for s in store.specs if is_gun_spec(s)} for k, g in GUNS.items() if k != 'm4'}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--apply', action='store_true', help='ghi vào weapon_data.py (mặc định chỉ in bảng)')
    ap.add_argument('--file', default=str(ROOT / 'user_params.json'), help='file bảng F1 đã lưu')
    args = ap.parse_args()
    user_file = Path(args.file)

    defaults = ParamStore(copy.deepcopy(GameParams()))
    store = ParamStore(copy.deepcopy(GameParams()))
    report = store.load(user_file)
    print(f'[{user_file.name}] {report.message}')
    if not report.ok:
        return 1
    for key, why in report.ignored:
        print(f'  bỏ qua {key}: {why}')
    other_changes = {k: store.gun_changes(k) for k in store.gun_keys() if k != 'm4'}
    other_changes = {k: v for k, v in other_changes.items() if v}
    for k, vals in other_changes.items():
        g = GUNS[k]
        print(f'\n{GUNS[k].name}: {len(vals)} số riêng, KHÔNG chốt tự động (sửa tay trong `{k.upper()} = GunData(...)` của weapon_data.py, rồi xoá khỏi user_params.json):')
        for sid, v in sorted(vals.items()):
            spec = store.by_id[sid]
            old = store._get_from(_GunHolder(g), spec)
            print(f'  {sid:<38} {spec.label[:34]:<34} {format_value(spec, old):>10} -> {format_value(spec, v):<10}')
    changed = store.changed_specs()
    if not changed:
        print('\nM4 và phần chung: không có số nào khác mặc định: không có gì để chốt tự động.')
        return 0

    print(f'\n{len(changed)} số khác mặc định:')
    for s in changed:
        print(f'  {s.id:<38} {s.label[:34]:<34} {format_value(s, defaults.by_id[s.id].default):>10} -> {format_value(s, store.get(s)):<10}')

    original = TARGET.read_bytes().decode('utf-8')
    new_text, failures = patch_source(original, edits_for(store.root, changed))
    failed_ids = set()
    for edit, why in failures:
        ids = [s.id for s in changed if s.attr == edit.attr and type(resolve(store.root, s.path)).__name__ == edit.owner]
        failed_ids.update(ids)
        print(f'\nKHÔNG chốt tự động được {edit.owner}.{edit.attr} ({", ".join(ids)}): {why}. Sửa tay trong weapon_data.py.')
    if not args.apply:
        print('\n(Chưa ghi gì. Thêm --apply để chốt.)')
        return 0
    if new_text == original:
        print('\nKhông có gì để ghi.')
        return 1

    others_before = other_guns_now(defaults)
    TARGET.write_bytes(new_text.encode('utf-8'))
    baked = {s.id: store.get(s) for s in changed if s.id not in failed_ids}
    proc = subprocess.run([sys.executable, '-X', 'utf8', '-c', CHECK, str(ROOT)], input=json.dumps(baked), capture_output=True, encoding='utf-8', cwd=ROOT)
    try:
        bad, others_after = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError, ValueError):
        bad, others_after = [('(không chạy lại được)', proc.stderr.strip()[-300:], '')], others_before
    drift = {k: [(sid, v, others_after.get(k, {}).get(sid)) for sid, v in vals.items() if others_after.get(k, {}).get(sid) != v] for k, vals in others_before.items()}
    drift = {k: v for k, v in drift.items() if v}
    if bad or drift:
        TARGET.write_bytes(original.encode('utf-8'))
        if bad:
            print('\nĐỐI CHIẾU SAI, đã khôi phục weapon_data.py như cũ:')
            for item in bad:
                print('  ', item)
        for k, items in drift.items():
            print(f'\n{GUNS[k].name} dùng chung mặc định của lớp nên SẼ BỊ ĐỔI THEO M4; đã khôi phục weapon_data.py như cũ. Ghim số cũ vào `{k.upper()} = GunData(...)` trước rồi chạy lại:')
            for sid, before, after in items:
                print(f'  {sid:<38} giữ {before} (nếu chốt sẽ thành {after})')
        return 1

    backups = ROOT / 'backups'
    backups.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M')
    backup = backups / f'user_params.baked.{stamp}.json'
    backup.write_bytes(user_file.read_bytes())
    left_shared = {s.id: store.get(s) for s in changed if s.id in failed_ids and not is_gun_spec(s)}
    left_guns = {'m4': {s.id: store.get(s) for s in changed if s.id in failed_ids and is_gun_spec(s)}, **other_changes}
    left_guns = {k: v for k, v in left_guns.items() if v}
    write_text_atomic(user_file, json.dumps({'version': 2, 'values': left_shared, 'guns': left_guns}, ensure_ascii=False, indent=2))
    n_left = len(left_shared) + sum(len(v) for v in left_guns.values())
    print(f'\nĐÃ CHỐT {len(baked)} số vào {TARGET.relative_to(ROOT)}, đối chiếu từng số đều khớp; súng khác không đổi.')
    print(f'Bản cũ của bảng F1: {backup.relative_to(ROOT)}; {user_file.name} còn {n_left} số chưa chốt (gồm số riêng của súng khác, sửa tay).')
    print('Việc tiếp: chạy pytest, ghi các số mới vào docs/notes (mục "mặc định đã chốt"), commit.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
