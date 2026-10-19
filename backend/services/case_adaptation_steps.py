"""
Bộ chạy một việc nhỏ của hàng việc phân tích vụ án, cùng các việc G1–G7 (spec 7.1a–7.5).

- ask_validated: gọi LLM một lần, kiểm kết quả bằng code; kết quả mỏng hoặc sai thì gọi lại, nối lý do bị loại
  vào cuối prompt; tối đa MAX_ATTEMPTS lần. Lỗi 9router không đáng thử lại (auth, no_credentials, http) thì
  dừng ngay. Hỏng thì raise StepFailed với thông báo tiếng Việt nêu đúng tên việc.
  Lỗi nhẹ (SoftRejected: tên thật, ngày tháng, tên trong prompt hình) cũng được gọi lại, nhưng hết lượt thì nhận
  kết quả đó; check_plan ở G7 tự thay tên đã có tên hư cấu và đánh dấu phần còn lại.
- chunk_source (G1): cắt bài theo đoạn văn (dòng trống, rồi tới xuống dòng); đoạn văn dài quá thì cắt theo câu,
  câu dài quá thì cắt ở khoảng trắng.
  Mỗi đoạn là một lát cắt nguyên văn của bài, nên nối lại không mất chữ nào.
- run_step: chạy một việc theo step.kind và trả StepResult. Không ghi kết quả; worker lưu
  StepResult.output vào steps/<step_id>.json rồi mới đánh dấu việc xong, và chèn StepResult.new_steps ngay sau việc đó.
    * extract_chunk (G2): đọc một đoạn → tên, sự việc, bằng chứng, quan hệ;
    * cluster_names (G3): gộp các cách gọi khác nhau của cùng một đối tượng;
    * assign_aliases (G4): đặt tên hư cấu, văn hoá, tên tập, rồi ghép với kết quả G2 thành CaseBible;
    * build_outline (G5): dàn ý theo nhịp; sinh ra write_vi/write_en/write_prompts cho từng nhịp, cuối cùng assemble;
    * write_vi, write_en, write_prompts (G6): lời Việt → lời Anh → prompt hình của một nhịp, đúng scene_count cảnh;
    * assemble (G7, không gọi LLM): chèn cảnh miễn trừ, ghép các nhịp, chuẩn hoá, check_plan rồi lưu plan.json.
- rewrite_english: viết lại lời Anh cho vài cảnh có lời Việt mới sửa (dùng khi tạo bản tiếng Anh).
- Hàm LLM mặc định lấy `case_adaptation_llm.call_llm_json` lúc gọi, để test và các task sau monkeypatch được.
"""
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

import config
from models.case_adaptation_schemas import (
    DISCLAIMER,
    MAX_ATTEMPTS,
    MAX_VIDEO_RATIO,
    TARGET_SCENES,
    AdaptedScene,
    CaseAdaptationPlan,
    CaseBible,
    CaseEntity,
    CaseEvidence,
    CaseOutline,
    CasePipeline,
    CaseRelation,
    PipelineStep,
    StoryPart,
    TimelineEvent,
)
from services import case_adaptation_llm, case_store, video_service
from services.case_adaptation_checks import (
    ForbiddenName,
    apply_aliases,
    build_forbidden_names,
    check_plan,
    find_dates,
    find_unknown_names,
    fold,
    is_kept_term,
)
from services.case_adaptation_llm import RETRYABLE_KINDS, LLMCall, LLMError
from services.case_adaptation_prompts import (
    BGM_ENERGIES,
    EN_WORDS,
    MAX_SCENES_PER_EVENT,
    MIN_EVENT_WORDS,
    MIN_IMAGE_PROMPT_WORDS,
    MIN_VIDEO_PROMPT_WORDS,
    NARRATIVE_BEATS,
    PART_KINDS,
    RELATION_TYPES,
    ROLES,
    SCENES_PER_MINUTE,
    SCENES_PER_PART,
    SYSTEM_PROMPT,
    VI_WORDS,
    VISUAL_KINDS,
    aliases_prompt,
    cluster_prompt,
    extract_prompt,
    max_events_per_scene,
    min_events_for,
    outline_prompt,
    prompts_prompt,
    rewrite_en_prompt,
    supported_scene_cap,
    video_scene_cap,
    word_count,
    write_en_prompt,
    write_vi_prompt,
)

T = TypeVar("T")

RETRY_NOTE = "\n\nLẦN TRƯỚC BỊ LOẠI VÌ: {reason}. Hãy làm lại đầy đủ, không tóm gọn."
OPENING_EXCERPT_CHARS = 1500

_TEMPERATURE_EXTRACT = 0.2
_TEMPERATURE_CLUSTER = 0.1
_TEMPERATURE_ALIASES = 0.6
_TEMPERATURE_OUTLINE = 0.3
_TEMPERATURE_VI = 0.7
_TEMPERATURE_EN = 0.6
_TEMPERATURE_PROMPTS = 0.5
_PREV_SCENES = 2                 # số cảnh cuối của nhịp trước đưa vào prompt lời Việt
_MAX_LISTED_IDS = 40             # id ngắn nên liệt kê được nhiều hơn tên
SHORT_MATERIAL_WARNING = "Bài chỉ đủ tư liệu cho khoảng {n} phút (bạn chọn {m} phút)."
_MIN_APPEARANCE_WORDS = 8      # prompt xin ít nhất 12 từ; ngưỡng loại nới hơn để không loại oan
_MIN_SETTING_WORDS = 12        # prompt xin ít nhất 30 từ
_MAX_LISTED = 12               # số mục tối đa liệt kê trong một lý do bị loại
_INVALID_JSON_REASON = "kết quả không phải JSON hợp lệ; chỉ trả đúng một JSON object theo mẫu, không kèm chữ nào khác"
_NO_VALUE = object()


class StepRejected(Exception):
    """Kết quả của LLM không đạt; `reason` được gửi lại cho LLM ở lần thử sau."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class SoftRejected(StepRejected):
    """Kết quả dùng được nhưng còn lỗi nên sửa (tên thật, ngày tháng cụ thể, tên trong prompt hình).
    ask_validated gửi lý do để model làm lại; hết lượt mà không có kết quả sạch thì dùng `value` của lần gần nhất,
    vì check_plan sẽ tự thay tên đã có tên hư cấu và đánh dấu phần còn lại để người dùng sửa."""

    def __init__(self, reason: str, value: Any):
        super().__init__(reason)
        self.value = value


class StepFailed(Exception):
    """Việc hỏng hẳn (hết số lần thử hoặc lỗi không đáng thử lại). `user_message` có tên việc và lý do."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


@dataclass
class StepResult:
    output: dict
    new_steps: list[PipelineStep] = field(default_factory=list)


# ---------------------------------------------------------------- một việc: gọi, kiểm, gọi lại

def _schema_reason(exc: ValidationError) -> str:
    errors = exc.errors()
    parts = []
    for err in errors[:5]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "(gốc)"
        parts.append(f"{loc}: {err.get('msg', '')}")
    if len(errors) > 5:
        parts.append(f"và {len(errors) - 5} lỗi khác")
    return "JSON sai cấu trúc so với mẫu (" + "; ".join(parts) + ")"


async def ask_validated(
    user: str,
    validate: Callable[[Any], T],
    *,
    llm: LLMCall,
    temperature: float = 0.4,
    step_label: str,
) -> T:
    """Gọi LLM tối đa MAX_ATTEMPTS lần cho tới khi `validate` nhận kết quả.

    - `validate` raise StepRejected (hoặc pydantic ValidationError) khi kết quả không đạt; lý do được nối vào prompt
      lần sau. Kết quả không phải dict/list (null, số, chuỗi) cũng bị loại.
    - `validate` raise SoftRejected khi kết quả dùng được nhưng còn lỗi nhẹ: vẫn gọi lại kèm lý do, nhưng nếu hết
      lượt mà không lần nào sạch thì trả `value` của lần SoftRejected gần nhất thay vì StepFailed.
    - LLMError thuộc RETRYABLE_KINDS thì thử lại; loại khác (auth, no_credentials, http) thì StepFailed ngay.
    """
    reason: Optional[str] = None   # lý do gửi lại cho LLM
    problem = ""                   # lý do báo người dùng nếu hỏng cả MAX_ATTEMPTS lần
    fallback: Any = _NO_VALUE      # kết quả dùng được (chỉ có lỗi nhẹ) của lần gần nhất
    for _attempt in range(MAX_ATTEMPTS):
        prompt = user if reason is None else user + RETRY_NOTE.format(reason=reason.rstrip(" ."))
        try:
            raw = await llm(SYSTEM_PROMPT, prompt, temperature=temperature)
        except LLMError as exc:
            if exc.kind not in RETRYABLE_KINDS:
                raise StepFailed(f"Bước {step_label} thất bại: {exc.user_message}") from exc
            problem = exc.user_message
            if exc.kind == "invalid_json":
                reason = _INVALID_JSON_REASON
            continue                # timeout/mạng: prompt chưa tới model, giữ nguyên lý do cũ (nếu có)
        try:
            if not isinstance(raw, (dict, list)):
                raise StepRejected("Kết quả không phải JSON object/array.")
            return validate(raw)
        except SoftRejected as exc:
            reason = problem = exc.reason
            fallback = exc.value
        except StepRejected as exc:
            reason = problem = exc.reason
        except ValidationError as exc:
            reason = problem = _schema_reason(exc)
    if fallback is not _NO_VALUE:
        return fallback
    raise StepFailed(f"Bước {step_label} thất bại sau {MAX_ATTEMPTS} lần: {problem}")


