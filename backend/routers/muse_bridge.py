import asyncio
import base64
import json
import logging
import os
import re
import shutil
import socket
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, Request, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import EXTRA_CHROME_PROFILES_DIRS, MUSE_AGENT_WAIT_MIN, PROJECTS_DIR, STATIC_DIR
from services.climax_brief import AGENT_REPLY_MAX_CHARS, AGENT_VIDEO_MODE
from services import location_sheets
from security import (
    MEDIA_EXTS,
    MAX_UPLOAD_BYTES,
    is_safe_id,
    is_within,
    read_upload_limited,
    require_safe_id,
    validate_path_ids,
)

logger = logging.getLogger("story_studio.muse_bridge")

router = APIRouter(prefix="/api/muse-bridge", tags=["Meta Muse Cloud Bridge"], dependencies=[Depends(validate_path_ids)])

# Thư mục lưu trữ media do Fleet Runner tạo ra
MUSE_OUTPUTS_DIR = STATIC_DIR / "muse_outputs"
MUSE_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

OFFLINE_THRESHOLD_SEC = 60.0  # Coi là offline nếu không nhận heartbeat sau 60s
# Task đã gán cho 1 tài khoản nhưng chờ quá lâu thì tài khoản rảnh khác CÙNG LOẠI được nhận thay
REASSIGN_AFTER_SEC = 20.0
# Thời gian chờ tối đa phía server cho 1 task: phải phủ cả vòng thử lại (MAX_TASK_RETRIES + 1 lượt, mỗi lượt ~30 s mở
# trình duyệt + MEDIA_WAIT_SEC của runner, nghỉ ACCOUNT_COOLDOWN_SEC giữa các lượt). Trước 26/10/2026 là 240 s: server bỏ
# cuộc và trả tiền ảnh 9router trong khi lượt thử lại của runner ra ảnh Muse 45 s sau.
IMAGE_TASK_TIMEOUT_SEC = 720.0
VIDEO_TASK_TIMEOUT_SEC = 1200.0
# Khóa tài khoản khi Muse báo hết quota / chặn vùng / mất phiên đăng nhập
ACCOUNT_BLOCK_SEC = 900.0
MAX_TASK_RETRIES = 2
# ID của 2 trạm VM cũ (đã ngừng dùng). Client cũ còn gửi thì coi như "không chỉ định tài khoản".
LEGACY_ALIAS_ACCOUNTS = {"muse_acc_image", "muse_acc_video"}

QUOTA_ERROR_KEYWORDS = (
    "quota", "rate limit", "429", "exceeded", "upgrade", "out of credits",
    "region block", "not_available", "not available in your",
)
SESSION_ERROR_KEYWORDS = ("session_expired", "login required", "đăng nhập lại")

# -------------------------------------------------------------
# In-Memory State & Task Queue
# -------------------------------------------------------------
# Worker gần nhất gửi tín hiệu (Fleet Runner trên máy này)
current_worker: Dict[str, Any] = {
    "worker_id": None,
    "hostname": socket.gethostname(),
    "os_info": None,
    "hardware": {},
    "capabilities": [],
    "status": "offline",  # "online" | "processing" | "offline"
    "last_heartbeat": 0,
    "active_task_id": None,
}

# Per-account worker connection state
account_workers: Dict[str, Dict[str, Any]] = {}

# Task storage
pending_tasks: List[Dict[str, Any]] = []
active_tasks: Dict[str, Dict[str, Any]] = {}
task_history: List[Dict[str, Any]] = []  # Lưu 100 task gần nhất
task_waiters: Dict[str, asyncio.Event] = {}

stats: Dict[str, Any] = {
    "tokens_used": 0,
    "completed_count": 0,
    "failed_count": 0,
}

# -------------------------------------------------------------
# Fleet Account Store & Strict Image/Video Router
# -------------------------------------------------------------
BACKEND_DIR = STATIC_DIR.parent
CONFIG_DIR = BACKEND_DIR / "config"
MUSE_FLEET_ACCOUNTS_FILE = CONFIG_DIR / "muse_fleet_accounts.json"
CHROME_PROFILES_DIR = BACKEND_DIR / "chrome_profiles"

IMAGE_CAPABILITIES = ["text-to-image", "image-upscale-2k"]
VIDEO_CAPABILITIES = ["image-to-video", "text-to-video"]
# Các trường do backend quản lý trong muse_fleet_accounts.json (runner chỉ ghi trạng thái chạy)
BACKEND_OWNED_FIELDS = (
    "label", "type", "capabilities", "profile_dir",
    "is_active_for_image", "is_active_for_video", "blocked_until", "block_reason",
)


def _default_fleet_accounts() -> List[Dict[str, Any]]:
    accounts = []
    for kind, short, caps in (("image", "img", IMAGE_CAPABILITIES), ("video", "vid", VIDEO_CAPABILITIES)):
        for i in range(1, 6):
            aid = f"muse_acc_{short}_{i:02d}"
            accounts.append({
                "account_id": aid,
                "label": f"Muse {kind.capitalize()} Account {i:02d}",
                "type": kind,
                "capabilities": list(caps),
                "profile_dir": f"chrome_profiles/{aid}",
                "status": "ready",
                "cooldown_until": 0,
                "is_active_for_image": kind == "image" and i == 1,
                "is_active_for_video": kind == "video" and i == 1,
            })
    return accounts


def task_kind(mode: Optional[str]) -> str:
    """Loại task: 'video' cho image-to-video / text-to-video, còn lại là 'image'."""
    return "video" if "video" in str(mode or "").lower() else "image"


# Side chat Muse dùng lại được (video cao trào, chủ dự án 28/10/2026): mỗi cảnh một chat trên một tài khoản video,
# tài khoản đó vẽ cả ảnh grid. Các trường dưới đây đều tuỳ chọn; thiếu thì task chạy y như cũ.
THREAD_URL_RE = re.compile(r"https://muse\.ai/thread/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
MUSE_REPLY_MAX_CHARS = 2000
# Giao việc nhiều bước cho Muse (video cao trào): runner chờ Muse làm xong lượt, nộp video cuối + ảnh phụ + báo cáo dài
AGENT_MAX_EXTRAS = 4
AGENT_MAX_WARNINGS = 10


def routing_kind(task: Dict[str, Any]) -> str:
    """Loại tài khoản nhận task: `route_kind` nếu có ("image"/"video"), không thì theo loại media của task.
    Khác `task_kind(mode)`: loại media quyết định đuôi file và cách kiểm kết quả (ảnh grid vẫn là ảnh)."""
    rk = task.get("route_kind")
    return rk if rk in ("image", "video") else task_kind(task.get("mode"))


def valid_thread_url(value: Any) -> Optional[str]:
    """Địa chỉ side chat Muse hợp lệ (đúng dạng https://muse.ai/thread/<uuid>), không thì None."""
    return value if isinstance(value, str) and THREAD_URL_RE.fullmatch(value) else None


def validate_thread_fields(task: Dict[str, Any]) -> None:
    """Kiểm các trường side chat của task trước khi xếp hàng; sai thì ValueError (không xếp hàng)."""
    if task.get("route_kind") is not None and task["route_kind"] not in ("image", "video"):
        raise ValueError(f"route_kind không hợp lệ: {task['route_kind']!r}")
    if task.get("thread_url") is not None and not valid_thread_url(task["thread_url"]):
        raise ValueError(f"thread_url không phải side chat Muse: {str(task['thread_url'])[:120]}")
    atts = task.get("attachments")
    if atts is not None:
        if not isinstance(atts, list) or not all(isinstance(a, str) for a in atts):
            raise ValueError("attachments phải là danh sách đường dẫn")
        for a in atts:
            if not (Path(a).is_file() and is_within(a, PROJECTS_DIR, STATIC_DIR)):
                raise ValueError(f"Ảnh đính kèm không có hoặc nằm ngoài projects/ và backend/static/: {a}")
        task["attachments"] = [str(Path(a).resolve()) for a in atts]
    avoid = task.get("avoid_accounts")
    if avoid is not None and (not isinstance(avoid, list) or not all(isinstance(a, str) for a in avoid)):
        raise ValueError("avoid_accounts phải là danh sách id tài khoản")


def account_kind(acc: Optional[Dict[str, Any]]) -> Optional[str]:
    """Loại tài khoản: ưu tiên trường 'type', nếu thiếu thì suy ra từ capabilities (phải rõ ràng 1 loại)."""
    if not acc:
        return None
    t = str(acc.get("type", "")).lower()
    if t in ("image", "video"):
        return t
    caps = acc.get("capabilities") or []
    has_video = any(c in caps for c in VIDEO_CAPABILITIES)
    has_image = "text-to-image" in caps
    if has_video != has_image:
        return "video" if has_video else "image"
    return None


def _read_fleet_file() -> Dict[str, Any]:
    try:
        with open(MUSE_FLEET_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            data = {"accounts": data}
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"Could not read muse_fleet_accounts.json ({e})")
        return {}


def load_muse_accounts() -> List[Dict[str, Any]]:
    data = _read_fleet_file()
    accs = [dict(a) for a in data.get("accounts", []) if isinstance(a, dict) and a.get("account_id")]
    accs = [a for a in accs if a["account_id"] not in LEGACY_ALIAS_ACCOUNTS]
    if not accs:
        accs = _default_fleet_accounts()
        save_muse_accounts(accs)
    return accs


def save_muse_accounts(accounts: List[Dict[str, Any]]) -> None:
    """Ghi các trường do backend quản lý vào muse_fleet_accounts.json, giữ nguyên trạng thái do runner ghi."""
    try:
        data = _read_fleet_file()
        on_disk = {a.get("account_id"): a for a in data.get("accounts", []) if isinstance(a, dict)}
        merged = []
        for acc in accounts:
            aid = acc["account_id"]
            if aid in LEGACY_ALIAS_ACCOUNTS:
                continue
            item = dict(on_disk.get(aid) or acc)
            for key in BACKEND_OWNED_FIELDS:
                if key in acc:
                    item[key] = acc[key]
            item["account_id"] = aid
            merged.append(item)
        data["accounts"] = merged
        data.setdefault("concurrency_limit", 2)
        # Fleet Runner là tiến trình riêng, không đọc .env: chuyển danh sách thư mục profile ngoài qua file này
        data["extra_profiles_dirs"] = [str(p) for p in EXTRA_CHROME_PROFILES_DIRS]
        MUSE_FLEET_ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = MUSE_FLEET_ACCOUNTS_FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, MUSE_FLEET_ACCOUNTS_FILE)
    except Exception as e:
        logger.error(f"Error saving muse_fleet_accounts.json: {e}")


