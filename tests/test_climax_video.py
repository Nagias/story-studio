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

from models.schemas import Project, Scene  # noqa: E402
from routers import climax_video as climax_router  # noqa: E402
from routers import muse_bridge  # noqa: E402
from services import climax_video as cv  # noqa: E402
from services import project_service  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                                reason="cần ffmpeg/ffprobe trong PATH")


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


def _save_project(scenes: list[Scene], pid="proj_crime_test01") -> Project:
    project = Project(id=pid, name="Vụ thử", character_anchor="round white face with dot eyes, grey coat",
                      scenes=scenes)
    project_service.ensure_project_dirs(pid)
    for s in scenes:
        if s.metadata.get("visual_kind") in cv.ELIGIBLE_KINDS:
            img = project_service.get_scene_media_paths(pid, s.id)["image"]
            _picture(img, seed=s.order)
            s.image_path = str(img)
            s.image_url = f"/api/projects/{pid}/media/images/{img.name}"
    project_service.save_project(project)
    return project


def _scene_now(pid: str, sid: str) -> Scene:
    return next(s for s in project_service.get_project(pid).scenes if s.id == sid)


class FakeMuse:
    """Muse giả. `clip_plan(n)` (n = số lần gọi clip, đếm từ 1) trả "good" | "dark_cut" | "error" | "other"."""

    def __init__(self, pid: str, sid: str, clip_plan=lambda n: "good", grid_error=False, darken=True):
        self.pid, self.sid = pid, sid
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
            ref = Image.open(task["reference_image_path"]).convert("RGB").resize((660, 368))
            grid = Image.new("RGB", (2048, 1152), "white")
            for i in range(9):
                r, c = divmod(i, 3)
                grid.paste(ref, (c * 682 + 11, r * 384 + 8))
            grid.save(out, "JPEG", quality=92)
            return {"output_path": str(out), "status": "completed"}
        self.clip_calls += 1
        kind = self.clip_plan(self.clip_calls)
        if kind == "error":
            raise TimeoutError("Meta Muse task timed out after 900s")
        panel = Path(task["input_image_url"])
        if kind == "dark_cut":   # nửa sau là âm bản của ô: chỉnh màu từng khung xong vẫn là một cú cắt rõ
            negative = out.with_suffix(".am_ban.jpg")
            ImageOps.invert(Image.open(panel).convert("RGB")).save(negative)
            _cut_clip(panel, negative, out)
        elif kind == "other":
            _clip_from_image(_picture(out.with_suffix(".khac.jpg"), seed=777), out, darken=False)
        else:
            _clip_from_image(panel, out, darken=self.darken)
        return {"output_path": str(out), "status": "completed"}


# ---------------------------------------------------------------------------------------------------- chấm điểm, chọn
def test_constants_match_contract():
    assert (cv.CLIMAX_RATIO, cv.CLIP_SECONDS, cv.PANELS_PER_GRID, cv.MAX_CLIP_ATTEMPTS) == (0.5, 5, 9, 2)
    assert (cv.MIN_FIRST_SIMILARITY, cv.MAX_FRAME_JUMP, cv.MAX_BRIGHTNESS_CHANGE) == (0.45, 45.0, 0.15)
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
    mid = cv.clip_prompt(scene, 4, 6)
    last = cv.clip_prompt(scene, 9, None)
    assert "panel 4" in mid and "panel 6" in mid and cv.STYLE_LOCK_EN in mid
    assert "panel 9" in last and cv.STYLE_LOCK_EN in last
    assert "slightly" in mid.lower()
    # máy quay đứng yên (đo thật 27/10/2026: xin máy quay chuyển động thì Muse zoom sát rồi vẽ lại mặt nhân vật)
    for p in (mid, last):
        assert cv.CLIP_CAMERA_EN in p and "no zoom" in p and "push-in." not in p.replace("no push-in", "")
        assert f"Avoid: {cv.CLIP_NEGATIVE_EN}" in p        # runner không gửi negative_prompt của video


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


