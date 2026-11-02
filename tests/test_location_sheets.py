"""Khoá bối cảnh (services/location_sheets.py, routers/location_sheets.py) và nới biểu cảm nhân vật đầu tròn.

Offline: LLM giả trả JSON dựng sẵn; Muse giả vẽ ảnh bằng PIL; dự án ghi vào thư mục tạm.
"""
import asyncio
import copy
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.schemas import Project, Scene  # noqa: E402
from routers import location_sheets as ls_router  # noqa: E402
from routers import muse_bridge as mb  # noqa: E402
from runners.muse_fleet_runner import MusePromptFormatter  # noqa: E402
from services import image_service, project_service  # noqa: E402
from services import location_sheets as ls  # noqa: E402

PID = "proj_crime_loc01"
THREAD = "https://muse.ai/thread/2d353dc3-3d3d-44b3-a3e7-51f54a295757"
APARTMENT = ("A cramped sixth-floor apartment living room: peeling pale green walls, a single window on the left with "
             "torn yellow curtains, a low brown sofa against the back wall, a round wooden table with a red thermos in "
             "the centre, a bare bulb hanging from the ceiling giving warm dim light, worn tiled floor.")
CORRIDOR = ("A long narrow police station corridor: grey concrete walls, a row of green metal doors on the right, a "
            "notice board on the left, flickering fluorescent tubes on the ceiling casting cold white light, a "
            "polished speckled terrazzo floor and a wooden bench at the far end.")


def _scene(n, prompt, kind="image", text=None):
    return Scene(id=f"scene_{n:03d}", order=n, text=text or f"Lời kể cảnh {n}.", image_prompt=prompt,
                 metadata={"visual_kind": kind})


def _make_project(images=True) -> Project:
    scenes = [
        _scene(1, "", kind="disclaimer"),
        _scene(2, "Wide shot of a cramped apartment living room with green walls, a woman sits on a brown sofa."),
        _scene(3, "Close-up of a red thermos on a round wooden table in the apartment."),
        _scene(4, "Medium shot of a detective walking down a grey police corridor under fluorescent lights."),
        _scene(5, "The woman looks out of the apartment window with torn yellow curtains at night."),
        _scene(6, "Two officers talk on a wooden bench at the end of the police corridor."),
        _scene(7, "A dark alley behind a market at dawn."),
    ]
    project = Project(id=PID, name="Vụ bối cảnh", style_preset="horror_cartoon_2d", scenes=scenes,
                      metadata={"case_id": "case_loc01"})
    project_service.ensure_project_dirs(PID)
    if images:
        for s in scenes[1:]:
            img = project_service.get_scene_media_paths(PID, s.id)["image"]
            Image.new("RGB", (1280, 720), (20 + s.order, 40, 60)).save(img)
            s.image_path = str(img)
    project_service.save_project(project)
    return project


GOOD = {"locations": [
    {"name_vi": "Phòng khách căn hộ tầng sáu", "description_en": APARTMENT,
     "scene_ids": ["scene_002", "scene_003", "scene_005"]},
    {"name_vi": "Hành lang đồn cảnh sát", "description_en": CORRIDOR, "scene_ids": ["scene_004", "scene_006"]},
]}


class FakeLLM:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    async def __call__(self, system, user, **kwargs):
        self.calls.append((system, user))
        return copy.deepcopy(self.answers.pop(0))


class FakeMuse:
    def __init__(self, fail_with=None):
        self.tasks, self.fail_with = [], fail_with

    async def __call__(self, task):
        self.tasks.append(copy.deepcopy(task))
        if self.fail_with:
            raise self.fail_with
        out = Path(task["output_path"])
        Image.new("RGB", (2048, 1152), (90, 90, 90)).save(out, "JPEG")
        return {"output_path": str(out), "thread_url": THREAD, "executed_by": "muse_acc_img_01"}


def _analyzed(llm=None):
    _make_project()
    return asyncio.run(ls.analyze_locations(PID, llm=llm or FakeLLM(GOOD)))


def _approved_apartment():
    data = _analyzed()
    loc_id = next(k for k, v in data.locations.items() if "căn hộ" in v.name_vi)
    asyncio.run(ls.draw_plate(PID, loc_id, FakeMuse()))
    ls.approve_plate(PID, loc_id)
    return loc_id


