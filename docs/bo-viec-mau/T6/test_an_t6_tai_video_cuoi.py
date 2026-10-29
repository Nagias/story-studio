"""Test ẩn bổ sung của bộ việc mẫu T6 (docs/bo-viec-mau): chỉ chép vào tests/ của bản chấm, không thuộc bộ test dự án.

Thay cho test của lần sửa thật `test_finish_agent_turn_rescans_page_when_blob_is_revoked` (bỏ chấm: test đó đòi đúng
thứ tự tải ["blob:cu", "blob:moi"], bài làm đúng theo cách khác bị chấm oan). Ở đây kiểm kết quả, không đòi thứ tự tải:
trang đổi địa chỉ blob sau mỗi lần đọc, địa chỉ cũ tải hỏng, thì runner vẫn lấy được video cuối đang có trên trang.
Trang giả chỉ hiểu các đoạn JS có sẵn và tải qua `_download_media()` (ràng buộc ghi trong đề T6, thêm 30/10/2026 sau
lần đo đầu: bài làm tải bằng đoạn JS mới trong trang bị chấm oan).
"""
import asyncio
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TOKEN = "XONG-ab12cd34"
VIDEO = b"\x00\x00\x00\x18ftypmp42" + b"v" * 5000


def test_runner_lay_duoc_video_cuoi_khi_blob_vua_doc_da_bi_huy(tmp_path, monkeypatch):
    from runners import muse_fleet_runner as mfr

    monkeypatch.setattr(mfr, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(mfr, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(mfr, "SCAN_INTERVAL_SEC", 0)
    monkeypatch.setattr(mfr.agent_turn, "AGENT_STABLE_SEC", 0)
    monkeypatch.setattr(mfr, "validate_video_file", lambda path, max_seconds=None: (True, "12.0s"))
    monkeypatch.setattr(mfr, "remember_delivered", lambda digest: None)
    prompt = "brief ... " + TOKEN

    async def noop(*a, **k):
        return None

    class FakePage:
        """Mỗi lần quét video, trang đưa một địa chỉ blob mới; chỉ địa chỉ của lần quét mới nhất còn tải được."""
        url = "https://muse.ai/thread/6a8b1802-dc4c-4b6c-959b-9e73cb93efd2"

        def __init__(self):
            self.scans = 0

        def is_closed(self):
            return False

        def __getattr__(self, name):        # reload(), goto(), wait_for_*… của bài làm: coi như không làm gì
            return noop

        async def evaluate(self, js, arg=None):
            if js == mfr.LOG_TEXT_JS:
                return "You:\n" + prompt + "\nĐã xong, gửi file.\n" + TOKEN
            if js == mfr.agent_turn.STREAMING_JS:
                return False
            if js == mfr.FIND_NEW_MEDIA_JS:
                if arg and arg[0] == "video":
                    self.scans += 1
                    return [{"src": f"blob:lan{self.scans}"}]
                return []
            return None

    page = FakePage()
    runner = mfr.MuseFleetRunner.__new__(mfr.MuseFleetRunner)
    tried = []

    async def download(pg, context, src):
        tried.append(src)
        return VIDEO if src == f"blob:lan{page.scans}" and page.scans >= 2 else None

    runner._download_media, runner.update_task_progress, runner._click_allow_if_asked = download, noop, noop
    task = {"task_id": "t_agent6", "_result_meta": {},
            "agent": {"done_token": TOKEN, "wait_sec": 60, "target_seconds": 12}}
    acc = SimpleNamespace(account_id="muse_acc_vid_02")
    args = [acc, page, None, task, "", prompt, []]
    extra = list(inspect.signature(runner._finish_agent_turn).parameters)[7:]
    kwargs = {name: [] for name in extra if name == "net_candidates"}   # bài làm còn giữ tham số cũ thì đưa rỗng
    ok, path, _ = asyncio.run(runner._finish_agent_turn(*args, **kwargs))
    assert ok and path is not None and Path(path).is_file()
    assert Path(path).read_bytes() == VIDEO
    assert len(tried) >= 2, "lần tải đầu hỏng mà không tải lại"
