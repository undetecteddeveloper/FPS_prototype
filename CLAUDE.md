# FPS prototype (Ursina, viewmodel kiểu Bodycam của Reissad Studio)

Game bắn súng góc nhìn thứ nhất bằng Ursina/Panda3D. Từ G7 viewmodel, giật, ánh sáng, ống kính theo kiểu Bodycam (quyết định của người dùng); số "CoD" trong ghi chú G2-G6 là của bản cũ.
LUẬT CỨNG: với MỌI prompt của người dùng, dòng đầu tiên của câu trả lời (trước mọi lệnh gọi công cụ) là "Cỡ: nhỏ / lớn, vì ..." (chi tiết `docs/WORKFLOW.md` mục 2). Phân vân thì xếp lớn.
Trả lời, commit, tài liệu bằng tiếng Việt thường. Cách làm việc (hỏi theo cỡ việc, phiên, subagent): `docs/WORKFLOW.md`, ĐỌC ĐẦU MỖI PHIÊN. Chi tiết từng giai đoạn: `docs/notes/` (danh sách cuối file).

## Lệnh
- Chạy game: `run.bat` (hoặc `.venv\Scripts\python.exe main.py`; cửa sổ không viền phủ kín). Tuỳ chọn: `--novsync`, `--window --size 1280x720`, `--quit-after 5`, `--mute`, `--defaults` (bỏ `user_params.json`), `--map flat` (nền trắng phẳng cũ, để so FPS; mặc định là phòng hồ bơi), `--rebake` (nướng lại ánh sáng + chụp lại phản chiếu của phòng hồ), `--low-memory` (ép chế độ giảm tải; game tự chọn khi máy thiếu bộ nhớ ảo).
- Game chết / treo / cửa sổ đen lúc khởi động: mở `logs\crash.log` (dòng đầu mỗi lần chạy ghi commit trống; crash native và treo > 150 s để lại dấu vết Python), rồi `docs/notes/troubleshooting.md`. Nguyên nhân đã biết (7/11/2026): máy hết commit (pagefile 3 GB). Đừng giết tiến trình theo tên (`Stop-Process python`): đó có thể là game của người dùng.
- Test thuần (toán + nạp glb, không mở cửa sổ): `.venv\Scripts\python.exe -X utf8 -m pytest` (~30 s).
- `tools\selftests\*` HIỆN KHÔNG CHẠY ĐƯỢC (dựng bằng bia và phòng bắn đã xoá 7/11/2026; người dùng bảo không cần). Cổng kiểm tra = pytest + chạy game thật. Nhiều game cùng lúc làm bài đo thời gian trượt oan: bọc `.venv\Scripts\python.exe -X utf8 tools\with_game_lock.py <lệnh gốc>`.
- Đo FPS: `tools\measure\g8_perf.py --gun glock|m4 [--map flat]` (9 tình huống, ngưỡng 55; máy nóng/bận cho số thấp, đo lại một mình). Máy yếu (G13): `tools\measure\weak_pc.py --gun m4|glock` (ước UHD 620 từ ms GPU / CPU đo thật; `docs/notes/performance.md`). Map hồ bơi: `tools\measure\pool_check.py [--gun glock]` (26 mục bằng game thật), `pool_shots.py` (chụp ảnh các góc). Kiểm rút/đổi súng: `tools\measure\swap_check.py`. Chụp tư thế: `tools\measure\g8_shots.py`.
- Công cụ đo/dựng: `tools\measure\`, `tools\build\` (dựng WAV). Danh mục + công tắc tắt để đo (`free_aim=False`, `lens=False`...): `docs/notes/tools.md`.
- Đóng gói exe demo (G15): `.venv\Scripts\python.exe -X utf8 tools\build\build_exe.py` -> `build\FPS_prototype_demo_<ngày>.zip` (skill `pyinstaller-packaging`). Thêm thư mục tài nguyên / gói Python mà game đọc lúc chạy thì thêm vào script đó.
- Cài lại môi trường: `py -3.13 -m venv .venv` rồi `.venv\Scripts\pip install -r requirements.txt` (KHÔNG dùng Python 3.15).

## Cấu trúc
```
main.py  run.bat  requirements.txt  pytest.ini  CLAUDE.md  CREDITS.txt    <- cửa vào, cấu hình, sổ luật
fps/        app.py (Game, create_game() dựng tất cả, prune_scene_entities(), main()), weapon_data.py (MỌI thông số, dataclass)
  core/     toán thuần, KHÔNG import ursina, có pytest: weaponcol (G14, súng ngóc lên sát tường), underwater + wetlens (G12), memplan (chọn chế độ theo commit trống), movement, ballistics, weapon, recoil, spread, spring, sway, handling, fx, shake, cues, footsteps, params + param_meta (bảng F1),
            freeaim, headcam, gaze, smoke, lens, exposure, easing, poolmap (map dựng từ hộp), lightbake (nướng ánh sáng, numpy), terrain (bậc thang + va chạm), waves (sóng nước), cubemap (ảnh phản chiếu 3×2)
  game/     ghép Ursina/Panda: player, combat, viewmodel, ground, sky, smoke, hud, gltf_patch, gun_audio, effects, look, shaders, foley, camera_shake, debug_panel (F1), frame_light, lens, decals, gltf_maps, pool (phòng hồ bơi), water, pool_capture, sysmem (commit trống + crash log, không import ursina)
