"""
Kiểm lọt tên thật, ngày tháng cụ thể và tự áp tên hư cấu (G7, không dùng LLM).

- fold: chữ thường, bỏ dấu (đ thành d), giữ nguyên độ dài từng ký tự để đổi vị trí khớp về chuỗi gốc.
- accept_match: quy tắc chung "nhận chỗ khớp này không?", dùng ở mọi chỗ tìm tên thật hay tên hư cấu trong chữ (kiểm
  lọt tên ở đây, _TextGuard của các bước viết, đổi tên hư cấu trên màn xem lại). Tên được tìm trên chuỗi đã fold, theo
  ranh giới từ; vì khi bỏ dấu nhiều từ thường trùng tên ("lẻ loi" ~ "Lê Lợi", "Năm" ~ "Nam"), chỗ khớp chỉ được nhận khi:
    * viết đúng dấu như tên (không phân biệt hoa thường, kiểu đặt dấu thanh cũ/mới coi như một) hoặc viết hoàn toàn
      không dấu ("Le Loi", "LE LOI");
    * viết hoa như tên riêng: tên một âm tiết ("Lâm") phải viết hoa chữ đầu, để không thay nhầm "làm", "lắm"; tên nhiều
      chữ thì chữ nào tên viết hoa, chỗ khớp cũng phải viết hoa ("Hòa Bình", "HÒA BÌNH"; "cuộc sống hòa bình" và
      "Lâm đồng ý" không phải tên). Riêng chữ chỉ loại đứng đầu ("đường", "cảng", "công ty", "ông"...) hay đứng cuối
      trong tiếng Anh ("street", "port"...) được viết thường ("trên đường Lê Lợi");
    * không nằm trong một danh từ chung của GENERIC_TERMS viết đúng dấu: tên thật "Hưng Thu" bỏ dấu trùng "hung thủ",
      tên "Hùng" không dấu trùng chữ "Hung" trong "Hung thủ", nhưng các cụm này trong lời kể không phải tên.
- find_name_matches / apply_aliases / find_unknown_names: tên thật trong chữ.
    * Mọi chỗ khớp của mọi tên được xét; chỉ giữ chỗ được nhận, rồi chọn các chỗ không chồng nhau, chỗ dài hơn trước.
      Vì vậy tên dài viết sai không che mất tên ngắn đúng ở cùng chỗ ("Lê Lợi hưng phấn" khi có tên "Lê Lợi Hùng").
    * Chỗ khớp nằm trọn trong một lần xuất hiện của tên hư cấu thì bỏ qua (tên hư cấu được phép
      chứa một mảnh trùng tên thật của người khác, ví dụ "Phan Đức Lâm" so với tên thật "Lâm").
    * Tên thật chỉ có một âm tiết và ngắn hơn 3 ký tự thì bỏ qua.
    * Hai tên thật chỉ khác dấu ("Nguyễn Văn Hùng", "Nguyễn Văn Hưng") là hai tên: mỗi cách viết đúng dấu dùng tên hư
      cấu của mình. Chỗ viết không dấu ("Nguyen Van Hung") mà khớp nhiều tên thật có tên hư cấu khác nhau thì không biết
      là ai: dùng tên của thực thể đứng trước trong bảng tên và đánh dấu `ambiguous` (check_plan ghi cảnh báo, không chặn).
    * Tên quốc gia và tên chung của cơ quan được giữ nguyên (spec mục 6): build_forbidden_names không đưa
      chúng vào danh sách cấm (khi entity là địa danh hoặc cơ quan), nên không bị coi là lọt tên.
- find_dates: ngày-tháng cụ thể và năm viết bằng số; giờ trong ngày và thập niên được giữ.
- identifying_numbers / find_identifying_numbers: con số nhận dạng của bài (số nhà, biển số, số điện thoại...) còn
  trong chữ; giờ, tuổi, số tiền và số lượng thì giữ.
- find_vi_forms_in_en: tên hư cấu dạng tiếng Việt dùng trong lời Anh.
- quotes_in / quote_source / find_unsourced_quotes: lời trích trong ngoặc kép không có nguyên văn trong bài gốc (lời
  nói bịa đặt cho người thật).
- check_plan: trả về bản sao mới; cờ (từng cảnh và cấp kế hoạch) và check_warnings tính lại từ đầu,
  còn warnings là danh sách bền, chỉ nối thêm các lần tự thay tên.
"""
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Optional, Sequence

from models.case_adaptation_schemas import CaseAdaptationPlan, CaseBible, Lang, SceneFlag
from services.case_fictionalizer import AnonymizerShield


# ---------------------------------------------------------------- thời lượng lời kể

# Tốc độ đọc đo bằng giọng Edge khi chạy thật vụ Nhũ Cô (21/10): lời Việt 229 chữ/phút, lời Anh 133 chữ/phút (VieNeu
# MaiAnh đo 218–234 tuỳ bài). Dùng để đổi lời kể ra số phút video (số chữ mỗi cảnh ở các bước viết, cảnh báo thời lượng).
VI_WORDS_PER_MINUTE = 229
EN_WORDS_PER_MINUTE = 133
# Lời kể cả video đọc lâu hơn số phút đã chọn quá tỉ lệ này thì màn xem lại cảnh báo.
DURATION_WARN_RATIO = 1.15


def speech_minutes(texts: Iterable[str], lang: Lang) -> float:
    """Số phút đọc hết các đoạn lời kể `texts` (đếm từ theo khoảng trắng, tốc độ đọc đã đo của `lang`)."""
    rate = VI_WORDS_PER_MINUTE if lang == "vi" else EN_WORDS_PER_MINUTE
    return sum(len(str(t or "").split()) for t in texts) / rate


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
_KEPT_NAMES = (
    "Việt Nam", "Đài Loan", "Hoa Kỳ", "Mỹ", "Trung Quốc", "Nhật Bản", "Hàn Quốc", "Thái Lan",
    "Singapore", "Malaysia", "Campuchia", "Lào", "Philippines", "Indonesia", "Ấn Độ", "Pháp", "Đức",
    "Nga", "Úc", "Canada", "Vương quốc Anh",
    "Vietnam", "Taiwan", "United States", "USA", "America", "China", "Japan", "South Korea", "Korea",
    "Thailand", "Cambodia", "Laos", "India", "France", "Germany", "Russia", "Australia", "United Kingdom",
    "cảnh sát", "công an", "tòa án", "toà án", "viện kiểm sát", "viện kiểm sát nhân dân", "bệnh viện",
    "police", "the police", "court", "the court", "prosecutor", "prosecutors", "hospital",
)
_KEPT_TERMS = frozenset(_key(t) for t in _KEPT_NAMES)