# ------------------------------------------------------------------------------------------------- tìm bằng LLM
def test_analyze_builds_recurring_locations_from_llm(isolated_projects_dir):
    llm = FakeLLM(GOOD)
    data = _analyzed(llm)
    assert len(llm.calls) == 1
    prompt = llm.calls[0][1]
    assert "id scene_002" in prompt and "id scene_007" in prompt and "id scene_001" not in prompt   # thẻ miễn trừ bỏ
    assert {v.name_vi for v in data.locations.values()} == {"Phòng khách căn hộ tầng sáu", "Hành lang đồn cảnh sát"}
    assert all(v.status == "draft" and len(v.scene_ids) >= 2 for v in data.locations.values())
    assert (isolated_projects_dir / PID / "locations" / "locations.json").is_file()
    assert ls.scene_location_map(ls.load_locations(PID))["scene_004"] in data.locations


@pytest.mark.parametrize("bad,reason", [
    ({"locations": [{"name_vi": "x", "description_en": APARTMENT, "scene_ids": ["scene_002", "scene_999"]}]},
     "scene_999"),
    ({"locations": [{"name_vi": "x", "description_en": APARTMENT, "scene_ids": ["scene_002"]}]}, "chỉ có 1 cảnh"),
    ({"locations": [{"name_vi": "x", "description_en": "small room", "scene_ids": ["scene_002", "scene_003"]}]},
     "từ"),
    ({"locations": [{"name_vi": "a", "description_en": APARTMENT, "scene_ids": ["scene_002", "scene_003"]},
                    {"name_vi": "b", "description_en": CORRIDOR, "scene_ids": ["scene_003", "scene_004"]}]},
     "mỗi cảnh chỉ thuộc một nơi"),
])
def test_analyze_rejects_bad_output_and_asks_again(isolated_projects_dir, bad, reason):
    llm = FakeLLM(bad, GOOD)
    data = _analyzed(llm)
    assert len(llm.calls) == 2 and reason in llm.calls[1][1]   # lý do gửi lại cho LLM
    assert len(data.locations) == 2


def test_analyze_needs_two_story_scenes(isolated_projects_dir):
    project = Project(id=PID, name="x", scenes=[_scene(1, "a"), _scene(2, "", kind="board")])
    project_service.save_project(project)
    with pytest.raises(ls.LocationError):
        asyncio.run(ls.analyze_locations(PID, llm=FakeLLM(GOOD)))


def test_reanalyze_keeps_manual_and_drawn_locations(isolated_projects_dir):
    loc_id = _approved_apartment()
    manual = ls.create_location(PID, "Con hẻm sau chợ", CORRIDOR.replace("police station", "market"),
                                ["scene_007", "scene_006"])
    data = asyncio.run(ls.analyze_locations(PID, llm=FakeLLM(GOOD)))
    assert data.locations[loc_id].status == "approved"
    assert data.locations[manual.location_id].scene_ids == ["scene_007", "scene_006"]
    corridor = [v for v in data.locations.values() if v.name_vi == "Hành lang đồn cảnh sát"]
    # cảnh 6 đã thuộc nơi tự thêm: nơi mới chỉ còn cảnh 4 (< 2 cảnh) nên bỏ
    assert corridor == []


# ------------------------------------------------------------------------------------------------ chỉnh tay
def test_edit_design_resets_approval_and_scene_moves_between_locations(isolated_projects_dir):
    loc_id = _approved_apartment()
    other = next(k for k in ls.load_locations(PID).locations if k != loc_id)
    ls.edit_location(PID, other, scene_ids=["scene_004", "scene_006", "scene_005"])
    data = ls.load_locations(PID)
    assert "scene_005" not in data.locations[loc_id].scene_ids                      # mỗi cảnh một nơi
    assert data.locations[loc_id].status == "approved"
    loc = ls.edit_location(PID, loc_id, design_en=APARTMENT + " A calendar hangs on the right wall.")
    assert loc.status == "draft"                                                      # đổi mô tả: duyệt lại
    with pytest.raises(ls.LocationError):
        ls.edit_location(PID, loc_id, design_en="too short")
    with pytest.raises(ls.LocationError):
        ls.edit_location(PID, loc_id, scene_ids=["scene_001", "scene_002"])           # thẻ miễn trừ không có bối cảnh
    ls.remove_location(PID, loc_id)
    assert loc_id not in ls.load_locations(PID).locations


