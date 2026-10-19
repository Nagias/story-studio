"""
Unit and Integration Tests for Muse Fleet Runner (Cơ chế B)
Tests:
- 10-account configuration loading & structure (5 image, 5 video)
- SingletonLock & SingletonCookie cleanup on Windows
- Image prompt vs Video prompt separation
- Account LRU / Round-Robin selection and cooldowns
- Concurrency limit constraint (N <= 2 slots)
"""

import sys
import os
import json
import time
import shutil
import asyncio
from pathlib import Path

import pytest

# Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Path setup
TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from runners.muse_fleet_runner import (
    MusePromptFormatter,
    clean_singleton_locks,
    FleetAccount,
    MuseFleetRunner,
    ACCOUNTS_CONFIG_PATH,
)


def test_accounts_config_structure():
    """Kiểm tra cấu hình 10 tài khoản trong muse_fleet_accounts.json."""
    assert ACCOUNTS_CONFIG_PATH.exists(), f"Không tìm thấy file: {ACCOUNTS_CONFIG_PATH}"
    with open(ACCOUNTS_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "accounts" in data
    accounts = data["accounts"]
    assert len(accounts) == 10, f"Mong đợi 10 accounts, nhưng có {len(accounts)}"

    image_accounts = [a for a in accounts if a["type"] == "image"]
    video_accounts = [a for a in accounts if a["type"] == "video"]

    assert len(image_accounts) == 5, f"Mong đợi 5 accounts Image, có {len(image_accounts)}"
    assert len(video_accounts) == 5, f"Mong đợi 5 accounts Video, có {len(video_accounts)}"

    # Kiểm tra các trường bắt buộc của mỗi account
    for acc in accounts:
        assert "account_id" in acc
        assert "label" in acc
        assert "type" in acc
        assert "profile_dir" in acc
        assert "status" in acc
        assert "cooldown_until" in acc
        assert acc["account_id"].startswith("muse_acc_")
        assert "chrome_profiles" in acc["profile_dir"]

    # Kiểm tra giới hạn Concurrency
    concurrency = data.get("concurrency_limit", 2)
    assert 1 <= concurrency <= 2, f"Concurrency limit phải từ 1 đến 2, nhưng là {concurrency}"


def test_singleton_lock_cleanup(tmp_path):
    """Kiểm tra tính năng dọn dẹp SingletonLock, SingletonCookie trên Windows."""
    mock_profile = tmp_path / "chrome_profile_test"
    mock_profile.mkdir(parents=True, exist_ok=True)

    lock_files = [
        "SingletonLock",
        "SingletonCookie",
        "SingletonSocket",
        "lockfile"
    ]
    for name in lock_files:
        (mock_profile / name).write_text("dummy lock content", encoding="utf-8")

    # Xác nhận các file lock đã được tạo
    for name in lock_files:
        assert (mock_profile / name).exists()

    # Thực hiện dọn dẹp
    clean_singleton_locks(mock_profile)

    # Xác nhận toàn bộ lock files đã bị xóa
    for name in lock_files:
        assert not (mock_profile / name).exists(), f"File {name} chưa được dọn dẹp!"


def test_prompt_formatter_image():
    """Kiểm tra phân tách cấu trúc Image Prompt."""
    task = {
        "prompt": "Cyberpunk detective inspecting evidence under torrential neon rain",
        "negative_prompt": "blurry, low resolution, extra limbs, watermark",
        "parameters": {
            "style_preset": "manga_murata_battle",
            "character_anchor": "detective_k",
            "lighting": "cyan and magenta volumetric neon, high contrast shadows",
            "aspect_ratio": "16:9",
        }
    }

    formatted = MusePromptFormatter.format_image_prompt(task)

    assert "Character Anchor: detective_k" in formatted
    assert "Style: manga_murata_battle" in formatted
    assert "Scene Details: Cyberpunk detective inspecting evidence" in formatted
    assert "Atmosphere: cyan and magenta volumetric neon" in formatted
    assert "16:9 widescreen" in formatted
    assert "Avoid: blurry, low resolution" in formatted


def test_prompt_formatter_video():
    """Kiểm tra phân tách cấu trúc Video Prompt."""
    task = {
        "prompt": "Detective turns his head slowly towards camera as lightning strikes",
        "parameters": {
            "camera_motion": "slow dynamic pan left, subtle push in",
            "action_cues": "head turn, rain dripping on coat collar",
            "pacing": "cinematic 24fps smooth pacing",
            "duration": 5,
        },
        "input_image_url": "http://127.0.0.1:8000/static/demo_images/scene_1.jpg"
    }

    formatted = MusePromptFormatter.format_video_prompt(task, has_input_image=True)

    assert "[Duration: 5s]" in formatted
    assert "Action: Detective turns his head slowly" in formatted
    assert "Camera: slow dynamic pan left" in formatted
    assert "Dynamics: head turn, rain dripping" in formatted
    assert "Pacing: cinematic 24fps smooth pacing" in formatted
    assert "[Mode: Image-to-Video]" in formatted


def test_account_lru_and_cooldown_selection():
    """Kiểm tra lựa chọn tài khoản theo Round-Robin / LRU và kiểm soát Cooldown."""
    runner = MuseFleetRunner()
    for acc in runner.accounts.values():
        acc.status = "ready"

    # Lựa chọn tài khoản Image
    img_acc_1 = runner.select_available_account("text-to-image", require_login=False)
    assert img_acc_1 is not None
    assert img_acc_1.type == "image"

    # Giả lập account 1 đang bận (tài khoản active được ưu tiên, nên phải bận thì mới chọn tài khoản khác)
    img_acc_1.last_used = time.time()
    img_acc_1.status = "busy"

    # Lựa chọn tài khoản tiếp theo (phải là tài khoản khác)
    img_acc_2 = runner.select_available_account("text-to-image", require_login=False)
    assert img_acc_2 is not None
    assert img_acc_2.account_id != img_acc_1.account_id

    # Đặt cooldown cho tài khoản 2
    img_acc_2.set_cooldown(60.0)
    assert not img_acc_2.is_ready()

    # Lựa chọn lại, không được chọn tài khoản 2
    img_acc_3 = runner.select_available_account("text-to-image", require_login=False)
    assert img_acc_3 is not None
    assert img_acc_3.account_id != img_acc_2.account_id

    # Lựa chọn tài khoản Video
    vid_acc = runner.select_available_account("image-to-video", require_login=False)
    assert vid_acc is not None
    assert vid_acc.type == "video"
