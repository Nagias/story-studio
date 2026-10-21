"""
Vox Narrative Engine & Semantic Story Analyzer
----------------------------------------------
Advanced semantic analysis and scene splitting for YouTube Vox-style documentary videos and novel chapters.
Features:
- Vox 5-Stage Narrative Arc (Hook 0-30s -> Setting -> Conflict Escalation -> Climax -> Resolution)
- Multi-tier Pacing Engine: Fast/Vox (3-4s), Balanced (5-6s), Deep Story (7-8s)
- Multi-dimensional Semantic Extraction: Setting, Subject & Emotion, Core Action, Lighting & Atmosphere, Cinematic Framing
- Two-tier Cinematic Prompt Generator:
    * Layer 1: Cloud LLM via Gemini 2.0 / OpenRouter API
    * Layer 2: Advanced In-Process Semantic Pattern & Cinematic Rule Parser (Offline / Zero-latency fallback)
- Long text and full chapter chunking engine
"""

import re
import json
import math
import logging
import functools
from typing import List, Dict, Any, Optional, Tuple, Callable, Awaitable

import httpx

from config import (
    GEMINI_API_KEY,
    NINEROUTER_API_KEY,
    NINEROUTER_BASE_URL,
    NINEROUTER_SCENE_MODEL,
    OPENROUTER_API_KEY,
)

logger = logging.getLogger("story_studio.script_splitter")

# ==============================================================================
# 1. PACING CONFIGURATIONS (YOUTUBE RETENTION OPTIMIZED)
# ==============================================================================

PACING_CONFIGS: Dict[str, Dict[str, Any]] = {
    "fast": {
        "label": "Fast / Vox Pacing",
        "description": "3-4 seconds per scene. Dynamic visual rhythm, rapid cuts, high YouTube audience retention.",
        "target_duration": 3.5,
        "min_words": 8,
        "max_words": 14,
        "words_per_second": 3.2,
    },
    "vox": {  # Alias for fast
        "label": "Vox Documentary Pacing",
        "description": "3-4 seconds per scene. Kinetic visual cuts, high engagement.",
        "target_duration": 3.5,
        "min_words": 8,
        "max_words": 14,
        "words_per_second": 3.2,
    },
    "balanced": {
        "label": "Balanced Pacing",
        "description": "5-6 seconds per scene. Standard narrative flow, balanced visual breathing room.",
        "target_duration": 5.5,
        "min_words": 15,
        "max_words": 22,
        "words_per_second": 3.2,
    },
    "deep_story": {
        "label": "Deep Story / Cinematic Pacing",
        "description": "7-8 seconds per scene. Immersive storytelling, dramatic pauses, atmospheric wide shots.",
        "target_duration": 7.5,
        "min_words": 23,
        "max_words": 32,
        "words_per_second": 3.2,
    },
}

# ==============================================================================
# 2. ADVANCED SEMANTIC LEXICAL TAXONOMY (OFFLINE LAYER 2 ENGINE)
# ==============================================================================

# Setting / Environment Patterns (Vietnamese -> Cinematic English)
SETTING_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(lâu đài|cung điện|hoàng cung|ngai vàng|thành trì)\b", re.I),
     "an imposing grand stone castle with towering gothic spires, ornate medieval throne room"),
    (re.compile(r"\b(rừng|rừng già|rừng rậm|cây cối|bụi cây|cánh rừng)\b", re.I),
     "ancient primordial forest, towering moss-covered trees, mystical floating dust particles"),
    (re.compile(r"\b(núi|núi tuyết|vách đá|đỉnh núi|hẻm núi|đèo)\b", re.I),
     "monumental snow-capped mountain peaks piercing through dramatic low-hanging clouds"),
    (re.compile(r"\b(biển|đại dương|sóng biển|bờ biển|hải đảo|bãi biển)\b", re.I),
     "vast turbulent ocean with powerful azure waves crashing against rugged black cliffs"),
    (re.compile(r"\b(ngôi làng|làng quê|đồng quê|xóm nhỏ|thôn dã)\b", re.I),
     "peaceful idyllic rustic village, thatched roof cottages, cobblestone pathways, morning mist"),
    (re.compile(r"\b(thành phố|đô thị|phố xá|tòa nhà|cao ốc|đường phố)\b", re.I),
     "sprawling modern metropolis, towering glass skyscrapers, bustling urban streets, neon reflections"),
    (re.compile(r"\b(cyberpunk|tương lai|khoa học viễn tưởng|robot|phi thuyền)\b", re.I),
     "cyberpunk megacity district, holographic advertisements, sleek chrome architecture, rainy streets"),
    (re.compile(r"\b(sa mạc|cát|cồn cát|hoang mạc|cằn cỗi)\b", re.I),
     "vast sun-scorched desert expanse, sweeping golden sand dunes, shimmering heat haze"),
    (re.compile(r"\b(hầm ngục|nhà lao|hang động|dưới lòng đất|mê cung)\b", re.I),
     "dark damp subterranean dungeon cavern, rugged stalactites, glowing moss, ancient stone ruins"),
    (re.compile(r"\b(phòng thí nghiệm|nghiên cứu|bệnh viện|phòng mổ)\b", re.I),
     "high-tech sterile laboratory, glowing holographic displays, intricate scientific apparatus"),
    (re.compile(r"\b(thư viện|sách|văn tự|tài liệu|học viện)\b", re.I),
     "grand ancient archival library, towering mahogany bookshelves filled with timeless tomes"),
    (re.compile(r"\b(chiến trường|khói lửa|bom đạn|đổ nát|hoang tàn)\b", re.I),
     "desolate war-torn battleground, smoking ruins, burning embers, apocalyptic battlefield haze"),
    (re.compile(r"\b(quán rượu|quán bar|quán ăn|tiệm cà phê|phòng khách)\b", re.I),
     "cozy dimly lit tavern interior, rustic wooden tables, warm amber incandescent lights"),
    (re.compile(r"\b(chợ|chợ đêm|phố chợ|gian hàng|buôn bán)\b", re.I),
     "vibrant bustling traditional marketplace, colorful cloth awnings, lantern glow, rich atmosphere"),
    (re.compile(r"\b(không gian|vũ trụ|thiên hà|sao trời|hành tinh)\b", re.I),
     "infinite deep cosmic space, swirling colorful nebulas, glowing distant celestial galaxies"),
    (re.compile(r"\b(sông|con suối|dòng suối|thác nước|bến thuyền)\b", re.I),
     "crystal-clear mountain river winding through lush emerald valleys, cascading waterfalls"),
]

# Subject & Emotion Patterns (Vietnamese -> Cinematic English)
SUBJECT_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(rồng|hỏa long|thần long|linh thú)\b", re.I),
     "a colossal mythical dragon with iridescent scales and fiery glowing breath"),
    (re.compile(r"\b(chiến binh|dũng sĩ|hiệp sĩ|tướng quân|binh lính)\b", re.I),
     "a battle-hardened warrior in detailed weathered steel plate armor, steadfast heroic posture"),
    (re.compile(r"\b(cậu bé|chú bé|thiếu niên|đứa trẻ)\b", re.I),
     "a spirited adventurous young boy with bright curious eyes and determined expression"),
    (re.compile(r"\b(cô bé|thiếu nữ|cô gái|nàng)\b", re.I),
     "an expressive young woman with an emotionally nuanced, resolute gaze"),
    (re.compile(r"\b(phù thủy|pháp sư|thầy phù thủy|thuật sĩ)\b", re.I),
     "a mysterious arcane sorcerer clad in embroidered robes, summoning glowing ethereal runes"),
    (re.compile(r"\b(ông lão|cụ già|bậc trưởng lão|nhà thông thái)\b", re.I),
     "a wise venerable sage with weathered facial features, long silver beard, and thoughtful eyes"),
    (re.compile(r"\b(hoàng tử|vua|hoàng đế|chúa tể)\b", re.I),
     "a dignified royal ruler wearing a golden crown and crimson velvet cloak"),
    (re.compile(r"\b(công chúa|nữ hoàng|hoàng hậu)\b", re.I),
     "a regal elegant queen adorned with intricate royal jewels and majestic silk gown"),
    (re.compile(r"\b(thám tử|điều tra viên|người theo dõi)\b", re.I),
     "an observant trench-coat detective analyzing subtle clues with sharp focused eyes"),
    (re.compile(r"\b(nhà khoa học|giáo sư|kỹ sư|học giả)\b", re.I),
     "an obsessive visionary scientist intensely adjusting precision optical instruments"),
    (re.compile(r"\b(quái vật|ác quỷ|sinh vật lạ|kẻ thù|bóng ma)\b", re.I),
     "a menacing shadowy creature with glowing crimson eyes emerging from darkness"),
    (re.compile(r"\b(đám đông|người dân|dân chúng|quần chúng)\b", re.I),
     "an agitated crowd of diverse citizens reacting with passionate expressive gestures"),
    (re.compile(r"\b(ngựa|bạch mã|chiến mã)\b", re.I),
     "a majestic galloping steed with flowing mane and muscular poise"),
    (re.compile(r"\b(con mèo|chú mèo|mèo)\b", re.I),
     "an alert sleek cat with luminous emerald eyes"),
    (re.compile(r"\b(chó|chú chó|chó săn)\b", re.I),
     "a loyal fierce companion hound standing faithfully at guard"),
]

