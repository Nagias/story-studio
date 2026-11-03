"""Khoá bối cảnh: nơi lặp lại ở từ 2 cảnh trở lên có mô tả cố định và một ảnh chuẩn (chủ dự án, câu 17 mục 1.2).

Trước đây mỗi cảnh tự tả bối cảnh trong prompt ảnh (LLM viết từng cảnh), nên cùng một nơi (căn hộ tầng sáu, hành lang
đồn cảnh sát) mỗi cảnh vẽ một kiểu. Module này:
1. Tìm bối cảnh lặp lại: MỘT lần gọi LLM đọc prompt ảnh và lời kể của mọi cảnh, gom cảnh cùng nơi, viết mô tả cố định
   tiếng Anh cho từng nơi (`analyze_locations()`; Python kiểm: mỗi nơi ≥ 2 cảnh có thật, mỗi cảnh một nơi, mô tả đủ dài).
2. Chủ dự án xem, sửa mô tả và danh sách cảnh, cho Muse vẽ ảnh chuẩn (cảnh trống, không người), ghi chỗ sai rồi vẽ lại
   trong cùng side chat, duyệt — giống bảng nhân vật (services/character_sheets.py).
3. Tạo ảnh cho cảnh thuộc bối cảnh ĐÃ DUYỆT: prompt thêm đúng mô tả cố định, đính kèm ảnh chuẩn khi khung hình thấy
   được bối cảnh (không phải cận cảnh) — `scene_lock()` trả gói dùng chung cho mọi đường tạo ảnh (qua `services/scene_locks.py`) và video Muse.

Dữ liệu ở `projects/<id>/locations/locations.json` — chỉ module này ghi (giao diện tự lưu dự án không đè được).
Không import routers/ (`muse_call` truyền vào). LLM gọi qua `ask_validated` của luồng vụ án (có thử lại, chờ khi bận).
"""
import asyncio
import logging
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, Field

from config import PROJECTS_DIR, STATIC_DIR
from models.schemas import Project, Scene
from security import is_safe_id, is_within
from services import project_service, safe_files
from services.case_adaptation_llm import LLMCall, call_llm_json
from services.case_adaptation_steps import StepRejected, ask_validated

logger = logging.getLogger("story_studio.location_sheets")

PlateStatus = Literal["draft", "drawing", "review", "approved", "failed"]
MuseCall = Callable[[dict], Awaitable[dict]]

MIN_SCENES = 2              # "bối cảnh lặp lại": xuất hiện từ chừng này cảnh trở lên
MAX_LOCATIONS = 24
MIN_DESIGN_WORDS = 25       # mô tả ngắn hơn thì Muse tự bịa phần còn lại: mỗi cảnh lại một kiểu
MAX_DESIGN_CHARS = 2000
NAME_MAX = 80
FEEDBACK_MAX = 500
PROMPT_EXCERPT_CHARS = 420  # mỗi cảnh gửi LLM tối đa chừng này ký tự prompt ảnh (dự án 80 cảnh ~ 50 nghìn ký tự)
TEXT_EXCERPT_CHARS = 220
# Cảnh không phải hình vẽ của câu chuyện (bảng ghim, thẻ miễn trừ) thì không có bối cảnh
SKIP_VISUAL_KINDS = ("board", "disclaimer", "title", "card")
# Khung hình gần như không thấy nền: chỉ thêm mô tả, không đính kèm ảnh chuẩn (ảnh chuẩn kéo khung về cảnh rộng)
CLOSE_SHOT = re.compile(r"\b(extreme\s+)?close[\s-]?up\b|\bmacro\b|\binsert\s+shot\b", re.I)

LOCK_LINE_EN = ("FIXED LOCATION (this place appears in several scenes and must look identical in every one of them: "
                "same architecture, layout, fixed objects, materials, colours and light sources; only the camera angle "
                "and the people change): ")
