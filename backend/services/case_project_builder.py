"""
Dựng dự án Story Studio từ kế hoạch chuyển thể vụ án, và tạo bản ngôn ngữ khác (spec 7.7, 7.8).

- create_project_from_plan: kế hoạch song ngữ -> dự án thường (bản Việt trước). Cảnh `board` và `disclaimer` được vẽ
  thẳng vào images/ của dự án; các cảnh còn lại chờ Muse vẽ. Không có đường nào ghi vào backend/static.
- create_language_version: chép dự án sang ngôn ngữ khác, dùng lại mọi ảnh và clip Muse, chỉ đổi lời kể, giọng đọc và
  các ảnh có chữ (bảng ghim, thẻ miễn trừ). Cảnh mới thêm hoặc đã sửa lời ở bản gốc thì LLM viết lại lời Anh
  (một lần gọi duy nhất qua rewrite_english).
- Chỉ lời kể, prompt và tên hư cấu đi vào file dự án. Cảnh báo của kế hoạch (warnings, check_warnings), chi tiết cờ và
  mô tả bằng chứng có thể chứa tên thật nên không bao giờ được chép sang.
"""
import asyncio
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from PIL import Image, ImageDraw

import config
from models.case_adaptation_schemas import DISCLAIMER, AdaptedScene, CaseAdaptationPlan, CaseEntity, Lang
from models.evidence_schemas import EvidenceNode, RelationEdge
from models.schemas import Project, Scene
from services import case_store, project_service
from services.case_adaptation_checks import (
    apply_aliases,
    build_forbidden_names,
    find_dates,
    find_unknown_names,
    fold,
    has_blocking_flags,
)
from services.case_adaptation_steps import rewrite_english
from services.investigation_board_engine import (  # NODE_TYPE_LABELS_EN: bảng nhãn tiếng Anh, định nghĩa ở engine
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    NODE_TYPE_LABELS_EN,
    NODE_TYPE_PALETTE,
    assign_fixed_anchor_layout,
    get_cumulative_board_state,
    get_font,
    render_board_image,
)

LANGS: tuple[str, ...] = ("vi", "en")
BOARD_TITLE = {"vi": "Hồ sơ điều tra", "en": "Case file"}
# Giọng dự phòng khi người dùng không chọn và dự án chưa nhớ giọng nào cho ngôn ngữ đó.
DEFAULT_VOICES = {"vi": "vi-VN-NamMinhNeural", "en": "en-US-AndrewMultilingualNeural"}
NOT_FROM_PLAN_MESSAGE = "Dự án này không được tạo từ kế hoạch chuyển thể."

_DISCLAIMER_BG = (12, 12, 16)
_DISCLAIMER_TEXT = (255, 255, 255)
_ID_TRIES = 20      # số lần sinh id dự án mới khi trùng id một dự án đang có


class BlockingFlagsError(Exception):
    """Kế hoạch còn cảnh hoặc nhãn bị đánh dấu (tên thật chưa có tên thay thế, ngày tháng...): chưa được tạo dự án."""


class LanguageVersionError(ValueError):
    """Không tạo được bản ngôn ngữ khác. Thông báo bằng tiếng Việt và không bao giờ nêu tên thật."""


# ---------------------------------------------------------------- bảng ghim theo ngôn ngữ

# Từ khoá (đã bỏ dấu) trong `CaseEvidence.kind` -> kiểu thẻ của engine. Không khớp thì là "clue".
_KIND_KEYWORDS = (
    ("weapon", ("weapon", "hung khi", "vu khi")),
    ("forensic_report", ("forensic", "giam dinh", "phap y")),
    ("location", ("location", "place", "dia diem", "hien truong")),
    ("timeline_event", ("timeline", "moc thoi gian")),
    ("victim", ("victim", "nan nhan")),
    ("suspect", ("suspect", "nghi pham")),
)


def _evidence_node_type(kind: str) -> str:
    if kind in NODE_TYPE_PALETTE:
        return kind
    folded = fold(kind or "")
    for node_type, words in _KIND_KEYWORDS:
        if any(word in folded for word in words):
            return node_type
    return "clue"