# Emotion modifiers (Vietnamese -> Emotional description)
EMOTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(sợ hãi|hoảng loạn|kinh hoàng|kinh sợ|run rẩy)\b", re.I),
     "expression of intense dread and wide dilated eyes, palpable fear"),
    (re.compile(r"\b(giận dữ|phẫn nộ|điên tiết|gầm lên|căm phẫn)\b", re.I),
     "intense burning fury, clenched jaw, fiercely furrowed brows"),
    (re.compile(r"\b(buồn|đau khổ|nước mắt|khóc|tuyệt vọng|cô đơn)\b", re.I),
     "deep sorrowful gaze, melancholic expression, heavy emotional gravity"),
    (re.compile(r"\b(vui vẻ|hạnh phúc|cười|mỉm cười|hân hoan|sung sướng)\b", re.I),
     "radiant uplifting smile, warm glowing happiness, hopeful aura"),
    (re.compile(r"\b(ngạc nhiên|kinh ngạc|sửng sốt|bàng hoàng|không tin vào mắt)\b", re.I),
     "breathless astonishment, wide eyes full of wonder and disbelief"),
    (re.compile(r"\b(quyết tâm|kiên định|mạnh mẽ|không bỏ cuộc|dũng cảm)\b", re.I),
     "unshakeable grit and ironclad determination, fierce confident focus"),
    (re.compile(r"\b(bí ẩn|nghi ngờ|do dự|suy tư|trầm ngâm|suy nghĩ)\b", re.I),
     "enigmatic calculating expression, deep contemplative focus"),
]

# Action Patterns (Vietnamese -> Action description)
ACTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(chạy|truy đuổi|chạy trốn|đuổi theo|vội vã)\b", re.I),
     "sprinting urgently at high velocity, motion blur, kinetic energy"),
    (re.compile(r"\b(chiến đấu|tấn công|đánh nhau|vung kiếm|bắn|chém)\b", re.I),
     "engaging in dynamic high-stakes combat, striking with precision power"),
    (re.compile(r"\b(nhìn|quan sát|dõi theo|nhìn chằm chằm|ngắm nhìn)\b", re.I),
     "intently gazing toward the horizon, sharp analytical focal point"),
    (re.compile(r"\b(tìm kiếm|khám phá|mở ra|phát hiện|bước vào)\b", re.I),
     "carefully uncovering a long-hidden secret, exploring uncharted territory"),
    (re.compile(r"\b(nói|hét lên|thì thầm|tuyên bố|ra lệnh)\b", re.I),
     "passionately delivering an urgent proclamation, heightened dramatic dialogue"),
    (re.compile(r"\b(chạm|cầm|nắm lấy|ôm|đỡ|nâng)\b", re.I),
     "hands delicately grasping an enigmatic artifact, tangible tactile tension"),
    (re.compile(r"\b(bay|lơ lửng|nhảy|lao xuống|rơi)\b", re.I),
     "soaring weightlessly through dynamic 3D space, breathtaking kinetic descent"),
    (re.compile(r"\b(ngủ|ngất|nằm|ngã gục|kiệt sức)\b", re.I),
     "lying exhausted on the ground, vulnerable posture, quiet stillness"),
]

# Lighting & Atmosphere Patterns (Vietnamese -> Cinematic Lighting)
LIGHTING_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(đêm|nửa đêm|tối tăm|màn đêm|bóng tối)\b", re.I),
     "nocturnal ambiance, deep chiaroscuro shadows, cool moonlight rim lighting"),
    (re.compile(r"\b(hoàng hôn|chiều tà|bóng chiều|ráng chiều)\b", re.I),
     "warm golden hour sunset, rich amber and crimson rim light, long cinematic shadows"),
    (re.compile(r"\b(bình minh|sáng sớm|tia nắng|sương sớm)\b", re.I),
     "gentle early morning dawn, ethereal volumetric god rays filtering through mist"),
    (re.compile(r"\b(mưa|mưa rào|mưa bão|giọt mưa|ướt át)\b", re.I),
     "dramatic heavy rain shower, glistening wet surfaces, atmospheric moody reflections"),
    (re.compile(r"\b(sương mù|khói bụi|mờ ảo|hư ảo)\b", re.I),
     "dense cinematic fog and volumetric haze, atmospheric depth, mysterious silhouette"),
    (re.compile(r"\b(sấm sét|chớp|giông bão|bão tố)\b", re.I),
     "electric lightning flashing across dark storm clouds, high-contrast flash lighting"),
    (re.compile(r"\b(lửa|ngọn lửa|cháy|ánh lửa|than hồng)\b", re.I),
     "flickering warm campfire glow, dancing orange embers, dramatic firelight contrast"),
    (re.compile(r"\b(neon|phát sáng|lấp lánh|ánh đèn neon)\b", re.I),
     "vivid cyberpunk neon illumination in cyan and magenta, high-contrast glow"),
]

# Vox Narrative Hook Markers
HOOK_MARKERS = [
    re.compile(r"\b(tại sao|làm thế nào|nhưng ít ai biết|sự thật là|nguy hiểm|bí mật)\b", re.I),
    re.compile(r"\b(hãy tưởng tượng|điều gì sẽ xảy ra|bạn có bao giờ|câu hỏi lớn)\b", re.I),
    re.compile(r"\?"),
]

# Escalation & Conflict Markers
ESCALATION_MARKERS = [
    re.compile(r"\b(nhưng|tuy nhiên|bất ngờ|đột nhiên|hiểm nguy|đe dọa|khủng hoảng)\b", re.I),
    re.compile(r"\b(thách thức|căng thẳng|đối đầu|nghiệt ngã|mâu thuẫn|sụp đổ)\b", re.I),
]

# Climax Markers
CLIMAX_MARKERS = [
    re.compile(r"\b(cuối cùng|bước ngoặt|đỉnh điểm|trận chiến quyết định|sự thật phơi bày)\b", re.I),
    re.compile(r"\b(quyết định sinh tử|giây phút|bùng nổ|cao trào|khoảnh khắc)\b", re.I),
]

# Resolution Markers
RESOLUTION_MARKERS = [
    re.compile(r"\b(kết quả|bài học|từ đó|khép lại|tương lai|di sản|ý nghĩa|hôm nay)\b", re.I),
    re.compile(r"\b(kết thúc|bình yên trở lại|nhìn lại|tóm lại|thông điệp)\b", re.I),
]

# ==============================================================================
# 3. CORE SEMANTIC STORY ANALYZER
# ==============================================================================