def test_match_clip_colors_restores_brightness_and_format(tmp_path):
    panel = _picture(tmp_path / "o1.jpg", seed=3)
    dark = _clip_from_image(panel, tmp_path / "muse.mp4", seconds=5, darken=True, size="1248x704")
    before = cv.check_clip(dark, panel, 5)
    assert not before["ok"] and before["brightness_change"] < -0.3
    assert any("sáng/tối" in r for r in before["reasons"])

    fixed = cv.match_clip_colors(dark, panel, tmp_path / "fixed.mp4")
    info = _probe(fixed)
    streams = info["streams"]
    assert [s["codec_type"] for s in streams] == ["video"]                      # không tiếng
    assert (streams[0]["width"], streams[0]["height"], streams[0]["r_frame_rate"]) == (1920, 1080, "25/1")
    assert abs(float(info["format"]["duration"]) - 5.0) < 0.15
    after = cv.check_clip(fixed, panel, 5)
    assert after["ok"], after
    assert abs(after["brightness_change"]) < 0.1


def test_check_clip_rejects_cut_wrong_start_and_bad_duration(tmp_path):
    panel = _picture(tmp_path / "o1.jpg", seed=5)
    good = cv.check_clip(_clip_from_image(panel, tmp_path / "good.mp4", darken=False), panel, 5)
    assert good["ok"] and good["reasons"] == []
    assert set(good) == {"ok", "reasons", "first_similarity", "max_jump", "brightness_change", "duration"}
    assert good["first_similarity"] > 0.9 and good["max_jump"] < 5

    cut = cv.check_clip(_cut_clip(panel, _picture(tmp_path / "x.jpg", seed=99), tmp_path / "cut.mp4"), panel, 5)
    assert not cut["ok"] and cut["max_jump"] > cv.MAX_FRAME_JUMP
    assert any("cắt cảnh" in r for r in cut["reasons"])

    other = cv.check_clip(_clip_from_image(_picture(tmp_path / "y.jpg", seed=42), tmp_path / "o.mp4", darken=False),
                          panel, 5)
    assert not other["ok"] and other["first_similarity"] < cv.MIN_FIRST_SIMILARITY
    assert any("khung đầu không giống ô gốc" in r for r in other["reasons"])

    short = cv.check_clip(_clip_from_image(panel, tmp_path / "short.mp4", seconds=2, darken=False), panel, 5)
    assert not short["ok"] and any("thời lượng" in r for r in short["reasons"])
    long_ = cv.check_clip(_clip_from_image(panel, tmp_path / "long.mp4", seconds=11, darken=False), panel, 5)
    assert not long_["ok"] and any("thời lượng" in r for r in long_["reasons"])
    ok10 = cv.check_clip(_clip_from_image(panel, tmp_path / "ten.mp4", seconds=10, darken=False), panel, 5)
    assert ok10["ok"], ok10


def test_concat_clips_joins_in_order(tmp_path):
    a = _clip_from_image(_picture(tmp_path / "a.jpg", seed=1), tmp_path / "a.mp4", seconds=2, darken=False)
    b = _clip_from_image(_picture(tmp_path / "b.jpg", seed=2), tmp_path / "b.mp4", seconds=3, darken=False,
                         size="640x360")
    out = cv.concat_clips([a, b], tmp_path / "joined.mp4")
    info = _probe(out)
    assert [s["codec_type"] for s in info["streams"]] == ["video"]
    v = info["streams"][0]
    assert (v["width"], v["height"], v["r_frame_rate"]) == (1920, 1080, "25/1")
    assert abs(float(info["format"]["duration"]) - 5.0) < 0.2
    # khung đầu là clip a, khung cuối là clip b
    first = cv._read_frames(out, 320, 180, 8)
    ref_a = cv._load_rgb(tmp_path / "a.jpg", (320, 180))
    ref_b = cv._load_rgb(tmp_path / "b.jpg", (320, 180))
    assert np.abs(first[0] - ref_a).mean() < np.abs(first[0] - ref_b).mean()
    assert np.abs(first[-1] - ref_b).mean() < np.abs(first[-1] - ref_a).mean()
    with pytest.raises(ValueError):
        cv.concat_clips([], tmp_path / "none.mp4")


