"""Chốt tỉ lệ video Muse: một nơi quyết định clip nào được tính, bao nhiêu phần trăm là đủ, và chặn dựng thành phẩm.

Chủ dự án (CLAUDE.md mục 1.2 câu 24): "50% là video gen từ muse, tạo chuyển động tốt hơn ảnh". Phải nhắc ít nhất 4 lần
(29/10, 06/11, hai lần 10/11/2026): vụ Khang Cúc Hoa ra 32,9% mà không ai báo; vụ xưởng sắt báo 65,5% nhưng clip chỉ
lia/zoom ảnh. Chủ dự án 11/11/2026: chặn khi dưới 45% (mục tiêu chọn cảnh vẫn 50%), áp dụng mọi dự án, cảnh phong cảnh
không người cũng được tính.

Clip được tính khi máy đo thấy có cử động (services/clip_motion.py) HOẶC chủ dự án đã xem và bấm "Đã xem, có cử động"
(`scene.metadata["motion_review"]`, gắn với đúng file clip: clip đổi thì phải duyệt lại). Clip chỉ lia/zoom, đứng hình,
hay không đo được mà chưa duyệt thì không tính.

Đường dựng (routers/api.py) phải gọi `require_gate()` trước `assemble_full_video()`: test kiến trúc
`test_every_final_render_passes_the_video_share_gate` chặn commit nếu thiếu. Bản nháp (`draft`) bỏ qua chốt nhưng ra file
riêng `DRAFT_VIDEO_NAME`, không ghi đè thành phẩm."""
import logging
from pathlib import Path
from typing import Iterable, Optional

from models.schemas import Project, Scene
from services import clip_motion, project_service
from services.climax_video import CLIMAX_RATIO, GATE_MIN
from services.dialogue_video import render_seconds
from services.render_inputs import scene_render_input
from services.tts_service import MediaDurationError, get_audio_duration
from services.video_service import moving_seconds

logger = logging.getLogger("story_studio.video_share")

VIDEO_EXTS = (".mp4", ".mov", ".webm", ".avi", ".mkv")
SHORT_CLIP_TOLERANCE_S = 0.5   # khung cuối đứng yên dài hơn chừng này thì báo cảnh có clip ngắn hơn lời kể
REVIEW_KEY = "motion_review"          # scene.metadata: chủ dự án đã xem clip, có cử động
DRAFT_VIDEO_NAME = "story_nhap_duoi_45.mp4"
GATE_CODE = "VIDEO_SHARE_LOW"


class VideoShareTooLow(RuntimeError):
    """Tỉ lệ video Muse dưới GATE_MIN: không dựng thành phẩm."""

    def __init__(self, report: dict):
        super().__init__(gate_problem(report) or "Tỉ lệ video Muse quá thấp")
        self.report = report


# ---------------------------------------------------------------------------------------------- duyệt tay một clip
def _clip_key(clip: Path) -> dict:
    st = clip.stat()
    return {"clip": clip.name, "size": st.st_size, "mtime": int(st.st_mtime)}


def review_stamp(clip: Path, ok: bool) -> dict:
    """Giá trị lưu vào scene.metadata[REVIEW_KEY] khi chủ dự án bấm duyệt clip `clip`."""
    return {"ok": bool(ok), **_clip_key(Path(clip))}


class ReviewError(ValueError):
    """Không duyệt được: cảnh không có, hoặc cảnh không dựng từ clip."""


def set_motion_review(project_id: str, scene_id: str, ok: bool) -> dict:
    """Nơi duy nhất ghi scene.metadata[REVIEW_KEY]: chủ dự án xem clip của cảnh rồi bấm "Đã xem, có cử động" (ok) hoặc
    bỏ duyệt. Gắn với file clip cảnh đang dùng khi dựng. Trả giá trị đã lưu."""
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không có dự án {project_id}")
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise LookupError(f"Không có cảnh {scene_id}")
    source = scene_render_input(scene, project_service.get_scene_media_paths(project_id, scene_id))
    if not source or Path(source).suffix.lower() not in VIDEO_EXTS:
        raise ReviewError("Cảnh này đang dựng từ ảnh, không có clip để duyệt")
    stamp = review_stamp(Path(source), ok)
    scene.metadata = dict(scene.metadata or {})
    scene.metadata[REVIEW_KEY] = stamp
    project_service.save_project(project)
    return stamp


