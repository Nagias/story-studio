"""Truyện chữ thành lời review từng cảnh, kể đủ ý (luồng 1-Click Bước 1).

Chủ dự án (CLAUDE.md mục 1.2): remake là kể kiểu review (câu 1, 16), không bê nguyên văn (câu 16); số phút chỉ để AI
không làm tắt, phải tách việc làm từng phần cho đủ ý (câu 10, 14) và chặn bằng script (câu 14, 21); truyện chọn tiếng
Việt hoặc tiếng Anh (câu 15).

Mỗi phần truyện (cắt theo đoạn văn, `PART_MAX_CHARS`) đi qua 3 việc LLM nhỏ, mỗi việc có code kiểm:
1. liet_ke_y: liệt kê mọi ý của phần (số ý tối thiểu theo độ dài phần).
2. viet_review: viết các cảnh, mỗi cảnh khai đã kể ý nào; code kiểm đủ ý, độ dài, đúng ngôn ngữ, ngôi thứ ba.
3. kiem_loi_ke (coverage_guard): LLM khác lượt trích nguyên văn bằng chứng cho từng ý và bắt lỗi kể lặp / trái điều
   đã kể; code đối chiếu câu trích. Thiếu ý hoặc có lỗi thì viết lại phần đó (tối đa `MAX_ROUNDS` vòng), hết vòng thì
   StoryReviewError: báo rõ cho người dùng, KHÔNG chép nguyên văn bài gốc thay lời review.
Sự thật mỗi phần đã kể dồn vào "bảng sự thật" gửi kèm các phần sau.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from services import case_adaptation_llm, coverage_guard
from services.case_adaptation_prompts import word_count
from services.case_adaptation_steps import StepFailed, StepRejected, ask_validated, chunk_source

logger = logging.getLogger("StoryReview")

LANGUAGES = ("vi", "en")
PART_MAX_CHARS = 2400          # cỡ đoạn của luồng vụ án: đủ ngắn để LLM không làm tắt
PART_MAX_CHARS_ZH = 1000       # tiếng Trung đặc chữ: 1.000 chữ Hán ~ 2.400 ký tự tiếng Việt về lượng nội dung
CHARS_PER_POINT_ZH = 140
MAX_ROUNDS = 3                 # viết → kiểm → viết lại
CHARS_PER_POINT = 350          # phần 2.400 ký tự phải có ít nhất 6 ý
MIN_POINTS = 2
SCENE_WORDS = {"vi": (10, 34), "en": (8, 28)}
WORDS_PER_SECOND = {"vi": 4.2, "en": 2.6}   # nhịp review (đo 29/10/2026: Trúc Ly 261, Andrew ~150 chữ/phút)
# Lời review phải dài ít nhất chừng này so với phần gốc (đếm từ; tiếng Việt đếm theo tiếng, tiếng Anh theo từ, tiếng
# Trung theo chữ Hán: một chữ Hán ~ một tiếng Hán Việt)
MIN_WORD_RATIO = {("vi", "vi"): 0.55, ("en", "en"): 0.55, ("vi", "en"): 0.4, ("en", "vi"): 0.75,
                  ("zh", "vi"): 0.5, ("zh", "en"): 0.3}
CAMERA_MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "action_camera_shake")
BEATS = ("hook", "setting", "escalation", "climax", "resolution")
_VI_MARKS = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", re.IGNORECASE)

STORY_SYSTEM = """\
Bạn là biên kịch cho kênh YouTube review truyện (light novel, truyện chữ). Người kể là một reviewer kể lại câu chuyện cho khán giả: kể ngôi thứ ba về các nhân vật, giọng kể nhanh, gọn, cuốn như review phim.
Công việc được chia thành nhiều việc nhỏ; mỗi tin nhắn giao đúng một việc (dòng đầu "TASK: ..."). Làm đúng, làm đủ việc đó.
Chỉ trả đúng một JSON object theo mẫu, không kèm chữ nào khác."""

_progress: dict[str, str] = {}


class StoryReviewError(Exception):
    """Không viết được lời review đạt yêu cầu; `user_message` nói phần nào, vì sao."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


def progress_of(job_id: str) -> Optional[str]:
    return _progress.get(job_id)


