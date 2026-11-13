"""Fleet Runner: một trình duyệt treo không được giữ luồng làm việc mãi.

Gặp 09/11/2026 (vụ xưởng sắt): `muse_acc_img_01` gửi prompt lúc 13:50 rồi một lệnh đọc trang của trình duyệt đứng im tới
19:17. Vòng chờ 150 giây không chạy tới lần kiểm giờ tiếp theo, nên một trong hai luồng của Fleet Runner bị chiếm 5,5
giờ và 25 ảnh cảnh hết giờ. Nay mỗi việc có trần thời gian; quá trần thì bỏ việc, đóng trình duyệt (cũng có trần) và
trả lỗi TASK_HUNG để luồng nhận việc khác."""
import asyncio
import io
import inspect
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

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


# --- Ảnh cảnh vẽ theo ảnh chuẩn bối cảnh không bị coi là ảnh đính kèm gửi lại ---------------------------------------
def _plate() -> Image.Image:
    """Ảnh chuẩn bối cảnh giả: bố cục thô rõ ràng (trời sáng trên, đất tối dưới, con đường giữa)."""
    img = Image.new("RGB", (2048, 1152), (70, 90, 60))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 2048, 460], fill=(170, 180, 190))
    d.polygon([(900, 460), (1150, 460), (1500, 1152), (550, 1152)], fill=(140, 120, 90))
    return img


def _jpeg_bytes(img: Image.Image, fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, quality=80)
    return buf.getvalue()


def test_scene_drawn_on_the_location_plate_is_not_rejected_as_an_echo():
    """Gặp 06/11 và 12/11/2026 (Khang Cúc Hoa cảnh 2): Muse vẽ xong cảnh trên con đường của ảnh chuẩn, vân tay 8x8 giống
    ảnh chuẩn nên runner loại ("trùng ảnh tham chiếu"), app rơi sang ảnh trả phí không theo bảng nhân vật."""
    plate = _plate()
    scene = plate.copy()
    d = ImageDraw.Draw(scene)   # hai nhân vật đầu tròn, xe đạp, lá ngô: cùng bố cục, khác chi tiết
    for x in (820, 1120):
        d.ellipse([x, 520, x + 150, 670], fill=(250, 250, 250))
        d.rectangle([x + 20, 670, x + 130, 980], fill=(60, 60, 80))
    for x in range(0, 2048, 60):
        d.line([(x, 700), (x + 30, 1152)], fill=(40, 110, 40), width=8)
    ref = fr.echo_ref(plate)
    assert bin(fr.average_hash(scene) ^ ref[0]).count("1") <= 6, "ca thử phải giống vân tay 8x8 như lỗi thật"
    ok, info = fr.validate_image_bytes(_jpeg_bytes(scene), [ref])
    assert ok, info
    # ảnh đính kèm gửi lại thật (cùng ảnh, nén WEBP) vẫn bị loại
    ok, info = fr.validate_image_bytes(_jpeg_bytes(plate, "WEBP"), [ref])
    assert not ok and "tham chiếu" in info


# --- Muse báo hết lượt dùng: bỏ việc ngay, không chờ hết 75 phút -----------------------------------------------------
QUOTA_TEXT = "Muse: You've reached your usage limit. Upgrade now or invite friends to get more Muse tokens."


def test_quota_message_is_recognised():
    assert fr.muse_quota_message("cũ", "cũ " + QUOTA_TEXT, "") is not None
    assert fr.muse_quota_message("cũ", "cũ Xong anh, video đã ghép.", "") is None


class _QuotaPage:
    url = "https://muse.ai/thread/abc"

    def is_closed(self):
        return False

    async def evaluate(self, js, *args):
        return "TRUOC " + QUOTA_TEXT if js == fr.LOG_TEXT_JS else False


