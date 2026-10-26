import base64
import io
import logging
import math
import random
import shutil
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
from PIL import Image, ImageDraw

from config import (
    OPENAI_API_KEY,
    NINEROUTER_BASE_URL,
    NINEROUTER_API_KEY,
    NINEROUTER_IMAGE_MODEL,
    DEFAULT_IMAGE_PROVIDER,
    DEFAULT_STYLE,
)

logger = logging.getLogger("story_studio.image_service")

# Tên provider được chấp nhận cho từng engine (giao diện và dữ liệu cũ dùng nhiều tên khác nhau)
MUSE_PROVIDERS = ("meta_muse_cloud", "meta_muse", "muse", "muse_cloud")
NINEROUTER_PROVIDERS = ("9router_gemini", "gemini", "gemini_image", "9router", "gemini_flash")

# Masterpiece negative prompt eliminating body mutations, deformed limbs, and style bleed
MASTER_NEGATIVE_PROMPT: str = (
    "deformed, bad anatomy, bad hands, missing fingers, extra fingers, mutated hands, "
    "poorly drawn hands, poorly drawn face, mutation, deformed limbs, floating limbs, "
    "disconnected limbs, malformed limbs, out of frame, blurry, bad art, extra head, "
    "fused fingers, too many fingers, long neck, low quality, normal quality, worst quality, "
    "jpeg artifacts, signature, watermark, username, inconsistent clothing, modern artifacts in historical scene"
)

STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    # 0a. HOẠT HÌNH 2D RÙNG RỢN: chủ dự án 26/10/2026 thích kiểu kênh "Thế Giới Kì Quái" hơn ảnh noir; thử thật trên Muse
    # với đúng đoạn mô tả này: ra nhân vật đầu tròn trắng, nền vẽ tay tối màu, giữ được nhân vật khi đính kèm ảnh cảnh trước.
    "horror_cartoon_2d": {
        "id": "horror_cartoon_2d",
        "name": "Hoạt hình 2D rùng rợn (nhân vật đầu tròn, nền vẽ tay tối)",
        "prompt_suffix": (
            "2D Chinese horror web-cartoon style, flat simple character design: characters have big perfectly round "
            "white heads, tiny dot eyes, simple line mouth, thin simple bodies, thick clean outlines; backgrounds are "
            "detailed dark painted illustrations with muted desaturated colors, cold blue-green night lighting, eerie "
            "quiet mood, cinematic 16:9 frame, no text, no watermark"
        ),
        "negative_prompt": "photorealistic, realistic skin, 3d render, anime big eyes, chibi, bright cheerful colors, blood, gore",
        "colors": ["#0f172a", "#334155", "#b91c1c"],
        "description": "Hoạt hình 2D kiểu truyện ma web: nhân vật đầu tròn trắng nét đơn giản, nền vẽ tay chi tiết, tông lạnh u tối.",
    },
    # 0. TRUE CRIME NEO-NOIR SILHOUETTE PRESET
    "neo_noir_silhouette": {
        "id": "neo_noir_silhouette",
        "name": "Neo-Noir Silhouette (Bóng Đen Trinh Thám Điện Ảnh)",
        "prompt_suffix": (
            "cinematic neo-noir visual style, stark chiaroscuro lighting, deep mysterious silhouettes, "
            "wet asphalt rain reflections, cold cyan streetlight cutting through dark heavy shadows, "
            "warm amber spotlight accent, 35mm anamorphic film grain, dramatic detective mystery thriller, 8k masterpiece"
        ),
        "negative_prompt": "bright daylight, cheerful, cartoon, anime, pastel, flat lighting, 3d plastic render, deformed limbs",
        "colors": ["#030712", "#f59e0b", "#dc2626"],
        "description": "Bóng đen trinh thám neo-noir điện ảnh, tương phản chiaroscuro sắc nét, mưa đêm, ánh đèn đường và bóng đổ bí ẩn.",
    },
    # 1. SPECIALIZED STYLES MATCHING REFERENCE SAMPLES (9ROUTER GEMINI OPTIMIZED)
    "manga_murata_battle": {
        "id": "manga_murata_battle",
        "name": "Manga Battle Action (Nét vẽ đại chiến Murata / One Punch Man)",
        "prompt_suffix": (
            "Yusuke Murata and Kengan Ashura master manga illustration style, "
            "meticulous black and white pen and ink crosshatching, fine screentone shading, "
            "dramatic chiaroscuro contrast, expressive character lineart, masterpiece manga double-page spread aesthetic"
        ),
        "negative_prompt": "photorealistic, 3d render, blurry, messy anatomy, pastel, flat lighting, amateur sketch",
        "colors": ["#000000", "#ef4444"],
        "description": "Manga đại chiến đỉnh cao phong cách Yusuke Murata, nét vẽ mực đen đan nét tinh tế, đổ bóng screentone tương phản chiaroscuro chuẩn truyện tranh Nhật Bản.",
    },
    "spartan_epic_mythology": {
        "id": "spartan_epic_mythology",
        "name": "Spartan Epic Mythology (Chiến binh sử thi Hy Lạp sơn dầu)",
        "prompt_suffix": (
            "epic classical dark fantasy oil painting, Frank Frazetta and Zack Snyder aesthetic, "
            "dramatic chiaroscuro lighting, warm golden amber atmospheric haze, cinematic rim lighting, "
            "floating embers, museum masterpiece quality, 8k cinematic art"
        ),
        "negative_prompt": "cartoon, anime, 3d plastic render, modern weaponry, flat lighting, blurry face, missing fingers, extra limbs",
        "colors": ["#78350f", "#f59e0b"],
        "description": "Chiến binh Sparta Hy Lạp dũng mãnh, phong cách sơn dầu cổ điển Zack Snyder / Frazetta, ánh hoàng hôn vàng óng sử thi.",
    },
    "intricate_ink_crosshatch": {
        "id": "intricate_ink_crosshatch",
        "name": "Intricate Ink Crosshatch (Tranh vẽ mực & đan nét Graphic Novel)",
        "prompt_suffix": (
            "masterpiece black and white comic illustration, fine pen and ink drawing, "
            "cross-hatching technique, heavy black ink shadows and delicate linework, "
            "vintage graphic novel aesthetic, comic book hatching, pure black ink on clean parchment white background"
        ),
        "negative_prompt": "color, photorealistic, 3d render, soft watercolor, blurry, messy anatomy, digital gradient",
        "colors": ["#18181b", "#ffffff"],
        "description": "Tranh vẽ mực đen trắng đan nét (cross-hatching) chi tiết cao, nét bút sắt sắc bén, đổ bóng tương phản chuẩn graphic novel phương Tây.",
    },
    "dark_fantasy": {
        "id": "dark_fantasy",
        "name": "Dark Fantasy (Thần thoại u tối Elden Ring)",
        "prompt_suffix": "dark fantasy concept art, Elden Ring and Dark Souls inspired, grim ambiance, moody fog, hyper-detailed armor and ruins, dramatic chiaroscuro shadows, epic scale composition, 8k",
        "negative_prompt": "bright, cheerful, cartoon, oversaturated, lowres, flat lighting",
        "colors": ["#0b0d13", "#991b1b"],
        "description": "Không gian huyền bí, u ám và tráng lệ mang phong cách Dark Souls/Elden Ring.",
    },
    "cinematic_realistic": {
        "id": "cinematic_realistic",
        "name": "Cinematic Realistic (Điện ảnh chân thực)",
        "prompt_suffix": "cinematic movie still, photorealistic 8k, shot on 35mm lens, depth of field, dramatic volumetric lighting, photoreal textures, masterpiece, high quality, 16:9 widescreen composition",
        "negative_prompt": "cartoon, 3d render, anime, blurry, low resolution, bad anatomy, deformed, oversaturated",
        "colors": ["#0f172a", "#d97706"],
        "description": "Phong cách điện ảnh Hollywood, chi tiết chân thực, ánh sáng có chiều sâu.",
    },
    "anime": {
        "id": "anime",
        "name": "Anime & Ghibli (Hoạt hình Nhật Bản)",
        "prompt_suffix": "masterpiece anime artwork, Makoto Shinkai studio ghibli aesthetic, vibrant emotional colors, dramatic sky lighting, crisp clean linework, detailed background, 4k resolution, 16:9",
        "negative_prompt": "ugly, deformed, photorealistic, 3d render, blurry, low quality, grainy",
        "colors": ["#1e293b", "#38bdf8"],
        "description": "Nét vẽ anime lung linh, màu sắc rực rỡ và lãng mạn như phim Shinkai/Ghibli.",
    },
    "cyberpunk": {
        "id": "cyberpunk",
        "name": "Cyberpunk (Tương lai viễn tưởng)",
        "prompt_suffix": "cyberpunk aesthetic, neon glow reflections, rainy futuristic metropolis, holographic displays, synthwave color grading, volumetric smoke, cinematic 8k, octane render",
        "negative_prompt": "vintage, medieval, blurry, washed out, low quality, daytime countryside",
        "colors": ["#18032e", "#06b6d4"],
        "description": "Ánh đèn neon rực rỡ, thành phố tương lai mưa đêm với công nghệ cao.",
    },
    "comic_book": {
        "id": "comic_book",
        "name": "Comic Book (Truyện tranh phương Tây)",
        "prompt_suffix": "American graphic novel comic illustration, dynamic panel composition, bold black ink outlines, halftone dot shading, vibrant pop colors, expressive dramatic angles, Marvel DC style",
        "negative_prompt": "photorealistic, 3d render, blurry, washed out, watercolor, soft edges",
        "colors": ["#1c1917", "#eab308"],
        "description": "Phong cách truyện tranh phương Tây với nét mực sắc nét và gam màu mạnh mẽ.",
    },
    "3d_animation": {
        "id": "3d_animation",
        "name": "3D Animation (Pixar / Disney)",
        "prompt_suffix": "Pixar Disney 3D animation style, adorable expressive character design, soft subsurface scattering, warm cinematic studio lighting, clean stylized render, Octane render 8k",
        "negative_prompt": "creepy, photorealistic human, dark grim, low poly, bad textures",
        "colors": ["#1e1b4b", "#f472b6"],
        "description": "Hoạt hình 3D cao cấp mềm mại, biểu cảm sinh động như phim Pixar/Disney.",
    },
    "fantasy_paladin_armor": {
        "id": "fantasy_paladin_armor",
        "name": "Fantasy Paladin Armor (Dũng sĩ giáp bạc ngọc lam Light Novel)",
        "prompt_suffix": "high fantasy anime key visual, Fate/Grand Order and Granblue Fantasy aesthetic, glorious anime knight in polished silver plate armor with radiant cyan turquoise crystal inlays, flowing rich crimson velvet cape, ornate carved gold-hilted legendary broadsword with glowing runic blade, luminous volumetric light rays, soft anime cel-shading with rich ambient occlusion, glowing magical particles, 8k high-end anime movie wallpaper, cinematic composition",
        "negative_prompt": "photorealistic human, 3d render, gritty live-action, lowres, deformed hands, bad armor geometry, dull colors, western cartoon",
        "colors": ["#06b6d4", "#ef4444"],
        "description": "Dũng sĩ giáp bạc ngọc lam, áo choàng đỏ rực, chuôi kiếm vàng chạm khắc phong cách anime điện ảnh / Light Novel Nhật Bản (Fate/Grand Order, Granblue Fantasy).",
    },
    "manga_historical_war": {
        "id": "manga_historical_war",
        "name": "Manga Historical War (Đại chiến cổ trang Kingdom / Yasuhisa Hara)",
        "prompt_suffix": "epic historical war manga illustration, Yasuhisa Hara Kingdom style, monumental double-page spread composition, vast army of tens of thousands of ancient soldiers marching with upright spears and halberds, billowing fluttering war flags with ancient Chinese calligraphy, mounted battlefield commanders on horseback in the distance, intricate cross-hatching and fine ink hatching details, sweeping panoramic perspective, dust rising from battlefield, gritty monochromatic manga art, cinematic masterpiece",
        "negative_prompt": "full color, modern technology, guns, tanks, cars, cartoon, flat 2d simple sketch, low quality, blurry, deformed soldiers",
        "colors": ["#18181b", "#71717a"],
        "description": "Manga đại chiến lịch sử hai trang đôi (Kingdom của Yasuhisa Hara), hàng vạn binh sĩ giáo mác rợp trời, cờ hiệu chữ Hán tung bay, tướng quân cưỡi ngựa xa xa.",
    },
    # Backwards compatibility aliases
    "manga_battle_action": {
        "id": "manga_battle_action",
        "name": "Manga Battle Action (Nét vẽ đại chiến Murata / One Punch Man)",
        "prompt_suffix": (
            "extreme action shonen battle manga double-page spread, Yusuke Murata and Kengan Ashura dynamic style, "
            "explosive kinetic impact, shattered concrete and pulverized debris flying airborne, intense radial speed lines converging to center shockwave, "
            "bold hand-drawn manga sound effects typography (SFX: KA-BOOM, CRASH, 衝撃, SHOCKWAVE), deep black ink screentone shading, "
            "selective dramatic crimson red energy aura glow on clashing fists and strikes, high contrast ink masterpiece"
        ),
        "negative_prompt": "photorealistic, 3d render, blurry, messy anatomy, pastel, flat lighting, amateur sketch",
        "colors": ["#000000", "#ef4444"],
        "description": "Manga đại chiến võ thuật tương phản cao, vệt tốc độ hội tụ, chữ SFX nổ ầm ầm (Murata / One Punch Man).",
    },
    "roman_legionary_epic": {
        "id": "roman_legionary_epic",
        "name": "Roman Legionary Epic (Quân đoàn La Mã sơn dầu sử thi)",
        "prompt_suffix": (
            "epic historical oil painting of the Roman legion, disciplined Roman legionaries in lorica segmentata iron armor "
            "with curved red scutum shields bearing a golden bull emblem, bronze galea helmets with crimson crests, pilum javelins, "
            "swirling desert sandstorm, dramatic chiaroscuro lighting, rich textured brushstrokes, Jean-Léon Gérôme academic realism, "
            "museum-grade masterpiece, cinematic composition"
        ),
        "negative_prompt": "anime, cartoon, 3d plastic render, modern weapons, fantasy elves, flat lighting, blurry, deformed hands",
        "colors": ["#991b1b", "#d97706"],
        "description": "Quân đoàn La Mã cổ đại nét sơn dầu sử thi: giáp lorica segmentata, khiên đỏ scutum vẽ bò tót vàng, mũ galea bờm đỏ, bão cát sa mạc.",
    },
    "spartan_mythic_warrior": {
        "id": "spartan_mythic_warrior",
        "name": "Spartan Mythic Warrior (Chiến binh Sparta Hy Lạp sử thi)",
        "prompt_suffix": (
            "epic dark fantasy artwork, heroic Spartan warrior with golden Corinthian helmet, "
            "anatomically sculpted bronze muscle cuirass with intricate filigree engravings, towering red horsehair crest, "
            "holding an ornate round hoplon shield with embossed sun emblem and a sharp bronze-tipped spear, "
            "dramatic low angle, intense warrior gaze, glowing golden amber atmospheric lighting, cinematic rim lighting, "
            "floating embers, Frank Frazetta and Troy aesthetic, highly detailed masterpiece, 8k"
        ),
        "negative_prompt": "cartoon, anime, 3d plastic render, modern weaponry, flat lighting, blurry face, missing fingers, extra limbs",
        "colors": ["#78350f", "#b45309"],
        "description": "Chiến binh Sparta Hy Lạp dũng mãnh, giáp đồng cơ bắp, mũ Corinthian bờm lông ngựa, khiên tròn hoplon.",
    },
}

