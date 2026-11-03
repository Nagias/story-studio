"""Tìm nhân vật của truyện chữ (luồng chung 03/11/2026: truyện chữ và vụ án cùng có danh sách nhân vật cố định).

Vụ án có người từ bảng tên của vụ (kế hoạch vụ án). Truyện chữ thì LLM đọc lời kể và prompt ảnh từng cảnh, trả mỗi nhân
vật: tên, giới tính, tuổi, vai, ngoại hình cố định (tiếng Anh, đủ dài để vẽ giống nhau) và các cảnh có mặt. Code kiểm
(id cảnh có thật, ngoại hình đủ chữ, tên không trùng, mỗi người ít nhất một cảnh) rồi ghi vào bảng nhân vật
(`character_sheets`): thiết kế mặc định ghép phong cách của dự án, nhân vật từng cảnh ghi vào `scene_cast`.

Truyện gốc (lưu khi tạo dự án, `story_source.txt`) gửi kèm để lấy đủ chi tiết ngoại hình mà lời review có thể đã lược
(gặp 03/11/2026: lời review bỏ "bộ ria bạc" của bác bảo vệ nên ngoại hình tìm được thiếu chi tiết đó).

Chạy lại: người đã có (cùng tên) giữ nguyên thiết kế nếu đã vẽ bảng hoặc chủ dự án đã sửa; người cũ không còn thấy mà
chưa vẽ bảng thì bỏ. Không import routers/ (LLM truyền vào được để test).
"""
import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Optional

from config import PROJECTS_DIR
from models.schemas import Project
from services import character_sheets as cs
from services import project_service, safe_files
from services.case_adaptation_llm import LLMCall, call_llm_json
from services.case_adaptation_steps import StepRejected, ask_validated

MIN_APPEARANCE_WORDS = 12      # như bảng tên vụ án: ngắn hơn thì Muse tự bịa phần còn lại, mỗi cảnh một kiểu
MAX_APPEARANCE_WORDS = 120
MAX_PEOPLE = 12
NAME_MAX = 60
TEXT_EXCERPT_CHARS = 260       # mỗi cảnh gửi LLM tối đa chừng này ký tự lời kể và prompt (dự án 80 cảnh ~ 45 nghìn ký tự)
PROMPT_EXCERPT_CHARS = 300
SOURCE_MAX_CHARS = 24000       # truyện gốc gửi kèm tối đa chừng này ký tự (ngoại hình thường tả ở đoạn đầu)
SOURCE_FILE = "story_source.txt"
GENDERS = ("male", "female", "other")
ROLES = ("main", "supporting", "other")

SYSTEM_PROMPT = """\
Bạn là trợ lý dựng hình cho video kể chuyện. Bạn đọc danh sách cảnh (lời kể và prompt ảnh) và lập danh sách NHÂN VẬT để
hoạ sĩ vẽ mỗi người giống hệt nhau ở mọi cảnh. Chỉ trả về đúng một JSON object, không thêm chữ nào."""


def eligible_scenes(project: Project) -> list:
    return [s for s in project.scenes if cs.is_drawn_scene(s) and (s.text or s.image_prompt or "").strip()]


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _name_key(name: str) -> str:
    return " ".join((name or "").lower().split())


def save_source(project_id: str, text: str) -> None:
    """Nơi duy nhất ghi truyện gốc của dự án truyện chữ (đọc lại khi tìm nhân vật)."""
    path = project_service.ensure_project_dirs(project_id) / SOURCE_FILE
    safe_files.write_text_atomic(path, text or "")


def load_source(project_id: str) -> str:
    return safe_files.read_text(PROJECTS_DIR / project_id / SOURCE_FILE) or ""


