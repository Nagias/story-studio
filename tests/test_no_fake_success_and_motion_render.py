"""
Kiểm tra 2 nhóm sửa lỗi (2026-10-19):

1. Thất bại không được báo thành công: chuỗi dự phòng ảnh chỉ còn Muse → 9router → lỗi,
   route gen-image/gen-voice ghi rõ lỗi hoặc engine dự phòng vào cảnh, mẫu giọng VieNeu
   không bị cache bằng bản Edge.
2. Clip video Muse vào được bản dựng: clip lưu file riêng, bước dựng đọc clip và ghi ra
   file segment khác, lệnh ffmpeg lặp clip và chuẩn hoá âm thanh 48 kHz stereo.

Mọi dữ liệu dự án nằm trong tmp_path; không gọi Muse, 9router, Edge-TTS hay ffmpeg thật.
"""
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import shutil
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
from models.schemas import ProjectCreateRequest, Scene, SceneCreateRequest  # noqa: E402
from routers import api as api_module  # noqa: E402
from routers import muse_bridge  # noqa: E402
from services import image_service, project_service, video_service  # noqa: E402

MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048


# ----------------------------------------------------------------------------- fixtures

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Chuyển thư mục dự án, static và muse_outputs sang tmp_path."""
    projects = tmp_path / "projects"
    static = tmp_path / "static"
    muse_out = static / "muse_outputs"
    for d in (projects, static, muse_out):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(project_service, "PROJECTS_DIR", projects)
    monkeypatch.setattr(api_module, "PROJECTS_DIR", projects)
    monkeypatch.setattr(api_module, "STATIC_DIR", static)
    monkeypatch.setattr(muse_bridge, "PROJECTS_DIR", projects)
    monkeypatch.setattr(muse_bridge, "MUSE_OUTPUTS_DIR", muse_out)
    monkeypatch.setattr(config, "STATIC_DIR", static)
    return SimpleNamespace(projects=projects, static=static, muse_out=muse_out)


@pytest.fixture
def api_client(sandbox):
    app = FastAPI()
    app.include_router(api_module.router)
    app.include_router(muse_bridge.router)
    with TestClient(app) as client:
        yield client


def _make_project_with_scene(provider: str = "9router_gemini"):
    project = project_service.create_project(ProjectCreateRequest(name="Test", image_provider=provider))
    scene = project_service.add_scene(project.id, SceneCreateRequest(text="Cảnh thử nghiệm", image_prompt="a dark alley"))
    return project, scene


def _write_jpg(path: Path, size=(1280, 720)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (20, 20, 20)).save(path, "JPEG")


# ----------------------------------------------------------------------------- việc 1: ảnh

@pytest.mark.asyncio
async def test_image_chain_reports_failure_instead_of_fake_image(tmp_path, monkeypatch):
    """Muse offline + 9router lỗi → success False, không gọi Pollinations hay ảnh giả, không có file."""
    monkeypatch.setattr(muse_bridge, "is_kind_online", lambda kind: False)

    async def broken_9router(prompt, output_path, model=None):
        raise RuntimeError("9router down")

    async def must_not_run(*args, **kwargs):
        raise AssertionError("Pollinations không được nằm trong chuỗi tự động")

    def mock_must_not_run(*args, **kwargs):
        raise AssertionError("Ảnh giả không được nằm trong chuỗi tự động")

    monkeypatch.setattr(image_service, "generate_9router_gemini", broken_9router)
    monkeypatch.setattr(image_service, "generate_pollinations", must_not_run)
    monkeypatch.setattr(image_service, "generate_mock_cinematic", mock_must_not_run)

    out = tmp_path / "scene.jpg"
    res = await image_service.generate_image(prompt="a dark alley", provider="meta_muse_cloud", output_path=str(out))

    assert res["success"] is False
    assert res["image_path"] is None
    assert "Muse" in res["error"] and "9router down" in res["error"]
    assert not out.exists()


@pytest.mark.asyncio
async def test_image_chain_muse_offline_falls_back_to_9router_with_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(muse_bridge, "is_kind_online", lambda kind: False)

    async def ok_9router(prompt, output_path, model=None):
        _write_jpg(Path(output_path))
        return output_path

    monkeypatch.setattr(image_service, "generate_9router_gemini", ok_9router)

    out = tmp_path / "scene.jpg"
    res = await image_service.generate_image(prompt="a dark alley", provider="meta_muse_cloud", output_path=str(out))

    assert res["success"] is True
    assert res["provider"] == "9router_gemini"
    assert "Muse" in (res["fallback_reason"] or "")
    assert out.exists()


@pytest.mark.asyncio
async def test_gemini_flash_alias_routes_to_9router(tmp_path, monkeypatch):
    called = {}

    async def ok_9router(prompt, output_path, model=None):
        called["yes"] = True
        _write_jpg(Path(output_path))
        return output_path

    monkeypatch.setattr(image_service, "generate_9router_gemini", ok_9router)
    res = await image_service.generate_image(prompt="x", provider="gemini_flash", output_path=str(tmp_path / "a.jpg"))
    assert res["success"] is True and called.get("yes")


def test_crop_to_aspect_makes_square_image_16_9():
    img = Image.new("RGB", (1024, 1024))
    cropped = image_service.crop_to_aspect(img, 16 / 9)
    w, h = cropped.size
    assert abs(w / h - 16 / 9) < 0.01
    assert w == 1024


def test_gen_image_route_returns_502_and_marks_scene_error(api_client, monkeypatch):
    project, scene = _make_project_with_scene()

    async def failing_generate_image(**kwargs):
        return {"success": False, "image_path": None, "provider": None, "error": "Muse: offline | 9router: HTTP 500"}

    monkeypatch.setattr(api_module, "generate_image", failing_generate_image)

    resp = api_client.post(f"/api/projects/{project.id}/scenes/{scene.id}/gen-image", json={"prompt": "x"})
    assert resp.status_code == 502
    assert "9router: HTTP 500" in resp.json()["detail"]

    saved = project_service.get_project(project.id).scenes[0]
    assert saved.status_image == "error"
    assert "9router" in saved.metadata["image_error"]
    assert saved.image_path is None
    assert saved.status != "ready"


def test_gen_image_route_reports_fallback_provider(api_client, monkeypatch):
    project, scene = _make_project_with_scene()

    async def fallback_generate_image(**kwargs):
        _write_jpg(Path(kwargs["output_path"]))
        return {
            "success": True,
            "image_path": kwargs["output_path"],
            "provider": "9router_gemini",
            "fallback_reason": "Meta Muse lỗi (offline), đã chuyển sang 9router.",
        }

    monkeypatch.setattr(api_module, "generate_image", fallback_generate_image)

    resp = api_client.post(f"/api/projects/{project.id}/scenes/{scene.id}/gen-image", json={"prompt": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "9router_gemini"
    assert "Muse" in body["fallback_reason"]

    saved = project_service.get_project(project.id).scenes[0]
    assert saved.status_image == "ready"
    assert saved.metadata["image_fallback"]["provider"] == "9router_gemini"


# ----------------------------------------------------------------------------- việc 1: chia cảnh

@pytest.mark.asyncio
async def test_scene_analysis_reports_why_it_fell_back_offline(monkeypatch):
    """9router lỗi (vd key sai → 401) thì kết quả offline phải mang lý do, không im lặng."""
    from services import script_splitter

    async def failing_llm(self, *args, **kwargs):
        self.last_error = '9router HTTP 401: {"error":{"message":"Invalid API key"}}'
        return None

    monkeypatch.setattr(script_splitter.SemanticStoryAnalyzer, "call_9router_semantic_analyzer", failing_llm)
    monkeypatch.setattr(script_splitter, "NINEROUTER_API_KEY", "dummy-key-for-test")
    res = await script_splitter.analyze_vox_script_async(full_text="Đêm mưa. Một chiếc taxi dừng lại.", provider="9router")

    assert res["scenes"]
    assert "401" in res["fallback_reason"]


@pytest.mark.asyncio
async def test_storyboard_llm_request_disables_streaming(monkeypatch):
    """Thiếu stream:false thì 9router trả body không phải JSON, storyboard luôn rơi về offline."""
    from services import storyboard_engine
    sent = {}

    class FakeResp:
        status_code = 500
        text = "stop here"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            sent["payload"] = json
            return FakeResp()

    monkeypatch.setattr(storyboard_engine.httpx, "AsyncClient", FakeClient)
    await storyboard_engine.deconstruct_script_async(
        "Đêm mưa. Một chiếc taxi dừng lại.", api_key="test-key", base_url="http://127.0.0.1:9/v1")

    assert sent["payload"]["stream"] is False


def test_create_from_script_records_offline_analysis(api_client, monkeypatch):
    async def offline_analysis(**kwargs):
        return {"scenes": [], "fallback_reason": "9router HTTP 401: Invalid API key"}

    monkeypatch.setattr(api_module, "analyze_vox_script_async", offline_analysis)
    resp = api_client.post("/api/projects/create-from-script", json={
        "text": "Đêm mưa tháng mười, một chiếc taxi dừng trước con hẻm nhỏ.",
        "generate_initial_images": False,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scenes"], "vẫn phải có cảnh từ bộ chia offline"
    assert "401" in body["metadata"]["scene_analysis"]["fallback_reason"]
    assert project_service.get_project(body["id"]).metadata["scene_analysis"]["provider"] == "offline"


# ----------------------------------------------------------------------------- việc 1: giọng

def _fake_tts(fallback: bool):
    async def fake_generate_speech(text, voice, output_audio_path, output_srt_path=None, rate="+0%", pitch="+0Hz"):
        Path(output_audio_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_audio_path).write_bytes(b"ID3" + b"\x00" * 2000)
        srt = output_srt_path or str(Path(output_audio_path).with_suffix(".srt"))
        Path(srt).write_text("1\n00:00:00,000 --> 00:00:02,000\nxin chào\n", encoding="utf-8")
        return {
            "audio_path": output_audio_path,
            "srt_path": srt,
            "duration": 2.0,
            "voice": "vi-VN-HoaiMyNeural" if fallback else voice,
            "requested_voice": voice,
            "fallback_used": fallback,
            "fallback_reason": "VieNeu voice 'vieneu-MaiAnh' unavailable" if fallback else None,
        }
    return fake_generate_speech


def test_vieneu_env_keeps_heavy_caches_in_project_folder(monkeypatch):
    """uv cache, Python của uv và model HuggingFace của VieNeu phải nằm trong .cache của dự án (ổ D)."""
    from services import tts_service
    monkeypatch.setenv("UV_CACHE_DIR", r"C:\Users\someone\AppData\Local\uv\cache")
    env = tts_service.vieneu_env()
    cache = (ROOT / ".cache").resolve()
    for key in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "HF_HOME"):
        assert Path(env[key]).resolve().is_relative_to(cache), key


@pytest.mark.asyncio
async def test_vieneu_failure_reason_is_reported(tmp_path, monkeypatch):
    """Server VieNeu không bật được + CLI lỗi → đọc bằng Edge nhưng fallback_reason nói rõ vì sao."""
    from services import tts_service

    async def no_server():
        return False

    class FakeProc:
        returncode = 1

        async def communicate(self):
            return b"", b"model load failed"

    async def fake_exec(*cmd, **kwargs):
        assert Path(kwargs["env"]["HF_HOME"]).resolve().is_relative_to((ROOT / ".cache").resolve())
        return FakeProc()

    class FakeCommunicate:
        def __init__(self, **kwargs):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"\xff\xfb" + b"\x00" * 2000}

    monkeypatch.setattr(tts_service, "ensure_vieneu_server", no_server)
    monkeypatch.setattr(tts_service.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(tts_service.edge_tts, "Communicate", FakeCommunicate)
    monkeypatch.setattr(tts_service, "get_audio_duration", lambda path: 1.5)  # file mp3 ở đây là giả

    res = await tts_service.generate_speech("Đêm mưa tháng mười.", voice="vieneu-MaiAnh",
                                            output_audio_path=str(tmp_path / "a.mp3"))
    assert res["fallback_used"] is True
    assert res["voice"] == "vi-VN-HoaiMyNeural"
    assert "server VieNeu không bật được" in res["fallback_reason"]
    assert "model load failed" in res["fallback_reason"]


def test_gen_voice_records_fallback_on_scene(api_client, monkeypatch):
    project, scene = _make_project_with_scene()
    monkeypatch.setattr(api_module, "generate_speech", _fake_tts(fallback=True))

    resp = api_client.post(f"/api/projects/{project.id}/scenes/{scene.id}/gen-voice", json={"voice": "vieneu-MaiAnh"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["fallback_used"] is True
    assert body["voice"] == "vi-VN-HoaiMyNeural"

    saved = project_service.get_project(project.id).scenes[0]
    assert saved.metadata["voice_fallback"]["used_voice"] == "vi-VN-HoaiMyNeural"
    assert saved.metadata["voice_fallback"]["requested_voice"] == "vieneu-MaiAnh"


def test_gen_voice_clears_old_fallback_flag(api_client, monkeypatch):
    project, scene = _make_project_with_scene()
    monkeypatch.setattr(api_module, "generate_speech", _fake_tts(fallback=True))
    api_client.post(f"/api/projects/{project.id}/scenes/{scene.id}/gen-voice", json={"voice": "vieneu-MaiAnh"})
    monkeypatch.setattr(api_module, "generate_speech", _fake_tts(fallback=False))
    api_client.post(f"/api/projects/{project.id}/scenes/{scene.id}/gen-voice", json={"voice": "vieneu-MaiAnh"})

    saved = project_service.get_project(project.id).scenes[0]
    assert "voice_fallback" not in saved.metadata


def test_voice_sample_fallback_is_not_cached_under_vieneu_name(api_client, sandbox, monkeypatch):
    monkeypatch.setattr(api_module, "generate_speech", _fake_tts(fallback=True))
    resp = api_client.get("/api/voices/vieneu-MaiAnh/sample")
    assert resp.status_code == 200
    assert resp.headers.get("X-Voice-Fallback")
    assert resp.headers.get("Cache-Control") == "no-store"

    samples = sandbox.static / "voice_samples"
    assert not (samples / "vieneu-MaiAnh.mp3").exists()
    assert not list(samples.glob("_tmp_*")), "file tạm phải được dọn sau khi trả về"


def test_voice_sample_real_voice_is_cached(api_client, sandbox, monkeypatch):
    monkeypatch.setattr(api_module, "generate_speech", _fake_tts(fallback=False))
    resp = api_client.get("/api/voices/vieneu-MaiAnh/sample")
    assert resp.status_code == 200
    assert (sandbox.static / "voice_samples" / "vieneu-MaiAnh.mp3").exists()


# ----------------------------------------------------------------------------- việc 2: clip Muse

def test_muse_video_complete_saves_separate_clip(api_client, sandbox):
    project, scene = _make_project_with_scene()
    task_id = "task_testclip01"
    muse_bridge.active_tasks[task_id] = {
        "task_id": task_id,
        "mode": "image-to-video",
        "project_id": project.id,
        "scene_id": scene.id,
        "status": "processing",
    }
    try:
        resp = api_client.post(
            f"/api/muse-bridge/tasks/{task_id}/complete",
            files={"file": ("clip.mp4", MP4_BYTES, "video/mp4")},
        )
    finally:
        muse_bridge.active_tasks.pop(task_id, None)
        muse_bridge.task_history[:] = [t for t in muse_bridge.task_history if t.get("task_id") != task_id]

    assert resp.status_code == 200
    videos = sandbox.projects / project.id / "videos"
    assert (videos / f"{scene.id}_muse.mp4").exists()
    assert not (videos / f"{scene.id}.mp4").exists(), "file segment dựng không được bị clip Muse chiếm"

    saved = project_service.get_project(project.id).scenes[0]
    assert saved.motion_video_path.endswith(f"{scene.id}_muse.mp4")
    assert saved.media_view_mode == "video"
    assert saved.status_video == "ready"


def test_render_input_prefers_motion_clip_over_segment(sandbox):
    media = {
        "image": sandbox.projects / "p1" / "images" / "s1.jpg",
        "video": sandbox.projects / "p1" / "videos" / "s1.mp4",
        "motion_video": sandbox.projects / "p1" / "videos" / "s1_muse.mp4",
        "audio": sandbox.projects / "p1" / "audio" / "s1.mp3",
    }
    _write_jpg(media["image"])
    media["motion_video"].parent.mkdir(parents=True, exist_ok=True)
    media["motion_video"].write_bytes(MP4_BYTES)
    media["video"].write_bytes(MP4_BYTES)  # đoạn dựng cũ

    video_scene = Scene(id="s1", order=1, text="x", media_view_mode="video",
                        motion_video_path=str(media["motion_video"]),
                        video_segment_path=str(media["video"]))
    assert api_module._scene_render_input(video_scene, media) == str(media["motion_video"])

    image_scene = Scene(id="s1", order=1, text="x", media_view_mode="image")
    assert api_module._scene_render_input(image_scene, media) == str(media["image"])


def test_render_input_migrates_legacy_clip_stored_on_segment_path(sandbox):
    """Dữ liệu cũ: clip Muse nằm ở videos/{scene}.mp4 → tách sang _muse.mp4 rồi mới dựng."""
    media = {
        "image": sandbox.projects / "p2" / "images" / "s1.jpg",
        "video": sandbox.projects / "p2" / "videos" / "s1.mp4",
        "motion_video": sandbox.projects / "p2" / "videos" / "s1_muse.mp4",
    }
    media["video"].parent.mkdir(parents=True)
    media["video"].write_bytes(MP4_BYTES)

    scene = Scene(id="s1", order=1, text="x", media_view_mode="video", video_segment_path=str(media["video"]))
    chosen = api_module._scene_render_input(scene, media)

    assert chosen == str(media["motion_video"])
    assert media["motion_video"].read_bytes() == MP4_BYTES
    assert scene.motion_video_path == str(media["motion_video"])


# ----------------------------------------------------------------------------- việc 2: ffmpeg

class _FakeProc:
    returncode = 0

    async def communicate(self):
        return b"", b""


@pytest.fixture
def captured_ffmpeg(monkeypatch):
    calls = []

    async def fake_exec(*cmd, **kwargs):
        calls.append(list(cmd))
        Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmd[-1]).write_bytes(b"\x00" * 2048)
        return _FakeProc()

    monkeypatch.setattr(video_service.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(video_service.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="", returncode=0))
    # ffmpeg/ffprobe đều là giả: thời lượng cũng phải giả rõ ràng (hàm thật nay báo lỗi thay vì đoán 3 giây)
    monkeypatch.setattr(video_service, "get_audio_duration", lambda path: 3.0)
    return calls


def _has_pair(cmd, flag, value):
    return any(cmd[i] == flag and cmd[i + 1] == value for i in range(len(cmd) - 1))


@pytest.mark.asyncio
async def test_video_clip_render_loops_clip_and_normalizes_audio(tmp_path, captured_ffmpeg):
    clip = tmp_path / "s1_muse.mp4"
    clip.write_bytes(MP4_BYTES)
    voice = tmp_path / "s1.mp3"
    voice.write_bytes(b"ID3" + b"\x00" * 100)
    out = tmp_path / "s1.mp4"

    await video_service.render_scene_video(
        image_path=str(clip), audio_path=str(voice), output_path=str(out),
        duration=14.0, resolution="720p", fps=25, transition="dip_to_black",
    )

    cmd = captured_ffmpeg[-1]
    loop_idx = cmd.index("-stream_loop")
    assert cmd[loop_idx + 1] == "-1" and cmd[loop_idx + 3] == str(clip), "clip phải được lặp cho đủ độ dài giọng"
    assert _has_pair(cmd, "-t", "14.0")
    assert _has_pair(cmd, "-ar", "48000") and _has_pair(cmd, "-ac", "2")
    assert "fps=25" in cmd[cmd.index("-filter_complex") + 1]
    assert cmd[-1] == str(out)


@pytest.mark.asyncio
async def test_video_clip_render_refuses_same_input_and_output(tmp_path, captured_ffmpeg):
    clip = tmp_path / "s1.mp4"
    clip.write_bytes(MP4_BYTES)
    with pytest.raises(ValueError):
        await video_service.render_scene_video(image_path=str(clip), audio_path=None, output_path=str(clip), duration=5.0)
    assert not captured_ffmpeg


@pytest.mark.asyncio
async def test_image_render_uses_48k_stereo_audio(tmp_path, captured_ffmpeg):
    img = tmp_path / "s1.jpg"
    _write_jpg(img)
    await video_service.render_scene_video(image_path=str(img), audio_path=None, output_path=str(tmp_path / "s1.mp4"),
                                           duration=4.0, resolution="720p")
    cmd = captured_ffmpeg[-1]
    assert _has_pair(cmd, "-ar", "48000") and _has_pair(cmd, "-ac", "2")
    assert video_service.SILENT_AUDIO_SRC in cmd
    assert "anullsrc=r=44100:cl=stereo" not in cmd


def test_video_service_has_logger():
    assert isinstance(video_service.logger, logging.Logger)


@pytest.mark.asyncio
async def test_assemble_logs_xfade_failure_and_falls_back_to_concat(tmp_path, captured_ffmpeg, monkeypatch, caplog):
    """Trước đây thiếu logger nên lỗi xfade làm cả lần dựng chết vì NameError."""
    async def broken_xfade(**kwargs):
        raise RuntimeError("xfade boom")

    monkeypatch.setattr(video_service, "build_xfade_video", broken_xfade)
    segs, srts = [], []
    for i in range(2):
        seg = tmp_path / f"seg{i}.mp4"
        seg.write_bytes(MP4_BYTES)
        srt = tmp_path / f"seg{i}.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        segs.append(str(seg))
        srts.append({"srt_path": str(srt), "duration": 3.0})

    with caplog.at_level(logging.WARNING, logger="story_studio.video_service"):
        res = await video_service.assemble_full_video(
            scene_video_paths=segs, scene_srt_infos=srts,
            output_video_path=str(tmp_path / "renders" / "final.mp4"),
            transition="crossfade", hardsub=False,
        )

    assert Path(res["video_path"]).exists()
    assert "xfade boom" in caplog.text
    assert any("concat" in c for c in captured_ffmpeg[0]), "phải chuyển sang ghép concat"


@pytest.mark.asyncio
async def test_assemble_succeeds_when_final_duration_cannot_be_measured(tmp_path, captured_ffmpeg, monkeypatch):
    """Ghép xong rồi mà ffprobe không đo được: vẫn là thành công, thời lượng ước bằng tổng các cảnh."""
    from services.tts_service import MediaDurationError

    def cannot_measure(path):
        raise MediaDurationError("Không đo được thời lượng final.mp4: ffprobe giả lỗi")

    monkeypatch.setattr(video_service, "get_audio_duration", cannot_measure)
    segs, srts = [], []
    for i in range(2):
        seg = tmp_path / f"seg{i}.mp4"
        seg.write_bytes(MP4_BYTES)
        srt = tmp_path / f"seg{i}.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        segs.append(str(seg))
        srts.append({"srt_path": str(srt), "duration": 2.5})
    res = await video_service.assemble_full_video(
        scene_video_paths=segs, scene_srt_infos=srts,
        output_video_path=str(tmp_path / "renders" / "final.mp4"), transition="cut", hardsub=False,
    )
    assert Path(res["video_path"]).exists()
    assert res["duration"] == 5.0


def test_vieneu_text_is_split_into_sentences_with_pauses():
    from services.tts_service import ELLIPSIS_PAUSE_S, SENTENCE_PAUSE_S, split_for_pauses
    pieces = split_for_pauses("Hai giờ sáng… chiếc xe dừng lại. Cô chạy lên cầu thang! Không ai biết.")
    assert pieces == [("Hai giờ sáng…", ELLIPSIS_PAUSE_S), ("chiếc xe dừng lại.", SENTENCE_PAUSE_S),
                      ("Cô chạy lên cầu thang!", SENTENCE_PAUSE_S), ("Không ai biết.", 0.0)]
    assert split_for_pauses("Một câu không dấu chấm") == [("Một câu không dấu chấm", 0.0)]


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="cần ffmpeg")
async def test_vieneu_reads_sentence_by_sentence_slower_with_pauses(tmp_path, monkeypatch):
    """Chủ dự án 26/10/2026: giọng VieNeu đọc nhanh, trôi tuồn tuột. Mỗi câu gửi riêng với tốc độ config.VIENEU_SPEED,
    ghép lại có khoảng lặng; file tạm từng câu được dọn."""
    import asyncio as _asyncio
    import subprocess as _subprocess
    import config
    from services import tts_service

    one_second = tmp_path / "cau.mp3"
    await _asyncio.to_thread(_subprocess.run, ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                             "sine=frequency=300:duration=1", "-ar", "48000", "-ac", "1", str(one_second)], check=True)
    sent = []

    class FakeResponse:
        status_code = 200
        content = one_second.read_bytes()
        text = ""

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json):
            sent.append(json)
            return FakeResponse()

    async def server_ready():
        return True

    import httpx
    monkeypatch.setattr(tts_service, "ensure_vieneu_server", server_ready)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    out = tmp_path / "scene.mp3"
    res = await tts_service.generate_speech("Hai giờ sáng… chiếc xe dừng lại. Không ai biết.", voice="vieneu-MaiAnh",
                                            output_audio_path=str(out))

    assert [j["input"] for j in sent] == ["Hai giờ sáng…", "chiếc xe dừng lại.", "Không ai biết."]
    assert all(j["speed"] == config.VIENEU_SPEED for j in sent)
    expected = 3 * 1.0 + tts_service.ELLIPSIS_PAUSE_S + tts_service.SENTENCE_PAUSE_S
    assert abs(res["duration"] - expected) < 0.3, res["duration"]
    assert not res["fallback_used"]
    names = sorted(p.name for p in tmp_path.iterdir() if p.suffix in (".mp3", ".srt") or p.name.startswith(".cau_"))
    assert names == ["cau.mp3", "scene.mp3", "scene.srt"]           # thư mục tạm từng câu đã dọn
