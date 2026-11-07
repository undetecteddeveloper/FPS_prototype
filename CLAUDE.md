# FPS prototype (Ursina, viewmodel kiểu Bodycam của Reissad Studio)

Game bắn súng góc nhìn thứ nhất bằng Ursina/Panda3D. Từ G7 viewmodel, giật, ánh sáng, ống kính theo kiểu Bodycam (quyết định của người dùng); số "CoD" trong ghi chú G2-G6 là của bản cũ.
Trả lời, commit, tài liệu bằng tiếng Việt thường. Cách làm việc (hỏi theo cỡ việc, phiên, subagent): `docs/WORKFLOW.md`, ĐỌC ĐẦU MỖI PHIÊN. Chi tiết từng giai đoạn: `docs/notes/` (danh sách cuối file).

## Lệnh
- Chạy game: `run.bat` (hoặc `.venv\Scripts\python.exe main.py`; cửa sổ không viền phủ kín). Tuỳ chọn: `--novsync`, `--window --size 1280x720`, `--quit-after 5`, `--mute`, `--defaults` (bỏ `user_params.json`).
- Test thuần (toán + nạp glb, không mở cửa sổ): `.venv\Scripts\python.exe -X utf8 -m pytest` (~30 s).
- `tools\selftests\*` HIỆN KHÔNG CHẠY ĐƯỢC (dựng bằng bia và phòng bắn đã xoá 7/11/2026; người dùng bảo không cần). Cổng kiểm tra = pytest + chạy game thật. Nhiều game cùng lúc làm bài đo thời gian trượt oan: bọc `.venv\Scripts\python.exe -X utf8 tools\with_game_lock.py <lệnh gốc>`.
- Đo FPS: `tools\measure\g8_perf.py --gun glock|m4` (6 tình huống, ngưỡng 55; máy nóng/bận cho số thấp, đo lại một mình). Kiểm rút/đổi súng: `tools\measure\swap_check.py`. Chụp tư thế: `tools\measure\g8_shots.py`.
- Công cụ đo/dựng: `tools\measure\`, `tools\build\` (dựng WAV). Danh mục + công tắc tắt để đo (`free_aim=False`, `lens=False`...): `docs/notes/tools.md`.
- Cài lại môi trường: `py -3.13 -m venv .venv` rồi `.venv\Scripts\pip install -r requirements.txt` (KHÔNG dùng Python 3.15).

## Cấu trúc
```
main.py  run.bat  requirements.txt  pytest.ini  CLAUDE.md  CREDITS.txt    <- cửa vào, cấu hình, sổ luật
fps/        app.py (Game, create_game() dựng tất cả, prune_scene_entities(), main()), weapon_data.py (MỌI thông số, dataclass)
  core/     toán thuần, KHÔNG import ursina, có pytest: movement, ballistics, weapon, recoil, spread, spring, sway, handling, fx, shake, cues, footsteps, params + param_meta (bảng F1),
            freeaim, headcam, gaze, smoke, lens, exposure, easing
  game/     ghép Ursina/Panda: player, combat, viewmodel, ground, sky, smoke, hud, gltf_patch, gun_audio, effects, look, shaders, foley, camera_shake, debug_panel (F1), frame_light, lens, decals, gltf_maps
