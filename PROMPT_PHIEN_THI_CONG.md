# Nhiệm vụ: xây FPS prototype bằng Ursina (cảm giác bắn kiểu Call of Duty: Modern Warfare 2019)

Thư mục dự án: `E:\ursina projects\FPS_prototype`. Hiện chỉ có hai file trong `guns\`. Chưa có code, chưa cài thư viện, chưa có git.
Người dùng không làm kỹ thuật: bạn tự quyết mọi việc kỹ thuật, chỉ hỏi khi có ≥2 hướng sản phẩm/thiết kế. Trả lời bằng tiếng Việt thường.

## 1. Mục tiêu
Một game FPS nhỏ làm nền cho dự án lớn hơn. Phải có đủ: **sway, recoil, accuracy (spread/bloom), reload, shooting, aim (ADS)**. Chất lượng của sáu thứ này quan trọng hơn mọi thứ khác. Không làm thêm tính năng ngoài danh sách (không menu, không multiplayer, không lưu game).

## 2. Quyết định đã chốt (đừng hỏi lại)
- Engine: **Ursina** (Python). Dùng **Python 3.13**, tạo venv trong dự án: `py -3.13 -m venv .venv`. KHÔNG dùng Python mặc định 3.15 (bản beta, panda3d chưa có bản cài).
- Phiên bản đã kiểm tra trên PyPI: ursina 8.3.0, panda3d 1.10.16, panda3d-gltf 1.3.0. Ghim vào `requirements.txt`.
- Vũ khí chính: **M4** từ `guns\m4_-_fps_weapon_animations_pack_v.1.glb` (Pack B). File `guns\animated_fps_hands_rifle_animation_pack.glb` (Pack A, ACR, 109 MB) **chưa dùng** ở phiên này; thiết kế code để sau này thêm súng thứ hai được (dữ liệu súng tách khỏi logic).
- Cảm giác: **CoD Modern Warfare 2019**: arcade hiện đại, recoil theo mẫu riêng của từng súng (hay lên và lệch phải), ADS gần như không tản đạn, hip-fire tản trong hình nón, ADS làm chậm di chuyển và hạ tầm nhìn.
- Đạn: **đạn bay có độ rơi, rơi nhẹ** (khác CoD 2019 thật vốn là hitscan; người dùng cố ý chọn vậy). Bắt đầu: tốc độ 500 m/s, g = 9,81, tức rơi ~0,1 m ở 75 m và ~0,45 m ở 150 m. Mọi số đều chỉnh được. Mỗi frame dò tia theo đoạn đạn vừa bay (swept raycast) để đạn nhanh không xuyên bia.
- Màn chơi: **trường bắn có bia**: làn bắn dài ≥ 200 m (để thấy đạn rơi), biển khoảng cách 10/25/50/100/150 m, bia đứng yên và bia chạy qua lại. Bia có phản hồi trúng (hit marker, nháy màu, lỗ đạn). Không có kẻ địch AI.

## 3. Dữ kiện đã đo từ file M4 (đã kiểm chứng bằng cách đọc JSON trong glb)
- Bộ xương 56 khớp; tay là mesh có skin; các phần súng (Main, Mag1, Mag2, Bolt, BoltCatch, Trigger, Safety, 2 viên đạn) là mesh KHÔNG skin, gắn làm con của các khớp, nên hoạt họa của chúng đi theo khớp. Có khớp `FPS_Camera_j_01`/node `FPS_Camera`.
- 5 animation: `Draw`, `Reload`, `Fire`, `Reload_Empty`, `Holster`. **Cả 5 nằm chung một dòng thời gian dài 10 giây, mỗi clip bắt đầu ở một mốc lệch** nên độ dài ghi trong file (3,67 s, 10 s, 8,33 s…) là sai. Khoảng thời gian thật (giây, ~30 fps):
  - Reload: 0,03 → 3,67 (≈3,6 s) | Reload_Empty: 3,70 → 7,50 (≈3,8 s) | Fire: 7,53 → 8,33 (≈0,8 s, 24 key) | Holster: 8,37 → 8,93 (≈0,57 s) | Draw: 8,97 → 10,0 (≈1,03 s).
  - Phải cắt đúng khoảng (dùng `Actor.play(name, fromFrame, toFrame)` hoặc tạo clip con) để không phải chờ phần đứng yên đầu clip.
- **Không có** Idle, Walk, Run, Sprint, ADS trong file. Idle/bob/sprint-pose/ADS làm bằng code (xem mục 5).
- `Fire` dài 0,8 s nên không lặp được ở tốc độ bắn tự động. Phần kick của từng phát bắn làm bằng lò xo bằng code; `Fire` chỉ dùng cho chuyển động bolt/tay khi bắn đơn hoặc tăng tốc phát.
- Vật liệu dùng `KHR_materials_pbrSpecularGlossiness`. Nếu panda3d-gltf không hiển thị đúng, hạ về chỉ dùng texture màu (diffuse).
- Giấy phép CC-BY 4.0: ghi công **BarcodeGames** (M4) trong file `CREDITS.txt` và trong game (dòng chữ nhỏ). Nếu sau này dùng Pack A: **Cransh**.

## 4. Rủi ro số 1: kiểm tra TRƯỚC khi viết gameplay (Giai đoạn 0)
Nạp glb bằng `from direct.actor.Actor import Actor` (cách tài liệu Ursina hướng dẫn). Phải chứng minh bằng ảnh chụp/lệnh chạy thật:
1. Tay và súng hiện đúng, đúng texture, không bị méo.
2. Các phần súng không skin (bolt, băng đạn, cò) **thật sự chuyển động theo animation**. Nếu không: thử `expose_joint`/`control_joint`; nếu vẫn không, tự đọc glb (pygltflib) và tự chạy animation; chọn cách đơn giản nhất chạy được và báo lại.
3. Từng clip chạy đúng khoảng thời gian ở mục 3.
4. Hiệu năng ≥ 60 FPS trên máy này.
Nếu không qua được, DỪNG và báo (kèm 2–3 lựa chọn), đừng lách.

## 5. Thiết kế hệ thống (mỗi thứ một module nhỏ, số liệu ở một chỗ duy nhất)
Cấu trúc gợi ý: `main.py`, `weapon_data.py` (toàn bộ thông số súng, dạng dataclass), `player.py`, `viewmodel.py`, `recoil.py`, `spread.py`, `sway.py`, `ballistics.py`, `targets.py`, `hud.py`, `debug_panel.py`, `CREDITS.txt`, `requirements.txt`. Phần toán thuần (spread, recoil, đạn rơi) phải kiểm thử được không cần mở cửa sổ (pytest).

Giá trị khởi điểm (mọi số đều là điểm bắt đầu để chỉnh; người dùng sẽ chỉnh bằng bảng debug):
- **Bắn**: tự động, ~750 phát/phút, băng 30 viên, dự trữ 150. Nhấn giữ chuột trái = bắn liên tục. Có thể phím chuyển tự động/bắn đơn.
- **Recoil**: gồm hai lớp riêng. (a) *Recoil của camera*: cộng vào góc nhìn theo **mẫu 30 bước của M4** (chủ yếu lên, lệch phải nhẹ, thêm nhiễu ngẫu nhiên ±10%); người chơi phải tự kéo chuột bù; sau khi ngừng bắn, hồi một phần (tham số `recovery`, bắt đầu 0,3, nguồn CoD 2019 về điểm này chưa xác nhận nên để chỉnh được). (b) *Kick của súng trên màn hình*: lò xo giảm chấn tác động lên vị trí và góc xoay của viewmodel, nhỏ hơn và nhanh hơn camera.
- **Accuracy**: góc tản = nền theo trạng thái + bloom cộng dồn theo từng phát, hồi theo thời gian. Nền bắt đầu: đứng 2,0°, đi 3,5°, nhảy/rơi 6°, ngồi ×0,7, ADS 0,1°. Mỗi phát cộng 0,25° (trần 4°), hồi 6°/s. Hướng đạn = hướng camera + lệch ngẫu nhiên trong hình nón theo góc tản. Tâm ngắm động chỉ hiện khi hip-fire, giãn theo góc tản; ẩn khi ADS.
- **Aim (ADS)**: giữ chuột phải, ~0,25 s để vào/ra; đưa viewmodel vào giữa màn hình (căn mắt ngắm với tâm, chỉnh offset bằng tay hoặc dựa trên khớp `FPS_Camera`), giảm FOV, giảm tốc độ nhìn và tốc độ đi (~60%), sway nhỏ lại. Bắt đầu bắn khi đang vào ADS thì phát đầu phải tản theo mức hiện tại của ADS, đúng như CoD.
- **Sway** (toàn bộ bằng code vì file không có Idle/Walk): (1) thở lúc đứng yên (đường cong Lissajous nhỏ); (2) lag theo chuột: súng trễ ngược hướng quay chuột, kéo về bằng lò xo; (3) bob khi đi/chạy theo nhịp bước; (4) tư thế sprint (súng hạ xuống/xoay) và **trễ sprint-to-fire** ~0,25 s; ADS giảm các thứ này xuống ~20%.
- **Reload**: phím R. `Reload` (còn đạn trong nòng) ≈3,6 s và `Reload_Empty` (băng cạn) ≈3,8 s. Hủy được bằng chuyển trạng thái khi cần (sprint cắt reload là hành vi CoD, mặc định bật). Số đạn chỉ cập nhật đúng thời điểm thay băng trong animation (chọn mốc theo clip), không phải đầu clip. Hết đạn thì tự reload khi bấm bắn.
- **Draw** khi vào game (clip `Draw`); `Holster` để sẵn cho phím đổi súng sau này.
- **Di chuyển**: WASD, Shift chạy nước rút, Ctrl/C ngồi, Space nhảy, chuột nhìn. Tự viết bộ điều khiển nhỏ nếu `FirstPersonController` của Ursina không đủ trạng thái; trạng thái di chuyển (đứng/đi/chạy/ngồi/rơi/ADS) là nguồn duy nhất cho spread, sway và tốc độ.
- **Bảng debug (F1)**: thanh trượt chỉnh trực tiếp mọi số ở trên và vẽ hình nón tản đạn; nút lưu/nạp bộ thông số. Đây là công cụ chính để người dùng tinh chỉnh cảm giác.
- **HUD**: tâm ngắm, số đạn (trong băng / dự trữ), hit marker, hiển thị FPS, khoảng cách tới bia vừa trúng.
- Âm thanh: không bắt buộc. Nếu thêm thì tự tạo âm đơn giản, không tải tài nguyên ngoài.

## 6. Giai đoạn và tiêu chí xong
Làm tuần tự, mỗi giai đoạn chạy game thật để kiểm, rồi commit.
- **G0** Môi trường + nạp glb + cắt clip đúng (mục 4).
- **G1** Người chơi + camera + trường bắn 200 m + viewmodel đứng yên đúng chỗ trước mặt camera.
- **G2** Bắn: nhịp bắn đúng RPM, đạn bay có độ rơi, trúng bia, đếm đạn, lỗ đạn, hit marker. Kiểm tra bằng số: bắn ngang tầm mắt vào bia 150 m, điểm trúng thấp hơn điểm ngắm ~0,45 m (±20%).
- **G3** Recoil (camera + súng) và accuracy (spread/bloom/tâm ngắm). Kiểm tra: bắn hết băng liên tục tạo mẫu đúng hướng, lặp lại giống nhau (trừ nhiễu); hip-fire tản rộng hơn khi chạy so với đứng; ADS đứng yên ≈ không tản.
- **G4** ADS + sway + bob + sprint + ngồi/nhảy.
- **G5** Reload hai kiểu + Draw, hủy reload, logic đạn.
- **G6** Bia chạy, biển khoảng cách, bảng debug, HUD hoàn chỉnh, CREDITS, dọn code.

## 7. Cách làm việc
- Bắt đầu: nói ngắn bạn sẽ làm G0 thế nào, rồi làm luôn. Không hỏi lại những gì đã chốt.
- Dự án chưa có git: chạy `git init`, tạo nhánh `dev`, thêm `.gitignore` (`.venv`, `__pycache__`, và **file glb 109 MB của Pack A**, vì vượt giới hạn 100 MB của GitHub nếu sau này push). Commit sau mỗi giai đoạn trên nhánh `dev`, dừng ở đó. Chỉ push khi người dùng nói.
- Tạo `CLAUDE.md` ngắn của dự án: lệnh chạy game, lệnh chạy pytest, quy ước “mọi thông số nằm trong `weapon_data.py`”.
- Cổng kiểm tra trước mỗi commit: pytest phần toán thuần qua, game mở được và chạy ≥ 60 FPS, không có lỗi trong console.
- Báo cáo cuối mỗi giai đoạn: dòng đầu `ĐỦ BƯỚC` hoặc `THIẾU n BƯỚC: <bước> — <lý do> — <người dùng cần làm gì>`. Nói bằng lời thường: chuyện gì xảy ra, một con số, các lựa chọn. Khi người dùng cần làm gì: chỉ nói LÀM GÌ và Ở ĐÂU (ví dụ: “chạy `run.bat`, giữ chuột phải rồi bắn”).
- Nếu công cụ thiếu hoặc lỗi: thử lại một lần, báo ngay, ghi CHƯA LÀM. Không nói “xong” khi chưa chạy thử thật.
