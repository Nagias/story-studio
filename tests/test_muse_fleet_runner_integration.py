import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from starlette.testclient import TestClient
from main import app
from routers.muse_bridge import (
    load_muse_accounts,
    muse_accounts,
    get_enriched_accounts,
    get_active_account,
    assign_task_account,
    is_local_fleet_runner_active,
    is_muse_worker_online,
    pending_tasks,
    active_tasks,
)


def test_fleet_runner_10_accounts_loaded():
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    resp = client.get("/api/muse-bridge/accounts")
    assert resp.status_code == 200
    data = resp.json()
    accounts = data["accounts"]

    # Must contain the 10 fleet accounts
    fleet_ids = [a["account_id"] for a in accounts if a["account_id"].startswith("muse_acc_img_") or a["account_id"].startswith("muse_acc_vid_")]
    assert len(fleet_ids) >= 10, f"Expected 10 fleet accounts, got {len(fleet_ids)}"

    img_fleet = [aid for aid in fleet_ids if "img" in aid]
    vid_fleet = [aid for aid in fleet_ids if "vid" in aid]
    assert len(img_fleet) == 5, f"Expected 5 image fleet accounts, got {len(img_fleet)}"
    assert len(vid_fleet) == 5, f"Expected 5 video fleet accounts, got {len(vid_fleet)}"

    # Check capabilities
    for aid in img_fleet:
        acc = next(a for a in accounts if a["account_id"] == aid)
        assert "text-to-image" in acc["capabilities"]

    for aid in vid_fleet:
        acc = next(a for a in accounts if a["account_id"] == aid)
        assert "image-to-video" in acc["capabilities"]


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


def test_local_fleet_runner_detection_and_task_polling():
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
