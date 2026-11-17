import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from starlette.testclient import TestClient
from main import app
from routers import muse_bridge
from routers.muse_bridge import (
    is_local_fleet_runner_active,
    is_muse_worker_online,
)


def test_fleet_accounts_loaded_with_capabilities_of_their_type():
    """API trả về các tài khoản Fleet, mỗi tài khoản có khả năng đúng với loại của nó.

    Số tài khoản và tên không cố định: chủ dự án 02/11/2026 (CLAUDE.md mục 1.2 câu 22) "có bao nhiêu dùng bấy nhiêu".
    Test cũ đòi đúng 5 ảnh + 5 video và đoán loại theo tên (img/vid), nên lỗi khi chủ dự án đổi muse_acc_vid_01, 02 thành
    tài khoản ảnh."""
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    resp = client.get("/api/muse-bridge/accounts")
    assert resp.status_code == 200
    accounts = [a for a in resp.json()["accounts"] if a["account_id"].startswith("muse_acc_")]
    assert accounts, "Không có tài khoản Fleet nào"
    for acc in accounts:   # "both": nhận cả ảnh lẫn video (chủ dự án 17/11/2026)
        assert acc.get("type") in ("image", "video", "both"), acc["account_id"]
        if acc["type"] in ("image", "both"):
            assert "text-to-image" in acc["capabilities"], acc["account_id"]
        if acc["type"] in ("video", "both"):
            assert "image-to-video" in acc["capabilities"], acc["account_id"]


def test_image_payload_separation():
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    resp = client.post(
        "/api/muse-bridge/tasks/create",
        json={
            "mode": "text-to-image",
            "prompt": "Samurai warrior standing in cherry blossoms, detailed armor",
            "character_anchor": "Kenshin, red hair, cross scar on left cheek",
            "aspect_ratio": "16:9",
            "parameters": {
                "style_preset": "manga_murata_battle",
                "resolution": "2K",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    task = data["task"]

    assert task["mode"] == "text-to-image"
    assert task["aspect_ratio"] == "16:9"
    assert task["character_anchor"] == "Kenshin, red hair, cross scar on left cheek"
    assert "16:9" in task["parameters"]["aspect_ratio"]
    assert task["parameters"]["character_anchor"] == "Kenshin, red hair, cross scar on left cheek"
    assert task["parameters"]["resolution"] == "2K"


def test_video_payload_separation():
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    resp = client.post(
        "/api/muse-bridge/tasks/create",
        json={
            "mode": "image-to-video",
            "prompt": "Warrior unsheathing katana with lightning sparks",
            "input_image_url": "http://127.0.0.1:8000/static/demo_images/scene_1.jpg",
            "camera_motion": "cinematic fast punch zoom, dynamic shake",
            "duration": 5,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    task = data["task"]

    assert task["mode"] == "image-to-video"
    assert task["duration"] == 5
    assert task["camera_motion"] == "cinematic fast punch zoom, dynamic shake"
    assert task["action_prompt"] == "Warrior unsheathing katana with lightning sparks"
    assert task["input_image_url"] == "http://127.0.0.1:8000/static/demo_images/scene_1.jpg"
    assert task["parameters"]["duration"] == 5
    assert task["parameters"]["camera_motion"] == "cinematic fast punch zoom, dynamic shake"
    assert task["parameters"]["action_cues"] == "Warrior unsheathing katana with lightning sparks"


def test_local_fleet_runner_detection_and_task_polling(monkeypatch):
    # Tài khoản ảnh giả: không phụ thuộc file tài khoản thật trên máy (17/11/2026 chủ dự án gỡ muse_acc_img_01)
    monkeypatch.setattr(muse_bridge, "muse_accounts", [
        {"account_id": "muse_acc_img_01", "type": "image", "capabilities": ["text-to-image", "image-upscale-2k"],
         "profile_dir": "chrome_profiles/muse_acc_img_01", "is_active_for_image": True}])
    monkeypatch.setattr(muse_bridge, "is_account_profile_installed", lambda acc: True)
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

    # Register local fleet runner worker
    resp_reg = client.post(
        "/api/muse-bridge/workers/register",
        json={
            "worker_id": "fleet-runner-local_muse_acc_img_01",
            "account_id": "muse_acc_img_01",
            "tailscale_ip": "127.0.0.1",
            "hostname": "localhost",
            "capabilities": ["text-to-image", "image-upscale-2k"],
        },
    )
    assert resp_reg.status_code == 200

    # Verify local fleet runner is active
    assert is_local_fleet_runner_active() is True
    assert is_muse_worker_online("muse_acc_img_01") is True

    # Ensure there is an image task for the image account to poll
    client.post(
        "/api/muse-bridge/tasks/create",
        json={"mode": "text-to-image", "prompt": "Samurai meditating under cherry blossom tree"},
    )

    # Poll task with fleet account
    resp_poll = client.get("/api/muse-bridge/tasks/poll?account_id=muse_acc_img_01&timeout=1")
    assert resp_poll.status_code == 200
    data = resp_poll.json()
    assert data["task"] is not None
    assert data["task"]["mode"] == "text-to-image"
