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
  trạng thái căng thẳng / run tay theo số phát bắn (`FreeAim.stress`, `tremor_*`). Tiếng thở dốc (hơi thở khi đứng yên) đã bỏ 7/11/2026 (`core/breath.py`, `audio.breath_*`); súng vẫn nhấp nhô nhẹ theo nhịp thở trong `sway`.
- Bộ selftest `tools/selftests/*` và vài công cụ đo cũ dựng bằng bia / phòng nên KHÔNG còn chạy được (người dùng bảo không cần selftest, 7/11/2026). Muốn dùng lại thì phải viết lại theo nền đất.

## Glock 17 (gói animation `assets/guns/glock17.glb`)
- File có sẵn tay + súng + 6 clip trên MỘT dòng thời gian 30 fps, giống gói M4: Reload 1–84, Fire 86–105, ReloadEmpty 107–197, Holster 198–211, Draw 212–245, Idle (một tư thế). Khung N của clip N khung bị bao về 0 nên khung dùng được cuối cùng là N−1.
- Gói luân phiên HAI băng đạn: Mag2 nằm trong súng ở tư thế sẵn sàng / bắn / rút / cất (Mag1 đậu xa), Mag1 nằm trong súng ở tư thế khoá slide và đầu hai clip nạp (Mag2 đậu xa). `GunData.mag_nodes = (nhóm sẵn sàng, nhóm khoá slide)`; `Viewmodel._update_mags` chỉ vẽ băng đang ở trong súng (cả hai trong lúc nạp).
  Tư thế sẵn sàng = khung cuối clip Draw (khung 245); tư thế khoá slide = khung đầu ReloadEmpty (107). Cắm băng mới xong ở khung 45 (Reload) / 151 (ReloadEmpty); nhả slide ở khung 164–165.
- `fps/game/gltf_patch.py` có thêm 2 bản vá (nay là 8): gộp các skin dùng chung xương (tay và găng là hai skin), và đặt gốc xương ở tổ tiên chung của mọi nút có animation (các bộ phận súng và camera nằm cạnh xương tay, không nằm dưới nó nên trước đây đứng yên).
  `tests/test_glock_model.py` kiểm các điều này; đổi file hoặc phiên bản thư viện thì chạy lại.
- Số đo bằng `tools/measure/g8_measure.py` (điểm ngắm, miệng nòng), mốc âm thanh đo bằng cách pose từng 2 khung rồi theo dõi băng đạn và slide (ghi trong `GLOCK_SOUND_CUES`). `hip_offset` z +0,15 và `ads_eye_relief` 0,5 là số đặt thử, người chơi chỉnh tiếp.
- Tác giả / giấy phép của file CHƯA RÕ: ghi ở `CREDITS.txt`, cần người dùng điền trước khi phát hành.

## Rung vào ống kính, ánh nhìn khi nạp, khói súng, đổi súng (7/11/2026, chiều)
- Rung kiểu Bodycam: camera thế giới đứng yên theo hướng nhìn; toàn bộ rung (đầu / thân, bước, nhảy / chạm đất, bắn, mốc nạp, trôi khi đứng, ánh nhìn khi nạp) cộng thành một tư thế,
  `core/lens.frame_shake` đổi ra độ dịch + nghiêng của CẢ khung ảnh (thế giới + súng + viền tối + tâm méo) trong `lens.frag`. Mép khung hé đen khi lắc mạnh (viền tối che bớt).
  Súng nằm trong ảnh nên lắc cùng khung (không còn tư thế "súng đi theo" riêng). Quy đổi: dịch đầu x mét như xoay atan(x / `lens.shake_pos_ref`); độ dịch nhân (1 + độ méo mắt cá) để giữa khung lắc như trước.
  Chỉnh ở F1, nhóm "Ống kính lắc": `shake_scale` (0 = khung đứng yên), `shake_glance` (0,45: cúi nhìn băng trượt khung ~1/8 chiều cao, người dùng chọn "vừa").
- Ánh nhìn khi nạp (`core/gaze.py`): nhìn vào điểm giữa tay trái (cầm băng) và thân súng (`Viewmodel.gaze_angles`, `gaze_hand_weight`). Chuyển điểm nhìn bằng cú LIẾC
  (đường minimum-jerk: chậm - nhanh - chậm, hơi quá đà), dừng nhìn 0,18-0,45 s, trong lúc dừng bám theo tay chậm; mỗi lần nạp độ sâu / nhịp / độ lệch khác nhẹ (`gaze_jitter`). Giới hạn mềm (tanh) thay vì kẹp cứng.
  Cúi xuống ~`glance_in_time`, ngẩng về `glance_out_time` (huỷ nạp: `glance_cancel_time`). Tích phân bước con 1/240 s nên 30 và 240 FPS cho cùng đường nhìn.