def _entity_node_type(entity: CaseEntity) -> str:
    """Thực thể đứng ở đầu mút của một quan hệ cũng cần một thẻ để sợi chỉ có chỗ bám."""
    if entity.kind == "place":
        return "location"
    if entity.kind == "person":
        if entity.role == "victim":
            return "victim"
        if entity.role in ("suspect", "perpetrator"):
            return "suspect"
    return "clue"


def _pick(lang: Lang, vi: str, en: str, *, fallback: bool) -> str:
    text = (vi if lang == "vi" else en) or ""
    if not text and fallback:
        text = (en if lang == "vi" else vi) or ""
    return text


def _first_reveals(plan: CaseAdaptationPlan) -> dict[str, int]:
    """id bằng chứng/quan hệ -> order của cảnh đầu tiên cho nó hiện ra."""
    first: dict[str, int] = {}
    for scene in sorted(plan.scenes, key=lambda s: s.order):
        for item_id in scene.board_reveal:
            first.setdefault(item_id, scene.order)
    return first


def plan_board_items(plan: CaseAdaptationPlan, lang: Lang) -> tuple[list[EvidenceNode], list[RelationEdge]]:
    """Thẻ và sợi chỉ của bảng ghim, nhãn theo `lang`; toạ độ cố định, không phụ thuộc ngôn ngữ.

    - Thẻ: mỗi bằng chứng đã hiện ra ở ít nhất một cảnh; cộng thực thể (nhân vật, địa danh...) đứng ở đầu mút của
      một quan hệ đã hiện ra, vì `relations` của kế hoạch nối các thực thể chứ không nối bằng chứng với nhau.
    - `appearance_scene_order` là order của cảnh đầu tiên cho id đó hiện ra (thực thể: sợi chỉ đầu tiên chạm tới nó).
    - Bằng chứng/quan hệ không cảnh nào cho hiện ra thì không có trên bảng. Mô tả bằng chứng không bao giờ lên thẻ
      (check_plan không quét mô tả nên có thể còn tên thật).
    - Bản `en`: `metadata["badge_label"]` là nhãn huy hiệu tiếng Anh.
    - Engine xếp chỗ một lần cho mọi thẻ của cả kế hoạch, nên vụ án nhiều bằng chứng không bị bỏ thẻ nào: lưới thêm
      ô, mọi thẻ cùng thu nhỏ theo `metadata["card_scale"]`, không thẻ nào đè thẻ nào, và cỡ thẻ giống nhau ở mọi cảnh
      và cả hai ngôn ngữ.
    """
    bible = plan.bible
    first = _first_reveals(plan)

    appears: dict[str, int] = {ev.id: first[ev.id] for ev in bible.evidence if ev.id in first}
    for rel in bible.relations:
        if rel.id not in first:
            continue
        for end in (rel.source_id, rel.target_id):
            appears[end] = min(appears.get(end, first[rel.id]), first[rel.id])

    def make(node_id: str, label: str, node_type: str) -> EvidenceNode:
        # pinned=False và (0, 0): chưa có chỗ. Toạ độ mặc định (960, 540) của EvidenceNode bị engine coi là đã ghim,
        # nên một thẻ nạn nhân mang toạ độ mặc định sẽ giữ chỗ giữa bảng và mọi thẻ còn lại bị xếp chồng lên đó.
        node = EvidenceNode(id=node_id, label=label, node_type=node_type, x=0, y=0, pinned=False,
                            appearance_scene_order=appears[node_id])
        if lang == "en":
            node.metadata["badge_label"] = NODE_TYPE_LABELS_EN[node_type]
        return node

    nodes: list[EvidenceNode] = []
    evidence_ids = {ev.id for ev in bible.evidence}
    for ev in bible.evidence:
        if ev.id in appears:
            nodes.append(make(ev.id, _pick(lang, ev.label_vi, ev.label_en, fallback=True), _evidence_node_type(ev.kind)))
    for ent in bible.entities:
        if ent.id in appears and ent.id not in evidence_ids:
            nodes.append(make(ent.id, _pick(lang, ent.alias_vi, ent.alias_en, fallback=True), _entity_node_type(ent)))
    nodes.sort(key=lambda n: n.appearance_scene_order)       # ổn định: thẻ hiện sớm được chọn chỗ trước
    assign_fixed_anchor_layout(nodes)

    node_ids = {n.id for n in nodes}
    edges: list[RelationEdge] = []
    for rel in bible.relations:
        if rel.id not in first or rel.source_id not in node_ids or rel.target_id not in node_ids:
            continue
        edges.append(RelationEdge(
            id=rel.id, source_id=rel.source_id, target_id=rel.target_id, relation_type=rel.relation_type,
            label=_pick(lang, rel.label_vi, rel.label_en, fallback=False) or None,
            appearance_scene_order=first[rel.id],
        ))
    return nodes, edges


