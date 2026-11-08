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
  Caustics (G11, làm lại 7/11/2026 theo ảnh người dùng; `core/caustics.py`, `game/caustics.py`, `assets/shaders/caustics.*`, `pool_waves.glsl`, `tests/test_caustics.py`): CHIẾU LƯỚI TIA mỗi khung kiểu WebGL Water (Evan Wallace). Một lưới tam giác phủ mặt nước (vẽ bằng instancing: một dải × số hàng), mỗi đỉnh khúc xạ nắng qua gợn nhỏ + sóng mô phỏng rồi rơi xuống đáy dốc; độ sáng = diện tích lúc nước phẳng / diện tích nơi rơi (dFdx/dFdy), cộng dồn vào texture số thực 16 bit trên mặt bằng hồ (nới rộng về phía tây, nơi nắng đi tới, để thành hồ tra được), có mipmap. Vì ánh sáng ở một điểm đáy là TỔNG mọi tia rơi vào đó nên vân là mắt lưới KHÉP KÍN; bản G10 (12 sóng, 1/|det| tính tại chỗ) cho sợi rối hở là sai về bản chất. Gợn nhỏ: 16 sóng dải hẹp (bước sóng 0,56 → 0,21 m quanh `wave_size` 0,35 m, cao rms `wave_height` 3 mm, tán sắc mao dẫn–trọng lực × `wave_speed` 0,4); CHÍNH các gợn này bẻ cong hình gạch dưới nước (`wave_bend` 2,5, ron gạch méo như ảnh) và một chút phản chiếu (`wave_mirror`). Đạn / lội làm vân vỡ và méo tại chỗ (`caustic_sim`; kiểm bằng ảnh A/B gợn đứng yên). Vân ngả trắng (`caustic_white`), gạch xanh lam đậm (`basin_color` 0,14/0,36/1,0, nước nuốt đỏ rồi lục). Nắng vàng cam của phòng làm vân hơi ngả lục ở chỗ nông: đó là màu nắng, không phải lỗi. F2 "Vệt sáng đáy hồ": Tắt / Vừa (lưới 256×512, texture 1024) / Cao (384×768, 2048). Chi phí đo A/B cùng tiến trình, cắm sạc, góc xuất phát: Cao +0,5–1,3 ms, Vừa +0,5–0,6 ms. Thành hồ chỉ GẦN ĐÚNG (tra vân của đáy theo tia nắng phẳng, `caustic_wall` 0,7). Bậc thang dùng chung vân của đáy. Nắng lấp lánh trên sóng (`glint_*`).
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
## G12: xuống chỗ sâu, camera dưới nước, ống kính ướt (7/11/2026; kế hoạch + bản chốt: `docs/sessions/G12.md`; skill `underwater-camera`)
- Bỏ "dây chặn" ngang ngực của G10 (`core/terrain.py` không còn `wade`): đi bộ xuống hết dốc tới đáy 2 m, mắt ở −0,44 (0,32 m dưới mặt nước). Đầu chìm thì đi chậm `SplashData.under_slow` 0,38 (đo trong game: 1,69 m/s, ngang ngực 2,45, bờ 4,31). Không bơi, không thở.
- Ống kính có một "ô kính" nhỏ (nửa cao `UnderwaterData.port_half` 5 cm). Pixel ở ndc (x, y) của ảnh dựng nhìn qua điểm mắt + right·x·aspect·h + up·y·h trên ô kính; điểm đó dưới mặt nước (mặt nước tại mắt = mức tĩnh + sóng nền giải tích, `core/underwater.py`) thì pixel "ướt".
  Camera thế giới không nghiêng nên vạch nước là đường ngang trong ảnh dựng ở y = −c / b; mắt cách mặt nước dưới 5 cm thì khung TÁCH ĐÔI. MỌI shader (phòng, nước, lòng hồ, súng, bụi, giọt nước) và ống kính tính cùng một hàm `port_h` (`assets/shaders/underwater.glsl`) nên ranh giới khớp nhau; ống kính cong thì vạch nước cong theo (như GoPro thật).
