"""Vẽ tất cả / duyệt tất cả bảng nhân vật và ảnh chuẩn bối cảnh (services/look_batch.py, task A6 15/11/2026).

Offline: Muse giả vẽ ảnh bằng PIL (như test_character_sheets, test_location_sheets), LLM tìm bối cảnh giả.
"""
import asyncio
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_character_sheets import PID as CPID
from tests.test_character_sheets import FakeMuse as CharMuse
from tests.test_character_sheets import _make_project as make_case_project
from tests.test_location_sheets import GOOD, FakeLLM
from tests.test_location_sheets import PID as LPID
from tests.test_location_sheets import FakeMuse as LocMuse
from tests.test_location_sheets import _make_project as make_loc_project

from routers import character_sheets as cs_router  # noqa: E402
from routers import location_sheets as ls_router  # noqa: E402
from services import character_sheets as cs  # noqa: E402
from services import location_sheets as ls  # noqa: E402
from services import look_batch  # noqa: E402

from PIL import Image  # noqa: E402


@pytest.fixture
def client(isolated_projects_dir, monkeypatch):
    monkeypatch.setattr(look_batch, "PACE_SEC", 0)
    app = FastAPI()
    app.include_router(cs_router.router)
    app.include_router(ls_router.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c
    look_batch._jobs.clear()
    look_batch._starting.clear()
    cs_router._drawing.clear()
    ls_router._drawing.clear()


def _wait_done(client, base, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        st = client.get(f"{base}/draw-all/status").json()
        if not st["running"]:
            return st
        time.sleep(0.05)
    raise AssertionError("vẽ tất cả không xong")


class Gate:
    """Muse giả chờ mở cổng trước mỗi lượt (để kiểm 409 và Dừng khi đang vẽ)."""

    def __init__(self, muse):
        self.muse, self.open, self.calls = muse, False, 0

    async def __call__(self, task):
        self.calls += 1
        while not self.open:
            await asyncio.sleep(0.02)
        return await self.muse(task)


def _entity_of(task) -> str:
    return Path(task["output_path"]).parent.name   # characters/<entity_id>/sheet_v<n>.jpg


# ------------------------------------------------------------------------------------------------ nhân vật
def test_character_draw_all_in_order_skips_approved_and_continues_after_failure(client, monkeypatch, tmp_path):
    make_case_project()
    img = tmp_path / "duyet.jpg"
    Image.new("RGB", (2048, 1152), (10, 10, 10)).save(img, "JPEG")
    cs.import_approved_sheet(CPID, "person_2", img)   # đã duyệt: không được vẽ lại
    ok = CharMuse()
    calls = []

    async def muse(task):
        calls.append(task)
        if len(calls) == 1:
            raise RuntimeError("tài khoản bận")   # người đầu lỗi: phải ghi failed rồi đi tiếp
        return await ok(task)

    monkeypatch.setattr(cs_router, "muse_call_starting_runner", muse)
    base = f"/api/projects/{CPID}/characters"
    r = client.post(f"{base}/draw-all")
    assert r.status_code == 200 and r.json()["total"] == 2
    st = _wait_done(client, base)
    assert st["done"] == 2 and st["total"] == 2 and st["drawn"] == ["person_15"]
    assert [f["entity_id"] for f in st["failed"]] == ["person_1"] and "tài khoản bận" in st["failed"][0]["error"]
    assert [_entity_of(t) for t in calls] == ["person_1", "person_15"]   # đúng thứ tự, tuần tự
    chars = cs.load_cast(CPID).characters
    assert chars["person_1"].status == "failed" and chars["person_15"].status == "review"
    assert chars["person_2"].status == "approved" and chars["person_2"].versions == [chars["person_2"].sheet_path]

    # chạy lại: chỉ còn người lỗi; xong thì không còn ai cần vẽ (400, không báo xong giả)
    assert client.post(f"{base}/draw-all").json()["total"] == 1
    st = _wait_done(client, base)
    assert st["drawn"] == ["person_1"] and st["failed"] == []
    assert client.post(f"{base}/draw-all").status_code == 400


def test_character_draw_all_409_while_running_and_stop_after_current(client, monkeypatch):
    make_case_project()
    gate = Gate(CharMuse())
    monkeypatch.setattr(cs_router, "muse_call_starting_runner", gate)
    base = f"/api/projects/{CPID}/characters"
    assert client.post(f"{base}/draw-all").json()["total"] == 3
    end = time.time() + 5
    while gate.calls == 0 and time.time() < end:
        time.sleep(0.02)
    st = client.get(f"{base}/draw-all/status").json()
    assert st["running"] and st["current_id"] == "person_1" and st["done"] == 0
    assert client.post(f"{base}/draw-all").status_code == 409
    assert client.post(f"{base}/person_1/draw").status_code == 409      # nút vẽ riêng thấy đang vẽ
    assert client.post(f"{base}/analyze").status_code in (400, 409)     # vụ án không tìm; đang vẽ cũng không
    assert client.get(base).json()["characters"][0]["drawing"] is True
    assert client.post(f"{base}/draw-all/stop").json()["stop_requested"] is True
    gate.open = True
    st = _wait_done(client, base)
    assert st["stopped"] and st["done"] == 1 and st["drawn"] == ["person_1"] and gate.calls == 1
    chars = cs.load_cast(CPID).characters
    assert chars["person_1"].status == "review" and chars["person_2"].status == "draft"


def test_character_approve_all_only_approves_drawn_sheets(client, monkeypatch):
    make_case_project()
    monkeypatch.setattr(cs_router, "muse_call_starting_runner", CharMuse())
    base = f"/api/projects/{CPID}/characters"
    for eid in ("person_1", "person_2"):
        asyncio.run(cs.draw_sheet(CPID, eid, CharMuse(), None))
    cs.reject_sheet(CPID, "person_2", "tóc góc sau sai")   # có bảng nhưng bị ghi chỗ sai: không duyệt
    r = client.post(f"{base}/approve-all")
    assert r.status_code == 200 and r.json() == {"approved": 1, "entity_ids": ["person_1"], "failed": []}
    chars = cs.load_cast(CPID).characters
    assert chars["person_1"].status == "approved"
    assert chars["person_2"].status == "draft" and chars["person_15"].status == "draft"
    assert client.post(f"{base}/approve-all").json()["approved"] == 0
    assert client.post("/api/projects/proj_khong_co/characters/approve-all").status_code == 404


def test_approve_all_rechecks_status_at_approval_and_reports_partial(isolated_projects_dir, monkeypatch):
    """Danh sách chụp lúc đầu đã cũ (người dùng ghi chỗ sai, người bị bỏ giữa chừng): bảng không còn "review" thì không
    duyệt, người không còn thì ghi lỗi, các người khác vẫn được duyệt (không 400 sau khi đã duyệt vài người)."""
    make_case_project()
    for eid in ("person_1", "person_2"):
        asyncio.run(cs.draw_sheet(CPID, eid, CharMuse(), None))
    cs.reject_sheet(CPID, "person_2", "tóc góc sau sai")   # vẫn còn file bảng, nhưng về "draft"
    monkeypatch.setattr(cs, "review_ids", lambda cast: ["person_2", "person_99", "person_1"])
    approved, failed = cs.approve_all(CPID)
    assert approved == ["person_1"] and [f["entity_id"] for f in failed] == ["person_99"]
    chars = cs.load_cast(CPID).characters
    assert chars["person_1"].status == "approved" and chars["person_2"].status == "draft"


def test_location_approve_all_rechecks_status(isolated_projects_dir, monkeypatch):
    make_loc_project()
    asyncio.run(ls.analyze_locations(LPID, llm=FakeLLM(GOOD)))
    ids = list(ls.load_locations(LPID).locations)
    for i in ids:
        asyncio.run(ls.draw_plate(LPID, i, LocMuse()))
    ls.reject_plate(LPID, ids[0], "thiếu cửa sổ")
    monkeypatch.setattr(ls, "review_ids", lambda data: [ids[0], "loc_khong_co", ids[1]])
    approved, failed = ls.approve_all(LPID)
    assert approved == [ids[1]] and [f["entity_id"] for f in failed] == ["loc_khong_co"]
    assert ls.load_locations(LPID).locations[ids[0]].status == "draft"


# ------------------------------------------------------------------------------------------------ bối cảnh
def test_location_draw_all_then_approve_all(client, monkeypatch):
    make_loc_project()
    asyncio.run(ls.analyze_locations(LPID, llm=FakeLLM(GOOD)))
    ids = list(ls.load_locations(LPID).locations)
    assert len(ids) == 2
    ok = LocMuse()
    calls = []

    async def muse(task):
        calls.append(task)
        if len(calls) == 1:
            raise TimeoutError("Muse quá giờ")
        return await ok(task)

    monkeypatch.setattr(ls_router, "muse_call_starting_runner", muse)
    base = f"/api/projects/{LPID}/locations"
    assert client.post(f"{base}/approve-all").json()["approved"] == 0   # chưa có ảnh chuẩn nào
    assert client.post(f"{base}/draw-all").json()["total"] == 2
    st = _wait_done(client, base)
    assert st["done"] == 2 and [f["entity_id"] for f in st["failed"]] == [ids[0]] and st["drawn"] == [ids[1]]
    r = client.post(f"{base}/approve-all").json()
    assert r == {"approved": 1, "location_ids": [ids[1]], "failed": []}
    data = ls.load_locations(LPID).locations
    assert data[ids[0]].status == "failed" and data[ids[1]].status == "approved"


def test_location_draw_all_409_and_stop(client, monkeypatch):
    make_loc_project()
    asyncio.run(ls.analyze_locations(LPID, llm=FakeLLM(GOOD)))
    gate = Gate(LocMuse())
    monkeypatch.setattr(ls_router, "muse_call_starting_runner", gate)
    base = f"/api/projects/{LPID}/locations"
    assert client.post(f"{base}/draw-all").status_code == 200
    end = time.time() + 5
    while gate.calls == 0 and time.time() < end:
        time.sleep(0.02)
    assert client.post(f"{base}/draw-all").status_code == 409
    assert client.post(f"{base}/analyze").status_code == 409
    client.post(f"{base}/draw-all/stop")
    gate.open = True
    st = _wait_done(client, base)
    assert st["stopped"] and st["done"] == 1 and gate.calls == 1


def test_status_without_job_is_empty(client):
    make_case_project()
    st = client.get(f"/api/projects/{CPID}/characters/draw-all/status").json()
    assert st == look_batch.BatchJob().as_json() and st["running"] is False and st["failed"] == []
