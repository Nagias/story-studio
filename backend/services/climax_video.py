"""Video cho cảnh cao trào của dự án vụ án, làm từ ảnh 9-grid của Muse.

Cách làm (chủ dự án chốt 27/10/2026, đo thật trên Muse cùng ngày):
1. Muse vẽ ảnh 9-grid (3x3) của cảnh, tham chiếu là ảnh hiện tại của cảnh: 9 khung liền mạch, cùng nhân vật và bối cảnh.
2. Cắt 9 ô; mỗi clip Muse 5 giây lấy một ô làm khung đầu, prompt khoá phong cách và chỉ cho cử động nhẹ (video dài hơn
   hoặc làm thẳng từ ảnh gốc thì nhân vật bị đổi mặt sau khoảng 1,5 giây).
3. Clip Muse tối dần (khung cuối tối hơn ô gốc 42–57%): chỉnh màu từng khung cho khớp ô gốc rồi máy kiểm clip.
4. Ghép các clip theo thứ tự thành clip chuyển động của cảnh. Lời kể dài hơn 9 clip thì vẽ thêm grid, grid sau lấy ô 9 của
   grid trước làm tham chiếu.

Module này không import routers/: hàm gọi Muse được truyền vào (`muse_call`). Không gọi LLM: prompt ghép bằng khuôn.

Từ 28/10/2026 (chủ dự án chốt sau lần chạy thật 27/10: mọi clip bị vẽ lại mặt): mỗi cảnh làm trong MỘT side chat Muse
của một tài khoản video — tài khoản đó vẽ cả ảnh grid; mỗi tin nhắn đính kèm ảnh (ảnh cảnh hoặc ô) và "bảng diễn viên"
(bảng nhân vật đủ góc đã duyệt, services/character_sheets.py). Grid phải được duyệt rồi mới làm clip.

Pha clip từ 28/10/2026 chiều (thay bước 2–4 ở trên): không gửi từng clip nữa mà giao MỘT việc nhiều bước cho Muse
(services/climax_brief.py; đo thật: 14/14 clip gửi lẻ bị vẽ lại đầu tròn, việc giao nhiều bước đạt suốt 12 giây).
Thiết kế: docs/superpowers/specs/2026-10-28-video-cao-trao-giao-viec-muse-design.md.
"""
import asyncio
import logging
import math
import os
import shutil
import unicodedata
import subprocess
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import numpy as np
from PIL import Image, UnidentifiedImageError

from config import MUSE_AGENT_WAIT_MIN, PROJECTS_DIR, STATIC_DIR
from models.schemas import Project, Scene
from security import is_within
from services import character_sheets as cs
from services import project_service
from services.climax_brief import AGENT_REPLY_MAX_CHARS, AGENT_VIDEO_MODE, NEW_SCENE_IMAGE_TAG, scene_brief, target_seconds
from services.tts_service import MediaDurationError, get_audio_duration

logger = logging.getLogger("story_studio.climax_video")

CLIMAX_RATIO = 0.5
CLIP_SECONDS = 5            # một ô lưới ứng với ~5 giây lời kể (số ô, số lưới); Muse tự quyết độ dài từng clip
PANELS_PER_GRID = 9
SCENE_IMAGE_MIN_SIMILARITY = 0.45   # ảnh Muse gửi kèm phải giống ảnh cảnh cũ chừng này mới thay (ảnh góc sau thì không)
SCENE_IMAGE_RATIO_TOL = 0.03
BACKUP_SUFFIX = ".truoc_sua_toc.jpg"
MIN_AGENT_VIDEO_SEC = 5.0

STYLE_LOCK_EN = (
    "Keep exactly the same art style as the attached image: the same drawing style, the same line work and outlines, "
    "the same color palette, and the same character faces exactly as drawn in the attached image (if a character has "
    "a round white face with dot eyes, keep that round white face with dot eyes, never turn it into a realistic or "
    "anime face). Same clothing, same setting, same lighting. Do not add any new people, no scene cuts, no text, "
    "no blood."
)
# Muse: nghỉ giữa hai lượt gọi để khỏi dồn tài khoản (chủ dự án 28/10: "cứ gọi từ từ thôi kẻo chết tài khoản")
MUSE_PACE_SEC = 15
# Trạng thái metadata["climax_video"]["status"]
GRID_REVIEW = "grid_review"
GRID_APPROVED = "grid_approved"
FEEDBACK_MAX = 500

ELIGIBLE_KINDS = ("image", "video")
OUT_W, OUT_H = 1920, 1080
CHECK_W, CHECK_H = 320, 180
MIN_GRID_W, MIN_GRID_H = 300, 168
PANEL_TRIM = 0.03
MEDIA_TIMEOUT_SEC = 600

MuseCall = Callable[[dict], Awaitable[dict]]


