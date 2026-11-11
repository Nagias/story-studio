"""Báo cáo sau khi dựng: bao nhiêu phần thời lượng video là clip video (Muse) và clip nào gần như đứng hình.

Chủ dự án (CLAUDE.md mục 1.2 câu 24): "50% là video gen từ muse, tạo chuyển động tốt hơn ảnh". Trước 11/11/2026 app
không báo con số này lúc dựng; tỉ lệ do agent tự tính tay, hai lần sai: vụ Khang Cúc Hoa 32,9% mà không ai biết tới khi
chủ dự án xem; vụ xưởng sắt báo 65,5% nhưng clip chỉ lia/zoom ảnh. Nay mỗi lần dựng đều ghi tỉ lệ vào nhật ký dựng và
`project.metadata["video_share"]`, kèm danh sách cảnh có clip gần như đứng hình (services/clip_motion.py)."""
import logging
from pathlib import Path
from typing import Iterable, Optional

from services import clip_motion
from services.climax_video import CLIMAX_RATIO

logger = logging.getLogger("story_studio.video_share")

VIDEO_EXTS = (".mp4", ".mov", ".webm", ".avi", ".mkv")


def _score(path: Path) -> Optional[float]:
    try:
        return clip_motion.motion_score(path)
    except clip_motion.ClipMotionError as e:
        logger.warning(f"Không đo được cử động của {path.name}: {e}")
        return None


def share_report(entries: Iterable[tuple[int, float, str]]) -> dict:
    """`entries`: (số thứ tự cảnh, số giây cảnh trong video, file đầu vào khi dựng: clip hay ảnh)."""
    total = video = 0.0
    still: list[int] = []
    unmeasured: list[int] = []
    for order, seconds, source in entries:
        seconds = float(seconds or 0)
        total += seconds
        path = Path(source)
        if path.suffix.lower() not in VIDEO_EXTS:
            continue
        video += seconds
        score = _score(path)
        if score is None:
            unmeasured.append(order)
        elif not clip_motion.has_real_motion(score):
            still.append(order)
    percent = round(100 * video / total, 1) if total > 0 else 0.0
    return {"video_seconds": round(video, 1), "total_seconds": round(total, 1), "percent": percent,
            "target_percent": round(CLIMAX_RATIO * 100), "enough": total > 0 and video >= CLIMAX_RATIO * total,
            "still_scenes": still, "unmeasured_scenes": unmeasured}


def _vi(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def report_lines(report: dict) -> list[str]:
    lines = [f"Video Muse: {_vi(report['video_seconds'])} / {_vi(report['total_seconds'])} giây = "
             f"{_vi(report['percent'])}% thời lượng (cần từ {report['target_percent']}%)."]
    if not report["enough"]:
        need = report["target_percent"] / 100 * report["total_seconds"] - report["video_seconds"]
        lines.append(f"⚠ DƯỚI {report['target_percent']}% VIDEO MUSE: thiếu khoảng {_vi(max(0.0, need))} giây. Bấm "
                     "\"Chọn cảnh cao trào\" rồi \"Tạo video\" cho đủ, sau đó dựng lại.")
    if report["still_scenes"]:
        lines.append(f"⚠ {len(report['still_scenes'])} cảnh có clip gần như đứng hình (người hầu như không cử động "
                     f"hoặc chỉ lia/zoom): cảnh {', '.join(str(o) for o in report['still_scenes'])}. Xem lại; đúng "
                     "vậy thì làm lại clip của cảnh đó.")
    if report["unmeasured_scenes"]:
        lines.append(f"⚠ Không đo được cử động ở cảnh {', '.join(str(o) for o in report['unmeasured_scenes'])}.")
    return lines
