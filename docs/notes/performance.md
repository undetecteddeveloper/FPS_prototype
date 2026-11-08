<!-- Mở khi: đụng tới hiệu năng, mức đồ hoạ Thấp, shader lite / bản biên dịch thay thế, độ phân giải 3D, công cụ đo GPU. G13 (7/11/2026). -->

# Hiệu năng cho máy yếu (G13, 7/11/2026)

Mục tiêu người dùng chốt: ở mức đồ hoạ **Thấp**, laptop văn phòng cũ (Intel UHD 620, 8 GB, màn 1080p) chạy trung bình ~60 FPS, 1% khung chậm nhất ≥ 50 FPS. Chỉ đổi cách VẼ, không đổi logic game. Vừa / Cao giữ nguyên hình. Skill kỹ thuật: `.claude/skills/gpu-perf-intel/SKILL.md`.

## Cách đo (không có máy yếu thật)
- `tools\measure\weak_pc.py [--gun m4|glock] [--level 0] [--passes]`: chạy `g8_perf.py` hai lượt. Lượt GPU ở cỡ màn hình (1920×1080 không viền, vsync tắt) đo ms GPU bằng bộ đếm thời gian OpenGL; lượt CPU ở cửa sổ 640×360 (GPU rảnh nên trình điều khiển không bắt CPU chờ). Máy yếu ước = max(GPU × 4, CPU × 2). ĐẠT khi trung bình ≥ 60 và 1% thấp ≥ 50 ở mọi cảnh.
  ×4 là thận trọng: Iris Xe 96 EU nhanh hơn UHD 620 khoảng 2,5–3,5 lần (Time Spy 1282 / 361, G3D 2593 / 1040).
- `tools\measure\gpu_timer.py`: bọc từng vùng vẽ bằng `glQueryCounter(GL_TIMESTAMP)` (ctypes, không cần PyOpenGL). `g8_perf.py --weak --passes` in ms của từng lượt vẽ (`buffer#vùng:camera`).
- So A/B trong CÙNG một tiến trình (đổi qua lại mỗi 2 s), vì số tuyệt đối trôi theo nhiệt độ ±20%.
- Bẫy đo: vsync bật thì CPU / GPU tự hạ xung (ms phồng 2–3 lần); vsync tắt ở cửa sổ lớn thì ~5% khung bị Windows giữ +10,5 ms (công cụ tự bỏ và đếm); CPU đo ở 1080p bị lẫn thời gian chờ GPU.
- Kiểm "Vừa / Cao không đổi hình": vẽ cùng một khung bằng shader mới rồi bằng shader của `HEAD` (cùng trạng thái, không chạy cập nhật giữa hai lần), so từng điểm ảnh. Kết quả G13: ≤ 0,03% điểm ảnh lệch quá 3/255, tối đa 7/255 (viền lỗ cửa sổ). Ảnh chụp ở hai lần chạy khác nhau KHÔNG so được (đầu / độ phóng dưới nước khác thời điểm).

## Số đo (mức Thấp, 1920×1080, GPU ms trên máy này → máy yếu ước)
| Cảnh | Trước G13 | Sau G13, Glock | Sau G13, M4 |
|---|---|---|---|
| đứng yên | 9,5 ms → ~26 FPS | 3,4 ms → ~73 | 3,5 ms → ~71 |
| bắn liên tục | 10,0 ms → ~25 | 3,7 ms → ~67 | 4,5 ms → **~56**, 1% thấp 51 |
| dưới nước | 10,1 ms → ~25 | 3,7 ms → ~68 | 3,8 ms → ~66 |
| nhìn lên mặt nước | 9,5 ms → ~26 | 3,4 ms → ~75 | 3,4 ms → ~73 |
| nửa chìm | 7,2 ms → ~35 | 4,1 ms → ~61 | 4,1 ms → ~61 |
CPU 1,0–1,6 ms (×2 vẫn dư). Duy nhất M4 bắn liên tục dưới 60 (khói dày); 1% thấp mọi cảnh ≥ 50.

## Đã làm (thứ tự theo lợi)
1. Tắt `camera.overlay` của Ursina: tấm phủ trong suốt toàn màn hình, trộn alpha mỗi khung, không ai dùng (1,6–3,3 ms; mọi mức).
2. Độ phân giải 3D (F2 "Độ phân giải 3D" 100 / 75 / 50%, Thấp = 75%): cả buffer cảnh và lượt ống kính chạy ở 75%, rồi `blit.frag` phóng ra cửa sổ; chữ và bảng F1 / F2 vẫn nét. `underwater.glsl` dùng cỡ buffer cho `gl_FragCoord`; chói sáng đọc mip lệch `log2(tỉ lệ)` để giữ bán kính trên màn hình.
3. Bản biên dịch thay thế (mỗi bản biên dịch + VẼ THỬ lúc khởi động trong `Game.warm_shader_builds`, vì trình điều khiển Intel chỉ biên dịch thật ở lần vẽ đầu: không có thì 50–150 ms khựng lần đầu xuống nước):
   - `POOL_LITE` cho nước / lòng hồ / phòng khi các cờ F2 của nút đó bằng mức Thấp (`core/graphics.py` `lite_water/lite_basin/lite_room`): tính năng tắt thành hằng `false`, mã chết bị bỏ (Intel: nhánh không chạy vẫn tốn thanh ghi).
   - Nước lite còn `VIEW_DRY` (không điểm nào ướt) / `VIEW_UNDER` (cả khung ướt, mắt dưới mặt nước), `game/underwater.py` chọn mỗi khung: bỏ nhánh dò tia lòng hồ của khung tách đôi (−0,54 ms nhìn lên).
   - Ống kính `LENS_DRY` khi không có vệt lằn nước trong tầm (`core/underwater.py band_visible`), dùng ở mọi mức (cùng hình). (Màng / giọt ống kính ướt đã xoá 8/11/2026.)
4. Cùng hình, mọi mức: vòng gợn đạn chỉ chạy qua số gợn còn sống (xếp lên đầu mảng); vòng giọt ống kính theo số giọt; `sun_visible` loại sớm theo từng cửa sổ (đúng y hệt; −0,5 ms ở lòng hồ); bầu trời trong phòng hồ chỉ là các tấm sau lỗ cửa sổ (`sky_window.vert`), vẽ sau vật đặc; khói tính xoay + ánh sáng ở vertex shader.
5. Chỉ mức Thấp (đổi hình nhẹ): "Dưới nước: Đơn giản" thì gương phản xạ toàn phần ngoài cửa sổ Snell là màu đáy hồ phủ sương theo quãng đường (mất vân gạch phản chiếu; −3,6 ms ở 75%); F2 "Khói súng: Đơn giản" (Thấp): tô theo góc tấm + vẽ một nửa số đám (chọn theo hạt giống, đậm hơn để giữ mật độ; khói hơi mỏng hơn).

## Cố ý không làm / còn mở
- Độ phân giải tự động theo FPS (người dùng chọn cố định 75%). Shader súng bản lite (đo chỉ −0,02 ms). Mipmap chói sáng tự dựng (−0,1 ms).
- M4 bắn liên tục ở mức Thấp ước ~56 FPS (1% thấp 51) với hệ số ×4; với hệ số 3,5 (theo benchmark) là ~64. Muốn hơn nữa: khói vẽ ở nửa độ phân giải (lượt riêng) hoặc giảm `SMOKE_SIMPLE_KEEP`.
- Chưa thử trên máy UHD 620 thật.