class ClimaxVideoError(RuntimeError):
    """Lỗi đã biết của một lần làm video cao trào; lời nhắn bằng tiếng Việt, hiện thẳng cho người dùng.
    `attempts`: số lần gọi Muse làm clip đã tốn trong phần việc báo lỗi."""

    def __init__(self, message: str, attempts: int = 0):
        super().__init__(message)
        self.message = message
        self.attempts = attempts


# ---------------------------------------------------------------------------------------------------------- chọn cảnh
def _visual_kind(scene: Scene) -> Optional[str]:
    return (scene.metadata or {}).get("visual_kind")


def is_eligible(scene: Scene) -> bool:
    """Cảnh làm được video cao trào: cảnh vụ án có hình vẽ (không phải bảng ghim, thẻ miễn trừ, cảnh truyện chữ)."""
    return _visual_kind(scene) in ELIGIBLE_KINDS


def scene_score(scene: Scene) -> int:
    """Điểm cao trào của cảnh (0 = không làm). Chỉ cảnh vụ án có visual_kind là image hoặc video."""
    if not is_eligible(scene):
        return 0
    meta = scene.metadata or {}
    score = 0
    if meta.get("visual_kind") == "video":
        score += 3
    beat = meta.get("narrative_beat")
    if beat == "climax":
        score += 2
    elif beat == "hook":
        score += 1
    energy = scene.bgm_energy or meta.get("bgm_energy")
    if energy == "dramatic_climax":
        score += 2
    elif energy == "tension_buildup":
        score += 1
    sfx = list(scene.sfx_cue or []) or list(meta.get("sfx_cue") or [])
    if "heartbeat" in sfx or "impact_hit" in sfx:
        score += 1
    return score


def climax_limit(project: Project) -> int:
    """Số cảnh tối đa được làm video: CLIMAX_RATIO số cảnh hợp lệ, làm tròn xuống."""
    eligible = sum(1 for s in project.scenes if is_eligible(s))
    return math.floor(CLIMAX_RATIO * eligible)


def pick_climax_scenes(project: Project) -> list[str]:
    """Id các cảnh nên làm video: điểm cao trước, bằng điểm thì cảnh đứng trước; trả theo thứ tự cảnh trong dự án."""
    scored = [(scene_score(s), i, s.id) for i, s in enumerate(project.scenes)]
    ranked = sorted((t for t in scored if t[0] > 0), key=lambda t: (-t[0], t[1]))
    chosen = {sid for _, _, sid in ranked[:climax_limit(project)]}
    return [s.id for s in project.scenes if s.id in chosen]


# --------------------------------------------------------------------------------------------------- số clip, số grid
def clip_count(seconds: float) -> int:
    """Số clip CLIP_SECONDS giây cần để phủ lời kể dài `seconds` giây."""
    if seconds is None or seconds <= 0:
        raise ValueError(f"Thời lượng cảnh phải lớn hơn 0 (nhận {seconds})")
    return max(1, math.ceil(seconds / CLIP_SECONDS))


def grid_plan(n_clips: int) -> list[list[int]]:
    """Mỗi phần tử: các ô (1–9) làm khung đầu clip trong một grid; trong grid có k clip thì ô rải đều từ 1 tới 9."""
    if n_clips < 1:
        raise ValueError(f"Số clip phải từ 1 trở lên (nhận {n_clips})")
    plan = []
    left = n_clips
    while left > 0:
        k = min(PANELS_PER_GRID, left)
        plan.append([1] if k == 1 else [1 + round(i * 8 / (k - 1)) for i in range(k)])
        left -= k
    return plan


# ------------------------------------------------------------------------------------------------------------ prompt
def _cast_lines(cast: Optional[list], positions: Optional[list[str]]) -> list[str]:
    """Mỗi nhân vật một dòng: tên, vị trí bảng của họ trong ảnh bảng diễn viên, thiết kế cố định."""
    lines = []
    for i, ch in enumerate(cast or []):
        if not positions:
            where = ""
        elif len(cast) == 1:
            where = " — character sheet = the SECOND attached image"
        else:
            where = f" — character sheet at the {positions[i]} of the SECOND attached image"
        lines.append(f"* {ch.name_vi}{where}:\n{ch.design_en.strip()}")
    return lines


