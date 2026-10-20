"""
Worker chạy hàng việc phân tích vụ án (spec 7.1a).

- Mỗi lúc chỉ chạy một việc cho mọi vụ án, vụ cũ hơn trước; danh sách việc lớn dần sau dàn ý.
- Server khởi động lại: việc đang `running` trở về `pending`, việc đã `done` không gọi LLM lại.
- Việc hỏng thì hàng việc dừng; "Thử lại" (resume_pipeline) chạy tiếp từ đúng việc đó.
- Dàn ý xong thì vụ dừng ở trạng thái `review` chờ người dùng duyệt (approve_outline); sửa dàn ý (edit_outline) được
  kiểm lại bằng các quy tắc dàn ý rồi sinh lại các việc viết cảnh.
- Lỗi ngoài dự kiến trong một việc không được làm chết vòng lặp worker.
- LLM giả (tests/case_adaptation_fakes.py), thư mục projects tạm (isolated_projects_dir); không gọi 9router thật.
"""
import asyncio
import copy
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config
from models.case_adaptation_schemas import MAX_SOURCE_CHARS
from services import case_adaptation_llm, case_adaptation_steps, case_store, case_worker
from services.case_adaptation_steps import chunk_source
from services.case_worker import (
    CaseInputError,
    CaseNotFoundError,
    OutlineEditError,
    OutlineStateError,
    approve_outline,
    edit_outline,
    outline_view,
    pipeline_progress,
    recover_interrupted,
    resume_pipeline,
    run_next_step,
    start_analysis,
    worker_loop,
)
from tests.case_adaptation_fakes import FIXTURES_DIR, load_fixture, make_fake_llm

DOSSIER = (FIXTURES_DIR / "dossier.txt").read_text(encoding="utf-8")
STYLE = "cinematic noir"
FULL_ORDER = [
    "EXTRACT 0", "EXTRACT 1", "CLUSTER", "ALIASES", "OUTLINE",
    "WRITE_VI p1", "WRITE_EN p1", "PROMPTS p1", "WRITE_VI p2", "WRITE_EN p2", "PROMPTS p2",
]
ALL_LABELS = [
    "Đang đọc đoạn 1/2", "Đang đọc đoạn 2/2", "Đang gộp tên nhân vật", "Đang đặt tên hư cấu", "Đang lên dàn ý",
    "Đang viết lời Việt, nhịp 1/2", "Đang viết lời Anh, nhịp 1/2", "Đang viết prompt hình, nhịp 1/2",
    "Đang viết lời Việt, nhịp 2/2", "Đang viết lời Anh, nhịp 2/2", "Đang viết prompt hình, nhịp 2/2",
    "Đang ráp và kiểm tra",
]
REVIEW_LABEL = "Dàn ý xong, chờ bạn duyệt"
REAL_VICTIM = "Nguyễn Văn Hùng"               # tên thật của nạn nhân trong dossier.txt, tên hư cấu "Trịnh Quang Vũ"


# ---------------------------------------------------------------- helpers

def _start(created_at: str = "", *, case_id: str = "", monkeypatch=None) -> str:
    """Vụ án mẫu (2 đoạn với chunk_chars=900). `created_at` đặt tay để thứ tự vụ cũ/mới không phụ thuộc đồng hồ;
    `case_id` (cần `monkeypatch`) cố định id để thứ tự theo id cũng không trùng thứ tự theo created_at do may rủi."""
    if case_id:
        monkeypatch.setattr(case_store, "new_case_id", lambda: case_id)
    case_id = start_analysis(DOSSIER, 8, STYLE, chunk_chars=900)
    if created_at:
        pipeline = case_store.load_pipeline(case_id)
        pipeline.created_at = created_at
        case_store.save_pipeline(pipeline)
    return case_id


def _older_and_newer(monkeypatch) -> tuple[str, str]:
    """Hai vụ: vụ MỚI được tạo trước và có id nhỏ hơn, vụ CŨ tạo sau và có id lớn hơn. Chỉ `created_at` cho biết vụ
    nào cũ, nên code xếp theo thứ tự tạo, theo id hay theo thứ tự thư mục đều làm test fail."""
    newer = _start("2026-10-19T10:00:05+00:00", case_id="case_00000001", monkeypatch=monkeypatch)
    older = _start("2026-10-19T10:00:00+00:00", case_id="case_ffffffff", monkeypatch=monkeypatch)
    return older, newer


def _pipeline(case_id: str):
    return case_store.load_pipeline(case_id)


def _progress(case_id: str) -> dict:
    return pipeline_progress(_pipeline(case_id))


def _drain(llm, limit: int = 100, *, approve: bool = True) -> int:
    """Gọi run_next_step tới khi trả False (như worker); trả số việc đã chạy. Vụ nào dừng chờ duyệt dàn ý thì duyệt
    luôn như người dùng bấm "Duyệt" (approve=False thì để nguyên ở trạng thái chờ)."""
    ran = 0
    while True:
        while asyncio.run(run_next_step(llm=llm)):
            ran += 1
            assert ran < limit, "hàng việc không dừng"
        waiting = [p.case_id for p in case_store.list_pipelines() if p.status == "review"] if approve else []
        if not waiting:
            return ran
        for case_id in waiting:
            approve_outline(case_id)


