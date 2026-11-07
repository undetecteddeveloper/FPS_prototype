"""What the game does when the machine is short of virtual memory at start-up (pure; tests/test_memplan.py).

Windows refuses a memory request once COMMIT (RAM + page file, minus what every program already reserved) is used up, and the game then dies inside whatever native call asked
(G11 session, 2026-11-07: an access violation in `copy_data_from` while loading the gun's glb, 3 s after launch; docs/notes/troubleshooting.md). The free commit of the laptop swings
between ~0.7 and ~2.1 GB with whatever else is open, and the game takes 0.62 GB (0.72 GB with 4x MSAA), so it fails whenever the others happen to leave less than that.
The plan reads the FREE commit once, before the window opens, and picks how much to build:
  full      everything the saved settings ask for;
  reduced   no MSAA (-0.1 GB) and the second gun is built on the first weapon switch, not at start-up (-0.12 GB; that one switch then takes one long frame);
  critical  not even the reduced game fits: do not start (a clear message instead of a crash half way through the build).
"""
from dataclasses import dataclass

FULL_MB = 950.0              # peak commit of the full game (742 MB measured with 4x MSAA) + a margin: other programs keep allocating while the game builds
REDUCED_MB = 700.0           # the reduced game peaks at 0.50-0.61 GB (measured with the machine busy, G11 session) + a margin of at least 0.1 GB
NOTICE_REDUCED = 'Máy thiếu bộ nhớ ảo: đã tắt khử răng cưa, súng thứ hai nạp muộn (chi tiết ở console)'      # the one line shown on screen (fps/game/hud.py Notice)


@dataclass(frozen=True)
class MemoryPlan:
    mode: str                # 'full' | 'reduced' | 'critical'
    low_memory: bool         # True: build the reduced game
    free_mb: float           # the free commit this was decided on (-1 = unknown)
    message: str             # for the user (Vietnamese, long: console / message box); '' when nothing needs saying
    notice: str = ''         # the short line for the screen ('' = none)


def plan(free_mb, force_reduced: bool = False) -> MemoryPlan:
    """`free_mb` = free commit in MB (None when the machine cannot tell: the full game, as before). `force_reduced` = the --low-memory flag."""
    if free_mb is None:
        return MemoryPlan('reduced' if force_reduced else 'full', force_reduced, -1.0, 'Đã bật chế độ giảm tải (--low-memory).' if force_reduced else '', NOTICE_REDUCED if force_reduced else '')
    free = float(free_mb)
    if free < REDUCED_MB:
        return MemoryPlan('critical', True, free,
                          f'Máy chỉ còn {free:.0f} MB bộ nhớ ảo (commit) trống, game cần ít nhất ~{REDUCED_MB:.0f} MB. '
                          'Đóng bớt ứng dụng (Chrome, Zalo, trình soạn thảo...) rồi mở lại; muốn hết hẳn thì tăng pagefile (docs/notes/troubleshooting.md).')
    if free < FULL_MB or force_reduced:
        why = 'theo yêu cầu (--low-memory)' if force_reduced and free >= FULL_MB else f'máy còn {free:.0f} MB bộ nhớ ảo trống'
        return MemoryPlan('reduced', True, free,
                          f'Đang chạy chế độ giảm tải ({why}): tắt khử răng cưa, súng thứ hai nạp ở lần đổi súng đầu tiên. '
                          'Đóng bớt ứng dụng hoặc tăng pagefile để chạy đủ (docs/notes/troubleshooting.md).', NOTICE_REDUCED)
    return MemoryPlan('full', False, free, '')
