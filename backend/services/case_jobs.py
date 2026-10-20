"""
Job trong bộ nhớ cho việc ngắn: tạo bản ngôn ngữ khác của một dự án (spec 7.8).

Phân tích vụ án thì không dùng cái này: nó chạy qua hàng việc lưu trên đĩa (case_worker) để tắt server giữa chừng vẫn
chạy tiếp được. Job ở đây chỉ nằm trong RAM (kiểu `active_renders`): tắt server lúc đang chạy thì người dùng bấm lại.

Một job là dict {job_id, kind, key, status, result, error, created_at, updated_at}; status là running, done hoặc
failed. `key` (có thể None) nói job làm việc gì, vd. "proj_x:en": start_job không tạo job thứ hai cùng kind và key khi
job trước còn chạy, nên bấm lại hay tải lại trang giữa chừng không sinh việc trùng.
Giữ tối đa MAX_JOBS job: quá thì bỏ job đã xong (done/failed) cũ nhất trước, không bao giờ bỏ job đang chạy.
"""
import copy
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

MAX_JOBS = 200
STATUSES = ("running", "done", "failed")
_IMMUTABLE = ("kind", "key", "created_at")      # job_id là tham số vị trí nên không thể nằm trong **fields

_lock = threading.Lock()
_jobs: "OrderedDict[str, dict]" = OrderedDict()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evict() -> None:
    """Gọi khi đang giữ _lock."""
    for job_id in [j for j, job in _jobs.items() if job["status"] != "running"]:
        if len(_jobs) <= MAX_JOBS:
            return
        del _jobs[job_id]


def _create(kind: str, key: Optional[str]) -> str:
    """Gọi khi đang giữ _lock."""
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    while job_id in _jobs:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
    now = _now()
    _jobs[job_id] = {"job_id": job_id, "kind": kind, "key": key, "status": "running", "result": None, "error": "",
                     "created_at": now, "updated_at": now}
    _evict()
    return job_id


def _running(kind: str, key: str) -> Optional[dict]:
    """Gọi khi đang giữ _lock."""
    return next((j for j in _jobs.values() if j["kind"] == kind and j["key"] == key and j["status"] == "running"), None)


def create_job(kind: str) -> str:
    """Tạo job đang chạy; trả job_id dạng `job_<8 hex>`."""
    with _lock:
        return _create(kind, None)


def start_job(kind: str, key: str) -> tuple[str, bool]:
    """Job đang chạy cùng `kind` và `key` nếu có, không thì tạo job mới. Trả (job_id, True nếu vừa tạo)."""
    with _lock:
        job = _running(kind, key)
        if job is not None:
            return job["job_id"], False
        return _create(kind, key), True


def find_running_job(kind: str, key: str) -> Optional[dict]:
    """Bản sao của job đang chạy cùng `kind` và `key`, hoặc None."""
    with _lock:
        job = _running(kind, key)
        return copy.deepcopy(job) if job is not None else None


def update_job(job_id: str, **fields) -> None:
    """Đổi các field của job (status, result, error). Job không có thì KeyError; status lạ hoặc đổi định danh thì
    ValueError."""
    if any(key in _IMMUTABLE for key in fields):
        raise ValueError(f"Không đổi được {', '.join(k for k in fields if k in _IMMUTABLE)} của job.")
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"status phải là một trong {STATUSES}, nhận {fields['status']!r}.")
    with _lock:
        job = _jobs[job_id]
        job.update(copy.deepcopy(fields))
        job["updated_at"] = _now()
        _evict()


def get_job(job_id: str) -> Optional[dict]:
    """Bản sao của job, hoặc None nếu không có."""
    with _lock:
        job = _jobs.get(job_id)
        return copy.deepcopy(job) if job is not None else None
