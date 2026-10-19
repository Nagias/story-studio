"""
Bộ chạy một việc nhỏ của hàng việc phân tích vụ án, cùng các việc G1–G4 (spec 7.1a, 7.2).

- ask_validated: gọi LLM một lần, kiểm kết quả bằng code; kết quả mỏng hoặc sai thì gọi lại, nối lý do bị loại
  vào cuối prompt; tối đa MAX_ATTEMPTS lần. Lỗi 9router không đáng thử lại (auth, no_credentials, http) thì
  dừng ngay. Hỏng thì raise StepFailed với thông báo tiếng Việt nêu đúng tên việc.
- chunk_source (G1): cắt bài theo đoạn văn (dòng trống, rồi tới xuống dòng); đoạn văn dài quá thì cắt theo câu,
  câu dài quá thì cắt ở khoảng trắng.
  Mỗi đoạn là một lát cắt nguyên văn của bài, nên nối lại không mất chữ nào.
- run_step: chạy một việc theo step.kind và trả StepResult. Không ghi kết quả; worker lưu
  StepResult.output vào steps/<step_id>.json rồi mới đánh dấu việc xong.
    * extract_chunk (G2): đọc một đoạn → tên, sự việc, bằng chứng, quan hệ;
    * cluster_names (G3): gộp các cách gọi khác nhau của cùng một đối tượng;
    * assign_aliases (G4): đặt tên hư cấu, văn hoá, tên tập, rồi ghép với kết quả G2 thành CaseBible.
- Hàm LLM mặc định lấy `case_adaptation_llm.call_llm_json` lúc gọi, để test và các task sau monkeypatch được.
"""
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from models.case_adaptation_schemas import (
    MAX_ATTEMPTS,
    CaseBible,
    CaseEntity,
    CaseEvidence,
    CasePipeline,
    CaseRelation,
    PipelineStep,
    TimelineEvent,
)
from services import case_adaptation_llm, case_store
from services.case_adaptation_checks import ForbiddenName, find_unknown_names, fold, is_kept_term
from services.case_adaptation_llm import RETRYABLE_KINDS, LLMCall, LLMError
from services.case_adaptation_prompts import (
    MIN_EVENT_WORDS,
    RELATION_TYPES,
    ROLES,
    SYSTEM_PROMPT,
    aliases_prompt,
    cluster_prompt,
    extract_prompt,
    min_events_for,
    word_count,
)

T = TypeVar("T")

RETRY_NOTE = "\n\nLẦN TRƯỚC BỊ LOẠI VÌ: {reason}. Hãy làm lại đầy đủ, không tóm gọn."
OPENING_EXCERPT_CHARS = 1500

_TEMPERATURE_EXTRACT = 0.2
_TEMPERATURE_CLUSTER = 0.1
_TEMPERATURE_ALIASES = 0.6
_MIN_APPEARANCE_WORDS = 8      # prompt xin ít nhất 12 từ; ngưỡng loại nới hơn để không loại oan
_MIN_SETTING_WORDS = 12        # prompt xin ít nhất 30 từ
_MAX_LISTED = 12               # số mục tối đa liệt kê trong một lý do bị loại
_INVALID_JSON_REASON = "kết quả không phải JSON hợp lệ; chỉ trả đúng một JSON object theo mẫu, không kèm chữ nào khác"


class StepRejected(Exception):
    """Kết quả của LLM không đạt; `reason` được gửi lại cho LLM ở lần thử sau."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


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
    - LLMError thuộc RETRYABLE_KINDS thì thử lại; loại khác (auth, no_credentials, http) thì StepFailed ngay.
    """
    reason: Optional[str] = None   # lý do gửi lại cho LLM
    problem = ""                   # lý do báo người dùng nếu hỏng cả MAX_ATTEMPTS lần
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
        except StepRejected as exc:
            reason = problem = exc.reason
        except ValidationError as exc:
            reason = problem = _schema_reason(exc)
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


def _looks_proper(name: str) -> bool:
    """Trông như tên riêng hay mã số. Không phải tên riêng:
    - không có chữ hoa hay chữ số nào ("cơ quan điều tra");
    - nhiều chữ mà chỉ chữ đầu viết hoa ("Cơ quan điều tra", "Lực lượng chức năng"): đó là chữ hoa đầu câu.
    Tên riêng nhiều chữ luôn viết hoa cả chữ sau ("ông Hùng", "Cảng Tân Hải", "TP Hải Phòng")."""
    tokens = name.split()
    if not tokens or not any(_has_capital(t) for t in tokens):
        return False
    return len(tokens) == 1 or any(_has_capital(t) for t in tokens[1:])


def _skip_name(name: str, kind: Optional[str] = None) -> bool:
    """Tên không cần tên hư cấu: không trông như tên riêng, hoặc là tên giữ nguyên (tên nước, danh từ chung chỉ
    cơ quan/vai trò; xem case_adaptation_checks.is_kept_term). Dùng chung cho danh sách tên và phần kiểm tên thiếu,
    để khớp đúng điều prompt đọc bài dặn model không liệt kê."""
    return not _looks_proper(name) or is_kept_term(name, kind)


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
    # nếu không thì tên đó không bao giờ được đặt tên hư cấu.
    index = _NameIndex()
    for n in [*known_names, *(item["name"] for item in names)]:
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


# ---------------------------------------------------------------- phân việc

_HANDLERS = {
    "extract_chunk": _run_extract,
    "cluster_names": _run_cluster,
    "assign_aliases": _run_aliases,
}


async def run_step(pipeline: CasePipeline, step: PipelineStep, *, llm: Optional[LLMCall] = None) -> StepResult:
    """Chạy một việc của hàng việc. Không truyền `llm` thì dùng case_adaptation_llm.call_llm_json (lấy lúc gọi)."""
    handler = _HANDLERS.get(step.kind)
    if handler is None:
        raise StepFailed(f"Chưa hỗ trợ loại việc '{step.kind}' (việc {step.id}).")
    return await handler(pipeline, step, llm if llm is not None else case_adaptation_llm.call_llm_json)
