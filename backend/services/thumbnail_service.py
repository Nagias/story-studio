"""
YouTube Thumbnail & SEO Packaging Engine
----------------------------------------
Compliant with OP_CTOOL Specification:
1. Generates 16:9 Full HD (1920x1080) high-CTR click-magnet thumbnails with Pillow:
   - Dynamic cinematic color enhancement & vignette
   - High-impact bold typography with gold/white fill, thick black outlines, and drop shadows
   - Customizable headlines, subtext, and branded badges
2. Generates comprehensive YouTube SEO metadata:
   - 3 CTR-optimized title variations (Click-magnet, Dramatic storyline, Search SEO)
   - SEO Description with automatic Chapter Timestamps, synopsis, credits, and hashtags
   - Targeted search tags list for YouTube metadata
"""

import os
import re
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

from config import PROJECTS_DIR
from services import safe_files

logger = logging.getLogger("story_studio.thumbnail_service")

# Windows font paths
WINDOWS_FONTS = Path(r"C:\Windows\Fonts")
FONT_IMPACT = WINDOWS_FONTS / "impact.ttf"
FONT_ARIAL_BOLD = WINDOWS_FONTS / "arialbd.ttf"
FONT_CALIBRI_BOLD = WINDOWS_FONTS / "calibrib.ttf"

def get_font(font_size: int, bold: bool = True) -> ImageFont.ImageFont:
    """Retrieve best available TrueType font on Windows, with fallback to default."""
    candidates = [FONT_IMPACT, FONT_ARIAL_BOLD, FONT_CALIBRI_BOLD] if bold else [FONT_ARIAL_BOLD]
    for c in candidates:
        if c.exists():
            try:
                return ImageFont.truetype(str(c), font_size)
            except Exception:
                pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None

def format_timestamp_mmss(seconds: float) -> str:
    """Format seconds into MM:SS chapter format."""
    total_secs = int(max(0, round(seconds)))
    mins = total_secs // 60
    secs = total_secs % 60
    return f"{mins:02d}:{secs:02d}"

