"""Video cho cảnh cao trào (dự án vụ án) làm từ ảnh 9-grid: services/climax_video.py và routers/climax_video.py.

Chạy offline: không gọi Muse. "Muse giả" vẽ ảnh grid bằng PIL và làm clip bằng ffmpeg từ ảnh ô (clip tối dần như Muse
thật đo ngày 27/10/2026). Dự án nằm trong thư mục tạm (conftest đổi PROJECTS_DIR).
"""
import asyncio
import copy
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageOps

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.case_adaptation_schemas import CaseAdaptationPlan, CaseBible, CaseEntity  # noqa: E402
from models.schemas import Project, Scene  # noqa: E402
from routers import climax_video as climax_router  # noqa: E402
from routers import muse_bridge  # noqa: E402
from services import climax_video as cv  # noqa: E402
from services import case_store, project_service  # noqa: E402
from services import character_sheets as cs  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                                reason="cần ffmpeg/ffprobe trong PATH")


THREAD = "https://muse.ai/thread/2d353dc3-3d3d-44b3-a3e7-51f54a295757"
WOMAN = "A slender East Asian woman in her early 20s with shoulder-length wavy dark hair and a pastel blouse"


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    monkeypatch.setattr(cv, "MUSE_PACE_SEC", 0)


# ------------------------------------------------------------------------------------------------ dựng dữ liệu giả
def _picture(path: Path, size=(1920, 1080), seed: int = 0) -> Path:
    """Ảnh có hình khối rõ ràng (SSIM so được), khác nhau theo seed."""
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", size, tuple(int(v) for v in rng.integers(40, 120, 3)))
    draw = ImageDraw.Draw(img)
    w, h = size
    for _ in range(12):
        x0, y0 = int(rng.integers(0, w - w // 5)), int(rng.integers(0, h - h // 5))
        draw.ellipse([x0, y0, x0 + w // 5, y0 + h // 5], fill=tuple(int(v) for v in rng.integers(0, 255, 3)))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=92)
    return path


def _ff(args: list) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, capture_output=True, timeout=120)


def _clip_from_image(img: Path, out: Path, seconds: float = 5.0, darken: bool = True, size="320x180") -> Path:
    """Clip như Muse: zoom rất chậm; darken thì tối dần (5 giây còn khoảng một nửa độ sáng)."""
    vf = f"scale={size.replace('x', ':')},setsar=1"
    if darken:
        vf += f",fade=t=out:st=0:d={seconds * 2}"
    _ff(["-loop", "1", "-i", str(img), "-vf", vf, "-t", str(seconds), "-r", "24", "-pix_fmt", "yuv420p", str(out)])
    return out


def _cut_clip(img_a: Path, img_b: Path, out: Path) -> Path:
    """Clip nửa đầu là ô gốc, nửa sau là ảnh khác hẳn: một lần cắt cảnh."""
    _ff(["-loop", "1", "-t", "2.5", "-i", str(img_a), "-loop", "1", "-t", "2.5", "-i", str(img_b),
         "-filter_complex", "[0:v]scale=320:180,setsar=1,fps=24[a];[1:v]scale=320:180,setsar=1,fps=24[b];"
                            "[a][b]concat=n=2:v=1:a=0[o]", "-map", "[o]", "-pix_fmt", "yuv420p", str(out)])
    return out


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _scene(sid: str, kind: str | None = "image", beat="setting", energy="ambient_low", sfx=(), duration=12.0) -> Scene:
    meta = {"visual_kind": kind, "narrative_beat": beat} if kind else {}
    return Scene(id=sid, order=int(sid.split("_")[-1]), text=f"Lời kể {sid}", image_prompt=f"a dark alley, {sid}",
                 bgm_energy=energy, sfx_cue=list(sfx), duration=duration, metadata=meta)


def _save_project(scenes: list[Scene], pid="proj_crime_test01", cast: str = "approved") -> Project:
    """Dự án vụ án thử: một nhân vật (person_1) có mặt ở mọi cảnh có hình. cast: "approved" (bảng đã duyệt),
    "draft" (chưa có bảng), "none" (cảnh chưa chọn nhân vật)."""
    case_id = f"case_{pid[-6:]}"
    case_store.save_plan(CaseAdaptationPlan(
        case_id=case_id, created_at="2026-10-28", model="fake", target_minutes=8, visual_style="horror_cartoon_2d",
        bible=CaseBible(source_language="vi", culture="vn", title_vi="t", title_en="t", timeline=[], entities=[
            CaseEntity(id="person_1", kind="person", real_names=["X"], alias_vi="Thẩm Nhã Uyên", alias_en="Ya",
                       appearance_en=WOMAN)]),
        parts=[], scenes=[]))
    project = Project(id=pid, name="Vụ thử", character_anchor="round white face with dot eyes, grey coat",
                      style_preset="horror_cartoon_2d", scenes=scenes, metadata={"case_id": case_id})
    project_service.ensure_project_dirs(pid)
    for s in scenes:
        if s.metadata.get("visual_kind") in cv.ELIGIBLE_KINDS:
            img = project_service.get_scene_media_paths(pid, s.id)["image"]
            _picture(img, seed=s.order)
            s.image_path = str(img)
            s.image_url = f"/api/projects/{pid}/media/images/{img.name}"
    project_service.save_project(project)
    if cast == "approved":
        sheet = _picture(project_service.get_scene_media_paths(pid, "bang")["image"].parent / "bang_nv.jpg",
                         size=(2048, 1152), seed=99)
        cs.import_approved_sheet(pid, "person_1", sheet, design_en="Round white head, two dot eyes, wavy hair.")
    for s in scenes:
        if s.metadata.get("visual_kind") in cv.ELIGIBLE_KINDS:
            cs.set_scene_cast(pid, s.id, [] if cast == "none" else ["person_1"])
    return project


def _scene_now(pid: str, sid: str) -> Scene:
    return next(s for s in project_service.get_project(pid).scenes if s.id == sid)


class FakeMuse:
    """Muse giả. `clip_plan(n)` (n = số lần gọi clip, đếm từ 1) trả "good" | "dark_cut" | "error" | "other"."""

    def __init__(self, pid: str, sid: str, clip_plan=lambda n: "good", grid_error=False, darken=True,
                 account="muse_acc_vid_02"):
        self.pid, self.sid, self.account = pid, sid, account
        self.clip_plan, self.grid_error, self.darken = clip_plan, grid_error, darken
        self.tasks: list[dict] = []
        self.status_during: list[str] = []
        self.clip_calls = 0

    async def __call__(self, task: dict) -> dict:
        self.tasks.append(copy.deepcopy(task))
        self.status_during.append(_scene_now(self.pid, self.sid).metadata.get("climax_video", {}).get("status"))
        out = Path(task["output_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        if task["mode"] == "text-to-image":
            if self.grid_error:
                raise RuntimeError("Không có tài khoản Muse ảnh nào đang online")
            ref_path = (task.get("attachments") or [task.get("reference_image_path")])[0]
            ref = Image.open(ref_path).convert("RGB").resize((660, 368))
            grid = Image.new("RGB", (2048, 1152), "white")
            for i in range(9):
                r, c = divmod(i, 3)
                grid.paste(ref, (c * 682 + 11, r * 384 + 8))
            grid.save(out, "JPEG", quality=92)
            return {"output_path": str(out), "status": "completed", "thread_url": THREAD, "executed_by": self.account}
        self.clip_calls += 1
        kind = self.clip_plan(self.clip_calls)
        if task["mode"] == "agent-video":
            return self._agent(task, out, kind)
        if kind == "error":
            raise TimeoutError("Meta Muse task timed out after 900s")
        if kind == "busy":
            raise RuntimeError("Muse task failed: MUSE_REPLIED_ERROR: Lệnh tạo video báo lỗi hệ thống quá tải (503)")
        if kind == "no_media":
            raise RuntimeError("Muse task failed: NO_MEDIA: Không nhận được video hợp lệ sau 300s cho task x")
        panel = Path(task["input_image_url"])
        if kind == "dark_cut":   # nửa sau là âm bản của ô: chỉnh màu từng khung xong vẫn là một cú cắt rõ
            negative = out.with_suffix(".am_ban.jpg")
            ImageOps.invert(Image.open(panel).convert("RGB")).save(negative)
            _cut_clip(panel, negative, out)
        elif kind == "other":
            _clip_from_image(_picture(out.with_suffix(".khac.jpg"), seed=777), out, darken=False)
        else:
            _clip_from_image(panel, out, darken=self.darken)
        return {"output_path": str(out), "status": "completed",
                "thread_url": task.get("thread_url") or THREAD, "executed_by": task.get("assigned_account") or self.account}

    def _agent(self, task: dict, out: Path, kind: str) -> dict:
        """Việc giao nhiều bước: video cuối (từ ảnh cảnh) + ảnh phụ: ảnh cảnh đã "sửa tóc" (giống ảnh cũ) và ảnh góc
        sau khác hẳn. kind: "good" | "short" (video 2 giây) | "error" | "busy" | "no_media" | "back_only"."""
        if kind == "error":
            raise TimeoutError("Meta Muse task timed out after 2820s")
        if kind == "busy":
            raise RuntimeError("Muse task failed: MUSE_REPLIED_ERROR: Lệnh tạo video báo lỗi hệ thống quá tải (503)")
        if kind == "no_media":
            raise RuntimeError("Muse task failed: NO_FINAL: Muse ghi dòng kết thúc nhưng không có video nào sau prompt")
        scene_img = Path(task["attachments"][0])
        seconds = 2.0 if kind == "short" else float(task["agent"]["target_seconds"])
        _clip_from_image(scene_img, out, seconds=seconds, darken=False)
        fixed = out.with_name(out.stem + "_extra_1.jpg")
        Image.open(scene_img).convert("RGB").point(lambda v: min(255, v + 12)).save(fixed, "JPEG", quality=92)
        back = _picture(out.with_name(out.stem + "_extra_2.jpg"), seed=4242)
        extras = [str(back)] if kind == "back_only" else [str(fixed), str(back)]
        return {"output_path": str(out), "status": "completed", "mode": task["mode"],
                "thread_url": task.get("thread_url") or THREAD,
                "executed_by": task.get("assigned_account") or self.account,
                "muse_reply": "Danh sách clip: 1) chạy tới cửa 2) hành lang. ANH_CANH_MOI: có. ĐẠT.",
                "media_count": {"video": 3, "image": 2}, "warnings": [], "extra_images": extras}


# ---------------------------------------------------------------------------------------------------- chấm điểm, chọn
def test_constants_match_contract():
    assert (cv.CLIMAX_RATIO, cv.CLIP_SECONDS, cv.PANELS_PER_GRID) == (0.5, 5, 9)
    assert (cv.SCENE_IMAGE_MIN_SIMILARITY, cv.BACKUP_SUFFIX) == (0.45, ".truoc_sua_toc.jpg")
    lock = cv.STYLE_LOCK_EN.lower()
    for word in ("style", "line", "palette", "face", "dot eyes", "clothing", "setting", "lighting", "no text",
                 "no blood", "no scene cuts"):
        assert word in lock, word


def test_scene_score_counts_each_signal():
    assert cv.scene_score(_scene("scene_001", kind=None)) == 0
    assert cv.scene_score(_scene("scene_001", kind="board", beat="climax", energy="dramatic_climax")) == 0
    assert cv.scene_score(_scene("scene_001", kind="disclaimer", beat="hook")) == 0
    assert cv.scene_score(_scene("scene_001")) == 0
    assert cv.scene_score(_scene("scene_001", kind="video")) == 3
    assert cv.scene_score(_scene("scene_001", beat="climax")) == 2
    assert cv.scene_score(_scene("scene_001", beat="hook")) == 1
    assert cv.scene_score(_scene("scene_001", energy="dramatic_climax")) == 2
    assert cv.scene_score(_scene("scene_001", energy="tension_buildup")) == 1
    assert cv.scene_score(_scene("scene_001", sfx=["heartbeat"])) == 1
    assert cv.scene_score(_scene("scene_001", sfx=["impact_hit", "heartbeat"])) == 1
    assert cv.scene_score(_scene("scene_001", sfx=["door_creak"])) == 0
    assert cv.scene_score(_scene("scene_001", kind="video", beat="climax", energy="dramatic_climax",
                                 sfx=["heartbeat"])) == 8


def test_pick_limits_to_half_prefers_score_then_order():
    scenes = [
        _scene("scene_001", kind="disclaimer", beat="hook"),            # không hợp lệ
        _scene("scene_002", beat="hook"),                               # 1
        _scene("scene_003", energy="tension_buildup"),                  # 1
        _scene("scene_004", kind="board", beat="climax"),               # không hợp lệ
        _scene("scene_005", beat="climax", energy="dramatic_climax"),   # 4
        _scene("scene_006"),                                            # 0
        _scene("scene_007", sfx=["heartbeat"]),                         # 1
        _scene("scene_008", kind="video"),                              # 3
        _scene("scene_009"),                                            # 0
    ]
    project = Project(id="proj_x", name="x", scenes=scenes)
    # 7 cảnh hợp lệ -> tối đa floor(3,5) = 3: điểm 4, 3, rồi trong ba cảnh 1 điểm lấy cảnh đứng trước (scene_002)
    assert cv.pick_climax_scenes(project) == ["scene_002", "scene_005", "scene_008"]
    # ít cảnh có điểm hơn giới hạn: chỉ lấy cảnh có điểm > 0
    few = Project(id="proj_y", name="y", scenes=[_scene("scene_001", beat="climax"), *[_scene(f"scene_00{i}")
                                                                                       for i in range(2, 7)]])
    assert cv.pick_climax_scenes(few) == ["scene_001"]
    assert cv.pick_climax_scenes(Project(id="proj_z", name="z", scenes=[_scene("scene_001", beat="climax")])) == []


def test_clip_count_and_grid_plan():
    assert cv.clip_count(0.4) == 1
    assert cv.clip_count(5) == 1
    assert cv.clip_count(5.01) == 2
    assert cv.clip_count(44.9) == 9
    assert cv.clip_count(46) == 10
    for bad in (0, -3):
        with pytest.raises(ValueError):
            cv.clip_count(bad)
    assert cv.grid_plan(1) == [[1]]
    assert cv.grid_plan(2) == [[1, 9]]
    assert cv.grid_plan(3) == [[1, 5, 9]]
    assert cv.grid_plan(4) == [[1 + round(i * 8 / 3) for i in range(4)]] == [[1, 4, 6, 9]]
    assert cv.grid_plan(9) == [list(range(1, 10))]
    assert cv.grid_plan(11) == [[1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 9]]
    assert cv.grid_plan(19) == [list(range(1, 10)), list(range(1, 10)), [1]]
    with pytest.raises(ValueError):
        cv.grid_plan(0)


def test_prompts_are_english_templates_with_style_lock():
    scene = _scene("scene_005", beat="climax")
    project = Project(id="proj_x", name="x", character_anchor="round white face with dot eyes")
    first = cv.grid_prompt(scene, project, first_grid=True)
    later = cv.grid_prompt(scene, project, first_grid=False)
    for p in (first, later):
        assert "3x3" in p and "nine consecutive frames" in p and "white borders" in p
        assert "No text, no numbers" in p and scene.image_prompt in p and cv.STYLE_LOCK_EN in p
    assert "Panel 1 (top left) is exactly the attached image" in first and "previous segment" not in first
    assert "last frame of the previous segment" in later and "exactly the attached image;" not in later


# ------------------------------------------------------------------------------------------------------ ảnh, video
def test_slice_grid_cuts_nine_panels_without_borders(tmp_path):
    colors = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30), (200, 30, 200),
              (30, 200, 200), (120, 60, 20), (20, 60, 120), (90, 90, 90)]
    grid = Image.new("RGB", (2048, 1152), "white")
    draw = ImageDraw.Draw(grid)
    for i, col in enumerate(colors):
        r, c = divmod(i, 3)
        draw.rectangle([c * 682 + 12, r * 384 + 10, (c + 1) * 682 - 12, (r + 1) * 384 - 10], fill=col)
    grid_path = tmp_path / "g.jpg"
    grid.save(grid_path, "JPEG", quality=95)

    panels = cv.slice_grid(grid_path, tmp_path / "out", "scene_005", 2)
    assert [p.name for p in panels] == [f"scene_005_grid2_o{i}.jpg" for i in range(1, 10)]
    for p, col in zip(panels, colors):
        arr = np.asarray(Image.open(p).convert("RGB"), dtype=np.float64)
        assert arr.shape == (1080, 1920, 3)
        # viền trắng đã bị cắt: cả mép ảnh cũng mang màu của ô
        for edge in (arr[:4].reshape(-1, 3), arr[-4:].reshape(-1, 3), arr[:, :4].reshape(-1, 3)):
            assert np.abs(edge.mean(axis=0) - col).max() < 25


def test_slice_grid_rejects_bad_images(tmp_path):
    small = tmp_path / "small.jpg"
    Image.new("RGB", (299, 200), "gray").save(small)
    with pytest.raises(ValueError):
        cv.slice_grid(small, tmp_path, "scene_001", 1)
    short = tmp_path / "short.jpg"
    Image.new("RGB", (400, 167), "gray").save(short)
    with pytest.raises(ValueError):
        cv.slice_grid(short, tmp_path, "scene_001", 1)
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    with pytest.raises(ValueError):
        cv.slice_grid(broken, tmp_path, "scene_001", 1)


# ----------------------------------------------------------------------------------------------- chạy trọn một cảnh
def _climax_project(duration=12.0, cast="approved"):
    scenes = [_scene("scene_001", kind="disclaimer"), _scene("scene_002"),
              _scene("scene_003", beat="climax", energy="dramatic_climax", duration=duration)]
    return _save_project(scenes, cast=cast)


def _run_full(pid, sid, muse):
    """Pha grid -> duyệt grid -> pha clip (như chủ dự án bấm trên giao diện)."""
    grid_state = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    assert grid_state["status"] == cv.GRID_REVIEW, grid_state
    cv.approve_grid(pid, sid)
    return asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))


def test_grid_phase_runs_on_video_account_with_scene_image_and_cast_board(isolated_projects_dir):
    project = _climax_project(duration=12.0)
    pid, sid = project.id, "scene_003"
    muse = FakeMuse(pid, sid)
    state = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    assert state["status"] == "grid_review" and len(state["grid_paths"]) == 1
    assert state["thread_url"] == THREAD and state["account_id"] == "muse_acc_vid_02"
    assert [t["mode"] for t in muse.tasks] == ["text-to-image"]                 # dừng chờ duyệt, chưa làm clip
    t = muse.tasks[0]
    scene_image = project_service.get_scene_media_paths(pid, sid)["image"]
    assert t["route_kind"] == "video" and t["raw_prompt"] is True and "thread_url" not in t
    assert Path(t["attachments"][0]).resolve() == scene_image.resolve()
    assert Path(t["attachments"][1]).name.startswith("board_")
    assert t["prompt"].startswith("tạo cho tôi 1 hình ảnh 2K") and "Round white head, two dot eyes" in t["prompt"]
    assert "Panel 1 (top left) is exactly the FIRST attached image" in t["prompt"]
    assert "Thẩm Nhã Uyên — character sheet = the SECOND attached image" in t["prompt"]
    with pytest.raises(cv.ClimaxVideoError):
        asyncio.run(cv.run_scene_clips(pid, sid, muse))                         # chưa duyệt grid: không làm clip


def test_long_narration_draws_second_grid_and_sends_both_to_muse(isolated_projects_dir):
    project = _climax_project(duration=50.0)          # 50 giây -> 10 ô -> grid 1 (9 ô) + grid 2
    pid, sid = project.id, "scene_003"
    muse = FakeMuse(pid, sid)
    result = _run_full(pid, sid, muse)

    assert (result["status"], result["grids"]) == ("ready", 2)
    grids = [t for t in muse.tasks if t["mode"] == "text-to-image"]
    assert len(grids) == 2
    assert Path(grids[1]["attachments"][0]).name == f"{sid}_grid1_o9.jpg"
    assert "last frame of the previous segment" in grids[1]["prompt"]
    assert grids[1]["thread_url"] == THREAD                                      # grid 2 cùng chat với grid 1
    agent = [t for t in muse.tasks if t["mode"] == "agent-video"]
    assert len(agent) == 1 and [Path(x).name for x in agent[0]["attachments"][2:]] ==         [f"{sid}_grid1_v1.jpg", f"{sid}_grid2_v1.jpg"]
    assert agent[0]["agent"]["target_seconds"] == 24 and "Ảnh 4" in agent[0]["prompt"]


def test_run_scene_fails_cleanly_when_grid_or_voice_missing(isolated_projects_dir):
    project = _climax_project()
    pid, sid = project.id, "scene_003"
    muse = FakeMuse(pid, sid, grid_error=True)
    result = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    assert result["status"] == "failed" and "9-grid" in result["error"] and "online" in result["error"]
    assert muse.clip_calls == 0

    no_voice = _scene_now(pid, sid)
    p = project_service.get_project(pid)
    for s in p.scenes:
        if s.id == sid:
            s.duration = None
    project_service.save_project(p)
    muse2 = FakeMuse(pid, sid)
    result2 = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse2))
    assert result2["status"] == "failed" and "giọng" in result2["error"]
    assert muse2.tasks == []                                                     # chưa tốn lượt Muse nào
    assert no_voice.image_path


