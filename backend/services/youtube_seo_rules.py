"""Luật SEO YouTube mà máy kiểm được: khoá cứng của gói SEO (không đạt thì không lưu, không cho tải về).

Luật chính thức của YouTube (đọc ngày 22/10/2026):
- Tiêu đề tối đa 100 ký tự, mô tả tối đa 5.000 byte, cả hai không chứa < hoặc >. Tags: tổng tối đa 500 ký tự; dấu phẩy
  giữa các tag tính vào; tag có khoảng trắng tính thêm 2 ký tự cho cặp ngoặc kép.
  https://developers.google.com/youtube/v3/docs/videos
- Hashtag không có khoảng trắng; video có hơn 60 hashtag thì YouTube bỏ hết. https://support.google.com/youtube/answer/6390658
- Chương: mốc đầu là 00:00, ít nhất 3 chương, tăng dần, mỗi chương dài ít nhất 10 giây.
  https://support.google.com/youtube/answer/9884579
- Thumbnail: 16:9, rộng ít nhất 640 px, JPG/PNG, tối đa 2 MB. https://support.google.com/youtube/answer/72431
- Tiêu đề: nên đặt từ quan trọng lên đầu, hạn chế viết HOA toàn bộ và emoji. https://support.google.com/youtube/answer/12340300

Luật riêng của app (để gói SEO bám từ khoá thật, không do AI tự nghĩ): tiêu đề chứa ít nhất một từ khoá đã chọn;
150 ký tự đầu của mô tả chứa từ khoá chính; tiêu đề không có emoji, không viết HOA quá nửa số chữ; tối đa 15 hashtag.
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional, Sequence

from PIL import Image, ImageDraw, ImageFont

TITLE_MAX_CHARS = 100
DESCRIPTION_MAX_BYTES = 5000
TAGS_MAX_CHARS = 500
HASHTAGS_MAX = 15
HASHTAGS_IGNORED_ABOVE = 60
CHAPTERS_MIN = 3
CHAPTER_MIN_SECONDS = 10
THUMB_MAX_BYTES = 2 * 1024 * 1024
THUMB_MIN_WIDTH = 640
THUMB_FORMATS = {"JPEG", "PNG"}
DESCRIPTION_KEYWORD_WINDOW = 150
CAPS_MIN_LETTERS = 12   # tiêu đề ngắn hơn thì không xét viết HOA
CAPS_MAX_RATIO = 0.5

_ANGLE = re.compile(r"[<>]")
# Emoji và ký hiệu hình (khối Unicode của emoji, ký hiệu, dingbat, cờ); không đụng chữ Việt
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF⬀-⯿️]")
_TIMESTAMP_LINE = re.compile(r"^\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\b")
_HASHTAG = re.compile(r"#[^\s#]+")


@dataclass(frozen=True)
class Check:
    rule: str      # mã ngắn, vd "title.length"
    ok: bool
    message: str   # tiếng Việt, hiện thẳng cho người dùng


def all_ok(checks: Iterable[Check]) -> bool:
    return all(c.ok for c in checks)


def failures(checks: Iterable[Check]) -> list[str]:
    return [c.message for c in checks if not c.ok]


def _contains(text: str, keyword: str) -> bool:
    return bool(keyword.strip()) and keyword.strip().casefold() in text.casefold()


# ----------------------------------------------------------------------------- tiêu đề, mô tả, tags, hashtag
def check_title(title: str, keywords: Sequence[str]) -> list[Check]:
    title = title or ""
    letters = [ch for ch in title if ch.isalpha()]
    upper = sum(ch.isupper() for ch in letters)
    too_caps = len(letters) >= CAPS_MIN_LETTERS and upper / len(letters) > CAPS_MAX_RATIO
    return [
        Check("title.length", 0 < len(title.strip()) and len(title) <= TITLE_MAX_CHARS,
              f"Tiêu đề phải có từ 1 đến {TITLE_MAX_CHARS} ký tự (đang {len(title)})."),
        Check("title.angle", not _ANGLE.search(title), "Tiêu đề không được chứa dấu < hoặc > (YouTube không nhận)."),
        Check("title.keyword", any(_contains(title, k) for k in keywords),
              "Tiêu đề phải chứa ít nhất một từ khoá đã chọn: " + ", ".join(keywords[:5])),
        Check("title.emoji", not _EMOJI.search(title), "Tiêu đề không dùng emoji (YouTube khuyên hạn chế)."),
        Check("title.caps", not too_caps, "Tiêu đề viết HOA quá nửa số chữ (YouTube khuyên hạn chế viết HOA)."),
    ]


def check_description(description: str, main_keyword: str) -> list[Check]:
    description = description or ""
    size = len(description.encode("utf-8"))
    return [
        Check("description.bytes", 0 < size <= DESCRIPTION_MAX_BYTES,
              f"Mô tả phải dài từ 1 đến {DESCRIPTION_MAX_BYTES} byte (đang {size}; một chữ có dấu chiếm 2–3 byte)."),
        Check("description.angle", not _ANGLE.search(description), "Mô tả không được chứa dấu < hoặc > (YouTube không nhận)."),
        Check("description.keyword", _contains(description[:DESCRIPTION_KEYWORD_WINDOW], main_keyword),
              f"{DESCRIPTION_KEYWORD_WINDOW} ký tự đầu của mô tả phải chứa từ khoá chính \"{main_keyword}\" "
              "(phần hiện trước nút Xem thêm)."),
    ]


def tags_length(tags: Sequence[str]) -> int:
    """Cách YouTube đếm: cộng độ dài các tag, cộng dấu phẩy ở giữa, tag có khoảng trắng tính thêm 2 (ngoặc kép)."""
    clean = [t.strip() for t in tags if t.strip()]
    return sum(len(t) + (2 if " " in t else 0) for t in clean) + max(0, len(clean) - 1)


def check_tags(tags: Sequence[str]) -> list[Check]:
    total = tags_length(tags)
    return [
        Check("tags.length", total <= TAGS_MAX_CHARS, f"Tags dài {total} ký tự theo cách YouTube đếm, tối đa {TAGS_MAX_CHARS}."),
        Check("tags.angle", not any(_ANGLE.search(t) for t in tags), "Tags không được chứa dấu < hoặc >."),
        Check("tags.comma", not any("," in t for t in tags), "Mỗi tag không được chứa dấu phẩy (dấu phẩy dùng để ngăn tag)."),
    ]


def check_hashtags(hashtags: Sequence[str], description: str = "", title: str = "") -> list[Check]:
    bad = [h for h in hashtags if not re.fullmatch(r"#[^\s#<>,]+", h or "")]
    used = len(_HASHTAG.findall(f"{title}\n{description}"))
    return [
        Check("hashtags.format", not bad, "Hashtag phải bắt đầu bằng # và không có khoảng trắng: " + ", ".join(bad[:5])),
        Check("hashtags.count", len(hashtags) <= HASHTAGS_MAX and used <= HASHTAGS_MAX,
              f"Tối đa {HASHTAGS_MAX} hashtag (YouTube bỏ hết nếu quá {HASHTAGS_IGNORED_ABOVE}); đang có {max(len(hashtags), used)}."),
    ]


# ----------------------------------------------------------------------------- chương
def format_timestamp(seconds: float, long_video: bool) -> str:
    """Mốc chương: M:SS/MM:SS, video từ 1 giờ trở lên thì H:MM:SS."""
    total = int(seconds)
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if long_video else f"{m:02d}:{s:02d}"


def parse_timestamp(text: str) -> int:
    parts = [int(p) for p in text.split(":")]
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def chapter_starts_in(description: str) -> list[int]:
    """Các mốc thời gian ở đầu dòng trong mô tả (YouTube đọc chương từ đây)."""
    return [parse_timestamp(m.group(1)) for line in (description or "").splitlines() if (m := _TIMESTAMP_LINE.match(line))]


def check_chapters(starts: Sequence[float], video_seconds: Optional[float]) -> list[Check]:
    """Không có mốc nào thì hợp lệ (video không có chương). Có mốc thì phải đúng luật chương của YouTube."""
    if not starts:
        return [Check("chapters.none", True, "Không có chương.")]
    gaps_ok = all(b - a >= CHAPTER_MIN_SECONDS for a, b in zip(starts, starts[1:]))
    last_ok = video_seconds is None or video_seconds - starts[-1] >= CHAPTER_MIN_SECONDS
    return [
        Check("chapters.first", starts[0] == 0, "Mốc chương đầu tiên phải là 00:00."),
        Check("chapters.count", len(starts) >= CHAPTERS_MIN, f"Cần ít nhất {CHAPTERS_MIN} chương (đang {len(starts)})."),
        Check("chapters.order", list(starts) == sorted(set(starts)), "Các mốc chương phải tăng dần, không trùng."),
        Check("chapters.length", gaps_ok and last_ok, f"Mỗi chương phải dài ít nhất {CHAPTER_MIN_SECONDS} giây."),
    ]


# ----------------------------------------------------------------------------- thumbnail, font
def _glyph(font: ImageFont.FreeTypeFont, ch: str) -> bytes:
    canvas = Image.new("L", (160, 160))
    ImageDraw.Draw(canvas).text((20, 10), ch, font=font, fill=255)
    return canvas.tobytes()


@lru_cache(maxsize=8)
def _notdef(font_path: str) -> tuple[ImageFont.FreeTypeFont, bytes]:
    font = ImageFont.truetype(font_path, 64)
    return font, _glyph(font, "￿")   # ký tự không tồn tại: font vẽ ô "thiếu chữ"


def missing_glyphs(font_path: Path, text: str) -> str:
    """Các ký tự trong `text` mà font không vẽ được (ra ô vuông)."""
    font, notdef = _notdef(str(font_path))
    seen, missing = set(), []
    for ch in text:
        if ch.isspace() or ch in seen:
            continue
        seen.add(ch)
        if _glyph(font, ch) == notdef:
            missing.append(ch)
    return "".join(missing)


def check_thumbnail(path: Path) -> list[Check]:
    path = Path(path)
    if not path.exists():
        return [Check("thumbnail.exists", False, "Chưa có file thumbnail.")]
    size = path.stat().st_size
    with Image.open(path) as im:
        fmt, (w, h) = im.format, im.size
    return [
        Check("thumbnail.format", fmt in THUMB_FORMATS, f"Thumbnail phải là JPG hoặc PNG (đang {fmt})."),
        Check("thumbnail.ratio", w * 9 == h * 16, f"Thumbnail phải đúng tỉ lệ 16:9 (đang {w}x{h})."),
        Check("thumbnail.width", w >= THUMB_MIN_WIDTH, f"Thumbnail phải rộng ít nhất {THUMB_MIN_WIDTH} px (đang {w})."),
        Check("thumbnail.size", size <= THUMB_MAX_BYTES, f"Thumbnail tối đa 2 MB (đang {size / 1024 / 1024:.2f} MB)."),
    ]


# ----------------------------------------------------------------------------- cả gói
def check_pack(*, title: str, description: str, tags: Sequence[str], hashtags: Sequence[str], keywords: Sequence[str],
               video_seconds: Optional[float]) -> list[Check]:
    main = keywords[0] if keywords else ""
    return [
        Check("keywords.present", bool(main.strip()), "Chưa chọn từ khoá nào."),
        *check_title(title, keywords),
        *check_description(description, main),
        *check_tags(tags),
        *check_hashtags(hashtags, description, title),
        *check_chapters(chapter_starts_in(description), video_seconds),
    ]