def get_available_styles() -> List[Dict[str, Any]]:
    """Return all available style presets."""
    return list(STYLE_PRESETS.values())

def build_character_anchored_prompt(
    scene_prompt: str,
    style_preset: str = "cinematic_realistic",
    character: Optional[Any] = None,
    character_anchor_override: Optional[str] = None,
) -> str:
    """
    Build a cinematic visual prompt ensuring character consistency without sacrificing shot variety.
    Intelligently respects shot composition (Wide Landscape, Close-up, Action Impact, Antagonist).
    Prevents repetitive full-body center-framed character portraits across video scenes.
    """
    parts = []
    clean_action = scene_prompt.strip()
    if clean_action:
        parts.append(clean_action)

    clean_lower = clean_action.lower()

    # Detect if this scene is a wide landscape, environment scale, or antagonist focus
    is_wide_or_landscape = any(term in clean_lower for term in [
        "wide shot", "panoramic", "landscape", "bird's-eye", "aerial", "establishing",
        "mountain", "plain", "valley", "pass of", "sea haze", "endless army", "city ruins",
        "shattered acropolis", "storm clouds"
    ])
    is_opponent_or_threat = any(term in clean_lower for term in [
        "demon god", "titan", "monstrous", "monster", "beast", "persian immortals",
        "enemy army", "opponent", "faceless mask"
    ])

    # Determine character anchor specification
    anchor_text = None
    if character_anchor_override and character_anchor_override.strip():
        anchor_text = character_anchor_override.strip()
    elif character is not None:
        if isinstance(character, str) and character.strip():
            anchor_text = character.strip()
        elif hasattr(character, "generate_anchor_prompt"):
            anchor_text = character.generate_anchor_prompt()
        elif isinstance(character, dict):
            char_parts = []
            if character.get("name"):
                char_parts.append(f"character {character['name']}")
            for k in ["face_features", "hair_style_and_color"]:
                if character.get(k):
                    char_parts.append(character[k])
            if character.get("armor_or_costume"):
                char_parts.append(f"wearing {character['armor_or_costume']}")
            if character.get("main_weapon"):
                char_parts.append(f"wielding {character['main_weapon']}")
            if character.get("signature_colors"):
                char_parts.append(f"signature colors: {character['signature_colors']}")
            if character.get("distinguishing_marks"):
                char_parts.append(f"distinctive details: {character['distinguishing_marks']}")
            if char_parts:
                anchor_text = ", ".join(char_parts)
            elif character.get("full_anchor_prompt"):
                anchor_text = character["full_anchor_prompt"]

    # Cảnh quái vật/đối thủ: không ép nhân vật chính vào khung hình.
    # Cảnh toàn cảnh: vẫn giữ đặc điểm nhân vật (để không lệch danh tính) nhưng là hình nhỏ trong khung,
    # tránh mọi cảnh đều thành chân dung toàn thân ở giữa khung.
    if anchor_text and not is_opponent_or_threat:
        # Check if clean_action already contains detailed character traits to avoid duplicate spam
        already_has_character_details = any(
            token in clean_lower for token in ["corinthian", "cuirass", "spartan", "hoplite", "dogi", "cape", "paladin"]
        ) and len(clean_action) > 100

        if not already_has_character_details:
            anchor_body = anchor_text[len("featuring character:"):].strip() if anchor_text.lower().startswith("featuring character:") else anchor_text
            if is_wide_or_landscape:
                parts.append(f"featuring character as a small figure within the wide establishing frame: {anchor_body}")
            else:
                parts.append(f"featuring character: {anchor_body}")

    preset = STYLE_PRESETS.get(style_preset) or STYLE_PRESETS.get(DEFAULT_STYLE) or STYLE_PRESETS["cinematic_realistic"]
    preset_suffix = preset.get("prompt_suffix", "")
    if preset_suffix and preset_suffix.lower() not in clean_lower:
        parts.append(preset_suffix)

    return ", ".join(parts)

