"""
API chuyển thể vụ án (spec 7.8): phân tích -> tiến độ -> xem lại/sửa -> tạo dự án -> bản ngôn ngữ khác.

- TestClient(app) với thư mục projects tạm (isolated_projects_dir) và LLM giả (tests/case_adaptation_fakes.py);
  worker nền bị tắt trong test nên test tự chạy hàng việc bằng asyncio.run(case_worker.run_next_step()).
- Không gọi 9router hay Muse thật.
- Luồng 70/30 cũ (/fictionalize, /create-project, _CASE_PLAN_CACHE) đã bỏ.
"""
import asyncio
import copy
import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from models.case_adaptation_schemas import (
    DISCLAIMER,
    MAX_SOURCE_CHARS,
    AdaptedScene,
    CaseAdaptationPlan,
    CaseBible,
    CaseEntity,
    StoryPart,
)
from models.schemas import ProjectCreateRequest
from routers import true_crime
from services import case_adaptation_llm, case_jobs, case_redact, case_store, case_worker, project_service
from services.image_service import STYLE_PRESETS, build_character_anchored_prompt
from services.project_service import get_project
from services.video_service import CAMERA_MOTIONS, build_zoompan_filter
from tests.case_adaptation_fakes import load_fixture, make_fake_llm
from tests.test_case_project_builder import REWRITE_3
from tests.test_case_worker import DOSSIER, _thin_write_vi

BASE = "/api/true-crime"
VI_VOICE = "vieneu-test-voice"
EN_VOICE = "en-US-AndrewMultilingualNeural"
REAL_VICTIM = "Nguyễn Văn Hùng"               # tên thật của nạn nhân trong dossier.txt
REGEX_ONLY_NAME = "Hoàng Minh Tuấn"           # tên chỉ regex trên bài gốc bắt được (không có trong bảng tên)
NOT_READY = "Đang phân tích, chưa có kế hoạch."


# ---------------------------------------------------------------- helpers (dùng lại ở test_true_crime_e2e.py)

@pytest.fixture
def client(isolated_projects_dir):
    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


@pytest.fixture
def small_chunks(monkeypatch):
    """Bài mẫu chỉ ~2 KB: cắt đoạn 900 ký tự (như test_case_worker) để ra 2 đoạn khớp fixture EXTRACT_0/1."""
    real = case_worker.start_analysis
    monkeypatch.setattr(case_worker, "start_analysis",
                        lambda raw, minutes, style, **kw: real(raw, minutes, style, chunk_chars=900))


def use_llm(monkeypatch, overrides=None):
    """Thay hàm gọi LLM thật bằng LLM giả; trả (llm, danh sách marker đã gọi)."""
    llm, calls = make_fake_llm(overrides)
    monkeypatch.setattr(case_adaptation_llm, "call_llm_json", llm)
    return llm, calls


def drain(limit: int = 100) -> int:
    """Chạy hàng việc như worker nền (một việc mỗi lần) tới khi hết việc."""
    ran = 0
    while asyncio.run(case_worker.run_next_step()):
        ran += 1
        assert ran < limit, "hàng việc không dừng"
    return ran


def analyze(client, **body) -> str:
    response = client.post(f"{BASE}/analyze", json={"raw_report": DOSSIER, **body})
    assert response.status_code == 200, response.text
    return response.json()["case_id"]


def finished_case(client, monkeypatch, overrides=None) -> str:
    use_llm(monkeypatch, overrides)
    case_id = analyze(client)
    drain()
    return case_id


def get_plan(client, case_id) -> dict:
    response = client.get(f"{BASE}/cases/{case_id}")
    assert response.status_code == 200, response.text
    return response.json()


def create_vi_project(client, case_id, **extra) -> str:
    response = client.post(f"{BASE}/cases/{case_id}/create-project",
                           json={"language": "vi", "voice": VI_VOICE, **extra})
    assert response.status_code == 200, response.text
    return response.json()["project_id"]


def scene_of(plan: dict, order: int) -> dict:
    return next(s for s in plan["scenes"] if s["order"] == order)


def wait_job(client, job_id: str) -> dict:
    response = client.get(f"{BASE}/jobs/{job_id}")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- kiểu hình và chuyển động (giữ từ bản cũ)

def test_neo_noir_style_and_camera_motion():
    # 1. Verify STYLE_PRESETS contains neo_noir_silhouette
    assert "neo_noir_silhouette" in STYLE_PRESETS
    preset = STYLE_PRESETS["neo_noir_silhouette"]
    assert "chiaroscuro" in preset["prompt_suffix"]
    assert "#030712" in preset["colors"]

    # 2. Verify prompt composition with neo_noir_silhouette
    composed = build_character_anchored_prompt(
        scene_prompt="Detective walking in heavy rain shining flashlight into dark alley",
        style_preset="neo_noir_silhouette",
    )
    assert "neo-noir" in composed.lower()
    assert "rain" in composed.lower()

    # 3. Verify camera motions in video_service
    assert "neo_noir_dutch_tilt" in CAMERA_MOTIONS
    assert "neo_noir_rain_motion" in CAMERA_MOTIONS

    filter_dutch = build_zoompan_filter("neo_noir_dutch_tilt", duration=5.0, width=1920, height=1080)
    assert "vignette" in filter_dutch
    assert "zoompan" in filter_dutch

    filter_rain = build_zoompan_filter("neo_noir_rain_motion", duration=5.0, width=1920, height=1080)
    assert "noise" in filter_rain
    assert "contrast" in filter_rain

    print("✓ test_neo_noir_style_and_camera_motion passed")


# ---------------------------------------------------------------- job trong bộ nhớ

def test_case_jobs_lifecycle_and_limits():
    job_id = case_jobs.create_job("language_version")
    assert re.fullmatch(r"job_[0-9a-f]{8}", job_id)
    job = case_jobs.get_job(job_id)
    assert (job["job_id"], job["kind"], job["status"], job["result"], job["error"]) == \
           (job_id, "language_version", "running", None, "")

    case_jobs.update_job(job_id, status="done", result={"project_id": "proj_x", "rewritten_orders": [3]})
    job = case_jobs.get_job(job_id)
    assert job["status"] == "done" and job["result"] == {"project_id": "proj_x", "rewritten_orders": [3]}

    job["status"] = "failed"                                     # get_job trả bản sao
    assert case_jobs.get_job(job_id)["status"] == "done"

    assert case_jobs.get_job("job_00000000") is None
    with pytest.raises(KeyError):
        case_jobs.update_job("job_00000000", status="done")
    with pytest.raises(ValueError):
        case_jobs.update_job(job_id, status="khong-ro")
    with pytest.raises(ValueError):
        case_jobs.update_job(job_id, kind="khac")                # không đổi được loại job


