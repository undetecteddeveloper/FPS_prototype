<!-- Mở khi: đụng tới level Backrooms (--map backrooms), kẻ địch, flow field, cửa / hành lang cầu thang, máu người chơi, nướng ánh sáng bằng đèn trần. G18 (12/11/2026). -->

# Backrooms - Pool rooms: level 5 tầng, kẻ địch capsule (G18, bố cục + thang máy G19)

Mở: `run.bat` (phòng hồ bơi, cầu thang bờ bắc dẫn lên tầng 1) hoặc `run.bat --map backrooms` (vào thẳng tầng 1). Phiên: `docs/sessions/G18.md`, `docs/sessions/G19.md`. Skills: `.claude/skills/enemy-swarm-ai/SKILL.md`, `poolrooms-level-design`.

## Luật chơi (người dùng chốt)
- Một mạch: phòng hồ (stage 0, không địch) -> cầu thang bờ bắc -> tầng 1 -> thang máy -> tầng 2 ... tầng 5. Mỗi tầng: MỘT sảnh hồ lớn (nước đầy đủ như hồ cũ: sóng, khúc xạ, lặn) + 3-5 phòng đục quanh (hành lang vòm, phòng tối / mờ / đỏ kiểu 37.1, gác lửng có cầu thang, đài nhảy, rừng cột, cửa sổ cao trên hồ). 8 / 10 / 12 / 14 / 15 địch (thường / nhanh / nặng tăng dần).
- Vào tầng thì cửa sau lưng đóng. Hạ hết địch thì cửa thang máy mở; vào cabin bấm E: cửa đóng, cabin rung + tiếng máy ~5 s, cửa mở ra tầng mới. Tầng 5: chuyến thang cuối kết thúc là THẮNG (hiện thời gian, Enter chơi lại).
- Chết thì chơi lại từ TẦNG 1. Máu tự hồi sau 5 s không bị đánh. Mỗi tầng nạp đầy đạn mọi súng.
- Không có chữ máu: bị đánh thì viền khung đỏ lên, máu thấp thì viền đỏ thường trực + màu nhạt dần (`lens.frag` `lens_hurt`). Số địch còn lại chỉ hiện thoáng qua khi một con chết.

## Cách dựng (đọc trước khi sửa)
- `core/backrooms.py`: một tầng = `build_map(MapData)` (sảnh + hồ ở giữa, không cửa sổ = không nắng) + một KHỐI ĐẶC bao quanh bị khoét bởi mọi thể tích khí (`Room`, `openings`, cabin) bằng phép trừ hộp chính xác (`subtract_box` / `carve`: không hai mặt nào chồng nhau; mảnh không chạm khí bị bỏ) + cột, `blocks` (sàn gác lửng, dầm, tường thấp), `stairs` (bậc chỉ để vẽ; đi bằng dốc `stair_ramp` vì bậc sâu 0,32 m hẹp hơn thân địch), đèn trần đặt theo MẬT ĐỘ từng phòng (`room_panels`, `BACKROOMS_DENSITY`: lit / dim / dark / red). Bố cục 5 tầng: `weapon_data.BACKROOMS` (`FloorSpec`, `Room`, `Cabin`).
- MẸO 5 TẦNG: mỗi lúc chỉ có MỘT tầng, hai lần đổi tầng đều vô hình vì người chơi bị nhốt trong một khối giống hệt hai phía:
  - phòng hồ -> tầng 1: hành lang cầu thang (hai đầu giống hệt, 14 bậc = 2,4 m = bội chu kỳ gạch), đổi tầng khi quá nửa cầu thang và cửa sau lưng đã đóng;
  - tầng k -> k+1: CABIN THANG MÁY (`Cabin`): khung (tâm cửa x, sàn y, z mặt tường phía phòng) phải là bội của 1,2 m trên cả ba trục để vân gạch hai cabin khớp; cabin luôn nằm PHÍA BẮC phòng của nó, cửa quay về -z. Cửa đóng thì tầng đổi, người chơi giữ nguyên chỗ trong cabin (`transfer(k)`, kiểm lệch 0,0 mm), rồi `RIDE` ~5 s, cửa mở.
