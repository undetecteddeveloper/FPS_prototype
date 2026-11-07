# Workflow dự án (chốt 6/11/2026)

Viết cho: người dùng và các agent mở phiên sau. Luật kỹ thuật của mã nằm ở `CLAUDE.md`; file này chỉ nói CÁCH LÀM VIỆC.

## 1. Năm nhóm nguyên tắc

| Nhóm | Luật | Cách kiểm |
|---|---|---|
| Ra lệnh | Người dùng prompt ngắn; agent hỏi đáp bằng AskUserQuestion (hai lớp: định hướng + kỹ thuật, có ví dụ đời thường, đáp án ngang sức) theo CỠ VIỆC, xem mục 1b | Mỗi phiên có bản chốt câu trả lời ở đầu `docs/sessions/Gx.md` |
| Mục tiêu | Mỗi phiên có 3-5 mục tiêu ĐO ĐƯỢC (selftest, pytest, FPS), viết trước khi code | Mục tiêu nào không có cách đo thì chưa được bắt đầu |
| Chọn việc | 80/20: mỗi phiên ghi rõ "làm" và "cố ý KHÔNG làm"; việc lòi thêm giữa chừng đưa vào danh sách chờ, không làm lẫn | Phần "không làm" của bản kế hoạch |
| Mã | Tìm trước khi viết: grep `fps/core` + `fps/game` xem đã có chưa; toán mới vào `fps/core` (không import ursina); mọi số vào `weapon_data.py` | Báo cáo cuối phiên nêu "đã tái dùng: ..." |
| Cảm giác chơi | Agent chỉ dựng bảng chỉnh (F1) + selftest; NGƯỜI chơi và chỉnh; xong thì chốt vào mặc định | Mục 4 |

## 1b. Mức hỏi theo cỡ việc (người dùng chốt 6/11/2026; luật của dự án này, thắng luật chung "tự quyết kỹ thuật")
- Agent ghi một dòng "Cỡ: nhỏ / lớn, vì ..." ở đầu câu trả lời đầu tiên để người dùng sửa nếu xếp sai.
- NHỎ (sửa một số, một lỗi, một chú thích; trong một file; người chơi không thấy hành vi đổi): hỏi tối đa MỘT vòng ngắn (1-2 câu), hoặc làm luôn rồi báo nếu yêu cầu đã rõ hoàn toàn.
- LỚN (tính năng, phiên mới, tài nguyên mới, đụng từ 2 module trở lên, mọi thứ đổi cảm giác chơi, mọi việc tốn credit): LUÔN đủ hai vòng. Vòng 1 hỏi về Ý TƯỞNG (muốn cảm giác gì, giống ví dụ nào, ai chơi, đâu là thành công). Vòng 2 hỏi kỹ thuật.
  Hỏi đến khi không còn giả định lớn nào chưa nói ra; không hỏi lại cái đã có trong tài liệu.
- Mỗi vòng tối đa 4 câu. Chữ phải đơn giản, mỗi lựa chọn có một ví dụ đời thường, hậu quả nói bằng lời thường.

## 2. Một phiên (Gx) đi qua 7 bước
1. Hỏi đáp (vòng định hướng rồi vòng kỹ thuật, tối đa 4 câu mỗi vòng, đáp án ngang sức).
1b. Học (mục 6e): chủ đề của việc chưa có skill kiến thức thì học sâu và LƯU skill trước khi làm.
2. Bản kế hoạch một trang `docs/sessions/Gx.md`: mục tiêu đo được, làm / không làm, chia việc cho subagent (nếu có).
3. Làm (mục 3 nếu chia việc).
4. Cổng kiểm tra: pytest, selftest liên quan, game mở được và >= 60 FPS.
5. Người chơi thử bằng bảng F1; ghi lại các số đã chỉnh.
6. Chốt số (mục 4).
7. Commit trên `dev`; báo cáo mở đầu bằng `ĐỦ BƯỚC` hoặc `THIẾU n BƯỚC`.

## 3. Subagent
- Chỉ chia khi: việc tách được, KHÔNG đụng chung file, và mỗi việc đủ lớn để bù chi phí khởi động nguội.
- Đáng song song: sinh tài nguyên, tra cứu. KHÔNG song song: nhiều agent cùng mở game HOẶC cùng chạy pytest / nạp model (máy chỉ chạy một cửa sổ; luôn bọc `tools\with_game_lock.py`).
  Ngày 7/11/2026 máy ĐƠ CỨNG phải bật lại khi 2 subagent và agent chính cùng chạy game + pytest: máy 8 GB RAM, Intel UHD 620 dùng chung RAM. Người dùng chốt: làm TUẦN TỰ, mỗi lúc một tiến trình nặng.