PLATE_RULES_EN = (
    "This is a LOCATION REFERENCE PLATE: show the whole place clearly from a wide eye-level establishing angle, with "
    "every fixed element of the design visible. Absolutely no people, no characters, no silhouettes, no animals, no "
    "text, no labels, no watermark. Before answering, check the image against every sentence of the design."
)
ANALYZE_SYSTEM_PROMPT = """\
Bạn là trợ lý dựng hình cho video kể chuyện. Bạn đọc danh sách cảnh (prompt ảnh tiếng Anh và lời kể) và tìm các NƠI
CHỐN xuất hiện lặp lại để hoạ sĩ vẽ chúng giống hệt nhau ở mọi cảnh. Chỉ trả về đúng một JSON object, không thêm chữ nào."""

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


class LocationSheet(BaseModel):
    location_id: str
    name_vi: str
    design_en: str
    scene_ids: list[str] = Field(default_factory=list)
    status: PlateStatus = "draft"
    plate_path: Optional[str] = None
    versions: list[str] = Field(default_factory=list)
    account_id: Optional[str] = None
    thread_url: Optional[str] = None
    error: Optional[str] = None
    feedback: list[str] = Field(default_factory=list)
    source: Literal["llm", "manual"] = "llm"


class ProjectLocations(BaseModel):
    locations: dict[str, LocationSheet] = Field(default_factory=dict)
    analyzed_at: Optional[str] = None
    analysis_error: Optional[str] = None


class LocationError(ValueError):
    """Lỗi dữ liệu bối cảnh; lời nhắn tiếng Việt hiện thẳng cho người dùng."""


# ------------------------------------------------------------------------------------------------------ lưu trữ
def _lock(project_id: str) -> threading.RLock:
    with _locks_guard:
        return _locks.setdefault(project_id, threading.RLock())


def _project(project_id: str) -> Project:
    project = project_service.get_project(project_id)
    if project is None:
        raise LookupError(f"Không có dự án {project_id}")
    return project


def locations_dir(project_id: str) -> Path:
    d = project_service.ensure_project_dirs(project_id) / "locations"
    d.mkdir(exist_ok=True)
    return d


def _store_path(project_id: str) -> Path:
    return locations_dir(project_id) / "locations.json"


def _existing_store_path(project_id: str) -> Path:
    """Đường dẫn file mà không tạo thư mục (đọc khi tạo ảnh không được sinh thư mục rác)."""
    return PROJECTS_DIR / project_id / "locations" / "locations.json"


def load_locations(project_id: str) -> ProjectLocations:
    _project(project_id)   # trước mọi thao tác thư mục: id sai không được sinh thư mục rác
    with _lock(project_id):
        text = safe_files.read_text(_existing_store_path(project_id))
        return ProjectLocations.model_validate_json(text) if text else ProjectLocations()


def save_locations(project_id: str, data: ProjectLocations) -> None:
    """Nơi duy nhất ghi locations.json."""
    with _lock(project_id):
        safe_files.write_text_atomic(_store_path(project_id), data.model_dump_json(indent=2))


def _mutate(project_id: str, change: Callable[[ProjectLocations], Any]) -> Any:
    _project(project_id)
    with _lock(project_id):   # đọc-sửa-ghi trong một khoá: hai lần vẽ xong cùng lúc không mất bản nào
        data = load_locations(project_id)
        out = change(data)
        save_locations(project_id, data)
        return out


def _update(project_id: str, location_id: str, change: Callable[[LocationSheet], None]) -> LocationSheet:
    def run(data: ProjectLocations) -> LocationSheet:
        loc = data.locations.get(location_id)
        if loc is None:
            raise LookupError(f"Dự án không có bối cảnh {location_id}")
        change(loc)
        return loc
    return _mutate(project_id, run)


# ------------------------------------------------------------------------------------------------ cảnh hợp lệ
def eligible_scenes(project: Project) -> list[Scene]:
    """Cảnh có hình vẽ của câu chuyện (bỏ bảng ghim, thẻ miễn trừ) và có prompt ảnh hoặc lời kể."""
    return [s for s in project.scenes
            if (s.metadata or {}).get("visual_kind") not in SKIP_VISUAL_KINDS and (s.image_prompt or s.text or "").strip()]


