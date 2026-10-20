"""
run.py không bật server thứ hai khi cổng đã có người dùng (bấm run.bat hai lần).

- Cổng trống: chạy server như thường.
- Story Studio đang chạy (/api/health trả 200): không bật server mới, chỉ mở trình duyệt vào server đó (trừ
  --no-browser), thoát mã 0.
- Chương trình khác giữ cổng: báo lỗi, thoát mã khác 0 để run.bat dừng lại cho người dùng đọc.
Chạy offline: server giả trên 127.0.0.1, không bật uvicorn, Fleet Runner hay trình duyệt thật.
"""
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import run  # noqa: E402


@contextmanager
def fake_server(health_status):
    """Server HTTP giả trên một cổng trống; GET /api/health trả `health_status`. Trả số cổng."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(health_status if self.path == "/api/health" else 404)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_existing_server_tells_story_studio_from_other_programs():
    assert run.existing_server("127.0.0.1", free_port()) is None
    with fake_server(200) as port:
        assert run.existing_server("127.0.0.1", port) == "story_studio"
        assert run.existing_server("0.0.0.0", port) == "story_studio"      # nghe mọi địa chỉ thì hỏi qua 127.0.0.1
    with fake_server(404) as port:
        assert run.existing_server("127.0.0.1", port) == "other"


@pytest.fixture
def launcher(monkeypatch):
    """Chặn mọi tác dụng thật của run.main: ghi lại việc bật server, Fleet Runner, mở trình duyệt."""
    calls = []
    monkeypatch.setattr(run.uvicorn, "run", lambda *a, **k: calls.append("uvicorn"))
    monkeypatch.setattr(run, "start_fleet_runner_daemon", lambda: calls.append("fleet"))
    monkeypatch.setattr(run, "open_browser", lambda url, delay=1.5: calls.append(("open_later", url)))
    monkeypatch.setattr(run.webbrowser, "open", lambda url: calls.append(("open", url)))
    monkeypatch.setattr(run, "HOST", "127.0.0.1")
    return calls


def test_main_starts_the_server_when_the_port_is_free(launcher, monkeypatch):
    port = free_port()
    monkeypatch.setattr(run, "PORT", port)
    monkeypatch.setattr(sys, "argv", ["run.py", "--no-browser"])
    run.main()
    assert launcher == ["fleet", "uvicorn"]


@pytest.mark.parametrize("argv, opened", [(["run.py"], True), (["run.py", "--no-browser"], False)])
def test_main_opens_the_running_story_studio_instead_of_a_second_server(launcher, monkeypatch, capsys, argv, opened):
    with fake_server(200) as port:
        monkeypatch.setattr(run, "PORT", port)
        monkeypatch.setattr(sys, "argv", argv)
        run.main()
    assert "uvicorn" not in launcher and "fleet" not in launcher
    assert launcher == ([("open", f"http://localhost:{port}")] if opened else [])
    assert "đang chạy" in capsys.readouterr().out


def test_main_stops_with_an_error_when_another_program_holds_the_port(launcher, monkeypatch, capsys):
    with fake_server(404) as port:
        monkeypatch.setattr(run, "PORT", port)
        monkeypatch.setattr(sys, "argv", ["run.py"])
        with pytest.raises(SystemExit) as exc:
            run.main()
    assert exc.value.code not in (0, None)
    assert launcher == []
    out = capsys.readouterr().out
    assert str(port) in out and "STORY_STUDIO_PORT" in out
