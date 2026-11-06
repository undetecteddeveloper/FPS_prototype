"""FPS prototype. Run: .venv\\Scripts\\python.exe main.py   (or double-click run.bat)

Options: --novsync (real FPS measurement), --size 1280x720, --fullscreen, --quit-after 5 (quits by itself after 5 seconds, for testing), --mute (mutes the gunshots)
The source code lives in the `fps/` package (see CLAUDE.md); this file is only the entry point.
"""
from fps.app import create_game, main  # noqa: F401  (create_game: the tools in tools\ call `from main import create_game`)

if __name__ == '__main__':
    main()
