"""
Kiểm lọt tên thật, ngày tháng cụ thể và tự áp tên hư cấu (G7, không dùng LLM).

- fold: chữ thường, bỏ dấu (đ thành d), giữ nguyên độ dài từng ký tự để đổi vị trí khớp về chuỗi gốc.
- apply_aliases / find_unknown_names: so khớp trên chuỗi đã fold, theo ranh giới từ.
    * Chỗ khớp nằm trọn trong một lần xuất hiện của tên hư cấu thì bỏ qua (tên hư cấu được phép
      chứa một mảnh trùng tên thật của người khác, ví dụ "Phan Đức Lâm" so với tên thật "Lâm").
    * Tên thật chỉ có một âm tiết và ngắn hơn 3 ký tự thì bỏ qua.
    * Tên thật một âm tiết (ví dụ "Lâm") chỉ khớp khi viết hoa chữ đầu và đúng dấu (hoặc bỏ hết dấu),
      để không thay nhầm "làm", "lắm" vì khi bỏ dấu chúng trùng "lam".
    * Tên quốc gia và tên chung của cơ quan được giữ nguyên (spec mục 6): build_forbidden_names không đưa
      chúng vào danh sách cấm (khi entity là địa danh hoặc cơ quan), nên không bị coi là lọt tên.
- find_dates: ngày-tháng cụ thể và năm viết bằng số; giờ trong ngày và thập niên được giữ.
- check_plan: tính lại cờ (từng cảnh) và cảnh báo (toàn kế hoạch) từ đầu, trả về bản sao mới.
"""
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Optional

from models.case_adaptation_schemas import CaseAdaptationPlan, CaseBible, Lang, SceneFlag
from services.case_fictionalizer import AnonymizerShield


# ---------------------------------------------------------------- fold

@lru_cache(maxsize=8192)
def _fold_char(ch: str) -> str:
    low = ch.lower()
    if len(low) != 1:           # vài ký tự đặc biệt khi hạ chữ thường đổi độ dài; giữ nguyên
        return ch
    if low == "đ":
        return "d"
    base = "".join(c for c in unicodedata.normalize("NFD", low) if unicodedata.category(c) != "Mn")
    return base if len(base) == 1 else low


def _fold_nfc(text: str) -> str:
    """Fold chuỗi đã chuẩn hoá NFC. Độ dài giữ nguyên nên vị trí khớp dùng được cho chuỗi gốc."""
    return "".join(_fold_char(c) for c in text)


def fold(text: str) -> str:
    """Chữ thường, bỏ dấu, `đ` thành `d`."""
    return _fold_nfc(unicodedata.normalize("NFC", text))


@lru_cache(maxsize=32768)
def _key(name: str) -> str:
    """Dạng so khớp của một tên: đã fold, khoảng trắng gộp thành một dấu cách."""
    return " ".join(fold(name).split())


# ---------------------------------------------------------------- tên cần giữ nguyên

# Tên quốc gia và tên chung của cơ quan được giữ nguyên trong lời kể (spec mục 6, 7.5).
_KEPT_TERMS = frozenset(_key(t) for t in [
    "Việt Nam", "Đài Loan", "Hoa Kỳ", "Mỹ", "Trung Quốc", "Nhật Bản", "Hàn Quốc", "Thái Lan",
    "Singapore", "Malaysia", "Campuchia", "Lào", "Philippines", "Indonesia", "Ấn Độ", "Pháp", "Đức",
    "Nga", "Úc", "Canada", "Vương quốc Anh",
    "Vietnam", "Taiwan", "United States", "USA", "America", "China", "Japan", "South Korea", "Korea",
    "Thailand", "Cambodia", "Laos", "India", "France", "Germany", "Russia", "Australia", "United Kingdom",
    "cảnh sát", "công an", "tòa án", "toà án", "viện kiểm sát", "viện kiểm sát nhân dân", "bệnh viện",
    "police", "the police", "court", "the court", "prosecutor", "prosecutors", "hospital",
])


# ---------------------------------------------------------------- tên cấm

@dataclass(frozen=True)
class ForbiddenName:
    real: str
    entity_id: Optional[str] = None
    alias_vi: Optional[str] = None
    alias_en: Optional[str] = None


