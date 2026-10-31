"""FPS prototype. Chạy: .venv\\Scripts\\python.exe main.py   (hoặc bấm đúp run.bat)

Tuỳ chọn: --novsync (đo FPS thật), --size 1280x720, --fullscreen, --quit-after 5 (tự thoát sau 5 giây, để kiểm tra)
Mã nguồn nằm trong gói `fps/` (xem CLAUDE.md); tệp này chỉ là cửa vào.
"""
from fps.app import create_game, main  # noqa: F401  (create_game: các công cụ trong tools\ gọi `from main import create_game`)

if __name__ == '__main__':
    main()
