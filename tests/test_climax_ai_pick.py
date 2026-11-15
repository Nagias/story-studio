"""AI (Gemini qua 9router) chọn cảnh cao trào (services/climax_ai_pick.py, routers/climax_video.py mode=ai).

LLM giả (không gọi mạng): đọc id trong mục "CẢNH CẦN CHẤM" của prompt rồi trả điểm theo bảng cho trước.
"""
import asyncio
import re
import time
from pathlib import Path

import pytest

from models.schemas import Project, Scene
from routers import climax_video as climax_router
from services import climax_ai_pick as ai
from services import project_service
from services.case_adaptation_llm import LLMError
from services.case_adaptation_steps import MAX_ATTEMPTS, StepFailed, StepRejected
from tests.test_climax_video import _api_project, _save_project, _scene, _statuses, client  # noqa: F401

STATIC = Path(__file__).resolve().parent.parent / "backend" / "static"


@pytest.fixture(autouse=True)
def _fresh_pick_state():
    climax_router._picking.clear()
    climax_router._pick_status.clear()
    yield
    climax_router._picking.clear()
    climax_router._pick_status.clear()


def _ids_to_score(user: str) -> list[str]:
    part = user.split("CẢNH CẦN CHẤM:", 1)[1].split("\n\n", 1)[0]
    return re.findall(r"^\[([^\]]+)\]", part, re.M)


def make_llm(scores: dict[str, float], bad_first: int = 0, delay: float = 0.0):
    """LLM giả: trả điểm theo `scores` (mặc định 1). `bad_first` lượt đầu trả id lạ và thiếu cảnh."""
    calls: list[str] = []

    async def fake(system: str, user: str, **kwargs):
        calls.append(user)
        if delay:
            await asyncio.sleep(delay)
        ids = _ids_to_score(user)
        if len(calls) <= bad_first:
            return {"scenes": [{"id": "scene_lạ", "score": 9, "reason": "bịa"}]}
        return {"scenes": [{"id": i, "score": scores.get(i, 1), "reason": f"lý do {i}"} for i in ids]}

    fake.calls = calls
    return fake


# ------------------------------------------------------------------------------------------- chia nhóm, prompt
def _plain_project(n: int, duration: float = 10.0) -> Project:
    scenes = [Scene(id=f"scene_{i:03d}", order=i, text=f"Lời kể cảnh {i}", duration=duration,
                    metadata={"visual_kind": "image"}) for i in range(1, n + 1)]
    return Project(id="proj_ai_pick", name="Vụ thử", scenes=scenes)


def test_groups_split_scenes_and_prompt_has_read_only_context():
    project = _plain_project(30)
    parts = ai.groups(project.scenes, 14)
    assert [len(g) for g in parts] == [14, 14, 2]
    prompt = ai.group_prompt(project, parts[1], 2, 3, {})
    assert prompt.startswith(f"TASK: {ai.TASK_MARKER} 2")
    assert _ids_to_score(prompt) == [f"scene_{i:03d}" for i in range(15, 29)]
    before = prompt.split("NGỮ CẢNH TRƯỚC", 1)[1].split("CẢNH CẦN CHẤM", 1)[0]
    after = prompt.split("NGỮ CẢNH SAU", 1)[1]
    assert "[scene_013]" in before and "[scene_014]" in before and "[scene_012]" not in before
    assert "[scene_029]" in after and "[scene_030]" in after
    first = ai.group_prompt(project, parts[0], 1, 3, {})
    assert "NGỮ CẢNH TRƯỚC" not in first and "Lời kể cảnh 1" in first


def test_validate_group_rejects_unknown_missing_duplicate_bad_score_and_empty_reason():
    ids = ["scene_001", "scene_002"]
    good = {"scenes": [{"id": "scene_001", "score": 7, "reason": "đuổi bắt"},
                       {"id": "scene_002", "score": 2.5, "reason": "giới thiệu"}]}
    assert ai.validate_group(good, ids) == {"scene_001": (7.0, "đuổi bắt"), "scene_002": (2.5, "giới thiệu")}
    bad_cases = [
        ({"scenes": [*good["scenes"], {"id": "scene_009", "score": 5, "reason": "x"}]}, "id lạ scene_009"),
        ({"scenes": good["scenes"][:1]}, "thiếu cảnh scene_002"),
        ({"scenes": [*good["scenes"], good["scenes"][0]]}, "hai lần"),
        ({"scenes": [good["scenes"][0], {"id": "scene_002", "score": 11, "reason": "x"}]}, "không phải số"),
        ({"scenes": [good["scenes"][0], {"id": "scene_002", "score": "8", "reason": "x"}]}, "không phải số"),
        ({"scenes": [good["scenes"][0], {"id": "scene_002", "score": True, "reason": "x"}]}, "không phải số"),
        ({"scenes": [good["scenes"][0], {"id": "scene_002", "score": 3, "reason": "  "}]}, "trống"),
        ({"items": []}, "scenes"),
    ]
    for raw, words in bad_cases:
        with pytest.raises(StepRejected) as e:
            ai.validate_group(raw, ids)
        assert words in e.value.reason, (raw, e.value.reason)