def test_case_jobs_evicts_old_finished_jobs_but_never_a_running_one(monkeypatch):
    monkeypatch.setattr(case_jobs, "MAX_JOBS", 3)
    running = case_jobs.create_job("language_version")
    finished = []
    for _ in range(5):
        job_id = case_jobs.create_job("language_version")
        case_jobs.update_job(job_id, status="done")
        finished.append(job_id)

    assert case_jobs.get_job(running)["status"] == "running"     # việc đang chạy không bị bỏ
    assert case_jobs.get_job(finished[0]) is None                # việc xong cũ nhất bị bỏ trước
    assert case_jobs.get_job(finished[-1]) is not None


# ---------------------------------------------------------------- phân tích -> tiến độ -> kế hoạch

def test_analyze_then_progress_then_case(client, small_chunks, monkeypatch):
    use_llm(monkeypatch)

    response = client.post(f"{BASE}/analyze", json={"raw_report": DOSSIER})
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"case_id"}
    case_id = response.json()["case_id"]
    assert re.fullmatch(r"case_[0-9a-f]{8}", case_id)

    pipeline = case_store.load_pipeline(case_id)                  # mặc định 8 phút, phong cách neo-noir
    assert (pipeline.target_minutes, pipeline.visual_style) == (8, "neo_noir_silhouette")
    assert case_store.load_source(case_id) == DOSSIER

    progress = client.get(f"{BASE}/cases/{case_id}/progress")
    assert progress.status_code == 200
    assert progress.json() == {"status": "running", "step_label": "Đang đọc đoạn 1/2", "steps_done": 0,
                               "steps_total": 5, "error": ""}

    drain()

    progress = client.get(f"{BASE}/cases/{case_id}/progress").json()
    assert progress["status"] == "done" and progress["error"] == ""
    assert progress["steps_done"] == progress["steps_total"] == 12

    plan = get_plan(client, case_id)
    assert plan["case_id"] == case_id
    assert len(plan["scenes"]) == 7
    assert plan["scenes"][0]["visual_kind"] == "disclaimer"
    assert plan["scenes"][0]["narration_vi"] == DISCLAIMER["vi"]
    assert not any(s["flags"] for s in plan["scenes"])


def test_analyze_takes_minutes_and_style(client, small_chunks, monkeypatch):
    case_id = analyze(client, target_minutes=15, visual_style="cinematic_realistic")
    pipeline = case_store.load_pipeline(case_id)
    assert (pipeline.target_minutes, pipeline.visual_style) == (15, "cinematic_realistic")

    for bad in ({"target_minutes": 0}, {"target_minutes": 500}, {"target_minutes": "tám"}):
        assert client.post(f"{BASE}/analyze", json={"raw_report": DOSSIER, **bad}).status_code == 422
    unknown_style = client.post(f"{BASE}/analyze", json={"raw_report": DOSSIER, "visual_style": "khong-co-kieu-nay"})
    assert unknown_style.status_code == 400
    assert len(case_store.list_pipelines()) == 1                  # yêu cầu bị từ chối thì không tạo vụ nào


def test_case_not_ready_409(client, small_chunks, monkeypatch):
    use_llm(monkeypatch)
    case_id = analyze(client)

    response = client.get(f"{BASE}/cases/{case_id}")
    assert response.status_code == 409
    assert response.json()["detail"] == NOT_READY

    assert client.get(f"{BASE}/cases/case_00000000").status_code == 404          # không có vụ này
    assert client.get(f"{BASE}/cases/case_00000000/progress").status_code == 404
    assert client.put(f"{BASE}/cases/{case_id}/scenes/3", json={"narration_vi": "Lời mới"}).status_code == 409
    assert client.put(f"{BASE}/cases/{case_id}/entities",
                      json={"updates": [{"id": "person_1", "alias_vi": "A", "alias_en": "B"}]}).status_code == 409
    create = client.post(f"{BASE}/cases/{case_id}/create-project", json={"language": "vi", "voice": VI_VOICE})
    assert create.status_code == 409 and create.json()["detail"] == NOT_READY
    render = client.post(f"{BASE}/render-board-scene/6", json={"case_id": case_id, "language": "vi"})
    assert render.status_code == 409