# ------------------------------------------------------------------------------------------- vẽ ảnh chuẩn
def test_draw_plate_prompt_reference_and_redraw_in_same_chat(isolated_projects_dir):
    data = _analyzed()
    loc_id = next(k for k, v in data.locations.items() if "căn hộ" in v.name_vi)
    muse = FakeMuse()
    loc = asyncio.run(ls.draw_plate(PID, loc_id, muse))
    t = muse.tasks[0]
    assert loc.status == "review" and loc.plate_path and Path(loc.plate_path).is_file()
    assert t["raw_prompt"] and t["prompt"].startswith("tạo cho tôi 1 hình ảnh 2K tỉ lệ 16:9")
    assert APARTMENT in t["prompt"] and "no people" in t["prompt"]
    assert "round white heads" in t["prompt"]                                         # nét vẽ của dự án
    assert image_service.FEMALE_HAIR_RULE_EN not in t["prompt"]                       # ảnh không người: bỏ quy tắc tóc
    assert t["attachments"] == [project_service.get_scene_media_paths(PID, "scene_002")["image"].__str__()]
    assert "thread_url" not in t
    ls.reject_plate(PID, loc_id, "cửa sổ phải ở bên trái")
    asyncio.run(ls.draw_plate(PID, loc_id, muse))
    t2 = muse.tasks[1]
    assert t2["thread_url"] == THREAD and t2["pin_account"] and "cửa sổ phải ở bên trái" in t2["prompt"]
    assert t2["output_path"].endswith("plate_v2.jpg")
    with pytest.raises(ls.LocationError):
        ls.reject_plate(PID, loc_id, "  ")


def test_draw_failure_is_reported_not_silent(isolated_projects_dir):
    data = _analyzed()
    loc_id = next(iter(data.locations))
    loc = asyncio.run(ls.draw_plate(PID, loc_id, FakeMuse(fail_with=TimeoutError("hết giờ"))))
    assert loc.status == "failed" and "hết giờ" in loc.error
    with pytest.raises(ls.LocationError):
        ls.approve_plate(PID, loc_id)


# ------------------------------------------------------------------------------------------- dùng khi tạo ảnh
def test_scene_lock_only_for_approved_and_plate_only_when_place_visible(isolated_projects_dir):
    data = _analyzed()
    loc_id = next(k for k, v in data.locations.items() if "căn hộ" in v.name_vi)
    assert ls.scene_lock(PID, "scene_002", "wide shot") is None                        # chưa duyệt: chưa khoá
    asyncio.run(ls.draw_plate(PID, loc_id, FakeMuse()))
    assert ls.scene_lock(PID, "scene_002", "wide shot") is None                        # chờ duyệt: chưa khoá
    ls.approve_plate(PID, loc_id)
    lock = ls.scene_lock(PID, "scene_002", "Wide shot of the room")
    assert lock["location_id"] == loc_id and APARTMENT in lock["prompt_line"]
    assert lock["plate_path"] and Path(lock["plate_path"]).is_file()
    close = ls.scene_lock(PID, "scene_003", "Close-up of a red thermos")
    assert close["prompt_line"] == lock["prompt_line"] and close["plate_path"] is None
    assert ls.scene_lock(PID, "scene_007", "x") is None                                # cảnh không thuộc nơi nào
    assert ls.scene_lock("proj_khong_co", "scene_002", "x") is None


