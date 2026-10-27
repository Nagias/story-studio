"""Bảng nhân vật đủ góc cho dự án vụ án (services/character_sheets.py, routers/character_sheets.py).

Offline: Muse giả vẽ ảnh bằng PIL; kế hoạch vụ án giả 3 người lưu bằng case_store vào thư mục tạm.
"""
import asyncio
import copy
import sys
from pathlib import Path

import pytest
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.case_adaptation_schemas import CaseAdaptationPlan, CaseBible, CaseEntity  # noqa: E402
from models.schemas import Project, Scene  # noqa: E402
from services import case_store, project_service  # noqa: E402
from services import character_sheets as cs  # noqa: E402

THREAD = "https://muse.ai/thread/2d353dc3-3d3d-44b3-a3e7-51f54a295757"
PID = "proj_crime_cast01"
EXAMINER = ("An elderly East Asian forensic examiner in his late 60s with silver-streaked hair, rimless spectacles, "
            "calm authoritative posture, wearing a white lab coat")
VICTIM = ("A slender East Asian woman in her early 20s with delicate features, shoulder-length wavy dark hair, "
          "expressive eyes, wearing a vintage pastel blouse")
PATRIARCH = ("An imposing East Asian clan patriarch in his late 60s with silver-white hair, solemn aristocratic "
             "posture, dressed in a dark silk tang suit")


def _person(eid, name, appearance, role="other"):
    return CaseEntity(id=eid, kind="person", real_names=["X"], role=role, alias_vi=name, alias_en=name,
                      appearance_en=appearance)


def _make_project(tmp_images: bool = True) -> Project:
    plan = CaseAdaptationPlan(
        case_id="case_cast01", created_at="2026-10-28", model="fake", target_minutes=8, visual_style="horror_cartoon_2d",
        bible=CaseBible(source_language="vi", culture="vn", title_vi="t", title_en="t", timeline=[],
                        entities=[_person("person_1", "Thẩm Nhã Uyên", VICTIM, "victim"),
                                  _person("person_2", "Lương Kiến Vĩ", EXAMINER, "investigator"),
                                  _person("person_15", "Gia tộc họ Tiền", PATRIARCH, "family"),
                                  CaseEntity(id="place_1", kind="place", real_names=["Y"], alias_vi="Trạm",
                                             alias_en="Station")]),
        parts=[], scenes=[])
    case_store.save_plan(plan)
    scenes = [
        Scene(id="scene_012", order=12, text="a", metadata={"visual_kind": "image"},
              image_prompt="Over-the-shoulder medium shot of an elderly East Asian forensic examiner in his late 60s "
                           "with silver-streaked hair, rimless spectacles, wearing a white lab coat."),
        Scene(id="scene_028", order=28, text="b", metadata={"visual_kind": "video"},
              image_prompt="Near a parked red sedan, a slender East Asian woman in her early 20s with shoulder-length "
                           "wavy dark hair hurries toward a dark entrance."),
        Scene(id="scene_063", order=63, text="c", metadata={"visual_kind": "image"},
              image_prompt="Two East Asian detectives search an archive room."),
        Scene(id="scene_001", order=1, text="d", metadata={"visual_kind": "disclaimer"}),
    ]
    project = Project(id=PID, name="Vụ thử", style_preset="horror_cartoon_2d", scenes=scenes,
                      metadata={"case_id": "case_cast01"})
    project_service.ensure_project_dirs(PID)
    if tmp_images:
        for s in scenes[:3]:
            img = project_service.get_scene_media_paths(PID, s.id)["image"]
            Image.new("RGB", (1280, 720), (30 + s.order, 40, 60)).save(img)
            s.image_path = str(img)
    project_service.save_project(project)
    return project


class FakeMuse:
    def __init__(self, fail_with=None):
        self.tasks, self.fail_with = [], fail_with

    async def __call__(self, task):
        self.tasks.append(copy.deepcopy(task))
        if self.fail_with:
            raise self.fail_with
        out = Path(task["output_path"])
        Image.new("RGB", (2048, 1152), (200, 200, 200)).save(out, "JPEG")
        return {"output_path": str(out), "thread_url": THREAD, "executed_by": "muse_acc_vid_02"}


