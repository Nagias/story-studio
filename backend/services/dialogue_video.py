"""Video Muse cho một cảnh, dài theo lời thoại (chủ dự án, câu 18 và 19 mục 1.2).

Muse không cho chọn độ dài: mỗi lần làm ra một video khoảng 5–10 giây. Cách làm:
1. `plan_segments()`: lời kể vừa một video (≤ SEGMENT_MAX_SEC giây đọc) thì 1 đoạn; dài hơn thì chia thành các đoạn liền
   nhau theo ranh giới câu (câu quá dài thì theo dấu phẩy, rồi theo chữ), số đoạn ít nhất có thể, các đoạn dài gần bằng
   nhau. Mỗi đoạn = một video Muse = một lượt Muse; giao diện báo số này trước khi chạy.
2. `run_scene()`: mỗi đoạn một việc Muse (tài khoản video), tất cả trong MỘT side chat để Muse thấy video trước. Prompt
   (`segment_prompt()`) đưa đúng lời kể của đoạn đó: lời kể chuyển sang nơi khác hay việc khác thì Muse phải đổi cảnh, không
   chỉ đổi góc máy. Đoạn 1 mở đầu từ ảnh cảnh; đoạn sau đính kèm khung cuối video trước (để nối nếu vẫn cùng nơi) và ảnh
   cảnh (giữ nhân vật, nét vẽ). Cảnh thuộc bối cảnh đã duyệt thì thêm mô tả cố định (services/location_sheets.py).
3. `assemble()`: 1 video thì giữ nguyên, không cắt (dài hơn lời kể một chút cũng được). Nhiều video: video thứ k chiếm
   đúng khoảng thời gian đoạn k được đọc (dài hơn thì bỏ phần thừa, ngắn hơn thì giữ khung cuối), video cuối giữ trọn.
   Khi dựng, cảnh kéo dài thêm cho hết video cuối, tối đa MAX_TAIL_SEC giây sau lời kể (`render_seconds()`).

Trạng thái ở `scene.metadata["muse_dialogue_video"]` (chỉ server ghi; giao diện tự lưu không đè). Video từng đoạn ở
`projects/<id>/videos/dialogue/`, video ghép ở `videos/<scene_id>_muse.mp4` (chỗ quen của clip Muse của cảnh).
Đoạn lỗi thì dừng, giữ các đoạn đã xong; bấm lại thì làm tiếp từ đoạn lỗi. Không gọi LLM; không import routers/.
"""
import asyncio
import logging
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Awaitable, Callable, Optional

from config import PROJECTS_DIR, STATIC_DIR
from models.schemas import Project, Scene
from security import is_within
from services import location_sheets, project_service
from services.case_adaptation_checks import EN_WORDS_PER_MINUTE, VI_WORDS_PER_MINUTE
from services.tts_service import MediaDurationError, get_audio_duration

logger = logging.getLogger("story_studio.dialogue_video")

STATE_KEY = "muse_dialogue_video"
MUSE_MIN_SEC = 5.0          # video Muse ngắn nhất (chủ dự án: "minimum video muse là 5 giây thì cứ để 5s")
SEGMENT_MAX_SEC = 8.0       # một đoạn lời kể dài tối đa chừng này giây đọc: vừa một video Muse (5–10 giây)
MAX_SEGMENTS = 12
MAX_TAIL_SEC = 5.0          # video cuối dài hơn lời kể: cảnh kéo thêm tối đa chừng này giây, không cắt
REQUEST_DURATION = 10       # xin Muse video 10 giây: runner nhận video tới 20,5 giây (Muse làm 5–10 giây)
PACE_SEC = 15               # nghỉ giữa hai lượt Muse (như video cao trào: "gọi từ từ kẻo chết tài khoản")
MEDIA_TIMEOUT_SEC = 600
OUT_W, OUT_H, OUT_FPS = 1920, 1080, 25
pace_sleep = asyncio.sleep  # lấy lúc gọi; test thay bằng hàm không chờ thật

MuseCall = Callable[[dict], Awaitable[dict]]
_SENTENCE = re.compile(r"(?<=[.!?…。！？])[\"'”’»)\]]*\s+")
_CLAUSE = re.compile(r"(?<=[,;:—–])\s+")


class DialogueVideoError(RuntimeError):
    """Lỗi đã biết; lời nhắn tiếng Việt hiện thẳng cho người dùng."""


# --------------------------------------------------------------------------------------------- chia lời thoại
def _word_count(text: str) -> int:
    return len(text.split())


