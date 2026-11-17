"""Trạng thái duyệt tự huỷ đúng lúc (rà soát 18/11/2026).

Trước đây: lưới 9 khung đã duyệt không bao giờ bị huỷ (đổi nhân vật, đổi thiết kế, thu lại giọng vẫn gửi lưới cũ hoặc báo
"vẽ lại grid" mãi); đổi thiết kế chỉ huỷ bảng "approved", bảng "review" vẽ theo thiết kế cũ vẫn được duyệt hàng loạt;
"drawing" lưu lại sau khi server tắt thì kẹt mãi; góp ý "Bản trước SAI" cộng dồn mãi; lần tìm nhân vật truyện chữ ghi đè
lựa chọn chủ dự án đã chọn tay."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from services import character_sheets as cs  # noqa: E402
from services import climax_video as cv  # noqa: E402
from tests.test_climax_video import FakeMuse, _climax_project, _run_full  # noqa: E402


def test_changed_design_redraws_the_approved_grid_instead_of_reusing_it(isolated_projects_dir):
    project = _climax_project()
    pid, sid = project.id, "scene_003"
    muse = FakeMuse(pid, sid)
    assert _run_full(pid, sid, muse)["status"] == "ready"
    grids_before = sum(t["mode"] == "text-to-image" for t in muse.tasks)
    sheet = cs.load_cast(pid).characters["person_1"]
    cs.set_design(pid, "person_1", sheet.design_en + " Now wears a red raincoat.")
    assert cs.load_cast(pid).characters["person_1"].status == "draft"         # phải duyệt lại bảng trước
    cs.approve_sheet(pid, "person_1")
    cv.redo_scene(pid, sid)
    state = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    assert state["status"] == cv.GRID_REVIEW                                  # vẽ lại lưới, không gửi lưới cũ
    assert sum(t["mode"] == "text-to-image" for t in muse.tasks) == grids_before + 1


def test_unchanged_scene_keeps_its_approved_grid(isolated_projects_dir):
    project = _climax_project()
    pid, sid = project.id, "scene_003"
    muse = FakeMuse(pid, sid)
    _run_full(pid, sid, muse)
    grids_before = sum(t["mode"] == "text-to-image" for t in muse.tasks)
    cv.redo_scene(pid, sid)
    assert asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))["status"] == "ready"
    assert sum(t["mode"] == "text-to-image" for t in muse.tasks) == grids_before


def test_design_change_cancels_a_sheet_waiting_for_review_and_old_feedback(isolated_projects_dir):
    project = _climax_project()
    pid = project.id

    def to_review(s):
        s.status = "review"
        s.feedback = ["tóc sai ở góc sau"]
    cs._update(pid, "person_1", to_review)
    s = cs.set_design(pid, "person_1", "Appearance: a different person in a grey coat.")
    assert s.status == "draft" and s.feedback == []
    assert "person_1" not in cs.approve_all(pid)[0]                            # không duyệt bảng vẽ theo thiết kế cũ


def test_leftover_drawing_status_after_restart_is_redrawable(isolated_projects_dir):
    project = _climax_project()
    pid = project.id
    cs._update(pid, "person_1", lambda s: setattr(s, "status", "drawing"))   # server tắt giữa lúc vẽ
    assert not cs.drawing_now(pid, "person_1")
    assert "person_1" in [s.entity_id for s in cs.batch_targets(cs.load_cast(pid), pid)]
    cs.set_design(pid, "person_1", "Appearance: someone else.")               # sửa được, không báo "đang vẽ"


def test_manual_scene_cast_survives_new_analysis(isolated_projects_dir):
    project = _climax_project()
    pid = project.id
    cs.set_scene_cast(pid, "scene_002", [])
    assert "scene_002" in cs.load_cast(pid).manual_scene_ids
