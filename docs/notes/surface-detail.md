<!-- Mở khi: đụng tới lỗ đạn, texture gạch sàn / tường / đáy hồ, bản đồ chiều cao + pháp tuyến, đổ chiều thị sai, hàng F2 "Chi tiết bề mặt", công cụ dựng texture bằng numpy. -->

# Chi tiết bề mặt: lỗ đạn, gạch có độ sâu (8/11/2026)

Người dùng chọn: texture dựng bằng NUMPY (5 ảnh AI Higgsfield đã bị loại và xoá, `docs/credits.md`), có đổ chiều thị sai (lõm thật), mức F2 chọn được.

## Công cụ
- `tools/build/surface_textures.py` (hàm dựng, numpy) + `tools/build/make_surface_textures.py` (ghi PNG vào `assets/textures/`, `--only holes`, `--preview DIR`). Game KHÔNG import numpy: PNG dựng sẵn được commit.
- Mỗi texture là một CẶP: ảnh màu (RGBA) + ảnh "relief" (RGB: R = chiều cao, 255 = mặt phẳng, 0 = đáy sâu nhất; G, B = pháp tuyến x, y). Cùng hạt giống thì cùng ảnh.
- Đổi hình dạng lỗ / độ sâu thì chạy lại công cụ; `HOLE_DEPTH` (công cụ) và `DEPTH` (`game/decals.py`) PHẢI bằng nhau (độ dốc pháp tuyến tính theo nó).

## Lỗ đạn (`core/holes.py`, `game/decals.py`, `assets/shaders/decal.*`)
- Atlas 2 × 2 (`bullet_hole_color.png` + `bullet_hole_relief.png`, 512 × 512): bốn lỗ khác nhau (miệng vỡ men lởm chởm, lòng xi măng, lỗ khoan tối, vết nứt toả tia + nứt vòng, mảnh men vỡ, một lỗ có mảnh men bong lệch về một bên). Mỗi viên chọn ngẫu nhiên một ô và xoay ngẫu nhiên trong mặt phẳng tường (xoay đỉnh quad, uv giữ nguyên để đổ chiều thị sai không rò sang ô bên cạnh).
- SỐNG 1,5 s (`FeedbackParams.hole_life`), mờ dần trong 0,4 s cuối (`hole_fade`), rồi quad bị thu về một điểm và, khi không còn lỗ nào, cả lưới bị ẩn (không vẽ gì). Vòng slot `HoleRing` (`max_holes` 64: M4 750 phát/phút = 12,5 lỗ/s, tối đa ~19 lỗ cùng sống). Tuổi tính theo thời gian thật của khung (`real_dt`), không phụ thuộc FPS; đồng hồ gửi shader lấy dư 4096 s để float32 không mất độ chính xác.
- `decals.count` = số lỗ ĐANG sống; `decals.added` = số lỗ đã tạo từ đầu (bộ kiểm đếm bằng cái này).
- Cỡ cả vết `hole_base_size` 0,28 m (miệng ~8 cm, men vỡ ~13 cm, nứt tới ~25 cm; bản đầu 0,12 m thì vết nứt không thấy từ 3 m).
- Ánh sáng: lỗ lấy ĐÚNG ánh sáng nướng của mặt tường nó nằm trên (`PoolHall.lightmap_at` -> `poolmap.face_at` + `lightmap_uv`, ghi vào cột đỉnh `lightmap`; bản dùng ánh nắng không bóng của `world.frag` làm miệng lỗ sáng chói giữa tường đang trong bóng). Bản đồ phẳng (không có lightmap) dùng công thức nắng + ánh nền như cũ.
- Mức F2 "Chi tiết bề mặt" (`GraphicsLevel.surface`; Thấp = Phẳng, Vừa, Cao): 0 chỉ ảnh màu; 1 pháp tuyến + tối ở lòng hố + đèn chính cố định từ trên (ánh sáng nướng không có hướng, nên cần một hướng giả để thấy khối) + đèn loé nòng; 2 thêm đổ chiều thị sai 12 bước. Chỉ đổi uniform, không biên dịch lại.
- Shader được vẽ thử một lần lúc khởi động (`HoleDecals.warm`, một lỗ vô hình trước camera) để lần bắn đầu không khựng 50-150 ms. Thiếu file PNG thì in cảnh báo và dùng lỗ tròn tạm (không dừng game).
- Kiểm: `tests/test_holes.py` (vòng đời, mờ dần, đồng hồ quay vòng, `face_at`, hàng F2), `pool_check.py` ("lỗ đạn sống 1,5 s rồi mất, lưới bị ẩn").

