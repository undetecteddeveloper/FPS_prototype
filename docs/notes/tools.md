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
- Công cụ dựng/đo: (ĐÃ XOÁ 8/11/2026 cùng file âm thanh không dùng nữa: `prep_sound.py`, `prep_foley.py`, `prep_user_audio.py` và 3 test của chúng; xem `assets/sounds` mục dưới),
  `tools\measure\sway_sim.py` (mô phỏng sway: lệch cực đại / quá đà / thời gian ổn định, thuần toán),
  `tools\measure\room_shots.py` (chụp phòng tập), `tools\measure\g4_ads_align.py` (đo điểm ngắm của súng, in tư thế ADS),
  `tools\measure\g5_reload_probe.py` (đo từng khung của clip nạp: băng rời / vào chỗ, bolt), `tools\measure\g5_muzzle_align.py` (đo miệng nòng),
  `tools\measure\g5_perf.py <biến thể>` (FPS lúc đứng yên so với lúc nạp, tắt từng thứ để tìm thủ phạm: base / noblend / cpuskin / noview / nolook / nofx / nohud)
- Benelli M1014 (G17, `docs/notes/m1014.md`; bọc `with_game_lock.py`): `tools\measure\m1014_check.py` (game thật, 34 mục: 9 viên / phát, bán tự động, hình nón, lực cản, chuỗi nạp từng viên, tiếng một lần mỗi viên, click ngắt nạp, clip dài, dự trữ ít, viên cuối, rút bằng mã, tab F1; thoát mã = số mục trượt),
  `tools\measure\m1014_measure.py` (đo thân súng bằng đỉnh ĐÃ ÁP XƯƠNG: hộp bao từng mesh, hồ sơ nóc, ảnh đám đỉnh quanh vòng ngắm sau / ruồi `shots\m1014_*.png`; ghi ra `ads_sights`, `muzzle`), `tools\measure\m1014_clips.py` (vị trí thanh trượt / viên cầm tay / tay trái theo khung của từng clip: tìm khung viên vào ổ),
  `tools\measure\gun_views.py [--gun m1014] [--clip reload --frame 20]` (chụp súng từ bên / trên / sau / chéo bằng cách dời camera súng, `shots\views_*.png`), `g8_shots.py --gun m1014 [--relief 0.4]`; `tools\build\prep_benelli_glb.py [--scale 0.0122] [--report]` (dựng `benelli_m1014.glb` từ file gốc 66 MB), `tools\build\prep_m1014_audio.py [--check]` (numpy; tiếng bắn + beat đầu của tiếng nạp + bản dưới nước). Ảnh chụp bằng cửa sổ offscreen của Panda có NỀN TRONG SUỐT (alpha 0): xem bằng công cụ ghép lên nền rồi mới đọc.
- Camera không tự trôi theo tâm ngắm (9/11/2026): `tools\measure\camera_drift_check.py [--gun m4|glock]` (game thật, bọc `with_game_lock.py`: súng lệch 8 hướng khi đứng / đi, camera phải đứng yên 3 s; chuột vẫn xoay camera khi quá vùng; ngắm xoay MỘT lần rồi dừng; thoát mã = số mục trượt).
- Map phòng hồ bơi (G9, chi tiết `docs/notes/pool-hall.md`; bọc `with_game_lock.py`): `tools\measure\pool_check.py [--gun m4|glock]` (26 mục bằng game thật: ngân sách tam giác, đạn trúng nước / tường / cửa sổ, xuống hồ, leo thang, nhảy lên bờ, ngắm trước-sau thẳng hàng với mắt khi súng bị đẩy lệch, ánh nền của súng theo phòng; thoát mã = số mục trượt),
  `tools\measure\ads_shots.py [--gun m4|glock] [--yaws 0,2.5] [--relief 0.38]` (chụp súng đang ngắm, bị đẩy lệch tâm, `shots\ads_*.png`; `--relief` thử khoảng cách mắt-ngắm sau),
  `tools\measure\pool_shots.py [--only spawn,east] [--ring] [--holes] [--exposure 4] [--gun]` (chụp `shots\g9_<góc>.png`: spawn, down, east, west, stairs, pool, ceiling, corner, water),
  `tools\build\bake_pool.py` (ép nướng lại ánh sáng + chụp lại phản chiếu), `tools\measure\g8_perf.py --gun m4 --map pool|flat` (so FPS phòng với nền phẳng cũ).
