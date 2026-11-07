<!-- Mở khi: đụng tới map (phòng hồ bơi), nước, ánh sáng nướng sẵn, phản chiếu, va chạm / bậc thang của người chơi. -->
# Map đầu tiên: phòng hồ bơi trong nhà (G9, 7/11/2026)

Viết cho: người dùng và agent mở phiên sau. Kế hoạch + bản chốt hỏi đáp: `docs/sessions/G9.md`. Skill kỹ thuật (nguồn, bẫy, số đo đã kiểm chứng): `.claude/skills/interior-water-light/SKILL.md`.
Ảnh tham chiếu do người dùng đưa: phòng hồ ốp gạch vuông nhỏ, nắng vàng xiên qua cửa sổ thành mảng cứng cạnh, nước tối như gương.

## Đã có gì
- Phòng 20 × 30 m, trần 4,2 m, hồ 12 × 24 m (nông 0,5 m, mặt nước thấp hơn bờ 12 cm), bờ 4 m hai bên và 3 m hai đầu. 4 cửa sổ hở ở tường ĐÔNG (không kính), 2 cột ở bờ tây, một flight cầu thang 4 bậc ở bờ bắc, 3 bậc xuống hồ ở đầu nam (cả bề rộng) và 3 bậc hẹp ở đầu bắc có 2 tay vịn inox uốn cong.
  Người chơi xuất phát ở bờ nam (0, 0, -13,5) nhìn về +z dọc hồ.
- Mọi thứ là HỘP (`core/poolmap.py`): sàn, tường có lỗ, trần, cột, bậc. Mặt lộ ra (`exposed_faces`) tự suy từ hộp: mặt chôn trong hộp khác, quay ra ngoài hay nằm dưới nước đều bị bỏ.
  Số đo hiện tại: 752 tam giác (phòng 174 + tay vịn 576 + nước 2), 2 lần vẽ (phòng + nước). Trần đặt ra là ≤ 6.000.
  Mỗi cửa sổ có đủ 4 mặt lót lỗ (bệ, trán, hai thanh bên) sâu bằng bề dày tường 0,4 m. Hộp rào vô hình lấp lỗ cửa sổ chỉ để chặn người chơi: KHÔNG được coi là vật rắn khi suy mặt lộ ra (`is_air` bỏ qua hộp `visible=False`).
- Ánh sáng NƯỚNG SẴN một lần (`core/lightbake.py`, numpy): nắng trực tiếp mềm viền (mặt trời ~7° thấp trên cửa sổ đông, `LookData.sun_dir`) + 2 lượt nảy + ánh trời qua cửa sổ.
  Lưu `assets/maps/pool/lightmap.png` (1024 × 512, bức xạ mã hoá gamma 2, 8 bit) + `ambient.json` (lưới ánh nền cho súng, xem dưới) + `meta.json` (băm hình học + nắng + số mã). Shader `room.frag` = albedo gạch (vẽ bằng shader từ toạ độ mét, không texture) × ánh sáng nướng.
- Nước (`game/water.py`, `water.vert|frag`): mặt phẳng; chỉ tính ĐỘ DỐC bề mặt (gợn nền 5 sóng sin + tối đa 12 vòng sóng đạn, `core/waves.py`) để nghiêng pháp tuyến → méo phản chiếu.
  Phản chiếu = căn phòng chụp SẴN một lần từ điểm (0; 1,3; 0) thành ảnh 3 × 2 mặt 512 px (`assets/maps/pool/reflect.png`, `core/cubemap.py`, `game/pool_capture.py`), tra bằng tia chiếu hộp (sửa lệch tâm). Fresnel + thân nước gần đen, ngọc lục bảo sát thành hồ / bậc.
  Khói súng, đạn bay và súng KHÔNG in xuống nước (người dùng chọn "chỉ căn phòng").
- Người chơi (`core/terrain.py`, `game/player.py`): xuống hồ bằng bậc (bước xuống ≤ 0,2 m không tính là rơi), rơi từ mép hồ 0,62 m (đi qua đúng cơ chế chạm đất của cú nhảy: lún camera, `Player.landed`), đáy hồ bị thành hồ chặn trừ khi nhảy (cao 0,93 m) hoặc leo bậc, cột và tường đẩy trượt dọc, cửa sổ có rào vô hình (đạn vẫn bay ra ngoài).
  Camera mượt khi bước lên / xuống bậc (`step_offset`, `PlayerParams.step_smooth`). Nước KHÔNG phản ứng với người chơi (không gợn, không tiếng): người dùng chọn vậy.
