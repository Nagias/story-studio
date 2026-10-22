import asyncio
import logging
import os
import re
import shutil
import subprocess
import unicodedata
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import quote

from starlette.background import BackgroundTask

logger = logging.getLogger("story_studio.api")

from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, UploadFile, File, Form, Body, Depends
from fastapi.responses import FileResponse

from config import (
    STORY_STUDIO_DIR,
    PROJECTS_DIR,
    BGM_DIR,
    COMIC_SLICES_DIR,
    STATIC_DIR,
    ASSETS_DIR,
    DEFAULT_IMAGE_PROVIDER,
    DEFAULT_VOICE,
)
from security import (
    is_within,
    read_upload_limited,
    require_safe_id,
    safe_upload_name,
    validate_path_ids,
)
from models.schemas import (
    Project,
    Scene,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    SceneCreateRequest,
    SceneUpdateRequest,
    ReorderScenesRequest,
    SplitScriptRequest,
    VoiceGenRequest,
    ImageGenRequest,
    RenderRequest,
    OpenFolderRequest,
    ComicSliceResponse,
    ComicImportRequest,
    VoxScriptAnalysisRequest,
    VoxScriptAnalysisResponse,
    VoxProjectScriptRequest,
    LongVideoProduceRequest,
    CreateProjectFromScriptRequest,
    NovelIngestRequest,
    get_preset_characters,
    get_preset_character_by_id,
    MasterStoryboard,
    DeconstructScriptRequest,
    MasterStoryboardImportRequest,
    master_storyboard_to_project,
)
from services import (
    get_available_voices,
    generate_speech,
    detect_language,
    get_available_styles,
    generate_image,
    render_scene_video,
    assemble_full_video,
    get_available_bgm_tracks,
    list_projects,
    get_project,
    create_project,
    update_project,
    delete_project,
    add_scene,
    update_scene,
    delete_scene,
    reorder_scenes,
    get_scene_media_paths,
    get_render_media_paths,
    split_text_into_scenes,
    analyze_vox_script_async,
    split_text_into_vox_scenes_offline,
    adapt_novel_chapter_to_us_podcast,
    PACING_CONFIGS,
    slice_comic,
    deconstruct_script_async,
    deconstruct_script_offline,
    generate_youtube_thumbnail,
)
from services.thumbnail_service import ThumbnailError

from services.project_service import _get_project_dir, ensure_project_dirs, save_project

router = APIRouter(prefix="/api", tags=["Story Studio"], dependencies=[Depends(validate_path_ids)])

# Các trường đường dẫn file của Scene mà client có thể gửi lên qua PUT /projects/{id}
SCENE_PATH_FIELDS = (
    "voice_audio_path",
    "audio_path",
    "srt_path",
    "image_path",
    "video_segment_path",
    "motion_video_path",
    "foreground_image_path",
    "background_image_path",
)


def _apply_voice_result(scene: Scene, tts_res: Dict[str, Any], project_id: str) -> None:
    """Ghi kết quả TTS vào cảnh, kể cả việc đã phải đổi sang giọng dự phòng."""
    scene.voice_audio_path = tts_res["audio_path"]
    scene.voice_audio_url = f"/api/projects/{project_id}/media/audio/{scene.id}.mp3"
    scene.srt_path = tts_res["srt_path"]
    scene.srt_url = f"/api/projects/{project_id}/media/audio/{scene.id}.srt"
    scene.duration = tts_res["duration"]
    scene.status_voice = "ready"
    scene.metadata.pop("voice_error", None)
    if tts_res.get("fallback_used"):
        scene.metadata["voice_fallback"] = {
            "requested_voice": tts_res.get("requested_voice"),
            "used_voice": tts_res.get("voice"),
            "reason": tts_res.get("fallback_reason"),
        }
    else:
        scene.metadata.pop("voice_fallback", None)


def _apply_image_result(scene: Scene, img_res: Dict[str, Any], project_id: str) -> bool:
    """Ghi kết quả tạo ảnh vào cảnh. Không có ảnh mới thì đánh dấu lỗi và trả False."""
    if not img_res.get("success"):
        scene.status_image = "error"
        scene.metadata["image_error"] = img_res.get("error") or "Không rõ lỗi"
        return False
    scene.image_path = img_res["image_path"]
    scene.image_url = f"/api/projects/{project_id}/media/images/{scene.id}.jpg"
    scene.status_image = "ready"
    scene.metadata.pop("image_error", None)
    if img_res.get("fallback_reason"):
        scene.metadata["image_fallback"] = {
            "provider": img_res.get("provider"),
            "reason": img_res["fallback_reason"],
        }
    else:
        scene.metadata.pop("image_fallback", None)
    if img_res.get("is_placeholder"):
        scene.metadata["image_placeholder"] = True
    else:
        scene.metadata.pop("image_placeholder", None)
    return True


IMAGE_RESULT_FIELDS = ["image_path", "image_url", "status_image", "status", "metadata"]
VOICE_RESULT_FIELDS = [
    "text", "voice_audio_path", "voice_audio_url", "srt_path", "srt_url",
    "duration", "status_voice", "status", "metadata",
]


def _save_scene_fields(project_id: str, scene: Scene, fields: List[str]) -> None:
    """
    Ghi kết quả của MỘT cảnh vào bản dự án mới nhất trên đĩa. Tạo ảnh qua Muse có thể mất vài
    phút; trong lúc đó giao diện tự lưu các chỉnh sửa khác, nên không được ghi đè cả danh sách cảnh
    bằng bản đọc lúc bắt đầu.
    """
    latest = get_project(project_id)
    if not latest:
        return
    for sc in latest.scenes:
        if sc.id == scene.id:
            for field in fields:
                setattr(sc, field, getattr(scene, field))
            break
    else:
        latest.scenes.append(scene)
    update_project(project_id, ProjectUpdateRequest(scenes=latest.scenes))


def _scene_motion_clip(scene: Scene, media: Dict[str, Path]) -> Optional[Path]:
    """
    Clip chuyển động gốc của cảnh (Muse hoặc tải lên). Không bao giờ trả về chính file
    segment dựng ra (media["video"]), để ffmpeg không đọc và ghi cùng một file.
    """
    segment = media["video"].resolve()
    candidates: List[Path] = []
    if scene.motion_video_path:
        candidates.append(_resolve_studio_path(scene.motion_video_path))
    candidates.append(media["motion_video"])
    if scene.media_view_mode == "video" and scene.video_segment_path:
        # Dữ liệu cũ: clip gắn từ Gallery Muse được lưu vào video_segment_path
        candidates.append(_resolve_studio_path(scene.video_segment_path))
    for cand in candidates:
        try:
            if (cand.exists() and cand.stat().st_size > 0 and cand.resolve() != segment
                    and is_within(cand, PROJECTS_DIR, STATIC_DIR)):
                return cand
        except OSError:
            continue
    # Dữ liệu cũ: clip Muse từng được lưu đè đúng lên file segment. Tách ra file riêng một lần.
    if (scene.media_view_mode == "video" and not scene.metadata.get("segment_rendered")
            and segment.exists() and segment.stat().st_size > 0):
        shutil.copy2(segment, media["motion_video"])
        scene.motion_video_path = str(media["motion_video"])
        return media["motion_video"]
    return None


def _scene_render_input(scene: Scene, media: Dict[str, Path]) -> Optional[str]:
    """Đầu vào để dựng segment: clip chuyển động nếu cảnh đang dùng video, ngược lại là ảnh."""
    clip = _scene_motion_clip(scene, media)
    has_image = media["image"].exists()
    if clip is not None and (scene.media_view_mode == "video" or not has_image):
        return str(clip)
    if has_image:
        return str(media["image"])
    return None


# Media do server tạo ra (Muse, TTS, render) có thể về trong lúc giao diện đang giữ bản cũ của cảnh.
# Khi giao diện tự lưu bản đó lên, các trường này để trống không được xoá mất kết quả trên server.
SERVER_OWNED_MEDIA_FIELDS = (
    "image_path", "image_url",
    "motion_video_path", "video_url",
    "video_segment_path", "video_segment_url",
    "voice_audio_path", "voice_audio_url",
    "srt_path", "srt_url",
)


def _keep_server_media(existing: Optional[Project], incoming_scenes: List[Scene]) -> None:
    if not existing:
        return
    server_scenes = {s.id: s for s in existing.scenes}
    for sc in incoming_scenes:
        old = server_scenes.get(sc.id)
        if not old:
            continue
        for field in SERVER_OWNED_MEDIA_FIELDS:
            if not getattr(sc, field, None) and getattr(old, field, None):
                setattr(sc, field, getattr(old, field))


def _resolve_studio_path(value: str) -> Path:
    """Đường dẫn tương đối được tính từ thư mục gốc Story Studio (không phụ thuộc cwd)."""
    p = Path(value)
    return p if p.is_absolute() else STORY_STUDIO_DIR / p


def _require_studio_media_path(value: Optional[str], field: str) -> None:
    """Client chỉ được trỏ tới file nằm trong projects/, backend/static/ hoặc backend/assets/."""
    if not value:
        return
    if not is_within(_resolve_studio_path(value), PROJECTS_DIR, STATIC_DIR, ASSETS_DIR):
        raise HTTPException(status_code=400, detail=f"{field} must point inside the Story Studio data folders")

# Active render state tracking & WebSocket management
active_renders: Dict[str, Dict[str, Any]] = {}
active_connections: Dict[str, List[WebSocket]] = {}

async def broadcast_render_update(render_id: str, data: Dict[str, Any]):
    """Broadcast progress update to active WebSockets."""
    active_renders[render_id].update(data)
    if render_id in active_connections:
        dead_sockets = []
        for ws in active_connections[render_id]:
            try:
                await ws.send_json(active_renders[render_id])
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            active_connections[render_id].remove(ws)