- Test (toán thuần + nạp glb, không mở cửa sổ): `.venv\Scripts\python.exe -X utf8 -m pytest`
- Công cụ G0: `tools\measure\g0_view.py` (chụp ảnh tư thế), `tools\measure\g0_timing.py` (đo clip + FPS), `tools\measure\g0_motion.py`
- Cài lại môi trường: `py -3.13 -m venv .venv` rồi `.venv\Scripts\pip install -r requirements.txt` (KHÔNG dùng Python 3.15)


# G10 (7/11/2026)
- `tools\measure\g8_perf.py --level 0|1|2` (mức đồ hoạ), `--trace` (in từng khung của giây đầu), `--size WxH`.
- `tools\measure\flash_shots.py [--gun-name m4|glock] [--spot dark|beam] [--set gun.flash.light_power=3]`: đứng chỗ tối nhất phòng hồ, bóp cò, chụp `shots\flash_<súng>_off.png` / `_on.png` và in độ sáng góc dưới-phải (nơi có súng). Tia lửa lên súng dùng đèn riêng nâng lên + lùi về phía mắt + ánh sáng ôm vòng (`gun.flash.gun_*`, `viewmodel.frag gun_flash_light`), vì đèn ở đầu nòng chỉ chiếu mặt súng quay ra trước (mặt người chơi thấy toàn mặt sau / trên, nên đen).
- `tools\measure\commit_probe.py <giây> <lệnh>` (game chiếm bao nhiêu commit hệ thống: trước / thấp nhất / ổn định), `tools\measure\job_limit_run.py <MB> <giây> <lệnh>` (chạy lệnh với giới hạn commit riêng để tái hiện lỗi thiếu bộ nhớ; chỉ ảnh hưởng tiến trình đó), `tools\measure\lowmem_check.py` (chế độ giảm tải bằng game thật). Xem `docs/notes/troubleshooting.md`.
- `tools\measure\pool_shots.py --level 0|1|2 --set water.wave_height=0.004 [--set ...]` (so A/B một số mà không cần F1); góc mới `deep`, `slope`, `wade`. `--ring --ring-ahead 3` đặt 3 viên đạn ngay trước mặt camera (thấy vân caustics vỡ theo sóng). So A/B một số trên ảnh: thêm `--set water.wave_speed=0 --set water.ripple_speed=0` để gợn đứng yên, nếu không hai lần chạy chụp ở hai thời điểm sóng khác nhau.
- Bước chân + tiếng nền (8/11/2026): `tools\build\prep_pool_audio.py [--check]` (numpy; dựng `foley/boot_step_0.wav`, `pool_ambience.wav`, `under_ambience.wav` và bản dưới nước của bước chân từ `assets/sounds/source/pool/`). `tests/test_pool_audio.py` kiểm.
- Âm thanh Glock (8/11/2026): `tools\build\prep_glock_audio.py [--check]` (numpy; dựng tiếng bắn `glock_shot_0.wav`, ba beat nạp `foley/glock_{release,magout,seat}_0.wav`, `glock_slide_0.wav` (nhả slide chỉ giữ beat đầu) và bản dưới nước từ `assets/sounds/source/glock/`; `--check` chỉ so với file hiện có). `tests/test_glock_audio.py` kiểm mốc tiếng với animation.
- G12 âm thanh: `tools\build\prep_underwater.py [--apply] [--cutoff 400] [--level 0.5] [--amb-cutoff 220] [--no-bubbles]` (không có --apply chỉ in bảng trước/sau; dựng `assets/sounds/foley_under/` + `under_ambience.wav`), `water_audio_check.py` thêm 6 mục dưới nước.
- G14: `pool_check.py [--gun m4|glock]` thêm 5 mục (thân dừng cách thành 0,30 m ở 3 thành sâu; súng ngóc + khoá bắn / ngắm sát tường, nạp đạn vẫn được, hạ khi lùi); `pool_shots.py` góc `ladder_front`, `ladder_wide`, `ladder_bank`, `ladder_deck`, `ladder_side`. Lỗi xuyên thành CHỈ tái hiện khi đi thật (giữ phím tiến) vào thành: đặt vị trí cách 5 mm không thấy.
- G13 (hiệu năng máy yếu, `docs/notes/performance.md`): `tools\measure\weak_pc.py [--gun m4|glock] [--level 0] [--passes]` (ước FPS trên UHD 620 từ ms GPU ×4 và ms CPU ×2; thoát mã 1 nếu trượt),
  `tools\measure\gpu_timer.py` (bộ đếm thời gian OpenGL cho từng vùng vẽ, chỉ dùng trong công cụ), `g8_perf.py --weak` (ms GPU / CPU + ước máy yếu) `--passes` (ms từng lượt vẽ) `--vsync` `--borderless` `--json FILE`.