- Khói thuốc súng: toán `core/smoke.py` (sức cản mũ chính xác theo bước, bốc lên, gió `look.wind`, trôi mượt, chạm đất thì loang; nòng + cửa nhả vỏ), vẽ `game/smoke.py` + `smoke.vert|frag`:
  MỘT lần vẽ, tối đa 128 búi, không texture, búi to sát mắt tự mờ (`FILL_FADE`, đỡ tốn tốc độ tô của card tích hợp), sắp xếp xa -> gần trên CPU. Màu xám trắng nhạt (khói trắng tinh biến mất trên nền trắng).
  Đo trên máy này: M4 xả liên tục 86 búi trung bình 94-100 FPS (thấp nhất ~70), Glock 128 FPS. Cửa nhả vỏ M4 / Glock là số ƯỚC LƯỢNG (`SmokeData.ejection_port`).
  Tia lửa (hình ngôi sao + 2 mặt phẳng) đã bỏ; còn lại ánh lóe ngắn (đèn điểm ở nòng) chiếu súng, tay, đất.
- Đổi súng: chỉ clip NẠP mới thu hẹp vùng súng tự do (`Player.reloading`); cất / rút không còn kéo súng về tâm. FreeLook, FreeAim, Sway, HeadCam, Shake được GIỮ khi đổi súng (chỉ thay dữ liệu), nên súng mới ra đúng chỗ súng cũ đang chĩa và khung không giật.
- Bảng F1 thêm nhóm "Khói thuốc súng", "Ánh lóe đầu nòng", "Ống kính lắc", và các thanh `gun.head.gaze_*`.

## Rút súng / đổi súng không hiện sai tư thế (7/11/2026)
- Lỗi người dùng thấy: lúc mở game và lúc đổi súng, viewmodel hiện tư thế idle gốc của gói model (cao, giữa khung, chưa qua tư thế Bodycam) một lúc rồi mới nhảy về tư thế thiết kế. Nguyên nhân đo được:
  `Viewmodel.prewarm` (vẽ thử cho GPU nóng máy) đẩy 2 khung RA MÀN HÌNH khi súng chưa có sway nào (ở lúc mở game các khung này dài ~1 s vì biên dịch shader), rồi thêm một khung ở tư thế sẵn sàng
  trước khi clip rút súng bắt đầu. Ảnh chụp trước/sau nằm ở scratchpad phiên này, không lưu.
- Sửa: `Viewmodel.hide_until_draw()` (gọi trong `Game.__init__` khi `draw=True` và trong `_apply_gun`) ẩn nhánh `sway` (tia lửa / cửa nhả vỏ cũng treo ở đó); `on_event('start', ...)` gọi `reveal()` NGAY khung tạo tư thế đầu của clip rút súng.
  `prewarm` vẫn vẽ súng (tạm `show`) nhưng khi ống kính vẽ súng vào buffer riêng thì CỬA SỔ NGHỈ các khung đó (`win.set_active(False)`), nên không khung nào ra màn hình. Không có ống kính (`lens=False`, chỉ công cụ) thì vẫn vẽ lên cửa sổ như cũ.
  Nếu `start_draw()` trả False (đang bận) thì `Game` gọi `reveal()` để súng không bị ẩn mãi. Mặc định Viewmodel KHÔNG ẩn (công cụ / selftest `draw=False` thấy súng ngay).
- Đứng hình khi đổi súng: ĐÃ BỎ HẲN (6/11/2026, xem mục dưới).

## Đổi súng không đứng hình, bắn được khi súng đã đứng yên (6/11/2026)
- Nguyên nhân đo bằng cProfile: mỗi lần đổi, `_apply_gun` DỰNG LẠI mọi thứ của súng. Lần đầu sang Glock 1 694 ms (1 250 ms là `build_animation_skeleton` bằng Python trong `gltf_patch`, 150 ms giải nén texture),
  mỗi lần về M4 520 ms (400 ms `read_normal_maps` giải nén PNG + `quick_filter_from` lại từ glb), cộng ~100 ms âm thanh, ảnh lóe nòng vẽ từng điểm ảnh, 2 khung vẽ thử.
