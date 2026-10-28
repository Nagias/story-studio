"""Quy tắc tóc nhân vật nữ cho phong cách đầu tròn (chủ dự án 28/10/2026: tóc phủ nhiều trên đầu, không chỉ chút ở gáy).

Offline: kế hoạch vụ án giả lưu bằng case_store vào thư mục tạm.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.case_adaptation_schemas import CaseAdaptationPlan, CaseBible, CaseEntity  # noqa: E402
from models.schemas import Project  # noqa: E402
from services import case_store, project_service  # noqa: E402
from services import character_sheets as cs  # noqa: E402
from services.character_sheets import CharacterSheet  # noqa: E402
from services.image_service import FEMALE_HAIR_RULE_EN, ROUND_HEAD_STYLES, STYLE_PRESETS  # noqa: E402

OLD_DESIGN = ("Appearance: a slender young woman.\nHAIR: dark wavy hair covers the WHOLE BACK HALF of the head, "
              "starting at the crown.")


def _project(style: str, pid: str = "proj_crime_hair01") -> Project:
    people = [CaseEntity(id="person_1", kind="person", real_names=["X"], role="victim", alias_vi="Nhã Uyên",
                         alias_en="Ya", gender="female", appearance_en="a slender young woman"),
              CaseEntity(id="person_2", kind="person", real_names=["Y"], role="investigator", alias_vi="Kiến Vĩ",
                         alias_en="Jian", gender="male", appearance_en="an elderly man")]
    plan = CaseAdaptationPlan(
        case_id=f"case_{pid[-6:]}", created_at="2026-10-28", model="fake", target_minutes=8, visual_style=style,
        bible=CaseBible(source_language="vi", culture="vn", title_vi="t", title_en="t", timeline=[], entities=people),
        parts=[], scenes=[])
    case_store.save_plan(plan)
    project = Project(id=pid, name="Vụ thử", style_preset=style, scenes=[], metadata={"case_id": plan.case_id})
    project_service.ensure_project_dirs(pid)
    project_service.save_project(project)
    return project


def test_exact_rule_text_from_owner_ruling():
    assert FEMALE_HAIR_RULE_EN == (
        "Female characters always have thick, full hair covering most of the top of the head: a generous mass of "
        "hair on the crown that frames the white face, then falls to the length given in the design; never a bald "
        "round head with only a little hair at the nape.")
    assert ROUND_HEAD_STYLES == ("horror_cartoon_2d",)


def test_round_head_style_suffix_has_female_hair_rule_and_others_do_not():
    assert FEMALE_HAIR_RULE_EN in STYLE_PRESETS["horror_cartoon_2d"]["prompt_suffix"]
    others = [k for k, p in STYLE_PRESETS.items() if k != "horror_cartoon_2d" and FEMALE_HAIR_RULE_EN in p["prompt_suffix"]]
    assert others == []


def test_hair_rule_only_for_female_in_round_head_project(isolated_projects_dir):
    project = _project("horror_cartoon_2d")
    assert cs.hair_rule_for(project, "person_1") == FEMALE_HAIR_RULE_EN
    assert cs.hair_rule_for(project, "person_2") == ""
    assert cs.hair_rule_for(project, "person_404") == ""
    anime = _project("anime", pid="proj_crime_hair02")
    assert cs.hair_rule_for(anime, "person_1") == ""


def test_draw_sheet_sends_hair_rule_for_female_only(isolated_projects_dir, tmp_path):
    import asyncio
    from PIL import Image
    project = _project("horror_cartoon_2d")
    ref = tmp_path / "ref.jpg"
    Image.new("RGB", (1280, 720), (40, 40, 60)).save(ref)
    prompts = []

    async def fake_muse(task):
        prompts.append(task["prompt"])
        Image.new("RGB", (2048, 1152), (200, 200, 200)).save(task["output_path"], "JPEG")
        return {"output_path": task["output_path"]}

    cs.load_cast(project.id)
    asyncio.run(cs.draw_sheet(project.id, "person_1", fake_muse, ref))
    asyncio.run(cs.draw_sheet(project.id, "person_2", fake_muse, ref))
    # Thiết kế mặc định chép phong cách vẽ (đã có câu quy tắc): nữ có đúng một lần, không lặp; nam không có dòng ép
    # riêng (câu trong phong cách chỉ nói về nhân vật nữ nên vô hại).
    assert prompts[0].count(FEMALE_HAIR_RULE_EN) == 1
    assert "This hair rule overrides" not in prompts[1]


def test_draw_sheet_old_design_gets_override_line(isolated_projects_dir, tmp_path):
    import asyncio
    from PIL import Image
    project = _project("horror_cartoon_2d")
    ref = tmp_path / "ref.jpg"
    Image.new("RGB", (1280, 720), (40, 40, 60)).save(ref)
    prompts = []

    async def fake_muse(task):
        prompts.append(task["prompt"])
        Image.new("RGB", (2048, 1152), (200, 200, 200)).save(task["output_path"], "JPEG")
        return {"output_path": task["output_path"]}

    cs.load_cast(project.id)
    cs.set_design(project.id, "person_1", OLD_DESIGN)        # thiết kế cũ, chưa có câu quy tắc
    asyncio.run(cs.draw_sheet(project.id, "person_1", fake_muse, ref))
    assert "This hair rule overrides any other hair placement in the design: " + FEMALE_HAIR_RULE_EN in prompts[0]


def test_sheet_prompt_adds_rule_once_and_says_it_wins():
    sheet = CharacterSheet(entity_id="person_1", name_vi="Nhã Uyên", design_en=OLD_DESIGN)
    plain = cs.sheet_prompt(sheet)
    p = cs.sheet_prompt(sheet, FEMALE_HAIR_RULE_EN)
    assert p.count(FEMALE_HAIR_RULE_EN) == 1
    assert "This hair rule overrides any other hair placement in the design: " + FEMALE_HAIR_RULE_EN in p
    assert FEMALE_HAIR_RULE_EN not in plain and "overrides" not in plain
    # thiết kế đã có sẵn câu quy tắc (vd lấy từ prompt_suffix): không chép lần hai
    again = CharacterSheet(entity_id="person_1", name_vi="Nhã Uyên", design_en=OLD_DESIGN + "\n" + FEMALE_HAIR_RULE_EN)
    assert cs.sheet_prompt(again, FEMALE_HAIR_RULE_EN).count(FEMALE_HAIR_RULE_EN) == 1
