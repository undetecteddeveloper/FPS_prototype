<!-- Mở khi: khi đụng tới viewmodel, camera, chuột nhìn, FOV. Trích nguyên văn từ CLAUDE.md cũ (đường dẫn đã cập nhật); số đo ghi trong đây là của lúc đó. -->

# Viewmodel, thế giới, hiệu năng (G1)
- Súng vẽ bằng camera + vùng hiển thị RIÊNG (`viewmodel.py`: đồ thị `root -> sway -> rig -> actor`, sort 5, xoá lại độ sâu, FOV riêng
  `GunData.view_fov`). Code recoil/sway/ADS chỉ cần đặt vị trí/góc cho nút `viewmodel.sway`; `rig` chỉ để căn khớp `FPS_Camera` về gốc camera.
- Camera thế giới là `camera` của Ursina gắn vào `player.camera_pivot`; FOV ngang 80 (`PlayerParams.fov`). Recoil camera (G3) cộng vào pivot.
- Chuột: `mouse.velocity` của Ursina (đơn vị = chiều cao cửa sổ), nhân `mouse_sensitivity` độ/đơn vị. Khi `mouse.locked` mới nhìn.
- Độ sâu thế giới: near 0.1, far 10000 (mặc định Ursina) đủ cho 200 m. Vật nằm sát đất (vạch) dùng `set_depth_offset(1)`, không nâng lên.
- Kiểu `Entity` mới của Ursina 8.3 dùng `unlit_with_fog_shader` (màu phẳng); từ G5 vật thể trường bắn/bia/lỗ đạn dùng `assets/shaders/world.*` (đèn + sương mù), xem mục G5.
- KHÔNG bật MSAA: trên Intel UHD 620 của máy này mọi mức MSAA kéo FPS từ ~140 xuống ~20.
- Vạch ngang làn mảnh hơn một điểm ảnh ở ≥ 100 m nên đứt nét: chỉ vạch tới 50 m, xa hơn dùng biển treo trần (G6).
- Đã đo ở G1 (vsync tắt, 1280x720): trung bình 126 FPS, 1% thấp nhất 84. Khung lưu ảnh chụp rất chậm: loại khỏi số đo.
- Đừng dùng `taskkill /IM python.exe` để tắt game (tắt cả việc khác của người dùng): dùng `--quit-after`.
- Gọi `run.bat` từ Git Bash bằng `cmd //c` không chạy được (không thấy file); dùng PowerShell: `& .\run.bat --quit-after 5`.
- Sửa file bằng `python - <<'EOF'` hoặc `sed` mà chuỗi có `\n` thì dấu `\` bị nuốt và thành xuống dòng thật: dùng công cụ Edit.