def _clean_scene_ids(project: Project, scene_ids: list[str]) -> list[str]:
    known = {s.id for s in eligible_scenes(project)}
    ids = list(dict.fromkeys(str(x).strip() for x in scene_ids))
    unknown = [x for x in ids if x not in known]
    if unknown:
        raise LocationError(f"Không có cảnh (hoặc cảnh không có hình vẽ): {', '.join(unknown[:8])}")
    return ids


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _check_design(design_en: str) -> str:
    text = " ".join((design_en or "").split())
    if _words(text) < MIN_DESIGN_WORDS:
        raise LocationError(f"Mô tả bối cảnh cần ít nhất {MIN_DESIGN_WORDS} từ tiếng Anh (kiến trúc, bố cục, đồ vật cố "
                            "định, màu sắc, nguồn sáng) để mọi cảnh vẽ giống nhau")
    if len(text) > MAX_DESIGN_CHARS:
        raise LocationError(f"Mô tả bối cảnh tối đa {MAX_DESIGN_CHARS} ký tự")
    return text


def _check_name(name_vi: str) -> str:
    name = " ".join((name_vi or "").split())
    if not name:
        raise LocationError("Tên bối cảnh không được để trống")
    if len(name) > NAME_MAX:
        raise LocationError(f"Tên bối cảnh tối đa {NAME_MAX} ký tự")
    return name


def _take_scenes(data: ProjectLocations, location_id: str, scene_ids: list[str]) -> None:
    """Mỗi cảnh thuộc một bối cảnh: gán cảnh cho nơi này thì gỡ khỏi nơi khác (nơi đó đổi danh sách nên về nháp)."""
    for other in data.locations.values():
        if other.location_id != location_id and set(other.scene_ids) & set(scene_ids):
            other.scene_ids = [s for s in other.scene_ids if s not in scene_ids]


def scene_location_map(data: ProjectLocations) -> dict[str, str]:
    return {sid: loc.location_id for loc in data.locations.values() for sid in loc.scene_ids}


# ------------------------------------------------------------------------------------- tìm bối cảnh bằng LLM
def analyze_prompt(project: Project) -> str:
    lines = []
    allowed = {s.id for s in eligible_scenes(project)}
    for i, s in enumerate(project.scenes, 1):
        if s.id not in allowed:
            continue
        prompt = " ".join((s.image_prompt or "").split())[:PROMPT_EXCERPT_CHARS]
        text = " ".join((s.text or "").split())[:TEXT_EXCERPT_CHARS]
        lines.append(f"- id {s.id} (cảnh #{i}) | PROMPT: {prompt or '(trống)'} | LỜI KỂ: {text or '(trống)'}")
    return f"""TASK: LOCATIONS
Việc: tìm các nơi chốn LẶP LẠI trong video (một nơi xuất hiện ở từ {MIN_SCENES} cảnh trở lên, liền nhau hay cách xa
nhau đều tính) và viết cho mỗi nơi MỘT mô tả cố định để hoạ sĩ vẽ nơi đó giống hệt nhau ở mọi cảnh.

CÁC CẢNH:
{chr(10).join(lines)}

YÊU CẦU
1. Mỗi nơi chốn là một địa điểm cụ thể (ví dụ: phòng khách căn hộ tầng sáu, hành lang đồn cảnh sát, con hẻm sau chợ),
   không phải kiểu chung chung ("trong nhà", "ban đêm"). Hai phòng khác nhau của cùng toà nhà là hai nơi.
2. Mỗi cảnh thuộc TỐI ĐA một nơi (nơi chính của cảnh). Cảnh chỉ xuất hiện một lần ở nơi nào đó thì bỏ, không ghi.
3. "name_vi": tên ngắn tiếng Việt cho người dùng đọc (không ghi tên người).
4. "description_en": tiếng Anh, 40–90 từ, chỉ tả NƠI CHỐN: kiến trúc, bố cục (cái gì ở bên trái, bên phải, phía sau),
   đồ vật cố định, vật liệu, màu sắc chủ đạo, nguồn sáng. Lấy chi tiết từ các prompt của những cảnh đó; chỗ các prompt
   tả khác nhau thì chọn một cách và giữ cố định. KHÔNG tả người, KHÔNG tả hành động, KHÔNG ghi tên riêng, KHÔNG tả nét
   vẽ (phong cách vẽ đã có riêng).
5. "scene_ids": đúng id các cảnh ở nơi đó (chép id ở danh sách trên), ít nhất {MIN_SCENES} cảnh.
6. Tối đa {MAX_LOCATIONS} nơi. Không có nơi nào lặp lại thì trả "locations": [].

Trả về đúng một JSON object:
{{"locations": [{{"name_vi": "...", "description_en": "...", "scene_ids": ["scene_...", "scene_..."]}}]}}"""


