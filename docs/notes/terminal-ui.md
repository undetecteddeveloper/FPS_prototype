<!-- Mở khi: đụng màn splash, bảng đồ hoạ (Esc), lưới ký tự / bố cục UI kiểu terminal, âm thanh UI. Phiên G20, 12/11/2026. Kế hoạch + câu trả lời: docs/sessions/G20.md; skill: .claude/skills/phosphor-terminal-ui. -->

# Splash CLI quân đội + bảng đồ hoạ bodycam (G20)

## Quyết định của người dùng (12/11/2026)
- Splash KẾT HỢP: dòng log chạy theo các bước nạp THẬT, rồi đoạn kết cố định. Xanh phốt-pho trên đen (P1 `#33FF33`). Tiếng Anh thuật ngữ quân sự (ngoại lệ của quy ước "chữ cho người dùng viết tiếng Việt").
- KHÔNG thêm HUD (giữ quyết định 5/11/2026: màn hình sạch). "UI bodycam" = bảng đồ hoạ: dải trạng thái (chấm REC, giờ ghi, tiêu đề, FPS), hàng đảo màu, góc khung.
- **F1 không đụng** (không dịch `param_meta.py`, không sửa `debug_panel.py`). Bảng đồ hoạ **mở / đóng bằng Esc** (F2 không còn mở nó; Esc không còn bật / tắt khoá chuột).
- Âm thanh tự tổng hợp bằng numpy (không credit).

## Splash (`game/boot.py`, kịch bản `core/termui.py: BootSeq`)
Luồng: `main()` -> `create_game(splash=True)` dựng `BootScreen` ngay sau khi cửa sổ mở (hoạt ảnh bật CRT 0,34 s, tiếng degauss + tiếng hum nền). Trong lúc dựng, `Game._stage(nhãn, tiến độ)` báo từng bước THẬT (`OPEN DISPLAY`, `LOAD ENVIRONMENT MAP`, `INIT PLAYER / PHYSICS`, `INIT AUDIO SUBSYSTEM`, `LOAD WEAPON SYSTEMS`, `INIT RENDER PIPELINE`, `COMPILE SHADERS`, `PRELOAD WEAPON KITS`, `WARM SHADER BUILDS`, `BUILD INTERFACE`); mỗi lần vẽ một khung (dòng trước thành `[  OK  ]`, tem `[ 1.694]` là giây thật). Nướng ánh sáng báo tiến độ vào chính dòng đang chạy (`LIGHT BAKE POOL HALL 42%`, qua `pool._BakeScreen` -> `boot.ACTIVE`).
Dựng xong: `load_done()` đọc số THẬT (giờ máy, ổ đĩa trống, nguồn / pin, âm thanh) và xếp đoạn kết (~4 s: FIELD CHECK, CONTROLS kèm `ESC VIDEO CONFIGURATION`, `RECORDING ARMED`, `● REC` + tiếng bíp đôi). Rồi `Game.update` chạy `boot.update(dt)`:
`hold` (đoạn kết chạy, GAME BỊ GIỮ: không `player.tick`, súng chưa rút, tiếng nền chưa bật) -> `off` (hình xẹp thành một đường, 0,2 s) -> `fade` (game chạy, tấm phủ đen mờ dần 0,7 s) -> `gone`.
- Bấm phím / chuột bỏ qua đoạn kết, trừ (a) đang nạp, (b) 0,4 s đầu sau khi nạp (phím bấm lúc nạp tới game ở khung đầu tiên: đừng cho nó bỏ qua). Esc dưới splash chỉ bỏ qua, không mở bảng đồ hoạ.
- Đồng hồ splash sau khi nạp chạy theo thời gian KHUNG (mỗi khung cộng tối đa 0,1 s): khung đầu tiên của game có thể dài vài giây và không được ăn hết đoạn kết.
- `--no-splash` tắt; các công cụ kiểm bằng game thật không bao giờ thấy splash (`create_game(splash=False)` mặc định); `--quit-after` vẫn đếm cả lúc splash.
- Hiệu ứng CRT rẻ: đường quét (một texture 1x3 lặp, `nearest`) + viền tối (texture 128x128) + một tấm đen mờ nhấp nháy ≤ 3%, chỉ có lúc splash (mỗi tấm toàn màn hình tốn ~1,6-3,3 ms GPU ở 1080p trên máy này).