# ----------------------------------------------------------------------------------------------- chạy trọn một cảnh
def _climax_project(duration=12.0):
    scenes = [_scene("scene_001", kind="disclaimer"), _scene("scene_002"),
              _scene("scene_003", beat="climax", energy="dramatic_climax", duration=duration)]
    return _save_project(scenes)


def test_run_scene_success_attaches_joined_clip(isolated_projects_dir):
    project = _climax_project(duration=12.0)          # 12 giây -> 3 clip, 1 grid, ô 1, 5, 9
    pid, sid = project.id, "scene_003"
    muse = FakeMuse(pid, sid)
    result = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))

    assert result == {"status": "ready", "clips": 3, "grids": 1, "attempts": 3}
    grid_tasks = [t for t in muse.tasks if t["mode"] == "text-to-image"]
    clip_tasks = [t for t in muse.tasks if t["mode"] == "image-to-video"]
    assert len(grid_tasks) == 1 and len(clip_tasks) == 3
    scene_image = project_service.get_scene_media_paths(pid, sid)["image"]
    assert Path(grid_tasks[0]["reference_image_path"]).resolve() == scene_image.resolve()
    assert grid_tasks[0]["parameters"]["aspect_ratio"] == "16:9"
    assert "Panel 1 (top left) is exactly the attached image" in grid_tasks[0]["prompt"]
    assert [Path(t["input_image_url"]).name for t in clip_tasks] == [
        f"{sid}_grid1_o1.jpg", f"{sid}_grid1_o5.jpg", f"{sid}_grid1_o9.jpg"]
    for t in muse.tasks:
        assert "project_id" not in t and "scene_id" not in t           # Muse không tự gắn kết quả vào cảnh
        for key in ("reference_image_path", "input_image_url"):
            if key in t:
                assert Path(t[key]).resolve().is_relative_to(isolated_projects_dir.resolve())
    for t in clip_tasks:
        assert t["duration"] == cv.CLIP_SECONDS and t["parameters"]["duration_sec"] == cv.CLIP_SECONDS
        assert cv.STYLE_LOCK_EN in t["prompt"]
        assert t["camera_motion"] == t["parameters"]["camera_motion"] == cv.CLIP_CAMERA_EN
        assert t["parameters"]["pacing"] == cv.CLIP_PACING_EN
    assert muse.status_during == ["grid", "clips", "clips", "clips"]

    scene = _scene_now(pid, sid)
    final = project_service.get_scene_media_paths(pid, sid)["motion_video"]
    assert Path(scene.motion_video_path) == final and final.is_file()
    assert scene.media_view_mode == "video" and scene.status_video == "ready"
    assert scene.metadata["climax_video"] == result
    assert scene.image_path and Path(scene.image_path).is_file()               # ảnh gốc còn nguyên
    info = _probe(final)
    v = info["streams"][0]
    assert [s["codec_type"] for s in info["streams"]] == ["video"]
    assert (v["width"], v["height"], v["r_frame_rate"]) == (1920, 1080, "25/1")
    assert abs(float(info["format"]["duration"]) - 15.0) < 0.3
    # đã chỉnh màu: khung cuối của video ghép không tối đi như clip Muse giả
    last = cv._read_frames(final, 320, 180, 8)[-1]
    panel9 = cv._load_rgb(final.parent / "climax" / f"{sid}_grid1_o9.jpg", (320, 180))
    assert abs(cv._luma(last.astype(np.float64)).mean() / cv._luma(panel9).mean() - 1) < cv.MAX_BRIGHTNESS_CHANGE
    assert (final.parent / "climax").is_dir()
    # cảnh khác không bị đụng
    assert "climax_video" not in _scene_now(pid, "scene_002").metadata


