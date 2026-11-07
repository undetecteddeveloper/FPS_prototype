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

## G10: nước trong, sóng mô phỏng, hồ sâu 2 m, tia nắng, phím F2 (7/11/2026)
Kế hoạch + bản chốt: `docs/sessions/G10.md`. Skill kỹ thuật (nguồn, bẫy, số đo): `.claude/skills/pool-water-sim/SKILL.md`.
- Mức đồ hoạ (`weapon_data.GRAPHICS_LEVELS`, `core/graphics.py`): **F2** đổi Thấp / Vừa / Cao ngay khi chơi, có chữ báo 2 s. Đổi chỉ đổi uniform và bật/tắt buffer, không biên dịch lại shader: đổi mức ≤ 2 ms, khung chậm nhất sau đó ≤ 10 ms.
  Thấp = đúng như G9 (gương tối, vòng sóng vẽ sẵn, không tia nắng). Vừa = sóng 128×256, tia nắng 8 mẫu. Cao (mặc định) = sóng 256×512, tia nắng 16 mẫu.
- Sóng (Vừa/Cao): lưới độ cao trên GPU (`game/water_sim.py`, `water_sim.frag`, toán `core/watersim.py`), phương trình sóng có tắt dần, bước cố định 120 Hz, tối đa 2 bước/khung, thành hồ phản xạ sóng.
  Texture PHẢI là số thực 32 bit: 16 bit lệch 15-58 % sau 40-75 bước. GPU khớp bản Python tới 0,0000 mm (thí nghiệm đọc ngược). Đạn: ấn mặt nước `bullet_push` (−15 mm, bán kính 6 cm), là DỊCH CHỖ (cộng vào cả hai mức thời gian; chỉ cộng vào "bây giờ" thì thành cú đẩy vận tốc, 1 cm thành 9 cm).
- Nước trong (Vừa/Cao), `water.frag`: tia nhìn khúc xạ (Snell) được dò bằng toán vào lòng hồ (hộp lòng hồ từ trong ra + các hộp bậc + mặt dốc), KHÔNG vẽ thêm lượt nào. Đáy hồ chỉ thấy qua nước nên không nướng:
  ánh sáng lấy từ lưới ánh nền nướng sẵn (`ambient.json`, đưa lên GPU thành texture), tối ở góc, nước nuốt màu theo đường đi (`absorption`, đỏ mất trước), màu gạch đáy `basin_color` (xanh hồ bơi; có vạch màu ở mép nước).
  Caustics: lưới sáng (hai lớp nhân nhau + uốn toạ độ để khỏi lặp), chỉ mạnh nơi nắng thật sự lọt xuống (nắng khúc xạ, kiểm điểm vào mặt nước có thấy mặt trời qua cửa sổ không), sóng mô phỏng gom / tản nắng (laplacian). Nắng lấp lánh trên sóng (`glint_*`).
- Nắng qua cửa sổ bằng toán (`sun_window.glsl`, gương Python `core/poolmap.py sun_visible`): khớp phép dò tia trên mọi hộp của phòng ở > 99,5 % của 3 000 điểm ngẫu nhiên (`tests/test_graphics.py`).
  Tia nắng trong không khí: mỗi điểm ảnh của phòng và nước đi 8-16 bước từ mắt tới nó, cộng phần không khí có nắng (pha Henyey-Greenstein, bụi trôi chậm). Số trong F1 nhóm "Tia nắng trong không khí".
- Hồ sâu hơn (người dùng 7/11/2026): đầu nam 0,5 m (bậc + thềm phẳng tới z = −4), dốc tới 2,0 m ở z = +6, phẳng sâu 2 m tới đầu bắc. Mặt dốc KHÔNG phải hộp: `PoolMap.ramp`, đi lại qua `core/terrain.py` (ramps), vẽ trong `water.frag`.
  Lội tới chỗ nước sâu `wade_depth` 1,25 m (ngang ngực, z ≈ 1,0) thì bị chặn như dây phao; từ bờ cũng không vào được chỗ sâu (chưa có bơi). Lưới an toàn: ai lọt vào chỗ sâu thì đứng ở độ sâu ngang ngực và lội về được. Bỏ bậc phía bắc (`MapData.north_steps`), hai tay vịn thành thang. Đổi hình học thì game tự nướng lại (~30 s).
