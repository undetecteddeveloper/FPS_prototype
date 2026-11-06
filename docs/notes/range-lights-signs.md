<!-- Mở khi: khi đụng tới phòng, đèn, bóng, bia chạy, biển, bảng F1, foley, bước chân. Trích nguyên văn từ CLAUDE.md cũ (đường dẫn đã cập nhật); số đo ghi trong đây là của lúc đó. -->

# Phòng tập, đèn, bóng, bia chạy, biển (G6)
- Trường bắn là PHÒNG KÍN: tường bốn phía + trần 5,5 m + sàn gạch, lòng rộng 24 m, z từ −20 đến 216; người chơi kẹp bởi `WALK_BOUNDS` (x ±10,8). Hình học thuần ở `core/room.py` (tường, cột, dầm, tấm tiêu âm, vị trí đèn), mesh gộp ở
  `game/shooting_range.py`. Đạn trúng tường/trần (lỗ đạn trên đó); dò va chạm nhóm hộp 30 m (`ballistics.BoxGroup`) nên không tốn.
- Ánh sáng: 23 bóng đèn treo trần cách nhau 10 m (cao 4,6 m), mỗi đèn đổ bóng THẬT. `LookData` (đèn: màu, cường độ, bán kính, nón; ánh nền; exposure; sương trong phòng; `shadows` True / 'fake' / False,
  đổi lúc chạy bằng `game.look.set_shadow_mode`). Bản đồ bóng = atlas cubemap 5 mặt (bỏ mặt lên trần) vẽ MỘT lần lúc dựng (`render_now`) trong một kết cấu 2816x2816; mỗi khung chỉ tốn lấy mẫu trong shader.
  Vẽ atlas ở khung đầu làm khung đó dài ~0,5 s và g5 trượt 5 mục (rút súng): đã chuyển sang lúc dựng game. Máy trống: bóng thật 83-88 FPS, +6-9% thời gian khung so với tắt bóng (`tools\measure\room_perf.py`).
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
  Bắn (G7, viết lại kiểu Bodycam; mô hình trauma^power cũ làm phát lẻ chỉ ~6% và mọi phát giống nhau, đã bỏ): MỖI PHÁT một xung vào lò xo 6 trục (`fire_omega` 38, `fire_zeta` 0,45), đỉnh = độ mạnh ngẫu nhiên 0,6..1,4 x (`fire_bias` + `fire_spread` x ngẫu nhiên có dấu):
  pitch ngóc ~1 độ, roll ± tới 2 độ, yaw ± 0,55. Độ nóng `heat` (+1/25 mỗi phát, giữ 0,12 s rồi nguội 3/s) nhân cú giật 1 + `heat_boost` 1,2 và thêm run tay 22 Hz: cả băng ~2 lần phát lẻ, ngừng bắn về ~0 sau 0,5 s. `shake.trauma` = `heat` (tên cũ). Nạp: xung lò xo ở các mốc
  mag_out / seat / bolt (`ShakeData.reload_beats`), không rung suốt clip. ADS còn 50%. Súng đi theo 60% (`gun_follow`) trễ 0,02 s. Dấu đã đo: `camera.rotation_x` dương = nhìn xuống, `rotation_y` dương = quay phải,
  `rotation_z` dương = nghiêng phải. Sự kiện (`on_shot/on_beat/watch_reload`) phải vào TRƯỚC `Shake.update(dt)` của khung. Shake có seed riêng (không dùng chung `combat.rng`, kẻo đổi chuỗi ngẫu nhiên của đạn).
- Đẩy lùi súng: lò xo RIÊNG `GunKick.back` (omega 18, zeta 0,7; chậm hơn nhịp bắn 0,08 s nên các phát dồn lên); `back_peak` -0,036 (3,6 cm một phát, cả băng ~1,7 lần), ADS x1,3 (người dùng chỉnh: ngắm lùi NHIỀU hơn hông; bản đầu là 3 cm / 5 cm / x0,5). Lò xo kick cũ (omega 38) đã trượt về trước phát kế nên liên thanh chỉ lùi 2,2 cm.
  `back_x_ratio` 0,3 nhích súng vào giữa khi lùi (súng lệch phải 7 cm sẽ trượt ra rìa màn hình), chỉ lúc hông. `GunKick.on_shot(ads, age)` nhận tuổi phát trong khung (độc lập FPS). Cuối loạt hông thân sau súng tràn ra góc dưới phải;
  thấy nặng thì giảm `back_peak` (~0,025).
- Sway chuột (`MouseLag` trong `core/sway.py`): hệ bậc hai theo vận tốc quay (tham số tần số / giảm chấn / phản ứng, nghiệm chính xác nên ổn định mọi dt), đầu vào làm mượt `lag_smooth`, ngưỡng mềm `lag_deadzone`,
  nén tanh tới `lag_max` thay vì kẹp cứng (kẹp cứng cũ bẹt mọi cú xoay 120-900°/s ở 3,9°: nguyên nhân "cứng"). `lag_gain` là GIÂY (lệch = gain x tốc độ quay). Flick 240°/s: lệch 3,9° -> 7,2°, quá đà 13%, ổn định 0,25 s.
  Đỉnh flick ≈ `lag_max` (có thể vượt ~10%). Số đáng chỉnh: `lag_max` 10 (người dùng chỉnh từ 8), `lag_gain` 0,05 (từ 0,04), `lag_zeta` 0,60, `lag_omega` 17. Sway khi ngắm còn `ads_multiplier` 0,4 (từ 0,2). Nguồn tra được mỏng (Patreon t3ssel8r, wiki Valve trả 403): thuật toán là tự suy từ kiến thức về "second order dynamics".