# Cụm giữ nguyên chứa một chữ hay là tên người ("Nam" trong "Việt Nam", "miền Nam"; "Loan" trong "Đài Loan"; "Đức"
# trong "nước Đức"): tên ngắn nằm trọn bên trong một cụm như vậy không phải tên người, không thay, không báo. Chỉ gồm
# cụm hầu như không thể là một phần tên người, vì cụm này che tên thật nằm bên trong nó.
_PROTECTED_PHRASES = tuple(dict.fromkeys([
    *(t for t in _KEPT_NAMES if " " in t),
    "miền Nam", "miền Bắc", "miền Trung", "miền Tây", "miền Đông", "Nam Bộ", "Bắc Bộ", "Trung Bộ", "Tây Nguyên",
    "Đông Nam Á", "Triều Tiên", "Nam Phi",
    "nước Mỹ", "nước Anh", "nước Pháp", "nước Đức", "nước Nga", "nước Úc", "nước Lào", "nước Nhật",
]))

# Danh từ chung chỉ cơ quan, vai trò, nghề nghiệp trong vụ án: không phải tên riêng, không cần tên hư cấu.
# Prompt đọc bài (case_adaptation_prompts.extract_prompt) liệt kê đúng danh sách này, và bước đọc bài bỏ các mục
# này khỏi danh sách tên, nên prompt và code luôn khớp nhau.
GENERIC_TERMS: tuple[str, ...] = (
    "cảnh sát", "công an", "toà án", "tòa án", "toà án nhân dân", "tòa án nhân dân", "viện kiểm sát",
    "viện kiểm sát nhân dân", "bệnh viện",
    "cơ quan điều tra", "cơ quan công an", "cơ quan cảnh sát điều tra", "cơ quan chức năng", "lực lượng chức năng",
    "chính quyền địa phương", "công an phường", "công an xã", "công an huyện", "công an tỉnh", "đội trọng án",
    "cảnh sát giao thông", "cảnh sát hình sự", "cảnh sát cơ động", "phòng cháy chữa cháy",
    "cảnh sát phòng cháy chữa cháy", "trực ban hình sự", "pháp y", "bác sĩ pháp y", "giám định viên",
    "bệnh viện đa khoa", "trường học", "trường tiểu học", "trường trung học", "nạn nhân", "gia đình",
    "gia đình nạn nhân", "người thân", "nghi phạm", "nghi can", "hung thủ", "nhân chứng", "điều tra viên",
    "kiểm sát viên", "thẩm phán", "luật sư", "người dân", "hàng xóm", "người đàn ông", "người phụ nữ", "cô gái",
    "chàng trai", "người lạ", "đứa trẻ",
    "police", "court", "prosecutor", "hospital", "investigators", "detective", "coroner", "medical examiner",
    "victim", "suspect", "witness", "killer", "neighbors", "family",
)
def _accented_key(name: str) -> str:
    """Dạng so khớp giữ dấu: NFC, chữ thường, khoảng trắng gộp thành một dấu cách."""
    return " ".join(unicodedata.normalize("NFC", name).lower().split())


# Dấu thanh đặt kiểu cũ -> kiểu mới ("hoà" -> "hòa", "thuý" -> "thúy"), để hai cách viết cùng một tên được coi là một.
_TONE_PLACEMENT = {
    "oà": "òa", "oá": "óa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
    "oè": "òe", "oé": "óe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
    "uý": "úy", "uỳ": "ùy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
}
_TONE_PLACEMENT_RE = re.compile("|".join(_TONE_PLACEMENT))


@lru_cache(maxsize=32768)
def spelling_key(text: str) -> str:
    """Cách viết giữ dấu để so sánh: NFC, chữ thường, khoảng trắng gộp, dấu thanh theo kiểu mới.
    "Hoà Bình" và "HÒA BÌNH" cùng một cách viết; "Hùng" và "Hưng" là hai cách viết."""
    return _TONE_PLACEMENT_RE.sub(lambda m: _TONE_PLACEMENT[m.group(0)], _accented_key(text))


# So có phân biệt dấu: bỏ dấu thì tên thật trùng danh từ chung ("Gia Định" ~ "gia đình", "Hưng Thu" ~ "hung thủ").
_GENERIC_KEYS = frozenset(_accented_key(t) for t in GENERIC_TERMS)
_GENERIC_SPELLINGS = frozenset(spelling_key(t) for t in GENERIC_TERMS)
_GENERIC_FOLDED = tuple(sorted({_key(t) for t in GENERIC_TERMS}))


def is_kept_term(name: str, kind: Optional[str] = None) -> bool:
    """Tên được giữ nguyên trong lời kể, không cần tên hư cấu (spec mục 6):
    - danh từ chung trong GENERIC_TERMS, với mọi loại; so đúng dấu (không phân biệt hoa thường), vì khi bỏ dấu
      nhiều tên thật trùng danh từ chung;
    - tên quốc gia và tên chung của cơ quan (_KEPT_TERMS, so bỏ dấu), trừ khi là người (`kind == "person"`),
      vì "Đức", "Nga", "Mỹ" cũng là tên người. `kind` không rõ (None) thì coi như không phải người."""
    if _accented_key(name) in _GENERIC_KEYS:
        return True
    return kind != "person" and _key(name) in _KEPT_TERMS


# ---------------------------------------------------------------- tên cấm

_LINE_BREAKS = re.compile(r"[\r\n\v\f\x85  ]+")

@dataclass(frozen=True)
class ForbiddenName:
    real: str
    entity_id: Optional[str] = None
    alias_vi: Optional[str] = None
    alias_en: Optional[str] = None


