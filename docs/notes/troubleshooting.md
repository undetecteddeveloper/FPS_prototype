<!-- Mở khi: game không mở được / cửa sổ đen / game tự tắt lúc khởi động / âm thanh nền ngắt quãng rồi lặp một đoạn / dòng log dừng sau "[thông số] user_params.json". -->
# Xử lý sự cố: game chết hoặc treo lúc khởi động (7/11/2026)

## Triệu chứng đã gặp
- `.venv\Scripts\python main.py` in vài dòng rồi dừng ở `[thông số] user_params.json: đã nạp 0 giá trị`; cửa sổ đen; không vào được.
- Âm thanh nền (tiếng phòng hồ bơi) vang lên rồi **ngắt quãng và lặp mãi một đoạn ngắn**.
- Lúc đầu "đôi khi", sau đó gần như mọi lần. Game vẫn chạy ổn ở lần trước đó.

## Nguyên nhân gốc: máy hết bộ nhớ ảo (commit)
- Windows cho một chương trình xin bộ nhớ chỉ khi **commit** (RAM + pagefile, trừ phần mọi chương trình đã đặt chỗ) còn trống. Máy này: RAM 15,6 GB + pagefile ~3 GB (tự quản lý) = giới hạn ~18,6 GB,
  mà Chrome, Zalo, VS Code, Claude, McAfee, driver GPU (Intel dùng chung RAM) đã đặt chỗ 17-18 GB. **Phần trống dao động 0,7-2,1 GB** tuỳ lúc đó đang mở gì.
- Game cần **0,62 GB** (0,72-0,75 GB với khử răng cưa MSAA 4x). Khi phần trống thấp hơn, một lần xin bộ nhớ bị từ chối ở chỗ nào đó trong lúc dựng game; thường nhất là nạp file glb của súng
  (`gltf/_converter.py`, `copy_data_from`) vì đó là chỗ xin nhiều nhất. Thư viện native không xử lý lỗi này nên chết bằng `access violation` trong `VCRUNTIME140.dll` (memcpy vào con trỏ rỗng).
  Ở mức thiếu nhiều hơn thì **treo** (không crash): game kẹt trong `Viewmodel.prewarm`, lượt vẽ thử, khi driver GPU chờ bộ nhớ.
- **Âm thanh lặp đoạn ngắn = cùng sự cố.** `Game.__init__` bật âm thanh nền (dòng `ambience.play()`) TRƯỚC khi nạp súng. Tiến trình chết ở bước nạp súng nhưng Windows giữ nó ~10 giây để lập báo cáo lỗi
  (Event Log: `Application Error` lúc 05:08:25, báo cáo lưu lúc 05:08:35), và suốt thời gian đó thiết bị âm thanh lặp đoạn đệm cuối. (Suy luận từ thứ tự mã + mốc giờ; chưa nghe trực tiếp.)
- **Vì sao "tự dưng"**: không có thay đổi mã nào gây ra. Phần commit trống co lại sát mức game cần (các ứng dụng khác lớn dần); bật MSAA 4x lúc 05:06 thêm ~0,1 GB; vụ crash đầu tiên là 05:08.
  Hai vụ đầu (05:08, 05:20) xảy ra trước khi có mã G11 (caustics): G11 chỉ thêm vài MB.
- Không phải: lỗi trong đường nạp glb (chạy riêng 25 lần không lỗi), mã G10/G11, file âm thanh hỏng (đọc đúng header), TDR / treo driver (Event Log không có).

## Bằng chứng (cách truy nguyên, làm lại được)
1. **Event Log** (`Application`, nguồn `Application Error`): `python.exe`, module lỗi `VCRUNTIME140.dll`, mã `0xc0000005`, offset `0x1cc4d`, 3 lần giống hệt; mỗi tiến trình sống 2-3 giây.
2. `PYTHONFAULTHANDLER=1` + chạy 6 lần: 1 lần chết, dấu vết Python chỉ `gltf/_converter.py:1082 load_primitive` <- `Viewmodel.__init__`.
3. Đường nạp glb chạy riêng (không cửa sổ, không âm thanh) 25 lần: 0 lỗi -> lỗi chỉ ở điều kiện thiếu bộ nhớ của game thật.
4. `GlobalMemoryStatusEx`: commit trống 0,71 GB trước một lần chạy; đỉnh hệ thống chạm giới hạn lúc game chạy (giới hạn còn tự nở từ 18,6 lên ~21 GB trong lúc đo: pagefile tự quản lý đang phải lớn dần).
5. **Tái hiện theo yêu cầu** bằng Job Object giới hạn commit của riêng tiến trình game (`tools\measure\job_limit_run.py`): ở ~350-400 MB bản đầy đủ chết trong `gltf/_converter.py` đúng chuỗi gọi như lỗi thật;
   ở ~280 MB thì treo trong `Viewmodel.prewarm`; chế độ giảm tải sống được ở 380 MB.
6. Footprint đo bằng `tools\measure\commit_probe.py` (lúc máy bận, lặp nhiều lần lấy giá trị thấp): đầy đủ 0,72-0,75 GB (MSAA 4x), 0,62 GB (không MSAA), `--low-memory` 0,50-0,61 GB.
   Trong 0,49 GB của riêng tiến trình: `Viewmodel.prewarm` +192 MB (M4) và +87 MB (Glock), nạp glb +51 / +34 MB, phần còn lại là Python + Panda + cửa sổ.