- Đo (máy chạy PIN, Core 7 150U + Intel Graphics, 1366×768, vsync tắt; `g8_perf.py --level`): M4 mức Cao đứng yên 126, bắn 119 (thấp nhất 74,8), nạp 126 (thấp nhất 57,8), chạy 118; Vừa 150-200; Thấp ~157-275. Glock Cao: 114-129.
  Giây đầu sau khi mở game đôi khi ~30 FPS ở mức Vừa/Cao rồi nhanh dần về bình thường (giống GPU tăng xung; lúc có lúc không, chưa chứng minh do G10); đo lại khi cắm sạc.
- Kiểm: `pool_check.py` (thêm: sóng mô phỏng có thật, đạn ấn mặt nước, nhìn thẳng xuống thấy gạch đáy [độ tương phản Cao 0,17-0,19 so với Thấp 0,004], đổi F2 không giật, lội dừng ở vạch sâu, không vào được chỗ sâu từ bờ),
  `tests/test_watersim.py`, `tests/test_graphics.py`, `tests/test_terrain.py`; ảnh: `pool_shots.py --only spawn,down,water,deep,slope,wade [--level 0|1|2] [--set water.caustic_scale=0.6]`.
- Phần sau: xem mục G10 phần 2 bên dưới; còn lại tiếng nước ElevenLabs.

## G10 phần 2: lội nước, giọt nước, sàn ướt, vết chân, bụi, phản chiếu lên súng, tia nắng chính xác (7/11/2026)
- Lội (`core/splash.py`, `Player.water_depth`): đi chậm theo độ ngập (`splash.wade_slow` 0,55 ở ngang ngực, tuyến tính); đo trong game: bờ 4,31 m/s, nước tới gối 3,57, ngang ngực 2,45.
  Chân đẩy mặt nước mỗi `wake_spacing` 0,32 m (sóng mô phỏng thật), văng vài giọt; nhảy / rơi xuống nước: lõm sâu + vương miện giọt (`land_*`). Lội thì tắt tiếng bước chân trên gạch (tiếng nước: phần âm thanh sau).
- Giọt nước (`game/splash.py`, `splash.vert|frag`): một lần vẽ, vệt kéo dài theo vận tốc (như màn trập 25 ms), sáng vàng trong vệt nắng; giọt rơi lại tạo gợn nhỏ trong mô phỏng. Đạn trúng: 16 giọt; số giọt nhân theo mức đồ hoạ (Thấp 0, Vừa 0,6, Cao 1).
- Sàn ướt (`room.frag`, mức Vừa/Cao): vũng nước loang lổ (nhiễu, nhiều hơn sát mép hồ), gạch ướt tối hơn (Lagarde), vũng phản chiếu căn phòng (cùng ảnh chụp của nước, `cube_reflect.glsl`, Fresnel).
  Vết chân ướt (`core/footprints.py`): ra khỏi nước thì 12 s đầu để lại vết luân phiên trái / phải mỗi 0,62 m, nhạt dần theo độ khô của chân; vết khô sau 25 s. Vòng 24 vết trong uniform.
- Súng (mức Vừa/Cao): kim loại phản chiếu căn phòng chụp sẵn thay cho ước lượng từ ánh nền (`vm_env`, `Viewmodel.set_env`); tối đi ở chỗ phòng tối.
- Bụi (mức Cao, `game/dust.py`, `dust.vert|frag`): 600 hạt, vị trí tính hoàn toàn trên GPU từ hạt giống + đồng hồ, quấn trong hộp 7 m quanh mắt; chỉ hiện trong vệt nắng. Khu xuất phát phía nam KHÔNG có nắng (đúng vật lý); giữa phòng (−4; 0) ~25 % không khí có nắng.
- Tia nắng giờ tính CHÍNH XÁC đoạn có nắng của tia nhìn (mỗi cửa sổ một khoảng [t0, t1] bằng toán tuyến tính; `core/poolmap.py sunlit_segments` khớp cách đi từng 1 cm, `tests/test_graphics.py`); chỉ bụi lấy mẫu (Vừa 1, Cao 3 mẫu mỗi đoạn).
  Đo A/B trong cùng tiến trình: cách đi 16 bước tốn 7 ms/khung, cách mới ~1 ms. Cả mức Cao giờ 4,1-4,9 ms/khung (trước 8-10 ms); g8_perf mức Cao 145-310 FPS trung bình. Python mỗi khung ~0,7 ms.
