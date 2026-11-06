"""Bakes the numbers tuned on the F1 panel (user_params.json) into the DEFAULTS in fps/weapon_data.py.

Run:  .venv\\Scripts\\python.exe -X utf8 tools\\build\\bake_params.py            prints only the table of changes (writes nothing)
       .venv\\Scripts\\python.exe -X utf8 tools\\build\\bake_params.py --apply    writes to weapon_data.py

With --apply: fixes the exact values (keeps the comments), then reruns in a new process to check EACH number; on any mismatch the old file is restored.
On success: the old user_params.json moves to backups\\user_params.baked.<date-time>.json, and user_params.json keeps only the numbers that could not be baked.
Numbers that cannot be baked automatically (by default, anything that is not a plain literal) are listed and need a manual fix. After baking: run pytest and record the changes in CLAUDE.md / docs/notes.
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
from fps.core.params import ParamStore, format_value, resolve  # noqa: E402
from fps.weapon_data import GameParams  # noqa: E402

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
print(json.dumps(bad))
'''


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
    changed = store.changed_specs()
    if not changed:
        print('Không có số nào khác mặc định: không có gì để chốt.')
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

    TARGET.write_bytes(new_text.encode('utf-8'))
    baked = {s.id: store.get(s) for s in changed if s.id not in failed_ids}
    proc = subprocess.run([sys.executable, '-X', 'utf8', '-c', CHECK, str(ROOT)], input=json.dumps(baked), capture_output=True, encoding='utf-8', cwd=ROOT)
    try:
        bad = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        bad = [('(không chạy lại được)', proc.stderr.strip()[-300:], '')]
    if bad:
        TARGET.write_bytes(original.encode('utf-8'))
        print('\nĐỐI CHIẾU SAI, đã khôi phục weapon_data.py như cũ:')
        for item in bad:
            print('  ', item)
        return 1

    backups = ROOT / 'backups'
    backups.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M')
    backup = backups / f'user_params.baked.{stamp}.json'
    backup.write_bytes(user_file.read_bytes())
    left = {s.id: store.get(s) for s in changed if s.id in failed_ids}
    user_file.write_text(json.dumps({'version': 1, 'values': left}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nĐÃ CHỐT {len(baked)} số vào {TARGET.relative_to(ROOT)}, đối chiếu từng số đều khớp.')
    print(f'Bản cũ của bảng F1: {backup.relative_to(ROOT)}; {user_file.name} còn {len(left)} số chưa chốt được.')
    print('Việc tiếp: chạy pytest, ghi các số mới vào docs/notes (mục "mặc định đã chốt"), commit.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
