"""Vẽ lần lượt mọi bảng nhân vật / ảnh chuẩn bối cảnh còn thiếu trong một lượt (trang Hình mẫu, task A6 15/11/2026).

Chủ dự án 15/11/2026: người dùng không nắm hết được số nhân vật, phải có nút cho AI tự làm. Mỗi lần vẽ vẫn là đúng
một lượt Muse như nút vẽ từng người (giao diện báo tổng số lượt trước khi chạy). Vẽ TUẦN TỰ, không song song: mỗi lượt
xong (hay lỗi) mới sang người sau; một cái lỗi thì ghi vào `failed` rồi đi tiếp, không báo xong giả.

Module này chỉ giữ trạng thái lượt chạy trong bộ nhớ (theo loại "characters"/"locations" và dự án) và vòng lặp;
việc vẽ một cái do router truyền vào (`draw_one`), dùng đúng hàm của nút vẽ từng cái. Không import routers/.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

logger = logging.getLogger("story_studio.look_batch")

PACE_SEC = 15   # nghỉ giữa hai lượt Muse, như MUSE_PACE_SEC của video cao trào (test đặt 0)

DrawOne = Callable[[str], Awaitable[Optional[str]]]    # vẽ một cái: None = xong, chuỗi = lời báo lỗi
StillNeeded = Callable[[str], Awaitable[bool]]          # tới lượt mà còn cần vẽ không (người dùng đã vẽ tay, đã xoá…)


class BatchBusy(RuntimeError):
    """Đang có lượt vẽ tất cả (hoặc đang bắt đầu) cho đúng loại và dự án này."""


@dataclass
class BatchJob:
    total: int = 0
    done: int = 0
    current: Optional[str] = None        # tên đang vẽ
    current_id: Optional[str] = None
    failed: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    drawn: list[str] = field(default_factory=list)
    stop_requested: bool = False
    stopped: bool = False
    task: Optional[asyncio.Task] = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def as_json(self) -> dict:
        return {"running": self.running, "done": self.done, "total": self.total, "current": self.current,
                "current_id": self.current_id, "failed": list(self.failed), "skipped": list(self.skipped),
                "drawn": list(self.drawn), "stop_requested": self.stop_requested, "stopped": self.stopped}


_jobs: dict[tuple[str, str], BatchJob] = {}
# Giữ chỗ từ lúc kiểm tới lúc tạo task (qua các lần await đọc đĩa): bấm đúp thì lần thứ hai 409, không vẽ hai lượt
_starting: set[tuple[str, str]] = set()


def is_running(kind: str, project_id: str) -> bool:
    job = _jobs.get((kind, project_id))
    return (kind, project_id) in _starting or (job is not None and job.running)


def status(kind: str, project_id: str) -> dict:
    job = _jobs.get((kind, project_id))
    return job.as_json() if job else BatchJob().as_json()


def reserve(kind: str, project_id: str) -> None:
    """Gọi liền sau khi kiểm, không có await ở giữa; luôn kèm `release()` trong finally."""
    if is_running(kind, project_id):
        raise BatchBusy("Đang vẽ tất cả cho dự án này, chờ xong hoặc bấm Dừng")
    _starting.add((kind, project_id))


def release(kind: str, project_id: str) -> None:
    _starting.discard((kind, project_id))


def request_stop(kind: str, project_id: str) -> dict:
    job = _jobs.get((kind, project_id))
    if job is not None and job.running:
        job.stop_requested = True
    return status(kind, project_id)


async def _run(job: BatchJob, items: list[tuple[str, str]], still_needed: StillNeeded, draw_one: DrawOne) -> None:
    for i, (item_id, name) in enumerate(items):
        if job.stop_requested:
            job.stopped = True
            break
        if i and PACE_SEC > 0:
            await asyncio.sleep(PACE_SEC)
            if job.stop_requested:
                job.stopped = True
                break
        job.current, job.current_id = name, item_id
        try:
            if not await still_needed(item_id):
                job.skipped.append(item_id)
                continue
            error = await draw_one(item_id)
        except Exception as e:   # lỗi ngoài dự kiến của một cái: ghi lại, đi tiếp cái sau (không im lặng)
            logger.exception(f"Vẽ tất cả: {item_id} lỗi ngoài dự kiến")
            error = f"Lỗi ngoài dự kiến: {e}"
        finally:
            job.done += 1
        if error:
            job.failed.append({"entity_id": item_id, "name": name, "error": error})
        else:
            job.drawn.append(item_id)
    job.current = job.current_id = None


def start(kind: str, project_id: str, items: list[tuple[str, str]], still_needed: StillNeeded,
          draw_one: DrawOne) -> BatchJob:
    """Tạo task nền vẽ lần lượt `items` [(id, tên)]; gọi khi đã `reserve()`."""
    job = BatchJob(total=len(items))
    job.task = asyncio.create_task(_run(job, items, still_needed, draw_one))
    _jobs[(kind, project_id)] = job
    return job
