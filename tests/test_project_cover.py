"""Ảnh bìa dự án trong danh sách: lấy ảnh cảnh đầu có file thật, chỉ đọc, không tạo file."""
import json

from services import project_service


def _make(root, pid, scenes, files=()):
    d = root / pid
    d.mkdir(parents=True)
    (d / "project.json").write_text(json.dumps({"id": pid, "name": pid, "scenes": scenes}), encoding="utf-8")
    for rel in files:
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
    return d


def _snapshot(d):
    return sorted(str(p.relative_to(d)) for p in d.rglob("*"))


def _cover(pid):
    return {p["id"]: p for p in project_service.list_projects()}[pid]["cover_url"]


def test_cover_is_first_scene_image_that_exists(isolated_projects_dir):
    scenes = [{"image_url": "/api/projects/proj_a/media/images/s1.png"},
              {"image_url": "/api/projects/proj_a/media/images/s2.png"},
              {"image_path": "C:/x/projects/proj_a/images/s3.png".replace("/", chr(92))}]
    _make(isolated_projects_dir, "proj_a", scenes, files=["images/s2.png", "images/s3.png"])
    assert _cover("proj_a") == "/api/projects/proj_a/media/images/s2.png"


def test_cover_uses_image_path_basename(isolated_projects_dir):
    _make(isolated_projects_dir, "proj_b", [{"image_path": "D:/any/images/s3.png".replace("/", chr(92))}], files=["images/s3.png"])
    assert _cover("proj_b") == "/api/projects/proj_b/media/images/s3.png"


def test_cover_falls_back_to_existing_thumbnail(isolated_projects_dir):
    _make(isolated_projects_dir, "proj_c", [{"image_url": "/x/images/none.png"}], files=["renders/thumbnail.jpg"])
    assert _cover("proj_c") == "/api/projects/proj_c/media/renders/thumbnail.jpg"


def test_cover_none_without_images_and_creates_no_file(isolated_projects_dir):
    d = _make(isolated_projects_dir, "proj_d", [{"image_url": "/x/images/none.png"}, {}])
    before = _snapshot(d)
    assert _cover("proj_d") is None
    assert _snapshot(d) == before


def test_cover_ignores_path_traversal(isolated_projects_dir):
    d = _make(isolated_projects_dir, "proj_e", [{"image_url": "../project.json"}, {"image_path": ".."}])
    assert _cover("proj_e") is None
    assert (d / "project.json").exists()