async def _story_llm(_system: str, user: str, **kwargs: Any) -> Any:
    """ask_validated gửi lời dặn hệ thống của luồng vụ án; truyện dùng lời dặn riêng."""
    return await case_adaptation_llm.call_llm_json(STORY_SYSTEM, user, **kwargs)


_HAN = re.compile(r"[一-鿿]")


def detect_text_language(text: str) -> str:
    """"vi" | "en" | "zh" (truyện tiếng Trung: lời review mặc định tiếng Việt)."""
    text = text or ""
    if len(_HAN.findall(text)) >= max(20, 0.2 * len("".join(text.split()))):
        return "zh"
    return "vi" if len(_VI_MARKS.findall(text)) >= 5 else "en"


def source_words(text: str, lang: str) -> int:
    return len(_HAN.findall(text or "")) if lang == "zh" else word_count(text)


# ---------------------------------------------------------------- việc 1: liệt kê ý

class _Item(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Points(_Item):
    points: list[str]

    @field_validator("points", mode="before")
    @classmethod
    def _texts(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [v.get("text", "") if isinstance(v, dict) else v for v in value]
        return value


def min_points(part: str) -> int:
    per = CHARS_PER_POINT_ZH if len(_HAN.findall(part)) > len(part) // 3 else CHARS_PER_POINT
    return max(MIN_POINTS, len(part) // per)


def points_prompt(part: str, lang: str, index: int, total: int) -> str:
    out = "tiếng Việt" if lang == "vi" else "tiếng Anh"
    return f"""TASK: liet_ke_y (phần {index}/{total} của truyện)

Liệt kê MỌI ý của đoạn truyện dưới đây theo đúng thứ tự: từng sự việc, chi tiết quan trọng (ai, ở đâu, làm gì, kết quả), lời thoại then chốt (ghi ý của câu thoại), cảm xúc hay bước ngoặt của nhân vật. Không gộp nhiều sự việc vào một ý, không bỏ ý nào.
Đoạn này dài {len(part)} ký tự nên cần ít nhất {min_points(part)} ý. Mỗi ý là một câu {out} từ 8 đến 30 từ.

ĐOẠN TRUYỆN:
{part}

Trả: {{"points": ["...", "..."]}}"""


def check_points(raw: Any, part: str) -> list[str]:
    parsed = _Points.model_validate(raw)
    points = [" ".join(str(p).split()) for p in parsed.points if str(p).strip()]
    need = min_points(part)
    if len(points) < need:
        raise StepRejected(f"chỉ có {len(points)} ý, đoạn này cần ít nhất {need} ý; liệt kê đủ, không gộp")
    short = [p for p in points if word_count(p) < 6]
    if short:
        raise StepRejected(f"có {len(short)} ý quá ngắn (dưới 6 từ), vd \"{short[0]}\"; mỗi ý là một câu đủ nghĩa")
    return points


# ---------------------------------------------------------------- việc 2: viết lời review

class _Scene(_Item):
    text: str = ""
    covers: list[str] = []
    image_prompt: str = ""
    narrative_beat: str = "setting"
    camera_motion: str = "zoom_in"

    @field_validator("covers", mode="before")
    @classmethod
    def _ids(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value


class _Written(_Item):
    scenes: list[_Scene]


def write_prompt(part: str, points: list[tuple[str, str]], facts: list[str], prev_tail: list[str], lang: str,
                 index: int, total: int, style_preset: str, feedback: str = "") -> str:
    out = "TIẾNG VIỆT" if lang == "vi" else "TIẾNG ANH (English)"
    lo, hi = SCENE_WORDS[lang]
    point_lines = "\n".join(f"- {pid}: {text}" for pid, text in points)
    prev = "\n".join(f"- {t}" for t in prev_tail) or "(chưa có: đây là phần đầu)"
    opening = ("Đây là phần ĐẦU: cảnh 1 mở bằng khoảnh khắc gây tò mò hoặc căng nhất của phần này (kể lửng, chưa nói "
               "hết), rồi kể theo thứ tự." if index == 1 else
               "Đây là phần GIỮA truyện: kể tiếp liền mạch từ cảnh trước, KHÔNG mở đầu lại, KHÔNG giới thiệu lại truyện.")
    redo = f"\n\nLẦN VIẾT TRƯỚC CHƯA ĐẠT, SỬA ĐÚNG CÁC CHỖ SAU:\n{feedback}" if feedback else ""
    return f"""TASK: viet_review (phần {index}/{total})

Viết lời kể kiểu review truyện bằng {out} cho các cảnh video của phần truyện dưới đây.

LUẬT VIẾT:
1. Kể ĐỦ mọi ý trong danh sách, đúng thứ tự; mỗi cảnh ghi "covers" là id các ý cảnh đó kể (1 đến 3 ý). Không bỏ ý nào, không dồn nhiều ý vào một câu cho ngắn.
2. Giọng review phim: kể lại bằng lời của bạn (không chép nguyên văn truyện), ngôi thứ ba về nhân vật, người kể không xưng "tôi". Câu ngắn, động từ mạnh, từ nối tạo đà ("Đúng lúc đó", "Thế nhưng", "Vừa... thì..."). Được thêm một câu nhận xét ngắn của người kể khi hợp, nhưng không bịa sự việc mới.
3. Không lặp lại điều đã kể trong BẢNG SỰ THẬT, không kể lại một sự việc đã kể như thể mới xảy ra, không nói khác đi các chi tiết đã kể.
4. Mỗi cảnh {lo}–{hi} từ. "image_prompt" viết bằng tiếng Anh: góc máy, nhân vật, hành động, bối cảnh, ánh sáng của đúng cảnh đó (phong cách {style_preset}).
5. {opening}

BẢNG SỰ THẬT ĐÃ KỂ:
{coverage_guard.fact_lines(facts)}

CÁC CẢNH NGAY TRƯỚC:
{prev}

CÁC Ý PHẢI KỂ (id: nội dung):
{point_lines}

ĐOẠN TRUYỆN GỐC:
{part}{redo}

Trả: {{"scenes": [{{"text": "...", "covers": ["p1"], "image_prompt": "...", "narrative_beat": "{'|'.join(BEATS)}", "camera_motion": "{'|'.join(CAMERA_MOTIONS)}"}}]}}"""


def check_written(raw: Any, point_ids: list[str], part: str, lang: str, src_lang: str) -> list[dict]:
    parsed = _Written.model_validate(raw)
    if not parsed.scenes:
        raise StepRejected("không có cảnh nào")
    lo, hi = SCENE_WORDS[lang]
    known = set(point_ids)
    problems: list[str] = []
    covered: set[str] = set()
    scenes = []
    for k, s in enumerate(parsed.scenes, start=1):
        text = " ".join(s.text.split())
        words = word_count(text)
        if not lo <= words <= hi:
            problems.append(f"cảnh {k} dài {words} từ, cần {lo}–{hi} từ")
        ids = [c for c in s.covers if c in known]
        if not ids:
            problems.append(f"cảnh {k} không khai ý nào trong covers")
        covered.update(ids)
        hits = coverage_guard.first_person_hits(text, lang)
        if hits:
            problems.append(f'cảnh {k} người kể xưng "{hits[0]}"; kể ngôi thứ ba, không xưng tôi')
        has_vi = bool(_VI_MARKS.search(text))
        if lang == "vi" and not has_vi:
            problems.append(f"cảnh {k} không phải tiếng Việt")
        if lang == "en" and has_vi:
            problems.append(f"cảnh {k} còn chữ tiếng Việt; lời kể phải bằng tiếng Anh")
        if not s.image_prompt.strip():
            problems.append(f"cảnh {k} thiếu image_prompt")
        scenes.append({"text": text, "covers": ids, "image_prompt": s.image_prompt.strip(),
                       "narrative_beat": s.narrative_beat if s.narrative_beat in BEATS else "setting",
                       "camera_motion": s.camera_motion if s.camera_motion in CAMERA_MOTIONS else "zoom_in"})
    missing = [p for p in point_ids if p not in covered]
    if missing:
        problems.append(f"chưa kể các ý {', '.join(missing)}; mọi ý phải có trong covers của một cảnh")
    ratio = MIN_WORD_RATIO[(src_lang, lang)]
    total, src = sum(word_count(s["text"]) for s in scenes), source_words(part, src_lang)
    if total < ratio * src:
        problems.append(f"lời kể chỉ {total} từ, cần ít nhất {int(ratio * src)} từ ({int(ratio * 100)}% đoạn gốc "
                        f"{src} từ): kể đủ chi tiết từng ý, không làm tắt")
    if problems:
        raise StepRejected("; ".join(problems[:12]))
    return scenes


# ---------------------------------------------------------------- một phần: viết → kiểm → viết lại

def _verify_validator(point_ids: list[str], texts: list[str]) -> Callable[[Any], dict]:
    def validate(raw: Any) -> dict:
        try:
            return coverage_guard.check_verify(raw, point_ids, texts)
        except coverage_guard.QuoteRejected as exc:
            raise StepRejected(exc.reason) from exc
    return validate


async def review_part(part: str, *, lang: str, src_lang: str, index: int, total: int, facts: list[str],
                      prev_tail: list[str], style_preset: str, llm: Callable[..., Any]) -> tuple[list[dict], list[str], dict]:
    """Một phần truyện: trả (cảnh, sự thật mới, số liệu kiểm). Không đạt sau MAX_ROUNDS vòng thì StoryReviewError."""
    label = f"phần {index}/{total}"
    texts = await ask_validated(points_prompt(part, lang, index, total), lambda raw: check_points(raw, part),
                                llm=llm, temperature=0.2, step_label=f"liệt kê ý {label}")
    points = [(f"p{i}", t) for i, t in enumerate(texts, start=1)]
    ids = [p for p, _ in points]
    feedback = ""
    result: dict = {}
    for round_no in range(1, MAX_ROUNDS + 1):
        scenes = await ask_validated(
            write_prompt(part, points, facts, prev_tail, lang, index, total, style_preset, feedback),
            lambda raw: check_written(raw, ids, part, lang, src_lang),
            llm=llm, temperature=0.5, step_label=f"viết review {label}")
        narr = [s["text"] for s in scenes]
        result = await ask_validated(coverage_guard.verify_prompt(points, narr, facts, part),
                                     _verify_validator(ids, narr), llm=llm, temperature=0.1,
                                     step_label=f"kiểm lời kể {label}")
        if not result["missing"] and not result["issues"]:
            stats = {"part": index, "points": len(ids), "rounds": round_no, "source_words": source_words(part, src_lang),
                     "review_words": sum(word_count(t) for t in narr)}
            return scenes, result["facts"], stats
        feedback = coverage_guard.feedback_for_writer(result, dict(points))
        logger.warning("Review %s vòng %d chưa đạt: %s", label, round_no, feedback[:300])
    raise StoryReviewError(f"Không viết được lời review đủ ý cho {label} sau {MAX_ROUNDS} lần viết lại. Lần cuối còn: "
                           f"{coverage_guard.feedback_for_writer(result, dict(points))[:600]}")


async def review_story(text: str, *, language: Optional[str] = None, style_preset: str = "cinematic_realistic",
                       job_id: Optional[str] = None, llm: Optional[Callable[..., Any]] = None) -> dict:
    """Cả truyện: {"scenes": [...], "language": ..., "coverage": [...]}. Mỗi cảnh đã qua kiểm đủ ý."""
    src_lang = detect_text_language(text)
    lang = language if language in LANGUAGES else (src_lang if src_lang in LANGUAGES else "vi")
    parts = chunk_source(text, PART_MAX_CHARS_ZH if src_lang == "zh" else PART_MAX_CHARS)
    if not parts:
        raise StoryReviewError("Truyện trống")
    llm = llm or _story_llm
    facts: list[str] = []
    scenes: list[dict] = []
    stats: list[dict] = []
    try:
        for index, part in enumerate(parts, start=1):
            if job_id:
                _progress[job_id] = f"Đang viết và kiểm phần {index}/{len(parts)}"
            part_scenes, new_facts, st = await review_part(
                part, lang=lang, src_lang=src_lang, index=index, total=len(parts), facts=facts,
                prev_tail=[s["text"] for s in scenes[-2:]], style_preset=style_preset, llm=llm)
            facts += new_facts
            stats.append(st)
            for s in part_scenes:
                words = word_count(s["text"])
                s["metadata"] = {"narrative_beat": s.pop("narrative_beat"), "covers": s.pop("covers"),
                                 "story_part": index,
                                 "estimated_duration": round(max(2.0, words / WORDS_PER_SECOND[lang]), 1)}
                scenes.append(s)
    except StepFailed as exc:
        raise StoryReviewError(exc.user_message) from exc
    finally:
        if job_id:
            _progress.pop(job_id, None)
    return {"scenes": scenes, "language": lang, "coverage": stats, "verified": True}
