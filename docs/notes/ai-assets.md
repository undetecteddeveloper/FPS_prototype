<!-- Mở khi: sinh tài nguyên AI (ảnh, video, nhạc, tiếng, model 3D), đụng tới credit / phong bì, Blender (sửa model, rigging, animation), học chủ đề mới thành skill, thư mục review. Chuyển nguyên văn từ docs/WORKFLOW.md (7/11/2026); số mục 6..6f giữ nguyên để các file khác còn tham chiếu. -->

# Tài nguyên AI, credit, Blender, skill, review

## 6. Tài nguyên AI
| Loại | Công cụ | Ghi chú |
|---|---|---|
| Ảnh / video | Higgsfield qua Composio, bộ **`higgsfield_mcp`** (đăng nhập bằng tài khoản; Nano Banana Pro = `nano_banana_pro`, Seedance = `seedance_2_5`). KHÔNG dùng bộ `higgsfield` cũ (chỉ có Soul, khoá API đã hỏng, báo 401) | Ảnh 1k chỉ 2 credit (đo 6/11/2026). Kết quả trả về dạng job: gọi `HIGGSFIELD_MCP_JOB_STATUS` (sync) lấy URL rồi tải về. 3D AI Studio có Qwen 2.1 / Nano 2.1 rẻ cho bản nháp |
| Nhạc | ElevenLabs `music_v1` qua Composio | |
| Tiếng hiệu ứng | ElevenLabs qua Composio `ELEVENLABS_GENERATE_SOUND_EFFECTS` với `model_id: eleven_text_to_sound_v3` (công cụ cho chọn v2 hoặc v3; theo yêu cầu người dùng luôn dùng V3). Trả về URL tạm 1 giờ: tải về ngay | Lệnh không trả số credit đã tốn |
| Giọng nói | ElevenLabs V3 | Cần xác minh ID chính xác trước khi ghi cứng |
| Model / texture 3D | 3D AI Studio (nối trực tiếp, không qua Composio): Prism 3.1 mặc định, Meshy 7.1 khi cần texture 4K/8K, P2 khi cần quad | Danh sách không có Tripo. CẢNH BÁO: Prism 3.1 xuất ~1,4 triệu tam giác (41,7 MB) cho một khẩu súng lục: phải hạ số mặt (`low_poly_model` 15-35 credit, hoặc dùng P2 game-ready) trước khi đưa vào game |
- Phân loại: tài nguyên CHỦ CHỐT (súng, tiếng súng, tiếng nạp, tay) đi thẳng công cụ chính; ĐỒ PHỤ (đạo cụ, nền, tiếng nền, thử nghiệm) đi đường rẻ.
- Cổng duyệt: người dùng duyệt TỪNG CÁI, và CHƯA xem/nghe thì CHƯA được duyệt. Mỗi mục kèm prompt + công cụ + chi phí credit. Lô lớn gom thành một bảng để duyệt một lượt.
- Xem/nghe thử (nghiên cứu 6/11/2026; chỉ phiên chạy trong CLAUDE DESKTOP mới thấy thẻ xem, phiên VS Code chưa kiểm):
  - 3D AI Studio: ĐÃ XÁC NHẬN theo mô tả công cụ: ảnh và âm thanh tự hiện thẻ trong chat; model 3D gọi `show_generation` sau khi `get_generation` báo xong (khung xoay 3D, một lần cho mỗi bản).
  - ElevenLabs (qua Composio) và Higgsfield (qua Composio): CHƯA XÁC NHẬN. Tài liệu chính thức không nói có phát/xem ngay trong chat (README ElevenLabs chỉ nói chế độ `resources` trả dữ liệu base64, không nói Desktop có phát). Cách chắc ăn: ở lần sinh đầu tiên mỗi nền tảng, thử MỘT bản rẻ nhất trong Claude Desktop và ghi kết quả vào đây.
  - Phương án dự phòng khi không hiện: agent dựng trang xem thử (Artifact riêng tư, hoặc HTML mở trên máy: ảnh, nút nghe, video) rồi đưa link; model 3D xem bằng thẻ của 3D AI Studio hoặc ảnh chụp xoay.
  - Việc phiên sinh tài nguyên (cần xem/nghe) nên mở ở Claude Desktop; phiên viết mã mở ở VS Code. Hai bên trao đổi qua file trong `assets/` và bản kế hoạch phiên.

