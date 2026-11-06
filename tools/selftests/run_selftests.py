"""Runs the real-game tests one after another (one window per test, through the machine-wide lock). Prints the FAILED items and a summary. Exits with code 1 if any test fails.

Run: .venv\\Scripts\\python.exe -X utf8 tools\\selftests\\run_selftests.py [test name ...]       (default: all)
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding='utf-8')
ALL = ['g1_selftest', 'g2_selftest', 'g3_selftest', 'g4_selftest', 'g5_selftest', 'g6_shake_selftest', 'g6_targets_selftest', 'g6_debug_selftest',
       'g7_selftest', 'audio_selftest']
PY = str(ROOT / '.venv' / 'Scripts' / 'python.exe')
wanted = sys.argv[1:] or ALL
failed = []
for name in wanted:
    proc = subprocess.run([PY, '-X', 'utf8', str(ROOT / 'tools' / 'with_game_lock.py'), PY, '-X', 'utf8', str(ROOT / 'tools' / 'selftests' / f'{name}.py')],
                          cwd=ROOT, capture_output=True, encoding='utf-8', errors='replace')
    lines = proc.stdout.splitlines() + proc.stderr.splitlines()
    summary = next((ln for ln in reversed(lines) if re.search(r'\d+/\d+ mục', ln)), '(không có dòng tổng kết)')
    print(f'=== {name}: mã {proc.returncode}  {summary.strip()}')
    for ln in lines:
        if 'TRƯỢT' in ln or 'Traceback' in ln or re.match(r'^\s*(\w+Error|File ")', ln) or ':glgsg(error)' in ln or 'error:' in ln.lower():
            print('   ', ln[:190])
    if proc.returncode != 0:
        failed.append(name)
print('TRƯỢT: ' + ', '.join(failed) if failed else 'TẤT CẢ ĐẠT')
sys.exit(1 if failed else 0)
