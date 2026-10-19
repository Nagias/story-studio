"""
Master Storyboard Deconstructor Engine
---------------------------------------
Compliant with OP_CTOOL Master Specification:
Translates raw text/script into validated Master Storyboard JSON with:
1. Visual Style DNA & Character Anchors.
2. 9-Grid Composite Batching (sequential narrative sheet 3x3).
3. 3-Layer Audio Design (Voiceover + SFX cues + BGM Energy).
4. Dramatic Pacing (pause_after_sec 0.3s - 2.0s).
5. 2.5D Parallax layering hints.
6. Kinetic subtitle highlight keywords.
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional

import httpx

from config import (
    NINEROUTER_BASE_URL,
    NINEROUTER_API_KEY,
    NINEROUTER_LLM_MODEL,
)
from models.schemas import (
    MasterStoryboard,
    ProjectMetadata,
    MasterScene,
    MasterAudio,
    MasterSoundDesign,
    MasterVisual,
    MasterSubtitles,
    ParallaxMotion,
    CharacterAnchor,
)

logger = logging.getLogger("story_studio.storyboard_engine")

MASTER_SYSTEM_PROMPT = """BẠN LÀ TỔNG ĐẠO DIỄN VÀ NHÀ THIẾT KẾ PHÂN CẢNH ĐIỆN ẢNH (CHIEF FILM DIRECTOR & AUDIO-VISUAL ARCHITECT).
NHIỆM VỤ: Chuyển thể văn bản kịch bản thô thành một Bảng Phân Cảnh JSON (Master Storyboard) chuẩn xác tuyệt đối để hệ thống máy tính tự động dựng thành video YouTube đạt chuẩn điện ảnh.

QUY TẮC BẮT BUỘC (THE 5 COMMANDMENTS):
1. KHÓA TÍNH NHẤT QUÁN & CHIẾN LƯỢC 9-GRID SLICING (VŨ KHÍ BÍ TRUYỀN):
   - Phải xác lập một DNA phong cách duy nhất cho toàn bộ video (visual_style_dna).
   - Nếu có nhân vật, phải tạo một "Character Anchor Prompt" chi tiết (tuổi tác, kiểu tóc, đặc điểm mặt, trang phục, màu sắc). Mọi cảnh có nhân vật này PHẢI bắt đầu bằng Character Anchor đó.
   - Cơ chế 9-Grid Batching: Khi các phân cảnh diễn ra liên tiếp trong cùng một diễn biến/bối cảnh, LLM PHẢI gom tối đa 9 cảnh liên tiếp vào cùng một nhóm (grid_batch_id) và tạo một câu lệnh ma trận tổng hợp grid_composite_prompt_en dạng 3x3 (9-grid storyboard sequence: panel 1 [hành động 1], panel 2 [hành động 2]... panel 9 [hành động 9]). Hệ thống máy tính sẽ sinh 1 ảnh lớn và tự động cắt thành 9 khung hình con riêng biệt, đảm bảo tuyệt đối không bị đổi mặt nhân vật.
2. THIẾT KẾ ÂM THANH 3 LỚP (3-LAYER SOUND DESIGN):
   - Mỗi cảnh phải có: Giọng đọc (Voice), Hiệu ứng âm thanh cụ thể (sfx_cue - ví dụ: clock_ticking, heavy_rain, thunder_crack, heartbeat), và Tâm trạng nhạc nền (bgm_energy).
3. ĐIỀU PHỐI NHỊP THỞ KỊCH TÍNH (DRAMATIC PACING):
   - Tuyệt đối không để kịch bản đọc liên tục không ngắt. Hãy đặt 'pause_after_sec' từ 0.3s (câu thông thường) đến 1.5s - 2.0s (sau câu hỏi tu từ, cao trào, hoặc tiết lộ plot-twist).
4. NGÔN NGỮ ỐNG KÍNH ĐIỆN ẢNH (CINEMATIC SHOT LANGUAGE):
   - 'image_prompt_en' phải viết bằng tiếng Anh chuẩn ngành: Cỡ cảnh (Wide angle, Close-up, Dutch angle), Tiêu cự (35mm lens, 85mm portrait), Ánh sáng (Volumetric rim lighting, Moody chiaroscuro, Neo-noir wet reflections).
5. ĐỊNH DẠNG ĐẦU RA:
   - CHỈ TRẢ VỀ DUY NHẤT MỘT KHỐI JSON HỢP LỆ THEO SCHEMA BÊN DƯỚI. KHÔNG VIẾT LỜI DẪN, KHÔNG BỌC VĂN BẢN NGOÀI JSON.