assets/     guns/ (glb), sounds/ (wav; source/ = gốc, mp3 ElevenLabs, candidates/), shaders/ (GLSL, light_common.glsl dùng chung; room, water), maps/pool/ (ánh sáng nướng + ảnh phản chiếu, tự sinh)
tests/  tools/ (selftests, measure, build, with_game_lock.py)  docs/ (WORKFLOW.md, notes/, sessions/)  backups/ shots/ (gitignore)
```
- `fps/game/__init__.py` để TRỐNG có chủ đích: `fps.game.gltf_patch` phải nạp được trước khi import ursina. `main.py` chỉ re-export `create_game`, `main` (tools gọi `from main import create_game`).
- Tài nguyên mới vào `assets/`; nguồn + prompt giữ trong `assets/<loại>/source/`.

## Quy ước
- Mọi thông số súng/recoil/spread/sway nằm trong `fps/weapon_data.py`. Toán mới tách ra `fps/core/` (không import ursina) để pytest được; chỉ phần cần Ursina/Panda mới vào `fps/game/`.
- Thứ tự mỗi khung hình cố định trong `Game.update`: `player.tick()` -> `_update_wall()` (G14: tia dò tường, súng ngóc lên, khoá bắn / ngắm) -> `combat.update()` -> `sway.update()` -> `head.update` + `shake_view.frame_offset` -> `viewmodel.update(kick, sway, free_aim, free_look)` -> `light.set_camera/set_exposure` -> `smoke.update` -> `lens.update(..., frame)`.
  Đừng để từng đối tượng tự `update` riêng (thứ tự Ursina không đảm bảo, bắn sẽ dùng hướng nhìn của khung trước).
  Camera thế giới KHÔNG rung: mọi rung (bước, nhảy, bắn, nạp, ánh nhìn khi nạp) thành dịch + nghiêng cả khung ống kính (`game/camera_shake.py`, `core/lens.frame_shake`, `lens.frag`).
- Cổng kiểm tra trước mỗi commit: pytest qua, game mở được và ≥ 60 FPS, không lỗi console.
- Thế giới mặc định là phòng hồ bơi trong nhà (G9, `docs/notes/pool-hall.md`): dựng từ hộp, ánh sáng NƯỚNG SẴN (mặt trời cố định), nước phản chiếu căn phòng chụp sẵn.
  G10: nước TRONG (thấy đáy bằng tia khúc xạ dò trong shader), sóng mô phỏng trên GPU, hồ dốc 0,5 → 2 m (lội tới ngực), tia nắng, giọt nước, sàn ướt, bụi; **F2 mở bảng đồ hoạ** (`game/graphics_panel.py`: mức chung, khử răng cưa MSAA Tắt / 2x / 4x, từng hiệu ứng, hiện FPS; lưu `user_graphics.json`). Hiệu ứng mới nào cũng phải có dòng trong `core/graphics.py` (`GraphicsSettings`, `OPTIONS`) và đổi được ngay (không biên dịch lại shader). `--map flat` còn khối đất phẳng trắng cũ để so FPS. Không bia, không bóng đổ động; đừng dựng lại phòng bắn / bia khi chưa được hỏi.
  G12: đi bộ xuống đáy 2 m, camera dưới nước (`core/underwater.py`, `game/underwater.py`, `underwater.glsl` dùng chung ở mọi shader: pixel nào nhìn qua nước), lòng hồ thành lưới thật (`basin.*`), khung tách đôi ở mặt nước, ống kính ướt khi trồi lên (`core/wetlens.py`), dưới nước không bắn được.
  G13 (hiệu năng, `docs/notes/performance.md`): mức Thấp vẽ 3D ở 75% (F2 "Độ phân giải 3D"), khói đơn giản (F2 "Khói súng"); nước / lòng hồ / phòng / ống kính / khói có BẢN BIÊN DỊCH THAY THẾ (`POOL_LITE`, `VIEW_DRY` / `VIEW_UNDER`, `LENS_DRY`, `SMOKE_LITE`) chọn bằng Python, mỗi bản phải được vẽ thử trong `Game.warm_shader_builds` (trình điều khiển Intel biên dịch ở lần vẽ đầu: không vẽ thử = khựng 50-150 ms). Thêm bản mới thì thêm vào đó.
  Sửa hình học map (`MapData`) hay nắng (`sun_dir`, `sun_color`, `sky_irradiance`) thì game tự nướng lại (~60 s). Numpy chỉ dùng lúc nướng và ở test.
- `assets\guns\animated_fps_hands_rifle_animation_pack.glb` (109 MB) bị gitignore.

## Quy trình git (chép từ dự án NeonPool 7/11/2026, chỉnh theo dự án này: nhánh làm việc là `dev`)
1. Commit trên nhánh làm việc `dev`, KHÔNG BAO GIỜ commit thẳng `main`. Message tiếng Việt `type(scope): ...` (feat, fix, refactor, perf, test, docs, chore). Mỗi commit MỘT việc. Commit xong thì DỪNG, không làm tiếp việc khác. Chỉ commit sau khi cổng kiểm tra qua (mục Quy ước); chỉ sửa tài liệu thì bỏ cổng.
2. `git push` CHỈ khi người dùng nói "push" ở lượt nhắn gần nhất; Claude không tự push. Không bao giờ `push --force`. Không đẩy file ngoài git (`backups\`, `shots\`, `user_*.json`, bí mật).
3. "Gộp / merge / đưa lên main" chỉ khi người dùng nói. Khi đó nói một dòng "Tôi hiểu là gộp nhánh X vào main" rồi làm tuần tự: `git status` sạch → `git switch main` → `git merge dev` → chạy pytest trên main nếu không phải fast-forward → báo đang đứng ở nhánh nào. Xung đột hoặc pytest đỏ trên main: dừng, báo người dùng (`git merge --abort` nếu xung đột chưa xong). Muốn tách nhánh riêng cho một việc (`feat/<tên>`, `fix/<tên>`) thì tách từ `main`, gộp xong xoá bằng `git branch -d` (không dùng `-D`).
4. Việc không hoàn tác (`reset --hard`, `clean -f`, `checkout -- `, `restore` không `--staged`, `stash drop/clear`, `branch -D`, xoá file/thư mục, bỏ thay đổi chưa commit): chạy `git status` trước, nói hệ quả bằng lời thường, hỏi có/không rồi mới làm.
5. Worktree tạm (`git worktree add` để chạy cổng trên bản sạch): xoá ngay sau khi dùng (`git worktree remove <thư mục>`); cuối việc `git worktree list` chỉ còn thư mục chính. Cổng đỏ thì chạy lại trên bản sạch để biết do mình hay đỏ sẵn.
6. Cổng không chạy được thì DỪNG phần liên quan, không commit như thể cổng đã qua. Cấm viết "xong / ổn" cho bước chưa chạy thật.
(Dự án NeonPool còn hook trong `.claude` chặn các lệnh trên; dự án này chưa có hook, nên luật chỉ dựa vào Claude tự giữ.)
- Comment và docstring trong mã viết bằng TIẾNG ANH (cả mã mới). Chữ cho người dùng (HUD, bảng F1, tên mục selftest, thông báo) và file `.md` vẫn tiếng Việt.
- Mức hỏi người dùng theo cỡ việc: `docs/WORKFLOW.md` mục 2 (thắng luật chung "tự quyết kỹ thuật").
- HỌC TRƯỚC KHI LÀM: chủ đề chưa có skill trong `.claude/skills/` thì học sâu (WebSearch) và lưu skill trước (skill `learn-first`). Blender KHÔNG còn trong quy trình (bỏ 7/11/2026): không dùng, không đề xuất, không gọi MCP `blender-lab`.
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
- Máy (kiểm 6/11/2026): ASUS Vivobook 15, Core 7 150U, GPU Intel Graphics (đời Iris Xe, 96 EU), 16 GB DDR5 hai kênh, màn 1920×1080 60 Hz (ghi chép cũ "UHD 620, 8 GB, 1366×768" là SAI). Cửa sổ test dùng 1280×720. Đo FPS khi CẮM SẠC (chạy pin bị hạ công suất).

## Tài liệu theo chủ đề (mở khi đụng tới, đừng đọc hết)
- `docs/notes/tools.md`: danh mục công cụ, bài kiểm tra, công tắc tắt để đo.
- `docs/notes/troubleshooting.md` (7/11/2026): game chết / treo / âm thanh nền lặp đoạn ngắt lúc khởi động; nguyên nhân gốc (hết commit), bằng chứng, chế độ giảm tải, `logs/crash.log`, hướng dẫn tăng pagefile.
- `docs/notes/viewmodel-world.md` (G1): viewmodel, camera, độ sâu, chuột nhìn, FOV.
- `docs/notes/shooting-targets.md` (G2): bắn, đạn, bia, lỗ đạn, chữ HUD.
- `docs/notes/recoil-spread-kick.md` (G3): recoil, độ tản, bloom, kick.
- `docs/notes/ads-sway-audio.md` (G4): ngắm ADS, sway, bob, tư thế chạy, gun_audio.
- `docs/notes/reload-fx-shaders.md` (G5): rút súng, nạp đạn, tia lửa, tracer, shader súng.
- `docs/notes/ground-sky.md` (7/11/2026): nền, ánh sáng, bầu trời, Glock, `gltf_patch`, đổi súng / rút súng, những thứ đã xoá.
- `docs/notes/range-lights-signs.md` (G6; phần phòng/đèn/bia/biển đã xoá, còn đúng: shake, bảng F1, foley, bước chân).
- `docs/notes/pool-hall.md` (G9-G12): map phòng hồ bơi, camera dưới nước, nước, ánh sáng nướng sẵn, phản chiếu, bậc thang / va chạm, số đo.
- `docs/notes/weapon-collision.md` (G14): súng chĩa lên (High Ready) khi sát tường, khoá bắn / ngắm, tia dò, tư thế, kiểm. Thân dừng cách tường 0,30 m (gờ hồ tính theo vòng tròn thân; ép phím tiến thật mới tái hiện được lỗi, đặt vị trí thì không: `docs/notes/pool-hall.md` G14). Thang hồ bơi bám thành bắc có bóng nắng nướng sẵn.
- `docs/notes/performance.md` (G13): máy yếu ở mức Thấp, cách đo GPU / CPU và quy đổi, bẫy đo, bản biên dịch thay thế, số đo trước / sau.
- `docs/notes/bodycam.md` (G7): FreeLook / FreeAim, headcam, lens, exposure, ánh sáng thống nhất, âm thanh ElevenLabs.
- `docs/notes/ai-assets.md`: sinh tài nguyên AI, credit, skill học trước, thư mục review. `docs/notes/multiplayer.md`: hướng multiplayer.
