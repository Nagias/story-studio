"""Một luồng làm truyện cho truyện chữ và vụ án (03/11/2026): nhân vật cố định của truyện chữ (services/story_cast.py),
khoá nhân vật ở mọi lần tạo ảnh cảnh (services/scene_locks.py), thứ tự và vai trò ảnh đính kèm cho Muse, lối vào chung
ở Bước 1, cảnh truyện chữ cùng dạng cảnh vụ án.

Offline: LLM giả, Muse giả vẽ ảnh bằng PIL, dự án ghi vào thư mục tạm.
"""
import ast
import asyncio
import copy
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.schemas import Project, Scene  # noqa: E402
from routers import api as api_module  # noqa: E402
from routers import character_sheets as cs_router  # noqa: E402
from routers import muse_bridge as mb  # noqa: E402
from runners.muse_fleet_runner import MusePromptFormatter  # noqa: E402
from services import character_sheets as cs  # noqa: E402
from services import climax_video, image_service, project_service, scene_locks, story_cast, story_review  # noqa: E402
from services.case_adaptation_steps import StepFailed  # noqa: E402
from tests.story_review_fakes import FakePeopleLLM, FakeStoryLLM  # noqa: E402

PID = "proj_story_flow01"


def _story_project(images: bool = False) -> Project:
    scenes = [Scene(id=f"scene_{n:03d}", order=n, text=f"Lý Minh Hạ bước vào căn phòng thứ {n}, tim đập mạnh.",
                    image_prompt=f"Medium shot, Ly Minh Ha opens door number {n} in a dim basement corridor.")
              for n in range(1, 5)]
    project = Project(id=PID, name="Truyện thử", style_preset="horror_cartoon_2d", scenes=scenes,
                      character_anchor="featuring character: an old samurai with a red cape")
    project_service.ensure_project_dirs(PID)
    if images:
        for s in scenes:
            img = project_service.get_scene_media_paths(PID, s.id)["image"]
            Image.new("RGB", (1280, 720), (30, 40, 50 + s.order)).save(img)
            s.image_path = str(img)
    project_service.save_project(project)
    return project


def _approve_with_sheet(entity_id: str) -> None:
    sheet = cs.characters_dir(PID) / f"duyet_ngoai_{entity_id}.jpg"   # bảng duyệt ngoài app, chép vào chỗ của nó
    Image.new("RGB", (1600, 900), (200, 200, 200)).save(sheet)
    cs.import_approved_sheet(PID, entity_id, sheet)


# ------------------------------------------------------------------------------------ tìm nhân vật của truyện chữ

def test_people_found_from_story_are_written_to_cast(isolated_projects_dir):
    _story_project()
    llm = FakePeopleLLM()
    cast = asyncio.run(story_cast.analyze_people(PID, llm=llm))
    assert [c.name_vi for c in cast.characters.values()] == ["Lý Minh Hạ", "Giáo sư Trần"]
    hero = cast.characters["nv_1"]
    assert hero.source == "story" and hero.gender == "male"
    assert "messy black hair" in hero.design_en and "Drawing style:" in hero.design_en   # ghép phong cách dự án
    assert cast.scene_cast["scene_001"] == ["nv_1", "nv_2"] and cast.scene_cast["scene_004"] == ["nv_1"]
    assert "TASK: PEOPLE" in llm.calls[0] and "scene_003" in llm.calls[0]


def test_short_appearance_is_sent_back_for_rewrite(isolated_projects_dir):
    _story_project()
    llm = FakePeopleLLM(broken="short_look")
    cast = asyncio.run(story_cast.analyze_people(PID, llm=llm))
    assert len(llm.calls) == 2                                  # lần đầu sai luật: bị trả lại, viết lại
    assert "messy black hair" in cast.characters["nv_1"].design_en


def test_validator_rejects_unknown_scene_and_duplicate_name(isolated_projects_dir):
    project = _story_project()
    look = FakePeopleLLM.LOOK
    with pytest.raises(story_cast.StepRejected, match="không có trong danh sách"):
        story_cast.validate_people({"people": [{"name": "A", "appearance_en": look, "scene_ids": ["scene_999"]}]},
                                   project)
    with pytest.raises(story_cast.StepRejected, match="hai lần"):
        story_cast.validate_people({"people": [{"name": "A", "appearance_en": look, "scene_ids": ["scene_001"]},
                                               {"name": "a", "appearance_en": look, "scene_ids": ["scene_002"]}]},
                                   project)


