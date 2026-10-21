"""
True Crime Studio Router (spec 7.8)
-----------------------------------
Chuyển thể một vụ án thật thành truyện song ngữ Việt/Anh. Phân tích chạy qua hàng việc lưu trên đĩa (services/case_worker);
router chỉ nhận yêu cầu, báo tiến độ, cho xem và sửa kế hoạch, rồi dựng dự án.

Endpoints (prefix /api/true-crime):
- POST /analyze                           lưu bài gốc, tạo hàng việc -> {case_id}. Bài rỗng 400, quá dài 413.
- GET  /cases/{case_id}/progress          tiến độ của hàng việc (404 nếu không có vụ).
- POST /cases/{case_id}/resume            "Thử lại": chạy tiếp từ việc bị hỏng.
- GET  /cases/{case_id}/outline           dàn ý + dòng thời gian (tên hư cấu) cho màn duyệt (409 nếu chưa có dàn ý).
- PUT  /cases/{case_id}/outline           sửa dàn ý đang chờ duyệt (cả danh sách sự việc bỏ khỏi video); kiểm bằng các
                                          quy tắc dàn ý (400), 409 nếu đã duyệt.
- POST /cases/{case_id}/outline/approve   duyệt dàn ý: worker viết cảnh tiếp (409 nếu không chờ duyệt).
- GET  /cases/{case_id}                   kế hoạch (409 nếu chưa phân tích xong).
- PUT  /cases/{case_id}/entities          sửa tên hư cấu / thêm tên mới, áp cho cả kế hoạch, chạy lại kiểm tra.
- PUT  /cases/{case_id}/scenes/{order}    sửa lời Việt/Anh của một cảnh, chạy lại kiểm tra.
- POST /cases/{case_id}/create-project    dựng dự án bản Việt hoặc Anh (409 khi còn cảnh bị đánh dấu).
- POST /render-board-scene/{scene_id}     vẽ bảng ghim tích luỹ tới cảnh đó vào projects/_cases/<case_id>/boards/.
- GET  /jobs/{job_id}                     trạng thái job tạo bản ngôn ngữ khác (xem routers/language_versions.py).

Thông báo lỗi trả cho client chỉ nêu order cảnh và id thực thể, không bao giờ nêu tên thật. Kế hoạch trả cho màn xem lại
thì có tên thật (real_names, warnings): đó là dữ liệu của chính người dùng trên máy họ, nằm ngoài các thông báo lỗi.
"""
import asyncio
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from models.case_adaptation_schemas import CaseAdaptationPlan, Lang, PartKind
from security import is_safe_id, require_safe_id, validate_path_ids
from services import case_jobs, case_plan_edits, case_redact, case_store, case_worker
from services.case_project_builder import LANGS, BlockingFlagsError, create_project_from_plan, render_board_scene
from services.image_service import STYLE_PRESETS

router = APIRouter(prefix="/api/true-crime", tags=["True Crime Studio"], dependencies=[Depends(validate_path_ids)])

PROGRESS_ERROR_FALLBACK = "Phân tích bị dừng. Bấm Thử lại để chạy tiếp; nếu lặp lại, xem nhật ký máy chủ."
OUTLINE_ERROR_FALLBACK = ("Dàn ý chưa đạt quy tắc (số cảnh mỗi nhịp, mỗi sự việc thuộc đúng một nhịp, tổng số cảnh). "
                          "Kiểm lại các nhịp rồi lưu lại.")
MAX_VOICE_CHARS = 100


# ==============================================================================
# REQUEST MODELS
# ==============================================================================

class AnalyzeRequest(BaseModel):
    raw_report: str
    target_minutes: int = Field(default=8, ge=1, le=60, description="Độ dài video mong muốn (phút)")
    visual_style: str = "neo_noir_silhouette"


class OutlinePartEdit(BaseModel):
    kind: PartKind
    summary_vi: str = Field(default="", max_length=1000)
    event_ids: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=500)
    scene_count: int


class OutlineDroppedEdit(BaseModel):
    event_id: str = Field(max_length=64)
    reason: str = Field(default="", max_length=500)


class OutlineEditRequest(BaseModel):
    parts: list[OutlinePartEdit] = Field(max_length=100)
    supported_minutes: Optional[int] = Field(default=None, ge=1, le=60,
                                             description="Số phút bài đủ tư liệu; để trống thì giữ ước lượng của máy")
    dropped: Optional[list[OutlineDroppedEdit]] = Field(
        default=None, max_length=500, description="Sự việc bỏ khỏi video; để trống thì giữ danh sách đang lưu")