- Đạn (`game/combat.py` `_on_hit`): trúng nước (`owner.is_water`) → một vòng sóng, không lỗ đạn, không tiếng rơi đất; trúng tường / sàn / trần → lỗ đạn như cũ; bay ra cửa sổ → hết tuổi thọ 3 s, không lỗi.
- Súng và tay: nắng lấy từ `look_frame.y` (phần mặt trời tới được người chơi, tia CPU vào hộp, mượt 0,15 s); ánh NỀN lấy từ lưới nướng sẵn `ambient.json` (ánh trời + nảy, không nắng trực tiếp, trên mặt sàn mỗi 1 m, ở độ cao 1,4 m, `core/poolmap.py` `AmbientGrid`),
  nội suy tại chỗ người chơi và đưa vào `look_ambient_up / down` (mảng PTA sửa tại chỗ mỗi khung, `FrameLight.set_local_light`). Súng sáng trong mảng nắng, tối đi cùng phòng ở góc tối, hết viền trắng. Thanh F1 `look.ambient_*` vì vậy chỉ còn tác dụng trên `--map flat`.
- Màu: "ở giữa": `LensData.saturation` 0,70 → 0,88, `tint` (1; 0,99; 0,95), `noise` 0,030 → 0,024; viền tối, nhiễu, bloom giữ nguyên. `LookData.exposure` 1,0 → 1,7.

## Chạy và nướng lại
- Chạy: `run.bat` (mặc định map hồ). `--map flat` = nền trắng phẳng cũ (để so FPS). `--rebake` ép nướng lại + chụp lại.
- Lần đầu hoặc khi đổi `MapData` / nắng (`sun_dir`, `sun_color`, `sky_irradiance`): game TỰ nướng (~36 s, in `[map] ...`) rồi chụp phản chiếu (~2 s). Nướng cần numpy (đã vào `requirements.txt`); lúc chơi bình thường không nạp numpy.
- Đổi độ phơi sáng (`look.exposure`, `lens.exposure_*`, `auto_exposure`) hay màu sương: chỉ cần chụp lại phản chiếu (tự làm ở lần mở sau, vì `reflect_key` có các số đó); ánh sáng nướng không đổi. Bảng F1 sửa phơi sáng thì tường đổi ngay, phản chiếu trong nước chỉ đổi sau lần mở sau.
- Muốn commit file nướng: chạy `tools\build\bake_pool.py` với `--defaults` (không có chỉnh `user_params.json` ở nắng / ống kính), rồi commit `assets/maps/pool/*`.
- F1: nhóm "Nước hồ bơi" và "Sóng khi đạn trúng nước" (màu thân nước, độ gợn, sóng đạn...). Nắng chỉnh trong F1 chỉ đổi ánh sáng của SÚNG và lỗ đạn, KHÔNG đổi mảng nắng trên tường (nướng sẵn).

## Số đo (máy này: UHD 620, 1366 × 768, tắt vsync, M4, `g8_perf.py`)
| Tình huống | Phòng hồ bơi | Nền phẳng cũ |
|---|---|---|
| đứng yên | 137,9 | 157,3 |
| ngắm | 140,2 | 149,1 |
| bắn liên tục | 94,6 (1% thấp 72) | 100,9 (1% thấp 80) |
| nạp đạn | 133,0 | 145,6 |
| chạy nước rút | 155,7 | 162,1 |
Glock trên map hồ: đứng yên 146,6, ngắm 142,4, bắn liên tục 125,1, nạp 143,4, chạy 149,9. Phòng tốn khoảng 0,9 ms mỗi khung hình. Cú giật ~32 FPS lúc bắt đầu bắn có cả ở nền phẳng (36), không phải do map.

## Chọn lựa đã bỏ (người dùng chốt, không làm lại khi chưa hỏi)
Khúc xạ / nhìn xuyên nước; phản chiếu vẽ lại mỗi khung (chưa dựng, chưa đo); nước phản ứng với người chơi; nắng đổi theo giờ; bóng đổ động; kính cửa sổ; bia và luật chơi.