class SemanticStoryAnalyzer:
    """
    Analyzes story text using the Vox Narrative Engine framework.
    Extracts multi-layered semantic attributes, splits text into optimal video scenes,
    and produces cinematic English image prompts.
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        ninerouter_api_key: Optional[str] = None,
        ninerouter_base_url: Optional[str] = None,
        preferred_provider: str = "auto",
        model_name: Optional[str] = None,
    ):
        self.ninerouter_api_key = ninerouter_api_key or NINEROUTER_API_KEY
        self.ninerouter_base_url = ninerouter_base_url or NINEROUTER_BASE_URL
        self.ninerouter_model = model_name or NINEROUTER_SCENE_MODEL or "ag/gemini-3.8-flash-low"
        self.gemini_api_key = gemini_api_key or GEMINI_API_KEY or None
        self.openrouter_api_key = openrouter_api_key or OPENROUTER_API_KEY or None
        self.preferred_provider = preferred_provider.lower()
        self.model_name = model_name
        # Lý do lần gọi LLM gần nhất thất bại (không chứa key), để báo cho người dùng khi phải chia offline
        self.last_error: Optional[str] = None

    def classify_narrative_beat(
        self,
        scene_text: str,
        scene_idx: int,
        total_scenes: int,
        accumulated_seconds: float,
    ) -> str:
        """
        Classifies scene into Vox 5-Stage Arc:
        hook (0-30s or first ~15%), setting, escalation, climax, resolution.
        """
        progress_ratio = scene_idx / max(1, total_scenes)

        # Hook: within first 30 seconds or first 15% of scenes
        if (accumulated_seconds <= 30.0 or progress_ratio <= 0.15) and scene_idx <= 4:
            return "hook"

        # Check explicit markers
        lower = scene_text.lower()

        # Check resolution near the end
        if progress_ratio >= 0.85:
            return "resolution"
        if progress_ratio >= 0.75 and any(p.search(lower) for p in RESOLUTION_MARKERS):
            return "resolution"

        # Check climax in the 60%-85% segment
        if 0.55 <= progress_ratio <= 0.85 and any(p.search(lower) for p in CLIMAX_MARKERS):
            return "climax"

        # Check escalation
        if any(p.search(lower) for p in ESCALATION_MARKERS):
            return "escalation"

        # Setting vs Escalation by structural progress
        if progress_ratio <= 0.40:
            return "setting"
        elif progress_ratio <= 0.70:
            return "escalation"
        elif progress_ratio <= 0.88:
            return "climax"
        else:
            return "resolution"

    def select_camera_framing_and_motion(
        self,
        narrative_beat: str,
        scene_idx: int,
        has_character: bool,
        has_action: bool,
        has_landscape: bool,
    ) -> Tuple[str, str]:
        """
        Selects cinematic framing (Shot Framing) and dynamic Ken Burns motion.
        Framing: Extreme Close-Up, Close-Up, Medium Shot, Wide Establishing Shot, Low-Angle Hero Shot, Drone/Aerial High-Angle.
        Motion: zoom_in, zoom_out, pan_left, pan_right, kenburns_diagonal.
        """
        if narrative_beat == "hook":
            # Hook demands punchy visual: Close-up dramatic portrait or massive drone shot
            if has_character:
                return "dramatic close-up shot focusing on intense eyes", "zoom_in"
            else:
                return "breathtaking sweeping high-angle drone shot", "zoom_in"

        elif narrative_beat == "setting":
            # Setting requires spatial context
            if has_landscape or not has_character:
                motion = "pan_right" if scene_idx % 2 == 0 else "zoom_out"
                return "grand wide establishing shot showcasing full environment", motion
            else:
                return "cinematic medium wide shot", "pan_left"

        elif narrative_beat == "escalation":
            # Escalation emphasizes action and rising stakes
            if has_action:
                return "dynamic low-angle medium shot with Dutch tilt", "zoom_in"
            else:
                motion = "pan_left" if scene_idx % 2 == 0 else "pan_right"
                return "cinematic medium shot with intense depth of field", motion

        elif narrative_beat == "climax":
            # Climax: Maximum tension
            if has_character:
                return "intense low-angle hero close-up, dramatic lighting", "zoom_in"
            else:
                return "epic wide shot capturing pivotal catastrophic confrontation", "zoom_in"

        elif narrative_beat == "resolution":
            # Resolution: Calming, pull back
            return "serene wide resolution shot pulling backward into distance", "zoom_out"

        # Default fallback
        motions = ["zoom_in", "pan_left", "zoom_out", "pan_right"]
        return "cinematic eye-level medium shot", motions[scene_idx % len(motions)]

    def extract_semantic_layers_rule_based(
        self,
        scene_text: str,
        scene_idx: int,
        narrative_beat: str,
    ) -> Dict[str, Any]:
        """
        Multi-tier extraction using lexical grammar and semantic patterns.
        Extracts: setting, subject, emotion, action, lighting, framing, motion.
        """
        lower = scene_text.lower()

        # 1. Setting
        matched_settings = []
        for pattern, desc in SETTING_PATTERNS:
            if pattern.search(lower):
                matched_settings.append(desc)
        setting = matched_settings[0] if matched_settings else "atmospheric cinematic environment"

        # 2. Subject & Character
        matched_subjects = []
        for pattern, desc in SUBJECT_PATTERNS:
            if pattern.search(lower):
                matched_subjects.append(desc)
        has_character = bool(matched_subjects)
        subject = matched_subjects[0] if matched_subjects else "a charismatic narrative subject"

        # 3. Emotion
        matched_emotions = []
        for pattern, desc in EMOTION_PATTERNS:
            if pattern.search(lower):
                matched_emotions.append(desc)
        emotion = matched_emotions[0] if matched_emotions else "focused, resolute expression"

        # 4. Action
        matched_actions = []
        for pattern, desc in ACTION_PATTERNS:
            if pattern.search(lower):
                matched_actions.append(desc)
        has_action = bool(matched_actions)
        action = matched_actions[0] if matched_actions else "observing the unfolding event with quiet vigilance"

        # 5. Lighting & Atmosphere
        matched_lighting = []
        for pattern, desc in LIGHTING_PATTERNS:
            if pattern.search(lower):
                matched_lighting.append(desc)
        lighting = matched_lighting[0] if matched_lighting else "cinematic natural volumetric lighting with soft directional shadows"

        # 6. Framing & Motion
        framing, motion = self.select_camera_framing_and_motion(
            narrative_beat=narrative_beat,
            scene_idx=scene_idx,
            has_character=has_character,
            has_action=has_action,
            has_landscape=bool(matched_settings),
        )

        return {
            "setting": setting,
            "subject": subject,
            "emotion": emotion,
            "action": action,
            "lighting": lighting,
            "framing": framing,
            "camera_motion": motion,
        }

    def build_cinematic_english_prompt(
        self,
        semantics: Dict[str, Any],
        narrative_beat: str,
        style_preset: str = "cinematic_realistic",
        character_anchor: Optional[str] = None,
    ) -> str:
        """
        Synthesizes extracted semantic layers into a master Hollywood/Midjourney-grade visual prompt.
        """
        framing = semantics["framing"]
        subject = character_anchor if character_anchor else semantics["subject"]
        emotion = semantics["emotion"]
        action = semantics["action"]
        setting = semantics["setting"]
        lighting = semantics["lighting"]

        # Compose rich cinematic prompt
        prompt_parts = [
            f"{framing} of {subject}",
            f"{emotion}",
            f"{action}",
            f"set within {setting}",
            f"{lighting}",
            "photorealistic 8k, award-winning cinematography, Arri Alexa LF 35mm lens",
            "volumetric atmospheric depth, color graded, masterpiece composition",
        ]

        if style_preset == "cyberpunk":
            prompt_parts.append("neon cyan and magenta reflections, dystopian futuristic details")
        elif style_preset == "anime_masterpiece":
            prompt_parts.append("Makoto Shinkai aesthetic, vibrant cloudscapes, vivid hand-drawn anime details")
        elif style_preset == "watercolor":
            prompt_parts.append("expressive watercolor wash, subtle paper texture, artistic pigment bleeds")
        elif style_preset == "dark_fantasy":
            prompt_parts.append("dark gothic fantasy, dark souls concept art, gritty photorealistic textures")

        return ", ".join(prompt_parts)

    async def call_9router_semantic_analyzer(
        self,
        text_chunk: str,
        pacing_name: str = "fast",
        pacing: Optional[str] = None,
        style_preset: str = "manga_murata_battle",
        is_novel: bool = False,
        part_note: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Calls 9router Gateway with Gemini 3.8 Flash to analyze script or adapt novel chapter
        into engaging US YouTube story podcast scenes with detailed image prompts.
        """
        if not self.ninerouter_api_key:
            return None

        actual_pacing = pacing or pacing_name or "fast"
        model = self.ninerouter_model or "ag/gemini-3.8-flash-low"
        endpoint = f"{self.ninerouter_base_url.rstrip('/')}/chat/completions"
        pacing_info = PACING_CONFIGS.get(actual_pacing, PACING_CONFIGS["fast"])

        from services.tts_service import detect_language
        input_lang = detect_language(text_chunk)
        if input_lang == "vi":
            narration_rule = (
                "QUY TẮC CỐT LÕI: ĐÚNG CHẤT YOUTUBE REVIEW TRUYỆN (REVIEWER HOST):\n"
                "1. ĐÂY LÀ KỊCH BẢN REVIEW & TÓM TẮT TRUYỆN YOUTUBE: Người đọc là một Reviewer/Host chuyên nghiệp đang đọc và review, phân tích, dẫn dắt câu chuyện cho khán giả xem ('Tôi đọc và tôi review').\n"
                "2. TUYỆT ĐỐI KHÔNG DÙNG NGÔI THỨ NHẤT CỦA NHÂN VẬT (KHÔNG để nhân vật xưng 'Tôi là Nanahoshi... Tôi bị chuyển sinh... Tôi đi học võ...'). Đây KHÔNG phải kịch truyền thanh hay sách nói tự sự!\n"
                "3. BẮT BUỘC DÙNG NGÔI THỨ BA CHO CÁC NHÂN VẬT: Gọi rõ tên nhân vật ('Nanahoshi', 'cô ấy', 'cô nàng', 'Rudeus', 'Silvaril'). Người Reviewer đứng ở vai trò người dẫn chuyện bao quát để review lại hành trình và cảm xúc của nhân vật.\n"
                "4. VĂN PHONG YOUTUBE REVIEW TRIỆU VIEW: Lôi cuốn, nhịp điệu gãy gọn, tạo sự tò mò, kịch tính và đồng cảm. Giữ nguyên 100% TIẾNG VIỆT, tuyệt đối không dịch trường 'text' sang tiếng Anh.\n"
                "5. Trường 'image_prompt' PHẢI viết bằng TIẾNG ANH điện ảnh chi tiết, mô tả chính xác góc máy, nhân vật, hành động, biểu cảm và bối cảnh tương ứng để AI (Meta Muse) vẽ tranh đẹp nhất."
            )
            lang_label = "Vietnamese YouTube Novel Review Host ('text' in Vietnamese 3rd person review, 'image_prompt' in English)"
        else:
            narration_rule = (
                "1. Output English narration text in the 'text' field optimized for spoken audio (natural, punchy, engaging storytelling tone for a male US voice like Andrew / Guy).\n"
                "2. Output ultra-detailed cinematic English prompt in the 'image_prompt' field for AI image generation."
            )
            lang_label = "English narration ('text' and 'image_prompt' in English)"

        system_instruction = (
            "You are an elite YouTube Story Podcast Director and Hollywood Cinematographer.\n"
            "Your objective: Convert the provided story text or novel chapter into an unforgettable audio-visual story video with high YouTube retention.\n\n"
        )
        if input_lang == "vi":
            system_instruction += (
                "=== VAI TRÒ ĐẠO DIỄN: YOUTUBE MANGA/NOVEL REVIEWER & PODCAST HOST ===\n"
                "- Bạn là một Reviewer chuyên nghiệp trên YouTube chuyên tóm tắt và đánh giá các bộ tiểu thuyết/manga đình đám.\n"
                "- PHONG CÁCH: 'Tôi đọc và tôi review cho khán giả'. Người dẫn chuyện đứng ở góc nhìn thứ ba để kể lại, phân tích và làm nổi bật câu chuyện của nhân vật.\n"
                "- QUY TẮC NGÔI XƯNG: TUYỆT ĐỐI KHÔNG xưng 'Tôi' thay cho nhân vật (Không dùng ngôi thứ nhất của nhân vật). Hãy gọi tên nhân vật ('Nanahoshi', 'cô gái', 'cô ấy', 'Rudeus').\n"
                "- Ví dụ mẫu: 'Nhân vật chính của chúng ta là Nanahoshi Shizuka... Để tìm đường trở về thế giới thực, cô đã giam mình trong phòng thí nghiệm... Nhưng nghiệt ngã thay, mỗi lần cô tỉnh dậy thì thế giới đã trôi qua cả một năm...'\n"
                "- Toàn bộ nội dung trường 'text' BẮT BUỘC là TIẾNG VIỆT tự nhiên, cuốn hút. TUYỆT ĐỐI KHÔNG dịch trường 'text' sang tiếng Anh!\n"
                "- Trường 'image_prompt' BẮT BUỘC viết bằng TIẾNG ANH chi tiết phục vụ AI tạo ảnh.\n\n"
            )

        system_instruction += (
            "CRITICAL CINEMATIC RULE - MAXIMUM SHOT VARIETY & COMPOSITION:\n"
            "- NEVER generate the same full-body center-framed character portrait across consecutive scenes! It looks boring and amateurish.\n"
            "- Every single scene MUST feature a completely DIFFERENT camera angle, framing, distance, and focal subject:\n"
            "  * SCENE 1 (HOOK / VISCERAL TENSION): Extreme Macro Close-up or high-impact kinetic shot (e.g. fierce razor-sharp eyes through battered helmet visor, bleeding knuckles clenching, blade tip reflecting sunlight flare, boots digging into shattered asphalt).\n"
            "  * SCENE 2 (ESTABLISHING / WORLD SCALE): Monumental Wide Panoramic or Bird's-eye Aerial shot establishing the grand environment (e.g. shattered ancient acropolis ruins, colossal mountain gorges, churning turquoise ocean waves, dark burning storm skies, endless army marching to horizon. Main hero is tiny in distance or off-screen to let the epic scale breathe).\n"
            "  * SCENE 3 (ESCALATION / ANTAGONIST / MENACE): Medium shot or Over-the-shoulder shot framing the threat (e.g. towering demonic god descending through torn crimson clouds, menacing enemy army charging, faceless mask assassins emerging through dust).\n"
            "  * SCENE 4 (CLIMAX / DYNAMIC KINETIC IMPACT): Ground-level devastating collision, explosive mid-air strike, shattered shields, showering fiery sparks, pulverized stone debris exploding airborne, radial speed lines, kinetic motion blur!\n"
            "  * SCENE 5 (AFTERMATH / RESOLUTION): Dramatic low-angle heroic stance or atmospheric silhouette walking toward burning dawn horizon, fallen weapons planted in scorched earth.\n\n"
            "Style Guidelines:\n"
            f"- Target Style Preset: '{style_preset}'\n"
            "- If 'manga_murata_battle': intense shonen action, Yusuke Murata / Kengan Ashura double-page spread, flying debris, radial speed lines, hand-drawn SFX lettering (KA-BOOM, CRASH, 衝撃), screentone, crimson energy aura glow.\n"
            "- If 'spartan_epic_mythology': Frank Frazetta & Zack Snyder 300 aesthetic, Greek mythology oil painting, anatomical bronze armor, Corinthian helmet, sun hoplon shield, chiaroscuro golden amber rim lighting, floating embers, 8k.\n"
            "- If 'intricate_ink_crosshatch': fine black and white pen and ink graphic novel illustration, meticulous cross-hatching, heavy ink shadows, sharp lineart.\n"
            "- If 'dark_fantasy': Elden Ring / Dark Souls aesthetic, ruined gothic castles, grim fog, glowing runes, photorealistic textures.\n\n"
            "Requirements for Output:\n"
            f"{narration_rule}\n"
            "3. Scene 1 MUST be an irresistible 5-second HOOK that creates intense curiosity, conflict, or high stakes.\n"
            "4. Pacing: 3-6 seconds per scene (approx 10-25 spoken words per scene).\n"
            "5. Output format: A strictly valid JSON array of scene objects. Each object MUST contain:\n"
            "   - order: integer (1, 2, ...)\n"
            "   - text: narration sentence for this scene (in original language: Vietnamese VERBATIM if input is Vietnamese, TUYỆT ĐỐI KHÔNG DỊCH 'text' SANG TIẾNG ANH; English if input is English)\n"
            "   - narrative_beat: 'hook' | 'setting' | 'escalation' | 'climax' | 'resolution'\n"
            "   - camera_motion: 'zoom_in' | 'zoom_out' | 'pan_left' | 'pan_right' | 'action_camera_shake' | 'manga_speedlines' | 'punch_zoom'\n"
            "   - image_prompt: fully self-contained, descriptive master prompt specifying camera framing, focal subject, action, lighting, and debris/atmosphere (in English)\n"
            "   - estimated_duration: float seconds (approx word_count / 3.0)\n"
            "Return ONLY the raw JSON array. Do not wrap in markdown quotes or extra explanations."
        )

        headers = {
            "Authorization": f"Bearer {self.ninerouter_api_key}",
            "Content-Type": "application/json",
        }

        user_content = (
            f"TARGET PACING: {actual_pacing} ({pacing_info['description']})\n"
            f"STYLE PRESET: {style_preset}\n"
            f"IS LIGHT NOVEL CHAPTER: {is_novel}\n\n"
            f"{_part_header(part_note)}"
            f"STORY CONTENT TO ADAPT:\n{text_chunk}"
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=LLM_PART_TIMEOUT_S) as client:
                res = await client.post(endpoint, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    clean_json = re.sub(r"^```(?:json)?\s*", "", content.strip())
                    clean_json = re.sub(r"\s*```$", "", clean_json)
                    parsed = json.loads(clean_json)
                    if isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict) and "scenes" in parsed:
                        return parsed["scenes"]
                    self.last_error = "9router trả về JSON không đúng dạng danh sách cảnh"
                else:
                    logger.warning(f"9router LLM returned status {res.status_code}: {res.text[:200]}")
                    self.last_error = f"9router HTTP {res.status_code}: {res.text[:200]}"
        except httpx.TimeoutException:
            logger.error(f"9router LLM timeout after {LLM_PART_TIMEOUT_S:g}s")
            self.last_error = f"9router không trả lời trong {LLM_PART_TIMEOUT_S:g} giây"
        except Exception as e:
            logger.error(f"Error calling 9router LLM: {type(e).__name__}: {e}")
            # Một số lỗi httpx có chuỗi rỗng: kèm tên lỗi để người dùng biết chuyện gì xảy ra
            self.last_error = f"Lỗi gọi 9router: {type(e).__name__}: {e}".rstrip(": ")

        return None

    async def call_gemini_semantic_analyzer(
        self,
        text_chunk: str,
        pacing_name: str,
        part_note: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Calls Gemini API (gemini-2.0-flash / gemini-1.5-flash) to perform deep semantic decomposition.
        """
        if not self.gemini_api_key:
            return None

        model = self.model_name or "gemini-2.0-flash"
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}"

        pacing_info = PACING_CONFIGS.get(pacing_name, PACING_CONFIGS["fast"])

        system_instruction = (
            "You are a master YouTube documentary director (Vox / Johnny Harris style) and Hollywood cinematographer.\n"
            "Analyze the following story/script text and split it into engaging, coherent video scenes.\n"
            f"Pacing style: '{pacing_name}' ({pacing_info['description']}).\n"
            f"Target {pacing_info['min_words']} to {pacing_info['max_words']} Vietnamese words per scene.\n"
            "Vox Narrative Structure to apply:\n"
            "- Hook (first scenes): high tension, intriguing question, punchy visual.\n"
            "- Setting: establish space, time, stakes.\n"
            "- Escalation: conflict, rising stakes, active struggle.\n"
            "- Climax: peak emotional or narrative impact.\n"
            "- Resolution: takeaway, aftermath, synthesis.\n\n"
            "Return a strictly valid JSON array of objects with the following keys for each scene:\n"
            "- order (integer 1..N)\n"
            "- text (Vietnamese YouTube review sentence/segment - BẮT BUỘC dùng ngôi thứ ba về nhân vật như Nanahoshi, cô ấy; đứng từ góc nhìn Reviewer/Host kể và review truyện cho khán giả; TUYỆT ĐỐI không dùng ngôi thứ nhất 'tôi' của nhân vật, không dịch sang tiếng Anh)\n"
            "- narrative_beat ('hook' | 'setting' | 'escalation' | 'climax' | 'resolution')\n"
            "- setting (English description of environment/backdrop)\n"
            "- subject (English description of character or focal object)\n"
            "- action (English description of active movement/motion)\n"
            "- lighting (English description of lighting & atmosphere)\n"
            "- camera_framing ('Extreme Close-up' | 'Close-up' | 'Medium Shot' | 'Wide Establishing Shot' | 'Low-angle' | 'High-angle Drone')\n"
            "- camera_motion ('zoom_in' | 'zoom_out' | 'pan_left' | 'pan_right' | 'kenburns_diagonal')\n"
            "- image_prompt (Extremely detailed Midjourney/Flux English prompt with cinematic lighting, 8k, 35mm lens, atmospheric depth)\n"
            "- estimated_duration (float seconds based on narration length)\n"
            "Do NOT include markdown quotes around the JSON if possible, or wrap in ```json ... ```."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_instruction}\n\n{_part_header(part_note)}STORY SCRIPT:\n{text_chunk}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=LLM_PART_TIMEOUT_S) as client:
                res = await client.post(endpoint, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content = data["candidates"][0]["content"]["parts"][0]["text"]
                    clean_json = re.sub(r"^```json\s*", "", content.strip())
                    clean_json = re.sub(r"\s*```$", "", clean_json)
                    parsed = json.loads(clean_json)
                    if isinstance(parsed, list):
                        return parsed
                else:
                    logger.warning(f"Gemini API returned status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")

        return None

    async def call_openrouter_semantic_analyzer(
        self,
        text_chunk: str,
        pacing_name: str,
        part_note: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Calls OpenRouter API for deep semantic decomposition using Gemini or Claude or Llama models.
        """
        if not self.openrouter_api_key:
            return None

        model = self.model_name or "google/gemini-2.0-flash-001"
        endpoint = "https://openrouter.ai/api/v1/chat/completions"

        pacing_info = PACING_CONFIGS.get(pacing_name, PACING_CONFIGS["fast"])

        prompt = (
            "You are a master YouTube documentary director (Vox / Johnny Harris style) and Hollywood cinematographer.\n"
            "Analyze the following story/script text and split it into engaging, coherent video scenes.\n"
            f"Pacing style: '{pacing_name}' ({pacing_info['description']}).\n"
            f"Target {pacing_info['min_words']} to {pacing_info['max_words']} Vietnamese words per scene.\n"
            "Structure as Vox 5-Stage Arc (hook, setting, escalation, climax, resolution).\n"
            "Output JSON ONLY as an array of objects matching this schema:\n"
            "[{\n"
            '  "order": 1,\n'
            '  "text": "Vietnamese narrative sentence (BẮT BUỘC giữ nguyên văn bản tiếng Việt giàu cảm xúc kể chuyện review podcast, TUYỆT ĐỐI không tóm tắt hay tự ý dịch sang tiếng Anh)",\n'
            '  "narrative_beat": "hook",\n'
            '  "setting": "English description of environment",\n'
            '  "subject": "English description of character/object",\n'
            '  "action": "English description of action",\n'
            '  "lighting": "English description of lighting",\n'
            '  "camera_framing": "Close-up",\n'
            '  "camera_motion": "zoom_in",\n'
            '  "image_prompt": "Cinematic 8k English prompt for Midjourney/Flux",\n'
            '  "estimated_duration": 3.5\n'
            "}]\n\n"
            f"{_part_header(part_note)}"
            f"STORY SCRIPT:\n{text_chunk}"
        )

        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "HTTP-Referer": "https://opctool.local/story-studio",
            "X-Title": "YouTube Story Studio Vox Engine",
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You output strictly valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=LLM_PART_TIMEOUT_S) as client:
                res = await client.post(endpoint, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    clean_json = re.sub(r"^```json\s*", "", content.strip())
                    clean_json = re.sub(r"\s*```$", "", clean_json)
                    parsed = json.loads(clean_json)
                    if isinstance(parsed, list):
                        return parsed
                else:
                    logger.warning(f"OpenRouter API returned status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            logger.error(f"Error calling OpenRouter API: {e}")

        return None

# ==============================================================================
# 4. CHUNKING & OFFLINE VOX SCENE SPLITTING ENGINE
# ==============================================================================

def chunk_long_text_into_sentences(full_text: str) -> List[str]:
    """
    Splits long text, novel chapters, or articles into individual coherent sentences.
    Preserves dialogue quotes, punctuation, and avoids broken fragments.
    """
    clean_text = full_text.strip()
    if not clean_text:
        return []

    # Replace windows line endings
    clean_text = clean_text.replace("\r\n", "\n").replace("\r", "\n")

    # Split paragraphs first
    paragraphs = [p.strip() for p in clean_text.split("\n") if p.strip()]

    all_sentences: List[str] = []

    for para in paragraphs:
        # Split paragraph on sentence delimiters while preserving punctuation
        parts = re.split(r'([.!?…]+["\'”’]?\s+)', para)
        for i in range(0, len(parts) - 1, 2):
            sentence = (parts[i] + parts[i + 1]).strip()
            if sentence:
                all_sentences.append(sentence)
        # Any remaining tail without trailing sentence delimiter
        if len(parts) % 2 == 1 and parts[-1].strip():
            all_sentences.append(parts[-1].strip())

    return all_sentences


def group_sentences_by_pacing(
    sentences: List[str],
    pacing_name: str = "fast",
    max_words_override: Optional[int] = None,
) -> List[str]:
    """
    Groups individual sentences into scenes that strictly respect the target pacing word counts.
    """
    pacing_info = PACING_CONFIGS.get(pacing_name, PACING_CONFIGS["fast"])
    max_words = max_words_override if max_words_override else pacing_info["max_words"]

    scenes_raw: List[str] = []
    current_sentences: List[str] = []
    current_words = 0

    for sentence in sentences:
        words = len(sentence.split())

        # If a single sentence is already longer than max_words, handle it or split by clauses
        if words > max_words * 1.5:
            # If we had accumulated sentences, flush them
            if current_sentences:
                scenes_raw.append(" ".join(current_sentences))
                current_sentences = []
                current_words = 0

            # Split long sentence by semicolons, commas or dashes if possible
            sub_clauses = re.split(r'(?<=[,;—–])\s+', sentence)
            sub_current = []
            sub_count = 0
            for clause in sub_clauses:
                c_words = len(clause.split())
                if sub_count + c_words > max_words and sub_current:
                    scenes_raw.append(" ".join(sub_current))
                    sub_current = [clause]
                    sub_count = c_words
                else:
                    sub_current.append(clause)
                    sub_count += c_words
            if sub_current:
                scenes_raw.append(" ".join(sub_current))
            continue

        if current_words + words > max_words and current_sentences:
            scenes_raw.append(" ".join(current_sentences))
            current_sentences = [sentence]
            current_words = words
        else:
            current_sentences.append(sentence)
            current_words += words

    if current_sentences:
        scenes_raw.append(" ".join(current_sentences))

    return scenes_raw


# Mỗi lần gọi LLM chỉ gửi một phần ngắn, như luồng true-crime (khúc 3.000 ký tự): gửi cả chương
# một lần thì LLM hay tóm tắt, bỏ chi tiết hoặc trả quá lâu. Bài dài được chia nhiều phần, gọi lần lượt.
LLM_PART_MAX_CHARS = 3000
# Số lần gọi tối đa cho một phần: lần đầu và một lần thử lại kèm góp ý.
LLM_PART_ATTEMPTS = 2
# Lời kể các cảnh của một phần phải dài ít nhất chừng này so với phần gốc; ngắn hơn là LLM đã tóm tắt.
# Đo thật 20/10/2026 trên bài true-crime tiếng Việt: lời kể kiểu reviewer 40-64% vẫn đủ mọi sự kiện;
# 30% đã mất cả một tình tiết; gửi cả bài một lần (LLM lười) chỉ còn 12%. Lần thử lại kèm góp ý
# đưa phần 27% lên 60-76%.
LLM_MIN_COVERAGE = 0.4
# Bấy nhiêu phần liền nhau gọi lỗi (HTTP, timeout, JSON hỏng) thì coi như LLM đang hỏng: các phần còn lại
# chia offline, không chờ thêm. Phần LLM trả lời nhưng kể quá ngắn không tính, vì LLM vẫn chạy.
LLM_MAX_FAILED_PARTS_IN_ROW = 2
# Timeout một lần gọi (giây). Luồng true-crime đo thật ≤ 63 s cho khúc 3.000 ký tự; chừa thêm vì
# danh sách cảnh kèm prompt ảnh dài hơn.
LLM_PART_TIMEOUT_S = 150.0

# Chỗ ngắt câu: sau dấu kết câu (kèm nháy/ngoặc đóng) có khoảng trắng, để "3.5" không bị tách;
# dấu kết câu CJK không cần khoảng trắng phía sau.
_SENTENCE_BREAK = re.compile(r'(?:(?<=[.!?…])|(?<=[.!?…]["\'”’)\]]))\s+|(?<=[。！？])\s*')


def _pack_pieces(pieces: List[str], sep: str, max_chars: int) -> List[str]:
    """Gộp các mảnh (mỗi mảnh <= max_chars) thành ít phần nhất, mỗi phần <= max_chars."""
    packed: List[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{sep}{piece}" if current else piece
        if len(candidate) <= max_chars:
            current = candidate
        else:
            packed.append(current)
            current = piece
    if current:
        packed.append(current)
    return packed


def split_text_for_llm(full_text: str, max_chars: int) -> List[str]:
    """
    Chia bài thành các phần <= max_chars ký tự để gửi LLM, ưu tiên ranh giới đoạn văn rồi câu;
    câu dài hơn giới hạn mới cắt theo từ. Không bỏ chữ nào: chỉ khoảng trắng ở chỗ cắt có thể đổi.
    """
    text = full_text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    pieces: List[str] = []
    for para in (p.strip() for p in text.split("\n")):
        if len(para) <= max_chars:
            if para:
                pieces.append(para)
            continue
        sentence_pieces: List[str] = []
        for sentence in _SENTENCE_BREAK.split(para):
            if len(sentence) <= max_chars:
                if sentence:
                    sentence_pieces.append(sentence)
                continue
            words: List[str] = []
            for word in sentence.split():
                words.extend(word[i:i + max_chars] for i in range(0, len(word), max_chars))
            sentence_pieces.extend(_pack_pieces(words, " ", max_chars))
        pieces.extend(_pack_pieces(sentence_pieces, " ", max_chars))
    return _pack_pieces(pieces, "\n", max_chars)


def _llm_part_note(index: int, total: int) -> Optional[str]:
    """Dặn LLM đây là một phần của bài dài, để không tóm tắt và không mở hook mới giữa chừng."""
    if total <= 1:
        return None
    note = (
        f"PART {index}/{total} OF THE SAME STORY (the text is long, so it is sent in parts). "
        "Adapt ALL of this part's content in order; do not summarize or skip anything."
    )
    if index > 1:
        note += " Continue directly from the previous part: do NOT open with a new hook or re-introduce the story."
    return note


def _part_header(part_note: Optional[str]) -> str:
    return f"{part_note}\n\n" if part_note else ""


def _check_part_scenes(part: str, scenes: Any) -> Optional[Tuple[str, str]]:
    """Kiểm cảnh LLM trả cho một phần. Đạt thì None; không đạt thì (lý do cho người dùng, góp ý gửi lại LLM)."""
    if not isinstance(scenes, list) or not scenes:
        return "LLM không trả về cảnh nào", "Your previous answer contained no scenes. Return the JSON array of scenes."
    if any(not isinstance(s, dict) or not str(s.get("text") or "").strip() for s in scenes):
        return "LLM trả cảnh thiếu lời kể", "Every scene object MUST have a non-empty 'text' field."
    coverage = sum(len(str(s["text"]).strip()) for s in scenes) / max(len(part), 1)
    if coverage < LLM_MIN_COVERAGE:
        pct = round(coverage * 100)
        return (
            f"LLM tóm tắt quá ngắn (lời kể chỉ bằng {pct}% phần gốc)",
            f"Your previous answer narrated only about {pct}% of this part and skipped content. Narrate ALL "
            "events, details and dialogue of this part in order, using as many scenes as needed; do not summarize.",
        )
    return None


async def _llm_scenes_for_part(
    analyzer: "SemanticStoryAnalyzer",
    call_part: Callable[..., Awaitable[Optional[List[Dict[str, Any]]]]],
    part: str,
    index: int,
    total: int,
) -> Tuple[Optional[List[Dict[str, Any]]], str, bool]:
    """
    Gọi LLM cho một phần; lỗi hoặc kết quả mỏng thì thử lại kèm góp ý.
    Trả (cảnh, "", False) khi đạt, hoặc (None, lý do, có phải lỗi gọi LLM ở lần cuối không).
    """
    base_note = _llm_part_note(index, total)
    note = base_note
    reason = ""
    call_error = False
    for _attempt in range(LLM_PART_ATTEMPTS):
        analyzer.last_error = None
        scenes = await call_part(part, part_note=note)
        problem = _check_part_scenes(part, scenes)
        if problem is None and isinstance(scenes, list):
            for scene in scenes:
                try:
                    scene["estimated_duration"] = float(scene.get("estimated_duration", 4.0))
                except (TypeError, ValueError):
                    scene["estimated_duration"] = 4.0
            return scenes, "", False
        user_reason, llm_feedback = problem or ("LLM không trả về cảnh nào", "")
        call_error = bool(analyzer.last_error)
        reason = analyzer.last_error or user_reason
        logger.warning(f"Chia cảnh bằng LLM: phần {index}/{total} không đạt ({reason})")
        # Lỗi gọi (HTTP, timeout, JSON hỏng) thì gọi lại như cũ; kết quả mỏng/thiếu lời thì kèm góp ý
        feedback = None if call_error else f"PREVIOUS ATTEMPT REJECTED: {llm_feedback}"
        note = "\n\n".join(n for n in (base_note, feedback) if n) or None
    return None, reason, call_error


async def _scenes_in_parts(
    analyzer: "SemanticStoryAnalyzer",
    text: str,
    call_part: Callable[..., Awaitable[Optional[List[Dict[str, Any]]]]],
    offline_part: Callable[[str], List[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], List[Tuple[int, int, int, str]], int, int]:
    """
    Chia bài thành phần nhỏ, gọi LLM lần lượt từng phần, nối cảnh và đánh lại order từ 1.
    Phần LLM không làm được (sau khi thử lại) thì chỉ phần đó chia offline, các phần khác giữ cảnh AI;
    LLM_MAX_FAILED_PARTS_IN_ROW phần liền nhau gọi lỗi thì các phần còn lại chia offline luôn.
    Trả (cảnh, các phần chia offline [(phần, cảnh đầu, cảnh cuối, lý do)], số phần AI làm, tổng số phần).
    """
    parts = split_text_for_llm(text, LLM_PART_MAX_CHARS)
    total = len(parts)
    if total > 1:
        logger.info(f"Bài dài {len(text)} ký tự, chia {total} phần (tối đa {LLM_PART_MAX_CHARS} ký tự) để gọi LLM")
    scenes: List[Dict[str, Any]] = []
    offline_notes: List[Tuple[int, int, int, str]] = []
    ai_parts = 0
    failed_in_row = 0
    for index, part in enumerate(parts, start=1):
        if failed_in_row >= LLM_MAX_FAILED_PARTS_IN_ROW:
            part_scenes, reason, call_error = None, f"bỏ qua LLM vì {failed_in_row} phần liền trước gọi lỗi", True
        else:
            part_scenes, reason, call_error = await _llm_scenes_for_part(analyzer, call_part, part, index, total)
        # Chỉ lỗi gọi mới tính vào chuỗi lỗi; LLM trả lời (dù kể ngắn) nghĩa là nó vẫn chạy
        failed_in_row = failed_in_row + 1 if call_error else 0
        if part_scenes:
            ai_parts += 1
        else:
            part_scenes = offline_part(part)
            offline_notes.append((index, len(scenes) + 1, len(scenes) + len(part_scenes), reason))
        scenes.extend(part_scenes)
    for order, scene in enumerate(scenes, start=1):
        scene["order"] = order
    return scenes, offline_notes, ai_parts, total


def _offline_parts_reason(offline_notes: List[Tuple[int, int, int, str]], total: int) -> str:
    """Báo những cảnh nào chia offline; các phần liền nhau cùng lý do được gộp một mục."""
    groups: List[List[Any]] = []
    for part, first, last, reason in offline_notes:
        if groups and groups[-1][4] == reason and groups[-1][1] == part - 1:
            groups[-1][1], groups[-1][3] = part, last
        else:
            groups.append([part, part, first, last, reason])
    items = []
    for p1, p2, first, last, reason in groups:
        parts_label = f"phần {p1}/{total}" if p1 == p2 else f"phần {p1}–{p2}/{total}"
        items.append(f"cảnh {first}–{last} ({parts_label}): {reason}")
    return "Chia offline, prompt ảnh là mẫu chung ở " + "; ".join(items)


def _offline_fallback_reason(llm_failure: str, has_key: bool) -> str:
    """
    Vì sao cả bài phải chia offline. Không lặng lẽ: caller cần báo người dùng rằng prompt ảnh
    là mẫu chung, không do AI viết. llm_failure là lý do LLM lỗi ở phần đầu tiên ("" nếu chưa gọi).
    """
    if llm_failure:
        return llm_failure
    if not has_key:
        return "Chưa cấu hình key 9router (NINEROUTER_API_KEY)"
    return "LLM không trả về cảnh nào"


# ==============================================================================
# 5. PUBLIC API INTERFACES
# ==============================================================================

async def analyze_vox_script_async(
    full_text: str,
    pacing: str = "fast",
    max_words_per_scene: Optional[int] = None,
    style_preset: str = "cinematic_realistic",
    character_anchor: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openrouter_api_key: Optional[str] = None,
    provider: str = "auto",
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main asynchronous analyzer:
    1. Tries cloud LLM (Gemini or OpenRouter) if keys are provided or found in environment.
    2. Seamlessly falls back to the in-process Semantic Pattern & Rule Parser (Layer 2).
    """
    analyzer = SemanticStoryAnalyzer(
        gemini_api_key=gemini_api_key,
        openrouter_api_key=openrouter_api_key,
        preferred_provider=provider,
        model_name=model_name,
    )

    clean_text = full_text.strip()
    if not clean_text:
        return {
            "title": "Empty Script",
            "total_scenes": 0,
            "estimated_total_duration": 0.0,
            "pacing": pacing,
            "narrative_summary": {},
            "scenes": [],
        }

    # Attempt Cloud LLM if available and requested: bài chia phần nhỏ, gọi lần lượt;
    # phần LLM không làm được thì chỉ phần đó chia offline, không bỏ chữ nào.
    call_part = None
    if provider != "offline":
        if provider in ("9router", "auto", "gemini") and analyzer.ninerouter_api_key:
            call_part = functools.partial(
                analyzer.call_9router_semantic_analyzer, pacing=pacing, style_preset=style_preset
            )
        elif (provider in ("gemini", "auto") and analyzer.gemini_api_key):
            call_part = functools.partial(analyzer.call_gemini_semantic_analyzer, pacing_name=pacing)
        elif (provider in ("openrouter", "auto") and analyzer.openrouter_api_key):
            call_part = functools.partial(analyzer.call_openrouter_semantic_analyzer, pacing_name=pacing)

    def offline_part(part: str) -> List[Dict[str, Any]]:
        return split_text_into_vox_scenes_offline(
            full_text=part,
            pacing=pacing,
            max_words_per_scene=max_words_per_scene,
            style_preset=style_preset,
            character_anchor=character_anchor,
        )["scenes"]

    llm_failure = ""
    if call_part:
        llm_scenes, offline_notes, ai_parts, total_parts = await _scenes_in_parts(
            analyzer, clean_text, call_part, offline_part)
        if not ai_parts:
            llm_failure = offline_notes[0][3] if offline_notes else ""
    else:
        llm_scenes, offline_notes, ai_parts, total_parts = [], [], 0, 0

    # Process scenes if LLM succeeded (ít nhất một phần)
    if ai_parts:
        total_duration = sum(s.get("estimated_duration", 4.0) for s in llm_scenes)
        beats_count = {}
        for s in llm_scenes:
            b = s.get("narrative_beat", "setting")
            beats_count[b] = beats_count.get(b, 0) + 1
            s.setdefault("setting", "Cinematic environment")
            s.setdefault("subject", "Main character / focal subject")
            s.setdefault("action", "Dramatic story event")
            s.setdefault("lighting", "Atmospheric volumetric lighting")
            s.setdefault("camera_framing", "dramatic close-up shot focusing on intense eyes" if b == "hook" else "cinematic medium shot")
            # Ensure camera_motion conforms to core Ken Burns motions
            valid_motions = ["zoom_in", "zoom_out", "pan_left", "pan_right"]
            if s.get("camera_motion") not in valid_motions:
                s["camera_motion"] = "zoom_in"
            s.setdefault("emotion", "")
            s.setdefault("image_prompt", s.get("text", ""))

        result = {
            "title": "Vox Storyboard Analysis (AI Generated)",
            "total_scenes": len(llm_scenes),
            "estimated_total_duration": round(total_duration, 2),
            "pacing": pacing,
            "provider_used": "llm",
            "narrative_summary": beats_count,
            "scenes": llm_scenes,
        }
        if offline_notes:
            result["provider_used"] = "llm_partial"
            result["fallback_reason"] = _offline_parts_reason(offline_notes, total_parts)
        return result

    # Layer 2: Offline High-Fidelity Semantic Parser
    offline = split_text_into_vox_scenes_offline(
        full_text=clean_text,
        pacing=pacing,
        max_words_per_scene=max_words_per_scene,
        style_preset=style_preset,
        character_anchor=character_anchor,
    )
    if provider != "offline":
        has_key = bool(analyzer.ninerouter_api_key or analyzer.gemini_api_key or analyzer.openrouter_api_key)
        offline["fallback_reason"] = _offline_fallback_reason(llm_failure, has_key)
    return offline


async def adapt_novel_chapter_to_us_podcast(
    novel_text: str,
    pacing: str = "fast",
    style_preset: str = "manga_murata_battle",
    target_character: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dedicated pipeline to adapt raw Light Novel chapters into high-retention US Podcast Storyboards.
    Generates captivating English audio script, 5s Hook, Murata/Spartan/Ink prompts, and camera movements.
    """
    analyzer = SemanticStoryAnalyzer()
    clean_text = novel_text.strip()
    if not clean_text:
        return {"title": "Empty Novel Text", "scenes": [], "total_scenes": 0}

    def offline_part(part: str) -> List[Dict[str, Any]]:
        return split_text_into_vox_scenes_offline(
            part, pacing=pacing, style_preset=style_preset, character_anchor=target_character,
        )["scenes"]

    # Chương chia phần nhỏ, gọi lần lượt; phần LLM không làm được thì chỉ phần đó chia offline
    scenes: List[Dict[str, Any]] = []
    offline_notes: List[Tuple[int, int, int, str]] = []
    ai_parts = total_parts = 0
    if analyzer.ninerouter_api_key:
        scenes, offline_notes, ai_parts, total_parts = await _scenes_in_parts(
            analyzer,
            clean_text,
            functools.partial(
                analyzer.call_9router_semantic_analyzer,
                pacing_name=pacing,
                style_preset=style_preset,
                is_novel=True,
            ),
            offline_part,
        )
    if not ai_parts:
        # Fallback to local splitter (chỉ dùng 9router nên chỉ key 9router mới tính)
        offline = split_text_into_vox_scenes_offline(
            clean_text,
            pacing=pacing,
            style_preset=style_preset,
            character_anchor=target_character,
        )
        offline["fallback_reason"] = _offline_fallback_reason(
            offline_notes[0][3] if offline_notes else "", bool(analyzer.ninerouter_api_key))
        return offline

    total_duration = sum(s.get("estimated_duration", 4.0) for s in scenes)
    result = {
        "title": "US Novel Podcast Storyboard",
        "total_scenes": len(scenes),
        "estimated_total_duration": round(total_duration, 2),
        "pacing": pacing,
        "style_preset": style_preset,
        "provider_used": "9router_gemini",
        "scenes": scenes,
    }
    if offline_notes:
        result["provider_used"] = "9router_gemini_partial"
        result["fallback_reason"] = _offline_parts_reason(offline_notes, total_parts)
    return result


def split_text_into_vox_scenes_offline(
    full_text: str,
    pacing: str = "fast",
    max_words_per_scene: Optional[int] = None,
    style_preset: str = "cinematic_realistic",
    character_anchor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Offline Semantic Story Analyzer (Layer 2).
    Zero-network dependency, instant execution, rich cinematic prompts.
    """
    analyzer = SemanticStoryAnalyzer()
    pacing_info = PACING_CONFIGS.get(pacing, PACING_CONFIGS["fast"])
    words_per_sec = pacing_info["words_per_second"]

    sentences = chunk_long_text_into_sentences(full_text)
    scene_texts = group_sentences_by_pacing(
        sentences,
        pacing_name=pacing,
        max_words_override=max_words_per_scene,
    )

    total_scenes = len(scene_texts)
    accumulated_duration = 0.0
    scenes_output = []
    beats_count: Dict[str, int] = {}

    for idx, text in enumerate(scene_texts, start=1):
        word_count = len(text.split())
        est_duration = max(3.0, round(word_count / words_per_sec, 2))

        # Classify Vox beat
        beat = analyzer.classify_narrative_beat(
            scene_text=text,
            scene_idx=idx,
            total_scenes=total_scenes,
            accumulated_seconds=accumulated_duration,
        )
        beats_count[beat] = beats_count.get(beat, 0) + 1

        # Extract semantic layers
        semantics = analyzer.extract_semantic_layers_rule_based(
            scene_text=text,
            scene_idx=idx,
            narrative_beat=beat,
        )

        # Build English cinematic prompt
        image_prompt = analyzer.build_cinematic_english_prompt(
            semantics=semantics,
            narrative_beat=beat,
            style_preset=style_preset,
            character_anchor=character_anchor,
        )

        scene_dict = {
            "order": idx,
            "text": text,
            "narrative_beat": beat,
            "estimated_duration": est_duration,
            "setting": semantics["setting"],
            "subject": semantics["subject"],
            "emotion": semantics["emotion"],
            "action": semantics["action"],
            "lighting": semantics["lighting"],
            "camera_framing": semantics["framing"],
            "camera_motion": semantics["camera_motion"],
            "image_prompt": image_prompt,
        }
        scenes_output.append(scene_dict)
        accumulated_duration += est_duration

    return {
        "title": "Vox Storyboard Analysis (Semantic Offline Engine)",
        "total_scenes": total_scenes,
        "estimated_total_duration": round(accumulated_duration, 2),
        "pacing": pacing,
        "provider_used": "offline_semantic_rules",
        "narrative_summary": beats_count,
        "scenes": scenes_output,
    }


def split_text_into_scenes(
    full_text: str,
    max_words_per_scene: int = 30,
    language: str = "vi",
    pacing: str = "fast",
    style_preset: str = "cinematic_realistic",
    character_anchor: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Backwards-compatible drop-in replacement for legacy split_text_into_scenes.
    Directly uses the Vox Narrative Engine and Semantic Story Analyzer.
    """
    # Map max_words_per_scene to pacing if appropriate
    pacing_to_use = pacing
    if max_words_per_scene <= 14:
        pacing_to_use = "fast"
    elif max_words_per_scene <= 22:
        pacing_to_use = "balanced"
    elif max_words_per_scene >= 23:
        pacing_to_use = "deep_story"

    result = split_text_into_vox_scenes_offline(
        full_text=full_text,
        pacing=pacing_to_use,
        max_words_per_scene=max_words_per_scene,
        style_preset=style_preset,
        character_anchor=character_anchor,
    )

    # Convert to the flat scene dictionary expected by existing callers
    legacy_scenes = []
    from services.audio_engine import auto_detect_scene_sfx
    for sc in result["scenes"]:
        sfx_cues = auto_detect_scene_sfx(sc.get("text", ""), sc.get("image_prompt", ""))
        legacy_scenes.append({
            "order": sc["order"],
            "text": sc["text"],
            "image_prompt": sc["image_prompt"],
            "camera_motion": sc["camera_motion"],
            "narrative_beat": sc["narrative_beat"],
            "estimated_duration": sc["estimated_duration"],
            "setting": sc["setting"],
            "subject": sc["subject"],
            "emotion": sc["emotion"],
            "action": sc["action"],
            "lighting": sc["lighting"],
            "camera_framing": sc["camera_framing"],
            "sfx_cue": sfx_cues,
        })

    return legacy_scenes
