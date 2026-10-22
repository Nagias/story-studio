"""Gói SEO YouTube của một dự án: nơi DUY NHẤT ghi `Project.youtube_seo` (qua project_service.save_project).

Luồng:
1. `save_research`: lưu từ khoá tìm được (services/youtube_keywords.py) vào dự án.
2. `generate_pack`: chương chia theo thời gian của video đã dựng (renders/story_final.mp4); AI chỉ viết câu (tiêu đề,
   đoạn mở đầu mô tả, nhãn chương, chữ thumbnail) trong khuôn từ khoá đã chọn; tags và hashtag lấy thẳng từ từ khoá;
   cả gói phải qua mọi luật ở services/youtube_seo_rules.py mới được lưu.
3. `update_pack`: người dùng sửa tay; kiểm lại đủ luật, không đạt thì không lưu.
4. `download_text`: file .txt để dán vào YouTube Studio (chỉ từ gói đã lưu, tức là đã đạt luật).

AI gọi qua `ask_validated` của luồng vụ án (một đường gọi 9router duy nhất, có thử lại và chờ khi 9router bận).
"""
import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from models.schemas import Project
from models.youtube_seo import Chapter, KeywordResearch, SeoPack, YoutubeSeoState
from services import project_service
from services import youtube_seo_rules as rules
from services.case_adaptation_llm import LLMCall, call_llm_json
from services.case_adaptation_steps import SoftRejected, StepRejected, ask_validated
from services.thumbnail_service import thumbnail_font_path
from services.tts_service import get_audio_duration
from services.youtube_keywords import is_expired

logger = logging.getLogger(__name__)

CHAPTER_TARGET_S = 150           # khoảng 2,5 phút một chương
CHAPTERS_MAX = 30
TITLE_TARGET_CHARS = 90          # xin AI viết ngắn hơn giới hạn 100 để còn chỗ sửa tay
INTRO_MIN_CHARS, INTRO_MAX_CHARS = 60, 700
LABEL_MAX_CHARS = 70
THUMB_LINE_MAX_CHARS = 24
STORY_EXCERPT_CHARS = 2500
CHAPTER_EXCERPT_CHARS = 300
HASHTAG_COUNT = 3
TITLE_OPTIONS = 3

_VI_LETTERS = re.compile("[ăâđêôơưĂÂĐÊÔƠƯàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
                         "ÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ]")
_TIMESTAMP_ANYWHERE = re.compile(r"\b\d{1,2}:\d{2}\b")

SEO_SYSTEM_PROMPT = """\
Bạn là biên tập viên YouTube cho kênh kể chuyện ở Việt Nam và Mỹ. Bạn chỉ viết câu chữ trong khuôn được giao:
- dùng nguyên văn các từ khoá được cung cấp (lấy từ dữ liệu tìm kiếm thật), không tự thêm từ khoá mới;
- giới thiệu đúng nội dung video, không giật tít sai sự thật, không hứa điều video không có, không ghi số tập khi không có;
- không dùng emoji, không viết HOA cả câu, không dùng dấu < hoặc >.
Chỉ trả về đúng một JSON object theo mẫu, không kèm chữ nào khác."""

DISCLOSURE = {
    "vi": "Câu chuyện dựa trên một vụ án có thật; tên người và địa danh đã được thay đổi.",
    "en": "Based on a true case; the names of people and places have been changed.",
}
CHAPTERS_HEADER = {"vi": "Mục lục", "en": "Chapters"}
LANGUAGE_NAME = {"vi": "Tiếng Việt", "en": "English"}


