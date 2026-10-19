"""
Schema chuyển thể vụ án thật thành truyện song ngữ Việt/Anh.

- CaseBible: hồ sơ vụ án rút ra từ bài gốc (nhân vật, địa danh, dòng thời gian, chứng cứ).
- StoryPart / CaseOutline: dàn ý theo nhịp. AdaptedScene: một cảnh đã viết.
- CaseAdaptationPlan: kế hoạch hoàn chỉnh để dựng dự án.
- CasePipeline / PipelineStep: hàng việc phân tích chạy tuần tự, lưu đĩa để chạy tiếp sau khi tắt máy.
"""
from typing import Literal

from pydantic import BaseModel

Lang = Literal["vi", "en"]

# Câu miễn trừ ở cảnh 1, nguyên văn theo từng ngôn ngữ.
DISCLAIMER = {
    "vi": "Câu chuyện dựa trên một vụ án có thật; tên người và địa danh đã được thay đổi.",
    "en": "This story is based on a real case; names of people and places have been changed.",
}

# Số phút video -> (tối thiểu, tối đa) cảnh mục tiêu.
TARGET_SCENES = {8: (35, 40), 15: (50, 60), 20: (70, 80), 30: (100, 120)}
MAX_SOURCE_CHARS = 200_000   # độ dài tối đa của bài gốc (ký tự)
MAX_VIDEO_RATIO = 0.15       # tỉ lệ cảnh video tối đa trên tổng số cảnh
MAX_ATTEMPTS = 3             # số lần thử tối đa cho một việc nhỏ


class CaseEntity(BaseModel):
    id: str
    kind: Literal["person", "place", "organization", "identifier"]
    real_names: list[str]
    role: str = "other"
    alias_vi: str
    alias_en: str
    gender: str = ""
    age_range: str = ""
    appearance_en: str = ""
    notes: str = ""


class TimelineEvent(BaseModel):
    id: str
    order: int
    chunk_index: int
    time_label: str = ""
    summary: str
    entity_ids: list[str] = []


class CaseEvidence(BaseModel):
    id: str
    kind: str = "clue"
    label_vi: str
    label_en: str
    description_vi: str = ""
    description_en: str = ""
    entity_ids: list[str] = []


class CaseRelation(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation_type: str = "suspect_link"
    label_vi: str = ""
    label_en: str = ""


class CaseBible(BaseModel):
    source_language: str
    culture: str
    solved: bool = True
    title_vi: str
    title_en: str
    logline_vi: str = ""
    logline_en: str = ""
    entities: list[CaseEntity]
    timeline: list[TimelineEvent]
    evidence: list[CaseEvidence] = []
    relations: list[CaseRelation] = []
    setting_notes_en: str = ""


class StoryPart(BaseModel):
    """Một nhịp của câu chuyện."""
    id: str
    kind: Literal["hook", "setup", "discovery", "investigation", "twist", "resolution", "open_questions", "epilogue"]
    summary_vi: str
    event_ids: list[str]
    scene_count: int


class CaseOutline(BaseModel):
    supported_minutes: int
    parts: list[StoryPart]


class SceneFlag(BaseModel):
    kind: Literal["unknown_name", "date", "missing_text", "bad_reveal"]
    field: str
    detail: str


class AdaptedScene(BaseModel):
    order: int
    part_id: str
    narration_vi: str
    narration_en: str
    visual_kind: Literal["image", "video", "board", "disclaimer"]
    board_reveal: list[str] = []
    covers_event_ids: list[str] = []
    image_prompt: str = ""
    video_prompt: str = ""
    camera_motion: str = "zoom_in"
    narrative_beat: str = ""
    sfx_cue: list[str] = []
    bgm_energy: str = "tension_buildup"
    flags: list[SceneFlag] = []


class CaseAdaptationPlan(BaseModel):
    case_id: str
    created_at: str
    model: str
    target_minutes: int
    visual_style: str
    languages: list[Lang] = ["vi", "en"]
    bible: CaseBible
    parts: list[StoryPart]
    scenes: list[AdaptedScene]
    # warnings: bền, chỉ được nối thêm (thông báo của hàng việc, các lần tự thay tên). check_plan không xoá.
    warnings: list[str] = []
    # check_warnings và flags (cờ cấp kế hoạch: tên tập, nhãn bằng chứng/quan hệ): check_plan tính lại từ đầu mỗi lần.
    check_warnings: list[str] = []
    flags: list[SceneFlag] = []


StepKind = Literal[
    "extract_chunk", "cluster_names", "assign_aliases", "build_outline",
    "write_vi", "write_en", "write_prompts", "assemble",
]


class PipelineStep(BaseModel):
    id: str
    kind: StepKind
    params: dict = {}
    status: Literal["pending", "running", "done", "failed"] = "pending"
    attempts: int = 0
    error: str = ""


class CasePipeline(BaseModel):
    case_id: str
    status: Literal["running", "done", "failed"] = "running"
    target_minutes: int
    visual_style: str
    chunk_chars: int = 3000
    created_at: str
    updated_at: str
    steps: list[PipelineStep]