def grid_prompt(scene: Scene, project: Project, first_grid: bool, cast: Optional[list] = None,
                positions: Optional[list[str]] = None, feedback: Optional[list[str]] = None) -> str:
    """Prompt ảnh 9-grid (tiếng Anh) của cảnh. Có `cast` (bảng nhân vật đã duyệt) thì khoá từng nhân vật theo bảng."""
    parts = []
    if cast:
        parts.append("tạo cho tôi 1 hình ảnh 2K tỉ lệ 16:9:")
    parts += [
        "A 3x3 storyboard grid: nine consecutive frames of one continuous shot of the same scene, read left to right, "
        "top to bottom, each frame a small moment later than the previous one with only gentle movement.",
        "The nine frames are separated by thin, perfectly straight white borders. No text, no numbers, no captions, "
        "no labels anywhere in the image.",
    ]
    which = "FIRST attached image" if cast else "attached image"
    if first_grid:
        parts.append(f"Panel 1 (top left) is exactly the {which}; the other eight panels continue from it.")
    else:
        parts.append(f"Continue from the {which} (the last frame of the previous segment): panel 1 picks up "
                     f"exactly where the {which} ends.")
    if scene.image_prompt:
        parts.append(f"Scene: {scene.image_prompt.strip()}")
    if (project.character_anchor or "").strip():
        parts.append(f"Characters: {project.character_anchor.strip()}")
    if cast:
        parts.append("CHARACTER LOCK — the second attached image is the approved character reference board. Every "
                     "character below must match their sheet exactly in all nine panels, from whatever angle they are "
                     "seen (head shape, face, hair, clothes, shoes, colours):")
        parts += _cast_lines(cast, positions)
    parts.append(STYLE_LOCK_EN)
    for fb in feedback or []:
        parts.append(f"Bản grid trước SAI: {fb.strip()} — sửa đúng chỗ này.")
    return "\n".join(parts)


# ------------------------------------------------------------------------------------------------------------ ảnh
def slice_grid(grid_path: Path, out_dir: Path, scene_id: str, grid_index: int) -> list[Path]:
    """Cắt ảnh 3x3 thành 9 ảnh 1920x1080 (bỏ viền ngăn: cắt 3% mỗi cạnh của từng ô)."""
    try:
        with Image.open(grid_path) as raw:
            img = raw.convert("RGB")
    except (OSError, UnidentifiedImageError) as e:
        raise ValueError(f"Không đọc được ảnh grid {Path(grid_path).name}: {e}") from e
    w, h = img.size
    if w < MIN_GRID_W or h < MIN_GRID_H:
        raise ValueError(f"Ảnh grid quá nhỏ ({w}x{h}, cần tối thiểu {MIN_GRID_W}x{MIN_GRID_H})")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cw, ch = w / 3, h / 3
    mx, my = cw * PANEL_TRIM, ch * PANEL_TRIM
    panels = []
    for idx in range(PANELS_PER_GRID):
        r, c = divmod(idx, 3)
        box = (round(c * cw + mx), round(r * ch + my), round((c + 1) * cw - mx), round((r + 1) * ch - my))
        cell = img.crop(box).resize((OUT_W, OUT_H), Image.Resampling.LANCZOS)
        dest = out_dir / f"{scene_id}_grid{grid_index}_o{idx + 1}.jpg"
        cell.save(dest, "JPEG", quality=95)
        panels.append(dest)
    return panels


def _load_rgb(path: Path, size: tuple[int, int]) -> np.ndarray:
    try:
        with Image.open(path) as raw:
            img = raw.convert("RGB").resize(size, Image.Resampling.BILINEAR)
    except (OSError, UnidentifiedImageError) as e:
        raise ValueError(f"Không đọc được ảnh {Path(path).name}: {e}") from e
    return np.asarray(img, dtype=np.float64)


def _luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _ssim_global(a: np.ndarray, b: np.ndarray) -> float:
    """SSIM một cửa sổ (cả ảnh) giữa hai ảnh xám 0–255."""
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    ma, mb = a.mean(), b.mean()
    va, vb = a.var(), b.var()
    cov = ((a - ma) * (b - mb)).mean()
    return float(((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma ** 2 + mb ** 2 + c1) * (va + vb + c2)))


# ------------------------------------------------------------------------------------------------------------ video
def _run_media(cmd: list[str], what: str) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=MEDIA_TIMEOUT_SEC)
    except FileNotFoundError as e:
        raise RuntimeError(f"Không tìm thấy {cmd[0]} trong PATH ({what})") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"{cmd[0]} chạy quá {MEDIA_TIMEOUT_SEC} giây ({what})") from e
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="ignore").strip()[-400:]
        raise RuntimeError(f"{cmd[0]} lỗi khi {what} (mã {proc.returncode}): {err}")
    return proc