def render_board_scene(plan: CaseAdaptationPlan, scene_order: int, lang: Lang, out_path) -> Path:
    """Vẽ bảng ghim tích luỹ tới cảnh `scene_order`, nhãn và tiêu đề theo `lang`, ghi vào `out_path`."""
    nodes, edges = plan_board_items(plan, lang)
    state = get_cumulative_board_state(SimpleNamespace(nodes=nodes, edges=edges), scene_order)
    state.title = BOARD_TITLE[lang]
    render_board_image(state, str(out_path))
    return Path(out_path)


# ---------------------------------------------------------------- thẻ miễn trừ

def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Ngắt dòng theo chiều rộng thật của chữ; từ dài hơn cả dòng thì ngắt theo ký tự."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = ""
        for ch in word:
            if current and draw.textlength(current + ch, font=font) > max_width:
                lines.append(current)
                current = ""
            current += ch
    if current:
        lines.append(current)
    return lines


def render_disclaimer_card(text: str, out_path) -> Path:
    """Ảnh 1920x1080 nền tối, chữ trắng căn giữa. Chữ dài thì thu nhỏ cho vừa khung."""
    out = Path(out_path)
    image = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), _DISCLAIMER_BG)
    draw = ImageDraw.Draw(image)
    max_width = CANVAS_WIDTH - 2 * 260
    max_height = CANVAS_HEIGHT - 2 * 160
    size = 58
    while True:
        font = get_font(size=size, bold=True)
        lines = _wrap_lines(draw, text, font, max_width)
        line_height = int(size * 1.45)
        if size <= 24 or line_height * len(lines) <= max_height:
            break
        size -= 4
    y = (CANVAS_HEIGHT - line_height * len(lines)) // 2
    for line in lines:
        width = draw.textlength(line, font=font)
        draw.text(((CANVAS_WIDTH - width) / 2, y), line, font=font, fill=_DISCLAIMER_TEXT)
        y += line_height
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(out), quality=95)
    return out


# ---------------------------------------------------------------- dựng dự án bản gốc

def _check_language(language: str) -> None:
    if language not in LANGS:
        raise ValueError(f"Ngôn ngữ không hợp lệ: {language!r}; chỉ nhận 'vi' hoặc 'en'.")


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _blocking_message(plan: CaseAdaptationPlan) -> str:
    """Chỉ nêu cảnh nào bị đánh dấu; chi tiết cờ có thể chứa tên thật nên không đưa vào."""
    where = []
    orders = [s.order for s in plan.scenes if s.flags]
    if orders:
        where.append("cảnh " + ", ".join(str(o) for o in orders))
    if plan.flags:
        where.append("tên tập hoặc nhãn bằng chứng/quan hệ")
    return (f"Kế hoạch còn mục bị đánh dấu ({'; '.join(where)}). "
            "Hãy sửa lời kể hoặc thêm tên vào bảng tên, rồi tạo dự án lại.")


def _media_url(project_id: str, project_dir: Path, path: str) -> str:
    return f"/api/projects/{project_id}/media/{Path(path).relative_to(project_dir).as_posix()}"


