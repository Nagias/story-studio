#!/usr/bin/env python3
"""
Meta Muse Fleet Runner (Cơ chế B - Multi-Account Local Browser Cluster)
Điều khiển các profile Chromium đã đăng nhập Muse (mỗi profile = 1 tài khoản) cho Story Studio.

Luồng xử lý 1 task:
1. Poll task từ backend (http://127.0.0.1:8000/api/muse-bridge) cho 1 tài khoản cụ thể.
   Tài khoản ảnh chỉ nhận task ảnh, tài khoản video chỉ nhận task video (backend + runner cùng chặn).
2. Mở profile Chromium (Playwright persistent context), mở "New side chat" để tách biệt với chat cũ.
3. Đính kèm ảnh đầu vào (image-to-video) hoặc ảnh tham chiếu nhân vật (image), điền prompt, gửi.
4. Chỉ nhận media MỚI xuất hiện trong khung chat sau khi gửi (đánh dấu toàn bộ media có sẵn trước đó),
   loại avatar mascot, đợi media ổn định rồi tải về.
5. Kiểm tra file thật (PIL cho ảnh, ffprobe cho video) trước khi nộp về backend.

CLI:
  --setup ACCOUNT_ID   Mở Chromium có giao diện để đăng nhập tài khoản 1 lần
  --daemon             Chạy nền (chỉ 1 bản duy nhất nhờ file lock)
  --list               Liệt kê tài khoản
"""

import os
import sys

# Windows UTF-8 console output safety
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import asyncio
import base64
import hashlib
import io
import json
import logging
import logging.handlers
import shutil
import socket
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Third-party dependencies
try:
    from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
except ImportError:
    print("[ERROR] Playwright is not installed. Please run: pip install playwright && playwright install chromium")
    sys.exit(1)

import httpx
from PIL import Image

try:
    from runners.single_instance import acquire_runner_lock, release_runner_lock
    from runners import muse_agent_turn as agent_turn
except ImportError:  # chạy trực tiếp: python backend/runners/muse_fleet_runner.py
    from single_instance import acquire_runner_lock, release_runner_lock
    import muse_agent_turn as agent_turn

# -------------------------------------------------------------
# Path Resolution
# -------------------------------------------------------------
RUNNERS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = RUNNERS_DIR.parent
STORY_STUDIO_DIR = BACKEND_DIR.parent
CONFIG_DIR = BACKEND_DIR / "config"
ACCOUNTS_CONFIG_PATH = CONFIG_DIR / "muse_fleet_accounts.json"
DEFAULT_PROFILES_DIR = BACKEND_DIR / "chrome_profiles"
STATIC_DIR = BACKEND_DIR / "static"
OUTPUTS_DIR = STATIC_DIR / "muse_outputs"
PROJECTS_DIR = STORY_STUDIO_DIR / "projects"
WORK_DIR = RUNNERS_DIR / ".work"  # ảnh đính kèm tải tạm
# Thư mục profile Chrome của app khác được phép dùng (vd tài khoản Muse của videopic-workflow). Backend ghi danh sách này
# (từ config.EXTRA_CHROME_PROFILES_DIRS) vào muse_fleet_accounts.json, khoá "extra_profiles_dirs"; runner đọc từ đó.
EXTRA_PROFILES_DIRS: List[Path] = []


def set_extra_profiles_dirs(values: Any) -> None:
    global EXTRA_PROFILES_DIRS
    EXTRA_PROFILES_DIRS = [Path(v) for v in values if isinstance(v, str) and v.strip()] if isinstance(values, list) else []


def is_path_within(path: Path, *bases: Path) -> bool:
    """True nếu path (sau khi resolve) nằm trong một trong các thư mục gốc."""
    try:
        target = Path(path).resolve()
    except (OSError, ValueError):
        return False
    return any(target.is_relative_to(Path(b).resolve()) for b in bases)


def discard_temp_file(path: Path) -> None:
    """Xoá MỘT file tạm do runner tự tạo: ảnh đính kèm/ảnh phụ trong .work, video tải về không hợp lệ trong muse_outputs.
    Chỗ xoá duy nhất cho file tạm của runner (đường cấm 12): file nằm ngoài hai thư mục này thì không xoá."""
    if is_path_within(path, WORK_DIR, OUTPUTS_DIR) and Path(path).is_file():
        Path(path).unlink(missing_ok=True)


def _muse_reply_part(text_before: str, text_now: str, prompt: str = "") -> str:
    """Chữ Muse viết sau prompt: bỏ phần chat có từ trước VÀ chính prompt vừa gửi (khung chat hiện lại prompt; prompt có
    thể chứa "terror", "lỗi" do chủ dự án ghi chú — duyệt độc lập 28/10/2026)."""
    if not text_now or text_now == text_before:
        return ""
    new = text_now[len(text_before):] if text_now.startswith(text_before) else text_now
    flat = " ".join(new.split())
    norm = " ".join((prompt or "").split())
    # Khung chat có thể hiện prompt khác chút (markdown): thử đuôi prompt dài trước, ngắn dần
    key = next((norm[-n:] for n in (200, 80, 40) if norm and norm[-n:] in flat), "")
    if key:
        flat = flat[flat.rfind(key) + len(key):]
    elif not text_now.startswith(text_before):
        return ""   # không xác định được phần mới: thà bỏ qua còn hơn bắt nhầm lỗi cũ trong chat dài
    return flat.strip()


def muse_reply_error(text_before: str, text_now: str, prompt: str = "") -> Optional[str]:
    """Câu Muse trả lời (sau prompt) nếu có cụm báo lỗi rõ ràng, không thì None."""
    said = _muse_reply_part(text_before, text_now, prompt)
    low = said.lower()
    return said[-600:] if said and any(w in low for w in MUSE_ERROR_WORDS) else None


def muse_new_text(text_before: str, text_now: str) -> str:
    """Phần chữ Muse viết thêm sau khi gửi prompt (bỏ phần đã có trước đó)."""
    if not text_now or text_now == text_before:
        return ""
    new = text_now[len(text_before):] if text_now.startswith(text_before) else text_now[-1500:]
    return " ".join(new.split())


def task_attachments(task: Dict[str, Any]) -> List[str]:
    """Ảnh đính kèm theo thứ tự: `attachments` nếu có, không thì một ảnh như cũ (ảnh đầu vào của video, ảnh tham chiếu
    của ảnh)."""
    atts = task.get("attachments")
    if isinstance(atts, list) and atts:
        return [str(a) for a in atts]
    params = task.get("parameters") or {}
    if "video" in str(task.get("mode", "")).lower():
        keys = ("input_image_url", "input_image_path")
    else:
        keys = ("reference_image_path", "reference_image_url", "reference_image")
    for k in keys:
        v = task.get(k) or params.get(k)
        if v:
            return [str(v)]
    return []


def profile_in_use(profile_dir: Path) -> bool:
    """Chrome khác (vd app videopic) đang mở profile này: Windows giữ khoá độc quyền file "lockfile" khi Chrome chạy."""
    lock = Path(profile_dir) / "lockfile"
    if not lock.exists():
        return False
    try:
        with open(lock, "r+b"):
            return False
    except PermissionError:
        return True
    except OSError as e:
        logger.warning(f"Không kiểm được khoá profile {profile_dir}: {e}")
        return True


# Ensure directories exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------
# Logging Configuration (xoay vòng 5 MB x 3 file, bỏ log từng request httpx)
# -------------------------------------------------------------
LOG_FILE = BACKEND_DIR / "muse_fleet_runner.log"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [FleetRunner:%(process)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("muse_fleet_runner")

# -------------------------------------------------------------
# Tham số kiểm soát chất lượng kết quả
# -------------------------------------------------------------
MEDIA_WAIT_SEC = {"image": 150, "video": 300}  # thời gian chờ Muse trả kết quả sau khi gửi prompt
SCAN_INTERVAL_SEC = 3
CANDIDATE_STABLE_CHECKS = 2  # media phải xuất hiện ổn định qua 2 lần quét liên tiếp mới tải
MIN_IMAGE_SIDE = 512
MIN_VIDEO_SECONDS = 3.0
MIN_VIDEO_SIDE = 360
ACCOUNT_COOLDOWN_SEC = 60.0
# Muse trả lời bằng chữ có từ báo lỗi (vd "hệ thống quá tải (503)") mà sau chừng này giây vẫn không có media: thất bại
# ngay thay vì chờ hết MEDIA_WAIT_SEC (đo 27/10/2026: hai lần 503, runner cũ chờ trọn 7 phút)
MUSE_REPLY_GRACE_SEC = 45
# Tài khoản vừa hỏi việc mà không có: nhường lượt hỏi cho tài khoản cùng loại khác trong chừng này giây. Không có thì khe
# luôn giữ tài khoản "active": việc tránh tài khoản đó (avoid_accounts) hay ghim vào tài khoản khác không ai nhận (gặp
# 28/10/2026: việc clip tránh muse_acc_vid_02 nằm chờ 30 phút, 3 tài khoản videopic online không được hỏi lần nào).
EMPTY_POLL_BACKOFF_SEC = 30
# Cụm báo lỗi rõ ràng (không dùng chữ trơn "error", "lỗi": Muse hay nhắc lại yêu cầu "không lỗi", "no error"...)
MUSE_ERROR_WORDS = ("503", "quá tải", "overload", "không tạo được", "chưa tạo được", "không khả dụng", "unavailable",
                    "báo lỗi", "gặp lỗi", "bị lỗi hệ thống", "failed to generate", "couldn't generate",
                    "could not generate", "không thể tạo")
LOG_TEXT_JS = "() => ((document.querySelector('[role=log]') || document.body).innerText || '')"
SCROLL_LOG_JS = "() => document.querySelectorAll('[role=log]').forEach(l => { l.scrollTop = l.scrollHeight; })"
# Trường trạng thái do runner ghi xuống muse_fleet_accounts.json (các trường khác do backend quản lý)
RUNTIME_FIELDS = ("status", "cooldown_until", "last_used", "success_count", "fail_count", "last_error", "has_profile")
NOT_READY_STATUSES = ("busy", "offline", "needs_login", "reserved")


# Dấu vân tay (sha256 nội dung gốc) của mọi ảnh/video đã giao. Khi không mở được chat mới, đoạn chat cũ có thể vẽ lại
# video cũ dưới link mới (gặp 26/10/2026: task image-to-video nhận video lính La Mã của dự án khác sau 9 giây), nên
# loại theo nội dung chứ không chỉ theo link.
DELIVERED_HASHES_FILE = OUTPUTS_DIR / ".delivered_media_hashes.json"
_delivered_hashes: Optional[set] = None


def media_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def delivered_hashes() -> set:
    """Nạp một lần: sổ dấu vân tay đã lưu + mọi video .mp4 có sẵn trong muse_outputs (video lưu nguyên bản tải về)."""
    global _delivered_hashes
    if _delivered_hashes is None:
        hashes: set = set()
        try:
            hashes.update(json.loads(DELIVERED_HASHES_FILE.read_text(encoding="utf-8")))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            logger.warning(f"Không đọc được {DELIVERED_HASHES_FILE.name} ({e}); chỉ dựa vào video có sẵn trong muse_outputs")
        for p in OUTPUTS_DIR.glob("*.mp4"):
            try:
                hashes.add(media_digest(p.read_bytes()))
            except OSError as e:
                logger.warning(f"Không đọc được {p.name} để lấy dấu vân tay: {e}")
        _delivered_hashes = hashes
    return _delivered_hashes


def remember_delivered(digest: str) -> None:
    hashes = delivered_hashes()
    hashes.add(digest)
    tmp = DELIVERED_HASHES_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(sorted(hashes)), encoding="utf-8")
        tmp.replace(DELIVERED_HASHES_FILE)
    except OSError as e:
        logger.warning(f"Không ghi được sổ dấu vân tay media ({e}); lần chạy sau vẫn loại được video cũ theo file trong muse_outputs")