def build_forbidden_names(bible: CaseBible, source_text: str) -> list[ForbiddenName]:
    """`real_names` của mọi entity, cộng tên regex bắt được trên bài gốc mà chưa có trong entity nào.
    - Tên trùng nhau khi so cách viết giữ dấu (spelling_key: không phân biệt hoa thường, dấu thanh kiểu cũ/mới) thì chỉ
      giữ tên đứng trước. Hai tên chỉ khác dấu ("Nguyễn Văn Hùng", "Nguyễn Văn Hưng") là hai tên, giữ cả hai.
    - Tên regex đã nằm trong cách viết của một tên có sẵn (cùng cách viết, hoặc là dạng không dấu của nó) thì bỏ.
    - Địa danh/cơ quan trùng tên quốc gia hay tên chung của cơ quan bị loại (được giữ nguyên trong lời kể);
      người thì không, vì "Đức" hay "Nga" cũng là tên người."""
    out: list[ForbiddenName] = []
    spellings: set[str] = set()
    by_key: dict[str, list[str]] = {}

    def add(name: str, fn: ForbiddenName) -> None:
        spellings.add(spelling_key(name))
        by_key.setdefault(_key(name), []).append(name)
        out.append(fn)

    for ent in bible.entities:
        kept = _KEPT_TERMS if ent.kind in ("place", "organization") else frozenset()
        for name in ent.real_names:
            key = _key(name)
            if not key or key in kept or spelling_key(name) in spellings:
                continue
            add(name, ForbiddenName(name.strip(), ent.id, ent.alias_vi.strip() or None, ent.alias_en.strip() or None))
    if source_text:
        # REGEX_PERSON nối chữ qua cả dòng mới ("Lê Thu Hà\nTrần"), nên đổi mỗi chỗ xuống dòng thành dấu chấm
        # để tên không bao giờ vắt qua dòng; tên còn dính ký tự xuống dòng thì bỏ.
        flat = _LINE_BREAKS.sub(" . ", source_text)
        for name in sorted(AnonymizerShield().extract_pii_candidates(flat)["persons"]):
            key = _key(name)
            if not key or key in _KEPT_TERMS or _LINE_BREAKS.search(name):
                continue
            if any(_same_spelling(name, other) for other in by_key.get(key, ())):
                continue
            add(name, ForbiddenName(name.strip()))
    return out


# ---------------------------------------------------------------- quy tắc chung "nhận chỗ khớp này không?"

def _same_spelling(orig: str, real: str) -> bool:
    """`orig` (chỗ khớp trên bài, trùng `real` khi bỏ dấu) có viết như tên `real` không: đúng từng dấu (không phân biệt
    hoa thường), hoặc hoàn toàn không dấu ("Le Loi", "le loi"). Viết sai dấu thì là từ khác trùng khi bỏ dấu."""
    if spelling_key(orig) == spelling_key(real):
        return True
    low = unicodedata.normalize("NFC", orig).lower()
    return _fold_nfc(low) == low


# Chữ chỉ loại đứng đầu tên (địa danh, cơ quan, cách gọi người): trong lời kể thường viết thường ("trên đường Lê Lợi",
# "ở cảng Tân Hải", "ông Hùng") nên không bắt viết hoa; phần tên riêng phía sau vẫn phải viết hoa. Tiếng Anh thì chữ chỉ
# loại đứng cuối ("Tan Hai port", "Le Loi street").
_FREE_PREFIXES = tuple(sorted({spelling_key(p) + " " for p in (
    "thành phố", "tp", "tp.", "tỉnh", "quận", "huyện", "thị xã", "thị trấn", "xã", "phường", "thôn", "ấp", "làng",
    "khu phố", "đường", "phố", "ngõ", "hẻm", "kiệt", "cảng", "sân bay", "ga", "chợ", "bến xe", "bến", "cầu", "sông",
    "núi", "đảo", "công ty", "tập đoàn", "ngân hàng", "bệnh viện", "trường", "nhà máy", "khách sạn", "nhà hàng",
    "cửa hàng", "siêu thị", "chung cư", "tòa nhà", "quán", "ông", "bà", "cô", "chị", "chú", "bác",
    "the", "port of", "city of",
)}, key=len, reverse=True))
_FREE_SUFFIXES = tuple(sorted({" " + spelling_key(s) for s in (
    "street", "st.", "road", "avenue", "lane", "port", "harbor", "harbour", "city", "county", "district", "province",
    "bridge", "river", "lake", "park", "company", "hospital", "school",
)}, key=len, reverse=True))


@lru_cache(maxsize=8192)
def _free_words(name: str) -> tuple[int, int]:
    """Số chữ đầu và số chữ cuối của tên được phép viết thường (chữ chỉ loại). Luôn chừa ít nhất một chữ phải viết hoa."""
    spelled = spelling_key(name)
    count = len(spelled.split())
    lead = next((len(p.split()) for p in _FREE_PREFIXES if spelled.startswith(p)), 0)
    trail = next((len(s.split()) for s in _FREE_SUFFIXES if spelled.endswith(s)), 0)
    return (lead, trail) if lead + trail < count else (0, 0)


def _capitalised_like(span: str, name: str) -> bool:
    """Chỗ khớp viết hoa như tên riêng `name` (xem accept_match)."""
    words, real = span.split(), name.split()
    if len(real) <= 1:
        if not name.strip().replace("-", "").isalpha():
            return True                    # số điện thoại, biển số...: không xét hoa thường
        return not span[:1].islower()
    lead, trail = _free_words(name)
    for i, (word, real_word) in enumerate(zip(words, real)):
        if i < lead or i >= len(real) - trail:
            continue
        if real_word[:1].isupper() and word[:1].islower():
            return False
    return True


@lru_cache(maxsize=1024)
def _generic_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Vị trí các danh từ chung của GENERIC_TERMS viết đúng dấu trong `text` (đã NFC)."""
    folded = _fold_nfc(text)
    spans: list[tuple[int, int]] = []
    for key in _GENERIC_FOLDED:
        if key.split(" ", 1)[0] not in folded:
            continue
        for m in _name_pattern(key).finditer(folded):
            if spelling_key(text[m.start():m.end()]) in _GENERIC_SPELLINGS:
                spans.append(m.span())
    return tuple(spans)


_PROTECTED_BY_KEY: dict[str, tuple[str, ...]] = {}
for _phrase in _PROTECTED_PHRASES:
    _PROTECTED_BY_KEY[_key(_phrase)] = (*_PROTECTED_BY_KEY.get(_key(_phrase), ()), _phrase)


@lru_cache(maxsize=1024)
def _protected_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Vị trí các cụm _PROTECTED_PHRASES trong `text` (đã NFC), viết đúng dấu hoặc hoàn toàn không dấu."""
    folded = _fold_nfc(text)
    spans: list[tuple[int, int]] = []
    for key, phrases in _PROTECTED_BY_KEY.items():
        if key.split(" ", 1)[0] not in folded:
            continue
        for m in _name_pattern(key).finditer(folded):
            if any(_same_spelling(text[m.start():m.end()], p) for p in phrases):
                spans.append(m.span())
    return tuple(spans)