def test_generate_image_sends_fixed_description_and_plate_to_muse(isolated_projects_dir, monkeypatch):
    _approved_apartment()
    lock = ls.scene_lock(PID, "scene_002", "Wide shot")
    sent = []

    async def fake_enqueue(task):
        sent.append(copy.deepcopy(task))
        Image.new("RGB", (1280, 720)).save(task["output_path"])
        return {"output_path": task["output_path"]}

    monkeypatch.setattr(mb, "is_kind_online", lambda kind: True)
    monkeypatch.setattr(mb, "enqueue_and_wait_muse_task", fake_enqueue)
    out = isolated_projects_dir / PID / "images" / "scene_002.jpg"
    prev = isolated_projects_dir / PID / "images" / "scene_003.jpg"
    res = asyncio.run(image_service.generate_image("Wide shot of the room", style_preset="horror_cartoon_2d",
                                                   provider="meta_muse_cloud", output_path=str(out),
                                                   reference_image=str(prev), reference_role="previous_scene",
                                                   location=lock))
    assert res["success"]
    t = sent[0]
    assert APARTMENT in t["prompt"] and ls.LOCK_LINE_EN.strip()[:20] in t["prompt"]
    assert t["attachments"] == [str(prev), lock["plate_path"]]
    assert t["parameters"]["location_reference"] is True
    # Fleet Runner dặn Muse đúng vai trò từng ảnh: ảnh đầu là cảnh trước, ảnh cuối là ảnh chuẩn bối cảnh
    text = MusePromptFormatter.build_prompt(t, has_attachment=True)
    assert "Ảnh đính kèm đầu tiên là khung hình của cảnh ngay trước" in text
    assert "Ảnh đính kèm cuối cùng là ẢNH CHUẨN CỦA BỐI CẢNH" in text


def test_runner_text_with_plate_only_does_not_call_it_a_character_reference():
    t = {"mode": "text-to-image", "prompt": "p", "attachments": ["plate.jpg"],
         "parameters": {"location_reference": True}}
    text = MusePromptFormatter.build_prompt(t, has_attachment=True)
    assert "ẢNH CHUẨN CỦA BỐI CẢNH" in text and "ảnh tham chiếu" not in text
    old = MusePromptFormatter.build_prompt({"mode": "text-to-image", "prompt": "p", "reference_image_path": "a.jpg",
                                            "parameters": {"reference_role": "previous_scene"}}, has_attachment=True)
    assert old.count("Ảnh đính kèm là khung hình của cảnh ngay trước") == 1   # việc cũ không đổi câu dặn


