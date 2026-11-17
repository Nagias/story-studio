"""Dựng video: một cách tính thời lượng cảnh, chặn trước khi tốn quota, phụ đề khớp khi chuyển cảnh xfade (18/11/2026)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from models.schemas import Project, Scene  # noqa: E402
from services import project_service, video_service, video_share  # noqa: E402


def test_gate_is_checked_before_voices_exist(isolated_projects_dir):
    """Trước đây nút dựng bỏ qua chốt khi còn cảnh chưa có giọng, rồi thu giọng, tạo ảnh (tốn quota) mới chặn."""
    scenes = [Scene(id=f"scene_{i:03d}", order=i, text="Một câu kể dài vừa phải cho cảnh này.") for i in range(1, 4)]
    project = Project(id="proj_gate_est", name="x", scenes=scenes)
    project_service.ensure_project_dirs(project.id)
    project_service.save_project(project)
    report = video_share.estimated_share(project)
    assert report["estimated"] is True and report["total_seconds"] > 0 and not report["gate_ok"]


def test_both_render_paths_use_the_same_scene_seconds():
    src = (ROOT / "backend" / "routers" / "api.py").read_text(encoding="utf-8")
    assert "duration=scene.duration," not in src          # nút Dựng cắt đuôi video thoại, nút Sản xuất thì không
    assert src.count("render_seconds(scene) or scene.duration") >= 2


def test_xfade_overlap_matches_what_subtitles_subtract():
    durs = [6.0, 8.0, 5.0]
    overlap = video_service.xfade_overlap(durs, 0.45)
    assert overlap == 0.45
    assert video_service.xfade_overlap([0.6, 9.0], 0.45) == 0.2