def accept_match(text: str, start: int, end: int, name: str, *, any_case: bool = False) -> bool:
    """Quy tắc chung "nhận chỗ khớp này không?" cho tên thật lẫn tên hư cấu.

    `text` đã chuẩn hoá NFC; `text[start:end]` trùng `name` khi bỏ dấu, theo ranh giới từ. Nhận khi:
    - viết như `name`: đúng dấu (không phân biệt hoa thường, dấu thanh kiểu cũ/mới), hoặc hoàn toàn không dấu;
    - viết hoa như tên riêng (bỏ qua khi `any_case`, dùng để ẩn tên trong thông báo lỗi, nơi ẩn thừa không hại gì):
      tên một âm tiết viết hoa chữ đầu; tên nhiều chữ thì chữ nào `name` viết hoa, chỗ khớp cũng viết hoa, trừ chữ chỉ
      loại đứng đầu ("đường", "cảng", "công ty", "ông"...) hay đứng cuối trong tiếng Anh ("street", "port"...);
    - không nằm trong một danh từ chung của GENERIC_TERMS viết đúng dấu ("Hung" trong "Hung thủ");
    - không nằm trọn bên trong một cụm _PROTECTED_PHRASES dài hơn nó ("Nam" trong "Việt Nam"). Tên dài chứa cả cụm đó
      ("Nguyễn Việt Nam") vẫn được nhận."""
    span = text[start:end]
    if not _same_spelling(span, name):
        return False
    if not any_case and not _capitalised_like(span, name):
        return False
    if any(a <= start and end <= b for a, b in _generic_spans(text)):
        return False
    return not any(a <= start and end <= b and b - a > end - start for a, b in _protected_spans(text))


@lru_cache(maxsize=8192)
def _name_pattern(key: str) -> re.Pattern:
    """Regex tìm một tên (dạng fold) theo ranh giới từ; giữa các chữ là khoảng trắng bất kỳ."""
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(tok) for tok in key.split()) + r"(?!\w)")


def _candidates(norm: str, names: Sequence[str], *, any_case: bool = False) -> list[tuple[int, int, list[int]]]:
    """Mọi chỗ trong `norm` (đã NFC) trùng một tên của `names` khi bỏ dấu mà accept_match nhận, kể cả các chỗ chồng nhau:
    (bắt đầu, kết thúc, chỉ số các tên nhận chỗ đó, theo thứ tự trong `names`)."""
    folded = _fold_nfc(norm)
    by_key: dict[str, list[int]] = {}
    for i, name in enumerate(names):
        key = _key(name)
        if key:
            by_key.setdefault(key, []).append(i)
    out: list[tuple[int, int, list[int]]] = []
    for key, indexes in by_key.items():
        if key.split(" ", 1)[0] not in folded:
            continue
        for m in _name_pattern(key).finditer(folded):
            start, end = m.span()
            ok = [i for i in indexes if accept_match(norm, start, end, names[i], any_case=any_case)]
            if ok:
                out.append((start, end, ok))
    return out


def _non_overlapping(cands: list[tuple[int, int, list[int]]]) -> list[tuple[int, int, list[int]]]:
    """Chọn các chỗ khớp không chồng nhau: chỗ dài hơn trước, bằng nhau thì chỗ đứng trước; trả theo thứ tự trong chuỗi."""
    chosen: list[tuple[int, int, list[int]]] = []
    for cand in sorted(cands, key=lambda c: (c[0] - c[1], c[0])):
        if all(cand[1] <= s or e <= cand[0] for s, e, _ in chosen):
            chosen.append(cand)
    return sorted(chosen, key=lambda c: c[0])


def _exact_first(span: str, indexes: list[int], names: Sequence[str]) -> list[int]:
    """`indexes` với các tên viết đúng y như `span` (giữ dấu) lên trước."""
    exact = [i for i in indexes if spelling_key(names[i]) == spelling_key(span)]
    return exact + [i for i in indexes if i not in exact]


def find_names(text: str, names: Sequence[str], *, any_case: bool = False) -> list[tuple[int, int, int]]:
    """Các chỗ trong `text` viết đúng một tên của `names` (accept_match), không chồng nhau, tên dài hơn thắng:
    (bắt đầu, kết thúc, chỉ số của tên trong `names`). Vị trí tính trên `text` đã NFC. Nhiều tên cùng nhận một chỗ thì
    chọn tên viết đúng y như chỗ đó, không có thì tên đứng trước."""
    if not text or not names:
        return []
    norm = unicodedata.normalize("NFC", text)
    return [(s, e, _exact_first(norm[s:e], indexes, names)[0])
            for s, e, indexes in _non_overlapping(_candidates(norm, names, any_case=any_case))]


# ---------------------------------------------------------------- tên thật trong chữ

def _active_entries(forbidden: Iterable[ForbiddenName]) -> list[ForbiddenName]:
    """Các tên còn hiệu lực, giữ thứ tự: bỏ tên rỗng, tên một âm tiết ngắn hơn 3 ký tự, và tên viết giống hệt
    (spelling_key) một tên đứng trước."""
    out: list[ForbiddenName] = []
    seen: set[str] = set()
    for fn in forbidden:
        key = _key(fn.real)
        if not key or (" " not in key and len(key) < 3):
            continue
        spelled = spelling_key(fn.real)
        if spelled in seen:
            continue
        seen.add(spelled)
        out.append(fn)
    return out


@dataclass(frozen=True)
class NameMatch:
    """Một chỗ trong chữ viết đúng một tên thật. Vị trí tính trên chữ đã NFC."""
    start: int
    end: int
    text: str                                # chữ như viết ở chỗ đó
    name: ForbiddenName                      # tên thật được chọn (mơ hồ thì là tên đứng trước có tên hư cấu)
    candidates: tuple[ForbiddenName, ...]    # mọi tên thật nhận chỗ này
    ambiguous: bool = False                  # viết không dấu, trùng nhiều tên thật có tên hư cấu khác nhau


