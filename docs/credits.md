# Sổ credit

Quy tắc ở `docs/notes/ai-assets.md` mục 6b. Mỗi lần sinh tài nguyên thêm MỘT dòng; số dư là số SAU lần sinh. Người dùng khai lại số dư thật đầu mỗi phiên sinh tài nguyên.

## Số dư đầu kỳ (người dùng khai 6/11/2026)
| Nền tảng | Credit |
|---|---|
| Higgsfield | 860 |
| 3D AI Studio | 864 |
| ElevenLabs | 8144 |

## Nhật ký
| Ngày | Nền tảng | Phong bì | Mục đích | Công cụ / model | Credit | Còn lại |
|---|---|---|---|---|---|---|
| 6/11/2026 | ElevenLabs | Nháp | Test kết nối: tiếng cạch súng 1 s (không giữ file) | Composio `ELEVENLABS_GENERATE_SOUND_EFFECTS`, `eleven_text_to_sound_v3`, mp3_44100_128 | chưa biết (lệnh không trả credit) | chưa biết |
| 6/11/2026 | Higgsfield | Nháp | Test ảnh: CHƯA LÀM, lỗi 401 khoá bị từ chối (Soul Standard 720p), thử 3 lần | Composio `HIGGSFIELD_GENERATE_SOUL_STANDARD_IMAGE` | 0 (không rõ có bị tính) | 860 |
| 6/11/2026 | 3D AI Studio | Nháp | Test model 3D: CHƯA LÀM, phiên không có công cụ 3D AI Studio (Prism 3.1) | — | 0 | 864 |
| 6/11/2026 | ElevenLabs | Tiếng hiệu ứng | Mẫu xem thử: tiếng súng lục 2 s (`assets/review/glock/audio/pistol_shot_eleven_v3.mp3`) | Composio `ELEVENLABS_GENERATE_SOUND_EFFECTS`, `eleven_text_to_sound_v3` | chưa biết (lệnh không trả credit) | chưa biết |
| 6/11/2026 | Higgsfield | Nháp | Ảnh concept súng lục 1k (`assets/review/glock/concept/pistol_concept_higgsfield.png`) | `higgsfield_mcp` `nano_banana_pro` (job ghi nhận chạy `nano_banana_2`) | 2 | 858 |
| 6/11/2026 | 3D AI Studio | Nháp | Model súng lục từ ảnh trên (`assets/review/glock/model/pistol_prism31.glb`, 1,43 triệu tam giác, 41,7 MB) | Prism 3.1, texture 3.0, PBR | 35 | 829 |
| 7/11/2026 | ElevenLabs | Tiếng hiệu ứng | 9 tiếng foley súng lục: tháo/thả/lắp/vào chỗ băng, nhả slide, rút, ổn định tay, cất, bấm cò rỗng (`assets/review/glock/audio/pistol_*_eleven_v3.mp3`; prompt ở `assets/sounds/source/elevenlabs/PROMPTS.txt` mục 31-39) | Composio `ELEVENLABS_GENERATE_SOUND_EFFECTS`, `eleven_text_to_sound_v3`, một lượt 9 lệnh | chưa biết (lệnh không trả credit) | chưa biết |
| 7/11/2026 | ElevenLabs | Tiếng hiệu ứng | 3 bản nháp tiếng đạn trúng nước (`assets/review/water/water_*_eleven_v3.mp3`; prompt ở `assets/sounds/source/elevenlabs/PROMPTS.txt` mục 40-42) | Composio `ELEVENLABS_GENERATE_SOUND_EFFECTS`, `eleven_text_to_sound_v3`, một lượt 3 lệnh | chưa biết (lệnh không trả credit) | chưa biết |
| 7/11/2026 | ElevenLabs | Tiếng hiệu ứng | G10: 9 tiếng nước: 3 bước lội, chạy trong nước, 2 nhảy / rơi xuống hồ, đạn trúng nước, nhỏ giọt khi lên bờ, tiếng nền phòng hồ 12 s lặp (`assets/review/water/*_eleven_v3.mp3`; prompt mục 43-51) | Composio `ELEVENLABS_GENERATE_SOUND_EFFECTS`, `eleven_text_to_sound_v3`, một lượt 9 lệnh | chưa biết (lệnh không trả credit; người dùng cho phép không giới hạn 7/11/2026) | chưa biết |
| 7/11/2026 | — | — | Dọn dẹp theo yêu cầu người dùng: XOÁ model Glock tự dựng cũ (`assets/review/glock/{concept,model,animation}`: ảnh concept, model Prism 3.1, bản hạ mặt + Blender, bản có animation; 475 MB, không còn dùng vì game dùng `assets/guns/glock17.glb`) và 9 bản nháp tiếng nước không chọn; giữ `wade_step_deep`, `water_jump_a`, `pool_ambience_loop` (`assets/review/water/`) | — | 0 | không đổi |
| 7/11/2026 | ElevenLabs | Tiếng hiệu ứng | G12: 6 bản nháp dưới nước (2 nền dưới nước lặp 12 s, 2 chìm xuống 2 s, 2 trồi lên 2 s; `assets/review/water/{under_ambience,submerge,surface}_{a,b}_eleven_v3.mp3`; prompt mục 52-57). Người dùng duyệt báo giá ~640 credit; nghe xong LOẠI cả 6 bản (không dùng) | Composio `ELEVENLABS_GENERATE_SOUND_EFFECTS`, `eleven_text_to_sound_v3`, một lượt 6 lệnh | ~640 theo giá API 20/s (lệnh không trả credit) | chưa biết |
| 8/11/2026 | — (người dùng đưa file) | Tiếng hiệu ứng | Tiếng bắn Glock 17 + hai file nạp đạn (beat đầu, beat cuối) do người dùng cung cấp (`assets/sounds/source/glock/*.wav`; nguồn gốc / giấy phép chưa ghi, cần người dùng điền) | — | 0 | không đổi |
| 8/11/2026 | Higgsfield | Ảnh chủ chốt | Texture bản nháp (người dùng duyệt kế hoạch 5 ảnh, bảo dùng Nano Banana Pro): gạch sàn, gạch ốp tường, vữa xi măng, 2 lỗ đạn vỡ men (`assets/review/textures/{floor_tile,wall_tile,grout,hole_a,hole_b}_ai.png`, 2048 × 2048; prompt ở `assets/review/textures/PROMPTS.txt`). Ảnh sàn lần đầu bị bộ lọc báo `nsfw` nhầm, viết lại prompt rồi sinh lại. Job báo chạy `nano_banana_2` dù yêu cầu `nano_banana_pro` (giống ghi chú 6/11/2026) | `higgsfield_mcp` `nano_banana_pro` qua `HIGGSFIELD_MCP_GENERATE_IMAGE_BATCH`, preflight 2 credit / ảnh | ~10-12 (5 ảnh xong + 1 lượt `nsfw` có thể bị tính; chưa đọc số dư) | ~848-850 (ước, chờ người dùng khai lại số dư) |
| 8/11/2026 | — | — | Người dùng KHÔNG ƯNG 5 ảnh AI ở dòng trên và bảo xoá: đã xoá cả 5 file ảnh (còn `PROMPTS.txt`). Texture sàn / tường / lỗ đạn chuyển sang dựng bằng numpy (không tốn credit) | — | 0 | không đổi |
| 8/11/2026 | — (người dùng đưa file) | Tiếng hiệu ứng | Bước chân giày trên gạch (`tatical_boot_footstep_on_brick_ground-*.wav`) và tiếng nền hồ bơi (`Tranquil_indoor_swim_narrow-*.wav`; bản `wide` để dành) (`assets/sounds/source/pool/`; nguồn gốc / giấy phép chưa ghi, cần người dùng điền) | — | 0 | không đổi |