def check_agent_video(path: Path, target: int) -> float:
    """Video cuối của Muse: có hình, dài 5 giây tới 2 × mục tiêu + 1. Trả số giây; sai thì ClimaxVideoError."""
    try:
        proc = _run_media(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=codec_type:format=duration", "-of", "default=nw=1", str(path)], "đo video của Muse")
    except RuntimeError as e:
        raise ClimaxVideoError(f"Video Muse gửi không đọc được: {e}") from e
    out = proc.stdout.decode("utf-8", errors="ignore")
    if "codec_type=video" not in out:
        raise ClimaxVideoError("Video Muse gửi không có hình")
    try:
        seconds = float(next(line.split("=", 1)[1] for line in out.splitlines() if line.startswith("duration=")))
    except (StopIteration, ValueError) as e:
        raise ClimaxVideoError("Không đo được độ dài video Muse gửi") from e
    if not MIN_AGENT_VIDEO_SEC <= seconds <= 2 * target + 1:
        raise ClimaxVideoError(f"Video Muse gửi dài {seconds:.1f} giây, cần {MIN_AGENT_VIDEO_SEC:.0f}–{2 * target + 1} giây")
    return seconds


def video_frame_size(path: Path) -> tuple[int, int]:
    """Cỡ khung (rộng, cao) của video; ảnh bìa video Muse gửi kèm có đúng cỡ này."""
    proc = _run_media(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                       "-of", "csv=p=0", str(path)], "đo cỡ khung video của Muse")
    w, h = proc.stdout.decode("utf-8", errors="ignore").strip().split(",")[:2]
    return int(w), int(h)


def muse_redrew_scene(report: str) -> bool:
    """Muse ghi "ANH_CANH_MOI: có" trong báo cáo (bản giao việc dặn) thì mới coi là có ảnh cảnh vẽ lại."""
    text = unicodedata.normalize("NFC", report or "").lower()
    return f"{NEW_SCENE_IMAGE_TAG.lower()}: có" in text


def choose_scene_image(old: Path, candidates: list[Path],
                       exclude_size: Optional[tuple[int, int]] = None) -> Optional[Path]:
    """Trong các ảnh Muse gửi kèm, ảnh cảnh đã sửa tóc = ảnh 16:9 giống ảnh cảnh cũ nhất (ảnh góc sau khác hẳn bố cục).
    Ảnh đúng cỡ khung video (`exclude_size`) là ảnh bìa của video: không bao giờ chọn (giám khảo 28/10/2026: ảnh bìa
    thật giống ảnh cảnh 0,68, vượt ngưỡng). Không ảnh nào đủ giống: None (giữ ảnh cũ)."""
    ref = _luma(_load_rgb(old, (CHECK_W, CHECK_H)))
    best, best_score = None, SCENE_IMAGE_MIN_SIMILARITY
    for cand in candidates:
        try:
            with Image.open(cand) as img:
                w, h = img.size
            if exclude_size is not None and (w, h) == tuple(exclude_size):
                continue
            if abs(w / h - 16 / 9) > SCENE_IMAGE_RATIO_TOL * 16 / 9:
                continue
            score = _ssim_global(ref, _luma(_load_rgb(cand, (CHECK_W, CHECK_H))))
        except (OSError, ValueError, UnidentifiedImageError, ZeroDivisionError):
            logger.warning(f"Bỏ ảnh Muse gửi kèm không đọc được: {cand}")
            continue
        if score >= best_score:
            best, best_score = cand, score
    return best


def replace_scene_image(project_id: str, scene_id: str, new: Path) -> Path:
    """Thay ảnh cảnh bằng ảnh Muse đã sửa (chủ dự án 28/10/2026: "giữ ảnh cũ làm bản dự phòng"). Bản dự phòng chỉ chép
    lần đầu (làm lại nhiều lần vẫn giữ ảnh gốc ban đầu). Ghi đè đúng file ảnh cảnh để mọi chỗ đang trỏ vẫn đúng."""
    _, scene = _load_scene(project_id, scene_id)
    current = _scene_image(scene, project_id)
    backup = current.with_name(f"{scene_id}{BACKUP_SUFFIX}")
    if not backup.exists():
        shutil.copy2(current, backup)
    tmp = current.with_name(f"{current.stem}.moi.tmp.jpg")
    with Image.open(new) as img:
        img.convert("RGB").save(tmp, "JPEG", quality=95)
    os.replace(tmp, current)
    return backup


# ------------------------------------------------------------------------------------------------- lưu trạng thái
def _update_scene(project_id: str, scene_id: str, change: Callable[[Scene], None]) -> None:
    """Đọc mới dự án, sửa đúng một cảnh, lưu ngay (giao diện có thể vừa lưu bản khác: không giữ bản đọc cũ lâu)."""
    project = project_service.get_project(project_id)
    if project is None:
        raise ClimaxVideoError(f"Dự án {project_id} không còn")
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise ClimaxVideoError(f"Cảnh {scene_id} không còn trong dự án")
    change(scene)
    project_service.save_project(project)


def _set_climax(project_id: str, scene_id: str, state: dict) -> None:
    def change(scene: Scene) -> None:
        scene.metadata = dict(scene.metadata or {})
        scene.metadata["climax_video"] = state
    _update_scene(project_id, scene_id, change)


