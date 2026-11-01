# FPS prototype (Ursina, cảm giác CoD MW2019)

Đề bài và quyết định đã chốt: `PROMPT_PHIEN_THI_CONG.md`. Trả lời, commit, tài liệu bằng tiếng Việt thường.

## Lệnh
- Chạy game: bấm đúp `run.bat` (hoặc `.venv\Scripts\python.exe main.py`). Tuỳ chọn: `--novsync`, `--size 1280x720`, `--fullscreen`,
  `--quit-after 5` (tự thoát sau 5 giây, dùng để kiểm tra mà không phải tắt tiến trình).
- Kiểm tra bằng game thật (điều khiển qua `held_keys`/`combat.pressed`, đo, chụp ảnh vào `shots\`; thoát mã 1 nếu trượt):
  `.venv\Scripts\python.exe -X utf8 tools\g1_selftest.py` (di chuyển), `tools\g2_selftest.py` (bắn: nhịp, độ rơi từng bia, đạn, hit marker, lỗ)
  `tools\g3_selftest.py` (recoil, độ tản theo trạng thái, bloom, tâm ngắm so với phép chiếu thật, kick súng trên màn hình),
  `tools\g4_selftest.py` (ADS, đường ngắm trùng tâm, thở/bob/lag chuột, quán tính nhảy/ngồi, tư thế chạy, sprint-to-fire)
  `tools\g5_selftest.py` (rút súng, nạp hai kiểu, huỷ nạp, logic đạn, tia lửa, tracer; 69 mục)
  `tools\g6_shake_selftest.py` (camera shake), `tools\g6_targets_selftest.py` (bia chạy, biển, bóng bia chạy; ~1,5 phút), `tools\g6_debug_selftest.py` (bảng F1, HUD, lưu/nạp; ~1 phút)
  và `tools\audio_selftest.py` (BẬT tiếng, kiểm trình phát thật và số lần phát; các selftest khác tắt tiếng bằng `create_game(sound=False)`).
  Các selftest G1–G4 gọi `create_game(draw=False)` để khỏi chờ 1 s rút súng; `create_game(effects=False, look=False)` tắt tia lửa/tracer và shader thế giới (để đo);
  `shake=False` tắt camera shake (g3 cần camera trùng tia ngắm); `moving_targets=False` làm mọi bia đứng yên (g1–g5, g6_shake)
- NHIỀU GAME CÙNG LÚC làm các bài đo theo thời gian (nhịp bắn, FPS) trượt oan. Khi có nhiều agent/terminal: bọc mọi lần mở cửa sổ game bằng
  `.venv\Scripts\python.exe -X utf8 tools\with_game_lock.py <lệnh gốc>` (ổ khoá toàn máy, tự chờ tới lượt). Máy nóng/bận hạ xung: mục "FPS trung bình >= 60" của g3 tụt 59 -> 45 sau nhiều lần chạy liền;
  chạy lại một mình khi máy yên (g3 yên = 62 FPS, sát ngưỡng). `tools\room_perf.py` đo FPS có/không bóng xen kẽ trong cùng một lần chạy (đáng tin hơn số tuyệt đối).
- Công cụ dựng/đo: `tools\prep_sound.py` (dựng `sounds\m4_shot.wav` từ file gốc), `tools\prep_foley.py [--check]` (tổng hợp 37 file `sounds\foley\*.wav` bằng mã thuần),
  `tools\prep_user_audio.py` (cắt hai file của người dùng thành `sounds\foley\user_*.wav`), `tools\sway_sim.py` (mô phỏng sway: lệch cực đại / quá đà / thời gian ổn định, thuần toán),
  `tools\room_shots.py` (chụp phòng tập), `tools\g4_ads_align.py` (đo điểm ngắm của súng, in tư thế ADS),
  `tools\g5_reload_probe.py` (đo từng khung của clip nạp: băng rời / vào chỗ, bolt), `tools\g5_muzzle_align.py` (đo miệng nòng),
  `tools\g5_perf.py <biến thể>` (FPS lúc đứng yên so với lúc nạp, tắt từng thứ để tìm thủ phạm: base / noblend / cpuskin / noview / nolook / nofx / nohud)
- Test (toán thuần + nạp glb, không mở cửa sổ): `.venv\Scripts\python.exe -X utf8 -m pytest`
- Công cụ G0: `tools\g0_view.py` (chụp ảnh tư thế), `tools\g0_timing.py` (đo clip + FPS), `tools\g0_motion.py`
- Cài lại môi trường: `py -3.13 -m venv .venv` rồi `.venv\Scripts\pip install -r requirements.txt` (KHÔNG dùng Python 3.15)

## Cấu trúc thư mục
```
main.py  run.bat  requirements.txt  pytest.ini  CLAUDE.md  CREDITS.txt  PROMPT_PHIEN_THI_CONG.md   <- root: chỉ cửa vào + cấu hình + tài liệu
fps/                     gói mã nguồn (import dạng `from fps.core.movement import ...`)
  app.py                 Game, create_game() (dựng tất cả; tools gọi lại hàm này), main()
  weapon_data.py         MỌI thông số (dataclass)
  core/                  toán thuần, KHÔNG import ursina, có pytest: movement, ballistics, weapon, recoil, spread, spring, sway, handling (nạp/rút súng), fx (tia lửa/tracer),
                         shake (camera shake), cues (mốc âm theo khung), footsteps, room (phòng tập), patrol (bia chạy), signs (biển), params + param_meta (bảng F1, lưu/nạp)
  game/                  phần ghép Ursina/Panda: player, combat, targets, viewmodel, shooting_range, hud, gltf_patch, gun_audio, effects, look, shaders,
                         foley (nạp đạn/bước chân), camera_shake, lamp_shadows (bóng đèn), signs (biển), debug_panel (F1)
shaders/                 GLSL: viewmodel.vert|frag (súng + tay, skin trên GPU), world.vert|frag (thế giới: đèn, sương mù, nhiễu mặt đất)
guns/  sounds/           tài nguyên (glb; wav, trong sounds/source là file gốc)
tests/  tools/  docs/    pytest; công cụ + bài kiểm tra bằng game thật; ghi chú các giai đoạn
shots/                   ảnh chụp của các bài kiểm tra (gitignore)
```
- `fps/game/__init__.py` để TRỐNG có chủ đích: `fps.game.gltf_patch` phải nạp được trước khi import ursina.
  `main.py` ở root chỉ re-export `create_game`, `main` (các tools gọi `from main import create_game`).

## Quy ước
- Mọi thông số súng/recoil/spread/sway nằm trong `fps/weapon_data.py` (dataclass). Không rải số ra module khác.
- Toán mới thì tách ra `fps/core/` (không import ursina) để pytest được; chỉ phần cần Ursina/Panda mới vào `fps/game/`.
- Thứ tự mỗi khung hình cố định trong `Game.update`: `player.tick()` -> `combat.update()` -> `sway.update()` -> `viewmodel.update(kick, sway)` -> `hud.update()`.
  Đừng để từng đối tượng tự `update` riêng (thứ tự Ursina không đảm bảo, bắn sẽ dùng hướng nhìn của khung trước).
- Cổng kiểm tra trước mỗi commit: pytest qua, game mở được và ≥ 60 FPS, không lỗi trong console.
- Commit trên nhánh `dev`. Chỉ push khi người dùng nói. `guns\animated_fps_hands_rifle_animation_pack.glb` (109 MB) bị gitignore.

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
- Không có normal map, không PBR. Từ G5 súng + tay vẽ bằng shader riêng `shaders/viewmodel.*` (xem mục G5), không còn đường cố định của Panda.

## Ursina/Windows
- `Ursina(vsync=False)` một mình KHÔNG tắt vsync. Muốn đo FPS thật: `loadPrcFileData('', 'sync-video 0')` trước `Ursina()`.
  Game thật chạy vsync (khóa ở tần số màn hình, 60 Hz); sức máy đo được khi phát clip: trung bình 218, thấp nhất 106 FPS.
- `color.rgb(r,g,b)` của Ursina 8 nhận 0–1, không phải 0–255.
- Console Windows mặc định cp1252: in tiếng Việt cần `PYTHONUTF8=1` hoặc `-X utf8` hoặc `sys.stdout.reconfigure(encoding='utf-8')`.
  (Cờ `-I` của Python bỏ qua `PYTHONUTF8`; dùng `-X utf8`.)
- Panda cache model trên đĩa (`%LOCALAPPDATA%\Panda3D-1.10`). `gltf_patch.apply()` đã tắt cache đó; nạp M4 mất ~1,5 s.
- Màn hình máy này 1366×768: cửa sổ test dùng 1280×720.

## Viewmodel, thế giới, hiệu năng (G1)
- Súng vẽ bằng camera + vùng hiển thị RIÊNG (`viewmodel.py`: đồ thị `root -> sway -> rig -> actor`, sort 5, xoá lại độ sâu, FOV riêng
  `GunData.view_fov`). Code recoil/sway/ADS chỉ cần đặt vị trí/góc cho nút `viewmodel.sway`; `rig` chỉ để căn khớp `FPS_Camera` về gốc camera.
- Camera thế giới là `camera` của Ursina gắn vào `player.camera_pivot`; FOV ngang 80 (`PlayerParams.fov`). Recoil camera (G3) cộng vào pivot.
- Chuột: `mouse.velocity` của Ursina (đơn vị = chiều cao cửa sổ), nhân `mouse_sensitivity` độ/đơn vị. Khi `mouse.locked` mới nhìn.
- Độ sâu thế giới: near 0.1, far 10000 (mặc định Ursina) đủ cho 200 m. Vật nằm sát đất (vạch) dùng `set_depth_offset(1)`, không nâng lên.
- Kiểu `Entity` mới của Ursina 8.3 dùng `unlit_with_fog_shader` (màu phẳng); từ G5 vật thể trường bắn/bia/lỗ đạn dùng `shaders/world.*` (đèn + sương mù), xem mục G5.
- KHÔNG bật MSAA: trên Intel UHD 620 của máy này mọi mức MSAA kéo FPS từ ~140 xuống ~20.
- Vạch ngang làn mảnh hơn một điểm ảnh ở ≥ 100 m nên đứt nét: chỉ vạch tới 50 m, xa hơn dùng biển treo trần (G6).
- Đã đo ở G1 (vsync tắt, 1280x720): trung bình 126 FPS, 1% thấp nhất 84. Khung lưu ảnh chụp rất chậm: loại khỏi số đo.
- Đừng dùng `taskkill /IM python.exe` để tắt game (tắt cả việc khác của người dùng): dùng `--quit-after`.
- Gọi `run.bat` từ Git Bash bằng `cmd //c` không chạy được (không thấy file); dùng PowerShell: `& .\run.bat --quit-after 5`.
- Sửa file bằng `python - <<'EOF'` hoặc `sed` mà chuỗi có `\n` thì dấu `\` bị nuốt và thành xuống dòng thật: dùng công cụ Edit.

## Bắn, đạn, bia, chữ (G2)
- Đạn xuất phát từ MẮT theo hướng nhìn (`player.aim_ray()`), 500 m/s, g = 9,81 (trong `GunData`). Mỗi khung đạn đi một đoạn rồi dò va chạm
  TRÊN CẢ ĐOẠN (`ballistics.first_hit`), nên không xuyên bia mỏng dù FPS thấp. Đo trên dây cung nên lệch tối đa g*dt²/8 so với cung thật (0,3 mm ở 60 FPS).
- Nhịp bắn: `Weapon.update` trả về tuổi của từng phát trong khung (đạn sinh ra rồi tự đẩy tiếp đúng tuổi đó): RPM đúng ở mọi FPS (test 30–1000).
  Phát đầu sau lúc nghỉ nổ đúng "bây giờ". Không dồn "tín dụng" nhịp bắn khi nhả cò, bóp nhanh không bắn nhanh hơn RPM.
- Bia: `targets.LAYOUT` xen kẽ hai bên làn, bia xa to dần, cao tối thiểu 1,9 m (phủ tầm mắt 1,62 m). KHÔNG đặt hai bia cùng trục x: bia gần che bia xa.
- Lỗ đạn: bể `max_holes` tạo sẵn lúc khởi động (tạo `Entity` giữa lúc bắn gây khựng ~10 ms), quay theo pháp tuyến (`ballistics.decal_rotation`),
  cỡ to dần theo khoảng cách (lỗ thật 5,56 mm không nhìn thấy). Gắn vào `target.root` (không scale) để bia chạy ở G6 mang lỗ theo.
- Phím: `R` nạp đạn (G5), `B` đổi tự động / bắn đơn. Không bắn khi chuột đã nhả (Esc).
- Chữ (`hud.py`): `setup_fonts()` dùng Segoe UI Semilight có sẵn trong Windows (đủ dấu tiếng Việt), độ phân giải font = cỡ chữ trên màn hình x2, mỗi dòng có bóng
  đen lệch 1 px (`UiText`). Font mặc định của Ursina (OpenSans Regular qua shader SDF ở 1080p) bị dày và nhoè khi thu nhỏ: ĐỪNG quay lại dùng `Text(...)` trần.
  Chữ mảnh dưới ~14 px luôn mờ: cỡ chữ HUD không xuống dưới `scale=0.75`. Mọi chữ mới của game đi qua `UiText`.
- `ursina.Color` không cắt lát được (`color[:3]` lỗi): dùng `.r .g .b .a`. `color.rgba` nhận 0–1.
- Đã đo ở G2 (vsync tắt, 1280x720, gồm bắn liên thanh): trung bình 121 FPS, 1% thấp nhất 75, khung chậm nhất 17 ms.

## Recoil, độ tản, kick súng (G3)
- Mỗi phát (trong `Combat.update`): lấy độ tản HIỆN TẠI -> hướng đạn = hướng nhìn + `random_in_cone` -> bắn -> cộng bloom, recoil camera, kick súng.
  Recoil camera áp SAU khi bắn nên phát hiện tại đi theo hướng nhìn trước cú giật. `Combat.last_shot` (`ShotInfo`) giữ hướng nhìn, hướng đạn, độ tản, trạng thái.
- Recoil camera cộng thẳng vào `player.yaw/pitch` qua `player.kick_view` (người chơi phải kéo chuột bù), làm mượt bằng hằng số thời gian 25 ms (đúng ở mọi FPS).
  Mẫu 30 bước `M4_PATTERN`, nhiễu ±10% độc lập cho lên/phải, nghỉ > 0,35 s thì về đầu mẫu. Hồi `recovery` = 30% tổng cú giật của loạt, bắt đầu 0,12 s sau phát cuối; bắn tiếp thì huỷ.
- Độ tản = nửa góc hình nón, đều theo diện tích đĩa. Nền theo `MoveState` (đứng 2 / đi 3,5 / chạy 4,5 / nhảy 6 / ngồi x0,7 / ADS 0,1; ADS đi 0,6) + bloom. `sprint = 4,5` và `ads_move = 0,6` là số tôi thêm, đề bài không có.
- Bloom CÓ thời gian chờ 0,15 s trước khi hồi (`bloom_recovery_delay`): theo đề (+0,25°/phát, hồi 6°/s) thì ở 750 phát/phút hồi 0,48° mỗi nhịp, triệt tiêu bloom, nên bloom không bao giờ dồn lên.
- ADS: `player.ads_amount` (0 hông .. 1 ngắm hẳn, G4 gán) nội suy nền hông -> nền ngắm và nhân bloom với `ads_bloom_multiplier` (0,05). Phát bắn lúc đang vào ADS tản theo mức hiện tại.
- Tâm ngắm (`hud.py`): vạch dạt ra đúng bằng góc tản chiếu qua FOV thế giới (`spread.crosshair_gap`, đã so với `camera.lens.project`); ẩn dần khi ads_amount -> 1.
- Kick súng: `GunKick` = lò xo giảm chấn 6 thành phần, mỗi phát đẩy một xung tính từ "độ lệch đỉnh một phát đơn" (`spring.impulse_gain`), nghiệm chính xác nên ổn định mọi dt. `Viewmodel.update(kick)` đặt lên nút `sway`.
- BẪY DẤU: `set_hpr` thô của nút `sway` KHÁC `Entity.rotation` của Ursina ở thế giới: h dương quay súng sang TRÁI, p dương ngóc nòng LÊN, r dương nghiêng PHẢI. `Viewmodel.update` đã đảo cho đúng; G4 (sway/ADS) nhớ dấu này. Đo bằng `get_tight_bounds` của nút `Main_M4_D_0-parent` (không dùng hộp bao cả actor: tay kéo dài ra sau lưng camera).
- `spread.angle_between` dùng `atan2(|tích có hướng|, tích vô hướng)`: `acos` sai ~0,01° ở góc nhỏ vì làm tròn float32 của `camera.forward`.
- `g2_selftest.py` tắt độ tản (đo độ rơi cần đạn đi đúng hướng ngắm); `g3_selftest.py` tự tắt bloom và tăng nhịp bắn lên 250 phát/s khi đo độ tản theo trạng thái (cần >= 100 mẫu mỗi mục).
- Chi phí G3 mỗi khung ~0,06 ms (tâm ngắm 53 µs là phần lớn). Đã đo ở G3 (vsync tắt, 1280x720, gồm hai loạt liên thanh): trung bình 102 FPS, 1% thấp nhất 66, khung chậm nhất 17 ms.
  Lần chạy khác trên cùng máy có lúc rớt 1% xuống ~50 và khung 29–120 ms do máy nhiễu (G2 chạy lại cũng thấy); chạy lại trước khi kết luận tụt FPS.

## Ngắm, sway, chạy, âm thanh (G4)
- `player.ads_amount` và `player.sprint_amount` là tiến độ TUYẾN TÍNH 0..1 (`gun.ads_time` 0,25 s; `sprint_in_time` 0,2 s, `sprint_out_time` 0,25 s). `smoothstep` chỉ áp khi dùng cho hình ảnh
  (FOV, tư thế súng, tốc độ đi, độ nhạy chuột); độ tản (`spread.py`) dùng số thô. FOV thế giới 80 -> `GunData.ads_fov` 65; độ nhạy chuột nhân `ads_look_multiplier` 0,7 ngay trong `Player.look()`.
- Đường ngắm: `GunData.ads_sights` = (tâm vòng ngắm sau, đỉnh CỘT ngắm trước) đo bằng `tools\g4_ads_align.py` từ đỉnh mô hình (quét nút `Main_M4_D_0-parent`; đừng lấy đỉnh hai cánh che, cao hơn cột 2 mm).
  `sway.ads_pose()` tính phép xoay + tịnh tiến đưa đường ngắm trùng trục nhìn, vòng sau cách mắt `ads_eye_relief` (0,18 m). `g4_selftest` kiểm bằng phép chiếu thật: lệch < 6 px (đo ~1 px).
- `Sway` (`fps/core/sway.py`) cộng 6 thứ thành một tư thế: thở (Lissajous 1:2), lag chuột (lò xo; chuột quay phải thì súng trễ trái), bob (PHA theo quãng đường, bước 2,4 m: nhịp đúng ở mọi tốc độ),
  quán tính dọc theo `player.eye_dy` (thay cho xung nhảy/ngồi riêng: camera lên thì súng trễ xuống) + nhún khi chạm đất, tư thế chạy, tư thế ADS. Khi ngắm, 4 thứ đầu còn `ads_multiplier` = 20%.
  `Viewmodel.update(*poses)` cộng tư thế của kick (G3) và sway rồi đặt lên nút `sway` (dấu hpr: xem BẪY DẤU ở G3).
- Nhún chạm đất: `Player._dip` hạ `camera_pivot.y` (đỉnh `land_dip_per_speed` x tốc độ rơi, ~3,9 cm khi nhảy) và `aim_ray()` lấy gốc tia từ chỗ camera đang ở.
- Sprint-to-fire (`PlayerParams.sprint_blocks_fire` = True): bóp cò khi đang chạy thì thôi chạy (đi bộ), súng đưa lên trong `sprint_out_time`, rồi mới bắn (đo 0,26 s); `Combat` nhớ cú bóp lúc chưa sẵn sàng (bắn đơn
  không mất phát). Đặt False thì bắn thẳng từ tư thế chạy: `g3_selftest` làm vậy để đo độ tản của trạng thái chạy (`accuracy.sprint` chỉ có hiệu lực khi False). Bấm ngắm cũng cắt chạy.
- Tư thế chạy `SwayData.sprint_pose` là số chỉnh bằng mắt (ảnh `shots\g4_sprint.png`): hạ quá tay thì súng văng khỏi màn hình (xoay quanh mắt kéo thân súng xuống ~19 cm với y -0,09 và pitch -20).
- Âm thanh: `fps/game/gun_audio.py` phát từ nhóm 8 bản luân phiên (tiếng 0,5 s, nhịp 0,08 s) với cao độ ngẫu nhiên ±3%. `sounds\m4_shot.wav` dựng bằng `tools\prep_sound.py` từ `sounds\source\m4_shot_original.wav`
  (file gốc 2 s, mở đầu im 48 ms làm tiếng trễ ~3 khung: cắt đầu và đuôi, mờ dần 80 ms). Tắt tiếng: `--mute`; selftest tắt bằng `create_game(sound=False)`. Không nghe được loa nên `tools\audio_selftest.py` kiểm gián tiếp
  (trình phát thật không phải âm câm, độ dài, số lần phát, trạng thái PLAYING); CREDITS ghi rõ nguồn/giấy phép tiếng súng CHƯA có.
- Git/Windows: cây làm việc dùng CRLF (autocrlf), cảnh báo "LF will be replaced by CRLF" vô hại; script thay chuỗi trên file `.py` phải chuẩn hoá `\r\n` -> `\n` trước (đã vấp khi dọn cấu trúc).
- Đã đo ở G4 (vsync tắt, 1280x720, cả kịch bản): trung bình 95 FPS, 1% thấp nhất 70, khung chậm nhất 18 ms.

## Rút súng, nạp đạn, tia lửa, tracer, shader (G5)
- Logic nạp/rút súng thuần: `core/handling.py` (READY / DRAW / RELOAD), số liệu ở `weapon_data.ReloadData` + `Clip.swap`/`Clip.settle`. Clip chạy theo đồng hồ Panda (`actor.play` + nội suy khung `setBlend(frameBlend=True)`),
  logic nhận `time.dt` THẬT (không cắt 50 ms) nên hai bên khớp; `Handling.drain()` đưa sự kiện (start/swap/done/cancel) sang `Viewmodel.on_event`.
- Đo bằng `tools\g5_reload_probe.py` (đừng đoán lại): băng mới vào chỗ ở khung **61** (Reload, 2,0 s) và **172** (Reload_Empty, 2,03 s); đạn đổi đúng lúc đó, huỷ trước mốc thì đạn y nguyên. Tổng 3,63 s / 3,77 s (`ReloadData.speed` nhân tốc độ).
  Một băng duy nhất (Mag1) rút ra rồi ấn lại; `Mag2` và viên đạn thứ hai không bao giờ tới gần súng trong clip nào (vẫn ẩn). Khung đầu của Reload_Empty có bolt khoá sau (BoltCatch 18 cm, Bolt 6 cm) nên đó chính là tư thế "băng cạn":
  `Viewmodel.animate` trộn 0,04 s sang khung 111 khi băng về 0 (bolt khoá ngay phát cuối), không cần clip riêng. Draw bắt đầu ở khung đầu tiên của game (không phải lúc dựng), 1,0 s, không bắn/ngắm/nạp được.
- Luật: băng cạn + bóp cò (hoặc R) -> Reload_Empty; hết sạch đạn thì không làm gì (HUD "HẾT ĐẠN"); R lúc chạy bị bỏ (chờ `sprint_amount` về 0); chạy nước rút cắt nạp (`ReloadData.sprint_cancels`); nạp luôn kéo súng ra khỏi ADS
  (`Player.ads_blocked`, vào lại ADS tự động khi xong nếu còn giữ chuột phải); cú bóp lúc đang nạp bị bỏ (khác sprint-to-fire: ở đó được nhớ).
- Huỷ nạp: clip đứng yên tại khung hiện tại rồi trượt về tư thế sẵn sàng 0,18 s bằng `enableBlend` + `setControlEffect` (hai AnimControl khác nhau: clip bị huỷ và `Draw` ở khung cuối). Huỷ Reload_Empty trước mốc thì tư thế sẵn sàng có bolt đóng
  rồi 0,04 s sau mới khoá lại (không dùng chung được một AnimControl cho cả hai).
- Clip nạp được dựng cho góc nhìn rộng: tay trái và băng đạn nằm dưới mép màn hình ở FOV súng 70 (kể cả lúc nghỉ). Khi nạp FOV súng mở 88 và súng nhích lên 4 cm (`ReloadData.view_fov/view_pose`, trộn 0,25 s). Phải TẮT XONG ở `Clip.settle`
  (88 / 206) chứ không phải hết clip: đoạn cuối clip chỉ là ngón tay xếp lại, để nguyên thì súng đứng cao thêm ~0,6 s sau khi nạp xong (lỗi đã gặp).
- **FPS lúc nạp (lỗi đã gặp)**: nội suy khung làm bộ xương đổi MỌI khung nên Panda skin lại 2 875 đỉnh bàn tay trên CPU mỗi khung (đo `animate_vertices`: 1,28 ms). Đo xen kẽ trung vị khung hình: cách cũ đứng yên 10,0 -> nạp 13,2 ms (-24% FPS);
  skin trên GPU 10,1 -> ~10,5 ms. Hiện `shaders/viewmodel.vert` skin bằng `p3d_TransformTable` + `transform_weight/index` (mẫu từ panda3d-simplepbr) với cờ `ShaderAttrib.F_hardware_skinning`, đặt riêng cho mesh có cột `transform_blend`;
  mesh cứng của súng dùng biến thể không skin. Đừng bỏ shader này mà quay lại đường cố định.
- Tia lửa + tracer: `game/effects.py`, số liệu `FlashData`/`TracerData`, toán `core/fx.py`. Miệng nòng (0,0677, -0,0752, 0,7326) trong hệ camera lúc nghỉ (`GunData.muzzle`, đo bằng `g5_muzzle_align`).
  Tia lửa vẽ trong cảnh súng (ngôi sao + hai tấm dọc nòng, trộn cộng) kèm đèn điểm đưa vào shader súng; ngắm thì nhỏ còn 35%. Tracer bám viên đạn THẬT (cùng vị trí, độ rơi), cứ 3 viên một vệt, viên đầu của loạt luôn có,
  xuất phát từ miệng nòng rồi hội tụ về đường đạn từ mắt trong 18 m (`Tracer.offset`, `convergence`); hệ số `lens_ratio` bù chênh FOV thế giới/FOV súng để điểm xuất phát trùng miệng nòng trên màn hình (kiểm ở selftest < 4 px).
  Đạn bay xa dọc hướng nhìn thì vệt co lại thành chấm: thêm chấm sáng 20 px ở đầu vệt. Màu phải bão hoà (cam), trắng chìm vào mặt đường và bầu trời vì trộn cộng.
- BẪY Panda/Ursina: `CardMaker` dựng thẻ trong mặt phẳng **XY** (pháp tuyến +z) vì Ursina dùng hệ y-up, không phải XZ như tài liệu Panda. Đặt thẻ bằng `set_mat` tường minh (hàng 0 = ảnh trục ngang, hàng 1 = ảnh trục dọc, hàng 2 = pháp tuyến).
  Đầu vào shader riêng của vật thể Ursina (`camera_world_position`, `fog_color`... từ `unlit_with_fog_shader`) ĐÈ lên đầu vào đặt ở `render`: uniform của shader mình phải có tiền tố riêng (`look_`), không thì thấy giá trị 0.
  Uniform đổi mỗi khung (đèn tia lửa, vị trí camera) đưa bằng mảng `PTA_LVecBase3f` sửa tại chỗ; gọi lại `set_shader_input` mỗi khung làm đổi trạng thái vẽ của cả cây cảnh.
- (G5; từ G6 mặt trời/trời/sương ngoài trời đã THAY bằng phòng kín + đèn treo trần, xem mục G6) Shader thế giới `shaders/world.*` (áp bằng `Entity.shader` trong `game/look.py`): đèn nửa cầu + mặt trời (pháp tuyến lấy từ đạo hàm vị trí nên không cần mesh có normal), nhiễu giá trị hai tỉ lệ trên mặt nằm ngang (mờ dần 40-160 m),
  sương mù exp 0,0032 hoà vào màu chân trời (0,75, 0,84, 0,87), lớp tối góc màn hình. Chi phí đo được ~0,2 ms/khung (trong nhiễu của máy). Số liệu ở `weapon_data.LookData`.
  KHÔNG dùng FXAA của Ursina (`camera.shader = fxaa_shader`): bầu trời thành xám phẳng khi có vùng vẽ súng riêng; MSAA vẫn cấm.
- Đạn chia bước <= 1/120 s khi dò va chạm (`MAX_BULLET_STEP`): trước đây một khung treo 40 ms làm điểm trúng lệch tới `g*dt^2/8` = 3 mm ở 10 m (g2_selftest bắt được).
- CHƯA GIẢI QUYẾT: phát bắn ĐẦU TIÊN của phiên có một khung ~40 ms (các phát sau 8-13 ms). Chỉ xảy ra khi tia lửa/tracer được cập nhật thật (tắt `Effects.update` thì hết). Đã thử: `prepare_scene`, vẽ thử nút vài khung lúc dựng
  (giảm khung thứ hai từ 25 xuống 10 ms), chạy thử đường mã, thay billboard bằng ma trận, PTA cho đèn, đóng băng bộ gom rác: không hết. Giờ chỉ còn một lần mỗi phiên.
- Đã đo ở G5 (vsync tắt, 1280x720, cả kịch bản g5_selftest): trung bình 85 FPS, 1% thấp nhất 59; bắn liên thanh có tia lửa + tracer không tụt đáng kể.

## Phòng tập, đèn, bóng, bia chạy, biển (G6)
- Trường bắn là PHÒNG KÍN: tường bốn phía + trần 5,5 m + sàn gạch, lòng rộng 24 m, z từ −20 đến 216; người chơi kẹp bởi `WALK_BOUNDS` (x ±10,8). Hình học thuần ở `core/room.py` (tường, cột, dầm, tấm tiêu âm, vị trí đèn), mesh gộp ở
  `game/shooting_range.py`. Đạn trúng tường/trần (lỗ đạn trên đó); dò va chạm nhóm hộp 30 m (`ballistics.BoxGroup`) nên không tốn.
- Ánh sáng: 23 bóng đèn treo trần cách nhau 10 m (cao 4,6 m), mỗi đèn đổ bóng THẬT. `LookData` (đèn: màu, cường độ, bán kính, nón; ánh nền; exposure; sương trong phòng; `shadows` True / 'fake' / False,
  đổi lúc chạy bằng `game.look.set_shadow_mode`). Bản đồ bóng = atlas cubemap 5 mặt (bỏ mặt lên trần) vẽ MỘT lần lúc dựng (`render_now`) trong một kết cấu 2816x2816; mỗi khung chỉ tốn lấy mẫu trong shader.
  Vẽ atlas ở khung đầu làm khung đó dài ~0,5 s và g5 trượt 5 mục (rút súng): đã chuyển sang lúc dựng game. Máy trống: bóng thật 83-88 FPS, +6-9% thời gian khung so với tắt bóng (`tools\room_perf.py`).
- BẪY shader bóng: camera bóng chỉ vẽ mặt sau của vật + đẩy điểm theo pháp tuyến (chống acne); `render.hide(BitMask32.bit(7))` + `show_through` cho vật đổ bóng; shader `#version 140` phải dùng `Shader.make`,
  KHÔNG dùng `shaders.load_glsl` (tự chèn `#version 120`); `mat4` truyền vào GLSL qua mảng `PTA_LMatrix4f` dùng theo kiểu `M * vec4`; thẻ có alpha phải dùng shader thế giới (shader mặc định Ursina gần như không hiện).
- Bia chạy: 3 bia (25 m 1,5 m/s; 100 m 3 m/s; 200 m 4 m/s) đi ngang làn, nghỉ 0,35 s mỗi đầu (`targets.MOVERS`). Toán `core/patrol.py` theo thời gian chính xác (độc lập FPS). Cập nhật ở ĐẦU `Combat.update`.
  Đạn dò với hộp bia tịnh tiến trong từng bước đạn (`ballistics.moving_hit`): trúng/trượt giống hệt ở 20, 60, 240 FPS (lấy vị trí cuối khung lệch tới 20 cm ở 20 FPS). `Entity.root.x` là float32: so sánh dung sai ~1e-5.
  Bia xa 150 m ở x = 0 che các tia nhắm gần trục: test nhắm bia khác phải tránh nó.
- Bóng bia chạy: atlas lúc dựng KHÔNG chứa bia chạy; `WorldLook._tick_movers` vẽ lại 2-3 đèn gần mỗi bia, 8 Hz luân phiên (`LookData.mover_shadow_hz`, `mover_shadow_reach`; 0 = tắt), `LampShadows.refresh*` vẽ đúng một khung.
  Vật chuyển động mới thì thêm vào `look.movers`. Tốn +5-7% thời gian khung.
- Biển khoảng cách: treo trần thành cặp trái/phải ở 10/25/50/100/150/200 m, mặt về phía người bắn; chữ Segoe UI Semilight vẽ bằng PIL vào MỘT atlas (mipmap + anisotropic 8) ở `game/signs.py`; shader thế giới `look_material = 6`
  (nhận đèn, sương, bóng; chữ phát sáng nhẹ). x từng biển chọn để biển gần che biển xa < 10% (`tests/test_signs.py`). Biển 200 m khó đọc bằng mắt từ vạch bắn (trần chặn chiều cao): cần ngắm hoặc đi gần.
- Camera shake (`core/shake.py`, `game/camera_shake.py`, `ShakeData`): CHỈ HÌNH ẢNH, không đổi `player.yaw/pitch`, `aim_ray()` hay hướng đạn (chạy cùng kịch bản bật/tắt cho tia ngắm và điểm trúng giống hệt).
  Bắn: mỗi phát cộng trauma (xem số hiện tại bên dưới; bản đầu 0,22, trần 0,70, tắt 2,0/s, power 1,5, 16 Hz), biên độ = trauma^power nhân nhiễu mượt, nhân `fire_scale` 1,2 (kẹp trauma chứ không kẹp biên độ nên tỉ lệ đúng). Mặc định hiện tại (người dùng chỉnh): +0,30 trauma/phát, trần 0,75, tắt 2,5/s, `power` 2,3, `fire_freq` 20 Hz, pitch 0,50 ở trauma 1. Nạp: xung lò xo ở các mốc
  mag_out / seat / bolt (`ShakeData.reload_beats`), không rung suốt clip. ADS còn 50%. Súng đi theo 60% (`gun_follow`) trễ 0,02 s. Dấu đã đo: `camera.rotation_x` dương = nhìn xuống, `rotation_y` dương = quay phải,
  `rotation_z` dương = nghiêng phải. Sự kiện (`on_shot/on_beat/watch_reload`) phải vào TRƯỚC `Shake.update(dt)` của khung. Shake có seed riêng (không dùng chung `combat.rng`, kẻo đổi chuỗi ngẫu nhiên của đạn).
- Đẩy lùi súng: lò xo RIÊNG `GunKick.back` (omega 18, zeta 0,7; chậm hơn nhịp bắn 0,08 s nên các phát dồn lên); `back_peak` -0,036 (3,6 cm một phát, cả băng ~1,7 lần), ADS x1,3 (người dùng chỉnh: ngắm lùi NHIỀU hơn hông; bản đầu là 3 cm / 5 cm / x0,5). Lò xo kick cũ (omega 38) đã trượt về trước phát kế nên liên thanh chỉ lùi 2,2 cm.
  `back_x_ratio` 0,3 nhích súng vào giữa khi lùi (súng lệch phải 7 cm sẽ trượt ra rìa màn hình), chỉ lúc hông. `GunKick.on_shot(ads, age)` nhận tuổi phát trong khung (độc lập FPS). Cuối loạt hông thân sau súng tràn ra góc dưới phải;
  thấy nặng thì giảm `back_peak` (~0,025).
- Sway chuột (`MouseLag` trong `core/sway.py`): hệ bậc hai theo vận tốc quay (tham số tần số / giảm chấn / phản ứng, nghiệm chính xác nên ổn định mọi dt), đầu vào làm mượt `lag_smooth`, ngưỡng mềm `lag_deadzone`,
  nén tanh tới `lag_max` thay vì kẹp cứng (kẹp cứng cũ bẹt mọi cú xoay 120-900°/s ở 3,9°: nguyên nhân "cứng"). `lag_gain` là GIÂY (lệch = gain x tốc độ quay). Flick 240°/s: lệch 3,9° -> 7,2°, quá đà 13%, ổn định 0,25 s.
  Đỉnh flick ≈ `lag_max` (có thể vượt ~10%). Số đáng chỉnh: `lag_max` 10 (người dùng chỉnh từ 8), `lag_gain` 0,05 (từ 0,04), `lag_zeta` 0,60, `lag_omega` 17. Sway khi ngắm còn `ads_multiplier` 0,4 (từ 0,2). Nguồn tra được mỏng (Patreon t3ssel8r, wiki Valve trả 403): thuật toán là tự suy từ kiến thức về "second order dynamics".
- Bob súng: `bob_rate` 0,4 (đi / ngồi đi) và `bob_sprint_rate` 0,3 (chạy nước rút) nhân vào tốc độ pha; biên độ giữ nguyên. Nhịp bước chân KHÔNG đọc pha bob.
- Âm thanh nạp đạn / bước chân (`game/foley.py`, `core/cues.py`, `core/footsteps.py`, `AudioData`): tiếng phát theo MỐC KHUNG của clip (`M4_SOUND_CUES`, thời điểm thật = (khung − clip.start)/30/`ReloadData.speed`), huỷ nạp thì
  bỏ mốc chưa tới (+ tiếng `settle` nếu đã phát ít nhất một tiếng). Bước chân KHỚP NHỊP BOB của sway: `Footsteps` nhận `Sway.phase` mỗi khung và phát một tiếng mỗi lần pha đi qua `AudioData.step_bob_phase`
  (3 pi / 4 = súng thấp nhất = chân chạm đất) và cộng pi, tức hai bước mỗi chu kỳ bob; chân trái / phải theo từng mốc; `Foley.update(dt, sway.phase)` gọi SAU `Sway.update`. Đổi `bob_rate` / `bob_sprint_rate` / `bob_stride`
  là nhịp bước đổi theo: đi 1,5 bước/s (cách nhau 0,67 s), chạy nước rút 1,7 bước/s, ngồi 0,73 bước/s. Lý do: bản cũ tính theo quãng đường (0,75 m/bước) ra 6 tiếng/s khi đi mà mỗi tiếng dài 0,31 s nên kêu liên tục.
  Ngồi x0,35 âm lượng. Sải theo quãng đường (`step_stride_*`, `step_start_phase`) chỉ còn là đường dự phòng khi không đưa `bob_phase` (test). Bước đầu tiên sau khi đứng yên đến lúc bob chạm điểm thấp tiếp theo (tối đa nửa chu kỳ).
  Mặc định dùng tiếng do người dùng cung cấp:
  `AudioData.sound_files` ánh xạ tên logic -> nhóm file (`user_*` cắt từ `sounds\source\reload_user_original.wav`, `footstep_wood_user_original.wav` bằng `tools\prep_user_audio.py`; xoá một dòng ánh xạ là quay về tiếng tổng hợp),
  `pitch_scale` đổi cao độ khi dùng chung một file (chạy 1,06; chạm đất 0,78; nhảy 1,12). Tiếng người dùng được chuẩn hoá đỉnh từng lát (bước gốc chênh 7 dB); lát cắt sát cú va nên mốc khung đặt thẳng vào lúc va
  (chốt băng 26, băng trượt vào 57 [rất nhỏ], băng vào chỗ 61; Reload_Empty: 136, 168, 172, và bolt 190). File gốc có 3 cú va: NẠP THƯỜNG chỉ chạy hai cú đầu (không bolt), NẠP CẠN chạy cả ba.
  Không còn tiếng tổng hợp nào trong clip nạp (đã bỏ `mag_out`, `mag_tap`, `bolt_tick`: người dùng nghe thấy tiếng tổng hợp cũ lẫn vào cú va đầu); chỉ `settle` (tay trượt về khi huỷ nạp) và rút súng còn là tiếng tổng hợp.
  `CueSchedule.update` đầu tiên sau `start` KHÔNG cộng dt (lệnh nạp xử lý sau `Handling.update` của khung đó). `Foley.update(dt)` phải nhận cùng dt thật với `Handling`. Nguồn / giấy phép hai file người dùng CHƯA RÕ (xem CREDITS).
- MẶC ĐỊNH ĐÃ CHỐT TỪ BẢNG F1 (người dùng chỉnh bằng tay rồi yêu cầu lấy làm mặc định, 1/11/2026; đã ghi thẳng vào `weapon_data.py`): `gun.reserve` 600 (từ 150), `ads_time` 0,19 (từ 0,25), `view_fov` 75 (từ 70),
  `kick.back_peak` -0,036 (từ -0,030), `back_ads_scale` 1,3 (từ 0,5), sway `lag_gain` 0,05 / `lag_max` 10 / `ads_multiplier` 0,4, shake bắn (trauma 0,30, trần 0,75, tắt 2,5, power 2,3, 20 Hz, pitch 0,50), `tracer.every` 2 (từ 3),
  `view_light.specular` 1,5 (từ 0,30), đèn `lamp_intensity` 4 (từ 3) / `lamp_emissive` 1,5 (từ 3) / `lamp_cone` 60 (từ 30) / `lamp_side` 0,45 (từ 0,35), `fog_density` 0,004, `detail_strength` 1,2 (từ 0,55).
  Các ghi chú đo ở các mục trên (3 cm, 5 cm, 20%...) là của số CŨ. File lưu cũ nằm ở `user_params.baked.json` (không còn được nạp; `.gitignore` bỏ qua `user_params*.json`).
  Các selftest game thật (g3 nhóm G đẩy lùi, g5, g6_shake, g6_debug...) đã được sửa cho khớp bằng cách ĐỌC CODE, CHƯA chạy lại sau lần đổi này: chạy lại để xác nhận.
- Bảng debug F1 (`game/debug_panel.py`) + `ParamStore` (`core/params.py`): 231 thanh sinh TỰ ĐỘNG từ các dataclass (nhóm Bắn / Giật / Độ tản / Ngắm / Sway / Rung / Âm lượng / Nạp / Ánh sáng / Di chuyển / Hiệu ứng; nâng cao ẩn sau nút),
  nhãn + chú thích tiếng Việt ở `core/param_meta.py` (`META`, `GROUPS`, `EXCLUDED`). `test_params` BẮT BUỘC mọi trường mới của `GameParams` phải có trên bảng hoặc trong `EXCLUDED` kèm lý do.
  Lưu / nạp `user_params.json` cạnh `main.py` (gitignore; chỉ ghi số khác mặc định; game thật tự nạp, `--defaults` bỏ qua; `create_game()` mặc định KHÔNG nạp nên selftest không dính file cá nhân).
  Module mới phải ĐỌC LẠI số từ dataclass mỗi lần dùng, không chép lúc dựng (đã sửa `Weapon.interval`, tracer, ánh sáng súng). Trường chép lúc dựng ghi cờ "cần khởi động lại": `gun.magazine`, `gun.reserve`,
  `gun.reload.draw_speed`, `look.lamp_radius`. Bảng mở: `player.ui_open = True` chặn bắn / ngắm / nhìn; chuột nhả. Hình nón tản đạn = 7 vòng (Đứng/Đi/Chạy/Nhảy/Ngồi/Ngắm/Ngắm đi) lấy từ `Accuracy.base`, mặt cắt tại 25 m.
  Lần bấm F1 đầu tiên khựng 226-298 ms (dựng bảng). Đặt màu chữ mỗi khung làm Panda dựng lại hình chữ: chỉ đặt khi đổi (`_tint`).
- HUD: số đạn / dự trữ, chế độ bắn, ĐANG NẠP ĐẠN + thanh tiến độ, HẾT ĐẠN, FPS, khoảng cách bia vừa trúng (2 s rồi mờ), gợi ý phím, ghi công "M4: BarcodeGames (CC BY 4.0)". Bảng mở thì ẩn FPS/gợi ý/ghi công.
- Cây làm việc lẫn CRLF / LF (công cụ Edit và script ghi khác nhau); git tự chuẩn hoá nên vô hại, nhưng đừng coi "giữ CRLF" là tuyệt đối. Heredoc Bash có nháy đơn trong tiếng Việt dễ báo "unexpected EOF": dùng Write / Edit.
- Đã đo ở G6 (máy trống, vsync tắt, 1280x720): đứng yên có bóng thật 83-88 FPS (1% thấp 48-64); cả kịch bản g1 82, g2 71, g3 62 (1% thấp 34-37, sát ngưỡng), g4 82, g5 66. Cao nhất là chi phí shader thế giới mới
  (5 đèn mỗi điểm ảnh) + phòng lớn, thấp hơn G3-G5 (102 / 85) khoảng 20%. `g6_debug_selftest` từng chết (segmentation fault) lúc khởi động đúng 1 trong 5 lần chạy, chạy lại thì đạt: lỗi chập chờn của cửa sổ GL, chưa tìm ra nguyên nhân.