def build_consistent_prompt(
    scene_prompt: str,
    style_preset: str = "cinematic_realistic",
    character_anchor: str = "",
    character: Optional[Any] = None,
) -> str:
    """
    Build a consistent and cohesive prompt by combining:
    1. Scene action & environment
    2. Character visual anchor sheet
    3. Style preset styling suffix
    """
    target_char = character if character is not None else character_anchor
    return build_character_anchored_prompt(
        scene_prompt=scene_prompt,
        style_preset=style_preset,
        character=target_char,
    )

def generate_mock_cinematic(
    prompt: str,
    style_preset: str,
    output_path: str,
    scene_index: Optional[int] = None,
) -> str:
    """
    Generate an offline, high-polish cinematic image.
    Prioritizes real high-resolution AI illustration templates from the demo_images catalog.
    Falls back to Pillow procedural rendering if no templates are found.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    width, height = 1280, 720
    preset = STYLE_PRESETS.get(style_preset, STYLE_PRESETS["cinematic_realistic"])

    # Base palette
    palette_map = {
        "anime": ((15, 23, 42), (56, 189, 248)),
        "cinematic_realistic": ((15, 23, 42), (217, 119, 6)),
        "dark_fantasy": ((11, 13, 19), (153, 27, 27)),
        "cyberpunk": ((24, 3, 46), (6, 182, 212)),
        "comic_book": ((28, 25, 23), (234, 179, 8)),
        "3d_animation": ((30, 27, 75), (244, 114, 182)),
        "manga_battle_action": ((10, 10, 10), (240, 240, 240)),
        "manga_historical_war": ((24, 24, 27), (161, 161, 170)),
        "fantasy_paladin_armor": ((6, 182, 212), (239, 68, 68)),
        "roman_legionary_epic": ((153, 27, 27), (217, 119, 6)),
        "spartan_mythic_warrior": ((120, 53, 15), (180, 83, 9)),
    }
    c_top, c_bottom = palette_map.get(style_preset, ((15, 23, 42), (99, 102, 241)))

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Vertical gradient
    for y in range(height):
        t = y / float(height)
        r = int(c_top[0] * (1 - t) + c_bottom[0] * t)
        g = int(c_top[1] * (1 - t) + c_bottom[1] * t)
        b = int(c_top[2] * (1 - t) + c_bottom[2] * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Add dynamic speedlines if manga style
    if style_preset in ("manga_battle_action", "manga_historical_war"):
        cx, cy = width // 2, height // 2
        for angle_deg in range(0, 360, 6):
            rad = math.radians(angle_deg)
            r_start = random.randint(120, 220)
            r_end = max(width, height)
            x1 = int(cx + r_start * math.cos(rad))
            y1 = int(cy + r_start * math.sin(rad))
            x2 = int(cx + r_end * math.cos(rad))
            y2 = int(cy + r_end * math.sin(rad))
            draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, 80) if style_preset == "manga_battle_action" else (180, 180, 180, 60), width=random.randint(1, 3))

    # Add atmospheric radial lighting glow in upper center
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    cx, cy = width // 2, int(height * 0.4)
    max_radius = 350
    for r_step in range(max_radius, 0, -25):
        alpha = int(25 * (1 - r_step / max_radius))
        glow_draw.ellipse(
            [(cx - r_step, cy - r_step), (cx + r_step, cy + r_step)],
            fill=(255, 255, 255, alpha),
        )
    img.paste(Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB"), (0, 0))

    # Add subtle silhouettes (landscape/horizon)
    horizon_y = int(height * 0.65)
    horizon_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(horizon_overlay)
    h_draw.polygon(
        [
            (0, height),
            (0, horizon_y + 40),
            (width * 0.25, horizon_y - 20),
            (width * 0.5, horizon_y + 30),
            (width * 0.75, horizon_y - 40),
            (width, horizon_y + 20),
            (width, height),
        ],
        fill=(10, 10, 15, 140),
    )
    img.paste(Image.alpha_composite(img.convert("RGBA"), horizon_overlay).convert("RGB"), (0, 0))

    # Cinema framing & information badge
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)

    # Subtle cinematic border
    ov_draw.rectangle([(25, 25), (width - 25, height - 25)], outline=(255, 255, 255, 40), width=2)

    # Badge in bottom-left
    box_w = min(width - 100, 1000)
    ov_draw.rounded_rectangle([(40, height - 130), (40 + box_w, height - 35)], radius=12, fill=(10, 15, 25, 210), outline=(255, 255, 255, 50), width=1)

    # Scene tag
    scene_label = f"SCENE {scene_index}" if scene_index is not None else "STORYBOARD STILL"
    style_label = preset["name"]
    ov_draw.text((60, height - 118), f"▶ {scene_label} | {style_label}", fill=(245, 158, 11))

    # Short prompt display
    display_prompt = prompt[:110] + ("..." if len(prompt) > 110 else "")
    ov_draw.text((60, height - 88), f"Prompt: {display_prompt}", fill=(240, 240, 240))
    ov_draw.text((60, height - 62), "Offline High-Resolution Visual Generator", fill=(156, 163, 175))

    final_img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    final_img.save(output_path, "JPEG", quality=95)
    return output_path

def clean_watermark(image_path: str):
    """Cleanly trim bottom-right watermark from generated images."""
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            if w > 100 and h > 100:
                crop_bottom = int(h * 0.068)
                cropped = img.crop((0, 0, w, h - crop_bottom))
                resized = cropped.resize((w, h), Image.Resampling.LANCZOS)
                fmt = "PNG" if image_path.lower().endswith(".png") else "JPEG"
                if fmt == "JPEG":
                    resized = resized.convert("RGB")
                resized.save(image_path, fmt, quality=95)
    except Exception as e:
        print(f"Warning cleaning watermark: {e}")

async def generate_pollinations(
    prompt: str,
    output_path: str,
    seed: Optional[int] = None,
) -> str:
    """Download image from pollinations.ai and strip watermark."""
    if seed is None:
        seed = random.randint(1000, 9999999)

    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed}"

    headers = {
        "User-Agent": "StoryStudio/1.0 (Mozilla/5.0)",
        "Accept": "image/jpeg,image/png,image/*",
    }

    async with httpx.AsyncClient(timeout=40.0) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Pollinations returned status {resp.status_code}")
        with open(output_path, "wb") as f:
            f.write(resp.content)

    clean_watermark(output_path)
    return output_path

async def generate_9router_gemini(
    prompt: str,
    output_path: str,
    model: Optional[str] = None,
) -> str:
    """
    Generate high-resolution image using 9router AI Gateway (ag/gemini-3.1-flash-image).
    Supports base64 JSON payload and remote image URL.
    """
    target_model = model or NINEROUTER_IMAGE_MODEL or "ag/gemini-3.1-flash-image"
    headers = {
        "Authorization": f"Bearer {NINEROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    # Gateway không có tham số tỉ lệ khung đã biết: nhắc tỉ lệ trong prompt, rồi cắt về 16:9 sau khi nhận ảnh
    payload = {
        "prompt": f"{prompt}, wide 16:9 landscape composition",
        "model": target_model,
    }

    url = f"{NINEROUTER_BASE_URL.rstrip('/')}/images/generations"
    async with httpx.AsyncClient(timeout=75.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"9router Image API failed with HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()

    image_data = data.get("data", [])
    if not image_data:
        raise RuntimeError("9router Image API returned empty data list.")

    first_item = image_data[0]
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if "b64_json" in first_item:
        img_bytes = base64.b64decode(first_item["b64_json"])
    elif first_item.get("url"):
        async with httpx.AsyncClient(timeout=40.0) as client:
            r = await client.get(first_item["url"])
        if r.status_code != 200:
            raise RuntimeError(f"Không tải được ảnh 9router (HTTP {r.status_code})")
        img_bytes = r.content
    else:
        raise RuntimeError("9router Image API returned unrecognized data item format.")

    try:
        with Image.open(io.BytesIO(img_bytes)) as pil_img:
            pil_img = crop_to_aspect(pil_img.convert("RGB"), 16 / 9)
            pil_img.save(str(out), "JPEG", quality=95)
    except Exception as e:
        raise RuntimeError(f"9router trả về dữ liệu không phải ảnh hợp lệ: {e}") from e

    return str(out)


def crop_to_aspect(img: Image.Image, target_ratio: float, tolerance: float = 0.02) -> Image.Image:
    """Cắt giữa ảnh về đúng tỉ lệ khung (vd 16:9) nếu lệch quá tolerance."""
    w, h = img.size
    if not w or not h or abs(w / h - target_ratio) / target_ratio <= tolerance:
        return img
    if w / h > target_ratio:
        new_w = int(round(h * target_ratio))
        left = (w - new_w) // 2
        return img.crop((left, 0, left + new_w, h))
    new_h = int(round(w / target_ratio))
    top = (h - new_h) // 2
    return img.crop((0, top, w, top + new_h))

async def generate_openai_dalle(prompt: str, output_path: str) -> str:
    """Generate image via OpenAI DALL-E 3 if API key is present."""
    api_key = OPENAI_API_KEY or None
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)

    response = await client.images.generate(
        model="dall-e-3",
        prompt=prompt[:950],
        size="1792x1024",
        quality="standard",
        n=1,
    )
    image_url = response.data[0].url

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        r = await http_client.get(image_url)
        with open(output_path, "wb") as f:
            f.write(r.content)

    return output_path

async def generate_image(
    prompt: str,
    style_preset: str = "manga_murata_battle",
    character_anchor: str = "",
    character: Optional[Any] = None,
    provider: Optional[str] = None,
    seed: Optional[int] = None,
    output_path: Optional[str] = None,
    scene_index: Optional[int] = None,
    reference_image: Optional[str] = None,
    reference_role: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate an image using the selected provider with consistent styling.

    Chuỗi dự phòng tự động chỉ có Muse → 9router. Khi tất cả đều lỗi hàm trả về
    success=False kèm error, không bao giờ thay bằng ảnh giả. Pollinations, DALL-E
    và mock_cinematic chỉ chạy khi được chọn đích danh làm provider.
    """
    if not output_path:
        raise ValueError("output_path must be provided.")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    target_char = character if character is not None else character_anchor

    full_prompt = build_character_anchored_prompt(
        scene_prompt=prompt,
        style_preset=style_preset,
        character=target_char,
    )

    requested_provider = provider or DEFAULT_IMAGE_PROVIDER or "meta_muse_cloud"
    used_provider = requested_provider
    error_msg = None
    attempts: List[str] = []

    # Resolve reference image from direct param or character object
    ref_img = reference_image
    if not ref_img and character:
        if hasattr(character, "character_reference_image") and character.character_reference_image:
            ref_img = character.character_reference_image
        elif hasattr(character, "avatar_url") and character.avatar_url:
            ref_img = character.avatar_url
        elif isinstance(character, dict):
            ref_img = character.get("character_reference_image") or character.get("avatar_url") or character.get("reference_image")

    char_anchor_str = ""
    if character_anchor:
        char_anchor_str = character_anchor
    elif hasattr(target_char, "generate_anchor_prompt"):
        char_anchor_str = target_char.generate_anchor_prompt()
    elif isinstance(target_char, str):
        char_anchor_str = target_char
    elif isinstance(target_char, dict) and target_char.get("full_anchor_prompt"):
        char_anchor_str = target_char["full_anchor_prompt"]

    def _ok(provider_name: str) -> Dict[str, Any]:
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"{provider_name} báo xong nhưng không có file ảnh tại {out}")
        res = {
            "image_path": str(out),
            "full_prompt": full_prompt,
            "provider": provider_name,
            "requested_provider": requested_provider,
            "fallback_reason": error_msg,
            "success": True,
        }
        if provider_name == "meta_muse_cloud":
            res["reference_image"] = ref_img
        return res

    # 0. Meta Muse Fleet Runner / Cloud Worker (2K Masterpiece via Chromium Multi-Profile Fleet)
    if used_provider in MUSE_PROVIDERS:
        try:
            from routers.muse_bridge import enqueue_and_wait_muse_task, is_kind_online
            if not is_kind_online("image"):
                raise RuntimeError("Không có tài khoản Muse ảnh nào online (Fleet Runner)")

            task_dict = {
                "mode": "text-to-image",
                "prompt": full_prompt,
                "negative_prompt": MASTER_NEGATIVE_PROMPT,
                "output_path": str(out),
                "scene_index": scene_index,
                "reference_image": ref_img,
                "reference_image_url": str(ref_img) if ref_img and (str(ref_img).startswith("http") or str(ref_img).startswith("/")) else None,
                "reference_image_path": str(ref_img) if ref_img and not str(ref_img).startswith("http") else None,
                "character_anchor": char_anchor_str,
                "aspect_ratio": "16:9",
                "parameters": {
                    "aspect_ratio": "16:9",
                    "resolution": "2K",
                    "style_preset": style_preset,
                    "seed": seed,
                    "reference_image": ref_img,
                    "character_anchor": char_anchor_str,
                    # "previous_scene": ảnh đính kèm là cảnh ngay trước (vẽ nối tiếp), không phải ảnh nhân vật mẫu
                    "reference_role": reference_role,
                    "visual_details": prompt,
                    "lighting": "cinematic lighting, volumetric atmosphere, 8k resolution",
                },
            }
            res = await enqueue_and_wait_muse_task(task_dict)
            muse_file = Path(res.get("output_path") or out) if isinstance(res, dict) else out
            if muse_file.resolve() != out.resolve() and muse_file.exists():
                shutil.copy2(muse_file, out)
            return _ok("meta_muse_cloud")
        except Exception as e:
            attempts.append(f"Muse: {e}")
            error_msg = f"Meta Muse lỗi ({e}), đã chuyển sang 9router."
            used_provider = "9router_gemini"

    # 1. 9router Gemini (dự phòng duy nhất trong chuỗi tự động)
    if used_provider in NINEROUTER_PROVIDERS:
        try:
            await generate_9router_gemini(full_prompt, str(out))
            return _ok("9router_gemini")
        except Exception as e:
            attempts.append(f"9router: {e}")
            return _failed(requested_provider, full_prompt, attempts)

    # Các provider dưới đây chỉ chạy khi được chọn đích danh, lỗi thì báo lỗi luôn
    if used_provider == "api":
        try:
            await generate_openai_dalle(full_prompt, str(out))
            return _ok("api")
        except Exception as e:
            attempts.append(f"DALL-E: {e}")
            return _failed(requested_provider, full_prompt, attempts)

    if used_provider == "pollinations":
        try:
            await generate_pollinations(full_prompt, str(out), seed=seed)
            return _ok("pollinations")
        except Exception as e:
            attempts.append(f"Pollinations: {e}")
            return _failed(requested_provider, full_prompt, attempts)

    if used_provider == "mock_cinematic":
        # Ảnh minh hoạ offline: chỉ dùng khi chọn đích danh, đánh dấu rõ là ảnh tạm
        generate_mock_cinematic(
            prompt=prompt,
            style_preset=style_preset,
            output_path=str(out),
            scene_index=scene_index,
        )
        res = _ok("mock_cinematic")
        res["is_placeholder"] = True
        return res

    attempts.append(f"Provider ảnh không hỗ trợ: '{requested_provider}'")
    return _failed(requested_provider, full_prompt, attempts)


def _failed(requested_provider: str, full_prompt: str, attempts: List[str]) -> Dict[str, Any]:
    """Kết quả khi không tạo được ảnh: không có file mới, caller phải báo lỗi cho người dùng."""
    error = " | ".join(attempts) or "Không rõ lỗi"
    logger.warning(f"Image generation failed (provider={requested_provider}): {error}")
    return {
        "image_path": None,
        "full_prompt": full_prompt,
        "provider": None,
        "requested_provider": requested_provider,
        "success": False,
        "error": error,
    }
