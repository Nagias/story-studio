"""Chế độ giao việc nhiều bước của Fleet Runner (runners/muse_agent_turn.py): hàm thuần, không bật trình duyệt."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from runners.muse_agent_turn import (AGENT_STABLE_SEC, STREAMING_JS, budget_warnings, pick_final_video,  # noqa: E402
                                     turn_done)
from runners.muse_fleet_runner import MuseFleetRunner, _muse_reply_part  # noqa: E402

TOKEN = "XONG-ab12cd34"
PROMPT = "Làm video cho một cảnh...\nDòng cuối cùng của tin nhắn cuối cùng ghi đúng nguyên văn: " + TOKEN


def said(text_now: str, text_before: str = "") -> str:
    return _muse_reply_part(text_before, text_now, PROMPT)


def test_token_inside_prompt_is_not_done():
    assert not turn_done(said("You:\n" + PROMPT), TOKEN)
    assert not turn_done(said("You:\n" + PROMPT + "\n👍"), TOKEN)


def test_done_only_when_muse_text_ends_with_token():
    assert turn_done(said("You:\n" + PROMPT + "\nĐã xong, gửi file.\n" + TOKEN + "\n"), TOKEN)
    assert not turn_done(said("You:\n" + PROMPT + "\nMình sẽ ghi " + TOKEN + " khi xong, giờ làm clip 1"), TOKEN)


def test_old_chat_text_before_prompt_is_ignored():
    before = "You:\nviệc cũ " + TOKEN + "\n" + TOKEN
    assert not turn_done(said(before + "\nYou:\n" + PROMPT, text_before=before), TOKEN)


def test_report_words_like_loi_do_not_end_the_turn():
    text = "You:\n" + PROMPT + "\nClip 1 LOẠI: gặp lỗi 502, không tạo được, mình tạo lại..."
    assert not turn_done(said(text), TOKEN)


def test_pick_final_video():
    assert pick_final_video(["a", "b", "c"]) == "c"
    assert pick_final_video([]) is None


def test_budget_warnings():
    assert budget_warnings(videos=1, images=2) == []
    w = budget_warnings(videos=7, images=5)
    assert len(w) == 2 and "7 video" in w[0] and "5 ảnh" in w[1]
    assert "3 video" in budget_warnings(videos=1, images=0, final_videos=3)[0]


def test_complete_uploads_extras_under_field_name_extras(tmp_path):
    import asyncio
    import json
    from runners.muse_fleet_runner import MuseFleetRunner

    class FakeResp:
        status_code, text = 200, "ok"

    class FakeHttp:
        is_closed = False

        def __init__(self):
            self.calls = []

        async def post(self, url, files=None, data=None, timeout=None):
            self.calls.append((url, files, data))
            return FakeResp()

    video = tmp_path / "t1.mp4"
    video.write_bytes(b"v" * 100)
    extra = tmp_path / "t1_extra_1.jpg"
    extra.write_bytes(b"j" * 50)
    runner = MuseFleetRunner.__new__(MuseFleetRunner)
    runner._http, runner.loopback_url = FakeHttp(), "http://127.0.0.1:1/api/muse-bridge"
    meta = {"muse_reply": "x", "_extra_files": [str(extra), str(tmp_path / "missing.jpg")]}
    ok, _ = asyncio.run(runner.complete_task_to_backend("t1", video, meta))
    assert ok
    _, files, data = runner._http.calls[0]
    assert [f[0] for f in files] == ["file", "extras"]
    assert files[1][1][2] == "image/jpeg"
    assert "_extra_files" not in json.loads(data["metadata"])     # đường dẫn máy này không gửi đi
    assert "_extra_files" in meta                                  # không sửa dict của người gọi


def test_discard_temp_file_only_inside_runner_temp_dirs(tmp_path, monkeypatch):
    from runners import muse_fleet_runner as mfr
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(mfr, "WORK_DIR", work)
    monkeypatch.setattr(mfr, "OUTPUTS_DIR", tmp_path / "outputs")
    inside, outside = work / "a_extra_1.jpg", tmp_path / "du_lieu_nguoi_dung.jpg"
    inside.write_bytes(b"x")
    outside.write_bytes(b"x")
    mfr.discard_temp_file(inside)
    mfr.discard_temp_file(outside)
    assert not inside.exists() and outside.exists()


def test_constants():
    from runners.muse_agent_turn import AGENT_VIDEO_MODE
    from services.climax_brief import AGENT_VIDEO_MODE as SERVICE_MODE
    assert AGENT_VIDEO_MODE == SERVICE_MODE == "agent-video"     # runner và dịch vụ phải gọi cùng một tên
    assert AGENT_STABLE_SEC == 90
    assert "data-hatch-markdown-streaming" in STREAMING_JS


def test_finish_agent_turn_rescans_page_when_blob_is_revoked(tmp_path, monkeypatch):
    """Chạy thật 28/10/2026 21:27 và 21:35: Muse tạo lại địa chỉ blob của video cuối liên tục; runner tải địa chỉ đã bị
    huỷ (cả blob bắt từ mạng) -> "Failed to fetch", NO_FINAL dù Muse đã làm xong. Phải quét lại trang lấy địa chỉ mới."""
    import asyncio
    from runners import muse_fleet_runner as mfr

    monkeypatch.setattr(mfr, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(mfr, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(mfr, "SCAN_INTERVAL_SEC", 0)
    monkeypatch.setattr(mfr.agent_turn, "AGENT_STABLE_SEC", 0)
    monkeypatch.setattr(mfr, "validate_video_file", lambda path, max_seconds=None: (True, "12.0s"))
    monkeypatch.setattr(mfr, "remember_delivered", lambda digest: None)
    prompt = "brief ... " + TOKEN

    class FakePage:
        url = "https://muse.ai/thread/6a8b1802-dc4c-4b6c-959b-9e73cb93efd2"

        def __init__(self):
            self.video_scans = 0

        def is_closed(self):
            return False

        async def wait_for_timeout(self, ms):
            return None

        async def evaluate(self, js, arg=None):
            if js == mfr.LOG_TEXT_JS:
                return "You:\n" + prompt + "\nĐã xong, gửi file.\n" + TOKEN
            if js == mfr.agent_turn.STREAMING_JS:
                return False
            if js == mfr.FIND_NEW_MEDIA_JS:
                if arg[0] == "video":
                    self.video_scans += 1
                    return [{"src": "blob:cu" if self.video_scans == 1 else "blob:moi"}]
                return []
            return None

    runner = MuseFleetRunner.__new__(MuseFleetRunner)
    tried = []

    async def download(page, context, src):
        tried.append(src)
        return b"\x00\x00\x00\x18ftypmp42" + b"v" * 5000 if src == "blob:moi" else None

    async def noop(*a, **k):
        return None

    runner._download_media, runner.update_task_progress, runner._click_allow_if_asked = download, noop, noop
    task = {"task_id": "t_agent1", "_result_meta": {},
            "agent": {"done_token": TOKEN, "wait_sec": 60, "target_seconds": 12}}
    from types import SimpleNamespace
    acc = SimpleNamespace(account_id="muse_acc_vid_02")
    ok, path, _ = asyncio.run(runner._finish_agent_turn(acc, FakePage(), None, task, "", prompt, []))
    assert ok and path.is_file()
    assert tried == ["blob:cu", "blob:moi"]                   # đọc lại trang lấy địa chỉ mới sau lần tải hỏng