## Bảng đồ hoạ (`game/graphics_panel.py`)
- `Game.input`: Esc (khi F1 đóng) = `gfx_panel.toggle()`. Mở thì nhả chuột + chặn bắn / ngắm (`player.ui_open`), đóng thì khoá chuột + lưu `user_graphics.json` (nền, atomic). F1 mở thì Esc vẫn đóng F1.
- Phím: ↑↓ chọn, ←→ / Enter đổi; chuột: dòng dưới con trỏ được chọn khi con trỏ DI CHUYỂN, bấm trái = lựa chọn kế, phải = trước, lăn = di chuyển.
- Chuyển động: mở từ một đường (0,16 s), đóng (0,11 s), thanh chọn trượt tới dòng (nhảy > 3 dòng thì bật tới), đổi giá trị thì thanh sáng lên 0,12 s, chấm REC nhấp nháy 1 Hz. Âm thanh: mở / đóng / di chuyển / đổi.
- Nhãn tiếng Anh trong `core/graphics.OPTIONS` (nhãn ≤ 38, giá trị ≤ 8 ký tự IN HOA: test giữ). File lưu chỉ chứa GIÁ TRỊ, dịch nhãn không làm hỏng `user_graphics.json`.
- Dựng SẴN lúc nạp (`prebuild()`): dựng ~40 dòng chữ mất ~0,8 s, để lười thì lần Esc đầu tiên khựng cả game.

## Lưới ký tự và chuyện "lệch bố cục tinh vi"
- Consolas: ô ký tự = 0,55 em. `termui.make_grid(H)` chọn `cw` NGUYÊN pixel, `lh` = 2,1 `cw`, và `Grid.text_scale` để một ô đúng `cw` px (đo: bước ký tự 10,000 px ở 720p, 15 / 11 px ở 1080p / 768p). Mọi toạ độ là pixel nguyên (gốc trên-trái), đổi sang Ursina bằng `px_to_ui_*`; hình chữ nhật (`theme.rect`) có mép đúng ranh pixel.
- Tâm chữ HOA nằm 0,45 em dưới mép trên của Text (`CAP_CENTER_EM`, đo ở 720p / 768p / 1080p), nên chữ nằm giữa dòng ±0,5 px.
- Cột giá trị cố định (mũi tên ở ô 0 và ô cuối, giá trị luôn bắt đầu ô 2): đổi giá trị / chọn dòng không làm gì xê dịch. Căn GIỮA theo pixel (`centered_x`), không theo cột (tiêu đề 19 cột trong 60 cột lệch nguyên một cột nếu căn theo cột). Biểu ngữ dưới của splash neo theo ĐÁY cửa sổ (lưới từ trên xuống để hở 24 px ở 1080p).
- Ký tự khung `─│┌` vẽ lệch trong Consolas qua Ursina: đường kẻ dùng hình chữ nhật. `█ ░ ● ◄ ► ↑ ↓ ← →` đều có trong Consolas.
- Kiểm: `tests/test_termui.py` (68 mục, 9 độ phân giải: lề, bước hàng, cột, giữa, không chồng nhau) và `tools\measure\ui_check.py` đo PIXEL trên ảnh thật: bốn góc panel đúng pixel, thanh chọn đúng hàng ±0 px, chữ đầu mỗi nhãn nằm giữa hàng (≤ 1,5 px; thực đo 0,5 px ở 720p, 1,0 px ở 1080p), không mũi tên ở hàng không chọn, tiêu đề lệch ≤ 1 px.