def analyze_prompt(project: Project, source: str = "") -> str:
    lines = []
    allowed = {s.id for s in eligible_scenes(project)}
    for i, s in enumerate(project.scenes, 1):
        if s.id not in allowed:
            continue
        text = " ".join((s.text or "").split())[:TEXT_EXCERPT_CHARS]
        prompt = " ".join((s.image_prompt or "").split())[:PROMPT_EXCERPT_CHARS]
        lines.append(f"- id {s.id} (cảnh #{i}) | LỜI KỂ: {text or '(trống)'} | PROMPT: {prompt or '(trống)'}")
    excerpt = " ".join((source or "").split())[:SOURCE_MAX_CHARS]
    source_block = (f"\nTRUYỆN GỐC (lấy đủ chi tiết ngoại hình mà lời kể có thể đã lược: tóc, râu, áo, màu sắc):\n"
                    f"{excerpt}\n" if excerpt else "")
    return f"""TASK: PEOPLE
Việc: lập danh sách mọi nhân vật NHÌN THẤY ĐƯỢC trong các cảnh (người được vẽ trong khung hình), để mỗi người có một
ngoại hình cố định dùng cho mọi cảnh.

CÁC CẢNH:
{chr(10).join(lines)}
{source_block}
YÊU CẦU
1. Mỗi nhân vật là một người cụ thể của câu chuyện (có tên, hoặc gọi theo vai nếu truyện không có tên, ví dụ "ông lão
   gác cổng"). Một người chỉ ghi một lần dù lời kể gọi bằng nhiều cách. Đám đông, người qua đường không ghi.
2. "name": tên đúng như lời kể gọi (tối đa {NAME_MAX} ký tự).
3. "gender": "male" | "female" | "other". "age_range": ví dụ "early 20s", "about 60". "role": "main" (nhân vật chính) |
   "supporting" | "other".
4. "appearance_en": tiếng Anh, {MIN_APPEARANCE_WORDS}–60 từ, tả ngoại hình CỐ ĐỊNH: dân tộc, tuổi, vóc dáng, kiểu tóc
   và màu tóc, râu, khuôn mặt, trang phục thường mặc, màu chủ đạo. Giữ ĐỦ mọi chi tiết ngoại hình truyện gốc nói tới;
   lấy thêm từ lời kể và prompt; chỗ các cảnh tả khác nhau thì
   chọn một cách và giữ cố định; truyện không nói thì tự đặt cho hợp vai và thời đại. KHÔNG ghi tên, KHÔNG tả hành động,
   KHÔNG tả nét vẽ (phong cách vẽ đã có riêng).
5. "scene_ids": đúng id các cảnh mà người đó xuất hiện trong khung hình (chép id ở danh sách trên). Người chỉ được nhắc
   tới mà không có mặt thì không tính cảnh đó.
6. Tối đa {MAX_PEOPLE} người, ưu tiên người xuất hiện nhiều cảnh. Không có ai thì trả "people": [].

Trả về đúng một JSON object:
{{"people": [{{"name": "...", "gender": "male", "age_range": "...", "role": "main", "appearance_en": "...", "scene_ids": ["scene_..."]}}]}}"""


