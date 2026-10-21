"""
Worker chạy hàng việc phân tích vụ án ngay trong tiến trình server (spec 7.1a).

- start_analysis: kiểm bài gốc, lưu source.txt, chunks.json rồi pipeline.json (lưu sau cùng, nên worker không bao
  giờ thấy hàng việc thiếu bài gốc).
- run_next_step: chạy đúng MỘT việc của vụ cũ nhất còn việc chờ. Việc kế tiếp của một vụ là việc đầu tiên chưa
  `done`, nên các việc luôn chạy theo thứ tự. Trước khi chạy: `running`, `attempts += 1`, lưu. Xong: lưu kết quả
  vào steps/<step_id>.json, đánh dấu `done`, chèn các việc mới sinh ngay sau việc vừa xong; hết việc thì vụ `done`.
  Việc báo cần duyệt (dàn ý, StepResult.needs_review) thì vụ sang `review`: worker không chạy tiếp vụ đó.
- outline_view / edit_outline / approve_outline: màn duyệt dàn ý. Sửa (chỉ khi `review`) được kiểm bằng chính các quy
  tắc dàn ý, lưu đè steps/outline.json rồi sinh lại các việc viết cảnh; duyệt thì vụ về `running` (việc viết cảnh
  được sinh lại từ dàn ý đã lưu, nên máy tắt giữa hai lần ghi khi sửa cũng không lệch).
  Hỏng (StepFailed, hoặc lỗi ngoài dự kiến như lỗi lập trình, lỗi đọc ghi đĩa): việc và vụ thành `failed`, lưu
  thông báo tiếng Việt; vụ đó dừng, các vụ khác vẫn chạy.
- worker_loop: gọi run_next_step liên tục, hết việc thì nghỉ `idle_sleep` giây. Mọi lỗi trong một vòng đều được ghi
  log, vòng lặp không bao giờ chết vì lỗi. Chỉ có một worker_loop (main.py) nên mỗi lúc chỉ có một lần gọi LLM.
- acquire_worker_lock / release_worker_lock: khoá file của hệ điều hành trong projects/_cases, để chỉ một server chạy
  worker (và recover_interrupted) dù bật hai server, kể cả ở hai cổng khác nhau. Khoá tự nhả khi tiến trình chết.
- recover_interrupted: gọi lúc server khởi động; việc đang `running` (server tắt giữa chừng) về `pending`.
- resume_pipeline ("Thử lại"): việc `failed` về `pending`, attempts = 0; vụ chạy tiếp từ đúng việc đó.
- pipeline_progress: trạng thái cho giao diện, nhãn tiếng Việt kiểu "Đang đọc đoạn 2/5".

Đọc ghi đĩa (case_store) là hàm chặn, có thể chờ tới ~0,6 s khi Windows khoá file, nên phần async gọi chúng qua
asyncio.to_thread. Mọi thao tác đọc-sửa-ghi pipeline.json trong tiến trình đi qua một khoá chung (_lock), và kết
quả một việc được áp lên bản pipeline đọc lại từ đĩa (không ghi đè thay đổi mà API vừa làm trong lúc việc đang chạy).
"""
import asyncio
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import config
from models.case_adaptation_schemas import MAX_SOURCE_CHARS, CasePipeline, PipelineStep
from runners.single_instance import try_lock_file, unlock_file
from services import case_adaptation_steps, case_store
from services.case_adaptation_llm import LLMCall
from services.case_adaptation_steps import StepFailed, StepRejected, StepResult, chunk_source, initial_steps

logger = logging.getLogger(__name__)

_lock = threading.RLock()
# Chỉ một run_next_step chạy tại một thời điểm trong tiến trình (mọi event loop, mọi luồng). Lấy kiểu không chặn:
# lần gọi chồng trả False ngay. Nhả trong finally, kể cả khi task bị huỷ.
_RUN_GATE = threading.Lock()
_ERROR_DETAIL_CHARS = 300
_MAX_ERROR_SLEEP = 60.0       # nghỉ tối đa giữa hai vòng khi vòng lặp gặp lỗi liên tiếp
_INTERRUPTED = ("Việc này bị gián đoạn khi đang chạy (không lưu được kết quả lần trước). "
                "Bấm Thử lại để chạy lại việc này.")


class CaseInputError(ValueError):
    """Bài gốc không nhận được: rỗng (`empty`, API trả 400) hoặc quá dài (`too_long`, API trả 413)."""

    def __init__(self, reason: Literal["empty", "too_long"], message: str):
        super().__init__(message)
        self.reason = reason
        self.user_message = message


