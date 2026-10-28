"""Bản giao việc nhiều bước cho Muse (services/climax_brief.py): khuôn trong code, không gọi LLM.

Đối chiếu: bản giao việc thí nghiệm 2 (28/10/2026, `.cache/thu-muse-28-lan2/`) đạt suốt 12 giây.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.case_adaptation_schemas import CaseAdaptationPlan, CaseBible, CaseEntity  # noqa: E402
from models.schemas import Project, Scene  # noqa: E402
from services import case_store, project_service  # noqa: E402
from services.character_sheets import CharacterSheet  # noqa: E402
from services.climax_brief import (AGENT_MAX_IMAGES, AGENT_MAX_SECONDS, AGENT_MAX_VIDEOS,  # noqa: E402
                                   NEW_SCENE_IMAGE_TAG, scene_brief, target_seconds)
from services.image_service import FEMALE_HAIR_RULE_EN  # noqa: E402

NARRATION = ("Khoảng hai giờ sáng, chiếc xe đỗ lại ven đường. Thẩm Nhã Uyên vội vã bước xuống rồi chạy nhanh lên "
             "lầu… Đó là thời khắc cuối cùng có nhân chứng nhìn thấy cô còn sống.")
TOKEN = "XONG-ab12cd34"


def _setup(isolated_projects_dir):
    people = [CaseEntity(id="person_1", kind="person", real_names=["X"], role="victim", alias_vi="Thẩm Nhã Uyên",
                         alias_en="Ya", gender="female", appearance_en="a slender young woman"),
              CaseEntity(id="person_2", kind="person", real_names=["Y"], role="investigator", alias_vi="Lương Kiến Vĩ",
                         alias_en="Jian", gender="male", appearance_en="an elderly man")]
    plan = CaseAdaptationPlan(
        case_id="case_brief1", created_at="2026-10-28", model="fake", target_minutes=8, visual_style="horror_cartoon_2d",
        bible=CaseBible(source_language="vi", culture="vn", title_vi="t", title_en="t", timeline=[], entities=people),
        parts=[], scenes=[])
    case_store.save_plan(plan)
    scene = Scene(id="scene_028", order=28, text=NARRATION, metadata={"visual_kind": "video"})
    project = Project(id="proj_crime_brief1", name="Vụ thử", style_preset="horror_cartoon_2d", scenes=[scene],
                      metadata={"case_id": plan.case_id})
    project_service.ensure_project_dirs(project.id)
    project_service.save_project(project)
    nu = CharacterSheet(entity_id="person_1", name_vi="Thẩm Nhã Uyên", status="approved",
                        design_en="HAIR: dark wavy hair covers the WHOLE BACK HALF of the head. CLOTHES: pale blue-grey blouse.")
    nam = CharacterSheet(entity_id="person_2", name_vi="Lương Kiến Vĩ", status="approved",
                         design_en="Silver-streaked hair, rimless spectacles, white lab coat.")
    return project, scene, nu, nam


def test_limits_match_spec():
    assert (AGENT_MAX_VIDEOS, AGENT_MAX_IMAGES, AGENT_MAX_SECONDS) == (6, 4, 24)
    assert NEW_SCENE_IMAGE_TAG == "ANH_CANH_MOI"


def test_target_seconds_bounds():
    assert target_seconds(3.2) == 5
    assert target_seconds(11.877) == 12
    assert target_seconds(24.0) == 24
    assert target_seconds(80) == 24


def test_brief_has_every_rule_and_ends_with_token(isolated_projects_dir):
    project, scene, nu, nam = _setup(isolated_projects_dir)
    b = scene_brief(project, scene, [nu, nam], grid_count=1, seconds=11.877, done_token=TOKEN)
    assert b.rstrip().splitlines()[-1].strip().endswith(TOKEN)
    for must in ["6 video", "4 ảnh", "không clip nào", "xoay", "góc sau", "mỗi giây", "khung cuối", "mặt người",
                 "chạy tại chỗ", "danh sách clip", NARRATION, nu.name_vi, nam.name_vi, "ANH_CANH_MOI: có",
                 "chỉ một video", "12 giây"]:
        assert must in b, must
    assert "WHOLE BACK HALF" in b and "Silver-streaked" in b      # thiết kế đã duyệt của từng người
    assert b.count(FEMALE_HAIR_RULE_EN) == 1                       # một người nữ -> một lần, nam không có


def test_brief_without_female_has_no_hair_rule(isolated_projects_dir):
    project, scene, _, nam = _setup(isolated_projects_dir)
    assert FEMALE_HAIR_RULE_EN not in scene_brief(project, scene, [nam], grid_count=1, seconds=8, done_token=TOKEN)


def test_brief_lists_attachments_in_order(isolated_projects_dir):
    project, scene, nu, _ = _setup(isolated_projects_dir)
    one = scene_brief(project, scene, [nu], grid_count=1, seconds=11, done_token=TOKEN)
    two = scene_brief(project, scene, [nu], grid_count=2, seconds=40, done_token=TOKEN)
    assert one.index("Ảnh 1") < one.index("Ảnh 2") < one.index("Ảnh 3")
    assert "Ảnh 4" not in one and "Ảnh 4" in two
    assert "24 giây" in two


def test_long_design_is_cut(isolated_projects_dir):
    project, scene, nu, _ = _setup(isolated_projects_dir)
    nu.design_en = "x" * 3000
    b = scene_brief(project, scene, [nu], grid_count=1, seconds=11, done_token=TOKEN)
    assert "x" * 1500 in b and "x" * 1501 not in b


def test_hair_rule_survives_default_design_and_long_approved_design(isolated_projects_dir):
    """Giám khảo 28/10/2026: thiết kế mặc định chép phong cách (có câu quy tắc tóc ở sau ký tự ~400); cắt 600 ký tự
    làm rơi câu quy tắc, mà dòng 'thắng' cũng không thêm. Thiết kế thật 920–1340 ký tự còn mất CLOTHES."""
    from services.character_sheets import default_design
    project, scene, _, _ = _setup(isolated_projects_dir)
    entity = CaseEntity(id="person_1", kind="person", real_names=["X"], role="victim", alias_vi="Thẩm Nhã Uyên",
                        alias_en="Ya", gender="female",
                        appearance_en="a slender East Asian woman in her early 20s with shoulder-length wavy dark hair, "
                                      "wearing a vintage pastel blouse and high-waisted slacks")
    nu = CharacterSheet(entity_id="person_1", name_vi="Thẩm Nhã Uyên", status="approved",
                        design_en=default_design(entity, "horror_cartoon_2d"))
    b = scene_brief(project, scene, [nu], grid_count=1, seconds=11, done_token=TOKEN)
    assert b.count(FEMALE_HAIR_RULE_EN) == 1 and "This hair rule overrides" in b
    long_design = "HEAD: round. " + "x" * 1000 + " CLOTHES: pale blue-grey blouse. FIXED in every view."
    nu2 = CharacterSheet(entity_id="person_1", name_vi="Thẩm Nhã Uyên", status="approved", design_en=long_design)
    b2 = scene_brief(project, scene, [nu2], grid_count=1, seconds=11, done_token=TOKEN)
    assert "CLOTHES: pale blue-grey blouse" in b2 and "FIXED in every view" in b2
