"""
True Crime Studio Router
------------------------
Endpoints:
- POST /api/true-crime/fictionalize: Anonymize case report & construct 70/30 Jubensha DAG.
- POST /api/true-crime/render-board-scene/{scene_id}: Render cumulative corkboard frame/clip.
- POST /api/true-crime/create-project: Convert case plan into playable Story Studio project.
"""

import os
import uuid
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from config import STATIC_DIR, PROJECTS_DIR, DEFAULT_VOICE
from models.schemas import Project, Scene
from models.evidence_schemas import (
    EvidenceNode,
    RelationEdge,
    BoardState,
    ForeshadowingItem,
    FictionalCasePlan,
)
from services.case_fictionalizer import CaseFictionalizerEngine
from services.investigation_board_engine import (
    get_cumulative_board_state,
    render_board_image,
    render_board_animation_clip,
)
from services.project_service import _get_project_dir, _ensure_project_subdirs, _save_project
from security import require_safe_id, validate_path_ids

router = APIRouter(prefix="/api/true-crime", tags=["True Crime Studio"], dependencies=[Depends(validate_path_ids)])

# In-memory plan cache for quick board rendering by case_id
_CASE_PLAN_CACHE: Dict[str, FictionalCasePlan] = {}


# ==============================================================================
# REQUEST & RESPONSE MODELS
# ==============================================================================

class FictionalizeRequest(BaseModel):
    raw_report: str = Field(description="Raw true crime article or incident dossier text")
    case_id: Optional[str] = Field(default=None, description="Optional custom case id")
    duration_minutes: Optional[int] = Field(default=1, description="Desired video length (1, 8, 10, 15 mins)")
    truth_ratio: Optional[float] = Field(default=0.70, description="Truth proportion (default 70%)")
    fiction_ratio: Optional[float] = Field(default=0.30, description="Fiction proportion (default 30%)")
    custom_mappings: Optional[Dict[str, str]] = Field(default=None, description="Manual alias overrides")


class RenderBoardSceneRequest(BaseModel):
    case_id: str
    plan: Optional[FictionalCasePlan] = None
    render_video: bool = False
    duration_sec: float = 5.0
    fps: int = 24


class CreateTrueCrimeProjectRequest(BaseModel):
    plan: Optional[FictionalCasePlan] = None
    raw_report: Optional[str] = None
    case_title: Optional[str] = None
    voice: Optional[str] = Field(default="vi-VN-NamMinhNeural", description="Vietnamese detective narrator voice")
    pre_render_boards: bool = True


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.post("/fictionalize", response_model=FictionalCasePlan)
async def fictionalize_case_endpoint(req: FictionalizeRequest):
    """
    Analyzes raw criminal case report:
    1. Anonymizes PII into a deterministic alias vault.
    2. Builds 70% forensic truth + 30% red herring Jubensha matrix.
    3. Tracks foreshadowing ledger.
    4. Generates 5s scenes with 3rd-person reviewer voice.
    """
    if not req.raw_report.strip():
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp nội dung hồ sơ vụ án.")
    if req.case_id:
        require_safe_id(req.case_id, "case_id")

    engine = CaseFictionalizerEngine()
    plan = await engine.fictionalize_case(
        raw_report=req.raw_report,
        case_id=req.case_id,
        duration_minutes=req.duration_minutes or 1,
    )

    # Cache plan for fast board frame rendering
    _CASE_PLAN_CACHE[plan.case_id] = plan
    return plan


@router.post("/render-board-scene/{scene_id}")
async def render_board_scene_endpoint(scene_id: int, req: RenderBoardSceneRequest):
    """
    Renders cumulative corkboard evidence state at scene K:
    - 1080p static PNG/JPG.
    - Optional 5-second dynamic MP4 animation clip with gravity Bezier red threads.
    """
    require_safe_id(req.case_id, "case_id")
    if req.plan is not None:
        require_safe_id(req.plan.case_id, "case_id")
    if not (0 < req.duration_sec <= 60 and 1 <= req.fps <= 60):
        raise HTTPException(status_code=400, detail="duration_sec phải trong (0, 60] và fps trong [1, 60].")
    plan = req.plan or _CASE_PLAN_CACHE.get(req.case_id)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy dữ liệu plan cho case_id '{req.case_id}'. Vui lòng truyền kèm object plan.",
        )

    # Compute cumulative state at scene_id
    board_state = get_cumulative_board_state(plan, scene_order=scene_id)

    # Output directory in static folder for immediate web preview
    board_dir = STATIC_DIR / "evidence_boards" / req.case_id
    board_dir.mkdir(parents=True, exist_ok=True)

    img_filename = f"board_scene_{scene_id:03d}.jpg"
    img_path = board_dir / img_filename
    render_board_image(board_state, output_path=str(img_path))

    video_path_str = None
    video_url_str = None

    if req.render_video:
        video_filename = f"board_scene_{scene_id:03d}.mp4"
        video_path = board_dir / video_filename
        render_board_animation_clip(
            board_state=board_state,
            output_video_path=str(video_path),
            duration_sec=req.duration_sec,
            fps=req.fps,
        )
        video_path_str = str(video_path)
        video_url_str = f"/static/evidence_boards/{req.case_id}/{video_filename}"

    return {
        "success": True,
        "case_id": req.case_id,
        "scene_id": scene_id,
        "image_url": f"/static/evidence_boards/{req.case_id}/{img_filename}",
        "image_path": str(img_path),
        "video_url": video_url_str,
        "video_path": video_path_str,
        "cumulative_nodes_count": len(board_state.cumulative_nodes),
        "cumulative_edges_count": len(board_state.cumulative_edges),
        "delta_nodes_count": len(board_state.delta_nodes),
        "delta_edges_count": len(board_state.delta_edges),
    }


