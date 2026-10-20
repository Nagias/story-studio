"""
Sửa kế hoạch chuyển thể sau khi phân tích xong (spec 7.8): bảng tên và lời kể từng cảnh.

Mỗi thao tác đọc plan.json, sửa, chạy lại check_plan (tự thay tên thật đã có tên hư cấu, đánh dấu phần còn lại) rồi ghi
lại. Cả chuỗi đó nằm trong một khoá chung nên hai yêu cầu sửa chồng nhau không ghi đè nhau. Đây là hàm chặn (đọc ghi
đĩa): router gọi qua asyncio.to_thread.

- edit_entities: đổi tên hư cấu của thực thể có sẵn và/hoặc thêm thực thể mới (thường là tên mà regex bắt được trên bài
  gốc). Tên hư cấu cũ được thay bằng tên mới trong mọi chữ của kế hoạch theo ranh giới từ, một lượt duy nhất (đổi chỗ
  hai tên cho nhau không bị thay chồng), và không thay chỗ nằm trong một tên hư cấu dài hơn của thực thể khác.
  Chỗ khớp phải qua cùng quy tắc với phần kiểm lọt tên (case_adaptation_checks.accept_match): "Năm ấy" không phải tên
  "Nam", "Hung thủ" không phải tên "Hùng".
  Tên thật mới thêm chỉ bị từ chối khi trùng cách viết giữ dấu của một tên thật có sẵn: "Nguyễn Văn Hưng" thêm được
  khi đã có "Nguyễn Văn Hùng" (hai người khác nhau), "NGUYỄN VĂN HÙNG" thì không.
- edit_scene: sửa lời kể Việt và/hoặc Anh của một cảnh.
- Thông báo lỗi chỉ nêu id thực thể, số mục và order cảnh; không bao giờ nêu tên thật hay chữ người dùng vừa nhập.
"""
import threading
import unicodedata
from typing import Literal, Optional, Sequence

from pydantic import BaseModel, Field

from models.case_adaptation_schemas import CaseAdaptationPlan, CaseEntity, Lang
from services import case_store
from services.case_adaptation_checks import build_forbidden_names, check_plan, find_names, fold, spelling_key
from services.case_worker import CaseNotFoundError

_LOCK = threading.RLock()
MAX_ALIAS_CHARS = 120
MAX_REAL_NAMES = 20

NOT_READY = "Đang phân tích, chưa có kế hoạch."
NOT_READY_FAILED = "Phân tích bị dừng, chưa có kế hoạch. Bấm Thử lại để chạy tiếp."


class PlanNotReadyError(Exception):
    """Vụ án có hàng việc nhưng chưa có plan.json (còn đang phân tích, hoặc phân tích bị dừng)."""

    def __init__(self, failed: bool = False):
        self.failed = failed
        self.message = NOT_READY_FAILED if failed else NOT_READY
        super().__init__(self.message)


class PlanEditError(ValueError):
    """Yêu cầu sửa không hợp lệ (API trả 400). Thông báo tiếng Việt, không nêu tên thật."""


class EntityUpdate(BaseModel):
    id: str = Field(max_length=64)
    alias_vi: str = Field(max_length=500)
    alias_en: str = Field(max_length=500)


class EntityAddition(BaseModel):
    kind: Literal["person", "place", "organization", "identifier"]
    real_names: list[str] = Field(max_length=100)
    alias_vi: str = Field(max_length=500)
    alias_en: str = Field(max_length=500)


def load_ready_plan(case_id: str) -> CaseAdaptationPlan:
    """Kế hoạch đã lưu. Không có vụ án thì CaseNotFoundError; chưa có kế hoạch thì PlanNotReadyError."""
    plan = case_store.load_plan(case_id)
    if plan is not None:
        return plan
    pipeline = case_store.load_pipeline(case_id)
    if pipeline is None:
        raise CaseNotFoundError(f"Không tìm thấy vụ án {case_id}.")
    raise PlanNotReadyError(failed=pipeline.status == "failed")