def _pieces(text: str, total_words: int, seconds: float) -> list[str]:
    """Cắt lời kể thành mẩu nhỏ nhất theo thứ tự ưu tiên: câu, vế câu (dấu phẩy...), nhóm chữ. Mỗi mẩu ≤ SEGMENT_MAX_SEC."""
    per_word = seconds / max(1, total_words)
    out: list[str] = []
    for sentence in [s for s in _SENTENCE.split(text.strip()) if s.strip()]:
        if _word_count(sentence) * per_word <= SEGMENT_MAX_SEC:
            out.append(sentence.strip())
            continue
        for clause in [c for c in _CLAUSE.split(sentence) if c.strip()]:
            words = clause.split()
            if len(words) * per_word <= SEGMENT_MAX_SEC:
                out.append(clause.strip())
                continue
            step = max(1, int(SEGMENT_MAX_SEC / per_word))
            out.extend(" ".join(words[i:i + step]) for i in range(0, len(words), step))
    return out


def _best_partition(weights: list[float], groups: int) -> list[int]:
    """Chia dãy liền nhau thành `groups` nhóm sao cho nhóm nặng nhất nhẹ nhất; trả chỉ số bắt đầu của từng nhóm."""
    n = len(weights)
    prefix = [0.0]
    for w in weights:
        prefix.append(prefix[-1] + w)
    inf = float("inf")
    cost = [[inf] * (n + 1) for _ in range(groups + 1)]
    cut = [[0] * (n + 1) for _ in range(groups + 1)]
    cost[0][0] = 0.0
    for g in range(1, groups + 1):
        for i in range(g, n + 1):
            for j in range(g - 1, i):
                c = max(cost[g - 1][j], prefix[i] - prefix[j])
                if c < cost[g][i]:
                    cost[g][i], cut[g][i] = c, j
    starts, i = [], n
    for g in range(groups, 0, -1):
        j = cut[g][i]
        starts.append(j)
        i = j
    return list(reversed(starts))


def plan_segments(text: str, seconds: float) -> list[dict]:
    """Các đoạn lời kể liền nhau, mỗi đoạn một video Muse: [{index, text, start, end, seconds}]. Thời gian chia theo
    số chữ của từng đoạn trên tổng thời lượng lời kể."""
    text = " ".join((text or "").split())
    if not text:
        raise DialogueVideoError("Cảnh chưa có lời kể để chia thành video")
    seconds = max(float(seconds or 0), 0.1)
    total_words = _word_count(text)
    if seconds <= SEGMENT_MAX_SEC:
        groups = [text]
    else:
        pieces = _pieces(text, total_words, seconds)
        weights = [_word_count(p) * seconds / total_words for p in pieces]
        groups = pieces
        for k in range(max(1, math.ceil(seconds / SEGMENT_MAX_SEC)), len(pieces) + 1):
            starts = _best_partition(weights, k)
            bounds = starts + [len(pieces)]
            if max(sum(weights[bounds[g]:bounds[g + 1]]) for g in range(k)) <= SEGMENT_MAX_SEC + 1e-6:
                groups = [" ".join(pieces[bounds[g]:bounds[g + 1]]) for g in range(k)]
                break
    if len(groups) > MAX_SEGMENTS:
        raise DialogueVideoError(f"Lời kể dài {seconds:.0f} giây cần {len(groups)} video Muse, quá {MAX_SEGMENTS}: "
                                 "tách cảnh này thành nhiều cảnh nhỏ hơn trước")
    out, t = [], 0.0
    for i, g in enumerate(groups, 1):
        dur = seconds * _word_count(g) / total_words
        out.append({"index": i, "text": g, "start": round(t, 3), "end": round(t + dur, 3), "seconds": round(dur, 3)})
        t += dur
    out[-1]["end"] = round(seconds, 3)
    return out


# ----------------------------------------------------------------------------------------------- thời lượng
def _studio_path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else PROJECTS_DIR.parent / p


def voice_file(scene: Scene) -> Optional[Path]:
    audio = scene.voice_audio_path or scene.audio_path
    if audio and _studio_path(audio).is_file():
        return _studio_path(audio)
    return None


