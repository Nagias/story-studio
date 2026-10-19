"""
Lưu trữ phân tích vụ án trên đĩa: projects/_cases/<case_id>/

    source.txt            bài gốc
    chunks.json           các đoạn đã cắt
    pipeline.json         hàng việc (CasePipeline)
    steps/<step_id>.json  kết quả từng việc
    plan.json             kế hoạch hoàn chỉnh (CaseAdaptationPlan)

Thư mục `_cases` không có project.json nên list_projects() không thấy.
Mọi file ghi UTF-8, ghi qua file tạm rồi đổi tên để tắt máy giữa chừng không để lại file cụt.
Đọc/đổi tên gặp PermissionError (Windows khoá file vài ms khi luồng khác đang đọc/ghi) thì tự thử lại.
Id không an toàn (case_id, step_id) thì raise ValueError.
"""
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from models.case_adaptation_schemas import CaseAdaptationPlan, CasePipeline
from security import is_safe_id, require_safe_id
from services import project_service

logger = logging.getLogger(__name__)

_TRIES = 8           # số lần thử khi file đang bị khoá (chỉ tốn thời gian khi thật sự bị khoá)
_RETRY_DELAY = 0.02  # giây chờ sau lần thử đầu, tăng tuyến tính ở các lần sau (20, 40, ... 140 ms)


def cases_dir() -> Path:
    # Đọc PROJECTS_DIR lúc gọi để test đổi được sang thư mục tạm.
    return project_service.PROJECTS_DIR / "_cases"


def new_case_id() -> str:
    return f"case_{uuid.uuid4().hex[:8]}"


def _safe(value: object, field: str) -> str:
    try:
        return require_safe_id(value, field)
    except HTTPException as exc:
        raise ValueError(f"{field} không hợp lệ: {value!r}") from exc


def _case_dir(case_id: str) -> Path:
    return cases_dir() / _safe(case_id, "case_id")


def _retry_if_locked(action):
    """Windows báo PermissionError khi file đang bị tiến trình/luồng khác mở (đọc đúng lúc đổi tên,
    hoặc đổi tên đúng lúc có người đọc). Khoá chỉ kéo dài vài ms nên thử lại vài lần rồi mới báo lỗi."""
    for attempt in range(_TRIES):
        try:
            return action()
        except PermissionError:
            if attempt == _TRIES - 1:
                raise
            time.sleep(_RETRY_DELAY * (attempt + 1))  # chờ lâu dần


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        _retry_if_locked(lambda: os.replace(tmp, path))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _read_text(path: Path) -> Optional[str]:
    try:
        return _retry_if_locked(lambda: path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _write_json(path: Path, data) -> None:
    _write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def _read_json(path: Path):
    text = _read_text(path)
    return None if text is None else json.loads(text)


def save_plan(plan: CaseAdaptationPlan) -> None:
    _write_text(_case_dir(plan.case_id) / "plan.json", plan.model_dump_json(indent=2))


def load_plan(case_id: str) -> Optional[CaseAdaptationPlan]:
    text = _read_text(_case_dir(case_id) / "plan.json")
    return None if text is None else CaseAdaptationPlan.model_validate_json(text)


def save_source(case_id: str, text: str) -> None:
    _write_text(_case_dir(case_id) / "source.txt", text)


def load_source(case_id: str) -> Optional[str]:
    return _read_text(_case_dir(case_id) / "source.txt")


def save_chunks(case_id: str, chunks: list[str]) -> None:
    _write_json(_case_dir(case_id) / "chunks.json", chunks)


def load_chunks(case_id: str) -> Optional[list[str]]:
    return _read_json(_case_dir(case_id) / "chunks.json")


def save_pipeline(pipeline: CasePipeline) -> None:
    _write_text(_case_dir(pipeline.case_id) / "pipeline.json", pipeline.model_dump_json(indent=2))


def load_pipeline(case_id: str) -> Optional[CasePipeline]:
    text = _read_text(_case_dir(case_id) / "pipeline.json")
    return None if text is None else CasePipeline.model_validate_json(text)


def list_pipelines() -> list[CasePipeline]:
    """Mọi hàng việc đọc được, cũ trước. Thư mục lạ, file hỏng hoặc file đang bị khoá thì bỏ qua và ghi log."""
    root = cases_dir()
    if not root.is_dir():
        return []
    found = []
    for d in root.iterdir():
        if not d.is_dir() or not is_safe_id(d.name):
            continue
        try:
            text = _read_text(d / "pipeline.json")
            if text is not None:
                found.append(CasePipeline.model_validate_json(text))
        except (OSError, ValueError) as exc:  # khoá/lỗi đọc; JSON hỏng hoặc sai schema (ValidationError là ValueError)
            logger.warning("Bỏ qua pipeline không đọc được %s: %s", d.name, exc)
    return sorted(found, key=lambda p: (p.created_at, p.case_id))


def _step_path(case_id: str, step_id: str) -> Path:
    return _case_dir(case_id) / "steps" / f"{_safe(step_id, 'step_id')}.json"


def save_step_output(case_id: str, step_id: str, data: dict) -> None:
    _write_json(_step_path(case_id, step_id), data)


def load_step_output(case_id: str, step_id: str) -> Optional[dict]:
    return _read_json(_step_path(case_id, step_id))
