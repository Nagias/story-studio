"""
Kiểm thử phía Fleet Runner không cần trình duyệt:
- Chọn tài khoản đúng loại, không giữ chỗ trùng.
- Thời lượng video 5s/10s.
- Kiểm tra file kết quả: loại avatar mascot (video vuông 480x480 ~5s), ảnh quá nhỏ, ảnh trùng ảnh tham chiếu.
- Khóa chạy 1 bản duy nhất.
"""
import io
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from runners import single_instance  # noqa: E402
from runners.muse_fleet_runner import (  # noqa: E402
    FleetAccount,
    MuseFleetRunner,
    average_hash,
    clamp_video_duration,
    max_video_seconds,
    to_jpeg_bytes,
    validate_image_bytes,
    validate_video_file,
)

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def make_runner(tmp_path) -> MuseFleetRunner:
    runner = MuseFleetRunner.__new__(MuseFleetRunner)
    runner.accounts = {}
    for aid, kind in (("muse_acc_img_01", "image"), ("muse_acc_img_02", "image"),
                      ("muse_acc_vid_01", "video"), ("muse_acc_vid_02", "video")):
        acc = FleetAccount({"account_id": aid, "type": kind, "profile_dir": f"chrome_profiles/{aid}",
                            "is_active_for_image": aid == "muse_acc_img_01", "is_active_for_video": aid == "muse_acc_vid_01"})
        runner.accounts[aid] = acc
    return runner


def test_select_account_never_crosses_kind(tmp_path):
    runner = make_runner(tmp_path)
    assert runner.select_available_account("text-to-image", require_login=False).type == "image"
    assert runner.select_available_account("image-to-video", require_login=False).type == "video"
    # Active được ưu tiên
    assert runner.select_available_account("image-to-video", require_login=False).account_id == "muse_acc_vid_01"
    # Hết tài khoản video rảnh -> None, không lấy tài khoản ảnh
    for aid in ("muse_acc_vid_01", "muse_acc_vid_02"):
        runner.accounts[aid].status = "busy"
    assert runner.select_available_account("image-to-video", require_login=False) is None


def test_reserve_does_not_hand_out_same_account_twice(tmp_path, monkeypatch):
    runner = make_runner(tmp_path)
    monkeypatch.setattr(FleetAccount, "is_logged_in", lambda self: True)
    first = runner._reserve_account(["video"])
    second = runner._reserve_account(["video"])
    assert first and second and first.account_id != second.account_id
    assert runner._reserve_account(["video"]) is None
    runner._release_account(first)
    assert runner._reserve_account(["video"]).account_id == first.account_id


def test_needs_login_account_is_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(FleetAccount, "is_logged_in", lambda self: True)
    acc = make_runner(tmp_path).accounts["muse_acc_img_01"]
    acc.status = "needs_login"
    assert not acc.is_ready()


@pytest.mark.parametrize("value,expected", [(3, 5), (5, 5), (7, 5), (8, 10), (10, 10), (19.5, 10), (None, 5), ("abc", 5)])
def test_video_duration_is_5_or_10(value, expected):
    assert clamp_video_duration(value) == expected


def _jpeg(w, h, color=(10, 120, 200)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (w, h), color)
    for x in range(0, w, 40):  # hoạ tiết để average hash có ý nghĩa
        for y in range(0, h // 2):
            img.putpixel((x, y), (255, 255, 255))
    img.save(buf, "JPEG")
    return buf.getvalue()


def test_validate_image_rejects_small_and_reference_copy():
    ok, info = validate_image_bytes(_jpeg(300, 200), [])
    assert not ok and "nhỏ" in info
    good = _jpeg(1920, 1080)
    assert validate_image_bytes(good, [])[0]
    ref_hash = average_hash(Image.open(io.BytesIO(good)))
    ok, info = validate_image_bytes(good, [ref_hash])
    assert not ok and "tham chiếu" in info
    assert not validate_image_bytes(b"not an image", [])[0]


def _make_video(path: Path, w: int, h: int, seconds: float):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=24",
         "-t", str(seconds), "-pix_fmt", "yuv420p", str(path)],
        check=True, timeout=60,
    )