def test_run_scene_long_narration_uses_second_grid_from_panel_9(isolated_projects_dir, monkeypatch):
    project = _climax_project(duration=50.0)          # 50 giây -> 10 clip -> grid 1 (9 clip) + grid 2 (ô 1)
    pid, sid = project.id, "scene_003"
    # phần chỉnh màu/ghép thật đã có test riêng; ở đây chỉ xem thứ tự grid và ô, cho nhanh
    monkeypatch.setattr(cv, "match_clip_colors", lambda clip, panel, out: Path(shutil.copy2(clip, out)))
    joined = []
    monkeypatch.setattr(cv, "concat_clips", lambda clips, out: (joined.extend(clips), Path(shutil.copy2(clips[0], out)))[1])
    muse = FakeMuse(pid, sid, darken=False)
    result = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))

    assert result == {"status": "ready", "clips": 10, "grids": 2, "attempts": 10}
    grids = [t for t in muse.tasks if t["mode"] == "text-to-image"]
    assert len(grids) == 2
    assert Path(grids[1]["reference_image_path"]).name == f"{sid}_grid1_o9.jpg"
    assert "last frame of the previous segment" in grids[1]["prompt"]
    clips = [Path(t["input_image_url"]).name for t in muse.tasks if t["mode"] == "image-to-video"]
    assert clips == [f"{sid}_grid1_o{i}.jpg" for i in range(1, 10)] + [f"{sid}_grid2_o1.jpg"]
    assert [p.name for p in joined] == [f"{sid}_grid1_o{i}_lan1.mp4" for i in range(1, 10)] + [f"{sid}_grid2_o1_lan1.mp4"]


def test_run_scene_retries_a_bad_clip_once(isolated_projects_dir):
    project = _climax_project(duration=4.0)           # 1 clip
    pid, sid = project.id, "scene_003"
    muse = FakeMuse(pid, sid, clip_plan=lambda n: "dark_cut" if n == 1 else "good")
    result = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))
    assert result == {"status": "ready", "clips": 1, "grids": 1, "attempts": 2}
    assert _scene_now(pid, sid).media_view_mode == "video"


@pytest.mark.parametrize("plan, words", [
    (lambda n: "dark_cut", "cắt cảnh"),
    (lambda n: "other", "khung đầu không giống ô gốc"),
    (lambda n: "error", "timed out"),
])
def test_run_scene_fails_after_max_attempts_and_keeps_image(isolated_projects_dir, plan, words):
    project = _climax_project(duration=8.0)           # 2 clip; clip đầu hỏng cả hai lần
    pid, sid = project.id, "scene_003"
    before = _scene_now(pid, sid)
    muse = FakeMuse(pid, sid, clip_plan=plan)
    result = asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=muse))

    assert result["status"] == "failed" and words in result["error"]
    assert set(result) == {"status", "error"}
    assert muse.clip_calls == cv.MAX_CLIP_ATTEMPTS                              # dừng ở clip hỏng, không gọi tiếp
    scene = _scene_now(pid, sid)
    assert scene.metadata["climax_video"] == result
    assert scene.motion_video_path is None and scene.media_view_mode == before.media_view_mode == "image"
    assert scene.image_path == before.image_path and Path(scene.image_path).is_file()
    assert not project_service.get_scene_media_paths(pid, sid)["motion_video"].exists()


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
    deadline = time.time() + 120
    while client.get(f"{base}/status").json()["running"] and time.time() < deadline:
        time.sleep(0.2)
    st = client.get(f"{base}/status").json()
    assert st["running"] is False
    assert st["scenes"] == [{"scene_id": "scene_004", "status": "ready", "error": None, "clips": 1, "grids": 1,
                             "attempts": 1}]
    scene = _scene_now(pid, "scene_004")
    assert scene.media_view_mode == "video" and Path(scene.motion_video_path).is_file()
    assert scene.video_url == f"/api/projects/{pid}/media/videos/scene_004_muse.mp4"

    # tắt cảnh đã có video: về lại ảnh, clip vẫn còn trên đĩa
    assert client.put(f"{base}/scenes/scene_004", json={"enabled": False}).status_code == 200
    scene = _scene_now(pid, "scene_004")
    assert scene.media_view_mode == "image" and Path(scene.motion_video_path).is_file()


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

    monkeypatch.setattr(cv, "match_clip_colors", out_of_memory)
    with pytest.raises(MemoryError):
        asyncio.run(cv.run_scene_climax_video(pid, sid, muse_call=FakeMuse(pid, sid)))
    state = _scene_now(pid, sid).metadata["climax_video"]
    assert state["status"] == "failed" and "MemoryError" in state["error"]