def _mark_image_ready(scene: Scene, project_id: str, project_dir: Path, image: Path) -> None:
    scene.image_path = str(image)
    scene.image_url = _media_url(project_id, project_dir, str(image))
    scene.status_image = "ready"
    scene.status = "imaged"


def _draw_text_image(plan: CaseAdaptationPlan, scene: Scene, kind: str, plan_order: int, language: Lang,
                     project_id: str, project_dir: Path) -> None:
    """Vẽ ảnh có chữ (bảng ghim, thẻ miễn trừ) của cảnh vào images/ của dự án."""
    image = project_dir / "images" / f"{scene.id}.jpg"
    if kind == "board":
        render_board_scene(plan, plan_order, language, image)
    else:
        render_disclaimer_card(DISCLAIMER[language], image)
    _mark_image_ready(scene, project_id, project_dir, image)


def _scene_from_plan(plan: CaseAdaptationPlan, adapted: AdaptedScene, language: Lang,
                     project_id: str, project_dir: Path) -> Scene:
    kind = adapted.visual_kind
    if kind == "disclaimer":
        narration = dict(DISCLAIMER)                    # câu miễn trừ là chuỗi cố định, luôn đúng nguyên văn
    else:
        narration = {"vi": adapted.narration_vi, "en": adapted.narration_en}
    text = narration[language]
    scene = Scene(
        id=f"scene_{adapted.order:03d}", order=adapted.order, text=text,
        image_prompt=adapted.image_prompt, video_prompt=adapted.video_prompt, camera_motion=adapted.camera_motion,
        sfx_cue=list(adapted.sfx_cue), bgm_energy=adapted.bgm_energy,
        shot_type="B_ROLL_BOARD" if kind == "board" else "A_ROLL_NOIR",
        metadata={
            "case_id": plan.case_id,
            "narration": narration,
            "narration_source": text,                   # lời của ngôn ngữ dự án lúc tạo: so với text để biết cảnh đã bị sửa
            "visual_kind": kind,
            "board_reveal": list(adapted.board_reveal),
            "narrative_beat": adapted.narrative_beat,
            "plan_order": adapted.order,                # bảng ghim tích luỹ tính theo thứ tự trong kế hoạch, kể cả khi cảnh bị dời
        },
    )
    if kind in ("board", "disclaimer"):
        _draw_text_image(plan, scene, kind, adapted.order, language, project_id, project_dir)
    return scene


def _new_project_id() -> str:
    return f"proj_crime_{uuid.uuid4().hex[:8]}"


def _claim_project_dir() -> tuple[str, Path]:
    """Tạo thư mục cho một dự án mới. Thư mục phải chưa tồn tại (exist_ok=False): id trùng một dự án đang có (rất hiếm)
    thì sinh id khác, để hoàn tác khi lỗi chỉ xoá thư mục do chính lần gọi này tạo và không bao giờ đụng dự án khác."""
    for _ in range(_ID_TRIES):
        project_id = _new_project_id()
        project_dir = project_service._get_project_dir(project_id)
        try:
            project_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        try:
            project_service._ensure_project_subdirs(project_id)
        except BaseException:
            project_service.delete_project(project_id)      # thư mục vừa tạo ở trên
            raise
        return project_id, project_dir
    raise RuntimeError("Không tạo được mã dự án mới (trùng mã nhiều lần liên tiếp). Hãy thử lại.")


