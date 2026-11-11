"""Cảnh dựng từ clip hay từ ảnh: một nơi cho hai đường dựng (routers/api.py) và chốt tỉ lệ video Muse
(services/video_share.py). Chuyển từ routers/api.py ngày 11/11/2026 để services không phải import routers."""
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from config import PROJECTS_DIR, STATIC_DIR, STORY_STUDIO_DIR
from models.schemas import Scene
from security import is_within


def resolve_studio_path(value: str) -> Path:
    """Đường dẫn tương đối được tính từ thư mục gốc Story Studio (không phụ thuộc cwd)."""
    p = Path(value)
    return p if p.is_absolute() else STORY_STUDIO_DIR / p


def scene_motion_clip(scene: Scene, media: Dict[str, Path]) -> Optional[Path]:
    """
    Clip chuyển động gốc của cảnh (Muse hoặc tải lên). Không bao giờ trả về chính file
    segment dựng ra (media["video"]), để ffmpeg không đọc và ghi cùng một file.
    """
    segment = media["video"].resolve()
    candidates: List[Path] = []
    if scene.motion_video_path:
        candidates.append(resolve_studio_path(scene.motion_video_path))
    candidates.append(media["motion_video"])
    if scene.media_view_mode == "video" and scene.video_segment_path:
        # Dữ liệu cũ: clip gắn từ Gallery Muse được lưu vào video_segment_path
        candidates.append(resolve_studio_path(scene.video_segment_path))
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


def scene_render_input(scene: Scene, media: Dict[str, Path]) -> Optional[str]:
    """Đầu vào để dựng segment: clip chuyển động nếu cảnh đang dùng video, ngược lại là ảnh."""
    clip = scene_motion_clip(scene, media)
    has_image = media["image"].exists()
    if clip is not None and (scene.media_view_mode == "video" or not has_image):
        return str(clip)
    if has_image:
        return str(media["image"])
    return None