@router.post("/create-project")
async def create_true_crime_project_endpoint(req: CreateTrueCrimeProjectRequest):
    """
    Creates a full Story Studio Project from a true crime case:
    - Configures 5s scenes alternating A-Roll (Neo-Noir Silhouette) & B-Roll (Evidence Board).
    - Automatically pre-renders evidence board images for B-Roll scenes.
    - Compatible with Story Studio Player, Subtitles, and 1-Click Master Render Pipeline.
    """
    engine = CaseFictionalizerEngine()
    plan = req.plan

    if not plan:
        if not req.raw_report:
            raise HTTPException(status_code=400, detail="Vui lòng cung cấp 'plan' hoặc 'raw_report'.")
        plan = await engine.fictionalize_case(req.raw_report)
    require_safe_id(plan.case_id, "case_id")

    # Generate Project ID
    pid = f"proj_crime_{uuid.uuid4().hex[:8]}"
    _ensure_project_subdirs(pid)

    p_dir = _get_project_dir(pid)
    img_dir = p_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    # Pre-render Board States if requested
    board_img_map: Dict[int, Path] = {}
    board_dir = STATIC_DIR / "evidence_boards" / plan.case_id
    board_dir.mkdir(parents=True, exist_ok=True)

    if req.pre_render_boards:
        for bs in plan.board_states:
            b_file = board_dir / f"board_scene_{bs.scene_order:03d}.jpg"
            render_board_image(bs, output_path=str(b_file))
            board_img_map[bs.scene_order] = b_file

    # Construct Story Studio Scenes
    scenes_list: List[Scene] = []
    for sc in plan.scenes_script:
        order = sc.get("order", len(scenes_list) + 1)
        sid = f"scene_{order:03d}"
        shot_type = sc.get("shot_type", "A_ROLL_NOIR")
        board_order = sc.get("board_scene_order", 1)

        b_img_url = None
        b_img_path = None

        if shot_type == "B_ROLL_BOARD":
            dst_scene_image = img_dir / f"{sid}.jpg"
            # If board was pre-rendered, copy to project image dir
            src_board = board_img_map.get(board_order)
            if src_board and src_board.exists():
                shutil.copy2(src_board, dst_scene_image)
            else:
                # Render directly on the fly
                bs = get_cumulative_board_state(plan, scene_order=board_order)
                render_board_image(bs, output_path=str(dst_scene_image))

            b_img_path = str(dst_scene_image)
            b_img_url = f"/api/projects/{pid}/media/images/{sid}.jpg"

        camera_motion = "neo_noir_dutch_tilt" if shot_type == "A_ROLL_NOIR" else "zoom_in"
        if sc.get("camera_motion"):
            camera_motion = sc["camera_motion"]

        scene_obj = Scene(
            id=sid,
            order=order,
            text=sc.get("text", ""),
            image_prompt=sc.get("image_prompt", ""),
            camera_motion=camera_motion,
            speaker="narrator",
            voice_emotion="tense",
            shot_type=shot_type,
            duration=sc.get("estimated_duration", 5.0),
            image_url=b_img_url,
            image_path=b_img_path,
            status="imaged" if b_img_path else "draft",
            status_image="ready" if b_img_path else "idle",
            sfx_cue=sc.get("sound_design", {}).get("sfx_cue", ["rain_ambient"]),
            bgm_energy=sc.get("sound_design", {}).get("bgm_energy", "tension_buildup"),
            metadata={
                "shot_type": shot_type,
                "narrative_beat": sc.get("narrative_beat", "escalation"),
                "board_scene_order": board_order,
                "case_id": plan.case_id,
            },
        )
        scenes_list.append(scene_obj)

    now = datetime.utcnow().isoformat()
    project = Project(
        id=pid,
        name=req.case_title or plan.title,
        description=f"Hồ Sơ Kỳ Án True Crime (70/30 Formula & Evidence Corkboard DAG) - {len(scenes_list)} phân cảnh",
        voice=req.voice or "vi-VN-NamMinhNeural",
        style_preset="neo_noir_silhouette",
        image_provider="meta_muse_cloud",
        bgm_overall_genre="mysterious_dark",
        target_aspect_ratio="16:9",
        scenes=scenes_list,
        created_at=now,
        updated_at=now,
    )

    _save_project(project)

    return {
        "success": True,
        "project_id": project.id,
        "title": project.name,
        "scenes_count": len(project.scenes),
        "plan": plan,
        "redirect_url": f"/?project_id={project.id}",
    }