def create_project_from_plan(plan: CaseAdaptationPlan, language: Lang, voice: str, *,
                             visual_style: Optional[str] = None, image_provider: str = "meta_muse_cloud",
                             voices: Optional[dict] = None) -> Project:
    """Kế hoạch -> dự án mới `proj_crime_<8 hex>` bằng `language`. Còn cờ chặn thì BlockingFlagsError."""
    _check_language(language)
    if has_blocking_flags(plan):
        raise BlockingFlagsError(_blocking_message(plan))
    voice = voice or DEFAULT_VOICES[language]

    project_id, project_dir = _claim_project_dir()
    try:
        scenes = [_scene_from_plan(plan, adapted, language, project_id, project_dir)
                  for adapted in sorted(plan.scenes, key=lambda s: s.order)]
        now = _now()
        project = Project(
            id=project_id,
            name=(plan.bible.title_vi if language == "vi" else plan.bible.title_en) or plan.case_id,
            description=f"Chuyển thể từ một vụ án có thật, {len(scenes)} cảnh.",
            voice=voice,
            style_preset=visual_style or plan.visual_style or "neo_noir_silhouette",
            image_provider=image_provider,
            bgm_overall_genre="mysterious_dark",
            target_aspect_ratio="16:9",
            scenes=scenes,
            created_at=now,
            updated_at=now,
            metadata={
                "case_id": plan.case_id,
                "language": language,
                "sibling_project_ids": [],
                "voices": {**(voices or {}), language: voice},
            },
        )
        project_service._save_project(project)
    except BaseException:
        project_service.delete_project(project_id)      # thư mục vừa tạo, còn dở dang
        raise
    return project


# ---------------------------------------------------------------- bản ngôn ngữ khác

def _rebase_path(value: Optional[str], old_dir: Path, new_dir: Path) -> Optional[str]:
    """Đường dẫn file trong dự án cũ -> đường dẫn tương ứng trong dự án mới; None nếu file không có ở dự án mới."""
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = config.STORY_STUDIO_DIR / path
    try:
        relative = path.resolve().relative_to(old_dir.resolve())
    except (OSError, ValueError):
        return None
    candidate = new_dir / relative
    return str(candidate) if candidate.is_file() else None


def _copy_media(old_dir: Path, new_dir: Path) -> None:
    """Chép images/* và videos/*_muse.mp4. Giọng, phụ đề, đoạn dựng và video cuối ở lại dự án cũ."""
    if (old_dir / "images").is_dir():
        shutil.copytree(old_dir / "images", new_dir / "images", dirs_exist_ok=True)
    if (old_dir / "videos").is_dir():
        for clip in (old_dir / "videos").glob("*_muse.mp4"):
            shutil.copy2(clip, new_dir / "videos" / clip.name)


def _carry_scene_media(scene: Scene, old_dir: Path, new_id: str, new_dir: Path) -> None:
    """Bản sao của cảnh: giữ ảnh và clip Muse (trỏ sang dự án mới), bỏ giọng đọc, phụ đề và đoạn dựng."""
    image = _rebase_path(scene.image_path, old_dir, new_dir)
    scene.image_path = image
    scene.image_url = _media_url(new_id, new_dir, image) if image else None
    scene.status_image = "ready" if image else "idle"
    scene.status = "imaged" if image else "draft"
    scene.foreground_image_path = _rebase_path(scene.foreground_image_path, old_dir, new_dir)
    scene.background_image_path = _rebase_path(scene.background_image_path, old_dir, new_dir)

    clip = _rebase_path(scene.motion_video_path, old_dir, new_dir)
    if clip is None and (new_dir / "videos" / f"{scene.id}_muse.mp4").is_file():
        clip = str(new_dir / "videos" / f"{scene.id}_muse.mp4")
    scene.motion_video_path = clip
    scene.video_url = scene.video_segment_url = _media_url(new_id, new_dir, clip) if clip else None
    scene.video_segment_path = None
    scene.status_video = "ready" if clip else "idle"
    if clip is None and scene.media_view_mode == "video":
        scene.media_view_mode = "image"

    scene.voice_audio_path = scene.voice_audio_url = None
    scene.audio_path = scene.audio_url = None
    scene.srt_path = scene.srt_url = None
    scene.duration = None
    scene.status_voice = "idle"
    scene.kinetic_highlight_words = []                  # từ nhấn của phụ đề thuộc về lời kể ngôn ngữ cũ
    for key in ("voice_error", "voice_fallback", "segment_rendered"):
        scene.metadata.pop(key, None)


