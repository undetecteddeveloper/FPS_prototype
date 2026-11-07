# FPS prototype (Ursina, viewmodel kiểu Bodycam của Reissad Studio)

Game bắn súng góc nhìn thứ nhất bằng Ursina/Panda3D. Từ G7 viewmodel, giật, ánh sáng, ống kính theo kiểu Bodycam (quyết định của người dùng); số "CoD" trong các ghi chú G2-G6 là của bản cũ.
Trả lời, commit, tài liệu bằng tiếng Việt thường. CÁCH LÀM VIỆC (phiên, subagent, tài nguyên AI, multiplayer): `docs/WORKFLOW.md`. Sổ này chỉ giữ phần luôn cần; chi tiết từng giai đoạn ở `docs/notes/` (xem mục cuối).

## Lệnh
- Chạy game: bấm đúp `run.bat` (hoặc `.venv\Scripts\python.exe main.py`; cửa sổ không viền phủ kín màn hình). Tuỳ chọn: `--novsync`, `--window --size 1280x720`, `--quit-after 5` (tự thoát, để kiểm tra), `--mute`, `--defaults` (bỏ qua `user_params.json`).
- Test thuần (toán + nạp glb, không mở cửa sổ): `.venv\Scripts\python.exe -X utf8 -m pytest` (~20 s).
- Bài kiểm tra bằng game thật `tools\selftests\*`: HIỆN KHÔNG CHẠY ĐƯỢC (dựng bằng bia và phòng bắn đã xoá 7/11/2026; người dùng bảo không cần; xem `docs/notes/ground-sky.md`). Cổng kiểm tra dùng pytest + chạy game thật.
  Dạng chạy: `.venv\Scripts\python.exe -X utf8 tools\selftests\g3_selftest.py`. NHIỀU GAME CÙNG LÚC làm bài đo thời gian trượt oan: bọc bằng `.venv\Scripts\python.exe -X utf8 tools\with_game_lock.py <lệnh gốc>` (ổ khoá toàn máy).
- Đo FPS: `tools\measure\g8_perf.py --gun glock|m4` (6 tình huống, ngưỡng 55; `perf_scenarios.py` cũ dựng bằng bia nên không còn chạy); máy nóng/bận cho số thấp bất thường (đo lại một mình khi máy yên).
- Công cụ đo/dựng: `tools\measure\` (đo clip, điểm ngắm, miệng nòng, FPS, chụp ảnh) và `tools\build\` (dựng WAV: `prep_sound`, `prep_foley`, `prep_user_audio`, `prep_elevenlabs`). Danh mục đầy đủ + công tắc tắt để đo (`free_aim=False`, `lens=False`...): `docs/notes/tools.md`.
- Cài lại môi trường: `py -3.13 -m venv .venv` rồi `.venv\Scripts\pip install -r requirements.txt` (KHÔNG dùng Python 3.15).

## Cấu trúc thư mục
```
main.py  run.bat  requirements.txt  pytest.ini  CLAUDE.md  CREDITS.txt        <- root: cửa vào + cấu hình + sổ luật
fps/                    gói mã nguồn (import dạng `from fps.core.movement import ...`)
  app.py                Game, create_game() (dựng tất cả; tools gọi lại hàm này), prune_scene_entities(), main()
  weapon_data.py        MỌI thông số (dataclass)
  core/                 toán thuần, KHÔNG import ursina, có pytest: movement, ballistics, weapon, recoil, spread, spring, sway, handling, fx, shake, cues, footsteps,
                        params + param_meta (bảng F1), freeaim, headcam, gaze (ánh nhìn khi nạp), smoke, lens, exposure
  game/                 phần ghép Ursina/Panda: player, combat, viewmodel, ground (nền đất), sky (bầu trời + mây), smoke (khói súng), hud, gltf_patch, gun_audio, effects, look, shaders, foley, camera_shake,
                        debug_panel (F1), frame_light, lens, decals, gltf_maps