# ---------------------------------------------------------------- thay tên hư cấu

def _key(text: str) -> str:
    """Dạng so khớp: chữ thường, bỏ dấu, khoảng trắng gộp thành một dấu cách (như case_adaptation_checks)."""
    return " ".join(fold(text).split())


def _clean_text(value: str, what: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if not text:
        raise PlanEditError(f"{what} đang để trống.")
    if len(text) > limit:
        raise PlanEditError(f"{what} dài quá {limit} ký tự.")
    return text


class _AliasSwap:
    """Đổi tên hư cấu cũ thành mới cho một ngôn ngữ, một lượt duy nhất trên mỗi chuỗi.

    `table`: cách viết giữ dấu của tên (spelling_key) -> (tên như đã viết, chữ thay thế hoặc None nếu chỉ để giữ nguyên).
    Mọi tên hư cấu hiện có (cả hai ngôn ngữ, cả thực thể không đổi) đều có trong bảng: chỗ khớp tên dài hơn mà thực thể
    khác sở hữu thắng, nên tên ngắn nằm trong đó không bị thay giữa chừng. Chỗ khớp tìm bằng find_names, tức cùng quy tắc
    accept_match với phần kiểm lọt tên."""

    def __init__(self, table: dict[str, tuple[str, Optional[str]]]):
        self.names = [name for name, _replacement in table.values()]
        self.replacements = [replacement for _name, replacement in table.values()]

    def __call__(self, text: str) -> str:
        if not text or not self.names:
            return text
        norm = unicodedata.normalize("NFC", text)
        parts: list[str] = []
        last = 0
        for start, end, index in find_names(norm, self.names):
            replacement = self.replacements[index]
            if replacement is None:
                continue
            parts.append(norm[last:start])
            parts.append(replacement)
            last = end
        if not parts:
            return text
        parts.append(norm[last:])
        return "".join(parts)


def _swaps(old: list[CaseEntity], changed: dict[str, CaseEntity]) -> dict[Lang, _AliasSwap]:
    """Bảng thay cho từng ngôn ngữ. Chữ của một ngôn ngữ có khi còn tên cũ ở dạng của ngôn ngữ kia ("Hùng" hay
    "Lý Tiểu Long" trong lời Anh, "Li Xiaolong" trong lời Việt): dạng đó cũng đổi sang tên mới của ngôn ngữ đang sửa.
    Trừ một trường hợp: dạng tiếng Anh trùng dạng Việt khi bỏ dấu ("Hung" của "Hùng") thì trong lời Việt nó là chữ
    tiếng Việt ("Hung hăng", "Lam lũ"), nên để nguyên."""
    tables: dict[Lang, dict[str, tuple[str, Optional[str]]]] = {"vi": {}, "en": {}}
    for ent in old:                                      # tên hiện có, để giữ nguyên
        for alias in (ent.alias_vi, ent.alias_en):
            if _key(alias):
                for table in tables.values():
                    table.setdefault(spelling_key(alias), (alias, None))
    renamed = [(ent, changed[ent.id]) for ent in old if ent.id in changed]
    for ent, new in renamed:                             # tên bị đổi: ghi đè lên mục giữ nguyên
        for lang, before, after in (("vi", ent.alias_vi, new.alias_vi), ("en", ent.alias_en, new.alias_en)):
            if before != after and _key(before):
                tables[lang][spelling_key(before)] = (before, after)
    for ent, new in renamed:                             # dạng của ngôn ngữ kia: chỉ lấp mục còn để giữ nguyên
        cross: list[tuple[Lang, str, str]] = [("en", ent.alias_vi, new.alias_en)]
        if _key(ent.alias_en) != _key(ent.alias_vi):
            cross.append(("vi", ent.alias_en, new.alias_vi))
        for lang, before, after in cross:
            spelled = spelling_key(before)
            if _key(before) and spelled != spelling_key(after) and tables[lang].get(spelled, ("", None))[1] is None:
                tables[lang][spelled] = (before, after)
    return {lang: _AliasSwap(table) for lang, table in tables.items()}


def _apply_swaps(plan: CaseAdaptationPlan, swaps: dict[Lang, _AliasSwap]) -> None:
    """Thay trong mọi chữ của kế hoạch có dùng tên hư cấu. Cảnh miễn trừ là câu cố định nên bỏ qua."""
    def fix(obj, field: str, lang: Lang) -> None:
        value = getattr(obj, field)
        if value:
            setattr(obj, field, swaps[lang](value))

    for scene in plan.scenes:
        if scene.visual_kind == "disclaimer":
            continue
        for field, lang in (("narration_vi", "vi"), ("narration_en", "en"), ("image_prompt", "en"),
                            ("video_prompt", "en")):
            fix(scene, field, lang)
    bible = plan.bible
    for field, lang in (("title_vi", "vi"), ("logline_vi", "vi"), ("title_en", "en"), ("logline_en", "en")):
        fix(bible, field, lang)
    for ev in bible.evidence:
        for field, lang in (("label_vi", "vi"), ("description_vi", "vi"), ("label_en", "en"), ("description_en", "en")):
            fix(ev, field, lang)
    for rel in bible.relations:
        fix(rel, "label_vi", "vi")
        fix(rel, "label_en", "en")
    for part in plan.parts:
        fix(part, "summary_vi", "vi")


# ---------------------------------------------------------------- sửa bảng tên

def _new_entity_id(kind: str, taken: set[str]) -> str:
    n = 1
    while f"{kind}_{n}" in taken:
        n += 1
    return f"{kind}_{n}"


def edit_entities(case_id: str, updates: Sequence[EntityUpdate], additions: Sequence[EntityAddition]) -> CaseAdaptationPlan:
    """Đổi tên hư cấu / thêm thực thể, áp cho toàn kế hoạch, chạy lại kiểm tra và lưu. Trả kế hoạch đã lưu."""
    if not updates and not additions:
        raise PlanEditError("Không có thay đổi nào để lưu.")
    with _LOCK:
        plan = load_ready_plan(case_id)
        source = case_store.load_source(case_id) or ""
        new = plan.model_copy(deep=True)
        entities = new.bible.entities
        by_id = {e.id: e for e in entities}
        labels: dict[str, str] = {}                      # id thực thể -> cách gọi trong thông báo lỗi
        changed: dict[str, CaseEntity] = {}              # id -> thực thể sau khi sửa (chỉ các mục sửa)

        seen: set[str] = set()
        for i, up in enumerate(updates, start=1):
            where = f"Mục sửa số {i}"
            ent = by_id.get(up.id)
            if ent is None:
                raise PlanEditError(f"{where}: không có thực thể nào với id đó trong bảng tên.")
            if up.id in seen:
                raise PlanEditError(f"{where}: id này đã xuất hiện ở một mục sửa trước đó.")
            seen.add(up.id)
            ent.alias_vi = _clean_text(up.alias_vi, f"{where}: alias_vi", MAX_ALIAS_CHARS)
            ent.alias_en = _clean_text(up.alias_en, f"{where}: alias_en", MAX_ALIAS_CHARS)
            labels[ent.id] = f"thực thể '{ent.id}'"
            changed[ent.id] = ent

        # So cách viết giữ dấu: "Nguyễn Văn Hưng" và "Nguyễn Văn Hùng" là hai người, thêm được; khác hoa thường thì không.
        real_spellings = {spelling_key(n) for e in entities for n in e.real_names}
        for j, add in enumerate(additions, start=1):
            where = f"Mục thêm số {j}"
            names = list(dict.fromkeys(_clean_text(n, f"{where}: một tên thật", MAX_ALIAS_CHARS)
                                       for n in add.real_names if n and n.strip()))
            if not names:
                raise PlanEditError(f"{where}: cần ít nhất một tên thật.")
            if len(names) > MAX_REAL_NAMES:
                raise PlanEditError(f"{where}: tối đa {MAX_REAL_NAMES} tên thật cho một thực thể.")
            if {spelling_key(n) for n in names} & real_spellings:
                raise PlanEditError(f"{where}: có tên thật đã thuộc một thực thể trong bảng tên.")
            real_spellings |= {spelling_key(n) for n in names}
            ent = CaseEntity(
                id=_new_entity_id(add.kind, set(by_id)), kind=add.kind, real_names=names, role="other",
                alias_vi=_clean_text(add.alias_vi, f"{where}: alias_vi", MAX_ALIAS_CHARS),
                alias_en=_clean_text(add.alias_en, f"{where}: alias_en", MAX_ALIAS_CHARS),
            )
            entities.append(ent)
            by_id[ent.id] = ent
            labels[ent.id] = where.lower()

        _check_names(entities, labels, build_forbidden_names(new.bible, source))

        old_entities = plan.bible.entities
        _apply_swaps(new, _swaps(old_entities, changed))
        return _save(new, source)


def _check_names(entities: list[CaseEntity], labels: dict[str, str], forbidden) -> None:
    """Tên hư cấu mới (của các thực thể vừa sửa hoặc thêm) không được trùng một tên thật, và không được trùng tên hư cấu
    của thực thể khác (kể cả khác hoa thường hay dấu). Tên thật mới thêm cũng không được trùng một tên hư cấu."""
    real_keys = {_key(f.real) for f in forbidden}
    alias_keys = {e.id: {k for k in (_key(e.alias_vi), _key(e.alias_en)) if k} for e in entities}
    for ent in entities:
        if ent.id not in labels:
            continue
        if alias_keys[ent.id] & real_keys:
            raise PlanEditError(f"Tên thay thế của {labels[ent.id]} trùng một tên thật trong hồ sơ. "
                                "Hãy đặt tên khác hẳn tên thật.")
        for other in entities:
            if other.id != ent.id and alias_keys[ent.id] & alias_keys[other.id]:
                raise PlanEditError(f"Tên thay thế của {labels[ent.id]} trùng tên thay thế của thực thể '{other.id}'. "
                                    "Mỗi thực thể cần một tên riêng.")
        own = {_key(n) for n in ent.real_names}
        clash = [o for o in entities if o.id != ent.id and own & alias_keys[o.id]]
        if clash:
            raise PlanEditError(f"Tên thật của {labels[ent.id]} trùng tên thay thế của thực thể '{clash[0].id}'.")


# ---------------------------------------------------------------- sửa lời kể

def edit_scene(case_id: str, order: int, narration_vi: Optional[str], narration_en: Optional[str]) -> CaseAdaptationPlan:
    """Sửa lời kể Việt và/hoặc Anh của cảnh `order` rồi chạy lại kiểm tra và lưu. Trả kế hoạch đã lưu."""
    if narration_vi is None and narration_en is None:
        raise PlanEditError("Không có lời kể nào để sửa.")
    with _LOCK:
        plan = load_ready_plan(case_id)
        source = case_store.load_source(case_id) or ""
        new = plan.model_copy(deep=True)
        scene = next((s for s in new.scenes if s.order == order), None)
        if scene is None:
            raise PlanEditError(f"Không có cảnh {order} trong kế hoạch.")
        if scene.visual_kind == "disclaimer":
            raise PlanEditError(f"Cảnh {order} là câu miễn trừ cố định, không sửa được.")
        if narration_vi is not None:
            scene.narration_vi = narration_vi.strip()
        if narration_en is not None:
            scene.narration_en = narration_en.strip()
        return _save(new, source)


def _save(plan: CaseAdaptationPlan, source: str) -> CaseAdaptationPlan:
    checked = check_plan(plan, source)
    case_store.save_plan(checked)
    return checked