def _alias_pair(fn: ForbiddenName) -> tuple[str, str]:
    return (fn.alias_vi or "").strip(), (fn.alias_en or "").strip()


def _resolve(span: str, accepted: tuple[ForbiddenName, ...]) -> tuple[ForbiddenName, bool]:
    """Tên thật của một chỗ khớp: tên viết đúng y như chỗ đó; chỗ viết không dấu mà khớp nhiều tên có tên hư cấu khác
    nhau thì không biết là ai: lấy tên đứng trước (theo thứ tự bảng tên) có tên hư cấu, và báo là mơ hồ."""
    exact = [fn for fn in accepted if spelling_key(fn.real) == spelling_key(span)]
    if exact:
        return exact[0], False
    if len({_alias_pair(fn) for fn in accepted}) <= 1:
        return accepted[0], False
    named = [fn for fn in accepted if any(_alias_pair(fn))]
    return (named or list(accepted))[0], True


def find_name_matches(text: str, forbidden: Iterable[ForbiddenName], aliases: Iterable[str] = (), *,
                      any_case: bool = False) -> list[NameMatch]:
    """Các chỗ trong `text` viết đúng một tên thật (accept_match), không chồng nhau, tên dài hơn thắng; bỏ chỗ nằm trọn
    trong một lần xuất hiện của tên hư cấu thuộc `aliases`. Alias trùng một tên thật (sau fold) không được tính là
    lá chắn, nếu không thì LLM đặt alias giống hệt tên thật sẽ lọt qua kiểm tra."""
    if not text:
        return []
    forbidden = list(forbidden)
    entries = _active_entries(forbidden)
    if not entries:
        return []
    norm = unicodedata.normalize("NFC", text)
    real_keys = {_key(f.real) for f in forbidden}
    shields = [a for a in dict.fromkeys(a.strip() for a in aliases if a and a.strip()) if _key(a) not in real_keys]
    shield_spans = [(s, e) for s, e, _ in _candidates(norm, shields, any_case=any_case)]
    cands = [c for c in _candidates(norm, [f.real for f in entries], any_case=any_case)
             if not any(a <= c[0] and c[1] <= b for a, b in shield_spans)]
    out: list[NameMatch] = []
    for start, end, indexes in _non_overlapping(cands):
        accepted = tuple(entries[i] for i in indexes)
        name, ambiguous = _resolve(norm[start:end], accepted)
        out.append(NameMatch(start, end, norm[start:end], name, accepted, ambiguous))
    return out


def _alias_for(fn: ForbiddenName, lang: Lang) -> Optional[str]:
    alias = ((fn.alias_vi if lang == "vi" else fn.alias_en) or "").strip()
    if not alias or _key(alias) == _key(fn.real):
        return None
    return alias


def _forbidden_aliases(forbidden: Iterable[ForbiddenName]) -> list[str]:
    return [a for f in forbidden for a in (f.alias_vi, f.alias_en) if a]


def _replace_names(text: str, forbidden: list[ForbiddenName], lang: Lang, pool: Iterable[str], *,
                   any_case: bool = False) -> tuple[str, list[tuple[NameMatch, str]]]:
    """Thay tên thật đã có alias bằng alias của `lang`. Trả (chữ mới, các (chỗ khớp, alias) đã thay)."""
    norm = unicodedata.normalize("NFC", text)
    parts: list[str] = []
    done: list[tuple[NameMatch, str]] = []
    last = 0
    for match in find_name_matches(norm, forbidden, pool, any_case=any_case):
        alias = _alias_for(match.name, lang)
        if alias is None:
            continue
        parts += [norm[last:match.start], alias]
        last = match.end
        done.append((match, alias))
    if not done:
        return text, []
    parts.append(norm[last:])
    return "".join(parts), done


def apply_aliases(text: str, forbidden: list[ForbiddenName], lang: Lang,
                  extra_aliases: Iterable[str] = (), *, any_case: bool = False) -> tuple[str, list[str]]:
    """Thay tên thật đã có alias bằng alias của `lang`. Trả (văn bản mới, các tên thật đã thay).
    Tên chưa có alias được để nguyên (find_unknown_names sẽ bắt). `any_case`: xem accept_match."""
    if not text:
        return text, []
    pool = [*_forbidden_aliases(forbidden), *extra_aliases]
    fixed, done = _replace_names(text, forbidden, lang, pool, any_case=any_case)
    return fixed, _unique(match.name.real for match, _alias in done)


def find_unknown_names(text: str, forbidden: list[ForbiddenName], aliases: list[str]) -> list[str]:
    """Tên thật còn sót trong `text`, bỏ qua chỗ nằm trọn trong một tên hư cấu thuộc `aliases`."""
    return _unique(match.name.real for match in find_name_matches(text, forbidden, aliases))


# ---------------------------------------------------------------- con số nhận dạng, dạng tên Việt trong lời Anh

# Con số đứng riêng, từ 2 chữ số (không dính chữ, dấu ":" hay "/": "22h15", "02:21", "15B1", "2020s" không tính).
_NUMBER = re.compile(r"(?<![\w.,:/\-])(\d{2,})(?![\w:/\-]|[.,]\d)")
# Trên chữ đã fold: chữ báo hiệu số nhà, biển số, số điện thoại... đứng ngay trước hoặc ngay sau con số. Không có "no"
# trơn, vì "nợ" bỏ dấu cũng là "no" ("nợ 50 triệu" là động cơ, không phải số nhà); "No." có dấu chấm thì vẫn tính.
_ID_CUE_BEFORE = re.compile(
    r"(?<!\w)(?:so nha|so|nha|duong|pho|hem|ngo|kiet|can ho|phong|bien so|bien kiem soat|dien thoai|sdt|"
    r"no\.|number|street|plate|phone|room|apartment|unit|#)\s*$")
_ID_CUE_AFTER = re.compile(r"\s*(?:duong|pho|street|st\.|road|avenue|lane)(?!\w)")
# Trong lời kể: con số là giờ, tuổi hay thời lượng thì giữ (spec 7.6).
_TIME_AGE_AFTER = re.compile(r"\s*(?:gio|phut|giay|tuoi|a\.?m\b|p\.?m\b|years?|year-old|minutes?|hours?|seconds?|"
                             r"o'clock|%)", re.IGNORECASE)