# ---------------------------------------------------------------- G1: cắt bài

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
_LINE_BREAK = re.compile(r"\n")   # bài dán từ web thường tách đoạn văn chỉ bằng một lần xuống dòng
_SENTENCE_END = re.compile(r"[.!?…。！？]+[\"'”’»)\]]*(?=\s)")
# Ranh giới để cắt, ưu tiên từ trên xuống: dòng trống, xuống dòng, hết câu. Hết cấp thì cắt ở khoảng trắng.
_BOUNDARIES = (_PARAGRAPH_BREAK, _LINE_BREAK, _SENTENCE_END)


def _trim(text: str, start: int, end: int) -> Optional[tuple[int, int]]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def _split_at(text: str, start: int, end: int, pattern: re.Pattern) -> list[tuple[int, int]]:
    """Cắt [start, end) ngay sau mỗi chỗ khớp `pattern`; bỏ khoảng trắng hai đầu từng khúc."""
    spans, pos = [], start
    for m in pattern.finditer(text, start, end):
        span = _trim(text, pos, m.end())
        if span:
            spans.append(span)
        pos = m.end()
    span = _trim(text, pos, end)
    if span:
        spans.append(span)
    return spans


def _hard_split(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Câu dài hơn max_chars: cắt ở khoảng trắng cuối cùng trong giới hạn, không có thì cắt cứng."""
    spans = []
    while end - start > max_chars:
        window = text[start:start + max_chars + 1]
        cut = max(window.rfind(" "), window.rfind("\t"))
        if cut <= 0:
            cut = max_chars
        span = _trim(text, start, start + cut)
        if span:
            spans.append(span)
        start += cut
        while start < end and text[start].isspace():
            start += 1
    span = _trim(text, start, end)
    if span:
        spans.append(span)
    return spans


def _units(text: str, start: int, end: int, max_chars: int, level: int = 0) -> list[tuple[int, int]]:
    """Chia [start, end) thành các khúc ≤ max_chars, chỉ đi xuống cấp ranh giới nhỏ hơn khi khúc còn quá dài."""
    if end - start <= max_chars:
        return [(start, end)]
    if level == len(_BOUNDARIES):
        return _hard_split(text, start, end, max_chars)
    spans: list[tuple[int, int]] = []
    for s, e in _split_at(text, start, end, _BOUNDARIES[level]):
        spans.extend(_units(text, s, e, max_chars, level + 1))
    return spans


def chunk_source(text: str, max_chars: int) -> list[str]:
    """Cắt bài thành các đoạn dài tối đa `max_chars` ký tự, theo ranh giới đoạn văn.

    Đoạn văn (ngăn bằng dòng trống) vừa cỡ thì không bị cắt. Đoạn văn dài hơn `max_chars` thì cắt ở chỗ xuống
    dòng (bài dán từ web tách đoạn văn bằng một lần xuống dòng), rồi mới theo câu, câu dài hơn nữa thì cắt ở
    khoảng trắng. Các khúc được xếp lần lượt vào đoạn hiện tại cho tới khi đầy."""
    if max_chars < 1:
        raise ValueError("max_chars phải lớn hơn 0")
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    trimmed = _trim(text, 0, len(text))
    units = _units(text, *trimmed, max_chars) if trimmed else []

    chunks: list[str] = []
    current: Optional[tuple[int, int]] = None
    for start, end in units:
        if current is not None and end - current[0] <= max_chars:
            current = (current[0], end)
            continue
        if current is not None:
            chunks.append(text[current[0]:current[1]])
        current = (start, end)
    if current is not None:
        chunks.append(text[current[0]:current[1]])
    return chunks


def initial_steps(n_chunks: int) -> list[PipelineStep]:
    """Hàng việc ban đầu: đọc từng đoạn, gộp tên, đặt tên hư cấu, dàn ý. Việc viết cảnh sinh ra sau dàn ý."""
    steps = [PipelineStep(id=f"extract_{i:02d}", kind="extract_chunk", params={"index": i}) for i in range(n_chunks)]
    steps += [
        PipelineStep(id="cluster", kind="cluster_names"),
        PipelineStep(id="aliases", kind="assign_aliases"),
        PipelineStep(id="outline", kind="build_outline"),
    ]
    return steps


# ---------------------------------------------------------------- chuẩn hoá tên và nhãn

def _exact_key(name: str) -> str:
    """Khoá so tên "y nguyên": NFC, chữ thường, gộp khoảng trắng. Giữ dấu để "Hùng" và "Hưng" khác nhau."""
    return " ".join(unicodedata.normalize("NFC", str(name)).lower().split())


def _fold_key(name: str) -> str:
    """Khoá so tên bỏ dấu (dùng khi cách viết khác dấu, khác hoa thường)."""
    return " ".join(fold(str(name)).split())


def _has_capital(token: str) -> bool:
    """Có chữ hoa, chữ số, hoặc chữ không phân biệt hoa thường (chữ Hán)."""
    return any(c.isdigit() or (c.isalpha() and not c.islower()) for c in token)


def _looks_proper(name: str, kind: Optional[str] = None) -> bool:
    """Trông như tên riêng hay mã số.
    - Không có chữ hoa hay chữ số nào ("cơ quan điều tra") thì không phải, với mọi loại.
    - Người (`kind == "person"`) và tên chưa rõ loại (`kind` None, ở phần kiểm tên thiếu): chỉ cần có chữ hoa, vì
      biệt danh chỉ viết hoa chữ đầu ("Hùng sẹo", "Sáu lùn"); bỏ sót biệt danh là lọt tên thật.
    - Nơi chốn, tổ chức nhiều chữ mà chỉ chữ đầu viết hoa ("Trường tiểu học") là chữ hoa đầu câu, không phải tên
      riêng; tên riêng của nơi chốn, tổ chức viết hoa cả chữ sau ("Cảng Tân Hải", "TP Hải Phòng")."""
    tokens = name.split()
    if not tokens or not any(_has_capital(t) for t in tokens):
        return False
    if kind in (None, "person"):
        return True
    return len(tokens) == 1 or any(_has_capital(t) for t in tokens[1:])


def _skip_name(name: str, kind: Optional[str] = None) -> bool:
    """Tên không cần tên hư cấu: không trông như tên riêng, hoặc là tên giữ nguyên (tên nước, danh từ chung trong
    GENERIC_TERMS; xem case_adaptation_checks.is_kept_term). Dùng chung cho danh sách tên (biết kind) và phần kiểm
    tên thiếu (kind None), để khớp đúng điều prompt đọc bài dặn model không liệt kê."""
    return not _looks_proper(name, kind) or is_kept_term(name, kind)


class _NameIndex:
    """Ánh xạ một cách viết tên sang giá trị (tên chuẩn hoặc id entity): khớp y nguyên trước, rồi khớp bỏ dấu
    nếu không mơ hồ."""

    def __init__(self) -> None:
        self._exact: dict[str, str] = {}
        self._folded: dict[str, set[str]] = {}

    def add(self, name: str, value: str) -> None:
        self._exact.setdefault(_exact_key(name), value)
        self._folded.setdefault(_fold_key(name), set()).add(value)

    def get(self, name: str) -> Optional[str]:
        hit = self._exact.get(_exact_key(name))
        if hit is not None:
            return hit
        candidates = self._folded.get(_fold_key(name), set())
        return next(iter(candidates)) if len(candidates) == 1 else None


def _quoted_list(items: list[str]) -> str:
    shown = ", ".join(f"'{i}'" for i in items[:_MAX_LISTED])
    return shown + (f" và {len(items) - _MAX_LISTED} tên khác" if len(items) > _MAX_LISTED else "")


_KIND_SYNONYMS = {
    "person": "person", "people": "person", "human": "person", "người": "person", "nguoi": "person",
    "place": "place", "location": "place", "địa danh": "place", "dia danh": "place", "địa điểm": "place",
    "organization": "organization", "organisation": "organization", "org": "organization",
    "company": "organization", "tổ chức": "organization", "to chuc": "organization",
    "identifier": "identifier", "id": "identifier", "mã số": "identifier", "ma so": "identifier",
}
_ROLE_SYNONYMS = {
    "nạn nhân": "victim", "nghi phạm": "suspect", "nghi can": "suspect", "hung thủ": "perpetrator",
    "killer": "perpetrator", "murderer": "perpetrator", "nhân chứng": "witness", "điều tra viên": "investigator",
    "detective": "investigator", "police": "investigator", "người nhà": "family", "gia đình": "family",
}

Kind = Literal["person", "place", "organization", "identifier"]


def _norm_kind(value: Any) -> Any:
    if isinstance(value, str):
        key = " ".join(value.strip().lower().split())
        return _KIND_SYNONYMS.get(key, key)
    return value


def _norm_role(value: Any) -> str:
    key = " ".join(str(value or "").strip().lower().split())
    key = _ROLE_SYNONYMS.get(key, key)
    return key if key in ROLES else "other"


def _norm_relation_type(value: Any) -> str:
    key = re.sub(r"[\s\-]+", "_", str(value or "").strip().lower())
    return key if key in RELATION_TYPES else "suspect_link"


class _Item(BaseModel):
    """Mẫu đọc kết quả LLM: bỏ khoá thừa, cắt khoảng trắng; giá trị null coi như không có (lấy mặc định)."""
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


def _clean_names(values: list[str]) -> list[str]:
    out, seen = [], set()
    for v in values:
        v = " ".join(str(v).split())
        if v and _exact_key(v) not in seen:
            seen.add(_exact_key(v))
            out.append(v)
    return out


# ---------------------------------------------------------------- G2: đọc một đoạn

class _ExtractName(_Item):
    name: str
    kind: Kind
    role: str = "other"
    context: str = ""

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: Any) -> Any:
        return _norm_kind(value)


class _ExtractEvent(_Item):
    summary: str
    time_label: str = ""
    names: list[str] = []


class _ExtractEvidence(_Item):
    label_vi: str
    label_en: str
    description_vi: str = ""
    description_en: str = ""
    names: list[str] = []


class _ExtractRelation(_Item):
    source_name: str
    target_name: str
    relation_type: str = "suspect_link"
    label_vi: str = ""
    label_en: str = ""


class _ExtractOutput(_Item):
    names: list[_ExtractName]
    events: list[_ExtractEvent]
    evidence: list[_ExtractEvidence] = []
    relations: list[_ExtractRelation] = []


def _validate_extract(raw: Any, chunk: str, known_names: list[str]) -> dict:
    parsed = _ExtractOutput.model_validate(raw)
    problems: list[str] = []

    names: list[dict] = []
    seen: set[str] = set()
    for item in parsed.names:
        name = " ".join(item.name.split())
        if not name or _skip_name(name, item.kind) or _exact_key(name) in seen:
            continue
        seen.add(_exact_key(name))
        names.append({"name": name, "kind": item.kind, "role": _norm_role(item.role), "context": item.context})

    words = word_count(chunk)
    need = min_events_for(words)
    if len(parsed.events) < need:
        problems.append(
            f"Đoạn dài {words} từ nhưng chỉ có {len(parsed.events)} sự việc, cần ít nhất {need}. "
            "Mỗi hành động, phát hiện, lời khai, kết quả giám định là một sự việc riêng; không gộp nhiều sự việc làm một"
        )
    short = [(i, ev) for i, ev in enumerate(parsed.events, start=1) if word_count(ev.summary) < MIN_EVENT_WORDS]
    for i, ev in short[:5]:
        problems.append(f"Tóm tắt sự việc số {i} quá ngắn ({word_count(ev.summary)} từ, cần ít nhất "
                        f"{MIN_EVENT_WORDS} từ): \"{ev.summary}\"")
    if len(short) > 5:
        problems.append(f"Còn {len(short) - 5} tóm tắt sự việc khác cũng quá ngắn")

    # Tên nhắc trong sự việc, bằng chứng, quan hệ phải có trong "names" (hoặc đã gặp ở đoạn trước),
    # nếu không thì tên đó không bao giờ được đặt tên hư cấu. "Có trong names" tính theo mọi mục model đã liệt kê,
    # kể cả mục bị lọc bỏ ở trên (ví dụ "Cảnh sát giao thông" ghi là organization): liệt kê vào names, với kind
    # bất kỳ, luôn gỡ được lý do bị loại, nên không có vòng loại đi loại lại.
    index = _NameIndex()
    for n in [*known_names, *(" ".join(item.name.split()) for item in parsed.names)]:
        if n:
            index.add(n, n)
    referenced = [n for ev in parsed.events for n in ev.names]
    referenced += [n for ev in parsed.evidence for n in ev.names]
    referenced += [n for rel in parsed.relations for n in (rel.source_name, rel.target_name)]
    missing = [n for n in _clean_names(referenced) if not _skip_name(n) and index.get(n) is None]
    if missing:
        problems.append(f"Các tên sau có trong events/evidence/relations nhưng thiếu trong names: {_quoted_list(missing)}. "
                        "Hãy thêm từng tên vào names (kèm kind, role, context)")
    if problems:
        raise StepRejected("; ".join(problems))

    return {
        "names": names,
        "events": [{"summary": ev.summary, "time_label": ev.time_label, "names": _clean_names(ev.names)}
                   for ev in parsed.events],
        "evidence": [{"label_vi": ev.label_vi, "label_en": ev.label_en, "description_vi": ev.description_vi,
                      "description_en": ev.description_en, "names": _clean_names(ev.names)}
                     for ev in parsed.evidence if ev.label_vi or ev.label_en],
        "relations": [{"source_name": rel.source_name, "target_name": rel.target_name,
                       "relation_type": _norm_relation_type(rel.relation_type),
                       "label_vi": rel.label_vi, "label_en": rel.label_en}
                      for rel in parsed.relations if rel.source_name and rel.target_name],
    }


def _extract_outputs(pipeline: CasePipeline, label: str, *, before: Optional[int] = None) -> list[tuple[int, dict]]:
    """Kết quả các việc đọc đoạn đã xong, theo thứ tự đoạn. Thiếu kết quả của một đoạn thì StepFailed."""
    found = []
    for step in pipeline.steps:
        if step.kind != "extract_chunk":
            continue
        idx = int(step.params.get("index", 0))
        if before is not None and idx >= before:
            continue
        data = case_store.load_step_output(pipeline.case_id, step.id)
        if data is None:
            raise StepFailed(f"Bước {label} thất bại: chưa có kết quả của bước đọc đoạn {idx + 1}.")
        found.append((idx, data))
    return sorted(found, key=lambda pair: pair[0])


def _distinct_names(outputs: list[tuple[int, dict]]) -> list[dict]:
    """Mọi tên khác nhau (so y nguyên, không phân biệt hoa thường) trong các kết quả đọc đoạn, giữ lần gặp đầu."""
    names, seen = [], set()
    for _idx, data in outputs:
        for item in data.get("names", []):
            key = _exact_key(item.get("name", ""))
            if key and key not in seen:
                seen.add(key)
                names.append({"name": item["name"], "kind": item.get("kind", ""),
                              "role": item.get("role", "other"), "context": item.get("context", "")})
    return names


async def _run_extract(pipeline: CasePipeline, step: PipelineStep, llm: LLMCall) -> StepResult:
    index = int(step.params.get("index", 0))
    label = f"đọc đoạn {index + 1}"
    chunks = case_store.load_chunks(pipeline.case_id) or []
    if not 0 <= index < len(chunks):
        raise StepFailed(f"Bước {label} thất bại: không tìm thấy đoạn {index + 1} trong hồ sơ vụ án.")
    chunk = chunks[index]
    known = [n["name"] for n in _distinct_names(_extract_outputs(pipeline, label, before=index))]
    output = await ask_validated(
        extract_prompt(chunk, index, len(chunks), known),
        lambda raw: _validate_extract(raw, chunk, known),
        llm=llm, temperature=_TEMPERATURE_EXTRACT, step_label=label,
    )
    return StepResult(output=output)


# ---------------------------------------------------------------- G3: gộp tên

_GROUP_ID = re.compile(r"[a-z][a-z0-9_]{0,39}")


class _Group(_Item):
    id: str = ""
    kind: Kind
    role: str = "other"
    real_names: list[str]

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: Any) -> Any:
        return _norm_kind(value)


class _ClusterOutput(_Item):
    groups: list[_Group]


def _validate_cluster(raw: Any, names: list[dict]) -> dict:
    parsed = _ClusterOutput.model_validate(raw)
    index = _NameIndex()
    for item in names:
        index.add(item["name"], item["name"])

    groups: list[tuple[_Group, list[str]]] = []
    owner: dict[str, int] = {}
    doubled: dict[str, list[int]] = {}
    for group in parsed.groups:
        members: list[str] = []
        for written in group.real_names:
            canonical = index.get(written)          # tên lạ (không có trong danh sách) thì bỏ
            if canonical is not None and canonical not in members:
                members.append(canonical)
        if not members:
            continue
        position = len(groups)
        groups.append((group, members))
        for name in members:
            if name in owner:
                doubled.setdefault(name, [owner[name] + 1]).append(position + 1)
            else:
                owner[name] = position

    problems = []
    missing = [item["name"] for item in names if item["name"] not in owner]
    if missing:
        problems.append(f"Thiếu {len(missing)} tên, chưa nằm trong nhóm nào: {_quoted_list(missing)}. "
                        "Mỗi tên trong danh sách phải nằm trong đúng một nhóm")
    if doubled:
        listed = ", ".join(f"'{n}' (nhóm thứ {', '.join(map(str, pos))})" for n, pos in list(doubled.items())[:_MAX_LISTED])
        problems.append(f"Các tên nằm trong nhiều hơn một nhóm: {listed}. Mỗi tên chỉ được nằm trong một nhóm")
    if problems:
        raise StepRejected("; ".join(problems))

    # id: giữ id của LLM nếu hợp lệ và chưa dùng, còn lại tự đặt "<kind>_<n>".
    ids: list[Optional[str]] = []
    used: set[str] = set()
    for group, _members in groups:
        gid = group.id.strip().lower()
        if _GROUP_ID.fullmatch(gid) and gid not in used:
            used.add(gid)
            ids.append(gid)
        else:
            ids.append(None)
    counters: dict[str, int] = {}
    out = []
    for (group, members), gid in zip(groups, ids):
        if gid is None:
            while True:
                counters[group.kind] = counters.get(group.kind, 0) + 1
                gid = f"{group.kind}_{counters[group.kind]}"
                if gid not in used:
                    break
            used.add(gid)
        role = _norm_role(group.role) if group.kind == "person" else "other"
        out.append({"id": gid, "kind": group.kind, "role": role, "real_names": members})
    return {"groups": out}


async def _run_cluster(pipeline: CasePipeline, step: PipelineStep, llm: LLMCall) -> StepResult:
    label = "gộp tên"
    names = _distinct_names(_extract_outputs(pipeline, label))
    if not names:                                   # bài không có tên riêng nào: không có gì để gộp
        return StepResult(output={"groups": []})
    output = await ask_validated(
        cluster_prompt(names),
        lambda raw: _validate_cluster(raw, names),
        llm=llm, temperature=_TEMPERATURE_CLUSTER, step_label=label,
    )
    return StepResult(output=output)


# ---------------------------------------------------------------- G4: đặt tên hư cấu → hồ sơ

class _AliasEntity(_Item):
    id: str
    alias_vi: str = ""
    alias_en: str = ""
    gender: str = ""
    age_range: str = ""
    appearance_en: str = ""


class _AliasOutput(_Item):
    culture: str
    solved: bool
    title_vi: str
    title_en: str
    logline_vi: str = ""
    logline_en: str = ""
    setting_notes_en: str = ""
    entities: list[_AliasEntity]


_VI_LETTERS = set("ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ")


def _detect_language(text: str) -> str:
    """Ngôn ngữ bài gốc: "vi" khi có chữ cái riêng của tiếng Việt, "zh" khi phần lớn là chữ Hán, còn lại "en"."""
    letters = [c for c in unicodedata.normalize("NFC", text or "") if c.isalpha()]
    if not letters:
        return "en"
    han = sum(1 for c in letters if "一" <= c <= "鿿")
    if han / len(letters) >= 0.3:
        return "zh"
    vi = sum(1 for c in letters if c.lower() in _VI_LETTERS)
    return "vi" if vi / len(letters) >= 0.01 else "en"


def _norm_culture(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", fold(value)).strip("_")


def _word_pattern(key: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(tok) for tok in key.split()) + r"(?!\w)")


def _check_aliases(parsed: _AliasOutput, groups: list[dict]) -> list[str]:
    by_id: dict[str, _AliasEntity] = {}
    for ent in parsed.entities:
        by_id.setdefault(ent.id.strip(), ent)
    real_names = [n for g in groups for n in g["real_names"]]
    real_keys = {_fold_key(n): n for n in real_names}
    multi_word_real = [(_word_pattern(k), n) for k, n in real_keys.items() if " " in k]

    missing, equal_real, contains_real, keeps_given, short_looks = [], [], [], [], []
    alias_owner: dict[str, str] = {}
    duplicates: list[str] = []
    for group in groups:
        gid = group["id"]
        ent = by_id.get(gid)
        if ent is None or not ent.alias_vi or not ent.alias_en:
            missing.append(f"{gid} ({', '.join(group['real_names'][:2])})")
            continue
        own_given = {_fold_key(n).split()[-1] for n in group["real_names"] if _fold_key(n)}
        for alias in dict.fromkeys((ent.alias_vi, ent.alias_en)):
            key = _fold_key(alias)
            if key in real_keys:
                equal_real.append(f"'{alias}' (trùng tên thật '{real_keys[key]}')")
                continue
            inside = next((n for pattern, n in multi_word_real if pattern.search(key)), None)
            if inside:
                contains_real.append(f"'{alias}' (chứa tên thật '{inside}')")
            if group["kind"] == "person":
                last = key.split()[-1] if key else ""
                if len(last) >= 2 and last in own_given:
                    keeps_given.append(f"'{alias}' (giữ chữ '{alias.split()[-1]}' của tên thật)")
            owner = alias_owner.setdefault(key, gid)
            if owner != gid:
                duplicates.append(f"'{alias}' (dùng cho cả {owner} và {gid})")
        if group["kind"] == "person" and len(ent.appearance_en.split()) < _MIN_APPEARANCE_WORDS:
            short_looks.append(gid)

    problems = []
    if missing:
        problems.append(f"Thiếu alias_vi hoặc alias_en cho các nhóm: {', '.join(missing)}. Mỗi nhóm phải có đủ hai tên hư cấu")
    if equal_real:
        problems.append(f"Tên hư cấu trùng tên thật (kể cả khi bỏ dấu, khác hoa thường): {', '.join(equal_real)}. Hãy đặt tên khác hẳn")
    if contains_real:
        problems.append(f"Tên hư cấu chứa nguyên một tên thật: {', '.join(contains_real)}. Hãy đặt tên khác hẳn")
    if keeps_given:
        problems.append(f"Tên hư cấu của người giữ lại tên thật: {', '.join(keeps_given)}. Hãy đổi cả tên")
    if duplicates:
        problems.append(f"Tên hư cấu bị trùng giữa các nhóm: {', '.join(duplicates)}. Mỗi nhóm cần một tên riêng")
    if short_looks:
        problems.append(f"Thiếu hoặc quá ngắn appearance_en (cần ít nhất 12 từ) cho người: {', '.join(short_looks)}")
    return problems


def _check_texts(parsed: _AliasOutput, groups: list[dict]) -> list[str]:
    problems = []
    for field_name in ("culture", "title_vi", "title_en"):
        if not getattr(parsed, field_name):
            problems.append(f"Thiếu {field_name}")
    if len(parsed.setting_notes_en.split()) < _MIN_SETTING_WORDS:
        problems.append("setting_notes_en thiếu hoặc quá ngắn (cần 2–4 câu, ít nhất 30 từ)")

    forbidden = [ForbiddenName(real=n) for g in groups for n in g["real_names"]]
    aliases = [a for ent in parsed.entities for a in (ent.alias_vi, ent.alias_en) if a]
    texts = [(f, getattr(parsed, f)) for f in ("title_vi", "title_en", "logline_vi", "logline_en", "setting_notes_en")]
    texts += [(f"appearance_en của {ent.id}", ent.appearance_en) for ent in parsed.entities]
    for where, text in texts:
        leaked = find_unknown_names(text, forbidden, aliases)
        if leaked:
            problems.append(f"{where} chứa tên thật: {_quoted_list(leaked)}. Chỉ được dùng tên hư cấu")
    return problems


def _build_bible(parsed: _AliasOutput, groups: list[dict], extracts: list[tuple[int, dict]], source: str) -> CaseBible:
    by_id = {}
    for ent in parsed.entities:
        by_id.setdefault(ent.id.strip(), ent)
    entities = []
    names = _NameIndex()
    for group in groups:
        ent = by_id[group["id"]]
        entities.append(CaseEntity(
            id=group["id"], kind=group["kind"], real_names=list(group["real_names"]), role=group.get("role") or "other",
            alias_vi=ent.alias_vi, alias_en=ent.alias_en, gender=ent.gender, age_range=ent.age_range,
            appearance_en=ent.appearance_en,
        ))
        for real in group["real_names"]:
            names.add(real, group["id"])

    def ids_of(values: list[str]) -> list[str]:
        return list(dict.fromkeys(i for i in (names.get(v) for v in values) if i is not None))

    timeline: list[TimelineEvent] = []
    evidence: list[CaseEvidence] = []
    evidence_by_key: dict[tuple[str, str], CaseEvidence] = {}
    relations: list[CaseRelation] = []
    relation_keys: set[tuple[str, str, str]] = set()
    for chunk_index, data in extracts:
        for n, ev in enumerate(data.get("events", []), start=1):
            timeline.append(TimelineEvent(
                id=f"ev_{chunk_index}_{n}", order=len(timeline) + 1, chunk_index=chunk_index,
                time_label=ev.get("time_label", ""), summary=ev["summary"], entity_ids=ids_of(ev.get("names", [])),
            ))
        for item in data.get("evidence", []):
            # Chỉ gộp khi trùng cả nhãn lẫn mô tả (so bỏ dấu): nhãn ngắn kiểu "Lời khai nhân chứng" hay
            # "Camera an ninh" lặp lại cho nhiều bằng chứng khác nhau, gộp theo nhãn sẽ làm mất sự thật.
            key = (_fold_key(item.get("label_vi") or item.get("label_en", "")),
                   _fold_key(item.get("description_vi") or item.get("description_en", "")))
            same = evidence_by_key.get(key)
            if same is not None:                     # đúng bằng chứng đó nhắc lại: chỉ gộp entity
                same.entity_ids = list(dict.fromkeys([*same.entity_ids, *ids_of(item.get("names", []))]))
                continue
            record = CaseEvidence(
                id=f"evd_{len(evidence) + 1}", label_vi=item.get("label_vi", ""), label_en=item.get("label_en", ""),
                description_vi=item.get("description_vi", ""), description_en=item.get("description_en", ""),
                entity_ids=ids_of(item.get("names", [])),
            )
            evidence.append(record)
            evidence_by_key[key] = record
        for item in data.get("relations", []):
            source_id, target_id = names.get(item.get("source_name", "")), names.get(item.get("target_name", ""))
            relation_type = item.get("relation_type", "suspect_link")
            key = (source_id, target_id, relation_type)
            if source_id is None or target_id is None or source_id == target_id or key in relation_keys:
                continue                             # không ánh xạ được, tự nối vào chính nó, hoặc trùng
            relation_keys.add(key)
            relations.append(CaseRelation(
                id=f"rel_{len(relations) + 1}", source_id=source_id, target_id=target_id, relation_type=relation_type,
                label_vi=item.get("label_vi", ""), label_en=item.get("label_en", ""),
            ))

    return CaseBible(
        source_language=_detect_language(source), culture=_norm_culture(parsed.culture), solved=parsed.solved,
        title_vi=parsed.title_vi, title_en=parsed.title_en, logline_vi=parsed.logline_vi, logline_en=parsed.logline_en,
        entities=entities, timeline=timeline, evidence=evidence, relations=relations,
        setting_notes_en=parsed.setting_notes_en,
    )


def _validate_aliases(raw: Any, groups: list[dict], extracts: list[tuple[int, dict]], source: str) -> dict:
    parsed = _AliasOutput.model_validate(raw)
    problems = _check_aliases(parsed, groups) + _check_texts(parsed, groups)
    if problems:
        raise StepRejected("; ".join(problems))
    return _build_bible(parsed, groups, extracts, source).model_dump()


def _step_output(pipeline: CasePipeline, kind: str, label: str) -> dict:
    step = next((s for s in pipeline.steps if s.kind == kind), None)
    data = case_store.load_step_output(pipeline.case_id, step.id) if step is not None else None
    if data is None:
        raise StepFailed(f"Bước {label} thất bại: chưa có kết quả của bước trước ({kind}).")
    return data


async def _run_aliases(pipeline: CasePipeline, step: PipelineStep, llm: LLMCall) -> StepResult:
    label = "đặt tên hư cấu"
    groups = _step_output(pipeline, "cluster_names", label).get("groups", [])
    extracts = _extract_outputs(pipeline, label)
    source = case_store.load_source(pipeline.case_id)
    if source is None:
        source = "\n\n".join(case_store.load_chunks(pipeline.case_id) or [])
    source = source.replace("\r\n", "\n").strip()
    output = await ask_validated(
        aliases_prompt(groups, source[:OPENING_EXCERPT_CHARS]),
        lambda raw: _validate_aliases(raw, groups, extracts, source),
        llm=llm, temperature=_TEMPERATURE_ALIASES, step_label=label,
    )
    return StepResult(output=output)


# ---------------------------------------------------------------- G5–G7: phần dùng chung

def target_scenes(minutes: int) -> tuple[int, int]:
    """Số cảnh mục tiêu (tối thiểu, tối đa) cho `minutes` phút. Thời lượng ngoài bảng TARGET_SCENES thì co giãn
    theo mốc gần nhất."""
    if minutes in TARGET_SCENES:
        return TARGET_SCENES[minutes]
    key = min(TARGET_SCENES, key=lambda k: (abs(k - minutes), k))
    lo, hi = TARGET_SCENES[key]
    scale = max(int(minutes), 1) / key
    return max(1, round(lo * scale)), max(1, round(hi * scale))


def _id_list(ids: list[str]) -> str:
    shown = ", ".join(ids[:_MAX_LISTED_IDS])
    return shown + (f" và {len(ids) - _MAX_LISTED_IDS} id khác" if len(ids) > _MAX_LISTED_IDS else "")


def _clean_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v.strip() for v in values if isinstance(v, str) and v.strip()))


def _norm_token(value: Any) -> str:
    return re.sub(r"[\s\-]+", "_", str(value or "").strip().lower())


def _as_list(value: Any) -> Any:
    """Model đôi khi trả một chuỗi ("ev_0_1, ev_0_2") thay cho mảng: tách theo dấu phẩy/chấm phẩy."""
    if isinstance(value, str):
        return [v for v in re.split(r"[,;]", value) if v.strip()]
    return value


def _parse_model(model: type[BaseModel], data: Any, label: str, what: str) -> Any:
    """Đọc kết quả đã lưu của một bước trước; sai cấu trúc thì StepFailed (không gọi lại LLM được)."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise StepFailed(f"Bước {label} thất bại: kết quả của bước {what} không đúng cấu trúc "
                         f"({_schema_reason(exc)}).") from exc