def test_agent_turn_stops_at_once_when_muse_is_out_of_quota(monkeypatch):
    """Gặp 12/11/2026 (vụ xưởng sắt cảnh 26): Muse báo hết lượt ngay, runner vẫn chờ đủ 4.500 giây rồi mới báo
    AGENT_TIMEOUT; các cảnh sau lỗi hàng loạt vì tài khoản bị khoá."""
    runner = fr.MuseFleetRunner()

    async def nothing(*a, **k):
        return None

    monkeypatch.setattr(runner, "_click_allow_if_asked", nothing)
    monkeypatch.setattr(runner, "update_task_progress", nothing)
    task = {"task_id": "t_quota", "mode": agent_turn.AGENT_VIDEO_MODE, "_result_meta": {},
            "agent": {"done_token": "XONG-1", "wait_sec": 4500, "target_seconds": 10}}
    started = time.monotonic()
    import pytest
    with pytest.raises(fr.TaskFailure) as err:
        asyncio.run(asyncio.wait_for(   # trần 5 giây: bản lỗi chờ 4.500 giây thì test đỏ ngay chứ không treo
            runner._finish_agent_turn(_account("video"), _QuotaPage(), None, task, "TRUOC", "prompt", []), 5))
    assert time.monotonic() - started < 5
    assert err.value.code == "QUOTA_EXCEEDED" and "usage limit" in str(err.value)


# --- Profile dùng chung đang bị app khác mở: không nhận việc cho tài khoản đó ------------------------------------------
def test_account_whose_shared_profile_is_open_elsewhere_is_skipped_before_taking_a_task(monkeypatch, tmp_path):
    """Gặp 12/11/2026: app VideoPic mở profile của muse_acc_vp_04; runner vẫn nhận việc cho tài khoản này, mỗi việc hỏng
    ngay (PROFILE_IN_USE) và 29 cảnh video cao trào bị ghi lỗi trong 10 phút."""
    runner = fr.MuseFleetRunner()
    monkeypatch.setattr(fr, "EXTRA_PROFILES_DIRS", [tmp_path])     # thư mục profile của app khác (đã khai báo)
    monkeypatch.setattr(fr.FleetAccount, "is_logged_in", lambda self: True)
    busy = fr.FleetAccount({"account_id": "muse_acc_vp_thu", "type": "video", "profile_dir": str(tmp_path / "videopic")})
    free = fr.FleetAccount({"account_id": "muse_acc_vid_thu", "type": "video"})
    assert busy.is_external
    runner.accounts = {busy.account_id: busy, free.account_id: free}
    busy.last_used, free.last_used = 0, 100          # busy đứng đầu hàng chọn
    monkeypatch.setattr(fr, "profile_in_use", lambda d: Path(d) == Path(busy.profile_dir))
    got = runner._reserve_account(["video"])
    assert got is free and busy.status == "cooldown" and busy.cooldown_until > time.time()


def test_muse_usage_limit_blocks_the_account_for_hours_not_minutes():
    """Gặp 12/11/2026: khoá 15 phút thì cứ 15 phút lại giao cảnh cho tài khoản hết lượt và cảnh hỏng ngay."""
    from routers import muse_bridge as mb
    assert mb.block_seconds_for("QUOTA_EXCEEDED: Muse: You've reached your usage limit.") >= 6 * 3600
    assert mb.block_seconds_for("Hết quota / bị chặn: 429 rate limit") == mb.ACCOUNT_BLOCK_SEC