def review_valid(scene: Scene, clip: Path) -> bool:
    """Chủ dự án đã duyệt "có cử động" cho ĐÚNG file clip này (đổi clip thì lần duyệt cũ hết hiệu lực)."""
    saved = (scene.metadata or {}).get(REVIEW_KEY)
    if not isinstance(saved, dict) or saved.get("ok") is not True:
        return False
    try:
        return all(saved.get(k) == v for k, v in _clip_key(Path(clip)).items())
    except OSError as e:   # clip mất hay không đọc được: lần duyệt không áp được, clip không được tính
        logger.warning(f"Không đọc được clip {Path(clip).name} để đối chiếu lần duyệt: {e}")
        return False


def _clip_seconds(path: Path) -> Optional[float]:
    try:
        return get_audio_duration(str(path))
    except MediaDurationError as e:
        logger.warning(f"Không đo được độ dài clip {path.name}: {e}")
        return None


def _score(path: Path) -> Optional[float]:
    try:
        return clip_motion.motion_score(path)
    except clip_motion.ClipMotionError as e:
        logger.warning(f"Không đo được cử động của {path.name}: {e}")
        return None


# --------------------------------------------------------------------------------------------------------- báo cáo
def share_report(entries: Iterable[tuple[Scene, float, Optional[str]]]) -> dict:
    """`entries`: (cảnh, số giây cảnh trong video, file đầu vào khi dựng: clip hay ảnh, None nếu chưa có)."""
    total = clips = counted = 0.0
    still: list[int] = []
    unmeasured: list[int] = []
    reviewed: list[int] = []
    short: list[int] = []
    for scene, seconds, source in entries:
        seconds = float(seconds or 0)
        total += seconds
        if not source or Path(source).suffix.lower() not in VIDEO_EXTS:
            continue
        path = Path(source)
        clips += seconds
        order = scene.order
        if review_valid(scene, path):
            ok = True
            reviewed.append(order)
        else:
            score = _score(path)
            ok = score is not None and clip_motion.has_real_motion(score)
            if score is None:
                unmeasured.append(order)
            elif not ok:
                still.append(order)
        if not ok:
            continue
        # Clip ngắn hơn lời kể: lúc dựng chỉ kéo chậm có giới hạn rồi giữ khung cuối đứng yên. Phần đứng yên không phải
        # video (gặp 13/11/2026: Muse trả clip 9 giây cho lời kể 18 giây, cách đếm cũ tính đủ 18 giây).
        moved = moving_seconds(_clip_seconds(path), seconds)
        counted += moved
        if seconds - moved > SHORT_CLIP_TOLERANCE_S:
            short.append(order)
    percent = round(100 * counted / total, 1) if total > 0 else 0.0
    return {"video_seconds": round(counted, 1), "clip_seconds": round(clips, 1), "total_seconds": round(total, 1),
            "percent": percent, "target_percent": round(CLIMAX_RATIO * 100), "gate_percent": round(GATE_MIN * 100),
            "enough": total > 0 and counted >= CLIMAX_RATIO * total - 1e-6,
            "gate_ok": total > 0 and counted >= GATE_MIN * total - 1e-6,
            "still_scenes": still, "unmeasured_scenes": unmeasured, "reviewed_scenes": reviewed,
            "short_scenes": short}


def project_entries(project: Project) -> list[tuple[Scene, float, Optional[str]]]:
    """Ước lượng trước khi dựng: mỗi cảnh dài bằng lời kể (video theo lời thoại dài hơn lời thì theo video)."""
    out = []
    for scene in project.scenes:
        media = project_service.get_scene_media_paths(project.id, scene.id)
        out.append((scene, render_seconds(scene) or scene.duration or 0, scene_render_input(scene, media)))
    return out


def has_all_durations(project: Project) -> bool:
    """Mọi cảnh đã có giọng đọc (biết thời lượng): mới tính được tỉ lệ trước khi dựng."""
    return bool(project.scenes) and all((s.duration or 0) > 0 for s in project.scenes)