def narration_seconds(project: Project, scene: Scene) -> tuple[float, bool]:
    """(số giây lời kể, có phải ước tính không). Có giọng đọc thì đo file; chưa có thì ước theo số chữ/phút."""
    audio = voice_file(scene)
    if audio is not None:
        try:
            return float(get_audio_duration(str(audio))), False
        except MediaDurationError as e:
            raise DialogueVideoError(f"Không đo được thời lượng giọng đọc của cảnh: {e}") from e
    if scene.duration and scene.duration > 0 and scene.voice_audio_path:
        return float(scene.duration), False
    lang = (project.metadata or {}).get("language") or ("en" if (project.voice or "").lower().startswith("en-") else "vi")
    rate = EN_WORDS_PER_MINUTE if lang == "en" else VI_WORDS_PER_MINUTE
    return max(1.0, _word_count(scene.text or "") * 60.0 / rate), True


def scene_plan(project: Project, scene: Scene) -> dict:
    seconds, estimated = narration_seconds(project, scene)
    segments = plan_segments(scene.text or "", seconds)
    return {"scene_id": scene.id, "narration_seconds": round(seconds, 2), "estimated": estimated,
            "video_count": len(segments), "segments": segments, "segment_max_seconds": SEGMENT_MAX_SEC}


# ------------------------------------------------------------------------------------------------ prompt Muse
def _style_rules(project: Project) -> list[str]:
    from services.image_service import FEMALE_HAIR_RULE_EN, ROUND_HEAD_EXPRESSION_RULE_EN, ROUND_HEAD_STYLES  # nạp muộn
    if project.style_preset not in ROUND_HEAD_STYLES:
        return []
    return ["- Nhân vật đầu tròn: đầu luôn là quả bóng tròn trắng to, mặt phẳng, chấm mắt. " + ROUND_HEAD_EXPRESSION_RULE_EN,
            "- " + FEMALE_HAIR_RULE_EN]


def segment_prompt(project: Project, scene: Scene, segments: list[dict], k: int, lock: Optional[dict],
                   has_plate: bool) -> str:
    """Prompt nguyên văn gửi Muse cho đoạn thứ k (đếm từ 1)."""
    seg = segments[k - 1]
    n = len(segments)
    target = max(int(MUSE_MIN_SEC), min(10, math.ceil(seg["seconds"] - 1e-9)))
    lines = [f"tạo cho tôi 1 video 16:9 dài khoảng {target} giây (ít nhất {int(MUSE_MIN_SEC)} giây) — video {k}/{n} "
             "của một cảnh trong video kể chuyện.",
             f"LỜI KỂ CỦA ĐÚNG ĐOẠN NÀY (video phải thể hiện đúng nội dung này): \"{seg['text']}\""]
    if n > 1:
        lines.append(f"Cả cảnh có {n} video nối nhau theo lời kể; toàn bộ lời kể để hiểu mạch: \"{' '.join((scene.text or '').split())}\"")
        if k > 1:
            lines.append(f"Đoạn ngay trước (đã làm ở video trước trong chat này): \"{segments[k - 2]['text']}\"")
        if k < n:
            lines.append(f"Đoạn ngay sau (video sau sẽ làm, đừng làm trước): \"{segments[k]['text']}\"")
    lines.append(f"Hình của cảnh (mô tả ảnh cảnh): {' '.join((scene.image_prompt or '').split()) or '(không có)'}")
    if lock:
        # Bối cảnh khoá là nơi chính của cảnh: chỉ áp khi đoạn này diễn ra ở đó (lời kể chuyển nơi thì luật đổi cảnh thắng)
        lines.append(f"Nơi chính của cảnh — chỉ áp dụng khi đoạn này diễn ra ở nơi đó: {lock['prompt_line']}")
    lines.append("Ảnh đính kèm, theo thứ tự:")
    if k == 1:
        lines.append("- Ảnh 1 — ẢNH CẢNH: dùng làm khung hình mở đầu của video.")
    else:
        lines.append("- Ảnh 1 — KHUNG CUỐI CỦA VIDEO TRƯỚC: nếu đoạn này vẫn ở cùng nơi và cùng việc thì bắt đầu từ khung "
                     "này, đổi góc máy, hành động tiếp diễn.")
        lines.append("- Ảnh 2 — ẢNH CẢNH: chuẩn về nhân vật (gương mặt, tóc, quần áo) và nét vẽ.")
    if has_plate:
        lines.append(f"- Ảnh {2 if k == 1 else 3} — ẢNH CHUẨN CỦA BỐI CẢNH: khi đoạn này diễn ra ở nơi đó, vẽ đúng nơi này.")
    lines += [
        "Luật:",
        "- Lời kể đoạn này chuyển sang NƠI KHÁC hoặc VIỆC KHÁC so với ảnh cảnh hay đoạn trước thì ĐỔI CẢNH theo lời kể "
        "(nơi chốn, hành động, đồ vật mới mà lời kể nói tới), không được chỉ đổi góc máy trên cùng một khung cảnh.",
        "- Giữ đúng phong cách vẽ và nhân vật như ảnh cảnh; không thêm người mà lời kể không nói tới.",
        *_style_rules(project),
        "- Không chữ, không phụ đề, không logo, không máu, không vết thương.",
        "Chỉ gửi lại đúng một video kết quả.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------- ffmpeg, ffprobe
def _run_media(cmd: list[str], what: str) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=MEDIA_TIMEOUT_SEC)
    except FileNotFoundError as e:
        raise DialogueVideoError(f"Không tìm thấy {cmd[0]} trong PATH ({what})") from e
    except subprocess.TimeoutExpired as e:
        raise DialogueVideoError(f"{cmd[0]} chạy quá {MEDIA_TIMEOUT_SEC} giây ({what})") from e
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="ignore").strip()[-400:]
        raise DialogueVideoError(f"{cmd[0]} lỗi khi {what} (mã {proc.returncode}): {err}")
    return proc


