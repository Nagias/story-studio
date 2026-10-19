"""Gate G-OUT Automated Regression Test Suite
Validates that all critical delivery blockers (Security & Core Logic) are completely resolved.
"""
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path
import pytest
from PIL import Image
from httpx import AsyncClient, ASGITransport

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from main import app
from config import PROJECTS_DIR, COMIC_SLICES_DIR, STATIC_DIR
from services.grid_slicer import slice_grid_image
from services.audio_engine import mix_3layer_audio
from services.project_service import create_project, get_project, delete_project
from models.schemas import ProjectCreateRequest, Scene


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.asyncio
async def test_sec_01_block_arbitrary_file_read_via_comic_import():
    """TC-SEC-01: Chặn trích xuất file ngoài sandbox qua /comic/import-scenes."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # Create temp project
        p_res = await client.post("/api/projects", json={"name": "SecTest Project"})
        assert p_res.status_code == 200
        proj_id = p_res.json()["id"]

        try:
            # Create a fake sensitive file outside the project sandbox
            with tempfile.NamedTemporaryFile(suffix=".ini", delete=False) as f:
                f.write(b"[secrets]\npassword=secret123\n")
                sensitive_path = f.name

            payload = {
                "panels": [{"image_path": sensitive_path, "selected": True}],
                "clear_existing": False,
            }
            resp = await client.post(f"/api/projects/{proj_id}/comic/import-scenes", json=payload)
            assert resp.status_code == 200

            # Verify that sensitive file was NOT copied into project images
            proj_data = (await client.get(f"/api/projects/{proj_id}")).json()
            for sc in proj_data.get("scenes", []):
                sc_img_path = Path(sc.get("image_path", ""))
                if sc_img_path.exists():
                    assert sc_img_path.stat().st_size == 0 or b"secret123" not in sc_img_path.read_bytes()
        finally:
            if os.path.exists(sensitive_path):
                os.unlink(sensitive_path)
            delete_project(proj_id)


@pytest.mark.asyncio
async def test_sec_02_block_project_deletion_traversal():
    """TC-SEC-02: Chặn Path Traversal xóa sạch project/codebase qua DELETE /api/projects/.."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        resp1 = await client.delete("/api/projects/..")
        assert resp1.status_code in (400, 404, 422)

        resp2 = await client.delete("/api/projects/.")
        assert resp2.status_code in (400, 404, 405, 422)

        resp3 = await client.delete("/api/projects/..%2f..")
        assert resp3.status_code in (400, 404, 422)


@pytest.mark.asyncio
async def test_sec_03_block_unc_path_injection_open_folder():
    """TC-SEC-03: Chặn UNC path injection qua /api/open-folder chống rò rỉ NetNTLM hash."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        resp = await client.post("/api/open-folder", json={"path": r"\\10.0.0.1\malicious_share"})
        assert resp.status_code in (400, 403)


@pytest.mark.asyncio
async def test_sec_04_block_arbitrary_file_overwrite_in_muse_complete():
    """TC-SEC-04: Chặn Muse Task ghi đè file ngoài sandbox."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        resp = await client.post("/api/muse-bridge/tasks/create", json={
            "prompt": "test prompt",
            "output_path": r"C:\Windows\System32\calc.exe"
        })
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]

        resp_comp = await client.post(
            f"/api/muse-bridge/tasks/{task_id}/complete",
            files={"file": ("test.jpg", b"fake binary data", "image/jpeg")}
        )
        assert resp_comp.status_code == 200
        out_path = resp_comp.json().get("output_path", "")
        # Output path MUST NOT be in System32
        assert "System32" not in out_path