- Luật quản lý: mỗi subagent nhận (a) danh sách file nó được sửa, (b) mục tiêu đo được, (c) mẫu báo cáo ngắn. Không ai sửa file ngoài danh sách; agent chính ghép và chạy cổng kiểm tra. Hai việc cần cùng một file thì làm tuần tự.
- Việc cơ học (đổi tên, dựng cắt âm, chạy lô tài nguyên) giao model rẻ; thiết kế và ghép giữ ở agent chính.
- Agent chính không bao giờ nói "xong" thay subagent: đọc kết quả, chạy lại kiểm tra.

## 4. Chốt số từ bảng F1
- Người chơi chỉnh bằng F1 rồi bấm Lưu (`user_params.json`). Khi người dùng nói "chốt": `.venv\Scripts\python.exe -X utf8 tools\build\bake_params.py` (in bảng thay đổi, không ghi), xác nhận với người dùng, rồi thêm `--apply`.
  Công cụ sửa đúng giá trị trong `weapon_data.py` (giữ chú thích), chạy lại để đối chiếu từng số (sai thì tự khôi phục), chuyển bản cũ vào `backups\`. Sau đó chạy pytest và commit.
  Lõi ở `fps/core/bake.py`, `tests/test_bake.py` kiểm cả 231 thanh. Số nào có mặc định không phải số viết thẳng thì công cụ báo để sửa tay.

## 5. Phương án ngang sức
- Chỉ dùng cho quyết định KHÓ ĐẢO NGƯỢC hoặc đổi cảm giác chơi. Mẫu: mỗi phương án 3 dòng bằng nhau — được gì / tốn gì / hỏng khi nào. Không đánh dấu "khuyên dùng" trừ khi người dùng hỏi ý kiến.
- Việc nhỏ, đảo ngược được: agent tự chọn, ghi một dòng lý do.

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

## 7. Hạ tầng và multiplayer
- Chế độ: HỢP TÁC, N phòng dựng sẵn, mỗi phòng 4 người, đánh bia/bot.
- Máy chủ phòng: Cloudflare Durable Object, mỗi phòng một đối tượng, nói chuyện WebSocket. Phải viết lại luật bắn / di chuyển / bia chạy bằng TypeScript.
  Giữ hai bản mã KHỚP bằng vector kiểm: Python sinh bộ dữ liệu vào-ra từ `fps/core` (đạn, nhịp bắn, `patrol`), bản TypeScript phải ra cùng kết quả.
- Làm sau, nhưng từ nay mã mới phải tách rõ TRẠNG THÁI người chơi khỏi hiển thị, và toán thuần giữ trong `fps/core` (đang đúng).
- Supabase: game gọi TRỰC TIẾP lúc chạy (khoá anon + RLS). Composio chỉ cho agent quản trị lúc dựng (tạo bảng, truy vấn kiểm).
- Chưa dựng gì cho đến khi game một người xong phần cảm giác và có phiên riêng cho mạng.

## 8. Sổ luật hai tầng (ĐÃ LÀM 6/11/2026)
- Tầng 1 `CLAUDE.md` (~10 KB, từ 50 KB): lệnh, cấu trúc, quy ước, bẫy nạp M4, bẫy Windows, và danh sách "mở khi đụng tới ...".
- Tầng 2 `docs/notes/*.md`: nội dung G1-G7 và danh mục công cụ, trích nguyên văn. Agent chỉ mở file khớp việc đang làm; cuối phiên cập nhật đúng file đó (không thêm lịch sử vào `CLAUDE.md`).
- Cấu trúc thư mục: `assets/` (guns, sounds, shaders), `tools/{selftests,measure,build}`, `docs/{notes,images}`, `backups/`.

## 9. Việc còn mở
- NỢ HIỆU NĂNG: `perf_scenarios` bắn liên thanh khi ngắm 51,7 FPS (ngưỡng 55); tổng 77,1 đạt. Cần phiên tối ưu riêng.
- NỢ KIỂM TRA: sau G7 `tools\selftests\audio_selftest.py` trượt 11/50 mục (kỳ vọng cũ: chưa tính tiếng thở `breath`, tiếng ElevenLabs dài hơn, số nhóm tiếng 15 thay vì 11); g1-g7 và g5/g6 chưa chạy lại đầy đủ.
- Súng lục Glock (phiên G8, 6/11/2026): mẫu đã duyệt, tài nguyên ở `assets/review/glock/`; kế hoạch `docs/sessions/G8.md`. Higgsfield ghi nhận model thực chạy là `nano_banana_2` dù yêu cầu `nano_banana_pro`: cần kiểm lại.
- Xác minh Cloudflare có đủ cho tần số cập nhật của FPS 4 người (đo thật, đừng đoán).
- Tripo không có trong 3D AI Studio: hỏi người dùng muốn dùng đường khác hay thay bằng Prism/P2.
- Thử xem/nghe thử trong Claude Desktop với ElevenLabs và Higgsfield (mục 6, mỗi nền tảng một bản rẻ nhất), ghi kết quả vào mục 6.
- Chưa có cách tự đọc số dư ElevenLabs (khoá thiếu quyền) nên số dư do người dùng khai.