assets/                 tài nguyên: guns/ (glb), sounds/ (wav; source/ = file gốc, mp3 ElevenLabs, candidates/), shaders/ (GLSL, light_common.glsl dùng chung)
tests/                  pytest
tools/                  selftests/ (bài kiểm tra bằng game thật), measure/ (đo, chụp), build/ (dựng âm thanh), with_game_lock.py
docs/                   WORKFLOW.md, notes/ (ghi chú theo chủ đề), images/ (ảnh tư thế các giai đoạn)
backups/  shots/        file lưu cũ của bảng F1 / ảnh chụp của bài kiểm tra (cả hai gitignore)
```
- `fps/game/__init__.py` để TRỐNG có chủ đích: `fps.game.gltf_patch` phải nạp được trước khi import ursina.
  `main.py` ở root chỉ re-export `create_game`, `main` (các tools gọi `from main import create_game`).
- Tài nguyên mới (ảnh, model 3D, âm) vào `assets/`; nguồn gốc + prompt giữ trong `assets/<loại>/source/` (xem WORKFLOW mục 6).

## Quy ước
- Mọi thông số súng/recoil/spread/sway nằm trong `fps/weapon_data.py` (dataclass). Không rải số ra module khác.
- Toán mới thì tách ra `fps/core/` (không import ursina) để pytest được; chỉ phần cần Ursina/Panda mới vào `fps/game/`.
- Thứ tự mỗi khung hình cố định trong `Game.update`: `player.tick()` -> `combat.update()` -> `sway.update()` -> `head.update` + `shake_view.frame_offset` -> `viewmodel.update(kick, sway, free_aim, free_look)` -> `light.set_camera/set_exposure` -> `smoke.update` -> `lens.update(..., frame)`.
  Camera thế giới KHÔNG rung: mọi rung (bước, nhảy, bắn, nạp, ánh nhìn khi nạp) thành dịch + nghiêng cả khung ống kính (`game/camera_shake.py`, `core/lens.frame_shake`, `lens.frag`).
  Đừng để từng đối tượng tự `update` riêng (thứ tự Ursina không đảm bảo, bắn sẽ dùng hướng nhìn của khung trước).
- Cổng kiểm tra trước mỗi commit: pytest qua, game mở được và ≥ 60 FPS, không lỗi trong console.
- Thế giới là MỘT khối đất phẳng trắng + lưới + bầu trời mây (không bia, không phòng, không bóng đổ); đừng dựng lại phòng bắn khi chưa được hỏi.
- Commit trên nhánh `dev`. Chỉ push khi người dùng nói. `assets\guns\animated_fps_hands_rifle_animation_pack.glb` (109 MB) bị gitignore.
- Comment và docstring trong mã viết bằng TIẾNG ANH (đã dịch toàn bộ mã hiện có 6/11/2026, xem `docs/WORKFLOW.md` 6c; mã mới phải giữ như vậy). Chữ cho người dùng (HUD, bảng F1, tên mục selftest, thông báo) và file `.md` vẫn tiếng Việt.
- Mức hỏi người dùng theo cỡ việc (nhỏ: tối đa 1 vòng ngắn; lớn: luôn 2 vòng ý tưởng + kỹ thuật): `docs/WORKFLOW.md` 1b. Luật này thắng luật chung "tự quyết kỹ thuật" khi làm dự án này.
- HỌC TRƯỚC KHI LÀM: chủ đề chưa có skill kiến thức trong `.claude/skills/` thì học sâu (WebSearch) và lưu skill trước, giao thức ở skill `learn-first`; Blender dùng để sửa model, rigging, animation (`docs/WORKFLOW.md` 6d, 6e).
- Tài nguyên AI: xem/nghe xong mới được duyệt, chi tiêu theo phong bì và ghi `docs/credits.md` (`docs/WORKFLOW.md` 6, 6b).

## Nạp M4 (bẫy đã trả giá ở G0, đừng làm lại)
- LUÔN `from fps.game import gltf_patch; gltf_patch.apply()` trước khi tạo `Ursina()` hay nạp glb (`fps/app.py` và các tools đã làm). `panda3d-gltf 1.3.0` nạp sai file này theo
  6 cách (xem docstring `gltf_patch.py`). `tests\test_gltf_load.py` bắt từng lỗi; đổi phiên bản thư viện thì chạy lại.
- Mô hình tính bằng **cm**, quay mặt về −Z. Đặt dưới `Entity(scale=0.01, rotation_y=180)`. Mắt (khớp `FPS_Camera_j_01`) ở
  (−0.011, 1.539, −0.101) trong hệ của Entity đó; súng cách mắt ~10 cm xuống, ~22 cm ra trước, lệch phải ~7 cm.
- Khoảng khung HỢP LỆ của từng clip (30 fps; khung N của clip có N khung bị bao về 0, nên dùng khung cuối N−1):
  Reload 1–110 · Reload_Empty 111–224 · Fire 226–249 · Holster 251–268 · Draw 269–299.
  Chạy thật: `actor.play(clip, fromFrame=a, toFrame=b)`. Đo được lệch ≤ 0,04 s so với dự kiến.
- `actor.pose()` không tự cập nhật khớp: gọi thêm `actor.getPartBundle('modelRoot').force_update()` (chỉ cần khi pose bằng tay).
- Phần súng không skin (Bolt, Mag1, Trigger...) đi theo nút `<Tên>_M4_D_0-parent`. Gốc của nút này nằm ở (0,0,0) khi ở tư thế
  bind, vì đỉnh mesh là toạ độ tuyệt đối. Muốn biết vị trí thật thì dùng `getTightBounds`.
- `Mag2` và hai viên đạn là đồ của clip reload: ngoài reload chúng lơ lửng bên dưới/phải súng. Ẩn chúng khi không reload.
- Cẳng tay trái có vân da xoáy (da bị xoắn quanh trục): đặc tính của asset, chỉ lộ một mẩu ở mép dưới-trái màn hình.
- File CÓ normal map và tangent; `gltf_patch` bỏ chúng lúc nạp model (đường cố định của Panda không dùng được) còn `game/gltf_maps.py` đọc lại cho shader súng. Thân súng có specular 0 trong file: độ bóng là số chỉnh tay (`ViewLightData`).

## Ursina/Windows
- `Ursina(vsync=False)` một mình KHÔNG tắt vsync. Muốn đo FPS thật: `loadPrcFileData('', 'sync-video 0')` trước `Ursina()`.
  Game thật chạy vsync (khóa ở tần số màn hình, 60 Hz); sức máy đo được khi phát clip: trung bình 218, thấp nhất 106 FPS.
- `color.rgb(r,g,b)` của Ursina 8 nhận 0–1, không phải 0–255.
- Console Windows mặc định cp1252: in tiếng Việt cần `PYTHONUTF8=1` hoặc `-X utf8` hoặc `sys.stdout.reconfigure(encoding='utf-8')`.
  (Cờ `-I` của Python bỏ qua `PYTHONUTF8`; dùng `-X utf8`.)
- Panda cache model trên đĩa (`%LOCALAPPDATA%\Panda3D-1.10`). `gltf_patch.apply()` đã tắt cache đó; nạp M4 mất ~1,5 s.
- Màn hình máy này 1366×768: cửa sổ test dùng 1280×720.


## Tài liệu theo chủ đề (mở khi đụng tới, đừng đọc hết)
- [`docs/WORKFLOW.md`](docs/WORKFLOW.md): cách làm việc (phiên, subagent, tài nguyên AI, hướng multiplayer). ĐỌC ĐẦU MỖI PHIÊN.
- [`docs/notes/tools.md`](docs/notes/tools.md): Danh mục đầy đủ công cụ, bài kiểm tra và công tắc tắt để đo. Mở khi cần chạy / thêm một bài kiểm tra hoặc công cụ đo.
- [`docs/notes/viewmodel-world.md`](docs/notes/viewmodel-world.md): G1: viewmodel, camera, độ sâu, hiệu năng nền. Mở khi đụng tới viewmodel, camera, chuột nhìn, FOV.
- [`docs/notes/shooting-targets.md`](docs/notes/shooting-targets.md): G2: bắn, đạn, bia, lỗ đạn, chữ HUD. Mở khi đụng tới đạn, nhịp bắn, bia, lỗ đạn, UiText.
- [`docs/notes/recoil-spread-kick.md`](docs/notes/recoil-spread-kick.md): G3: recoil, độ tản, bloom, kick súng. Mở khi đụng tới giật, độ tản, tâm ngắm, kick.
- [`docs/notes/ads-sway-audio.md`](docs/notes/ads-sway-audio.md): G4: ngắm (ADS), sway, bob, chạy nước rút, tiếng súng. Mở khi đụng tới ngắm, sway, bob, sprint, gun_audio.
- [`docs/notes/reload-fx-shaders.md`](docs/notes/reload-fx-shaders.md): G5: rút súng, nạp đạn, tia lửa, tracer, shader. Mở khi đụng tới nạp / rút súng, animation, tia lửa, tracer, shader súng.
- [`docs/notes/ground-sky.md`](docs/notes/ground-sky.md): 7/11/2026: nền đất trắng + lưới, ánh sáng mặt trời, bầu trời có mây, Glock 17 mới (gói animation), những thứ đã xoá. Mở khi đụng tới nền, ánh sáng, bầu trời, Glock, `gltf_patch`.
- [`docs/notes/range-lights-signs.md`](docs/notes/range-lights-signs.md): G6 (PHẦN PHÒNG, ĐÈN, BÓNG, BIA, BIỂN ĐÃ BỊ XOÁ; còn đúng: shake, bảng F1, âm thanh foley). Mở khi đụng tới shake, bảng F1, foley, bước chân.
- [`docs/notes/bodycam.md`](docs/notes/bodycam.md): G7: kiểu Bodycam (chuột đưa súng, đạn theo nòng, camera đầu, ống kính, ánh sáng, hiệu năng, âm thanh ElevenLabs). Mở khi đụng tới FreeLook / FreeAim, headcam, lens, exposure, ánh sáng thống nhất, âm thanh G7.
