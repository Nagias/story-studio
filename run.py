import socket
import sys
import time
import threading
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional

# Safe console re-encoding on Windows
if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr:
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Setup paths
STORY_STUDIO_DIR = Path(__file__).resolve().parent
BACKEND_DIR = STORY_STUDIO_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import uvicorn
from config import HOST, PORT

def silence_proactor_pipe_error():
    """Silence Windows WinError 10054 connection reset in asyncio Proactor loop."""
    if sys.platform == "win32":
        try:
            from asyncio.proactor_events import _ProactorBasePipeTransport
            _orig_call = _ProactorBasePipeTransport._call_connection_lost
            def _silent_call_connection_lost(self, exc=None):
                try:
                    _orig_call(self, exc)
                except (ConnectionResetError, OSError):
                    pass
            _ProactorBasePipeTransport._call_connection_lost = _silent_call_connection_lost
        except Exception:
            pass

silence_proactor_pipe_error()

def open_browser(url: str, delay: float = 1.5):
    """Wait for server to start, then automatically open default web browser."""
    def _target():
        time.sleep(delay)
        print(f"[*] Opening browser at: {url}")
        webbrowser.open(url)
    
    t = threading.Thread(target=_target, daemon=True)
    t.start()

def existing_server(host: str, port: int) -> Optional[str]:
    """Ai đang nghe ở cổng `port`: None nếu cổng trống, "story_studio" nếu /api/health trả 200, "other" nếu là
    chương trình khác. Bấm run.bat hai lần thì bản thứ hai thấy "story_studio" và không bật server nữa."""
    probe = "127.0.0.1" if host in ("", "0.0.0.0") else "::1" if host == "::" else host
    try:
        with socket.create_connection((probe, port), timeout=0.5):
            pass
    except OSError:
        return None
    url_host = f"[{probe}]" if ":" in probe else probe
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # máy có proxy vẫn hỏi thẳng localhost
    try:
        with opener.open(f"http://{url_host}:{port}/api/health", timeout=2) as resp:
            return "story_studio" if resp.status == 200 else "other"
    except Exception:
        return "other"


def start_fleet_runner_daemon():
    """Tự động khởi động Fleet Runner ngầm cùng Web Server để xử lý các tác vụ Muse."""
    runner_script = STORY_STUDIO_DIR / "backend" / "runners" / "muse_fleet_runner.py"
    from runners.single_instance import is_runner_running
    if is_runner_running():
        print("[*] Meta Muse Fleet Runner is already running")
        return

    if runner_script.exists():
        try:
            import subprocess
            creationflags = 0
            if sys.platform == "win32":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(
                [sys.executable, str(runner_script), "--daemon", "--concurrency", "2"],
                cwd=str(STORY_STUDIO_DIR),
                creationflags=creationflags,
            )
            print("[*] Automatically started Meta Muse Fleet Runner Daemon (Concurrency: 2)")
        except Exception as e:
            print(f"[!] Warning: Could not start Fleet Runner daemon: {e}")

def main():
    url = f"http://localhost:{PORT}"
    print("=" * 60)
    print("[*] Starting YouTube Story Maker Web Studio...")
    print(f"[*] Root directory: {STORY_STUDIO_DIR}")
    print(f"[*] Server URL: {url}")
    print("=" * 60)

    # Check for --no-browser argument
    auto_open = "--no-browser" not in sys.argv

    # Không bật server thứ hai khi cổng đã có người dùng
    running = existing_server(HOST, PORT)
    if running == "story_studio":
        print(f"[*] Story Studio đang chạy sẵn ở {url}: không bật thêm server thứ hai.")
        if auto_open:
            webbrowser.open(url)
        return
    if running == "other":
        print(f"[!] Cổng {PORT} đang bị một chương trình khác dùng. Tắt chương trình đó, hoặc đặt biến môi trường "
              f"STORY_STUDIO_PORT sang cổng khác rồi chạy lại.")
        sys.exit(1)

    # Automatically start local fleet runner
    start_fleet_runner_daemon()

    if auto_open:
        open_browser(url)

    # Launch uvicorn server
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        app_dir=str(BACKEND_DIR),
        reload=False,
    )

if __name__ == "__main__":
    main()
