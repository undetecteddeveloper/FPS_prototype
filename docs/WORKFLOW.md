# Workflow dự án (chốt 6/11/2026)

Viết cho: người dùng và các agent mở phiên sau. Luật kỹ thuật của mã nằm ở `CLAUDE.md`; file này chỉ nói CÁCH LÀM VIỆC.

## 1. Năm nhóm nguyên tắc

| Nhóm | Luật | Cách kiểm |
|---|---|---|
| Ra lệnh | Người dùng prompt ngắn; agent hỏi đáp kỹ bằng AskUserQuestion (đủ lớp: định hướng + kỹ thuật, có ví dụ đời thường) trước khi làm | Mỗi phiên có bản chốt câu trả lời ở đầu `docs/sessions/Gx.md` |
| Mục tiêu | Mỗi phiên có 3-5 mục tiêu ĐO ĐƯỢC (selftest, pytest, FPS), viết trước khi code | Mục tiêu nào không có cách đo thì chưa được bắt đầu |
| Chọn việc | 80/20: mỗi phiên ghi rõ "làm" và "cố ý KHÔNG làm"; việc lòi thêm giữa chừng đưa vào danh sách chờ, không làm lẫn | Phần "không làm" của bản kế hoạch |
| Mã | Tìm trước khi viết: grep `fps/core` + `fps/game` xem đã có chưa; toán mới vào `fps/core` (không import ursina); mọi số vào `weapon_data.py` | Báo cáo cuối phiên nêu "đã tái dùng: ..." |
| Cảm giác chơi | Agent chỉ dựng bảng chỉnh (F1) + selftest; NGƯỜI chơi và chỉnh; xong thì chốt vào mặc định | Mục 4 |

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
- Hiện chép tay `user_params.json` -> `weapon_data.py`. CHƯA LÀM: viết `tools\bake_params.py` so file lưu với mặc định, in bảng thay đổi, ghi vào `weapon_data.py` sau khi người dùng nói "chốt", rồi chuyển file cũ sang `user_params.baked.json`. Phiên đầu tiên có điều chỉnh cảm giác thì làm công cụ này trước.

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
- Cổng duyệt: người dùng duyệt TỪNG CÁI. Agent gom mỗi lô thành một bảng (ảnh lưới / danh sách nghe) để duyệt một lượt, mỗi mục kèm prompt + công cụ + chi phí.
- Truy nguyên: mỗi tài nguyên giữ prompt, công cụ, model, seed trong `assets/source/` (hoặc `sounds/source/`) để làm lại được; ghi nguồn/giấy phép vào `CREDITS.txt`.

## 7. Hạ tầng và multiplayer
- Chế độ: HỢP TÁC, N phòng dựng sẵn, mỗi phòng 4 người, đánh bia/bot.
- Máy chủ phòng: Cloudflare Durable Object, mỗi phòng một đối tượng, nói chuyện WebSocket. Phải viết lại luật bắn / di chuyển / bia chạy bằng TypeScript.
  Giữ hai bản mã KHỚP bằng vector kiểm: Python sinh bộ dữ liệu vào-ra từ `fps/core` (đạn, nhịp bắn, `patrol`), bản TypeScript phải ra cùng kết quả.
- Làm sau, nhưng từ nay mã mới phải tách rõ TRẠNG THÁI người chơi khỏi hiển thị, và toán thuần giữ trong `fps/core` (đang đúng).
- Supabase: game gọi TRỰC TIẾP lúc chạy (khoá anon + RLS). Composio chỉ cho agent quản trị lúc dựng (tạo bảng, truy vấn kiểm).
- Chưa dựng gì cho đến khi game một người xong phần cảm giác và có phiên riêng cho mạng.

## 8. Sổ luật hai tầng (CHƯA LÀM)
- Tầng 1 `CLAUDE.md`: lệnh, cấu trúc, quy ước, bẫy còn hiệu lực (~5 KB, luôn nạp).
- Tầng 2 `docs/`: mục G1-G7 hiện nằm trong `CLAUDE.md` (~50 KB) chuyển sang `docs/gN.md`; `CLAUDE.md` chỉ giữ một dòng trỏ tới và dòng "đọc khi đụng tới ...".
- Cần thực hiện cẩn thận vì `CLAUDE.md` đang có thay đổi chưa commit của G7.

## 9. Việc còn mở
- Xác minh ID model giọng nói của ElevenLabs V3 trước khi dùng.
- Xác minh Cloudflare có đủ cho tần số cập nhật của FPS 4 người (đo thật, đừng đoán).
- Tripo không có trong 3D AI Studio: hỏi người dùng muốn dùng đường khác hay thay bằng Prism/P2.
- Ngân sách credit mỗi tháng chưa có; chưa có cách xem số dư ElevenLabs (khoá thiếu quyền).
