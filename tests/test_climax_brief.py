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
from services.climax_brief import (AGENT_MAX_IMAGES, AGENT_MAX_VIDEOS, AGENT_PART_MAX_SEC,  # noqa: E402
                                   BRIEF_MAX_CHARS, NEW_SCENE_IMAGE_TAG, agent_parts, part_panels, scene_brief,
                                   target_seconds)
from services.prompt_rules import FEMALE_HAIR_RULE_EN  # noqa: E402

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
    assert (AGENT_MAX_VIDEOS, AGENT_MAX_IMAGES, AGENT_PART_MAX_SEC) == (6, 4, 15)
    assert NEW_SCENE_IMAGE_TAG == "ANH_CANH_MOI"


def test_target_seconds_bounds():
    assert target_seconds(3.2) == 5
    assert target_seconds(11.877) == 12
    assert target_seconds(14.2) == 15


def test_long_scene_is_split_so_each_muse_job_keeps_room_to_redo():
    """Chủ dự án 18/11/2026: cảnh dài chia nhiều việc, mỗi việc 12–15 giây (6 video, clip 3–6 giây: còn 2–3 lượt làm
    lại). Trước đây một việc phủ tới 24 giây: 18 báo cáo Muse KHÔNG ĐẠT vì hết ngân sách ở hai vụ."""
    scene = Scene(id="s", order=1, text=NARRATION + " " + NARRATION, metadata={"visual_kind": "video"})
    parts = agent_parts(scene, 24.0)
    assert len(parts) == 2 and all(p["seconds"] <= AGENT_PART_MAX_SEC + 1e-6 for p in parts)
    assert " ".join(p["text"] for p in parts) == " ".join(scene.text.split())
    assert part_panels(parts[0])[0] == 1 and part_panels(parts[1])[1] == 5     # 24 giây = ô 1–5
    one = agent_parts(Scene(id="t", order=2, text=NARRATION), 11.0)
    assert len(one) == 1


def test_brief_has_every_rule_and_ends_with_token(isolated_projects_dir):
    project, scene, nu, nam = _setup(isolated_projects_dir)
    b = scene_brief(project, scene, [nu, nam], grid_count=1, seconds=11.877, done_token=TOKEN)
    assert b.rstrip().splitlines()[-1].strip().endswith(TOKEN)
    for must in ["6 video", "4 ảnh", "Không clip nào", "xoay", "góc sau", "mỗi giây", "khung cuối", "mặt người",
                 "CHUYỂN ĐỘNG THẬT", "GÓC MÁY THEO CỬ ĐỘNG", "danh sách clip", NARRATION, nu.name_vi, nam.name_vi,
                 "ANH_CANH_MOI: có", "chỉ một video", "12 giây"]:
        assert must in b, must
    assert "WHOLE BACK HALF" in b and "Silver-streaked" in b      # thiết kế đã duyệt của từng người
    assert b.count(FEMALE_HAIR_RULE_EN) == 1                       # một người nữ -> một lần, nam không có


def test_brief_without_female_cast_has_no_override_line(isolated_projects_dir):
    project, scene, _, nam = _setup(isolated_projects_dir)
    assert "This hair rule overrides" not in scene_brief(project, scene, [nam], grid_count=1, seconds=8, done_token=TOKEN)


def test_brief_lists_attachments_in_order(isolated_projects_dir):
    project, scene, nu, _ = _setup(isolated_projects_dir)
    one = scene_brief(project, scene, [nu], grid_count=1, seconds=11, done_token=TOKEN)
    two = scene_brief(project, scene, [nu], grid_count=2, seconds=40, done_token=TOKEN)
    assert one.index("Ảnh 1") < one.index("Ảnh 2") < one.index("Ảnh 3")
    assert "Ảnh 4" not in one and "Ảnh 4" in two


def test_design_is_never_cut_and_style_not_repeated_per_person(isolated_projects_dir):
    """Trước 18/11/2026: thiết kế chép cả đoạn phong cách cho từng người rồi cắt ở 1.500 ký tự, cắt cụt luật tóc mọi góc.
    Nay chỉ phần ngoại hình, không cắt; luật đầu tròn có đúng một lần dù hai người."""
    from services.character_sheets import default_design
    from services.prompt_rules import ROUND_HEAD_RULE_EN
    project, scene, nu, nam = _setup(isolated_projects_dir)
    nu.design_en = "Appearance: " + "x" * 2000 + " CLOTHES: pale blue-grey blouse."
    entity = CaseEntity(id="person_2", kind="person", real_names=["Y"], role="investigator", alias_vi="Lương Kiến Vĩ",
                        alias_en="Jian", gender="male", appearance_en="an elderly man in a lab coat")
    nam.design_en = default_design(entity, "horror_cartoon_2d")
    b = scene_brief(project, scene, [nu, nam], grid_count=1, seconds=11, done_token=TOKEN)
    assert "x" * 2000 + " CLOTHES: pale blue-grey blouse." in b
    assert b.count(ROUND_HEAD_RULE_EN) == 1 and "Drawing style" not in b


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


def test_hair_rule_covers_every_female_in_round_head_scene(isolated_projects_dir):
    """Cảnh 41 (29/10/2026): cô gái trong cảnh không có bảng nhân vật nên bản giao việc không nhắc tóc của cô, ảnh cảnh
    vẫn đầu trọc. Phong cách đầu tròn: quy tắc tóc áp cho MỌI nhân vật nữ trong cảnh, ảnh cảnh có nữ đầu trọc thì vẽ lại."""
    project, scene, _, nam = _setup(isolated_projects_dir)
    b = scene_brief(project, scene, [nam], grid_count=1, seconds=20, done_token=TOKEN)
    assert FEMALE_HAIR_RULE_EN in b and "kể cả người không có trong bảng diễn viên" in b
    assert "đầu trọc" in b
    anime = project.model_copy(update={"style_preset": "anime"})
    assert FEMALE_HAIR_RULE_EN not in scene_brief(anime, scene, [nam], grid_count=1, seconds=20, done_token=TOKEN)


def test_real_brief_stays_within_length_budget(isolated_projects_dir):
    """Bản giao việc thật vụ Khang Cúc Hoa dài 7.000–8.600 ký tự (phong cách lặp cho từng người): Muse dễ bỏ qua cuối."""
    from services.character_sheets import default_design
    project, scene, nu, nam = _setup(isolated_projects_dir)
    for p, g in ((nu, "female"), (nam, "male")):
        e = CaseEntity(id=p.entity_id, kind="person", real_names=["Z"], role="x", alias_vi=p.name_vi, alias_en="z",
                       gender=g, appearance_en="a person in their 40s with short dark hair, wearing a grey work jacket")
        p.design_en = default_design(e, "horror_cartoon_2d")
    b = scene_brief(project, scene, [nu, nam], grid_count=1, seconds=14, done_token=TOKEN)
    assert len(b) <= BRIEF_MAX_CHARS, len(b)
