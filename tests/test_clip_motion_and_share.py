"""Đo clip có cử động thật (services/clip_motion.py), báo tỉ lệ video Muse khi dựng (services/video_share.py), nút chọn
cảnh báo khi không đủ 50% (climax_video.coverage) và bản giao việc cao trào không còn cho phép "cử động ít".

Gặp 09–11/11/2026: vụ xưởng sắt báo 65,5% video Muse nhưng clip chỉ lia/zoom; sau khi làm lại vẫn 34/38 clip gần như
đứng hình vì bản giao việc dặn "cử động ít vẫn đạt", "bị loại thì giảm cử động"; vụ Khang Cúc Hoa 32,9% không ai báo;
bản Anh Khang Cúc Hoa nút chọn cảnh chỉ đạt 49,2% mà không báo."""
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.schemas import Project, Scene  # noqa: E402
from services import clip_motion, video_share  # noqa: E402
from services import climax_video as cv  # noqa: E402
from services.climax_brief import scene_brief  # noqa: E402
from tests.test_climax_video import FakeMuse, _climax_project, _run_full  # noqa: E402

W, H, FPS, SECONDS = 1280, 720, 24, 6


def _background(seed: int = 3) -> np.ndarray:
    """Nền có nét như tranh vẽ (để đo bù được máy quay)."""
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), 90, np.uint8)
    for _ in range(140):
        x, y = int(rng.integers(0, W)), int(rng.integers(0, H))
        cv2.rectangle(img, (x, y), (x + int(rng.integers(20, 120)), y + int(rng.integers(20, 120))),
                      tuple(int(c) for c in rng.integers(30, 220, 3)), int(rng.integers(2, 5)))
    return img


def _write(path: Path, frames) -> Path:
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for f in frames:
        out.write(f)
    out.release()
    return path


def _zoom_of_still(path: Path) -> Path:
    """Ảnh tĩnh, máy quay phóng to dần và lia ngang: kiểu clip vụ xưởng sắt."""
    bg, n = _background(), FPS * SECONDS
    frames = []
    for i in range(n):
        z = 1.0 + 0.25 * i / n
        m = cv2.getRotationMatrix2D((W / 2 + 60 * i / n, H / 2), 0, z)
        frames.append(cv2.warpAffine(bg, m, (W, H), borderMode=cv2.BORDER_REFLECT))
    return _write(path, frames)


def _person_walks(path: Path) -> Path:
    """Máy quay đứng yên, một người (đầu tròn trắng + thân) đi ngang khung và giơ tay."""
    bg, n = _background(), FPS * SECONDS
    frames = []
    for i in range(n):
        f = bg.copy()
        x = 200 + int(800 * i / n)
        cv2.circle(f, (x, 300), 70, (245, 245, 245), -1)
        cv2.rectangle(f, (x - 60, 370), (x + 60, 620), (40, 40, 40), -1)
        arm_y = 380 - int(150 * abs(np.sin(i / 8)))
        cv2.line(f, (x + 60, 400), (x + 150, arm_y), (40, 40, 40), 22)
        frames.append(f)
    return _write(path, frames)


def test_camera_only_clip_scores_low_and_moving_person_scores_high(tmp_path):
    still = clip_motion.measure(_zoom_of_still(tmp_path / "zoom.mp4"))
    moving = clip_motion.measure(_person_walks(tmp_path / "walk.mp4"))
    assert not clip_motion.has_real_motion(still), still
    assert clip_motion.has_real_motion(moving), moving


def test_score_is_cached_beside_the_clip_and_redone_when_clip_changes(tmp_path, monkeypatch):
    clip = _person_walks(tmp_path / "walk.mp4")
    first = clip_motion.motion_score(clip)
    assert (tmp_path / "walk.mp4.motion.json").is_file()

    def boom(_p):
        raise AssertionError("không được đo lại khi clip không đổi")
    monkeypatch.setattr(clip_motion, "measure", boom)
    assert clip_motion.motion_score(clip) == pytest.approx(first, abs=1e-3)

    _zoom_of_still(clip)   # ghi đè clip: cỡ hoặc giờ sửa khác thì phải đo lại
    monkeypatch.setattr(clip_motion, "measure", lambda p: 0.0)
    assert clip_motion.motion_score(clip) == 0.0