def validate_people(raw: Any, project: Project) -> list[dict]:
    """Kiểm kết quả LLM; sai thì StepRejected (lý do gửi lại cho LLM viết lại)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("people"), list):
        raise StepRejected('Cần JSON object có khoá "people" là một mảng.')
    known = {s.id for s in eligible_scenes(project)}
    seen: set[str] = set()
    out: list[dict] = []
    for i, item in enumerate(raw["people"][:MAX_PEOPLE], 1):
        if not isinstance(item, dict):
            raise StepRejected(f"Phần tử {i} của people không phải object.")
        name = " ".join(str(item.get("name") or "").split())[:NAME_MAX]
        if not name:
            raise StepRejected(f"Người {i} thiếu name.")
        if _name_key(name) in seen:
            raise StepRejected(f'"{name}" được ghi hai lần: mỗi người chỉ ghi một lần, gộp các cảnh lại.')
        look = " ".join(str(item.get("appearance_en") or "").split())
        words = _words(look)
        if words < MIN_APPEARANCE_WORDS or words > MAX_APPEARANCE_WORDS:
            raise StepRejected(f"appearance_en của {name} có {words} từ: cần {MIN_APPEARANCE_WORDS}–60 từ tả dân tộc, "
                               "tuổi, vóc dáng, tóc, khuôn mặt, trang phục.")
        ids = item.get("scene_ids")
        if not isinstance(ids, list):
            raise StepRejected(f"{name}: scene_ids phải là mảng id cảnh.")
        ids = list(dict.fromkeys(str(x).strip() for x in ids))
        unknown = [x for x in ids if x not in known]
        if unknown:
            raise StepRejected(f"{name} có id cảnh không có trong danh sách: {', '.join(unknown[:6])}. Chỉ chép id ở "
                               "danh sách cảnh.")
        if not ids:
            raise StepRejected(f"{name} không có cảnh nào: chỉ ghi người xuất hiện trong ít nhất một cảnh.")
        gender = str(item.get("gender") or "").strip().lower()
        role = str(item.get("role") or "").strip().lower()
        seen.add(_name_key(name))
        out.append({"name": name, "gender": gender if gender in GENDERS else "other",
                    "age_range": " ".join(str(item.get("age_range") or "").split())[:40],
                    "role": role if role in ROLES else "other", "appearance_en": look, "scene_ids": ids})
    return out


def _apply(project: Project, found: list[dict]) -> cs.ProjectCast:
    with cs._lock(project.id):
        cast = cs.load_cast(project.id)
        by_name = {_name_key(s.name_vi): s for s in cast.characters.values()}
        n = max([int(m.group(1)) for k in cast.characters for m in [re.fullmatch(r"nv_(\d+)", k)] if m] + [0])
        kept: dict[str, cs.CharacterSheet] = {}
        for item in found:
            old = by_name.get(_name_key(item["name"]))
            design = cs.design_text(item["appearance_en"], item["gender"], item["age_range"], item["role"],
                                    project.style_preset)
            if old is not None:
                if not old.versions and old.status == "draft":   # chưa vẽ bảng: lấy ngoại hình mới tìm
                    old.design_en = design
                old.gender, old.role = item["gender"], item["role"]
                kept[old.entity_id] = old
                item["entity_id"] = old.entity_id
            else:
                n += 1
                eid = f"nv_{n}"
                kept[eid] = cs.CharacterSheet(entity_id=eid, name_vi=item["name"], role=item["role"], design_en=design,
                                              gender=item["gender"], source="story")
                item["entity_id"] = eid
        for eid, sheet in cast.characters.items():   # người cũ không còn thấy: giữ nếu đã vẽ bảng
            if eid not in kept and sheet.versions:
                kept[eid] = sheet
        cast.characters = kept
        for s in eligible_scenes(project):
            cast.scene_cast[s.id] = [it["entity_id"] for it in found if s.id in it["scene_ids"]]
        cast.analyzed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cast.analysis_error = None
        cs.save_cast(project.id, cast)
        return cast


async def analyze_people(project_id: str, llm: Optional[LLMCall] = None) -> cs.ProjectCast:
    """Tìm nhân vật bằng LLM (1 lần gọi, thêm lần thử lại khi kết quả sai luật) và ghi vào bảng nhân vật."""
    project = await asyncio.to_thread(cs._project, project_id)
    if cs.case_people(project):
        raise cs.CastError("Dự án vụ án lấy nhân vật từ bảng tên đã duyệt của vụ án, không cần tìm lại")
    if not eligible_scenes(project):
        raise cs.CastError("Dự án chưa có cảnh nào có lời kể hoặc prompt ảnh để tìm nhân vật")
    base = llm or call_llm_json

    async def call(_system: str, user: str, **kwargs: Any) -> Any:
        return await base(SYSTEM_PROMPT, user, **kwargs)

    source = await asyncio.to_thread(load_source, project_id)
    found = await ask_validated(analyze_prompt(project, source), lambda raw: validate_people(raw, project), llm=call,
                                temperature=0.2, step_label="tìm nhân vật")
    return await asyncio.to_thread(_apply, project, found)


def record_analysis_error(project_id: str, message: str) -> None:
    with cs._lock(project_id):
        cast = cs.load_cast(project_id)
        cast.analysis_error = message
        cs.save_cast(project_id, cast)
