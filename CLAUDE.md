# FPS prototype (Ursina, cảm giác CoD MW2019)

Đề bài và quyết định đã chốt: `PROMPT_PHIEN_THI_CONG.md`. Trả lời, commit, tài liệu bằng tiếng Việt thường.

## Lệnh
- Chạy game: bấm đúp `run.bat` (hoặc `.venv\Scripts\python.exe main.py`). Tuỳ chọn: `--novsync`, `--size 1280x720`, `--fullscreen`,
  `--quit-after 5` (tự thoát sau 5 giây, dùng để kiểm tra mà không phải tắt tiến trình).
- Kiểm tra bằng game thật (điều khiển qua `held_keys`/`combat.pressed`, đo, chụp ảnh vào `shots\`; thoát mã 1 nếu trượt):
  `.venv\Scripts\python.exe -X utf8 tools\g1_selftest.py` (di chuyển), `tools\g2_selftest.py` (bắn: nhịp, độ rơi từng bia, đạn, hit marker, lỗ)
  và `tools\g3_selftest.py` (recoil, độ tản theo trạng thái, bloom, tâm ngắm so với phép chiếu thật, kick súng trên màn hình)
- Test (toán thuần + nạp glb, không mở cửa sổ): `.venv\Scripts\python.exe -X utf8 -m pytest`
- Công cụ G0: `tools\g0_view.py` (chụp ảnh tư thế), `tools\g0_timing.py` (đo clip + FPS), `tools\g0_motion.py`
- Cài lại môi trường: `py -3.13 -m venv .venv` rồi `.venv\Scripts\pip install -r requirements.txt` (KHÔNG dùng Python 3.15)

## Quy ước
- Mọi thông số súng/recoil/spread/sway nằm trong `weapon_data.py` (dataclass). Không rải số ra module khác.
- Module: `weapon_data.py` (mọi số), toán thuần không import ursina và có pytest: `movement.py`, `ballistics.py` (đạn, va chạm), `weapon.py`
  (nhịp bắn, đạn), `recoil.py` (recoil camera + kick súng), `spread.py` (độ tản, bloom, hình nón, tâm ngắm), `spring.py` (lò xo giảm chấn); phần ghép Ursina: `player.py`, `combat.py`, `targets.py`, `viewmodel.py`, `shooting_range.py`, `hud.py`,
  `main.py` (`create_game()` dựng tất cả; tools gọi lại hàm này). Toán mới thì tách ra module thuần để pytest được.
- Thứ tự mỗi khung hình cố định trong `Game.update`: `player.tick()` -> `combat.update()` -> `viewmodel.update()` -> `hud.update()`.
  Đừng để từng đối tượng tự `update` riêng (thứ tự Ursina không đảm bảo, bắn sẽ dùng hướng nhìn của khung trước).
- Cổng kiểm tra trước mỗi commit: pytest qua, game mở được và ≥ 60 FPS, không lỗi trong console.
- Commit trên nhánh `dev`. Chỉ push khi người dùng nói. `guns\animated_fps_hands_rifle_animation_pack.glb` (109 MB) bị gitignore.

## Nạp M4 (bẫy đã trả giá ở G0, đừng làm lại)
- LUÔN `import gltf_patch; gltf_patch.apply()` trước khi tạo `Ursina()` hay nạp glb. `panda3d-gltf 1.3.0` nạp sai file này theo
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
- Không có normal map, không PBR (đường vẽ cố định của Panda). Muốn đẹp hơn thì cần simplepbr; chưa làm.

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
- Kiểu `Entity` mới của Ursina dùng shader không đèn (màu phẳng); chỉ viewmodel có đèn.
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
- Phím tạm: `R` nạp đầy băng từ dự trữ ngay lập tức (G5 thay bằng reload có animation). `B` đổi tự động / bắn đơn. Không bắn khi chuột đã nhả (Esc).
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
