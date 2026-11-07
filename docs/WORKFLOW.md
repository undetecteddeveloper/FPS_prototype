# Cách làm việc (chốt 6/11/2026, rút gọn 7/11/2026)

Luật kỹ thuật của mã: `CLAUDE.md`. File này chỉ nói CÁCH LÀM VIỆC. Phần chỉ cần ở một số việc đã chuyển nguyên văn sang: `docs/notes/ai-assets.md` (tài nguyên AI, credit, Blender, học thành skill, thư mục review; mục 6-6f), `docs/notes/multiplayer.md`.

## 1. Nguyên tắc
- Người dùng prompt ngắn; agent hỏi bằng AskUserQuestion theo CỠ VIỆC (mục 2). Mỗi phiên có bản chốt câu trả lời ở đầu `docs/sessions/Gx.md`.
- Mục tiêu: mỗi phiên 3-5 mục tiêu ĐO ĐƯỢC (selftest, pytest, FPS), viết trước khi code. Chưa có cách đo thì chưa bắt đầu.
- 80/20: ghi rõ "làm" và "cố ý KHÔNG làm"; việc lòi thêm giữa chừng vào danh sách chờ, không làm lẫn.
- Mã: grep `fps/core` + `fps/game` xem đã có chưa trước khi viết; toán mới vào `fps/core`; mọi số vào `weapon_data.py`. Báo cáo cuối nêu "đã tái dùng: ...".
- Cảm giác chơi: agent chỉ dựng bảng F1 + kiểm tra; NGƯỜI chơi chỉnh, rồi chốt vào mặc định (mục 4).

## 2. Mức hỏi theo cỡ việc (người dùng chốt 6/11/2026; thắng luật chung "tự quyết kỹ thuật")
- Dòng đầu câu trả lời đầu tiên: "Cỡ: nhỏ / lớn, vì ...", để người dùng sửa nếu xếp sai.
- NHỎ = sửa một số, một lỗi, một chú thích; trong một file; người chơi KHÔNG thấy hành vi đổi. Hỏi tối đa một vòng ngắn (1-2 câu), hoặc làm luôn rồi báo nếu yêu cầu rõ hoàn toàn.
- LỚN = tính năng, phiên mới, tài nguyên mới, đụng từ 2 module, MỌI thứ đổi cảm giác chơi, mọi việc tốn credit. LUÔN đủ hai vòng: vòng 1 hỏi Ý TƯỞNG (cảm giác gì, giống ví dụ nào, ai chơi, thế nào là thành công); vòng 2 hỏi kỹ thuật. Hỏi đến khi không còn giả định lớn nào chưa nói ra; không hỏi lại cái đã có trong tài liệu.
- Mỗi vòng ≤ 4 câu; chữ đơn giản, mỗi lựa chọn kèm ví dụ đời thường và hậu quả nói bằng lời thường.
- Phương án ngang sức (chỉ cho quyết định khó đảo ngược hoặc đổi cảm giác chơi): mỗi phương án 3 dòng bằng nhau (được gì / tốn gì / hỏng khi nào), không đánh dấu "khuyên dùng" trừ khi được hỏi ý kiến. Việc nhỏ đảo ngược được thì tự chọn, ghi một dòng lý do.

## 3. Một phiên (Gx): 7 bước
1 Hỏi đáp (mục 2) · 1b Học: chủ đề chưa có skill thì học và LƯU skill trước (`ai-assets.md` 6e) · 2 Bản kế hoạch một trang `docs/sessions/Gx.md` (mục tiêu đo được, làm / không làm, chia việc subagent nếu có) · 3 Làm · 4 Cổng kiểm tra (pytest, selftest liên quan, game mở được, ≥ 60 FPS) · 5 Người chơi thử bằng F1, ghi số đã chỉnh · 6 Chốt số (mục 4) · 7 Commit trên `dev`; báo cáo mở đầu `ĐỦ BƯỚC` hoặc `THIẾU n BƯỚC`.