class SeoPackError(Exception):
    """Không làm được gói SEO; `user_message` là lời thường hiện cho người dùng."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class SeoPackRejected(SeoPackError):
    """Gói không đạt luật; `checks` là kết quả từng luật để giao diện hiện."""

    def __init__(self, checks: list):
        super().__init__("Gói SEO chưa đạt luật YouTube: " + " ".join(rules.failures(checks)))
        self.checks = checks


@dataclass
class ChapterDraft:
    start_s: int
    excerpt: str


# ----------------------------------------------------------------------------- dữ liệu dự án
def project_language(project: Project) -> str:
    lang = (project.metadata or {}).get("language")
    if lang in ("vi", "en"):
        return lang
    return "en" if (project.voice or "").lower().startswith("en-") else "vi"


def is_true_crime(project: Project) -> bool:
    return bool((project.metadata or {}).get("case_id"))


def load_project(project_id: str) -> Project:
    project = project_service.get_project(project_id)
    if project is None:
        raise SeoPackError("Không tìm thấy dự án.")
    return project


def current_state(project: Project) -> YoutubeSeoState:
    """Trạng thái gói SEO; dữ liệu từ khoá quá 30 ngày thì bỏ (chính sách nhà phát triển của YouTube)."""
    state = project.youtube_seo or YoutubeSeoState()
    if is_expired(state.research):
        state = YoutubeSeoState(research=None, pack=state.pack)
    return state


def _write_state(project_id: str, update) -> YoutubeSeoState:
    """Đọc bản mới nhất trên đĩa, chỉ đổi youtube_seo, ghi lại (đọc-sửa-ghi ngắn, tránh đè chỉnh sửa khác)."""
    project = load_project(project_id)
    state = update(current_state(project))
    project.youtube_seo = state
    project_service.save_project(project)
    return state


def save_research(project_id: str, research: KeywordResearch) -> YoutubeSeoState:
    return _write_state(project_id, lambda s: YoutubeSeoState(research=research, pack=s.pack))


def final_video_seconds(project_id: str) -> float:
    video = project_service.get_render_media_paths(project_id)["final_video"]
    if not video.exists():
        raise SeoPackError("Chưa có video dựng xong (renders/story_final.mp4). Dựng video ở Bước 3 trước, vì mốc chương "
                           "phải khớp thời gian của video thật.")
    return get_audio_duration(str(video))


# ----------------------------------------------------------------------------- chương
def plan_chapters(project: Project, video_seconds: float) -> list[ChapterDraft]:
    """Chia chương tại ranh giới cảnh, mỗi chương khoảng CHAPTER_TARGET_S giây, ưu tiên chỗ đổi nhịp truyện.

    Thời điểm bắt đầu cảnh = cộng dồn thời lượng cảnh, nhân theo tỉ lệ để tổng khớp đúng độ dài video đã dựng
    (chuyển cảnh, khoảng nghỉ làm video lệch chút so với tổng thời lượng giọng)."""
    scenes = list(project.scenes)
    if not scenes:
        raise SeoPackError("Dự án chưa có cảnh nào.")
    no_duration = [i + 1 for i, s in enumerate(scenes) if not s.duration or s.duration <= 0]
    if no_duration:
        raise SeoPackError(f"Cảnh {', '.join(map(str, no_duration[:10]))} chưa có thời lượng (chưa thu giọng). "
                           "Thu giọng và dựng lại video trước.")
    if video_seconds < rules.CHAPTERS_MIN * rules.CHAPTER_MIN_SECONDS:
        return []
    durations = [float(s.duration or 0) for s in scenes]
    total = sum(durations)
    scale = video_seconds / total
    starts, acc = [], 0.0
    for d in durations:
        starts.append(acc * scale)
        acc += d
    beats = [(s.metadata or {}).get("narrative_beat") for s in scenes]

    n = max(rules.CHAPTERS_MIN, min(CHAPTERS_MAX, round(video_seconds / CHAPTER_TARGET_S)))
    span = video_seconds / n
    min_gap = max(rules.CHAPTER_MIN_SECONDS, span / 2)
    bounds = [0]
    for k in range(1, n):
        ideal = k * span
        options = [i for i in range(1, len(scenes)) if abs(starts[i] - ideal) <= span / 4
                   and starts[i] - starts[bounds[-1]] >= min_gap and video_seconds - starts[i] >= min_gap]
        if not options:
            continue
        beat_changes = [i for i in options if beats[i] and beats[i] != beats[i - 1]]
        bounds.append(min(beat_changes or options, key=lambda i: abs(starts[i] - ideal)))
    if len(bounds) < rules.CHAPTERS_MIN:
        return []

    drafts = []
    for b, nxt in zip(bounds, bounds[1:] + [len(scenes)]):
        text = " ".join((s.text or "").strip() for s in scenes[b:nxt])
        drafts.append(ChapterDraft(start_s=0 if b == 0 else int(starts[b]), excerpt=text[:CHAPTER_EXCERPT_CHARS]))
    return drafts


# ----------------------------------------------------------------------------- AI viết câu trong khuôn
def _seo_llm(llm: LLMCall) -> LLMCall:
    """ask_validated gửi system prompt của luồng vụ án; gói SEO thay bằng system prompt riêng."""
    async def call(_system: str, user: str, **kwargs: Any) -> Any:
        return await llm(SEO_SYSTEM_PROMPT, user, **kwargs)
    return call


def build_prompt(project: Project, keywords: Sequence[str], chapters: Sequence[ChapterDraft], language: str,
                 video_seconds: float) -> str:
    story = " ".join((s.text or "").strip() for s in project.scenes)[:STORY_EXCERPT_CHARS]
    kind = ("truyện kể dựa trên một vụ án có thật, đã đổi tên người và địa danh" if is_true_crime(project)
            else "truyện kể (review, kể lại light novel)")
    long_video = video_seconds >= 3600
    chapter_lines = "\n".join(f"{i}. [{rules.format_timestamp(c.start_s, long_video)}] {c.excerpt}"
                              for i, c in enumerate(chapters, 1)) or "(video không chia chương)"
    keyword_lines = "\n".join(f"{i}. {k}" for i, k in enumerate(keywords, 1))
    return f"""TASK: viết gói SEO YouTube