# Trên chữ gốc (giữ dấu, phân biệt hoa thường): đơn vị tiền và số lượng đứng ngay sau con số thì đó là số tiền, số lượng
# ("nợ 50 triệu", "30 người", "12 ngày"), không phải số nhận dạng. Viết hoa thì là tên đường ("số 88 Đồng Khởi").
_QUANTITY_AFTER = re.compile(
    r"\s*(?:triệu|tỷ|tỉ|nghìn|ngàn|trăm|đồng|usd|USD|vnd|VND|vnđ|VNĐ|dollars?|euros?|km|kg|mét|"
    r"người|people|persons?|ngày|tuần|tháng|days?|weeks?|months?)(?!\w)")


def _numbers(text: str) -> tuple[str, str, list[tuple[int, int]]]:
    """(chữ đã NFC, chữ đã fold, vị trí các con số đứng riêng). Hai chuỗi dài bằng nhau nên vị trí dùng chung."""
    norm = unicodedata.normalize("NFC", text or "")
    folded = _fold_nfc(norm)
    return norm, folded, [m.span(1) for m in _NUMBER.finditer(folded)]


def identifying_numbers(source_text: str) -> set[str]:
    """Các con số trong bài gốc đứng cạnh chữ báo hiệu số nhà, biển số, số điện thoại ("số 88", "88 Đường..."),
    trừ số tiền và số lượng."""
    norm, folded, spans = _numbers(source_text)
    found: set[str] = set()
    for start, end in spans:
        if _QUANTITY_AFTER.match(norm, end):
            continue
        if _ID_CUE_BEFORE.search(folded[max(0, start - 24):start]) or _ID_CUE_AFTER.match(folded, end):
            found.add(folded[start:end])
    return found


def find_identifying_numbers(text: str, id_numbers: set[str]) -> list[str]:
    """Con số nhận dạng của bài (`id_numbers`, xem identifying_numbers) còn trong `text`; giờ, tuổi, số tiền và số
    lượng thì giữ."""
    norm, folded, spans = _numbers(text)
    found: list[str] = []
    for start, end in spans:
        number = folded[start:end]
        if number not in id_numbers or number in found:
            continue
        if _TIME_AGE_AFTER.match(folded, end) or _QUANTITY_AFTER.match(norm, end):
            continue
        found.append(number)
    return found


def find_vi_forms_in_en(text: str, entities: Iterable) -> list:
    """Các thực thể (CaseEntity) có tên hư cấu dạng tiếng Việt (Hán-Việt...) xuất hiện trong lời Anh `text`, khi dạng
    Anh khác hẳn. Mã số (identifier) thì bỏ qua."""
    if not text:
        return []
    norm = unicodedata.normalize("NFC", text)
    out = []
    for ent in entities:
        if ent.kind == "identifier":
            continue
        key_vi, key_en = _key(ent.alias_vi or ""), _key(ent.alias_en or "")
        if not key_vi or not key_en or key_vi == key_en or key_vi in key_en:
            continue
        en_spans = [(s, e) for s, e, _ in find_names(norm, [ent.alias_en])]
        if any(not any(a <= s and e <= b for a, b in en_spans) for s, e, _ in find_names(norm, [ent.alias_vi])):
            out.append(ent)
    return out


# ---------------------------------------------------------------- lời trích không có trong bài

# Lời nói trực tiếp trong lời kể: chữ trong cặp ngoặc kép (“...”, "...", «...», 「...」).
_QUOTE = re.compile(r'“([^”]+)”|"([^"]+)"|«([^»]+)»|「([^」]+)」')
MIN_QUOTE_WORDS = 4      # ngắn hơn thường là biệt danh, tên gọi hay chữ nhấn mạnh, không phải một câu nói


def _plain(text: str) -> str:
    """Chữ đã fold, bỏ dấu câu, khoảng trắng gộp: để so một lời trích với bài gốc."""
    return " ".join(re.sub(r"\W+", " ", fold(text or "")).split())


def quotes_in(text: str) -> list[str]:
    """Các lời trích trong ngoặc kép dài từ MIN_QUOTE_WORDS từ trở lên."""
    out: list[str] = []
    for match in _QUOTE.finditer(unicodedata.normalize("NFC", text or "")):
        quote = next(g for g in match.groups() if g is not None).strip()
        if len(quote.split()) >= MIN_QUOTE_WORDS and quote not in out:
            out.append(quote)
    return out


def quote_source(source_text: str, forbidden: list[ForbiddenName], lang: Lang) -> str:
    """Bài gốc đã đổi tên thật sang tên hư cấu của `lang` rồi chuẩn hoá như _plain, để tìm lời trích của lời kể."""
    aliased, _done = apply_aliases(source_text or "", forbidden, lang)
    return f" {_plain(aliased)} "


def find_unsourced_quotes(text: str, source: str) -> list[str]:
    """Lời trích trong `text` không có nguyên văn trong bài gốc (`source` lấy từ quote_source). Lời kể và bài phải
    cùng ngôn ngữ; khác ngôn ngữ thì lời trích là bản dịch, không so được."""
    return [q for q in quotes_in(text) if f" {_plain(q)} " not in source]


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
# Đơn vị tiền và đơn vị đo viết tắt: đứng ngay sau con số thì đó là số lượng, không phải năm.
_UNAMBIGUOUS_UNIT_AFTER = re.compile(
    r"\s*(?:usd|vnd|vnđ|ntd|nt\$|đồng|đ|đô|euros?|dollars?|bucks|yuan|rmb|baht|tệ|triệu|tỷ|mét|km|kg)(?!\w)",
    re.IGNORECASE,
)
# Danh từ có thể đứng ngay sau một năm ("In 2014 people left"): chỉ coi là số lượng khi có từ chỉ lượng
# đứng ngay trước con số ("about 2000 people", "hơn 2000 người").
_AMBIGUOUS_UNIT_AFTER = re.compile(r"\s*(?:người|people|words|miles|meters|feet)(?!\w)", re.IGNORECASE)
_QUANTITY_CUE_BEFORE = re.compile(
    r"(?<!\w)(?:total\s+of|number\s+of|about|over|around|nearly|almost|than|approximately|roughly|some|only|"
    r"up\s+to|hơn|khoảng|gần|tầm|chừng|trên|dưới|xấp\s+xỉ|ước|cỡ)\s*$",
    re.IGNORECASE,
)


