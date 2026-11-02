"""Kiểm lời kể: kể đủ ý, không kể lặp, không trái điều đã kể, giữ ngôi thứ ba (khuôn và luật bằng code, không gọi LLM).

Chủ dự án 29/10–02/11/2026 (CLAUDE.md mục 1.2 câu 10, 11, 14, 21): số phút chỉ để AI không làm tắt; phải tách việc,
làm từng phần, đủ ý, không cắt gọt, và chặn bằng script chứ không chỉ ghi CLAUDE.md. Gặp 29/10/2026: video Trạm Dung
kể việc phát hiện thi thể hai lần như hai lần khác nhau (cảnh 5 "dọn mảng trần sập", cảnh 11 "giữa bếp và phòng ngủ,
dưới lớp quần áo"), người xem tưởng truyện mâu thuẫn.

Cách dùng (mọi bước viết lời kể đều phải qua, test kiến trúc kiểm):
1. Viết xong một phần thì gọi LLM kiểm riêng với `verify_prompt(...)`.
2. `check_verify(...)` đối chiếu bằng code: mỗi ý phải có câu trích NGUYÊN VĂN có thật trong lời kể; lỗi kể lặp / trái
   điều đã kể chỉ tính khi kèm câu trích có thật. Câu trích bịa thì `QuoteRejected` (người gọi bắt LLM kiểm lại).
3. Còn ý thiếu hoặc lỗi thì `feedback_for_writer(...)` thành góp ý để viết lại phần đó.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

MIN_QUOTE_WORDS = 3            # câu trích quá ngắn ("cô ấy") khớp ở đâu cũng được, không làm bằng chứng
MAX_FACTS_PER_PART = 8
MAX_FACTS_IN_PROMPT = 40       # bảng sự thật gửi kèm: chỉ những dòng gần nhất
ISSUE_KINDS = {
    "lap_lai": "kể lại như mới một sự việc đã kể ở phần trước",
    "trai_nguoc": "nói khác bảng sự thật đã kể hoặc khác đoạn gốc",
    "bia": "thêm sự việc, chi tiết hay lời nói mà đoạn gốc không có",
}
# Lời kể ngôi thứ ba: người kể không xưng "tôi" (lời thoại trong ngoặc kép thì được)
_FIRST_PERSON = {
    "vi": re.compile(r"(?<![\wÀ-ỹ])(tôi|chúng tôi|tao|chúng tao)(?![\wÀ-ỹ])", re.IGNORECASE),
    "en": re.compile(r"\b(I|me|my|mine|myself)\b"),
}
_QUOTED = re.compile(r"“[^”]*”|\"[^\"]*\"|«[^»]*»|‘[^’]*’")


class QuoteRejected(ValueError):
    """Bản kiểm của LLM có câu trích không có trong lời kể; `reason` gửi lại cho LLM kiểm."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def normalize(text: str) -> str:
    """Chữ thường, NFC, bỏ dấu câu và khoảng trắng thừa: để so câu trích với lời kể."""
    text = unicodedata.normalize("NFC", str(text or "")).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def quote_found(quote: str, texts: list[str]) -> bool:
    q = normalize(quote)
    if len(q.split()) < MIN_QUOTE_WORDS:
        return False
    return any(q in normalize(t) for t in texts)


def first_person_hits(text: str, lang: str) -> list[str]:
    """Các chữ xưng ngôi thứ nhất của người kể (ngoài lời thoại trong ngoặc kép)."""
    pattern = _FIRST_PERSON.get(lang)
    if pattern is None:
        return []
    return [m.group(0) for m in pattern.finditer(_QUOTED.sub(" ", str(text or "")))]


def fact_lines(facts: list[str]) -> str:
    shown = [f for f in facts if f][-MAX_FACTS_IN_PROMPT:]
    return "\n".join(f"- {f}" for f in shown) or "(chưa có: đây là phần đầu)"


