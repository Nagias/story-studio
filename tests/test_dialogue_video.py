"""Video Muse của một cảnh theo độ dài lời thoại (services/dialogue_video.py, routers/scene_muse_video.py).

Offline: Muse giả làm video bằng ffmpeg (testsrc), giọng đọc giả bằng ffmpeg (sine); dự án ghi vào thư mục tạm.
"""
import asyncio
import copy
import json
import subprocess
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
from routers import scene_muse_video as smv_router  # noqa: E402
from services import dialogue_video as dv  # noqa: E402
from services import project_service  # noqa: E402
from services.video_service import render_scene_video  # noqa: E402

PID = "proj_dlg01"
THREAD = "https://muse.ai/thread/2d353dc3-3d3d-44b3-a3e7-51f54a295757"
LONG_TEXT = ("Đêm đó, Lâm Hạ trở về căn hộ tầng sáu và thấy cửa khép hờ. Cô đứng lặng trong bóng tối của hành lang, "
             "nghe tiếng nước nhỏ giọt từ trong bếp. Sáng hôm sau, cô tới đồn cảnh sát trình báo, nhưng viên trực ban "
             "chỉ ghi vài dòng rồi bảo cô về nhà chờ. Ba ngày sau, người ta tìm thấy chiếc xe đạp của em trai cô bên "
             "bờ sông.")


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def _seconds(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         capture_output=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def _make_project(text=LONG_TEXT, voice_sec=20.0, voice=True) -> tuple[Project, Scene]:
    scene = Scene(id="scene_005", order=5, text=text, image_prompt="Wide shot of a woman at an apartment door at night.",
                  metadata={"visual_kind": "image"})
    project = Project(id=PID, name="Thử video lời thoại", style_preset="horror_cartoon_2d", scenes=[scene])
    project_service.ensure_project_dirs(PID)
    media = project_service.get_scene_media_paths(PID, scene.id)
    Image.new("RGB", (1280, 720), (30, 40, 60)).save(media["image"])
    scene.image_path = str(media["image"])
    if voice:
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=300:duration={voice_sec}", str(media["audio"]))
        scene.voice_audio_path = str(media["audio"])
        scene.duration = voice_sec
    project_service.save_project(project)
    return project, scene


class FakeMuse:
    """Làm video `seconds` giây (mặc định 6) tại output_path; lỗi ở lượt `fail_at` (đếm từ 1) nếu có."""

    def __init__(self, seconds=6.0, fail_at=None):
        self.tasks, self.seconds, self.fail_at = [], seconds, fail_at

    async def __call__(self, task):
        self.tasks.append(copy.deepcopy(task))
        if self.fail_at == len(self.tasks):
            raise RuntimeError("NO_MEDIA: Muse không trả video")
        sec = self.seconds[len(self.tasks) - 1] if isinstance(self.seconds, list) else self.seconds
        _ffmpeg("-f", "lavfi", "-i", f"testsrc=size=1280x720:rate=24:duration={sec}", "-pix_fmt", "yuv420p",
                task["output_path"])
        return {"output_path": task["output_path"], "thread_url": THREAD, "executed_by": "muse_acc_vid_01"}


@pytest.fixture(autouse=True)
def _no_pace(monkeypatch):
    async def no_sleep(_s):
        return None
    monkeypatch.setattr(dv, "pace_sleep", no_sleep)


def _scene():
    return dv.load_scene(PID, "scene_005")[1]


# ---------------------------------------------------------------------------------------------- chia lời thoại
def test_short_narration_is_one_video():
    segs = dv.plan_segments("Cô mở cửa. Căn phòng tối om.", 4.2)
    assert len(segs) == 1 and segs[0]["start"] == 0 and segs[0]["end"] == 4.2


def test_long_narration_splits_into_contiguous_sentence_segments():
    segs = dv.plan_segments(LONG_TEXT, 20.0)
    # 4 câu 4,1 / 4,7 / 6,6 / 4,7 giây: hai câu liền nhau nào cũng quá 8 giây nên mỗi câu một video (cắt ở hết câu)
    assert [s["text"][:12] for s in segs] == ["Đêm đó, Lâm ", "Cô đứng lặng", "Sáng hôm sau", "Ba ngày sau,"]
    assert " ".join(s["text"] for s in segs) == " ".join(LONG_TEXT.split())     # đủ chữ, đúng thứ tự, không lặp
    assert all(s["seconds"] <= dv.SEGMENT_MAX_SEC for s in segs)
    assert segs[0]["start"] == 0 and segs[-1]["end"] == 20.0
    assert all(abs(a["end"] - b["start"]) < 1e-6 for a, b in zip(segs, segs[1:]))


def test_one_very_long_sentence_is_split_by_clauses_then_words():
    sentence = ", ".join(["người đàn ông đi chậm qua con hẻm tối"] * 8) + "."
    segs = dv.plan_segments(sentence, 24.0)
    assert len(segs) >= 3 and all(s["seconds"] <= dv.SEGMENT_MAX_SEC + 1e-6 for s in segs)
    assert " ".join(s["text"] for s in segs) == sentence
    words = " ".join(["chữ"] * 120)
    segs = dv.plan_segments(words, 30.0)
    assert len(segs) == 4 and " ".join(s["text"] for s in segs) == words


def test_too_many_videos_is_refused_and_empty_text_too():
    with pytest.raises(dv.DialogueVideoError):
        dv.plan_segments(" ".join(["Câu ngắn."] * 200), 200.0)
    with pytest.raises(dv.DialogueVideoError):
        dv.plan_segments("   ", 5)


def test_plan_without_voice_is_an_estimate(isolated_projects_dir):
    project, scene = _make_project(voice=False)
    plan = dv.scene_plan(project, scene)
    assert plan["estimated"] is True and plan["video_count"] >= 2
    with pytest.raises(dv.DialogueVideoError, match="thu giọng"):
        dv.prepare_run(PID, scene.id)                                           # không tốn lượt Muse khi chưa có giọng


# ------------------------------------------------------------------------------------------------- chạy, ghép
def test_long_scene_makes_one_muse_video_per_segment_and_assembles(isolated_projects_dir):
    _make_project(voice_sec=20.0)
    state = dv.prepare_run(PID, "scene_005")
    assert state["video_count"] == 4
    muse = FakeMuse(seconds=[6.0, 9.0, 5.0, 5.0])
    res = asyncio.run(dv.run_scene(PID, "scene_005", muse))
    assert res["status"] == "ready" and len(muse.tasks) == 4
    segs = state["segments"]
    for k, t in enumerate(muse.tasks, 1):
        assert t["mode"] == "image-to-video" and t["raw_prompt"]
        assert f"video {k}/4" in t["prompt"] and f"\"{segs[k - 1]['text']}\"" in t["prompt"]
        assert "ĐỔI CẢNH" in t["prompt"] and "không được chỉ đổi góc máy" in t["prompt"]
        assert "realistic human face" in t["prompt"]                            # luật mặt đầu tròn
    assert muse.tasks[0]["attachments"] == [str(project_service.get_scene_media_paths(PID, "scene_005")["image"])]
    assert muse.tasks[1]["attachments"][0].endswith("scene_005_seg1_cuoi.jpg")  # khung cuối video trước
    assert "thread_url" not in muse.tasks[0]
    assert muse.tasks[1]["thread_url"] == THREAD and muse.tasks[3]["pin_account"]   # cùng một side chat
    scene = _scene()
    final = Path(scene.motion_video_path)
    assert final.name == "scene_005_muse.mp4" and scene.media_view_mode == "video" and scene.status_video == "ready"
    # video 1–3 chiếm đúng thời gian đoạn 1–3 được đọc (video 3 dài 5 s, ngắn hơn đoạn 3 thì giữ khung cuối);
    # video cuối 5 s dài hơn đoạn 4 (4,7 s): giữ trọn, không cắt
    expected = segs[0]["seconds"] + segs[1]["seconds"] + segs[2]["seconds"] + max(segs[3]["seconds"], 5.0)
    assert abs(_seconds(final) - expected) < 0.2
    st = dv.scene_state(scene)
    assert st["status"] == "ready" and st["muse_calls"] == 4 and len(st["clips"]) == 4


def test_short_scene_one_video_kept_whole_and_render_does_not_cut_it(isolated_projects_dir):
    _make_project(text="Cô mở cửa. Căn phòng tối om.", voice_sec=3.0)
    assert dv.prepare_run(PID, "scene_005")["video_count"] == 1
    muse = FakeMuse(seconds=5.0)
    asyncio.run(dv.run_scene(PID, "scene_005", muse))
    scene = _scene()
    assert len(muse.tasks) == 1 and abs(_seconds(scene.motion_video_path) - 5.0) < 0.15
    assert dv.render_seconds(scene) == pytest.approx(5.0, abs=0.15)              # cảnh dài theo video, không cắt
    media = project_service.get_scene_media_paths(PID, "scene_005")
    out = asyncio.run(render_scene_video(scene.motion_video_path, str(media["audio"]), str(media["video"]),
                                         duration=dv.render_seconds(scene), resolution="720p"))
    assert abs(_seconds(out["video_path"]) - 5.0) < 0.2
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=duration",
                            "-of", "csv=p=0", out["video_path"]], capture_output=True, text=True).stdout
    assert abs(float(probe.strip()) - 5.0) < 0.2                                # tiếng đệm lặng cho hết cảnh