async def _wait_until(predicate, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "quá thời gian chờ"
        await asyncio.sleep(0.02)


def _run_loop_until_settled(case_ids: list[str], timeout: float = 30.0) -> None:
    """Chạy worker_loop cho tới khi mọi vụ trong `case_ids` không còn `running`, rồi dừng vòng lặp. Mọi vụ đã dừng mà
    có vụ chờ duyệt dàn ý thì duyệt hết các vụ đó (như người dùng bấm "Duyệt") rồi chờ tiếp."""

    async def main():
        stop = asyncio.Event()
        task = asyncio.create_task(worker_loop(stop, idle_sleep=0.01))
        try:
            while True:
                await _wait_until(lambda: all(_pipeline(c).status != "running" for c in case_ids), timeout)
                waiting = [c for c in case_ids if _pipeline(c).status == "review"]
                if not waiting:
                    break
                for case_id in waiting:
                    approve_outline(case_id)
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)
        assert task.exception() is None

    asyncio.run(main())


def _thin_write_vi() -> dict:
    thin = copy.deepcopy(load_fixture("WRITE_VI p1"))
    thin["scenes"] = thin["scenes"][:2]                 # cần 3 cảnh
    return thin


# ---------------------------------------------------------------- start_analysis

def test_start_analysis_saves_source_chunks_and_pipeline(isolated_projects_dir):
    case_id = start_analysis(DOSSIER, 8, STYLE, chunk_chars=900)

    assert case_store.load_source(case_id) == DOSSIER
    assert case_store.load_chunks(case_id) == chunk_source(DOSSIER, 900)
    pipeline = _pipeline(case_id)
    assert pipeline.status == "running"
    assert (pipeline.target_minutes, pipeline.visual_style, pipeline.chunk_chars) == (8, STYLE, 900)
    assert [s.id for s in pipeline.steps] == ["extract_00", "extract_01", "cluster", "aliases", "outline"]
    assert all(s.status == "pending" and s.attempts == 0 for s in pipeline.steps)
    assert pipeline.created_at and pipeline.updated_at