def test_choose_reaches_half_of_runtime_by_score_or_half_of_scenes_without_voice():
    project = _plain_project(6)
    project.scenes[0].duration = 40.0   # tổng 90 giây -> cần >= 45
    scores = {"scene_001": 2, "scene_002": 9, "scene_003": 8, "scene_004": 8, "scene_005": 1, "scene_006": 0}
    chosen = ai.choose(project, scores, {})
    # 002 (10) + 003 (10) + 004 (10) = 30 < 45 -> thêm 001 (40) = 70
    assert chosen == ["scene_001", "scene_002", "scene_003", "scene_004"]
    for s in project.scenes:
        s.duration = None
    assert ai.choose(project, scores, {}) == ["scene_002", "scene_003", "scene_004"]   # ceil(50% * 6)
    # bằng điểm: cảnh có nhân vật trước cảnh không người
    flat = {s.id: 5 for s in project.scenes}
    assert ai.choose(project, flat, {"scene_001": False, "scene_002": False}) == ["scene_003", "scene_004",
                                                                                 "scene_005"]


# ------------------------------------------------------------------------------------------------- ai_pick
def test_ai_pick_scores_every_group_and_covers_half(isolated_projects_dir, monkeypatch):
    project = _api_project()   # cảnh vẽ: 002 (12 s), 003 (12 s), 004 (4 s), 006 (12 s); tổng lời kể 64 s
    monkeypatch.setattr(ai, "GROUP_SIZE", 3)
    llm = make_llm({"scene_006": 9, "scene_003": 8, "scene_004": 7, "scene_002": 1})
    result = asyncio.run(ai.ai_pick(project.id, llm=llm))
    assert len(llm.calls) == 2                                   # 4 cảnh, nhóm 3 -> 2 lượt
    assert _ids_to_score(llm.calls[0]) == ["scene_002", "scene_003", "scene_004"]
    assert _ids_to_score(llm.calls[1]) == ["scene_006"]
    assert not any("scene_001" in _ids_to_score(c) for c in llm.calls)   # thẻ miễn trừ không được chấm
    # cần >= 32 giây: 006 (12) + 003 (12) + 004 (4) = 28 -> thêm 002 = 40
    assert result["chosen"] == ["scene_002", "scene_003", "scene_004", "scene_006"]
    assert result["scores"]["scene_006"] == 9 and result["reasons"]["scene_003"] == "lý do scene_003"
    assert result["coverage"]["enough"] is True


def test_ai_pick_retries_when_ids_are_wrong(isolated_projects_dir):
    project = _api_project()
    llm = make_llm({"scene_002": 9, "scene_003": 9, "scene_006": 9}, bad_first=1)
    result = asyncio.run(ai.ai_pick(project.id, llm=llm))
    assert len(llm.calls) == 2 and "scene_lạ" in llm.calls[1]   # lý do bị loại gửi lại cho LLM
    assert set(result["chosen"]) >= {"scene_002", "scene_003", "scene_006"}


def test_ai_pick_fails_loudly_after_all_attempts(isolated_projects_dir):
    project = _api_project()
    llm = make_llm({}, bad_first=99)
    with pytest.raises(StepFailed):
        asyncio.run(ai.ai_pick(project.id, llm=llm))
    assert len(llm.calls) == MAX_ATTEMPTS


# ------------------------------------------------------------------------------------------------------ API
def _wait_pick(client, base, seconds=30):  # noqa: F811
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        st = client.get(f"{base}/pick-status").json()
        if st["state"] != "running":
            return st
        time.sleep(0.05)
    raise AssertionError("lượt AI chọn cảnh không xong")


def _meta(pid, sid):
    return next(s for s in project_service.get_project(pid).scenes if s.id == sid).metadata.get("climax_video")


