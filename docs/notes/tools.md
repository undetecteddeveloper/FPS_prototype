<!-- Mở khi: khi cần chạy / thêm một bài kiểm tra hoặc công cụ đo. Trích nguyên văn từ CLAUDE.md cũ (đường dẫn đã cập nhật); số đo ghi trong đây là của lúc đó. -->

# Lệnh
- Chạy game: bấm đúp `run.bat` (hoặc `.venv\Scripts\python.exe main.py`): cửa sổ không viền phủ kín màn hình. Tuỳ chọn: `--novsync`, `--window` + `--size 1280x720`,
  `--quit-after 5` (tự thoát sau 5 giây, dùng để kiểm tra mà không phải tắt tiến trình).
- Kiểm tra bằng game thật (điều khiển qua `held_keys`/`combat.pressed`, đo, chụp ảnh vào `shots\`; thoát mã 1 nếu trượt):
  `.venv\Scripts\python.exe -X utf8 tools\selftests\g1_selftest.py` (di chuyển), `tools\selftests\g2_selftest.py` (bắn: nhịp, độ rơi từng bia, đạn, hit marker, lỗ)
  `tools\selftests\g3_selftest.py` (recoil, độ tản theo trạng thái, bloom, tâm ngắm so với phép chiếu thật, kick súng trên màn hình),
  `tools\selftests\g4_selftest.py` (ADS, đường ngắm trùng tâm, thở/bob/lag chuột, quán tính nhảy/ngồi, tư thế chạy, sprint-to-fire)
  `tools\selftests\g5_selftest.py` (rút súng, nạp hai kiểu, huỷ nạp, logic đạn, tia lửa, tracer; 69 mục)
  `tools\selftests\g6_shake_selftest.py` (camera shake), `tools\selftests\g6_targets_selftest.py` (bia chạy, biển, bóng bia chạy; ~1,5 phút), `tools\selftests\g6_debug_selftest.py` (bảng F1, HUD, lưu/nạp; ~1 phút)
  `tools\selftests\g7_selftest.py` (kiểu Bodycam: súng tự do theo chuột, đạn theo nòng, giật ngẫu nhiên, ánh sáng đọc từ điểm ảnh thật, ống kính, phơi sáng, cửa sổ phủ kín). `tools\selftests\run_selftests.py` chạy lần lượt tất cả (> 10 phút: chạy nền).
  Tắt để đo: `free_aim=False` (chuột quay thẳng màn hình, đạn ra giữa), `lens=False` (ảnh không méo, cần cho so khớp chữ), `hud=True` (bật lại HUD để đọc số; game thật không có HUD).
  và `tools\selftests\audio_selftest.py` (BẬT tiếng, kiểm trình phát thật và số lần phát; các selftest khác tắt tiếng bằng `create_game(sound=False)`).
  Các selftest G1–G4 gọi `create_game(draw=False)` để khỏi chờ 1 s rút súng; `create_game(effects=False, look=False)` tắt tia lửa/tracer và shader thế giới (để đo);
  `shake=False` tắt camera shake (g3 cần camera trùng tia ngắm); `moving_targets=False` làm mọi bia đứng yên (g1–g5, g6_shake)
- NHIỀU GAME CÙNG LÚC làm các bài đo theo thời gian (nhịp bắn, FPS) trượt oan. Khi có nhiều agent/terminal: bọc mọi lần mở cửa sổ game bằng
  `.venv\Scripts\python.exe -X utf8 tools\with_game_lock.py <lệnh gốc>` (ổ khoá toàn máy, tự chờ tới lượt). Máy nóng/bận hạ xung: mục "FPS trung bình >= 60" của g3 tụt 59 -> 45 sau nhiều lần chạy liền;
  chạy lại một mình khi máy yên (g3 yên = 62 FPS, sát ngưỡng). `tools\measure\room_perf.py` đo FPS có/không bóng xen kẽ trong cùng một lần chạy (đáng tin hơn số tuyệt đối).
- Rút súng / đổi súng: `tools\measure\swap_check.py` (ghi từng khung engine vẽ lúc mở game + 3 lần đổi súng, kiểm khung đầu tiên hiện súng chạy clip `draw`; in thời gian đứng hình; thoát mã 1 nếu trượt), `tools\measure\g8_shots.py --only hip,sprint [--gun m4|glock]` (chụp `shots\g8_<súng>_*.png`).
- Đo FPS: `tools\measure\perf_scenarios.py` (11 tình huống ở 1366x768, ngưỡng tổng 60, từng tình huống 55), `tools\measure\perf_profile.py idle|fire|ads_fire|reload` (hàm Python tốn nhất), `tools\measure\bodycam_shots.py` (chụp `shots\bc_*.png`).
- Công cụ dựng/đo: `tools\build\prep_sound.py` (dựng `assets\sounds\m4_shot.wav` từ file gốc), `tools\build\prep_foley.py [--check]` (tổng hợp 37 file `assets\sounds\foley\*.wav` bằng mã thuần),
  `tools\build\prep_user_audio.py` (cắt hai file của người dùng thành `assets\sounds\foley\user_*.wav`), `tools\measure\sway_sim.py` (mô phỏng sway: lệch cực đại / quá đà / thời gian ổn định, thuần toán),
  `tools\measure\room_shots.py` (chụp phòng tập), `tools\measure\g4_ads_align.py` (đo điểm ngắm của súng, in tư thế ADS),
  `tools\measure\g5_reload_probe.py` (đo từng khung của clip nạp: băng rời / vào chỗ, bolt), `tools\measure\g5_muzzle_align.py` (đo miệng nòng),
  `tools\measure\g5_perf.py <biến thể>` (FPS lúc đứng yên so với lúc nạp, tắt từng thứ để tìm thủ phạm: base / noblend / cpuskin / noview / nolook / nofx / nohud)
- Map phòng hồ bơi (G9, chi tiết `docs/notes/pool-hall.md`; bọc `with_game_lock.py`): `tools\measure\pool_check.py` (23 mục bằng game thật: ngân sách tam giác, đạn trúng nước / tường / cửa sổ, xuống hồ, leo thang, nhảy lên bờ, ánh sáng súng; thoát mã = số mục trượt),
  `tools\measure\pool_shots.py [--only spawn,east] [--ring] [--holes] [--exposure 4] [--gun]` (chụp `shots\g9_<góc>.png`: spawn, down, east, west, stairs, pool, ceiling, corner, water),
  `tools\build\bake_pool.py` (ép nướng lại ánh sáng + chụp lại phản chiếu), `tools\measure\g8_perf.py --gun m4 --map pool|flat` (so FPS phòng với nền phẳng cũ).
- Test (toán thuần + nạp glb, không mở cửa sổ): `.venv\Scripts\python.exe -X utf8 -m pytest`
- Công cụ G0: `tools\measure\g0_view.py` (chụp ảnh tư thế), `tools\measure\g0_timing.py` (đo clip + FPS), `tools\measure\g0_motion.py`
- Cài lại môi trường: `py -3.13 -m venv .venv` rồi `.venv\Scripts\pip install -r requirements.txt` (KHÔNG dùng Python 3.15)

