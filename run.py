import sys
import time
import threading
import webbrowser
from pathlib import Path

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
    print("=" * 60)
    print("[*] Starting YouTube Story Maker Web Studio...")
    print(f"[*] Root directory: {STORY_STUDIO_DIR}")
    print(f"[*] Server URL: http://localhost:{PORT}")
    print("=" * 60)

    # Automatically start local fleet runner
    start_fleet_runner_daemon()

    # Check for --no-browser argument
    auto_open = "--no-browser" not in sys.argv
    if auto_open:
        open_browser(f"http://localhost:{PORT}")

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
