<!-- Mở khi: khi đụng tới nạp / rút súng, animation, tia lửa, tracer, shader súng. Trích nguyên văn từ CLAUDE.md cũ (đường dẫn đã cập nhật); số đo ghi trong đây là của lúc đó. -->

# Rút súng, nạp đạn, tia lửa, tracer, shader (G5)
- Logic nạp/rút súng thuần: `core/handling.py` (READY / DRAW / RELOAD), số liệu ở `weapon_data.ReloadData` + `Clip.swap`/`Clip.settle`. Clip chạy theo đồng hồ Panda (`actor.play` + nội suy khung `setBlend(frameBlend=True)`),
  logic nhận `time.dt` THẬT (không cắt 50 ms) nên hai bên khớp; `Handling.drain()` đưa sự kiện (start/swap/done/cancel) sang `Viewmodel.on_event`.
- Đo bằng `tools\measure\g5_reload_probe.py` (đừng đoán lại): băng mới vào chỗ ở khung **61** (Reload, 2,0 s) và **172** (Reload_Empty, 2,03 s); đạn đổi đúng lúc đó, huỷ trước mốc thì đạn y nguyên. Tổng 3,63 s / 3,77 s (`ReloadData.speed` nhân tốc độ).
  Một băng duy nhất (Mag1) rút ra rồi ấn lại; `Mag2` và viên đạn thứ hai không bao giờ tới gần súng trong clip nào (vẫn ẩn). Khung đầu của Reload_Empty có bolt khoá sau (BoltCatch 18 cm, Bolt 6 cm) nên đó chính là tư thế "băng cạn":
  `Viewmodel.animate` trộn 0,04 s sang khung 111 khi băng về 0 (bolt khoá ngay phát cuối), không cần clip riêng. Draw bắt đầu ở khung đầu tiên của game (không phải lúc dựng), 1,0 s, không bắn/ngắm/nạp được.
- Luật: băng cạn + bóp cò (hoặc R) -> Reload_Empty; hết sạch đạn thì không làm gì (HUD "HẾT ĐẠN"); R lúc chạy bị bỏ (chờ `sprint_amount` về 0); chạy nước rút cắt nạp (`ReloadData.sprint_cancels`); nạp luôn kéo súng ra khỏi ADS
  (`Player.ads_blocked`, vào lại ADS tự động khi xong nếu còn giữ chuột phải); cú bóp lúc đang nạp bị bỏ (khác sprint-to-fire: ở đó được nhớ).
- Huỷ nạp: clip đứng yên tại khung hiện tại rồi trượt về tư thế sẵn sàng 0,18 s bằng `enableBlend` + `setControlEffect` (hai AnimControl khác nhau: clip bị huỷ và `Draw` ở khung cuối). Huỷ Reload_Empty trước mốc thì tư thế sẵn sàng có bolt đóng
  rồi 0,04 s sau mới khoá lại (không dùng chung được một AnimControl cho cả hai).
- Clip nạp được dựng cho góc nhìn rộng: tay trái và băng đạn nằm dưới mép màn hình ở FOV súng 70 (kể cả lúc nghỉ). Khi nạp FOV súng mở 88 và súng nhích lên 4 cm (`ReloadData.view_fov/view_pose`, trộn 0,25 s). Phải TẮT XONG ở `Clip.settle`
  (88 / 206) chứ không phải hết clip: đoạn cuối clip chỉ là ngón tay xếp lại, để nguyên thì súng đứng cao thêm ~0,6 s sau khi nạp xong (lỗi đã gặp).
- **FPS lúc nạp (lỗi đã gặp)**: nội suy khung làm bộ xương đổi MỌI khung nên Panda skin lại 2 875 đỉnh bàn tay trên CPU mỗi khung (đo `animate_vertices`: 1,28 ms). Đo xen kẽ trung vị khung hình: cách cũ đứng yên 10,0 -> nạp 13,2 ms (-24% FPS);
  skin trên GPU 10,1 -> ~10,5 ms. Hiện `assets/shaders/viewmodel.vert` skin bằng `p3d_TransformTable` + `transform_weight/index` (mẫu từ panda3d-simplepbr) với cờ `ShaderAttrib.F_hardware_skinning`, đặt riêng cho mesh có cột `transform_blend`;
  mesh cứng của súng dùng biến thể không skin. Đừng bỏ shader này mà quay lại đường cố định.