def build_forbidden_names(bible: CaseBible, source_text: str) -> list[ForbiddenName]:
    """`real_names` của mọi entity, cộng tên regex bắt được trên bài gốc mà chưa có trong entity nào.
    Địa danh/cơ quan trùng tên quốc gia hay tên chung của cơ quan bị loại (được giữ nguyên trong lời kể);
    người thì không, vì "Đức" hay "Nga" cũng là tên người."""
    out: list[ForbiddenName] = []
    seen: set[str] = set()
    for ent in bible.entities:
        kept = _KEPT_TERMS if ent.kind in ("place", "organization") else frozenset()
        for name in ent.real_names:
            key = _key(name)
            if not key or key in seen or key in kept:
                continue
            seen.add(key)
            out.append(ForbiddenName(name.strip(), ent.id, ent.alias_vi.strip() or None, ent.alias_en.strip() or None))
    if source_text:
        for name in sorted(AnonymizerShield().extract_pii_candidates(source_text)["persons"]):
            key = _key(name)
            if key and key not in seen and key not in _KEPT_TERMS:
                seen.add(key)
                out.append(ForbiddenName(name.strip()))
    return out


# ---------------------------------------------------------------- so khớp tên

def _active_entries(forbidden: Iterable[ForbiddenName]) -> dict[str, ForbiddenName]:
    """Các tên còn hiệu lực, theo dạng fold. Bỏ tên rỗng và tên một âm tiết ngắn hơn 3 ký tự."""
    entries: dict[str, ForbiddenName] = {}
    for fn in forbidden:
        key = _key(fn.real)
        if not key or key in entries:
            continue
        if " " not in key and len(key) < 3:
            continue
        entries[key] = fn
    return entries


@lru_cache(maxsize=64)
def _compile_names(keys: tuple[str, ...]) -> Optional[re.Pattern]:
    """Một regex duy nhất cho mọi tên, tên dài thử trước để tên đầy đủ thắng tên gọi tắt của nó."""
    if not keys:
        return None
    ordered = sorted(keys, key=lambda k: (-len(k), k))
    alts = [r"\s+".join(re.escape(tok) for tok in k.split()) for k in ordered]
    return re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)")


def _alias_spans(folded: str, aliases: Iterable[str], real_keys: set[str]) -> list[tuple[int, int]]:
    """Vị trí các lần xuất hiện của tên hư cấu. Alias trùng một tên thật (sau fold) không được tính là
    lá chắn, nếu không thì LLM đặt alias giống hệt tên thật sẽ lọt qua kiểm tra."""
    keys = {k for k in (_key(a) for a in aliases if a) if k and k not in real_keys}
    pattern = _compile_names(tuple(sorted(keys)))
    if pattern is None:
        return []
    return [m.span() for m in pattern.finditer(folded)]


def _single_token_ok(orig: str, real: str) -> bool:
    """Tên một âm tiết chỉ nhận khi viết hoa chữ đầu và đúng dấu (hoặc bỏ hết dấu)."""
    if not real.strip().replace("-", "").isalpha():
        return True                       # số điện thoại, biển số...: so khớp bình thường
    if orig[:1].islower():
        return False
    low = orig.lower()
    return low == unicodedata.normalize("NFC", real).strip().lower() or low == _fold_nfc(low)


def _scan(norm: str, forbidden: Iterable[ForbiddenName], alias_pool: Iterable[str]):
    """Các chỗ khớp tên thật chưa nằm trong tên hư cấu: (bắt đầu, kết thúc, ForbiddenName)."""
    entries = _active_entries(forbidden)
    pattern = _compile_names(tuple(entries))
    if pattern is None:
        return []
    folded = _fold_nfc(norm)
    spans = _alias_spans(folded, alias_pool, {_key(f.real) for f in forbidden})
    hits = []
    for m in pattern.finditer(folded):
        s, e = m.span()
        if any(a <= s and e <= b for a, b in spans):
            continue
        key = " ".join(m.group(0).split())
        fn = entries[key]
        if " " not in key and not _single_token_ok(norm[s:e], fn.real):
            continue
        hits.append((s, e, fn))
    return hits


def _alias_for(fn: ForbiddenName, lang: Lang) -> Optional[str]:
    alias = ((fn.alias_vi if lang == "vi" else fn.alias_en) or "").strip()
    if not alias or _key(alias) == _key(fn.real):
        return None
    return alias


def _forbidden_aliases(forbidden: Iterable[ForbiddenName]) -> list[str]:
    return [a for f in forbidden for a in (f.alias_vi, f.alias_en) if a]