class TaskFailure(Exception):
    """Lỗi xử lý task có mã rõ ràng (gửi về backend dạng 'CODE: message')."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def __str__(self) -> str:
        return f"{self.code}: {self.args[0]}"


# -------------------------------------------------------------
# Prompt Engineering Formatter (Phân tách Image vs Video)
# -------------------------------------------------------------
def clamp_video_duration(value: Any) -> int:
    """Muse chỉ tạo clip 5s hoặc 10s."""
    try:
        d = float(value)
    except (TypeError, ValueError):
        d = 5.0
    return 10 if d > 7.5 else 5


class MusePromptFormatter:
    """Định dạng cấu trúc prompt chuyên biệt cho tạo Ảnh và tạo Video theo chuẩn Muse AI."""

    @staticmethod
    def attachment_role_tags(roles: List[str]) -> List[str]:
        """Câu dặn Muse vai trò từng ảnh đính kèm (thứ tự do services/scene_locks.py xếp)."""
        n = len(roles)
        tags = []
        for i, role in enumerate(roles):
            if n == 1:
                which = "Ảnh đính kèm"
            elif i == 0:
                which = "Ảnh đính kèm đầu tiên"
            elif i == n - 1:
                which = "Ảnh đính kèm cuối cùng"
            else:
                which = "Ảnh đính kèm thứ hai"
            if role == "characters":
                tags.append(f"{which} là BẢNG NHÂN VẬT (FIXED CHARACTERS bên dưới), vẽ mỗi người từ mọi góc: vẽ đúng "
                            "dáng đầu, gương mặt, kiểu tóc, trang phục, màu sắc của họ; không chép bố cục của bảng, "
                            "không vẽ bảng vào cảnh")
            elif role == "previous_scene":
                tags.append(f"{which} là khung hình của cảnh ngay trước trong cùng câu chuyện: giữ đúng nhân vật "
                            "(gương mặt, kiểu tóc, trang phục), cùng bối cảnh và cùng phong cách vẽ; vẽ khung hình TIẾP "
                            "THEO theo mô tả dưới đây (đổi góc máy, hành động tiếp diễn), không chép lại ảnh đính kèm")
            elif role == "location":
                tags.append(f"{which} là ẢNH CHUẨN CỦA BỐI CẢNH (FIXED LOCATION bên dưới): vẽ đúng nơi này (kiến "
                            "trúc, bố cục, đồ vật cố định, màu sắc, nguồn sáng), chỉ đổi góc máy theo mô tả; không "
                            "chép bố cục khung hình của ảnh đó")
            else:
                tags.append(f"Giữ đúng gương mặt, trang phục và đặc điểm nhân vật trong {which.lower()} (ảnh tham chiếu)")
        return tags

    @staticmethod
    def format_image_prompt(task: Dict[str, Any], has_reference: bool = False) -> str:
        """Định dạng prompt tạo ảnh gửi tới chat Muse AI."""
        raw_prompt = task.get("prompt", "").strip()
        params = task.get("parameters", {}) or {}
        aspect_ratio = params.get("aspect_ratio", "16:9")
        anchor = task.get("character_anchor") or params.get("character_anchor")
        style = params.get("style_preset", "")
        lighting = params.get("lighting", "")
        negative = task.get("negative_prompt", "")

        tags = []
        roles = params.get("attachment_roles")
        n_attach = len(task_attachments(task))
        if has_reference and isinstance(roles, list) and len(roles) == n_attach:
            # Khoá hình của cảnh (services/scene_locks.py): vai trò từng ảnh đính kèm theo đúng thứ tự
            tags += MusePromptFormatter.attachment_role_tags(roles)
            roles_done = True
        else:
            roles_done = False
        # Khoá bối cảnh: ảnh chuẩn của bối cảnh là ảnh đính kèm CUỐI; ảnh trước nó (nếu có) là ảnh tham chiếu như cũ
        location_ref = bool(has_reference and params.get("location_reference")) and not roles_done
        person_ref = has_reference and not roles_done and (not location_ref or n_attach > 1)
        first = "Ảnh đính kèm đầu tiên" if location_ref else "Ảnh đính kèm"
        if person_ref and params.get("reference_role") == "previous_scene":
            # vẽ nối tiếp (chủ dự án 26/10/2026: mỗi ảnh như một câu chuyện riêng, không liên quan nhau)
            tags.append(f"{first} là khung hình của cảnh ngay trước trong cùng câu chuyện: giữ đúng nhân vật (gương mặt, "
                        "kiểu tóc, trang phục), cùng bối cảnh và cùng phong cách vẽ; vẽ khung hình TIẾP THEO theo mô tả "
                        "dưới đây (đổi góc máy, hành động tiếp diễn), không chép lại ảnh đính kèm")
        elif person_ref:
            tags.append(f"Giữ đúng gương mặt, trang phục và đặc điểm nhân vật trong {first.lower()} (ảnh tham chiếu)")
        if location_ref:
            tags.append("Ảnh đính kèm cuối cùng là ẢNH CHUẨN CỦA BỐI CẢNH (FIXED LOCATION bên dưới): vẽ đúng nơi này "
                        "(kiến trúc, bố cục, đồ vật cố định, màu sắc, nguồn sáng), chỉ đổi góc máy theo mô tả; không "
                        "chép bố cục khung hình của ảnh đó")
        if anchor:
            tags.append(f"Character Anchor: {anchor}")
        if style:
            tags.append(f"Style: {style}")
        tags.append(f"Scene Details: {raw_prompt}")
        if lighting:
            tags.append(f"Atmosphere: {lighting}")
        tags.append("16:9 widescreen cinematic" if aspect_ratio == "16:9" else f"{aspect_ratio}")
        if negative:
            tags.append(f"Avoid: {negative}")

        return f"tạo cho tôi 1 hình ảnh 2K tỉ lệ {aspect_ratio}: " + ", ".join(tags)

    @staticmethod
    def format_video_prompt(task: Dict[str, Any], has_input_image: bool = False) -> str:
        """Định dạng prompt tạo video gửi tới chat Muse AI."""
        raw_prompt = task.get("prompt", "").strip() or task.get("action_prompt", "").strip()
        params = task.get("parameters", {}) or {}
        duration = clamp_video_duration(params.get("duration") or params.get("duration_sec") or task.get("duration") or 5)
        camera_motion = params.get("camera_motion") or params.get("camera") or ""
        action_cues = params.get("action_cues") or ""
        pacing = params.get("pacing") or "cinematic 24fps smooth pacing"

        tags = [f"[Duration: {duration}s]"]
        if has_input_image:
            tags.append("[Mode: Image-to-Video] Dùng đúng ảnh đính kèm làm khung hình gốc, giữ nguyên bố cục và nhân vật")
        else:
            tags.append("[Mode: Text-to-Video Motion Generation]")
        tags.append(f"Action: {raw_prompt}")
        if camera_motion:
            tags.append(f"Camera: {camera_motion}")
        if action_cues and action_cues != raw_prompt:
            tags.append(f"Dynamics: {action_cues}")
        if pacing:
            tags.append(f"Pacing: {pacing}")
        tags.append("16:9 landscape")

        return f"tạo cho tôi 1 video {duration}s: " + ", ".join(tags)

    @staticmethod
    def build_prompt(task: Dict[str, Any], has_attachment: bool = False) -> str:
        """Prompt gửi Muse: `raw_prompt` thì gửi nguyên văn (người gọi tự viết, kể cả câu mở đầu), không thì bọc khuôn."""
        if task.get("raw_prompt"):
            return str(task.get("prompt") or "").strip()
        if "video" in str(task.get("mode", "")).lower():
            return MusePromptFormatter.format_video_prompt(task, has_input_image=has_attachment)
        return MusePromptFormatter.format_image_prompt(task, has_reference=has_attachment)


# -------------------------------------------------------------
# Windows Singleton Lock Cleaner
# -------------------------------------------------------------
def clean_singleton_locks(profile_dir: Path) -> None:
    """
    Dọn các file SingletonLock / SingletonCookie / SingletonSocket còn sót lại sau khi Chromium bị tắt cứng.
    An toàn vì chỉ có 1 Fleet Runner chạy (file lock) và mỗi profile chỉ mở 1 lần (account.lock).
    """
    if not profile_dir.exists():
        profile_dir.mkdir(parents=True, exist_ok=True)
        return

    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile", "SingletonLock.lnk"):
        target = profile_dir / name
        try:
            if target.is_symlink() or target.is_file():
                target.unlink(missing_ok=True)
            elif target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
        except Exception as e:
            logger.warning(f"[{profile_dir.name}] Không thể gỡ lock {name}: {e}")


# -------------------------------------------------------------
# Chromium Configuration
# -------------------------------------------------------------
def get_installed_browser_channel() -> Optional[str]:
    """
    Tự động phát hiện Google Chrome hoặc Microsoft Edge đã cài sẵn trên Windows.
    Ưu tiên: Chrome -> Edge -> None (Playwright bundled Chromium).
    """
    local_app_data = os.environ.get("LocalAppData") or str(Path.home() / "AppData" / "Local")
    chrome_paths = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(local_app_data) / "Google/Chrome/Application/chrome.exe",
    ]
    if any(p.exists() for p in chrome_paths):
        return "chrome"
    edge_paths = [
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    if any(p.exists() for p in edge_paths):
        return "msedge"
    return None

CHROME_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-gpu-sandbox",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--window-size=1280,800",
    "--lang=vi-VN,vi,en-US,en",
]

CHROME_IGNORE_DEFAULT_ARGS = [
    "--enable-automation",
    "--enable-blink-features=IdleDetection",
]

REALISTIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = { runtime: {} };
"""