- Tia lửa + tracer: `game/effects.py`, số liệu `FlashData`/`TracerData`, toán `core/fx.py`. Miệng nòng (0,0677, -0,0752, 0,7326) trong hệ camera lúc nghỉ (`GunData.muzzle`, đo bằng `g5_muzzle_align`).
  Tia lửa vẽ trong cảnh súng (ngôi sao + hai tấm dọc nòng, trộn cộng) kèm đèn điểm đưa vào shader súng; ngắm thì nhỏ còn 35%. Tracer bám viên đạn THẬT (cùng vị trí, độ rơi), cứ 3 viên một vệt, viên đầu của loạt luôn có,
  xuất phát từ miệng nòng rồi hội tụ về đường đạn từ mắt trong 18 m (`Tracer.offset`, `convergence`); hệ số `lens_ratio` bù chênh FOV thế giới/FOV súng để điểm xuất phát trùng miệng nòng trên màn hình (kiểm ở selftest < 4 px).
  Đạn bay xa dọc hướng nhìn thì vệt co lại thành chấm: thêm chấm sáng 20 px ở đầu vệt. Màu phải bão hoà (cam), trắng chìm vào mặt đường và bầu trời vì trộn cộng.
- BẪY Panda/Ursina: `CardMaker` dựng thẻ trong mặt phẳng **XY** (pháp tuyến +z) vì Ursina dùng hệ y-up, không phải XZ như tài liệu Panda. Đặt thẻ bằng `set_mat` tường minh (hàng 0 = ảnh trục ngang, hàng 1 = ảnh trục dọc, hàng 2 = pháp tuyến).
  Đầu vào shader riêng của vật thể Ursina (`camera_world_position`, `fog_color`... từ `unlit_with_fog_shader`) ĐÈ lên đầu vào đặt ở `render`: uniform của shader mình phải có tiền tố riêng (`look_`), không thì thấy giá trị 0.
  Uniform đổi mỗi khung (đèn tia lửa, vị trí camera) đưa bằng mảng `PTA_LVecBase3f` sửa tại chỗ; gọi lại `set_shader_input` mỗi khung làm đổi trạng thái vẽ của cả cây cảnh.
- (G5; từ G6 mặt trời/trời/sương ngoài trời đã THAY bằng phòng kín + đèn treo trần, xem mục G6) Shader thế giới `assets/shaders/world.*` (áp bằng `Entity.shader` trong `game/look.py`): đèn nửa cầu + mặt trời (pháp tuyến lấy từ đạo hàm vị trí nên không cần mesh có normal), nhiễu giá trị hai tỉ lệ trên mặt nằm ngang (mờ dần 40-160 m),
  sương mù exp 0,0032 hoà vào màu chân trời (0,75, 0,84, 0,87), lớp tối góc màn hình. Chi phí đo được ~0,2 ms/khung (trong nhiễu của máy). Số liệu ở `weapon_data.LookData`.
  KHÔNG dùng FXAA của Ursina (`camera.shader = fxaa_shader`): bầu trời thành xám phẳng khi có vùng vẽ súng riêng; MSAA vẫn cấm.
- Đạn chia bước <= 1/120 s khi dò va chạm (`MAX_BULLET_STEP`): trước đây một khung treo 40 ms làm điểm trúng lệch tới `g*dt^2/8` = 3 mm ở 10 m (g2_selftest bắt được).
- CHƯA GIẢI QUYẾT: phát bắn ĐẦU TIÊN của phiên có một khung ~40 ms (các phát sau 8-13 ms). Chỉ xảy ra khi tia lửa/tracer được cập nhật thật (tắt `Effects.update` thì hết). Đã thử: `prepare_scene`, vẽ thử nút vài khung lúc dựng
  (giảm khung thứ hai từ 25 xuống 10 ms), chạy thử đường mã, thay billboard bằng ma trận, PTA cho đèn, đóng băng bộ gom rác: không hết. Giờ chỉ còn một lần mỗi phiên.
- Đã đo ở G5 (vsync tắt, 1280x720, cả kịch bản g5_selftest): trung bình 85 FPS, 1% thấp nhất 59; bắn liên thanh có tia lửa + tracer không tụt đáng kể.