- Sửa: `GunKit` (app.py) giữ một bộ (dữ liệu súng, Viewmodel, Effects, GunAudio, Foley) cho MỖI khẩu. `create_game` gọi `preload_guns()` dựng sẵn khẩu kia lúc mở game (+~1,7 s mở game),
  khẩu không cầm thì `park()` (tắt display region, ẩn, tư thế sẵn sàng; Effects tắt lóe + thu tracer; Foley `resume()` khi lấy lại). Đổi súng giờ ~1 ms, không khung nào > 25 ms.
  Hệ quả: số chỉnh bằng F1 cho một khẩu được GIỮ khi đổi đi rồi đổi lại (trước đây mỗi lần đổi chép lại bản gốc từ `GUNS`).
- Clip rút súng bắt đầu NGAY trong khung clip cất súng xong (không còn khung trống mà `Handling` ở READY lúc súng mới chưa rút: trước đây bấm chuột trái ở khung đó thì Glock bắn khi súng còn ẩn, bấm phím đổi súng thì súng mới bị cất khi chưa rút).
  `request_gun` cũng bỏ qua khi súng chưa rút (`_draw_pending`).
- Bắn / ngắm được từ `Clip.settle` của clip rút súng (M4 khung 291 = 0,73 s, Glock 233 = 0,70 s; trước đây chờ hết clip 1,0 / 1,1 s). Đo bằng độ dời lớn nhất của khớp giữa hai khung:
  sau mốc đó < 0,5 cm/khung (chỉ tay ổn định lại). `Handling` phát ('ready', key, tail) thay cho 'done'; Viewmodel chạy tiếp phần đuôi (`_tail_left`), phát súng đầu tiên cắt ngang đuôi.
  Đổi mốc: sửa `settle=` trong `weapon_data.py` (bỏ `settle` thì quay về chờ hết clip).
- Kiểm: `tools\measure\swap_check.py` (đứng hình 0 ms, khung đầu hiện súng là clip rút), `tests/test_handling.py` (mốc 'ready').
- Kiểm: `tools\measure\swap_check.py` (mở game + 3 lần đổi súng; khung đầu tiên hiện súng trên màn hình phải chạy clip `draw`; trên mã cũ trượt cả 4 lần).

## Sửa lần 2 (7/11/2026, tối)
- Dải đen ở mép khi khung trượt: VẼ DƯ MÉP (`lens.overscan` 0,22). Thế giới và súng được vẽ với tan(nửa FOV) x 1,22 (`core/lens.overscan_fov`; `camera.fov` và FOV súng là FOV VẼ,
  `Player.view_fov` là FOV HIỆN), ống kính lấy phần giữa (`src /= lens_motion.w`). Độ trượt nén mềm tới 0,9 x overscan (`soft_limit`), nên chỉ còn viền bo tròn. Đổi lại ảnh mềm hơn ~20%.
  Cúi nhìn băng vì vậy trượt tối đa ~1/10 chiều cao (thay vì 1/8). Tỉ lệ tan giữa súng và thế giới giữ nguyên nên hướng đạn theo nòng không đổi.
- Ánh nhìn khi nạp: chuyển động theo cubic-bezier kiểu CSS (`core/easing.py`, skill `camera-easing-bezier`): cúi xuống `gaze_enter_ease`, liếc `gaze_glance_ease` (quá đà 4%), ngẩng `gaze_leave_ease`.
  Nhịp của ĐẦU, không phải mắt: liếc 0,3 s + 0,012 s/độ, dừng 0,6-0,85 s, bám tay chậm 0,8/s, ngưỡng liếc 4°; đo mô phỏng: liếc cách nhau ~1,1 s (2-3 chỗ mỗi lần nạp). Ngẩng lên 0,7 s, bắt đầu 0,42 s trước `Clip.settle`.
- Rung khi di chuyển: đi bộ -40% (`step_*`), chạy -30% (`sprint_*`, `jitter_angle/pos`), `jitter_walk` chỉnh để rung tay lúc đi cũng -40%.

## Nạp đạn cũng mở khoá ở mốc settle (7/11/2026)
Clip nạp còn chạy 0,5-0,75 s sau khi súng đã về chỗ và game khoá bắn / ngắm / đổi súng suốt đoạn đó (người dùng thấy ~1,5 s kể từ lúc băng đạn vào). Giờ `Handling` phát `ready` ở `Clip.settle` như clip rút súng; chi tiết, số đo và công cụ kiểm: `docs/notes/pool-hall.md` mục \"Nạp đạn: bắn / ngắm / đổi súng được từ lúc súng về chỗ\".