# ----------------- SYSTEM & PRESETS -----------------

@router.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": "YouTube Story Maker Backend",
        "version": "1.0.0",
        "ffmpeg": True,
    }

@router.get("/voices")
async def get_voices():
    """Return available TTS voices."""
    return get_available_voices()

@router.get("/voices/{voice_id}/sample")
async def get_voice_sample(voice_id: str):
    """Generate or serve cached audio sample for a given voice ID."""
    from config import STATIC_DIR
    samples_dir = STATIC_DIR / "voice_samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    clean_voice_id = voice_id.strip()
    cache_file = samples_dir / f"{clean_voice_id}.mp3"

    if cache_file.exists() and cache_file.stat().st_size > 500:
        return FileResponse(cache_file, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})

    # Find sample text for this voice
    voices = get_available_voices()
    sample_text = "Xin chào, đây là giọng đọc thử nghiệm của trí tuệ nhân tạo Story Studio."
    for v in voices:
        if v["id"].lower() == clean_voice_id.lower():
            sample_text = v.get("sample") or sample_text
            clean_voice_id = v["id"]
            break

    # Sinh ra file tạm trước: chỉ lưu vào cache khi đúng giọng được yêu cầu,
    # tránh lưu bản Edge-TTS dự phòng dưới tên vieneu-*.mp3
    tmp_file = samples_dir / f"_tmp_{uuid.uuid4().hex[:8]}.mp3"
    tmp_sidecars = [tmp_file.with_suffix(".srt"), tmp_file.with_suffix(".words.json")]
    try:
        tts_res = await generate_speech(
            text=sample_text,
            voice=clean_voice_id,
            output_audio_path=str(tmp_file),
        )
        if not (tmp_file.exists() and tmp_file.stat().st_size > 500):
            raise HTTPException(status_code=500, detail="Không thể tạo mẫu âm thanh giọng đọc.")
    except HTTPException:
        tmp_file.unlink(missing_ok=True)
        raise
    except Exception as e:
        tmp_file.unlink(missing_ok=True)
        logger.error(f"Failed to generate voice sample for {voice_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for side in tmp_sidecars:
            side.unlink(missing_ok=True)

    if not tts_res.get("fallback_used"):
        tmp_file.replace(cache_file)
        return FileResponse(cache_file, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})

    logger.warning(f"Voice sample for {clean_voice_id} used fallback: {tts_res.get('fallback_reason')}")
    return FileResponse(
        tmp_file,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Voice-Fallback": quote(str(tts_res.get("voice") or "")),
        },
        background=BackgroundTask(lambda: tmp_file.unlink(missing_ok=True)),
    )

@router.get("/styles")
async def get_styles():
    """Return available image style presets."""
    return get_available_styles()

@router.get("/characters/presets")
async def get_preset_characters_route():
    """Return catalog of master character consistency presets."""
    return [c.model_dump() for c in get_preset_characters()]