## 6b. Ngân sách credit (số dư người dùng khai 6/11/2026; chia theo phong bì, ĐỀ XUẤT, chỉnh được)
| Nền tảng | Còn | Phong bì |
|---|---|---|
| 3D AI Studio | 864 | Chủ chốt (vũ khí, nhân vật/bot) 40% = 345 · Đạo cụ / cảnh 30% = 260 · Nháp, thử prompt 15% = 130 · Làm lại, dự phòng 15% = 129 |
| Higgsfield | 860 | Ảnh chủ chốt (Nano Banana Pro) 45% = 387 · Video Seedance 35% = 301 · Dự phòng 20% = 172 |
| ElevenLabs | 8144 | Tiếng hiệu ứng 50% = 4072 · Nhạc 30% = 2443 · Giọng nói 10% = 814 · Dự phòng 10% = 815 |
- Giá tham khảo 3D AI Studio: Prism 3.1 35 credit/model (+ texture cao hơn), ảnh Qwen 2.1 từ 1-2 credit, Nano Banana 2.1 từ 6 credit. Chưa biết giá Seedance / ElevenLabs theo credit: GHI giá thật ngay sau lần sinh đầu của mỗi loại.
- Sổ chi tiêu `docs/credits.md`: mỗi lần sinh một dòng (ngày, nền tảng, phong bì, mục đích, credit, số dư còn). Khoá API ElevenLabs không đọc được số dư: người dùng khai lại số dư đầu mỗi phiên sinh tài nguyên.
- Hết phong bì thì DỪNG và hỏi (không tự lấy từ phong bì khác). Việc mới không thuộc phong bì nào: hỏi trước khi tạo phong bì mới. Mỗi lô tốn credit nói trước tổng ước tính.

## 6c. Comment tiếng Anh (người dùng chốt 6/11/2026)
- Mọi comment và docstring trong mã (`fps/`, `tests/`, `tools/`, `assets/shaders`) viết bằng TIẾNG ANH. Giữ nguyên TIẾNG VIỆT: chữ hiển thị cho người (HUD, bảng F1 và `param_meta`, tên mục của selftest, thông báo lỗi cho người dùng) và mọi file `.md` / `CREDITS.txt`.
- Đợt dịch toàn bộ cho mã hiện có (ĐÃ LÀM 6/11/2026: 106 file .py + 8 file GLSL, kiểm đạt, còn 0 dòng comment tiếng Việt): subagent model rẻ dịch theo nhóm file không chồng nhau; kiểm bằng cách so cây AST đã bỏ docstring trước/sau (phải trùng) cộng pytest; mã GLSL chỉ đổi phần comment. Các số đo nằm trong comment phải giữ nguyên chữ số và đơn vị.
- Truy nguyên: mỗi tài nguyên giữ prompt, công cụ, model, seed trong `assets/source/` (hoặc `sounds/source/`) để làm lại được; ghi nguồn/giấy phép vào `CREDITS.txt`.

## 6d. Blender: sửa model + rigging + animation (người dùng chốt 6/11/2026: vũ khí trước, nhân vật/bot sau)
- Kết nối: máy chủ `blender-lab` (Claude Code, stdio) + extension Blender Lab "MCP" 1.0.0 (Blender 5.1, `localhost:9876`); mã trung gian ở `C:\Users\ASUS\tools\blender_mcp`, đăng ký bằng `claude mcp add blender-lab -- uv --directory C:/Users/ASUS/tools/blender_mcp/mcp run blender-mcp`. CHƯA gọi thử công cụ nào (cần phiên mới). Chỉ cho các công cụ ĐỌC lúc đầu; công cụ chạy mã Python thực thi trong Blender không có rào chắn thật: dùng cảnh thử, từng lần hỏi người dùng.
- Đường đi của một vũ khí: 3D AI Studio (glb thô, ~1,4 triệu tam giác) -> Blender: hạ số mặt, kiểm UV/texture, đặt đúng quy ước mô hình -> rig bộ phận động -> animation -> xuất glb -> nạp bằng `gltf_patch` và thử trong game -> người dùng duyệt.
- Chuẩn mục tiêu (đo từ M4 6/11/2026): tổng 14.814 tam giác gồm cả tay (4.480 tam giác có skin), 56 xương, 4 vật liệu, 11,5 MB, 5 animation. Súng lục: đặt trần ~10.000 tam giác (Intel UHD 620 là máy chuẩn), điều chỉnh lại sau khi đo FPS thật.
- Quy ước cần khớp (xem `docs/notes/tools.md` và mục "Nạp M4" của `CLAUDE.md`): mô hình tính bằng cm, quay mặt về −Z; bộ phận cứng (slide, bolt, băng, cò) đi theo nút xương cha, KHÔNG skin; chỉ phần mềm (tay) mới skin trên GPU. `panda3d-gltf` nạp sai theo 6 cách: file mới phải qua `tests/test_gltf_load.py`-kiểu kiểm.
- Xuất hoạt ảnh: MỘT file glb chứa mọi clip (bắn, nạp, nạp cạn, rút, ...) khớp cách M4 chạy (`Clip(tên, từ khung, đến khung)` ở `weapon_data.py`, 30 fps). Cách ghi cụ thể (một timeline nối tiếp hay nhiều animation có tên) kiểm khi thử với `gltf_patch`.
- Kiểm kết quả: ẢNH CHỤP cho người dùng xem (turntable vài góc + lưới các khung chính của từng clip, lưu ở `assets/review/<tên>/`), người dùng duyệt từng cái. Kèm các số tối thiểu để người xem biết: số tam giác, số xương, khoảng khung của từng clip.