# -------------------------------------------------------------
# DOM helpers (chạy trong trang Muse)
# -------------------------------------------------------------
CHAT_INPUT_SELECTORS = [
    "textarea[aria-label='Message']",
    "textarea[placeholder='Message']",
    "textarea[placeholder*='Nhắn tin' i]",
    "textarea[placeholder*='message' i]",
    "div[contenteditable='true'][role='textbox']",
]
NEW_CHAT_SELECTORS = [
    "[data-testid='hatch-chat-compose']",
    "button[aria-label='New side chat']",
    "[aria-label='New side chat']",
]

# Đánh dấu toàn bộ media/link đang có trên trang trước khi gửi prompt -> chỉ nhận media mới sinh ra sau đó
MARK_EXISTING_MEDIA_JS = r"""() => {
  const srcs = [];
  document.querySelectorAll('img, video, a[href]').forEach(el => {
    el.setAttribute('data-ss-pre', '1');
    const s = el.currentSrc || el.src || el.href;
    if (s) srcs.push(s);
  });
  return srcs;
}"""

# Tìm media mới trong khung chat (ưu tiên vùng [role=log]), loại avatar/mascot (khung tròn, video vuông)
FIND_NEW_MEDIA_JS = r"""([kind, preSrcs, rejected]) => {
  const pre = new Set(preSrcs), bad = new Set(rejected);
  const logs = [...document.querySelectorAll('[role=log]')];
  const inChat = el => logs.length ? logs.some(l => l.contains(el)) : !!el.closest("[class*='message'], [class*='bubble']");
  const isAvatar = el => !!el.closest("[class*='rounded-full'], [class*='avatar'], [class*='landing']");
  const fresh = (el, src) => src && !el.hasAttribute('data-ss-pre') && !pre.has(src) && !bad.has(src);
  const out = [];
  if (kind === 'video') {
    for (const a of document.querySelectorAll('a[href]')) {
      const h = a.href || '';
      if (fresh(a, h) && /^https?:/i.test(h) && /\.mp4(\?|#|$)/i.test(h) && inChat(a)) out.push({ src: h, how: 'link' });
    }
    for (const v of document.querySelectorAll('video')) {
      const src = v.currentSrc || v.src;
      if (!fresh(v, src) || isAvatar(v) || !inChat(v)) continue;
      if (v.getBoundingClientRect().width < 200) continue;
      if (v.videoWidth && v.videoHeight && v.videoWidth <= v.videoHeight * 1.1) continue;
      if (v.duration && isFinite(v.duration) && v.duration < 3) continue;
      out.push({ src, how: 'video', w: v.videoWidth, h: v.videoHeight, dur: v.duration });
    }
  } else {
    for (const i of document.querySelectorAll('img')) {
      const src = i.currentSrc || i.src;
      if (!fresh(i, src) || isAvatar(i) || !inChat(i)) continue;
      if (!i.complete || i.naturalWidth < 512 || i.naturalHeight < 288) continue;
      out.push({ src, how: 'img', w: i.naturalWidth, h: i.naturalHeight });
    }
  }
  return out;
}"""

LOGIN_WALL_JS = r"""() => {
  const url = location.href.toLowerCase();
  if (/login|signin|sign-in|auth|accounts\./.test(url)) return true;
  return [...document.querySelectorAll('a, button')].some(e => /^(log ?in|sign ?in|đăng nhập|continue with)/i.test((e.innerText || '').trim()));
}"""

BLOB_TO_DATAURL_JS = r"""async (blobUrl) => {
  const res = await fetch(blobUrl);
  const blob = await res.blob();
  return await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.readAsDataURL(blob);
  });
}"""

# Đếm phần tử xem trước tệp đính kèm quanh ô nhập (để xác nhận đính kèm thành công)
COMPOSER_ATTACHMENT_COUNT_JS = r"""() => {
  const ta = document.querySelector("textarea[aria-label='Message'], textarea");
  if (!ta) return -1;
  let box = ta;
  for (let i = 0; i < 6 && box.parentElement; i++) box = box.parentElement;
  const imgs = box.querySelectorAll('img').length;
  const removers = [...box.querySelectorAll('button, [role=button]')].filter(b => /remove|xóa|xoá|delete/i.test(b.getAttribute('aria-label') || '')).length;
  return imgs + removers;
}"""

ALLOW_BUTTON_SELECTOR = "button:has-text('Cho phép'), button:has-text('Allow')"


# -------------------------------------------------------------
# Media validation
# -------------------------------------------------------------
def average_hash(img: Image.Image) -> int:
    small = img.convert("L").resize((8, 8))
    pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for p in pixels:
        bits = (bits << 1) | (1 if p >= avg else 0)
    return bits


def file_average_hash(path: Path) -> Optional[int]:
    try:
        with Image.open(path) as img:
            return average_hash(img)
    except Exception:
        return None


def validate_image_bytes(data: bytes, reject_hashes: List[int]) -> Tuple[bool, str]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            w, h = img.size
            ahash = average_hash(img)
    except Exception as e:
        return False, f"không phải ảnh hợp lệ ({e})"
    if min(w, h) < MIN_IMAGE_SIDE:
        return False, f"ảnh quá nhỏ {w}x{h}"
    for ref in reject_hashes:
        if bin(ahash ^ ref).count("1") <= 6:
            return False, "trùng ảnh tham chiếu đã đính kèm (không phải ảnh mới tạo)"
    ratio = w / h
    if abs(ratio - 16 / 9) > 0.2:
        logger.warning(f"Ảnh trả về {w}x{h} (tỉ lệ {ratio:.2f}) lệch 16:9")
    return True, f"{w}x{h}"


def parse_aspect(value: Any) -> Optional[float]:
    try:
        w, h = str(value).split(":")
        return float(w) / float(h)
    except (ValueError, ZeroDivisionError):
        return None


def to_jpeg_bytes(data: bytes, aspect: Optional[float] = None) -> bytes:
    """
    Chuẩn hóa ảnh kết quả: cắt giữa về đúng tỉ lệ yêu cầu (Muse đôi khi trả 3:2 / 1:1 dù prompt ghi 16:9)
    và lưu JPEG thật (Muse thường trả WEBP/PNG).
    """
    with Image.open(io.BytesIO(data)) as img:
        w, h = img.size
        crop_box = None
        if aspect and abs(w / h - aspect) > 0.02:
            if w / h > aspect:
                new_w = int(round(h * aspect))
                crop_box = ((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h)
            else:
                new_h = int(round(w / aspect))
                crop_box = (0, (h - new_h) // 2, w, (h - new_h) // 2 + new_h)
        if img.format == "JPEG" and crop_box is None:
            return data
        out = img.convert("RGB")
        if crop_box:
            out = out.crop(crop_box)
            logger.info(f"Cắt ảnh {w}x{h} về {out.size[0]}x{out.size[1]} cho đúng tỉ lệ yêu cầu")
        buf = io.BytesIO()
        out.save(buf, "JPEG", quality=95)
        return buf.getvalue()


def probe_video(path: Path) -> Optional[Dict[str, float]]:
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "json", str(path)],
            capture_output=True, timeout=30,
        )
        info = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
        stream = (info.get("streams") or [{}])[0]
        return {
            "width": float(stream.get("width") or 0),
            "height": float(stream.get("height") or 0),
            "duration": float((info.get("format") or {}).get("duration") or 0),
        }
    except Exception:
        return None


def max_video_seconds(requested: int) -> float:
    """Clip Muse thật dài 5s hoặc 10s; dài quá gấp đôi mức yêu cầu là video cũ có sẵn trong đoạn chat."""
    return requested * 2 + 0.5


def validate_video_file(path: Path, max_seconds: Optional[float] = None) -> Tuple[bool, str]:
    head = path.read_bytes()[:16]
    if not (head[4:8] == b"ftyp" or head.startswith(b"\x1a\x45\xdf\xa3")):
        return False, "không phải file video MP4/WebM"
    info = probe_video(path)
    if info is None:
        size = path.stat().st_size
        return (size >= 500_000, f"{size} bytes (không có ffprobe để kiểm tra kỹ)")
    w, h, dur = info["width"], info["height"], info["duration"]
    if dur < MIN_VIDEO_SECONDS:
        return False, f"video quá ngắn {dur:.1f}s"
    if max_seconds and dur > max_seconds:
        return False, f"video dài {dur:.1f}s, quá {max_seconds:.1f}s so với thời lượng yêu cầu (có thể là video cũ trong đoạn chat)"
    if min(w, h) < MIN_VIDEO_SIDE:
        return False, f"độ phân giải quá thấp {int(w)}x{int(h)}"
    if w <= h * 1.1:
        return False, f"video vuông/dọc {int(w)}x{int(h)} (avatar mascot, không phải kết quả 16:9)"
    return True, f"{int(w)}x{int(h)} {dur:.1f}s"


