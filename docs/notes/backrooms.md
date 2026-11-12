<!-- Mở khi: đụng tới level Backrooms (--map backrooms), kẻ địch, flow field, cửa / hành lang cầu thang, máu người chơi, nướng ánh sáng bằng đèn trần. G18 (12/11/2026). -->

# Backrooms - Pool rooms: level 5 tầng, kẻ địch capsule (G18)

Mở: `run.bat --map backrooms` (hoặc `main.py --map backrooms`). Phòng hồ cũ vẫn là map mặc định. Phiên: `docs/sessions/G18.md`. Skill AI: `.claude/skills/enemy-swarm-ai/SKILL.md`.

## Luật chơi (người dùng chốt)
- 5 tầng, mỗi tầng một sảnh gạch trắng có hồ (nước đầy đủ như hồ cũ: sóng, khúc xạ, lặn), cột, vách, đèn trần. 8 / 10 / 12 / 14 / 15 địch (thường / nhanh / nặng tăng dần).
- Vào sảnh thì cửa sau lưng đóng. Hạ hết địch thì cửa bắc mở; leo cầu thang, cửa sau lưng đóng, lên giữa chừng thì sang tầng trên. Hết tầng 5, lên tới đầu cầu thang là THẮNG (hiện thời gian, Enter chơi lại).
- Chết thì chơi lại từ TẦNG 1. Máu tự hồi sau 5 s không bị đánh. Mỗi tầng nạp đầy đạn mọi súng.
- Không có chữ máu: bị đánh thì viền khung đỏ lên, máu thấp thì viền đỏ thường trực + màu nhạt dần (`lens.frag` `lens_hurt`). Số địch còn lại chỉ hiện thoáng qua khi một con chết.

## Cách dựng (đọc trước khi sửa)
- `core/backrooms.py`: một tầng = `build_map(MapData)` (sảnh + hồ ở giữa, không cửa sổ = không nắng) + lỗ cửa bắc / nam (`cut_hole`), cột, vách, tấm đèn (`Box.emit`), hai HÀNH LANG cầu thang bên ngoài sảnh. Bố cục 5 tầng: `weapon_data.BACKROOMS` (`FloorSpec`).
- MẸO 5 TẦNG: mỗi lúc chỉ có MỘT tầng. Hành lang lên của tầng k và hành lang xuống của tầng k+1 giống hệt nhau (cùng hộp, đèn, gốc vân gạch `Box.uv_origin`; leo 14 bậc = 2,4 m = bội chu kỳ gạch). Khi người chơi lên quá nửa cầu thang VÀ cửa sau lưng đã đóng, game thay tầng và dời người chơi `transfer(k)`: quanh anh ta không có gì đổi (kiểm: lệch 0,00 mm). Hai đầu cụt của hành lang có cửa đóng vĩnh viễn.
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
- Game thật: `tools\measure\backrooms_check.py [--vsync]`: đi hết 5 tầng (cửa, địch đuổi + đánh trúng, đạn hạ địch, sạch tầng, đổi tầng lệch 0,00 mm, thắng, Enter chơi lại, chết chơi lại từ tầng 1), đo FPS khi 8-15 con đuổi, chụp `shots\g18_floorN_*.png`.
- CPU phần level (đàn + vẽ + cửa): trung bình 0,66 ms / khung, 99% < 4,7 ms. Có vsync: ~58-60 FPS, khung rớt 2-4%: BẰNG phòng hồ cũ đo cùng cách (5-7%, do Windows / DWM với cửa sổ; tắt vsync thì 166-237 FPS).

## Hạn chế / cố ý không làm
- Địch dưới mặt nước KHÔNG thấy được (nước vẽ khúc xạ bằng tính toán, không chụp cảnh): phần chìm của capsule bị nước che. Flow field né nước sâu nên ít gặp.
- Địch không theo lên tầng, không bắn xa; đèn không nhấp nháy (nướng tĩnh); không nhìn xuyên tầng; không lưu tiến trình.
- Chưa đo trên máy yếu (`weak_pc.py` chưa có cảnh Backrooms). Exe chưa dựng lại.
