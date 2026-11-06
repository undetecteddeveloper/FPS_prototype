<!-- Mở khi: khi đụng tới đạn, nhịp bắn, bia, lỗ đạn, UiText. Trích nguyên văn từ CLAUDE.md cũ (đường dẫn đã cập nhật); số đo ghi trong đây là của lúc đó. -->

# Bắn, đạn, bia, chữ (G2)
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