def apply_aliases(text: str, forbidden: list[ForbiddenName], lang: Lang,
                  extra_aliases: Iterable[str] = ()) -> tuple[str, list[str]]:
    """Thay tên thật đã có alias bằng alias của `lang`. Trả (văn bản mới, các tên thật đã thay).
    Tên chưa có alias được để nguyên (find_unknown_names sẽ bắt)."""
    if not text:
        return text, []
    norm = unicodedata.normalize("NFC", text)
    pool = [*_forbidden_aliases(forbidden), *extra_aliases]
    parts: list[str] = []
    replaced: list[str] = []
    last = 0
    for s, e, fn in _scan(norm, forbidden, pool):
        alias = _alias_for(fn, lang)
        if alias is None:
            continue
        parts.append(norm[last:s])
        parts.append(alias)
        last = e
        if fn.real not in replaced:
            replaced.append(fn.real)
    if not replaced:
        return text, []
    parts.append(norm[last:])
    return "".join(parts), replaced


def find_unknown_names(text: str, forbidden: list[ForbiddenName], aliases: list[str]) -> list[str]:
    """Tên thật còn sót trong `text`, bỏ qua chỗ nằm trọn trong một tên hư cấu thuộc `aliases`."""
    if not text:
        return []
    norm = unicodedata.normalize("NFC", text)
    found: list[str] = []
    for _s, _e, fn in _scan(norm, forbidden, aliases):
        if fn.real not in found:
            found.append(fn.real)
    return found


# ---------------------------------------------------------------- ngày tháng

_D = r"(?:3[01]|[12]\d|0?[1-9])"
_M = r"(?:1[0-2]|0?[1-9])"
_Y = r"(?:1[89]|20)\d{2}"

# Tiếng Việt: khớp trên chuỗi đã fold (ngay/thang/nam).
_VI_DM = re.compile(
    rf"(?<!\w)(?:ngay\s+)?{_D}(?!\d)\s+thang\s+{_M}(?!\d)(?:\s+nam\s+\d{{4}}(?!\d))?"
    r"(?!\s+(?:ngay|tuan|gio|phut|thang)(?!\w))"
)
_VI_YEAR = re.compile(r"(?<!\w)nam\s+(\d{4})(?!\d)")

# Số: dd/mm, dd/mm/yyyy, dd-mm-yyyy (dạng dd-mm không năm là khoảng như "3-4" nên bỏ), mm/yyyy, yyyy-mm-dd.
_NUM_DATE = re.compile(r"(?<![\w/.\-])(\d{1,2})([/-])(\d{1,2})(?:\2(\d{4}|\d{2}))?(?![\w/])")
_NUM_MONTH_YEAR = re.compile(rf"(?<![\w/.\-])({_M})[/-]{_Y}(?!\d)")
_NUM_ISO = re.compile(rf"(?<![\w/.\-]){_Y}([/-])(\d{{1,2}})\1(\d{{1,2}})(?![\w/])")


def _month_alternatives() -> str:
    names = [("Jan", "uary"), ("Feb", "ruary"), ("Mar", "ch"), ("Apr", "il"), ("May", ""), ("Jun", "e"),
             ("Jul", "y"), ("Aug", "ust"), ("Sep", "tember"), ("Oct", "ober"), ("Nov", "ember"), ("Dec", "ember")]
    forms = {"Sept", "SEPT"}
    for abbr, rest in names:
        for w in (abbr, abbr + rest):
            forms.add(w)
            forms.add(w.upper())
    return "|".join(sorted((re.escape(f) for f in forms), key=len, reverse=True))


# Tiếng Anh: tên tháng phải viết hoa (Mar/May/March dễ nhầm với động từ viết thường).
_MON = _month_alternatives()
_ORD = r"(?i:st|nd|rd|th)"
_EN_MONTH_DAY = re.compile(rf"(?<!\w)(?:{_MON})\.?\s+{_D}(?!\d)(?:{_ORD}(?!\w))?(?:,?\s+{_Y}(?!\d))?")
_EN_DAY_MONTH = re.compile(rf"(?<!\w){_D}(?!\d)(?:{_ORD})?(?:\s+(?i:of))?\s+(?:{_MON})(?!\w)\.?(?:,?\s+{_Y}(?!\d))?")
_EN_MONTH_YEAR = re.compile(rf"(?<!\w)(?:{_MON})\.?,?\s+{_Y}(?!\d)")
_EN_IN_YEAR = re.compile(rf"(?<!\w)(?i:in)\s+({_Y})(?!\w)")
_STANDALONE_YEAR = re.compile(rf"(?<![\w.,:/$€£¥])({_Y})(?!\w)(?![.,]\d)(?!:)")