## Giới hạn đã biết
- Phản chiếu lệch tâm: vật gần mặt nước nhưng xa tường (cột, bậc) lệch vài chục cm trong nước. Tay vịn đặt cách tường bắc 0,35 m nên gần đúng.
- Tay súng nhận ánh nền theo lưới 1 m (một lớp ở độ cao 1,4 m, trộn lên / xuống theo pháp tuyến) và mặt trời có thấy hay không; không nhận màu nảy theo hướng từng mặt.
- Khói súng đi xuyên tường (chưa va); mặt đất khói vẫn ở y = 0.
- Ảnh ánh sáng 8 bit gamma 2: chưa thấy vạch bậc, chưa đo.
- Bầu trời chỉ là vòm màu + quầng mặt trời; ngoài cửa sổ không có mặt đất / biển.
- Tiếng nước khi đạn trúng: CHƯA CÓ trong game. 3 bản nháp ElevenLabs V3 (7/11/2026, prompt mục 40-42 của `assets/sounds/source/elevenlabs/PROMPTS.txt`) nằm ở `assets/review/water/`: `water_splash_a` (đạn chạm mặt hồ trong sảnh gạch), `water_splash_b` (vật nhỏ rơi nước êm, có tiếng sóng vỗ vào gạch), `water_bullet_c` (đạn xé nước, khô, gần). Người dùng nghe và chọn; sau khi duyệt: dựng thành wav như các tiếng foley (`tools/build/prep_*.py`), thêm đường dẫn + âm lượng vào `AudioData`, gắn `Game.pool.water.on_splash = foley.on_water_impact` (nhớ trễ theo khoảng cách như `on_impact`). Chưa kiểm xem Claude Desktop có phát được mp3 trong chat hay không: nghe bằng cách mở file.

## Sửa theo góp ý của người dùng (7/11/2026, sau lần commit đầu)
1. **Viền trắng quanh súng ở góc tối nhất.** Nguyên nhân đo được: súng dùng ánh nền CỐ ĐỊNH (`LookData.ambient_up` 0,27) dù tường quanh nó gần đen, và phản chiếu viền kim loại cộng `ambient × 6`. Sửa: lưới ánh nền nướng sẵn (xem trên). Đo: ánh nền ở góc tối 0,058, dưới cửa sổ 0,191 (cũ: 0,27 mọi nơi). Kiểm: `pool_check.py`.
2. **Ngắm trước / ngắm sau lệch nhau khi súng bị chuột đẩy ra xa tâm (M4), và không thấy ngắm trước của Glock.**
   - M4: các tư thế bị CỘNG góc và CỘNG dịch vào một nút, nên phần dịch của tư thế ngắm (ADS, 0,2-0,5 m) không xoay theo khi súng quay quanh mắt: ngắm lệch 0,4° ở độ lệch 1,5° và 3,1° ở 10° (mắt chỉ cách ngắm sau 0,18 m). Sửa: nút `aim` mới là CHA của nút `sway` (`Viewmodel.update(..., aim=(free_aim, free_look))`):
     xoay cả khối súng quanh mắt, phần dịch của tư thế `aim` (bàn tay, vị trí nghỉ) tắt dần khi ngắm (`core/sway.py` `aim_translation_weight`). Đạn theo nòng là hợp của hai phép quay (`barrel_view_dir(base_pose, ..., then=aim_pose)`). Đo trên cây nút thật: 0,0° ở mọi độ lệch tới 15°; phép đo sống 0,2° không đổi theo độ lệch (đó là rung thở).
     Hệ quả nhỏ: lúc cầm súng ngang hông, vị trí nghỉ của súng cũng xoay theo vùng tự do (tối đa ~3 cm ở mép vùng): đúng hơn trước, nhưng là đổi cảm giác nhỏ; chỉnh bằng F1 nhóm "Tư thế cầm súng" nếu không hợp.
   - Glock: điểm ngắm sau do công cụ đo đặt thấp hơn đỉnh hai cánh 3,5 mm, trong khi khe giữa chỉ sâu 2,3 mm: đường ngắm xuyên qua thân slide, đầu ruồi nằm khuất. Sửa: điểm ngắm sau ở giữa khe (y −0,0203). Thêm: mắt cách ngắm sau 0,50 → 0,38 m để đầu ruồi 2 mm không chỉ còn vài điểm ảnh (chỉnh trên F1 mục "Khi ngắm" nếu muốn).
   - Kiểm: `tests/test_sights.py` (21 bài, cả hai khẩu), `pool_check.py --gun m4|glock`, ảnh `tools\measure\ads_shots.py`.
3. **Tường ở cửa sổ mỏng như tờ giấy.** Mỗi mảnh tường phía đông chỉ có đúng một mặt (mặt trong): bệ, trán và hai thanh bên của lỗ cửa sổ không được vẽ, vì hộp rào vô hình lấp lỗ bị coi là vật rắn khi xét "mặt này có tiếp xúc không khí không". Sửa `is_air`. Thêm 16 mặt (4 cửa sổ × 4). Đã nâng `BAKE_VERSION` lên 2 để file nướng cũ bị bỏ. Kiểm: `test_every_window_hole_shows_its_full_wall_thickness`.