@pytest.mark.parametrize("cast, words", [("none", "Chưa chọn nhân vật"), ("draft", "Thẩm Nhã Uyên")])
def test_missing_cast_or_unapproved_sheet_blocks_without_muse(isolated_projects_dir, cast, words):
    project = _climax_project(cast=cast)
    muse = FakeMuse(project.id, "scene_003")
    result = asyncio.run(cv.run_scene_climax_video(project.id, "scene_003", muse_call=muse))
    assert result["status"] == "failed" and words in result["error"] and muse.tasks == []


def test_reject_grid_redraws_with_feedback_in_same_chat(isolated_projects_dir):
    project = _climax_project(duration=4.0)
    pid, sid = project.id, "scene_003"
    muse = FakeMuse(pid, sid)
    asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    with pytest.raises(cv.ClimaxVideoError):
        cv.reject_grid(pid, sid, "   ")
    assert cv.reject_grid(pid, sid, "tóc góc sau sai")["status"] == "selected"
    state = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    assert state["status"] == "grid_review" and state["grid_version"] == 2
    second = muse.tasks[1]
    assert "Bản grid trước SAI: tóc góc sau sai" in second["prompt"]
    assert second["thread_url"] == THREAD and second["pin_account"] is True
    with pytest.raises(cv.ClimaxVideoError):
        cv.approve_grid(pid, "scene_002")                                        # không có grid chờ duyệt