class EntitiesRequest(BaseModel):
    updates: list[case_plan_edits.EntityUpdate] = Field(default_factory=list, max_length=500)
    additions: list[case_plan_edits.EntityAddition] = Field(default_factory=list, max_length=100)


class SceneEditRequest(BaseModel):
    narration_vi: Optional[str] = Field(default=None, max_length=5000)
    narration_en: Optional[str] = Field(default=None, max_length=5000)


class CreateProjectRequest(BaseModel):
    language: Lang
    voice: str = Field(default="", max_length=MAX_VOICE_CHARS, description="Để trống thì dùng giọng mặc định của ngôn ngữ")
    voices: Optional[dict[str, str]] = Field(default=None, description="Giọng nhớ sẵn cho từng ngôn ngữ, ví dụ {'en': ...}")
    visual_style: Optional[str] = None
    image_provider: str = "meta_muse_cloud"


class RenderBoardRequest(BaseModel):
    case_id: str
    language: Lang


# ==============================================================================
# HELPERS
# ==============================================================================

def _require_style(value: str) -> None:
    if value not in STYLE_PRESETS:
        raise HTTPException(status_code=400, detail="Phong cách hình không hợp lệ; hãy chọn một kiểu trong danh sách phong cách.")


async def _load_plan(case_id: str) -> CaseAdaptationPlan:
    """Kế hoạch đã lưu của vụ án; 404 nếu không có vụ, 409 nếu chưa phân tích xong."""
    try:
        return await asyncio.to_thread(case_plan_edits.load_ready_plan, case_id)
    except case_worker.CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Không tìm thấy vụ án.") from None
    except case_plan_edits.PlanNotReadyError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from None


async def _edit_plan(func, *args) -> CaseAdaptationPlan:
    """Chạy một thao tác sửa kế hoạch (case_plan_edits) và đổi lỗi của nó thành mã HTTP."""
    try:
        return await asyncio.to_thread(func, *args)
    except case_worker.CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Không tìm thấy vụ án.") from None
    except case_plan_edits.PlanNotReadyError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from None
    except case_plan_edits.PlanEditError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


async def _outline_call(case_id: str, func, *args):
    """Chạy một thao tác duyệt dàn ý (case_worker) và đổi lỗi của nó thành mã HTTP. Lý do dàn ý bị từ chối có thể trích
    id hay chữ người dùng gửi lên, nên ẩn tên thật như thông báo tiến độ."""
    try:
        return await asyncio.to_thread(func, case_id, *args)
    except case_worker.CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Không tìm thấy vụ án.") from None
    except case_worker.OutlineStateError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from None
    except case_worker.OutlineEditError as exc:
        detail = await asyncio.to_thread(case_redact.hide_real_names, case_id, exc.message, OUTLINE_ERROR_FALLBACK)
        raise HTTPException(status_code=400, detail=detail) from None


# ==============================================================================
# PHÂN TÍCH
# ==============================================================================

@router.post("/analyze")
async def analyze_case(req: AnalyzeRequest):
    """Lưu bài gốc, tạo hàng việc; worker nền tự nhận và chạy. Trả {case_id}."""
    _require_style(req.visual_style)
    try:
        case_id = await asyncio.to_thread(case_worker.start_analysis, req.raw_report, req.target_minutes, req.visual_style)
    except case_worker.CaseInputError as exc:
        raise HTTPException(status_code=400 if exc.reason == "empty" else 413, detail=exc.user_message) from None
    return {"case_id": case_id}