def test_muse_2k_button_task_gets_location_lock(isolated_projects_dir, monkeypatch):
    _approved_apartment()
    queued = []
    monkeypatch.setattr(mb, "enqueue_task", lambda task: queued.append(task) or task)
    monkeypatch.setattr(mb, "ensure_local_fleet_runner", lambda: None)
    app = FastAPI()
    app.include_router(mb.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        r = c.post("/api/muse-bridge/tasks/create", json={"project_id": PID, "scene_id": "scene_005",
                                                         "mode": "text-to-image", "prompt": "The woman at the window"})
        assert r.status_code == 200
        r2 = c.post("/api/muse-bridge/tasks/create", json={"project_id": PID, "scene_id": "scene_007",
                                                          "mode": "text-to-image", "prompt": "Dark alley"})
        assert r2.status_code == 200
    t = queued[0]
    assert t["prompt"].startswith("The woman at the window") and APARTMENT in t["prompt"]
    assert len(t["attachments"]) == 1 and t["attachments"][0].endswith("plate_v1.jpg")
    assert queued[1]["prompt"] == "Dark alley" and "attachments" not in queued[1]      # cảnh không có bối cảnh khoá


def test_produce_and_gen_image_paths_pass_location(isolated_projects_dir, monkeypatch):
    """Nút "Gen lại ảnh AI" (gen-image) truyền khoá bối cảnh vào generate_image."""
    from routers import api as api_module
    _approved_apartment()
    seen = []

    async def fake_generate_image(**kwargs):
        seen.append(kwargs)
        Image.new("RGB", (64, 36)).save(kwargs["output_path"])
        return {"success": True, "image_path": kwargs["output_path"], "provider": "meta_muse_cloud"}

    monkeypatch.setattr(api_module, "generate_image", fake_generate_image)
    app = FastAPI()
    app.include_router(api_module.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        r = c.post(f"/api/projects/{PID}/scenes/scene_002/gen-image", json={})
    assert r.status_code == 200, r.text
    assert seen[0]["location"]["design_en"] == APARTMENT


# ---------------------------------------------------------------------------------------------------- API
@pytest.fixture
def client(isolated_projects_dir):
    app = FastAPI()
    app.include_router(ls_router.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c
    ls_router._drawing.clear()
    ls_router._analyzing.clear()


def _wait(pred, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return
        time.sleep(0.1)
    raise AssertionError("chờ quá lâu")


def test_api_full_flow(client, monkeypatch):
    _make_project()
    base = f"/api/projects/{PID}/locations"
    assert client.get("/api/projects/proj_khong_co/locations").status_code == 404
    assert client.get(base).json()["locations"] == []
    monkeypatch.setattr(ls, "call_llm_json", FakeLLM(GOOD))
    assert client.post(f"{base}/analyze").json() == {"analyzing": True}
    _wait(lambda: not client.get(base).json()["analyzing"])
    data = client.get(base).json()
    assert data["analysis_error"] is None and len(data["locations"]) == 2
    loc = next(v for v in data["locations"] if "căn hộ" in v["name_vi"])
    lid = loc["location_id"]
    assert client.post(f"{base}/{lid}/approve").status_code == 400                    # chưa có ảnh chuẩn
    assert client.get(f"{base}/{lid}/plate").status_code == 404
    assert client.put(f"{base}/{lid}", json={"design_en": "short"}).status_code == 400
    assert client.put(f"{base}/{lid}", json={"name_vi": "Căn hộ tầng 6"}).json()["name_vi"] == "Căn hộ tầng 6"
    muse = FakeMuse()
    monkeypatch.setattr(ls_router, "muse_call_starting_runner", muse)
    assert client.post(f"{base}/{lid}/draw").json()["drawing"] is True
    _wait(lambda: next(v for v in client.get(base).json()["locations"] if v["location_id"] == lid)["status"] == "review")
    assert client.get(f"{base}/{lid}/plate").status_code == 200
    assert client.post(f"{base}/{lid}/approve").json()["status"] == "approved"
    created = client.post(base, json={"name_vi": "Hẻm chợ", "design_en": CORRIDOR, "scene_ids": ["scene_007", "scene_006"]})
    assert created.status_code == 200 and created.json()["source"] == "manual"
    assert client.post(base, json={"name_vi": "x", "design_en": CORRIDOR, "scene_ids": ["scene_007"]}).status_code == 400
    assert client.post(base, json={"name_vi": "x", "design_en": CORRIDOR,
                                   "scene_ids": ["../x", "scene_006"]}).status_code == 400
    assert client.delete(f"{base}/{created.json()['location_id']}").json()["removed"] is True
    assert client.put(f"{base}/bad%20id", json={"name_vi": "x"}).status_code == 400


def test_api_analysis_failure_is_shown(client, monkeypatch):
    _make_project()
    from services.case_adaptation_llm import LLMError
    monkeypatch.setattr(ls, "call_llm_json", FakeLLM(*[{"x": 1}] * 10))
    client.post(f"/api/projects/{PID}/locations/analyze")
    base = f"/api/projects/{PID}/locations"
    _wait(lambda: not client.get(base).json()["analyzing"])
    assert "tìm bối cảnh lặp lại" in client.get(base).json()["analysis_error"]

    async def no_key(*a, **k):
        raise LLMError("auth", "Chưa cấu hình NINEROUTER_API_KEY")
    monkeypatch.setattr(ls, "call_llm_json", no_key)
    client.post(f"{base}/analyze")
    _wait(lambda: not client.get(base).json()["analyzing"])
    assert "NINEROUTER_API_KEY" in client.get(base).json()["analysis_error"]


# ------------------------------------------------------------------------------------- biểu cảm đầu tròn
def test_round_head_style_allows_expressions_but_never_real_or_anime_faces():
    style = image_service.STYLE_PRESETS["horror_cartoon_2d"]
    suffix = style["prompt_suffix"]
    for allowed in ("eyebrows", "tears", "half of the round white face shaded grey"):
        assert allowed in suffix
    assert "never a realistic human face and never an anime face" in suffix and "no nose" in suffix
    assert "irises" in suffix and image_service.FEMALE_HAIR_RULE_EN in suffix          # quy tắc tóc nữ giữ nguyên
    assert "realistic human face" in style["negative_prompt"] and "anime face" in style["negative_prompt"]
    from services.climax_brief import scene_brief
    project = Project(id="p", name="p", style_preset="horror_cartoon_2d")
    brief = scene_brief(project, Scene(id="s", order=1, text="t"), [], 1, 6, "XONG-1")
    assert "không lông mày" not in brief and "lông mày một nét" in brief and "KHÔNG BAO GIỜ thành mặt người" in brief