def test_run_scene_rejects_wrong_scene_before_calling_muse(isolated_projects_dir):
    project = _climax_project()
    muse = FakeMuse(project.id, "scene_003")
    with pytest.raises(ValueError):
        asyncio.run(cv.run_scene_climax_video(project.id, "scene_001", muse_call=muse))   # thẻ miễn trừ
    with pytest.raises(LookupError):
        asyncio.run(cv.run_scene_climax_video(project.id, "scene_999", muse_call=muse))
    with pytest.raises(LookupError):
        asyncio.run(cv.run_scene_climax_video("proj_khong_co", "scene_003", muse_call=muse))
    assert muse.tasks == []


# ------------------------------------------------------------------------------------------------------------ API
@pytest.fixture
def client(isolated_projects_dir):
    app = FastAPI()
    app.include_router(climax_router.router)
    app.include_router(muse_bridge.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c
    climax_router._running.clear()


def _api_project():
    scenes = [_scene("scene_001", kind="disclaimer"), _scene("scene_002", beat="climax"), _scene("scene_003"),
              _scene("scene_004", energy="dramatic_climax", duration=4.0), _scene("scene_005", kind="board"),
              _scene("scene_006", sfx=["heartbeat"])]
    return _save_project(scenes, pid="proj_crime_api01")


def _statuses(pid):
    return {s.id: s.metadata.get("climax_video", {}).get("status") for s in project_service.get_project(pid).scenes}


def test_api_pick_toggle_and_ids(client):
    project = _api_project()
    pid = project.id
    base = f"/api/projects/{pid}/climax-video"
    # 4 cảnh hợp lệ -> tối đa 2: scene_002 (2 điểm), scene_004 (2 điểm)
    r = client.post(f"{base}/pick")
    assert r.status_code == 200 and r.json()["scene_ids"] == ["scene_002", "scene_004"]
    assert _statuses(pid) == {"scene_001": None, "scene_002": "selected", "scene_003": None, "scene_004": "selected",
                              "scene_005": None, "scene_006": None}

    # đã đủ 2 cảnh: bật thêm thì 400; tắt một cảnh rồi bật cảnh khác thì được
    assert client.put(f"{base}/scenes/scene_006", json={"enabled": True}).status_code == 400
    assert client.put(f"{base}/scenes/scene_002", json={"enabled": False}).json()["status"] is None
    assert client.put(f"{base}/scenes/scene_006", json={"enabled": True}).json()["status"] == "selected"
    # cảnh bảng ghim / thẻ miễn trừ không bật được
    assert client.put(f"{base}/scenes/scene_005", json={"enabled": True}).status_code == 400
    assert client.put(f"{base}/scenes/scene_001", json={"enabled": True}).status_code == 400
    assert client.put(f"{base}/scenes/scene_999", json={"enabled": True}).status_code == 404

    # chọn lại: bỏ dấu "selected" cũ (scene_006), không đụng cảnh "ready"
    p = project_service.get_project(pid)
    for s in p.scenes:
        if s.id == "scene_004":
            s.metadata["climax_video"] = {"status": "ready", "clips": 1, "grids": 1, "attempts": 1}
    project_service.save_project(p)
    r = client.post(f"{base}/pick")
    assert r.json()["scene_ids"] == ["scene_002", "scene_004"]
    assert _statuses(pid)["scene_004"] == "ready" and _statuses(pid)["scene_006"] is None
    assert _statuses(pid)["scene_002"] == "selected"

    st = client.get(f"{base}/status").json()
    assert st["running"] is False
    assert {s["scene_id"]: s["status"] for s in st["scenes"]} == {"scene_002": "selected", "scene_004": "ready"}

    assert client.post("/api/projects/proj_khong_co/climax-video/pick").status_code == 404
    assert client.get("/api/projects/proj_khong_co/climax-video/status").status_code == 404
    assert client.post("/api/projects/bad.id/climax-video/pick").status_code in (400, 404)
    assert client.put(f"{base}/scenes/bad%20id", json={"enabled": True}).status_code == 400
    assert client.get("/api/projects/_cases/climax-video/status").status_code == 400


def test_api_run_in_background_and_409_while_running(client, monkeypatch):
    project = _api_project()
    pid = project.id
    base = f"/api/projects/{pid}/climax-video"
    assert client.post(f"{base}/run").status_code == 400                        # chưa chọn cảnh nào
    client.put(f"{base}/scenes/scene_004", json={"enabled": True})              # 4 giây -> 1 clip

    gate = {"open": False}
    muse = FakeMuse(pid, "scene_004")

    async def slow_muse(task):
        while not gate["open"]:
            await asyncio.sleep(0.05)
        return await muse(task)

    monkeypatch.setattr(climax_router, "enqueue_and_wait_muse_task", slow_muse)
    r = client.post(f"{base}/run")
    assert r.status_code == 200 and r.json() == {"queued": ["scene_004"]}
    assert client.post(f"{base}/run").status_code == 409
    assert client.post(f"{base}/pick").status_code == 409
    assert client.get(f"{base}/status").json()["running"] is True

    gate["open"] = True
    _wait_idle(client, base)
    st = client.get(f"{base}/status").json()
    assert st["scenes"][0]["status"] == "grid_review" and st["scenes"][0]["grid_count"] == 1
    assert client.get(f"{base}/scenes/scene_004/grid?i=1").status_code == 200
    assert client.get(f"{base}/scenes/scene_004/grid?i=2").status_code == 404
    assert client.post(f"{base}/scenes/scene_004/grid/reject", json={"feedback": ""}).status_code == 400
    assert client.post(f"{base}/pick").json()["scene_ids"]                      # chọn lại không xoá grid đang chờ duyệt
    assert _statuses(pid)["scene_004"] == "grid_review"
    assert client.post(f"{base}/scenes/scene_004/grid/approve").json()["status"] == "grid_approved"
    for sid, st_ in _statuses(pid).items():                                    # bỏ cảnh khác vừa được chọn lại
        if sid != "scene_004" and st_:
            client.put(f"{base}/scenes/{sid}", json={"enabled": False})
    assert client.post(f"{base}/run").json() == {"queued": ["scene_004"]}
    _wait_idle(client, base)
    st = client.get(f"{base}/status").json()
    assert st["running"] is False
    s4 = st["scenes"][0]
    assert (s4["scene_id"], s4["status"], s4["error"], s4["clips"], s4["grids"], s4["attempts"]) == \
        ("scene_004", "ready", None, 1, 1, 1)
    scene = _scene_now(pid, "scene_004")
    assert scene.media_view_mode == "video" and Path(scene.motion_video_path).is_file()
    assert scene.video_url == f"/api/projects/{pid}/media/videos/scene_004_muse.mp4"

    # tắt cảnh đã có video: về lại ảnh, clip vẫn còn trên đĩa
    assert client.put(f"{base}/scenes/scene_004", json={"enabled": False}).status_code == 200
    scene = _scene_now(pid, "scene_004")
    assert scene.media_view_mode == "image" and Path(scene.motion_video_path).is_file()


def _wait_idle(client, base, seconds=120):
    deadline = time.time() + seconds
    while client.get(f"{base}/status").json()["running"] and time.time() < deadline:
        time.sleep(0.2)


def test_router_muse_call_uses_current_muse_bridge_function(monkeypatch):
    """Router truyền enqueue_and_wait_muse_task (qua lớp bọc bật Fleet Runner); thay hàm ở muse_bridge cũng có tác dụng."""
    seen = []

    async def fake(task):
        seen.append(task)
        return {"output_path": "x"}

    monkeypatch.setattr(muse_bridge, "enqueue_and_wait_muse_task", fake)
    assert asyncio.run(climax_router._muse_call({"mode": "text-to-image", "prompt": "p"})) == {"output_path": "x"}
    assert seen == [{"mode": "text-to-image", "prompt": "p"}]


def test_unexpected_error_names_its_type(isolated_projects_dir, monkeypatch):
    """Đo thật 27/10/2026: MemoryError không có chữ nào, lý do hiện ra rỗng ("Lỗi ngoài dự kiến: ")."""
    project = _climax_project(duration=4.0)
    pid, sid = project.id, "scene_003"

    def out_of_memory(*a, **k):
        raise MemoryError()

    asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=FakeMuse(pid, sid)))   # grid
    cv.approve_grid(pid, sid)
    monkeypatch.setattr(cv, "check_agent_video", out_of_memory)
    with pytest.raises(MemoryError):
        asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=FakeMuse(pid, sid)))
    state = _scene_now(pid, sid).metadata["climax_video"]
    assert state["status"] == "failed" and "MemoryError" in state["error"]