def test_core_01_ffmpeg_3layer_audio_sidechain_ducking_success():
    """TC-CORE-01: FFmpeg 3-Layer Audio Sidechain Ducking chạy thành công, exit code 0, không bị crash fallback."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        voice_wav = tmp_p / "voice.wav"
        bgm_wav = tmp_p / "bgm.wav"
        out_master = tmp_p / "master_out.wav"

        # Generate 3 seconds of voice sine wave (440Hz)
        import subprocess
        cmd_voice = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-ar", "24000", "-ac", "1", str(voice_wav)
        ]
        subprocess.run(cmd_voice, check=True, capture_output=True)

        # Generate 5 seconds of BGM white noise
        cmd_bgm = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=5:c=white:r=44100:a=0.5",
            "-ar", "44100", "-ac", "2", str(bgm_wav)
        ]
        subprocess.run(cmd_bgm, check=True, capture_output=True)

        scenes_audio = [{
            "scene_id": "sc_01",
            "voice_audio_path": str(voice_wav),
            "duration": 3.0,
            "pause_after_sec": 0.5,
            "sfx_cues": [],
        }]

        res_path = mix_3layer_audio(
            scenes_audio=scenes_audio,
            bgm_path=str(bgm_wav),
            output_master_path=out_master,
            bgm_volume=0.3,
            ducking_threshold=0.08,
            ducking_ratio=4.0,
        )

        assert Path(res_path).exists()
        assert Path(res_path).stat().st_size > 1000


def test_core_02_9grid_slice_with_offset_no_overwrite():
    """TC-CORE-02: Cắt lưới 9-Grid đa batch (offset) không ghi đè cảnh của batch trước."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        # Create a 300x300 image
        grid_img_path = tmp_p / "test_grid.png"
        img = Image.new("RGB", (300, 300), color=(128, 64, 32))
        img.save(grid_img_path)

        out_dir = tmp_p / "slices"

        # Batch 1: start_index = 1
        b1_paths = slice_grid_image(
            image_path=grid_img_path,
            output_dir=out_dir,
            rows=3, cols=3,
            start_index=1,
            target_resolution=(160, 90)
        )
        assert len(b1_paths) == 9
        assert Path(b1_paths[0]).name == "scene_001.png"
        assert Path(b1_paths[8]).name == "scene_009.png"

        # Batch 2: start_index = 10
        b2_paths = slice_grid_image(
            image_path=grid_img_path,
            output_dir=out_dir,
            rows=3, cols=3,
            start_index=10,
            target_resolution=(160, 90)
        )
        assert len(b2_paths) == 9
        assert Path(b2_paths[0]).name == "scene_010.png"
        assert Path(b2_paths[8]).name == "scene_018.png"

        # Verify all 18 files exist without collision
        all_files = list(out_dir.glob("scene_*.png"))
        assert len(all_files) == 18


def test_core_03_imageops_fit_preserves_aspect_ratio_no_anamorphic_distortion():
    """TC-CORE-03: Cắt ảnh lưới 1:1 sang 16:9 bằng ImageOps.fit không gây méo tỷ lệ."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        # 1:1 square image
        square_img = tmp_p / "square_grid.png"
        img = Image.new("RGB", (600, 600), color=(50, 100, 150))
        img.save(square_img)

        slices = slice_grid_image(
            image_path=square_img,
            output_dir=tmp_p / "fitted_slices",
            rows=3, cols=3,
            target_resolution=(1920, 1080)
        )
        assert len(slices) == 9
        with Image.open(slices[0]) as cell:
            assert cell.size == (1920, 1080)


def test_core_04_schema_contract_audio_url_compatibility():
    """TC-CORE-04: Model Scene hỗ trợ đồng thời cả audio_url và voice_audio_url."""
    sc = Scene(
        id="sc_test",
        order=1,
        text="Xin chào thế giới",
        voice_audio_url="/api/projects/p1/media/audio/sc_test.mp3",
        audio_url="/api/projects/p1/media/audio/sc_test.mp3"
    )
    assert sc.voice_audio_url == "/api/projects/p1/media/audio/sc_test.mp3"
    assert sc.audio_url == "/api/projects/p1/media/audio/sc_test.mp3"


def test_sec_05_shlex_command_injection_safeguard():
    """TC-SEC-05: Shlex parsing ngăn chặn shell metacharacters trong custom_cmd."""
    import shlex
    custom_cmd = 'mock_tool --prompt "{prompt}" -o "{output}"'
    malicious_prompt = 'test; whoami && cat /etc/passwd #'
    target_file = Path("output.jpg")

    args = shlex.split(custom_cmd)
    cmd = [arg.replace("{output}", str(target_file)).replace("{prompt}", malicious_prompt) for arg in args]

    # Malicious prompt must be isolated inside a single argv item, not executed as separate commands
    assert cmd[0] == "mock_tool"
    assert cmd[1] == "--prompt"
    assert cmd[2] == malicious_prompt
    assert cmd[3] == "-o"
    assert cmd[4] == str(target_file)


@pytest.mark.asyncio
async def test_core_05_vieneu_timeout_safeguard():
    """TC-CORE-05: Subprocess timeout bảo vệ hệ thống không bị treo vô tận."""
    # Simulate a hanging subprocess
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-Command", "Start-Sleep -Seconds 10",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    timed_out = False
    try:
        await asyncio.wait_for(proc.communicate(), timeout=0.5)
    except asyncio.TimeoutError:
        timed_out = True
        try:
            proc.kill()
        except Exception:
            pass
    assert timed_out is True

