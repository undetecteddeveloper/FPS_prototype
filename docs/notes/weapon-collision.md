<!-- Mở khi: đụng tới súng chĩa lên khi sát tường (High Ready), khoá bắn / ngắm sát tường, hoặc `core/weaponcol.py`. G14 (7/11/2026). -->

# Va chạm súng, "High Ready" (G14, 7/11/2026; kế hoạch + bản chốt: `docs/sessions/G14.md`)

Người dùng chốt: đứng quá sát tường thì nhân vật CHĨA SÚNG LÊN TRỜI (High Ready), càng sát tường càng ngóc cao; khoá BẮN và NGẮM khi đã nâng, NẠP ĐẠN vẫn được. Lý do: viewmodel vẽ riêng (xoá độ sâu) nên luôn đè lên thế giới; nòng M4 (mắt tới nòng ~0,78 m) thò qua thành khi úp mặt vào thành.

## Cách chạy (mỗi khung, `Game._update_wall`, ngay sau `player.tick()`)
- `core/weaponcol.py` (toán thuần, `tests/test_weaponcol.py`): `probe_distance` bắn 3 tia ngắn từ MẮT theo HƯỚNG NHÌN (giữa và ±`side_angle` 18°) vào các hộp va chạm (bỏ mặt nước), lấy khoảng cách gần nhất. Dùng hướng nhìn, KHÔNG dùng hướng nòng: súng ngóc lên thì tia theo nòng buông tường ra, súng lại hạ xuống, rồi nhấp nháy. Tầm súng `reach_of(gun)` = mắt → nòng của tư thế nghỉ (M4 0,78 m, Glock 0,60 m). `wall_target`: 0 khi tường xa hơn `clear_ratio` (1,12) × tầm, 1 khi gần hơn `full_ratio` (0,52) × tầm (thân dừng cách tường 0,30 m nên chạm tường là ngóc hết cỡ), tuyến tính ở giữa.
- `WallReady`: làm mượt (`in_time` 0,16 s lên, `out_time` 0,30 s xuống, không phụ thuộc FPS) và cờ `blocked` có độ trễ (`block_at` 0,30, `block_hysteresis` 0,10: cò không nhấp nháy ở ngưỡng).
- Tư thế: `SwayData.wall_pose` CỘNG vào `rest_pose`, trộn theo `smoothstep(wall_amount)` trong `Sway.update`; nó THAY tư thế ngắm và tư thế chạy (`ads` và `sprint` nhân (1 − wall)). BẪY: tư thế quay quanh MẮT (`hip_offset` là một phần vị trí mô hình bên trong node bị quay), nên ngóc 65° mà không dịch lại thì báng súng và tay bay khỏi đỉnh khung. Phần dịch được GIẢI để báng (điểm ngắm sau) về chỗ tay nghỉ, thấp hơn 3 cm và gần hơn 4 cm: M4 (0, −0,175, 0,043, 65°), Glock (0, −0,404, 0,173, 65°; hip_offset z 0,15 nên xa mắt hơn). `tests/test_weaponcol.py` giữ: nòng ngóc > 55°, báng trong 7 cm quanh chỗ nghỉ, nòng cao hơn báng.
- Khoá: `Player.wall_blocked` → `read_keys` bỏ nút ngắm (`ads` False, `ads_amount` tụt về 0 như khi nạp đạn); `Combat.wall_blocked` → `ready` False, lần bấm bị bỏ (không bắn bù khi lùi ra), `on_blocked('wall')` → dòng nhỏ "Quá sát tường" (`WallData.blocked_text`, 0,9 s). Nạp đạn không đọc cờ này. Dưới nước vẫn là `on_blocked('water')`.
- Đổi súng cạnh tường giữ độ ngóc (`Game._apply_gun` đổi `wall_ready.d` và tầm súng).
- F1: nhóm "Sát tường (súng ngóc lên)" trong tab Sway (tư thế + 8 số). Tia dò tốn 3-12 µs mỗi khung (xấu nhất 0,13 ms ở góc phòng).

## Kiểm
- `tests/test_weaponcol.py` (14 bài: tầm súng, đường cong, tia dò gồm tường chéo / góc / nước, thời gian không phụ thuộc FPS, độ trễ, tư thế cả hai súng, Sway, khoá cò / nút ngắm, nạp đạn không bị khoá).
- `tools\measure\pool_check.py [--gun glock]` (5 mục G14 bằng game thật: ép vào tường thì ngóc hết cỡ + khoá, cò bị từ chối + chữ, nút ngắm vô hiệu, nạp đạn chạy, lùi ra thì hạ và mở khoá).
- Ảnh: `shots\...` bằng kịch bản đứng cách tường 1,2 / 0,9 / 0,7 / 0,5 / 0,35 m rồi ép thật (không có công cụ riêng; xem `docs/sessions/G14.md`).

## Chưa làm / có thể chỉnh
- Chỉ dò theo hướng nhìn: súng lệch tâm do chuột (vùng tự do ±~10°) chạm tường chéo thì tia ±18° bắt được, nhưng không dò theo nòng thật.
- Súng chưa tự hạ khi nhìn xuống sàn sát chân (mắt luôn cách sàn 1,68 m nên chưa gặp).
- Nếu muốn ngóc cao hơn / thấp hơn: `wall_pose` pitch (F1), Glock nhìn thẳng hơn M4 vì ngắn.
