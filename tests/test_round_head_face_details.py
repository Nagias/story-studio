"""Gặp 13/11/2026: thiết kế đã duyệt của vài nhân vật có chữ tả mặt thật ("deep sun-etched wrinkles", "weathered
features", "sunken cheeks") lấy từ bài báo; với phong cách đầu tròn, Muse vẽ mặt nhăn, mũi rõ khi khóc ở 9 cảnh của hai
vụ. Lúc ghép prompt (ảnh cảnh, lưới 9 ô, bản giao việc video) bỏ các vế tả mặt; thiết kế đã lưu không bị sửa."""
from models.schemas import Project
from services import character_sheets as cs
from services.prompt_rules import ROUND_HEAD_RULE_EN

MINH = ("Appearance: An East Asian man in his early 60s with thinning graying hair, deep sun-etched wrinkles, a stooped "
        "posture, wearing a faded blue cotton worker shirt and dark trousers.\n"
        "Facial expressions are allowed and encouraged, drawn with the same simple flat lines: short line eyebrows.\n"
        "The head always stays a big flat round white ball with dot eyes: never a realistic human face.")


def test_face_details_removed_but_age_hair_clothes_and_rules_kept():
    out = cs.without_face_details(MINH)
    first = out.splitlines()[0]
    assert "wrinkl" not in first and "sun-etched" not in first
    for keep in ("early 60s", "thinning graying hair", "stooped posture", "faded blue cotton worker shirt",
                 "dark trousers"):
        assert keep in first
    assert out.splitlines()[1:] == MINH.splitlines()[1:]          # câu quy tắc (có chữ "eyebrows", "dot eyes") giữ nguyên


def test_other_face_words():
    d = ("Appearance: An East Asian man in his late 30s with a gaunt face, sunken cheeks, greasy parted hair, and a lean "
         "restless posture, wearing an oversized windbreaker.")
    out = cs.without_face_details(d)
    assert "cheek" not in out and "gaunt" not in out and "greasy parted hair" in out and "windbreaker" in out
    d2 = "Appearance: A man in his late 40s with sharp resolute eyes, short crew-cut hair, a sturdy frame."
    assert "eyes" not in cs.without_face_details(d2) and "crew-cut" in cs.without_face_details(d2)


def test_only_round_head_styles_are_stripped():
    round_p = Project(id="proj_r1", name="x", style_preset="horror_cartoon_2d", scenes=[])
    other_p = Project(id="proj_r2", name="x", style_preset="cinematic", scenes=[])
    assert "wrinkl" not in cs.prompt_design(round_p, MINH).splitlines()[0]
    assert cs.prompt_design(other_p, MINH) == MINH


def test_round_head_rule_covers_old_people_crying():
    # một luật đầu tròn duy nhất (services/prompt_rules.py) cho ảnh, lưới, video: tuổi chỉ bằng tóc, dáng, quần áo
    assert "no wrinkles" in ROUND_HEAD_RULE_EN and "Age is shown only by hair" in ROUND_HEAD_RULE_EN
    assert "even when crying" in ROUND_HEAD_RULE_EN