def test_failed_pipeline_and_resume_route(client, small_chunks, monkeypatch):
    use_llm(monkeypatch, {"WRITE_VI p1": _thin_write_vi()})       # lời Việt mỏng cả 3 lần
    case_id = analyze(client)
    drain()

    progress = client.get(f"{BASE}/cases/{case_id}/progress").json()
    assert progress["status"] == "failed"
    assert progress["step_label"] == "Dừng ở bước viết lời Việt, nhịp 1/2"
    assert "lời Việt" in progress["error"]
    stored = next(s.error for s in case_store.load_pipeline(case_id).steps if s.status == "failed")
    assert progress["error"] == stored                            # thông báo không có tên thật thì giữ nguyên chữ
    not_ready = client.get(f"{BASE}/cases/{case_id}")
    assert not_ready.status_code == 409 and "Thử lại" in not_ready.json()["detail"]

    resumed = client.post(f"{BASE}/cases/{case_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running" and resumed.json()["error"] == ""
    assert client.get(f"{BASE}/cases/{case_id}/progress").json()["status"] == "running"

    use_llm(monkeypatch)                                          # LLM hết lỗi
    drain()
    assert client.get(f"{BASE}/cases/{case_id}/progress").json()["status"] == "done"
    assert len(get_plan(client, case_id)["scenes"]) == 7

    assert client.post(f"{BASE}/cases/case_00000000/resume").status_code == 404


def test_progress_error_never_contains_real_names(client, small_chunks, monkeypatch):
    # Alias trùng đúng tên thật: việc đặt tên hỏng, và thông báo của việc đó trích dẫn tên thật.
    bad = copy.deepcopy(load_fixture("ALIASES"))
    bad["entities"][0]["alias_vi"] = REAL_VICTIM
    use_llm(monkeypatch, {"ALIASES": bad})
    case_id = analyze(client)
    drain()

    stored = case_store.load_pipeline(case_id).steps[3].error
    assert REAL_VICTIM in stored                                  # tiền đề: thông báo gốc có tên thật
    progress = client.get(f"{BASE}/cases/{case_id}/progress").json()
    assert progress["status"] == "failed"
    assert "Hùng" not in progress["error"] and REAL_VICTIM not in progress["error"]
    assert case_redact.MASK in progress["error"]


def test_empty_and_too_long_report(client, isolated_projects_dir):
    for text in ("", "   \n\t  "):
        response = client.post(f"{BASE}/analyze", json={"raw_report": text})
        assert response.status_code == 400
        assert "trống" in response.json()["detail"]

    response = client.post(f"{BASE}/analyze", json={"raw_report": "x" * (MAX_SOURCE_CHARS + 1)})
    assert response.status_code == 413
    assert "ký tự" in response.json()["detail"]

    assert client.post(f"{BASE}/analyze", json={}).status_code == 422
    assert not (isolated_projects_dir / "_cases").exists()        # bị từ chối thì không lưu gì


# ---------------------------------------------------------------- sửa bảng tên

def scenes_mentioning(plan: dict, field: str, text: str) -> list[int]:
    return [s["order"] for s in plan["scenes"] if text in s[field]]


def test_entities_update_and_validation(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    before = get_plan(client, case_id)
    old_vi, old_en = "Trịnh Quang Vũ", "Trinh Quang Vu"
    vi_scenes = scenes_mentioning(before, "narration_vi", old_vi)
    en_scenes = scenes_mentioning(before, "narration_en", old_en)
    assert vi_scenes and en_scenes

    # Đổi tên thay thế của nạn nhân: lời kể chỉ còn tên mới.
    response = client.put(f"{BASE}/cases/{case_id}/entities", json={
        "updates": [{"id": "person_1", "alias_vi": "Triệu Văn Khôi", "alias_en": "Trieu Van Khoi"}]})
    assert response.status_code == 200, response.text
    after = response.json()
    assert after == get_plan(client, case_id)                     # PUT trả kế hoạch đã lưu
    assert scenes_mentioning(after, "narration_vi", old_vi) == []
    assert scenes_mentioning(after, "narration_en", old_en) == []
    assert scenes_mentioning(after, "narration_vi", "Triệu Văn Khôi") == vi_scenes
    assert scenes_mentioning(after, "narration_en", "Trieu Van Khoi") == en_scenes
    victim = next(e for e in after["bible"]["entities"] if e["id"] == "person_1")
    assert (victim["alias_vi"], victim["alias_en"]) == ("Triệu Văn Khôi", "Trieu Van Khoi")
    assert victim["real_names"] == next(e for e in before["bible"]["entities"] if e["id"] == "person_1")["real_names"]
    assert not any(s["flags"] for s in after["scenes"])
    assert old_vi not in json.dumps(after["scenes"], ensure_ascii=False)                    # cả prompt lẫn nhãn

    def put(updates=(), additions=()):
        return client.put(f"{BASE}/cases/{case_id}/entities", json={"updates": list(updates), "additions": list(additions)})

    def update(entity_id="person_1", alias_vi="Một Cái Tên", alias_en="Mot Cai Ten"):
        return put([{"id": entity_id, "alias_vi": alias_vi, "alias_en": alias_en}])

    # Alias trùng tên thay thế của thực thể khác (kể cả khác hoa thường, bỏ dấu) -> 400.
    for clash in ("Đặng Thu Hà", "ĐẶNG THU HÀ", "dang thu ha", "Dang Thu Ha"):
        assert update(alias_vi=clash).status_code == 400, clash
        assert update(alias_en=clash).status_code == 400, clash
    # Alias là một tên thật (kể cả bỏ dấu, viết hoa) -> 400, và thông báo không nhắc lại tên thật.
    for real in (REAL_VICTIM, "NGUYỄN VĂN HÙNG", "nguyen van hung", "Lê Thị Mai"):
        response = update(alias_vi=real)
        assert response.status_code == 400, real
        assert "Hùng" not in response.text and "Mai" not in response.text
        assert update(alias_en=real).status_code == 400, real
    # Alias là tên chỉ regex bắt được trên bài gốc -> 400.
    case_store.save_source(case_id, case_store.load_source(case_id) + f"\nÔng {REGEX_ONLY_NAME} là tài xế xe tải.")
    assert update(alias_vi=REGEX_ONLY_NAME).status_code == 400
    # Đầu vào sai khác -> 400.
    assert update(entity_id="person_99").status_code == 400
    assert update(alias_vi="   ").status_code == 400
    assert put().status_code == 400                                                         # không có thay đổi nào
    assert put([{"id": "person_1", "alias_vi": "A B", "alias_en": "A B"},
                {"id": "person_1", "alias_vi": "C D", "alias_en": "C D"}]).status_code == 400

    assert get_plan(client, case_id) == after                     # mọi yêu cầu bị từ chối đều không đổi kế hoạch


def test_entity_update_swaps_two_names_without_chaining(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    before = get_plan(client, case_id)
    victim_scenes = scenes_mentioning(before, "narration_vi", "Trịnh Quang Vũ")
    witness_scenes = scenes_mentioning(before, "narration_vi", "Đặng Thu Hà")
    assert victim_scenes and witness_scenes

    response = client.put(f"{BASE}/cases/{case_id}/entities", json={"updates": [
        {"id": "person_1", "alias_vi": "Đặng Thu Hà", "alias_en": "Dang Thu Ha"},
        {"id": "person_2", "alias_vi": "Trịnh Quang Vũ", "alias_en": "Trinh Quang Vu"},
    ]})
    assert response.status_code == 200, response.text
    after = response.json()
    assert scenes_mentioning(after, "narration_vi", "Đặng Thu Hà") == victim_scenes
    assert scenes_mentioning(after, "narration_vi", "Trịnh Quang Vũ") == witness_scenes


def test_entity_update_does_not_touch_a_longer_alias_that_contains_the_old_one(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    added = client.put(f"{BASE}/cases/{case_id}/entities", json={"additions": [
        {"kind": "place", "real_names": ["Bến Cũ"], "alias_vi": "Cảng Hải Yến Mới", "alias_en": "New Hai Yen Port"}]})
    assert added.status_code == 200, added.text
    both = ("Chiếc xe dừng ở Cảng Hải Yến Mới rồi quay đầu về Cảng Hải Yến, nơi mưa vẫn rơi trên những dãy container "
            "im lìm, và không một ai ngoài người trực ban còn thức vào lúc ấy của đêm.")
    assert client.put(f"{BASE}/cases/{case_id}/scenes/3", json={"narration_vi": both}).status_code == 200

    response = client.put(f"{BASE}/cases/{case_id}/entities", json={"updates": [
        {"id": "place_1", "alias_vi": "Cảng Long Hải", "alias_en": "Long Hai Port"}]})
    assert response.status_code == 200, response.text
    text = scene_of(response.json(), 3)["narration_vi"]
    assert "Cảng Hải Yến Mới" in text                             # tên dài hơn của thực thể khác không bị thay giữa chừng
    assert "về Cảng Long Hải," in text and "về Cảng Hải Yến," not in text


def test_entities_additions_apply_new_names_everywhere(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    case_store.save_source(case_id, case_store.load_source(case_id) + f"\nÔng {REGEX_ONLY_NAME} là tài xế xe tải.")
    leak = f"Trong màn mưa, {REGEX_ONLY_NAME} lặng lẽ đứng canh bên chiếc xe tải ở cuối bãi, không ai để ý tới ông cả."
    flagged = client.put(f"{BASE}/cases/{case_id}/scenes/3", json={"narration_vi": leak}).json()
    assert [f["kind"] for f in scene_of(flagged, 3)["flags"]] == ["unknown_name"]

    addition = {"kind": "person", "real_names": [REGEX_ONLY_NAME, "ông Tuấn"], "alias_vi": "Lục Gia Bảo",
                "alias_en": "Luc Gia Bao"}
    response = client.put(f"{BASE}/cases/{case_id}/entities", json={"additions": [addition]})
    assert response.status_code == 200, response.text
    plan = response.json()
    scene = scene_of(plan, 3)
    assert REGEX_ONLY_NAME not in scene["narration_vi"] and "Lục Gia Bảo" in scene["narration_vi"]
    assert scene["flags"] == []
    entity = plan["bible"]["entities"][-1]
    assert (entity["kind"], entity["alias_vi"], entity["alias_en"]) == ("person", "Lục Gia Bảo", "Luc Gia Bao")
    assert entity["real_names"] == [REGEX_ONLY_NAME, "ông Tuấn"]
    assert entity["id"] not in [e["id"] for e in plan["bible"]["entities"][:-1]]
    assert any("Lục Gia Bảo" in w for w in plan["warnings"])      # ghi lại lần tự thay tên

    def add(**changes):
        body = {**addition, "real_names": ["Phạm Văn Zed"], "alias_vi": "Mã Văn Khoa", "alias_en": "Ma Van Khoa", **changes}
        return client.put(f"{BASE}/cases/{case_id}/entities", json={"additions": [body]})

    assert add(alias_vi="Trịnh Quang Vũ").status_code == 400      # trùng tên thay thế có sẵn
    assert add(alias_vi="Lê Thị Mai").status_code == 400          # trùng tên thật
    assert add(real_names=["Lê Thị Mai"]).status_code == 400      # tên thật đã thuộc thực thể khác
    assert add(real_names=["Trịnh Quang Vũ"]).status_code == 400  # tên thật trùng một tên thay thế
    assert add(real_names=["  ", ""]).status_code == 400          # không có tên thật nào
    assert add(alias_en="").status_code == 400
    assert add(kind="khong-ro").status_code == 422
    assert get_plan(client, case_id) == plan


def test_entities_can_add_a_real_name_that_differs_only_in_diacritics(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    brother = "Nguyễn Văn Hưng"                                    # bỏ dấu thì trùng tên nạn nhân "Nguyễn Văn Hùng"
    case_store.save_source(case_id, case_store.load_source(case_id) + f"\nEm trai nạn nhân là {brother}.")
    text = (f"Đêm ấy, {brother} đứng chờ ở cổng cảng, còn {REAL_VICTIM} vẫn ngồi trong văn phòng xem sổ sách tới tận "
            "khuya, không hay biết gì về bóng người ngoài kia.")
    flagged = client.put(f"{BASE}/cases/{case_id}/scenes/3", json={"narration_vi": text}).json()
    assert [f["kind"] for f in scene_of(flagged, 3)["flags"]] == ["unknown_name"]     # không lọt lặng lẽ
    assert brother in scene_of(flagged, 3)["narration_vi"]

    def add(real_names):
        return client.put(f"{BASE}/cases/{case_id}/entities", json={"additions": [
            {"kind": "person", "real_names": real_names, "alias_vi": "Mã Văn Khoa", "alias_en": "Ma Van Khoa"}]})

    assert add(["NGUYỄN VĂN HÙNG"]).status_code == 400              # cùng cách viết, chỉ khác hoa thường
    response = add([brother])
    assert response.status_code == 200, response.text
    scene = scene_of(response.json(), 3)
    assert scene["flags"] == []
    assert scene["narration_vi"].startswith("Đêm ấy, Mã Văn Khoa đứng chờ") and "còn Trịnh Quang Vũ vẫn" in scene["narration_vi"]
    assert add([brother]).status_code == 400                        # giờ đã thuộc một thực thể

    # Viết không dấu thì không biết là ai: thay bằng tên của thực thể đứng trước, cảnh báo (không chặn, không nêu tên thật).
    english = "Nguyen Van Hung stood at the port gate in the rain, waiting for someone who never came back that night."
    plan = client.put(f"{BASE}/cases/{case_id}/scenes/4", json={"narration_en": english}).json()
    assert scene_of(plan, 4)["narration_en"].startswith("Trinh Quang Vu stood at the port gate")
    assert scene_of(plan, 4)["flags"] == []
    notes = [w for w in plan["check_warnings"] if "cảnh 4" in w]
    assert len(notes) == 1 and "Trinh Quang Vu" in notes[0]
    assert "Hùng" not in notes[0] and "Hưng" not in notes[0] and "Hung" not in notes[0]


SHORT_ALIASES = [CaseEntity(id="person_1", kind="person", real_names=["Trần Văn Bảo"], alias_vi="Nam", alias_en="Nam"),
                 CaseEntity(id="person_2", kind="person", real_names=["Lý Văn Cường"], alias_vi="Hùng", alias_en="Hung")]
SHORT_RENAMES = [{"id": "person_1", "alias_vi": "Tuấn", "alias_en": "Tuan"},
                 {"id": "person_2", "alias_vi": "Dũng", "alias_en": "Dung"}]


def save_one_scene_plan(entities, text_vi, text_en):
    """Lưu một kế hoạch đã xong gồm cảnh miễn trừ và một cảnh (order 2) có lời kể cho sẵn; trả case_id."""
    plan = CaseAdaptationPlan(
        case_id="case_0a1b2c3d", created_at="2026-10-20T00:00:00", model="test", target_minutes=8, visual_style="noir",
        bible=CaseBible(source_language="vi", culture="vietnamese", title_vi="Bến Cảng", title_en="The Docks", timeline=[],
                        entities=entities),
        parts=[StoryPart(id="p1", kind="hook", summary_vi=text_vi, event_ids=[], scene_count=1)],
        scenes=[AdaptedScene(order=1, part_id="disclaimer", narration_vi=DISCLAIMER["vi"], narration_en=DISCLAIMER["en"],
                             visual_kind="disclaimer"),
                AdaptedScene(order=2, part_id="p1", narration_vi=text_vi, narration_en=text_en, visual_kind="image")],
    )
    case_store.save_plan(plan)
    return plan.case_id


def test_entity_update_swaps_only_real_occurrences_of_short_aliases(client, isolated_projects_dir):
    text_vi = "Năm ấy, Nam sống một mình bên bến cảng. Hung thủ vẫn lẩn trốn, còn Hùng vẫn chờ."
    text_en = "That year, Nam lived alone by the docks. The killer was still out there, and Hung kept waiting."
    case_id = save_one_scene_plan(SHORT_ALIASES, text_vi, text_en)
    response = client.put(f"{BASE}/cases/{case_id}/entities", json={"updates": SHORT_RENAMES})
    assert response.status_code == 200, response.text
    after = response.json()
    expected_vi = "Năm ấy, Tuấn sống một mình bên bến cảng. Hung thủ vẫn lẩn trốn, còn Dũng vẫn chờ."
    assert scene_of(after, 2)["narration_vi"] == expected_vi           # "Năm", "Hung thủ" giữ nguyên
    assert after["parts"][0]["summary_vi"] == expected_vi
    assert scene_of(after, 2)["narration_en"] == ("That year, Tuan lived alone by the docks. The killer was still out "
                                                  "there, and Dung kept waiting.")


def test_entity_update_also_renames_the_other_language_form_of_the_old_name(client, isolated_projects_dir):
    # Lời Anh còn dạng tiếng Việt ("Hùng", "Lý Tiểu Long"), lời Việt còn dạng tiếng Anh của tên Hoa ("Li Xiaolong").
    # Dạng tiếng Anh viết không dấu trùng dạng Việt ("Hung") thì trong lời Việt là chữ "hung" ("Hung hăng"): giữ nguyên.
    entities = [SHORT_ALIASES[1], CaseEntity(id="person_3", kind="person", real_names=["Trương Vĩ Kiệt"],
                                             alias_vi="Lý Tiểu Long", alias_en="Li Xiaolong")]
    text_vi = "Hùng gặp Li Xiaolong ở bến cảng. Hung hăng, gã đàn ông lao tới."
    text_en = "Hùng met Lý Tiểu Long at the docks. Hung said nothing."
    case_id = save_one_scene_plan(entities, text_vi, text_en)
    response = client.put(f"{BASE}/cases/{case_id}/entities", json={"updates": [
        SHORT_RENAMES[1], {"id": "person_3", "alias_vi": "Lý Đại Hổ", "alias_en": "Li Dahu"}]})
    assert response.status_code == 200, response.text
    scene = scene_of(response.json(), 2)
    assert scene["narration_vi"] == "Dũng gặp Lý Đại Hổ ở bến cảng. Hung hăng, gã đàn ông lao tới."
    assert scene["narration_en"] == "Dung met Li Dahu at the docks. Dung said nothing."


def test_entity_update_leaves_country_and_region_names_that_contain_the_old_name(client, isolated_projects_dir):
    text_vi = "Nam rời Việt Nam sang Đài Loan, còn gia đình ở lại miền Nam."
    text_en = "Nam left Viet Nam for Taiwan; his family stayed in the South."
    case_id = save_one_scene_plan(SHORT_ALIASES, text_vi, text_en)
    response = client.put(f"{BASE}/cases/{case_id}/entities", json={"updates": SHORT_RENAMES})
    assert response.status_code == 200, response.text
    scene = scene_of(response.json(), 2)
    assert scene["narration_vi"] == "Tuấn rời Việt Nam sang Đài Loan, còn gia đình ở lại miền Nam."
    assert scene["narration_en"] == "Tuan left Viet Nam for Taiwan; his family stayed in the South."


# ---------------------------------------------------------------- sửa lời từng cảnh, tạo dự án

def test_scene_edit_validation_and_auto_alias(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    plan = get_plan(client, case_id)
    edited_vi = "Cảnh được người dùng viết lại bằng tay, kể rõ diễn biến và vẫn giữ nguyên nhịp của câu chuyện."

    response = client.put(f"{BASE}/cases/{case_id}/scenes/3", json={"narration_vi": edited_vi})
    assert response.status_code == 200, response.text
    after = response.json()
    assert scene_of(after, 3)["narration_vi"] == edited_vi
    assert scene_of(after, 3)["narration_en"] == scene_of(plan, 3)["narration_en"]       # trường không gửi thì giữ nguyên
    assert after == get_plan(client, case_id)

    # Tên thật đã có tên hư cấu thì được tự thay.
    leaky_en = "Nguyen Van Hung lay still between the containers while the rain kept falling on the silent yard."
    response = client.put(f"{BASE}/cases/{case_id}/scenes/4", json={"narration_en": leaky_en})
    assert response.status_code == 200
    assert scene_of(response.json(), 4)["narration_en"].startswith("Trinh Quang Vu lay still")
    assert scene_of(response.json(), 4)["flags"] == []

    # Ngày cụ thể: không tự sửa được, bị đánh dấu.
    response = client.put(f"{BASE}/cases/{case_id}/scenes/5",
                          json={"narration_vi": "Vụ việc xảy ra vào đêm ngày 15 tháng 10 năm 2021 giữa cơn mưa lớn ở bãi cảng."})
    assert [f["kind"] for f in scene_of(response.json(), 5)["flags"]] == ["date"]

    unchanged = get_plan(client, case_id)
    assert client.put(f"{BASE}/cases/{case_id}/scenes/99", json={"narration_vi": "x"}).status_code == 400      # order lạ
    assert client.put(f"{BASE}/cases/{case_id}/scenes/0", json={"narration_vi": "x"}).status_code == 400
    assert client.put(f"{BASE}/cases/{case_id}/scenes/1", json={"narration_vi": "x"}).status_code == 400       # cảnh miễn trừ
    assert client.put(f"{BASE}/cases/{case_id}/scenes/3", json={}).status_code == 400                          # không có gì để sửa
    assert client.put(f"{BASE}/cases/{case_id}/scenes/ba", json={"narration_vi": "x"}).status_code == 422
    assert client.put(f"{BASE}/cases/{case_id}/scenes/3", json={"narration_vi": "x" * 6000}).status_code == 422
    assert get_plan(client, case_id) == unchanged


def test_scene_edit_then_create_project(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    case_store.save_source(case_id, case_store.load_source(case_id) + f"\nÔng {REGEX_ONLY_NAME} là tài xế xe tải.")

    # Ghi vào lời kể một tên thật mà chỉ regex bắt được -> cảnh bị đánh dấu -> không tạo được dự án.
    leak = f"Trong màn mưa, {REGEX_ONLY_NAME} lặng lẽ đứng canh bên chiếc xe tải ở cuối bãi, không ai để ý tới ông cả."
    response = client.put(f"{BASE}/cases/{case_id}/scenes/3", json={"narration_vi": leak})
    assert response.status_code == 200
    assert [f["kind"] for f in scene_of(response.json(), 3)["flags"]] == ["unknown_name"]

    blocked = client.post(f"{BASE}/cases/{case_id}/create-project", json={"language": "vi", "voice": VI_VOICE})
    assert blocked.status_code == 409
    reason = blocked.json()["detail"]
    assert "3" in reason                                                    # nêu order cảnh bị đánh dấu
    assert "Hoàng" not in reason and "Tuấn" not in reason                   # nhưng không nêu tên thật
    assert [p for p in project_service.list_projects()] == []               # không tạo gì

    # Sửa sạch -> tạo được, dự án có đủ số cảnh.
    clean = "Trong màn mưa, một người đàn ông lặng lẽ đứng canh bên chiếc xe tải ở cuối bãi, không ai để ý tới ông cả."
    assert client.put(f"{BASE}/cases/{case_id}/scenes/3", json={"narration_vi": clean}).status_code == 200
    created = client.post(f"{BASE}/cases/{case_id}/create-project", json={
        "language": "vi", "voice": VI_VOICE, "voices": {"en": EN_VOICE}, "visual_style": "neo_noir_silhouette"})
    assert created.status_code == 200, created.text
    body = created.json()
    assert set(body) == {"project_id", "redirect_url"}
    assert body["project_id"].startswith("proj_crime_")
    assert body["redirect_url"] == f"/?project_id={body['project_id']}"

    fetched = client.get(f"/api/projects/{body['project_id']}")
    assert fetched.status_code == 200
    project = fetched.json()
    assert len(project["scenes"]) == 7
    assert project["scenes"][2]["text"] == clean
    assert project["voice"] == VI_VOICE and project["style_preset"] == "neo_noir_silhouette"
    assert project["image_provider"] == "meta_muse_cloud"
    assert project["metadata"]["language"] == "vi" and project["metadata"]["case_id"] == case_id
    assert project["metadata"]["voices"] == {"en": EN_VOICE, "vi": VI_VOICE}
    assert get_project(body["project_id"]) is not None


def test_date_flag_blocks_create_project(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    dated = "Vụ việc xảy ra vào đêm ngày 15 tháng 10 năm 2021 giữa cơn mưa lớn ở bãi cảng, không ai hay biết."
    assert client.put(f"{BASE}/cases/{case_id}/scenes/5", json={"narration_vi": dated}).status_code == 200

    blocked = client.post(f"{BASE}/cases/{case_id}/create-project", json={"language": "en", "voice": EN_VOICE})
    assert blocked.status_code == 409
    assert "5" in blocked.json()["detail"] and "2021" not in blocked.json()["detail"]


def test_create_project_validates_input(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    url = f"{BASE}/cases/{case_id}/create-project"

    assert client.post(url, json={"language": "fr", "voice": VI_VOICE}).status_code == 422
    assert client.post(url, json={"voice": VI_VOICE}).status_code == 422
    assert client.post(url, json={"language": "vi", "visual_style": "khong-co"}).status_code == 400
    assert client.post(url, json={"language": "vi", "image_provider": "../x"}).status_code == 400
    assert client.post(url, json={"language": "vi", "voices": {"fr": "x"}}).status_code == 400
    assert client.post(f"{BASE}/cases/case_00000000/create-project", json={"language": "vi"}).status_code == 404
    assert project_service.list_projects() == []

    # voice bỏ trống thì dùng giọng mặc định của ngôn ngữ
    response = client.post(url, json={"language": "en", "image_provider": "9router_gemini"})
    assert response.status_code == 200, response.text
    project = get_project(response.json()["project_id"])
    assert project.voice == "en-US-AndrewMultilingualNeural" and project.image_provider == "9router_gemini"
    assert project.scenes[0].text == DISCLAIMER["en"]


# ---------------------------------------------------------------- vẽ bảng ghim

def test_render_board_scene_writes_into_case_folder(client, small_chunks, monkeypatch, isolated_projects_dir):
    case_id = finished_case(client, monkeypatch)

    vi = client.post(f"{BASE}/render-board-scene/6", json={"case_id": case_id, "language": "vi"})
    en = client.post(f"{BASE}/render-board-scene/6", json={"case_id": case_id, "language": "en"})
    assert vi.status_code == en.status_code == 200, vi.text
    assert set(vi.json()) == {"image_path"}

    boards = isolated_projects_dir / "_cases" / case_id / "boards"
    assert Path(vi.json()["image_path"]) == boards / "board_006_vi.jpg"
    assert Path(en.json()["image_path"]) == boards / "board_006_en.jpg"
    for path in (boards / "board_006_vi.jpg", boards / "board_006_en.jpg"):
        assert path.is_file() and path.stat().st_size > 30000
        with Image.open(path) as img:
            assert img.size == (1920, 1080)

    static_boards = PROJECT_DIR / "backend" / "static" / "evidence_boards" / case_id
    assert not static_boards.exists()                             # thư mục static là công khai: không ghi vào đó

    assert client.post(f"{BASE}/render-board-scene/99", json={"case_id": case_id, "language": "vi"}).status_code == 400
    assert client.post(f"{BASE}/render-board-scene/6", json={"case_id": case_id, "language": "fr"}).status_code == 422
    assert client.post(f"{BASE}/render-board-scene/6", json={"case_id": "case_00000000", "language": "vi"}).status_code == 404
    assert client.post(f"{BASE}/render-board-scene/6", json={"case_id": "../x", "language": "vi"}).status_code == 400
    assert client.post(f"{BASE}/render-board-scene/0", json={"case_id": case_id, "language": "vi"}).status_code == 422


# ---------------------------------------------------------------- bản ngôn ngữ khác (job)

def test_create_language_version_route(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    vi_id = create_vi_project(client, case_id)
    plan = get_plan(client, case_id)

    response = client.post(f"/api/projects/{vi_id}/create-language-version", json={"language": "en"})
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"job_id", "already_running"}
    assert response.json()["already_running"] is False
    job_id = response.json()["job_id"]
    assert re.fullmatch(r"job_[0-9a-f]{8}", job_id)

    job = wait_job(client, job_id)
    assert job["status"] == "done", job
    assert job["error"] == ""
    assert job["result"]["project_id"] != vi_id
    assert job["result"]["rewritten_orders"] == []

    en = client.get(f"/api/projects/{job['result']['project_id']}").json()
    assert en["metadata"]["language"] == "en" and en["metadata"]["sibling_project_ids"] == [vi_id]
    assert en["voice"] == "en-US-AndrewMultilingualNeural"
    assert [s["text"] for s in en["scenes"]] == [s["narration_en"] for s in plan["scenes"]]
    assert client.get(f"/api/projects/{vi_id}").json()["metadata"]["sibling_project_ids"] == [en["id"]]

    # voice chọn riêng được dùng
    other = client.post(f"/api/projects/{vi_id}/create-language-version", json={"voice": "en-GB-RyanNeural"})
    assert other.status_code == 200                                # ngôn ngữ mặc định là "en"
    other_job = wait_job(client, other.json()["job_id"])
    assert other_job["status"] == "done"
    assert client.get(f"/api/projects/{other_job['result']['project_id']}").json()["voice"] == "en-GB-RyanNeural"


def test_create_language_version_rewrites_edited_scenes(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    vi_id = create_vi_project(client, case_id)
    saved = project_service.get_project(vi_id)
    edited_vi = "Run rẩy, bà Hà gọi trực ban hình sự và nói vừa thấy một bóng người áo khoác sẫm chạy qua cổng cảng."
    next(s for s in saved.scenes if s.order == 3).text = edited_vi
    project_service._save_project(saved)
    llm, calls = use_llm(monkeypatch, {"REWRITE_EN": {"scenes": [{"order": 3, "narration_en": REWRITE_3}]}})

    response = client.post(f"/api/projects/{vi_id}/create-language-version", json={"language": "en"})
    job = wait_job(client, response.json()["job_id"])

    assert job["status"] == "done", job
    assert job["result"]["rewritten_orders"] == [3]
    assert calls == ["REWRITE_EN"]
    en = get_project(job["result"]["project_id"])
    assert next(s for s in en.scenes if s.order == 3).text == REWRITE_3


def test_create_language_version_failures_are_reported_in_the_job(client, small_chunks, monkeypatch):
    # Dự án thường (không tạo từ kế hoạch): job failed với đúng thông báo của builder.
    plain = project_service.create_project(ProjectCreateRequest(name="Dự án thường"))
    response = client.post(f"/api/projects/{plain.id}/create-language-version", json={"language": "en"})
    assert response.status_code == 200
    job = wait_job(client, response.json()["job_id"])
    assert job["status"] == "failed" and job["result"] is None
    assert job["error"] == "Dự án này không được tạo từ kế hoạch chuyển thể."

    assert client.post("/api/projects/proj_khongco/create-language-version", json={"language": "en"}).status_code == 404
    assert client.post(f"/api/projects/{plain.id}/create-language-version", json={"language": "fr"}).status_code == 422
    assert client.get(f"{BASE}/jobs/job_00000000").status_code == 404

    # Đã ở ngôn ngữ đó
    case_id = finished_case(client, monkeypatch)
    vi_id = create_vi_project(client, case_id)
    job = wait_job(client, client.post(f"/api/projects/{vi_id}/create-language-version",
                                       json={"language": "vi"}).json()["job_id"])
    assert job["status"] == "failed" and job["error"] == "Dự án này đã ở ngôn ngữ đó."


def test_language_version_has_one_running_job_per_project_and_language(client, monkeypatch):
    # Giao diện tải lại trang giữa chừng rồi bấm lại: máy chủ trả đúng việc đang chạy, không tạo việc trùng.
    from routers import language_versions
    started = []

    async def fake_run(job_id, project_id, language, voice):
        started.append((job_id, project_id, language))

    monkeypatch.setattr(language_versions, "_run_job", fake_run)
    project = project_service.create_project(ProjectCreateRequest(name="Dự án gốc"))

    def post(language="en"):
        response = client.post(f"/api/projects/{project.id}/create-language-version", json={"language": language})
        assert response.status_code == 200, response.text
        return response.json()

    def running(language="en"):
        response = client.get(f"/api/projects/{project.id}/language-version-job", params={"language": language})
        assert response.status_code == 200, response.text
        return response.json()["job"]

    assert running() is None
    first = post()
    assert first["already_running"] is False and len(started) == 1
    job = running()
    assert job["job_id"] == first["job_id"] and job["status"] == "running"

    again = post()
    assert again == {"job_id": first["job_id"], "already_running": True}
    assert len(started) == 1                                        # không chạy thêm việc nào
    other_language = post("vi")
    assert other_language["job_id"] != first["job_id"] and len(started) == 2

    case_jobs.update_job(first["job_id"], status="done", result={"project_id": "proj_x", "rewritten_orders": []})
    assert running() is None                                        # việc đã xong không còn là việc đang chạy
    assert post()["job_id"] != first["job_id"] and len(started) == 3

    assert client.get(f"/api/projects/{project.id}/language-version-job", params={"language": "fr"}).status_code == 422
    assert client.get("/api/projects/..%2Fx/language-version-job").status_code in (400, 404)


def test_case_jobs_start_job_reuses_only_a_running_job_with_the_same_key():
    first, created = case_jobs.start_job("language_version", "proj_a:en")
    assert created is True
    assert case_jobs.start_job("language_version", "proj_a:en") == (first, False)
    assert case_jobs.find_running_job("language_version", "proj_a:en")["job_id"] == first
    assert case_jobs.start_job("language_version", "proj_b:en")[0] != first
    assert case_jobs.start_job("other_kind", "proj_a:en")[0] != first
    case_jobs.update_job(first, status="failed", error="x")
    assert case_jobs.find_running_job("language_version", "proj_a:en") is None
    second, created = case_jobs.start_job("language_version", "proj_a:en")
    assert created is True and second != first


def test_language_version_job_error_never_contains_real_names(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    vi_id = create_vi_project(client, case_id)
    saved = project_service.get_project(vi_id)
    next(s for s in saved.scenes if s.order == 3).text = "Một lời Việt mới cho cảnh ba, được sửa tay sau khi tạo dự án."
    project_service._save_project(saved)
    # Lời Anh quá ngắn (loại) và còn tên thật: thông báo của việc hỏng trích dẫn tên thật.
    bad = {"scenes": [{"order": 3, "narration_en": f"Short line about {REAL_VICTIM}."}]}
    use_llm(monkeypatch, {"REWRITE_EN": bad})

    job = wait_job(client, client.post(f"/api/projects/{vi_id}/create-language-version",
                                       json={"language": "en"}).json()["job_id"])

    assert job["status"] == "failed"
    assert "lời Anh" in job["error"]
    assert "Hùng" not in job["error"] and REAL_VICTIM not in job["error"]
    assert sorted(p["id"] for p in project_service.list_projects()) == [vi_id]        # không để lại dự án dở


def test_language_version_job_unexpected_error_is_reported_without_details(client, small_chunks, monkeypatch):
    case_id = finished_case(client, monkeypatch)
    vi_id = create_vi_project(client, case_id)

    async def boom(*args, **kwargs):
        raise RuntimeError(f"hỏng ngoài dự kiến liên quan tới {REAL_VICTIM}")

    from routers import language_versions
    monkeypatch.setattr(language_versions, "create_language_version", boom)
    job = wait_job(client, client.post(f"/api/projects/{vi_id}/create-language-version",
                                       json={"language": "en"}).json()["job_id"])
    assert job["status"] == "failed"
    assert "RuntimeError" in job["error"] and REAL_VICTIM not in job["error"] and "Hùng" not in job["error"]


# ---------------------------------------------------------------- luồng cũ đã bỏ, kiểm id

def test_old_routes_removed(client):
    assert client.post(f"{BASE}/fictionalize", json={"raw_report": DOSSIER, "duration_minutes": 1}).status_code in (404, 405)
    assert client.post(f"{BASE}/create-project", json={"raw_report": DOSSIER}).status_code in (404, 405)
    assert not hasattr(true_crime, "_CASE_PLAN_CACHE")
    assert not hasattr(true_crime, "CaseFictionalizerEngine")

    from services import case_fictionalizer
    for name in ("JubenshaMatrix", "ForeshadowingLedgerManager", "YouTubeReviewerScriptGenerator",
                 "CaseFictionalizerEngine"):
        assert not hasattr(case_fictionalizer, name), name
    for name in ("AnonymizerShield", "REGEX_PERSON", "REGEX_PLATE", "REGEX_PHONE", "REGEX_DATE", "VN_SURNAMES",
                 "FICTIONAL_SUSPECT_NAMES", "FICTIONAL_VICTIM_NAMES", "FICTIONAL_LOCATIONS"):
        assert hasattr(case_fictionalizer, name), name

    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any(p.startswith(f"{BASE}/fictionalize") or p == f"{BASE}/create-project" for p in paths)


def test_openapi_lists_the_new_routes_only(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in (f"{BASE}/analyze", f"{BASE}/cases/{{case_id}}", f"{BASE}/cases/{{case_id}}/progress",
                 f"{BASE}/cases/{{case_id}}/resume", f"{BASE}/cases/{{case_id}}/entities",
                 f"{BASE}/cases/{{case_id}}/scenes/{{order}}", f"{BASE}/cases/{{case_id}}/create-project",
                 f"{BASE}/render-board-scene/{{scene_id}}", f"{BASE}/jobs/{{job_id}}",
                 "/api/projects/{project_id}/create-language-version"):
        assert path in paths, path
    assert f"{BASE}/fictionalize" not in paths and f"{BASE}/create-project" not in paths


def test_path_ids_validated(client):
    # `..%2Fx` được giải mã thành `../x`: không bao giờ trả 200.
    assert client.get(f"{BASE}/cases/..%2Fx").status_code != 200
    assert client.get(f"{BASE}/cases/..%2Fx/progress").status_code != 200
    assert client.get(f"{BASE}/jobs/..%2Fx").status_code != 200

    for path in (f"{BASE}/cases/%2E%2E", f"{BASE}/cases/bad.id", f"{BASE}/cases/bad.id/progress",
                 f"{BASE}/cases/a%20b", f"{BASE}/jobs/bad.id", f"{BASE}/jobs/%2E%2E"):
        assert client.get(path).status_code == 400, path
    assert client.post(f"{BASE}/cases/bad.id/resume").status_code == 400
    assert client.put(f"{BASE}/cases/bad.id/entities", json={"updates": []}).status_code == 400
    assert client.put(f"{BASE}/cases/bad.id/scenes/3", json={"narration_vi": "x"}).status_code == 400
    assert client.post(f"{BASE}/cases/bad.id/create-project", json={"language": "vi"}).status_code == 400
    assert client.post("/api/projects/bad.id/create-language-version", json={"language": "en"}).status_code == 400
    assert client.post("/api/projects/%2E%2E/create-language-version", json={"language": "en"}).status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