## Game đã làm gì để không chết nữa (code)
- `fps/core/memplan.py` + `fps/game/sysmem.py`, gọi ở đầu `main()` TRƯỚC khi mở cửa sổ: đọc commit trống rồi chọn
  | commit trống | chế độ | việc game làm |
  |---|---|---|
  | >= 950 MB | đầy đủ | như cũ |
  | 700-950 MB | giảm tải | tắt MSAA tạm thời (file `user_graphics.json` KHÔNG bị ghi đè; bảng F2 vẫn hiện mức đã lưu; chọn lại mức khử răng cưa trong F2 thì có hiệu lực ngay) và nạp súng thứ hai ở lần đổi súng đầu tiên (một khung dài thay vì nạp lúc khởi động); báo một dòng trên màn hình + console |
  | < 700 MB | dừng | hộp thoại tiếng Việt nói còn bao nhiêu, cần bao nhiêu, cách xử lý; thoát (mã 1) trước khi cửa sổ hay model nào được dựng |
  `--low-memory` ép chế độ giảm tải (để thử / máy yếu). Ngưỡng ở `memplan.FULL_MB` / `REDUCED_MB`: lấy từ số đo ở trên + biên >= 0,1-0,2 GB; đo lại và chỉnh nếu game đổi cỡ (thêm buffer / texture lớn).
- **`logs/crash.log`** (gitignore): mỗi lần chạy một dòng đầu (giờ, lệnh, commit trống / giới hạn, chế độ); nếu crash native thì thêm dấu vết Python của mọi luồng; nếu dựng game quá `STARTUP_WATCHDOG_S` = 150 s
  thì ghi luồng đang kẹt ở đâu (game vẫn chạy tiếp). `SetErrorMode` tắt báo cáo lỗi của Windows: tiến trình chết ngay, không treo 10 giây (hết kiểu "âm thanh lặp 10 giây").
- Âm thanh nền (2 MB) bị Panda phát bằng **streaming** (ngưỡng nạp sẵn mặc định 1 MB; luồng chính phải đổ thêm vào hàng đợi 3 giây mỗi khung, nên luồng chính đứng > 3 s thì âm thanh đứt).
  `AUDIO_PRELOAD_BYTES` = 16 MB: file nằm sẵn trong bộ nhớ, OpenAL tự lặp, không phụ thuộc luồng chính. `tests/test_memplan.py` giữ file nhỏ hơn ngưỡng.
- Kiểm: `tests/test_memplan.py` (15 bài: ngưỡng, `main()` từ chối khi thiếu, crash thật ghi log và thoát < 8 s không để lại sự kiện Application Error, canh giờ), `tools\measure\lowmem_check.py` (game thật).

## Việc của BẠN (gốc rễ nằm ở cấu hình Windows; tôi không đổi cài đặt hệ thống)
Pagefile 3 GB quá nhỏ so với mức máy đang đặt chỗ. Tăng cố định (C: còn ~90 GB trống) thì giới hạn commit lên ~24 GB ngay (RAM 15,6 + 8) và tới ~36 GB khi pagefile nở hết, nên game không còn phải chạy giảm tải:
1. `Win+R` -> `sysdm.cpl` -> tab **Advanced** -> **Performance: Settings** -> tab **Advanced** -> **Virtual memory: Change...**
2. Bỏ dấu "Automatically manage paging file size for all drives"; chọn ổ **C:** -> **Custom size**: Initial **8192**, Maximum **20480** (MB) -> **Set** -> OK -> khởi động lại máy.
3. Hoặc PowerShell chạy bằng quyền Admin (chưa chạy thử trên máy này): 
   ```powershell
   $cs = Get-CimInstance Win32_ComputerSystem; Set-CimInstance -InputObject $cs -Property @{AutomaticManagedPagefile=$false}
   Get-CimInstance Win32_PageFileSetting -ErrorAction SilentlyContinue | Remove-CimInstance
   New-CimInstance -ClassName Win32_PageFileSetting -Property @{Name='C:\pagefile.sys'; InitialSize=[uint32]8192; MaximumSize=[uint32]20480}
   ```
   rồi khởi động lại.
4. Kiểm sau khi khởi động lại: `.venv\Scripts\python -X utf8 -c "from fps.game import sysmem; print(sysmem.free_commit_mb(), sysmem.commit_limit_mb())"` -> giới hạn phải từ ~24000 MB trở lên (hiện ~18600-21000) và phần trống vài GB.
Đóng bớt ứng dụng nặng (Chrome, Zalo, nhiều cửa sổ VS Code / Claude) cũng cho thêm phần trống ngay, không cần khởi động lại.

## Gặp lại lỗi tương tự thì làm gì
1. Mở `logs\crash.log`: dòng `===` cuối cho biết commit trống lúc mở game; có dấu vết Python (`Windows fatal exception` / `Fatal Python error`) thì đó là chỗ chết; có `Timeout (0:02:30)!` thì đó là chỗ treo.
2. Chưa có log (bản cũ, hoặc chết trước `main()`): Event Viewer -> Windows Logs -> Application -> `Application Error` / `python.exe` (module, offset, giờ).
3. Đo: `tools\measure\commit_probe.py` (game chiếm bao nhiêu) và `tools\measure\job_limit_run.py` (ép thiếu bộ nhớ để tái hiện); đừng giết tiến trình theo tên (`Get-Process python | Stop-Process` giết cả game của người dùng).
