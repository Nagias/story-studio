"""
Language Versions Router (spec 7.8)
-----------------------------------
POST /api/projects/{project_id}/create-language-version  body {language="en", voice=None} -> {job_id, already_running}
GET  /api/projects/{project_id}/language-version-job?language=en -> {job}: việc đang chạy (hoặc null), để giao diện tải
     lại trang giữa chừng vẫn theo dõi tiếp được.

Tạo bản ngôn ngữ khác của một dự án đã dựng từ kế hoạch chuyển thể: chép ảnh và clip Muse, đổi lời kể, giọng, ảnh có chữ;
cảnh mới thêm hoặc đã sửa lời thì nhờ LLM viết lại lời Anh. Việc ngắn nên chạy qua BackgroundTasks, trạng thái nằm trong
bộ nhớ (services/case_jobs); giao diện hỏi GET /api/true-crime/jobs/{job_id}.

Xong: job `done`, result = {project_id, rewritten_orders}. Hỏng: job `failed`, error là thông báo tiếng Việt. Thông báo
không bao giờ chứa tên thật (LanguageVersionError vốn không nêu tên; thông báo của việc viết lại được ẩn tên).
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from models.case_adaptation_schemas import Lang
from security import validate_path_ids
from services import case_jobs, case_redact, project_service
from services.case_adaptation_steps import StepFailed
from services.case_project_builder import LanguageVersionError, create_language_version

logger = logging.getLogger("story_studio.language_versions")

router = APIRouter(prefix="/api/projects", tags=["Language versions"], dependencies=[Depends(validate_path_ids)])

JOB_KIND = "language_version"
STEP_ERROR_FALLBACK = "Việc viết lại lời Anh thất bại. Kiểm tra 9router rồi tạo lại; nếu lặp lại, xem nhật ký máy chủ."


class LanguageVersionRequest(BaseModel):
    language: Lang = "en"
    voice: Optional[str] = Field(default=None, max_length=100, description="Để trống thì dùng giọng nhớ sẵn hoặc mặc định")


def _case_id_of(project_id: str) -> Optional[str]:
    project = project_service.get_project(project_id)
    return project.metadata.get("case_id") if project is not None else None


async def _failure_message(project_id: str, exc: StepFailed) -> str:
    """Thông báo của việc hỏng (viết lại lời Anh) có thể trích dẫn chữ có tên thật: ẩn tên trước khi lưu vào job."""
    try:
        case_id = await asyncio.to_thread(_case_id_of, project_id)
    except Exception:
        logger.exception("Dự án %s: không đọc được case_id để ẩn tên trong thông báo lỗi", project_id)
        return STEP_ERROR_FALLBACK
    if not case_id:
        return STEP_ERROR_FALLBACK
    return await asyncio.to_thread(case_redact.hide_real_names, case_id, exc.user_message, STEP_ERROR_FALLBACK)


async def _run_job(job_id: str, project_id: str, language: str, voice: Optional[str]) -> None:
    """Chạy nền; job luôn kết thúc ở `done` hoặc `failed`, không bao giờ treo ở `running`."""
    try:
        project, rewritten = await create_language_version(project_id, language, voice)
    except LanguageVersionError as exc:
        case_jobs.update_job(job_id, status="failed", error=str(exc))
    except StepFailed as exc:
        case_jobs.update_job(job_id, status="failed", error=await _failure_message(project_id, exc))
    except Exception as exc:    # lỗi lập trình, lỗi đọc ghi...: không đưa chi tiết (có thể chứa tên thật) ra ngoài
        logger.exception("Job %s: tạo bản %s của dự án %s gặp lỗi ngoài dự kiến", job_id, language, project_id)
        case_jobs.update_job(job_id, status="failed",
                             error=f"Lỗi ngoài dự kiến ({type(exc).__name__}). Xem nhật ký máy chủ để biết chi tiết.")
    else:
        case_jobs.update_job(job_id, status="done", result={"project_id": project.id, "rewritten_orders": rewritten})


def _job_key(project_id: str, language: str) -> str:
    return f"{project_id}:{language}"


@router.post("/{project_id}/create-language-version")
async def create_language_version_endpoint(project_id: str, req: LanguageVersionRequest, background_tasks: BackgroundTasks):
    """Mỗi dự án và ngôn ngữ chỉ có một việc chạy tại một thời điểm: bấm lại khi việc trước chưa xong thì nhận lại
    đúng việc đó (`already_running` = true, `voice` của lần bấm sau bị bỏ qua)."""
    if await asyncio.to_thread(project_service.get_project, project_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    job_id, created = case_jobs.start_job(JOB_KIND, _job_key(project_id, req.language))
    if created:
        background_tasks.add_task(_run_job, job_id, project_id, req.language, req.voice)
    return {"job_id": job_id, "already_running": not created}


@router.get("/{project_id}/language-version-job")
async def running_language_version_job(project_id: str, language: Lang = "en"):
    return {"job": case_jobs.find_running_job(JOB_KIND, _job_key(project_id, language))}