# -------------------------------------------------------------
# Account Management Class
# -------------------------------------------------------------
class FleetAccount:
    def __init__(self, raw: Dict[str, Any]):
        self.lock = asyncio.Lock()
        self.status: str = raw.get("status", "ready")
        if self.status in ("busy", "reserved"):
            self.status = "ready"  # trạng thái tạm của lần chạy trước bị tắt ngang
        self.cooldown_until: float = float(raw.get("cooldown_until", 0) or 0)
        self.last_used: float = float(raw.get("last_used", 0) or 0)
        self.success_count: int = int(raw.get("success_count", 0) or 0)
        self.fail_count: int = int(raw.get("fail_count", 0) or 0)
        self.last_error: Optional[str] = raw.get("last_error")
        self.last_empty_poll: float = 0.0   # chỉ trong RAM: lần cuối hỏi việc mà không có
        self.apply_config(raw)

    def apply_config(self, raw: Dict[str, Any]) -> None:
        """Nạp các trường do backend quản lý (loại tài khoản, profile, cờ active)."""
        self.account_id: str = raw["account_id"]
        self.label: str = raw.get("label", self.account_id)
        self.capabilities: List[str] = list(raw.get("capabilities", []) or [])
        t = str(raw.get("type", "")).lower()
        if t not in ("image", "video"):
            t = "video" if any(c in self.capabilities for c in ("image-to-video", "text-to-video")) else "image"
        self.type: str = t
        if not self.capabilities:
            self.capabilities = ["text-to-image", "image-upscale-2k"] if t == "image" else ["image-to-video", "text-to-video"]
        self.is_active_for_image: bool = bool(raw.get("is_active_for_image", False))
        self.is_active_for_video: bool = bool(raw.get("is_active_for_video", False))

        p_dir = raw.get("profile_dir") or f"chrome_profiles/{self.account_id}"
        p_path = Path(p_dir)
        profile = p_path.resolve() if p_path.is_absolute() else (BACKEND_DIR / p_path).resolve()
        # Profile Chrome chỉ được nằm trong backend/chrome_profiles hoặc thư mục profile ngoài được khai báo
        roots = [DEFAULT_PROFILES_DIR, *EXTRA_PROFILES_DIRS]
        if not is_path_within(profile, *roots) or any(profile == r.resolve() for r in roots):
            logger.warning(f"[{self.account_id}] profile_dir ngoài chrome_profiles bị bỏ qua: {p_dir}")
            profile = (DEFAULT_PROFILES_DIR / self.account_id).resolve()
        self.profile_dir: Path = profile
        # Profile của app khác: không dọn file khoá của nó, và không mở khi app đó đang dùng
        self.is_external: bool = not is_path_within(profile, DEFAULT_PROFILES_DIR)

    @property
    def is_active(self) -> bool:
        return self.is_active_for_video if self.type == "video" else self.is_active_for_image

    def is_logged_in(self) -> bool:
        """Profile đã có phiên đăng nhập Muse trên đĩa (cookie / IndexedDB)."""
        default_dir = self.profile_dir / "Default"
        if not default_dir.exists():
            return False
        idb = default_dir / "IndexedDB" / "https_muse.ai_0.indexeddb.leveldb"
        cookies = default_dir / "Network" / "Cookies"
        return idb.exists() or cookies.exists()

    def is_ready(self, require_login: bool = True) -> bool:
        """Tài khoản sẵn sàng nhận việc (không bận, không cần đăng nhập lại, hết cooldown)."""
        if self.status in NOT_READY_STATUSES:
            return False
        if require_login and not self.is_logged_in():
            return False
        if time.time() < self.cooldown_until:
            return False
        if self.status == "cooldown":
            self.status = "ready"
        return True

    def set_cooldown(self, seconds: float = ACCOUNT_COOLDOWN_SEC):
        self.cooldown_until = time.time() + seconds
        self.status = "cooldown"
        logger.info(f"[{self.account_id}] Cooldown {int(seconds)}s.")

    def runtime_state(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "cooldown_until": self.cooldown_until,
            "last_used": self.last_used,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "last_error": self.last_error,
            "has_profile": self.is_logged_in(),
        }