def extract_headline_hooks(project: Any) -> Tuple[str, str]:
    """Generate punchy 2-line YouTube headline hook from project name and characters."""
    name = (getattr(project, "name", None) or "Huyền Thoại").strip()
    # Clean punctuation and novel chapter artifacts
    clean_name = re.sub(r"^[0-9\.\-\:\s]+", "", name)
    clean_name = clean_name.replace("US Novel:", "").replace("Sử thi:", "").strip()

    if "Spartan" in clean_name or "Sparta" in clean_name:
        return ("300 DŨNG SĨ SPARTA", "TRẬN CHIẾN TẠI CỬA TỬ")
    elif "Murata" in clean_name or "Battle" in clean_name or "Võ" in clean_name:
        return ("VÕ GIẢ CUỒNG NỘ", "ĐẠI CHIẾN NGHẸT THỞ")
    elif "Paladin" in clean_name or "Thánh" in clean_name or "Kai" in clean_name:
        return ("DŨNG SĨ THÁNH GIÁP", "BÍ MẬT BẢO KIẾM")
    elif "Kingdom" in clean_name or "Shin" in clean_name:
        return ("ĐẠI CHIẾN VẠN QUÂN", "TƯỚNG QUÂN XUNG TRẬN")
    elif "Rừng" in clean_name or "Sương" in clean_name:
        return ("RỪNG SƯƠNG MÙ", "BÍ MẬT KINH HOÀNG")
    else:
        words = clean_name.split()
        if len(words) <= 3:
            return (clean_name.upper(), "TẬP 1: BẮT ĐẦU")
        else:
            mid = min(4, len(words) // 2 + 1)
            line1 = " ".join(words[:mid]).upper()
            line2 = " ".join(words[mid:mid+4]).upper()
            return (line1[:28], line2[:28])

def generate_youtube_thumbnail(
    project: Any,
    scene_index: Optional[int] = None,
    custom_headline: Optional[str] = None,
    custom_subtext: Optional[str] = None,
    badge_text: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a 16:9 Full HD (1920x1080) YouTube thumbnail with dramatic visual grading
    and bold, high-CTR typography.
    """
    proj_id = getattr(project, "id", "default_proj")
    scenes = getattr(project, "scenes", []) or []

    # 1. Select source image
    source_img_path = None
    if scene_index is not None and 0 <= scene_index < len(scenes):
        sc = scenes[scene_index]
        source_img_path = getattr(sc, "image_path", None)
    
    if not source_img_path or not os.path.exists(source_img_path):
        # Look for first available scene image
        for sc in scenes:
            ip = getattr(sc, "image_path", None)
            if ip and os.path.exists(ip):
                source_img_path = ip
                break

    canvas_w, canvas_h = 1920, 1080

    if source_img_path and os.path.exists(source_img_path):
        try:
            with Image.open(source_img_path) as raw_img:
                base_img = raw_img.convert("RGB")
                # Scale & center crop to 1920x1080
                from PIL import ImageOps
                base_img = ImageOps.fit(base_img, (canvas_w, canvas_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        except Exception as e:
            logger.warning(f"Error reading source image {source_img_path}: {e}")
            base_img = Image.new("RGB", (canvas_w, canvas_h), color=(18, 12, 28))
    else:
        # Create dramatic gradient canvas if no scene image yet
        base_img = Image.new("RGB", (canvas_w, canvas_h), color=(22, 14, 38))
        draw_g = ImageDraw.Draw(base_img)
        for y in range(canvas_h):
            r = int(22 + 40 * (y / canvas_h))
            g = int(14 + 10 * (y / canvas_h))
            b = int(38 + 60 * (y / canvas_h))
            draw_g.line([(0, y), (canvas_w, y)], fill=(r, g, b))

    # 2. Color Enhancement (Vibrancy & Contrast boost for YouTube feed standout)
    try:
        contrast = ImageEnhance.Contrast(base_img).enhance(1.22)
        color = ImageEnhance.Color(contrast).enhance(1.18)
        base_img = ImageEnhance.Sharpness(color).enhance(1.25)
    except Exception:
        pass

    # 3. Add cinematic dark gradient vignette on left (where headline text sits)
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)

    # Left-to-right dark gradient for text readability
    grad_width = 1150
    for x in range(grad_width):
        alpha = int(230 * (1.0 - (x / grad_width) ** 1.3))
        draw_ov.line([(x, 0), (x, canvas_h)], fill=(0, 0, 0, alpha))

    # Bottom dark bar gradient
    for y in range(canvas_h - 250, canvas_h):
        progress = (y - (canvas_h - 250)) / 250.0
        alpha = int(180 * progress)
        draw_ov.line([(0, y), (canvas_w, y)], fill=(0, 0, 0, alpha))

    base_rgba = base_img.convert("RGBA")
    composite_img = Image.alpha_composite(base_rgba, overlay).convert("RGB")
    draw = ImageDraw.Draw(composite_img)

    # 4. Determine Headlines
    default_h1, default_h2 = extract_headline_hooks(project)
    headline_line1 = (custom_headline or default_h1).strip().upper()
    headline_line2 = (custom_subtext or default_h2).strip().upper()

    font_h1 = get_font(96, bold=True)
    font_h2 = get_font(74, bold=True)
    font_badge = get_font(34, bold=True)

    # Helper function for text with thick outline and drop shadow
    def draw_text_with_outline(d, pos, text, font, fill_color, outline_color, outline_w=6, shadow_offset=(6, 6)):
        x, y = pos
        # Drop shadow
        sx, sy = shadow_offset
        d.text((x + sx, y + sy), text, font=font, fill=(0, 0, 0, 240))
        # 8-direction outline
        for dx in range(-outline_w, outline_w + 1):
            for dy in range(-outline_w, outline_w + 1):
                if dx * dx + dy * dy <= outline_w * outline_w:
                    d.text((x + dx, y + dy), text, font=font, fill=outline_color)
        # Main fill
        d.text((x, y), text, font=font, fill=fill_color)

    # 5. Draw Top Badge (Pill)
    badge_label = (badge_text or "🔥 1080P FULL MOVIE").strip().upper()
    badge_x, badge_y = 70, 70
    badge_pad_x, badge_pad_y = 20, 10
    
    # Calculate badge bounding box
    badge_bbox = draw.textbbox((badge_x, badge_y), badge_label, font=font_badge)
    pill_rect = [
        badge_bbox[0] - badge_pad_x,
        badge_bbox[1] - badge_pad_y,
        badge_bbox[2] + badge_pad_x,
        badge_bbox[3] + badge_pad_y,
    ]
    draw.rounded_rectangle(pill_rect, radius=12, fill=(220, 38, 38), outline=(254, 202, 202), width=2)
    draw.text((badge_x, badge_y), badge_label, font=font_badge, fill=(255, 255, 255))

    # 6. Draw Line 1 (Golden Yellow #FFE600 with Thick Black Outline)
    text_start_y = 660
    draw_text_with_outline(
        draw,
        pos=(70, text_start_y),
        text=headline_line1,
        font=font_h1,
        fill_color=(255, 230, 0),       # Bright YouTube Gold
        outline_color=(0, 0, 0),         # Jet Black
        outline_w=6,
        shadow_offset=(8, 8),
    )

    # 7. Draw Line 2 (Pure White #FFFFFF with Badge Background or Red Outline)
    draw_text_with_outline(
        draw,
        pos=(70, text_start_y + 115),
        text=headline_line2,
        font=font_h2,
        fill_color=(255, 255, 255),     # Crisp White
        outline_color=(15, 15, 20),      # Dark Outline
        outline_w=5,
        shadow_offset=(7, 7),
    )

    # 8. Add sleek 4px border around entire thumbnail
    draw.rectangle([(0, 0), (canvas_w - 1, canvas_h - 1)], outline=(255, 215, 0), width=4)

    # 9. Save thumbnail file
    if output_path:
        out_f = Path(output_path)
    else:
        out_f = PROJECTS_DIR / proj_id / "renders" / "thumbnail.jpg"
    
    out_f.parent.mkdir(parents=True, exist_ok=True)
    # Ghi file tạm rồi đổi tên: request khác (giao diện, bước dựng) không đọc phải ảnh đang ghi dở
    tmp_f = out_f.with_name(f"{out_f.stem}.{uuid.uuid4().hex[:8]}.tmp{out_f.suffix}")
    try:
        composite_img.save(str(tmp_f), "JPEG", quality=95)
        safe_files.retry_if_locked(lambda: os.replace(tmp_f, out_f))
    except BaseException:
        tmp_f.unlink(missing_ok=True)
        raise
    logger.info(f"YouTube 1080p Thumbnail successfully generated: {out_f}")

    thumb_url = f"/api/projects/{proj_id}/thumbnail"
    return {
        "success": True,
        "thumbnail_path": str(out_f),
        "thumbnail_url": thumb_url,
        "headline_line1": headline_line1,
        "headline_line2": headline_line2,
        "badge_text": badge_label,
        "resolution": f"{canvas_w}x{canvas_h}",
    }

def generate_youtube_seo_pack(project: Any) -> Dict[str, Any]:
    """
    Generate viral, CTR-optimized YouTube SEO metadata pack:
    - 3 Click-worthy title variations
    - Description with automatic Chapter Timestamps & Synopsis
    - High-ranking Tags and Hashtags
    """
    proj_id = getattr(project, "id", "default_proj")
    name = (getattr(project, "name", None) or "Huyền Thoại").strip()
    scenes = getattr(project, "scenes", []) or []

    # Clean title
    clean_title = re.sub(r"^[0-9\.\-\:\s]+", "", name)
    clean_title = clean_title.replace("US Novel:", "").replace("Sử thi:", "").strip()

    # 1. Title Variations
    title_v1 = f"🔥 [TẬP 1] {clean_title} - BÍ MẬT KINH HOÀNG KHÔNG THỂ BỎ LỠ | Phim Truyện AI 1080p"
    title_v2 = f"⚔️ {clean_title}: Cuộc Đại Chiến Nghẹt Thở Tại Vùng Cấm | Tóm Tắt Truyện Full HD"
    title_v3 = f"{clean_title} (Tập 1) - Tóm Tắt Truyện Audio & Phim Hoạt Hình 1080p Hay Nhất"

    # 2. Compute Chapter Timestamps
    cumulative_time = 0.0
    chapter_lines = []
    synopsis_sentences = []

    for idx, sc in enumerate(scenes, start=1):
        ts = format_timestamp_mmss(cumulative_time)
        raw_text = (getattr(sc, "text", "") or "").strip()
        # Take first 6 words as chapter subtitle
        snippet = " ".join(raw_text.split()[:6]) if raw_text else f"Phân cảnh {idx}"
        if snippet:
            chapter_lines.append(f"{ts} - Phần {idx}: {snippet}...")
        
        if idx <= 3 and raw_text:
            synopsis_sentences.append(raw_text)

        dur = float(getattr(sc, "duration", 0.0) or 5.0)
        cumulative_time += dur

    # 3. Build Description
    synopsis = " ".join(synopsis_sentences[:2]) if synopsis_sentences else "Theo dõi câu chuyện kịch tính đầy bất ngờ được tái hiện sống động qua hình ảnh điện ảnh 1080p và giọng đọc truyền cảm AI."
    
    chapters_block = "\n".join(chapter_lines) if chapter_lines else "00:00 - Bắt đầu câu chuyện"

    description = f"""🎬 {clean_title} - Tập 1 (Full Movie 1080p)

📖 TÓM TẮT NỘI DUNG:
{synopsis}

⏱️ DANH SÁCH CÁC CHƯƠNG (TIMESTAMPS):
{chapters_block}

✨ CÔNG NGHỆ SẢN XUẤT:
- Kịch bản & Phân cảnh: YouTube AI Storyboard Studio
- Đồ họa: 9-Grid Spec 8K Composite Slicing
- Lồng tiếng: Voice AI Multilingual Master Sound
- Âm thanh: 3-Layer Audio Sidechain Ducking & Dynamic Foley SFX

🔔 Đừng quên bấm LIKE, ĐĂNG KÝ KÊNH và BẬT CHUÔNG THÔNG BÁO để không bỏ lỡ tập tiếp theo nhé!
Cảm ơn các bạn đã theo dõi và ủng hộ kênh!

#StoryStudio #{re.sub(r'[^a-zA-Z0-9]', '', clean_title)} #TomTatTruyen #AnimeAction #KeChuyenAudio #YouTube1080p #AIAnimation
"""

    # 4. Targeted YouTube Tags
    tags = [
        clean_title,
        f"{clean_title} tập 1",
        "tóm tắt truyện",
        "kể chuyện audio",
        "phim truyện ai",
        "light novel",
        "anime action",
        "truyện tranh 1080p",
        "story studio",
        "review phim",
        "audiobook việt nam",
        "ai video generator",
    ]

    hashtags = [
        f"#{re.sub(r'[^a-zA-Z0-9]', '', clean_title)}",
        "#StoryStudio",
        "#TomTatTruyen",
        "#AnimeAction",
        "#KeChuyenAudio",
        "#FullMovie1080p",
    ]

    return {
        "project_id": proj_id,
        "recommended_title": title_v1,
        "title_variations": [title_v1, title_v2, title_v3],
        "description": description.strip(),
        "chapters": chapter_lines,
        "tags": tags,
        "hashtags": hashtags,
    }
