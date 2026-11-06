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
2. Bản kế hoạch một trang `docs/sessions/Gx.md`: mục tiêu đo được, làm / không làm, chia việc cho subagent (nếu có).
3. Làm (mục 3 nếu chia việc).
4. Cổng kiểm tra: pytest, selftest liên quan, game mở được và >= 60 FPS.
5. Người chơi thử bằng bảng F1; ghi lại các số đã chỉnh.
6. Chốt số (mục 4).
7. Commit trên `dev`; báo cáo mở đầu bằng `ĐỦ BƯỚC` hoặc `THIẾU n BƯỚC`.

## 3. Subagent
- Chỉ chia khi: việc tách được, KHÔNG đụng chung file, và mỗi việc đủ lớn để bù chi phí khởi động nguội.
- Đáng song song: sinh tài nguyên, toán thuần + pytest, tra cứu. KHÔNG song song: nhiều agent cùng mở game (máy chỉ chạy một cửa sổ; luôn bọc `tools\with_game_lock.py`).
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
| Ảnh / video | Higgsfield qua Composio (Nano Banana Pro, Seedance) | 3D AI Studio có Qwen 2.1 / Nano 2.1 rẻ cho bản nháp |
| Nhạc | ElevenLabs `music_v1` qua Composio | |
| Tiếng hiệu ứng | ElevenLabs `eleven_text_to_sound_v2` (HOẶC `generate_sound_effect` của 3D AI Studio, rẻ) | V3 chỉ là model GIỌNG NÓI |
| Giọng nói | ElevenLabs V3 | Cần xác minh ID chính xác trước khi ghi cứng |
| Model / texture 3D | 3D AI Studio (nối trực tiếp, không qua Composio): Prism 3.1 mặc định, Meshy 7.1 khi cần texture 4K/8K, P2 khi cần quad | Danh sách không có Tripo |
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
- Đợt dịch toàn bộ một lần cho mã hiện có (CHƯA LÀM): subagent model rẻ dịch theo nhóm file không chồng nhau; kiểm bằng cách so cây AST đã bỏ docstring trước/sau (phải trùng) cộng pytest; mã GLSL chỉ đổi phần comment. Các số đo nằm trong comment phải giữ nguyên chữ số và đơn vị.
- Truy nguyên: mỗi tài nguyên giữ prompt, công cụ, model, seed trong `assets/source/` (hoặc `sounds/source/`) để làm lại được; ghi nguồn/giấy phép vào `CREDITS.txt`.

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
- Xác minh ID model giọng nói của ElevenLabs V3 trước khi dùng.
- Xác minh Cloudflare có đủ cho tần số cập nhật của FPS 4 người (đo thật, đừng đoán).
- Tripo không có trong 3D AI Studio: hỏi người dùng muốn dùng đường khác hay thay bằng Prism/P2.
- Thử xem/nghe thử trong Claude Desktop với ElevenLabs và Higgsfield (mục 6, mỗi nền tảng một bản rẻ nhất), ghi kết quả vào mục 6.
- Đợt dịch comment sang tiếng Anh (mục 6c): chờ người dùng nói bắt đầu.
- Chưa có cách tự đọc số dư ElevenLabs (khoá thiếu quyền) nên số dư do người dùng khai.
