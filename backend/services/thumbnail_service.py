"""
Thumbnail YouTube 16:9 (1920x1080) bằng Pillow: ảnh cảnh + chỉnh màu + nền tối bên trái + chữ to viền đen.

- Font: font Windows có đủ chữ có dấu tiếng Việt (đo 22/10/2026: Segoe UI Black, Arial Bold đủ 109/109 chữ có dấu;
  Impact và Arial Black thiếu 80, vẽ ra ô vuông). Thư mục font lấy từ config.WINDOWS_FONTS_DIR (biến WINDIR).
- Chữ nào font không vẽ được thì báo lỗi ThumbnailError, không vẽ ra ô vuông. Chữ dài tự thu nhỏ hoặc xuống dòng.
- Chữ mặc định: dòng chữ thumbnail của gói SEO (nếu đã tạo), không thì tên dự án. Không tự thêm nhãn quảng cáo.
- File ra phải đạt luật thumbnail của YouTube (services/youtube_seo_rules.check_thumbnail: 16:9, JPG, tối đa 2 MB).
"""

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

import config
from config import PROJECTS_DIR
from services import safe_files
from services import youtube_seo_rules as rules

logger = logging.getLogger("story_studio.thumbnail_service")

THUMB_FONT_FILES = ("seguibl.ttf", "arialbd.ttf", "segoeuib.ttf")   # ưu tiên trước; đều đủ chữ có dấu tiếng Việt
CANVAS_W, CANVAS_H = 1920, 1080
TEXT_LEFT = 70
TEXT_MAX_W = 1100
LINE_SIZES = ((112, 60), (84, 48))   # (cỡ chữ lớn nhất, nhỏ nhất) cho dòng 1 và dòng 2
BADGE_SIZE = 36
JPEG_QUALITIES = (92, 85, 75, 65)


class ThumbnailError(RuntimeError):
    """Không làm được thumbnail đạt luật; thông điệp là lời thường cho người dùng."""


def thumbnail_font_path() -> Optional[Path]:
    fonts = config.WINDOWS_FONTS_DIR
    if fonts is None:
        return None
    for name in THUMB_FONT_FILES:
        if (fonts / name).exists():
            return fonts / name
    return None


def _font(size: int) -> ImageFont.FreeTypeFont:
    path = thumbnail_font_path()
    if path is None:
        raise ThumbnailError("Không tìm thấy font có đủ chữ tiếng Việt (" + ", ".join(THUMB_FONT_FILES)
                             + ") trong thư mục font của Windows.")
    return ImageFont.truetype(str(path), size)


def default_lines(project: Any) -> List[str]:
    seo = getattr(project, "youtube_seo", None)
    pack = getattr(seo, "pack", None) if seo else None
    if pack and pack.thumbnail_lines:
        return list(pack.thumbnail_lines)
    return [(getattr(project, "name", None) or "").strip() or "Story Studio"]


def _fit_lines(draw: ImageDraw.ImageDraw, text: str, max_size: int, min_size: int) -> List[tuple]:
    """Thu nhỏ chữ cho vừa TEXT_MAX_W; nhỏ nhất vẫn không vừa thì xuống dòng theo từ. Trả [(dòng, font)]."""
    for size in range(max_size, min_size - 1, -4):
        font = _font(size)
        if draw.textlength(text, font=font) <= TEXT_MAX_W:
            return [(text, font)]
    font = _font(min_size)
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font) > TEXT_MAX_W:
            lines.append(current)
            current = word
        else:
            current = trial
    lines.append(current)
    return [(line, font) for line in lines]


def _draw_outlined(draw: ImageDraw.ImageDraw, pos, text, font, fill, outline, width: int, shadow: int) -> None:
    x, y = pos
    draw.text((x + shadow, y + shadow), text, font=font, fill=(0, 0, 0))
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx * dx + dy * dy <= width * width:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def _source_image(scenes: list, scene_index: Optional[int]) -> Image.Image:
    candidates = []
    if scene_index is not None and 0 <= scene_index < len(scenes):
        candidates.append(getattr(scenes[scene_index], "image_path", None))
    candidates += [getattr(sc, "image_path", None) for sc in scenes]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                with Image.open(path) as raw:
                    return ImageOps.fit(raw.convert("RGB"), (CANVAS_W, CANVAS_H), method=Image.Resampling.LANCZOS)
            except OSError as e:
                logger.warning(f"Không đọc được ảnh cảnh {path}: {e}")
    base = Image.new("RGB", (CANVAS_W, CANVAS_H))
    draw = ImageDraw.Draw(base)
    for y in range(CANVAS_H):
        draw.line([(0, y), (CANVAS_W, y)], fill=(int(22 + 40 * y / CANVAS_H), int(14 + 10 * y / CANVAS_H),
                                                  int(38 + 60 * y / CANVAS_H)))
    return base