def validate_analysis(raw: Any, project: Project) -> list[dict]:
    """Kiểm kết quả LLM; sai thì StepRejected (lý do gửi lại cho LLM viết lại)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("locations"), list):
        raise StepRejected('Cần JSON object có khoá "locations" là một mảng.')
    known = {s.id for s in eligible_scenes(project)}
    seen: dict[str, str] = {}
    out: list[dict] = []
    for i, item in enumerate(raw["locations"][:MAX_LOCATIONS], 1):
        if not isinstance(item, dict):
            raise StepRejected(f"Phần tử {i} của locations không phải object.")
        name = " ".join(str(item.get("name_vi") or "").split())[:NAME_MAX]
        design = " ".join(str(item.get("description_en") or "").split())
        ids = item.get("scene_ids")
        if not name:
            raise StepRejected(f"Nơi {i} thiếu name_vi.")
        if not isinstance(ids, list):
            raise StepRejected(f"Nơi {i} ({name}): scene_ids phải là mảng id cảnh.")
        ids = list(dict.fromkeys(str(x).strip() for x in ids))
        unknown = [x for x in ids if x not in known]
        if unknown:
            raise StepRejected(f"Nơi {i} ({name}) có id cảnh không có trong danh sách: {', '.join(unknown[:6])}. "
                               "Chỉ chép id ở danh sách cảnh.")
        dup = [x for x in ids if x in seen]
        if dup:
            raise StepRejected(f"Cảnh {', '.join(dup[:6])} được xếp vào cả nơi \"{seen[dup[0]]}\" lẫn nơi \"{name}\": "
                               "mỗi cảnh chỉ thuộc một nơi.")
        if len(ids) < MIN_SCENES:
            raise StepRejected(f"Nơi {i} ({name}) chỉ có {len(ids)} cảnh: chỉ ghi nơi có từ {MIN_SCENES} cảnh trở lên.")
        if _words(design) < MIN_DESIGN_WORDS:
            raise StepRejected(f"Mô tả nơi {i} ({name}) chỉ có {_words(design)} từ: cần 40–90 từ tả kiến trúc, bố cục, "
                               "đồ vật cố định, màu sắc, nguồn sáng.")
        for x in ids:
            seen[x] = name
        out.append({"name_vi": name, "design_en": design[:MAX_DESIGN_CHARS], "scene_ids": ids})
    return out


async def analyze_locations(project_id: str, llm: Optional[LLMCall] = None) -> ProjectLocations:
    """Tìm bối cảnh lặp lại bằng LLM (1 lần gọi, thêm lần thử lại khi kết quả sai luật) và thay danh sách cũ.
    Bối cảnh chủ dự án tự thêm, và bối cảnh đã có ảnh chuẩn (đang chờ duyệt hoặc đã duyệt), được giữ nguyên; nơi mới
    trùng cảnh với chúng thì nhường cảnh đó."""
    project = await asyncio.to_thread(_project, project_id)
    if len(eligible_scenes(project)) < MIN_SCENES:
        raise LocationError(f"Dự án cần ít nhất {MIN_SCENES} cảnh có hình vẽ mới tìm được bối cảnh lặp lại")
    base = llm or call_llm_json

    async def call(_system: str, user: str, **kwargs: Any) -> Any:
        return await base(ANALYZE_SYSTEM_PROMPT, user, **kwargs)

    found = await ask_validated(analyze_prompt(project), lambda raw: validate_analysis(raw, project), llm=call,
                                temperature=0.3, step_label="tìm bối cảnh lặp lại")

    def apply(data: ProjectLocations) -> ProjectLocations:
        kept = {k: v for k, v in data.locations.items()
                if v.source == "manual" or v.status in ("review", "approved", "drawing") or v.versions}
        taken = {sid for v in kept.values() for sid in v.scene_ids}
        n = max([int(m.group(1)) for k in data.locations for m in [re.fullmatch(r"loc_(\d+)", k)] if m] + [0])
        new: dict[str, LocationSheet] = dict(kept)
        for item in found:
            ids = [x for x in item["scene_ids"] if x not in taken]
            if len(ids) < MIN_SCENES:
                continue
            n += 1
            loc_id = f"loc_{n}"
            new[loc_id] = LocationSheet(location_id=loc_id, name_vi=item["name_vi"], design_en=item["design_en"],
                                        scene_ids=ids)
            taken.update(ids)
        data.locations = new
        data.analyzed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data.analysis_error = None
        return data
    return await asyncio.to_thread(_mutate, project_id, apply)


def record_analysis_error(project_id: str, message: str) -> None:
    def change(data: ProjectLocations) -> None:
        data.analysis_error = message
    _mutate(project_id, change)


# --------------------------------------------------------------------------------------- chủ dự án chỉnh tay
def create_location(project_id: str, name_vi: str, design_en: str, scene_ids: list[str]) -> LocationSheet:
    project = _project(project_id)
    name, design = _check_name(name_vi), _check_design(design_en)
    ids = _clean_scene_ids(project, scene_ids)
    if len(ids) < MIN_SCENES:
        raise LocationError(f"Bối cảnh lặp lại cần ít nhất {MIN_SCENES} cảnh")

    def run(data: ProjectLocations) -> LocationSheet:
        if len(data.locations) >= MAX_LOCATIONS:
            raise LocationError(f"Tối đa {MAX_LOCATIONS} bối cảnh")
        n = max([int(m.group(1)) for k in data.locations for m in [re.fullmatch(r"loc_(\d+)", k)] if m] + [0]) + 1
        loc = LocationSheet(location_id=f"loc_{n}", name_vi=name, design_en=design, scene_ids=ids, source="manual")
        _take_scenes(data, loc.location_id, ids)
        data.locations[loc.location_id] = loc
        return loc
    return _mutate(project_id, run)


def edit_location(project_id: str, location_id: str, name_vi: Optional[str] = None, design_en: Optional[str] = None,
                  scene_ids: Optional[list[str]] = None) -> LocationSheet:
    project = _project(project_id)
    name = _check_name(name_vi) if name_vi is not None else None
    design = _check_design(design_en) if design_en is not None else None
    ids = _clean_scene_ids(project, scene_ids) if scene_ids is not None else None
    if ids is not None and len(ids) < MIN_SCENES:
        raise LocationError(f"Bối cảnh lặp lại cần ít nhất {MIN_SCENES} cảnh (muốn bỏ hẳn thì bấm \"Bỏ bối cảnh\")")

    def run(data: ProjectLocations) -> LocationSheet:
        loc = data.locations.get(location_id)
        if loc is None:
            raise LookupError(f"Dự án không có bối cảnh {location_id}")
        if loc.status == "drawing":
            raise LocationError("Muse đang vẽ ảnh chuẩn của bối cảnh này, chờ xong rồi sửa")
        if name is not None:
            loc.name_vi = name
        if design is not None and design != loc.design_en:
            loc.design_en = design
            if loc.status == "approved":
                loc.status = "draft"   # đổi mô tả thì ảnh chuẩn cũ không còn đúng: duyệt lại
        if ids is not None:
            _take_scenes(data, location_id, ids)
            loc.scene_ids = ids
        return loc
    return _mutate(project_id, run)


def remove_location(project_id: str, location_id: str) -> None:
    """Bỏ bối cảnh khỏi danh sách (cảnh của nó thôi khoá). Ảnh chuẩn đã vẽ vẫn giữ trên đĩa."""
    def run(data: ProjectLocations) -> None:
        loc = data.locations.get(location_id)
        if loc is None:
            raise LookupError(f"Dự án không có bối cảnh {location_id}")
        if loc.status == "drawing":
            raise LocationError("Muse đang vẽ ảnh chuẩn của bối cảnh này, chờ xong rồi bỏ")
        del data.locations[location_id]
    _mutate(project_id, run)


# ------------------------------------------------------------------------------------------- vẽ, duyệt ảnh chuẩn
def _studio_path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else PROJECTS_DIR.parent / p


def reference_image(project: Project, loc: LocationSheet) -> Optional[Path]:
    """Ảnh cảnh đầu tiên của nơi này (để Muse vẽ ảnh chuẩn đúng nét vẽ của dự án); chưa cảnh nào có ảnh thì None."""
    by_id = {s.id: s for s in project.scenes}
    for sid in loc.scene_ids:
        s = by_id.get(sid)
        if s and s.image_path:
            p = _studio_path(s.image_path)
            if p.is_file() and is_within(p, PROJECTS_DIR, STATIC_DIR):
                return p
    return None


def _style_text(style_id: str) -> str:
    """Nét vẽ của phong cách dự án, bỏ câu quy tắc tóc nhân vật (ảnh chuẩn không có người)."""
    from services.image_service import FEMALE_HAIR_RULE_EN, ROUND_HEAD_EXPRESSION_RULE_EN, STYLE_PRESETS  # nạp muộn
    style = (STYLE_PRESETS.get(style_id) or {}).get("prompt_suffix", "")
    return " ".join(style.replace(FEMALE_HAIR_RULE_EN, " ").replace(ROUND_HEAD_EXPRESSION_RULE_EN, " ").split())


def plate_prompt(loc: LocationSheet, style_id: str, has_reference: bool) -> str:
    head = ("tạo cho tôi 1 hình ảnh 2K tỉ lệ 16:9: LOCATION REFERENCE PLATE of ONE place"
            + (", drawn in exactly the same art style as the attached scene image (copy only the art style and the "
               "place, never the people)." if has_reference else "."))
    lines = [head, f"LOCATION DESIGN:\n{loc.design_en.strip()}"]
    style = _style_text(style_id)
    if style:
        lines.append(f"Drawing style: {style}")
    lines.append(PLATE_RULES_EN)
    for fb in loc.feedback:
        lines.append(f"Bản trước SAI: {fb.strip()} — sửa đúng chỗ này, phần còn lại giữ nguyên mô tả.")
    return "\n".join(lines)


def _clear_thread(loc: LocationSheet) -> None:
    loc.thread_url = None
    loc.account_id = None


async def draw_plate(project_id: str, location_id: str, muse_call: MuseCall) -> LocationSheet:
    """Muse (tài khoản ảnh) vẽ ảnh chuẩn của bối cảnh; vẽ lại thì dùng đúng side chat cũ. Xong: trạng thái "review"."""
    data = await asyncio.to_thread(load_locations, project_id)
    loc = data.locations.get(location_id)
    if loc is None:
        raise LookupError(f"Dự án không có bối cảnh {location_id}")
    project = await asyncio.to_thread(_project, project_id)
    ref = reference_image(project, loc)
    n = len(loc.versions) + 1
    out = locations_dir(project_id) / location_id / f"plate_v{n}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    task = {"mode": "text-to-image", "raw_prompt": True, "prompt": plate_prompt(loc, project.style_preset, ref is not None),
            "attachments": [str(ref)] if ref else [], "aspect_ratio": "16:9",
            "parameters": {"aspect_ratio": "16:9", "resolution": "2K"}, "output_path": str(out)}
    if loc.thread_url and loc.account_id:
        task.update(thread_url=loc.thread_url, assigned_account=loc.account_id, pin_account=True)
    await asyncio.to_thread(_update, project_id, location_id, lambda s: setattr(s, "status", "drawing"))
    try:
        result = await muse_call(task)
        got = Path(result.get("output_path") or "") if isinstance(result, dict) else Path()
        if not got.is_file():
            raise RuntimeError("Muse báo xong nhưng không có file ảnh")
        if got.resolve() != out.resolve():
            await asyncio.to_thread(shutil.copy2, got, out)
    except (RuntimeError, TimeoutError, OSError, ValueError) as e:
        err = e
        dirty = isinstance(err, TimeoutError) or "side chat" in str(err) or "THREAD_OPEN_FAILED" in str(err)

        def failed(s: LocationSheet) -> None:
            s.status, s.error = "failed", f"Muse không vẽ được ảnh chuẩn bối cảnh: {err}"
            if dirty:
                _clear_thread(s)   # chat có thể còn việc dở: lần sau mở chat mới
        logger.warning(f"Ảnh chuẩn bối cảnh {project_id}/{location_id} lỗi: {err}")
        return await asyncio.to_thread(_update, project_id, location_id, failed)

    def done(s: LocationSheet) -> None:
        s.status, s.error = "review", None
        s.plate_path = str(out)
        s.versions.append(str(out))
        s.thread_url = result.get("thread_url") or s.thread_url
        s.account_id = result.get("executed_by") or s.account_id
    return await asyncio.to_thread(_update, project_id, location_id, done)


def mark_draw_crashed(project_id: str, location_id: str, message: str) -> None:
    """Lỗi ngoài dự kiến khi vẽ: không để bối cảnh kẹt mãi ở "drawing"."""
    def change(s: LocationSheet) -> None:
        s.status, s.error = "failed", message
    _update(project_id, location_id, change)


def approve_plate(project_id: str, location_id: str) -> LocationSheet:
    def change(s: LocationSheet) -> None:
        if not (s.plate_path and Path(s.plate_path).is_file()):
            raise LocationError(f"Bối cảnh {s.name_vi} chưa có ảnh chuẩn để duyệt")
        s.status, s.error = "approved", None
    return _update(project_id, location_id, change)


def reject_plate(project_id: str, location_id: str, feedback: str) -> LocationSheet:
    fb = (feedback or "").strip()
    if not fb:
        raise LocationError("Ghi rõ ảnh chuẩn sai chỗ nào để Muse vẽ lại đúng chỗ đó")
    if len(fb) > FEEDBACK_MAX:
        raise LocationError(f"Ghi chú tối đa {FEEDBACK_MAX} ký tự")

    def change(s: LocationSheet) -> None:
        s.feedback.append(fb)
        s.status = "draft"
    return _update(project_id, location_id, change)


# --------------------------------------------------------------------------------- dùng khi tạo ảnh / video cảnh
def lock_line(design_en: str) -> str:
    return LOCK_LINE_EN + " ".join(design_en.split())


def plate_fits(scene_prompt: str) -> bool:
    """Ảnh chuẩn chỉ đính kèm khi khung hình thấy được bối cảnh (không phải cận cảnh mặt, đồ vật)."""
    return not CLOSE_SHOT.search(scene_prompt or "")


def scene_lock(project_id: str, scene_id: str, scene_prompt: str = "") -> Optional[dict]:
    """Gói khoá bối cảnh của một cảnh, hoặc None nếu cảnh không thuộc bối cảnh ĐÃ DUYỆT nào (hay dự án chưa có danh
    sách bối cảnh). Gói: location_id, name_vi, design_en, prompt_line (câu chèn vào prompt), plate_path (đường dẫn ảnh
    chuẩn nếu nên đính kèm, không thì None). File locations.json hỏng thì báo lỗi, không coi như không có khoá."""
    if not (is_safe_id(project_id) and is_safe_id(scene_id)):
        return None
    path = _existing_store_path(project_id)
    with _lock(project_id):
        text = safe_files.read_text(path)
    if not text:
        return None
    data = ProjectLocations.model_validate_json(text)
    loc = next((v for v in data.locations.values() if scene_id in v.scene_ids and v.status == "approved"), None)
    if loc is None:
        return None
    plate = Path(loc.plate_path) if loc.plate_path else None
    use_plate = plate is not None and plate.is_file() and is_within(plate, PROJECTS_DIR) and plate_fits(scene_prompt)
    return {"location_id": loc.location_id, "name_vi": loc.name_vi, "design_en": loc.design_en,
            "prompt_line": lock_line(loc.design_en),
            "plate_path": str(plate.resolve()) if use_plate and plate is not None else None}
