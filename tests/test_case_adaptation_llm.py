"""
Client LLM qua 9router cho luồng chuyển thể vụ án: payload stream:false, bóc JSON từ nội dung model trả về,
và ánh xạ lỗi sang LLMError(kind, user_message) tiếng Việt cụ thể.
Dùng httpx.MockTransport, không gọi 9router thật; giá trị cấu hình được monkeypatch, không phụ thuộc .env.
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config
from services.case_adaptation_llm import RETRYABLE_KINDS, LLMError, call_llm_json

TEST_KEY = "sk-test-khong-phai-key-that"
TEST_BASE = "http://9router.test/v1"
TEST_MODEL = "ag/test-model"


@pytest.fixture(autouse=True)
def _fake_config(monkeypatch):
    monkeypatch.setattr(config, "NINEROUTER_API_KEY", TEST_KEY)
    monkeypatch.setattr(config, "NINEROUTER_BASE_URL", TEST_BASE)
    monkeypatch.setattr(config, "NINEROUTER_LLM_MODEL", TEST_MODEL)


def _completion(content) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _call(handler, **kwargs):
    """Chạy call_llm_json với MockTransport(handler); trả về kết quả hoặc raise như thật."""

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await call_llm_json("SYS", "USER", client=client, **kwargs)

    return asyncio.run(run())


def _reply(content):
    return lambda request: httpx.Response(200, json=_completion(content))


def _error_of(handler, **kwargs) -> LLMError:
    with pytest.raises(LLMError) as info:
        _call(handler, **kwargs)
    return info.value


def test_payload_has_stream_false():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_completion('{"ok": true}'))

    assert _call(handler, temperature=0.1) == {"ok": True}
    payload = seen["payload"]
    assert payload["stream"] is False
    assert payload["model"] == config.NINEROUTER_LLM_MODEL
    assert payload["temperature"] == 0.1
    assert payload["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]
    assert seen["url"] == f"{TEST_BASE}/chat/completions"
    assert seen["auth"] == f"Bearer {TEST_KEY}"


def test_base_url_trailing_slash_is_tolerated(monkeypatch):
    monkeypatch.setattr(config, "NINEROUTER_BASE_URL", TEST_BASE + "/")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_completion("[]"))

    assert _call(handler) == []
    assert seen["url"] == f"{TEST_BASE}/chat/completions"


def test_parses_fenced_json():
    assert _call(_reply('```json\n{"a": 1}\n```')) == {"a": 1}


def test_parses_json_with_extra_text():
    assert _call(_reply("Đây là kết quả:\n[1, 2]\nHết.")) == [1, 2]


def test_parses_object_when_text_has_small_list_around_it():
    assert _call(_reply('Kết quả [1]: {"a": [1, 2, 3], "b": "x"} xong')) == {"a": [1, 2, 3], "b": "x"}


def test_keeps_vietnamese_text_intact():
    assert _call(_reply('{"tên": "Nguyễn Văn Ánh"}')) == {"tên": "Nguyễn Văn Ánh"}


def test_invalid_json_raises():
    err = _error_of(_reply("Xin lỗi, tôi không thể trả lời bằng JSON."))
    assert err.kind == "invalid_json"
    assert err.kind in RETRYABLE_KINDS


def test_broken_json_inside_text_is_invalid_json():
    assert _error_of(_reply('Kết quả: {"a": 1, "b": }')).kind == "invalid_json"


def test_empty_content_is_invalid_json():
    assert _error_of(_reply("")).kind == "invalid_json"
    assert _error_of(_reply(None)).kind == "invalid_json"


def test_non_json_200_body_is_invalid_json():
    """Quên stream:false thì 9router trả 200 với thân không phải JSON (dạng stream)."""
    err = _error_of(lambda request: httpx.Response(200, text='data: {"choices": []}\n\ndata: [DONE]\n\n'))
    assert err.kind == "invalid_json"


def test_response_without_choices_is_invalid_json():
    assert _error_of(lambda request: httpx.Response(200, json={"id": "x"})).kind == "invalid_json"


def test_401_maps_to_auth():
    err = _error_of(lambda request: httpx.Response(401, json={"error": {"message": "Invalid API key"}}))
    assert err.kind == "auth"
    assert "401" in err.user_message
    assert "NINEROUTER_API_KEY" in err.user_message
    assert err.kind not in RETRYABLE_KINDS


def test_no_credentials_maps():
    body = {"error": {"message": "No active credentials for provider: antigravity"}}
    err = _error_of(lambda request: httpx.Response(404, json=body))
    assert err.kind == "no_credentials"
    assert "kết nối Gemini" in err.user_message
    assert err.kind not in RETRYABLE_KINDS


def test_timeout_maps():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("quá hạn", request=request)

    err = _error_of(handler, timeout=7)
    assert err.kind == "timeout"
    assert "7" in err.user_message
    assert err.kind in RETRYABLE_KINDS


def test_connection_error_maps_to_network():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    err = _error_of(handler)
    assert err.kind == "network"
    assert TEST_BASE in err.user_message
    assert err.kind in RETRYABLE_KINDS


def test_other_http_status_maps_to_http():
    err = _error_of(lambda request: httpx.Response(500, text="boom"))
    assert err.kind == "http"
    assert "500" in err.user_message
    assert err.kind not in RETRYABLE_KINDS


# ---------------------------------------------------------------- 9router bận (429/502/503/504)

@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_busy_statuses_map_to_busy(status):
    err = _error_of(lambda request: httpx.Response(status, text="upstream overloaded"))
    assert err.kind == "busy"
    assert "9router" in err.user_message and "bận" in err.user_message
    assert str(status) in err.user_message
    assert err.retry_after_s is None
    assert err.kind not in RETRYABLE_KINDS          # bận thì chờ rồi gọi lại, không tốn lượt thử


def test_busy_reads_reset_hint_from_body():
    """Thân lỗi thật của 9router khi tài khoản Gemini đang bị giới hạn."""
    body = "[antigravity/gemini-3.8-flash-high] [403]: HTTP 403 (reset after 2m)"
    err = _error_of(lambda request: httpx.Response(503, text=body))
    assert err.kind == "busy"
    assert err.retry_after_s == 120


@pytest.mark.parametrize("text, seconds", [
    ("reset after 45s", 45),
    ("Rate limited, Reset after 1m30s", 90),
    ("reset after 1h", 3600),
    ('{"error": {"message": "quota exceeded, retry in 2 minutes"}}', 120),
])
def test_busy_reset_hint_formats(text, seconds):
    assert _error_of(lambda request: httpx.Response(429, text=text)).retry_after_s == seconds


def test_busy_reads_retry_after_header():
    err = _error_of(lambda request: httpx.Response(429, headers={"Retry-After": "30"}, text="slow down"))
    assert err.kind == "busy"
    assert err.retry_after_s == 30


def test_busy_retry_after_http_date():
    from email.utils import format_datetime
    from datetime import datetime, timedelta, timezone

    when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=90), usegmt=True)
    err = _error_of(lambda request: httpx.Response(503, headers={"Retry-After": when}))
    assert 80 <= err.retry_after_s <= 91


def test_no_credentials_wins_over_busy_status():
    body = {"error": {"message": "No active credentials for provider: antigravity"}}
    assert _error_of(lambda request: httpx.Response(503, json=body)).kind == "no_credentials"


def test_llm_error_retry_after_defaults_to_none():
    assert LLMError("timeout", "Hết giờ").retry_after_s is None
    assert LLMError("busy", "Bận", retry_after_s=5).retry_after_s == 5


def test_missing_key_raises_auth_without_calling_api(monkeypatch):
    monkeypatch.setattr(config, "NINEROUTER_API_KEY", "")
    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request)
        return httpx.Response(200, json=_completion("{}"))

    err = _error_of(handler)
    assert err.kind == "auth"
    assert "NINEROUTER_API_KEY" in err.user_message
    assert called == []


def test_missing_base_url_raises_auth(monkeypatch):
    monkeypatch.setattr(config, "NINEROUTER_BASE_URL", "")
    err = _error_of(_reply("{}"))
    assert err.kind == "auth"
    assert "NINEROUTER_BASE_URL" in err.user_message


def test_str_of_error_is_user_message():
    err = LLMError("timeout", "Hết giờ")
    assert str(err) == "Hết giờ"
    assert err.kind == "timeout"
    assert err.user_message == "Hết giờ"


def test_retryable_kinds_exact():
    assert RETRYABLE_KINDS == {"timeout", "network", "invalid_json"}


def test_key_never_leaks_into_error_messages():
    """Thân lỗi của máy chủ có thể lặp lại header; thông báo hiển thị cho người dùng không được chứa key."""
    handlers = [
        lambda request: httpx.Response(500, text=f"echo Authorization: Bearer {TEST_KEY}"),
        lambda request: httpx.Response(401, text=f"bad {TEST_KEY}"),
        lambda request: httpx.Response(503, text=f"echo {TEST_KEY} (reset after 1m)"),
        _reply(f"không phải json {TEST_KEY}"),
    ]
    for handler in handlers:
        assert TEST_KEY not in _error_of(handler).user_message