def _same_text(a: Optional[str], b: Optional[str]) -> bool:
    """Lời có bị sửa không: chỉ khác khoảng trắng hay xuống dòng (giao diện có thể tự chuẩn hoá) thì chưa tính là sửa."""
    return " ".join((a or "").split()) == " ".join((b or "").split())


def _alias_pool(plan: CaseAdaptationPlan) -> list[str]:
    return list(dict.fromkeys(a.strip() for e in plan.bible.entities for a in (e.alias_vi, e.alias_en)
                              if a and a.strip()))


def _guard_rewritten(plan: CaseAdaptationPlan, rewritten: dict[int, str]) -> dict[int, str]:
    """rewrite_english không có bài gốc nên chỉ bắt được tên trong bảng tên. Ở đây quét thêm các tên mà regex bắt
    được trên bài gốc: tên đã có tên hư cấu thì tự thay, tên chưa có thì dừng. Ngày tháng hoặc năm cụ thể cũng dừng.
    Thông báo chỉ nêu cảnh nào, không bao giờ nêu tên thật hay nội dung lời."""
    if not rewritten:
        return {}
    forbidden = build_forbidden_names(plan.bible, case_store.load_source(plan.case_id) or "")
    aliases = _alias_pool(plan)
    safe: dict[int, str] = {}
    for order, text in rewritten.items():
        fixed, _replaced = apply_aliases(text, forbidden, "en", extra_aliases=aliases)
        if find_unknown_names(fixed, forbidden, aliases):
            raise LanguageVersionError(
                f"Lời Anh viết lại cho cảnh {order} còn tên thật chưa có tên thay thế. "
                "Hãy thêm tên đó vào bảng tên hoặc sửa lời Việt của cảnh này rồi tạo lại.")
        if find_dates(fixed):
            raise LanguageVersionError(
                f"Lời Anh viết lại cho cảnh {order} còn ngày tháng hoặc năm cụ thể. "
                "Hãy sửa lời Việt của cảnh này thành cách nói chung (ví dụ \"giữa thập niên 2010\") rồi tạo lại.")
        safe[order] = fixed
    return safe


def _materialize_language_version(source: Project, plan: CaseAdaptationPlan, language: Lang, voice: str,
                                  source_language: str, texts: dict[str, str]) -> Project:
    """Phần nặng của create_language_version (chép file, vẽ bảng ghim, lưu): chạy trong luồng riêng.
    `texts`: scene.id -> lời kể mới."""
    old_id = source.id
    old_dir = project_service._get_project_dir(old_id)
    new_id, new_dir = _claim_project_dir()
    try:
        _copy_media(old_dir, new_dir)
        new = source.model_copy(deep=True)
        new.id = new_id
        title = plan.bible.title_vi if language == "vi" else plan.bible.title_en
        new.name = title or source.name
        new.voice = voice
        if "voice" in new.settings:                     # giao diện ưu tiên settings.voice hơn project.voice
            new.settings["voice"] = voice
        new.final_video_path = new.final_video_url = None
        new.thumbnail_path = new.thumbnail_url = None
        new.seo_title = new.seo_description = None      # SEO viết cho lời kể ngôn ngữ cũ
        new.seo_tags = []
        new.created_at = _now()
        voices = dict(source.metadata.get("voices") or {})
        voices[language] = voice
        new.metadata = {**source.metadata, "case_id": plan.case_id, "language": language,
                        "sibling_project_ids": [old_id], "voices": voices}

        for scene in new.scenes:
            old_text = scene.text
            kind = scene.metadata.get("visual_kind")
            new_text = texts[scene.id]
            narration = dict(scene.metadata.get("narration") or {})
            if kind == "disclaimer":
                narration = dict(DISCLAIMER)
            elif old_text.strip():
                narration[source_language] = old_text   # giữ cả lời Việt đã sửa tay để bản sau còn dùng được
            narration[language] = new_text
            scene.text = new_text
            scene.metadata["narration"] = narration
            scene.metadata["narration_source"] = new_text
            _carry_scene_media(scene, old_dir, new_id, new_dir)
            if kind in ("board", "disclaimer"):
                plan_order = scene.metadata.get("plan_order")
                _draw_text_image(plan, scene, kind, plan_order if isinstance(plan_order, int) else scene.order,
                                 language, new_id, new_dir)

        project_service._save_project(new)
        # Liên kết hai chiều. Đọc lại dự án gốc: lúc LLM viết lại, giao diện có thể đã tự lưu chỉnh sửa khác.
        latest = project_service.get_project(old_id) or source
        siblings = list(latest.metadata.get("sibling_project_ids") or [])
        if new_id not in siblings:
            siblings.append(new_id)
        latest.metadata["sibling_project_ids"] = siblings
        project_service._save_project(latest)
    except BaseException:
        project_service.delete_project(new_id)          # dự án mới còn dở dang
        raise
    return new