# ----------------------------------------------------------------------------------------------------- dịch vụ
def test_load_cast_builds_people_from_case_plan(isolated_projects_dir):
    _make_project()
    cast = cs.load_cast(PID)
    assert set(cast.characters) == {"person_1", "person_2", "person_15"}          # chỉ người, không địa điểm
    s = cast.characters["person_1"]
    assert s.status == "draft" and s.name_vi == "Thẩm Nhã Uyên"
    assert VICTIM in s.design_en and cs.ANGLE_RULE_EN in s.design_en
    assert "round white heads" in s.design_en                                    # nét vẽ của phong cách dự án
    assert (isolated_projects_dir / PID / "characters" / "characters.json").is_file()


def test_load_cast_unknown_project_creates_nothing(isolated_projects_dir):
    with pytest.raises(LookupError):
        cs.load_cast("proj_khong_co")
    assert not (isolated_projects_dir / "proj_khong_co").exists()


def test_guess_scene_cast_matches_distinct_appearance_and_resolves_overlap():
    app = {"person_1": VICTIM, "person_2": EXAMINER, "person_15": PATRIARCH}
    # "in his late 60s with silver" cũng khớp người 15, nhưng người 2 khớp dài hơn trên cùng đoạn
    assert cs.guess_scene_cast("an elderly East Asian forensic examiner in his late 60s with silver-streaked hair", app) \
        == ["person_2"]
    assert cs.guess_scene_cast("a slender East Asian woman in her early 20s with shoulder-length wavy dark hair "
                               "talks to an elderly East Asian forensic examiner in his late 60s", app) \
        == ["person_1", "person_2"]
    assert cs.guess_scene_cast("Two East Asian detectives search an archive room.", app) == []
    assert cs.guess_scene_cast("", app) == []


def test_owner_scene_cast_overrides_guess(isolated_projects_dir):
    project = _make_project()
    cast = cs.load_cast(PID)
    assert cs.scene_cast(project, cast)["scene_028"] == ["person_1"]
    cs.set_scene_cast(PID, "scene_028", ["person_1", "person_2", "person_1"])
    cast = cs.load_cast(PID)
    assert cs.scene_cast(project, cast)["scene_028"] == ["person_1", "person_2"]
    assert "scene_001" not in cs.scene_cast(project, cast)                       # thẻ miễn trừ không có nhân vật
    with pytest.raises(cs.CastError):
        cs.set_scene_cast(PID, "scene_028", ["person_99"])
    with pytest.raises(LookupError):
        cs.set_scene_cast(PID, "scene_999", ["person_1"])


def test_sheet_prompt_contains_layout_design_and_feedback():
    sheet = cs.CharacterSheet(entity_id="person_1", name_vi="X", design_en="Appearance: round white head",
                              feedback=["tóc lúc phủ cả đầu lúc chỉ ở dưới"])
    p = cs.sheet_prompt(sheet)
    assert p.startswith("tạo cho tôi 1 hình ảnh 2K tỉ lệ 16:9:")
    for part in ("LEFT SIDE", "RIGHT SIDE", "BACK", "TOP", "Appearance: round white head",
                 "Bản trước SAI: tóc lúc phủ cả đầu lúc chỉ ở dưới", "no text"):
        assert part in p


def test_draw_sheet_reuses_thread_and_pins_account_on_redraw(isolated_projects_dir):
    _make_project()
    muse = FakeMuse()
    ref = project_service.get_scene_media_paths(PID, "scene_028")["image"]
    s1 = asyncio.run(cs.draw_sheet(PID, "person_1", muse, ref))
    t1 = muse.tasks[0]
    assert t1["mode"] == "text-to-image" and t1["route_kind"] == "video" and t1["raw_prompt"] is True
    assert t1["attachments"] == [str(ref)] and "thread_url" not in t1 and "pin_account" not in t1
    assert s1.status == "review" and s1.thread_url == THREAD and s1.account_id == "muse_acc_vid_02"
    cs.reject_sheet(PID, "person_1", "tóc sai ở góc sau")
    s2 = asyncio.run(cs.draw_sheet(PID, "person_1", muse, ref))
    t2 = muse.tasks[1]
    assert t2["thread_url"] == THREAD and t2["pin_account"] is True and t2["assigned_account"] == "muse_acc_vid_02"
    assert "Bản trước SAI: tóc sai ở góc sau" in t2["prompt"]
    assert [Path(v).name for v in s2.versions] == ["sheet_v1.jpg", "sheet_v2.jpg"]
    assert all(Path(v).is_file() for v in s2.versions)
    assert cs.approve_sheet(PID, "person_1").status == "approved"


