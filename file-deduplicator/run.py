"""
Launch the File Explorer as a native desktop app.

Usage:
    python run.py

Opens a native window powered by pywebview + FastAPI.
"""

import sys
import os
import threading

# Fix Windows console encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import uvicorn
import webview

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


class WindowApi:
    """Exposed to JS as window.pywebview.api.*"""

    def __init__(self):
        self._window = None

    def close(self):
        if self._window:
            self._window.destroy()

    def minimize(self):
        if self._window:
            self._window.minimize()

    def zoom(self):
        """macOS 'Zoom' — maximize/restore without leaving the desktop."""
        if self._window:
            if self._window.maximized:
                self._window.restore()
            else:
                self._window.maximize()

    def fullscreen(self):
        """macOS green-button default — toggle native fullscreen."""
        if self._window:
            self._window.toggle_fullscreen()


def start_server():
    """Run FastAPI in a background thread."""
    uvicorn.run(
        "app.server:app",
        host=HOST,
        port=PORT,
        log_level="warning",
    )


if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    import time
    time.sleep(1)

    api = WindowApi()
    window = webview.create_window(
        "Sift",
        URL,
        width=1100,
        height=700,
        min_size=(800, 500),
        frameless=True,
        js_api=api,
    )
    api._window = window
    webview.start()
