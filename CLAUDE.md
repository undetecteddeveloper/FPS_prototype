# FPS prototype (Ursina, cảm giác CoD MW2019)

Đề bài và quyết định đã chốt: `PROMPT_PHIEN_THI_CONG.md`. Trả lời, commit, tài liệu bằng tiếng Việt thường.

## Lệnh
- Chạy game: bấm đúp `run.bat` (hoặc `.venv\Scripts\python.exe main.py`). Tuỳ chọn: `--novsync`, `--size 1280x720`, `--fullscreen`,
  `--quit-after 5` (tự thoát sau 5 giây, dùng để kiểm tra mà không phải tắt tiến trình).
- Kiểm tra G1 bằng game thật (điều khiển qua `held_keys`, đo, chụp ảnh vào `shots\`): `.venv\Scripts\python.exe -X utf8 tools\g1_selftest.py`
- Test (toán thuần + nạp glb, không mở cửa sổ): `.venv\Scripts\python.exe -X utf8 -m pytest`
- Công cụ G0: `tools\g0_view.py` (chụp ảnh tư thế), `tools\g0_timing.py` (đo clip + FPS), `tools\g0_motion.py`
- Cài lại môi trường: `py -3.13 -m venv .venv` rồi `.venv\Scripts\pip install -r requirements.txt` (KHÔNG dùng Python 3.15)

## Quy ước
- Mọi thông số súng/recoil/spread/sway nằm trong `weapon_data.py` (dataclass). Không rải số ra module khác.
- Module: `weapon_data.py` (mọi số), `movement.py` (toán thuần, không import ursina), `player.py`, `viewmodel.py`, `shooting_range.py`,
  `hud.py`, `main.py` (`create_game()` dựng tất cả; tools gọi lại hàm này). Toán mới thì tách ra module thuần để pytest được.
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