@router.get("/characters/presets/{char_id}")
async def get_preset_character_by_id_route(char_id: str):
    """Return a single preset character template by ID."""
    char = get_preset_character_by_id(char_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character preset not found.")
    return char.model_dump()

@router.get("/bgm-tracks")
async def get_bgm_tracks():
    """Return catalog of available background music tracks."""
    return get_available_bgm_tracks(BGM_DIR)

@router.get("/bgm/{filename}")
async def get_bgm_file(filename: str):
    """Serve a specific BGM track file."""
    file_path = (BGM_DIR / filename).resolve()
    if not file_path.is_relative_to(BGM_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected.")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="BGM file not found.")
    return FileResponse(file_path, media_type="audio/mpeg")

MAX_BGM_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/bgm-tracks/upload")
async def upload_bgm_track(file: UploadFile = File(...)):
    """Nhận file MP3 nhạc nền riêng, lưu vào assets/bgm với tên an toàn; trả về ID để chọn khi dựng video."""
    safe_upload_name(file.filename, {".mp3"}, prefix="custom")  # chỉ nhận .mp3
    content = await read_upload_limited(file, max_bytes=MAX_BGM_UPLOAD_BYTES)
    if not content:
        raise HTTPException(status_code=400, detail="File nhạc trống.")
    # MP3 thật bắt đầu bằng thẻ ID3 hoặc khung MPEG (11 bit đầu đều là 1)
    if not (content[:3] == b"ID3" or (len(content) > 1 and content[0] == 0xFF and (content[1] & 0xE0) == 0xE0)):
        raise HTTPException(status_code=400, detail="File không phải MP3 hợp lệ.")

    # Tên file = custom_<tên gốc không dấu>_<mã ngẫu nhiên>: vừa là ID an toàn, vừa đọc được
    stem = unicodedata.normalize("NFKD", Path(file.filename or "").stem.replace("đ", "d").replace("Đ", "D"))
    slug = re.sub(r"[^a-z0-9]+", "_", stem.encode("ascii", "ignore").decode().lower()).strip("_")[:30] or "nhac"
    track_id = f"custom_{slug}_{uuid.uuid4().hex[:6]}"
    require_safe_id(track_id, "bgm_track")
    target = BGM_DIR / f"{track_id}.mp3"
    if not is_within(target, BGM_DIR):
        raise HTTPException(status_code=400, detail="Tên file nhạc không hợp lệ.")
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return {
        "success": True,
        "id": track_id,
        "name": slug.replace("_", " "),
        "filename": target.name,
        "url": f"/api/bgm/{target.name}",
    }

@router.post("/open-folder")
async def open_folder(req: OpenFolderRequest):
    """Open folder in Windows Explorer."""
    target_path = None
    if req.path:
        clean_p = req.path.strip()
        if clean_p.startswith("\\\\") or clean_p.startswith("//"):
            raise HTTPException(status_code=400, detail="UNC network paths are prohibited.")
        p = Path(clean_p).resolve()
        allowed = [PROJECTS_DIR.resolve(), STATIC_DIR.resolve(), ASSETS_DIR.resolve()]
        if not any(p.is_relative_to(base) for base in allowed):
            raise HTTPException(status_code=403, detail="Access denied: outside allowed Story Studio directories.")
        if not p.exists():
            raise HTTPException(status_code=404, detail="Directory not found.")
        target_path = p if p.is_dir() else p.parent
    elif req.project_id:
        try:
            p_dir = _get_project_dir(req.project_id)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        if (p_dir / "renders").exists():
            target_path = p_dir / "renders"
        else:
            target_path = p_dir

    if not target_path or not target_path.exists():
        raise HTTPException(status_code=404, detail="Directory not found.")

    try:
        os.startfile(str(target_path))
    except Exception:
        subprocess.Popen(["explorer", str(target_path)])

    return {"success": True, "opened_path": str(target_path)}

# ----------------- SCRIPT SPLITTING & VOX NARRATIVE ENGINE -----------------

@router.get("/vox/pacing-presets")
async def get_vox_pacing_presets():
    """Return available Vox narrative pacing presets."""
    return PACING_CONFIGS

@router.post("/vox/analyze-script", response_model=VoxScriptAnalysisResponse)
async def analyze_vox_script(req: VoxScriptAnalysisRequest):
    """
    Semantic Story Analyzer (Vox Narrative Engine):
    - Cuts long text / chapter into Vox 5-Stage Arc (Hook, Setting, Escalation, Climax, Resolution).
    - Supports Fast/Vox (3-4s), Balanced (5-6s), Deep Story (7-8s) pacing.
    - Generates multi-layered semantic attributes & rich cinematic English prompts.
    - Uses Gemini API / OpenRouter when available, with automatic offline semantic parser fallback.
    """
    try:
        result = await analyze_vox_script_async(
            full_text=req.text,
            pacing=req.pacing or "fast",
            max_words_per_scene=req.max_words_per_scene,
            style_preset=req.style_preset or "cinematic_realistic",
            character_anchor=req.character_anchor,
            gemini_api_key=req.api_key if req.provider in ("gemini", "auto") else None,
            openrouter_api_key=req.api_key if req.provider in ("openrouter", "auto") else None,
            provider=req.provider or "auto",
            model_name=req.model_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze Vox script: {str(e)}")

@router.post("/projects/{project_id}/vox-script")
async def import_vox_script_to_project(project_id: str, req: VoxProjectScriptRequest):
    """
    Analyze long text / novel chapter with Vox Narrative Engine and inject scenes directly into project.
    Optionally replaces existing scenes if replace_existing=True.
    """
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    style_preset = req.style_preset or project.style_preset or "cinematic_realistic"
    character_anchor = req.character_anchor or project.character_anchor or None

    try:
        analysis = await analyze_vox_script_async(
            full_text=req.text,
            pacing=req.pacing or "fast",
            max_words_per_scene=req.max_words_per_scene,
            style_preset=style_preset,
            character_anchor=character_anchor,
            gemini_api_key=req.api_key if req.provider in ("gemini", "auto") else None,
            openrouter_api_key=req.api_key if req.provider in ("openrouter", "auto") else None,
            provider=req.provider or "auto",
            model_name=req.model_name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze Vox script: {str(e)}")
    if analysis.get("fallback_reason"):
        logger.warning(f"vox-script dùng bộ chia offline: {analysis['fallback_reason']}")

    if req.replace_existing:
        for existing_scene in list(project.scenes):
            delete_scene(project_id, existing_scene.id)

    created_scenes = []
    for sc in analysis.get("scenes", []):
        meta = {
            "narrative_beat": sc.get("narrative_beat", "setting"),
            "estimated_duration": sc.get("estimated_duration", 3.5),
            "setting": sc.get("setting", ""),
            "subject": sc.get("subject", ""),
            "emotion": sc.get("emotion", ""),
            "action": sc.get("action", ""),
            "lighting": sc.get("lighting", ""),
            "camera_framing": sc.get("camera_framing", ""),
        }
        c_req = SceneCreateRequest(
            text=sc["text"],
            image_prompt=sc.get("image_prompt", ""),
            camera_motion=sc.get("camera_motion", "zoom_in"),
            metadata=meta,
        )
        scene_obj = add_scene(project_id, c_req)
        if scene_obj:
            created_scenes.append(scene_obj)

    updated_proj = get_project(project_id)
    return {
        "success": True,
        "pacing": req.pacing or "fast",
        "provider_used": analysis.get("provider_used", "offline_semantic_rules"),
        "fallback_reason": analysis.get("fallback_reason"),
        "narrative_summary": analysis.get("narrative_summary", {}),
        "added_scenes": len(created_scenes),
        "total_scenes": len(updated_proj.scenes) if updated_proj else 0,
        "project": updated_proj,
    }

@router.post("/novel/ingest-chapter")
async def ingest_novel_chapter(req: NovelIngestRequest):
    """
    US Light Novel Storyboard Ingest Pipeline:
    - Analyzes raw chapter with 9router Gemini 3.8 Flash.
    - Generates high-retention English story podcast script (with 5s Hook).
    - Produces ultra-detailed visual prompts for 9router Gemini Image (Murata / Spartan / Ink styles).
    - Creates or updates project with default US voice (Guy) and 9router Gemini image generator.
    """
    clean_text = req.novel_text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Novel text cannot be empty.")

    style_preset = req.style_preset or "manga_murata_battle"
    pacing = req.pacing or "fast"
    voice = req.voice or "en-US-GuyNeural"

    analysis = await adapt_novel_chapter_to_us_podcast(
        novel_text=clean_text,
        pacing=pacing,
        style_preset=style_preset,
        target_character=req.target_character,
    )

    fallback_reason = analysis.get("fallback_reason")
    if fallback_reason:
        logger.warning(f"ingest-chapter dùng bộ chia offline: {fallback_reason}")
    scenes_list = analysis.get("scenes", [])
    if not scenes_list:
        detail = "Failed to parse scenes from novel text."
        raise HTTPException(status_code=500, detail=f"{detail} {fallback_reason}" if fallback_reason else detail)

    proj_id = req.project_id
    if not proj_id or req.create_new_project:
        title = req.project_title or "Light Novel US Podcast Episode"
        new_proj_req = ProjectCreateRequest(
            name=title,
            description="Auto-generated US Story Podcast from Light Novel Chapter",
            voice=voice,
            style_preset=style_preset,
            image_provider="9router_gemini",
        )
        created_proj = create_project(new_proj_req)
        proj_id = created_proj.id

    created_scenes = []
    for sc in scenes_list:
        c_req = SceneCreateRequest(
            text=sc.get("text", "").strip(),
            image_prompt=sc.get("image_prompt", "").strip(),
            camera_motion=sc.get("camera_motion", "zoom_in"),
            metadata={
                "narrative_beat": sc.get("narrative_beat", "setting"),
                "estimated_duration": sc.get("estimated_duration", 4.0),
            },
        )
        s_obj = add_scene(proj_id, c_req)
        if s_obj:
            created_scenes.append(s_obj)

    project = get_project(proj_id)
    return {
        "success": True,
        "project_id": proj_id,
        "total_scenes": len(created_scenes),
        "style_preset": style_preset,
        "voice": voice,
        "image_provider": "9router_gemini",
        "fallback_reason": fallback_reason,
        "project": project,
        "scenes": created_scenes,
    }

@router.post("/split-script")
async def split_script(req: SplitScriptRequest):
    """Parse text into scene drafts without attaching to a project."""
    scenes = split_text_into_scenes(
        full_text=req.text,
        max_words_per_scene=req.max_words_per_scene or 30,
        language=req.language or "vi",
        pacing=req.pacing or "fast",
        style_preset=req.style_preset or "cinematic_realistic",
        character_anchor=req.character_anchor,
    )
    return {"scenes": scenes, "count": len(scenes)}

@router.post("/projects/{project_id}/split-script")
async def split_script_to_project(project_id: str, req: SplitScriptRequest):
    """Parse text and append the generated scenes directly to the project."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    style_preset = req.style_preset or project.style_preset
    character_anchor = req.character_anchor or project.character_anchor

    new_scenes = split_text_into_scenes(
        full_text=req.text,
        max_words_per_scene=req.max_words_per_scene or 30,
        language=req.language or "vi",
        pacing=req.pacing or "fast",
        style_preset=style_preset,
        character_anchor=character_anchor,
    )

    created = []
    for sc in new_scenes:
        c_req = SceneCreateRequest(
            text=sc["text"],
            image_prompt=sc["image_prompt"],
            camera_motion=sc["camera_motion"],
        )
        scene_obj = add_scene(project_id, c_req)
        if scene_obj:
            created.append(scene_obj)

    updated_proj = get_project(project_id)
    return {
        "success": True,
        "added_scenes": len(created),
        "total_scenes": len(updated_proj.scenes) if updated_proj else 0,
        "project": updated_proj,
    }

# ----------------- PROJECT CRUD -----------------

@router.get("/projects")
async def get_projects():
    """List all projects."""
    return list_projects()

@router.post("/projects")
async def create_new_project(req: ProjectCreateRequest):
    """Create a new story studio project."""
    project = create_project(req)
    return project

@router.post("/projects/create-from-script")
async def create_project_from_script(req: CreateProjectFromScriptRequest):
    """
    Clean-slate workflow & 1-Click Pipeline:
    Create a new project from raw script text, automatically split it into scenes,
    preserve Vietnamese emotional podcast storytelling verbatim,
    and immediately generate distinct visuals for ALL scenes using Meta Muse Cloud
    so Step 2 (Director Board) has full scene images ready right away.
    """
    first_line = req.text.strip().split("\n")[0][:45].strip()
    clean_title = (req.name or first_line).strip()
    if not clean_title:
        clean_title = "Câu Chuyện Mới"

    lang = detect_language(req.text)
    if lang == "vi":
        # Chuẩn hóa giọng đọc tiếng Việt chất lượng cao cho review podcast
        if not req.voice or req.voice.startswith("en-"):
            # giọng mặc định (.env DEFAULT_VOICE) nếu là giọng Việt; giọng Anh không đọc được truyện Việt
            chosen_voice = DEFAULT_VOICE if DEFAULT_VOICE.lower().startswith(("vi-", "vieneu")) else "vi-VN-NamMinhNeural"
        else:
            chosen_voice = req.voice
    else:
        chosen_voice = req.voice or "en-US-AndrewMultilingualNeural"

    chosen_image_provider = req.image_provider or DEFAULT_IMAGE_PROVIDER or "meta_muse_cloud"
    if chosen_image_provider == "9router_gemini" and not req.image_provider:
        chosen_image_provider = "meta_muse_cloud"

    p_req = ProjectCreateRequest(
        name=clean_title,
        style_preset=req.style_preset or "manga_murata_battle",
        character_preset_id=req.character_preset_id,
        character_anchor=req.character_anchor or "",
        character_reference_image=req.character_reference_image,
        voice=chosen_voice,
        image_provider=chosen_image_provider,
    )
    project = create_project(p_req)

    # Split text into scenes using 9router Gemini 3.8 Flash for maximum cinematic shot variety
    analysis_fallback_reason = None
    # "9router": AI chia hết; "partial": AI chia, vài phần bài chia offline; "offline": cả bài chia offline
    analysis_provider = "9router"
    try:
        analysis = await analyze_vox_script_async(
            full_text=req.text,
            pacing=req.pacing or "fast",
            style_preset=project.style_preset,
            character_anchor=project.character_anchor,
            provider="9router",
        )
        scenes_data = analysis.get("scenes", [])
        analysis_fallback_reason = analysis.get("fallback_reason")
        if analysis.get("provider_used") == "llm_partial":
            analysis_provider = "partial"
    except Exception as e:
        logger.warning(f"9router scene analysis failed ({e}), falling back to offline splitter.")
        analysis_fallback_reason = f"Lỗi phân tích cảnh bằng 9router: {e}"
        scenes_data = []
    if analysis_fallback_reason:
        logger.warning(f"create-from-script dùng bộ chia offline: {analysis_fallback_reason}")

    if not scenes_data:
        scenes_data = split_text_into_scenes(
            full_text=req.text,
            pacing=req.pacing or "fast",
            style_preset=project.style_preset,
            character_anchor=project.character_anchor,
        )

    created_scenes = []
    for sc in scenes_data:
        c_req = SceneCreateRequest(
            text=sc["text"],
            image_prompt=sc["image_prompt"],
            camera_motion=sc.get("camera_motion", "zoom_in"),
            sfx_cue=sc.get("sfx_cue", []),
            metadata=sc.get("metadata", {
                "narrative_beat": sc.get("narrative_beat", "setting"),
                "estimated_duration": sc.get("estimated_duration", 4.0),
            }),
        )
        scene_obj = add_scene(project.id, c_req)
        if scene_obj:
            created_scenes.append(scene_obj)

    # Generate real scene images immediately using Meta Muse Cloud so Step 2 is fully populated
    if req.generate_initial_images and created_scenes:
        for idx, sc in enumerate(created_scenes, start=1):
            media_paths = get_scene_media_paths(project.id, sc.id)
            try:
                img_res = await generate_image(
                    prompt=sc.image_prompt,
                    style_preset=project.style_preset,
                    character=project.character,
                    character_anchor=project.character_anchor,
                    reference_image=project.character_reference_image,
                    provider=project.image_provider or DEFAULT_IMAGE_PROVIDER or "meta_muse_cloud",
                    output_path=str(media_paths["image"]),
                    scene_index=idx,
                )
            except Exception as e:
                img_res = {"success": False, "error": str(e)}
            if _apply_image_result(sc, img_res, project.id):
                sc.status = "imaged"
            else:
                logger.warning(f"create-from-script: scene {sc.id} image failed: {img_res.get('error')}")

        update_project(project.id, ProjectUpdateRequest(scenes=created_scenes))

    project = get_project(project.id) or project
    if not project.scenes and created_scenes:
        project.scenes = created_scenes
    # Ghi lại cách chia cảnh để giao diện cảnh báo khi prompt ảnh chỉ là mẫu offline
    project.metadata["scene_analysis"] = {
        "provider": "offline" if analysis_fallback_reason and analysis_provider != "partial" else analysis_provider,
        "fallback_reason": analysis_fallback_reason,
    }
    save_project(project)
    return project

@router.post("/projects/create-1click-pipeline")
async def create_1click_pipeline(req: CreateProjectFromScriptRequest):
    """Dedicated 1-Click Pipeline endpoint for producing story studio projects."""
    return await create_project_from_script(req)

@router.post("/projects/{project_id}/scenes/{scene_id}/upload-media")
async def upload_scene_media(
    project_id: str,
    scene_id: str,
    file: UploadFile = File(...),
    kind: str = Form("image"),
):
    """
    Người dùng tự tải ảnh/video cho một cảnh. Lưu đúng vào file mà bước dựng đọc:
    ảnh → images/{scene}.jpg, video → videos/{scene}_muse.mp4 (clip gốc, không phải đoạn dựng).
    """
    if kind not in ("image", "video"):
        raise HTTPException(status_code=400, detail="kind phải là 'image' hoặc 'video'.")
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found.")

    content = await read_upload_limited(file)
    if not content:
        raise HTTPException(status_code=400, detail="File tải lên đang trống.")
    media = get_scene_media_paths(project_id, scene_id)

    if kind == "image":
        try:
            from PIL import Image
            import io
            with Image.open(io.BytesIO(content)) as img:
                img = img.convert("RGB")
                media["image"].parent.mkdir(parents=True, exist_ok=True)
                img.save(media["image"], "JPEG", quality=95)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"File không phải ảnh hợp lệ: {e}")
        scene.image_path = str(media["image"])
        scene.image_url = f"/api/projects/{project_id}/media/images/{scene_id}.jpg"
        scene.status_image = "ready"
        scene.media_view_mode = "image"
        for key in ("image_error", "image_fallback", "image_placeholder"):
            scene.metadata.pop(key, None)
    else:
        from routers.muse_bridge import detect_media_kind
        if detect_media_kind(content) != "video":
            raise HTTPException(status_code=400, detail="File không phải video MP4/MOV/WebM hợp lệ.")
        media["motion_video"].parent.mkdir(parents=True, exist_ok=True)
        media["motion_video"].write_bytes(content)
        scene.motion_video_path = str(media["motion_video"])
        scene.video_url = f"/api/projects/{project_id}/media/videos/{media['motion_video'].name}"
        scene.video_segment_url = scene.video_url
        scene.media_view_mode = "video"
        scene.status_video = "ready"

    if scene.voice_audio_path:
        scene.status = "ready"
    update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))
    return {"success": True, "scene": scene, "project_id": project_id}


@router.get("/projects/{project_id}")
async def get_project_detail(project_id: str):
    """Get project details."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project

@router.put("/projects/{project_id}")
async def update_project_detail(project_id: str, req: ProjectUpdateRequest):
    """Update project details."""
    for sc in req.scenes or []:
        require_safe_id(sc.id, "scene_id")
        for field in SCENE_PATH_FIELDS:
            _require_studio_media_path(getattr(sc, field, None), field)
    _require_studio_media_path(req.thumbnail_path, "thumbnail_path")
    if req.scenes:
        _keep_server_media(get_project(project_id), req.scenes)
    project = update_project(project_id, req)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project

@router.delete("/projects/{project_id}")
async def delete_project_by_id(project_id: str):
    """Delete a project."""
    try:
        success = delete_project(project_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    if not success:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"success": True, "deleted_id": project_id}

@router.get("/projects/{project_id}/download")
async def download_final_video(project_id: str):
    """Download the final rendered MP4 video."""
    paths = get_render_media_paths(project_id)
    if not paths["final_video"].exists():
        raise HTTPException(status_code=404, detail="Final video has not been rendered yet.")
    return FileResponse(
        paths["final_video"],
        media_type="video/mp4",
        filename=f"{project_id}_story.mp4",
    )

@router.get("/projects/{project_id}/download-srt")
async def download_final_srt(project_id: str):
    """Download the final synchronized SRT subtitles."""
    paths = get_render_media_paths(project_id)
    if not paths["final_srt"].exists():
        raise HTTPException(status_code=404, detail="Final subtitles (.srt) have not been rendered yet.")
    return FileResponse(
        paths["final_srt"],
        media_type="text/plain; charset=utf-8",
        filename=f"{project_id}_subtitles.srt",
    )

@router.get("/projects/{project_id}/download-ass")
async def download_final_ass(project_id: str):
    """Download the final Kinetic Karaoke ASS subtitles."""
    paths = get_render_media_paths(project_id)
    final_ass = paths["final_video"].with_suffix(".ass")
    if not final_ass.exists():
        raise HTTPException(status_code=404, detail="Final subtitles (.ass) have not been generated yet.")
    return FileResponse(
        final_ass,
        media_type="text/plain; charset=utf-8",
        filename=f"{project_id}_kinetic_subtitles.ass",
    )

@router.post("/projects/{project_id}/thumbnail/generate")
async def api_generate_thumbnail(project_id: str, data: Dict[str, Any] = Body(default_factory=dict)):
    """Generate or customize a 16:9 Full HD click-magnet YouTube Thumbnail."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    scene_index = data.get("scene_index")
    custom_headline = data.get("custom_headline")
    custom_subtext = data.get("custom_subtext")
    badge_text = data.get("badge_text")

    try:
        res = await asyncio.to_thread(  # PIL vẽ ảnh: chạy ở luồng phụ để server không khựng
            generate_youtube_thumbnail,
            project=project,
            scene_index=scene_index,
            custom_headline=custom_headline,
            custom_subtext=custom_subtext,
            badge_text=badge_text,
        )
    except ThumbnailError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    project.thumbnail_path = res["thumbnail_path"]
    project.thumbnail_url = res["thumbnail_url"]
    update_project(project_id, ProjectUpdateRequest(
        thumbnail_path=res["thumbnail_path"],
        thumbnail_url=res["thumbnail_url"],
    ))

    return res

@router.get("/projects/{project_id}/thumbnail")
async def get_project_thumbnail(project_id: str):
    """Serve the 16:9 Full HD YouTube Thumbnail image."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    thumb_file = PROJECTS_DIR / project_id / "renders" / "thumbnail.jpg"
    if not thumb_file.exists():
        # Chưa có thì vẽ luôn (chữ mặc định); font thiếu chữ thì báo lý do thay vì ảnh lỗi
        try:
            await asyncio.to_thread(generate_youtube_thumbnail, project=project)
        except ThumbnailError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None

    if not thumb_file.exists():
        raise HTTPException(status_code=404, detail="Thumbnail could not be generated.")

    return FileResponse(
        thumb_file,
        media_type="image/jpeg",
        filename=f"{project_id}_youtube_thumbnail.jpg",
        headers={"Cache-Control": "public, max-age=3600"},
    )

# ----------------- SCENES CRUD -----------------

@router.post("/projects/{project_id}/scenes")
async def create_scene_for_project(project_id: str, req: SceneCreateRequest):
    """Add a scene to project."""
    scene = add_scene(project_id, req)
    if not scene:
        raise HTTPException(status_code=404, detail="Project not found.")
    return scene

@router.put("/projects/{project_id}/scenes/{scene_id}")
async def update_scene_for_project(project_id: str, scene_id: str, req: SceneUpdateRequest):
    """Update a scene."""
    scene = update_scene(project_id, scene_id, req)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene or project not found.")
    return scene

@router.delete("/projects/{project_id}/scenes/{scene_id}")
async def delete_scene_for_project(project_id: str, scene_id: str):
    """Delete a scene."""
    success = delete_scene(project_id, scene_id)
    if not success:
        raise HTTPException(status_code=404, detail="Scene not found.")
    return {"success": True, "scene_id": scene_id}

@router.post("/projects/{project_id}/scenes/reorder")
async def reorder_project_scenes(project_id: str, req: ReorderScenesRequest):
    """Reorder scenes in project."""
    scenes = reorder_scenes(project_id, req.scene_ids)
    if scenes is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return scenes

# ----------------- AI GENERATION ENDPOINTS -----------------

@router.post("/projects/{project_id}/scenes/{scene_id}/gen-voice")
async def generate_scene_voice(project_id: str, scene_id: str, req: VoiceGenRequest):
    """Generate Edge-TTS voice and synchronized SRT for a single scene with auto-upsert."""
    project = get_project(project_id)
    if not project:
        project = update_project(project_id, ProjectUpdateRequest(name="Dự án Story Studio"))

    target_scene = next((s for s in project.scenes if s.id == scene_id), None)
    if not target_scene:
        target_scene = Scene(
            id=scene_id,
            order=len(project.scenes) + 1,
            text=req.text or f"Cảnh {len(project.scenes) + 1}",
        )
        project.scenes.append(target_scene)
        update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))

    if req.text and req.text.strip():
        target_scene.text = req.text.strip()

    default_v = "en-US-AndrewMultilingualNeural" if detect_language(target_scene.text) == "en" else "vi-VN-NamMinhNeural"
    voice = req.voice or project.voice or default_v
    rate = req.rate or project.voice_rate or "+0%"
    pitch = req.pitch or project.voice_pitch or "+0Hz"

    media_paths = get_scene_media_paths(project_id, scene_id)

    try:
        tts_res = await generate_speech(
            text=target_scene.text,
            voice=voice,
            output_audio_path=str(media_paths["audio"]),
            output_srt_path=str(media_paths["srt"]),
            rate=rate,
            pitch=pitch,
        )

        _apply_voice_result(target_scene, tts_res, project_id)
        if target_scene.image_path:
            target_scene.status = "ready"
        else:
            target_scene.status = "voiced"

        _save_scene_fields(project_id, target_scene, VOICE_RESULT_FIELDS)

        return {
            "success": True,
            "scene_id": scene_id,
            "audio_url": target_scene.voice_audio_url,
            "srt_url": target_scene.srt_url,
            "duration": tts_res["duration"],
            "voice": tts_res.get("voice"),
            "requested_voice": tts_res.get("requested_voice", voice),
            "fallback_used": bool(tts_res.get("fallback_used")),
            "fallback_reason": tts_res.get("fallback_reason"),
            "scene": target_scene,
        }
    except Exception as e:
        target_scene.status_voice = "error"
        target_scene.metadata["voice_error"] = str(e)
        _save_scene_fields(project_id, target_scene, ["status_voice", "metadata"])
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")

@router.post("/projects/{project_id}/scenes/{scene_id}/gen-image")
async def generate_scene_image(project_id: str, scene_id: str, req: ImageGenRequest):
    """Generate image for a single scene with auto-upsert."""
    project = get_project(project_id)
    if not project:
        project = update_project(project_id, ProjectUpdateRequest(name="Dự án Story Studio"))

    target_scene = next((s for s in project.scenes if s.id == scene_id), None)
    if not target_scene:
        scene_num = req.scene_index or (len(project.scenes) + 1)
        target_scene = Scene(
            id=scene_id,
            order=scene_num,
            text=f"Cảnh #{scene_num}",
            image_prompt=req.prompt or "",
        )
        project.scenes.append(target_scene)
        update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))

    prompt = req.prompt or target_scene.image_prompt or target_scene.text
    style = req.style or target_scene.style_override or project.style_preset
    provider = req.provider or project.image_provider

    media_paths = get_scene_media_paths(project_id, scene_id)

    try:
        img_res = await generate_image(
            prompt=prompt,
            style_preset=style,
            character_anchor=req.character_anchor or project.character_anchor,
            character=req.character or getattr(project, "character", None),
            reference_image=req.reference_image or req.character_reference_image or getattr(project, "character_reference_image", None),
            provider=provider,
            seed=req.seed,
            output_path=str(media_paths["image"]),
            scene_index=target_scene.order,
        )
    except Exception as e:
        img_res = {"success": False, "error": str(e)}

    ok = _apply_image_result(target_scene, img_res, project_id)
    if ok:
        target_scene.status = "ready" if target_scene.voice_audio_path else "imaged"
    _save_scene_fields(project_id, target_scene, IMAGE_RESULT_FIELDS)

    if not ok:
        raise HTTPException(status_code=502, detail=f"Không tạo được ảnh: {img_res.get('error')}")

    return {
        "success": True,
        "scene_id": scene_id,
        "image_url": target_scene.image_url,
        "provider": img_res["provider"],
        "fallback_reason": img_res.get("fallback_reason"),
        "is_placeholder": bool(img_res.get("is_placeholder")),
        "full_prompt": img_res.get("full_prompt", ""),
        "scene": target_scene,
    }

