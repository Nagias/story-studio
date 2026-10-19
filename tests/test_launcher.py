import os
import sys
import time
import subprocess
from pathlib import Path
import httpx
import pytest

TEST_DIR = Path(__file__).resolve().parent
STORY_STUDIO_DIR = TEST_DIR.parent

def test_launcher_files_exist():
    """Verify run.py and run.bat launcher scripts exist in apps/story-studio."""
    run_py = STORY_STUDIO_DIR / "run.py"
    run_bat = STORY_STUDIO_DIR / "run.bat"

    assert run_py.exists(), "apps/story-studio/run.py not found!"
    assert run_bat.exists(), "apps/story-studio/run.bat not found!"
    assert run_py.stat().st_size > 200, "run.py is unexpectedly small"
    assert run_bat.stat().st_size > 200, "run.bat is unexpectedly small"

def test_run_bat_content():
    """Verify run.bat has proper Windows shell commands and checks."""
    run_bat = STORY_STUDIO_DIR / "run.bat"
    with open(run_bat, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    assert "python run.py" in content
    assert "where python" in content
    assert "cd /d" in content

def test_run_py_server_lifecycle():
    """Test launcher run.py can start the server, respond to health checks and serve the web UI."""
    run_py = STORY_STUDIO_DIR / "run.py"

    proc = subprocess.Popen(
        [sys.executable, str(run_py), "--no-browser"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Retry loop to connect to server
        connected = False
        for _ in range(25):
            time.sleep(0.4)
            try:
                r = httpx.get("http://127.0.0.1:8000/api/health", timeout=1.0)
                if r.status_code == 200:
                    connected = True
                    break
            except Exception:
                pass

        assert connected, "Failed to connect to web server started by run.py"

        # Check health API response
        r_health = httpx.get("http://127.0.0.1:8000/api/health", timeout=2.0)
        assert r_health.status_code == 200
        assert r_health.json()["status"] == "online"

        # Check frontend root endpoint
        r_root = httpx.get("http://127.0.0.1:8000/", timeout=2.0)
        assert r_root.status_code == 200
        assert "Storyboard" in r_root.text

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