def _load_bible(pipeline: CasePipeline, label: str) -> CaseBible:
    return _parse_model(CaseBible, _step_output(pipeline, "assign_aliases", label), label, "đặt tên hư cấu")


def _load_outline(pipeline: CasePipeline, label: str) -> CaseOutline:
    return _parse_model(CaseOutline, _step_output(pipeline, "build_outline", label), label, "lập dàn ý")


def _part_step_id(kind: str, part_id: str) -> str:
    return f"{kind}_{part_id}"


def _part_output(pipeline: CasePipeline, kind: str, part_id: str, label: str) -> list[dict]:
    """Các cảnh do bước `kind` (write_vi/write_en/write_prompts) của nhịp `part_id` viết ra."""
    step_id = _part_step_id(kind, part_id)
    data = case_store.load_step_output(pipeline.case_id, step_id)
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
        raise StepFailed(f"Bước {label} thất bại: chưa có kết quả của bước {step_id}.")
    return data["scenes"]


class _TextGuard:
    """Tìm lỗi nhẹ trong chữ LLM viết: tên thật (kể cả tên regex bắt được trên bài gốc), ngày tháng cụ thể,
    dạng tên tiếng Việt trong lời Anh, tên người trong prompt hình. Mỗi lỗi là một câu ngắn gửi lại cho model."""

    def __init__(self, bible: CaseBible, source_text: str = ""):
        self.bible = bible
        self.forbidden = build_forbidden_names(bible, source_text)
        self.by_real = {f.real: f for f in self.forbidden}
        self.aliases = list(dict.fromkeys(a.strip() for e in bible.entities
                                          for a in (e.alias_vi, e.alias_en) if a and a.strip()))

    def real_names(self, text: str, lang: str) -> list[str]:
        out = []
        for real in find_unknown_names(text, self.forbidden, self.aliases):
            fn = self.by_real.get(real)
            alias = ((fn.alias_vi if lang == "vi" else fn.alias_en) if fn else None) or ""
            if alias:
                out.append(f"có tên thật '{real}' (thay bằng '{alias}')")
            else:
                out.append(f"có tên thật '{real}' (không có tên hư cấu: bỏ tên này, thay bằng cách gọi chung)")
        return out

    @staticmethod
    def dates(text: str) -> list[str]:
        return [f"có ngày tháng hoặc năm cụ thể '{d}' (đổi thành thời kỳ, mùa hoặc mốc tương đối)"
                for d in dict.fromkeys(find_dates(text))]

    def vi_forms_in_en(self, text: str) -> list[str]:
        """Tên hư cấu dạng tiếng Việt (Hán-Việt...) xuất hiện trong lời Anh, khi dạng Anh khác hẳn."""
        folded = fold(text)
        out = []
        for ent in self.bible.entities:
            if ent.kind == "identifier":
                continue
            key_vi, key_en = _fold_key(ent.alias_vi), _fold_key(ent.alias_en)
            if not key_vi or not key_en or key_vi == key_en or key_vi in key_en:
                continue
            rest = _word_pattern(key_en).sub(" ", folded)
            if _word_pattern(key_vi).search(rest):
                out.append(f"dùng dạng tên tiếng Việt '{ent.alias_vi}' (lời Anh phải dùng '{ent.alias_en}')")
        return out

    def names_in_prompt(self, text: str) -> list[str]:
        out = [f"có tên thật '{real}'" for real in find_unknown_names(text, self.forbidden, self.aliases)]
        folded = fold(text)
        for ent in self.bible.entities:
            if ent.kind != "person":
                continue
            for alias in dict.fromkeys((ent.alias_en, ent.alias_vi)):
                key = _fold_key(alias)
                if key and _word_pattern(key).search(folded):
                    out.append(f"ghi tên nhân vật '{alias}' (tả bằng ngoại hình, không ghi tên)")
                    break
        return out

    def narration(self, text: str, lang: str) -> list[str]:
        issues = self.real_names(text, lang) + self.dates(text)
        if lang == "en":
            issues += self.vi_forms_in_en(text)
        return issues