@router.post("/gen-image")
async def generate_standalone_image(req: ImageGenRequest):
    """Direct standalone image generation without requiring prior project structure."""
    p_id = require_safe_id(req.project_id or "default_preview", "project_id")
    s_id = require_safe_id(req.scene_id or f"direct_{uuid.uuid4().hex[:6]}", "scene_id")
    media_paths = get_scene_media_paths(p_id, s_id)
    
    prompt = req.prompt or "Cinematic scene still"
    style = req.style or "manga_murata_battle"
    provider = req.provider or DEFAULT_IMAGE_PROVIDER or "meta_muse_cloud"
    order = req.scene_index or 1

    try:
        img_res = await generate_image(
            prompt=prompt,
            style_preset=style,
            character_anchor=req.character_anchor or "",
            character=req.character,
            reference_image=req.reference_image or req.character_reference_image,
            provider=provider,
            seed=req.seed,
            output_path=str(media_paths["image"]),
            scene_index=order,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")
    if not img_res.get("success"):
        raise HTTPException(status_code=502, detail=f"Không tạo được ảnh: {img_res.get('error')}")
    image_url = f"/api/projects/{p_id}/media/images/{s_id}.jpg"
    return {
        "success": True,
        "image_url": image_url,
        "provider": img_res["provider"],
        "fallback_reason": img_res.get("fallback_reason"),
        "is_placeholder": bool(img_res.get("is_placeholder")),
        "scene_id": s_id,
        "project_id": p_id,
    }

# ----------------- FULL VIDEO RENDER & WEBSOCKET -----------------

async def execute_full_render(project_id: str, render_id: str, options: RenderRequest):
    """Background pipeline executing the 4-step movie rendering process."""
    try:
        project = get_project(project_id)
        if not project or not project.scenes:
            raise ValueError("Project has no scenes to render.")

        await broadcast_render_update(render_id, {
            "status": "rendering",
            "progress": 5,
            "step": 1,
            "step_label": "Kiểm tra và chuẩn bị dữ liệu phân cảnh...",
            "logs": ["Bắt đầu quy trình dựng video..."],
        })

        # Step 1: Ensure all voice & images exist
        total_scenes = len(project.scenes)
        for i, scene in enumerate(project.scenes, start=1):
            media = get_scene_media_paths(project_id, scene.id)

            scene_logs: List[str] = []
            if not media["audio"].exists() or not scene.voice_audio_path:
                tts = await generate_speech(
                    text=scene.text,
                    voice=project.voice,
                    output_audio_path=str(media["audio"]),
                    output_srt_path=str(media["srt"]),
                )
                _apply_voice_result(scene, tts, project_id)
                if tts.get("fallback_used"):
                    scene_logs.append(f"⚠ Scene {i}: dùng giọng dự phòng {tts.get('voice')} ({tts.get('fallback_reason')}).")

            if _scene_render_input(scene, media) is None:
                try:
                    img = await generate_image(
                        prompt=scene.image_prompt or scene.text,
                        style_preset=project.style_preset,
                        character_anchor=project.character_anchor,
                        character=project.character,
                        reference_image=project.character_reference_image,
                        provider=project.image_provider,
                        output_path=str(media["image"]),
                        scene_index=scene.order,
                    )
                except Exception as e:
                    img = {"success": False, "error": str(e)}
                if not _apply_image_result(scene, img, project_id):
                    update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))
                    raise RuntimeError(f"Scene {i} chưa có ảnh/video và tạo ảnh thất bại: {img.get('error')}")
                if img.get("fallback_reason"):
                    scene_logs.append(f"⚠ Scene {i}: ảnh tạo bằng {img.get('provider')} ({img['fallback_reason']}).")

            cur_p = int(5 + (i / total_scenes) * 20)
            await broadcast_render_update(render_id, {
                "progress": cur_p,
                "logs": active_renders[render_id]["logs"] + scene_logs + [f"Đã kiểm tra Scene {i}/{total_scenes}: Âm thanh & Ảnh sẵn sàng."],
            })

        update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))

        # Step 2: Render individual scene segments (25% -> 60%)
        await broadcast_render_update(render_id, {
            "step": 2,
            "step_label": "Dựng phân đoạn Ken Burns video cho từng Scene...",
        })

        scene_video_paths = []
        scene_srt_infos = []

        for i, scene in enumerate(project.scenes, start=1):
            media = get_scene_media_paths(project_id, scene.id)
            motion = options.camera_motion or scene.camera_motion or project.default_motion

            # Cảnh dùng video (Muse hoặc tải lên) thì lấy clip gốc làm đầu vào, giữ âm thanh môi trường (25%)
            input_media = _scene_render_input(scene, media)
            if not input_media:
                raise RuntimeError(f"Scene {i} không có ảnh hoặc video để dựng.")

            chosen_trans = options.transition or project.transition or "dip_to_black"
            v_res = await render_scene_video(
                image_path=input_media,
                audio_path=str(media["audio"]) if media["audio"].exists() else None,
                output_path=str(media["video"]),
                duration=scene.duration,
                camera_motion=motion,
                resolution=options.resolution or project.resolution,
                fps=options.fps or project.fps,
                transition=chosen_trans,
            )

            scene.video_segment_path = v_res["video_path"]
            scene.metadata["segment_rendered"] = True
            scene_video_paths.append(v_res["video_path"])
            scene_srt_infos.append({
                "srt_path": str(media["srt"]),
                "duration": v_res["duration"],
            })

            cur_p = int(25 + (i / total_scenes) * 35)
            await broadcast_render_update(render_id, {
                "progress": cur_p,
                "logs": active_renders[render_id]["logs"] + [f"Render xong video phân đoạn Scene {i} (Ken Burns: {motion})."],
            })

        # Step 3 & 4: Assemble video + BGM Ducking + Hardsub (60% -> 100%)
        await broadcast_render_update(render_id, {
            "step": 3,
            "step_label": "Ghép nối video phân đoạn và đồng bộ phụ đề...",
            "progress": 65,
        })

        render_paths = get_render_media_paths(project_id)
        bgm_track_id = options.bgm or project.bgm_track

        bgm_file_path = None
        if bgm_track_id and bgm_track_id != "none":
            candidate = BGM_DIR / f"{bgm_track_id}.mp3"
            if candidate.exists():
                bgm_file_path = str(candidate)

        def sync_progress(percent: int, step_num: int, message: str):
            asyncio.create_task(broadcast_render_update(render_id, {
                "progress": percent,
                "step": step_num,
                "step_label": message,
                "logs": active_renders[render_id]["logs"] + [message],
            }))

        chosen_trans = options.transition or project.transition or "dip_to_black"
        chosen_sub_style = options.subtitle_style or project.subtitle_style or "kinetic_pop"
        scenes_data_list = [sc.model_dump() for sc in project.scenes]

        assemble_res = await assemble_full_video(
            scene_video_paths=scene_video_paths,
            scene_srt_infos=scene_srt_infos,
            output_video_path=str(render_paths["final_video"]),
            bgm_path=bgm_file_path,
            bgm_volume=options.bgm_volume if options.bgm_volume is not None else project.bgm_volume,
            ducking=options.ducking if options.ducking is not None else project.ducking,
            hardsub=options.hardsub if options.hardsub is not None else project.hardsub,
            subtitle_style=chosen_sub_style,
            resolution=options.resolution or project.resolution,
            transition=chosen_trans,
            scenes_data=scenes_data_list,
            progress_callback=sync_progress,
        )

        final_video_url = f"/api/projects/{project_id}/media/renders/story_final.mp4"
        project.final_video_path = assemble_res["video_path"]
        project.final_video_url = final_video_url

        # Tự vẽ thumbnail mặc định sau khi dựng (gói SEO làm riêng ở Bước 4)
        try:
            t_res = await asyncio.to_thread(generate_youtube_thumbnail, project)
            project.thumbnail_path = t_res["thumbnail_path"]
            project.thumbnail_url = t_res["thumbnail_url"]
        except Exception as e:
            logger.warning(f"Auto thumbnail generation warning: {e}")

        update_project(project_id, ProjectUpdateRequest(
            scenes=project.scenes,
            thumbnail_path=project.thumbnail_path,
            thumbnail_url=project.thumbnail_url,
        ))

        # Save to project json directly to ensure persistence
        p_obj = get_project(project_id)
        if p_obj:
            p_obj.final_video_path = assemble_res["video_path"]
            p_obj.final_video_url = final_video_url
            save_project(p_obj)

        await broadcast_render_update(render_id, {
            "status": "completed",
            "progress": 100,
            "step": 4,
            "step_label": "Hoàn tất dựng video truyện thành công!",
            "video_url": final_video_url,
            "video_path": assemble_res["video_path"],
            "logs": active_renders[render_id]["logs"] + [
                f"Xuất file thành công: {assemble_res['video_path']}",
                f"Thời lượng tổng: {assemble_res['duration']}s",
            ],
        })

    except Exception as e:
        err_msg = str(e)
        await broadcast_render_update(render_id, {
            "status": "failed",
            "progress": 0,
            "error": err_msg,
            "logs": (active_renders.get(render_id, {}).get("logs", [])) + [f"LỖI RENDER: {err_msg}"],
        })

