"""/api/open-folder: mở thư mục dự án (trước đây lỗi 500 vì thiếu import _get_project_dir)."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
import routers.api as api_module  # noqa: E402

LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


def test_open_folder_by_project_id(monkeypatch, tmp_path):
    proj = tmp_path / "proj_open_test"
    (proj / "renders").mkdir(parents=True)
    opened = []
    monkeypatch.setattr(api_module, "_get_project_dir", lambda pid: proj)
    monkeypatch.setattr(api_module.os, "startfile", lambda p: opened.append(p), raising=False)

    r = TestClient(app, **LOCAL).post("/api/open-folder", json={"project_id": "proj_open_test"})
    assert r.status_code == 200, r.text
    assert Path(opened[0]) == proj / "renders"


def test_open_folder_rejects_bad_ids_and_outside_paths(monkeypatch):
    monkeypatch.setattr(api_module.os, "startfile", lambda p: (_ for _ in ()).throw(AssertionError("không được mở")), raising=False)
    c = TestClient(app, **LOCAL)
    assert c.post("/api/open-folder", json={"project_id": "..\\..\\Windows"}).status_code == 400
    assert c.post("/api/open-folder", json={"path": "C:\\Windows"}).status_code == 403
    assert c.post("/api/open-folder", json={"path": "\\\\server\\share"}).status_code == 400