- `game/backrooms.py`: `Floor` (PoolHall + bầy địch + lưới đường + cửa), `Level` (tiến trình, cửa trượt, âm thanh, máu). Tầng sau dựng LÚC TẦNG HIỆN TẠI SẠCH (khựng ngắn khi không còn ai đánh), tầng cũ bị huỷ (`PoolHall.destroy`, `WaterSurface.destroy`). `Game._enter_floor` nối lại người chơi, đạn, lỗ đạn, giọt nước, camera dưới nước, bụi, phản chiếu.
- Cửa: lá cửa trượt lên (`door_box`); chưa mở hẳn thì là vật cản cho người chơi / địch (`Terrain.dynamic`) và đạn (`Combat.dynamic_boxes`). Trong bake cửa là hộp chắn sáng (`caster`) nên đèn sảnh không lọt vào hành lang (hai hành lang mới sáng giống nhau).

## Ánh sáng nướng bằng đèn trần
- `core/lightbake.py bake_lights`: trực tiếp = từng tấm đèn 2 x 2 mẫu, mỗi mẫu một tia bóng (bóng mềm), tắt dần 8 → 10 m; gián tiếp = hai lượt như bake nắng nhưng tia trúng bề mặt thì TRA ánh sáng trực tiếp đã nướng ở đó (không bắn tia ra nắng); tia trúng đèn hoặc lọt ra lỗ cửa mang về 0. Tấm đèn tự ghi giá trị `BACKROOMS_LIGHT_SHOWN` (phát sáng trong hình).
- Nướng sẵn: `tools\build\bake_backrooms.py [--floor N] [--force]` (~30-55 s / tầng), commit `assets/maps/backrooms/floorN/`. Game tự nướng tầng cũ khoá lúc mở level (màn hình chữ tiến độ). Ảnh phản chiếu của mỗi tầng chụp lần đầu vào tầng đó (`reflect.png`, commit luôn).
- Đèn hành lang yếu hơn đèn sảnh (`BACKROOMS_CORRIDOR_LIGHT`): hành lang hẹp tường trắng dội sáng nhiều lần, bằng đèn sảnh thì cháy trắng.
- Không nắng: `PoolHall.windows = False` -> súng không nhận nắng, không caustic, không tia nắng (F2 vẫn đổi các mục khác).

## Kẻ địch (`core/enemies.py`, `core/flowfield.py`; vẽ `game/enemies.py`, `enemy.frag`)
- Flow field: lưới 0,5 m dựng từ đúng `Terrain` của người chơi (cột / vách chặn theo bán kính thân, gờ cao > 0,2 m là vách: phải xuống hồ bằng bậc / dốc, nước sâu tốn thêm). Dijkstra từ ô người chơi, CHIA NHỎ ≤ 450 ô / khung; đổi đích giữa chừng thì chờ lượt đang chạy xong (khởi động lại mỗi khung làm không bao giờ tính xong khi người chơi đi liên tục).
- Mỗi con: thấy người chơi trong ~9 m thì lao thẳng (lệch sang một bên `flank_angle` để bao vây), xa hơn theo flow field; tách nhau (spatial hash 2 m); đi bằng `resolve_move` như người chơi (không xuyên tường / gờ hồ).
- Giác quan: nón nhìn 120° + tia nhìn (bỏ hộp nước) ~5 lần / s lệch pha; tiếng súng báo động mọi con trong 30 m; con vừa phát hiện gọi đồng bọn trong 7 m.
- Lượt tấn công (token, kiểu Doom 2016): tối đa 3 con cùng gồng / đánh; con không có lượt vòng quanh ở 2,6 m. Gồng 0,3-0,65 s (mắt đỏ, chồm tới, tiếng rít): lùi khỏi tầm là né. Trúng đạn: khựng, huỷ cú gồng, chớp trắng. Trúng đầu (22% trên) x2.
- 3 loại (`weapon_data` `EnemyKind` / `RunnerKind` / `BruteKind`; F1 nhóm "Kẻ địch"): thường 100 máu 4 m/s; nhanh 55 máu 5,6 m/s; nặng 340 máu 2,7 m/s đánh 34.
- Sát thương súng `GunData.damage / damage_near / damage_far / damage_min`: M4 3 phát, Glock 4 phát, M1014 một phát gần (9 viên chì x 16).
- Âm thanh tổng hợp bằng numpy (`tools\build\make_enemy_sounds.py` -> `assets/sounds/enemy/`), không AI, không credit.