def _year_is_kept(norm: str, folded: str, start: int, end: int, *, allow_units: bool = True) -> bool:
    """Năm đứng riêng nhưng thực ra là thập niên (2010s, thập niên 2010, những năm 1990) hoặc số tiền/số lượng.
    `allow_units=False` cho dạng "in YYYY": đã có giới từ chỉ thời gian nên không bao giờ là số lượng."""
    if _PLURAL_AFTER.match(norm, end):
        return True
    before = folded[:start].rstrip()
    if _DECADE_BEFORE.search(before):
        return True
    if norm[start:end].endswith("0") and before.endswith("nhung nam"):
        return True
    if not allow_units:
        return False
    if _UNAMBIGUOUS_UNIT_AFTER.match(norm, end):
        return True
    return bool(_AMBIGUOUS_UNIT_AFTER.match(norm, end) and _QUANTITY_CUE_BEFORE.search(norm[:start]))


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
        if not _year_is_kept(norm, folded, m.start(1), m.end(1), allow_units=False):
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


# Chữ nối đứng ngay trước ngày tháng trong một nhãn ngắn, bỏ cùng ngày ("ngày 28 tháng 2", "on February 28").
_DATE_LEAD = re.compile(r"(?:[\s,(\-–]*\b(?:ngày|hôm|vào|lúc|năm|on|dated|from|in|of)\b)?[\s,(\-–]*$", re.IGNORECASE)