async def create_language_version(project_id: str, language: Lang, voice: Optional[str] = None, *,
                                  llm=None) -> tuple[Project, list[int]]:
    """Chép dự án sang `language`: dùng lại ảnh và clip Muse, đổi lời kể, giọng và các ảnh có chữ.
    Trả (dự án mới, danh sách order các cảnh đã được viết lại lời). Hỏng ở bất kỳ bước nào thì không để lại dự án mới."""
    if language not in LANGS:
        raise LanguageVersionError("Ngôn ngữ phải là 'vi' hoặc 'en'.")
    try:
        source = project_service.get_project(project_id)
    except ValueError:                                  # mã dự án sai định dạng
        source = None
    if source is None:
        raise LanguageVersionError("Không tìm thấy dự án.")
    case_id = source.metadata.get("case_id")
    if not case_id or not any(isinstance(s.metadata.get("narration"), dict) for s in source.scenes):
        raise LanguageVersionError(NOT_FROM_PLAN_MESSAGE)
    source_language = source.metadata.get("language")
    if source_language not in LANGS:
        source_language = "vi"
    if language == source_language:
        raise LanguageVersionError("Dự án này đã ở ngôn ngữ đó.")
    try:
        plan = case_store.load_plan(case_id)
    except ValueError:
        plan = None                                     # case_id không hợp lệ hoặc plan.json hỏng
    if plan is None:
        raise LanguageVersionError("Không tìm thấy kế hoạch chuyển thể của dự án này nên chưa tạo được bản ngôn ngữ khác.")

    voices = source.metadata.get("voices") or {}
    voice = voice or voices.get(language) or DEFAULT_VOICES[language]

    # Cảnh nào dùng lại lời có sẵn, cảnh nào phải viết lại.
    texts: dict[str, str] = {}
    to_rewrite: list[Scene] = []
    for scene in source.scenes:
        meta = scene.metadata
        narration = meta.get("narration")
        existing = narration.get(language) if isinstance(narration, dict) else None
        if meta.get("visual_kind") == "disclaimer":
            texts[scene.id] = DISCLAIMER[language]
        elif existing and _same_text(scene.text, meta.get("narration_source")):
            texts[scene.id] = existing
        elif not scene.text.strip():
            texts[scene.id] = ""                        # cảnh trống: không có gì để viết lại
        else:
            to_rewrite.append(scene)
    if to_rewrite and language != "en":
        orders = ", ".join(str(s.order) for s in to_rewrite)
        raise LanguageVersionError(
            f"Cảnh {orders} đã được sửa hoặc thêm sau khi tạo dự án, nhưng chỉ viết lại tự động được sang tiếng Anh. "
            "Hãy sửa lời của các cảnh này bằng tay hoặc đưa chúng về lời gốc rồi thử lại.")

    rewritten = (await rewrite_english(plan.bible, [(s.order, s.text) for s in to_rewrite], llm=llm,
                                       target_minutes=plan.target_minutes) if to_rewrite else {})
    rewritten = _guard_rewritten(plan, rewritten)
    for scene in to_rewrite:
        texts[scene.id] = rewritten[scene.order]

    new = await asyncio.to_thread(_materialize_language_version, source, plan, language, voice, source_language, texts)
    return new, [s.order for s in to_rewrite]