def _raise_if_problems(problems: list[str], soft: list[str], value: Any) -> Any:
    """Lỗi nặng thì StepRejected (kèm cả lỗi nhẹ để model sửa một lần); chỉ có lỗi nhẹ thì SoftRejected."""
    if problems:
        raise StepRejected("; ".join(problems + soft))
    if soft:
        raise SoftRejected("; ".join(soft), value)
    return value


class _ScenesOutput(_Item):
    """Kết quả dạng {"scenes": [...]}; model trả thẳng một mảng thì cũng nhận."""

    @model_validator(mode="before")
    @classmethod
    def wrap_list(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"scenes": data}
        return data


# ---------------------------------------------------------------- G5: dàn ý

_PART_KIND_SYNONYMS = {
    "opening": "hook", "intro": "hook", "teaser": "hook", "cold_open": "hook", "mở_đầu": "hook",
    "background": "setup", "setting": "setup", "context": "setup", "bối_cảnh": "setup",
    "discover": "discovery", "the_discovery": "discovery", "phát_hiện": "discovery",
    "investigate": "investigation", "điều_tra": "investigation",
    "turning_point": "twist", "climax": "twist", "bước_ngoặt": "twist",
    "solution": "resolution", "solved": "resolution", "arrest": "resolution", "trial": "resolution",
    "phá_án": "resolution",
    "unsolved": "open_questions", "open_question": "open_questions", "questions": "open_questions",
    "mystery": "open_questions",
    "aftermath": "epilogue", "ending": "epilogue", "conclusion": "epilogue", "outro": "epilogue", "kết": "epilogue",
}