_DECADE_BEFORE = re.compile(r"(?:thap\s+nien|thap\s+ky|thap\s+ki|decades?)\s*(?:(?:of|the)\s+)?$")
_PLURAL_AFTER = re.compile(r"['’]?s(?!\w)")
_UNIT_AFTER = re.compile(
    r"\s*(?:usd|vnd|vnđ|ntd|nt\$|đồng|đ(?!\w)|đô|euros?|dollars?|bucks|yuan|rmb|baht|tệ|người|mét|km|kg|"
    r"people|meters|feet|miles|words)(?!\w)",
    re.IGNORECASE,
)


def _year_is_kept(norm: str, folded: str, start: int, end: int) -> bool:
    """Năm đứng riêng nhưng thực ra là thập niên (2010s, thập niên 2010, những năm 1990) hoặc số tiền/số lượng."""
    if _PLURAL_AFTER.match(norm, end):
        return True
    before = folded[:start].rstrip()
    if _DECADE_BEFORE.search(before):
        return True
    if norm[start:end].endswith("0") and before.endswith("nhung nam"):
        return True
    if _UNIT_AFTER.match(norm, end):
        return True
    return False


def _valid_numeric_date(a: int, b: int, sep: str, year: Optional[str]) -> bool:
    if sep == "-" and year is None:
        return False
    if not (1 <= a <= 31 and 1 <= b <= 31 and (a <= 12 or b <= 12)):
        return False
    if year is None and (a, b) == (24, 7):      # "mở cửa 24/7"
        return False
    return True


def find_dates(text: str) -> list[str]:
    """Ngày-tháng cụ thể và năm viết bằng số, mỗi mục là đoạn nguyên văn trong `text`. Các chỗ khớp
    chồng nhau gộp thành đoạn dài nhất. Giờ trong ngày (02:21), thập niên và mốc tương đối được giữ."""
    if not text:
        return []
    norm = unicodedata.normalize("NFC", text)
    folded = _fold_nfc(norm)
    spans: list[tuple[int, int]] = []

    for m in _VI_DM.finditer(folded):
        spans.append(m.span())
    for m in _VI_YEAR.finditer(folded):
        year = m.group(1)
        if year.endswith("0") and folded[:m.start()].rstrip().endswith("nhung"):
            continue                              # "những năm 2010"
        spans.append(m.span())

    for m in _NUM_DATE.finditer(norm):
        year = m.group(4)
        if _valid_numeric_date(int(m.group(1)), int(m.group(3)), m.group(2), year):
            spans.append(m.span())
    spans.extend(m.span() for m in _NUM_MONTH_YEAR.finditer(norm))
    for m in _NUM_ISO.finditer(norm):
        if 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31:
            spans.append(m.span())

    for pattern in (_EN_MONTH_DAY, _EN_DAY_MONTH, _EN_MONTH_YEAR):
        spans.extend(m.span() for m in pattern.finditer(norm))
    for m in _EN_IN_YEAR.finditer(norm):
        if not _year_is_kept(norm, folded, m.start(1), m.end(1)):
            spans.append(m.span())
    for m in _STANDALONE_YEAR.finditer(norm):
        if not _year_is_kept(norm, folded, m.start(1), m.end(1)):
            spans.append(m.span())

    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [norm[s:e] for s, e in merged]


# ---------------------------------------------------------------- kiểm cả kế hoạch

_NARRATION_FIELDS = ("narration_vi", "narration_en")
# (trường, ngôn ngữ của tên hư cấu dùng để thay). Prompt viết bằng tiếng Anh nên dùng alias_en.
_SCENE_FIELDS: tuple[tuple[str, Lang], ...] = (
    ("narration_vi", "vi"), ("narration_en", "en"), ("image_prompt", "en"), ("video_prompt", "en"),
)
_MISSING_TEXT = {"narration_vi": "Thiếu lời kể tiếng Việt.", "narration_en": "Thiếu lời kể tiếng Anh."}


