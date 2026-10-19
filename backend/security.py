"""
Security helpers dùng chung cho toàn bộ backend.

- Kiểm tra ID (project_id, scene_id, case_id, task_id...) chỉ gồm [A-Za-z0-9_-].
- Kiểm tra đường dẫn nằm trong thư mục cho phép (chống path traversal).
- Sinh tên file upload an toàn (bỏ qua filename do client gửi lên).
- LocalAccessMiddleware: chỉ cho phép truy cập từ chính máy này (loopback, không qua proxy/tunnel),
  chặn request cross-site từ trang web lạ. Fleet Runner cũng chạy trên máy này nên gọi qua loopback.
"""
import os
import re
import uuid
from pathlib import Path
from typing import Iterable, Optional, Union
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

SAFE_ID_RE = re.compile(r"[A-Za-z0-9_\-]{1,64}")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

# Giới hạn dung lượng upload mặc định (MB), có thể đổi qua .env
MAX_UPLOAD_MB = int(os.getenv("STORY_STUDIO_MAX_UPLOAD_MB", "200"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def is_safe_id(value: object) -> bool:
    return isinstance(value, str) and SAFE_ID_RE.fullmatch(value) is not None


def require_safe_id(value: object, field: str = "id") -> str:
    if not is_safe_id(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value  # type: ignore[return-value]


PATH_ID_PARAMS = (
    "project_id", "scene_id", "session_id", "case_id", "task_id",
    "render_id", "voice_id", "char_id", "account_id",
)


async def validate_path_ids(request: Request) -> None:
    """Router dependency: mọi path param dạng *_id phải là ID an toàn."""
    for key in PATH_ID_PARAMS:
        if key in request.path_params:
            require_safe_id(request.path_params[key], key)


def is_within(path: Union[str, Path], *bases: Path) -> bool:
    """True nếu path (sau khi resolve) nằm bên trong một trong các thư mục gốc."""
    try:
        target = Path(path).resolve()
    except (OSError, ValueError):
        return False
    return any(target.is_relative_to(Path(b).resolve()) for b in bases)


def safe_upload_name(filename: Optional[str], allowed_exts: Iterable[str], prefix: str = "upload") -> str:
    """Tạo tên file mới bằng uuid, chỉ giữ phần mở rộng nằm trong whitelist."""
    allowed = {e.lower() for e in allowed_exts}
    ext = Path(filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'none'}")
    return f"{prefix}_{uuid.uuid4().hex[:12]}{ext}"


async def read_upload_limited(upload, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    """Đọc UploadFile theo từng khối, từ chối nếu vượt quá giới hạn dung lượng."""
    chunks = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"File too large (max {max_bytes // (1024 * 1024)} MB)")
        chunks.append(chunk)
    return b"".join(chunks)


# -------------------------------------------------------------
# Access control middleware
# -------------------------------------------------------------
LOOPBACK_IPS = {"127.0.0.1", "::1"}
PROXY_HEADERS = {
    "x-forwarded-for",
    "x-forwarded-host",
    "x-real-ip",
    "forwarded",
    "cf-connecting-ip",
    "true-client-ip",
}


def _split_env_list(name: str) -> set:
    return {v.strip().lower() for v in os.getenv(name, "").split(",") if v.strip()}


def _hostname(host_value: str) -> str:
    """Tách hostname khỏi giá trị Host header ('localhost:8000', '[::1]:8000')."""
    try:
        return (urlsplit(f"//{host_value}").hostname or "").lower()
    except ValueError:
        return ""


class LocalAccessMiddleware:
    """
    ASGI middleware (HTTP + WebSocket):
    - Request "tin cậy" = từ loopback, không mang header của proxy/tunnel, Host là localhost.
    - Request tin cậy nhưng đến từ trang web khác (Origin lạ / Sec-Fetch-Site: cross-site) bị chặn.
    - Request không tin cậy (máy khác, qua proxy/tunnel, Host lạ) bị chặn hoàn toàn.
    """

    def __init__(self, app):
        self.app = app
        self.allowed_hosts = {"localhost", "127.0.0.1", "::1"} | _split_env_list("STORY_STUDIO_ALLOWED_HOSTS")
        self.allowed_origins = _split_env_list("STORY_STUDIO_ALLOWED_ORIGINS")

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        client_ip = (scope.get("client") or ("", 0))[0]
        path = scope.get("path", "")
        method = scope.get("method", "GET")

        has_proxy_header = any(h in PROXY_HEADERS for h in headers)
        host_value = headers.get("host", "")
        trusted_local = (
            client_ip in LOOPBACK_IPS
            and not has_proxy_header
            and _hostname(host_value) in self.allowed_hosts
        )

        if trusted_local:
            if self._is_cross_site(headers, host_value, method, path, scope["type"]):
                return await self._deny(scope, receive, send, "Cross-site request blocked")
            return await self.app(scope, receive, send)

        return await self._deny(scope, receive, send, "Access restricted to this computer")

    def _is_cross_site(self, headers: dict, host_value: str, method: str, path: str, scope_type: str) -> bool:
        origin = headers.get("origin")
        if origin is not None:
            if origin.lower() in self.allowed_origins:
                return False
            parts = urlsplit(origin)
            if parts.scheme not in ("http", "https") or parts.netloc.lower() != host_value.lower():
                return True
        fetch_site = headers.get("sec-fetch-site", "")
        if fetch_site == "cross-site":
            # Cho phép người dùng mở trang chính từ link ngoài, không cho gọi API từ trang khác
            is_page_navigation = (
                scope_type == "http"
                and method == "GET"
                and headers.get("sec-fetch-mode") == "navigate"
                and not path.startswith("/api/")
            )
            return not is_page_navigation
        return False

    async def _deny(self, scope, receive, send, reason: str):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = ('{"detail":"%s"}' % reason).encode()
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