def strip_dates(text: str) -> tuple[str, list[str]]:
    """Bỏ ngày tháng, năm cụ thể (find_dates) khỏi một nhãn ngắn (tên tập, nhãn bằng chứng/quan hệ), kèm chữ nối ngay
    trước. Trả (nhãn mới, các ngày đã bỏ); bỏ xong mà nhãn rỗng thì giữ nguyên nhãn và trả [] để người dùng tự sửa."""
    found = find_dates(text)
    if not found:
        return text, []
    out = unicodedata.normalize("NFC", text)
    for date in found:
        at = out.find(date)
        if at < 0:
            continue
        out = _DATE_LEAD.sub("", out[:at]) + " " + out[at + len(date):]
    out = " ".join(out.split()).strip(" ,;:-–(")
    return (out, found) if out else (text, [])


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
    """Trả bản sao đã kiểm; không đổi `plan`. Gọi lại sau mỗi lần người dùng sửa đều đúng.

    - `warnings` là danh sách bền: không bao giờ xoá, chỉ nối thêm các thông báo "Đã tự thay..." (không trùng).
      Thông báo do bước khác ghi vào (ví dụ bài chỉ đủ tư liệu cho N phút) vì vậy còn nguyên.
    - `check_warnings` và mọi cờ (`flags` ở từng cảnh và `flags` cấp kế hoạch) tính lại từ đầu mỗi lần.
    - Tên thật đã có alias: tự thay (lời kể, prompt, tên tập, nhãn bằng chứng/quan hệ) và ghi vào `warnings`.
    - Cờ chặn tạo dự án:
        * ở cảnh: tên thật chưa có alias (lời kể, prompt), thiếu lời kể, id lạ trong board_reveal, ngày cụ thể trong lời kể;
        * cấp kế hoạch: tên thật chưa có alias trong tên tập (field "title") hoặc nhãn ("evidence:<id>", "relation:<id>").
    - Ngày cụ thể trong tên tập và nhãn bằng chứng/quan hệ (hiện trong video, màn xem lại không sửa được nhãn): tự bỏ
      (strip_dates) và ghi vào `warnings`; nhãn chỉ có ngày thì giữ nguyên và cảnh báo.
    - Ngày cụ thể trong prompt hình và bằng chứng chưa hiện ra: chỉ vào `check_warnings`, không chặn.
    - Cũng chỉ vào `check_warnings` (các bước viết gọi lại model khi gặp, nhưng hết lượt thì vẫn nhận kết quả):
        * tên viết không dấu trùng tên thật của nhiều người có tên hư cấu khác nhau: đã thay bằng tên hư cấu của thực thể
          đứng trước trong bảng tên, cảnh báo nêu cảnh và tên hư cấu đã dùng, không nêu tên thật;
        * con số nhận dạng lấy từ bài gốc (số nhà, biển số...) còn trong lời kể hay prompt;
        * tên hư cấu dạng tiếng Việt trong lời Anh;
        * lời trích trong ngoặc kép không có nguyên văn trong bài gốc (chỉ so khi lời kể cùng ngôn ngữ với bài);
        * lời kể bản Việt hay bản Anh đọc lâu hơn số phút đã chọn quá DURATION_WARN_RATIO (tính cả cảnh miễn trừ).
    - Cảnh `disclaimer` không bị quét.
    """
    new = plan.model_copy(deep=True)
    bible = new.bible
    forbidden = build_forbidden_names(bible, source_text)
    aliases = _unique(a.strip() for e in bible.entities for a in (e.alias_vi, e.alias_en) if a and a.strip())
    pool = [*_forbidden_aliases(forbidden), *aliases]
    id_numbers = identifying_numbers(source_text)
    # bài gốc đã đổi tên, để so lời trích; chỉ dựng khi có lời kể cùng ngôn ngữ với bài và có lời trích
    quote_lang = bible.source_language if bible.source_language in ("vi", "en") and source_text.strip() else None
    quote_sources: dict[str, str] = {}
    if quote_lang and any(quotes_in(getattr(s, f"narration_{quote_lang}")) for s in new.scenes):
        quote_sources[quote_lang] = quote_source(source_text, forbidden, quote_lang)
    warnings: list[str] = list(new.warnings)    # bền: chỉ nối thêm
    check_warnings: list[str] = []              # tính lại từ đầu
    plan_flags: list[SceneFlag] = []            # tính lại từ đầu

    def note(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    def warn(message: str) -> None:
        if message not in check_warnings:
            check_warnings.append(message)

    def clean(text: str, lang: Lang, where: str) -> tuple[str, list[tuple[str, str]], list[str]]:
        """Thay tên, trả (chữ mới, các (tên thật, alias) đã thay chắc chắn, tên thật còn sót). Chỗ mơ hồ đã thay thì
        cảnh báo ở `where`, không ghi vào `warnings` vì không biết đó là tên thật nào."""
        fixed, done = _replace_names(text, forbidden, lang, pool)
        pairs = _unique((match.name.real, alias) for match, alias in done if not match.ambiguous)
        for alias in _unique(alias for match, alias in done if match.ambiguous):
            warn(f"Đã thay một tên viết không dấu (trùng tên thật của nhiều người) bằng '{alias}' ở {where}, theo "
                 "thực thể đứng trước trong bảng tên; hãy xem lại cho đúng người.")
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
            where = f"cảnh {scene.order} ({field})"
            fixed, pairs, unknown = clean(text, lang, where)
            if fixed != text:
                setattr(scene, field, fixed)
            for real, alias in pairs:
                note(f"Đã tự thay tên thật '{real}' bằng '{alias}' ở {where}.")
            for name in unknown:
                flags.append(SceneFlag(kind="unknown_name", field=field,
                                       detail=f"Tên thật chưa có tên thay thế: '{name}'."))
            for found in _unique(find_dates(fixed)):
                if field in _NARRATION_FIELDS:
                    flags.append(SceneFlag(kind="date", field=field,
                                           detail=f"Ngày tháng hoặc năm cụ thể: '{found}'."))
                else:
                    warn(f"Còn ngày tháng hoặc năm cụ thể '{found}' ở {where}; hãy sửa thành cách nói chung.")
            for number in find_identifying_numbers(fixed, id_numbers):
                warn(f"Còn con số nhận dạng '{number}' lấy từ bài gốc (số nhà, biển số, số điện thoại...) ở {where}; "
                     "hãy bỏ số này hoặc nói chung chung.")
            if field == "narration_en":
                for ent in find_vi_forms_in_en(fixed, bible.entities):
                    warn(f"Lời Anh ở {where} dùng dạng tên tiếng Việt '{ent.alias_vi}'; hãy đổi thành '{ent.alias_en}'.")
            if field in _NARRATION_FIELDS and lang in quote_sources:
                for quote in find_unsourced_quotes(fixed, quote_sources[lang]):
                    warn(f"Lời trích \"{quote}\" ở {where} không có nguyên văn trong bài gốc; hãy kể gián tiếp hoặc "
                         "chép đúng câu trong bài.")
        for rid in _unique(scene.board_reveal):
            if rid not in valid_ids:
                flags.append(SceneFlag(kind="bad_reveal", field="board_reveal",
                                       detail=f"Id không có trong bằng chứng hoặc quan hệ: '{rid}'."))
        scene.flags = flags

    # --- tên tập và nhãn bằng chứng/quan hệ: hiện trong video nên tên thật chưa có alias là cờ cấp kế hoạch
    def clean_label(obj, field: str, lang: Lang, where: str, flag_field: str) -> None:
        text = getattr(obj, field)
        if not text or not text.strip():
            return
        fixed, pairs, unknown = clean(text, lang, f"{where} ({field})")
        if fixed != text:
            setattr(obj, field, fixed)
        for real, alias in pairs:
            note(f"Đã tự thay tên thật '{real}' bằng '{alias}' ở {where} ({field}).")
        for name in unknown:
            plan_flags.append(SceneFlag(kind="unknown_name", field=flag_field,
                                        detail=f"Tên thật chưa có tên thay thế ở {where} ({field}): '{name}'."))
        # tên tập và nhãn hiện ra trong video (bảng ghim) mà màn xem lại không sửa được nhãn: tự bỏ ngày cụ thể
        undated, removed = strip_dates(fixed)
        if removed:
            setattr(obj, field, undated)
            note(f"Đã tự bỏ ngày tháng cụ thể {', '.join(repr(d) for d in removed)} ở {where} ({field}).")
        for found in _unique(find_dates(undated)):
            warn(f"Còn ngày tháng hoặc năm cụ thể '{found}' ở {where} ({field}); hãy sửa thành cách nói chung.")

    clean_label(bible, "title_vi", "vi", "tiêu đề", "title")
    clean_label(bible, "title_en", "en", "tiêu đề", "title")
    for ev in bible.evidence:
        clean_label(ev, "label_vi", "vi", f"nhãn bằng chứng '{ev.id}'", f"evidence:{ev.id}")
        clean_label(ev, "label_en", "en", f"nhãn bằng chứng '{ev.id}'", f"evidence:{ev.id}")
    for rel in bible.relations:
        clean_label(rel, "label_vi", "vi", f"nhãn quan hệ '{rel.id}'", f"relation:{rel.id}")
        clean_label(rel, "label_en", "en", f"nhãn quan hệ '{rel.id}'", f"relation:{rel.id}")

    # --- bằng chứng chưa hiện ra ở cảnh nào
    for ev in bible.evidence:
        if ev.id not in revealed:
            warn(f"Bằng chứng '{ev.id}' ({ev.label_vi}) chưa hiện ra trên bảng điều tra ở cảnh nào.")

    # --- thời lượng: số chữ mỗi cảnh đã giới hạn ở các bước viết, nhưng người dùng sửa lời hay dàn ý nhiều cảnh vẫn có
    # thể làm cả video dài hơn số phút đã chọn; báo để rút gọn
    for lang, label in (("vi", "bản Việt"), ("en", "bản Anh")):
        minutes = speech_minutes((getattr(s, f"narration_{lang}") for s in new.scenes), lang)
        if new.target_minutes and minutes > new.target_minutes * DURATION_WARN_RATIO:
            rate = VI_WORDS_PER_MINUTE if lang == "vi" else EN_WORDS_PER_MINUTE
            shown = f"{minutes:.1f}".replace(".", ",")
            warn(f"Lời kể {label} đọc mất khoảng {shown} phút (khoảng {rate} từ mỗi phút), dài hơn video "
                 f"{new.target_minutes} phút đã chọn; hãy rút gọn lời ở các cảnh dài.")

    new.warnings = warnings
    new.check_warnings = check_warnings
    new.flags = plan_flags
    return new


def has_blocking_flags(plan: CaseAdaptationPlan) -> bool:
    """Còn cờ ở cảnh hoặc cờ cấp kế hoạch (tên tập, nhãn) thì chặn tạo dự án."""
    return bool(plan.flags) or any(scene.flags for scene in plan.scenes)