def _unique(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def check_plan(plan: CaseAdaptationPlan, source_text: str) -> CaseAdaptationPlan:
    """Trả bản sao đã kiểm; không đổi `plan`. Cờ và cảnh báo luôn tính lại từ đầu nên gọi lại sau khi
    người dùng sửa vẫn đúng.

    - Tên thật đã có alias: tự thay (ở lời kể, prompt, tên tập, nhãn bằng chứng/quan hệ) và ghi cảnh báo.
    - Tên thật chưa có alias, thiếu lời kể, id lạ trong board_reveal: cờ ở cảnh (chặn tạo dự án).
    - Ngày cụ thể trong lời kể: cờ ở cảnh. Ở prompt, tên tập, nhãn: cảnh báo của cả kế hoạch, không chặn
      (SceneFlag gắn theo cảnh nên các chỗ ngoài cảnh chỉ có cảnh báo).
    - Cảnh `disclaimer` không bị quét.
    """
    new = plan.model_copy(deep=True)
    bible = new.bible
    forbidden = build_forbidden_names(bible, source_text)
    aliases = _unique(a.strip() for e in bible.entities for a in (e.alias_vi, e.alias_en) if a and a.strip())
    by_key = _active_entries(forbidden)
    warnings: list[str] = []

    def clean(text: str, lang: Lang) -> tuple[str, list[tuple[str, str]], list[str]]:
        fixed, replaced = apply_aliases(text, forbidden, lang, extra_aliases=aliases)
        pairs = [(real, _alias_for(by_key[_key(real)], lang) or "") for real in replaced]
        return fixed, pairs, find_unknown_names(fixed, forbidden, aliases)

    # --- từng cảnh
    valid_ids = {e.id for e in bible.evidence} | {r.id for r in bible.relations}
    revealed: set[str] = set()
    for scene in new.scenes:
        revealed.update(scene.board_reveal)
        if scene.visual_kind == "disclaimer":
            scene.flags = []
            continue
        flags: list[SceneFlag] = []
        for field, lang in _SCENE_FIELDS:
            text = getattr(scene, field)
            if not text.strip():
                if field in _NARRATION_FIELDS:
                    flags.append(SceneFlag(kind="missing_text", field=field, detail=_MISSING_TEXT[field]))
                continue
            fixed, pairs, unknown = clean(text, lang)
            if fixed != text:
                setattr(scene, field, fixed)
            for real, alias in pairs:
                warnings.append(f"Đã tự thay tên thật '{real}' bằng '{alias}' ở cảnh {scene.order} ({field}).")
            for name in unknown:
                flags.append(SceneFlag(kind="unknown_name", field=field,
                                       detail=f"Tên thật chưa có tên thay thế: '{name}'."))
            for found in _unique(find_dates(fixed)):
                if field in _NARRATION_FIELDS:
                    flags.append(SceneFlag(kind="date", field=field,
                                           detail=f"Ngày tháng hoặc năm cụ thể: '{found}'."))
                else:
                    warnings.append(f"Còn ngày tháng hoặc năm cụ thể '{found}' ở cảnh {scene.order} ({field}); "
                                    "hãy sửa thành cách nói chung.")
        for rid in _unique(scene.board_reveal):
            if rid not in valid_ids:
                flags.append(SceneFlag(kind="bad_reveal", field="board_reveal",
                                       detail=f"Id không có trong bằng chứng hoặc quan hệ: '{rid}'."))
        scene.flags = flags

    # --- tên tập và nhãn bằng chứng/quan hệ: không có cờ theo cảnh nên chỉ tự thay và cảnh báo
    def clean_label(obj, field: str, lang: Lang, where: str) -> None:
        text = getattr(obj, field)
        if not text or not text.strip():
            return
        fixed, pairs, unknown = clean(text, lang)
        if fixed != text:
            setattr(obj, field, fixed)
        for real, alias in pairs:
            warnings.append(f"Đã tự thay tên thật '{real}' bằng '{alias}' ở {where} ({field}).")
        for name in unknown:
            warnings.append(f"Tên thật '{name}' còn trong {where} ({field}) nhưng chưa có tên thay thế; "
                            "hãy thêm tên này vào bảng tên.")
        for found in _unique(find_dates(fixed)):
            warnings.append(f"Còn ngày tháng hoặc năm cụ thể '{found}' ở {where} ({field}); "
                            "hãy sửa thành cách nói chung.")

    clean_label(bible, "title_vi", "vi", "tiêu đề")
    clean_label(bible, "title_en", "en", "tiêu đề")
    for ev in bible.evidence:
        clean_label(ev, "label_vi", "vi", f"nhãn bằng chứng '{ev.id}'")
        clean_label(ev, "label_en", "en", f"nhãn bằng chứng '{ev.id}'")
    for rel in bible.relations:
        clean_label(rel, "label_vi", "vi", f"nhãn quan hệ '{rel.id}'")
        clean_label(rel, "label_en", "en", f"nhãn quan hệ '{rel.id}'")

    # --- bằng chứng chưa hiện ra ở cảnh nào
    for ev in bible.evidence:
        if ev.id not in revealed:
            warnings.append(f"Bằng chứng '{ev.id}' ({ev.label_vi}) chưa hiện ra trên bảng điều tra ở cảnh nào.")

    new.warnings = warnings
    return new


def has_blocking_flags(plan: CaseAdaptationPlan) -> bool:
    """Còn cảnh bị đánh dấu thì chặn tạo dự án."""
    return any(scene.flags for scene in plan.scenes)