muse_accounts: List[Dict[str, Any]] = load_muse_accounts()

fleet_runner_proc = None


def find_account(account_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not account_id:
        return None
    return next((a for a in muse_accounts if a.get("account_id") == account_id), None)


def ensure_local_fleet_runner():
    """Tự động kích hoạt cụm Fleet Runner chạy ngầm trên Windows PC nếu chưa chạy (Single Instance Guard)."""
    global fleet_runner_proc
    from config import PORT
    from runners import autostart
    if fleet_runner_proc is not None and fleet_runner_proc.poll() is None:
        return  # vừa spawn, runner chưa kịp lấy lock
    save_muse_accounts(muse_accounts)   # để runner thấy đúng danh sách thư mục profile ngoài (extra_profiles_dirs)
    try:
        proc = autostart.start_fleet_runner_daemon(PORT)
    except OSError as e:
        logger.warning(f"Không bật được Fleet Runner: {e}")
        return
    if proc is not None:
        fleet_runner_proc = proc
        logger.info("Đã bật Fleet Runner chạy ngầm (gọi về %s)", autostart.runner_url(PORT))


def is_account_online(account_id: Optional[str]) -> bool:
    w = account_workers.get(account_id or "")
    return bool(w and (time.time() - w.get("last_heartbeat", 0)) < OFFLINE_THRESHOLD_SEC)


def is_local_fleet_runner_active() -> bool:
    """Fleet Runner được coi là đang chạy khi có ít nhất 1 tài khoản gửi heartbeat gần đây."""
    return any(is_account_online(aid) for aid in account_workers)


def is_account_profile_installed(acc: Dict[str, Any]) -> bool:
    """Xác thực profile Chromium có tồn tại và đã có phiên đăng nhập trên đĩa."""
    p_dir = acc.get("profile_dir")
    if not p_dir:
        return False
    full_p = (BACKEND_DIR / p_dir).resolve() if not Path(p_dir).is_absolute() else Path(p_dir).resolve()
    if not is_within(full_p, CHROME_PROFILES_DIR, *EXTRA_CHROME_PROFILES_DIRS):
        return False
    default_p = full_p / "Default"
    if not default_p.exists():
        return False
    idb = default_p / "IndexedDB" / "https_muse.ai_0.indexeddb.leveldb"
    cookies = default_p / "Network" / "Cookies"
    return idb.exists() or cookies.exists()


def is_account_blocked(acc: Dict[str, Any]) -> bool:
    return float(acc.get("blocked_until") or 0) > time.time()


def is_account_available(acc: Optional[Dict[str, Any]]) -> bool:
    """Tài khoản dùng được: xác định rõ loại, đã đăng nhập, không bị khóa quota/phiên."""
    return bool(acc) and account_kind(acc) is not None and is_account_profile_installed(acc) and not is_account_blocked(acc)


def is_kind_online(kind: str) -> bool:
    """Có ít nhất 1 tài khoản đúng loại đang online và dùng được."""
    return any(
        account_kind(a) == kind and is_account_available(a) and is_account_online(a["account_id"])
        for a in muse_accounts
    )


def get_enriched_accounts() -> List[Dict[str, Any]]:
    now = time.time()
    # Nạp lại trạng thái chạy (status/cooldown/thống kê) do runner ghi xuống đĩa
    on_disk = {a.get("account_id"): a for a in _read_fleet_file().get("accounts", []) if isinstance(a, dict)}

    enriched = []
    for acc in muse_accounts:
        item = dict(acc)
        aid = item["account_id"]
        disk = on_disk.get(aid) or {}
        for key in ("status", "cooldown_until", "last_used", "success_count", "fail_count"):
            if key in disk:
                item[key] = disk[key]

        w = account_workers.get(aid)
        has_profile = is_account_profile_installed(item)
        blocked = is_account_blocked(item)
        is_on = has_profile and is_account_online(aid)

        item["has_profile"] = has_profile
        item["kind"] = account_kind(item)
        item["online"] = is_on
        if not has_profile:
            item["status"] = "offline"
        elif blocked:
            item["status"] = "blocked"
        elif is_on and item.get("status") not in ("busy", "cooldown"):
            item["status"] = "online"
        elif item.get("status") not in ("ready", "busy", "cooldown", "online"):
            item["status"] = "ready"
        item["last_seen_sec"] = round(now - w["last_heartbeat"], 1) if (w and is_on) else None
        item["worker_id"] = w.get("worker_id") if (w and is_on) else None
        item["hardware"] = dict((w or {}).get("hardware") or {})
        enriched.append(item)
    return enriched


def get_active_account(mode: str = "image") -> Optional[Dict[str, Any]]:
    """Tài khoản đang được chọn cho loại task (chỉ trong đúng loại image/video)."""
    kind = task_kind(mode)
    active_key = "is_active_for_video" if kind == "video" else "is_active_for_image"
    same_kind = [a for a in muse_accounts if account_kind(a) == kind]
    usable = [a for a in same_kind if is_account_available(a)]
    for pool in (usable, same_kind):
        for acc in pool:
            if acc.get(active_key):
                return acc
        if pool:
            return pool[0]
    return None


def get_active_account_id(mode: str) -> Optional[str]:
    acc = get_active_account(mode)
    return acc["account_id"] if acc else None


def _set_task_account(task: Dict[str, Any], acc: Optional[Dict[str, Any]]) -> None:
    task["assigned_account"] = acc["account_id"] if acc else None
    task["account_label"] = acc.get("label") if acc else None
    task["profile_dir"] = acc.get("profile_dir") if acc else None


def assign_task_account(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gán tài khoản cho task theo loại NGHIÊM NGẶT: task ảnh -> tài khoản image, task video -> tài khoản video.
    Tài khoản client yêu cầu chỉ được dùng nếu đúng loại và đang dùng được; nếu không thì dùng tài khoản active cùng loại.
    """
    kind = routing_kind(task)
    task["task_kind"] = kind
    req_acc_id = task.get("assigned_account") or task.get("account_id")
    if not req_acc_id and isinstance(task.get("parameters"), dict):
        req_acc_id = task["parameters"].get("assigned_account") or task["parameters"].get("account_id")

    selected = None
    if req_acc_id and req_acc_id not in LEGACY_ALIAS_ACCOUNTS:
        acc = find_account(req_acc_id)
        if acc and account_kind(acc) == kind and (is_account_available(acc) or task.get("pin_account")):
            selected = acc   # task ghim (side chat của tài khoản này) giữ đúng tài khoản; dùng được không thì người gọi báo lỗi
        elif acc:
            logger.warning(
                f"Task {task.get('task_id')} ({kind}) yêu cầu tài khoản '{req_acc_id}' "
                f"(loại {account_kind(acc)}, dùng được: {is_account_available(acc)}) -> chuyển sang tài khoản {kind} active."
            )

    avoid = set(task.get("avoid_accounts") or [])
    if selected is None and avoid:
        selected = next((a for a in sorted(muse_accounts, key=lambda a: (not is_account_online(a["account_id"]), a["account_id"]))
                         if account_kind(a) == kind and a["account_id"] not in avoid and is_account_available(a)), None)
    _set_task_account(task, selected or get_active_account(kind))
    return task


def enqueue_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Đưa task vào hàng đợi (đã gán tài khoản đúng loại)."""
    task.setdefault("task_id", f"task_m_{uuid.uuid4().hex[:8]}")
    task.setdefault("created_at", time.time())
    task["queued_at"] = time.time()
    task["status"] = "pending"
    assign_task_account(task)
    pending_tasks.append(task)
    return task


def pick_fallback_account(kind: str, exclude: Optional[str] = None,
                          avoid: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Tài khoản dự phòng cùng loại, ưu tiên đang online, không bị khóa, không nằm trong `avoid`."""
    skip = set(avoid or [])
    candidates = [
        a for a in muse_accounts
        if account_kind(a) == kind and a["account_id"] != exclude and a["account_id"] not in skip
        and is_account_available(a)
    ]
    candidates.sort(key=lambda a: (not is_account_online(a["account_id"]), a["account_id"]))
    return candidates[0] if candidates else None


def block_account(account_id: str, reason: str) -> None:
    """Khóa tài khoản 15 phút (hết quota / mất phiên) và chuyển cờ active sang tài khoản khác cùng loại."""
    acc = find_account(account_id)
    kind = account_kind(acc)
    if not acc or not kind:
        return
    acc["blocked_until"] = time.time() + ACCOUNT_BLOCK_SEC
    acc["block_reason"] = reason[:200]
    active_key = "is_active_for_video" if kind == "video" else "is_active_for_image"
    if acc.get(active_key):
        nxt = pick_fallback_account(kind, exclude=account_id)
        if nxt:
            for a in muse_accounts:
                if account_kind(a) == kind:
                    a[active_key] = a["account_id"] == nxt["account_id"]
            logger.info(f"[AUTO-FAILOVER] Tài khoản {kind} active chuyển từ {account_id} sang {nxt['account_id']}")
    save_muse_accounts(muse_accounts)
    logger.warning(f"Khóa tài khoản {account_id} trong {int(ACCOUNT_BLOCK_SEC)}s: {reason[:120]}")

# -------------------------------------------------------------
# Pydantic Schemas
# -------------------------------------------------------------
class AccountSwitchRequest(BaseModel):
    mode: str = Field(description="'image' | 'video'")
    account_id: str

class AccountCreateUpdateRequest(BaseModel):
    account_id: str
    label: str
    capabilities: List[str] = Field(default_factory=list)
    profile_dir: Optional[str] = None
    is_active_for_image: Optional[bool] = False
    is_active_for_video: Optional[bool] = False

class WorkerRegisterRequest(BaseModel):
    worker_id: str
    account_id: Optional[str] = None
    hostname: Optional[str] = None
    tailscale_ip: Optional[str] = None  # không còn dùng (VM cũ), giữ để runner cũ gửi lên không lỗi
    os_info: Optional[str] = None
    hardware: Optional[Dict[str, Any]] = None
    capabilities: Optional[List[str]] = None
    agent_version: Optional[str] = "1.0.0"
    timestamp: Optional[int] = None

class WorkerHeartbeatRequest(BaseModel):
    worker_id: str
    account_id: Optional[str] = None
    hardware: Optional[Dict[str, Any]] = None

class TaskCreateRequest(BaseModel):
    mode: str = Field(default="text-to-image", description="text-to-image | image-to-video | text-to-video")
    prompt: str
    negative_prompt: Optional[str] = ""
    project_id: Optional[str] = None
    scene_id: Optional[str] = None
    output_path: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    input_image_url: Optional[str] = None
    reference_image_url: Optional[str] = None
    reference_image_path: Optional[str] = None
    reference_image: Optional[str] = None
    character_anchor: Optional[str] = None
    camera_motion: Optional[str] = None
    action_prompt: Optional[str] = None
    # None: lấy parameters.duration / duration_sec (nút "Muse Video" chỉ gửi duration_sec), không có thì 5 giây
    duration: Optional[int] = None
    aspect_ratio: Optional[str] = "16:9"
    assigned_account: Optional[str] = None
    profile_dir: Optional[str] = None
    timeout_sec: Optional[int] = 180

class TaskProgressRequest(BaseModel):
    task_id: str
    worker_id: Optional[str] = None
    status: str = "processing"
    progress_percent: int = 0
    stage: Optional[str] = ""
    status_message: Optional[str] = ""
    elapsed_seconds: Optional[float] = 0.0

class TaskFailRequest(BaseModel):
    task_id: str
    worker_id: Optional[str] = None
    error: str

# -------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------
def is_muse_worker_online(account_id: Optional[str] = None) -> bool:
    """Có tài khoản Fleet nào (hoặc đúng tài khoản account_id) đang gửi heartbeat không."""
    if account_id:
        if account_id in LEGACY_ALIAS_ACCOUNTS:
            return is_kind_online("video" if account_id == "muse_acc_video" else "image")
        return is_account_online(account_id)
    return is_local_fleet_runner_active()


def _task_timeout(task: Dict[str, Any]) -> float:
    if task.get("mode") == AGENT_VIDEO_MODE:
        return MUSE_AGENT_WAIT_MIN * 60 + 120
    return VIDEO_TASK_TIMEOUT_SEC if task_kind(task.get("mode")) == "video" else IMAGE_TASK_TIMEOUT_SEC


def abandon_task(task_id: str, reason: str) -> None:
    """
    Người gọi đã bỏ cuộc (timeout): gỡ task khỏi hàng đợi, đánh dấu abandoned.
    Kết quả về muộn (nếu có) chỉ lưu vào bộ sưu tập muse_outputs, KHÔNG ghi đè vào dự án.
    """
    task = active_tasks.pop(task_id, None)
    if task is None:
        for idx, p in enumerate(pending_tasks):
            if p["task_id"] == task_id:
                task = pending_tasks.pop(idx)
                break
    if task is None:
        return
    task["status"] = "failed"
    task["abandoned"] = True
    task["error"] = reason
    task["failed_at"] = time.time()
    task_history.insert(0, task)
    stats["failed_count"] += 1
    if current_worker.get("active_task_id") == task_id:
        current_worker["active_task_id"] = None


def get_worker_status_string() -> str:
    if not is_muse_worker_online():
        return "offline"
    # Dọn task đang chạy quá thời gian tối đa của loại task đó
    now = time.time()
    stale_ids = [
        tid for tid, t in active_tasks.items()
        if now - t.get("started_at", t.get("created_at", now)) > _task_timeout(t) + 60
    ]
    for tid in stale_ids:
        abandon_task(tid, "Task timed out (stale active task)")
    if current_worker.get("active_task_id") or len(active_tasks) > 0:
        return "busy"
    return "online"


async def enqueue_and_wait_muse_task(task_dict: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
    """
    Hàm gọi từ Python Service (image_service / video_service) để đưa task vào queue và chờ kết quả.
    Raise lỗi nếu không có tài khoản đúng loại đang online hoặc timeout để service fallback sang engine khác.
    """
    validate_thread_fields(task_dict)
    kind = task_kind(task_dict.get("mode"))   # loại media: quyết định cách chuẩn hoá payload bên dưới
    route = routing_kind(task_dict)           # loại tài khoản nhận việc
    if not is_kind_online(route):
        raise RuntimeError(
            f"Không có tài khoản Muse {'video' if route == 'video' else 'ảnh'} nào đang online "
            f"(Fleet Runner chưa chạy hoặc tài khoản chưa đăng nhập / đang bị khóa)"
        )
    avoid = set(task_dict.get("avoid_accounts") or [])
    if avoid and not task_dict.get("pin_account") and not any(
            account_kind(a) == route and a["account_id"] not in avoid and is_account_available(a)
            and is_account_online(a["account_id"]) for a in muse_accounts):
        raise RuntimeError(f"Mọi tài khoản Muse {route} đang online đều vừa lỗi với việc này "
                           f"({', '.join(sorted(avoid))}): chờ lúc khác hoặc thêm tài khoản")
    if task_dict.get("pin_account"):
        owner = task_dict.get("assigned_account")
        acc = find_account(owner)
        if not (acc and account_kind(acc) == route and is_account_available(acc) and is_account_online(owner)):
            raise RuntimeError(f"Tài khoản {owner} của side chat này không dùng được (offline, bị khoá hoặc mất "
                               f"đăng nhập): mở chat mới trên tài khoản khác")

    task_id = task_dict.get("task_id") or f"task_m_{uuid.uuid4().hex[:8]}"
    task_dict["task_id"] = task_id
    task_dict["created_at"] = time.time()

    # Chuẩn hóa và phân tách payload chuẩn cho Image vs Video
    params = task_dict.setdefault("parameters", {})
    if kind == "video":
        if task_dict.get("mode") != AGENT_VIDEO_MODE:   # việc nhiều bước giữ nguyên chế độ để runner nhận ra
            task_dict["mode"] = "image-to-video" if (task_dict.get("input_image_url") or params.get("input_image_url")) else "text-to-video"
        camera_motion = task_dict.get("camera_motion") or params.get("camera_motion") or "cinematic slow tracking pan, smooth camera motion"
        duration = task_dict.get("duration") or params.get("duration") or params.get("duration_sec") or 5
        action_prompt = task_dict.get("action_prompt") or task_dict.get("prompt")
        input_img = task_dict.get("input_image_url") or params.get("input_image_url")

        task_dict["camera_motion"] = camera_motion
        task_dict["duration"] = duration
        task_dict["action_prompt"] = action_prompt
        if input_img:
            task_dict["input_image_url"] = str(input_img)

        params.setdefault("camera_motion", camera_motion)
        params.setdefault("duration", duration)
        params.setdefault("duration_sec", duration)
        params.setdefault("action_cues", action_prompt)
        params.setdefault("fps", 24)
        if input_img:
            params.setdefault("input_image_url", str(input_img))
    else:
        task_dict["mode"] = "text-to-image"
        aspect_ratio = task_dict.get("aspect_ratio") or params.get("aspect_ratio") or "16:9"
        char_anchor = task_dict.get("character_anchor") or params.get("character_anchor") or ""
        task_dict["aspect_ratio"] = aspect_ratio
        params.setdefault("aspect_ratio", aspect_ratio)
        params.setdefault("resolution", "2K")
        if char_anchor:
            task_dict["character_anchor"] = char_anchor
            params.setdefault("character_anchor", char_anchor)

    # Chuẩn hóa reference image nếu có
    ref = task_dict.get("reference_image") or task_dict.get("reference_image_url") or task_dict.get("reference_image_path")
    if ref:
        task_dict["reference_image"] = ref
        if not task_dict.get("reference_image_url"):
            if str(ref).startswith("http") or str(ref).startswith("/"):
                task_dict["reference_image_url"] = str(ref)
            else:
                p_ref = Path(ref)
                if p_ref.exists() and is_within(p_ref, PROJECTS_DIR, STATIC_DIR):
                    task_dict["reference_image_url"] = f"/api/muse-bridge/reference-file?path={urllib.parse.quote(str(p_ref.resolve()))}"
        if not task_dict.get("reference_image_path") and not str(ref).startswith("http"):
            task_dict["reference_image_path"] = str(ref)

    # Tạo event chờ
    waiter = asyncio.Event()
    task_waiters[task_id] = waiter

    enqueue_task(task_dict)
    wait_sec = timeout or _task_timeout(task_dict)
    logger.info(
        f"Enqueued Muse task {task_id}: {task_dict.get('mode')} -> {task_dict.get('assigned_account')} "
        f"(timeout {int(wait_sec)}s) - Prompt: {str(task_dict.get('prompt'))[:50]}..."
    )

    try:
        await asyncio.wait_for(waiter.wait(), timeout=wait_sec)
    except asyncio.TimeoutError:
        abandon_task(task_id, f"Caller timed out after {int(wait_sec)}s")
        raise TimeoutError(f"Meta Muse task {task_id} timed out after {int(wait_sec)}s")
    finally:
        task_waiters.pop(task_id, None)

    # Lấy task đã hoàn thành
    for item in task_history:
        if item.get("task_id") == task_id:
            if item.get("status") == "failed":
                raise RuntimeError(f"Muse task failed: {item.get('error')}")
            return item

    raise RuntimeError(f"Muse task {task_id} settled without recorded result")

# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@router.get("/status")
async def get_bridge_status():
    """Cung cấp trạng thái Telemetry và Task Queue cho Web Dashboard."""
    worker_online = is_muse_worker_online()
    status_str = get_worker_status_string()
    now = time.time()
    last_seen_sec = round(now - current_worker["last_heartbeat"], 1) if current_worker["last_heartbeat"] > 0 else 9999

    active_job = None
    if active_tasks:
        active_job = list(active_tasks.values())[0]

    # Collect recent completed items with guaranteed valid URLs
    gallery_items = []
    seen_ids = set()
    for item in task_history:
        if item.get("status") != "completed":
            continue
        tid = item.get("task_id")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            m_url = item.get("media_url") or ""
            out_str = item.get("output_path") or item.get("image_path") or ""
            if not m_url or m_url.endswith("/") or "None" in m_url:
                if out_str and str(out_str).strip():
                    out_p = Path(out_str)
                    if out_p.is_file() and out_p.exists() and out_p.name:
                        m_url = f"/static/muse_outputs/{out_p.name}"
                    else:
                        m_url = f"/api/muse-bridge/download/{tid}"
                else:
                    m_url = f"/api/muse-bridge/download/{tid}"
            item["media_url"] = m_url
            item["download_url"] = f"/api/muse-bridge/download/{tid}"
            item["media_type"] = "video" if ("video" in str(item.get("mode", "")) or str(m_url).endswith(".mp4")) else "image"
            gallery_items.append(item)

    # If gallery is short, also include any media files in MUSE_OUTPUTS_DIR
    # (bỏ qua file đã hiện qua lịch sử task: file tên task_xxx.jpg trùng task_id task_xxx)
    shown_urls = {it.get("media_url") for it in gallery_items}
    for f in sorted(MUSE_OUTPUTS_DIR.glob("*.*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".mp4"):
            file_key = f.name
            if f.stem in seen_ids or f"/static/muse_outputs/{f.name}" in shown_urls:
                continue
            if file_key not in seen_ids:
                seen_ids.add(file_key)
                is_vid = f.suffix.lower() == ".mp4"
                label_name = f"Cảnh {f.stem.replace('scene_', '#')} (Video 10s)" if is_vid else f"Cảnh {f.stem.replace('scene_', '#')} (Ảnh 2K)"
                gallery_items.append({
                    "task_id": f.stem,
                    "scene_id": label_name,
                    "media_type": "video" if is_vid else "image",
                    "media_url": f"/static/muse_outputs/{f.name}",
                    "download_url": f"/static/muse_outputs/{f.name}",
                    "status": "completed",
                    "output_path": str(f),
                })

    enriched_accounts = get_enriched_accounts()
    fleet_active = is_local_fleet_runner_active()

    return {
        "online": worker_online,
        "status": status_str,
        "is_fleet_runner": True,
        "runner_mode": "local_fleet",
        "fleet_runner_active": fleet_active,
        "image_online": is_kind_online("image"),
        "video_online": is_kind_online("video"),
        "concurrency_limit": 2,
        "active_job": active_job,
        "recent_completed": gallery_items[:30],
        "accounts": enriched_accounts,
        "active_image_account": get_active_account_id("image"),
        "active_video_account": get_active_account_id("video"),
        "worker": {
            "worker_id": current_worker["worker_id"],
            "hostname": current_worker["hostname"],
            "os_info": current_worker["os_info"],
            "capabilities": current_worker["capabilities"],
            "active_task_id": current_worker["active_task_id"],
        },
        "stats": {
            "pending_tasks": len(pending_tasks),
            "processing_tasks": len(active_tasks),
            "completed_tasks": stats["completed_count"],
            "failed_tasks": stats["failed_count"],
            "tokens_used": stats["tokens_used"],
        },
        "telemetry": {
            "hostname": current_worker["hostname"],
            "last_seen_sec": last_seen_sec if worker_online else None,
        },
    }

# -------------------------------------------------------------
# Fleet Account Endpoints
# -------------------------------------------------------------
@router.get("/accounts")
async def list_muse_accounts():
    """Lấy danh sách các tài khoản Meta Muse và cấu hình kích hoạt cho ảnh và video."""
    enriched = get_enriched_accounts()
    return {
        "accounts": enriched,
        "active_image_account": get_active_account_id("image"),
        "active_video_account": get_active_account_id("video"),
    }

@router.post("/accounts/switch")
async def switch_muse_account(req: AccountSwitchRequest):
    """
    Kích hoạt tài khoản được chọn cho mode ('image' hoặc 'video'). Chỉ chọn được tài khoản đúng loại.
    """
    mode = req.mode.strip().lower()
    if mode not in ("image", "video"):
        raise HTTPException(status_code=400, detail="Mode phải là 'image' hoặc 'video'")

    target_acc = find_account(req.account_id)
    if not target_acc:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài khoản '{req.account_id}'")
    if account_kind(target_acc) != mode:
        raise HTTPException(
            status_code=400,
            detail=f"Tài khoản '{req.account_id}' là tài khoản {account_kind(target_acc) or 'chưa rõ loại'}, không dùng cho {mode}",
        )

    active_key = "is_active_for_image" if mode == "image" else "is_active_for_video"
    for acc in muse_accounts:
        if account_kind(acc) == mode:
            acc[active_key] = acc["account_id"] == req.account_id
    save_muse_accounts(muse_accounts)
    logger.info(f"Switched active Muse {mode} account to {req.account_id} ({target_acc.get('label')})")

    return {
        "success": True,
        "message": f"Đã kích hoạt tài khoản {target_acc.get('label')} cho chế độ {mode}",
        "mode": mode,
        "active_account_id": req.account_id,
        "accounts": get_enriched_accounts(),
        "active_image_account": get_active_account_id("image"),
        "active_video_account": get_active_account_id("video"),
    }

@router.post("/accounts/add")
async def add_or_update_muse_account(req: AccountCreateUpdateRequest):
    """Thêm mới hoặc cập nhật cấu hình tài khoản Fleet (mỗi tài khoản chỉ 1 loại: image hoặc video)."""
    require_safe_id(req.account_id, "account_id")
    if req.account_id in LEGACY_ALIAS_ACCOUNTS:
        raise HTTPException(status_code=400, detail="ID trạm VM cũ không còn dùng được")
    if req.profile_dir is not None:
        # Profile Chrome chỉ được nằm trong backend/chrome_profiles
        p_dir = Path(req.profile_dir)
        resolved = p_dir if p_dir.is_absolute() else BACKEND_DIR / p_dir
        if not is_within(resolved, CHROME_PROFILES_DIR) or resolved.resolve() == CHROME_PROFILES_DIR.resolve():
            raise HTTPException(status_code=400, detail="profile_dir must be inside backend/chrome_profiles")
    kind = account_kind({"capabilities": req.capabilities})
    if kind is None:
        raise HTTPException(
            status_code=400,
            detail="capabilities phải là của tài khoản ảnh (text-to-image) HOẶC tài khoản video (image-to-video/text-to-video), không trộn lẫn",
        )

    acc = find_account(req.account_id)
    if acc is None:
        acc = {
            "account_id": req.account_id,
            "profile_dir": f"chrome_profiles/{req.account_id}",
            "is_active_for_image": False,
            "is_active_for_video": False,
            "status": "offline",
        }
        muse_accounts.append(acc)
    acc["label"] = req.label
    acc["type"] = kind
    acc["capabilities"] = list(req.capabilities)
    if req.profile_dir is not None:
        acc["profile_dir"] = req.profile_dir
    active_flag = req.is_active_for_image if kind == "image" else req.is_active_for_video
    if active_flag:
        active_key = "is_active_for_image" if kind == "image" else "is_active_for_video"
        for a in muse_accounts:
            if account_kind(a) == kind:
                a[active_key] = a["account_id"] == req.account_id

    save_muse_accounts(muse_accounts)
    return {
        "success": True,
        "accounts": get_enriched_accounts(),
        "active_image_account": get_active_account_id("image"),
        "active_video_account": get_active_account_id("video"),
    }

def _touch_worker(worker_id: Optional[str], account_id: Optional[str], hardware: Optional[Dict[str, Any]] = None) -> None:
    now = time.time()
    if worker_id:
        current_worker["worker_id"] = worker_id
    current_worker["last_heartbeat"] = now
    current_worker["status"] = "online"
    if hardware:
        current_worker["hardware"] = dict(hardware)
    if account_id:
        w = account_workers.setdefault(account_id, {"account_id": account_id})
        w["worker_id"] = worker_id or w.get("worker_id")
        w["last_heartbeat"] = now
        if hardware:
            w["hardware"] = dict(hardware)

@router.post("/workers/register")
async def register_worker(req: WorkerRegisterRequest):
    """Fleet Runner đăng ký từng tài khoản đã đăng nhập."""
    if req.hostname:
        current_worker["hostname"] = req.hostname
    if req.os_info:
        current_worker["os_info"] = req.os_info
    if req.capabilities:
        current_worker["capabilities"] = req.capabilities
    _touch_worker(req.worker_id, req.account_id, req.hardware)
    if req.account_id:
        account_workers[req.account_id]["capabilities"] = req.capabilities or []
        if not find_account(req.account_id):
            logger.warning(f"Worker {req.worker_id} đăng ký tài khoản lạ '{req.account_id}' (không có trong muse_fleet_accounts.json)")
    logger.debug(f"Worker {req.worker_id} registered for account {req.account_id}")
    return {
        "success": True,
        "message": f"Worker {req.worker_id} registered successfully",
        "account_id": req.account_id,
        "poll_interval_sec": 3,
        "heartbeat_interval_sec": 15,
    }

@router.post("/workers/heartbeat")
async def worker_heartbeat(req: WorkerHeartbeatRequest):
    """Fleet Runner gửi nhịp tim định kỳ cho từng tài khoản."""
    _touch_worker(req.worker_id, req.account_id, req.hardware)
    return {"success": True, "server_time": int(time.time()), "account_id": req.account_id}

def _pick_task_for_account(account_id: str, kind: str) -> int:
    """Chọn task trong hàng đợi cho tài khoản: đúng loại, ưu tiên task gán cho chính nó."""
    now = time.time()
    fallback_idx = -1
    for idx, t in enumerate(pending_tasks):
        if routing_kind(t) != kind:
            continue  # Rào chắn tuyệt đối: tài khoản ảnh không nhận video và ngược lại
        if account_id in (t.get("avoid_accounts") or []):
            continue  # tài khoản vừa lỗi với việc này (vd Muse quá tải): không nhận lại, kể cả nhận thay
        assigned = t.get("assigned_account")
        if assigned == account_id:
            return idx
        if fallback_idx != -1 or t.get("pin_account"):
            continue  # task ghim: side chat thuộc tài khoản đã gán, không tài khoản nào nhận thay
        if not assigned or assigned in LEGACY_ALIAS_ACCOUNTS:
            fallback_idx = idx
            continue
        other = find_account(assigned)
        waited = now - t.get("queued_at", t.get("created_at", now))
        # Nhận thay khi tài khoản được gán không dùng được, offline, hoặc task đã chờ quá lâu
        if (account_kind(other) != kind or not is_account_available(other)
                or not is_account_online(assigned) or waited > REASSIGN_AFTER_SEC):
            fallback_idx = idx
    return fallback_idx

@router.get("/tasks/poll")
async def poll_task(
    worker_id: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    timeout: int = Query(15),
):
    """
    Fleet Runner long-poll lấy task cho 1 tài khoản cụ thể.
    Chỉ trả task cùng loại với tài khoản (image/video). Hàng đợi trống thì giữ kết nối tối đa `timeout` giây.
    """
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")
    acc = find_account(account_id)
    kind = account_kind(acc)
    _touch_worker(worker_id, account_id)
    if acc is None or kind is None:
        logger.warning(f"Poll từ tài khoản không hợp lệ '{account_id}' (không có trong cấu hình hoặc không rõ loại)")
        return {"task": None}
    if is_account_blocked(acc):
        return {"task": None, "blocked_until": acc.get("blocked_until"), "block_reason": acc.get("block_reason")}

    timeout = max(1, min(int(timeout), 30))
    start_wait = time.time()
    while time.time() - start_wait < timeout:
        chosen_idx = _pick_task_for_account(account_id, kind)
        if chosen_idx != -1:
            task = pending_tasks.pop(chosen_idx)
            if task.get("assigned_account") != account_id:
                logger.info(f"Task {task['task_id']} ({kind}) chuyển từ {task.get('assigned_account')} sang {account_id}")
            _set_task_account(task, acc)
            task_id = task["task_id"]
            task["status"] = "processing"
            task["started_at"] = time.time()
            active_tasks[task_id] = task
            current_worker["active_task_id"] = task_id
            logger.info(f"Assigned task {task_id} ({kind}) to account {account_id} (worker {worker_id})")
            return {"task": task}
        await asyncio.sleep(0.5)

    return {"task": None}

@router.post("/tasks/create")
async def create_task(req: TaskCreateRequest):
    """API cho Story Studio Web UI hoặc các router khác tạo tác vụ Muse."""
    task_id = f"task_m_{uuid.uuid4().hex[:8]}"

    if req.project_id is not None:
        require_safe_id(req.project_id, "project_id")
    if req.scene_id is not None:
        require_safe_id(req.scene_id, "scene_id")
    if req.output_path:
        out_p = Path(req.output_path)
        if out_p.suffix.lower() not in MEDIA_EXTS or not is_within(out_p, MUSE_OUTPUTS_DIR, PROJECTS_DIR):
            raise HTTPException(status_code=400, detail="output_path must be a media file inside the projects or muse_outputs folder")
    req.profile_dir = None  # profile luôn lấy từ cấu hình tài khoản (assign_task_account)

    mode = req.mode or "text-to-image"
    is_video = "video" in mode.lower()

    ref_img = req.reference_image or req.reference_image_url or req.reference_image_path
    ref_url = req.reference_image_url or (str(ref_img) if ref_img and (str(ref_img).startswith("http") or str(ref_img).startswith("/")) else None)
    ref_path = req.reference_image_path or (str(ref_img) if ref_img and not str(ref_img).startswith("http") else None)
    if ref_path and not ref_url and is_within(ref_path, PROJECTS_DIR, STATIC_DIR) and Path(ref_path).exists():
        ref_url = f"/api/muse-bridge/reference-file?path={urllib.parse.quote(str(Path(ref_path).resolve()))}"

    params = dict(req.parameters or {})

    # Phân tách rõ ràng payload cho Image vs Video
    if is_video:
        mode = "image-to-video" if (req.input_image_url or ref_img or params.get("input_image_url")) else mode
        camera_motion = req.camera_motion or params.get("camera_motion") or "cinematic slow tracking pan, smooth camera motion"
        duration = req.duration or params.get("duration") or params.get("duration_sec") or 5
        input_img = req.input_image_url or ref_url or ref_path or params.get("input_image_url")
        action_prompt = req.action_prompt or req.prompt

        params.setdefault("camera_motion", camera_motion)
        params.setdefault("duration", duration)
        params.setdefault("duration_sec", duration)
        params.setdefault("action_cues", action_prompt)
        params.setdefault("fps", 24)
        if input_img:
            params.setdefault("input_image_url", str(input_img))

        task = {
            "task_id": task_id,
            "mode": mode,
            "prompt": req.prompt,
            "action_prompt": action_prompt,
            "negative_prompt": req.negative_prompt,
            "project_id": req.project_id,
            "scene_id": req.scene_id,
            "output_path": req.output_path,
            "parameters": params,
            "input_image_url": str(input_img) if input_img else None,
            "camera_motion": camera_motion,
            "duration": duration,
            "assigned_account": req.assigned_account,
            "profile_dir": req.profile_dir,
            "timeout_sec": req.timeout_sec or 180,
            "status": "pending",
            "created_at": time.time(),
        }
    else:
        mode = "text-to-image"
        aspect_ratio = req.aspect_ratio or params.get("aspect_ratio") or "16:9"
        char_anchor = req.character_anchor or params.get("character_anchor") or ""
        params.setdefault("aspect_ratio", aspect_ratio)
        params.setdefault("resolution", "2K")
        if char_anchor:
            params.setdefault("character_anchor", char_anchor)

        task = {
            "task_id": task_id,
            "mode": mode,
            "prompt": req.prompt,
            "negative_prompt": req.negative_prompt,
            "project_id": req.project_id,
            "scene_id": req.scene_id,
            "output_path": req.output_path,
            "parameters": params,
            "reference_image": ref_img,
            "reference_image_url": ref_url,
            "reference_image_path": ref_path,
            "character_anchor": char_anchor,
            "aspect_ratio": aspect_ratio,
            "assigned_account": req.assigned_account,
            "profile_dir": req.profile_dir,
            "timeout_sec": req.timeout_sec or 180,
            "status": "pending",
            "created_at": time.time(),
        }
        # Nút "Muse 2K" của thẻ cảnh: cảnh thuộc bối cảnh đã duyệt thì thêm mô tả cố định và ảnh chuẩn
        if req.project_id and req.scene_id:
            try:
                lock = await asyncio.to_thread(location_sheets.scene_lock, req.project_id, req.scene_id, req.prompt)
            except ValueError as e:   # locations.json hỏng: báo rõ, không âm thầm vẽ thiếu khoá
                raise HTTPException(status_code=409, detail=f"Không đọc được danh sách bối cảnh của dự án: {e}") from None
            location_sheets.apply_lock_to_image_task(task, lock)

    ensure_local_fleet_runner()
    enqueue_task(task)
    logger.info(f"Created task {task_id} for mode {mode} (Account: {task.get('assigned_account')}, Ref: {bool(ref_img)})")
    return {"success": True, "task_id": task_id, "task": task}

@router.post("/tasks/{task_id}/progress")
async def update_task_progress(task_id: str, req: TaskProgressRequest):
    """Worker cập nhật tiến độ xử lý tác vụ."""
    require_safe_id(task_id, "task_id")
    if task_id in active_tasks:
        active_tasks[task_id]["progress_percent"] = req.progress_percent
        active_tasks[task_id]["stage"] = req.stage
        active_tasks[task_id]["status_message"] = req.status_message
        active_tasks[task_id]["elapsed_seconds"] = req.elapsed_seconds
    return {"success": True}

def detect_media_kind(data: bytes) -> Optional[str]:
    """Nhận diện loại media từ magic bytes: 'image' (JPEG/PNG/WebP/GIF), 'video' (MP4/MOV/WebM) hoặc None."""
    head = data[:16]
    if head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG\r\n\x1a\n") or head[:6] in (b"GIF87a", b"GIF89a"):
        return "image"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image"
    if head[4:8] == b"ftyp" or head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video"
    return None


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    request: Request,
    file: Optional[UploadFile] = File(None),
    metadata: Optional[str] = Form(None),
    extras: List[UploadFile] = File(default=[]),
):
    """
    Worker upload kết quả media sau khi hoàn thành.
    Hỗ trợ multipart file upload hoặc JSON payload chứa base64.
    Media phải đúng loại của task (ảnh cho task ảnh, video cho task video), nếu không sẽ bị từ chối (422).
    """
    require_safe_id(task_id, "task_id")
    task = active_tasks.get(task_id)
    if not task:
        task = next((p for p in pending_tasks if p["task_id"] == task_id), None)
    if not task:
        # Kết quả về muộn cho task đã bị đánh dấu timeout vẫn được nhận (chỉ lưu vào bộ sưu tập)
        task = next((h for h in task_history if h.get("task_id") == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    parsed_meta = {}
    if metadata:
        try:
            parsed_meta = json.loads(metadata)
        except Exception:
            pass

    kind = task_kind(task.get("mode"))
    ext = ".mp4" if kind == "video" else ".jpg"
    abandoned = bool(task.get("abandoned"))

    # Đọc dữ liệu nhị phân (giới hạn dung lượng) trước khi ghi đĩa
    raw_bytes = None
    if file:
        raw_bytes = await read_upload_limited(file)
    else:
        # Kiểm tra JSON body nếu gửi qua raw JSON
        try:
            body = await request.json()
            b64_data = body.get("b64_data") if isinstance(body, dict) else None
            if b64_data:
                if len(b64_data) > MAX_UPLOAD_BYTES * 4 // 3 + 4:
                    raise HTTPException(status_code=413, detail="Payload too large")
                raw_bytes = base64.b64decode(b64_data)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed parsing body for task {task_id}: {e}")

    if not raw_bytes:
        raise HTTPException(status_code=422, detail="Không có dữ liệu media")
    media_kind = detect_media_kind(raw_bytes)
    if media_kind != kind:
        logger.error(f"Task {task_id} ({kind}) nhận media sai loại ({media_kind or 'không rõ'}) từ {parsed_meta.get('account_id')}")
        raise HTTPException(status_code=422, detail=f"Media sai loại: task {kind} nhưng nhận được {media_kind or 'dữ liệu không rõ'}")

    # Ưu tiên project/scene của task do server tạo; metadata của worker chỉ dùng khi task không có
    project_id = task.get("project_id") or parsed_meta.get("project_id")
    scene_id = task.get("scene_id") or parsed_meta.get("scene_id")
    target_output_path = task.get("output_path")

    # Xác định đường dẫn file lưu trữ an toàn trong sandbox
    final_file_path = None
    if abandoned:
        project_id = scene_id = None  # người gọi đã fallback sang engine khác, không ghi đè dự án
        logger.warning(f"Task {task_id} về muộn sau khi đã timeout: chỉ lưu vào bộ sưu tập muse_outputs")
    elif project_id and scene_id and is_safe_id(str(project_id)) and is_safe_id(str(scene_id)):
        # Clip video lưu file riêng ({scene}_muse.mp4): videos/{scene}.mp4 là đoạn dựng, bị ghi lại mỗi lần render
        if kind == "video":
            target_path = (PROJECTS_DIR / str(project_id) / "videos" / f"{scene_id}_muse{ext}").resolve()
        else:
            target_path = (PROJECTS_DIR / str(project_id) / "images" / f"{scene_id}{ext}").resolve()
        if is_within(target_path, PROJECTS_DIR):
            final_file_path = target_path
    elif target_output_path:
        p_cand = Path(target_output_path).resolve()
        if p_cand.suffix.lower() in MEDIA_EXTS and is_within(p_cand, MUSE_OUTPUTS_DIR, PROJECTS_DIR):
            final_file_path = p_cand
        else:
            logger.warning(f"Blocked unauthorized output_path in muse complete: {target_output_path}")
    if final_file_path is None:
        final_file_path = (MUSE_OUTPUTS_DIR / f"{task_id}{ext}").resolve()

    # Chỉ gỡ task khỏi hàng đợi sau khi payload hợp lệ
    active_tasks.pop(task_id, None)
    for idx, p in enumerate(pending_tasks):
        if p["task_id"] == task_id:
            pending_tasks.pop(idx)
            break

    final_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(final_file_path, "wb") as f:
        f.write(raw_bytes)

    # Cập nhật thống kê token và task
    estimated_tokens = parsed_meta.get("estimated_tokens_used", 60000 if kind == "video" else 15000)
    stats["tokens_used"] += estimated_tokens
    stats["completed_count"] += 1

    task["status"] = "completed"
    task["completed_at"] = time.time()
    task["output_path"] = str(final_file_path)
    task["image_path"] = str(final_file_path)
    task["provider"] = "meta_muse_cloud"
    task["success"] = True
    task["executed_by"] = parsed_meta.get("account_id") or task.get("assigned_account")
    # Side chat: địa chỉ chat để lần sau mở lại, và chữ Muse trả lời (tự kiểm, báo lỗi) — chỉ nhận đúng dạng
    if valid_thread_url(parsed_meta.get("thread_url")):
        task["thread_url"] = parsed_meta["thread_url"]
    is_agent = task.get("mode") == AGENT_VIDEO_MODE
    if isinstance(parsed_meta.get("muse_reply"), str):
        task["muse_reply"] = parsed_meta["muse_reply"][-(AGENT_REPLY_MAX_CHARS if is_agent else MUSE_REPLY_MAX_CHARS):]
    if is_agent:
        counts = parsed_meta.get("media_count")
        if isinstance(counts, dict) and counts and all(isinstance(v, int) for v in counts.values()):
            task["media_count"] = {str(k)[:20]: int(v) for k, v in counts.items()}
        warns = parsed_meta.get("warnings")
        if isinstance(warns, list) and all(isinstance(w, str) for w in warns):
            task["warnings"] = [w[:300] for w in warns[:AGENT_MAX_WARNINGS]]
        task["extra_images"] = await _save_extra_images(task_id, extras)

    # Web URL
    has_proj = bool(project_id and project_id != "None" and is_safe_id(str(project_id))
                    and (PROJECTS_DIR / str(project_id)).exists())
    if has_proj and is_within(final_file_path, PROJECTS_DIR / str(project_id)):
        rel_media = "videos" if kind == "video" else "images"
        task["media_url"] = f"/api/projects/{project_id}/media/{rel_media}/{final_file_path.name}"
        # Luôn sao 1 bản sang MUSE_OUTPUTS_DIR (đặt tên theo task_id để không đè nhau) cho Gallery
        try:
            shutil.copy2(final_file_path, MUSE_OUTPUTS_DIR / f"{task_id}{ext}")
        except Exception:
            pass
    elif not is_within(final_file_path, MUSE_OUTPUTS_DIR):
        copy_dest = MUSE_OUTPUTS_DIR / f"{task_id}{ext}"
        try:
            shutil.copy2(final_file_path, copy_dest)
        except Exception:
            pass
        task["media_url"] = f"/static/muse_outputs/{copy_dest.name}"
    else:
        task["media_url"] = f"/static/muse_outputs/{final_file_path.name}"

    task["download_url"] = f"/api/muse-bridge/download/{task_id}"

    # Tự cập nhật scene trong project.json nếu task gắn với project/scene
    if project_id and scene_id:
        try:
            from services.project_service import get_project, update_project
            from models.schemas import ProjectUpdateRequest
            proj = get_project(project_id)
            if proj:
                for sc in proj.scenes:
                    if sc.id == scene_id:
                        if kind == "video":
                            sc.motion_video_path = str(final_file_path)
                            sc.video_url = task["media_url"]
                            sc.video_segment_url = task["media_url"]  # để xem trước ngay; render sẽ ghi lại
                            sc.media_view_mode = "video"
                            sc.status_video = "ready"
                            sc.status = "ready" if sc.voice_audio_path else "imaged"
                        else:
                            sc.image_path = str(final_file_path)
                            sc.image_url = task["media_url"]
                            sc.status = "ready" if sc.voice_audio_path else "imaged"
                        break
                update_project(project_id, ProjectUpdateRequest(scenes=proj.scenes))
                logger.info(f"Updated scene {scene_id} in project {project_id} with Muse {kind} output.")
        except Exception as p_err:
            logger.warning(f"Failed to auto-update project {project_id} scene {scene_id}: {p_err}")

    task_history[:] = [t for t in task_history if t is not task]
    task_history.insert(0, task)
    if len(task_history) > 100:
        task_history.pop()

    if current_worker.get("active_task_id") == task_id:
        current_worker["active_task_id"] = None

    # Báo cho caller async đang chờ (nếu có)
    waiter = task_waiters.get(task_id)
    if waiter:
        waiter.set()

    logger.info(f"Task {task_id} ({kind}) completed by {task['executed_by']}. Saved to {final_file_path}")
    return {
        "success": True,
        "task_id": task_id,
        "output_path": str(final_file_path),
        "media_url": task.get("media_url"),
        "abandoned": abandoned,
    }

async def _save_extra_images(task_id: str, extras: List[UploadFile]) -> List[str]:
    """Ảnh phụ của việc nhiều bước (vd ảnh cảnh Muse đã sửa tóc): tối đa AGENT_MAX_EXTRAS ảnh, chỉ nhận đúng ảnh,
    lưu vào muse_outputs theo task_id. Người gọi (dịch vụ video cao trào) tự chọn ảnh nào dùng."""
    saved: List[str] = []
    for upload in extras or []:
        if len(saved) >= AGENT_MAX_EXTRAS:
            break
        data = await read_upload_limited(upload)
        if detect_media_kind(data) != "image":
            logger.warning(f"Task {task_id}: bỏ ảnh phụ {upload.filename!r} (không phải ảnh)")
            continue
        dest = (MUSE_OUTPUTS_DIR / f"{task_id}_extra_{len(saved) + 1}.jpg").resolve()
        await asyncio.to_thread(dest.write_bytes, data)
        saved.append(str(dest))
    return saved

@router.post("/tasks/{task_id}/fail")
async def fail_task(task_id: str, req: TaskFailRequest):
    """
    Worker báo task lỗi.
    - Hết quota / chặn vùng / mất phiên đăng nhập: khóa tài khoản 15 phút, chuyển active sang tài khoản khác cùng loại.
    - Còn lượt retry: đưa lại hàng đợi, ưu tiên tài khoản khác CÙNG LOẠI (không bao giờ chéo ảnh/video).
    """
    require_safe_id(task_id, "task_id")
    task = active_tasks.pop(task_id, None)
    if not task:
        for idx, p in enumerate(pending_tasks):
            if p["task_id"] == task_id:
                task = pending_tasks.pop(idx)
                break
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    kind = routing_kind(task)
    err_str = str(req.error).lower()
    failed_acc = task.get("assigned_account")
    if failed_acc and any(kw in err_str for kw in SESSION_ERROR_KEYWORDS):
        block_account(failed_acc, f"Mất phiên đăng nhập: {req.error}")
    elif failed_acc and any(kw in err_str for kw in QUOTA_ERROR_KEYWORDS):
        block_account(failed_acc, f"Hết quota / bị chặn: {req.error}")

    if current_worker.get("active_task_id") == task_id:
        current_worker["active_task_id"] = None

    retry_count = int(task.get("retry_count", 0))
    # Task ghim vào side chat của một tài khoản: không thử lại ở đây (tài khoản khác không mở được chat đó);
    # người gọi tự quyết mở chat mới trên tài khoản khác.
    # Việc giao nhiều bước (agent-video) không tự thử lại: mỗi lần Muse làm tốn tới 6 video (chạy thật 28/10/2026)
    if (retry_count < MAX_TASK_RETRIES and not task.get("abandoned") and not task.get("pin_account")
            and task.get("mode") != AGENT_VIDEO_MODE):
        nxt = pick_fallback_account(kind, exclude=failed_acc, avoid=task.get("avoid_accounts")) or (
            find_account(failed_acc) if is_account_available(find_account(failed_acc)) else None
        )
        if nxt:
            task["retry_count"] = retry_count + 1
            task["last_error"] = req.error
            task["error"] = None
            task["status"] = "pending"
            task["queued_at"] = time.time()
            _set_task_account(task, nxt)
            pending_tasks.append(task)
            logger.info(f"[AUTO-RETRY] Task {task_id} ({kind}) thử lại lần {task['retry_count']}/{MAX_TASK_RETRIES} trên {nxt['account_id']}")
            return {
                "success": True,
                "auto_failover": nxt["account_id"] != failed_acc,
                "switched_to": nxt["account_id"],
                "retry_count": task["retry_count"],
                "message": f"Task {task_id} được thử lại trên tài khoản {nxt['account_id']}",
            }

    task["status"] = "failed"
    task["error"] = req.error
    task["failed_at"] = time.time()
    task_history.insert(0, task)
    stats["failed_count"] += 1

    waiter = task_waiters.get(task_id)
    if waiter:
        waiter.set()

    logger.error(f"Task {task_id} ({kind}) failed on {failed_acc}: {req.error}")
    return {"success": True, "auto_failover": False}

@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Tra cứu trạng thái của 1 task cụ thể."""
    if task_id in active_tasks:
        return {"task": active_tasks[task_id]}
    for t in pending_tasks:
        if t["task_id"] == task_id:
            return {"task": t}
    for t in task_history:
        if t["task_id"] == task_id:
            return {"task": t}
    raise HTTPException(status_code=404, detail="Task not found")

def _is_servable_media(path: Path) -> bool:
    return (
        path.is_file()
        and path.suffix.lower() in MEDIA_EXTS
        and is_within(path, MUSE_OUTPUTS_DIR, PROJECTS_DIR)
    )

@router.get("/download/{task_id}")
async def download_task_media(task_id: str):
    """Download the media file generated for a task with original filename and Content-Disposition."""
    require_safe_id(task_id, "task_id")
    target_path = None
    # 1. Search in task_history
    for t in task_history:
        if t.get("task_id") == task_id:
            out_p = t.get("output_path") or t.get("image_path")
            if out_p and _is_servable_media(Path(out_p)):
                target_path = Path(out_p)
                break

    # 2. Search in MUSE_OUTPUTS_DIR
    if not target_path:
        for cand in MUSE_OUTPUTS_DIR.glob(f"{task_id}*"):
            if _is_servable_media(cand):
                target_path = cand
                break

    # 3. Search in projects directory if task has project_id and scene_id
    if not target_path:
        for cand in PROJECTS_DIR.glob(f"**/*{task_id}*"):
            if _is_servable_media(cand):
                target_path = cand
                break

    if not target_path or not target_path.exists():
        raise HTTPException(status_code=404, detail="File media không tồn tại")

    ext = target_path.suffix.lower()
    mime = "video/mp4" if ext == ".mp4" else "image/jpeg"
    return FileResponse(
        path=str(target_path),
        filename=target_path.name,
        media_type=mime,
    )

@router.get("/reference-file")
async def get_reference_file(path: str = Query(...)):
    """Phục vụ file ảnh tham chiếu (character reference image) an toàn cho Muse VM Worker tải về."""
    clean_path = urllib.parse.unquote(path)
    target = Path(clean_path).resolve()
    allowed_roots = [PROJECTS_DIR.resolve(), STATIC_DIR.resolve()]
    if not any(target.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Access denied: outside allowed workspace directories")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Reference image file not found")
    mime = "image/png" if target.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(target), media_type=mime)

@router.delete("/gallery/clear-all")
async def clear_all_gallery():
    """Dọn sạch toàn bộ file media rác trong thư mục muse_outputs và lịch sử task."""
    global task_history
    cleared_count = 0
    for f in list(MUSE_OUTPUTS_DIR.iterdir()):
        if f.is_file():
            try:
                f.unlink(missing_ok=True)
                cleared_count += 1
            except Exception as e:
                logger.warning(f"Could not delete {f}: {e}")

    task_history.clear()
    return {
        "success": True,
        "cleared_count": cleared_count,
        "message": f"Đã dọn sạch {cleared_count} tệp media trong bộ sưu tập.",
    }

@router.delete("/gallery/{task_id}")
async def delete_gallery_item(task_id: str):
    """Xóa một sản phẩm ảnh/video khỏi bộ sưu tập và dọn dẹp file trên đĩa."""
    require_safe_id(task_id, "task_id")
    deleted_files = 0
    # 1. Delete from MUSE_OUTPUTS_DIR
    for cand in list(MUSE_OUTPUTS_DIR.glob(f"{task_id}*")):
        if cand.is_file() and is_within(cand, MUSE_OUTPUTS_DIR):
            try:
                cand.unlink(missing_ok=True)
                deleted_files += 1
            except Exception as e:
                logger.warning(f"Could not delete {cand}: {e}")

    # 2. Delete matching tasks from task_history
    global task_history
    orig_len = len(task_history)
    task_history = [t for t in task_history if t.get("task_id") != task_id]

    return {
        "success": True,
        "deleted_task_id": task_id,
        "deleted_files_count": deleted_files,
        "removed_from_history": orig_len - len(task_history),
    }