Ngôn ngữ đầu ra: {LANGUAGE_NAME[language]} (mọi chữ trong JSON viết bằng ngôn ngữ này)
Tên dự án: {project.name}
Loại nội dung: {kind}
Độ dài video: {round(video_seconds / 60)} phút

Từ khoá đã chọn (từ dữ liệu tìm kiếm thật trên YouTube; từ khoá chính đứng đầu):
{keyword_lines}

Nội dung video (trích phần đầu):
{story}

Các chương (đánh số, kèm đoạn trích):
{chapter_lines}

Yêu cầu:
- "titles": {TITLE_OPTIONS} tiêu đề khác nhau, mỗi tiêu đề tối đa {TITLE_TARGET_CHARS} ký tự, chứa NGUYÊN VĂN ít nhất một từ khoá
  trong danh sách (ưu tiên từ khoá chính, đặt gần đầu tiêu đề).
- "description_intro": 2–3 câu (tối đa 500 ký tự) giới thiệu đúng nội dung video; câu đầu chứa NGUYÊN VĂN từ khoá chính
  "{keywords[0]}".
- "chapter_labels": đúng {len(chapters)} nhãn ngắn (mỗi nhãn tối đa 60 ký tự), theo thứ tự chương, nói chương đó kể gì;
  không ghi mốc thời gian.
- "thumbnail_lines": 1–2 dòng chữ ngắn cho ảnh bìa, mỗi dòng tối đa {THUMB_LINE_MAX_CHARS} ký tự, gợi tò mò nhưng đúng nội dung.