@router.post("/projects/{project_id}/render")
async def start_render(project_id: str, options: RenderRequest, background_tasks: BackgroundTasks):
    """Start full movie render pipeline asynchronously."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    if not project.scenes:
        raise HTTPException(status_code=400, detail="Project must have at least one scene to render.")

    render_id = f"render_{uuid.uuid4().hex[:8]}"
    active_renders[render_id] = {
        "render_id": render_id,
        "project_id": project_id,
        "status": "queued",
        "progress": 0,
        "step": 1,
        "step_label": "Đang chuẩn bị hàng đợi...",
        "logs": ["Đã nhận yêu cầu dựng video."],
        "video_url": None,
        "video_path": None,
        "error": None,
    }

    background_tasks.add_task(execute_full_render, project_id, render_id, options)

    return {
        "success": True,
        "render_id": render_id,
        "project_id": project_id,
        "status": "queued",
        "status_url": f"/api/render-status/{render_id}",
        "ws_url": f"/ws/render/{render_id}",
    }

@router.get("/render-status/{render_id}")
async def get_render_status(render_id: str):
    """Get the current render job status."""
    if render_id not in active_renders:
        raise HTTPException(status_code=404, detail="Render task not found.")
    return active_renders[render_id]

# ----------------- MONEYPRINTERTURBO STEPPER LONG VIDEO PRODUCER -----------------

async def execute_produce_long_video(project_id: str, render_id: str, req: LongVideoProduceRequest):
    """
    Background pipeline executing the 5-phase MoneyPrinterTurbo Stepper production workflow:
    (1) Phân tích kịch bản & khóa nhân vật (15%)
    (2) Thu âm Edge-TTS & trích xuất phụ đề (40%)
    (3) Sinh hình ảnh chất lượng cao 8K theo Style Preset (65%)
    (4) Dựng video phân cảnh với hiệu ứng chuyển động FX (85%)
    (5) Ghép video hoàn chỉnh 1080p + Audio Ducking BGM + Phụ đề (100%)
    """
    try:
        project = get_project(project_id)
        if not project:
            project = update_project(project_id, ProjectUpdateRequest(name="Dự án Video Dài MoneyPrinterTurbo"))

        # Update project configs if passed
        if req.style_preset:
            project.style_preset = req.style_preset
        if getattr(req, "image_provider", None):
            project.image_provider = req.image_provider
        if req.character_anchor is not None:
            project.character_anchor = req.character_anchor
        if req.voice:
            project.voice = req.voice
        if req.voice_rate:
            project.voice_rate = req.voice_rate
        if req.voice_pitch:
            project.voice_pitch = req.voice_pitch
        if req.resolution:
            project.resolution = req.resolution
        if req.fps:
            project.fps = req.fps
        if req.bgm:
            project.bgm_track = req.bgm
        if req.bgm_volume is not None:
            project.bgm_volume = req.bgm_volume
        if req.ducking is not None:
            project.ducking = req.ducking
        if req.hardsub is not None:
            project.hardsub = req.hardsub
        ref_img = getattr(req, "character_reference_image", None) or getattr(req, "reference_image", None)
        if ref_img:
            project.character_reference_image = ref_img

        # ----------------- PHASE 1: SCRIPT & CHARACTER ANCHOR (0% -> 15%) -----------------
        await broadcast_render_update(render_id, {
            "status": "rendering",
            "progress": 5,
            "step": 1,
            "step_label": "Bước 1/5: Phân tích kịch bản & Khóa đặc điểm nhân vật đồng bộ...",
            "logs": ["Bắt đầu chu trình sản xuất Video Dài theo Stepper Pipeline (MoneyPrinterTurbo)..."],
        })

        analysis_note = None  # lý do cảnh được chia offline (prompt ảnh mẫu chung), để báo trong log
        if req.text and req.text.strip():
            pacing = req.pacing or "fast"
            try:
                vox_res = await analyze_vox_script_async(
                    full_text=req.text.strip(),
                    pacing=pacing,
                    style_preset=project.style_preset,
                    character_anchor=project.character_anchor,
                    provider="9router",
                )
                raw_scenes = vox_res.get("scenes", [])
                analysis_note = vox_res.get("fallback_reason")
            except Exception as e:
                analysis_note = f"Lỗi phân tích cảnh bằng 9router: {e}"
                raw_scenes = split_text_into_vox_scenes_offline(
                    full_text=req.text.strip(),
                    pacing=pacing,
                    style_preset=project.style_preset,
                    character_anchor=project.character_anchor,
                )["scenes"]
            if analysis_note:
                logger.warning(f"produce-long-video dùng bộ chia offline: {analysis_note}")

            new_scenes = []
            for idx, sc in enumerate(raw_scenes, start=1):
                motion = req.camera_motion or sc.get("camera_motion") or project.default_motion
                sc_id = f"scene_{idx:02d}_{uuid.uuid4().hex[:4]}"
                new_scenes.append(Scene(
                    id=sc_id,
                    order=idx,
                    text=sc.get("text", f"Cảnh #{idx}"),
                    image_prompt=sc.get("image_prompt", ""),
                    camera_motion=motion,
                    status="draft"
                ))
            project.scenes = new_scenes
            update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))

        if not project.scenes:
            raise ValueError("Không tìm thấy phân cảnh nào để sản xuất video.")

        total_scenes = len(project.scenes)
        await broadcast_render_update(render_id, {
            "progress": 15,
            "step": 1,
            "step_label": f"Bước 1 hoàn tất: Kịch bản gồm {total_scenes} phân cảnh & Nhân vật đã khóa.",
            "logs": active_renders[render_id]["logs"] + [
                f"[Giai đoạn 1/5] Đã thiết lập kịch bản gồm {total_scenes} cảnh. Nhân vật: {project.character_anchor or 'Mặc định'}."
            ] + ([f"⚠ Chia cảnh: {analysis_note}"] if analysis_note else []),
        })

        # ----------------- PHASE 2: EDGE-TTS & SRT (15% -> 40%) -----------------
        await broadcast_render_update(render_id, {
            "step": 2,
            "step_label": f"Bước 2/5: Thu âm Edge-TTS tiếng Việt & trích xuất phụ đề SRT ({project.voice})...",
            "progress": 18,
        })

        for i, scene in enumerate(project.scenes, start=1):
            media = get_scene_media_paths(project_id, scene.id)
            if media["audio"].exists() and media["srt"].exists() and getattr(scene, "duration", None) and scene.duration > 0 and (scene.voice_audio_path or scene.voice_audio_url):
                scene.voice_audio_path = str(media["audio"])
                scene.voice_audio_url = f"/api/projects/{project_id}/media/audio/{scene.id}.mp3"
                scene.srt_path = str(media["srt"])
                scene.srt_url = f"/api/projects/{project_id}/media/audio/{scene.id}.srt"
                scene.status = "voiced"
                log_msg = f"[Giai đoạn 2/5] Cảnh {i}/{total_scenes}: Tái sử dụng âm thanh có sẵn ({scene.duration:.1f}s) & SRT."
            else:
                sample_text = (project.scenes[0].text if project.scenes else "")
                default_proj_voice = "en-US-AndrewMultilingualNeural" if detect_language(sample_text) == "en" else "vi-VN-NamMinhNeural"
                tts_res = await generate_speech(
                    text=scene.text,
                    voice=project.voice or default_proj_voice,
                    output_audio_path=str(media["audio"]),
                    output_srt_path=str(media["srt"]),
                    rate=project.voice_rate or "+0%",
                    pitch=project.voice_pitch or "+0Hz",
                )
                _apply_voice_result(scene, tts_res, project_id)
                scene.status = "voiced"
                log_msg = f"[Giai đoạn 2/5] Cảnh {i}/{total_scenes}: Đã thu âm ({tts_res['duration']}s) & đồng bộ SRT."
                if tts_res.get("fallback_used"):
                    log_msg += f" ⚠ Dùng giọng dự phòng {tts_res.get('voice')} ({tts_res.get('fallback_reason')})."

            cur_p = int(15 + (i / total_scenes) * 25)
            await broadcast_render_update(render_id, {
                "progress": cur_p,
                "logs": active_renders[render_id]["logs"] + [log_msg],
            })

        update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))

        # ----------------- PHASE 3: IMAGE GENERATION 8K (40% -> 65%) -----------------
        await broadcast_render_update(render_id, {
            "step": 3,
            "step_label": f"Bước 3/5: Sinh hình ảnh chất lượng cao 8K theo Style Preset ({project.style_preset})...",
            "progress": 40,
        })

        for i, scene in enumerate(project.scenes, start=1):
            media = get_scene_media_paths(project_id, scene.id)
            img_note = ""
            if _scene_render_input(scene, media) is None:
                try:
                    img_res = await generate_image(
                        prompt=scene.image_prompt or scene.text,
                        style_preset=project.style_preset,
                        character_anchor=project.character_anchor,
                        character=project.character,
                        reference_image=project.character_reference_image,
                        provider=project.image_provider,
                        output_path=str(media["image"]),
                        scene_index=scene.order,
                    )
                except Exception as e:
                    img_res = {"success": False, "error": str(e)}
                if not _apply_image_result(scene, img_res, project_id):
                    update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))
                    raise RuntimeError(f"Cảnh {i} chưa có ảnh/video và tạo ảnh thất bại: {img_res.get('error')}")
                if img_res.get("fallback_reason"):
                    img_note = f" ⚠ Ảnh tạo bằng {img_res.get('provider')} ({img_res['fallback_reason']})."

            scene.status = "ready"
            cur_p = int(40 + (i / total_scenes) * 25)
            await broadcast_render_update(render_id, {
                "progress": cur_p,
                "logs": active_renders[render_id]["logs"] + [
                    f"[Giai đoạn 3/5] Cảnh {i}/{total_scenes}: Hình ảnh sẵn sàng.{img_note}"
                ],
            })

        update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))

        # ----------------- PHASE 4: MOTION FX SCENE SEGMENTS (65% -> 85%) -----------------
        await broadcast_render_update(render_id, {
            "step": 4,
            "step_label": "Bước 4/5: Dựng video phân cảnh với hiệu ứng chuyển động Motion FX...",
            "progress": 65,
        })

        scene_video_paths = []
        scene_srt_infos = []

        for i, scene in enumerate(project.scenes, start=1):
            media = get_scene_media_paths(project_id, scene.id)
            motion = req.camera_motion or scene.camera_motion or project.default_motion

            chosen_trans = req.transition or project.transition or "dip_to_black"
            input_media = _scene_render_input(scene, media)
            if not input_media:
                raise RuntimeError(f"Cảnh {i} không có ảnh hoặc video để dựng.")
            v_res = await render_scene_video(
                image_path=input_media,
                audio_path=str(media["audio"]),
                output_path=str(media["video"]),
                duration=scene.duration,
                camera_motion=motion,
                resolution=req.resolution or project.resolution,
                fps=req.fps or project.fps,
                transition=chosen_trans,
            )

            scene.video_segment_path = v_res["video_path"]
            scene.metadata["segment_rendered"] = True
            scene_video_paths.append(v_res["video_path"])
            scene_srt_infos.append({
                "srt_path": str(media["srt"]),
                "duration": v_res["duration"],
            })

            cur_p = int(65 + (i / total_scenes) * 20)
            await broadcast_render_update(render_id, {
                "progress": cur_p,
                "logs": active_renders[render_id]["logs"] + [
                    f"[Giai đoạn 4/5] Cảnh {i}/{total_scenes}: Dựng xong video phân đoạn FX ({motion})."
                ],
            })

        # ----------------- PHASE 5: ASSEMBLE FULL MOVIE + DUCKING + HARDSUB (85% -> 100%) -----------------
        await broadcast_render_update(render_id, {
            "step": 5,
            "step_label": "Bước 5/5: Ghép video hoàn chỉnh 1080p + Audio Ducking BGM + Phụ đề...",
            "progress": 87,
        })

        render_paths = get_render_media_paths(project_id)
        bgm_track_id = req.bgm or project.bgm_track

        bgm_file_path = None
        if bgm_track_id and bgm_track_id != "none":
            candidate = BGM_DIR / f"{bgm_track_id}.mp3"
            if candidate.exists():
                bgm_file_path = str(candidate)

        def sync_progress(percent: int, step_num: int, message: str):
            mapped_p = int(85 + (percent / 100.0) * 15)
            asyncio.create_task(broadcast_render_update(render_id, {
                "progress": min(99, mapped_p),
                "step": 5,
                "step_label": message,
                "logs": active_renders[render_id]["logs"] + [message],
            }))

        chosen_trans = req.transition or project.transition or "dip_to_black"
        chosen_sub_style = req.subtitle_style or project.subtitle_style or "kinetic_pop"
        scenes_data_list = [sc.model_dump() for sc in project.scenes]

        assemble_res = await assemble_full_video(
            scene_video_paths=scene_video_paths,
            scene_srt_infos=scene_srt_infos,
            output_video_path=str(render_paths["final_video"]),
            bgm_path=bgm_file_path,
            bgm_volume=req.bgm_volume if req.bgm_volume is not None else project.bgm_volume,
            ducking=req.ducking if req.ducking is not None else project.ducking,
            hardsub=req.hardsub if req.hardsub is not None else project.hardsub,
            subtitle_style=chosen_sub_style,
            resolution=req.resolution or project.resolution,
            transition=chosen_trans,
            scenes_data=scenes_data_list,
            progress_callback=sync_progress,
        )

        final_video_url = f"/api/projects/{project_id}/media/renders/story_final.mp4"
        final_srt_url = f"/api/projects/{project_id}/download-srt"

        project.final_video_path = assemble_res["video_path"]
        project.final_video_url = final_video_url

        # Tự vẽ thumbnail mặc định sau khi dựng (gói SEO làm riêng ở Bước 4)
        try:
            t_res = await asyncio.to_thread(generate_youtube_thumbnail, project)
            project.thumbnail_path = t_res["thumbnail_path"]
            project.thumbnail_url = t_res["thumbnail_url"]
        except Exception as e:
            logger.warning(f"Auto thumbnail generation warning: {e}")

        update_project(project_id, ProjectUpdateRequest(
            scenes=project.scenes,
            thumbnail_path=project.thumbnail_path,
            thumbnail_url=project.thumbnail_url,
        ))

        p_obj = get_project(project_id)
        if p_obj:
            p_obj.final_video_path = assemble_res["video_path"]
            p_obj.final_video_url = final_video_url
            save_project(p_obj)

        await broadcast_render_update(render_id, {
            "status": "completed",
            "progress": 100,
            "step": 5,
            "step_label": "Hoàn tất sản xuất Video Dài thành công (100%)!",
            "video_url": final_video_url,
            "video_path": assemble_res["video_path"],
            "srt_url": final_srt_url,
            "srt_path": str(render_paths["final_srt"]),
            "logs": active_renders[render_id]["logs"] + [
                f"[Giai đoạn 5/5] Hoàn tất ghép video: {assemble_res['video_path']}",
                f"[Giai đoạn 5/5] Tổng thời lượng: {assemble_res['duration']}s",
                "Video đã sẵn sàng phát tại Rạp Chiếu Phim Thành Phẩm!"
            ],
        })

    except Exception as e:
        err_msg = str(e)
        await broadcast_render_update(render_id, {
            "status": "failed",
            "progress": 0,
            "error": err_msg,
            "logs": (active_renders.get(render_id, {}).get("logs", [])) + [f"LỖI SẢN XUẤT: {err_msg}"],
        })

@router.post("/projects/{project_id}/produce-long-video")
async def produce_long_video_endpoint(
    project_id: str,
    req: LongVideoProduceRequest,
    background_tasks: BackgroundTasks,
):
    """
    Produce long video from A-Z with MoneyPrinterTurbo 5-phase Stepper pipeline:
    (1) Script parsing & character anchoring (15%)
    (2) Edge-TTS voice generation & timed SRT subtitles (40%)
    (3) 8K Style Preset Visual generation (65%)
    (4) Motion FX Scene segments (85%)
    (5) Video assembly + Studio BGM Ducking + Hardsub subtitles (100%)
    """
    project = get_project(project_id)
    if not project:
        project = update_project(project_id, ProjectUpdateRequest(name="Dự án Video Dài"))

    render_id = f"produce_{uuid.uuid4().hex[:8]}"
    active_renders[render_id] = {
        "render_id": render_id,
        "project_id": project_id,
        "status": "queued",
        "progress": 0,
        "step": 1,
        "step_label": "Đang chuẩn bị chu trình sản xuất video dài...",
        "logs": ["Đã tiếp nhận yêu cầu sản xuất video dài trọn gói."],
        "video_url": None,
        "video_path": None,
        "srt_url": None,
        "srt_path": None,
        "error": None,
    }

    background_tasks.add_task(execute_produce_long_video, project_id, render_id, req)

    return {
        "success": True,
        "render_id": render_id,
        "project_id": project_id,
        "status": "queued",
        "status_url": f"/api/render-status/{render_id}",
        "ws_url": f"/ws/render/{render_id}",
    }

# ----------------- MEDIA FILE STREAMING -----------------

@router.get("/projects/{project_id}/media/{folder}/{filename}")
async def serve_project_media(project_id: str, folder: str, filename: str):
    """Safely serve media assets (audio, images, videos, renders)."""
    allowed_folders = ["audio", "images", "videos", "renders"]
    if folder not in allowed_folders:
        raise HTTPException(status_code=400, detail="Invalid media folder.")

    target_dir = (PROJECTS_DIR / project_id / folder).resolve()
    if not target_dir.is_relative_to(PROJECTS_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected.")

    file_path = (target_dir / filename).resolve()
    if not file_path.is_relative_to(target_dir):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected.")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found.")

    media_type = "application/octet-stream"
    if filename.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
        media_type = "image/jpeg"
    elif filename.endswith(".png"):
        media_type = "image/png"
    elif filename.endswith(".mp4"):
        media_type = "video/mp4"
    elif filename.endswith(".srt"):
        media_type = "text/plain; charset=utf-8"

    return FileResponse(file_path, media_type=media_type)

# ----------------- COMIC / WEBTOON SLICER ENDPOINTS -----------------

@router.post("/comic/slice", response_model=ComicSliceResponse)
async def slice_comic_endpoint(
    file: UploadFile = File(...),
    mode: str = Form("grid"),
    reading_order: str = Form("ltr"),
    min_area_ratio: float = Form(0.03),
    project_id: Optional[str] = Form(None),
):
    """
    Upload a comic page or webtoon strip image and slice it into panels.
    Returns list of extracted panels with bounding boxes, aspect ratio, camera motion, and preview URLs.
    """
    if project_id:
        require_safe_id(project_id, "project_id")
    try:
        content = await read_upload_limited(file)
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        session_id = uuid.uuid4().hex[:8]
        if project_id:
            out_dir = PROJECTS_DIR / project_id / "images"
            out_dir.mkdir(parents=True, exist_ok=True)
            url_prefix = f"/api/projects/{project_id}/media/images"
        else:
            out_dir = COMIC_SLICES_DIR / session_id
            out_dir.mkdir(parents=True, exist_ok=True)
            url_prefix = f"/api/comic/media/{session_id}"

        result = await asyncio.to_thread(  # OpenCV trên ảnh lớn mất vài giây: luồng phụ
            slice_comic,
            image_input=content,
            output_dir=out_dir,
            mode=mode,
            reading_order=reading_order,
            min_area_ratio=min_area_ratio,
            url_prefix=url_prefix,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comic slicing failed: {str(e)}")

@router.post("/projects/{project_id}/comic/slice", response_model=ComicSliceResponse)
async def slice_comic_for_project(
    project_id: str,
    file: UploadFile = File(...),
    mode: str = Form("grid"),
    reading_order: str = Form("ltr"),
    min_area_ratio: float = Form(0.03),
):
    """
    Upload a comic/webtoon image directly into a specific project.
    Cropped panels are stored in the project's images directory and ready to be imported.
    """
    return await slice_comic_endpoint(
        file=file,
        mode=mode,
        reading_order=reading_order,
        min_area_ratio=min_area_ratio,
        project_id=project_id,
    )

@router.post("/projects/{project_id}/comic/import-scenes")
async def import_comic_panels_to_storyboard(
    project_id: str,
    req: ComicImportRequest,
):
    """
    Import extracted comic panels as Scenes in the storyboard of project_id.
    Each panel becomes a Scene with camera_motion pre-assigned according to aspect ratio.
    """
    project = get_project(project_id)
    if not project:
        project = update_project(project_id, ProjectUpdateRequest(name="Dự án Comic / Webtoon"))

    if req.clear_existing:
        project.scenes = []

    imported_scenes = []
    failed_panels = 0
    p_images_dir = PROJECTS_DIR / project_id / "images"
    p_images_dir.mkdir(parents=True, exist_ok=True)

    for idx, panel in enumerate(req.panels, start=len(project.scenes) + 1):
        # Skip unselected panels if flag is provided
        if panel.get("selected") is False:
            continue

        scene_id = f"scene_{idx:02d}_{uuid.uuid4().hex[:4]}"
        src_image_path = panel.get("image_path")
        camera_motion = panel.get("camera_motion") or "zoom_in"
        ar = panel.get("aspect_ratio", 1.0)
        
        # Target destination in project images folder
        dst_image_path = p_images_dir / f"{scene_id}.jpg"

        # Khung không chép được ảnh thì đánh dấu "Lỗi ảnh" (status_image="error"), không trỏ vào file không có
        image_error = None
        src_name = Path(str(src_image_path)).name if src_image_path else "(không có đường dẫn)"
        if not src_image_path or not os.path.exists(src_image_path):
            image_error = f"Không thấy ảnh khung tranh {src_name}"
        elif not is_within(src_image_path, COMIC_SLICES_DIR, PROJECTS_DIR / project_id, STATIC_DIR):
            logger.warning(f"Blocked unauthorized file copy in comic import: {src_image_path}")
            image_error = f"Ảnh {src_name} nằm ngoài thư mục cho phép"
        else:
            try:
                shutil.copy2(Path(src_image_path).resolve(), dst_image_path)
            except OSError as e:
                image_error = f"Chép ảnh {src_name} thất bại: {e}"
        if image_error:
            failed_panels += 1

        scene_text = panel.get("custom_text") or f"{req.text_prefix or 'Khung tranh'} #{idx}"
        metadata = {
            "source": "comic_slicer",
            "aspect_ratio": ar,
            "bbox": panel.get("bbox", {}),
            "is_wide": panel.get("is_wide", False),
        }
        if image_error:
            metadata["image_error"] = image_error

        new_scene = Scene(
            id=scene_id,
            order=idx,
            text=scene_text,
            image_prompt=f"Comic panel #{idx} (Aspect Ratio: {ar:.2f})",
            camera_motion=camera_motion,
            image_path=None if image_error else str(dst_image_path),
            image_url=None if image_error else f"/api/projects/{project_id}/media/images/{scene_id}.jpg",
            status="draft" if image_error else "imaged",
            status_image="error" if image_error else "ready",
            metadata=metadata,
        )

        project.scenes.append(new_scene)
        imported_scenes.append(new_scene)

    # Persist updated project
    update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))
    updated_proj = get_project(project_id)

    return {
        "success": True,
        "project_id": project_id,
        "imported_scenes_count": len(imported_scenes),
        "failed_panels": failed_panels,
        "total_scenes": len(updated_proj.scenes) if updated_proj else 0,
        "project": updated_proj,
    }

@router.get("/comic/media/{session_id}/{filename}")
async def serve_comic_media(session_id: str, filename: str):
    """
    Serve temporary sliced comic images and previews.
    """
    target_dir = (COMIC_SLICES_DIR / session_id).resolve()
    if not target_dir.is_relative_to(COMIC_SLICES_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected.")
    file_path = (target_dir / filename).resolve()
    if not file_path.is_relative_to(target_dir):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected.")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Comic media file not found.")

    media_type = "image/jpeg"
    if filename.endswith(".png"):
        media_type = "image/png"

    return FileResponse(file_path, media_type=media_type)

# ==============================================================================
# OP_CTOOL MASTER STORYBOARD & VIDEO PRODUCTION STUDIO ENDPOINTS
# ==============================================================================

@router.post("/storyboard/deconstruct", response_model=MasterStoryboard)
async def api_deconstruct_storyboard(req: DeconstructScriptRequest):
    """
    Deconstructs raw script into Master Storyboard JSON adhering to OP_CTOOL Spec:
    - DNA Style & Character Anchors
    - 9-Grid Sequential Narrative Slicing Prompts
    - 3-Layer Audio Design & SFX Cues
    - Dramatic Pacing Pauses (0.3s - 2.0s)
    - 2.5D Parallax Depth hints
    """
    try:
        storyboard = await deconstruct_script_async(
            raw_text=req.script_text,
            art_style=req.art_style or "Dark moody cinematic neo-noir, 35mm anamorphic film grain",
            tone_and_mood=req.tone_and_mood or "tense_suspense",
            batch_9_grid=req.batch_9_grid,
            provider=req.provider or "auto",
            api_key=req.api_key,
        )
        return storyboard
    except Exception as e:
        logger.error(f"Error in deconstruct_storyboard: {e}", exc_info=True)
        # Always fallback to offline deterministic parse
        return deconstruct_script_offline(
            raw_text=req.script_text,
            art_style=req.art_style or "Dark moody cinematic neo-noir, 35mm anamorphic film grain",
            tone_and_mood=req.tone_and_mood or "tense_suspense",
            batch_9_grid=req.batch_9_grid,
        )

@router.post("/storyboard/import")
async def api_import_master_storyboard(req: MasterStoryboardImportRequest):
    """
    Imports Master Storyboard JSON and instantiates a fully editable Story Studio Project.
    """
    if req.project_id is not None:
        require_safe_id(req.project_id, "project_id")
    project = master_storyboard_to_project(req.storyboard, project_id=req.project_id)
    require_safe_id(project.id, "project_id")
    for sc in project.scenes:
        require_safe_id(sc.id, "scene_id")
    if req.title:
        project.name = req.title

    ensure_project_dirs(project.id)
    save_project(project)

    return {
        "success": True,
        "project_id": project.id,
        "title": project.name,
        "scenes_count": len(project.scenes),
        "project": project,
    }