- Một lần dựng, không camera thứ hai. Pixel ướt: sương nước kiểu hiển thị `c·T + màu_xa·(1 − T)`, T = exp(−(hấp thụ + đục)·d) (`turbidity` 0,32/m: mất nửa ở 2,2 m). Lòng hồ dựng thành lưới thật (`poolmap.basin_faces` + `ramp_quad`, 22 mặt; tô bằng `basin_common.glsl shade_basin`, cùng cách tô với đáy nhìn qua mặt nước từ trên), chỉ vẽ khi có pixel ướt (vài khung đầu vẽ ẩn để biên dịch sẵn shader).
  Mặt nước nhìn từ dưới (`water.frag underside`): khúc xạ ra không khí trong cửa sổ Snell (căn phòng chụp sẵn) và phản xạ toàn phần ngoài cửa sổ (lòng hồ dò bằng `trace_basin`), Fresnel phía không khí. Pixel ướt khi mắt còn ở trên: tia đi thẳng trong nước tới đáy. Pixel khô khi mắt vừa chìm: thấy căn phòng (ảnh chụp sẵn) thẳng theo tia.
- BẪY đã gặp: mắt cách mặt nước 2 cm thì mặt cắt gần 0,1 m của camera xén mất mặt nước ngay trước mắt (một vạch thẳng thứ hai trong ảnh). Sửa: `clip_plane_near` = 1 cm khi mắt trong vòng 0,3 m quanh mặt nước, 0,1 m lúc khác.
- Chìm hẳn: hình phóng to `zoom` 1,22 và cong rìa thêm `warp` 0,18, chuyển trong `zoom_time` 0,35 s; bụi trong nắng ẩn. Vạch nước có "meniscus" (lõi tối, viền sáng phía khô) và gợn `wobble` 2,5 mm (+6 mm mỗi m/s đi).
- Trồi lên: ống kính ướt (màng nước chảy + giọt khúc xạ; `core/wetlens.py`) ĐÃ XOÁ HẲN 8/11/2026 theo yêu cầu người dùng (mã, shader, test, dòng F1 / F2, thông số `film_*` / `drop_*`). Trồi lên thì ống kính sạch ngay; vạch lằn nước (meniscus) lúc mặt nước cắt ngang khung và phóng to khi chìm hẳn vẫn còn. File `user_graphics.json` / `user_params.json` cũ còn khoá `wetlens` / `film_*` thì bị bỏ qua (có test).
- Đầu chìm: bóp cò không bắn, lần bấm bị bỏ (không bắn bù khi trồi lên), dòng nhỏ "Không thể bắn ở đây" ở cạnh dưới 1,6 s (`Notice` ở dưới). Nạp đạn vẫn được.
- Âm thanh: OpenAL của Panda KHÔNG lọc được (`configure_filters` trả False; FMOD Ex lọc được nhưng là thư viện 2014, Panda 1.10 chưa có bản nối với FMOD mới). 6 bản ElevenLabs sinh lần đầu bị người dùng loại (7/11/2026: "không ổn"). Người dùng chọn LỌC SẴN bằng numpy, "nghẹt nhiều", nền làm từ tiếng nền phòng, KHÔNG có tiếng riêng lúc chìm / trồi:
  `tools\build\prep_underwater.py --apply` dựng (numpy chỉ lúc dựng, game không import numpy) `assets/sounds/foley_under/<tên>.wav` cho MỌI tiếng foley (bước chân, nạp đạn, tiếng nước...) bằng lọc thông thấp zero-phase trong miền tần số (Butterworth bậc 4, cắt 400 Hz: tâm phổ từ ~5 kHz xuống ~350 Hz; kéo lại RMS còn 0,5 lần bản gốc) và `assets/sounds/under_ambience.wav` từ `pool_ambience.wav` (lọc vòng ở 220 Hz nên vòng lặp vẫn mượt, thêm tiếng ù 46/71/103 Hz tròn số chu kỳ, tiếng ì nâu lặp đúng, 9 bọt khí nhỏ không vắt qua chỗ nối).
  Game: `Foley.under` (đặt mỗi khung theo `eye_under`) chọn bản nghẹt của cùng nhóm trong `_Bank`; thiếu thư mục thì giữ bản thường. `UnderwaterAudio` chuyển dần (0,25 s) tiếng nền phòng <-> tiếng dưới nước. Âm lượng: F1 "Dưới nước: tiếng nền" (`under_ambience_volume` 0,45) và "chuyển tiếng nền". Đổi độ nghẹt thì chạy lại công cụ với `--cutoff` / `--level` (không có thanh trượt: là file dựng sẵn).
  Tiếng đang phát dở lúc chìm không đổi giữa chừng (đều ngắn). Kiểm: `tests/test_prep_underwater.py` (9 bài), `tools\measure\water_audio_check.py` (thêm 6 mục G12 bằng game thật có tiếng). CHƯA có ai nghe: người dùng nghe và chỉnh `--cutoff` nếu chưa ưng.