## Âm thanh (`tools/build/make_ui_sounds.py` -> `assets/sounds/ui/`, 13 file, ~460 KB)
`boot_degauss`, `boot_hum` (lặp liền mạch: số chu kỳ nguyên, nhiễu tuần hoàn), `key_0..2` (gõ chữ, xoay vòng + giới hạn nhịp), `blip`, `ok`, `relay`, `rec_start` (bíp đôi 1,9 / 2,5 kHz), `ui_open`, `ui_close`, `ui_move`, `ui_change`. Mức từng âm ở `game/ui_audio.py: VOLUME`. Test `tests/test_ui_sounds.py`: định dạng, độ dài, đỉnh 0,3-0,9, không click đầu / cuối, không lệch DC, hum lặp không có mối nối, file khớp đúng công cụ. **TÔI KHÔNG NGHE ĐƯỢC LOA**: cảm giác thật do người dùng đánh giá (chưa ưng thì chỉnh hằng số trong công cụ rồi chạy lại).

## Bẫy đã gặp (đừng lặp lại)
1. UI vẽ TRƯỚC khung đầu tiên phải gọi `window.update_aspect_ratio()`; không thì chữ to ~20 lần (`BootScreen` gọi).
2. Vẽ một khung GIỮA lúc `Game.__init__` dựng sẽ vẽ cả cảnh 3D dở dang: Panda ném `Shader input look_camera_pos is not present`. `BootScreen._frame` ẩn `base.render` quanh lệnh vẽ. (`warm_shader_builds` vẫn vẽ cảnh thật vì nó tự gọi vẽ.)
3. Thời gian một khung bị tính vào khung SAU: bộ kiểm chụp PNG + phân tích numpy bên trong `update` làm khung kế tiếp trông như khựng 0,9 s. Đo thời gian khung phải chờ vài khung sau việc nặng.
4. Khung ẩn chạy ~1 ms: chờ "0,11 s hiệu ứng" bằng số khung là sai, chờ bằng thời gian thật.
5. Đặt màu `Text` dựng lại glyph (~0,3 ms): `TermText.set` chỉ đổi khi khác.
6. Glow đối xứng (hai bản lệch ±1 px) chỉ dùng cho dòng nổi (tiêu đề, thanh tiến độ); log cuộn không dùng vì mỗi lần cuộn dựng lại hết các dòng.

## Hạn chế / chưa làm
- Chưa chạy bằng CỬA SỔ THẬT (người dùng đang dùng máy): nhánh hoạt ảnh bật CRT chạy được trong buffer ẩn, nhưng cảm giác thời gian, tiếng loa, nhấp nháy CRT cần người dùng xem / nghe. `chaos_check.py` và `launch_check.py` (cần cửa sổ) chưa chạy lại sau khi Esc đổi nghĩa; `chaos_check` đã sửa cho khớp.
- Chưa đo máy yếu (`weak_pc.py`); đo ẩn: panel mở thêm ~1,2-2,7 ms mỗi khung ở 720p / 1080p (chỉ khi đang mở). Exe chưa dựng lại.
- Còn chữ tiếng Việt / phím cũ ở những chỗ CỐ Ý không đụng: bảng F1 (dòng gợi ý "Esc nhả chuột" nay sai vì Esc mở bảng đồ hoạ; `param_meta.py` còn nói "mức F2", "Chi tiết bề mặt"), `hud.py` (HUD chỉ dùng khi kiểm tra), `Notice` (tên tầng Backrooms), tên `GraphicsLevel` (Thấp / Vừa / Cao, hiện qua `Notice`).
- Tên đơn vị `BWC-07`, `RECON-1`, ngày dựng `2026.11.12` là hằng số hư cấu; đoạn kết ghi rõ `TRAINING SIMULATION - NOT A REAL SYSTEM` để không giả làm hệ thống / tổ chức thật.
