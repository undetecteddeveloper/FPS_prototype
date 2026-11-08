<!-- Mở khi: khi đụng tới giật, độ tản, tâm ngắm, kick. Trích nguyên văn từ CLAUDE.md cũ (đường dẫn đã cập nhật); số đo ghi trong đây là của lúc đó. -->

# Recoil, độ tản, kick súng (G3)
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


## Số đã chốt từ bảng F1 (8/11/2026, chỉ M4; Glock giữ số cũ)
- Người dùng chỉnh trên F1 khi cầm M4, chốt bằng `tools\build\bake_params.py --apply` (bản cũ của `user_params.json`: `backups\user_params.baked.20261108-0543.json`).
- Độ tản (độ, nửa góc nón): đứng 1,00, đi 2,20, nhảy / rơi 5,05, hệ số ngồi 0,80, ngắm đứng 0,10, ngắm đi 0,25 (trước: mọi trạng thái 0,03). Không bloom.
- Đẩy lùi: `back_peak` -0,040 m (trước -0,030), `back_ads_scale` 1,00 (ngắm = bắn hông; trước 1,15).
- Đầu khi nạp (`HeadCamData`): `body_omega` 8,0, liếc súng ngẩng sớm 0,70 s / ngẩng trong 1,00 s, nhìn tay 0,85, thời gian liếc 0,40 s, mỗi lần một khác 0 (nạp lần nào cũng giống nhau). Súng lúc nạp: `reload.view_pose` lên 0 (trước 0,105).
- Tầm nhìn bắn hông `player.fov` 90 (trước 96), người dùng chọn.
- BẪY: `bake_params.py` ghi vào mặc định của LỚP (`AccuracyData`, `GunKickData`, `HeadCamData`, `ReloadData`), mà Glock dùng chung các lớp đó. Lần chốt này phải ghim số cũ vào `GLOCK = GunData(...)` bằng tay.
- Bảng F1 THEO TỪNG SÚNG (8/11/2026): thanh `gun.*` là của súng đang cầm, mặc định / dấu "đã đổi" / vạch mặc định theo súng đó, "Mặc định súng này" chỉ đặt lại súng đang cầm; `user_params.json` v2 = `{"values": {chung}, "guns": {"m4": {...}, "glock": {...}}}` (file v1: số `gun.*` thuộc M4). `bake_params.py` chốt M4 vào mặc định của lớp, IN số của Glock để sửa tay (người dùng chọn), và tự khôi phục + báo nếu lần chốt M4 làm đổi ngầm Glock. Mã: `fps/core/params.py` (`default_of`, `register_gun`, `set_gun`), `tests/test_params_per_gun.py`.
