---
name: game-stability-qa
description: The release-quality bar used for this single-player PC FPS (researched 2026-11-07, G16) - Microsoft XR-001 Title Stability / XR-003 Title Integrity, the top PC certification failures, indie release-checklist numbers (crash-free sessions, first-launch success, memory growth, load times), bug severity levels, and the 22-item checklist that applies here (crash/hang, silent death, static screen, focus loss, corrupted settings/caches, atomic writes, long sessions). Use when auditing for crashes / hangs / broken assets, judging whether the game is "good enough to send", adding a file the game writes, or touching start-up error handling, window focus, or tools/measure/chaos_check.py.
---

# Game stability / completeness bar (researched 2026-11-07, G16)

## Sources and what they require
- Microsoft XR-001 "Title Stability" (Xbox Requirements, also PC): no crash, no hang, no loss of user data; FAIL examples: a non-interactive static
  screen > 20 s; a loading screen > 2 min without progress; a crash WITHOUT user notification.
  https://learn.microsoft.com/en-us/gaming/gdk/docs/store/policies/pc/live-policy-tests-pc
- XR-003 "Title Integrity": no crashes, freezes, unplayable frame rates, graphical corruption, progression blockers (stuck / fall out of map);
  in-game options must persist after relaunch; keyboard + mouse must work (fail: cannot reload, gets stuck).
- Top failing PC test cases: 001-01 stability = 34% of failures. Testers try 1366x768 .. 4K, windowed and fullscreen, RANDOM INPUT on every screen,
  rapidly entering / leaving menus. https://learn.microsoft.com/zh-tw/gaming/gdk/_content/gc/policies/pc/live-topfailingtestcases-pc
- Indie release checklist (Bugnet, blog numbers, not a platform rule): zero P0/P1 bugs; crash-free sessions >= 99.5% (99% = 1 in 100 sessions
  crashes, bad reviews); >= 99% first launches succeed; memory must not grow over a long session; corrupt a save -> game must not crash;
  kill mid-save -> recovers; 99th-percentile frame time <= 2x median; initial load <= 15 s.
  https://bugnet.io/blog/game-release-checklist-qa-stability-performance , https://bugnet.io/blog/crash-free-rate-game-metric
- Severity ladder (common to most studios): Blocker/P0 = crash or unplayable (ship-stopper), Critical/P1 = main feature broken, Major/P2 =
  noticeable with workaround, Minor = cosmetic. https://bugnet.io/blog/bug-severity-classification-for-game-developers
- Alt-tab / focus (PC norm): decide per game (pause / mute / keep running); clear held input on focus loss (missed key-up = stuck key);
  borderless window avoids exclusive-fullscreen device loss. This game: release mouse + keys, mute, keep running (user's choice, G15 notes).

## Not applicable here
Xbox Live, achievements, accounts, cloud saves, multiplayer joins, store metadata, Steam Deck (controller, 1280x800 text) - single-player PC prototype.

## The 22-item checklist (status lives in docs/sessions/G16.md)
A stability: launch >= 99% | no crash/hang under random input | unexpected Python error -> dialog + logs/crash.log, then exit | native crash logged
| no static screen > 20 s (bake shows progress) | low memory -> clear message | window close exits cleanly | a 2 s hitch does not explode physics.
B integrity: never stuck / out of map | gun state never stuck (hidden, reload, switch, ammo) | no NaN on camera / gun | options persist | FPS.
C data: corrupt settings never kill the start | settings + caches written atomically (temp file + os.replace) | corrupt bake cache -> rebake
| missing asset -> message naming the file.
D window/input: focus loss releases mouse + keys, mutes; regain = no camera jump, no stray shot | bad CLI args -> message | no monitor info -> fallback.
E long session: 10 min -> no memory growth | node / entity / sound counts bounded.

## Lessons
- Every file the game reads back must survive: missing, empty, truncated, wrong JSON shape (list instead of object, wrong value types).
- A Panda task exception propagates out of `app.run()`: catch there (and around `create_game`) to log + show a message box; the windowed exe has
  no console, so a print is invisible to the player.