def video_seconds(path: Path) -> float:
    proc = _run_media(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                       "stream=codec_type:format=duration", "-of", "default=nw=1", str(path)], "đo video Muse")
    out = proc.stdout.decode("utf-8", errors="ignore")
    if "codec_type=video" not in out:
        raise DialogueVideoError(f"Video {path.name} không có hình")
    try:
        return float(next(line.split("=", 1)[1] for line in out.splitlines() if line.startswith("duration=")))
    except (StopIteration, ValueError) as e:
        raise DialogueVideoError(f"Không đo được độ dài video {path.name}") from e


def last_frame(video: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    _run_media(["ffmpeg", "-y", "-sseof", "-0.2", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)],
               "trích khung cuối video trước")
    if not out.is_file():
        raise DialogueVideoError("Không trích được khung cuối của video trước")
    return out


def clip_windows(segments: list[dict], clip_seconds: list[float]) -> list[float]:
    """Thời lượng mỗi video chiếm trong video ghép: video k (trừ video cuối) đúng khoảng đoạn k được đọc; video cuối
    giữ trọn (ngắn hơn phần lời kể còn lại thì kéo khung cuối cho đủ)."""
    out = [float(s["end"] - s["start"]) for s in segments[:-1]]
    last = segments[-1]
    out.append(max(float(last["end"] - last["start"]), float(clip_seconds[-1])))
    return out