## Kiểm tra / số đo (12/11/2026, máy này)
- pytest: `test_backrooms.py`, `test_flowfield.py`, `test_enemies.py` (gồm đo CPU 15 con đuổi trên tầng 5 < 2,5 ms / khung), `test_level.py`, `test_broadphase.py`.
- Game thật (G19, chạy ẨN): `tools\measure\backrooms_check.py [--vsync] [--no-shots]`: phòng hồ -> cầu thang (lệch 0,00 mm) -> tầng 1 -> địch đuổi + đánh trúng, đạn hạ địch, sạch tầng -> thang máy (E, đổi tầng trong cabin lệch 0,0 mm, rung, cửa mở) x4 -> chuyến cuối thắng -> Enter chơi lại -> chết chơi lại từ tầng 1; đo FPS + thời gian `Level.update` khi 8-15 con đuổi; chụp `shots\g19_floorN_<phòng>.png` (mỗi phòng mỗi tầng, cabin, bầy địch).
- Số đo ẩn 12/11/2026 (bộ đệm offscreen, ~500-700 FPS): `Level.update` trung bình 0,36-0,57 ms nhưng p99 3,2-5,9 ms (mục tiêu G19 ≤ 3 ms: CHƯA ĐẠT; G18 đo p99 4,7 ms: không tệ đi). Đã loại nguyên nhân: không phải flow field (< 0,5 ms), không phải GC (tắt GC vẫn có), không phải lần dò tầm nhìn (≤ 0,12 ms), không có điểm nóng trong `_update_one` (tối đa 1,4 ms / con); khung chậm là CẢ khung chậm đồng loạt (tốc độ chu kỳ CPU vẫn như khung thường, nên không phải bị ngắt luồng) - hợp với bộ nhớ dùng chung CPU / GPU Intel hơn là một đoạn thuật toán. Khung rớt (> 25 ms) chỉ 0-0,4%.
- Độ sáng (trung bình lightmap các texel sáng): tầng 1 = 83, tầng 2-5 = 64-75: không tầng nào sáng hơn tầng 1.
- (G18, có vsync: ~58-60 FPS, khung rớt 2-4%: BẰNG phòng hồ cũ đo cùng cách; bản G19 chưa đo lại có vsync vì cần cửa sổ thật.)

## Hạn chế / cố ý không làm
- Địch dưới mặt nước KHÔNG thấy được (nước vẽ khúc xạ bằng tính toán, không chụp cảnh): phần chìm của capsule bị nước che. Flow field né nước sâu nên ít gặp.
- Địch không theo vào thang máy, không bắn xa; đèn không nhấp nháy (nướng tĩnh); không nhìn xuyên tầng; không lưu tiến trình; chỉ MỘT hồ đầy đủ mỗi tầng.
- Ánh sáng từng phòng: `tools\measure\room_light_report.py` (độ rọi trung vị trên lightmap, KHÔNG phụ thuộc phơi sáng; mốc 0,28 = sảnh tầng 1 cũ) + `tests/test_room_light.py` giữ mọi phòng trong dải của loại đèn (`BACKROOMS_DENSITY`, `BACKROOMS_KIND_GAIN`, `Room.gain`). Phòng nhỏ / trần thấp dội sáng nhiều: 'lit' hay quá sáng, thường phải 'dim'. Đừng đặt dầm / vật chắn ngay dưới đèn (đèn lưới đặt giữa mỗi ô).
- Chưa đo trên máy yếu (`weak_pc.py` chưa có cảnh Backrooms). Exe chưa dựng lại.