## 4. Chốt số từ bảng F1
Người chơi chỉnh bằng F1 rồi bấm Lưu (`user_params.json`). Khi người dùng nói "chốt": chạy `.venv\Scripts\python.exe -X utf8 tools\build\bake_params.py` (chỉ in bảng thay đổi), xác nhận với người dùng, rồi thêm `--apply`. Công cụ sửa đúng giá trị trong `weapon_data.py` (giữ chú thích), đối chiếu lại từng số (sai thì tự khôi phục), chuyển bản cũ vào `backups\`. Sau đó pytest và commit. Lõi: `fps/core/bake.py`, `tests/test_bake.py`; số nào có mặc định không phải số viết thẳng thì công cụ báo để sửa tay.

## 5. Subagent
- Chỉ chia khi việc tách được, KHÔNG đụng chung file, và đủ lớn để bù chi phí khởi động nguội. Đáng song song: sinh tài nguyên, tra cứu.
- KHÔNG chạy song song nhiều agent mở game / pytest / nạp model: máy 8 GB RAM + Intel UHD 620 dùng chung RAM đã ĐƠ CỨNG 7/11/2026. Người dùng chốt: TUẦN TỰ, mỗi lúc một tiến trình nặng; luôn bọc `tools\with_game_lock.py`.
- Mỗi subagent nhận (a) danh sách file được sửa, (b) mục tiêu đo được, (c) mẫu báo cáo ngắn; không ai sửa ngoài danh sách; hai việc cần cùng file thì làm tuần tự. Agent chính ghép, chạy cổng kiểm tra, KHÔNG nói "xong" thay subagent (đọc kết quả, chạy lại kiểm tra).
- Việc cơ học (đổi tên, dựng cắt âm, chạy lô tài nguyên) giao model rẻ; thiết kế và ghép giữ ở agent chính.

## 6. Tài nguyên AI: luật cốt lõi (chi tiết: `docs/notes/ai-assets.md`)
Người dùng duyệt TỪNG CÁI và phải xem/nghe xong mới được duyệt; mỗi mục kèm prompt + công cụ + chi phí. Chi tiêu theo phong bì, ghi `docs/credits.md`; hết phong bì thì DỪNG và hỏi. Mọi tài nguyên sinh ra lưu vào `assets/review/<object>/` trước, chỉ bản đã duyệt mới chép sang `assets/`.

## 7. Việc còn mở (cập nhật 7/11/2026)
- NỢ TEST: `tests/test_breath.py` không nạp được và 5 bài `tests/test_prep_elevenlabs.py` trượt (do bỏ tiếng thở / đổi tiếng súng M4, commit 64c057e; người dùng tự sửa). Selftest bằng game thật không chạy được (xem `CLAUDE.md`).
- NỢ HIỆU NĂNG: `perf_scenarios` cũ không còn chạy; đo bằng `tools\measure\g8_perf.py`.
- G9 (map hồ bơi, `docs/sessions/G9.md`, `docs/notes/pool-hall.md`): CHỜ NGƯỜI DÙNG (a) xem map trong game bằng `run.bat` và so với ảnh tham chiếu, chỉnh bằng F1 rồi chốt số; (b) nghe 3 bản nháp tiếng nước ở `assets/review/water/` và chọn một (hoặc bảo tạo lại), rồi mới gắn vào game.
- Glock (G8, `docs/sessions/G8.md`, tài nguyên `assets/review/glock/`): Higgsfield ghi model thực chạy là `nano_banana_2` dù yêu cầu `nano_banana_pro`, cần kiểm lại.
- Chưa xác nhận xem/nghe thử ElevenLabs / Higgsfield trong Claude Desktop; chưa tự đọc được số dư ElevenLabs (người dùng khai); Tripo không có trong 3D AI Studio (hỏi người dùng); chưa đo Cloudflare đủ cho FPS 4 người.