def assemble(clips: list[Path], segments: list[dict], out: Path) -> float:
    """Ghép video các đoạn thành video của cảnh; trả số giây. Một video: chép nguyên, không cắt."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.stem}.ghep.tmp.mp4")
    if len(clips) == 1:
        shutil.copy2(clips[0], tmp)
    else:
        windows = clip_windows(segments, [video_seconds(c) for c in clips])
        cmd = ["ffmpeg", "-y"]
        for c in clips:
            cmd += ["-i", str(c)]
        parts = []
        for i, w in enumerate(windows):
            parts.append(f"[{i}:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
                         f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={OUT_FPS},setpts=PTS-STARTPTS,"
                         f"tpad=stop_mode=clone:stop_duration={w:.3f},trim=duration={w:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append("".join(f"[v{i}]" for i in range(len(windows))) + f"concat=n={len(windows)}:v=1:a=0[vout]")
        cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-an", "-c:v", "libx264", "-preset", "fast",
                "-pix_fmt", "yuv420p", str(tmp)]
        _run_media(cmd, "ghép video các đoạn")
    seconds = video_seconds(tmp)
    tmp.replace(out)
    return seconds


def render_seconds(scene: Scene) -> Optional[float]:
    """Thời lượng cảnh khi dựng nếu cảnh dùng video theo lời thoại và video dài hơn lời kể: lời kể + phần thừa của
    video (tối đa MAX_TAIL_SEC), để không cắt video. None: dựng như cũ (theo lời kể)."""
    state = (scene.metadata or {}).get(STATE_KEY)
    if not isinstance(state, dict) or state.get("status") != "ready" or scene.media_view_mode != "video":
        return None
    if not scene.motion_video_path or Path(scene.motion_video_path).resolve() != Path(state.get("video_path") or "").resolve():
        return None   # cảnh đã đổi sang clip khác (tải lên, video cao trào): dựng như cũ
    base = float(scene.duration or 0)
    vid = float(state.get("video_seconds") or 0)
    if base <= 0 or vid <= base:
        return None
    return min(vid, base + MAX_TAIL_SEC)


# ------------------------------------------------------------------------------------------------- trạng thái
def scene_state(scene: Scene) -> dict:
    value = (scene.metadata or {}).get(STATE_KEY)
    return dict(value) if isinstance(value, dict) else {}


def load_scene(project_id: str, scene_id: str) -> tuple[Project, Scene]:
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không có dự án {project_id}")
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise LookupError(f"Dự án {project_id} không có cảnh {scene_id}")
    return project, scene


def _update_scene(project_id: str, scene_id: str, change: Callable[[Scene], None]) -> None:
    """Đọc mới dự án, sửa đúng một cảnh, lưu ngay (giao diện có thể vừa lưu bản khác)."""
    project, scene = load_scene(project_id, scene_id)
    change(scene)
    project_service.save_project(project)


def _merge_state(project_id: str, scene_id: str, changes: dict) -> dict:
    holder: dict = {}

    def change(scene: Scene) -> None:
        state = scene_state(scene)
        state.update(changes)
        scene.metadata = dict(scene.metadata or {})
        scene.metadata[STATE_KEY] = state
        holder.update(state)
    _update_scene(project_id, scene_id, change)
    return holder


def _scene_image(project_id: str, scene: Scene) -> Path:
    for cand in ([_studio_path(scene.image_path)] if scene.image_path else []) + \
            [project_service.get_scene_media_paths(project_id, scene.id)["image"]]:
        if cand.is_file() and is_within(cand, PROJECTS_DIR, STATIC_DIR):
            return cand.resolve()
    raise DialogueVideoError("Cảnh chưa có ảnh để làm khung mở đầu video: tạo ảnh cảnh trước")


def _work_dir(project_id: str) -> Path:
    d = project_service.get_scene_media_paths(project_id, "x")["video"].parent / "dialogue"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _same_plan(old: list[dict], new: list[dict]) -> bool:
    return [s.get("text") for s in old] == [s.get("text") for s in new]


def prepare_run(project_id: str, scene_id: str) -> dict:
    """Kiểm trước khi chạy (lỗi thì DialogueVideoError, không tốn lượt Muse) và ghi kế hoạch vào trạng thái. Lời kể
    không đổi thì giữ các video đoạn đã làm (làm tiếp từ đoạn chưa xong)."""
    project, scene = load_scene(project_id, scene_id)
    if voice_file(scene) is None:
        raise DialogueVideoError("Cảnh chưa có giọng đọc nên chưa biết lời kể dài bao lâu: thu giọng cảnh này trước "
                                 "(số video Muse tính theo độ dài giọng đọc thật)")
    _scene_image(project_id, scene)
    plan = scene_plan(project, scene)
    old = scene_state(scene)
    done = old.get("clips") or []
    if not _same_plan(old.get("segments") or [], plan["segments"]):
        done = []
        old = {}
    state = {"status": "queued", "segments": plan["segments"], "video_count": plan["video_count"],
             "narration_seconds": plan["narration_seconds"], "clips": done[:plan["video_count"]],
             "thread_url": old.get("thread_url"), "account_id": old.get("account_id"), "error": None,
             "muse_calls": int(old.get("muse_calls") or 0)}
    _merge_state(project_id, scene_id, state)
    _update_scene(project_id, scene_id, lambda s: setattr(s, "status_video", "generating"))
    return state


def _dirty(err: BaseException) -> bool:
    text = str(err)
    return isinstance(err, TimeoutError) or any(c in text for c in (
        "THREAD_OPEN_FAILED", "side chat", "MUSE_REPLIED_ERROR", "NO_MEDIA", "PROFILE_IN_USE", "SESSION_EXPIRED",
        "BROWSER_ERROR"))


async def run_scene(project_id: str, scene_id: str, muse_call: MuseCall) -> dict:
    """Làm lần lượt video của các đoạn chưa xong (đã `prepare_run`), rồi ghép. Lỗi: trạng thái "failed" kèm lý do."""
    try:
        return await _run(project_id, scene_id, muse_call)
    except (DialogueVideoError, RuntimeError, TimeoutError, OSError, ValueError, LookupError) as e:
        msg = str(e) or type(e).__name__
        dirty = _dirty(e)
        logger.warning(f"Video theo lời thoại {project_id}/{scene_id} lỗi: {msg}")

        def failed(scene: Scene) -> None:
            state = scene_state(scene)
            state.update(status="failed", error=msg)
            if dirty:
                state.update(thread_url=None, account_id=None)   # chat có thể còn việc dở: lần sau chat mới
            scene.metadata = dict(scene.metadata or {})
            scene.metadata[STATE_KEY] = state
            scene.status_video = "error"
        try:
            await asyncio.to_thread(_update_scene, project_id, scene_id, failed)
        except LookupError as gone:   # cảnh vừa bị xoá: không còn chỗ ghi lỗi
            logger.warning(f"Không ghi được lỗi video theo lời thoại vào cảnh: {gone}")
        return {"status": "failed", "error": msg}


async def _run(project_id: str, scene_id: str, muse_call: MuseCall) -> dict:
    project, scene = await asyncio.to_thread(load_scene, project_id, scene_id)
    state = scene_state(scene)
    segments = state.get("segments") or []
    if not segments:
        raise DialogueVideoError("Chưa có kế hoạch chia đoạn: bấm lại nút làm video")
    clips: list[str] = [c for c in (state.get("clips") or []) if Path(c).is_file()]
    image = await asyncio.to_thread(_scene_image, project_id, scene)
    lock = await asyncio.to_thread(location_sheets.scene_lock, project_id, scene_id, scene.image_prompt or "")
    plate = lock.get("plate_path") if lock else None
    work = await asyncio.to_thread(_work_dir, project_id)
    thread_url, account = state.get("thread_url"), state.get("account_id")
    calls = int(state.get("muse_calls") or 0)
    for k in range(len(clips) + 1, len(segments) + 1):
        await asyncio.to_thread(_merge_state, project_id, scene_id, {"status": "running", "current": k})
        if k == 1:
            attachments = [str(image)]
        else:
            frame = await asyncio.to_thread(last_frame, Path(clips[-1]), work / f"{scene_id}_seg{k - 1}_cuoi.jpg")
            attachments = [str(frame), str(image)]
        if plate:
            attachments.append(plate)
        out = work / f"{scene_id}_seg{k}.mp4"
        task = {"mode": "image-to-video", "raw_prompt": True,
                "prompt": segment_prompt(project, scene, segments, k, lock, bool(plate)),
                "attachments": attachments, "input_image_url": attachments[0], "duration": REQUEST_DURATION,
                "parameters": {"duration": REQUEST_DURATION, "aspect_ratio": "16:9"}, "output_path": str(out)}
        if thread_url and account:
            task.update(thread_url=thread_url, assigned_account=account, pin_account=True)
        if calls and PACE_SEC > 0:
            await pace_sleep(PACE_SEC)
        calls += 1
        await asyncio.to_thread(_merge_state, project_id, scene_id, {"muse_calls": calls})
        result = await muse_call(task)
        got = Path(result.get("output_path") or "") if isinstance(result, dict) else Path()
        if not got.is_file():
            raise DialogueVideoError(f"Muse báo xong video {k}/{len(segments)} nhưng không có file")
        if got.resolve() != out.resolve():
            await asyncio.to_thread(shutil.copy2, got, out)
        await asyncio.to_thread(video_seconds, out)   # file hỏng thì báo ngay, không ghép
        thread_url = (result.get("thread_url") if isinstance(result, dict) else None) or thread_url
        account = (result.get("executed_by") if isinstance(result, dict) else None) or account
        clips.append(str(out))
        await asyncio.to_thread(_merge_state, project_id, scene_id,
                                {"clips": list(clips), "thread_url": thread_url, "account_id": account})
    final = project_service.get_scene_media_paths(project_id, scene_id)["motion_video"]
    seconds = await asyncio.to_thread(assemble, [Path(c) for c in clips], segments, final)

    def ready(s: Scene) -> None:
        state = scene_state(s)
        state.update(status="ready", error=None, current=None, video_path=str(final), video_seconds=round(seconds, 3))
        s.metadata = dict(s.metadata or {})
        s.metadata[STATE_KEY] = state
        s.motion_video_path = str(final)
        s.video_url = f"/api/projects/{project_id}/media/videos/{final.name}"
        s.media_view_mode = "video"
        s.status_video = "ready"
    await asyncio.to_thread(_update_scene, project_id, scene_id, ready)
    return {"status": "ready", "video_seconds": seconds, "videos": len(clips)}
