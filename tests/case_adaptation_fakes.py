"""
LLM giả cho test luồng chuyển thể vụ án, cùng chữ ký với call_llm_json(system, user, *, temperature, timeout, client).

- Marker là dòng đầu của user prompt, bỏ tiền tố "TASK: " (ví dụ "EXTRACT 0", "CLUSTER", "ALIASES").
- Mặc định trả nội dung fixtures/case_adaptation/<marker, dấu cách đổi thành _>.json (ví dụ EXTRACT_0.json).
- overrides[marker] có thể là:
    * một giá trị: lần gọi nào cũng trả giá trị đó;
    * một Exception (hoặc lớp Exception): lần gọi nào cũng raise;
    * một list: mỗi lần gọi lấy phần tử kế tiếp (phần tử là giá trị hoặc Exception); hết list thì trả fixture.
- Danh sách marker đã gọi được ghi theo thứ tự (phần tử thứ hai của tuple trả về).
  Thuộc tính `prompts` của hàm giả ghi lại toàn văn user prompt từng lần gọi, cùng thứ tự.
"""
import copy
import json
from pathlib import Path
from typing import Any, Optional

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "case_adaptation"
_TASK_PREFIX = "TASK:"
_EXHAUSTED = object()


def marker_of(user: str) -> str:
    first = user.split("\n", 1)[0].strip()
    if first.startswith(_TASK_PREFIX):
        first = first[len(_TASK_PREFIX):].strip()
    return first


def load_fixture(marker: str) -> Any:
    path = FIXTURES_DIR / f"{marker.replace(' ', '_')}.json"
    if not path.is_file():
        raise AssertionError(f"LLM giả không có fixture cho marker {marker!r} ({path.name}).")
    return json.loads(path.read_text(encoding="utf-8"))


def _is_exception(value: Any) -> bool:
    return isinstance(value, BaseException) or (isinstance(value, type) and issubclass(value, BaseException))


def make_fake_llm(overrides: Optional[dict] = None):
    """Trả (hàm LLM giả, danh sách marker đã gọi)."""
    calls: list[str] = []
    prompts: list[str] = []
    pending = {key: (list(value) if isinstance(value, list) else value) for key, value in (overrides or {}).items()}

    def _next_override(marker: str) -> Any:
        if marker not in pending:
            return _EXHAUSTED
        value = pending[marker]
        if isinstance(value, list):
            return value.pop(0) if value else _EXHAUSTED
        return value

    async def fake_llm(system: str, user: str, *, temperature: float = 0.4, timeout: float = 240.0, client=None) -> Any:
        marker = marker_of(user)
        calls.append(marker)
        prompts.append(user)
        value = _next_override(marker)
        if value is _EXHAUSTED:
            return load_fixture(marker)
        if _is_exception(value):
            raise value
        return copy.deepcopy(value)

    fake_llm.prompts = prompts
    return fake_llm, calls