def test_rerun_keeps_approved_sheet_and_its_design(isolated_projects_dir):
    _story_project()
    asyncio.run(story_cast.analyze_people(PID, llm=FakePeopleLLM()))
    cs.set_design(PID, "nv_1", "Appearance: chủ dự án sửa tay, áo khoác đỏ.")
    _approve_with_sheet("nv_1")
    cast = asyncio.run(story_cast.analyze_people(PID, llm=FakePeopleLLM()))
    assert cast.characters["nv_1"].status == "approved"
    assert "chủ dự án sửa tay" in cast.characters["nv_1"].design_en


def test_case_project_takes_people_from_name_table(isolated_projects_dir, monkeypatch):
    project = _story_project()
    monkeypatch.setattr(cs, "case_people", lambda p: [object()])
    with pytest.raises(cs.CastError, match="bảng tên"):
        asyncio.run(story_cast.analyze_people(project.id, llm=FakePeopleLLM()))


# ------------------------------------------------------------------------------------------- khoá nhân vật

def test_scene_without_cast_has_no_lock_and_writes_no_file(isolated_projects_dir):
    _story_project()
    assert scene_locks.character_lock(PID, "scene_001") is None
    assert not (isolated_projects_dir / PID / "characters").exists()


def test_character_lock_has_fixed_looks_and_board_of_approved_sheets(isolated_projects_dir):
    _story_project()
    asyncio.run(story_cast.analyze_people(PID, llm=FakePeopleLLM()))
    lock = scene_locks.character_lock(PID, "scene_001")
    assert lock["entity_ids"] == ["nv_1", "nv_2"] and lock["board_path"] is None
    assert scene_locks.CHARACTER_LINE_EN in lock["prompt_line"]
    assert "Lý Minh Hạ: A slender young East Asian man" in lock["prompt_line"]
    assert "Drawing style:" not in lock["prompt_line"] and cs.ANGLE_RULE_EN not in lock["prompt_line"]
    assert "hair" in lock["prompt_line"].split("Giáo sư Trần:", 1)[1]   # nữ + đầu tròn: quy tắc tóc
    _approve_with_sheet("nv_1")
    lock = scene_locks.character_lock(PID, "scene_002")
    assert lock["board_path"] and Path(lock["board_path"]).is_file()
    assert "CHARACTER SHEET shows Lý Minh Hạ" in lock["prompt_line"]


def test_attachments_order_and_roles():
    chars = {"entity_ids": ["nv_1"], "names": ["A"], "prompt_line": "FIXED CHARACTERS: A", "board_path": "board.jpg"}
    loc = {"location_id": "loc_1", "prompt_line": "FIXED LOCATION: room", "plate_path": "plate.jpg"}
    prev = {"prompt": "p", "reference_image_path": "prev.jpg", "parameters": {"reference_role": "previous_scene"}}
    t = scene_locks.apply_to_image_task(copy.deepcopy(prev), loc, chars)
    assert t["attachments"] == ["board.jpg", "prev.jpg", "plate.jpg"]
    assert t["parameters"]["attachment_roles"] == ["characters", "previous_scene", "location"]
    assert "FIXED CHARACTERS: A" in t["prompt"] and "FIXED LOCATION: room" in t["prompt"]
    text = MusePromptFormatter.build_prompt(t, has_attachment=True)
    assert "Ảnh đính kèm đầu tiên là BẢNG NHÂN VẬT" in text
    assert "Ảnh đính kèm thứ hai là khung hình của cảnh ngay trước" in text
    assert "Ảnh đính kèm cuối cùng là ẢNH CHUẨN CỦA BỐI CẢNH" in text
    # ảnh nhân vật chung cũ của dự án nhường chỗ cho khoá nhân vật, kể cả khi chưa có bảng duyệt
    old = {"prompt": "p", "reference_image_path": "hero.jpg", "character_anchor": "old hero",
           "parameters": {"character_anchor": "old hero"}}
    t = scene_locks.apply_to_image_task(old, None, dict(chars, board_path=None))
    assert t["reference_image_path"] is None and t["character_anchor"] == "" and "attachments" not in t
    assert "character_anchor" not in t["parameters"]


def test_generate_image_sends_board_and_drops_project_anchor(isolated_projects_dir, monkeypatch):
    _story_project()
    asyncio.run(story_cast.analyze_people(PID, llm=FakePeopleLLM()))
    _approve_with_sheet("nv_1")
    sent = []

    async def fake_enqueue(task):
        sent.append(copy.deepcopy(task))
        Image.new("RGB", (1280, 720)).save(task["output_path"])
        return {"output_path": task["output_path"]}

    monkeypatch.setattr(mb, "is_kind_online", lambda kind: True)
    monkeypatch.setattr(mb, "enqueue_and_wait_muse_task", fake_enqueue)
    project = project_service.get_project(PID)
    out = isolated_projects_dir / PID / "images" / "scene_003.jpg"
    locks = scene_locks.scene_locks(PID, "scene_003", project.scenes[2].image_prompt)
    res = asyncio.run(image_service.generate_image(
        project.scenes[2].image_prompt, style_preset=project.style_preset, character_anchor=project.character_anchor,
        provider="meta_muse_cloud", output_path=str(out), location=locks["location"], characters=locks["characters"]))
    assert res["success"]
    t = sent[0]
    assert "old samurai" not in t["prompt"] and "Lý Minh Hạ" in t["prompt"]
    assert t["attachments"] == [locks["characters"]["board_path"]]
    assert t["parameters"]["attachment_roles"] == ["characters"]