def generate_youtube_thumbnail(
    project: Any,
    scene_index: Optional[int] = None,
    custom_headline: Optional[str] = None,
    custom_subtext: Optional[str] = None,
    badge_text: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Vẽ thumbnail 1920x1080 và lưu vào renders/thumbnail.jpg (ghi tạm rồi đổi tên)."""
    proj_id = getattr(project, "id", "default_proj")
    scenes = getattr(project, "scenes", []) or []

    if custom_headline or custom_subtext:
        texts = [t.strip() for t in (custom_headline, custom_subtext) if t and t.strip()]
    else:
        texts = default_lines(project)
    texts = [t.upper() for t in texts[:2]]
    badge = (badge_text or "").strip().upper()

    font_path = thumbnail_font_path()
    if font_path is None:
        raise ThumbnailError("Không tìm thấy font có đủ chữ tiếng Việt (" + ", ".join(THUMB_FONT_FILES)
                             + ") trong thư mục font của Windows.")
    missing = rules.missing_glyphs(font_path, "".join(texts) + badge)
    if missing:
        raise ThumbnailError(f"Font thumbnail không vẽ được các ký tự: {missing} (bỏ emoji hay ký hiệu lạ rồi thử lại).")

    img = _source_image(scenes, scene_index)
    img = ImageEnhance.Sharpness(ImageEnhance.Color(ImageEnhance.Contrast(img).enhance(1.18)).enhance(1.12)).enhance(1.2)
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    for x in range(1250):   # nền tối bên trái để chữ dễ đọc
        draw_ov.line([(x, 0), (x, CANVAS_H)], fill=(0, 0, 0, int(225 * (1.0 - (x / 1250) ** 1.3))))
    for y in range(CANVAS_H - 300, CANVAS_H):
        draw_ov.line([(0, y), (CANVAS_W, y)], fill=(0, 0, 0, int(170 * (y - (CANVAS_H - 300)) / 300)))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    if badge:
        font_badge = _font(BADGE_SIZE)
        box = draw.textbbox((TEXT_LEFT, 70), badge, font=font_badge)
        draw.rounded_rectangle([box[0] - 20, box[1] - 10, box[2] + 20, box[3] + 10], radius=12, fill=(220, 38, 38))
        draw.text((TEXT_LEFT, 70), badge, font=font_badge, fill=(255, 255, 255))

    styled = []   # (dòng, font, màu chữ)
    for i, text in enumerate(texts):
        max_size, min_size = LINE_SIZES[min(i, 1)]
        color = (255, 230, 0) if i == 0 else (255, 255, 255)
        styled += [(line, font, color) for line, font in _fit_lines(draw, text, max_size, min_size)]
    heights = [draw.textbbox((0, 0), line, font=font)[3] + 18 for line, font, _ in styled]
    y = max(150, CANVAS_H - 90 - sum(heights))
    for (line, font, color), h in zip(styled, heights):
        _draw_outlined(draw, (TEXT_LEFT, y), line, font, color, (0, 0, 0), width=6, shadow=7)
        y += h

    out_f = Path(output_path) if output_path else PROJECTS_DIR / proj_id / "renders" / "thumbnail.jpg"
    out_f.parent.mkdir(parents=True, exist_ok=True)
    tmp_f = out_f.with_name(f"{out_f.stem}.{uuid.uuid4().hex[:8]}.tmp{out_f.suffix}")
    try:
        for quality in JPEG_QUALITIES:   # giữ dưới 2 MB (giới hạn của YouTube)
            img.save(str(tmp_f), "JPEG", quality=quality)
            if tmp_f.stat().st_size <= rules.THUMB_MAX_BYTES:
                break
        problems = rules.failures(rules.check_thumbnail(tmp_f))
        if problems:
            raise ThumbnailError("Thumbnail chưa đạt luật YouTube: " + " ".join(problems))
        safe_files.retry_if_locked(lambda: os.replace(tmp_f, out_f))
    except BaseException:
        tmp_f.unlink(missing_ok=True)
        raise
    logger.info(f"Thumbnail 1920x1080: {out_f}")

    return {
        "success": True,
        "thumbnail_path": str(out_f),
        "thumbnail_url": f"/api/projects/{proj_id}/thumbnail",
        "lines": [line for line, _, _ in styled],
        "headline_line1": texts[0] if texts else "",
        "headline_line2": texts[1] if len(texts) > 1 else "",
        "badge_text": badge,
        "resolution": f"{CANVAS_W}x{CANVAS_H}",
    }