def verify_prompt(points: list[tuple[str, str]], scenes: list[str], facts: list[str], source: str,
                  note: str = "") -> str:
    """Việc kiểm: tìm câu trích cho từng ý, bắt lỗi kể lặp / trái / bịa, ghi sự thật mới của phần này."""
    point_lines = "\n".join(f"- {pid}: {text}" for pid, text in points)
    scene_lines = "\n".join(f"[cảnh {k}] {t}" for k, t in enumerate(scenes, start=1))
    kinds = "\n".join(f'- "{k}": {v}' for k, v in ISSUE_KINDS.items())
    return f"""TASK: kiem_loi_ke

Bạn là người kiểm tra lời kể của một video kể chuyện. Không viết lại, chỉ kiểm.

ĐOẠN GỐC:
{source}

CÁC Ý PHẢI CÓ (id: nội dung):
{point_lines}

BẢNG SỰ THẬT ĐÃ KỂ Ở CÁC PHẦN TRƯỚC:
{fact_lines(facts)}

LỜI KỂ CẦN KIỂM:
{scene_lines}

Làm 3 việc:
1. "quotes": với MỖI ý ở trên, nếu lời kể có kể ý đó thì chép NGUYÊN VĂN một câu (hoặc một cụm ít nhất {MIN_QUOTE_WORDS + 3} từ) trong lời kể chứng minh, kèm số cảnh. Chép đúng từng chữ, không sửa, không tóm lại. Ý nào lời kể không kể thì KHÔNG ghi ý đó.
2. "issues": lỗi của lời kể, mỗi lỗi chép NGUYÊN VĂN câu sai vào "quote". Loại lỗi:
{kinds}
   Nhận xét, cảm nghĩ của người kể (kiểu người review) không phải lỗi "bia". Không có lỗi thì để [].{(' ' + note) if note else ''}
3. "facts": tối đa {MAX_FACTS_PER_PART} sự thật MỚI mà phần này đã kể (ai, làm gì, ở đâu, khi nào, chi tiết then chốt), mỗi dòng một câu ngắn, để các phần sau không kể lại hay kể khác đi.

Trả đúng một JSON object:
{{"quotes": [{{"point_id": "p1", "scene": 1, "quote": "..."}}], "issues": [{{"scene": 2, "kind": "lap_lai", "quote": "...", "detail": "..."}}], "facts": ["..."]}}"""


class _Item(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Quote(_Item):
    point_id: str = ""
    scene: int = 0
    quote: str = ""


class _Issue(_Item):
    scene: int = 0
    kind: str = ""
    quote: str = ""
    detail: str = ""


class _VerifyOut(_Item):
    quotes: list[_Quote] = []
    issues: list[_Issue] = []
    facts: list[str] = []

    @field_validator("facts", mode="before")
    @classmethod
    def _as_list(cls, value: Any) -> Any:
        return [value] if isinstance(value, str) else value


def check_verify(raw: Any, point_ids: list[str], scenes: list[str]) -> dict:
    """Đối chiếu bản kiểm của LLM với lời kể bằng code.

    Trả {"covered": {id: (cảnh, câu trích)}, "missing": [id], "issues": [...], "facts": [...]}.
    Câu trích bịa (không có trong lời kể) thì QuoteRejected để LLM kiểm lại; lỗi kèm câu trích bịa bị bỏ."""
    parsed = _VerifyOut.model_validate(raw)
    known = set(point_ids)
    covered: dict[str, tuple[int, str]] = {}
    fake = []
    for q in parsed.quotes:
        pid = q.point_id.strip()
        if pid not in known or pid in covered:
            continue
        if quote_found(q.quote, scenes):
            covered[pid] = (q.scene, q.quote.strip())
        else:
            fake.append(pid)
    if fake:
        raise QuoteRejected(
            f"câu trích của {', '.join(fake[:10])} không có nguyên văn trong lời kể; chép đúng từng chữ một câu có "
            f"thật trong lời kể (ít nhất {MIN_QUOTE_WORDS + 3} từ), hoặc bỏ ý đó khỏi quotes nếu lời kể không kể")
    issues = []
    for it in parsed.issues:
        kind = it.kind.strip()
        if kind in ISSUE_KINDS and quote_found(it.quote, scenes):
            issues.append({"scene": it.scene, "kind": kind, "quote": it.quote.strip(), "detail": it.detail.strip()})
    facts = [" ".join(str(f).split()) for f in parsed.facts if str(f).strip()][:MAX_FACTS_PER_PART]
    return {"covered": covered, "missing": [p for p in point_ids if p not in covered], "issues": issues,
            "facts": facts}


def feedback_for_writer(result: dict, points: dict[str, str]) -> str:
    """Góp ý cho lần viết lại, từ kết quả check_verify."""
    lines = []
    if result["missing"]:
        lines.append("Lời kể CHƯA KỂ các ý sau, phải kể đủ, đúng thứ tự: "
                     + "; ".join(f"{p} ({points.get(p, '')})" for p in result["missing"]))
    for it in result["issues"]:
        lines.append(f'cảnh {it["scene"]}: lỗi {ISSUE_KINDS[it["kind"]]}: "{it["quote"]}" — {it["detail"]}')
    return "\n".join(lines)
