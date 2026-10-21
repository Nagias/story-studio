"""Nơi DUY NHẤT tự bật Fleet Runner chạy ngầm (run.py lúc khởi động, muse_bridge khi có việc Muse mới).

- Không bật khi STORY_STUDIO_DISABLE_FLEET_AUTOSTART=1 (test, server thử) hoặc khi đã có runner giữ khoá.
- Runner gọi về đúng cổng server đang chạy (--url), không mặc định cứng cổng 8000.
"""
import subprocess
import sys
from pathlib import Path
from typing import Optional

from runners import single_instance

RUNNER_SCRIPT = Path(__file__).resolve().parent / "muse_fleet_runner.py"
STORY_STUDIO_DIR = RUNNER_SCRIPT.parent.parent.parent


def runner_url(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}/api/muse-bridge"


def start_fleet_runner_daemon(port: int, concurrency: int = 2) -> Optional[subprocess.Popen]:
    """Bật runner ngầm nếu được phép và chưa có; trả tiến trình vừa bật, hoặc None nếu không bật."""
    if single_instance.autostart_disabled() or single_instance.is_runner_running():
        return None
    if not RUNNER_SCRIPT.exists():
        return None
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
    return subprocess.Popen(
        [sys.executable, str(RUNNER_SCRIPT), "--daemon", "--concurrency", str(concurrency), "--url", runner_url(port)],
        cwd=str(STORY_STUDIO_DIR),
        creationflags=creationflags,
    )