def test_muse_2k_button_task_gets_character_lock(isolated_projects_dir, monkeypatch):
    _story_project()
    asyncio.run(story_cast.analyze_people(PID, llm=FakePeopleLLM()))
    queued = []
    monkeypatch.setattr(mb, "enqueue_task", lambda task: queued.append(task) or task)
    monkeypatch.setattr(mb, "ensure_local_fleet_runner", lambda: None)
    app = FastAPI()
    app.include_router(mb.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        r = c.post("/api/muse-bridge/tasks/create", json={"project_id": PID, "scene_id": "scene_002",
                                                         "mode": "text-to-image", "prompt": "Ly opens the door",
                                                         "character_anchor": "an old samurai",
                                                         "parameters": {"style_preset": "horror_cartoon_2d"}})
        assert r.status_code == 200
    assert "Lý Minh Hạ" in queued[0]["prompt"] and queued[0]["character_anchor"] == ""
    # câu mô tả phong cách đầu tròn, không chỉ mã phong cách (03/11/2026: Muse 2K chỉ gửi mã nên ảnh sai phong cách)
    assert image_service.STYLE_PRESETS["horror_cartoon_2d"]["prompt_suffix"] in queued[0]["prompt"]


def test_every_scene_image_path_in_routers_passes_both_locks():
    """Khoá cứng: mọi chỗ tạo ảnh cảnh trong routers/api.py gửi kèm khoá nhân vật và khoá bối cảnh (trừ /gen-image tạo
    ảnh lẻ không thuộc dự án)."""
    tree = ast.parse((BACKEND_DIR / "routers" / "api.py").read_text(encoding="utf-8"))
    missing = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name == "generate_standalone_image":
            continue
        for call in ast.walk(fn):
            if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "generate_image":
                kws = {k.arg for k in call.keywords}
                if not {"characters", "location"} <= kws:
                    missing.append(f"{fn.name}:{call.lineno}")
    assert not missing, f"generate_image() thiếu khoá nhân vật/bối cảnh ở: {missing}"
    bridge = (BACKEND_DIR / "routers" / "muse_bridge.py").read_text(encoding="utf-8")
    assert "scene_locks.apply_to_image_task(" in bridge


# ------------------------------------------------------------------------------------- bảng nhân vật qua API

def test_analyze_api_runs_in_background_and_reports(isolated_projects_dir, monkeypatch):
    _story_project()
    monkeypatch.setattr(story_cast, "call_llm_json", FakePeopleLLM())
    app = FastAPI()
    app.include_router(cs_router.router)
    with TestClient(app) as client:
        base = f"/api/projects/{PID}/characters"
        assert client.get(base).json()["source"] == "story"
        assert client.post(f"{base}/analyze").status_code == 200
        for _ in range(100):
            data = client.get(base).json()
            if not data["analyzing"]:
                break
            asyncio.run(asyncio.sleep(0.05))
        assert data["analyzed_at"] and len(data["characters"]) == 2 and data["analysis_error"] is None


def test_analyze_failure_is_recorded(isolated_projects_dir, monkeypatch):
    _story_project()

    async def broken(*_a, **_k):
        raise StepFailed("9router không trả lời")
    monkeypatch.setattr(story_cast, "ask_validated", broken)
    asyncio.run(cs_router._analyze(PID))
    assert "9router không trả lời" in cs.load_cast(PID).analysis_error


# --------------------------------------------------------------------- truyện chữ thành dự án (lối vào chung)

@pytest.fixture
def client(isolated_projects_dir, monkeypatch):
    monkeypatch.setattr(api_module, "PROJECTS_DIR", isolated_projects_dir)
    monkeypatch.setattr(story_review, "_story_llm", FakeStoryLLM())
    monkeypatch.setattr(story_cast, "call_llm_json", FakePeopleLLM())
    app = FastAPI()
    app.include_router(api_module.router)
    with TestClient(app) as c:
        yield c


def _story_text() -> str:
    from tests.test_story_review import _story
    return _story(1)


def test_one_click_finds_people_and_makes_no_images(client, monkeypatch):
    calls = []

    async def no_image(**kw):
        calls.append(kw)
        return {"success": False, "error": "không được gọi"}
    monkeypatch.setattr(api_module, "generate_image", no_image)
    resp = client.post("/api/projects/create-from-script", json={"text": _story_text(), "output_language": "vi"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert calls == []                                            # làm từng bước: không tự tạo ảnh
    assert body["metadata"]["story_cast"] == {"people": 2, "error": None}
    meta = body["scenes"][0]["metadata"]
    assert meta["visual_kind"] == "image" and meta["part_id"] == "phan_1"
    cast = cs.load_cast(body["id"])
    assert set(cast.scene_cast) == {s["id"] for s in body["scenes"]}


def test_one_click_keeps_project_when_people_search_fails(client, monkeypatch):
    async def broken(*_a, **_k):
        raise StepFailed("9router không trả lời")
    monkeypatch.setattr(story_cast, "ask_validated", broken)
    resp = client.post("/api/projects/create-from-script", json={"text": _story_text()})
    assert resp.status_code == 200
    assert "9router không trả lời" in resp.json()["metadata"]["story_cast"]["error"]


def test_story_scenes_get_library_sound_cues_only():
    raw = {"scenes": [{"text": "Cánh cửa bật mở, một tiếng động vang lên làm cả căn phòng lặng đi trong giây lát.",
                       "covers": ["p1"], "image_prompt": "door", "sfx_cue": ["Door Creak", "dragon roar"]}]}
    scenes = story_review.check_written(raw, ["p1"], "Cánh cửa bật mở.", "vi", "vi")
    assert scenes[0]["sfx_cue"] == ["door_creak"]


def test_old_story_scene_without_kind_counts_as_drawn():
    s = Scene(id="scene_001", order=1, text="x", image_prompt="y")
    assert cs.is_drawn_scene(s) and climax_video.is_eligible(s)
    board = Scene(id="scene_002", order=2, text="x", metadata={"visual_kind": "board"})
    assert not cs.is_drawn_scene(board) and not climax_video.is_eligible(board)


# ---------------------------------------------------------------------------------- Bước 1: một lối vào

def _select_values(html: str, select_id: str) -> list[str]:
    m = re.search(rf'<select id="{select_id}"[^>]*>(.*?)</select>', html, re.S)
    assert m, f"không thấy ô {select_id}"
    return re.findall(r'<option value="([^"]+)"', m.group(1))


def test_style_lists_are_the_same_everywhere():
    """Khoá cứng: Bước 1, cửa sổ vụ án và cài đặt dự án cho chọn cùng một danh sách phong cách (có đầu tròn), mọi
    phong cách đều có trong STYLE_PRESETS."""
    html = (BACKEND_DIR / "static" / "index.html").read_text(encoding="utf-8")
    lists = {sid: _select_values(html, sid) for sid in ("step1-style-select", "tc-visual-style", "select-project-style")}
    assert lists["step1-style-select"] == lists["tc-visual-style"] == lists["select-project-style"]
    assert "horror_cartoon_2d" in lists["step1-style-select"]
    assert set(lists["step1-style-select"]) <= set(image_service.STYLE_PRESETS)


def test_step1_has_one_entry_for_story_and_case():
    html = (BACKEND_DIR / "static" / "index.html").read_text(encoding="utf-8")
    assert _select_values(html, "step1-content-kind") == ["story", "case"]
    app_js = (BACKEND_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert "generate_initial_images: false" in app_js and "generate_initial_images: true" not in app_js
    assert "window.tcStartFromStep1(" in app_js
    assert "window.tcStartFromStep1 = tcStartFromStep1" in (BACKEND_DIR / "static" / "true_crime.js").read_text(
        encoding="utf-8")


def test_people_search_reads_the_original_story(isolated_projects_dir):
    """Lời review có thể lược chi tiết ngoại hình (03/11/2026: mất "bộ ria bạc"): bước tìm nhân vật đọc cả truyện gốc."""
    _story_project()
    story_cast.save_source(PID, "Ông Tư, bác bảo vệ già có bộ ria bạc và chiếc áo khoác xanh bạc màu.")
    llm = FakePeopleLLM()
    asyncio.run(story_cast.analyze_people(PID, llm=llm))
    assert "TRUYỆN GỐC" in llm.calls[0] and "bộ ria bạc" in llm.calls[0]


def test_produce_request_keeps_each_scene_motion():
    """Nút "Sản xuất video dài" không gửi chuyển động chung (gặp 03/11/2026: "zoom_in" chung đè chuyển động riêng của
    mọi cảnh, cả video một kiểu)."""
    app_js = (BACKEND_DIR / "static" / "app.js").read_text(encoding="utf-8")
    block = app_js.split("const produceReq = {", 1)[1].split("};", 1)[0]
    assert "camera_motion:" not in block