@router.get("/cases/{case_id}/progress")
async def case_progress(case_id: str):
    pipeline = await asyncio.to_thread(case_store.load_pipeline, case_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy vụ án.")
    progress = case_worker.pipeline_progress(pipeline)
    if progress["error"]:       # thông báo của việc hỏng có thể trích dẫn tên thật
        progress["error"] = await asyncio.to_thread(
            case_redact.hide_real_names, case_id, progress["error"], PROGRESS_ERROR_FALLBACK)
    return progress


@router.post("/cases/{case_id}/resume")
async def resume_case(case_id: str):
    try:
        pipeline = await asyncio.to_thread(case_worker.resume_pipeline, case_id)
    except case_worker.CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Không tìm thấy vụ án.") from None
    return case_worker.pipeline_progress(pipeline)


# ==============================================================================
# DUYỆT DÀN Ý
# ==============================================================================

@router.get("/cases/{case_id}/outline")
async def get_outline(case_id: str):
    """Dàn ý, dòng thời gian đã đổi tên hư cấu và giới hạn số cảnh; `editable` chỉ True khi đang chờ duyệt."""
    return await _outline_call(case_id, case_worker.outline_view)


@router.put("/cases/{case_id}/outline")
async def edit_outline(case_id: str, req: OutlineEditRequest):
    """Thay toàn bộ các nhịp của dàn ý đang chờ duyệt (đổi loại, tóm tắt, số cảnh, chuyển sự việc, thêm bớt nhịp) và,
    nếu gửi, số phút bài đủ tư liệu và danh sách sự việc bỏ khỏi video. Trả dàn ý đã lưu như GET."""
    dropped = None if req.dropped is None else [d.model_dump() for d in req.dropped]
    await _outline_call(case_id, case_worker.edit_outline, [p.model_dump() for p in req.parts], req.supported_minutes,
                        dropped)
    return await _outline_call(case_id, case_worker.outline_view)


@router.post("/cases/{case_id}/outline/approve")
async def approve_outline(case_id: str):
    """Duyệt dàn ý; worker viết cảnh tiếp. Trả tiến độ."""
    pipeline = await _outline_call(case_id, case_worker.approve_outline)
    return case_worker.pipeline_progress(pipeline)


# ==============================================================================
# XEM LẠI VÀ SỬA
# ==============================================================================

@router.get("/cases/{case_id}", response_model=CaseAdaptationPlan)
async def get_case(case_id: str):
    return await _load_plan(case_id)


@router.put("/cases/{case_id}/entities", response_model=CaseAdaptationPlan)
async def edit_entities(case_id: str, req: EntitiesRequest):
    """Đổi tên hư cấu hoặc thêm tên mới; áp cho lời kể, prompt, nhãn rồi chạy lại kiểm tra. Trả kế hoạch đã lưu."""
    return await _edit_plan(case_plan_edits.edit_entities, case_id, req.updates, req.additions)


@router.put("/cases/{case_id}/scenes/{order}", response_model=CaseAdaptationPlan)
async def edit_scene(case_id: str, order: int, req: SceneEditRequest):
    """Sửa lời Việt và/hoặc Anh của một cảnh rồi chạy lại kiểm tra. Trả kế hoạch đã lưu."""
    return await _edit_plan(case_plan_edits.edit_scene, case_id, order, req.narration_vi, req.narration_en)


# ==============================================================================
# DỰNG DỰ ÁN VÀ BẢNG GHIM
# ==============================================================================

@router.post("/cases/{case_id}/create-project")
async def create_case_project(case_id: str, req: CreateProjectRequest):
    """Dựng dự án từ kế hoạch bằng `language`. Còn cảnh bị đánh dấu thì 409 (chỉ nêu order các cảnh đó)."""
    if req.visual_style is not None:
        _require_style(req.visual_style)
    if not is_safe_id(req.image_provider):
        raise HTTPException(status_code=400, detail="image_provider không hợp lệ.")
    voices = req.voices
    if voices is not None and (any(k not in LANGS for k in voices) or any(len(v) > MAX_VOICE_CHARS for v in voices.values())):
        raise HTTPException(status_code=400, detail="voices chỉ nhận khoá 'vi' hoặc 'en' với tên giọng không quá "
                                                    f"{MAX_VOICE_CHARS} ký tự.")
    plan = await _load_plan(case_id)
    try:
        project = await asyncio.to_thread(
            create_project_from_plan, plan, req.language, req.voice, visual_style=req.visual_style,
            image_provider=req.image_provider, voices=voices)
    except BlockingFlagsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"project_id": project.id, "redirect_url": f"/?project_id={project.id}"}


@router.post("/render-board-scene/{scene_id}")
async def render_board_scene_endpoint(scene_id: Annotated[int, Path(ge=1)], req: RenderBoardRequest):
    """Vẽ bảng ghim tích luỹ tới cảnh `scene_id` (order trong kế hoạch) bằng nhãn của `language`, vào
    projects/_cases/<case_id>/boards/board_<NNN>_<lang>.jpg (không ghi vào backend/static, thư mục công khai)."""
    require_safe_id(req.case_id, "case_id")
    plan = await _load_plan(req.case_id)
    if scene_id not in {s.order for s in plan.scenes}:
        raise HTTPException(status_code=400, detail=f"Không có cảnh {scene_id} trong kế hoạch.")
    out_path = case_store.cases_dir() / req.case_id / "boards" / f"board_{scene_id:03d}_{req.language}.jpg"
    image = await asyncio.to_thread(render_board_scene, plan, scene_id, req.language, out_path)
    return {"image_path": str(image)}


# ==============================================================================
# JOB BẢN NGÔN NGỮ KHÁC
# ==============================================================================

@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = case_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job.")
    return job
