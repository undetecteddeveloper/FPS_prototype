# Nền đất, bầu trời, Glock 17 mới (7/11/2026)

Viết cho: người dùng và agent mở phiên sau. Thay thế phần phòng bắn của `range-lights-signs.md` (G6) và model Glock tự dựng của G8.

## Nền đất và bầu trời
- Thế giới chỉ còn MỘT khối hộp phẳng 120 × 120 m, dày 2 m, mặt trên ở y = 0 (`fps/game/ground.py`). Người chơi đứng ở gốc, nhìn về +z, đi được trong khung cách mép 2 m (`WALK_BOUNDS`).
  Đạn trúng khối hộp (`first_hit(..., ground_y=None)`): ra khỏi mép thì rơi vào khoảng trống. Lỗ đạn vẫn vẽ trên đất (`game/decals.py`).
- Màu đất TRẮNG hoàn toàn, không vân (người dùng chốt): `LookData.ground_color = (1, 1, 1)`, `detail_strength = 0`. Vì không có mốc nên có LƯỚI mảnh vẽ trong shader (`world.frag`, `grid_lines`):
  vạch mảnh mỗi 2 m, vạch đậm mỗi 10 m, đặt sao cho điểm xuất phát nằm giữa một ô lớn. Chỉnh bằng F1 mục "Mặt đất và sương" (`look.grid_*`; `grid_strength = 0` thì tắt).
- Ánh sáng: một mặt trời (`look.sun_dir`, `look.sun_color`) cộng ánh nền (`ambient_up/down`), KHÔNG có bóng đổ. Dùng chung cho đất và súng qua `assets/shaders/light_common.glsl`; công thức CPU ở `fps/core/exposure.py` (phơi sáng giờ là một số cố định theo ánh sáng, không còn tự thích nghi).
- Bầu trời: vòm trời vẽ bằng shader (`fps/game/sky.py`, `assets/shaders/sky.vert|frag`): gradient từ màu sương ở chân trời (cùng màu `fog_color`) lên xanh đậm hơn, mây trôi chậm từ nhiễu `look_detail_tex`. Vòm chỉ nhận xoay của camera nên không cần đi theo người chơi.
- ĐÃ XOÁ: phòng bắn, tường, cột, đèn trần, bóng đổ, biển, bia và bia chạy (`core/room`, `core/patrol`, `core/signs`, `game/targets`, `game/signs`, `game/lamp_shadows`, `shooting_range`), tiếng đạn trúng bia (`audio.hit_target_volume`), dấu đánh trúng và số mét bia trên HUD,
  trạng thái căng thẳng / run tay theo số phát bắn (`FreeAim.stress`, `tremor_*`). Tiếng thở và nhịp thở của súng GIỮ NGUYÊN.
- Bộ selftest `tools/selftests/*` và vài công cụ đo cũ dựng bằng bia / phòng nên KHÔNG còn chạy được (người dùng bảo không cần selftest, 7/11/2026). Muốn dùng lại thì phải viết lại theo nền đất.

## Glock 17 (gói animation `assets/guns/glock17.glb`)
- File có sẵn tay + súng + 6 clip trên MỘT dòng thời gian 30 fps, giống gói M4: Reload 1–84, Fire 86–105, ReloadEmpty 107–197, Holster 198–211, Draw 212–245, Idle (một tư thế). Khung N của clip N khung bị bao về 0 nên khung dùng được cuối cùng là N−1.
- Gói luân phiên HAI băng đạn: Mag2 nằm trong súng ở tư thế sẵn sàng / bắn / rút / cất (Mag1 đậu xa), Mag1 nằm trong súng ở tư thế khoá slide và đầu hai clip nạp (Mag2 đậu xa). `GunData.mag_nodes = (nhóm sẵn sàng, nhóm khoá slide)`; `Viewmodel._update_mags` chỉ vẽ băng đang ở trong súng (cả hai trong lúc nạp).
  Tư thế sẵn sàng = khung cuối clip Draw (khung 245); tư thế khoá slide = khung đầu ReloadEmpty (107). Cắm băng mới xong ở khung 45 (Reload) / 151 (ReloadEmpty); nhả slide ở khung 164–165.
- `fps/game/gltf_patch.py` có thêm 2 bản vá (nay là 8): gộp các skin dùng chung xương (tay và găng là hai skin), và đặt gốc xương ở tổ tiên chung của mọi nút có animation (các bộ phận súng và camera nằm cạnh xương tay, không nằm dưới nó nên trước đây đứng yên).
  `tests/test_glock_model.py` kiểm các điều này; đổi file hoặc phiên bản thư viện thì chạy lại.
- Số đo bằng `tools/measure/g8_measure.py` (điểm ngắm, miệng nòng), mốc âm thanh đo bằng cách pose từng 2 khung rồi theo dõi băng đạn và slide (ghi trong `GLOCK_SOUND_CUES`). `hip_offset` z +0,15 và `ads_eye_relief` 0,5 là số đặt thử, người chơi chỉnh tiếp.
- Tác giả / giấy phép của file CHƯA RÕ: ghi ở `CREDITS.txt`, cần người dùng điền trước khi phát hành.