def _mark_ready(project_id: str, scene_id: str, video: Path, state: dict) -> None:
    def change(scene: Scene) -> None:
        scene.motion_video_path = str(video)
        scene.video_url = f"/api/projects/{project_id}/media/videos/{video.name}"
        scene.media_view_mode = "video"
        scene.status_video = "ready"
        scene.metadata = dict(scene.metadata or {})
        scene.metadata["climax_video"] = state
    _update_scene(project_id, scene_id, change)


# ---------------------------------------------------------------------------------------------------- chạy một cảnh
def _studio_path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else PROJECTS_DIR.parent / p


def _scene_seconds(scene: Scene) -> float:
    if scene.duration and scene.duration > 0:
        return float(scene.duration)
    audio = scene.voice_audio_path or scene.audio_path
    if audio and _studio_path(audio).is_file():
        try:
            return float(get_audio_duration(str(_studio_path(audio))))
        except MediaDurationError as e:
            raise ClimaxVideoError(f"Không đo được thời lượng giọng đọc của cảnh: {e}") from e
    raise ClimaxVideoError("Cảnh chưa có giọng đọc nên chưa biết lời kể dài bao lâu: thu giọng cảnh này trước")


def _scene_image(scene: Scene, project_id: str) -> Path:
    candidates = []
    if scene.image_path:
        candidates.append(_studio_path(scene.image_path))
    candidates.append(project_service.get_scene_media_paths(project_id, scene.id)["image"])
    for cand in candidates:
        if cand.is_file() and is_within(cand, PROJECTS_DIR, STATIC_DIR):
            return cand.resolve()
    raise ClimaxVideoError("Cảnh chưa có ảnh (trong thư mục dự án) để làm tham chiếu cho ảnh 9-grid")


def _result_file(result: Any, kind: str) -> Path:
    path = result.get("output_path") if isinstance(result, dict) else None
    if not path or not Path(path).is_file():
        raise ClimaxVideoError(f"Muse báo xong {kind} nhưng không có file kết quả")
    return Path(path)