def test_muse_usage_limit_blocks_until_the_reset_time_muse_states():
    """Gặp 12/11/2026 21:49: tài khoản hết lượt tuần bị khoá 6 tiếng, hết 6 tiếng app mở lại, giao cảnh 29 và cảnh hỏng
    ngay. Muse ghi rõ giờ lượt dùng hồi lại: khoá đúng tới giờ đó (giờ máy, Muse hiện theo giờ trình duyệt)."""
    import datetime as dt
    from routers import muse_bridge as mb
    now = dt.datetime(2026, 11, 12, 21, 49).timestamp()
    msg = ("QUOTA_EXCEEDED: Muse: You've reached your usage limit. Upgrade now or invite friends to get more Muse "
           "tokens. Your full weekly usage will reset at \u206811:34 PM\u2069 on \u2068Tuesday, November 17\u2069.")
    reset = dt.datetime(2026, 11, 17, 23, 34).timestamp()
    got = mb.block_seconds_for(msg, now=now)
    assert reset - now <= got <= reset - now + 600
    # qua năm mới: tháng 1 là năm sau
    late = dt.datetime(2026, 12, 30, 10, 0).timestamp()
    got = mb.block_seconds_for("usage limit. Your full weekly usage will reset at 9:05 AM on Monday, January 4", now=late)
    assert abs(got - (dt.datetime(2027, 1, 4, 9, 5).timestamp() - late)) <= 600
    # không đọc được giờ, hoặc giờ vô lý (quá 8 ngày) thì về mức 6 tiếng
    assert mb.block_seconds_for("QUOTA_EXCEEDED: usage limit", now=now) == mb.MUSE_USAGE_LIMIT_BLOCK_SEC
    assert mb.block_seconds_for("usage limit, reset at 1:00 AM on Friday, March 5", now=now) == mb.MUSE_USAGE_LIMIT_BLOCK_SEC


def test_agent_turn_without_any_video_because_of_a_limit_counts_as_quota():
    """Gặp 13/11/2026 02:09: tài khoản video cuối cùng chạm hạn mức tạo video; trang Muse không hiện thông báo hết lượt
    mà Muse tự viết báo cáo "Tổng số đã tạo: 0 video / 0 ảnh mới — lần gọi clip A bị chặn ở cổng hạn mức". Runner ghi
    NO_FINAL nên tài khoản không bị khoá và nhận tiếp cảnh sau để hỏng tiếp (trước đó vp_03 hỏng 12 việc cùng kiểu)."""
    said = ("Kế hoạch clip A, B, C... Tổng số đã tạo: 0 video / 0 ảnh mới — lần gọi clip A bị chặn ở cổng hạn mức, "
            "chưa sinh ra file nào. Kết quả: KHÔNG ĐẠT. XONG-fe4c7191")
    assert fr.agent_no_video_reason(said)
    assert fr.agent_no_video_reason("Video generation is rate limited right now, no clip was created. XONG-1")
    # Muse có làm video nhưng tải về lỗi: không phải hết hạn mức
    assert fr.agent_no_video_reason("Tổng số đã tạo: 4 video / 2 ảnh. Kết quả: ĐẠT. XONG-1") is None
    assert fr.agent_no_video_reason("Đã tạo 10 video, giữ 3. XONG-1") is None


def test_new_media_must_come_after_the_prompt_just_sent():
    """Gặp 13/11/2026 (vụ Khang Cúc Hoa cảnh 004): không mở được chat mới, runner dùng lại chat cũ và sau 15 giây nhận một
    ảnh cũ của chat đó (tải lười khi cuộn, địa chỉ blob mới) làm ảnh mới. Nay chỉ nhận media sau tin nhắn prompt vừa gửi."""
    from runners import muse_fleet_runner as fr
    assert fr.prompt_anchor("tạo cho tôi 1 hình ảnh 2K tỉ lệ 16:9: Style: horror\ndòng hai") == \
        "tạo cho tôi 1 hình ảnh 2K tỉ lệ 16:9: St"
    assert fr.prompt_anchor("") == "" and fr.prompt_anchor(None) == ""
    js = fr.FIND_NEW_MEDIA_JS
    assert "anchorText" in js and "DOCUMENT_POSITION_FOLLOWING" in js and "afterPrompt(el)" in js
    import inspect
    src = inspect.getsource(fr)
    calls = src.count("page.evaluate(FIND_NEW_MEDIA_JS,")
    assert calls >= 3 and src.count("prompt_anchor(prompt)])") == calls   # mọi chỗ tìm media đều truyền mốc prompt