class _OutlinePart(_Item):
    id: str = ""
    kind: str
    summary_vi: str = ""
    event_ids: list[str] = []
    scene_count: int

    @field_validator("event_ids", mode="before")
    @classmethod
    def split_ids(cls, value: Any) -> Any:
        return _as_list(value)


class _OutlineOutput(_Item):
    supported_minutes: int
    parts: list[_OutlinePart]


def _repeated_event_problems(drafts: list[tuple[str, str, list[str], int]]) -> list[str]:
    """Mỗi sự việc thuộc đúng một nhịp; riêng nhịp hook được mượn trước tối đa 1 sự việc của một nhịp khác.
    `drafts`: (kind, summary, event_ids, scene_count) theo thứ tự nhịp."""
    owners: dict[str, list[int]] = {}
    for n, (_kind, _summary, ids, _count) in enumerate(drafts, start=1):
        for event_id in ids:
            owners.setdefault(event_id, []).append(n)
    kinds = {n: draft[0] for n, draft in enumerate(drafts, start=1)}
    borrowed: dict[int, list[str]] = {}
    repeated: list[str] = []
    for event_id, where in owners.items():
        if len(where) < 2:
            continue
        hooks = [n for n in where if kinds[n] == "hook"]
        if len(where) == 2 and len(hooks) == 1:
            borrowed.setdefault(hooks[0], []).append(event_id)
        else:
            repeated.append(f"{event_id} (nhịp {', '.join(map(str, where))})")
    problems = []
    for n, events in borrowed.items():
        if len(events) > 1:
            problems.append(f"Nhịp {n} (hook) mượn trước {len(events)} sự việc của nhịp khác ({_id_list(events)}); "
                            "nhịp hook chỉ được mượn tối đa 1 sự việc")
    if repeated:
        problems.append(f"Các sự việc sau nằm trong nhiều nhịp: {_id_list(repeated)}. Mỗi sự việc chỉ thuộc đúng một "
                        "nhịp, không kể lại để độn cảnh (riêng nhịp hook được mượn trước 1 sự việc)")
    return problems