assets/     guns/ (glb), sounds/ (wav; source/ = gốc, mp3 ElevenLabs, candidates/), shaders/ (GLSL, light_common.glsl dùng chung)
tests/  tools/ (selftests, measure, build, with_game_lock.py)  docs/ (WORKFLOW.md, notes/, sessions/, images/)  backups/ shots/ (gitignore)
```
- `fps/game/__init__.py` để TRỐNG có chủ đích: `fps.game.gltf_patch` phải nạp được trước khi import ursina. `main.py` chỉ re-export `create_game`, `main` (tools gọi `from main import create_game`).
- Tài nguyên mới vào `assets/`; nguồn + prompt giữ trong `assets/<loại>/source/`.

## Quy ước
- Mọi thông số súng/recoil/spread/sway nằm trong `fps/weapon_data.py`. Toán mới tách ra `fps/core/` (không import ursina) để pytest được; chỉ phần cần Ursina/Panda mới vào `fps/game/`.
- Thứ tự mỗi khung hình cố định trong `Game.update`: `player.tick()` -> `combat.update()` -> `sway.update()` -> `head.update` + `shake_view.frame_offset` -> `viewmodel.update(kick, sway, free_aim, free_look)` -> `light.set_camera/set_exposure` -> `smoke.update` -> `lens.update(..., frame)`.
  Đừng để từng đối tượng tự `update` riêng (thứ tự Ursina không đảm bảo, bắn sẽ dùng hướng nhìn của khung trước).
  Camera thế giới KHÔNG rung: mọi rung (bước, nhảy, bắn, nạp, ánh nhìn khi nạp) thành dịch + nghiêng cả khung ống kính (`game/camera_shake.py`, `core/lens.frame_shake`, `lens.frag`).
- Cổng kiểm tra trước mỗi commit: pytest qua, game mở được và ≥ 60 FPS, không lỗi console.
- Thế giới là MỘT khối đất phẳng trắng + lưới + bầu trời mây (không bia, phòng, bóng đổ); đừng dựng lại phòng bắn khi chưa được hỏi.
- Commit trên nhánh `dev`; chỉ push khi người dùng nói. `assets\guns\animated_fps_hands_rifle_animation_pack.glb` (109 MB) bị gitignore.
- Comment và docstring trong mã viết bằng TIẾNG ANH (cả mã mới). Chữ cho người dùng (HUD, bảng F1, tên mục selftest, thông báo) và file `.md` vẫn tiếng Việt.
- Mức hỏi người dùng theo cỡ việc: `docs/WORKFLOW.md` mục 2 (thắng luật chung "tự quyết kỹ thuật").
- HỌC TRƯỚC KHI LÀM: chủ đề chưa có skill trong `.claude/skills/` thì học sâu (WebSearch) và lưu skill trước (skill `learn-first`). Blender dùng để sửa model, rigging, animation.
- Tài nguyên AI: xem/nghe xong mới được duyệt; chi tiêu theo phong bì, ghi `docs/credits.md` (`docs/notes/ai-assets.md`).

## Nạp M4 (bẫy đã trả giá ở G0, đừng làm lại)
- LUÔN `from fps.game import gltf_patch; gltf_patch.apply()` trước khi tạo `Ursina()` hay nạp glb (`fps/app.py` và tools đã làm). `panda3d-gltf 1.3.0` nạp sai file này 6 cách (xem docstring `gltf_patch.py`); `tests\test_gltf_load.py` bắt từng lỗi, đổi phiên bản thư viện thì chạy lại.
- Mô hình tính bằng **cm**, mặt về −Z. Đặt dưới `Entity(scale=0.01, rotation_y=180)`. Mắt (khớp `FPS_Camera_j_01`) ở (−0.011, 1.539, −0.101) trong hệ Entity đó; súng cách mắt ~10 cm xuống, ~22 cm ra trước, lệch phải ~7 cm.
- Khoảng khung HỢP LỆ của clip (30 fps; khung N của clip có N khung bị bao về 0, dùng khung cuối N−1): Reload 1–110 · Reload_Empty 111–224 · Fire 226–249 · Holster 251–268 · Draw 269–299. Chạy: `actor.play(clip, fromFrame=a, toFrame=b)` (lệch ≤ 0,04 s).
- `actor.pose()` không tự cập nhật khớp: gọi thêm `actor.getPartBundle('modelRoot').force_update()` (chỉ khi pose bằng tay).
- Phần súng không skin (Bolt, Mag1, Trigger...) đi theo nút `<Tên>_M4_D_0-parent`, gốc ở (0,0,0) lúc bind pose vì đỉnh mesh là toạ độ tuyệt đối; muốn vị trí thật dùng `getTightBounds`.
- `Mag2` và hai viên đạn là đồ của clip reload: ngoài reload chúng lơ lửng dưới/phải súng, ẩn khi không reload.
- Cẳng tay trái có vân da xoáy (đặc tính asset, chỉ lộ một mẩu ở mép dưới-trái màn hình).
- File CÓ normal map và tangent; `gltf_patch` bỏ chúng lúc nạp (đường cố định của Panda không dùng được), `game/gltf_maps.py` đọc lại cho shader súng. Thân súng có specular 0 trong file: độ bóng là số chỉnh tay (`ViewLightData`).

## Ursina/Windows
- `Ursina(vsync=False)` KHÔNG tắt vsync; muốn đo FPS thật: `loadPrcFileData('', 'sync-video 0')` trước `Ursina()`. Game thật chạy vsync (60 Hz).
- `color.rgb(r,g,b)` của Ursina 8 nhận 0–1, không phải 0–255.
- Console Windows mặc định cp1252: in tiếng Việt cần `PYTHONUTF8=1` hoặc `-X utf8` (cờ `-I` bỏ qua `PYTHONUTF8`).
- Panda cache model ở `%LOCALAPPDATA%\Panda3D-1.10`; `gltf_patch.apply()` đã tắt cache đó. Nạp M4 ~1,5 s.
- Màn hình máy này 1366×768: cửa sổ test dùng 1280×720.

## Tài liệu theo chủ đề (mở khi đụng tới, đừng đọc hết)
- `docs/notes/tools.md`: danh mục công cụ, bài kiểm tra, công tắc tắt để đo.
- `docs/notes/viewmodel-world.md` (G1): viewmodel, camera, độ sâu, chuột nhìn, FOV.
- `docs/notes/shooting-targets.md` (G2): bắn, đạn, bia, lỗ đạn, chữ HUD.
- `docs/notes/recoil-spread-kick.md` (G3): recoil, độ tản, bloom, kick.
- `docs/notes/ads-sway-audio.md` (G4): ngắm ADS, sway, bob, tư thế chạy, gun_audio.
- `docs/notes/reload-fx-shaders.md` (G5): rút súng, nạp đạn, tia lửa, tracer, shader súng.
- `docs/notes/ground-sky.md` (7/11/2026): nền, ánh sáng, bầu trời, Glock, `gltf_patch`, đổi súng / rút súng, những thứ đã xoá.
- `docs/notes/range-lights-signs.md` (G6; phần phòng/đèn/bia/biển đã xoá, còn đúng: shake, bảng F1, foley, bước chân).
- `docs/notes/bodycam.md` (G7): FreeLook / FreeAim, headcam, lens, exposure, ánh sáng thống nhất, âm thanh ElevenLabs.
- `docs/notes/ai-assets.md`: sinh tài nguyên AI, credit, Blender, skill học trước, thư mục review. `docs/notes/multiplayer.md`: hướng multiplayer.
