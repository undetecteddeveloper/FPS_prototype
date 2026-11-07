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