def test_render_seconds_caps_tail_and_ignores_other_clips(isolated_projects_dir):
    scene = Scene(id="s", order=1, text="t", duration=3.0, media_view_mode="video", motion_video_path="/x/a.mp4",
                  metadata={dv.STATE_KEY: {"status": "ready", "video_seconds": 20.0, "video_path": "/x/a.mp4"}})
    assert dv.render_seconds(scene) == 3.0 + dv.MAX_TAIL_SEC
    scene.motion_video_path = "/x/other.mp4"
    assert dv.render_seconds(scene) is None
    scene.motion_video_path, scene.metadata[dv.STATE_KEY]["video_seconds"] = "/x/a.mp4", 2.0
    assert dv.render_seconds(scene) is None


def test_failure_keeps_done_videos_and_rerun_continues(isolated_projects_dir):
    _make_project(voice_sec=20.0)
    dv.prepare_run(PID, "scene_005")
    res = asyncio.run(dv.run_scene(PID, "scene_005", FakeMuse(fail_at=2)))
    st = dv.scene_state(_scene())
    assert res["status"] == "failed" and st["status"] == "failed" and "NO_MEDIA" in st["error"]
    assert len(st["clips"]) == 1 and st["thread_url"] is None                   # chat hỏng: lần sau chat mới
    assert _scene().status_video == "error"
    dv.prepare_run(PID, "scene_005")
    again = FakeMuse()
    assert asyncio.run(dv.run_scene(PID, "scene_005", again))["status"] == "ready"
    assert len(again.tasks) == 3 and "video 2/4" in again.tasks[0]["prompt"]   # chỉ làm 3 video còn lại