- Chi phí từng hiệu ứng (tắt từng cái, cùng tiến trình): sàn ướt, phản chiếu súng, bụi, caustics, khúc xạ đều < 0,5 ms (lẫn trong nhiễu).
- Kiểm: `pool_check.py` thêm 5 mục (giọt khi đạn trúng, lội chậm theo độ sâu, lội đẩy sóng, rơi xuống nước té nước); `tests/test_splash.py`, `tests/test_footprints.py`.
  Bẫy đo: không vsync game chạy 400+ FPS, nên bài kiểm phải chờ theo THỜI GIAN / sự kiện (rơi 1,2 m cần 0,5 s, không phải 60 khung); đọc sóng ngay sau bước mô phỏng đầu tiên.
  Công cụ chụp nhảy góc ngay sau một góc nhìn thẳng mặt trời có thể còn dư ảnh của ống kính (quầng sáng giữa khung): chụp lại / chờ lâu hơn.
- `pool_shots.py`: góc `deck`, `prints`, `beam`, `beam2`; cờ `--prints`, `--ring-wait`, `--no-gun-env`, `--no-dust`. `g8_perf.py --at x,z,yaw` (vd `3,5,75` = giữa vệt nắng nhìn mặt trời).

## G10: bảng đồ hoạ F2 + khử răng cưa (7/11/2026, yêu cầu người dùng)
- F2 mở bảng (`game/graphics_panel.py`; dữ liệu + toán thuần `core/graphics.py`: `GraphicsSettings`, `OPTIONS`, `resolve`, `preset_of`, `cycle`). Dòng: Mức chung (Thấp / Vừa / Cao; đổi riêng một dòng thì thành "Tuỳ chỉnh"),
  Khử răng cưa (Tắt / 2x / 4x), Sóng nước mô phỏng, Nước trong, Vệt sáng đáy hồ, Nắng lấp lánh, Tia nắng, Bụi, Giọt nước, Sàn ướt, Súng phản chiếu, Hiện FPS.
  Phím mũi tên chọn / đổi, chuột trái = lựa chọn sau, chuột phải = lựa chọn trước, F2 / Esc đóng. Đổi là áp dụng ngay; đóng bảng thì lưu `user_graphics.json` (gitignore; `--defaults` bỏ qua file này). Mức chung không đổi khử răng cưa / hiện FPS.
- Khử răng cưa = MSAA trên buffer cảnh của ống kính (`Lens(samples=)`, `FrameBufferProperties.set_multisamples`): thế giới và súng vẽ chung buffer đó nên cùng được khử. Đổi = dựng lại buffer ống kính (3-4 ms) và chuyển vùng vẽ của mọi khẩu sang buffer mới
  (`Viewmodel.move_to_output` giữ trạng thái bật / tắt của khẩu đang cất). LẦN ĐẦU bật MSAA khựng một khung ~400 ms (driver), các lần sau ~27 ms. Chỉ khử cạnh hình học (MSAA), không khử nhiễu trong shader.
  Chi phí (cùng tiến trình, mức Cao): 2x +1,5 ms, 4x +3,3 ms mỗi khung (4x vẫn 134-148 FPS trung bình).
- Kiểm: `tools\measure\graphics_panel_check.py` (19 mục: buffer thật có 2 / 4 mẫu, súng sang buffer mới, mọi dòng đổi và quay vòng, lưu file); `tests/test_graphics.py` (mức chung qua lại, "Tuỳ chỉnh", file hỏng thì về mặc định).
- Bẫy: `Text` của Ursina coi `<` là đầu thẻ định dạng: chuỗi "< Cao >" làm lỗi IndexError trong `align`; dùng "‹ ›".

## G10: tiếng nước (người dùng chốt 7/11/2026)
- Người dùng nghe và CHỈ GIỮ 3 bản ElevenLabs V3 (prompt `PROMPTS.txt` mục 45, 47, 51): `wade_step_deep` cho MỌI bước lội (nước sâu, chạy, "lặn"), `water_jump_a` cho nhảy / rơi xuống hồ, `pool_ambience_loop` làm tiếng nền. 9 bản còn lại (và tiếng đạn trúng nước, nước nhỏ giọt) đã XOÁ cả file lẫn mã: đạn trúng nước giờ chỉ có sóng + giọt, không có tiếng.
  Còn trong `assets/review/water/` đúng 3 file đó (thư mục review bị gitignore). Dựng ra game: `.venv\Scripts\python.exe -X utf8 tools\build\prep_water_audio.py [--apply]` (giải mã mp3 bằng Panda3D, không cần ffmpeg) -> `assets/sounds/foley/wade_0.wav`, `water_land_0.wav`, `assets/sounds/pool_ambience.wav` (đã dựng, đã commit).
