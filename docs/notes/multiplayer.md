<!-- Mở khi: bàn chuyện multiplayer / máy chủ phòng / Cloudflare / Supabase. Chuyển nguyên văn từ docs/WORKFLOW.md mục 7 (7/11/2026). -->

## 7. Hạ tầng và multiplayer
- Chế độ: HỢP TÁC, N phòng dựng sẵn, mỗi phòng 4 người, đánh bia/bot.
- Máy chủ phòng: Cloudflare Durable Object, mỗi phòng một đối tượng, nói chuyện WebSocket. Phải viết lại luật bắn / di chuyển / bia chạy bằng TypeScript.
  Giữ hai bản mã KHỚP bằng vector kiểm: Python sinh bộ dữ liệu vào-ra từ `fps/core` (đạn, nhịp bắn, `patrol`), bản TypeScript phải ra cùng kết quả.
- Làm sau, nhưng từ nay mã mới phải tách rõ TRẠNG THÁI người chơi khỏi hiển thị, và toán thuần giữ trong `fps/core` (đang đúng).
- Supabase: game gọi TRỰC TIẾP lúc chạy (khoá anon + RLS). Composio chỉ cho agent quản trị lúc dựng (tạo bảng, truy vấn kiểm).
- Chưa dựng gì cho đến khi game một người xong phần cảm giác và có phiên riêng cho mạng.
