from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from models.youtube_seo import YoutubeSeoState

class Scene(BaseModel):
    id: str
    order: int
    text: str
    image_prompt: str = ""
    video_prompt: Optional[str] = ""
    camera_motion: str = "zoom_in"  # zoom_in, zoom_out, pan_left, pan_right, static, random
    style_override: Optional[str] = None
    voice_audio_path: Optional[str] = None
    voice_audio_url: Optional[str] = None
    audio_url: Optional[str] = None
    audio_path: Optional[str] = None
    duration: Optional[float] = None  # in seconds
    srt_path: Optional[str] = None
    srt_url: Optional[str] = None
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    video_segment_path: Optional[str] = None
    video_segment_url: Optional[str] = None
    video_url: Optional[str] = None
    # Clip chuyển động gốc (Muse image-to-video hoặc video tải lên). Khác với video_segment_path,
    # là đoạn đã dựng kèm giọng đọc và bị ghi lại mỗi lần render.
    motion_video_path: Optional[str] = None
    media_view_mode: Optional[str] = "image"  # "image" | "video"
    status: str = "draft"  # draft, voiced, imaged, ready, error
    status_image: Optional[str] = "idle"
    status_voice: Optional[str] = "idle"
    status_video: Optional[str] = "idle"
    # Master Storyboard & 3-Layer Audio Extensions
    speaker: Optional[str] = "narrator"
    voice_emotion: Optional[str] = "calm"
    pause_after_sec: float = 0.8
    sfx_cue: List[str] = Field(default_factory=list)
    bgm_energy: str = "ambient_low"  # ambient_low, tension_buildup, dramatic_climax
    # 9-Grid Composite & Parallax Extensions
    generation_mode: str = "single_shot"  # single_shot, 9_grid_composite
    grid_batch_id: Optional[str] = None
    grid_cell_index: Optional[int] = None
    grid_composite_prompt_en: Optional[str] = None
    shot_type: Optional[str] = None
    parallax_motion: Optional[Dict[str, Any]] = None
    foreground_image_path: Optional[str] = None
    background_image_path: Optional[str] = None
    kinetic_highlight_words: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

# ----------------- CHARACTER CONSISTENCY MODELS -----------------

