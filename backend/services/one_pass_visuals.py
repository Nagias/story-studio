"""Nút "Tạo hình cho cả dự án" ở trang Cảnh (task B 15/11/2026): cảnh thường ra ảnh, cảnh cao trào ra video, một lần bấm.

Chủ dự án 15/11/2026: "generate thì cao trào sẽ ra video, còn lại thì là ảnh. Như vậy là generate 1 lần ăn ngay". Lưới 9
khung vẽ xong thì tự duyệt và làm clip luôn (`climax_video.run_scene_climax_video(auto_approve_grid=True)`, ghi
`grid_approved_by: "auto"`).

- `plan()`: không gọi Muse, không ghi gì: đếm ảnh còn thiếu, cảnh cao trào cần làm video, ước số lượt Muse, và điều kiện
  còn thiếu chặn từng cảnh cao trào (chưa có giọng đọc, nhân vật chưa có bảng duyệt) kèm trang cần tới. Dùng đúng các
  hàm kiểm của đường thật (`climax_video.scene_seconds`, `cast_for`, `scene_people_kinds`).
- `start()`: lượt chạy nền (một dự án một lượt), tuần tự: (a) ảnh còn thiếu của mọi cảnh có hình vẽ, (b) từng cảnh cao
  trào đủ điều kiện: lưới, tự duyệt, clip. Cảnh lỗi ghi vào `failed` kèm lý do rồi đi tiếp; cảnh thiếu điều kiện ghi vào
  `skipped`; nghỉ `PACE_SEC` giữa hai lượt Muse (như services/look_batch.py); "Dừng" dừng sau bước đang làm.

Việc vẽ một ảnh và làm video một cảnh do router truyền vào (`draw_image`, `run_climax`): router dùng đúng route tạo ảnh
cảnh của nút trên thẻ (qua khoá hình `services/scene_locks.py`, CLAUDE.md đường cấm 16) và đúng hàm Muse của luồng cao
trào. Module này không import routers/ và không tự ghi project.json.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional

from config import PROJECTS_DIR, STATIC_DIR
from models.schemas import Project, Scene
from security import is_within
from services import character_sheets as cs
from services import climax_video as cv
from services import project_service

logger = logging.getLogger("story_studio.one_pass_visuals")

PACE_SEC = 15   # nghỉ giữa hai lượt Muse, như look_batch.PACE_SEC (test đặt 0)

# Trang cần tới để gỡ điều kiện còn thiếu (mã trang của showPage() trong workspace.js)
PAGE_SCRIPT = ("script", "Kịch bản và giọng")
PAGE_LOOK = ("look", "Hình mẫu")

# Kết quả vẽ một ảnh: {"error": None | lời báo lỗi, "provider": ..., "fallback_reason": ... (đường ảnh tự rơi sang
# nguồn khác thì ghi lý do, không giấu: CLAUDE.md đường cấm 4)}
DrawImage = Callable[[str], Awaitable[dict]]
RunClimax = Callable[[str], Awaitable[dict]]   # trạng thái climax_video của cảnh sau lượt chạy


class OnePassBusy(RuntimeError):
    """Đang có lượt "Tạo hình cho cả dự án" (hoặc đang bắt đầu) cho dự án này."""


def scene_label(project: Project, scene: Scene) -> str:
    index = next((i for i, s in enumerate(project.scenes, 1) if s.id == scene.id), None)
    return f"Cảnh {index}" if index else scene.id


def _studio_path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else PROJECTS_DIR.parent / p


def has_image(project_id: str, scene: Scene) -> bool:
    """Cảnh đã có file ảnh trong thư mục dự án (cùng chỗ tìm như climax_video: image_path hoặc images/<scene_id>.jpg)."""
    candidates = [_studio_path(scene.image_path)] if scene.image_path else []
    candidates.append(project_service.get_scene_media_paths(project_id, scene.id)["image"])
    return any(c.is_file() and is_within(c, PROJECTS_DIR, STATIC_DIR) for c in candidates)


def _climax_check(project: Project, scene: Scene, kind: str) -> tuple[Optional[dict], int]:
    """(điều kiện còn thiếu hoặc None, số lượt Muse vẽ lưới cần cho cảnh). Cùng thứ tự kiểm như run_scene_climax_video."""
    state = cv.scene_state(scene)
    approved = bool(state.get("grid_approved"))
    has_grid = approved or (state.get("status") == cv.GRID_REVIEW and bool(state.get("grid_paths")))
    if approved:   # như run_scene_clips: tin cờ đã lưu khi grid đã duyệt
        needs_cast = not (state.get("landscape") is True or state.get("crowd") is True)
    else:
        needs_cast = kind == "cast"
    label = scene_label(project, scene)
    try:
        seconds = cv.scene_seconds(scene)
    except cv.ClimaxVideoError as e:
        return {"scene_id": scene.id, "label": label, "reason": e.message, "page": PAGE_SCRIPT[0],
                "page_label": PAGE_SCRIPT[1]}, 0
    if needs_cast:
        try:
            cv.cast_for(project, scene)
        except cv.ClimaxVideoError as e:
            return {"scene_id": scene.id, "label": label, "reason": e.message, "page": PAGE_LOOK[0],
                    "page_label": PAGE_LOOK[1]}, 0
        except (cs.CastError, ValueError) as e:   # danh sách nhân vật hỏng: đường thật cũng dừng ở đây
            return {"scene_id": scene.id, "label": label, "reason": str(e), "page": PAGE_LOOK[0],
                    "page_label": PAGE_LOOK[1]}, 0
    grids = 0 if (has_grid or not needs_cast) else len(cv.grid_plan(cv.clip_count(seconds)))
    return None, grids


def plan(project: Project) -> dict:
    """Kế hoạch của một lượt (không tốn gì). Cảnh cao trào = cảnh có `metadata.climax_video.status` mà chưa "ready"."""
    eligible = [s for s in project.scenes if cv.is_eligible(s)]
    climax = [s for s in eligible if cv.scene_state(s).get("status") and cv.scene_state(s).get("status") != "ready"]
    climax_ids = {s.id for s in climax}
    kinds = cv.scene_people_kinds(project, climax) if climax else {}
    need_image = [s for s in eligible if not has_image(project.id, s)]
    runnable: list[dict] = []
    missing: list[dict] = []
    grid_turns = 0
    for s in climax:
        problem, grids = _climax_check(project, s, kinds.get(s.id, "cast"))
        if problem:
            missing.append(problem)
            continue
        grid_turns += grids
        runnable.append({"scene_id": s.id, "label": scene_label(project, s), "grid_turns": grids,
                         "needs_image": s.id in {x.id for x in need_image}})
    images_normal = [s.id for s in need_image if s.id not in climax_ids]
    images_climax = [s.id for s in need_image if s.id in climax_ids]
    return {
        "images": len(need_image), "images_normal": len(images_normal), "images_climax": len(images_climax),
        "image_scene_ids": [s.id for s in need_image],
        "climax_total": len(climax), "climax_videos": len(runnable),
        "climax_scene_ids": [r["scene_id"] for r in runnable],
        "climax_ready": sum(1 for s in eligible if cv.scene_state(s).get("status") == "ready"),
        "grid_turns": grid_turns,
        # ảnh: 1 lượt / cảnh; cao trào: lưới (trừ phong cảnh, đám đông, lưới đã có) + 1 việc agent-video
        "muse_turns": len(need_image) + grid_turns + len(runnable),
        "missing": missing,
    }


# --------------------------------------------------------------------------------------------------- lượt chạy nền
@dataclass
class OnePassJob:
    total: int = 0
    done: int = 0
    phase: Optional[str] = None          # "images" | "climax" | None (đã xong)
    current: Optional[str] = None        # nhãn cảnh đang làm
    current_id: Optional[str] = None
    images_total: int = 0
    climax_total: int = 0
    images_done: list[str] = field(default_factory=list)
    videos_done: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)      # {scene_id, label, step "image"|"climax", error}
    skipped: list[dict] = field(default_factory=list)     # {scene_id, label, step, reason}
    fallbacks: list[dict] = field(default_factory=list)   # {scene_id, label, provider, reason}
    stop_requested: bool = False
    stopped: bool = False
    task: Optional[asyncio.Task] = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def as_json(self) -> dict:
        return {"running": self.running, "phase": self.phase, "done": self.done, "total": self.total,
                "current": self.current, "current_id": self.current_id, "images_total": self.images_total,
                "climax_total": self.climax_total, "images_done": list(self.images_done),
                "videos_done": list(self.videos_done), "failed": list(self.failed), "skipped": list(self.skipped),
                "fallbacks": list(self.fallbacks), "stop_requested": self.stop_requested, "stopped": self.stopped}


_jobs: dict[str, OnePassJob] = {}
# Giữ chỗ từ lúc kiểm tới lúc tạo task (qua các lần await đọc đĩa): bấm đúp thì lần thứ hai 409, không chạy hai lượt
_starting: set[str] = set()


def is_running(project_id: str) -> bool:
    job = _jobs.get(project_id)
    return project_id in _starting or (job is not None and job.running)


def status(project_id: str) -> dict:
    job = _jobs.get(project_id)
    return job.as_json() if job else OnePassJob().as_json()


def reserve(project_id: str) -> None:
    """Gọi liền sau khi kiểm, không có await ở giữa; luôn kèm `release()` trong finally."""
    if is_running(project_id):
        raise OnePassBusy("Đang tạo hình cho cả dự án này, chờ xong hoặc bấm Dừng")
    _starting.add(project_id)


def release(project_id: str) -> None:
    _starting.discard(project_id)


def request_stop(project_id: str) -> dict:
    job = _jobs.get(project_id)
    if job is not None and job.running:
        job.stop_requested = True
    return status(project_id)


async def _pace(job: OnePassJob, used_muse: bool) -> bool:
    """Nghỉ giữa hai lượt Muse; trả True nếu người dùng bấm Dừng trong lúc nghỉ."""
    if used_muse and PACE_SEC > 0:
        await asyncio.sleep(PACE_SEC)
    if job.stop_requested:
        job.stopped = True
    return job.stop_requested


def _reload(project_id: str) -> Project:
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không còn dự án {project_id}")
    return project


def _scene(project: Project, scene_id: str) -> Optional[Scene]:
    return next((s for s in project.scenes if s.id == scene_id), None)


async def _image_phase(job: OnePassJob, project_id: str, items: list[tuple[str, str]], draw_image: DrawImage) -> bool:
    """Vẽ lần lượt ảnh còn thiếu. Trả True nếu đã dừng theo yêu cầu."""
    used_muse = False
    for scene_id, label in items:
        if (used_muse or job.stop_requested) and await _pace(job, used_muse):
            return True
        used_muse = False
        job.current, job.current_id = label, scene_id
        try:
            project = await asyncio.to_thread(_reload, project_id)
            scene = _scene(project, scene_id)
            if scene is None:
                job.skipped.append({"scene_id": scene_id, "label": label, "step": "image",
                                    "reason": "Cảnh không còn trong dự án"})
                continue
            if await asyncio.to_thread(has_image, project_id, scene):   # người dùng đã tự tạo ảnh trong lúc chờ
                job.skipped.append({"scene_id": scene_id, "label": label, "step": "image",
                                    "reason": "Cảnh đã có ảnh"})
                continue
            used_muse = True
            result = await draw_image(scene_id) or {}
            error = result.get("error")
        except Exception as e:   # lỗi ngoài dự kiến của một cảnh: ghi lại, đi tiếp (không im lặng)
            logger.exception(f"Tạo hình cả dự án {project_id}: ảnh {scene_id} lỗi ngoài dự kiến")
            result, error = {}, f"Lỗi ngoài dự kiến: {type(e).__name__}: {e}"
        finally:
            job.done += 1
        if error:
            job.failed.append({"scene_id": scene_id, "label": label, "step": "image", "error": str(error)})
            continue
        job.images_done.append(scene_id)
        if result.get("fallback_reason"):
            job.fallbacks.append({"scene_id": scene_id, "label": label, "provider": result.get("provider"),
                                  "reason": str(result["fallback_reason"])})
    return job.stop_requested and job.stopped


def _climax_blocker(project_id: str, scene_id: str) -> Optional[str]:
    """Lý do chưa làm được cảnh cao trào lúc tới lượt (None = làm được). Ảnh cảnh kiểm ở đây (pha ảnh có thể lỗi)."""
    project = _reload(project_id)
    scene = _scene(project, scene_id)
    if scene is None or not cv.is_eligible(scene):
        return "Cảnh không còn trong dự án hoặc không còn là cảnh có hình vẽ"
    st = cv.scene_state(scene).get("status")
    if not st:
        return "Cảnh đã bị tắt khỏi danh sách làm video"
    if st == "ready":
        return "Cảnh đã có video cao trào"
    problem, _ = _climax_check(project, scene, cv.scene_people_kind(project, scene))
    if problem:
        return problem["reason"]
    if not has_image(project_id, scene):
        return "Cảnh chưa có ảnh (tạo ảnh ở bước trước bị lỗi) nên chưa làm video được"
    return None


async def _climax_phase(job: OnePassJob, project_id: str, items: list[tuple[str, str]], run_climax: RunClimax,
                        stop_words: tuple[str, ...], used_muse: bool) -> None:
    for k, (scene_id, label) in enumerate(items):
        if (used_muse or job.stop_requested) and await _pace(job, used_muse):
            return
        used_muse = False
        job.current, job.current_id = label, scene_id
        error: Optional[str] = None
        try:
            reason = await asyncio.to_thread(_climax_blocker, project_id, scene_id)
            if reason:
                job.skipped.append({"scene_id": scene_id, "label": label, "step": "climax", "reason": reason})
                continue
            used_muse = True
            state = await run_climax(scene_id) or {}
            if state.get("status") != "ready":
                error = str(state.get("error") or f"Cảnh dừng ở trạng thái {state.get('status') or 'không rõ'}")
        except Exception as e:   # lỗi ngoài dự kiến: cảnh đã được ghi "failed" ở climax_video; ghi lại, đi tiếp
            logger.exception(f"Tạo hình cả dự án {project_id}: video {scene_id} lỗi ngoài dự kiến")
            error = f"Lỗi ngoài dự kiến: {type(e).__name__}: {e}"
        finally:
            job.done += 1
        if not error:
            job.videos_done.append(scene_id)
            continue
        job.failed.append({"scene_id": scene_id, "label": label, "step": "climax", "error": error})
        if any(w in error for w in stop_words):   # không còn tài khoản video: cảnh sau chắc chắn lỗi, không thử tiếp
            for sid, lab in items[k + 1:]:
                job.skipped.append({"scene_id": sid, "label": lab, "step": "climax",
                                    "reason": f"Dừng làm video vì không còn tài khoản Muse video: {error}"})
                job.done += 1
            return


async def _run(job: OnePassJob, project_id: str, images: list[tuple[str, str]], climax: list[tuple[str, str]],
               draw_image: DrawImage, run_climax: RunClimax, stop_words: tuple[str, ...]) -> None:
    try:
        job.phase = "images"
        stopped = await _image_phase(job, project_id, images, draw_image)
        if not stopped and not job.stop_requested:
            job.phase = "climax"
            await _climax_phase(job, project_id, climax, run_climax, stop_words, used_muse=bool(images))
        elif job.stop_requested:
            job.stopped = True
    finally:
        job.phase = None
        job.current = job.current_id = None


def start(project_id: str, project_plan: dict, project: Project, draw_image: DrawImage, run_climax: RunClimax,
          stop_words: tuple[str, ...] = ()) -> OnePassJob:
    """Tạo task nền theo `project_plan` (kết quả `plan()`); gọi khi đã `reserve()`. Cảnh cao trào thiếu điều kiện
    ghi ngay vào `skipped` kèm lý do (giao diện cho chọn "Chạy phần làm được")."""
    by_id = {s.id: s for s in project.scenes}

    def label(sid: str) -> str:
        return scene_label(project, by_id[sid]) if sid in by_id else sid

    images = [(sid, label(sid)) for sid in project_plan["image_scene_ids"]]
    climax = [(sid, label(sid)) for sid in project_plan["climax_scene_ids"]]
    job = OnePassJob(total=len(images) + len(climax), images_total=len(images), climax_total=len(climax))
    job.skipped = [{"scene_id": m["scene_id"], "label": m["label"], "step": "climax", "reason": m["reason"]}
                   for m in project_plan["missing"]]
    job.task = asyncio.create_task(_run(job, project_id, images, climax, draw_image, run_climax, stop_words))
    _jobs[project_id] = job
    return job
