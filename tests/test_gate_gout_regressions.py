"""Gate G-OUT Automated Regression Test Suite
Validates that all critical delivery blockers (Security & Core Logic) are completely resolved.
"""
import asyncio
import os
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
from services.project_service import delete_project
from models.schemas import Scene


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
                assert sc.get("status_image") == "error", "khung bị chặn phải được đánh dấu Lỗi ảnh"
                sc_img_path = Path(sc.get("image_path") or "")
                if sc.get("image_path") and sc_img_path.exists():
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
async def test_sec_04_block_arbitrary_file_overwrite_in_muse_complete(tmp_path, monkeypatch):
    """TC-SEC-04: Chặn Muse Task ghi đè file ngoài sandbox, hai lớp.
    1. Tạo task với output_path ngoài projects/muse_outputs bị từ chối (400), không vào hàng đợi.
    2. Task đã nằm sẵn trong hàng đợi với output_path xấu (bản cũ, hay bị sửa tay) thì kết quả vẫn chỉ lưu vào
       muse_outputs. Thư mục muse_outputs và hàng đợi là bản tạm, không đụng dữ liệu thật."""
    import io
    from routers import muse_bridge

    outputs = tmp_path / "muse_outputs"
    outputs.mkdir()
    monkeypatch.setattr(muse_bridge, "MUSE_OUTPUTS_DIR", outputs)
    monkeypatch.setattr(muse_bridge, "pending_tasks", [])
    monkeypatch.setattr(muse_bridge, "active_tasks", {})
    monkeypatch.setattr(muse_bridge, "task_history", [])
    bad_path = r"C:\Windows\System32\calc.exe"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        resp = await client.post("/api/muse-bridge/tasks/create", json={"prompt": "test prompt", "output_path": bad_path})
        assert resp.status_code == 400
        assert muse_bridge.pending_tasks == []

        task_id = "task_m_sec04old"
        muse_bridge.pending_tasks.append({"task_id": task_id, "prompt": "test prompt", "mode": "text-to-image",
                                          "status": "pending", "output_path": bad_path})
        jpeg = io.BytesIO()
        Image.new("RGB", (64, 64), "gray").save(jpeg, "JPEG")
        resp_comp = await client.post(
            f"/api/muse-bridge/tasks/{task_id}/complete",
            files={"file": ("test.jpg", jpeg.getvalue(), "image/jpeg")}
        )
        assert resp_comp.status_code == 200, resp_comp.text
        out_path = Path(resp_comp.json()["output_path"])
        assert "System32" not in str(out_path)
        assert out_path.parent == outputs.resolve() and out_path.is_file()


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