class Character(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    face_features: str
    hair_style_and_color: str
    armor_or_costume: str
    main_weapon: str
    signature_colors: str
    distinguishing_marks: str
    full_anchor_prompt: Optional[str] = None
    avatar_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    def generate_anchor_prompt(self) -> str:
        """Compose a unified, robust prompt segment for character consistency."""
        parts = [
            f"character {self.name}",
            self.face_features,
            self.hair_style_and_color,
            f"wearing {self.armor_or_costume}",
            f"wielding {self.main_weapon}",
            f"signature colors: {self.signature_colors}",
            f"distinctive details: {self.distinguishing_marks}",
        ]
        return ", ".join([p.strip() for p in parts if p.strip()])

PRESET_CHARACTERS: List[Character] = [
    Character(
        id="paladin_kai",
        name="Dũng Sĩ Kai (Silver & Cyan Paladin)",
        description="Dũng sĩ giáp bạc ngọc lam, áo choàng đỏ rực, chuôi kiếm vàng chạm khắc phong cách anime điện ảnh / Light Novel Nhật Bản (Fate/Grand Order, Granblue Fantasy).",
        face_features="handsome youthful anime protagonist face, sharp resolute blue eyes, determined heroic expression, clear skin",
        hair_style_and_color="spiky layered silver-white hair with a stray lock falling over forehead",
        armor_or_costume="ornate polished silver full plate armor inlaid with glowing cyan turquoise gemstones, flowing crimson scarlet velvet cape",
        main_weapon="legendary two-handed broadsword with an intricately carved gold hilt and glowing runic blade",
        signature_colors="gleaming silver, luminous cyan turquoise, crimson scarlet red, regal gold",
        distinguishing_marks="a faint glowing blue magical crest engraved on his silver breastplate, immaculate battle-ready posture",
        tags=["anime", "fantasy", "paladin", "light_novel"],
    ),
    Character(
        id="roman_titus",
        name="Binh Sĩ La Mã Titus (Roman Legionary)",
        description="Chiến binh La Mã cổ đại trong bão cát, khiên đỏ scutum vẽ bò tót, mũ đồng có bờm đỏ, ngọn lao pilum, nét vẽ sơn dầu lịch sử chân thực.",
        face_features="rugged sun-weathered Roman soldier face, stern gaze, strong square jaw with light battle stubble and scar",
        hair_style_and_color="short cropped Roman military haircut, dark brown hair",
        armor_or_costume="authentic lorica segmentata iron banded armor over crimson red tunic, brass buckles, heavy pteruges leather skirt",
        main_weapon="heavy iron-tipped pilum javelin held firmly, sheathed gladius short sword on right hip, large curved rectangular red scutum shield painted with a golden charging bull emblem",
        signature_colors="crimson imperial red, rusted iron, tarnished brass, desert sand gold",
        distinguishing_marks="polished bronze galea helmet crowned with a transverse crimson horsehair crest, grit and sand dust clinging to armor",
        tags=["historical", "roman", "warfare", "oil_painting"],
    ),
    Character(
        id="spartan_leon",
        name="Chiến Binh Sparta Leon (Hoplite Champion)",
        description="Chiến binh Sparta Hy Lạp, giáp ngực đồng cơ bắp, mũ Corinthian bờm lông ngựa, khiên tròn hoplon chạm khắc, ánh sáng vàng sử thi (Achilles/Leonidas).",
        face_features="fierce chiseled ancient Greek warrior face, intense unwavering battle-hardened glare, trimmed dark beard",
        hair_style_and_color="long thick dark warrior hair braided under helmet",
        armor_or_costume="anatomically sculpted bronze muscle cuirass gleaming under harsh sunlight, crimson hoplite mantle draped over one shoulder, bronze greaves on shins",
        main_weapon="heavy ash-wood dory spear with bronze spearhead, large circular bronze hoplon shield embossed with sacred chevron Lambda symbol",
        signature_colors="burnished antique bronze, deep crimson red, rich antique gold, deep shadow black",
        distinguishing_marks="full bronze Corinthian helmet with towering black and red horsehair plume casting dramatic shadow over upper face",
        tags=["greek", "spartan", "mythic", "ancient"],
    ),
    Character(
        id="murata_fighter",
        name="Võ Giả Cuồng Nộ (Murata Martial Fighter)",
        description="Võ giả shonen phong cách Murata / One Punch Man, cơ bắp cuồn cuộn gân guốc, trang phục võ thuật xé rách trong trận đại chiến, nắm đấm rực lửa phát sáng.",
        face_features="intense battle-hardened glare, clenched teeth, sharp furrowed brow, sweat and battle smudges",
        hair_style_and_color="spiky wild jet-black hair with dynamic wind motion",
        armor_or_costume="tattered dark martial arts dogi gi pants tied with black sash, bare athletic muscular chest and scarred arms wrapped in white combat tape",
        main_weapon="bare fists enveloped in radiant fiery red kinetic shockwave energy, glowing knuckles",
        signature_colors="deep ink black, crisp paper white, explosive crimson red energy glow",
        distinguishing_marks="extreme shonen battle screentone crosshatching, explosive shockwave aura, dynamic foreshortening",
        tags=["manga", "battle", "shonen", "murata", "action"],
    ),
    Character(
        id="kingdom_shin",
        name="Tướng Quân Shin (Kingdom)",
        description="Tướng quân trẻ thời Chiến Quốc phong cách manga Kingdom (Yasuhisa Hara): giáp vảy lam nhạt, tóc đuôi ngựa đen rối, đại kiếm vác sau lưng, nụ cười ngạo nghễ giữa chiến trường.",
        face_features="young fierce warrior general face, sharp determined eyes, confident battle smirk, small scar on cheek",
        hair_style_and_color="messy spiky black hair tied in a rough high ponytail",
        armor_or_costume="pale blue scale lamellar armor over a dark battle robe, worn leather bracers and belt",
        main_weapon="massive broadsword carried on his back, heavy tasseled war blade",
        signature_colors="pale steel blue, ink black, battlefield dust brown",
        distinguishing_marks="tattered pale blue scarf streaming in the wind, unbreakable fighting spirit aura",
        tags=["manga", "historical", "war", "kingdom"],
    ),
]

PRESET_CHARACTERS_MAP: Dict[str, Character] = {c.id: c for c in PRESET_CHARACTERS}

def get_preset_characters() -> List[Character]:
    """Return all pre-configured master consistency character templates."""
    return PRESET_CHARACTERS

def get_preset_character_by_id(char_id: str) -> Optional[Character]:
    """Retrieve a pre-configured character template by ID."""
    return PRESET_CHARACTERS_MAP.get(char_id)

class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    voice: str = "vi-VN-HoaiMyNeural"
    voice_rate: str = "+0%"
    voice_pitch: str = "+0Hz"
    style_preset: str = "cinematic_realistic"
    character_anchor: str = ""
    character: Optional[Character] = None
    character_reference_image: Optional[str] = None
    bgm_track: Optional[str] = "ambient_peaceful"
    bgm_volume: float = 0.2
    ducking: bool = True
    hardsub: bool = True
    resolution: str = "1080p"  # 1080p (1920x1080) or 720p (1280x720)
    fps: int = 25
    default_motion: str = "zoom_in"
    transition: Optional[str] = "dip_to_black"  # dip_to_black, crossfade, cut, flash_white, wipe_left
    subtitle_style: Optional[str] = "kinetic_pop"  # kinetic_pop, karaoke_sweep, classic
    image_provider: str = "9router_gemini"  # 9router_gemini, pollinations, api, mock_cinematic
    # Master Storyboard additions
    visual_style_dna: Optional[str] = None
    bgm_overall_genre: Optional[str] = None
    target_aspect_ratio: str = "16:9"
    grid_batches: Dict[str, Any] = Field(default_factory=dict)
    scenes: List[Scene] = Field(default_factory=list)
    final_video_path: Optional[str] = None
    final_video_url: Optional[str] = None
    thumbnail_path: Optional[str] = None
    thumbnail_url: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_tags: List[str] = Field(default_factory=list)
    # Gói SEO YouTube (từ khoá thật + gói đã kiểm luật); chỉ services/youtube_seo_pack.py ghi
    youtube_seo: Optional[YoutubeSeoState] = None
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # Tuỳ chọn của giao diện (bgm, ducking, hardsub, nhân vật dạng giao diện...). Bước dựng
    # dùng các trường thật ở trên (bgm_track, ducking, hardsub...), giao diện ghi cả hai.
    settings: Dict[str, Any] = Field(default_factory=dict)

# Request Models
class ProjectCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    voice: Optional[str] = None  # None: dùng config.DEFAULT_VOICE
    style_preset: Optional[str] = "manga_murata_battle"
    character_anchor: Optional[str] = ""
    character: Optional[Character] = None
    character_preset_id: Optional[str] = None
    character_reference_image: Optional[str] = None
    image_provider: Optional[str] = "meta_muse_cloud"

class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    voice: Optional[str] = None
    voice_rate: Optional[str] = None
    voice_pitch: Optional[str] = None
    style_preset: Optional[str] = None
    character_anchor: Optional[str] = None
    character: Optional[Character] = None
    character_preset_id: Optional[str] = None
    character_reference_image: Optional[str] = None
    bgm_track: Optional[str] = None
    bgm_volume: Optional[float] = None
    ducking: Optional[bool] = None
    hardsub: Optional[bool] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    default_motion: Optional[str] = None
    transition: Optional[str] = None
    subtitle_style: Optional[str] = None
    image_provider: Optional[str] = None
    scenes: Optional[List[Scene]] = None
    thumbnail_path: Optional[str] = None
    thumbnail_url: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_tags: Optional[List[str]] = None
    settings: Optional[Dict[str, Any]] = None

class SceneCreateRequest(BaseModel):
    text: str
    image_prompt: Optional[str] = ""
    video_prompt: Optional[str] = ""
    camera_motion: Optional[str] = "zoom_in"
    style_override: Optional[str] = None
    sfx_cue: Optional[List[str]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class SceneUpdateRequest(BaseModel):
    text: Optional[str] = None
    image_prompt: Optional[str] = None
    video_prompt: Optional[str] = None
    camera_motion: Optional[str] = None
    style_override: Optional[str] = None
    sfx_cue: Optional[List[str]] = None
    status: Optional[str] = None
    status_image: Optional[str] = None
    status_video: Optional[str] = None
    image_url: Optional[str] = None
    video_segment_url: Optional[str] = None
    video_url: Optional[str] = None
    media_view_mode: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class ReorderScenesRequest(BaseModel):
    scene_ids: List[str]

class SplitScriptRequest(BaseModel):
    text: str
    max_words_per_scene: Optional[int] = 30
    language: Optional[str] = "vi"
    pacing: Optional[str] = "fast"  # fast (3-4s/vox), balanced (5-6s), deep_story (7-8s)
    style_preset: Optional[str] = "cinematic_realistic"
    character_anchor: Optional[str] = None
    character: Optional[Character] = None
    character_preset_id: Optional[str] = None
    provider: Optional[str] = "auto"  # auto, gemini, openrouter, offline
    api_key: Optional[str] = None

class VoxScene(BaseModel):
    order: int
    text: str
    narrative_beat: str = "setting"  # hook, setting, escalation, climax, resolution
    estimated_duration: float = 4.0
    setting: Optional[str] = ""
    subject: Optional[str] = ""
    emotion: Optional[str] = ""
    action: Optional[str] = ""
    lighting: Optional[str] = ""
    camera_framing: Optional[str] = "cinematic medium shot"
    camera_motion: Optional[str] = "zoom_in"
    image_prompt: str = ""

class VoxScriptAnalysisRequest(BaseModel):
    text: str
    pacing: Optional[str] = "fast"  # fast (3-4s), balanced (5-6s), deep_story (7-8s)
    max_words_per_scene: Optional[int] = None
    style_preset: Optional[str] = "cinematic_realistic"
    character_anchor: Optional[str] = None
    character: Optional[Character] = None
    character_preset_id: Optional[str] = None
    api_key: Optional[str] = None
    provider: Optional[str] = "auto"  # auto, gemini, openrouter, offline
    model_name: Optional[str] = None

class VoxScriptAnalysisResponse(BaseModel):
    title: str
    total_scenes: int
    estimated_total_duration: float
    pacing: str
    provider_used: str
    narrative_summary: Dict[str, int]
    scenes: List[VoxScene]
    # Có giá trị khi LLM lỗi và cảnh do bộ chia offline tạo (prompt ảnh là mẫu chung)
    fallback_reason: Optional[str] = None

class VoxProjectScriptRequest(BaseModel):
    text: str
    pacing: Optional[str] = "fast"
    max_words_per_scene: Optional[int] = None
    style_preset: Optional[str] = None
    character_anchor: Optional[str] = None
    character: Optional[Character] = None
    character_preset_id: Optional[str] = None
    api_key: Optional[str] = None
    provider: Optional[str] = "auto"
    model_name: Optional[str] = None
    replace_existing: Optional[bool] = False

class VoiceGenRequest(BaseModel):
    text: Optional[str] = None
    voice: Optional[str] = None
    rate: Optional[str] = None
    pitch: Optional[str] = None

class ImageGenRequest(BaseModel):
    prompt: Optional[str] = None
    style: Optional[str] = None
    provider: Optional[str] = None
    seed: Optional[int] = None
    consistency: Optional[Dict[str, Any]] = None
    character_anchor: Optional[str] = None
    character: Optional[Character] = None
    character_preset_id: Optional[str] = None
    reference_image: Optional[str] = None
    character_reference_image: Optional[str] = None
    project_id: Optional[str] = None
    scene_id: Optional[str] = None
    scene_index: Optional[int] = None

class NovelIngestRequest(BaseModel):
    novel_text: str
    pacing: Optional[str] = "fast"
    style_preset: Optional[str] = "manga_murata_battle"
    voice: Optional[str] = "en-US-GuyNeural"
    target_character: Optional[str] = None
    project_id: Optional[str] = None
    create_new_project: Optional[bool] = True
    project_title: Optional[str] = None

class RenderRequest(BaseModel):
    resolution: Optional[str] = "1080p"
    ducking: Optional[bool] = True
    hardsub: Optional[bool] = True
    subtitle_style: Optional[str] = "kinetic_pop"  # kinetic_pop, karaoke_sweep, classic
    bgm: Optional[str] = "ambient_peaceful"
    bgm_volume: Optional[float] = 0.2
    fps: Optional[int] = 25
    camera_motion: Optional[str] = None
    transition: Optional[str] = "dip_to_black"  # dip_to_black, crossfade, cut, flash_white, wipe_left

class RenderStatusResponse(BaseModel):
    render_id: str
    project_id: str
    status: str  # idle, queued, rendering, completed, failed
    progress: int  # 0 to 100
    step: int  # 1 to 5
    step_label: str
    logs: List[str] = Field(default_factory=list)
    video_url: Optional[str] = None
    video_path: Optional[str] = None
    srt_url: Optional[str] = None
    srt_path: Optional[str] = None
    ass_url: Optional[str] = None
    ass_path: Optional[str] = None
    error: Optional[str] = None

class LongVideoProduceRequest(BaseModel):
    text: Optional[str] = None
    pacing: Optional[str] = "fast"
    style_preset: Optional[str] = None
    character_anchor: Optional[str] = None
    character_reference_image: Optional[str] = None
    reference_image: Optional[str] = None
    voice: Optional[str] = None
    voice_rate: Optional[str] = "+0%"
    voice_pitch: Optional[str] = "+0Hz"
    bgm: Optional[str] = "ambient_peaceful"
    bgm_volume: Optional[float] = 0.2
    ducking: Optional[bool] = True
    hardsub: Optional[bool] = True
    subtitle_style: Optional[str] = "kinetic_pop"
    resolution: Optional[str] = "1080p"
    fps: Optional[int] = 25
    camera_motion: Optional[str] = None
    transition: Optional[str] = "dip_to_black"
    # None = giữ provider đã chọn của dự án (trước đây mặc định "9router_gemini" ghi đè ngầm lựa chọn Muse/mock)
    image_provider: Optional[str] = None


class OpenFolderRequest(BaseModel):
    path: Optional[str] = None
    project_id: Optional[str] = None

# Comic / Manga / Webtoon Slicer Models
class ComicPanelBBox(BaseModel):
    x: int
    y: int
    width: int
    height: int

class ComicPanelSlice(BaseModel):
    id: str
    index: int
    bbox: ComicPanelBBox
    aspect_ratio: float
    camera_motion: str  # pan_left, pan_right, zoom_in
    width: int
    height: int
    is_wide: bool = False
    image_path: str
    image_url: str
    selected: bool = True
    custom_text: Optional[str] = None

class ComicSliceResponse(BaseModel):
    success: bool
    mode: str  # grid, strip
    reading_order: str  # ltr, rtl
    total_panels: int
    source_dimensions: Dict[str, int]
    panels: List[ComicPanelSlice]
    annotated_preview_url: Optional[str] = None
    annotated_preview_path: Optional[str] = None

class ComicImportRequest(BaseModel):
    panels: List[Dict[str, Any]]
    clear_existing: bool = False
    text_prefix: Optional[str] = "Khung tranh"

class CreateProjectFromScriptRequest(BaseModel):
    name: Optional[str] = None
    text: str
    pacing: Optional[str] = "fast"
    style_preset: Optional[str] = "manga_murata_battle"
    character_preset_id: Optional[str] = None
    character_anchor: Optional[str] = ""
    character_reference_image: Optional[str] = None
    voice: Optional[str] = None  # None: giọng mặc định theo ngôn ngữ truyện
    image_provider: Optional[str] = "meta_muse_cloud"
    generate_initial_images: Optional[bool] = True
    # Ngôn ngữ lời review: "vi" | "en"; None = theo ngôn ngữ truyện (CLAUDE.md mục 1.2 câu 15)
    output_language: Optional[str] = None
    # Mã do giao diện tạo để hỏi tiến độ trong lúc server viết từng phần (GET .../create-from-script/progress/{id})
    progress_id: Optional[str] = None

# ==============================================================================
# MASTER STORYBOARD SPEC MODELS (OP_CTOOL SPEC COMPLIANT)
# ==============================================================================

class CharacterAnchor(BaseModel):
    character_name: str
    visual_prompt_anchor: str

class ProjectMetadata(BaseModel):
    title: str = "Tác Phẩm Storyboard Điện Ảnh"
    target_aspect_ratio: str = "16:9"
    visual_style_dna: str = "Dark moody cinematic neo-noir, 35mm anamorphic film grain"
    character_anchors: List[CharacterAnchor] = Field(default_factory=list)
    bgm_overall_genre: str = "Cinematic Dark Ambient Cello & Muffled Piano"

class MasterAudio(BaseModel):
    speaker: str = "narrator"
    voice_emotion: Optional[str] = "calm"
    voiceover_text: str
    pause_after_sec: float = 0.8

class MasterSoundDesign(BaseModel):
    sfx_cue: List[str] = Field(default_factory=list)
    bgm_energy: str = "ambient_low"  # ambient_low | tension_buildup | dramatic_climax

class ParallaxMotion(BaseModel):
    enable: bool = True
    foreground_subject: Optional[str] = None
    background_scene: Optional[str] = None

class MasterVisual(BaseModel):
    generation_mode: str = "single_shot"  # 9_grid_composite | single_shot
    grid_batch_id: Optional[str] = None
    grid_cell_index: Optional[int] = None
    grid_composite_prompt_en: Optional[str] = None
    shot_type: Optional[str] = "Establishing Wide Shot"
    camera_movement: Optional[str] = "Slow continuous zoom-in 1.05x"
    image_prompt_en: str
    parallax_motion: Optional[ParallaxMotion] = None

class MasterSubtitles(BaseModel):
    kinetic_highlight_words: List[str] = Field(default_factory=list)

class MasterScene(BaseModel):
    scene_id: int
    estimated_duration_sec: float = 5.0
    audio: MasterAudio
    sound_design: MasterSoundDesign
    visual: MasterVisual
    subtitles: Optional[MasterSubtitles] = Field(default_factory=MasterSubtitles)

class MasterStoryboard(BaseModel):
    project_metadata: ProjectMetadata
    scenes: List[MasterScene] = Field(default_factory=list)

# API Request/Response Models for Master Spec Features
class DeconstructScriptRequest(BaseModel):
    script_text: str
    art_style: Optional[str] = "Dark moody cinematic neo-noir, 35mm anamorphic film grain"
    tone_and_mood: Optional[str] = "tense_suspense"
    batch_9_grid: bool = True
    provider: Optional[str] = "auto"
    api_key: Optional[str] = None

class MasterStoryboardImportRequest(BaseModel):
    storyboard: MasterStoryboard
    project_id: Optional[str] = None
    title: Optional[str] = None

def master_storyboard_to_project(storyboard: MasterStoryboard, project_id: Optional[str] = None) -> Project:
    """Convert MasterStoryboard into Story Studio Project instance."""
    import uuid
    from datetime import datetime

    pid = project_id or f"proj_{uuid.uuid4().hex[:8]}"
    meta = storyboard.project_metadata

    scenes_list: List[Scene] = []
    for sc in storyboard.scenes:
        sid = f"scene_{sc.scene_id:03d}"
        s_obj = Scene(
            id=sid,
            order=sc.scene_id,
            text=sc.audio.voiceover_text,
            image_prompt=sc.visual.image_prompt_en,
            camera_motion=sc.visual.camera_movement or "zoom_in",
            speaker=sc.audio.speaker,
            voice_emotion=sc.audio.voice_emotion or "calm",
            pause_after_sec=sc.audio.pause_after_sec,
            sfx_cue=sc.sound_design.sfx_cue,
            bgm_energy=sc.sound_design.bgm_energy,
            generation_mode=sc.visual.generation_mode,
            grid_batch_id=sc.visual.grid_batch_id,
            grid_cell_index=sc.visual.grid_cell_index,
            grid_composite_prompt_en=sc.visual.grid_composite_prompt_en,
            shot_type=sc.visual.shot_type,
            parallax_motion=sc.visual.parallax_motion.model_dump() if sc.visual.parallax_motion else None,
            kinetic_highlight_words=sc.subtitles.kinetic_highlight_words if sc.subtitles else [],
            duration=sc.estimated_duration_sec,
        )
        scenes_list.append(s_obj)

    anchor_str = ""
    if meta.character_anchors:
        anchor_str = ", ".join([f"{c.character_name}: {c.visual_prompt_anchor}" for c in meta.character_anchors])

    return Project(
        id=pid,
        name=meta.title,
        description=f"Generated via Master Storyboard Studio ({len(scenes_list)} scenes)",
        visual_style_dna=meta.visual_style_dna,
        bgm_overall_genre=meta.bgm_overall_genre,
        character_anchor=anchor_str,
        target_aspect_ratio=meta.target_aspect_ratio,
        scenes=scenes_list,
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
    )


