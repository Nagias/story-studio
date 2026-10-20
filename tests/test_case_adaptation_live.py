"""
Test thật (chọn chạy): đưa tests/fixtures/case_adaptation/dossier.txt qua 9router thật bằng worker, từng việc một.

Chỉ chạy khi có STORY_STUDIO_LIVE=1, vì gọi LLM thật (mất vài phút, tốn hạn mức Gemini của 9router):

    STORY_STUDIO_LIVE=1 ".venv/Scripts/python.exe" -m pytest tests/test_case_adaptation_live.py -q -s

`-s` để thấy dòng tóm tắt số lần gọi và thời gian. Dữ liệu ghi vào thư mục projects tạm (isolated_projects_dir),
không đụng projects/ thật. Biến STORY_STUDIO_LIVE_TIMEOUT_S đổi thời gian chờ tối đa của cả hàng việc (mặc định 3600 s).

Kiểm: một lần gọi nhỏ trước để biết 9router sẵn sàng (không thì báo ngay, không chờ 15 phút mỗi việc); hàng việc
chạy tới `done`; kế hoạch không còn cờ nào (cảnh lẫn cấp kế hoạch); không tên thật nào của bài trong lời Việt/Anh.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import case_adaptation_llm, case_store
from services.case_adaptation_checks import ForbiddenName, build_forbidden_names, find_unknown_names, has_blocking_flags
from services.case_adaptation_llm import RETRYABLE_KINDS, LLMError
from services.case_adaptation_steps import RETRY_NOTE
from services.case_worker import pipeline_progress, start_analysis, worker_loop
from tests.case_adaptation_fakes import FIXTURES_DIR

pytestmark = pytest.mark.skipif(
    os.getenv("STORY_STUDIO_LIVE") != "1",
    reason="Test gọi 9router thật; đặt STORY_STUDIO_LIVE=1 để chạy.",
)

DOSSIER = (FIXTURES_DIR / "dossier.txt").read_text(encoding="utf-8")
TARGET_MINUTES = 8
STYLE = "neo_noir_silhouette"      # phong cách mặc định của giao diện
TIMEOUT_S = float(os.getenv("STORY_STUDIO_LIVE_TIMEOUT_S", "3600"))
_RETRY_MARK = RETRY_NOTE.split("{")[0].strip()

# Tên và số nhận dạng thật trong dossier.txt, chép tay để kiểm độc lập với hồ sơ do model tự rút ra.
# Tên so bằng bộ so khớp của code thật (find_unknown_names): đúng dấu hoặc hoàn toàn không dấu, theo ranh giới từ,
# nên "lẻ loi" không bị coi là "Lê Lợi". Số nhận dạng toàn chữ ASCII nên so chuỗi liền.
REAL_NAMES = ["Nguyễn Văn Hùng", "Lê Thị Mai", "Vũ Đình Trọng", "Tân Hải", "Lê Lợi", "Hải Phòng"]
REAL_IDENTIFIERS = ["15B1", "0912345678", "987.65"]
_REAL_FORBIDDEN = [ForbiddenName(name) for name in REAL_NAMES]


def _real_names_in(text: str, aliases: list[str]) -> list[str]:
    found = find_unknown_names(text, _REAL_FORBIDDEN, aliases)
    return found + [ident for ident in REAL_IDENTIFIERS if ident.lower() in text.lower()]


class _CallLog:
    """Ghi mỗi lần gọi LLM thật: việc nào, mất bao lâu, kết quả (ok hoặc loại lỗi), có phải gọi lại sau khi bị loại."""

    def __init__(self):
        self.rows: list[dict] = []

    def wrap(self, real_call):
        async def call(system, user, **kwargs):
            started = time.monotonic()
            row = {"marker": user.split("\n", 1)[0].strip(), "retry_after_reject": _RETRY_MARK in user}
            self.rows.append(row)
            try:
                result = await real_call(system, user, **kwargs)
            except LLMError as exc:
                row["outcome"] = exc.kind
                raise
            finally:
                row["seconds"] = time.monotonic() - started
            row["outcome"] = "ok"
            return result

        return call

    def summary(self, total_seconds: float) -> str:
        count = lambda pred: sum(1 for r in self.rows if pred(r))
        return (
            f"LIVE: {len(self.rows)} lần gọi LLM, {total_seconds:.0f} s; "
            f"gọi lại sau khi bị loại: {count(lambda r: r['retry_after_reject'])}; "
            f"9router bận: {count(lambda r: r.get('outcome') == 'busy')}; "
            f"lỗi khác: {count(lambda r: r.get('outcome') not in ('ok', 'busy'))}"
        )


async def _wait_for_pipeline(case_id: str) -> bool:
    """Chạy worker cho tới khi hàng việc hết `running`. Trả True nếu quá TIMEOUT_S mà chưa xong."""
    stop = asyncio.Event()
    task = asyncio.create_task(worker_loop(stop, idle_sleep=0.5))
    deadline = time.monotonic() + TIMEOUT_S
    try:
        while case_store.load_pipeline(case_id).status == "running":
            if task.done():
                break
            if time.monotonic() > deadline:
                return True
            await asyncio.sleep(1.0)
        return False
    finally:
        stop.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _ping(real_call) -> None:
    await real_call("Chỉ trả JSON.", 'TASK: PING\nTrả về {"ok": true}', temperature=0.0, timeout=60.0)


def _check_9router_ready(real_call) -> None:
    """Một lần gọi nhỏ trước: 9router không sẵn sàng (bận, hết hạn mức, sai key) thì báo ngay thay vì để mỗi việc chờ tới
    15 phút. Lỗi tạm thời (timeout, mạng, JSON hỏng) được thử thêm một lần; bận, auth, không có tài khoản thì không."""
    not_ready = None
    for attempt in range(2):
        try:
            asyncio.run(_ping(real_call))
            return
        except LLMError as exc:
            not_ready = exc
            if exc.kind not in RETRYABLE_KINDS:
                break
    pytest.fail(f"9router chưa sẵn sàng ({not_ready.kind}): {not_ready.user_message}", pytrace=False)


def test_dossier_through_real_9router(isolated_projects_dir, monkeypatch, capsys):
    log = _CallLog()
    real_call = case_adaptation_llm.call_llm_json

    _check_9router_ready(real_call)

    monkeypatch.setattr(case_adaptation_llm, "call_llm_json", log.wrap(real_call))
    started = time.monotonic()
    case_id = start_analysis(DOSSIER, TARGET_MINUTES, STYLE)
    timed_out = asyncio.run(_wait_for_pipeline(case_id))
    elapsed = time.monotonic() - started
    with capsys.disabled():
        print("\n" + log.summary(elapsed))
    if timed_out:
        pytest.fail(f"Hàng việc chưa xong sau {TIMEOUT_S:.0f} s.", pytrace=False)

    pipeline = case_store.load_pipeline(case_id)
    progress = pipeline_progress(pipeline)
    assert pipeline.status == "done", f"{progress['step_label']}: {progress['error']}"
    plan = case_store.load_plan(case_id)
    assert plan is not None, "assemble xong mà không có plan.json"

    # Cảnh 1 là câu miễn trừ cố định; sau đó còn ít nhất vài cảnh có lời cả hai ngôn ngữ.
    assert plan.scenes[0].visual_kind == "disclaimer"
    story = plan.scenes[1:]
    assert len(story) >= 3, f"chỉ có {len(story)} cảnh truyện"
    assert all(s.narration_vi.strip() and s.narration_en.strip() for s in story)

    # Không còn cờ nào (tên thật chưa có tên thay, ngày tháng cụ thể, thiếu lời, id bảng ghim lạ).
    flags = [(s.order, f.kind, f.field, f.detail) for s in plan.scenes for f in s.flags]
    flags += [(0, f.kind, f.field, f.detail) for f in plan.flags]
    assert not has_blocking_flags(plan), f"còn cờ: {flags}"
    assert not flags

    # Không tên thật nào trong lời kể (và prompt hình). Hai cách: tên trong dossier chép tay, và hồ sơ model rút ra.
    forbidden = build_forbidden_names(plan.bible, DOSSIER)
    aliases = [a.strip() for e in plan.bible.entities for a in (e.alias_vi, e.alias_en) if a.strip()]
    leaks = []
    for scene in story:
        for field in ("narration_vi", "narration_en", "image_prompt", "video_prompt"):
            text = getattr(scene, field)
            for name in _real_names_in(text, aliases) + find_unknown_names(text, forbidden, aliases):
                leaks.append((scene.order, field, name))
    assert not leaks, f"lọt tên thật: {leaks}"
