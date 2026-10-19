"""
Client LLM cho luồng chuyển thể vụ án: một lời gọi nhỏ tới 9router (OpenAI-compatible), trả về JSON đã parse.

- Luôn gửi "stream": False. Thiếu cờ này 9router trả 200 với thân dạng stream (không phải JSON).
- Giá trị cấu hình đọc ở thời điểm gọi từ module `config` để test có thể monkeypatch.
- Lỗi được gom về LLMError(kind, user_message): `user_message` là tiếng Việt, hiển thị thẳng cho người dùng.
  `kind` thuộc {"auth", "no_credentials", "timeout", "network", "http", "invalid_json", "busy"};
  RETRYABLE_KINDS là các loại đáng thử lại, mỗi lần thử tính một lượt (lỗi tạm thời hoặc model trả JSON hỏng).
- HTTP 429/502/503/504 là "busy" (BUSY_KIND): 9router đang bận hoặc tài khoản Gemini đang bị giới hạn một lúc.
  Người gọi chờ rồi gọi lại, không tính lượt thử. `retry_after_s` là số giây nên chờ, lấy từ header Retry-After
  hoặc câu "reset after 2m" trong thân lỗi; không có thì None.
- Không bao giờ ghi log hay đưa API key vào thông báo lỗi.
"""
import json
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable, Optional

import httpx

import config

logger = logging.getLogger(__name__)

RETRYABLE_KINDS = {"timeout", "network", "invalid_json"}
BUSY_KIND = "busy"
BUSY_STATUSES = {429, 502, 503, 504}

# Chữ ký chung của hàm gọi LLM; worker nhận nó để test thay bằng LLM giả cùng chữ ký.
LLMCall = Callable[..., Awaitable[Any]]

_NO_CREDENTIALS_MARKER = "No active credentials"
_ERROR_BODY_PREVIEW = 200
_FENCE_START = re.compile(r"^```[A-Za-z0-9_-]*[ \t]*\r?\n?")
_FENCE_END = re.compile(r"\r?\n?```\s*$")
# "reset after 2m", "reset after 1m30s", "retry in 2 minutes": thời gian 9router (hoặc Gemini) báo phải chờ.
_UNIT = r"(ms|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)(?![a-z])"
_WAIT_HINT = re.compile(r"(?:reset|retry)\s*(?:after|in)\s*:?\s*((?:\d+(?:\.\d+)?\s*" + _UNIT + r"\s*)+)", re.I)
_WAIT_PART = re.compile(r"(\d+(?:\.\d+)?)\s*" + _UNIT, re.I)
_UNIT_SECONDS = {"ms": 0.001, "h": 3600.0, "m": 60.0, "s": 1.0}


class LLMError(Exception):
    def __init__(self, kind: str, user_message: str, *, retry_after_s: Optional[float] = None):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message
        self.retry_after_s = retry_after_s   # số giây nên chờ trước khi gọi lại (chỉ lỗi "busy" mới có)


def _redact(text: str, api_key: str) -> str:
    """Phòng khi máy chủ lặp lại header Authorization trong thân lỗi."""
    return text.replace(api_key, "***") if api_key else text


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = _FENCE_START.sub("", text, count=1)
        text = _FENCE_END.sub("", text, count=1)
    return text.strip()


def _bracket_spans(text: str) -> list[str]:
    """Các khối {…} và […] (từ ký tự mở đầu tiên đến ký tự đóng cuối cùng), khối dài hơn đứng trước."""
    spans = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            spans.append(text[start : end + 1])
    return sorted(spans, key=len, reverse=True)


