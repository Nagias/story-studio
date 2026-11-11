"""Fleet Runner: một trình duyệt treo không được giữ luồng làm việc mãi.

Gặp 09/11/2026 (vụ xưởng sắt): `muse_acc_img_01` gửi prompt lúc 13:50 rồi một lệnh đọc trang của trình duyệt đứng im tới
19:17. Vòng chờ 150 giây không chạy tới lần kiểm giờ tiếp theo, nên một trong hai luồng của Fleet Runner bị chiếm 5,5
giờ và 25 ảnh cảnh hết giờ. Nay mỗi việc có trần thời gian; quá trần thì bỏ việc, đóng trình duyệt (cũng có trần) và
trả lỗi TASK_HUNG để luồng nhận việc khác."""
import asyncio
import inspect
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from runners import muse_agent_turn as agent_turn  # noqa: E402
from runners import muse_fleet_runner as fr  # noqa: E402


def _account(kind: str = "image") -> fr.FleetAccount:
    return fr.FleetAccount({"account_id": f"muse_acc_thu_{kind}", "type": kind})


def test_ceiling_covers_muse_wait_plus_browser_overhead():
    assert fr.task_ceiling_sec({"mode": "text-to-image"}) == fr.MEDIA_WAIT_SEC["image"] + fr.TASK_OVERHEAD_SEC
    assert fr.task_ceiling_sec({"mode": "image-to-video"}) == fr.MEDIA_WAIT_SEC["video"] + fr.TASK_OVERHEAD_SEC
    agent = {"mode": agent_turn.AGENT_VIDEO_MODE, "agent": {"wait_sec": 4500}}
    assert fr.task_ceiling_sec(agent) == 4500 + fr.TASK_OVERHEAD_SEC


def test_hung_task_is_dropped_and_frees_the_slot(monkeypatch):
    runner = fr.MuseFleetRunner()

    async def hangs(acc, task):
        await asyncio.sleep(3600)

    monkeypatch.setattr(runner, "execute_task_with_browser", hangs)
    monkeypatch.setattr(fr, "task_ceiling_sec", lambda task: 0.2)
    started = time.monotonic()
    ok, out, err = asyncio.run(runner.run_task_with_ceiling(_account(), {"task_id": "t1", "mode": "text-to-image"}))
    assert time.monotonic() - started < 3
    assert (ok, out) == (False, None)
    assert err.startswith("TASK_HUNG")


class _HangingPage:
    def is_closed(self):
        return False

    async def goto(self, *a, **k):
        await asyncio.sleep(3600)   # trình duyệt đứng im như 09/11


class _HangingContext:
    def __init__(self):
        self.pages = [_HangingPage()]
        self.close_called = False

    async def close(self):
        self.close_called = True
        await asyncio.sleep(3600)   # đóng cũng đứng im


def test_hung_browser_whose_close_also_hangs_still_frees_the_slot(monkeypatch):
    """Cả lệnh đóng trình duyệt cũng treo: vẫn phải trả lời trong vài giây, không chờ mãi."""
    runner = fr.MuseFleetRunner()
    ctx = _HangingContext()

    async def make_context(acc, headless=True):
        return ctx

    async def no_progress(*a, **k):
        return None

    monkeypatch.setattr(runner, "create_browser_context", make_context)
    monkeypatch.setattr(runner, "update_task_progress", no_progress)
    monkeypatch.setattr(fr, "delivered_hashes", lambda: set())   # không đọc thư mục kết quả Muse thật (chậm)
    monkeypatch.setattr(fr, "task_ceiling_sec", lambda task: 0.3)
    monkeypatch.setattr(fr, "BROWSER_CLOSE_TIMEOUT_SEC", 0.2)
    started = time.monotonic()
    ok, out, err = asyncio.run(runner.run_task_with_ceiling(_account(), {"task_id": "t2", "mode": "text-to-image"}))
    assert time.monotonic() - started < 3
    assert ok is False and err.startswith("TASK_HUNG")
    assert ctx.close_called, "phải thử đóng trình duyệt của việc bị treo"


def test_worker_slots_run_tasks_through_the_ceiling():
    src = inspect.getsource(fr.MuseFleetRunner.worker_slot_loop)
    assert "run_task_with_ceiling(" in src
    assert "execute_task_with_browser(" not in src


# --- Bằng chứng khi Muse báo xong mà runner không thấy media (NO_MEDIA) -------------------------------------------------
class _DiagPage:
    url = "https://muse.ai/thread/abc"

    async def evaluate(self, js, *args):
        assert js == fr.MEDIA_DIAGNOSTIC_JS
        return [{"tag": "img", "src": "blob:x", "natural": [2048, 1152], "in_log": False, "pre": False}]

    async def screenshot(self, path, full_page=True):
        Path(path).write_bytes(b"png")


def test_no_media_saves_page_evidence_and_keeps_only_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "NO_MEDIA_DIAG_DIR", tmp_path)
    monkeypatch.setattr(fr, "NO_MEDIA_DIAG_KEEP", 2)
    runner = fr.MuseFleetRunner()
    for i in range(3):
        out = asyncio.run(runner.save_no_media_evidence(_DiagPage(), f"task_{i}", "muse_acc_thu", {"kind": "image"}))
        assert out is not None and out.is_file()
        time.sleep(0.02)
    saved = sorted(p.name for p in tmp_path.iterdir() if "_task_" in p.name)
    assert len(saved) == 4 and not any("task_0" in n for n in saved)       # giữ 2 lần gần nhất (json + png)
    import json
    data = json.loads(next(tmp_path.glob("*task_2.json")).read_text(encoding="utf-8"))
    assert data["media"][0]["natural"] == [2048, 1152] and data["url"].endswith("/abc") and data["kind"] == "image"


def test_no_media_evidence_failure_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "NO_MEDIA_DIAG_DIR", tmp_path)

    class Broken(_DiagPage):
        async def evaluate(self, js, *args):
            raise RuntimeError("trang đã đóng")
    assert asyncio.run(fr.MuseFleetRunner().save_no_media_evidence(Broken(), "t", "a", {})) is None
