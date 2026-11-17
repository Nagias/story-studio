"""Prompt CUỐI gửi Muse không được chứa cặp luật cãi nhau, không luật nào bị cắt, và mỗi luật chỉ một lần.

Rà soát 17–18/11/2026 (dựng lại prompt thật vụ Khang Cúc Hoa): cùng một prompt video có "máy quay đứng yên" và "đổi góc
máy"; lưới 9 khung "chỉ cử động nhẹ, không cắt cảnh" trong khi bản giao việc đòi cử động mạnh và cắt giữa hai clip; luật
tóc mọi góc bị cắt cụt ở mốc 1.500 ký tự; năm phong cách mặc định khác nhau. Test cũ chỉ kiểm "có dòng chữ X" nên vẫn
xanh. Test này dựng prompt thật của từng đường (ảnh, video thoại, lưới, bản giao việc) qua đúng hàm đường thật dùng."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import config  # noqa: E402
from models.schemas import Project, Scene  # noqa: E402
from services import climax_video as cv  # noqa: E402
from services import dialogue_video as dv  # noqa: E402
from services import prompt_rules  # noqa: E402
from services.character_sheets import CharacterSheet  # noqa: E402
from services.climax_brief import BRIEF_MAX_CHARS, crowd_brief, landscape_brief, scene_brief  # noqa: E402

NARRATION = ("Thẩm Hạo Nhiên bước chậm vào giữa ruộng ngô, cúi xuống nhìn tấm bạt xanh. Anh giơ đèn pin soi quanh "
             "rồi quay đầu gọi đồng nghiệp. Cơn mưa đêm qua đã xoá gần hết dấu chân trên nền đất. Người ta tìm thấy "
             "chiếc dép của nạn nhân cách đó mười mét, lấm bùn và rách quai.")
IMAGE = ("Wide shot of a desolate summer cornfield under an overcast twilight sky; a middle-aged investigator in an "
         "olive-green uniform inspects the perimeter with a flashlight.")

# Cặp luật không bao giờ được đi cùng nhau trong một prompt (đọc chữ thường)
FORBIDDEN_PAIRS = [
    ("máy quay đứng yên", "đổi góc máy"),
    ("không lia", "lia máy chậm"),
    ("gentle movement", "chuyển động thật"),
    ("no scene cuts", "cú cắt giữa hai clip"),
    ("chỉ đổi nét mặt", "đổi nét mặt, khóc"),
]


def _project(style="horror_cartoon_2d"):
    scene = Scene(id="scene_011", order=11, text=NARRATION, image_prompt=IMAGE, duration=24.0,
                  metadata={"visual_kind": "image"})
    return Project(id="proj_rules01", name="Thử luật", style_preset=style, scenes=[scene]), scene


def _person(gender="male"):
    return CharacterSheet(entity_id="person_1", name_vi="Thẩm Hạo Nhiên", status="approved", gender=gender,
                          design_en="Appearance: A middle-aged man in his late 40s, short crew-cut hair, sturdy frame, "
                                    "dark olive-green police uniform jacket.\nDrawing style: "
                                    + prompt_rules.ROUND_HEAD_RULE_EN + "\n" + prompt_rules.ANGLE_RULE_EN)


def _all_prompts():
    project, scene = _project()
    segs = dv.plan_segments(scene.text, 24.0)
    dialogue = [dv.segment_prompt(project, scene, segs, k, None, False) for k in range(1, len(segs) + 1)]
    parts = cv.agent_parts(scene, 24.0)
    briefs = [scene_brief(project, scene, [_person()], 1, 24.0, "XONG-1", part=p, n_parts=len(parts))
              for p in parts]
    briefs += [landscape_brief(project, scene, 12.0, "XONG-2", None, False),
               crowd_brief(project, scene, 12.0, "XONG-3", None, False)]
    grid = cv.grid_prompt(scene, project, first_grid=True)
    return {"dialogue": dialogue, "brief": briefs, "grid": [grid]}


def test_no_prompt_carries_two_rules_that_contradict_each_other():
    for path, prompts in _all_prompts().items():
        for p in prompts:
            low = p.lower()
            for a, b in FORBIDDEN_PAIRS:
                assert not (a in low and b in low), f"{path}: '{a}' và '{b}' cùng một prompt"


def test_each_rule_appears_once_per_prompt():
    for path, prompts in _all_prompts().items():
        for p in prompts:
            assert p.count(prompt_rules.ROUND_HEAD_RULE_EN) <= 1, path
            assert p.count(prompt_rules.FEMALE_HAIR_RULE_EN) <= 1, path
            assert p.count("MÁY QUAY ĐỨNG YÊN") <= 1, path


def test_briefs_never_cut_a_rule_and_stay_short():
    for p in _all_prompts()["brief"]:
        assert len(p) <= BRIEF_MAX_CHARS, len(p)
        assert "Drawing style" not in p                          # phong cách không chép lại cho từng người
        # mọi câu luật dài đều kết thúc trọn vẹn (không bị cắt giữa câu như ANGLE_RULE_EN trước đây)
        for line in p.splitlines():
            if line.startswith("- ") and len(line) > 60:
                assert re.search(r"[.!?:)\"”]$", line.strip()), line[-60:]


def test_long_scene_is_split_into_jobs_that_leave_room_to_redo():
    _, scene = _project()
    parts = cv.agent_parts(scene, 24.0)
    assert len(parts) == 2 and all(p["seconds"] <= 15 for p in parts)


def test_single_default_style_everywhere():
    assert config.DEFAULT_STYLE == "horror_cartoon_2d"
    js = (ROOT / "backend" / "static" / "app.js").read_text(encoding="utf-8")
    m = re.search(r"const DEFAULT_STYLE_PRESET = '([a-z0-9_]+)';", js)
    assert m and m.group(1) == config.DEFAULT_STYLE
    assert "spartan_epic_mythology';" not in js and '|| "cinematic_realistic"' not in js
    from models import schemas
    assert schemas.Project(id="proj_x", name="x").style_preset == config.DEFAULT_STYLE


def test_style_negative_prompt_is_sent():
    from services.muse_image_task import image_task_fields
    task = image_task_fields("a cornfield", {"style_preset": "horror_cartoon_2d"})
    assert "realistic human face" in task["negative_prompt"] and "anime face" in task["negative_prompt"]


def test_shared_character_anchor_is_never_glued_into_the_prompt():
    from services import scene_prompt_preview as spp
    project, scene = _project()
    project = project.model_copy(update={"character_anchor": "an old samurai with a red cape"})
    assert "samurai" not in spp.base_image_prompt(project, scene)
    assert "samurai" not in cv.grid_prompt(scene, project, first_grid=True)
