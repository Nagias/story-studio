import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import PROJECTS_DIR
from models.schemas import (
    Project,
    Scene,
    Character,
    get_preset_character_by_id,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    SceneCreateRequest,
    SceneUpdateRequest,
)

import re

def _get_project_dir(project_id: str) -> Path:
    if not project_id or not re.fullmatch(r"[a-zA-Z0-9_\-]{1,64}", project_id):
        raise ValueError(f"Invalid project_id format: {project_id}")
    # Thư mục bắt đầu bằng "_" dành cho hệ thống (vd _cases chứa phân tích vụ án), không phải dự án.
    if project_id.startswith("_"):
        raise ValueError(f"Reserved project_id: {project_id}")
    p_dir = (PROJECTS_DIR / project_id).resolve()
    if not p_dir.is_relative_to(PROJECTS_DIR.resolve()) or p_dir == PROJECTS_DIR.resolve():
        raise ValueError("Project directory traversal detected.")
    return p_dir

def _get_project_json_path(project_id: str) -> Path:
    return _get_project_dir(project_id) / "project.json"

def _ensure_project_subdirs(project_id: str):
    p_dir = _get_project_dir(project_id)
    (p_dir / "audio").mkdir(parents=True, exist_ok=True)
    (p_dir / "images").mkdir(parents=True, exist_ok=True)
    (p_dir / "videos").mkdir(parents=True, exist_ok=True)
    (p_dir / "renders").mkdir(parents=True, exist_ok=True)

def _save_project(project: Project):
    p_dir = _get_project_dir(project.id)
    p_dir.mkdir(parents=True, exist_ok=True)
    json_path = _get_project_json_path(project.id)
    project.updated_at = datetime.utcnow().isoformat()
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(project.model_dump_json(indent=2))

def list_projects() -> List[Dict[str, Any]]:
    """List all projects found in PROJECTS_DIR."""
    projects = []
    if not PROJECTS_DIR.exists():
        return []

    for d in PROJECTS_DIR.iterdir():
        if d.is_dir():
            json_file = d / "project.json"
            if json_file.exists():
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        projects.append({
                            "id": data.get("id"),
                            "name": data.get("name"),
                            "description": data.get("description", ""),
                            "style_preset": data.get("style_preset"),
                            "voice": data.get("voice"),
                            "character_reference_image": data.get("character_reference_image"),
                            "scenes_count": len(data.get("scenes", [])),
                            "final_video_url": data.get("final_video_url"),
                            "updated_at": data.get("updated_at"),
                            "created_at": data.get("created_at"),
                        })
                except Exception:
                    pass

    projects.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return projects

def get_project(project_id: str) -> Optional[Project]:
    """Retrieve full project schema by id."""
    json_path = _get_project_json_path(project_id)
    if not json_path.exists():
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return Project.model_validate(data)
    except Exception:
        return None

def create_project(data: ProjectCreateRequest) -> Project:
    """Create a new story studio project."""
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    _ensure_project_subdirs(project_id)

    char_obj = data.character
    if not char_obj and data.character_preset_id:
        char_obj = get_preset_character_by_id(data.character_preset_id)

    anchor = data.character_anchor or ""
    if not anchor and char_obj:
        anchor = char_obj.generate_anchor_prompt()

    now = datetime.utcnow().isoformat()
    project = Project(
        id=project_id,
        name=data.name,
        description=data.description or "",
        voice=data.voice or "vi-VN-NamMinhNeural",
        style_preset=data.style_preset or "cinematic_realistic",
        character_anchor=anchor,
        character=char_obj,
        character_reference_image=data.character_reference_image,
        image_provider=data.image_provider or "meta_muse_cloud",
        scenes=[],
        created_at=now,
        updated_at=now,
    )
    _save_project(project)
    return project

def update_project(project_id: str, data: ProjectUpdateRequest) -> Optional[Project]:
    """Update or upsert project details."""
    project = get_project(project_id)
    if not project:
        _ensure_project_subdirs(project_id)
        char_obj = data.character
        if not char_obj and data.character_preset_id:
            char_obj = get_preset_character_by_id(data.character_preset_id)

        anchor = data.character_anchor or ""
        if not anchor and char_obj:
            anchor = char_obj.generate_anchor_prompt()

        now = datetime.utcnow().isoformat()
        project = Project(
            id=project_id,
            name=data.name or "Dự án Story Studio",
            description=data.description or "",
            voice=data.voice or "vi-VN-NamMinhNeural",
            style_preset=data.style_preset or "cinematic_realistic",
            character_anchor=anchor,
            character=char_obj,
            character_reference_image=data.character_reference_image,
            image_provider=data.image_provider or "meta_muse_cloud",
            scenes=[],
            created_at=now,
            updated_at=now,
        )

    update_dict = data.model_dump(exclude_unset=True)
    if "character_preset_id" in update_dict and update_dict["character_preset_id"]:
        preset_c = get_preset_character_by_id(update_dict["character_preset_id"])
        if preset_c:
            project.character = preset_c
            if not project.character_anchor:
                project.character_anchor = preset_c.generate_anchor_prompt()

    for key, value in update_dict.items():
        if key == "character_preset_id":
            continue
        if value is not None and hasattr(project, key):
            if key == "scenes" and isinstance(value, list):
                scenes_models = []
                for s in value:
                    if isinstance(s, Scene):
                        scenes_models.append(s)
                    elif isinstance(s, dict):
                        scenes_models.append(Scene.model_validate(s))
                    else:
                        scenes_models.append(s)
                setattr(project, key, scenes_models)
            else:
                setattr(project, key, value)

    _save_project(project)
    return project