class CaseNotFoundError(LookupError):
    """Không có hàng việc của vụ án này."""


class OutlineStateError(Exception):
    """Chưa có dàn ý, hoặc dàn ý không ở trạng thái chờ duyệt (API trả 409). `message` tiếng Việt, không nêu tên."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class OutlineEditError(ValueError):
    """Dàn ý sửa không qua các quy tắc dàn ý (API trả 400). `message` có thể trích id hay chữ người dùng gửi lên nên
    router ẩn tên thật trước khi trả."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def worker_disabled() -> bool:
    """Tắt worker (test đặt STORY_STUDIO_DISABLE_CASE_WORKER=1 để không chạy hàng việc ngầm)."""
    return os.getenv("STORY_STUDIO_DISABLE_CASE_WORKER", "").strip().lower() in ("1", "true", "yes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _vn_number(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# ---------------------------------------------------------------- tạo hàng việc

def start_analysis(raw_report: str, target_minutes: int, visual_style: str, *, chunk_chars: int = 3000) -> str:
    """Lưu bài gốc, các đoạn và hàng việc ban đầu; trả case_id. Worker tự nhận và chạy."""
    text = raw_report or ""
    if not text.strip():
        raise CaseInputError("empty", "Bài gốc đang trống. Dán nội dung vụ án rồi bấm Phân tích.")
    if len(text) > MAX_SOURCE_CHARS:
        raise CaseInputError(
            "too_long",
            f"Bài gốc dài {_vn_number(len(text))} ký tự, vượt giới hạn {_vn_number(MAX_SOURCE_CHARS)} ký tự. "
            "Rút gọn bài (bỏ phần không liên quan tới vụ án) rồi thử lại.",
        )
    chunks = chunk_source(text, chunk_chars)
    case_id = case_store.new_case_id()
    while case_store.load_source(case_id) is not None:     # trùng id (rất hiếm) thì không ghi đè vụ cũ
        case_id = case_store.new_case_id()
    now = _now()
    pipeline = CasePipeline(
        case_id=case_id, target_minutes=target_minutes, visual_style=visual_style, chunk_chars=chunk_chars,
        created_at=now, updated_at=now, steps=initial_steps(len(chunks)),
    )
    case_store.save_source(case_id, text)
    case_store.save_chunks(case_id, chunks)
    case_store.save_pipeline(pipeline)
    return case_id


# ---------------------------------------------------------------- chạy một việc

def _next_step(pipeline: CasePipeline) -> Optional[PipelineStep]:
    """Việc đầu tiên chưa xong (các việc chạy đúng thứ tự trong hàng việc)."""
    return next((s for s in pipeline.steps if s.status != "done"), None)


def _claim_next() -> Optional[tuple[CasePipeline, PipelineStep]]:
    """Chọn vụ `running` cũ nhất có việc kế tiếp đang `pending`; đánh dấu việc đó `running`, attempts += 1, lưu."""
    with _lock:
        for pipeline in case_store.list_pipelines():
            if pipeline.status != "running":
                continue
            step = _next_step(pipeline)
            if step is None:                       # không còn việc nào: sửa trạng thái cho đúng
                pipeline.status = "done"
            elif step.status == "pending":
                step.status = "running"
                step.attempts += 1
                step.error = ""
                pipeline.updated_at = _now()
                case_store.save_pipeline(pipeline)
                return pipeline, step
            else:
                # `running` mà không phải do vòng này chạy (lần trước không lưu được kết quả), hoặc `failed` trong một
                # vụ còn `running`: dừng vụ để người dùng thấy và bấm Thử lại, thay vì chạy tiếp các việc sau nó.
                step.status = "failed"
                step.error = step.error or _INTERRUPTED
                pipeline.status = "failed"
                logger.warning("Vụ %s: việc %s ở trạng thái lạ, dừng vụ", pipeline.case_id, step.id)
            pipeline.updated_at = _now()
            case_store.save_pipeline(pipeline)
    return None


def _reload(case_id: str, step_id: str) -> Optional[tuple[CasePipeline, PipelineStep]]:
    pipeline = case_store.load_pipeline(case_id)
    step = next((s for s in pipeline.steps if s.id == step_id), None) if pipeline else None
    if step is None:
        logger.warning("Vụ %s: không còn việc %s trên đĩa, bỏ kết quả", case_id, step_id)
        return None
    return pipeline, step


def _finish_done(case_id: str, step_id: str, result: StepResult) -> None:
    case_store.save_step_output(case_id, step_id, result.output)   # có kết quả trên đĩa rồi mới đánh dấu xong
    with _lock:
        found = _reload(case_id, step_id)
        if found is None:
            return
        pipeline, step = found
        step.status = "done"
        step.error = ""
        existing = {s.id for s in pipeline.steps}
        new_steps = [s for s in result.new_steps if s.id not in existing]
        index = pipeline.steps.index(step)
        pipeline.steps[index + 1:index + 1] = new_steps
        if all(s.status == "done" for s in pipeline.steps):
            pipeline.status = "done"
        elif result.needs_review:
            pipeline.status = "review"
        pipeline.updated_at = _now()
        case_store.save_pipeline(pipeline)


def _finish_failed(case_id: str, step_id: str, message: str) -> None:
    with _lock:
        found = _reload(case_id, step_id)
        if found is None:
            return
        pipeline, step = found
        step.status = "failed"
        step.error = message
        pipeline.status = "failed"
        pipeline.updated_at = _now()
        case_store.save_pipeline(pipeline)


def _error_detail(exc: BaseException) -> str:
    """"Loại lỗi: nội dung" của một lỗi ngoài dự kiến, đã che API key và cắt ngắn."""
    detail = str(exc).strip()
    key = (config.NINEROUTER_API_KEY or "").strip()
    if key:
        detail = detail.replace(key, "***")
    detail = detail[:_ERROR_DETAIL_CHARS]
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


_REPORT_HINT = "Bấm Thử lại; nếu lặp lại, gửi thông báo này cho người phát triển."


async def run_next_step(*, llm: Optional[LLMCall] = None) -> bool:
    """Chạy một việc. Trả False khi không còn việc nào để chạy (mọi vụ đã xong, hỏng hoặc không có vụ nào), hoặc khi
    một run_next_step khác trong tiến trình đang chạy: lần gọi chồng đó không đọc, không ghi gì (nếu không, nó sẽ thấy
    việc đang `running` và tưởng là việc bị gián đoạn)."""
    if not _RUN_GATE.acquire(blocking=False):
        logger.warning("run_next_step đang chạy ở nơi khác trong tiến trình; bỏ qua lần gọi chồng")
        return False
    try:
        return await _run_one(llm)
    finally:
        _RUN_GATE.release()


async def _run_one(llm: Optional[LLMCall]) -> bool:
    claimed = await asyncio.to_thread(_claim_next)
    if claimed is None:
        return False
    pipeline, step = claimed
    case_id, step_id, phrase = pipeline.case_id, step.id, _step_phrase(pipeline, step)
    try:
        result = await case_adaptation_steps.run_step(pipeline, step, llm=llm)
    except StepFailed as exc:
        logger.warning("Vụ %s: việc %s hỏng: %s", case_id, step_id, exc.user_message)
        await asyncio.to_thread(_finish_failed, case_id, step_id, exc.user_message)
        return True
    except Exception as exc:    # lỗi lập trình, lỗi đọc ghi...: dừng vụ này, không làm chết worker
        logger.exception("Vụ %s: việc %s gặp lỗi ngoài dự kiến", case_id, step_id)
        message = f"Bước {phrase} gặp lỗi ngoài dự kiến ({_error_detail(exc)}). {_REPORT_HINT}"
        await asyncio.to_thread(_finish_failed, case_id, step_id, message)
        return True
    try:
        await asyncio.to_thread(_finish_done, case_id, step_id, result)
    except Exception as exc:
        logger.exception("Vụ %s: không lưu được kết quả việc %s", case_id, step_id)
        message = f"Bước {phrase} chạy xong nhưng không lưu được kết quả ({_error_detail(exc)}). {_REPORT_HINT}"
        await asyncio.to_thread(_finish_failed, case_id, step_id, message)
    return True


async def worker_loop(stop: asyncio.Event, idle_sleep: float = 1.0) -> None:
    """Chạy hàng việc cho tới khi `stop` được bật. Không có việc thì nghỉ `idle_sleep` giây; gặp lỗi thì ghi log,
    nghỉ lâu dần (tối đa _MAX_ERROR_SLEEP giây) rồi chạy tiếp."""
    errors = 0
    while not stop.is_set():
        try:
            worked = await run_next_step()
            errors = 0
        except Exception:
            errors += 1
            logger.exception("Worker phân tích vụ án gặp lỗi (lần %d liên tiếp); sẽ chạy tiếp", errors)
            worked = False
        if worked:
            continue
        pause = idle_sleep
        if errors:
            pause = min(idle_sleep * 2 ** min(errors - 1, 16), max(idle_sleep, _MAX_ERROR_SLEEP))
        try:
            await asyncio.wait_for(stop.wait(), timeout=pause)
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------- một server chạy worker

_worker_lock_guard = threading.Lock()
_worker_lock: Optional[tuple[Path, int]] = None          # (file khoá, fd) mà tiến trình này đang giữ


def worker_lock_path() -> Path:
    return case_store.cases_dir() / ".worker.lock"


def acquire_worker_lock() -> bool:
    """Giữ khoá hàng việc cho tiến trình này. True nếu đang giữ (gọi lại vẫn True), False nếu server khác đang giữ.
    Lỗi đĩa (không tạo được thư mục hay file khoá) thì ném OSError."""
    global _worker_lock
    path = worker_lock_path()
    with _worker_lock_guard:
        if _worker_lock is not None:
            if _worker_lock[0] == path:
                return True
            unlock_file(_worker_lock[1])                 # thư mục projects đã đổi (test): nhả khoá của thư mục cũ
            _worker_lock = None
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = try_lock_file(path)
        if fd is None:
            return False
        _worker_lock = (path, fd)
        return True


def release_worker_lock() -> None:
    global _worker_lock
    with _worker_lock_guard:
        if _worker_lock is None:
            return
        fd = _worker_lock[1]
        _worker_lock = None
        unlock_file(fd)


# ---------------------------------------------------------------- khởi động lại, thử lại

def recover_interrupted() -> int:
    """Gọi lúc server khởi động: việc đang `running` (bị tắt giữa chừng) về `pending`. Trả số việc đã đổi."""
    changed = 0
    with _lock:
        for pipeline in case_store.list_pipelines():
            running = [s for s in pipeline.steps if s.status == "running"]
            if not running:
                continue
            for step in running:
                step.status = "pending"
            changed += len(running)
            pipeline.updated_at = _now()
            case_store.save_pipeline(pipeline)
            logger.info("Vụ %s: %d việc bị gián đoạn sẽ chạy lại", pipeline.case_id, len(running))
    return changed


def _require_pipeline(case_id: str) -> CasePipeline:
    pipeline = case_store.load_pipeline(case_id)
    if pipeline is None:
        raise CaseNotFoundError(f"Không tìm thấy vụ án {case_id}.")
    return pipeline


def resume_pipeline(case_id: str) -> CasePipeline:
    """"Thử lại": việc `failed` về `pending` với attempts = 0, vụ chạy tiếp. Không có vụ thì CaseNotFoundError.
    Vụ đang chờ duyệt dàn ý thì vẫn chờ: Thử lại không thay cho việc duyệt."""
    with _lock:
        pipeline = _require_pipeline(case_id)
        for step in pipeline.steps:
            if step.status == "failed":
                step.status = "pending"
                step.attempts = 0
                step.error = ""
        if pipeline.status != "review":
            pipeline.status = "done" if all(s.status == "done" for s in pipeline.steps) else "running"
        pipeline.updated_at = _now()
        case_store.save_pipeline(pipeline)
        return pipeline


# ---------------------------------------------------------------- duyệt dàn ý

OUTLINE_NOT_READY = "Chưa có dàn ý: phân tích chưa tới bước lập dàn ý."
OUTLINE_APPROVED = "Dàn ý đã được duyệt và đang dùng để viết cảnh, không sửa hay duyệt lại được nữa."


def _outline_step(pipeline: CasePipeline) -> Optional[PipelineStep]:
    """Việc lập dàn ý nếu đã xong."""
    return next((s for s in pipeline.steps if s.kind == "build_outline" and s.status == "done"), None)


def _require_review(pipeline: CasePipeline) -> PipelineStep:
    outline = _outline_step(pipeline)
    if outline is None:
        raise OutlineStateError(OUTLINE_NOT_READY)
    if pipeline.status != "review":
        raise OutlineStateError(OUTLINE_APPROVED)
    return outline


def _replace_story_steps(pipeline: CasePipeline, outline: PipelineStep, steps: list[PipelineStep]) -> None:
    """Thay mọi việc sau việc lập dàn ý (khi chờ duyệt, đó là các việc viết cảnh và ráp, đều chưa chạy)."""
    index = pipeline.steps.index(outline)
    pipeline.steps[index + 1:] = steps
    pipeline.updated_at = _now()


def outline_view(case_id: str) -> dict:
    """Dàn ý và dòng thời gian cho màn duyệt (case_adaptation_steps.outline_review); `editable` chỉ True khi đang chờ
    duyệt. Chưa có dàn ý thì OutlineStateError."""
    pipeline = _require_pipeline(case_id)
    if _outline_step(pipeline) is None:
        raise OutlineStateError(OUTLINE_NOT_READY)
    try:
        return case_adaptation_steps.outline_review(pipeline)
    except StepFailed as exc:
        raise OutlineStateError(exc.user_message) from None


def edit_outline(case_id: str, parts: list[dict], supported_minutes: Optional[int] = None,
                 dropped: Optional[list[dict]] = None) -> CasePipeline:
    """Sửa dàn ý đang chờ duyệt: `parts` là toàn bộ các nhịp mới ({kind, summary_vi, event_ids, scene_count}),
    `supported_minutes` (tuỳ chọn) là số phút bài đủ tư liệu, `dropped` (tuỳ chọn) là các sự việc bỏ khỏi video
    ({event_id, reason}). Qua các quy tắc dàn ý thì lưu đè dàn ý và sinh lại các việc viết cảnh (vụ vẫn chờ duyệt);
    không qua thì OutlineEditError và không đổi gì."""
    with _lock:
        pipeline = _require_pipeline(case_id)
        outline = _require_review(pipeline)
        try:
            result = case_adaptation_steps.revise_outline(pipeline, parts, supported_minutes, dropped)
        except StepRejected as exc:
            raise OutlineEditError(exc.reason) from None
        except StepFailed as exc:
            raise OutlineStateError(exc.user_message) from None
        case_store.save_step_output(case_id, outline.id, result.output)
        _replace_story_steps(pipeline, outline, result.new_steps)
        case_store.save_pipeline(pipeline)
        return pipeline


def approve_outline(case_id: str) -> CasePipeline:
    """Duyệt dàn ý: sinh lại các việc viết cảnh từ dàn ý đã lưu, vụ về `running` để worker chạy tiếp."""
    with _lock:
        pipeline = _require_pipeline(case_id)
        outline = _require_review(pipeline)
        try:
            steps = case_adaptation_steps.outline_steps(pipeline)
        except StepFailed as exc:
            raise OutlineStateError(exc.user_message) from None
        _replace_story_steps(pipeline, outline, steps)
        pipeline.status = "running"
        case_store.save_pipeline(pipeline)
        return pipeline


# ---------------------------------------------------------------- tiến độ

REVIEW_LABEL = "Dàn ý xong, chờ bạn duyệt"
_STATIC_PHRASES = {
    "cluster_names": "gộp tên nhân vật",
    "assign_aliases": "đặt tên hư cấu",
    "dedupe_events": "lọc sự việc trùng",
    "build_outline": "lên dàn ý",
    "assemble": "ráp và kiểm tra",
}
_PART_PHRASES = {
    "write_vi": "viết lời Việt",
    "write_en": "viết lời Anh",
    "write_prompts": "viết prompt hình",
}


def _step_phrase(pipeline: CasePipeline, step: PipelineStep) -> str:
    """Tên việc dạng "đọc đoạn 2/5", "viết lời Việt, nhịp 1/2". Không bao giờ raise (params lạ thì dùng id việc)."""
    try:
        if step.kind == "extract_chunk":
            total = sum(1 for s in pipeline.steps if s.kind == "extract_chunk")
            return f"đọc đoạn {int(step.params.get('index', 0)) + 1}/{total}"
        if step.kind in _PART_PHRASES:
            same = [s.id for s in pipeline.steps if s.kind == step.kind]
            return f"{_PART_PHRASES[step.kind]}, nhịp {same.index(step.id) + 1}/{len(same)}"
    except (TypeError, ValueError):
        return step.id
    return _STATIC_PHRASES.get(step.kind, step.id)


def pipeline_progress(p: CasePipeline) -> dict:
    """{"status", "step_label", "steps_done", "steps_total", "error"} cho giao diện; vụ hỏng thì `error` là thông báo
    của việc hỏng."""
    done = sum(1 for s in p.steps if s.status == "done")
    current = next((s for s in p.steps if s.status == "running"), None) or _next_step(p)
    failed = next((s for s in p.steps if s.status == "failed"), None)
    if p.status == "failed":
        stopped_at = failed or current
        label = f"Dừng ở bước {_step_phrase(p, stopped_at)}" if stopped_at else "Phân tích bị dừng"
    elif p.status == "review":
        label = REVIEW_LABEL
    elif p.status == "done" or current is None:
        label = "Đã phân tích xong"
    else:
        label = f"Đang {_step_phrase(p, current)}"
    error = ""
    if p.status == "failed":
        error = (failed.error if failed else "") or "Phân tích bị dừng. Bấm Thử lại để chạy tiếp."
    return {"status": p.status, "step_label": label, "steps_done": done, "steps_total": len(p.steps), "error": error}