def test_start_analysis_rejects_empty_and_too_long(isolated_projects_dir):
    for text in ["", "   \n\t  ", None]:
        with pytest.raises(CaseInputError) as info:
            start_analysis(text, 8, STYLE)
        assert info.value.reason == "empty"
        assert isinstance(info.value, ValueError)
        assert "trống" in str(info.value)

    with pytest.raises(CaseInputError) as info:
        start_analysis("x" * (MAX_SOURCE_CHARS + 1), 8, STYLE)
    assert info.value.reason == "too_long"
    assert "ký tự" in str(info.value)

    assert case_store.list_pipelines() == []
    assert not (isolated_projects_dir / "_cases").exists()      # bị từ chối thì không lưu gì

    case_id = start_analysis("x " * (MAX_SOURCE_CHARS // 2), 8, STYLE)   # đúng giới hạn thì nhận
    assert len(case_store.load_source(case_id)) == MAX_SOURCE_CHARS


# ---------------------------------------------------------------- tiến độ

def test_progress_labels(isolated_projects_dir):
    case_id = _start()
    progress = _progress(case_id)
    assert progress == {"status": "running", "step_label": "Đang đọc đoạn 1/2", "steps_done": 0,
                        "steps_total": 5, "error": ""}


def test_progress_label_for_every_step_kind(isolated_projects_dir):
    case_id = _start()
    base, _calls = make_fake_llm()
    seen_running = []

    async def llm(system, user, **kwargs):
        # Lúc LLM đang chạy, việc đó đã được đánh dấu running và tăng attempts trên đĩa.
        running = [s for s in _pipeline(case_id).steps if s.status == "running"]
        seen_running.append((running[0].id, running[0].attempts, _progress(case_id)["step_label"]))
        return await base(system, user, **kwargs)

    labels = []
    while True:
        labels.append(_progress(case_id)["step_label"])
        if asyncio.run(run_next_step(llm=llm)):
            continue
        if _pipeline(case_id).status != "review":
            break
        approve_outline(case_id)

    assert labels[:-1] == ALL_LABELS[:5] + [REVIEW_LABEL] + ALL_LABELS[5:]
    assert [label for _id, _n, label in seen_running] == ALL_LABELS[:-1]   # assemble không gọi LLM
    assert all(n == 1 for _id, n, _label in seen_running)
    done = _progress(case_id)
    assert done["status"] == "done"
    assert done["steps_done"] == done["steps_total"] == 12
    assert done["error"] == ""


# ---------------------------------------------------------------- chạy cả hàng việc

def test_runs_all_steps_sequentially(isolated_projects_dir):
    case_id = _start()
    llm, calls = make_fake_llm()

    assert _drain(llm) == 12

    assert calls == FULL_ORDER
    pipeline = _pipeline(case_id)
    assert pipeline.status == "done"
    assert [s.id for s in pipeline.steps] == [
        "extract_00", "extract_01", "cluster", "aliases", "outline", "write_vi_p1", "write_en_p1", "write_prompts_p1",
        "write_vi_p2", "write_en_p2", "write_prompts_p2", "assemble",
    ]
    assert all(s.status == "done" and s.attempts == 1 and s.error == "" for s in pipeline.steps)
    assert all(case_store.load_step_output(case_id, s.id) is not None for s in pipeline.steps)
    plan = case_store.load_plan(case_id)
    assert plan is not None and len(plan.scenes) == 7
    assert asyncio.run(run_next_step(llm=llm)) is False


def test_restart_resumes_without_repeating(isolated_projects_dir):
    case_id = _start()
    llm, calls = make_fake_llm()
    for _ in range(4):
        assert asyncio.run(run_next_step(llm=llm)) is True
    assert calls == FULL_ORDER[:4]

    pipeline = _pipeline(case_id)                       # server tắt giữa lúc đang chạy việc thứ 5
    pipeline.steps[4].status = "running"
    case_store.save_pipeline(pipeline)

    assert recover_interrupted() == 1
    assert _pipeline(case_id).steps[4].status == "pending"
    _drain(llm)

    assert _pipeline(case_id).status == "done"
    for marker in FULL_ORDER[:4]:
        assert calls.count(marker) == 1, marker
    assert calls == FULL_ORDER
    assert case_store.load_plan(case_id) is not None


def test_cancelled_step_stays_running_then_recovered(isolated_projects_dir):
    """Tắt server (huỷ task worker) lúc LLM đang chạy: việc còn `running` trên đĩa, khởi động lại thì chạy lại việc đó."""
    case_id = _start()
    base, calls = make_fake_llm()
    for _ in range(4):
        asyncio.run(run_next_step(llm=base))

    async def hanging_llm(system, user, **kwargs):
        calls.append("treo")
        await asyncio.Event().wait()                      # không bao giờ trả lời

    async def main():
        task = asyncio.create_task(run_next_step(llm=hanging_llm))
        await _wait_until(lambda: "treo" in calls, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    outline = _pipeline(case_id).steps[4]
    assert (outline.id, outline.status, outline.attempts) == ("outline", "running", 1)

    assert recover_interrupted() == 1
    _drain(base)
    pipeline = _pipeline(case_id)
    assert pipeline.status == "done"
    assert pipeline.steps[4].attempts == 2
    assert [c for c in calls if c != "treo"] == FULL_ORDER


def test_recover_interrupted_counts_only_running(isolated_projects_dir):
    assert recover_interrupted() == 0
    case_id = _start()
    assert recover_interrupted() == 0
    pipeline = _pipeline(case_id)
    pipeline.steps[0].status = "done"
    pipeline.steps[1].status = "running"
    case_store.save_pipeline(pipeline)
    assert recover_interrupted() == 1
    assert [s.status for s in _pipeline(case_id).steps[:2]] == ["done", "pending"]


# ---------------------------------------------------------------- hỏng và thử lại

def test_failure_stops_then_resume(isolated_projects_dir):
    case_id = _start()
    llm, calls = make_fake_llm({"WRITE_VI p1": _thin_write_vi()})   # mỏng cả 3 lần

    _drain(llm)

    pipeline = _pipeline(case_id)
    assert pipeline.status == "failed"
    failed = [s for s in pipeline.steps if s.status == "failed"]
    assert [s.id for s in failed] == ["write_vi_p1"]
    assert "lời Việt" in failed[0].error
    progress = pipeline_progress(pipeline)
    assert progress["status"] == "failed"
    assert progress["step_label"] == "Dừng ở bước viết lời Việt, nhịp 1/2"
    assert "lời Việt" in progress["error"]
    assert progress["error"] == failed[0].error
    assert "WRITE_EN p1" not in calls
    assert asyncio.run(run_next_step(llm=llm)) is False          # hàng việc hỏng không tự chạy tiếp

    resumed = resume_pipeline(case_id)
    assert resumed.status == "running"
    step = next(s for s in resumed.steps if s.id == "write_vi_p1")
    assert (step.status, step.attempts, step.error) == ("pending", 0, "")
    assert _pipeline(case_id) == resumed

    fixed, fixed_calls = make_fake_llm()                        # bỏ override
    _drain(fixed)
    assert _pipeline(case_id).status == "done"
    assert fixed_calls == FULL_ORDER[5:]                        # chạy tiếp từ đúng việc hỏng
    assert len(case_store.load_plan(case_id).scenes) == 7


def test_stale_running_step_stops_case_instead_of_skipping_ahead(isolated_projects_dir):
    """Việc còn `running` mà không được recover (lần trước không lưu được kết quả): không chạy vượt qua nó."""
    case_id = _start()
    pipeline = _pipeline(case_id)
    pipeline.steps[0].status = "running"
    case_store.save_pipeline(pipeline)
    llm, calls = make_fake_llm()

    assert asyncio.run(run_next_step(llm=llm)) is False
    assert calls == []
    pipeline = _pipeline(case_id)
    assert pipeline.status == "failed"
    assert pipeline.steps[0].status == "failed" and "Thử lại" in pipeline.steps[0].error
    assert [s.status for s in pipeline.steps[1:]] == ["pending"] * 4

    resume_pipeline(case_id)
    _drain(llm)
    assert _pipeline(case_id).status == "done"
    assert calls == FULL_ORDER


def test_result_save_error_fails_step_then_resume(isolated_projects_dir, monkeypatch):
    case_id = _start()
    real_save = case_store.save_step_output
    state = {"fail": True}

    def flaky_save(cid, step_id, data):
        if state["fail"]:
            state["fail"] = False
            raise OSError("đĩa đầy (giả)")
        return real_save(cid, step_id, data)

    monkeypatch.setattr(case_store, "save_step_output", flaky_save)
    llm, calls = make_fake_llm()
    assert asyncio.run(run_next_step(llm=llm)) is True

    pipeline = _pipeline(case_id)
    assert pipeline.status == "failed"
    error = pipeline.steps[0].error
    assert "không lưu được kết quả" in error and "OSError" in error and "đọc đoạn 1/2" in error

    resume_pipeline(case_id)
    _drain(llm)
    assert _pipeline(case_id).status == "done"
    assert calls.count("EXTRACT 0") == 2                       # kết quả lần đầu không lưu được nên chạy lại


def test_resume_unknown_case_raises(isolated_projects_dir):
    with pytest.raises(CaseNotFoundError):
        resume_pipeline("case_00000000")
    assert issubclass(CaseNotFoundError, LookupError)


def test_failed_case_does_not_block_newer_case(isolated_projects_dir, monkeypatch):
    old, new = _older_and_newer(monkeypatch)
    llm, _calls = make_fake_llm({"WRITE_VI p1": _thin_write_vi()})
    _drain(llm)
    assert _pipeline(old).status == "failed"
    assert _pipeline(new).status == "failed"                    # cùng override nên vụ mới cũng hỏng ở cùng việc

    resume_pipeline(new)
    fixed, fixed_calls = make_fake_llm()
    _drain(fixed)
    assert _pipeline(new).status == "done"
    assert _pipeline(old).status == "failed"


# ---------------------------------------------------------------- lỗi ngoài dự kiến

def test_unexpected_error_in_step_fails_pipeline(isolated_projects_dir, monkeypatch):
    monkeypatch.setattr(config, "NINEROUTER_API_KEY", "sk-test-bi-mat")
    case_id = _start()

    async def broken(pipeline, step, *, llm=None):
        raise RuntimeError("ổ đĩa giả bị hỏng (sk-test-bi-mat)")

    monkeypatch.setattr(case_adaptation_steps, "run_step", broken)
    assert asyncio.run(run_next_step()) is True

    pipeline = _pipeline(case_id)
    assert pipeline.status == "failed"
    step = pipeline.steps[0]
    assert step.status == "failed"
    assert "RuntimeError" in step.error and "ổ đĩa giả bị hỏng" in step.error
    assert "sk-test-bi-mat" not in step.error                   # không lộ key
    assert pipeline_progress(pipeline)["error"] == step.error
    assert asyncio.run(run_next_step()) is False


def test_unexpected_error_does_not_stop_worker_loop(isolated_projects_dir, monkeypatch):
    first, second = _older_and_newer(monkeypatch)
    real_run_step = case_adaptation_steps.run_step

    async def flaky(pipeline, step, *, llm=None):
        if pipeline.case_id == first and step.id == "cluster":
            raise RuntimeError("lỗi lập trình giả")
        return await real_run_step(pipeline, step, llm=llm)

    llm, _calls = make_fake_llm()
    monkeypatch.setattr(case_adaptation_steps, "run_step", flaky)
    monkeypatch.setattr(case_adaptation_llm, "call_llm_json", llm)

    _run_loop_until_settled([first, second])

    broken = _pipeline(first)
    assert broken.status == "failed"
    assert [s.status for s in broken.steps] == ["done", "done", "failed", "pending", "pending"]
    assert "RuntimeError" in pipeline_progress(broken)["error"]
    assert _pipeline(second).status == "done"
    assert case_store.load_plan(second) is not None


def test_worker_loop_survives_error_outside_steps(isolated_projects_dir, monkeypatch):
    """Lỗi ngay trong một vòng lặp (ví dụ đọc đĩa hỏng một lúc) thì ghi log rồi chạy tiếp ở vòng sau."""
    case_id = _start()
    real_next = case_worker.run_next_step
    state = {"calls": 0}

    async def flaky_next(**kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise OSError("ổ đĩa tạm thời không đọc được")
        return await real_next(**kwargs)

    llm, _calls = make_fake_llm()
    monkeypatch.setattr(case_worker, "run_next_step", flaky_next)
    monkeypatch.setattr(case_adaptation_llm, "call_llm_json", llm)

    _run_loop_until_settled([case_id])

    assert state["calls"] > 1
    assert _pipeline(case_id).status == "done"


# ---------------------------------------------------------------- một lần gọi LLM mỗi lúc

def test_one_llm_call_at_a_time(isolated_projects_dir, monkeypatch):
    older, newer = _older_and_newer(monkeypatch)
    assert [p.case_id for p in case_store.list_pipelines()] == [older, newer]
    base, calls = make_fake_llm()
    state = {"active": 0, "peak": 0}
    owners: list[str] = []

    async def slow_llm(system, user, **kwargs):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        try:
            running = [p.case_id for p in case_store.list_pipelines()
                       if any(s.status == "running" for s in p.steps)]
            assert len(running) == 1
            owners.append(running[0])
            await asyncio.sleep(0.01)
            return await base(system, user, **kwargs)
        finally:
            state["active"] -= 1

    monkeypatch.setattr(case_adaptation_llm, "call_llm_json", slow_llm)

    _run_loop_until_settled([older, newer])

    assert state["peak"] == 1
    # Vụ cũ chạy tới dàn ý rồi chờ duyệt; trong lúc đó vụ mới chạy tiếp tới dàn ý. Duyệt cả hai thì vụ cũ viết xong
    # hẳn rồi mới tới vụ mới.
    assert owners == [older] * 5 + [newer] * 5 + [older] * 6 + [newer] * 6
    assert calls == FULL_ORDER[:5] * 2 + FULL_ORDER[5:] * 2
    for case_id in (older, newer):
        assert _pipeline(case_id).status == "done"
        assert len(case_store.load_plan(case_id).scenes) == 7


def test_overlapping_run_next_step_returns_false_without_touching_state(isolated_projects_dir):
    case_id = _start()
    base, calls = make_fake_llm()
    release = asyncio.Event()

    async def held_llm(system, user, **kwargs):
        await release.wait()
        return await base(system, user, **kwargs)

    async def main():
        first = asyncio.create_task(run_next_step(llm=held_llm))
        await _wait_until(lambda: calls == [] and _pipeline(case_id).steps[0].status == "running", 5)
        before = _pipeline(case_id)
        assert await run_next_step(llm=base) is False            # gọi chồng: không làm gì
        assert _pipeline(case_id) == before                      # việc đang chạy giữ nguyên, attempts vẫn 1
        assert calls == []
        release.set()
        assert await first is True

    asyncio.run(main())
    pipeline = _pipeline(case_id)
    assert (pipeline.steps[0].status, pipeline.steps[0].attempts) == ("done", 1)
    assert pipeline.steps[1].status == "pending"
    assert calls == ["EXTRACT 0"]


def test_worker_loop_idles_and_stops(isolated_projects_dir):
    async def main():
        stop = asyncio.Event()
        task = asyncio.create_task(worker_loop(stop, idle_sleep=0.01))
        await asyncio.sleep(0.05)                               # không có việc: vòng lặp chờ, không lỗi
        assert not task.done()
        stop.set()
        await asyncio.wait_for(task, 2)

    asyncio.run(main())


# ---------------------------------------------------------------- duyệt dàn ý

def _outline(case_id: str) -> dict:
    return case_store.load_step_output(case_id, "outline")


def _edited_parts(case_id: str, **changes) -> list[dict]:
    """Các nhịp của dàn ý đã lưu dưới dạng gửi lên khi sửa; `changes`: {số thứ tự nhịp (0-based): {trường: giá trị}}."""
    parts = [{k: p[k] for k in ("kind", "summary_vi", "event_ids", "scene_count")} for p in _outline(case_id)["parts"]]
    for index, fields in changes.items():
        parts[int(index)].update(fields)
    return parts


def _in_review() -> tuple[str, list[str]]:
    case_id = _start()
    llm, calls = make_fake_llm()
    assert _drain(llm, approve=False) == 5
    return case_id, calls


def test_outline_waits_for_review_then_approve_runs_the_rest(isolated_projects_dir):
    case_id, calls = _in_review()

    assert calls == FULL_ORDER[:5]
    pipeline = _pipeline(case_id)
    assert pipeline.status == "review"
    assert [s.id for s in pipeline.steps][5:] == [
        "write_vi_p1", "write_en_p1", "write_prompts_p1", "write_vi_p2", "write_en_p2", "write_prompts_p2", "assemble",
    ]
    assert all(s.status == "pending" for s in pipeline.steps[5:])
    assert _progress(case_id) == {"status": "review", "step_label": REVIEW_LABEL, "steps_done": 5,
                                  "steps_total": 12, "error": ""}
    llm, more_calls = make_fake_llm()
    assert asyncio.run(run_next_step(llm=llm)) is False           # chờ duyệt: worker không chạy tiếp
    assert more_calls == []

    approved = approve_outline(case_id)
    assert approved.status == "running"
    assert _pipeline(case_id) == approved
    assert _drain(llm) == 7
    assert more_calls == FULL_ORDER[5:]
    assert _pipeline(case_id).status == "done"
    assert case_store.load_plan(case_id) is not None


def test_resume_keeps_the_case_waiting_for_review(isolated_projects_dir):
    case_id, _calls = _in_review()
    assert resume_pipeline(case_id).status == "review"
    assert _pipeline(case_id).status == "review"


def test_outline_view_has_parts_timeline_with_fictional_names_and_limits(isolated_projects_dir):
    case_id, _calls = _in_review()

    view = outline_view(case_id)

    assert view["status"] == "review" and view["editable"] is True
    assert view["parts"] == _outline(case_id)["parts"]
    assert view["supported_minutes"] == 2 and view["target_minutes"] == 8
    assert view["total_scenes"] == {"min": 0, "max": 9}           # tư liệu chỉ đủ 2 phút: tối đa 9 cảnh
    assert sorted(view["scene_limits"], key=int) == [str(m) for m in range(1, 9)]
    assert view["scene_limits"]["2"] == view["total_scenes"]
    assert view["scene_limits"]["8"] == {"min": 34, "max": 47}     # đủ 8 phút: 35–40 cảnh kể cả miễn trừ, tối đa 48
    assert view["scenes_per_part"] == [2, 6]
    assert "resolution" not in view["part_kinds"] and "open_questions" in view["part_kinds"]   # vụ chưa phá
    assert view["solved"] is False
    assert view["logline_vi"] and view["title_vi"]
    bible = case_store.load_step_output(case_id, "aliases")
    assert [e["id"] for e in view["timeline"]] == [e["id"] for e in bible["timeline"]]
    text = repr(view)
    assert REAL_VICTIM not in text and "Hùng" not in text
    assert any("Trịnh Quang Vũ" in e["summary"] for e in view["timeline"])


def test_edit_outline_revalidates_renumbers_and_regenerates_steps(isolated_projects_dir):
    case_id, _calls = _in_review()
    parts = _edited_parts(case_id)
    hook, rest = parts[0], parts[1]
    moved = hook["event_ids"][4:]
    parts = [
        {**hook, "event_ids": hook["event_ids"][:4], "scene_count": 2},
        {"kind": "investigation", "summary_vi": f"Hai manh mối đầu tiên quanh cái chết của {REAL_VICTIM}.",
         "event_ids": moved, "scene_count": 2},
        rest,
    ]

    pipeline = edit_outline(case_id, parts)

    assert pipeline.status == "review"
    assert [s.id for s in pipeline.steps][5:] == [
        "write_vi_p1", "write_en_p1", "write_prompts_p1", "write_vi_p2", "write_en_p2", "write_prompts_p2",
        "write_vi_p3", "write_en_p3", "write_prompts_p3", "assemble",
    ]
    assert all(s.status == "pending" for s in pipeline.steps[5:])
    assert _pipeline(case_id) == pipeline
    saved = _outline(case_id)
    assert saved["supported_minutes"] == 2                         # giữ ước lượng tư liệu của bước dàn ý
    assert [p["id"] for p in saved["parts"]] == ["p1", "p2", "p3"]
    assert [p["kind"] for p in saved["parts"]] == ["hook", "investigation", "open_questions"]
    assert saved["parts"][1]["event_ids"] == moved
    assert REAL_VICTIM not in saved["parts"][1]["summary_vi"]       # tên thật trong tóm tắt đổi sang tên hư cấu
    assert "Trịnh Quang Vũ" in saved["parts"][1]["summary_vi"]
    assert outline_view(case_id)["parts"] == saved["parts"]


def test_edit_outline_is_used_by_the_writing_steps(isolated_projects_dir):
    case_id, _calls = _in_review()
    summary = "Những nghi vấn xoay quanh đối tác làm ăn và chiếc bật lửa bỏ lại ở hiện trường."
    edit_outline(case_id, _edited_parts(case_id, **{"1": {"kind": "investigation", "summary_vi": summary}}))
    approve_outline(case_id)
    llm, calls = make_fake_llm()

    _drain(llm)

    assert calls == FULL_ORDER[5:]
    plan = case_store.load_plan(case_id)
    assert plan.parts[1].kind == "investigation" and plan.parts[1].summary_vi == summary
    write_vi_p2 = next(p for p in llm.prompts if p.startswith("TASK: WRITE_VI p2"))
    assert summary in write_vi_p2


def test_edit_outline_rejected_by_outline_rules_changes_nothing(isolated_projects_dir):
    case_id, _calls = _in_review()
    before_pipeline, before_outline = _pipeline(case_id), _outline(case_id)

    with pytest.raises(OutlineEditError) as info:
        edit_outline(case_id, _edited_parts(case_id, **{"0": {"scene_count": 9}}))
    message = info.value.message
    assert "Nhịp 1 có 9 cảnh" in message and "từ 2 đến 6 cảnh" in message
    assert len(message.splitlines()) == 2                           # mỗi lỗi một dòng: số cảnh nhịp 1, tổng số cảnh
    for jargon in ("scene_count", "supported_minutes", "hook"):     # lời cho người dùng, không phải tên trường JSON
        assert jargon not in message

    parts = _edited_parts(case_id)
    parts[1]["event_ids"] = parts[1]["event_ids"][:-1]              # bỏ sót một sự việc
    with pytest.raises(OutlineEditError) as info:
        edit_outline(case_id, parts)
    assert "chưa nằm trong nhịp nào" in info.value.message

    with pytest.raises(OutlineEditError):
        edit_outline(case_id, [])
    assert _pipeline(case_id) == before_pipeline and _outline(case_id) == before_outline


def test_edit_outline_can_raise_the_minutes_the_material_supports(isolated_projects_dir):
    """Máy ước bài chỉ đủ 2 phút (tối đa 9 cảnh). Người dùng nâng lên 3 phút thì được tới 14 cảnh; quy tắc mỗi sự việc
    tối đa 2 cảnh vẫn giữ, nên không độn được."""
    case_id, _calls = _in_review()
    assert outline_view(case_id)["scene_limits"]["3"] == {"min": 0, "max": 14}
    longer = _edited_parts(case_id, **{"0": {"scene_count": 6}, "1": {"scene_count": 5}})   # 11 cảnh

    with pytest.raises(OutlineEditError) as info:
        edit_outline(case_id, longer)                               # vẫn 2 phút: quá 9 cảnh
    assert 'nâng ô "Bài đủ tư liệu cho' in info.value.message       # chỉ đúng ô cần sửa trên màn duyệt
    assert "supported_minutes" not in info.value.message

    edit_outline(case_id, longer, supported_minutes=3)

    assert _outline(case_id)["supported_minutes"] == 3
    view = outline_view(case_id)
    assert view["supported_minutes"] == 3 and view["total_scenes"] == {"min": 0, "max": 14}
    assert [p["scene_count"] for p in view["parts"]] == [6, 5]

    for bad in (0, 9):                                              # 1..số phút đã chọn (8)
        with pytest.raises(OutlineEditError) as info:
            edit_outline(case_id, longer, supported_minutes=bad)
        assert "từ 1 đến 8 phút" in info.value.message
    assert _outline(case_id)["supported_minutes"] == 3


def test_approve_regenerates_writing_steps_from_the_saved_outline(isolated_projects_dir):
    """Máy tắt giữa lúc lưu dàn ý đã sửa và lưu hàng việc: duyệt vẫn sinh việc viết cảnh khớp dàn ý đã lưu."""
    case_id, _calls = _in_review()
    outline = _outline(case_id)
    first, second = outline["parts"]
    outline["parts"] = [{**first, "event_ids": first["event_ids"][:3], "scene_count": 2},
                        {**first, "id": "p2", "kind": "setup", "event_ids": first["event_ids"][3:], "scene_count": 2},
                        {**second, "id": "p3"}]
    case_store.save_step_output(case_id, "outline", outline)

    pipeline = approve_outline(case_id)

    assert [s.id for s in pipeline.steps if s.kind == "write_vi"] == ["write_vi_p1", "write_vi_p2", "write_vi_p3"]
    assert pipeline.steps[-1].id == "assemble" and pipeline.status == "running"


def test_outline_review_only_while_waiting(isolated_projects_dir):
    case_id = _start()
    with pytest.raises(OutlineStateError):
        outline_view(case_id)                                       # chưa có dàn ý
    with pytest.raises(OutlineStateError):
        approve_outline(case_id)
    with pytest.raises(OutlineStateError):
        edit_outline(case_id, [])

    llm, _calls = make_fake_llm()
    _drain(llm, approve=False)
    parts = _edited_parts(case_id)
    approve_outline(case_id)
    with pytest.raises(OutlineStateError) as info:
        approve_outline(case_id)                                   # đã duyệt rồi
    assert "đã được duyệt" in info.value.message
    with pytest.raises(OutlineStateError):
        edit_outline(case_id, parts)
    view = outline_view(case_id)                                   # sau khi duyệt vẫn xem được, không sửa được
    assert view["status"] == "running" and view["editable"] is False

    for func, args in ((outline_view, ()), (approve_outline, ()), (edit_outline, ([],))):
        with pytest.raises(CaseNotFoundError):
            func("case_00000000", *args)


# ---------------------------------------------------------------- khởi động cùng app (main.py)

def _client():
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


def _hold_lock_in_child(path: Path):
    """Tiến trình con giữ khoá file `path` (như một server Story Studio khác đang chạy). Trả Popen; gọi kill khi xong."""
    import subprocess
    path.parent.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen(
        [sys.executable, "-c",
         "import sys, time; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
         "from runners.single_instance import try_lock_file; "
         "print(try_lock_file(Path(sys.argv[2])) is not None, flush=True); time.sleep(30)",
         str(BACKEND_DIR), str(path)],
        stdout=subprocess.PIPE, text=True,
    )
    assert child.stdout.readline().strip() == "True"
    return child


def _stop_child(child) -> None:
    child.kill()
    child.wait()


def _wait_lock_free(deadline_s: float = 5.0) -> None:
    # venv launcher trên Windows có một tiến trình con thật, tiến trình đó thoát chậm hơn một chút
    deadline = time.monotonic() + deadline_s
    while not case_worker.acquire_worker_lock():
        assert time.monotonic() < deadline, "khoá worker không được nhả sau khi tiến trình kia thoát"
        time.sleep(0.2)


def test_worker_lock_is_held_by_one_process_only(isolated_projects_dir):
    assert case_worker.acquire_worker_lock()
    assert case_worker.acquire_worker_lock()                        # gọi lại trong cùng tiến trình vẫn được
    case_worker.release_worker_lock()
    child = _hold_lock_in_child(case_worker.worker_lock_path())
    try:
        assert not case_worker.acquire_worker_lock()
    finally:
        _stop_child(child)
    _wait_lock_free()
    case_worker.release_worker_lock()
    assert case_store.list_pipelines() == []                        # file khoá không bị coi là một vụ án


def test_app_leaves_the_queue_alone_when_another_server_runs_the_worker(isolated_projects_dir, monkeypatch):
    events = []

    async def fake_loop(stop, idle_sleep=1.0):
        events.append("start")
        await stop.wait()

    monkeypatch.delenv("STORY_STUDIO_DISABLE_CASE_WORKER", raising=False)
    monkeypatch.setattr(case_worker, "recover_interrupted", lambda: events.append("recover") or 0)
    monkeypatch.setattr(case_worker, "worker_loop", fake_loop)
    child = _hold_lock_in_child(case_worker.worker_lock_path())
    try:
        with _client() as client:
            time.sleep(0.1)
            assert client.get("/favicon.ico").status_code == 204    # server vẫn chạy, chỉ không có worker
        assert events == []                                         # không đụng việc `running` của server kia
    finally:
        _stop_child(child)
    _wait_lock_free()
    case_worker.release_worker_lock()
    with _client():                                                 # server kia tắt: lần bật sau chạy worker
        deadline = time.monotonic() + 5
        while "start" not in events:
            assert time.monotonic() < deadline
            time.sleep(0.01)
    assert events[:2] == ["recover", "start"]
    assert case_worker.acquire_worker_lock()                        # tắt app thì khoá được nhả
    case_worker.release_worker_lock()


def test_app_does_not_start_worker_when_disabled(monkeypatch):
    started = []

    async def fake_loop(stop, idle_sleep=1.0):
        started.append(True)

    monkeypatch.setenv("STORY_STUDIO_DISABLE_CASE_WORKER", "1")
    monkeypatch.setattr(case_worker, "recover_interrupted", lambda: started.append("recover") or 0)
    monkeypatch.setattr(case_worker, "worker_loop", fake_loop)
    with _client():
        time.sleep(0.05)
    assert started == []


def test_app_recovers_then_starts_and_stops_worker(isolated_projects_dir, monkeypatch):
    events = []

    async def fake_loop(stop, idle_sleep=1.0):
        events.append("start")
        try:
            await stop.wait()
            events.append("stop")
        except asyncio.CancelledError:
            events.append("cancel")
            raise

    def fake_recover():
        events.append("recover")
        return 2

    monkeypatch.delenv("STORY_STUDIO_DISABLE_CASE_WORKER", raising=False)
    monkeypatch.setattr(case_worker, "recover_interrupted", fake_recover)
    monkeypatch.setattr(case_worker, "worker_loop", fake_loop)
    with _client():
        deadline = time.monotonic() + 5
        while "start" not in events:
            assert time.monotonic() < deadline
            time.sleep(0.01)
    assert events[:2] == ["recover", "start"]
    assert events[2] in ("stop", "cancel")                      # tắt app thì worker dừng


def test_app_starts_even_if_recover_fails(isolated_projects_dir, monkeypatch):
    events = []

    async def fake_loop(stop, idle_sleep=1.0):
        events.append("start")
        await stop.wait()

    def broken_recover():
        raise OSError("không đọc được _cases")

    monkeypatch.delenv("STORY_STUDIO_DISABLE_CASE_WORKER", raising=False)
    monkeypatch.setattr(case_worker, "recover_interrupted", broken_recover)
    monkeypatch.setattr(case_worker, "worker_loop", fake_loop)
    with _client() as client:
        deadline = time.monotonic() + 5
        while "start" not in events:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert client.get("/favicon.ico").status_code == 204
