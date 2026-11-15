"""Huỷ việc tạo bản tiếng Anh (nút "Huỷ" ở trang Dựng): cờ huỷ của job, các điểm kiểm trong create_language_version,
dọn dự án dở dang, và route POST /api/true-crime/jobs/{job_id}/cancel. Cô lập, LLM giả."""

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import language_versions
from services import case_jobs, project_service
from services.case_jobs import JobCancelled
from services.case_project_builder import create_language_version
from tests.case_adaptation_fakes import make_fake_llm
from tests.test_case_project_builder import (build_plan, make_vi_project, prepare_source_media, run, scene_by_order)


@pytest.fixture
def client(isolated_projects_dir):
    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


def project_ids():
    return sorted(p["id"] for p in project_service.list_projects())


def edited_source():
    """Dự án Việt có một cảnh sửa lời, nên bản Anh cần một lượt LLM viết lại."""
    plan = build_plan()
    source = make_vi_project(plan)
    saved = project_service.get_project(source.id)
    scene_by_order(saved, 3).text = "Run rẩy, bà Hà gọi trực ban hình sự và nói vừa thấy một bóng người chạy qua cổng cảng."
    project_service.save_project(saved)
    return source


def test_cancel_before_llm_makes_no_llm_call_and_no_new_project(isolated_projects_dir):
    source = edited_source()
    before = project_ids()
    llm, calls = make_fake_llm()

    with pytest.raises(JobCancelled):
        run(create_language_version(source.id, "en", llm=llm, should_stop=lambda: True))

    assert calls == []
    assert project_ids() == before == [source.id]


def test_cancel_during_copy_loop_removes_half_built_project_and_keeps_source(isolated_projects_dir):
    plan = build_plan()
    source = prepare_source_media(make_vi_project(plan))
    before_json = project_service.get_project(source.id).model_dump_json()
    ticks = {"n": 0}

    def stop_on_third_scene() -> bool:
        ticks["n"] += 1
        return ticks["n"] >= 6          # 2 điểm kiểm trước/sau LLM, 1 đầu phần chép, rồi tới cảnh thứ ba

    with pytest.raises(JobCancelled):
        run(create_language_version(source.id, "en", should_stop=stop_on_third_scene))

    assert ticks["n"] == 6              # thật sự đã vào vòng cảnh rồi mới dừng
    assert project_ids() == [source.id]
    assert project_service.get_project(source.id).model_dump_json() == before_json
    leftovers = [p.name for p in project_service._get_project_dir(source.id).parent.iterdir() if p.is_dir() and not p.name.startswith("_")]
    assert leftovers == [source.id]     # không còn thư mục dự án mới dở dang


def test_run_job_marks_job_cancelled(isolated_projects_dir):
    source = edited_source()
    job_id = case_jobs.create_job("language_version")
    assert case_jobs.request_cancel(job_id) == "running"
    assert case_jobs.is_cancel_requested(job_id)

    run(language_versions._run_job(job_id, source.id, "en", None))

    job = case_jobs.get_job(job_id)
    assert job["status"] == "cancelled" and job["error"] == "Đã huỷ theo yêu cầu"
    assert project_ids() == [source.id]


def test_cancel_route_running_job_returns_202_and_sets_flag(client):
    job_id = case_jobs.create_job("language_version")

    response = client.post(f"/api/true-crime/jobs/{job_id}/cancel")

    assert response.status_code == 202 and response.json() == {"status": "cancelling"}
    assert case_jobs.is_cancel_requested(job_id)
    assert case_jobs.get_job(job_id)["status"] == "running"      # chưa dừng ngay: chờ điểm kiểm kế tiếp


def test_cancel_route_finished_job_returns_409(client):
    job_id = case_jobs.create_job("language_version")
    case_jobs.update_job(job_id, status="done", result={"project_id": "proj_x"})

    response = client.post(f"/api/true-crime/jobs/{job_id}/cancel")

    assert response.status_code == 409 and "done" in response.json()["detail"]
    assert not case_jobs.is_cancel_requested(job_id)


def test_cancel_route_unknown_job_returns_404_and_bad_id_400(client):
    assert client.post("/api/true-crime/jobs/job_00000000/cancel").status_code == 404
    assert client.post("/api/true-crime/jobs/..%2Fx/cancel").status_code in (400, 404)