- G12: `pool_shots.py` góc `uw_level`, `uw_up`, `uw_wall`, `uw_half`, `uw_half_down`, `surfaced` (0,3 s sau khi trồi; ống kính phải sạch), `surfaced_late` đã bỏ 8/11/2026; `pool_check.py` thêm 12 mục dưới nước (xuống đáy sâu, chặn bắn + chữ, trồi lên thì ống kính sạch, F2 dưới nước); `g8_perf.py` thêm 3 tình huống dưới nước.
- `tools\measure\pool_check.py`: thêm mục sóng mô phỏng (đọc ngược texture từ GPU: dùng `WaterSim.drawn_texture`, KHÔNG `latest_texture` - pass của khung này chưa vẽ), nhìn thấy đáy, F2 không giật, vạch nước sâu.
- Đọc ngược GPU (`extract_texture_data`) chặn GPU: khung KẾ TIẾP bị tính chậm 60-75 ms; đo thời gian thì chờ ~30 khung sau mỗi lần đọc.
- Công tắc để đo: F2 / `game.set_graphics(0)` = tắt mọi hiệu ứng G10 (như G9).
- `tools\measure\graphics_panel_check.py`: bảng đồ hoạ F2 bằng game thật (MSAA thật, mọi dòng, lưu file vào thư mục tạm).
- `tools\build\prep_water_audio.py [--set nhóm=bản,...] [--apply]`: dựng tiếng nước từ bản duyệt (không cần ffmpeg). `tools\measure\water_audio_check.py`: đường phát tiếng nước bằng game thật.
- `tools\measure\reload_check.py [--gun m4|glock]`: sau nạp đạn súng dùng lại được từ lúc về chỗ (game thật, thao tác thật). `tools\build\prep_water_audio.py` giờ chỉ dựng 3 tiếng đã chọn (+ in tỉ lệ to nhỏ so với bước gạch); `water_audio_check.py` kiểm cả việc hiệu chỉnh nông / sâu / chạy.
- Bản exe demo (G15, 7/11/2026): `tools\build\build_exe.py [--console] [--no-zip]` (cần `.venv\Scripts\pip install -r requirements-build.txt`) dựng `build\FPS_prototype\FPS_prototype.exe` + `build\FPS_prototype_demo_<ngày>.zip` (~90 s, thư mục 192 MB, zip 88 MB). Kiểm khoá ánh sáng nướng trước khi đóng gói. Cách đóng gói, bẫy, cách kiểm như máy bạn bè: skill `pyinstaller-packaging`.
- Độ ổn định (G16, 7/11/2026; tiêu chí `docs/sessions/G16.md`, skill `game-stability-qa`):
  `tools\measure\chaos_check.py [--seconds 60] [--seed 1] [--gun m4|glock]` phá game thật (phím / chuột ngẫu nhiên, đổi súng giữa lúc nạp, F1 / F2, khựng giả 0,3-2 s, thu nhỏ cửa sổ thật); bất biến mỗi khung; mẫu bộ nhớ / node mỗi 5 s, từ 300 s xét rò rỉ. Bản 60 s làm cổng mỗi commit đụng vòng lặp game.
  `tools\measure\launch_check.py [--runs 10] [--run-s 4] [--exe <đường dẫn exe>]` mở / đóng (WM_CLOSE như Alt+F4) N lần, mã 0; `--run-s 0.3` đóng giữa lúc tải.