- HIỆU CHỈNH một bản thu cho mọi kiểu bước (`fps/game/foley.py` `_play_foot`, số trong F1 nhóm "Âm lượng" mục "Nước hồ bơi"):
  cao độ (tốc độ phát) từ `wade_pitch_shallow` 1,30 (nước ngang mắt cá, nhẹ và cao) xuống `wade_pitch_deep` 1,00 (ngang ngực, đúng bản thu, đầy tiếng) tuyến tính theo độ ngập (`wade_deep_ref` 1,25 m); âm lượng từ `wade_shallow_gain` 0,50 lên 1,0 cùng chiều;
  chạy: cao độ ×`wade_run_pitch` 1,25 (bước dồn, tiếng ngắn lại) và âm lượng ×`wade_run_gain` 1,15. 3 bản phát luân phiên cho nhóm này (đuôi vẩy nước 0,75 s không bị cắt khi bước dồn).
  Mức to nhỏ: bản thu to gấp 1,48 lần tiếng bước gạch ở cùng âm lượng (đo RMS, `prep_water_audio.py` in tỉ lệ) nên `wade_volume` 0,30 (≈ 1,3 lần bước gạch ở ngang ngực); tiếng nhảy nước nhỏ hơn bước (0,55 lần) nên `water_land_volume` 0,85; tiếng nền `ambience_volume` 0,30.
  Đo trong game: nông 1,20 / 0,21, ngang ngực 1,02 / 0,30, chạy nông 1,43 / 0,24 (tốc độ phát / âm lượng).
- Tiếng nền: file 11,63 s, ghép vòng bằng crossfade 0,6 s cuối vào đầu (đo: chênh lệch tại chỗ nối 0,011, nhỏ hơn chênh lệch trung vị giữa hai mẫu kề nhau 0,015; mức RMS không đổi quanh chỗ nối).
- Lội thì không còn tiếng bước gạch; lên bờ thì tiếng gạch trở lại. Nhóm tiếng tuỳ chọn: thiếu file thì im, không lỗi.
- Kiểm: `tools\measure\water_audio_check.py` (8 mục bằng game thật với file thật: tiếng nền lặp, một bản thu cho mọi bước, hiệu chỉnh nông / sâu / chạy, rơi xuống nước, tiếng gạch trở lại).

## Nạp đạn: bắn / ngắm / đổi súng được từ lúc súng về chỗ (người dùng báo 7/11/2026)
- Triệu chứng: sau khi nạp (cả M4 và Glock) phải chờ ~1,5 s mới bắn / ngắm / đổi súng được. Nguyên nhân đo được: KHÔNG có độ trễ trong mã (sau `done` hành động được sau 0,02 s), mà clip nạp còn chạy tiếp M4 0,73 / 0,60 s, Glock 0,47 / 0,57 s sau mốc `Clip.settle`
  (súng, băng đạn, cò đã về chỗ; phần đó chỉ là tay thu về, chuyển động khớp < 1 cm / khung), và suốt thời gian đó `Handling` còn bận. Sau khi băng đạn vào (`swap`) clip còn 1,63 s (M4) / 1,3 s (Glock): đúng con số ~1,5 s người dùng cảm thấy.
- Sửa (cùng cách với clip rút súng): `Handling` phát `('ready', key, tail)` thay `done` ở `Clip.settle − ReloadData.ready_lead` (không bao giờ trước lúc băng đạn vào chỗ); từ đó bắn / ngắm / đổi súng / nạp lại được, `Viewmodel` chạy tiếp phần đuôi, phát súng đầu tiên (Glock) cắt ngang đuôi, M4 vừa bắn vừa để đuôi chạy nốt.
  Mốc tiếng và rung của clip đều nằm trước `settle` nên không mất; cái đầu vẫn ngẩng lên đúng (cửa sổ nhìn xuống đóng từ trước `settle`). `ReloadData.ready_lead` (F1 nhóm "Nạp đạn": "Nạp xong: bắn sớm hơn", mặc định 0) cho kéo mốc sớm thêm tối đa 0,8 s.
  Đừng kéo nhiều với Glock: bắn sớm thì bàn tay trái bị kéo giật sang clip bắn (đo: lệch ~8 cm ở 0,1 s trước `settle`, ~22 cm ở 0,25 s trước). M4 không có clip bắn nên không giật, nhưng nạp cạn thì sớm hơn ~0,25 s là lúc tay còn đập tay kéo bolt.
- Kiểm: `tools\measure\reload_check.py [--gun m4|glock]` (12 mục bằng game thật, thao tác thật: mở khoá đúng lúc `settle`, bắn / ngắm trong 0,03 s, đuôi còn chạy, rồi về tư thế sẵn sàng, chỉ băng đạn đúng được hiện, đổi súng ngay được), `tests/test_handling.py`.