def delete_project(project_id: str) -> bool:
    """Delete a project and all associated media files."""
    p_dir = _get_project_dir(project_id)
    if p_dir.exists():
        shutil.rmtree(p_dir, ignore_errors=True)
        return True
    return False

def add_scene(project_id: str, data: SceneCreateRequest) -> Optional[Scene]:
    """Add a new scene to the project."""
    project = get_project(project_id)
    if not project:
        return None

    _ensure_project_subdirs(project_id)
    scene_id = f"scene_{len(project.scenes) + 1}_{uuid.uuid4().hex[:4]}"
    order = len(project.scenes) + 1

    scene = Scene(
        id=scene_id,
        order=order,
        text=data.text,
        image_prompt=data.image_prompt or "",
        camera_motion=data.camera_motion or project.default_motion,
        style_override=data.style_override,
        sfx_cue=data.sfx_cue or [],
        status="draft",
        metadata=data.metadata or {},
    )

    project.scenes.append(scene)
    _save_project(project)
    return scene

def update_scene(project_id: str, scene_id: str, updates: SceneUpdateRequest) -> Optional[Scene]:
    """Update a scene within a project."""
    project = get_project(project_id)
    if not project:
        return None

    target_scene = None
    for s in project.scenes:
        if s.id == scene_id:
            target_scene = s
            break

    if not target_scene:
        return None

    up_dict = updates.model_dump(exclude_unset=True)
    for k, v in up_dict.items():
        if v is not None and hasattr(target_scene, k):
            setattr(target_scene, k, v)

    _save_project(project)
    return target_scene

def delete_scene(project_id: str, scene_id: str) -> bool:
    """Delete a scene and clean up its files."""
    project = get_project(project_id)
    if not project:
        return False

    initial_len = len(project.scenes)
    project.scenes = [s for s in project.scenes if s.id != scene_id]

    if len(project.scenes) == initial_len:
        return False

    # Reorder remaining scenes
    for idx, s in enumerate(project.scenes, start=1):
        s.order = idx

    _save_project(project)
    return True

def reorder_scenes(project_id: str, scene_ids: List[str]) -> Optional[List[Scene]]:
    """Reorder scenes according to the list of scene_ids."""
    project = get_project(project_id)
    if not project:
        return None

    scenes_by_id = {s.id: s for s in project.scenes}
    new_scenes = []

    for idx, s_id in enumerate(scene_ids, start=1):
        if s_id in scenes_by_id:
            s = scenes_by_id[s_id]
            s.order = idx
            new_scenes.append(s)

    # Append any scenes not in scene_ids
    for s in project.scenes:
        if s.id not in scene_ids:
            s.order = len(new_scenes) + 1
            new_scenes.append(s)

    project.scenes = new_scenes
    _save_project(project)
    return project.scenes

def get_scene_media_paths(project_id: str, scene_id: str) -> Dict[str, Path]:
    """Get absolute file paths for a scene's assets."""
    if not scene_id or not re.fullmatch(r"[a-zA-Z0-9_\-]{1,64}", scene_id):
        raise ValueError(f"Invalid scene_id format: {scene_id}")
    p_dir = _get_project_dir(project_id)
    return {
        "audio": p_dir / "audio" / f"{scene_id}.mp3",
        "srt": p_dir / "audio" / f"{scene_id}.srt",
        "image": p_dir / "images" / f"{scene_id}.jpg",
        # "video" là đoạn đã dựng (ghi lại mỗi lần render); clip Muse/tải lên nằm ở file riêng
        "video": p_dir / "videos" / f"{scene_id}.mp4",
        "motion_video": p_dir / "videos" / f"{scene_id}_muse.mp4",
    }

def get_render_media_paths(project_id: str) -> Dict[str, Path]:
    """Get render output paths for a project."""
    p_dir = _get_project_dir(project_id)
    return {
        "renders_dir": p_dir / "renders",
        "final_video": p_dir / "renders" / "story_final.mp4",
        "final_srt": p_dir / "renders" / "story_final.srt",
    }
