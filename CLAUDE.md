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
  và `tools\audio_selftest.py` (BẬT tiếng, kiểm trình phát thật và số lần phát; các selftest khác tắt tiếng bằng `create_game(sound=False)`).
  Các selftest G1–G4 gọi `create_game(draw=False)` để khỏi chờ 1 s rút súng; `create_game(effects=False, look=False)` tắt tia lửa/tracer và shader thế giới (để đo)
- Công cụ dựng/đo: `tools\prep_sound.py` (dựng `sounds\m4_shot.wav` từ file gốc), `tools\g4_ads_align.py` (đo điểm ngắm của súng, in tư thế ADS),
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
  core/                  toán thuần, KHÔNG import ursina, có pytest: movement, ballistics, weapon, recoil, spread, spring, sway, handling (nạp/rút súng), fx (tia lửa/tracer)
  game/                  phần ghép Ursina/Panda: player, combat, targets, viewmodel, shooting_range, hud, gltf_patch, gun_audio, effects, look, shaders
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
- Vạch ngang làn mảnh hơn một điểm ảnh ở ≥ 100 m nên đứt nét: chỉ vạch tới 50 m, xa hơn dùng cột (G6 thêm biển chữ).
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
- Shader thế giới `shaders/world.*` (áp bằng `Entity.shader` trong `game/look.py`): đèn nửa cầu + mặt trời (pháp tuyến lấy từ đạo hàm vị trí nên không cần mesh có normal), nhiễu giá trị hai tỉ lệ trên mặt nằm ngang (mờ dần 40-160 m),
  sương mù exp 0,0032 hoà vào màu chân trời (0,75, 0,84, 0,87), lớp tối góc màn hình. Chi phí đo được ~0,2 ms/khung (trong nhiễu của máy). Số liệu ở `weapon_data.LookData`.
  KHÔNG dùng FXAA của Ursina (`camera.shader = fxaa_shader`): bầu trời thành xám phẳng khi có vùng vẽ súng riêng; MSAA vẫn cấm.
- Đạn chia bước <= 1/120 s khi dò va chạm (`MAX_BULLET_STEP`): trước đây một khung treo 40 ms làm điểm trúng lệch tới `g*dt^2/8` = 3 mm ở 10 m (g2_selftest bắt được).
- CHƯA GIẢI QUYẾT: phát bắn ĐẦU TIÊN của phiên có một khung ~40 ms (các phát sau 8-13 ms). Chỉ xảy ra khi tia lửa/tracer được cập nhật thật (tắt `Effects.update` thì hết). Đã thử: `prepare_scene`, vẽ thử nút vài khung lúc dựng
  (giảm khung thứ hai từ 25 xuống 10 ms), chạy thử đường mã, thay billboard bằng ma trận, PTA cho đèn, đóng băng bộ gom rác: không hết. Giờ chỉ còn một lần mỗi phiên.
- Đã đo ở G5 (vsync tắt, 1280x720, cả kịch bản g5_selftest): trung bình 85 FPS, 1% thấp nhất 59; bắn liên thanh có tia lửa + tracer không tụt đáng kể.