def project_share(project: Project) -> dict:
    return share_report(project_entries(project))


# ----------------------------------------------------------------------------------------------------------- chốt
def _vi(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def _need(report: dict, ratio: float) -> float:
    return max(0.0, ratio * report["total_seconds"] - report["video_seconds"])


def gate_problem(report: dict) -> Optional[str]:
    """Câu báo vì sao chưa dựng được thành phẩm; None khi đạt GATE_MIN."""
    if report["gate_ok"]:
        return None
    parts = [f"Chưa dựng được video thành phẩm: video Muse có cử động chỉ chiếm {_vi(report['percent'])}% "
             f"({_vi(report['video_seconds'])} / {_vi(report['total_seconds'])} giây), cần ít nhất "
             f"{report['gate_percent']}% (mục tiêu {report['target_percent']}%). Thiếu khoảng "
             f"{_vi(_need(report, GATE_MIN))} giây để đạt {report['gate_percent']}%, "
             f"{_vi(_need(report, CLIMAX_RATIO))} giây để đạt {report['target_percent']}%."]
    waiting = report["still_scenes"] + report["unmeasured_scenes"]
    if waiting:
        parts.append(f"{len(waiting)} cảnh có clip chưa được tính vì gần như đứng hình hoặc không đo được: cảnh "
                     f"{', '.join(str(o) for o in waiting)}. Xem clip trên thẻ cảnh: có cử động thật thì bấm \"Đã xem, "
                     "có cử động\", không thì \"Làm lại cảnh này\".")
    parts.append("Làm thêm video: bấm \"Chọn cảnh cao trào\" rồi \"Tạo video\". Muốn xem thử thì dựng bản nháp "
                 "(không phải thành phẩm).")
    return " ".join(parts)


def require_gate(report: dict, draft: bool) -> None:
    """Chốt cuối của mọi đường dựng: dưới GATE_MIN và không phải bản nháp thì ném VideoShareTooLow."""
    if not draft and not report["gate_ok"]:
        raise VideoShareTooLow(report)


def report_lines(report: dict) -> list[str]:
    """Các dòng ghi vào nhật ký dựng sau khi dựng xong."""
    lines = [f"Video Muse có cử động: {_vi(report['video_seconds'])} / {_vi(report['total_seconds'])} giây = "
             f"{_vi(report['percent'])}% thời lượng (mục tiêu {report['target_percent']}%, tối thiểu "
             f"{report['gate_percent']}%). Tổng clip: {_vi(report['clip_seconds'])} giây."]
    if not report["enough"]:
        lines.append(f"⚠ DƯỚI {report['target_percent']}% VIDEO MUSE: thiếu khoảng {_vi(_need(report, CLIMAX_RATIO))} "
                     "giây. Bấm \"Chọn cảnh cao trào\" rồi \"Tạo video\" cho đủ, sau đó dựng lại.")
    if report["still_scenes"]:
        lines.append(f"⚠ {len(report['still_scenes'])} cảnh có clip gần như đứng hình (người hầu như không cử động "
                     f"hoặc chỉ lia/zoom), không được tính: cảnh {', '.join(str(o) for o in report['still_scenes'])}. "
                     "Xem lại; có cử động thật thì bấm \"Đã xem, có cử động\", không thì làm lại clip.")
    if report["unmeasured_scenes"]:
        lines.append(f"⚠ Không đo được cử động ở cảnh {', '.join(str(o) for o in report['unmeasured_scenes'])}, "
                     "không được tính cho tới khi duyệt.")
    if report.get("short_scenes"):
        lines.append(f"⚠ {len(report['short_scenes'])} cảnh có clip ngắn hơn lời kể (cuối cảnh là khung đứng yên, phần "
                     f"đó không tính là video): cảnh {', '.join(str(o) for o in report['short_scenes'])}.")
    if report["reviewed_scenes"]:
        lines.append(f"Clip đã được duyệt tay: cảnh {', '.join(str(o) for o in report['reviewed_scenes'])}.")
    return lines