- F2: dòng "Dưới nước" (Đơn giản: không vệt sáng trên lòng hồ, mặt nước nhìn từ dưới phẳng / Đầy đủ). F1 nhóm "Ánh sáng": "Dưới nước, khung tách đôi"; "Dưới đáy: tốc độ khi đầu chìm" ở nhóm lội nước. (Dòng "Ống kính ướt khi trồi lên" của F1 / F2 đã xoá 8/11/2026.)
- Đo: `g8_perf.py --level 2` thêm "dưới nước" / "nhìn lên mặt nước" / "nửa chìm": M4 222 / 193 / 254 FPS, Glock 236 / 193 / 251 (cắm sạc, 1366×768), 18/18 ĐẠT. `pool_check.py` thêm 12 mục G12 (qua hết; đổi F2 dưới nước khung chậm nhất 15,3 ms).
  Ảnh `pool_shots.py` góc `uw_level`, `uw_up`, `uw_wall`, `uw_half`, `uw_half_down`, `surfaced` (`shots\g9_*_g12.png`; `surfaced_late` đã bỏ cùng ống kính ướt).

## G14: thân không xuyên thành hồ, thang hồ bơi thật (7/11/2026; kế hoạch + bản chốt: `docs/sessions/G14.md`)
- LỖI người dùng báo: ép nhân vật vào thành hồ (cả bốn mặt) thì camera nhìn xuyên qua thành, súng thò ra ngoài, nhưng không đi xuyên được. Nguyên nhân ĐO ĐƯỢC (ép phím tiến thật, không đặt vị trí): tâm nhân vật dừng cách mặt phẳng thành 0,000 m thay vì 0,30 m, mắt nằm đúng trên thành. `resolve_move` (`core/terrain.py`) chặn "gờ" (mặt bờ cao hơn `step_up`) chỉ bằng ĐIỂM tâm; cột và tường phòng dùng đẩy theo vòng tròn nên không bị. Đặt vị trí cách thành 5 mm KHÔNG tái hiện được lỗi: phải đi thật.
- Sửa: mặt trên nào cao hơn `y + step_up` thì đẩy cả VÒNG TRÒN thân ra khỏi hình chiếu của nó (cùng `push_out_of_box` như tường / cột), bỏ thành phần vận tốc đâm vào. Người lỡ đè lên gờ (rơi từ bờ xuống sát mép) được đẩy ra từ từ, không kẹt. Nhảy ra khỏi hồ và leo bậc (phía nam, cầu thang phía bắc) không đổi. Kiểm: `tests/test_terrain.py` (3 thành sâu × 4 tốc độ, góc, kẹt, nhảy, thang), `pool_check.py` (3 mục: dừng cách 0,300 m).
- Thang (`core/poolmap.py` `rail_meshes`, `ladder_x/z`, `rung_heights`): hai tay vịn cách nhau `ladder_width` 0,6 m (trước: 2,5 m, đứng hai bên bậc thang bắc đã tắt), căn giữa chỗ cũ; từ bờ bắc lên 0,65 m, vòm bán kính ~0,23 m qua mép hồ, rồi THẲNG xuống sát thành bắc (cách `ladder_standoff` 0,10 m) tới đáy −2,12 m; `ladder_rungs` 5 bậc ngang chìm từ 0,30 m dưới mặt nước tới 0,10 m trên đáy (cách nhau 0,4 m). Thân dừng cách thành 0,30 m nên không chạm thang.
- Bóng nắng trên bờ, nướng sẵn: `Box.caster` = hộp không vẽ, không va chạm, chỉ chắn nắng khi nướng (`lightbake.Occluders`), xếp quanh phần thang TRÊN mặt nước (mỗi hộp ôm 3 điểm ống, 18 hộp); dưới nước không bóng (người dùng chọn: không che vệt sáng đáy hồ). Nắng chiếu tới sàn bờ bắc (4476 / 4800 điểm sáng) và thang đổi 344 điểm. `BAKE_VERSION` = 3 nên game tự nướng lại (37 s lần đầu); ảnh nướng trong `assets/maps/pool/` đổi theo.
- Ảnh: `pool_shots.py` góc `ladder_front`, `ladder_wide`, `ladder_bank`, `ladder_deck`, `ladder_side`. Hạn chế: nhìn từ trên mặt nước, phần chân thang dưới nước bị mặt nước (đục, tính khúc xạ bằng hộp) che, như mọi vật khác trong hồ.