def _keep_copy(src: Path, dest: Path) -> Path:
    """Muse lưu kết quả ở chỗ của nó: chép vào thư mục làm việc của cảnh (giữ nguyên bản gốc)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest


def _load_scene(project_id: str, scene_id: str) -> tuple[Project, Scene]:
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không có dự án {project_id}")
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise LookupError(f"Dự án {project_id} không có cảnh {scene_id}")
    if not is_eligible(scene):
        raise ValueError(f"Cảnh {scene_id} không phải cảnh vụ án có hình vẽ (visual_kind image/video)")
    return project, scene


def _thread_dirty_error(err: BaseException) -> bool:
    """Lỗi làm side chat không dùng tiếp được: quá giờ (Muse có thể còn việc dở, kết quả muộn sẽ bị nhận nhầm), không
    mở được chat, hoặc tài khoản chủ chat không dùng được."""
    text = str(err)
    return isinstance(err, TimeoutError) or "THREAD_OPEN_FAILED" in text or "side chat" in text


def _muse_error_switch_account(err: BaseException) -> bool:
    """Muse trả lời lỗi (quá tải 503...) hoặc tài khoản hỏng: lần thử sau đổi sang tài khoản video khác, chat mới."""
    text = str(err)
    # NO_MEDIA: runner chờ hết giờ không có video (chạy thật 28/10/2026: tài khoản báo "dịch vụ tạo video không khả
    # dụng"); Muse có thể còn làm dở trong chat đó nên cũng bỏ chat.
    return (_thread_dirty_error(err) or any(code in text for code in (
        "MUSE_REPLIED_ERROR", "NO_MEDIA", "PROFILE_IN_USE", "SESSION_EXPIRED", "BROWSER_ERROR", "503", "quá tải")))


class SceneThread:
    """Side chat Muse của một cảnh: địa chỉ, tài khoản sở hữu, tài khoản nên tránh (vừa lỗi)."""

    def __init__(self, state: dict):
        self.url: Optional[str] = None if state.get("thread_dirty") else state.get("thread_url")
        self.account: Optional[str] = None if state.get("thread_dirty") else state.get("account_id")
        # Mỗi lần bấm chạy là một lần thử mới: tài khoản quá tải lúc trước có thể đã ổn (chạy thật 28/10/2026: đêm qua
        # lỗi hết thì sáng hôm sau không thử được tài khoản nào). Chỉ tránh tài khoản lỗi ngay trong lần chạy này.
        self.avoid: list[str] = []

    def apply(self, task: dict) -> dict:
        if self.url and self.account:
            task.update(thread_url=self.url, assigned_account=self.account, pin_account=True)
        elif self.avoid:
            task["avoid_accounts"] = list(self.avoid)
        return task

    def remember(self, result: Any) -> None:
        if isinstance(result, dict):
            self.url = result.get("thread_url") or self.url
            self.account = result.get("executed_by") or self.account
            self.avoid = []   # làm được rồi: thôi tránh (danh sách cũ không được chặn mãi các lần chạy sau)

    def drop(self, switch_account: bool) -> None:
        if switch_account and self.account and self.account not in self.avoid:
            self.avoid.append(self.account)
        self.url = self.account = None

    def state(self) -> dict:
        return {"thread_url": self.url, "account_id": self.account, "thread_dirty": False,
                "avoid_accounts": self.avoid[-4:]}


async def _pace() -> None:
    if MUSE_PACE_SEC > 0:
        await asyncio.sleep(MUSE_PACE_SEC)


async def _muse(muse_call: MuseCall, thread: SceneThread, task: dict) -> dict:
    """Gọi Muse trong side chat của cảnh; lỗi làm hỏng chat thì bỏ chat (lần sau chat mới, tránh tài khoản lỗi)."""
    try:
        result = await muse_call(thread.apply(task))
    except (RuntimeError, TimeoutError, OSError, ValueError) as e:
        if _muse_error_switch_account(e):
            thread.drop(switch_account=True)
        raise
    thread.remember(result)
    return result


def _prepare(scene: Scene, project_id: str) -> tuple[float, Path]:
    return _scene_seconds(scene), _scene_image(scene, project_id)


def _scene_state(scene: Scene) -> dict:
    value = (scene.metadata or {}).get("climax_video")
    return dict(value) if isinstance(value, dict) else {}


def _merge_climax(project_id: str, scene_id: str, changes: dict) -> dict:
    """Sửa vài khoá của metadata["climax_video"] (giữ khoá khác như chat, grid đã vẽ); trả trạng thái mới."""
    out: dict = {}

    def change(scene: Scene) -> None:
        state = _scene_state(scene)
        state.update(changes)
        for k in [k for k, v in state.items() if v is None]:
            state.pop(k)
        scene.metadata = dict(scene.metadata or {})
        scene.metadata["climax_video"] = state
        out.update(state)
    _update_scene(project_id, scene_id, change)
    return out


def _cast_for(project: Project, scene: Scene) -> tuple[list, list[str], Path]:
    """Nhân vật của cảnh (bảng đã duyệt), vị trí trong bảng diễn viên, ảnh bảng diễn viên. Thiếu thì ClimaxVideoError
    nêu rõ ai/cái gì (chưa gọi Muse)."""
    cast = cs.load_cast(project.id)
    people = cs.scene_characters(project, cast, scene)
    if not people:
        raise ClimaxVideoError("Chưa chọn nhân vật cho cảnh: bấm chip nhân vật trên thẻ cảnh hoặc mở Bảng nhân vật")
    missing = [p.name_vi for p in people if p.status != "approved"]
    if missing:
        raise ClimaxVideoError(f"Chưa có bảng nhân vật được duyệt: {', '.join(missing)} (mở Bảng nhân vật)")
    try:
        board = cs.cast_board(project.id, [p.entity_id for p in people])
    except cs.CastError as e:
        raise ClimaxVideoError(str(e)) from e
    return people, cs.board_positions(len(people)), board


async def run_scene_grid(project_id: str, scene_id: str, muse_call: MuseCall) -> dict:
    """Pha 1: Muse (tài khoản video, side chat của cảnh) vẽ mọi ảnh 9-grid của cảnh, đính kèm [ảnh cảnh hoặc ô 9 grid
    trước, bảng diễn viên]. Xong: trạng thái "grid_review" chờ duyệt. Lỗi: "failed" kèm lý do, giữ ảnh."""
    project, scene = await asyncio.to_thread(_load_scene, project_id, scene_id)
    work = project_service.get_scene_media_paths(project_id, scene_id)["video"].parent / "climax"
    old = _scene_state(scene)
    thread = SceneThread(old)
    try:
        seconds, image = await asyncio.to_thread(_prepare, scene, project_id)
        people, positions, board = await asyncio.to_thread(_cast_for, project, scene)
        plan = grid_plan(clip_count(seconds))
        grids: list[str] = []
        reference = image
        version = int(old.get("grid_version") or 0) + 1
        for g in range(1, len(plan) + 1):
            await asyncio.to_thread(_merge_climax, project_id, scene_id,
                                    {"status": "grid", "grid": g, "grids": len(plan), "error": None,
                                     "grid_approved": None, "grid_paths": None})
            out = work / f"{scene_id}_grid{g}_v{version}.jpg"
            task = {"mode": "text-to-image", "route_kind": "video", "raw_prompt": True,
                    "prompt": grid_prompt(scene, project, first_grid=(g == 1), cast=people, positions=positions,
                                          feedback=old.get("grid_feedback")),
                    "attachments": [str(reference), str(board)], "aspect_ratio": "16:9",
                    "parameters": {"aspect_ratio": "16:9"}, "output_path": str(out)}
            if g > 1:
                await _pace()
            try:
                result = await _muse(muse_call, thread, task)
                grid_file = await asyncio.to_thread(_keep_copy, _result_file(result, "ảnh 9-grid"), out)
                panels = await asyncio.to_thread(slice_grid, grid_file, work, scene_id, g)
            except ClimaxVideoError:
                raise
            except ValueError as e:
                raise ClimaxVideoError(f"Ảnh 9-grid {g} của Muse không dùng được: {e}") from e
            except (RuntimeError, TimeoutError, OSError) as e:
                raise ClimaxVideoError(f"Muse không vẽ được ảnh 9-grid {g}: {e}") from e
            grids.append(str(grid_file))
            reference = panels[PANELS_PER_GRID - 1]
        state = await asyncio.to_thread(_merge_climax, project_id, scene_id, {
            "status": GRID_REVIEW, "grids": len(plan), "grid": None, "grid_paths": grids, "grid_version": version,
            "error": None, **thread.state()})
        logger.info(f"Grid cao trào {project_id}/{scene_id}: {len(grids)} grid, chờ duyệt")
        return state
    except ClimaxVideoError as e:
        logger.warning(f"Grid cao trào {project_id}/{scene_id} thất bại: {e.message}")
        return await asyncio.to_thread(_merge_climax, project_id, scene_id,
                                       {"status": "failed", "error": e.message, "grid": None, **thread.state()})
    except Exception as e:
        logger.exception(f"Grid cao trào {project_id}/{scene_id}: lỗi ngoài dự kiến")
        await asyncio.to_thread(_merge_climax, project_id, scene_id,
                                {"status": "failed", "error": f"Lỗi ngoài dự kiến: {type(e).__name__}: {e}"})
        raise


def approve_grid(project_id: str, scene_id: str) -> dict:
    _, scene = _load_scene(project_id, scene_id)
    state = _scene_state(scene)
    if state.get("status") != GRID_REVIEW or not state.get("grid_paths"):
        raise ClimaxVideoError("Cảnh không có ảnh grid đang chờ duyệt")
    return _merge_climax(project_id, scene_id, {"status": GRID_APPROVED, "grid_approved": True, "error": None})


def reject_grid(project_id: str, scene_id: str, feedback: str) -> dict:
    fb = (feedback or "").strip()
    if not fb:
        raise ClimaxVideoError("Ghi rõ grid sai chỗ nào để Muse vẽ lại đúng chỗ đó")
    if len(fb) > FEEDBACK_MAX:
        raise ClimaxVideoError(f"Ghi chú tối đa {FEEDBACK_MAX} ký tự")
    _, scene = _load_scene(project_id, scene_id)
    state = _scene_state(scene)
    if not state.get("grid_paths") or state.get("status") not in (GRID_REVIEW, GRID_APPROVED, "failed"):
        raise ClimaxVideoError("Cảnh chưa có ảnh grid để vẽ lại (hoặc đang chạy)")
    return _merge_climax(project_id, scene_id, {"status": "selected", "grid_approved": None,
                                                "grid_feedback": list(state.get("grid_feedback") or []) + [fb]})


async def run_scene_clips(project_id: str, scene_id: str, muse_call: MuseCall) -> dict:
    """Pha 2 (sau khi duyệt grid): MỘT việc giao nhiều bước cho Muse trong side chat của cảnh (services/climax_brief.py):
    Muse tự chia đoạn, tự trích khung kiểm, tự làm lại, gửi một video cuối và ảnh cảnh đã sửa tóc (nếu có). App kiểm
    video, gắn làm clip của cảnh, thay ảnh cảnh (giữ bản cũ). Lỗi: giữ ảnh, bỏ chat (lần sau chat mới), không tự thử lại."""
    project, scene = await asyncio.to_thread(_load_scene, project_id, scene_id)
    old = _scene_state(scene)
    if not old.get("grid_approved") or not old.get("grid_paths"):
        raise ClimaxVideoError("Grid của cảnh chưa được duyệt")
    work = project_service.get_scene_media_paths(project_id, scene_id)["video"].parent / "climax"
    thread = SceneThread(old)
    called = False
    try:
        seconds, image = await asyncio.to_thread(_prepare, scene, project_id)
        people, _positions, board = await asyncio.to_thread(_cast_for, project, scene)
        grid_files = [Path(p) for p in old["grid_paths"]]
        if not all(is_within(p, work) for p in grid_files):
            raise ClimaxVideoError("Đường dẫn ảnh grid nằm ngoài thư mục làm việc của cảnh: vẽ lại grid")
        if len(grid_files) != len(grid_plan(clip_count(seconds))) or not all(p.is_file() for p in grid_files):
            raise ClimaxVideoError("Ảnh grid đã duyệt không khớp độ dài lời kể hiện tại: vẽ lại grid")
        target = target_seconds(seconds)
        token = f"XONG-{uuid.uuid4().hex[:8]}"
        version = int(old.get("clip_version") or 0) + 1
        out = work / f"{scene_id}_agent_v{version}.mp4"
        task = {"mode": AGENT_VIDEO_MODE, "route_kind": "video", "raw_prompt": True,
                "prompt": scene_brief(project, scene, people, len(grid_files), seconds, token),
                "attachments": [str(image), str(board), *(str(p) for p in grid_files)],
                "agent": {"done_token": token, "wait_sec": MUSE_AGENT_WAIT_MIN * 60, "target_seconds": target},
                "output_path": str(out)}
        await asyncio.to_thread(_merge_climax, project_id, scene_id,
                                {"status": "clips", "error": None, **thread.state()})
        called = True
        try:
            result = await _muse(muse_call, thread, task)
        except (RuntimeError, TimeoutError, OSError, ValueError) as e:
            raise ClimaxVideoError(f"Muse chưa làm xong video của cảnh: {e}") from e
        got = await asyncio.to_thread(_keep_copy, _result_file(result, "video"), out)
        length = await asyncio.to_thread(check_agent_video, got, target)
        await asyncio.to_thread(_merge_climax, project_id, scene_id, {"status": "checking"})
        final = project_service.get_scene_media_paths(project_id, scene_id)["motion_video"]
        await asyncio.to_thread(_keep_copy, got, final)
        extras = [Path(x) for x in (result.get("extra_images") or []) if isinstance(x, str)]
        chosen = None
        if extras and muse_redrew_scene(str(result.get("muse_reply") or "")):
            frame = await asyncio.to_thread(video_frame_size, got)
            chosen = await asyncio.to_thread(choose_scene_image, image, extras, frame)
        backup = await asyncio.to_thread(replace_scene_image, project_id, scene_id, chosen) if chosen else None
        state = {**old, **thread.state(), "status": "ready", "clips": 1, "grids": len(grid_files), "attempts": 1,
                 "clip_version": version, "video_seconds": round(length, 1),
                 "muse_report": str(result.get("muse_reply") or "")[-AGENT_REPLY_MAX_CHARS:],
                 "media_count": result.get("media_count"), "warnings": list(result.get("warnings") or []),
                 "scene_image_updated": chosen is not None, "backup_image": str(backup) if backup else None,
                 "grid": None, "done": None, "error": None}
        state = {k: v for k, v in state.items() if v is not None}
        await asyncio.to_thread(_mark_ready, project_id, scene_id, final, state)
        logger.info(f"Video cao trào {project_id}/{scene_id}: {length:.1f} s, thay ảnh cảnh: {chosen is not None}")
        return state
    except ClimaxVideoError as e:
        if called:
            thread.drop(switch_account=False)   # Muse có thể vẫn đang làm và gửi kết quả muộn vào chat này
        logger.warning(f"Clip cao trào {project_id}/{scene_id} thất bại: {e.message}")
        return await asyncio.to_thread(_merge_climax, project_id, scene_id, {
            "status": "failed", "error": e.message, "grid": None, "done": None, **thread.state()})
    except Exception as e:
        logger.exception(f"Clip cao trào {project_id}/{scene_id}: lỗi ngoài dự kiến")
        await asyncio.to_thread(_merge_climax, project_id, scene_id,
                                {"status": "failed", "error": f"Lỗi ngoài dự kiến: {type(e).__name__}: {e}"})
        raise


def redo_scene(project_id: str, scene_id: str) -> dict:
    """"Làm lại cảnh này": cảnh đã có kết quả (xong hoặc lỗi) với grid đã duyệt quay về chờ làm clip, chat mới."""
    _, scene = _load_scene(project_id, scene_id)
    state = _scene_state(scene)
    if not state.get("grid_approved") or state.get("status") not in ("ready", "failed"):
        raise ClimaxVideoError("Cảnh chưa có video hay lần làm lỗi với grid đã duyệt để làm lại")
    return _merge_climax(project_id, scene_id, {"status": GRID_APPROVED, "thread_dirty": True, "error": None})


async def run_scene_climax_video(project_id: str, scene_id: str, muse_call: MuseCall) -> dict:
    """Bước tiếp theo của một cảnh: grid đã duyệt thì làm clip, không thì vẽ grid (rồi dừng chờ duyệt).

    Id sai, dự án/cảnh không có: LookupError/ValueError (chưa gọi Muse). Muse lỗi hay clip không đạt: ghi
    {"status": "failed", "error": ...} vào cảnh, giữ ảnh, trả trạng thái đó. Lỗi ngoài dự kiến: ghi "failed" rồi ném tiếp.
    """
    _, scene = await asyncio.to_thread(_load_scene, project_id, scene_id)
    if _scene_state(scene).get("grid_approved"):
        return await run_scene_clips(project_id, scene_id, muse_call)
    return await run_scene_grid(project_id, scene_id, muse_call)
