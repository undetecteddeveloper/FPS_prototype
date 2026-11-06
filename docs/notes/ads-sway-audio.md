<!-- Mở khi: khi đụng tới ngắm, sway, bob, sprint, gun_audio. Trích nguyên văn từ CLAUDE.md cũ (đường dẫn đã cập nhật); số đo ghi trong đây là của lúc đó. -->

# Ngắm, sway, chạy, âm thanh (G4)
- `player.ads_amount` và `player.sprint_amount` là tiến độ TUYẾN TÍNH 0..1 (`gun.ads_time` 0,25 s; `sprint_in_time` 0,2 s, `sprint_out_time` 0,25 s). `smoothstep` chỉ áp khi dùng cho hình ảnh
  (FOV, tư thế súng, tốc độ đi, độ nhạy chuột); độ tản (`spread.py`) dùng số thô. FOV thế giới 80 -> `GunData.ads_fov` 65; độ nhạy chuột nhân `ads_look_multiplier` 0,7 ngay trong `Player.look()`.
- Đường ngắm: `GunData.ads_sights` = (tâm vòng ngắm sau, đỉnh CỘT ngắm trước) đo bằng `tools\measure\g4_ads_align.py` từ đỉnh mô hình (quét nút `Main_M4_D_0-parent`; đừng lấy đỉnh hai cánh che, cao hơn cột 2 mm).
  `sway.ads_pose()` tính phép xoay + tịnh tiến đưa đường ngắm trùng trục nhìn, vòng sau cách mắt `ads_eye_relief` (0,18 m). `g4_selftest` kiểm bằng phép chiếu thật: lệch < 6 px (đo ~1 px).
- `Sway` (`fps/core/sway.py`) cộng 6 thứ thành một tư thế: thở (Lissajous 1:2), lag chuột (lò xo; chuột quay phải thì súng trễ trái), bob (PHA theo quãng đường, bước 2,4 m: nhịp đúng ở mọi tốc độ),
  quán tính dọc theo `player.eye_dy` (thay cho xung nhảy/ngồi riêng: camera lên thì súng trễ xuống) + nhún khi chạm đất, tư thế chạy, tư thế ADS. Khi ngắm, 4 thứ đầu còn `ads_multiplier` = 20%.
  `Viewmodel.update(*poses)` cộng tư thế của kick (G3) và sway rồi đặt lên nút `sway` (dấu hpr: xem BẪY DẤU ở G3).
- Nhún chạm đất: `Player._dip` hạ `camera_pivot.y` (đỉnh `land_dip_per_speed` x tốc độ rơi, ~3,9 cm khi nhảy) và `aim_ray()` lấy gốc tia từ chỗ camera đang ở.
- Sprint-to-fire (`PlayerParams.sprint_blocks_fire` = True): bóp cò khi đang chạy thì thôi chạy (đi bộ), súng đưa lên trong `sprint_out_time`, rồi mới bắn (đo 0,26 s); `Combat` nhớ cú bóp lúc chưa sẵn sàng (bắn đơn
  không mất phát). Đặt False thì bắn thẳng từ tư thế chạy: `g3_selftest` làm vậy để đo độ tản của trạng thái chạy (`accuracy.sprint` chỉ có hiệu lực khi False). Bấm ngắm cũng cắt chạy.
- Tư thế chạy `SwayData.sprint_pose` là số chỉnh bằng mắt (ảnh `shots\g4_sprint.png`): hạ quá tay thì súng văng khỏi màn hình (xoay quanh mắt kéo thân súng xuống ~19 cm với y -0,09 và pitch -20).
- Âm thanh: `fps/game/gun_audio.py` phát từ nhóm 8 bản luân phiên (tiếng 0,5 s, nhịp 0,08 s) với cao độ ngẫu nhiên ±3%. `assets\sounds\m4_shot.wav` dựng bằng `tools\build\prep_sound.py` từ `assets\sounds\source\m4_shot_original.wav`
  (file gốc 2 s, mở đầu im 48 ms làm tiếng trễ ~3 khung: cắt đầu và đuôi, mờ dần 80 ms). Tắt tiếng: `--mute`; selftest tắt bằng `create_game(sound=False)`. Không nghe được loa nên `tools\selftests\audio_selftest.py` kiểm gián tiếp
  (trình phát thật không phải âm câm, độ dài, số lần phát, trạng thái PLAYING); CREDITS ghi rõ nguồn/giấy phép tiếng súng CHƯA có.
- Git/Windows: cây làm việc dùng CRLF (autocrlf), cảnh báo "LF will be replaced by CRLF" vô hại; script thay chuỗi trên file `.py` phải chuẩn hoá `\r\n` -> `\n` trước (đã vấp khi dọn cấu trúc).
- Đã đo ở G4 (vsync tắt, 1280x720, cả kịch bản): trung bình 95 FPS, 1% thấp nhất 70, khung chậm nhất 18 ms.