- Bob súng (6/11/2026 người dùng bảo tăng nhịp 40%: nay `bob_rate` 0,56 và `bob_sprint_rate` 0,483 (0,42 rồi +15% riêng khi chạy); nhịp bước chân và nhịp nhún camera đi theo vì cùng đọc pha bob; các số bước/s ghi ở mục âm thanh bên dưới là của 0,4 / 0,3, nhân 1,4): `bob_rate` 0,4 (đi / ngồi đi) và `bob_sprint_rate` 0,3 (chạy nước rút) nhân vào tốc độ pha; biên độ giữ nguyên. Nhịp bước chân KHÔNG đọc pha bob.
- Âm thanh nạp đạn / bước chân (`game/foley.py`, `core/cues.py`, `core/footsteps.py`, `AudioData`): tiếng phát theo MỐC KHUNG của clip (`M4_SOUND_CUES`, thời điểm thật = (khung − clip.start)/30/`ReloadData.speed`), huỷ nạp thì
  bỏ mốc chưa tới (+ tiếng `settle` nếu đã phát ít nhất một tiếng). Bước chân KHỚP NHỊP BOB của sway: `Footsteps` nhận `Sway.phase` mỗi khung và phát một tiếng mỗi lần pha đi qua `AudioData.step_bob_phase`
  (3 pi / 4 = súng thấp nhất = chân chạm đất) và cộng pi, tức hai bước mỗi chu kỳ bob; chân trái / phải theo từng mốc; `Foley.update(dt, sway.phase)` gọi SAU `Sway.update`. Đổi `bob_rate` / `bob_sprint_rate` / `bob_stride`
  là nhịp bước đổi theo: đi 1,5 bước/s (cách nhau 0,67 s), chạy nước rút 1,7 bước/s, ngồi 0,73 bước/s. Lý do: bản cũ tính theo quãng đường (0,75 m/bước) ra 6 tiếng/s khi đi mà mỗi tiếng dài 0,31 s nên kêu liên tục.
  Ngồi x0,35 âm lượng. Sải theo quãng đường (`step_stride_*`, `step_start_phase`) chỉ còn là đường dự phòng khi không đưa `bob_phase` (test). Bước đầu tiên sau khi đứng yên đến lúc bob chạm điểm thấp tiếp theo (tối đa nửa chu kỳ).
  Mặc định dùng tiếng do người dùng cung cấp:
  `AudioData.sound_files` ánh xạ tên logic -> nhóm file (`user_*` cắt từ `assets\sounds\source\reload_user_original.wav`, `footstep_wood_user_original.wav` bằng `tools\build\prep_user_audio.py`; xoá một dòng ánh xạ là quay về tiếng tổng hợp),
  `pitch_scale` đổi cao độ khi dùng chung một file (chạy 1,06; chạm đất 0,78; nhảy 1,12). Tiếng người dùng được chuẩn hoá đỉnh từng lát (bước gốc chênh 7 dB); lát cắt sát cú va nên mốc khung đặt thẳng vào lúc va
  (chốt băng 26, băng trượt vào 57 [rất nhỏ], băng vào chỗ 61; Reload_Empty: 136, 168, 172, và bolt 190). File gốc có 3 cú va: NẠP THƯỜNG chỉ chạy hai cú đầu (không bolt), NẠP CẠN chạy cả ba.
  Không còn tiếng tổng hợp nào trong clip nạp (đã bỏ `mag_out`, `mag_tap`, `bolt_tick`: người dùng nghe thấy tiếng tổng hợp cũ lẫn vào cú va đầu); chỉ `settle` (tay trượt về khi huỷ nạp) và rút súng còn là tiếng tổng hợp.
  `CueSchedule.update` đầu tiên sau `start` KHÔNG cộng dt (lệnh nạp xử lý sau `Handling.update` của khung đó). `Foley.update(dt)` phải nhận cùng dt thật với `Handling`. Nguồn / giấy phép hai file người dùng CHƯA RÕ (xem CREDITS).
- MẶC ĐỊNH ĐÃ CHỐT TỪ BẢNG F1 (người dùng chỉnh bằng tay rồi yêu cầu lấy làm mặc định, 1/11/2026; đã ghi thẳng vào `weapon_data.py`): `gun.reserve` 600 (từ 150), `ads_time` 0,19 (từ 0,25), `view_fov` 75 (từ 70),
  `kick.back_peak` -0,036 (từ -0,030), `back_ads_scale` 1,3 (từ 0,5), sway `lag_gain` 0,05 / `lag_max` 10 / `ads_multiplier` 0,4, shake bắn (trauma 0,30, trần 0,75, tắt 2,5, power 2,3, 20 Hz, pitch 0,50; G7 đã thay cả mô hình, xem mục camera shake), `tracer.every` 2 (từ 3),
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