def test_draw_sheet_failure_keeps_old_sheet_and_timeout_drops_thread(isolated_projects_dir):
    _make_project()
    ref = project_service.get_scene_media_paths(PID, "scene_028")["image"]
    asyncio.run(cs.draw_sheet(PID, "person_1", FakeMuse(), ref))
    s = asyncio.run(cs.draw_sheet(PID, "person_1", FakeMuse(fail_with=RuntimeError("MUSE_REPLIED_ERROR: quá tải (503)")), ref))
    assert s.status == "failed" and "503" in s.error and s.thread_url == THREAD     # lỗi Muse: vẫn dùng lại được chat
    assert s.sheet_path and Path(s.sheet_path).is_file()
    s = asyncio.run(cs.draw_sheet(PID, "person_1", FakeMuse(fail_with=TimeoutError("hết giờ")), ref))
    assert s.status == "failed" and s.thread_url is None and s.account_id is None   # quá giờ: chat bẩn, lần sau chat mới


def test_reject_needs_feedback_and_design_change_unapproves(isolated_projects_dir):
    _make_project()
    with pytest.raises(cs.CastError):
        cs.reject_sheet(PID, "person_1", "  ")
    with pytest.raises(cs.CastError):
        cs.approve_sheet(PID, "person_1")                                         # chưa có bảng
    img = isolated_projects_dir / "duyet.jpg"
    Image.new("RGB", (2048, 1152), "white").save(img)
    s = cs.import_approved_sheet(PID, "person_1", img, design_en="Tóc ôm cả phía sau đầu", thread_url=THREAD,
                                 account_id="muse_acc_vid_02")
    assert s.status == "approved" and s.design_en == "Tóc ôm cả phía sau đầu"
    assert cs.set_design(PID, "person_1", "Thiết kế mới").status == "draft"


def test_cast_board_requires_approved_sheets_and_is_16_9(isolated_projects_dir):
    _make_project()
    with pytest.raises(cs.CastError) as err:
        cs.cast_board(PID, ["person_1"])
    assert "Thẩm Nhã Uyên" in str(err.value)
    with pytest.raises(cs.CastError):
        cs.cast_board(PID, [])
    for eid, color in (("person_1", "red"), ("person_2", "blue")):
        img = isolated_projects_dir / f"{eid}.jpg"
        Image.new("RGB", (2048, 1152), color).save(img)
        cs.import_approved_sheet(PID, eid, img)
    board = cs.cast_board(PID, ["person_1", "person_2"])
    with Image.open(board) as b:
        assert b.size == (2048, 1152)
        left, right = b.getpixel((400, 576)), b.getpixel((1600, 576))
    assert left[0] > 200 and left[2] < 60 and right[2] > 200 and right[0] < 60
    assert cs.board_positions(2) == ["left", "right"]
    assert cs.board_positions(1) == ["whole image"]
    assert cs.board_positions(4) == ["top left", "top right", "bottom left", "bottom right"]
    assert cs.cast_board(PID, ["person_1", "person_2"]) == board                  # cùng bảng: dùng lại file


def test_reference_image_is_first_scene_with_the_person(isolated_projects_dir):
    project = _make_project()
    cast = cs.load_cast(PID)
    assert cs.reference_image(project, cast, "person_2").name == "scene_012.jpg"
    assert cs.reference_image(project, cast, "person_15") is None


# --------------------------------------------------------------------------------------------------------- API
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routers import character_sheets as cs_router  # noqa: E402