# -------------------------------------------------------------
# Core Fleet Runner Engine
# -------------------------------------------------------------
class MuseFleetRunner:
    def __init__(
        self,
        loopback_url: str = "http://127.0.0.1:8000/api/muse-bridge",
        muse_web_url: str = "https://muse.ai",
        concurrency_limit: int = 2,
        max_memory_mb: int = 1500,
        worker_id: str = "fleet-runner-local",
    ):
        self.loopback_url = loopback_url.rstrip("/")
        parts = urllib.parse.urlsplit(self.loopback_url)
        self.backend_origin = f"{parts.scheme}://{parts.netloc}"
        self.muse_web_url = muse_web_url
        self.concurrency_limit = max(1, min(concurrency_limit, 2))  # Giới hạn an toàn 1 - 2 slots
        self.max_memory_mb = max_memory_mb
        self.worker_id = worker_id

        self.accounts: Dict[str, FleetAccount] = {}
        self.concurrency_semaphore = asyncio.Semaphore(self.concurrency_limit)
        self.running = False
        self.playwright: Optional[Playwright] = None
        self._http: Optional[httpx.AsyncClient] = None
        self._last_conn_warning = 0.0

        self.load_accounts_config()

    # ---------------------------------------------------------
    # Account config (muse_fleet_accounts.json, chia sẻ với backend)
    # ---------------------------------------------------------
    def _read_config(self) -> Dict[str, Any]:
        try:
            with open(ACCOUNTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"accounts": data} if isinstance(data, list) else (data if isinstance(data, dict) else {})
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.error(f"Lỗi khi đọc file cấu hình tài khoản: {e}")
            return {}

    def _write_config(self, data: Dict[str, Any]) -> None:
        tmp = ACCOUNTS_CONFIG_PATH.with_suffix(".json.runner.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, ACCOUNTS_CONFIG_PATH)

    def load_accounts_config(self) -> None:
        """Đọc danh sách tài khoản từ muse_fleet_accounts.json (tạo mặc định nếu chưa có)."""
        if not ACCOUNTS_CONFIG_PATH.exists():
            logger.warning(f"Không tìm thấy {ACCOUNTS_CONFIG_PATH}, tạo danh sách mặc định...")
            self.create_default_config()

        data = self._read_config()
        set_extra_profiles_dirs(data.get("extra_profiles_dirs"))
        self.accounts.clear()
        for item in data.get("accounts", []):
            if isinstance(item, dict) and item.get("account_id") and item["account_id"] not in ("muse_acc_image", "muse_acc_video"):
                acc = FleetAccount(item)
                self.accounts[acc.account_id] = acc

        cfg_concurrency = data.get("concurrency_limit")
        if cfg_concurrency:
            self.concurrency_limit = max(1, min(int(cfg_concurrency), 2))
            self.concurrency_semaphore = asyncio.Semaphore(self.concurrency_limit)

        logger.info(f"Đã tải {len(self.accounts)} tài khoản Fleet Muse (Concurrency = {self.concurrency_limit}).")

    def refresh_accounts_from_disk(self) -> None:
        """Nạp lại cờ active / loại / tài khoản mới do backend thay đổi, giữ nguyên trạng thái chạy trong RAM."""
        data = self._read_config()
        set_extra_profiles_dirs(data.get("extra_profiles_dirs"))
        seen = set()
        for item in data.get("accounts", []):
            if not isinstance(item, dict) or not item.get("account_id"):
                continue
            aid = item["account_id"]
            if aid in ("muse_acc_image", "muse_acc_video"):
                continue
            seen.add(aid)
            if aid in self.accounts:
                self.accounts[aid].apply_config(item)
            else:
                self.accounts[aid] = FleetAccount(item)
                logger.info(f"Phát hiện tài khoản mới trong cấu hình: {aid}")
        for aid in list(self.accounts):
            if aid not in seen and not self.accounts[aid].lock.locked():
                del self.accounts[aid]

    def save_accounts_config(self) -> None:
        """Ghi trạng thái chạy (status, cooldown, thống kê) vào file, không đụng các trường do backend quản lý."""
        try:
            data = self._read_config()
            if not data.get("accounts"):
                return
            for item in data["accounts"]:
                acc = self.accounts.get(item.get("account_id"))
                if acc:
                    item.update(acc.runtime_state())
            data.setdefault("concurrency_limit", self.concurrency_limit)
            data.setdefault("max_memory_mb", self.max_memory_mb)
            data["loopback_url"] = self.loopback_url
            self._write_config(data)
        except Exception as e:
            logger.warning(f"Không thể lưu accounts config: {e}")

    def create_default_config(self) -> None:
        """Khởi tạo cấu trúc 10 tài khoản chuẩn nếu chưa có (5 ảnh + 5 video)."""
        accounts = []
        for kind, short, caps in (("image", "img", ["text-to-image", "image-upscale-2k"]),
                                  ("video", "vid", ["image-to-video", "text-to-video"])):
            for i in range(1, 6):
                aid = f"muse_acc_{short}_{i:02d}"
                accounts.append({
                    "account_id": aid,
                    "label": f"Muse {kind.capitalize()} Account {i:02d}",
                    "type": kind,
                    "capabilities": caps,
                    "profile_dir": f"chrome_profiles/{aid}",
                    "status": "ready",
                    "cooldown_until": 0,
                    "is_active_for_image": kind == "image" and i == 1,
                    "is_active_for_video": kind == "video" and i == 1,
                })
        self._write_config({
            "concurrency_limit": 2,
            "max_memory_mb": 1500,
            "loopback_url": self.loopback_url,
            "accounts": accounts,
        })

    def select_available_account(self, mode: str, require_login: bool = True) -> Optional[FleetAccount]:
        """Tài khoản rảnh đúng loại (ưu tiên active, rồi dùng lâu nhất chưa dùng) - không bao giờ chéo loại."""
        target_type = "video" if "video" in mode.lower() else "image"
        candidates = [a for a in self.accounts.values() if a.type == target_type and a.is_ready(require_login=require_login)]
        if not candidates:
            return None
        now = time.time()
        candidates.sort(key=lambda a: (now - a.last_empty_poll < EMPTY_POLL_BACKOFF_SEC, not a.is_active, a.last_used))
        return candidates[0]

    def _reserve_account(self, kinds: List[str]) -> Optional[FleetAccount]:
        """Giữ chỗ 1 tài khoản trước khi poll để 2 slot không cùng poll 1 tài khoản."""
        for kind in kinds:
            acc = self.select_available_account(kind)
            if acc:
                acc.status = "reserved"
                return acc
        return None

    @staticmethod
    def _release_account(acc: FleetAccount) -> None:
        if acc.status == "reserved":
            acc.status = "ready"

    # ---------------------------------------------------------
    # Loopback Communication with Story Studio Backend
    # ---------------------------------------------------------
    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            # trust_env=False: không đi qua proxy hệ thống (backend chỉ nhận request trực tiếp từ máy này)
            self._http = httpx.AsyncClient(timeout=30.0, trust_env=False)
        return self._http

    def _warn_backend_unreachable(self, err: Exception) -> None:
        now = time.time()
        if now - self._last_conn_warning > 60:
            self._last_conn_warning = now
            logger.warning(f"Không kết nối được backend {self.loopback_url} ({type(err).__name__}: {err}). Server Story Studio đã chạy chưa?")

    async def register_account_to_backend(self, acc: FleetAccount) -> bool:
        payload = {
            "worker_id": f"{self.worker_id}_{acc.account_id}",
            "account_id": acc.account_id,
            "hostname": socket.gethostname(),
            "os_info": f"Windows Chromium Fleet (Profile: {acc.account_id})",
            "hardware": {"status": acc.status, "concurrency_limit": self.concurrency_limit},
            "capabilities": acc.capabilities,
            "agent_version": "3.0.0-fleet",
            "timestamp": int(time.time()),
        }
        try:
            resp = await self.http.post(f"{self.loopback_url}/workers/register", json=payload, timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError as e:
            self._warn_backend_unreachable(e)
            return False

    async def send_account_heartbeat(self, acc: FleetAccount) -> bool:
        payload = {
            "worker_id": f"{self.worker_id}_{acc.account_id}",
            "account_id": acc.account_id,
            "hardware": {"status": acc.status, "concurrency_limit": self.concurrency_limit, "last_used": acc.last_used},
        }
        try:
            resp = await self.http.post(f"{self.loopback_url}/workers/heartbeat", json=payload, timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError as e:
            self._warn_backend_unreachable(e)
            return False

    async def poll_task_from_backend(self, acc: FleetAccount) -> Optional[Dict[str, Any]]:
        """Long-poll task mới cho đúng tài khoản này."""
        params = {"worker_id": f"{self.worker_id}_{acc.account_id}", "account_id": acc.account_id, "timeout": 5}
        try:
            resp = await self.http.get(f"{self.loopback_url}/tasks/poll", params=params, timeout=15.0)
        except httpx.HTTPError as e:
            self._warn_backend_unreachable(e)
            return None
        if resp.status_code != 200:
            logger.warning(f"[{acc.account_id}] Poll lỗi HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        body = resp.json()
        if body.get("blocked_until"):
            # Backend đang khóa tài khoản (hết quota / mất phiên) -> nghỉ đến hết hạn khóa
            acc.cooldown_until = max(acc.cooldown_until, float(body["blocked_until"]))
            acc.status = "cooldown"
            logger.info(f"[{acc.account_id}] Backend đang khóa tài khoản: {body.get('block_reason')}")
            return None
        return body.get("task")

    async def update_task_progress(self, task_id: str, percent: int, stage: str, message: str) -> None:
        payload = {"task_id": task_id, "progress_percent": percent, "stage": stage, "status_message": message}
        try:
            await self.http.post(f"{self.loopback_url}/tasks/{task_id}/progress", json=payload, timeout=5.0)
        except httpx.HTTPError:
            pass

    async def complete_task_to_backend(self, task_id: str, file_path: Path, meta: Dict[str, Any]) -> Tuple[bool, str]:
        """Upload file kết quả. Trả (thành công, chi tiết) - backend từ chối (422) nếu media sai loại."""
        if not file_path.exists() or file_path.stat().st_size == 0:
            return False, f"File kết quả không tồn tại hoặc rỗng: {file_path}"
        mime = "video/mp4" if file_path.suffix.lower() == ".mp4" else "image/jpeg"
        meta = dict(meta)
        extras = [Path(p) for p in meta.pop("_extra_files", []) or []]   # ảnh phụ của việc agent-video (đường dẫn máy này)
        try:
            files = [("file", (file_path.name, await asyncio.to_thread(file_path.read_bytes), mime))]
            for p in extras:
                if p.is_file():
                    files.append(("extras", (p.name, await asyncio.to_thread(p.read_bytes), "image/jpeg")))
            resp = await self.http.post(
                f"{self.loopback_url}/tasks/{task_id}/complete",
                files=files,
                data={"metadata": json.dumps(meta)},
                timeout=120.0,
            )
        except httpx.HTTPError as e:
            self._warn_backend_unreachable(e)
            return False, f"Không gửi được kết quả: {e}"
        finally:
            for p in extras:   # file tạm do runner tải về .work (như ảnh đính kèm), không phải dữ liệu người dùng
                discard_temp_file(p)
        if resp.status_code != 200:
            return False, f"Backend từ chối kết quả (HTTP {resp.status_code}): {resp.text[:200]}"
        return True, "ok"

    async def fail_task_to_backend(self, task_id: str, error_msg: str, acc_id: Optional[str] = None) -> None:
        payload = {
            "task_id": task_id,
            "error": error_msg,
            "worker_id": f"{self.worker_id}_{acc_id}" if acc_id else self.worker_id,
        }
        try:
            await self.http.post(f"{self.loopback_url}/tasks/{task_id}/fail", json=payload, timeout=10.0)
        except httpx.HTTPError as e:
            self._warn_backend_unreachable(e)

    async def resolve_task_image(self, task: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[Path]:
        """
        Lấy file ảnh cục bộ cho ảnh đầu vào / ảnh tham chiếu của task.
        Hỗ trợ: đường dẫn file trong projects/ hoặc static/, URL nội bộ backend (/api/..., /static/...), URL http(s).
        """
        params = task.get("parameters") or {}
        for key in keys:
            raw = task.get(key) or params.get(key)
            if not raw:
                continue
            val = str(raw)
            if val.startswith(("http://", "https://")) or val.startswith("/"):
                url = val if val.startswith("http") else f"{self.backend_origin}{val}"
                try:
                    resp = await self.http.get(url, timeout=30.0)
                    if resp.status_code != 200:
                        logger.warning(f"Không tải được ảnh {key} ({resp.status_code}): {url[:120]}")
                        continue
                    data = resp.content
                except httpx.HTTPError as e:
                    logger.warning(f"Không tải được ảnh {key}: {e}")
                    continue
                try:
                    with Image.open(io.BytesIO(data)) as img:
                        fmt = (img.format or "JPEG").lower()
                except Exception:
                    logger.warning(f"Dữ liệu {key} không phải ảnh: {url[:120]}")
                    continue
                WORK_DIR.mkdir(parents=True, exist_ok=True)
                ext = ".png" if fmt == "png" else ".webp" if fmt == "webp" else ".jpg"
                dest = WORK_DIR / f"{task.get('task_id', 'task')}_{key}{ext}"
                dest.write_bytes(data)
                return dest
            p = Path(val)
            cand = p if p.is_absolute() else STORY_STUDIO_DIR / p
            if cand.is_file() and is_path_within(cand, PROJECTS_DIR, STATIC_DIR):
                return cand.resolve()
            logger.warning(f"Ảnh {key} không tồn tại hoặc nằm ngoài thư mục cho phép: {val[:160]}")
        return None

    # ---------------------------------------------------------
    # Browser Automation
    # ---------------------------------------------------------
    async def create_browser_context(self, acc: FleetAccount, headless: bool = True) -> BrowserContext:
        """Khởi tạo Chromium Persistent Context cho profile của tài khoản."""
        if acc.is_external:
            if profile_in_use(acc.profile_dir):
                raise TaskFailure("PROFILE_IN_USE", f"Profile {acc.profile_dir} đang được app khác mở, để lượt sau")
        else:
            clean_singleton_locks(acc.profile_dir)

        if not self.playwright:
            self.playwright = await async_playwright().start()

        channel = get_installed_browser_channel()

        context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(acc.profile_dir),
            headless=headless,
            args=CHROME_STEALTH_ARGS,
            ignore_default_args=CHROME_IGNORE_DEFAULT_ARGS,
            viewport={"width": 1280, "height": 800},
            user_agent=REALISTIC_USER_AGENT,
            accept_downloads=True,
            channel=channel,
        )
        await context.add_init_script(STEALTH_INIT_SCRIPT)
        return context

    @staticmethod
    async def _find_chat_input(page: Page, timeout_ms: int):
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            for sel in CHAT_INPUT_SELECTORS:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    return el
            await page.wait_for_timeout(500)
        return None

    @staticmethod
    async def _open_new_chat(page: Page) -> bool:
        for sel in NEW_CHAT_SELECTORS:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await page.wait_for_timeout(2500)
                return True
        return False

    @staticmethod
    async def _attach_file(page: Page, file_path: Path, acc_id: str) -> None:
        """Đính kèm file vào ô chat. Raise TaskFailure nếu không đính kèm được."""
        before = await page.evaluate(COMPOSER_ATTACHMENT_COUNT_JS)
        file_input = await page.query_selector("input[type=file]")
        try:
            if file_input:
                await file_input.set_input_files(str(file_path))
            else:
                btn = await page.query_selector("[aria-label='Attach file']")
                if not btn:
                    raise TaskFailure("ATTACH_FAILED", "Không tìm thấy nút/ô đính kèm file trên Muse")
                async with page.expect_file_chooser(timeout=8000) as chooser_info:
                    await btn.click()
                chooser = await chooser_info.value
                await chooser.set_files(str(file_path))
        except TaskFailure:
            raise
        except Exception as e:
            raise TaskFailure("ATTACH_FAILED", f"Lỗi đính kèm ảnh: {e}")

        # Chờ khung xem trước tệp đính kèm xuất hiện (upload xong)
        deadline = time.time() + 20
        while time.time() < deadline:
            after = await page.evaluate(COMPOSER_ATTACHMENT_COUNT_JS)
            if before >= 0 and after > before:
                logger.info(f"[{acc_id}] Đã đính kèm ảnh {file_path.name}")
                await page.wait_for_timeout(2000)
                return
            await page.wait_for_timeout(1000)
        raise TaskFailure("ATTACH_FAILED", f"Muse không hiện ảnh đính kèm {file_path.name} sau 20s")

    @staticmethod
    async def _submit_prompt(page: Page, input_el, prompt: str) -> None:
        """Gửi prompt và xác nhận ô nhập đã trống (tin nhắn đã đi)."""
        async def input_value() -> str:
            try:
                return (await input_el.input_value()) if await input_el.evaluate("e => 'value' in e") else (await input_el.inner_text())
            except Exception:
                return ""

        await input_el.focus()
        await page.keyboard.press("Enter")
        deadline = time.time() + 20
        clicked_send = False
        while time.time() < deadline:
            await page.wait_for_timeout(1000)
            if not (await input_value()).strip():
                return
            if not clicked_send:
                btn = await page.query_selector("button[aria-label*='send' i], button[aria-label*='gửi' i]")
                if btn and await btn.is_visible() and await btn.is_enabled():
                    await btn.click()
                    clicked_send = True
        raise TaskFailure("PROMPT_NOT_SENT", "Không gửi được prompt (ô nhập vẫn còn nội dung sau 20s)")

    @staticmethod
    async def _click_allow_if_asked(page: Page, acc_id: str) -> None:
        try:
            scope = await page.query_selector("[role=log]")
            btn = await (scope or page).query_selector(ALLOW_BUTTON_SELECTOR)
            if btn and await btn.is_visible():
                logger.info(f"[{acc_id}] Muse yêu cầu phê duyệt, tự động bấm [Cho phép]")
                await btn.click()
                await page.wait_for_timeout(2000)
        except Exception:
            pass

    async def _download_media(self, page: Page, context: BrowserContext, src: str) -> Optional[bytes]:
        try:
            if src.startswith("blob:"):
                data_url = await page.evaluate(BLOB_TO_DATAURL_JS, src)
                if data_url and "," in data_url:
                    return base64.b64decode(data_url.split(",", 1)[1])
                return None
            if src.startswith("data:"):
                return base64.b64decode(src.split(",", 1)[1])
            resp = await context.request.get(src, timeout=90000)
            if resp.ok:
                return await resp.body()
            logger.warning(f"Tải media lỗi HTTP {resp.status}: {src[:100]}")
        except Exception as e:
            logger.warning(f"Lỗi tải media {src[:80]}: {e}")
        return None

    async def _finish_agent_turn(self, acc: FleetAccount, page: Page, context: BrowserContext, task: Dict[str, Any],
                                 text_before: str, prompt: str,
                                 pre_srcs: List[str]) -> Tuple[bool, Optional[Path], str]:
        """Việc `agent-video`: chờ Muse làm xong lượt (chữ kết thúc bằng done_token và đứng yên), rồi lấy video cuối và
        mọi ảnh mới Muse gửi sau prompt (ảnh nộp kèm dạng file phụ). Không bỏ ngang vì chữ "lỗi" trong báo cáo."""
        task_id = task["task_id"]
        agent = task.get("agent") or {}
        token = str(agent.get("done_token") or "")
        wait_sec = int(agent.get("wait_sec") or 2700)
        target = int(agent.get("target_seconds") or 10)
        if not token:
            raise TaskFailure("AGENT_BAD_TASK", "Việc agent-video thiếu done_token")
        logger.info(f"[{acc.account_id}] Đã gửi bản giao việc, chờ Muse làm xong lượt (tối đa {wait_sec}s)...")
        await self.update_task_progress(task_id, 60, "generating", "Muse đang làm nhiều bước (tạo, tự kiểm, làm lại)...")
        started = time.time()
        last_text, stable_since = "", time.time()
        while True:
            if page.is_closed():
                raise TaskFailure("PAGE_CLOSED", "Trang Muse đã bị đóng giữa chừng")
            if time.time() - started > wait_sec:
                raise TaskFailure("AGENT_TIMEOUT", f"Muse chưa xong sau {wait_sec}s (chưa thấy dòng kết thúc {token})")
            await self._click_allow_if_asked(page, acc.account_id)
            if "/thread/" in page.url and not page.url.endswith("/thread/new"):
                task["_result_meta"]["thread_url"] = page.url
            now_text = await page.evaluate(LOG_TEXT_JS)
            if now_text != last_text:
                last_text, stable_since = now_text, time.time()
            said = _muse_reply_part(text_before, now_text, prompt)
            if (agent_turn.turn_done(said, token) and time.time() - stable_since >= agent_turn.AGENT_STABLE_SEC
                    and not await page.evaluate(agent_turn.STREAMING_JS)):
                break
            await asyncio.sleep(SCAN_INTERVAL_SEC * 5)

        task["_result_meta"]["muse_reply"] = said[-agent_turn.REPLY_MAX_CHARS:]
        await page.evaluate(SCROLL_LOG_JS)
        await page.wait_for_timeout(3000)
        # Muse tạo lại địa chỉ blob của video liên tục (chạy thật 28/10/2026: địa chỉ vừa đọc đã bị huỷ, "Failed to
        # fetch"): chỉ lấy địa chỉ đang có trên trang (không dùng blob bắt từ mạng, đã cũ) và đọc lại trang trước mỗi lần thử
        data, final, videos = None, None, []
        for _ in range(agent_turn.DOWNLOAD_TRIES):
            videos = [c["src"] for c in await page.evaluate(FIND_NEW_MEDIA_JS, ["video", pre_srcs, []])]
            final = agent_turn.pick_final_video(videos)
            if final is not None:
                data = await self._download_media(page, context, final)
                if data:
                    break
            await page.wait_for_timeout(2000)
        if final is None:
            raise TaskFailure("NO_FINAL", "Muse ghi dòng kết thúc nhưng không có video nào sau prompt")
        if not data:
            raise TaskFailure("NO_FINAL", f"Không tải được video cuối của Muse sau {agent_turn.DOWNLOAD_TRIES} lần: {final[:100]}")
        images = [c["src"] for c in await page.evaluate(FIND_NEW_MEDIA_JS, ["image", pre_srcs, []])]
        dest_file = OUTPUTS_DIR / f"{task_id}.mp4"
        dest_file.write_bytes(data)
        ok, info = validate_video_file(dest_file, 2 * target + 1)
        if not ok:
            discard_temp_file(dest_file)
            raise TaskFailure("NO_FINAL", f"Video cuối của Muse không dùng được: {info}")
        remember_delivered(media_digest(data))

        extra_files: List[str] = []
        for i, src in enumerate(images[:agent_turn.AGENT_MAX_IMAGES]):
            img = await self._download_media(page, context, src)
            if not img:
                logger.warning(f"[{acc.account_id}] Bỏ ảnh phụ {i + 1} (không tải được): {src[:80]}")
                continue
            good, why = validate_image_bytes(img, [])
            if not good:
                logger.warning(f"[{acc.account_id}] Bỏ ảnh phụ {i + 1} ({why}): {src[:80]}")
                continue
            path = WORK_DIR / f"{task_id}_extra_{i + 1}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(to_jpeg_bytes(img, None))   # giữ nguyên khung: app tự kiểm tỉ lệ để bỏ ảnh không phải cảnh
            extra_files.append(str(path))
        task["_result_meta"].update(
            media_count={"video": len(videos), "image": len(images)},
            warnings=agent_turn.budget_warnings(len(videos), len(images), final_videos=len(videos)),
            _extra_files=extra_files)
        logger.info(f"[{acc.account_id}] Muse xong lượt sau {int(time.time() - started)}s: {info}, "
                    f"{len(videos)} video, {len(images)} ảnh -> {dest_file.name}")
        await self.update_task_progress(task_id, 95, "downloaded", f"Đã nhận video cuối {info}")
        return True, dest_file, "Thành công"

    async def execute_task_with_browser(self, acc: FleetAccount, task: Dict[str, Any]) -> Tuple[bool, Optional[Path], str]:
        """
        Thực thi 1 task trên trình duyệt của tài khoản. Trả (thành công, file kết quả, thông điệp lỗi).
        """
        task_id = task.get("task_id") or f"task_{int(time.time())}"
        mode = task.get("mode", "text-to-image")
        kind = "video" if "video" in mode.lower() else "image"

        # Bảo vệ định tuyến nghiêm ngặt: tài khoản ảnh không xử lý video và ngược lại (route_kind cho phép tài khoản
        # video vẽ ảnh grid trong side chat của cảnh)
        route = task.get("route_kind") if task.get("route_kind") in ("image", "video") else kind
        if acc.type != route:
            err = f"ROUTING: tài khoản {acc.type} '{acc.account_id}' không được xử lý task {kind} '{task_id}'"
            logger.error(err)
            return False, None, err

        # Chuẩn bị ảnh đính kèm (một hay nhiều ảnh, theo thứ tự). Ảnh đính kèm hiện lại trong tin nhắn đã gửi, cùng cỡ
        # với kết quả (gặp 27/10/2026): loại theo nội dung MỌI ảnh đính kèm.
        attach_paths: List[Path] = []
        reject_hashes: List[int] = []
        for i, raw in enumerate(task_attachments(task)):
            got = await self.resolve_task_image({"task_id": f"{task_id}_{i}", "src": raw}, ("src",))
            if not got:
                return False, None, f"INPUT_IMAGE_MISSING: task {task_id} không lấy được ảnh đính kèm {str(raw)[:120]}"
            attach_paths.append(got)
            h = file_average_hash(got)
            if h is not None:
                reject_hashes.append(h)
        if kind == "video" and mode != "text-to-video" and not attach_paths:
            return False, None, f"INPUT_IMAGE_MISSING: task image-to-video {task_id} không có ảnh đầu vào dùng được"
        attach_path: Optional[Path] = attach_paths[0] if attach_paths else None
        thread_url = task.get("thread_url")
        task["_result_meta"] = {}

        logger.info(f"[{acc.account_id}] Bắt đầu task {task_id} ({mode}, {len(attach_paths)} ảnh đính kèm"
                    f"{', chat ' + thread_url if thread_url else ''})")
        await asyncio.to_thread(delivered_hashes)   # lần đầu đọc mọi .mp4 trong muse_outputs: ở luồng phụ, không trễ heartbeat
        await self.update_task_progress(task_id, 10, "launching", f"Khởi động profile {acc.account_id}")

        context: Optional[BrowserContext] = None
        page: Optional[Page] = None
        text_before: Optional[str] = None
        prompt = ""
        try:
            context = await self.create_browser_context(acc, headless=True)
            page = context.pages[0] if context.pages else await context.new_page()

            await self.update_task_progress(task_id, 20, "navigating", "Truy cập Muse AI...")
            await page.goto(thread_url or self.muse_web_url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(6000 if thread_url else 3000)

            input_el = await self._find_chat_input(page, 20000)
            if not input_el:
                if thread_url:
                    raise TaskFailure("THREAD_OPEN_FAILED", f"Không mở được side chat {thread_url} (không thấy ô chat)")
                if await page.evaluate(LOGIN_WALL_JS):
                    raise TaskFailure("SESSION_EXPIRED", f"Tài khoản {acc.account_id} cần đăng nhập lại (chạy setup_muse_accounts.bat)")
                raise TaskFailure("INPUT_NOT_FOUND", "Không tìm thấy ô nhập chat của Muse (giao diện có thể đã đổi)")

            # Video: link CDN đôi khi chỉ thấy qua network. Ghi lại cả video tải TRƯỚC khi gửi prompt
            # (video cũ của đoạn chat) để không nhận nhầm chúng là kết quả mới.
            net_candidates: List[str] = []
            pre_net: set = set()
            submitted = {"v": False}
            if kind == "video":
                def on_response(response):
                    try:
                        ctype = (response.headers.get("content-type") or "").lower()
                        url = response.url
                        if "video/mp4" not in ctype:
                            return
                        if not submitted["v"]:
                            pre_net.add(url)
                        elif url not in pre_net and url not in net_candidates:
                            net_candidates.append(url)
                    except Exception:
                        pass
                page.on("response", on_response)

            # Mở đoạn chat mới để không lẫn với kết quả cũ (task có thread_url: dùng lại đúng chat đó)
            if thread_url:
                await page.evaluate(SCROLL_LOG_JS)
                await page.wait_for_timeout(3000)
            elif await self._open_new_chat(page):
                input_el = await self._find_chat_input(page, 10000) or input_el
            else:
                logger.warning(f"[{acc.account_id}] Không thấy nút New side chat, dùng đoạn chat hiện tại")
                # Cuộn hết đoạn chat cũ và chờ media cũ tải xong, để bước đánh dấu bên dưới thấy hết chúng
                await page.evaluate("() => document.querySelectorAll('[role=log]').forEach(l => { l.scrollTop = l.scrollHeight; })")
                await page.wait_for_timeout(3000)

            if attach_paths:
                await self.update_task_progress(task_id, 35, "attaching", f"Đính kèm {len(attach_paths)} ảnh...")
                for ap in attach_paths:
                    await self._attach_file(page, ap, acc.account_id)

            # Đánh dấu media đang có trên trang (kể cả ảnh vừa đính kèm, avatar mascot) để loại trừ
            pre_srcs = await page.evaluate(MARK_EXISTING_MEDIA_JS)
            requested_sec = clamp_video_duration((task.get("parameters") or {}).get("duration")
                                                 or (task.get("parameters") or {}).get("duration_sec")
                                                 or task.get("duration") or 5)

            prompt = MusePromptFormatter.build_prompt(task, has_attachment=bool(attach_path))
            logger.info(f"[{acc.account_id}] Prompt: {prompt[:140]}...")
            text_before = await page.evaluate(LOG_TEXT_JS)

            await self.update_task_progress(task_id, 45, "prompting", "Gửi prompt lên Muse...")
            await input_el.fill(prompt)
            await page.wait_for_timeout(500)
            pre_net.update(pre_srcs)
            submitted["v"] = True
            await self._submit_prompt(page, input_el, prompt)
            if mode == agent_turn.AGENT_VIDEO_MODE:
                return await self._finish_agent_turn(acc, page, context, task, text_before, prompt, pre_srcs)
            logger.info(f"[{acc.account_id}] Đã gửi prompt, chờ Muse tạo {kind} (tối đa {MEDIA_WAIT_SEC[kind]}s)...")
            error_since: Optional[float] = None
            await self.update_task_progress(task_id, 60, "generating", f"Muse đang tạo {kind}...")

            ext =".mp4" if kind == "video" else ".jpg"
            dest_file = OUTPUTS_DIR / f"{task_id}{ext}"
            rejected: set = set()
            seen_count: Dict[str, int] = {}
            started = time.time()
            deadline = started + MEDIA_WAIT_SEC[kind]

            while time.time() < deadline:
                if page.is_closed():
                    raise TaskFailure("PAGE_CLOSED", "Trang Muse đã bị đóng giữa chừng")
                await self._click_allow_if_asked(page, acc.account_id)
                if "/thread/" in page.url and not page.url.endswith("/thread/new"):
                    task["_result_meta"]["thread_url"] = page.url
                reply_err = muse_reply_error(text_before, await page.evaluate(LOG_TEXT_JS), prompt)
                if reply_err:
                    error_since = error_since or time.time()
                    if time.time() - error_since >= MUSE_REPLY_GRACE_SEC:
                        task["_result_meta"]["muse_reply"] = reply_err
                        raise TaskFailure("MUSE_REPLIED_ERROR", reply_err[:400])
                else:
                    error_since = None

                candidates = await page.evaluate(FIND_NEW_MEDIA_JS, [kind, pre_srcs, list(rejected)])
                srcs = [c["src"] for c in candidates] + [u for u in net_candidates if u not in rejected]
                for src in dict.fromkeys(srcs):
                    seen_count[src] = seen_count.get(src, 0) + 1
                    if seen_count[src] < CANDIDATE_STABLE_CHECKS:
                        continue
                    data = await self._download_media(page, context, src)
                    if not data:
                        rejected.add(src)
                        continue
                    digest = media_digest(data)
                    if digest in delivered_hashes():
                        logger.warning(f"[{acc.account_id}] Bỏ qua media cũ (trùng nội dung một kết quả đã giao trước đây): {src[:80]}")
                        rejected.add(src)
                        continue
                    if kind == "image":
                        ok, info = validate_image_bytes(data, reject_hashes)
                        if ok:
                            aspect = parse_aspect((task.get("parameters") or {}).get("aspect_ratio") or task.get("aspect_ratio") or "16:9")
                            dest_file.write_bytes(to_jpeg_bytes(data, aspect))
                    else:
                        dest_file.write_bytes(data)
                        ok, info = validate_video_file(dest_file, max_video_seconds(requested_sec))
                        if not ok:
                            discard_temp_file(dest_file)
                    if ok:
                        remember_delivered(digest)
                        await page.wait_for_timeout(8000)   # chờ Muse viết xong lời kèm kết quả (tự kiểm, ghi chú)
                        # Chat mới có địa chỉ thật (/thread/<uuid>) sau tin nhắn đầu, có khi chậm hơn kết quả: đọc lại ở đây
                        # (gặp 28/10/2026: cảnh 41 nhận ảnh grid ngay, địa chỉ còn /thread/new nên không lưu được chat)
                        if "/thread/" in page.url and not page.url.endswith("/thread/new"):
                            task["_result_meta"]["thread_url"] = page.url
                        now_text = await page.evaluate(LOG_TEXT_JS)
                        new_text = now_text[len(text_before):] if now_text.startswith(text_before) else now_text[-2000:]
                        task["_result_meta"]["muse_reply"] = new_text.strip()[-2000:]
                        logger.info(f"[{acc.account_id}] Nhận {kind} hợp lệ sau {int(time.time() - started)}s: {info} -> {dest_file.name}")
                        await self.update_task_progress(task_id, 95, "downloaded", f"Đã nhận {kind} {info}")
                        return True, dest_file, "Thành công"
                    logger.warning(f"[{acc.account_id}] Bỏ qua media không đạt ({info}): {src[:80]}")
                    rejected.add(src)
                await asyncio.sleep(SCAN_INTERVAL_SEC)

            raise TaskFailure("NO_MEDIA", f"Không nhận được {kind} hợp lệ sau {MEDIA_WAIT_SEC[kind]}s cho task {task_id}")

        except TaskFailure as tf:
            msg = str(tf)
            # Đã gửi prompt: kèm câu Muse vừa viết và địa chỉ chat để biết vì sao (chạy thật 28/10/2026: 3 tài khoản
            # NO_MEDIA liền, không ai biết Muse nói gì)
            if text_before is not None and page is not None and not page.is_closed() and tf.code != "MUSE_REPLIED_ERROR":
                try:
                    now_text = await page.evaluate(LOG_TEXT_JS)
                    said = _muse_reply_part(text_before, now_text, prompt)
                    if said:
                        msg += f" | Muse nói: {said[-400:]}"
                    if "/thread/" in page.url and not page.url.endswith("/thread/new"):
                        msg += f" | chat {page.url}"
                except Exception as e:   # trang hỏng giữa chừng: giữ lỗi gốc
                    logger.warning(f"[{acc.account_id}] Không đọc được chữ Muse sau lỗi: {e}")
            logger.error(f"[{acc.account_id}] Task {task_id} lỗi: {msg}")
            return False, None, msg
        except Exception as e:
            logger.error(f"[{acc.account_id}] Lỗi xử lý browser task {task_id}: {e}", exc_info=True)
            return False, None, f"BROWSER_ERROR: {e}"
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            for ap in attach_paths:
                discard_temp_file(ap)

    # ---------------------------------------------------------
    # Worker Task Loop with Concurrency Semaphore (N <= 2 slots)
    # ---------------------------------------------------------
    async def worker_slot_loop(self, slot_id: int):
        """Mỗi slot: giữ chỗ 1 tài khoản rảnh -> poll đúng tài khoản đó -> chạy task."""
        logger.info(f"Khởi động Fleet Worker Slot #{slot_id}")
        # Slot lẻ ưu tiên ảnh, slot chẵn ưu tiên video (vẫn chỉ nhận task đúng loại tài khoản)
        primary = "video" if slot_id % 2 == 0 else "image"
        kinds = [primary, "image" if primary == "video" else "video"]

        while self.running:
            try:
                account = self._reserve_account(kinds)
                if not account:
                    await asyncio.sleep(2.0)
                    continue

                task = await self.poll_task_from_backend(account)
                if not task:
                    account.last_empty_poll = time.time()   # nhường lượt hỏi cho tài khoản khác cùng loại
                    self._release_account(account)
                    await asyncio.sleep(1.0)
                    continue

                async with self.concurrency_semaphore:
                    async with account.lock:
                        account.status = "busy"
                        account.last_used = time.time()
                        task_id = task["task_id"]
                        self.save_accounts_config()

                        success, out_path, err_msg = await self.execute_task_with_browser(account, task)

                        if success and out_path:
                            meta = {
                                "project_id": task.get("project_id"),
                                "scene_id": task.get("scene_id"),
                                "account_id": account.account_id,
                                "estimated_tokens_used": 60000 if "video" in task.get("mode", "") else 15000,
                                **(task.get("_result_meta") or {}),   # thread_url, muse_reply của side chat
                            }
                            ok, detail = await self.complete_task_to_backend(task_id, out_path, meta)
                            if ok:
                                account.success_count += 1
                                account.last_error = None
                                account.status = "ready"
                                logger.info(f"[{account.account_id}] Đã hoàn thành và nộp task {task_id}")
                            else:
                                success, err_msg = False, f"UPLOAD_REJECTED: {detail}"

                        if not success:
                            await self.fail_task_to_backend(task_id, err_msg, account.account_id)
                            account.fail_count += 1
                            account.last_error = err_msg[:300]
                            if err_msg.startswith("SESSION_EXPIRED"):
                                account.status = "needs_login"
                                logger.error(f"[{account.account_id}] Phiên đăng nhập hết hạn - tạm ngừng tài khoản, cần chạy setup lại")
                            elif err_msg.startswith(("INPUT_IMAGE_MISSING", "ROUTING", "PROFILE_IN_USE")):
                                account.status = "ready"  # lỗi dữ liệu task, không phải lỗi tài khoản
                            else:
                                account.set_cooldown(ACCOUNT_COOLDOWN_SEC)
                            logger.warning(f"[{account.account_id}] Task {task_id} thất bại: {err_msg}")

                        account.last_used = time.time()
                        self.save_accounts_config()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Lỗi trong worker slot #{slot_id}: {e}", exc_info=True)
                await asyncio.sleep(3.0)

    # ---------------------------------------------------------
    # Heartbeat & Registration Background Loop
    # ---------------------------------------------------------
    async def heartbeat_and_sync_loop(self):
        """15s/lần: nạp lại cấu hình từ backend và gửi heartbeat cho tài khoản đã đăng nhập."""
        while self.running:
            try:
                self.refresh_accounts_from_disk()
                for acc in list(self.accounts.values()):
                    if acc.is_logged_in() and acc.status != "needs_login":
                        await self.register_account_to_backend(acc)
                        await self.send_account_heartbeat(acc)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat loop tick error: {e}")
            await asyncio.sleep(15.0)

    # ---------------------------------------------------------
    # Interactive Setup Mode (--setup [account_id])
    # ---------------------------------------------------------
    async def run_setup_mode(self, target_account_id: str):
        """Mở browser Chromium có giao diện để người dùng đăng nhập bằng tay 1 lần."""
        if target_account_id not in self.accounts:
            logger.error(f"Tài khoản '{target_account_id}' không tồn tại trong danh sách tài khoản!")
            print("\n[DANH SÁCH TÀI KHOẢN HỢP LỆ]")
            for aid, acc in self.accounts.items():
                print(f"  - {aid}: {acc.label} ({acc.type.upper()})")
            return

        acc = self.accounts[target_account_id]
        print("\n" + "=" * 65)
        print(f"  [*] CHẾ ĐỘ THIẾT LẬP ĐĂNG NHẬP: {acc.label}")
        print(f"  [*] Account ID: {acc.account_id} | Phân loại: {acc.type.upper()}")
        print(f"  [*] Thư mục Profile: {acc.profile_dir}")
        print("=" * 65)
        print("\n[HƯỚNG DẪN]:")
        print("1. Trình duyệt Chromium sẽ tự động mở lên màn hình.")
        print("2. Vui lòng tiến hành đăng nhập tài khoản Muse của bạn.")
        print("3. Sau khi đăng nhập thành công và vào được trang chính Muse,")
        print("   quay lại đây và nhấn phím ENTER để lưu phiên vĩnh viễn.\n")

        clean_singleton_locks(acc.profile_dir)
        playwright = await async_playwright().start()
        channel = get_installed_browser_channel()

        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(acc.profile_dir),
            headless=False,
            args=CHROME_STEALTH_ARGS,
            ignore_default_args=CHROME_IGNORE_DEFAULT_ARGS,
            viewport={"width": 1280, "height": 850},
            user_agent=REALISTIC_USER_AGENT,
            channel=channel,
        )
        await context.add_init_script(STEALTH_INIT_SCRIPT)
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            await page.goto(self.muse_web_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            logger.warning(f"Lỗi tải trang Muse: {e}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input, ">>> Nhấn [ENTER] tại đây sau khi bạn đã đăng nhập xong...")

        print(f"\n[*] Đang lưu phiên đăng nhập cho {acc.account_id}...")
        await context.close()
        await playwright.stop()

        acc.status = "ready"
        acc.cooldown_until = 0
        acc.last_error = None
        self.save_accounts_config()
        print(f"[OK] Thiết lập thành công cho tài khoản {acc.account_id}! Profile đã được lưu.")

    # ---------------------------------------------------------
    # Daemon Execution Mode (--daemon)
    # ---------------------------------------------------------
    async def run_daemon(self):
        """Chạy Fleet Runner nền. Chỉ 1 bản được chạy (file lock tự nhả khi process chết)."""
        if not acquire_runner_lock():
            logger.info("Fleet Runner khác đang chạy. Bỏ qua lần khởi động trùng.")
            print("[INFO] Fleet Runner already running. Exiting duplicate instance.")
            return

        print("\n" + "=" * 65)
        print("   META MUSE FLEET RUNNER - CỤM TRÌNH DUYỆT ĐA TÀI KHOẢN")
        print(f"   Loopback Backend: {self.loopback_url}")
        print(f"   Số tài khoản quản lý: {len(self.accounts)}")
        print(f"   Concurrency khống chế: N = {self.concurrency_limit} slots (RAM < 1.5GB)")
        print("=" * 65 + "\n")
        logger.info(f"Fleet Runner bắt đầu (PID {os.getpid()}, {len(self.accounts)} tài khoản)")

        self.running = True
        self.playwright = await async_playwright().start()
        worker_tasks = [asyncio.create_task(self.worker_slot_loop(slot_id=i + 1)) for i in range(self.concurrency_limit)]
        heartbeat_task = asyncio.create_task(self.heartbeat_and_sync_loop())

        try:
            await asyncio.gather(*worker_tasks, heartbeat_task)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Nhận tín hiệu dừng Fleet Runner...")
        finally:
            self.running = False
            for t in worker_tasks:
                t.cancel()
            heartbeat_task.cancel()
            if self.playwright:
                await self.playwright.stop()
            if self._http:
                await self._http.aclose()
            self.save_accounts_config()
            release_runner_lock()
            logger.info("Fleet Runner đã dừng an toàn.")


# -------------------------------------------------------------
# CLI Entrypoint
# -------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Story Studio Meta Muse Fleet Runner")
    parser.add_argument("--setup", type=str, metavar="ACCOUNT_ID", help="Mở giao diện Chromium để đăng nhập tài khoản thủ công")
    parser.add_argument("--daemon", action="store_true", help="Chạy Fleet Runner ở chế độ Daemon ngầm đa tài khoản")
    parser.add_argument("--concurrency", type=int, default=2, help="Số lượng browser slot chạy song song tối đa (1 hoặc 2)")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000/api/muse-bridge", help="Loopback URL tới Story Studio Backend")
    parser.add_argument("--muse-url", type=str, default="https://muse.ai", help="Địa chỉ giao diện Web Muse AI")
    parser.add_argument("--list", action="store_true", help="Hiển thị danh sách tài khoản trong Fleet")

    args = parser.parse_args()

    runner = MuseFleetRunner(
        loopback_url=args.url,
        muse_web_url=args.muse_url,
        concurrency_limit=args.concurrency,
    )

    if args.list:
        print("\n" + "=" * 86)
        print(f"{'ACCOUNT ID':<20} {'TYPE':<7} {'STATUS':<12} {'LOGIN':<6} {'ACTIVE':<7} {'LABEL'}")
        print("=" * 86)
        for aid, acc in runner.accounts.items():
            print(f"{aid:<20} {acc.type.upper():<7} {acc.status:<12} {'yes' if acc.is_logged_in() else 'no':<6} {'yes' if acc.is_active else '':<7} {acc.label}")
        print("=" * 86 + "\n")
        return

    if args.setup:
        asyncio.run(runner.run_setup_mode(args.setup.strip()))
    elif args.daemon:
        asyncio.run(runner.run_daemon())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
