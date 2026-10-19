"""
Worker chạy hàng việc phân tích vụ án (spec 7.1a).

- Mỗi lúc chỉ chạy một việc cho mọi vụ án, vụ cũ hơn trước; danh sách việc lớn dần sau dàn ý.
- Server khởi động lại: việc đang `running` trở về `pending`, việc đã `done` không gọi LLM lại.
- Việc hỏng thì hàng việc dừng; "Thử lại" (resume_pipeline) chạy tiếp từ đúng việc đó.
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


# ---------------------------------------------------------------- helpers

def _start(created_at: str = "") -> str:
    """Vụ án mẫu (2 đoạn với chunk_chars=900). `created_at` đặt tay để thứ tự vụ cũ/mới không phụ thuộc đồng hồ."""
    case_id = start_analysis(DOSSIER, 8, STYLE, chunk_chars=900)
    if created_at:
        pipeline = case_store.load_pipeline(case_id)
        pipeline.created_at = created_at
        case_store.save_pipeline(pipeline)
    return case_id


def _pipeline(case_id: str):
    return case_store.load_pipeline(case_id)


def _progress(case_id: str) -> dict:
    return pipeline_progress(_pipeline(case_id))


def _drain(llm, limit: int = 100) -> int:
    """Gọi run_next_step tới khi trả False (như worker); trả số việc đã chạy."""
    ran = 0
    while asyncio.run(run_next_step(llm=llm)):
        ran += 1
        assert ran < limit, "hàng việc không dừng"
    return ran


async def _wait_until(predicate, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "quá thời gian chờ"
        await asyncio.sleep(0.02)


def _run_loop_until_settled(case_ids: list[str], timeout: float = 30.0) -> None:
    """Chạy worker_loop cho tới khi mọi vụ trong `case_ids` không còn `running`, rồi dừng vòng lặp."""

    async def main():
        stop = asyncio.Event()
        task = asyncio.create_task(worker_loop(stop, idle_sleep=0.01))
        try:
            await _wait_until(lambda: all(_pipeline(c).status != "running" for c in case_ids), timeout)
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
        if not asyncio.run(run_next_step(llm=llm)):
            break

    assert labels[:-1] == ALL_LABELS
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


def test_failed_case_does_not_block_newer_case(isolated_projects_dir):
    old = _start("2026-10-19T10:00:00+00:00")
    new = _start("2026-10-19T10:00:01+00:00")
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
    first = _start("2026-10-19T10:00:00+00:00")
    second = _start("2026-10-19T10:00:01+00:00")
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
    older = _start("2026-10-19T10:00:00+00:00")
    newer = _start("2026-10-19T10:00:01+00:00")
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
    assert owners == [older] * len(FULL_ORDER) + [newer] * len(FULL_ORDER)   # vụ cũ xong hẳn rồi mới tới vụ mới
    assert calls == FULL_ORDER * 2
    for case_id in (older, newer):
        assert _pipeline(case_id).status == "done"
        assert len(case_store.load_plan(case_id).scenes) == 7


def test_worker_loop_idles_and_stops(isolated_projects_dir):
    async def main():
        stop = asyncio.Event()
        task = asyncio.create_task(worker_loop(stop, idle_sleep=0.01))
        await asyncio.sleep(0.05)                               # không có việc: vòng lặp chờ, không lỗi
        assert not task.done()
        stop.set()
        await asyncio.wait_for(task, 2)

    asyncio.run(main())


# ---------------------------------------------------------------- khởi động cùng app (main.py)

def _client():
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


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


def test_app_recovers_then_starts_and_stops_worker(monkeypatch):
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


def test_app_starts_even_if_recover_fails(monkeypatch):
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
