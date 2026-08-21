"""Desktop entry point: portable data dir, static UI, auto-open browser."""

import os
import sys
import threading
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000


def resource_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def configure_paths() -> None:
    if not getattr(sys, "frozen", False):
        return
    try:
        from platformdirs import user_data_dir

        data_dir = Path(user_data_dir("ExamVariator"))
    except ImportError:
        data_dir = Path.home() / ".exam_variator"
    os.environ.setdefault("EXAM_DATA_DIR", str(data_dir))
    os.environ.setdefault("EXAM_FRONTEND_DIR", str(resource_base() / "frontend"))


def main() -> None:
    configure_paths()

    import uvicorn

    from app.main import app

    url = f"http://{HOST}:{PORT}"
    threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