def test_changed_narration_restarts_plan(isolated_projects_dir):
    _make_project(voice_sec=20.0)
    dv.prepare_run(PID, "scene_005")
    asyncio.run(dv.run_scene(PID, "scene_005", FakeMuse(fail_at=2)))
    project, scene = dv.load_scene(PID, "scene_005")
    scene.text = "Cô mở cửa. Căn phòng tối om. " * 3
    project_service.save_project(project)
    assert dv.prepare_run(PID, "scene_005")["clips"] == []


def test_location_lock_goes_into_video_prompt(isolated_projects_dir):
    from services import location_sheets as ls
    _make_project(text="Cô mở cửa. Căn phòng tối om.", voice_sec=3.0)
    design = ("A cramped sixth-floor apartment living room with peeling pale green walls, a window on the left with "
              "torn yellow curtains, a low brown sofa, a round wooden table and a bare bulb giving warm dim light.")
    project, _ = dv.load_scene(PID, "scene_005")
    project.scenes.append(Scene(id="scene_006", order=6, text="x", image_prompt="room", metadata={"visual_kind": "image"}))
    project_service.save_project(project)
    loc = ls.create_location(PID, "Căn hộ", design, ["scene_005", "scene_006"])
    plate = isolated_projects_dir / PID / "locations" / loc.location_id / "plate_v1.jpg"
    plate.parent.mkdir(parents=True)
    Image.new("RGB", (1280, 720)).save(plate)

    def approve(s):
        s.plate_path, s.versions, s.status = str(plate), [str(plate)], "approved"
    ls._update(PID, loc.location_id, approve)
    dv.prepare_run(PID, "scene_005")
    muse = FakeMuse(seconds=5.0)
    asyncio.run(dv.run_scene(PID, "scene_005", muse))
    t = muse.tasks[0]
    assert design in t["prompt"] and t["attachments"][-1] == str(plate.resolve())
    assert "ẢNH CHUẨN CỦA BỐI CẢNH" in t["prompt"]


# ---------------------------------------------------------------------------------------------------- API
@pytest.fixture
def client(isolated_projects_dir):
    app = FastAPI()
    app.include_router(smv_router.router)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c
    smv_router._running.clear()


def test_api_plan_run_status(client, monkeypatch):
    _make_project(voice_sec=20.0)
    base = f"/api/projects/{PID}/scenes/scene_005/muse-video"
    plan = client.get(f"{base}/plan").json()
    assert plan["video_count"] == 4 and plan["estimated"] is False and len(plan["segments"]) == 4
    assert client.get(f"/api/projects/{PID}/scenes/scene_999/muse-video/plan").status_code == 404
    muse = FakeMuse(seconds=5.0)
    monkeypatch.setattr(smv_router, "muse_call_starting_runner", muse)
    r = client.post(f"{base}/run").json()
    assert r["muse_calls_needed"] == 4
    end = time.time() + 60
    while client.get(f"{base}/status").json()["running"] and time.time() < end:
        time.sleep(0.2)
    st = client.get(f"{base}/status").json()
    assert st["status"] == "ready" and st["done_videos"] == 4 and len(muse.tasks) == 4
    assert client.get(f"{base}/plan").json()["done_videos"] == 4


def test_api_run_without_voice_is_400_and_costs_nothing(client, monkeypatch):
    _make_project(voice=False)
    muse = FakeMuse()
    monkeypatch.setattr(smv_router, "muse_call_starting_runner", muse)
    r = client.post(f"/api/projects/{PID}/scenes/scene_005/muse-video/run")
    assert r.status_code == 400 and "thu giọng" in r.json()["detail"] and muse.tasks == []


def test_autosave_from_ui_keeps_server_owned_video_state(isolated_projects_dir):
    from routers.api import _keep_server_media
    _make_project(voice_sec=3.0)
    dv._merge_state(PID, "scene_005", {"status": "ready"})
    existing = project_service.get_project(PID)
    stale = existing.model_copy(deep=True).scenes
    stale[0].metadata.pop(dv.STATE_KEY)
    _keep_server_media(existing, stale)
    assert stale[0].metadata[dv.STATE_KEY]["status"] == "ready"