## 6e. Học trước khi làm, lưu thành skill (người dùng chốt 6/11/2026)
- Với MỌI việc, trước khi làm agent phải kiểm xem đã có skill kiến thức cho chủ đề đó chưa (`.claude/skills/<chủ-đề>/SKILL.md`, tự nạp theo mô tả). CHƯA có hoặc thiếu phần cần dùng: HỌC SÂU bằng WebSearch / đọc tài liệu chính thức, rồi LƯU trước khi làm việc. Đã đủ: dùng, chỉ học thêm phần thiếu. (Học một lần, tra sổ; không học lại cả chủ đề mỗi việc.)
- Ví dụ chủ đề cho model: mesh và topology, UV và texture (PBR), retopo / hạ số mặt, rigging cơ khí (xương cho bộ phận cứng), skinning, animation (khung chính, timing, đường cong), xuất glTF và quy ước Panda3D/Ursina. Mỗi chủ đề một skill riêng, tên ngắn kiểu `blender-rigging-mechanical`.
- Người đọc là Claude: viết bằng TIẾNG ANH, cô đọng, không cần bản tóm tắt tiếng Việt. Kích thước do agent tự quyết theo độ quan trọng và độ phức tạp của chủ đề: `SKILL.md` giữ gọn (mô tả đủ rõ để tự nạp + quy tắc cốt lõi + bẫy), chi tiết dài đẩy sang file kèm trong `references/` chỉ mở khi cần. Chủ đề lớn thì tách nhiều skill nhỏ.
- Nhãn độ tin cậy trên MỌI ý: nguồn (URL), ngày đọc, mức tin cậy (cao / vừa / thấp), trạng thái `unverified` hoặc `verified-in-project` (kèm tên thử nghiệm đã làm). Ý quan trọng phải được thử bằng một thí nghiệm nhỏ trong dự án rồi nâng lên `verified-in-project`. Mâu thuẫn giữa nguồn thì ghi cả hai, không chọn im lặng.
- Gắn phiên bản công cụ vào ghi chú (vd. Blender 5.1, extension 1.0.0) để biết khi nào cần xem lại; không đặt hạn cố định.
- Khung giao thức nằm ở skill `learn-first` (`.claude/skills/learn-first/SKILL.md`). Học xong phải LƯU rồi mới làm việc; báo cuối phiên nêu "đã học / đã cập nhật skill: ...".

## 6f. Thư mục review theo từng object (người dùng chốt 6/11/2026)
- MỖI object mới (súng, nhân vật, bia, đạo cụ...) có MỘT thư mục riêng `assets/review/<object>/` để người dùng xem/nghe mọi tài nguyên của object đó ở một chỗ. Tạo thư mục NGAY khi bắt đầu object, trước khi sinh tài nguyên đầu tiên.
- Cấu trúc con cố định: `concept/` (ảnh), `model/` (glb thô + glb đã hạ mặt), `animation/` (ảnh chụp turntable, lưới khung chính từng clip, video/gif nếu có), `audio/` (mọi tiếng của object, kể cả bản bị loại), thêm `README.md` ngắn: danh sách từng file, nguồn, trạng thái duyệt (chờ / duyệt / loại), số liệu (tam giác, xương, khung).
- Mọi tài nguyên sinh ra (AI, Blender, âm) lưu VÀO thư mục này trước; chỉ bản đã duyệt mới được chép sang `assets/guns/`, `assets/sounds/`... Đường dẫn trong `docs/credits.md` trỏ vào thư mục review.
- `assets/review/` bị gitignore (nặng): README là bản ghi, không có trong git.