def test_unreadable_clip_is_an_error_not_a_zero(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(clip_motion.ClipMotionError):
        clip_motion.measure(bad)


def test_share_report_counts_video_seconds_and_lists_still_clips(tmp_path, monkeypatch):
    """Clip gần như đứng hình (a.mp4) không được tính: chỉ clip có cử động (b.mp4) vào tỉ lệ."""
    scores = {"a.mp4": 0.0, "b.mp4": 6.0}
    monkeypatch.setattr(clip_motion, "motion_score", lambda p: scores[Path(p).name])

    def sc(order):
        return Scene(id=f"scene_{order:03d}", order=order, text="x")
    entries = [(sc(1), 10.0, str(tmp_path / "1.jpg")), (sc(2), 20.0, str(tmp_path / "a.mp4")),
               (sc(3), 10.0, str(tmp_path / "b.mp4")), (sc(4), 40.0, str(tmp_path / "4.jpg"))]
    rep = video_share.share_report(entries)
    assert rep["video_seconds"] == 10.0 and rep["clip_seconds"] == 30.0 and rep["total_seconds"] == 80.0
    assert rep["percent"] == 12.5 and rep["enough"] is False and rep["gate_ok"] is False and rep["still_scenes"] == [2]
    text = "\n".join(video_share.report_lines(rep))
    assert "12,5%" in text and "DƯỚI 50%" in text and "thiếu khoảng 30,0 giây" in text and "cảnh 2" in text

    rep2 = video_share.share_report([(sc(1), 10.0, str(tmp_path / "b.mp4")), (sc(2), 10.0, str(tmp_path / "1.jpg"))])
    assert rep2["enough"] is True and rep2["still_scenes"] == []
    assert not any("DƯỚI" in line or "đứng hình" in line for line in video_share.report_lines(rep2))


def _project(durations: dict) -> Project:
    scenes = [Scene(id=sid, order=i + 1, text="x", duration=d) for i, (sid, d) in enumerate(durations.items())]
    return Project(id="proj_share01", name="Thử", scenes=scenes)


def test_coverage_says_when_picked_scenes_cannot_reach_half():
    p = _project({"s1": 30.0, "s2": 19.0, "s3": 51.0})
    low = cv.coverage(p, ["s1", "s2"])
    assert low["percent"] == 49.0 and low["enough"] is False and low["target_percent"] == 50
    assert cv.coverage(p, ["s3"])["enough"] is True
    assert cv.coverage(_project({"s1": 0.0}), ["s1"])["enough"] is None   # chưa có giọng: chưa biết


def test_climax_brief_demands_body_motion_and_never_asks_to_reduce_it(isolated_projects_dir):
    project = _climax_project(duration=12.0)
    scene = next(s for s in project.scenes if s.id == "scene_003")
    brief = scene_brief(project, scene, [], 1, 12.0, "XONG-1")
    assert "cử động ít" not in brief and "giảm cử động" not in brief and "lia rất chậm" not in brief
    assert "không phải ảnh chuyển động" in brief and "không lia, không zoom" in brief
    assert "không được sửa bằng cách bớt cử động" in brief


@pytest.mark.parametrize("score, warned", [(0.0, True), (6.0, False)])
def test_ready_clip_gets_a_still_warning_on_its_card(isolated_projects_dir, monkeypatch, score, warned):
    monkeypatch.setattr(clip_motion, "motion_score", lambda p: score)
    project = _climax_project(duration=6.0)
    state = _run_full(project.id, "scene_003", FakeMuse(project.id, "scene_003"))
    assert state["status"] == "ready" and state["motion_score"] == score
    assert any("gần như đứng hình" in w for w in state.get("warnings", [])) is warned


def test_unmeasurable_clip_does_not_block_the_clip(isolated_projects_dir, monkeypatch):
    def fail(_p):
        raise clip_motion.ClipMotionError("hỏng")
    monkeypatch.setattr(clip_motion, "motion_score", fail)
    project = _climax_project(duration=6.0)
    state = _run_full(project.id, "scene_003", FakeMuse(project.id, "scene_003"))
    assert state["status"] == "ready" and "motion_score" not in state
