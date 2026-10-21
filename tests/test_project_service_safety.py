"""Dự án không bao giờ bị ghi đè thành dự án rỗng vì project.json hỏng, và không bị ghi cụt.

Lỗi cũ (rà soát 21/10/2026): get_project() trả None với MỌI lỗi đọc (JSON hỏng, schema đổi) nên update_project()
coi như dự án chưa có và ghi đè bằng dự án rỗng (scenes=[]). Lần lưu tự động kế tiếp của giao diện là mất hết cảnh.
"""
import json
import os

import pytest
from httpx import ASGITransport, AsyncClient

from models.schemas import ProjectCreateRequest, ProjectUpdateRequest
from services import project_service, safe_files


def _make_project(name="Dự án thử"):
    project = project_service.create_project(ProjectCreateRequest(name=name))
    project_service.update_project(project.id, ProjectUpdateRequest(scenes=[
        {"id": "scene_1", "order": 1, "text": "Cảnh một"},
        {"id": "scene_2", "order": 2, "text": "Cảnh hai"},
    ]))
    return project.id


def _json_path(projects_dir, project_id):
    return projects_dir / project_id / "project.json"


@pytest.mark.parametrize("broken", [
    b"{ \"id\": \"proj_x\", \"scenes\": [",          # JSON cụt (ghi dở)
    b"{\"id\": \"proj_x\", \"scenes\": \"abc\"}",       # JSON đúng nhưng sai schema
    b"\xff\xfe\x00 not utf-8",                         # không phải UTF-8
])
def test_unreadable_project_is_not_overwritten(isolated_projects_dir, broken):
    project_id = _make_project()
    path = _json_path(isolated_projects_dir, project_id)
    path.write_bytes(broken)

    with pytest.raises(project_service.ProjectUnreadableError):
        project_service.get_project(project_id)
    with pytest.raises(project_service.ProjectUnreadableError):
        project_service.update_project(project_id, ProjectUpdateRequest(name="Tên mới"))
    assert path.read_bytes() == broken, "file hỏng phải được giữ nguyên để còn cứu"


def test_missing_project_still_upserts(isolated_projects_dir):
    assert project_service.get_project("proj_moi12345") is None
    project = project_service.update_project("proj_moi12345", ProjectUpdateRequest(name="Từ giao diện cũ"))
    assert project.name == "Từ giao diện cũ"
    assert project_service.get_project("proj_moi12345").name == "Từ giao diện cũ"


def test_failed_save_keeps_old_file_and_leaves_no_tmp(isolated_projects_dir, monkeypatch):
    project_id = _make_project()
    path = _json_path(isolated_projects_dir, project_id)
    before = path.read_bytes()
    monkeypatch.setattr(safe_files, "RETRY_DELAY", 0)

    def locked_replace(src, dst):
        raise PermissionError(13, "The process cannot access the file")

    monkeypatch.setattr(safe_files.os, "replace", locked_replace)
    with pytest.raises(PermissionError):
        project_service.update_project(project_id, ProjectUpdateRequest(name="Không lưu được"))
    monkeypatch.undo()
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.tmp"))


def test_save_project_is_the_public_way_to_write(isolated_projects_dir):
    project_id = _make_project()
    project = project_service.get_project(project_id)
    project.name = "Đổi qua save_project"
    project_service.save_project(project)
    data = json.loads(_json_path(isolated_projects_dir, project_id).read_text(encoding="utf-8"))
    assert data["name"] == "Đổi qua save_project"
    assert len(data["scenes"]) == 2


def test_list_projects_shows_unreadable_project(isolated_projects_dir, caplog):
    good = _make_project("Dự án tốt")
    bad = _make_project("Dự án hỏng")
    _json_path(isolated_projects_dir, bad).write_text("{ cụt", encoding="utf-8")

    listed = {p["id"]: p for p in project_service.list_projects()}
    assert listed[good]["name"] == "Dự án tốt" and not listed[good].get("unreadable")
    assert listed[bad]["unreadable"] is True
    assert bad in listed[bad]["name"]
    assert any(bad in rec.getMessage() for rec in caplog.records), "phải ghi log, không nuốt lỗi"


@pytest.mark.asyncio
async def test_api_reports_unreadable_project_and_keeps_file(isolated_projects_dir):
    from main import app

    project_id = _make_project()
    path = _json_path(isolated_projects_dir, project_id)
    path.write_text("{ cụt", encoding="utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        got = await client.get(f"/api/projects/{project_id}")
        put = await client.put(f"/api/projects/{project_id}", json={"name": "ghi đè"})
    for resp in (got, put):
        assert resp.status_code == 409, resp.text
        assert "không đọc được" in resp.json()["detail"]
    assert path.read_text(encoding="utf-8") == "{ cụt"
    assert os.path.exists(path)