@pytest.fixture
def client(isolated_projects_dir):
    app = FastAPI()
    app.include_router(cs_router.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c
    cs_router._drawing.clear()


def _wait_not_drawing(client, eid, seconds=10):
    import time
    end = time.time() + seconds
    while time.time() < end:
        chars = {c["entity_id"]: c for c in client.get(f"/api/projects/{PID}/characters").json()["characters"]}
        if not chars[eid]["drawing"]:
            return chars[eid]
        time.sleep(0.1)
    raise AssertionError("vẽ không xong")


def test_api_ids_and_missing_project(client):
    _make_project()
    assert client.get("/api/projects/proj_khong_co/characters").status_code == 404
    assert client.get("/api/projects/_cases/characters").status_code == 400
    assert client.post(f"/api/projects/{PID}/characters/bad%20id/approve").status_code == 400
    assert client.post(f"/api/projects/{PID}/characters/person_99/approve").status_code == 400
    assert client.put(f"/api/projects/{PID}/scenes/scene_999/cast", json={"entity_ids": []}).status_code == 404
    assert client.put(f"/api/projects/{PID}/scenes/scene_028/cast", json={"entity_ids": ["x y"]}).status_code == 400


def test_api_flow_draw_review_reject_redraw_approve(client, monkeypatch):
    project = _make_project()
    p = project_service.get_project(PID)
    for s in p.scenes:
        if s.id == "scene_028":
            s.metadata["climax_video"] = {"status": "selected"}
    project_service.save_project(p)
    muse = FakeMuse()
    monkeypatch.setattr(cs_router, "muse_call_starting_runner", muse)
    base = f"/api/projects/{PID}/characters"
    data = client.get(base).json()
    assert data["needed"] == ["person_1"] and data["scene_cast"]["scene_012"] == ["person_2"]
    assert all("thread_url" not in c for c in data["characters"])   # không lộ địa chỉ chat ra giao diện

    assert client.post(f"{base}/person_1/reject", json={"feedback": ""}).status_code == 400
    assert client.post(f"{base}/person_1/draw").status_code == 200
    c = _wait_not_drawing(client, "person_1")
    assert c["status"] == "review" and c["sheet_url"] and c["versions"] == 1
    assert client.get(c["sheet_url"]).status_code == 200
    assert client.post(f"{base}/person_1/reject", json={"feedback": "tóc sai ở góc sau"}).json()["status"] == "draft"
    client.post(f"{base}/person_1/draw")
    c = _wait_not_drawing(client, "person_1")
    assert c["versions"] == 2 and muse.tasks[1]["thread_url"] == THREAD
    assert client.post(f"{base}/person_1/approve").json()["status"] == "approved"
    r = client.put(f"{base}/person_1", json={"design_en": "Thiết kế mới"})
    assert r.status_code == 200 and r.json()["status"] == "draft"
    # người chưa có cảnh nào có ảnh: không vẽ được, báo rõ
    r = client.post(f"{base}/person_15/draw")
    assert r.status_code == 400 and "Gia tộc họ Tiền" in r.json()["detail"]
    assert project is not None


def test_api_draw_conflict_while_drawing(client, monkeypatch):
    _make_project()
    gate = {"open": False}

    async def slow(task):
        while not gate["open"]:
            await asyncio.sleep(0.05)
        return await FakeMuse()(task)

    monkeypatch.setattr(cs_router, "muse_call_starting_runner", slow)
    base = f"/api/projects/{PID}/characters"
    assert client.post(f"{base}/person_2/draw").status_code == 200
    assert client.post(f"{base}/person_2/draw").status_code == 409
    assert client.put(f"{base}/person_2", json={"design_en": "x"}).status_code == 409
    gate["open"] = True
    assert _wait_not_drawing(client, "person_2")["status"] == "review"


def test_project_put_does_not_touch_cast_file(isolated_projects_dir):
    from main import app
    _make_project()
    cs.set_scene_cast(PID, "scene_028", ["person_2"])
    path = isolated_projects_dir / PID / "characters" / "characters.json"
    before = path.read_text(encoding="utf-8")
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)) as c:
        body = c.get(f"/api/projects/{PID}").json()
        body["name"] = "Đổi tên"
        assert c.put(f"/api/projects/{PID}", json=body).status_code == 200
    assert path.read_text(encoding="utf-8") == before