def test_api_ai_pick_saves_reasons_keeps_finished_work_and_drops_old_selection(client, monkeypatch):  # noqa: F811
    project = _api_project()
    pid = project.id
    base = f"/api/projects/{pid}/climax-video"
    for s in project.scenes:   # 004 đã có video (giữ nguyên), 002 đang được bật tay
        if s.id == "scene_004":
            s.metadata["climax_video"] = {"status": "ready", "clips": 1}
        if s.id == "scene_002":
            s.metadata["climax_video"] = {"status": "selected", "picked_by": "manual"}
    project_service.save_project(project)
    llm = make_llm({"scene_006": 9, "scene_003": 8, "scene_004": 7, "scene_002": 0})
    monkeypatch.setattr(ai, "call_llm_json", llm)
    assert client.get(f"{base}/pick-status").json() == {"state": "idle"}
    r = client.post(f"{base}/pick")                                  # mặc định mode=ai, chạy nền
    assert r.status_code == 200 and r.json() == {"picking": True, "mode": "ai"}
    st = _wait_pick(client, base)
    assert st["state"] == "done" and st["mode"] == "ai"
    # cần >= 32 giây: 006 (12) + 003 (12) + 004 (4) = 28 -> thêm 002 = 40; 004 đã "ready" nên không đổi
    assert st["scene_ids"] == ["scene_002", "scene_003", "scene_004", "scene_006"]
    assert _meta(pid, "scene_006") == {"status": "selected", "picked_by": "ai", "reason": "lý do scene_006",
                                       "ai_score": 9.0}
    assert _meta(pid, "scene_004") == {"status": "ready", "clips": 1}
    assert _meta(pid, "scene_002")["picked_by"] == "ai"
    status = {s["scene_id"]: s for s in client.get(f"{base}/status").json()["scenes"]}
    assert status["scene_003"]["reason"] == "lý do scene_003" and status["scene_003"]["picked_by"] == "ai"

    # chọn lại: AI không chọn 002 nữa (cảnh khác đủ 50%) thì dấu "selected" cũ của 002 bị bỏ
    for s in (p := project_service.get_project(pid)).scenes:
        if s.id == "scene_006":
            s.duration = 40.0
    project_service.save_project(p)
    client.post(f"{base}/pick")
    assert _wait_pick(client, base)["state"] == "done"
    assert _meta(pid, "scene_002") is None and _meta(pid, "scene_006")["picked_by"] == "ai"


@pytest.mark.parametrize("error", [LLMError("auth", "9router từ chối khoá"), "bad_ids"])
def test_api_ai_failure_reports_failed_and_writes_nothing(client, monkeypatch, error):  # noqa: F811
    project = _api_project()
    pid = project.id
    base = f"/api/projects/{pid}/climax-video"
    before = project_service.get_project(pid).model_dump()

    async def broken(system, user, **kwargs):
        if error == "bad_ids":
            return {"scenes": []}
        raise error

    monkeypatch.setattr(ai, "call_llm_json", broken)
    assert client.post(f"{base}/pick").status_code == 200
    st = _wait_pick(client, base)
    assert st["state"] == "failed" and "AI chấm cảnh cao trào" in st["error"]
    assert project_service.get_project(pid).model_dump() == before   # không âm thầm chọn theo nhãn
    assert all(v is None for v in _statuses(pid).values())


def test_api_score_mode_keeps_old_behaviour_and_manual_toggle_is_marked(client):  # noqa: F811
    project = _api_project()
    pid = project.id
    base = f"/api/projects/{pid}/climax-video"
    r = client.post(f"{base}/pick?mode=score")
    assert r.json()["scene_ids"] == ["scene_002", "scene_003", "scene_004", "scene_006"] and r.json()["mode"] == "score"
    assert _meta(pid, "scene_002") == {"status": "selected", "picked_by": "score"}
    assert client.get(f"{base}/pick-status").json()["mode"] == "score"
    client.put(f"{base}/scenes/scene_006", json={"enabled": False})
    client.put(f"{base}/scenes/scene_006", json={"enabled": True})
    assert _meta(pid, "scene_006") == {"status": "selected", "picked_by": "manual"}
    assert client.post(f"{base}/pick?mode=khac").status_code == 400


def test_api_refuses_edits_while_ai_is_picking(client, monkeypatch):  # noqa: F811
    project = _api_project()
    pid = project.id
    base = f"/api/projects/{pid}/climax-video"
    monkeypatch.setattr(ai, "call_llm_json", make_llm({}, delay=0.5))
    client.post(f"{base}/pick")
    assert client.post(f"{base}/pick").status_code == 409
    assert client.put(f"{base}/scenes/scene_006", json={"enabled": True}).status_code == 409
    assert client.post(f"{base}/run").status_code == 409
    assert client.get(f"{base}/status").json()["picking"] is True
    assert _wait_pick(client, base)["state"] == "done"


def test_api_ai_pick_needs_drawn_scenes(client):  # noqa: F811
    p = _save_project([_scene("scene_001", kind="board"), _scene("scene_002", kind="disclaimer")], pid="proj_crime_ai02")
    assert client.post(f"/api/projects/{p.id}/climax-video/pick").status_code == 400


# ------------------------------------------------------------------------------------------- giao diện (tĩnh)
def test_scene_page_has_ai_button_summary_strip_and_filter():
    js = (STATIC / "climax_video.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "workspace.css").read_text(encoding="utf-8")
    assert 'id="climax-summary"' in html and html.index('id="climax-summary"') < html.index('id="scene-list-container"')
    assert "AI chọn cảnh cao trào" in html and "tối đa một nửa" not in html
    for text in ("AI đang đọc kịch bản…", "/pick-status", "Chọn theo nhãn kịch bản (không dùng AI)",
                 "mục tiêu", "Tất cả", "Làm video", "'Ảnh'", "Bạn chọn", "AI: "):
        assert text in js, text
    for cls in (".ws-cx-filter-video", ".ws-cx-filter-image", ".ws-cx-on", ".ws-cx-switch"):
        assert cls in css, cls