@pytest.mark.skipif(not HAS_FFMPEG, reason="cần ffmpeg/ffprobe")
def test_validate_video_rejects_mascot_like_clip(tmp_path):
    mascot = tmp_path / "mascot.mp4"
    _make_video(mascot, 480, 480, 5.04)  # giống avatar mascot của Muse
    ok, info = validate_video_file(mascot)
    assert not ok and "vuông" in info

    short = tmp_path / "short.mp4"
    _make_video(short, 1280, 720, 1)
    assert not validate_video_file(short)[0]

    real = tmp_path / "real.mp4"
    _make_video(real, 1280, 720, 5)
    ok, info = validate_video_file(real)
    assert ok, info


@pytest.mark.skipif(not HAS_FFMPEG, reason="cần ffmpeg/ffprobe")
def test_validate_video_rejects_old_long_clip_from_reused_chat(tmp_path):
    # 21/10/2026: Muse không có nút New side chat, runner nhận nhầm video cũ 21s trong đoạn chat cho yêu cầu 5s
    old = tmp_path / "old.mp4"
    _make_video(old, 1280, 720, 21)
    ok, info = validate_video_file(old, max_video_seconds(5))
    assert not ok and "video cũ" in info
    assert validate_video_file(old, max_video_seconds(10))[0] is False

    ten = tmp_path / "ten.mp4"
    _make_video(ten, 1280, 720, 10)
    assert validate_video_file(ten, max_video_seconds(5))[0]   # Muse đôi khi trả 10s cho yêu cầu 5s
    assert validate_video_file(ten, max_video_seconds(10))[0]


def test_validate_video_rejects_non_video(tmp_path):
    p = tmp_path / "fake.mp4"
    p.write_bytes(_jpeg(1280, 720))
    assert not validate_video_file(p)[0]


def test_single_instance_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(single_instance, "LOCK_FILE", tmp_path / "runner.lock")
    monkeypatch.setattr(single_instance, "_held_fd", None)
    assert not single_instance.is_runner_running()
    child = subprocess.Popen(
        [sys.executable, "-c",
         "import sys, time; sys.path.insert(0, sys.argv[1]); import single_instance as s; "
         "s.LOCK_FILE = __import__('pathlib').Path(sys.argv[2]); print(s.acquire_runner_lock(), flush=True); time.sleep(30)",
         str(BACKEND_DIR / "runners"), str(tmp_path / "runner.lock")],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout.readline().strip() == "True"
        assert single_instance.is_runner_running()
        assert not single_instance.acquire_runner_lock()
    finally:
        child.kill()
        child.wait()
    # venv launcher trên Windows có 1 process con thật, process đó thoát chậm hơn một chút
    deadline = time.time() + 5
    while single_instance.is_runner_running() and time.time() < deadline:
        time.sleep(0.2)
    assert not single_instance.is_runner_running()
    assert single_instance.acquire_runner_lock()
    single_instance.release_runner_lock()


def test_webp_result_is_converted_to_real_jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (2048, 1152), (200, 120, 40)).save(buf, "WEBP")
    out = to_jpeg_bytes(buf.getvalue())
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "JPEG" and img.size == (2048, 1152)
    jpg = _jpeg(1920, 1080)
    assert to_jpeg_bytes(jpg) == jpg


def test_off_ratio_image_is_center_cropped_to_16_9():
    buf = io.BytesIO()
    Image.new("RGB", (1920, 1280), (90, 30, 30)).save(buf, "WEBP")  # Muse trả 3:2
    out = to_jpeg_bytes(buf.getvalue(), 16 / 9)
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "JPEG" and img.size == (1920, 1080)
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), (90, 30, 30)).save(buf, "PNG")  # 1:1
    with Image.open(io.BytesIO(to_jpeg_bytes(buf.getvalue(), 16 / 9))) as img:
        assert img.size == (1024, 576)