## Gạch sàn, tường, đáy và thành hồ (`room.frag`, `basin_common.glsl`, `assets/textures/tile_*`)
- Hai texture lặp lại, dựng bởi `surface_textures.tile_texture`: `tile_floor_*` = 2 × 2 gạch 30 cm (men MỜ, hạt chống trượt thưa, mép vát, mạch 3,5% bề rộng gạch), `tile_wall_*` = 4 × 4 gạch mosaic 10 cm (men BÓNG, rạn men mảnh, lỗ kim, mạch 5%). Mỗi viên lát hơi lệch (pháp tuyến khác viên bên cạnh), màu khác nhau; lòng mạch là vữa sần, tối dần sát mép gạch. Ảnh màu là HỆ SỐ nhân với màu gạch của từng hộp (`Box.albedo`), nên màu phòng vẫn do `MapData` quyết; PNG lưu `hệ số / 1,25` (8 bit không chứa giá trị > 1; shader nhân lại `TILE_GAIN`). Độ sáng trung bình của hai texture 0,943 / 0,915, bản công thức cũ 0,914: phòng không sáng / tối hơn.
- Đặt bằng toạ độ mét (`metric` / (cỡ gạch × số gạch trong texture)), mép ô trùng bội số của cỡ gạch nên mạch thẳng hàng qua các mặt kề nhau. Sàn dùng `tile_floor` khi cỡ gạch > 0,2 m, còn lại (tường, trần, cột) dùng `tile_wall`. Tay vịn (`tile = 0`) không đụng tới. Thêm một chút đậm nhạt riêng từng ô bằng hash như bản cũ (texture lặp mỗi 2 / 4 viên).
- Mức F2 "Chi tiết bề mặt": Phẳng = chỉ ảnh màu; Vừa = + pháp tuyến (đèn chính giả từ trên vì ánh sáng nướng không có hướng, đèn loé nòng, gương sàn ướt vỡ theo mạch); Cao = + đổ chiều thị sai 8 bước chỉ trong ~11 m và mờ dần (mạch xa chỉ rộng vài pixel). Độ sâu mạch `LookData.tile_depth_floor` 6 mm, `tile_depth_wall` 3 mm, `tile_bump` (F1 nhóm "Gạch: độ sâu và gồ ghề"). Pháp tuyến dựng theo hai độ sâu gốc đó (`TILE_DEPTH_*` trong công cụ); đổi độ sâu trong F1 thì chỉ đổi đổ chiều thị sai, độ dốc pháp tuyến đổi bằng `tile_bump`.
- Lòng hồ (đáy, bậc, dốc, thành dưới nước): dùng chính `tile_wall` ở cỡ `water.basin_tile` 0,15 m, nhân màu xanh hồ bơi `basin_color`, có pháp tuyến cho ánh nắng khúc xạ + vệt sáng (mạch bắt sáng khác mặt gạch) từ mức Vừa; KHÔNG có đổ chiều thị sai (lòng hồ phần lớn được nhìn qua mặt nước, và `shade_basin` không biết hướng nhìn). Nên nói thật: độ sâu thị sai chỉ có ở sàn bờ, tường, trần và lỗ đạn.
- Mức Thấp biên dịch bản `POOL_LITE` KHÔNG có code relief (`lite_room`, `lite_basin`, `lite_water` đòi thêm `surface == 0`); mọi mức khác dùng bản đầy đủ, chuyển mức chỉ đổi uniform `look_surface`.
- Ảnh phản chiếu phòng chụp sẵn bị chụp lại một lần (`REFLECT_VERSION` 2) vì căn phòng nay trông khác.
- Đo (`g8_perf.py --gun m4`, mức Cao, 1366×768, cắm sạc): 179–267 FPS trung bình ở 9 tình huống, ĐẠT cả 9. Đo riêng 1280×720 không giới hạn FPS: mức Cao thêm ~1–2 ms so với Phẳng khi nhìn sát sàn / tường.
- Thiếu file `tile_*.png`: in cảnh báo, gạch trơn không có mạch (game vẫn chạy).