def _parse_json_content(content: Any) -> Any:
    """Bóc fence rồi json.loads; lỗi thì thử khối {…} / […] lớn nhất. Không parse được thì raise ValueError."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("nội dung rỗng")
    cleaned = _strip_fence(content)
    try:
        return json.loads(cleaned)
    except ValueError:
        pass
    for span in _bracket_spans(cleaned):
        try:
            return json.loads(span)
        except ValueError:
            continue
    raise ValueError("không có JSON hợp lệ")


def _hint_seconds(text: str) -> Optional[float]:
    """Số giây trong câu "reset after 1m30s" / "retry in 2 minutes" của thân lỗi; không có thì None."""
    match = _WAIT_HINT.search(text or "")
    if not match:
        return None
    total = 0.0
    for number, unit in _WAIT_PART.findall(match.group(1)):
        unit = unit.lower()
        total += float(number) * _UNIT_SECONDS["ms" if unit == "ms" else unit[0]]
    return total


def _retry_after_seconds(header: Optional[str], text: str) -> Optional[float]:
    """Header Retry-After (số giây hoặc ngày giờ HTTP) nếu đọc được, không thì gợi ý trong thân lỗi."""
    value = (header or "").strip()
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            pass
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, IndexError):
            pass
    return _hint_seconds(text)


def _http_error(status: int, text: str, api_key: str, retry_after: Optional[str] = None) -> LLMError:
    if _NO_CREDENTIALS_MARKER in text:
        return LLMError(
            "no_credentials",
            "9router chưa có tài khoản Gemini đang hoạt động. "
            "Mở 9router, kết nối Gemini (provider antigravity) rồi chạy lại.",
        )
    if status == 401:
        return LLMError(
            "auth",
            "9router từ chối API key (401). Kiểm tra NINEROUTER_API_KEY trong file .env "
            "rồi khởi động lại ứng dụng.",
        )
    preview = _redact(text.strip(), api_key)[:_ERROR_BODY_PREVIEW]
    if status in BUSY_STATUSES:
        detail = f"HTTP {status}: {preview}" if preview else f"HTTP {status}"
        return LLMError(
            BUSY_KIND,
            f"9router đang bận hoặc tạm thời không dùng được ({detail}).",
            retry_after_s=_retry_after_seconds(retry_after, text),
        )
    return LLMError("http", f"9router trả lỗi HTTP {status}: {preview}" if preview else f"9router trả lỗi HTTP {status}.")


async def call_llm_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.4,
    timeout: float = 240.0,
    client: Optional[httpx.AsyncClient] = None,
) -> Any:
    """Gọi 9router một lần, trả về JSON (dict/list) model sinh ra. Mọi lỗi đều là LLMError."""
    api_key = (config.NINEROUTER_API_KEY or "").strip()
    base_url = (config.NINEROUTER_BASE_URL or "").strip()
    if not api_key:
        raise LLMError("auth", "Chưa cấu hình NINEROUTER_API_KEY trong file .env. Thêm key của 9router rồi khởi động lại ứng dụng.")
    if not base_url:
        raise LLMError("auth", "Chưa cấu hình NINEROUTER_BASE_URL trong file .env (ví dụ http://127.0.0.1:20128/v1).")

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": config.NINEROUTER_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "temperature": temperature,
    }

    own_client = client is None
    http = httpx.AsyncClient(timeout=timeout) if own_client else client
    try:
        response = await http.post(endpoint, headers=headers, json=payload, timeout=timeout)
    except httpx.TimeoutException:
        raise LLMError(
            "timeout",
            f"9router không trả lời trong {timeout:g} giây. Kiểm tra 9router còn chạy và model Gemini sẵn sàng, rồi thử lại.",
        ) from None
    except httpx.RequestError as exc:
        logger.warning("9router network error: %s", type(exc).__name__)
        raise LLMError(
            "network",
            f"Không kết nối được 9router tại {base_url}. Kiểm tra 9router đã chạy chưa và NINEROUTER_BASE_URL trong file .env.",
        ) from None
    finally:
        if own_client:
            await http.aclose()

    if response.status_code != 200:
        error = _http_error(response.status_code, response.text, api_key, response.headers.get("retry-after"))
        logger.warning("9router HTTP %s (%s)", response.status_code, error.kind)
        raise error

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError(
            "invalid_json",
            "9router trả về phản hồi không đúng định dạng chat completion (không có choices[0].message.content). Thử lại.",
        ) from None

    try:
        return _parse_json_content(content)
    except ValueError:
        logger.warning("Model trả nội dung không phải JSON (%d ký tự)", len(content) if isinstance(content, str) else 0)
        raise LLMError(
            "invalid_json",
            "Model trả về nội dung không phải JSON hợp lệ. Thử lại; nếu lặp lại, rút ngắn bài gốc hoặc đổi model.",
        ) from None