def _too_few_scenes_problem(total: int, n_events: int, supported: int, target_minutes: int,
                            target: tuple[int, int], video_cap: int) -> str:
    """Lý do khi bài nhận đủ tư liệu (supported ≥ target) mà dàn ý ít cảnh hơn mục tiêu. Nếu số sự việc không cho
    phép đạt mục tiêu (mỗi sự việc tối đa 2 cảnh) thì bảo hạ supported_minutes, không bảo thêm cảnh."""
    lo, hi = target
    have = f"Tổng số cảnh chỉ có {total} ({total + 1} kể cả cảnh miễn trừ)"
    reachable = min(MAX_SCENES_PER_EVENT * n_events, video_cap - 1)
    if reachable + 1 < lo:
        honest = max(1, min(reachable // SCENES_PER_MINUTE, target_minutes - 1))
        return (f"{have}, trong khi supported_minutes = {supported} (≥ {target_minutes} phút) thì video cần ít nhất "
                f"{lo} cảnh. Bài có {n_events} sự việc nên dàn ý tối đa {reachable} cảnh (mỗi sự việc tối đa "
                f"{MAX_SCENES_PER_EVENT} cảnh, {reachable + 1} cảnh kể cả cảnh miễn trừ), vẫn ít hơn {lo}: tư liệu "
                f"không đủ cho {target_minutes} phút. Hãy hạ supported_minutes xuống mức tư liệu thật sự đủ "
                f"(khoảng {honest} phút) thay vì thêm cảnh, rồi giữ số cảnh vừa với số phút đó")
    return (f"{have}, trong khi supported_minutes = {supported} (≥ {target_minutes} phút) thì dàn ý cần từ {lo - 1} "
            f"đến {hi - 1} cảnh ({lo}–{hi} cảnh kể cả cảnh miễn trừ). Hãy tăng scene_count của các nhịp (mỗi sự việc "
            f"tối đa {MAX_SCENES_PER_EVENT} cảnh, dàn ý tối đa {reachable} cảnh), hoặc hạ supported_minutes nếu "
            "tư liệu không đủ")


def _validate_outline(raw: Any, bible: CaseBible, target_minutes: int) -> dict:
    parsed = _OutlineOutput.model_validate(raw)
    lo, hi = target_scenes(target_minutes)
    video_cap = video_scene_cap(hi)                     # cả video, kể cả cảnh miễn trừ
    min_part, max_part = SCENES_PER_PART
    known = [ev.id for ev in bible.timeline]
    known_set = set(known)
    # Bài có quá nhiều sự việc so với số cảnh tối đa thì mỗi cảnh buộc phải kể nhiều hơn.
    per_scene = max_events_per_scene(len(known), hi)
    forbidden = build_forbidden_names(bible, "")
    problems: list[str] = []

    if parsed.supported_minutes < 1:
        problems.append('"supported_minutes" phải là số nguyên từ 1 trở lên')
    if not parsed.parts:
        problems.append("Dàn ý không có nhịp nào")
    covered: set[str] = set()
    drafts = []
    for n, item in enumerate(parsed.parts, start=1):
        kind = _PART_KIND_SYNONYMS.get(_norm_token(item.kind), _norm_token(item.kind))
        if kind not in PART_KINDS:
            problems.append(f"Nhịp {n}: kind '{item.kind}' không hợp lệ; chỉ dùng một trong {' | '.join(PART_KINDS)}")
        elif kind == "resolution" and not bible.solved:
            kind = "open_questions"            # vụ chưa phá được: không có nhịp "phá án" (spec 7.3)
        ids = _clean_ids(item.event_ids)
        unknown = [e for e in ids if e not in known_set]
        if unknown:
            problems.append(f"Nhịp {n} có id sự việc không có trong dòng thời gian: {_id_list(unknown)}. "
                            "Chỉ dùng id có trong danh sách")
        ids = [e for e in ids if e in known_set]
        if known and not ids:
            problems.append(f"Nhịp {n} không có sự việc nào; mỗi nhịp phải kể ít nhất một sự việc")
        if not min_part <= item.scene_count <= max_part:
            problems.append(f"Nhịp {n} có scene_count = {item.scene_count}; mỗi nhịp phải có từ {min_part} đến "
                            f"{max_part} cảnh")
        elif len(ids) > item.scene_count * per_scene:
            need = math.ceil(len(ids) / per_scene)
            problems.append(f"Nhịp {n} có {len(ids)} sự việc mà chỉ {item.scene_count} cảnh; mỗi cảnh kể tối đa "
                            f"{per_scene} sự việc, nên cần ít nhất {need} cảnh hoặc tách thành nhiều nhịp")
        elif ids and item.scene_count > MAX_SCENES_PER_EVENT * len(ids):
            most = max(min_part, MAX_SCENES_PER_EVENT * len(ids))
            problems.append(f"Nhịp {n} có {len(ids)} sự việc mà tới {item.scene_count} cảnh; mỗi sự việc đủ cho tối đa "
                            f"{MAX_SCENES_PER_EVENT} cảnh, nên nhịp này tối đa {most} cảnh. Không kéo dài cho đủ số cảnh")
        covered.update(ids)
        summary, _replaced = apply_aliases(item.summary_vi, forbidden, "vi")
        drafts.append((kind, summary, ids, item.scene_count))

    missing = [e for e in known if e not in covered]
    if missing:
        problems.append(f"Có {len(missing)} sự việc chưa nằm trong nhịp nào: {_id_list(missing)}. "
                        "Mọi sự việc phải nằm trong đúng một nhịp")
    problems += _repeated_event_problems(drafts)
    total = sum(item.scene_count for item in parsed.parts)
    if total + 1 > video_cap:
        problems.append(f"Tổng số cảnh là {total} ({total + 1} kể cả cảnh miễn trừ), vượt mức tối đa {video_cap} cảnh "
                        f"của video {target_minutes} phút; dàn ý tối đa {video_cap - 1} cảnh")
    elif parsed.supported_minutes < target_minutes and total > supported_scene_cap(parsed.supported_minutes):
        problems.append(f"Bài chỉ đủ tư liệu cho {parsed.supported_minutes} phút nên tổng số cảnh tối đa "
                        f"{supported_scene_cap(parsed.supported_minutes)} cảnh, nhưng dàn ý có {total} cảnh. "
                        "Không kéo dài cho đủ số cảnh; bớt cảnh, hoặc ước lại supported_minutes cho đúng lượng tư liệu")
    elif total + 1 < lo and parsed.supported_minutes >= target_minutes:
        problems.append(_too_few_scenes_problem(total, len(known), parsed.supported_minutes, target_minutes,
                                                (lo, hi), video_cap))
    if problems:
        raise StepRejected("; ".join(problems))

    parts = [StoryPart(id=f"p{n}", kind=kind, summary_vi=summary, event_ids=ids, scene_count=count)
             for n, (kind, summary, ids, count) in enumerate(drafts, start=1)]
    return CaseOutline(supported_minutes=parsed.supported_minutes, parts=parts).model_dump()


def _story_steps(parts: list[StoryPart]) -> list[PipelineStep]:
    """Theo thứ tự nhịp: lời Việt → lời Anh → prompt hình; cuối cùng là ráp kế hoạch."""
    steps = []
    for part in parts:
        for kind in ("write_vi", "write_en", "write_prompts"):
            steps.append(PipelineStep(id=_part_step_id(kind, part.id), kind=kind, params={"part_id": part.id}))
    steps.append(PipelineStep(id="assemble", kind="assemble"))
    return steps


async def _run_outline(pipeline: CasePipeline, step: PipelineStep, llm: LLMCall) -> StepResult:
    label = "lập dàn ý"
    bible = _load_bible(pipeline, label)
    minutes = pipeline.target_minutes
    output = await ask_validated(
        outline_prompt(bible, minutes, target_scenes(minutes)),
        lambda raw: _validate_outline(raw, bible, minutes),
        llm=llm, temperature=_TEMPERATURE_OUTLINE, step_label=label,
    )
    parts = [StoryPart.model_validate(p) for p in output["parts"]]
    return StepResult(output=output, new_steps=_story_steps(parts))


# ---------------------------------------------------------------- G6: viết cảnh theo nhịp

@dataclass
class _PartContext:
    bible: CaseBible
    outline: CaseOutline
    part: StoryPart
    index: int            # vị trí của nhịp trong dàn ý (0-based)
    label: str            # ví dụ "viết lời Việt (nhịp 1/2)"

    @property
    def position(self) -> tuple[int, int]:
        return self.index + 1, len(self.outline.parts)


def _part_context(pipeline: CasePipeline, step: PipelineStep, what: str) -> _PartContext:
    part_id = str(step.params.get("part_id", ""))
    base = f"viết {what}"
    bible = _load_bible(pipeline, base)
    outline = _load_outline(pipeline, base)
    index = next((i for i, p in enumerate(outline.parts) if p.id == part_id), None)
    if index is None:
        raise StepFailed(f"Bước {base} thất bại: dàn ý không có nhịp '{part_id}'.")
    label = f"{base} (nhịp {index + 1}/{len(outline.parts)})"
    return _PartContext(bible, outline, outline.parts[index], index, label)


def _part_events(ctx: _PartContext) -> list[TimelineEvent]:
    by_id = {ev.id: ev for ev in ctx.bible.timeline}
    return [by_id[e] for e in ctx.part.event_ids if e in by_id]


def _part_chunks(pipeline: CasePipeline, ctx: _PartContext) -> list[str]:
    """Toàn văn các đoạn gốc chứa sự việc của nhịp, theo thứ tự đoạn."""
    chunks = case_store.load_chunks(pipeline.case_id) or []
    indices = sorted({ev.chunk_index for ev in _part_events(ctx)})
    if any(not 0 <= i < len(chunks) for i in indices):
        raise StepFailed(f"Bước {ctx.label} thất bại: thiếu đoạn gốc của các sự việc trong nhịp.")
    return [chunks[i] for i in indices]


def _source_text(pipeline: CasePipeline) -> str:
    return case_store.load_source(pipeline.case_id) or ""


class _VIScene(_Item):
    narration_vi: str
    visual_kind: str = "image"
    board_reveal: list[str] = []
    covers_event_ids: list[str] = []

    @field_validator("board_reveal", "covers_event_ids", mode="before")
    @classmethod
    def split_ids(cls, value: Any) -> Any:
        return _as_list(value)


class _VIOutput(_ScenesOutput):
    scenes: list[_VIScene]


_VISUAL_SYNONYMS = {
    "photo": "image", "still": "image", "picture": "image", "illustration": "image", "disclaimer": "image",
    "clip": "video", "motion": "video", "action": "video", "animation": "video",
    "evidence": "board", "evidence_board": "board", "corkboard": "board", "investigation_board": "board",
}


def _norm_visual(value: Any) -> str:
    key = _VISUAL_SYNONYMS.get(_norm_token(value), _norm_token(value))
    return key if key in VISUAL_KINDS else "image"


def _validate_write_vi(raw: Any, ctx: _PartContext, guard: _TextGuard) -> dict:
    parsed = _VIOutput.model_validate(raw)
    n = ctx.part.scene_count
    lo, hi = VI_WORDS
    board_ids = {e.id for e in ctx.bible.evidence} | {r.id for r in ctx.bible.relations}
    part_events = set(ctx.part.event_ids)
    per_scene = max_events_per_scene(len(ctx.part.event_ids), n)
    problems: list[str] = []
    soft: list[str] = []
    if len(parsed.scenes) != n:
        problems.append(f"Có {len(parsed.scenes)} cảnh, cần đúng {n} cảnh")
    covered: set[str] = set()
    scenes = []
    for k, scene in enumerate(parsed.scenes, start=1):
        words = word_count(scene.narration_vi)
        if not lo <= words <= hi:
            problems.append(f"cảnh {k}: narration_vi dài {words} từ, cần từ {lo} đến {hi} từ")
        reveal = _clean_ids(scene.board_reveal)
        unknown = [r for r in reveal if r not in board_ids]
        if unknown:
            problems.append(f"cảnh {k}: board_reveal có id không có trong danh sách bằng chứng/quan hệ: "
                            f"{_id_list(unknown)}")
        # Chỉ tính sự việc của nhịp này; mỗi cảnh phải kể 1..per_scene sự việc, để không dồn hết vào một cảnh.
        covers = [e for e in _clean_ids(scene.covers_event_ids) if e in part_events]
        if not covers:
            problems.append(f"cảnh {k}: covers_event_ids không có sự việc nào của nhịp; mỗi cảnh phải kể ít nhất 1 "
                            f"sự việc của nhịp")
        elif len(covers) > per_scene:
            problems.append(f"cảnh {k}: covers_event_ids có {len(covers)} sự việc, mỗi cảnh kể tối đa {per_scene} "
                            "sự việc; hãy chia các sự việc cho các cảnh theo thứ tự")
        covered.update(covers)
        soft += [f"cảnh {k} {issue}" for issue in guard.narration(scene.narration_vi, "vi")]
        scenes.append({"narration_vi": scene.narration_vi, "visual_kind": _norm_visual(scene.visual_kind),
                       "board_reveal": reveal, "covers_event_ids": covers})
    missing = [e for e in ctx.part.event_ids if e not in covered]
    if missing:
        problems.append(f"Các sự việc sau chưa được kể ở cảnh nào (covers_event_ids gộp lại còn thiếu): "
                        f"{_id_list(missing)}. Mọi sự việc của nhịp phải được kể")
    return _raise_if_problems(problems, soft, {"scenes": scenes})


async def _run_write_vi(pipeline: CasePipeline, step: PipelineStep, llm: LLMCall) -> StepResult:
    ctx = _part_context(pipeline, step, "lời Việt")
    previous = [_part_output(pipeline, "write_vi", p.id, ctx.label) for p in ctx.outline.parts[:ctx.index]]
    prev_scenes = previous[-1][-_PREV_SCENES:] if previous else []
    revealed = [r for scenes in previous for s in scenes for r in s.get("board_reveal", [])]
    guard = _TextGuard(ctx.bible, _source_text(pipeline))
    output = await ask_validated(
        write_vi_prompt(ctx.bible, ctx.part, _part_events(ctx), _part_chunks(pipeline, ctx), prev_scenes,
                        part_position=ctx.position, revealed_ids=revealed),
        lambda raw: _validate_write_vi(raw, ctx, guard),
        llm=llm, temperature=_TEMPERATURE_VI, step_label=ctx.label,
    )
    return StepResult(output=output)


class _ENScene(_Item):
    narration_en: str


class _ENOutput(_ScenesOutput):
    scenes: list[_ENScene]


def _check_en_words(text: str, where: str) -> list[str]:
    lo, hi = EN_WORDS
    words = word_count(text)
    return [] if lo <= words <= hi else [f"{where}: narration_en dài {words} từ, cần từ {lo} đến {hi} từ"]


def _validate_write_en(raw: Any, n: int, guard: _TextGuard) -> dict:
    parsed = _ENOutput.model_validate(raw)
    problems: list[str] = []
    soft: list[str] = []
    if len(parsed.scenes) != n:
        problems.append(f"Có {len(parsed.scenes)} cảnh, cần đúng {n} cảnh, mỗi cảnh tiếng Việt một cảnh tiếng Anh")
    for k, scene in enumerate(parsed.scenes, start=1):
        problems += _check_en_words(scene.narration_en, f"cảnh {k}")
        soft += [f"cảnh {k} {issue}" for issue in guard.narration(scene.narration_en, "en")]
    return _raise_if_problems(problems, soft, {"scenes": [{"narration_en": s.narration_en} for s in parsed.scenes]})


async def _run_write_en(pipeline: CasePipeline, step: PipelineStep, llm: LLMCall) -> StepResult:
    ctx = _part_context(pipeline, step, "lời Anh")
    vi_scenes = _part_output(pipeline, "write_vi", ctx.part.id, ctx.label)
    guard = _TextGuard(ctx.bible, _source_text(pipeline))
    output = await ask_validated(
        write_en_prompt(ctx.bible, ctx.part, vi_scenes, _part_chunks(pipeline, ctx), part_position=ctx.position),
        lambda raw: _validate_write_en(raw, len(vi_scenes), guard),
        llm=llm, temperature=_TEMPERATURE_EN, step_label=ctx.label,
    )
    return StepResult(output=output)


class _PromptScene(_Item):
    image_prompt: str = ""
    video_prompt: str = ""
    camera_motion: str = "zoom_in"
    narrative_beat: str = ""
    sfx_cue: list[str] = []
    bgm_energy: str = ""

    @field_validator("sfx_cue", mode="before")
    @classmethod
    def split_cues(cls, value: Any) -> Any:
        return _as_list(value)


class _PromptsOutput(_ScenesOutput):
    scenes: list[_PromptScene]


_BEAT_BY_KIND = {
    "hook": "hook", "setup": "setting", "discovery": "escalation", "investigation": "escalation",
    "twist": "climax", "resolution": "resolution", "open_questions": "resolution", "epilogue": "resolution",
}


def _validate_write_prompts(raw: Any, ctx: _PartContext, vi_scenes: list[dict], guard: _TextGuard) -> dict:
    parsed = _PromptsOutput.model_validate(raw)
    n = len(vi_scenes)
    problems: list[str] = []
    soft: list[str] = []
    if len(parsed.scenes) != n:
        problems.append(f"Có {len(parsed.scenes)} cảnh, cần đúng {n} cảnh")
    scenes = []
    for k, (scene, vi) in enumerate(zip(parsed.scenes, vi_scenes), start=1):
        words = word_count(scene.image_prompt)
        if words < MIN_IMAGE_PROMPT_WORDS:
            problems.append(f"cảnh {k}: image_prompt chỉ có {words} từ, cần ít nhất {MIN_IMAGE_PROMPT_WORDS} từ")
        if vi.get("visual_kind") == "video" and word_count(scene.video_prompt) < MIN_VIDEO_PROMPT_WORDS:
            problems.append(f"cảnh {k} là cảnh video nhưng thiếu video_prompt (hoặc quá ngắn, cần ít nhất "
                            f"{MIN_VIDEO_PROMPT_WORDS} từ tả chuyển động trong 5 giây)")
        for field_name in ("image_prompt", "video_prompt"):
            soft += [f"cảnh {k} ({field_name}) {issue}" for issue in guard.names_in_prompt(getattr(scene, field_name))]
        beat = _norm_token(scene.narrative_beat)
        energy = _norm_token(scene.bgm_energy)
        scenes.append({
            "image_prompt": scene.image_prompt,
            "video_prompt": scene.video_prompt,
            "camera_motion": _norm_token(scene.camera_motion) or "zoom_in",
            "narrative_beat": beat if beat in NARRATIVE_BEATS else _BEAT_BY_KIND.get(ctx.part.kind, "setting"),
            "sfx_cue": [c.strip() for c in scene.sfx_cue if isinstance(c, str) and c.strip()][:3],
            "bgm_energy": energy if energy in BGM_ENERGIES else "tension_buildup",
        })
    return _raise_if_problems(problems, soft, {"scenes": scenes})


async def _run_write_prompts(pipeline: CasePipeline, step: PipelineStep, llm: LLMCall) -> StepResult:
    ctx = _part_context(pipeline, step, "prompt hình")
    vi_scenes = _part_output(pipeline, "write_vi", ctx.part.id, ctx.label)
    en_scenes = _part_output(pipeline, "write_en", ctx.part.id, ctx.label)
    if len(en_scenes) != len(vi_scenes):
        raise StepFailed(f"Bước {ctx.label} thất bại: lời Việt có {len(vi_scenes)} cảnh nhưng lời Anh có "
                         f"{len(en_scenes)} cảnh.")
    scenes = [{**vi, "narration_en": en.get("narration_en", "")} for vi, en in zip(vi_scenes, en_scenes)]
    guard = _TextGuard(ctx.bible, _source_text(pipeline))
    output = await ask_validated(
        prompts_prompt(ctx.bible, ctx.part, scenes, pipeline.visual_style, part_position=ctx.position),
        lambda raw: _validate_write_prompts(raw, ctx, vi_scenes, guard),
        llm=llm, temperature=_TEMPERATURE_PROMPTS, step_label=ctx.label,
    )
    return StepResult(output=output)


# ---------------------------------------------------------------- G7: ráp kế hoạch

def _disclaimer_scene() -> AdaptedScene:
    """Cảnh 1: câu miễn trừ cố định trong code, không do LLM viết (spec 7.3)."""
    return AdaptedScene(
        order=1, part_id="disclaimer", narration_vi=DISCLAIMER["vi"], narration_en=DISCLAIMER["en"],
        visual_kind="disclaimer", camera_motion="static", narrative_beat="hook", bgm_energy="ambient_low",
    )


def _cap_videos(scenes: list[AdaptedScene]) -> None:
    """Giữ tối đa floor(MAX_VIDEO_RATIO × số cảnh) cảnh video, rải đều theo thứ tự; phần dư thành image
    (giữ video_prompt để người dùng có thể đổi lại)."""
    limit = math.floor(MAX_VIDEO_RATIO * len(scenes) + 1e-9)
    videos = [i for i, s in enumerate(scenes) if s.visual_kind == "video"]
    if len(videos) <= limit:
        return
    keep = {videos[(k * len(videos)) // limit] for k in range(limit)}
    for i in videos:
        if i not in keep:
            scenes[i].visual_kind = "image"


async def _run_assemble(pipeline: CasePipeline, step: PipelineStep, llm: LLMCall) -> StepResult:
    label = "ráp kế hoạch"
    bible = _load_bible(pipeline, label)
    outline = _load_outline(pipeline, label)
    motions = set(video_service.CAMERA_MOTIONS)
    scenes = [_disclaimer_scene()]
    for part in outline.parts:
        vi = _part_output(pipeline, "write_vi", part.id, label)
        en = _part_output(pipeline, "write_en", part.id, label)
        pr = _part_output(pipeline, "write_prompts", part.id, label)
        if not len(vi) == len(en) == len(pr):
            raise StepFailed(f"Bước {label} thất bại: nhịp {part.id} có {len(vi)} cảnh lời Việt, {len(en)} cảnh "
                             f"lời Anh và {len(pr)} cảnh prompt hình; số cảnh phải bằng nhau.")
        for v, e, p in zip(vi, en, pr):
            camera = p.get("camera_motion")
            data = {
                **{k: v[k] for k in ("narration_vi", "visual_kind", "board_reveal", "covers_event_ids") if k in v},
                "narration_en": e.get("narration_en", ""),
                **{k: p[k] for k in ("image_prompt", "video_prompt", "narrative_beat", "sfx_cue", "bgm_energy")
                   if k in p},
                "camera_motion": camera if camera in motions else "zoom_in",
                "order": len(scenes) + 1, "part_id": part.id,
            }
            scenes.append(_parse_model(AdaptedScene, data, label, f"viết cảnh của nhịp {part.id}"))
    _cap_videos(scenes)

    warnings = []
    if outline.supported_minutes < pipeline.target_minutes:
        warnings.append(SHORT_MATERIAL_WARNING.format(n=outline.supported_minutes, m=pipeline.target_minutes))
    plan = CaseAdaptationPlan(
        case_id=pipeline.case_id, created_at=datetime.now(timezone.utc).isoformat(),
        model=config.NINEROUTER_LLM_MODEL, target_minutes=pipeline.target_minutes,
        visual_style=pipeline.visual_style, bible=bible, parts=outline.parts, scenes=scenes, warnings=warnings,
    )
    plan = check_plan(plan, _source_text(pipeline))
    case_store.save_plan(plan)
    return StepResult(output={"case_id": pipeline.case_id})


# ---------------------------------------------------------------- viết lại lời Anh cho cảnh đã sửa

class _RewriteScene(_Item):
    order: int
    narration_en: str


class _RewriteOutput(_ScenesOutput):
    scenes: list[_RewriteScene]


def _validate_rewrite(raw: Any, orders: list[int], guard: _TextGuard) -> dict[int, str]:
    parsed = _RewriteOutput.model_validate(raw)
    found: dict[int, str] = {}
    for scene in parsed.scenes:
        found.setdefault(scene.order, scene.narration_en)
    problems: list[str] = []
    soft: list[str] = []
    missing = [o for o in orders if o not in found]
    if missing:
        problems.append(f"Thiếu lời Anh cho cảnh order {', '.join(map(str, missing))}; mỗi cảnh được giao phải có "
                        "đúng một phần tử với đúng order")
    result = {o: found[o] for o in orders if o in found}
    for order, text in result.items():
        problems += _check_en_words(text, f"order {order}")
        soft += [f"order {order} {issue}" for issue in guard.narration(text, "en")]
    return _raise_if_problems(problems, soft, result)


async def rewrite_english(bible: CaseBible, items: list[tuple[int, str]], *,
                          llm: Optional[LLMCall] = None) -> dict[int, str]:
    """Viết lại lời Anh cho các cảnh (order, lời Việt) vừa thêm hoặc sửa; trả {order: lời Anh}.
    Không có cảnh nào thì không gọi LLM. Hỏng thì StepFailed với tên việc "viết lại lời Anh"."""
    items = [(int(order), str(text)) for order, text in items]
    if not items:
        return {}
    orders = list(dict.fromkeys(order for order, _text in items))
    guard = _TextGuard(bible)
    return await ask_validated(
        rewrite_en_prompt(bible, items),
        lambda raw: _validate_rewrite(raw, orders, guard),
        llm=llm if llm is not None else case_adaptation_llm.call_llm_json,
        temperature=_TEMPERATURE_EN, step_label="viết lại lời Anh",
    )


# ---------------------------------------------------------------- phân việc

_HANDLERS = {
    "extract_chunk": _run_extract,
    "cluster_names": _run_cluster,
    "assign_aliases": _run_aliases,
    "build_outline": _run_outline,
    "write_vi": _run_write_vi,
    "write_en": _run_write_en,
    "write_prompts": _run_write_prompts,
    "assemble": _run_assemble,
}


async def run_step(pipeline: CasePipeline, step: PipelineStep, *, llm: Optional[LLMCall] = None) -> StepResult:
    """Chạy một việc của hàng việc. Không truyền `llm` thì dùng case_adaptation_llm.call_llm_json (lấy lúc gọi)."""
    handler = _HANDLERS.get(step.kind)
    if handler is None:
        raise StepFailed(f"Chưa hỗ trợ loại việc '{step.kind}' (việc {step.id}).")
    return await handler(pipeline, step, llm if llm is not None else case_adaptation_llm.call_llm_json)