Mẫu JSON:
{{"titles": ["..."], "description_intro": "...", "chapter_labels": ["..."], "thumbnail_lines": ["..."]}}"""


def _language_problem(texts: Sequence[str], language: str) -> Optional[str]:
    joined = " ".join(texts)
    if language == "en" and _VI_LETTERS.search(joined):
        return "bản tiếng Anh nhưng có chữ tiếng Việt"
    if language == "vi" and not _VI_LETTERS.search(joined):
        return "bản tiếng Việt nhưng không có chữ có dấu (viết không dấu hoặc sai ngôn ngữ)"
    return None


def validate_llm_output(raw: Any, *, keywords: Sequence[str], language: str, chapter_count: int,
                        font_path: Optional[Path]) -> dict:
    """Kiểm kết quả AI theo luật; StepRejected thì ask_validated gửi lý do để AI viết lại."""
    if not isinstance(raw, dict):
        raise StepRejected("Kết quả không phải JSON object.")
    titles = [str(t).strip() for t in raw.get("titles") or [] if str(t).strip()]
    intro = str(raw.get("description_intro") or "").strip()
    labels = [str(x).strip() for x in raw.get("chapter_labels") or []]
    lines = [str(x).strip() for x in raw.get("thumbnail_lines") or [] if str(x).strip()]
    problems: list[str] = []

    good_titles, title_reasons = [], []
    for t in titles:
        failed = rules.failures(rules.check_title(t, keywords))
        lang = _language_problem([t], language) if language == "en" else None
        if failed or lang:
            title_reasons.append(f"\"{t[:50]}\": " + " ".join(failed + ([lang] if lang else [])))
        else:
            good_titles.append(t)
    if not good_titles:
        problems.append("Không tiêu đề nào đạt: " + "; ".join(title_reasons[:3] or ["không có tiêu đề"]))

    intro_fail = rules.failures(rules.check_description(intro, keywords[0]))
    if not INTRO_MIN_CHARS <= len(intro) <= INTRO_MAX_CHARS:
        intro_fail.append(f"đoạn mở đầu phải dài {INTRO_MIN_CHARS}–{INTRO_MAX_CHARS} ký tự (đang {len(intro)})")
    if intro_fail:
        problems.append("description_intro: " + " ".join(intro_fail))

    if len(labels) != chapter_count:
        problems.append(f"chapter_labels phải có đúng {chapter_count} nhãn (đang {len(labels)})")
    else:
        bad = [x for x in labels if not 2 <= len(x) <= LABEL_MAX_CHARS or "<" in x or ">" in x
               or _TIMESTAMP_ANYWHERE.search(x)]
        if bad:
            problems.append(f"nhãn chương phải dài 2–{LABEL_MAX_CHARS} ký tự, không có mốc giờ, không có < >: "
                            + "; ".join(bad[:3]))

    if not 1 <= len(lines) <= 2 or any(len(x) > THUMB_LINE_MAX_CHARS for x in lines):
        problems.append(f"thumbnail_lines phải có 1–2 dòng, mỗi dòng tối đa {THUMB_LINE_MAX_CHARS} ký tự")
    elif font_path and (missing := rules.missing_glyphs(font_path, "".join(lines))):
        problems.append(f"thumbnail_lines có ký tự font không vẽ được: {missing}")

    lang = _language_problem([intro, *labels], language)
    if lang:
        problems.append(lang)
    if problems:
        raise StepRejected("; ".join(problems))

    value = {"titles": good_titles[:TITLE_OPTIONS], "description_intro": intro, "chapter_labels": labels,
             "thumbnail_lines": lines}
    if len(good_titles) < min(TITLE_OPTIONS, len(titles) or TITLE_OPTIONS):
        raise SoftRejected("Có tiêu đề chưa đạt: " + "; ".join(title_reasons[:3]), value)
    return value


# ----------------------------------------------------------------------------- ghép gói
def hashtag(keyword: str) -> str:
    words = re.findall(r"\w+", keyword)
    return "#" + "".join(w[:1].upper() + w[1:] for w in words)


def fit_tags(keywords: Sequence[str]) -> list[str]:
    tags: list[str] = []
    for kw in keywords:
        clean = kw.replace(",", " ").strip()
        if clean and rules.tags_length(tags + [clean]) <= rules.TAGS_MAX_CHARS:
            tags.append(clean)
    return tags


def assemble_description(intro: str, chapters: Sequence[Chapter], language: str, true_crime: bool,
                         hashtags: Sequence[str], video_seconds: float) -> str:
    parts = [intro]
    if chapters:
        long_video = video_seconds >= 3600
        parts.append(f"{CHAPTERS_HEADER[language]}:\n" + "\n".join(
            f"{rules.format_timestamp(c.start_s, long_video)} {c.label}" for c in chapters))
    if true_crime:
        parts.append(DISCLOSURE[language])
    if hashtags:
        parts.append(" ".join(hashtags))
    return "\n\n".join(parts)


def clean_keywords(keywords: Sequence[str]) -> list[str]:
    seen, out = set(), []
    for kw in keywords:
        kw = " ".join(str(kw).split())
        if kw and kw.casefold() not in seen:
            seen.add(kw.casefold())
            out.append(kw)
    if not out:
        raise SeoPackError("Chọn ít nhất một từ khoá (từ khoá đầu tiên là từ khoá chính).")
    return out


async def generate_pack(project_id: str, keywords: Sequence[str], *, llm: Optional[LLMCall] = None) -> SeoPack:
    """Tạo gói và lưu vào dự án. `llm` mặc định là call_llm_json (lấy lúc gọi để test thay bằng LLM giả)."""
    keywords = clean_keywords(keywords)
    project = await asyncio.to_thread(load_project, project_id)
    video_seconds = await asyncio.to_thread(final_video_seconds, project_id)
    language = project_language(project)
    drafts = plan_chapters(project, video_seconds)
    font = thumbnail_font_path()

    result = await ask_validated(
        build_prompt(project, keywords, drafts, language, video_seconds),
        lambda raw: validate_llm_output(raw, keywords=keywords, language=language, chapter_count=len(drafts),
                                        font_path=font),
        llm=_seo_llm(llm or call_llm_json), temperature=0.5, step_label="viết gói SEO YouTube",
    )
    chapters = [Chapter(start_s=d.start_s, label=label) for d, label in zip(drafts, result["chapter_labels"])]
    hashtags = [hashtag(k) for k in keywords[:HASHTAG_COUNT] if hashtag(k) != "#"]
    description = assemble_description(result["description_intro"], chapters, language, is_true_crime(project),
                                       hashtags, video_seconds)
    pack = SeoPack(language=language, keywords=keywords, title=result["titles"][0], title_options=result["titles"],
                   description=description, tags=fit_tags(keywords), hashtags=hashtags, chapters=chapters,
                   thumbnail_lines=result["thumbnail_lines"], video_seconds=video_seconds,
                   generated_at=datetime.now(timezone.utc))
    checks = pack_checks(pack)
    if not rules.all_ok(checks):
        raise SeoPackRejected(checks)
    await asyncio.to_thread(_write_state, project_id, lambda s: YoutubeSeoState(research=s.research, pack=pack))
    return pack


def pack_checks(pack: SeoPack) -> list:
    return rules.check_pack(title=pack.title, description=pack.description, tags=pack.tags, hashtags=pack.hashtags,
                            keywords=pack.keywords, video_seconds=pack.video_seconds)


def update_pack(project_id: str, *, title: str, description: str, tags: Sequence[str],
                hashtags: Sequence[str]) -> SeoPack:
    """Lưu bản người dùng sửa tay; phải đạt đủ luật như bản AI viết."""
    def update(state: YoutubeSeoState) -> YoutubeSeoState:
        if state.pack is None:
            raise SeoPackError("Chưa có gói SEO để sửa. Bấm Tạo gói SEO trước.")
        edited = state.pack.model_copy(update={
            "title": title.strip(), "description": description.strip(),
            "tags": [t.strip() for t in tags if t.strip()], "hashtags": [h.strip() for h in hashtags if h.strip()],
            "edited_at": datetime.now(timezone.utc)})
        checks = pack_checks(edited)
        if not rules.all_ok(checks):
            raise SeoPackRejected(checks)
        return YoutubeSeoState(research=state.research, pack=edited)

    pack = _write_state(project_id, update).pack
    assert pack is not None
    return pack


def download_text(project: Project) -> str:
    """Nội dung file .txt để dán vào YouTube Studio. Chỉ làm từ gói đã lưu (đã đạt luật)."""
    pack = current_state(project).pack
    if pack is None:
        raise SeoPackError("Chưa có gói SEO. Bấm Tạo gói SEO trước.")
    checks = pack_checks(pack)
    if not rules.all_ok(checks):   # phòng file dự án bị sửa tay ngoài app
        raise SeoPackRejected(checks)
    notes = ["- Thumbnail: tải ở nút Tải ảnh Thumbnail (Bước 4)."]
    if is_true_crime(project):
        notes.append("- Nội dung dựa trên vụ án có thật, hình do AI tạo: trong YouTube Studio, mục \"Nội dung bị thay đổi "
                     "hoặc nội dung tổng hợp\", chọn Có (luật YouTube về nội dung AI trông như thật).")
    return "\n".join([
        "TIÊU ĐỀ", pack.title, "",
        "MÔ TẢ (đã gồm mục lục chương và hashtag)", pack.description, "",
        "TAGS (dán vào ô Thẻ của YouTube Studio)", ", ".join(pack.tags), "",
        "TỪ KHOÁ ĐÃ DÙNG (từ khoá chính đứng đầu)", ", ".join(pack.keywords), "",
        "NHẮC VIỆC", *notes, "",
    ])