SCHEMA JSON BẮT BUỘC:
{
  "project_metadata": {
    "title": "string (Tiêu đề video tối ưu CTR YouTube)",
    "target_aspect_ratio": "16:9",
    "visual_style_dna": "string (Chuỗi prompt định hình ánh sáng và màu sắc toàn bộ phim)",
    "character_anchors": [
      {
        "character_name": "string",
        "visual_prompt_anchor": "string (Prompt tiếng Anh cố định nhận dạng)"
      }
    ],
    "bgm_overall_genre": "string (Ví dụ: Cinematic Dark Ambient, Investigative Cello)"
  },
  "scenes": [
    {
      "scene_id": 1,
      "estimated_duration_sec": 5.5,
      "audio": {
        "speaker": "narrator | character_name",
        "voice_emotion": "calm | tense | mysterious | aggressive | sorrowful",
        "voiceover_text": "string (Câu thoại tiếng Việt)",
        "pause_after_sec": 0.8
      },
      "sound_design": {
        "sfx_cue": ["string (Tên hiệu ứng âm thanh cụ thể)"],
        "bgm_energy": "ambient_low | tension_buildup | dramatic_climax"
      },
      "visual": {
        "generation_mode": "9_grid_composite | single_shot",
        "grid_batch_id": "batch_01 (nếu chọn 9_grid_composite)",
        "grid_cell_index": 0,
        "grid_composite_prompt_en": "string (Prompt 9-grid ma trận đầy đủ cho cả batch 9 ô)",
        "shot_type": "Establishing Wide Shot | Medium Shot | Macro Close-Up | Low Angle Hero Shot",
        "camera_movement": "Slow continuous zoom-in 1.05x | Left-to-right slow pan",
        "image_prompt_en": "string (Prompt chi tiết tiếng Anh của riêng cảnh/ô này)",
        "parallax_motion": {
          "enable": true,
          "foreground_subject": "string",
          "background_scene": "string"
        }
      },
      "subtitles": {
        "kinetic_highlight_words": ["string (Các từ then chốt cần làm nổi bật trên màn hình)"]
      }
    }
  ]
}"""

def _clean_json_response(raw_text: str) -> str:
    """Strip markdown code fence wrappers and extract pure JSON substring."""
    cleaned = raw_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    # Find matching first { and last }
    s = cleaned.find("{")
    e = cleaned.rfind("}")
    if s != -1 and e != -1 and e > s:
        cleaned = cleaned[s : e + 1]
    return cleaned

def deconstruct_script_offline(
    raw_text: str,
    art_style: str = "Dark moody cinematic neo-noir, 35mm anamorphic film grain",
    tone_and_mood: str = "tense_suspense",
    batch_9_grid: bool = True,
) -> MasterStoryboard:
    """
    High-precision deterministic offline parser for Master Storyboard.
    Deconstructs raw script into scenes, organizes into 9-grid batches, assigns 3-layer audio
    and cinematic camera movements without requiring external API access.
    """
    # Clean and split into sentences / narrative units
    raw_lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    full_text = " ".join(raw_lines)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", full_text) if len(s.strip()) > 5]
    if not sentences:
        sentences = [raw_text.strip() or "Cơn mưa rào trút xuống màn đêm tĩnh mịch."]

    # Derive title
    title = sentences[0][:60] + "..." if len(sentences[0]) > 60 else sentences[0]
    title = re.sub(r"[.!?…]+$", "", title)

    # Character detection
    char_match = re.search(r"\b(Nam|Huy|Minh|Linh|Lan|Mai|Tuấn|Hùng|Thám tử|Chiến binh)\b", full_text, re.I)
    char_name = char_match.group(1).capitalize() if char_match else "Detective"
    char_anchor = (
        f"35-year-old Asian detective {char_name}, rugged sharp facial features, "
        "tired intense eyes, wearing a dark worn charcoal trench coat over a black sweater"
    )

    metadata = ProjectMetadata(
        title=f"Bí Ẩn: {title}",
        target_aspect_ratio="16:9",
        visual_style_dna=art_style,
        character_anchors=[
            CharacterAnchor(character_name=char_name, visual_prompt_anchor=char_anchor)
        ],
        bgm_overall_genre="Cinematic Dark Ambient Cello & Muffled Piano",
    )

    scenes: List[MasterScene] = []
    total = len(sentences)

    for i, sent in enumerate(sentences):
        scene_id = i + 1
        is_question = bool(re.search(r"\?|tại sao|liệu|ai|đâu", sent, re.I))
        is_climax = bool(re.search(r"!|bất ngờ|kinh hoàng|xé toạc|nhấp nháy|máu|chết", sent, re.I))

        # Dynamic pause calculation (Dramatic Pacing)
        if is_question:
            pause_sec = 1.4
            bgm_energy = "tension_buildup"
            emotion = "mysterious"
        elif is_climax:
            pause_sec = 1.8
            bgm_energy = "dramatic_climax"
            emotion = "tense"
        else:
            pause_sec = 0.8
            bgm_energy = "ambient_low" if i < 2 else "tension_buildup"
            emotion = "calm"

        # SFX mapping based on Vietnamese keywords
        sfx_list = []
        if re.search(r"mưa|sấm|gió|bão", sent, re.I):
            sfx_list.append("heavy_rain_loop")
        if re.search(r"cổng|cửa|kẽo kẹt", sent, re.I):
            sfx_list.append("rusty_iron_gate_creak")
        if re.search(r"tim|hồi hộp|sợ|thở", sent, re.I):
            sfx_list.append("heartbeat_single_pulse")
        if re.search(r"bước|chân|đường", sent, re.I):
            sfx_list.append("wet_footsteps_gravel")
        if not sfx_list:
            sfx_list.append("clock_ticking" if i % 2 == 0 else "distant_thunder_subtle")

        # Visual 9-Grid batching logic
        if batch_9_grid and total >= 3:
            gen_mode = "9_grid_composite" if i > 0 else "single_shot"
            batch_id = f"batch_sequence_{i // 9 + 1:02d}" if gen_mode == "9_grid_composite" else None
            cell_idx = (i - 1) % 9 if gen_mode == "9_grid_composite" else None
        else:
            gen_mode = "single_shot"
            batch_id = None
            cell_idx = None

        shot_types = [
            "Establishing Wide Shot",
            "Medium Dutch Angle Shot",
            "Macro Close-Up",
            "Low Angle Hero Shot",
            "Over-the-shoulder Shot",
        ]
        shot_type = shot_types[i % len(shot_types)]

        camera_motions = [
            "Slow continuous zoom-in 1.05x",
            "Left-to-right slow pan",
            "Slow crane-down",
            "Creeping push-in 1.08x",
        ]
        cam_motion = camera_motions[i % len(camera_motions)]

        # Highlight words (Kinetic Subtitles)
        words = sent.split()
        kw = [w.strip(",.!?") for w in words if len(w) > 4][:2]
        if not kw and words:
            kw = [words[0].strip(",.!?")]

        single_prompt = (
            f"{shot_type} of {char_name} in {art_style}, dramatic lighting, "
            f"35mm film still, photorealistic cinematic 8k --ar 16:9"
        )
        composite_prompt = (
            f"9-grid storyboard sequence, sequential narrative sheet, {char_anchor}, "
            f"{art_style}, 9 continuous cinematic panels, unified art style --ar 16:9"
        ) if gen_mode == "9_grid_composite" else None

        sc_obj = MasterScene(
            scene_id=scene_id,
            estimated_duration_sec=round(max(3.5, len(sent.split()) * 0.32 + pause_sec), 1),
            audio=MasterAudio(
                speaker="narrator" if i % 3 != 1 else char_name,
                voice_emotion=emotion,
                voiceover_text=sent,
                pause_after_sec=pause_sec,
            ),
            sound_design=MasterSoundDesign(
                sfx_cue=sfx_list,
                bgm_energy=bgm_energy,
            ),
            visual=MasterVisual(
                generation_mode=gen_mode,
                grid_batch_id=batch_id,
                grid_cell_index=cell_idx,
                grid_composite_prompt_en=composite_prompt,
                shot_type=shot_type,
                camera_movement=cam_motion,
                image_prompt_en=single_prompt,
                parallax_motion=ParallaxMotion(
                    enable=True,
                    foreground_subject=f"Silhouette of {char_name}",
                    background_scene="Cinematic atmospheric moody backdrop",
                ),
            ),
            subtitles=MasterSubtitles(
                kinetic_highlight_words=kw,
            ),
        )
        scenes.append(sc_obj)

    return MasterStoryboard(
        project_metadata=metadata,
        scenes=scenes,
    )

async def deconstruct_script_async(
    raw_text: str,
    art_style: str = "Dark moody cinematic neo-noir, 35mm anamorphic film grain",
    tone_and_mood: str = "tense_suspense",
    batch_9_grid: bool = True,
    provider: str = "auto",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
) -> MasterStoryboard:
    """
    Deconstructs raw script via LLM with strict Master System Prompt and Pydantic validation.
    Falls back reliably to offline deterministic deconstruction if LLM call fails.
    """
    if provider == "offline":
        return deconstruct_script_offline(raw_text, art_style, tone_and_mood, batch_9_grid)

    active_base_url = (base_url or NINEROUTER_BASE_URL).rstrip("/")
    active_key = api_key or NINEROUTER_API_KEY
    active_model = model_name or NINEROUTER_LLM_MODEL

    user_prompt = f"""KỊCH BẢN ĐẦU VÀO:
\"\"\"
{raw_text.strip()}
\"\"\"

YÊU CẦU ĐẶC TẢ:
- Phong cách hình ảnh (Visual Style DNA): {art_style}
- Tông điệu & Cảm xúc (Tone & Mood): {tone_and_mood}
- Chế độ 9-Grid Batching: {'BẮT BUỘC gom các phân cảnh liên tục thành batch 9-grid 3x3' if batch_9_grid else 'Tự do'}

Hãy phân tích và xuất toàn bộ Master Storyboard dưới định dạng JSON duy nhất tuân thủ 100% schema đã quy định."""

    try:
        headers = {
            "Authorization": f"Bearer {active_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": active_model,
            "messages": [
                {"role": "system", "content": MASTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{active_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                clean_json = _clean_json_response(content)
                parsed = MasterStoryboard.model_validate_json(clean_json)
                logger.info(f"LLM successfully generated Master Storyboard with {len(parsed.scenes)} scenes.")
                return parsed
            else:
                logger.warning(f"LLM API returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"LLM deconstruct failed ({e}), using offline deterministic engine.")

    return deconstruct_script_offline(raw_text, art_style, tone_and_mood, batch_9_grid)
