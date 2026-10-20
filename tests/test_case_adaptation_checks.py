"""
Kiểm lọt tên thật, ngày tháng và tự áp tên hư cấu (case_adaptation_checks).

Chạy offline, không gọi LLM. Các test chính theo Review Focus 2: tên thật viết hoa toàn bộ,
bỏ dấu, hoặc chỉ là tên gọi vẫn bị bắt; chuỗi nằm trong một tên hư cấu thì không báo nhầm.
"""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.case_adaptation_schemas import (
    AdaptedScene,
    CaseAdaptationPlan,
    CaseBible,
    CaseEntity,
    CaseEvidence,
    CaseRelation,
    DISCLAIMER,
    SceneFlag,
)
from services import case_adaptation_checks as checks
from services.case_adaptation_checks import (
    ForbiddenName,
    apply_aliases,
    build_forbidden_names,
    check_plan,
    find_dates,
    find_unknown_names,
    fold,
    has_blocking_flags,
)


# ---------------------------------------------------------------- dữ liệu mẫu

def _entity(eid, real_names, alias_vi, alias_en, kind="person"):
    return CaseEntity(id=eid, kind=kind, real_names=real_names, alias_vi=alias_vi, alias_en=alias_en)


def _scene(order, **kw):
    base = dict(
        order=order,
        part_id="p1",
        narration_vi="Một đêm mưa, cả khu phố im lặng.",
        narration_en="One rainy night, the whole street fell silent.",
        visual_kind="image",
        image_prompt="A quiet wet street at night under a single streetlight, cinematic, wide shot.",
    )
    base.update(kw)
    return AdaptedScene(**base)


def _plan(scenes, entities=None, evidence=None, relations=None, title_vi="Đêm Không Ngủ", title_en="The Sleepless Night"):
    bible = CaseBible(
        source_language="vi",
        culture="vietnamese",
        title_vi=title_vi,
        title_en=title_en,
        entities=entities if entities is not None else [
            _entity("e1", ["Nguyễn Văn Hùng", "ông Hùng", "Hùng"], "Trịnh Quang Vũ", "Trinh Quang Vu"),
        ],
        timeline=[],
        evidence=evidence or [],
        relations=relations or [],
    )
    return CaseAdaptationPlan(
        case_id="case_test",
        created_at="2026-10-19T00:00:00",
        model="test-model",
        target_minutes=8,
        visual_style="noir",
        bible=bible,
        parts=[],
        scenes=scenes,
    )


# ---------------------------------------------------------------- fold

def test_fold_lowercases_and_strips_diacritics_including_d_stroke():
    assert fold("Nguyễn ĐÌNH Hùng") == "nguyen dinh hung"
    assert fold("Đặng Thuỳ Dương") == "dang thuy duong"
    assert fold("Liu Rongfu") == "liu rongfu"


def test_fold_is_stable_for_decomposed_input():
    decomposed = "Nguyễn Văn Hùng"  # NFD
    assert fold(decomposed) == "nguyen van hung"


# ---------------------------------------------------------------- apply_aliases / find_unknown_names

def test_leak_variants_are_caught():
    fb = [ForbiddenName("Nguyễn Văn Hùng", "e1", "Trịnh Quang Vũ", "Trinh Quang Vu")]
    for t in ["NGUYỄN VĂN HÙNG bước vào", "Nguyen Van Hung walked in", "ông Nguyễn Văn Hùng.", "NGUYEN VAN HUNG"]:
        new, replaced = apply_aliases(t, fb, "vi")
        assert "Hùng" not in new and "Hung" not in new and "HÙNG" not in new and "HUNG" not in new and replaced


def test_alias_language_follows_lang_argument():
    fb = [ForbiddenName("Nguyễn Văn Hùng", "e1", "Trịnh Quang Vũ", "Trinh Quang Vu")]
    new_vi, _ = apply_aliases("Nguyễn Văn Hùng bước vào", fb, "vi")
    new_en, _ = apply_aliases("Nguyễn Văn Hùng bước vào", fb, "en")
    assert new_vi == "Trịnh Quang Vũ bước vào"
    assert new_en == "Trinh Quang Vu bước vào"


def test_longest_real_name_wins_over_its_own_short_form():
    fb = [
        ForbiddenName("Hùng", "e1", "Vũ", "Vu"),
        ForbiddenName("Nguyễn Văn Hùng", "e1", "Trịnh Quang Vũ", "Trinh Quang Vu"),
    ]
    new, replaced = apply_aliases("Nguyễn Văn Hùng nói. Hùng im lặng.", fb, "vi")
    assert new == "Trịnh Quang Vũ nói. Vũ im lặng."
    assert replaced == ["Nguyễn Văn Hùng", "Hùng"]


def test_nothing_to_replace_returns_text_unchanged():
    fb = [ForbiddenName("Nguyễn Văn Hùng", "e1", "Trịnh Quang Vũ", "Trinh Quang Vu")]
    text = "Một đêm mưa, cả khu phố im lặng."
    assert apply_aliases(text, fb, "vi") == (text, [])


def test_word_boundary_does_not_cut_inside_longer_words():
    fb = [ForbiddenName("Hùng Dũng", "e1", "A B", "A B"), ForbiddenName("Vân Anh", "e2", "C D", "C D")]
    new, replaced = apply_aliases("Thanh Vân Anhxyz và HùngDũng", fb, "vi")
    assert new == "Thanh Vân Anhxyz và HùngDũng" and replaced == []


def test_alias_containing_real_fragment_not_flagged():
    fb = [ForbiddenName("Lâm", None, None, None), ForbiddenName("Vũ Đình Trọng", "e3", "Phan Đức Lâm", "Phan Duc Lam")]
    assert find_unknown_names("Phan Đức Lâm im lặng.", fb, ["Phan Đức Lâm"]) == []


def test_alias_containing_real_fragment_is_not_rewritten_and_not_double_replaced():
    fb = [
        ForbiddenName("Lâm", "e5", "Quang Huy", "Quang Huy"),
        ForbiddenName("Vũ Đình Trọng", "e3", "Phan Đức Lâm", "Phan Duc Lam"),
    ]
    text = "Phan Đức Lâm im lặng."
    assert apply_aliases(text, fb, "vi") == (text, [])
    # nhưng "Lâm" đứng riêng vẫn bị thay
    new, replaced = apply_aliases("Phan Đức Lâm gặp Lâm.", fb, "vi")
    assert new == "Phan Đức Lâm gặp Quang Huy." and replaced == ["Lâm"]


def test_real_fragment_outside_alias_is_still_flagged():
    fb = [ForbiddenName("Lâm", None, None, None), ForbiddenName("Vũ Đình Trọng", "e3", "Phan Đức Lâm", "Phan Duc Lam")]
    assert find_unknown_names("Phan Đức Lâm gặp Lâm.", fb, ["Phan Đức Lâm"]) == ["Lâm"]


def test_find_unknown_names_matches_folded_and_uppercase():
    fb = [ForbiddenName("Trần Quang Minh", None, None, None)]
    assert find_unknown_names("TRAN QUANG MINH đã khai", fb, []) == ["Trần Quang Minh"]
    assert find_unknown_names("Ông Tran Quang Minh đã khai", fb, []) == ["Trần Quang Minh"]
    assert find_unknown_names("Một người lạ đã khai", fb, []) == []
    # Viết thường cả tên thì là cụm từ thường, không phải tên riêng (xem các test viết hoa bên dưới).
    assert find_unknown_names("Ông trần quang minh đã khai", fb, []) == []


def test_alias_identical_to_real_name_is_not_a_shield():
    # LLM đặt alias trùng tên thật thì không được coi là "đã thay": vẫn phải bị bắt.
    fb = [ForbiddenName("Nguyễn Văn Hùng", "e1", "Nguyễn Văn Hùng", "Nguyen Van Hung")]
    assert find_unknown_names("Nguyễn Văn Hùng bước vào", fb, ["Nguyễn Văn Hùng"]) == ["Nguyễn Văn Hùng"]


def test_short_single_syllable_names_are_ignored():
    fb = [ForbiddenName("Lê", "e1", "An", "An"), ForbiddenName("Vy", None, None, None)]
    assert apply_aliases("Lê và Vy đi chợ", fb, "vi") == ("Lê và Vy đi chợ", [])
    assert find_unknown_names("Lê và Vy đi chợ", fb, []) == []


def test_single_syllable_name_does_not_rewrite_common_words():
    # "Lâm" khi bỏ dấu thành "lam", trùng "làm"/"lắm"; không được thay nhầm từ thường.
    fb = [ForbiddenName("Lâm", "e1", "Quang Huy", "Quang Huy")]
    text = "Anh ấy làm việc rất lắm. Làm sao đây?"
    assert apply_aliases(text, fb, "vi") == (text, [])
    new, replaced = apply_aliases("Ông Lâm bước vào. LÂM im lặng. Lam nói.", fb, "vi")
    assert new == "Ông Quang Huy bước vào. Quang Huy im lặng. Quang Huy nói."
    assert replaced == ["Lâm"]


STREET = [ForbiddenName("Lê Lợi", "e1", "Thanh Lam", "Thanh Lam"), ForbiddenName("Tân Hải", "e2", "Hải Yến", "Hai Yen")]


@pytest.mark.parametrize("text", [
    "Một bóng người lẻ loi đứng trong mưa.",
    "Một bóng người LẺ LOI đứng trong mưa.",
    "Cảnh tàn hại sau trận bão.",
    "Ông ta sống lẻ loi, tàn hại cả đời mình.",
    "Lê Loi và Le Lợi",           # lẫn dấu: không phải cách viết nào của tên thật
    "lê lợi", "le loi", "đường le loi", "Lê lợi",     # chữ của tên viết thường: cụm từ thường, không phải tên riêng
])
def test_multi_word_name_is_not_matched_inside_ordinary_words_that_fold_the_same(text):
    assert apply_aliases(text, STREET, "vi") == (text, [])
    assert find_unknown_names(text, STREET, []) == []


@pytest.mark.parametrize("text", [
    "Lê Lợi", "LÊ LỢI", "Le Loi", "LE LOI", "Đường Lê Lợi", "đường Le Loi", "Số 5 Lê  Lợi.",
])
def test_multi_word_name_is_matched_with_same_diacritics_or_without_any(text):
    assert find_unknown_names(text, STREET, []) == ["Lê Lợi"]
    new, replaced = apply_aliases(text, STREET, "vi")
    assert replaced == ["Lê Lợi"] and "Thanh Lam" in new and "Lợi" not in new and "Loi" not in new


def test_check_plan_keeps_ordinary_words_and_replaces_the_real_street():
    ents = [_entity("e1", ["Lê Lợi"], "Thanh Lam", "Thanh Lam", kind="place"),
            _entity("e2", ["Tân Hải"], "Hải Yến", "Hai Yen", kind="place")]
    plan = _plan([_scene(1, narration_vi="Một bóng người lẻ loi, cảnh tàn hại.", narration_en="A lonely figure."),
                  _scene(2, narration_vi="Nhà ở đường Lê Lợi, gần cảng Tân Hải.", narration_en="On LE LOI street.")],
                 entities=ents)
    checked = check_plan(plan, "")
    assert checked.scenes[0].narration_vi == "Một bóng người lẻ loi, cảnh tàn hại."
    assert checked.scenes[0].flags == []
    assert checked.scenes[1].narration_vi == "Nhà ở đường Thanh Lam, gần cảng Hải Yến."
    assert checked.scenes[1].narration_en == "On Thanh Lam street."
    assert not has_blocking_flags(checked)
    assert all("lẻ loi" not in w and "tàn hại" not in w for w in checked.warnings)


def test_old_and_new_tone_placement_are_the_same_spelling():
    fb = [ForbiddenName("Lê Thuý Hoà", "e1", "An Nhiên", "An Nhien"), ForbiddenName("Hoà", "e2", "Bình", "Binh")]
    for text in ["Lê Thuý Hoà", "Lê Thúy Hòa", "LÊ THÚY HÒA"]:
        assert apply_aliases(text, fb, "vi") == ("An Nhiên", ["Lê Thuý Hoà"])
    assert find_unknown_names("Cô Hòa bước vào, rồi Hoà đi.", fb, []) == ["Hoà"]
    assert apply_aliases("Cô Hòa bước vào.", fb, "vi") == ("Cô Bình bước vào.", ["Hoà"])


# Tên thật mà bỏ dấu thì trùng một danh từ chung: chỗ viết đúng dấu danh từ chung không phải là tên.
COLLIDING = [ForbiddenName("Hưng Thu", "e1", "Lê Minh", "Le Minh"),
             ForbiddenName("Gia Định", "e2", "Phú An", "Phu An")]


@pytest.mark.parametrize("text", [
    "Cảnh sát chưa tìm ra hung thủ.",
    "Hung thủ vẫn lẩn trốn.",
    "Cả gia đình ông đều có mặt.",
    "GIA ĐÌNH nạn nhân im lặng.",
])
def test_generic_term_text_is_not_a_folded_real_name(text):
    assert apply_aliases(text, COLLIDING, "vi") == (text, [])
    assert find_unknown_names(text, COLLIDING, []) == []


def test_colliding_real_names_are_still_replaced_and_flagged():
    new, replaced = apply_aliases("Hưng Thu đã khai ở Bệnh viện Gia Định, trước mặt gia đình.", COLLIDING, "vi")
    assert new == "Lê Minh đã khai ở Bệnh viện Phú An, trước mặt gia đình."
    assert replaced == ["Hưng Thu", "Gia Định"]
    assert find_unknown_names("HUNG THU said nothing.", COLLIDING, []) == ["Hưng Thu"]   # tên viết không dấu
    assert find_unknown_names("Ông Hưng Thu, hung thủ?", COLLIDING, ["Lê Minh"]) == ["Hưng Thu"]


def test_check_plan_leaves_generic_terms_alone_when_real_names_collide():
    ents = [_entity("e1", ["Hưng Thu"], "Lê Minh", "Le Minh"),
            _entity("e2", ["Gia Định"], "Phú An", "Phu An", kind="place")]
    clean = "Cả gia đình ông đều có mặt, nhưng cảnh sát chưa tìm ra hung thủ."
    named = "Hưng Thu lớn lên ở Gia Định."
    plan = _plan([_scene(1, narration_vi=clean), _scene(2, narration_vi=named)], entities=ents)
    checked = check_plan(plan, "")
    assert checked.scenes[0].narration_vi == clean and checked.scenes[0].flags == []
    assert checked.scenes[1].narration_vi == "Lê Minh lớn lên ở Phú An."
    assert all("cảnh 1 " not in w for w in checked.warnings)
    assert len(checked.warnings) == 2 and not has_blocking_flags(checked)


# ---------------------------------------------------------------- quy tắc chung "nhận chỗ khớp này không?"

@pytest.mark.parametrize("span, name, ok", [
    ("Nam", "Nam", True),
    ("Năm", "Nam", False),                    # khác dấu: từ khác
    ("nam", "Nam", False),                    # tên một âm tiết phải viết hoa chữ đầu
    ("Hung", "Hùng", True),                   # không dấu
    ("Hùng", "Hưng", False),
    ("Hòa Bình", "Hoà Bình", True),           # dấu thanh kiểu cũ/mới
    ("HOA BINH", "Hòa Bình", True),
    ("hòa bình", "Hòa Bình", False),          # viết thường: cụm từ thường
    ("Hòa bình", "Hòa Bình", False),          # chữ đầu câu viết hoa, chữ sau viết thường
    ("cảng Tân Hải", "Cảng Tân Hải", True),   # chữ chỉ loại địa danh đứng đầu được viết thường
    ("đường Lê Lợi", "Đường Lê Lợi", True),
    ("cảng tân hải", "Cảng Tân Hải", False),  # phần tên riêng vẫn phải viết hoa
    ("Tan Hai port", "Tan Hai Port", True),   # chữ chỉ loại đứng cuối (tiếng Anh) được viết thường
    ("ông Hùng", "ông Hùng", True),
    ("ông hùng", "ông Hùng", False),
])
def test_accept_match_spelling_and_capitals(span, name, ok):
    assert checks.accept_match(span, 0, len(span), name) is ok


def test_accept_match_skips_a_span_inside_a_correctly_spelled_generic_term():
    text = "Hung thủ vẫn lẩn trốn, còn Hùng vẫn chờ."
    assert checks.accept_match(text, 0, 4, "Hùng") is False                  # "Hung" nằm trong "Hung thủ"
    start = text.index("Hùng")
    assert checks.accept_match(text, start, start + 4, "Hùng") is True
    shouty = "HUNG THU vẫn lẩn trốn."                                  # không dấu: không phải danh từ chung "hung thủ"
    assert checks.accept_match(shouty, 0, 8, "Hưng Thu") is True


def test_single_syllable_real_name_is_not_found_inside_a_generic_term():
    fb = [ForbiddenName("Hùng", "e1", "Vũ", "Vu")]
    text = "Hung thủ vẫn lẩn trốn."
    assert apply_aliases(text, fb, "vi") == (text, [])
    assert find_unknown_names(text, fb, []) == []


# ---------------------------------------------------------------- hai tên thật trùng nhau khi bỏ dấu

HUNG_TWO = [_entity("e1", ["Nguyễn Văn Hùng", "Hùng"], "Trịnh Quang Vũ", "Trinh Quang Vu"),
            _entity("e2", ["Nguyễn Văn Hưng", "Hưng"], "Lê Minh Tâm", "Le Minh Tam")]


def test_build_forbidden_names_keeps_real_names_that_differ_only_in_diacritics():
    fb = build_forbidden_names(_plan([_scene(1)], entities=HUNG_TWO).bible, "")
    assert [(f.real, f.entity_id) for f in fb] == [
        ("Nguyễn Văn Hùng", "e1"), ("Hùng", "e1"), ("Nguyễn Văn Hưng", "e2"), ("Hưng", "e2")]


def test_real_names_that_fold_equal_each_get_their_own_alias():
    fb = build_forbidden_names(_plan([_scene(1)], entities=HUNG_TWO).bible, "")
    text = "Nguyễn Văn Hưng bước vào, Nguyễn Văn Hùng ở lại. Hưng nhìn Hùng."
    assert apply_aliases(text, fb, "vi") == (
        "Lê Minh Tâm bước vào, Trịnh Quang Vũ ở lại. Lê Minh Tâm nhìn Trịnh Quang Vũ.",
        ["Nguyễn Văn Hưng", "Nguyễn Văn Hùng", "Hưng", "Hùng"])
    assert find_unknown_names("Hưng bước vào.", fb, []) == ["Hưng"]
    assert find_unknown_names("NGUYỄN VĂN HƯNG bước vào.", fb, []) == ["Nguyễn Văn Hưng"]


def test_unaccented_name_shared_by_two_entities_uses_the_first_entity_and_is_marked_ambiguous():
    fb = build_forbidden_names(_plan([_scene(1)], entities=HUNG_TWO).bible, "")
    new, replaced = apply_aliases("Nguyen Van Hung walked in. Hung said nothing.", fb, "en")
    assert new == "Trinh Quang Vu walked in. Trinh Quang Vu said nothing."
    matches = checks.find_name_matches("Nguyen Van Hung walked in.", fb, [])
    assert len(matches) == 1 and matches[0].ambiguous
    assert matches[0].name.entity_id == "e1"
    assert {f.entity_id for f in matches[0].candidates} == {"e1", "e2"}
    # Viết đúng dấu thì không mơ hồ.
    assert not checks.find_name_matches("Nguyễn Văn Hưng bước vào.", fb, [])[0].ambiguous


def test_check_plan_replaces_each_accented_spelling_and_warns_about_the_ambiguous_one():
    plan = _plan([_scene(2, narration_vi="Nguyễn Văn Hưng bước vào, còn Hùng đứng chờ.",
                          narration_en="Nguyen Van Hung walked in; Hung said nothing.")], entities=HUNG_TWO)
    checked = check_plan(plan, "")
    scene = checked.scenes[0]
    assert scene.narration_vi == "Lê Minh Tâm bước vào, còn Trịnh Quang Vũ đứng chờ."
    assert scene.narration_en == "Trinh Quang Vu walked in; Trinh Quang Vu said nothing."
    assert scene.flags == [] and not has_blocking_flags(checked)       # mơ hồ không chặn tạo dự án
    notes = [w for w in checked.check_warnings if "cảnh 2" in w]
    assert len(notes) == 1 and "narration_en" in notes[0] and "Trinh Quang Vu" in notes[0]
    for real in ("Hùng", "Hưng", "Hung", "HUNG"):
        assert real not in notes[0]                                    # không nêu tên thật
    assert not any("narration_en" in w for w in checked.warnings)      # không ghi đoán tên thật vào danh sách bền
    assert any("'Nguyễn Văn Hưng' bằng 'Lê Minh Tâm'" in w for w in checked.warnings)


def test_unaccented_name_shared_by_two_spellings_of_one_entity_is_not_ambiguous():
    ents = [_entity("e1", ["Nguyễn Văn Hùng", "Nguyễn Văn Hưng"], "Trịnh Quang Vũ", "Trinh Quang Vu")]
    checked = check_plan(_plan([_scene(1, narration_en="Nguyen Van Hung left.")], entities=ents), "")
    assert checked.scenes[0].narration_en == "Trinh Quang Vu left."
    assert checked.check_warnings == [] and not has_blocking_flags(checked)


def test_regex_name_differing_only_in_diacritics_from_an_entity_name_is_still_forbidden():
    source = "Nguyễn Văn Hùng đi cùng em trai là Nguyễn Văn Hưng. Nguyen Van Hung bỏ chạy."
    reals = [f.real for f in build_forbidden_names(_plan([_scene(1)]).bible, source)]
    assert "Nguyễn Văn Hưng" in reals
    assert "Nguyen Van Hung" not in reals         # không dấu: đã nằm trong cách viết của tên thật "Nguyễn Văn Hùng"
    checked = check_plan(_plan([_scene(1, narration_vi="Nguyễn Văn Hưng đứng ở cổng.")]), source)
    assert [(f.kind, f.field) for f in checked.scenes[0].flags] == [("unknown_name", "narration_vi")]


# ---------------------------------------------------------------- tên dài bị loại không che tên ngắn

def test_longer_name_rejected_by_spelling_does_not_hide_a_shorter_exact_one():
    fb = [ForbiddenName("Lê Lợi", "e1", "Thanh Lam", "Thanh Lam"), ForbiddenName("Lê Lợi Hùng", "e2", "Bá Tùng", "Ba Tung")]
    assert apply_aliases("Lê Lợi hưng phấn kể lại.", fb, "vi") == ("Thanh Lam hưng phấn kể lại.", ["Lê Lợi"])
    assert find_unknown_names("Lê Lợi hưng phấn kể lại.", fb, []) == ["Lê Lợi"]

    fb2 = [ForbiddenName("Hùng", "e1", "Vũ", "Vu"), ForbiddenName("Hùng Anh", "e2", "Tuấn Kiệt", "Tuan Kiet")]
    assert apply_aliases("Hùng ánh mắt lạnh lùng.", fb2, "vi") == ("Vũ ánh mắt lạnh lùng.", ["Hùng"])
    assert find_unknown_names("Hùng ánh mắt lạnh lùng.", fb2, []) == ["Hùng"]
    # tên dài viết đúng vẫn thắng tên ngắn nằm trong nó
    assert apply_aliases("Hùng Anh gặp Hùng.", fb2, "vi") == ("Tuấn Kiệt gặp Vũ.", ["Hùng Anh", "Hùng"])


def test_check_plan_replaces_the_short_name_when_the_long_one_is_misspelled():
    ents = [_entity("e1", ["Lê Lợi"], "Thanh Lam", "Thanh Lam", kind="place"),
            _entity("e2", ["Lê Lợi Hùng"], "Bá Tùng", "Ba Tung")]
    checked = check_plan(_plan([_scene(1, narration_vi="Lê Lợi hưng phấn kể lại.")], entities=ents), "")
    assert checked.scenes[0].narration_vi == "Thanh Lam hưng phấn kể lại."
    assert not has_blocking_flags(checked)


# ---------------------------------------------------------------- tên nhiều chữ phải viết hoa

PEACE = [ForbiddenName("Hòa Bình", "e1", "Thanh Sơn", "Thanh Son")]


@pytest.mark.parametrize("text", [
    "Họ mơ một cuộc sống hòa bình.", "Hòa bình đã trở lại.", "cuộc sống hoà bình", "sống hoa binh",
])
def test_multi_word_name_written_in_lowercase_is_an_ordinary_phrase(text):
    assert apply_aliases(text, PEACE, "vi") == (text, [])
    assert find_unknown_names(text, PEACE, []) == []


@pytest.mark.parametrize("text", ["Hòa Bình", "HÒA BÌNH", "Hoa Binh", "HOA BINH", "Hoà Bình"])
def test_multi_word_name_in_title_case_or_capitals_is_replaced(text):
    assert apply_aliases(f"Họ về {text} sống.", PEACE, "vi") == ("Họ về Thanh Sơn sống.", ["Hòa Bình"])


@pytest.mark.parametrize("text", ["Bình minh lên.", "thành công rồi", "Anh ấy rất trung thành."])
def test_names_that_are_also_common_phrases_are_kept_in_lowercase(text):
    fb = [ForbiddenName("Bình Minh", "e1", "A Bê", "A Be"), ForbiddenName("Thành Công", "e2", "Xê Đê", "Xe De"),
          ForbiddenName("Trung Thành", "e3", "Ê Ép", "E Ep")]
    assert apply_aliases(text, fb, "vi") == (text, [])


def test_lowercase_second_word_is_not_part_of_the_name():
    fb = [ForbiddenName("Lâm", "e1", "Quang Huy", "Quang Huy"), ForbiddenName("Lâm Đồng", "e2", "Đồi Mây", "Doi May")]
    assert apply_aliases("Lâm đồng ý về Lâm Đồng.", fb, "vi") == ("Quang Huy đồng ý về Đồi Mây.", ["Lâm", "Lâm Đồng"])


def test_place_type_word_in_lowercase_still_matches_the_real_place():
    fb = [ForbiddenName("Cảng Tân Hải", "e1", "Cảng Hải Yến", "Hai Yen Port"),
          ForbiddenName("Đường Lê Lợi", "e2", "Đường Thanh Lam", "Thanh Lam Street")]
    new, replaced = apply_aliases("Xe dừng ở cảng Tân Hải, gần đường Lê Lợi.", fb, "vi")
    assert new == "Xe dừng ở Cảng Hải Yến, gần Đường Thanh Lam." and replaced == ["Cảng Tân Hải", "Đường Lê Lợi"]


def test_any_case_also_matches_names_written_in_lowercase():
    # Dùng để ẩn tên thật trong thông báo lỗi (case_redact): ẩn thừa không hại gì, ẩn thiếu thì lọt tên.
    fb = [ForbiddenName("Nguyễn Văn Hùng", "e1", "[ẩn]", "[ẩn]"), ForbiddenName("Lâm", "e2", "[ẩn]", "[ẩn]")]
    text = "tóm tắt quá ngắn: 'nguyễn văn hùng và lâm đi làm'"
    assert apply_aliases(text, fb, "vi")[0] == text
    assert apply_aliases(text, fb, "vi", any_case=True)[0] == "tóm tắt quá ngắn: '[ẩn] và [ẩn] đi làm'"


def test_check_plan_leaves_the_common_phrase_and_replaces_the_place():
    ents = [_entity("e1", ["Hòa Bình"], "Thanh Sơn", "Thanh Son", kind="place")]
    plan = _plan([_scene(1, narration_vi="Họ mơ một cuộc sống hòa bình ở Hòa Bình.")], entities=ents)
    checked = check_plan(plan, "")
    assert checked.scenes[0].narration_vi == "Họ mơ một cuộc sống hòa bình ở Thanh Sơn."
    assert checked.scenes[0].flags == []


# ---------------------------------------------------------------- con số nhận dạng, dạng tên Việt trong lời Anh

def test_identifying_numbers_skip_debts_money_and_quantities():
    source = ("Ông Trọng nợ 50 triệu đồng, nhà ở số 88 Đường Lê Lợi. Tổng số 30 người có mặt, số 12 ngày sau, "
              "chạy số 45 km. Phòng 12A, No. 7 Main Street.")
    assert checks.identifying_numbers(source) == {"88"}
    assert checks.identifying_numbers("He lived at No. 17 and owed no 25 dollars.") == {"17"}


def test_find_identifying_numbers_keeps_amounts_times_and_ages():
    ids = {"88", "14"}
    assert checks.find_identifying_numbers("Hắn nợ 88 triệu, lúc 14 giờ, cậu bé 14 tuổi, 14 ngày sau.", ids) == []
    assert checks.find_identifying_numbers("Căn nhà số 88 vẫn sáng đèn, 88 people waited.", ids) == ["88"]


def test_check_plan_warns_about_identifying_numbers_left_in_narration():
    source = "Kho bãi ở số 88 Đường Lê Lợi."
    plan = _plan([_scene(4, narration_vi="Căn nhà số 88 vẫn sáng đèn.", narration_en="At 88 the lights were on.")])
    checked = check_plan(plan, source)
    notes = [w for w in checked.check_warnings if "cảnh 4" in w and "'88'" in w]
    assert len(notes) == 2 and any("narration_vi" in w for w in notes) and any("narration_en" in w for w in notes)
    assert not has_blocking_flags(checked)                             # chỉ cảnh báo, không chặn
    assert check_plan(_plan([_scene(4, narration_vi="Hắn nợ 88 triệu đồng.")]), source).check_warnings == []


def test_check_plan_warns_about_vietnamese_alias_form_in_english_narration():
    ents = [_entity("e1", ["Lưu Vĩnh Phúc"], "Lưu Vinh Phú", "Liu Rongfu"),
            _entity("e2", ["Cảng Tân Hải"], "Cảng Hải Yến", "Hai Yen Port", kind="place")]
    plan = _plan([_scene(3, narration_en="Luu Vinh Phu walked to Cang Hai Yen alone.")], entities=ents)
    checked = check_plan(plan, "")
    notes = [w for w in checked.check_warnings if "cảnh 3" in w and "narration_en" in w]
    assert len(notes) == 2
    assert any("'Lưu Vinh Phú'" in w and "'Liu Rongfu'" in w for w in notes)
    assert any("'Cảng Hải Yến'" in w and "'Hai Yen Port'" in w for w in notes)
    assert not any("Lưu Vĩnh Phúc" in w for w in checked.check_warnings)
    assert not has_blocking_flags(checked)
    clean = _plan([_scene(3, narration_en="Liu Rongfu walked to Hai Yen Port alone.")], entities=ents)
    assert check_plan(clean, "").check_warnings == []


# ---------------------------------------------------------------- find_dates

def test_dates_found_but_times_kept():
    assert find_dates("Đêm ngày 15 tháng 10 năm 2021, lúc 23:30") == ["ngày 15 tháng 10 năm 2021"]
    assert find_dates("On October 7, 2014 at 02:21") == ["October 7, 2014"]
    assert find_dates("Cuộc gọi lúc 02:21, ba ngày sau") == []
    assert find_dates("giữa thập niên 2010") == []


def test_year_alone_flagged():
    assert find_dates("năm 2014")
    assert find_dates("in 2014")


def test_vietnamese_date_forms():
    assert find_dates("Vụ việc xảy ra ngày 7 tháng 10") == ["ngày 7 tháng 10"]
    assert find_dates("Vụ việc xảy ra 7 tháng 10") == ["7 tháng 10"]
    assert find_dates("Vụ việc xảy ra ngày 10/7") == ["10/7"]
    assert find_dates("Sinh ngày 07-10-1985") == ["07-10-1985"]
    assert find_dates("NGÀY 15 THÁNG 10 NĂM 2021") == ["NGÀY 15 THÁNG 10 NĂM 2021"]
    assert find_dates("ngay 15 thang 10 nam 2021") == ["ngay 15 thang 10 nam 2021"]


def test_english_date_forms():
    assert find_dates("It happened on Oct 7") == ["Oct 7"]
    assert find_dates("It happened on Oct. 7th, 2014.") == ["Oct. 7th, 2014"]
    assert find_dates("It happened on 7 October 2014") == ["7 October 2014"]
    assert find_dates("It happened on the 7th of October") == ["7th of October"]
    assert find_dates("It happened in October 2014") == ["October 2014"]
    assert find_dates("Back in 1998 he moved away") == ["in 1998"]
    assert find_dates("Sometime around 2003, he vanished") == ["2003"]


def test_decades_and_relative_expressions_are_kept():
    for text in [
        "giữa thập niên 2010", "đầu thập kỷ 1990", "những năm 2010", "những năm 1990",
        "in the 2010s", "in the 2010's", "during the decade 1990", "a late-autumn afternoon",
        "three days later", "ten years later", "one May evening", "she may 3 times",
        "ba ngày sau", "mười năm sau", "lúc 2 giờ sáng", "at 2:21 a.m.", "lúc 23:30",
    ]:
        assert find_dates(text) == [], text


def test_numbers_that_are_not_dates_are_kept():
    for text in [
        "kéo dài 3-4 tháng", "khoảng 2-3 người", "mở cửa 24/7", "tỉ số 3-1", "chuyển 2000 USD",
        "giá 2000 đồng", "trả $2000", "số điện thoại 0912-345-678", "tăng 12,019 đơn vị",
        "khoảng 45/60 phút", "5 tháng 3 ngày",
    ]:
        assert find_dates(text) == [], text


def test_year_followed_by_plural_noun_is_still_flagged():
    # Danh từ số nhiều đứng sau năm không phải đơn vị: "In 2014 people left" là một năm thật.
    assert find_dates("In 2014 people left town") == ["In 2014"]
    assert find_dates("By 2014 people had forgotten") == ["2014"]
    assert find_dates("After 1998 people stopped asking") == ["1998"]
    assert find_dates("In 2014 words failed him") == ["In 2014"]
    assert find_dates("In 2014, people left") == ["In 2014"]
    assert find_dates("Sau 2014 người dân rời đi") == ["2014"]


def test_of_and_toi_are_not_quantity_cues():
    # "of" và "tới" đứng trước năm rất thường gặp ("the end of 2014", "mãi tới 2014"): không được miễn.
    for text in [
        "At the end of 2014 people left",
        "In the summer of 2014 people fled",
        "By the end of 2014 people had forgotten",
        "Mãi tới 2014 người ta mới biết",
    ]:
        assert find_dates(text), text
    # chỉ cụm hai từ rõ nghĩa số lượng mới được miễn
    assert find_dates("a total of 2000 people") == []
    assert find_dates("the number of 2000 people") == []


def test_counts_and_amounts_are_kept_only_with_a_quantity_cue_or_unambiguous_unit():
    for text in [
        "about 2000 people came", "more than 2000 people", "over 1999 miles of road", "nearly 2000 words",
        "around 2000 meters up", "hơn 2000 người", "khoảng 1990 người", "gần 2000 người",
        "chuyển 2000 USD", "giá 2000 đồng", "trả $2000", "nợ 2000 triệu", "nặng 2000 kg", "dài 1999 km",
    ]:
        assert find_dates(text) == [], text


def test_unit_exemption_never_applies_to_in_year():
    assert find_dates("in 1999 dollars") == ["in 1999"]


def test_overlapping_matches_collapse_to_longest_span():
    # Ruling 1: "năm 2021" nằm trong "ngày 15 tháng 10 năm 2021" nên chỉ còn một mục.
    assert find_dates("ngày 15 tháng 10 năm 2021") == ["ngày 15 tháng 10 năm 2021"]
    assert find_dates("October 7, 2014") == ["October 7, 2014"]
    assert find_dates("Ngày 3/4 và năm 1999") == ["3/4", "năm 1999"]


# ---------------------------------------------------------------- build_forbidden_names

def test_build_forbidden_names_has_entity_names_and_regex_names_not_in_any_entity():
    plan = _plan([_scene(1)])
    source = "Nguyễn Văn Hùng gặp Trần Quang Minh ở quán. Trần Quang Minh là hàng xóm."
    fb = build_forbidden_names(plan.bible, source)
    reals = [f.real for f in fb]
    assert reals[:3] == ["Nguyễn Văn Hùng", "ông Hùng", "Hùng"]
    entity_ones = [f for f in fb if f.entity_id == "e1"]
    assert len(entity_ones) == 3 and all(f.alias_vi == "Trịnh Quang Vũ" and f.alias_en == "Trinh Quang Vu" for f in entity_ones)
    regex_ones = [f for f in fb if f.entity_id is None]
    assert [f.real for f in regex_ones] == ["Trần Quang Minh"]
    assert regex_ones[0].alias_vi is None and regex_ones[0].alias_en is None
    # tên regex trùng tên entity (khác hoa thường/dấu) thì không thêm lần nữa
    assert reals.count("Nguyễn Văn Hùng") == 1


def test_regex_names_do_not_span_line_breaks():
    # REGEX_PERSON gộp tên qua dòng mới ("Lê Thu Hà\nTrần"), khiến "Trần Quang Minh" không bao giờ bị cấm.
    source = "Nghi phạm: Trần Quang Minh\nNạn nhân: Lê Thu Hà\nTrần Quang Minh bị bắt."
    fb = build_forbidden_names(_plan([_scene(1)]).bible, source)
    reals = [f.real for f in fb]
    assert "Trần Quang Minh" in reals and "Lê Thu Hà" in reals
    assert not any("\n" in r or "\r" in r for r in reals)
    # và kiểm cả kế hoạch: tên đó trong lời kể phải bị đánh dấu
    checked = check_plan(_plan([_scene(1, narration_vi="Trần Quang Minh nhìn qua cửa sổ.")]), source)
    assert [(f.kind, f.field) for f in checked.scenes[0].flags] == [("unknown_name", "narration_vi")]


def test_regex_names_do_not_span_other_whitespace_breaks():
    source = "Lê Thu Hà\r\n\r\nTrần Quang Minh Đặng Văn Bình"
    reals = [f.real for f in build_forbidden_names(_plan([_scene(1)]).bible, source)]
    for expected in ("Lê Thu Hà", "Trần Quang Minh", "Đặng Văn Bình"):
        assert expected in reals


def test_build_forbidden_names_skips_kept_country_and_agency_terms():
    ents = [
        _entity("e1", ["Đài Loan", "Taiwan"], "Vùng Đảo", "Island", kind="place"),
        _entity("e2", ["Cảnh sát"], "Đội X", "Team X", kind="organization"),
        _entity("e3", ["Lưu Vinh Phú"], "Lâm Quốc Bảo", "Lin Guobao"),
    ]
    fb = build_forbidden_names(_plan([_scene(1)], entities=ents).bible, "")
    assert [f.real for f in fb] == ["Lưu Vinh Phú"]


def test_person_named_like_a_country_is_still_forbidden():
    # "Đức" là tên người (nhân vật) và cũng là tên nước: chỉ địa danh/cơ quan mới được miễn.
    ents = [_entity("e1", ["Đức"], "Quang Huy", "Quang Huy"), _entity("e2", ["Đức"], "Vùng Đảo", "Island", kind="place")]
    fb = build_forbidden_names(_plan([_scene(1)], entities=ents).bible, "")
    assert [(f.real, f.entity_id) for f in fb] == [("Đức", "e1")]


def test_build_forbidden_names_treats_empty_alias_as_missing():
    ents = [_entity("e1", ["Trần Quang Minh"], "", "")]
    fb = build_forbidden_names(_plan([_scene(1)], entities=ents).bible, "")
    assert fb[0].alias_vi is None and fb[0].alias_en is None


# ---------------------------------------------------------------- check_plan

def test_check_plan_autoreplaces_known_and_flags_unknown():
    scenes = [
        _scene(
            1,
            narration_en="Nguyen Van Hung locked the door and left.",
            narration_vi="Ông Hùng khoá cửa rồi ra đi.",
        ),
        _scene(2, narration_vi="Trần Quang Minh nhìn qua cửa sổ."),
    ]
    plan = _plan(scenes)
    source = "Nguyễn Văn Hùng khoá cửa. Trần Quang Minh nhìn qua cửa sổ."
    checked = check_plan(plan, source)

    s1, s2 = checked.scenes
    assert "Hung" not in s1.narration_en and "Trinh Quang Vu" in s1.narration_en
    assert "Hùng" not in s1.narration_vi and "Trịnh Quang Vũ" in s1.narration_vi
    assert s1.flags == []
    assert any("Đã tự thay" in w and "cảnh 1" in w and "narration_en" in w for w in checked.warnings)
    assert any("Đã tự thay" in w and "cảnh 1" in w and "narration_vi" in w for w in checked.warnings)

    assert [(f.kind, f.field) for f in s2.flags] == [("unknown_name", "narration_vi")]
    assert "Trần Quang Minh" in s2.flags[0].detail
    assert has_blocking_flags(checked) is True


def test_check_plan_warning_names_real_and_alias():
    plan = _plan([_scene(3, narration_en="Hung stood still.", narration_vi="Anh đứng im.")])
    checked = check_plan(plan, "")
    assert "Đã tự thay tên thật 'Hùng' bằng 'Trinh Quang Vu' ở cảnh 3 (narration_en)." in checked.warnings


def test_check_plan_does_not_mutate_input_and_is_idempotent():
    scenes = [_scene(1, narration_en="Nguyen Van Hung left.", narration_vi="Trần Quang Minh ở lại ngày 7 tháng 10.")]
    plan = _plan(scenes)
    before = plan.model_dump()
    source = "Trần Quang Minh ở lại."
    once = check_plan(plan, source)
    assert plan.model_dump() == before
    assert once is not plan and once.scenes[0] is not plan.scenes[0]

    twice = check_plan(once, source)
    assert [s.model_dump() for s in twice.scenes] == [s.model_dump() for s in once.scenes]
    assert twice.bible.model_dump() == once.bible.model_dump()
    assert twice.warnings == once.warnings and twice.check_warnings == once.check_warnings
    assert twice.flags == once.flags
    # tính lại từ đầu: cờ không nhân đôi qua các lần chạy
    assert [(f.kind, f.field) for f in twice.scenes[0].flags] == [(f.kind, f.field) for f in once.scenes[0].flags]
    assert len(twice.scenes[0].flags) == len(set((f.kind, f.field, f.detail) for f in twice.scenes[0].flags))


def test_check_plan_drops_stale_flags_after_user_fix():
    plan = _plan([_scene(1, narration_vi="Trần Quang Minh nhìn qua cửa sổ.")])
    source = "Trần Quang Minh nhìn qua cửa sổ."
    flagged = check_plan(plan, source)
    assert has_blocking_flags(flagged)
    fixed = flagged.model_copy(deep=True)
    fixed.scenes[0].narration_vi = "Một người đàn ông nhìn qua cửa sổ."
    rechecked = check_plan(fixed, source)
    assert rechecked.scenes[0].flags == [] and not has_blocking_flags(rechecked)


def test_check_plan_flags_dates_in_narration_only_as_blocking():
    plan = _plan([_scene(1, narration_vi="Đêm ngày 15 tháng 10 năm 2021, lúc 23:30, chuông reo.", narration_en="At 02:21, the phone rang.")])
    checked = check_plan(plan, "")
    flags = checked.scenes[0].flags
    assert [(f.kind, f.field) for f in flags] == [("date", "narration_vi")]
    assert "ngày 15 tháng 10 năm 2021" in flags[0].detail
    assert has_blocking_flags(checked)


def test_check_plan_flags_missing_text_and_bad_reveal():
    ev = [CaseEvidence(id="ev1", label_vi="Chiếc búa", label_en="The hammer")]
    scenes = [
        _scene(1, narration_en="", board_reveal=["ev1", "evX"], visual_kind="board"),
        _scene(2, narration_vi="   "),
    ]
    checked = check_plan(_plan(scenes, evidence=ev), "")
    f1 = {(f.kind, f.field) for f in checked.scenes[0].flags}
    assert ("missing_text", "narration_en") in f1
    bad = [f for f in checked.scenes[0].flags if f.kind == "bad_reveal"]
    assert len(bad) == 1 and "evX" in bad[0].detail and "ev1" not in bad[0].detail
    assert [(f.kind, f.field) for f in checked.scenes[1].flags] == [("missing_text", "narration_vi")]
    assert has_blocking_flags(checked)


def test_check_plan_accepts_relation_ids_in_board_reveal():
    ents = [_entity("e1", ["Trần Quang Minh"], "Lê Văn Tám", "Le Van Tam"), _entity("e2", ["Phạm Hữu Lộc"], "Võ Minh Kha", "Vo Minh Kha")]
    rel = [CaseRelation(id="r1", source_id="e1", target_id="e2")]
    ev = [CaseEvidence(id="ev1", label_vi="Chiếc búa", label_en="The hammer")]
    checked = check_plan(_plan([_scene(1, board_reveal=["ev1", "r1"], visual_kind="board")], entities=ents, evidence=ev, relations=rel), "")
    assert checked.scenes[0].flags == []


def test_country_names_not_flagged():
    ents = [_entity("e1", ["Nguyễn Văn Hùng"], "Trịnh Quang Vũ", "Trinh Quang Vu"), _entity("e2", ["Đài Loan"], "Vùng Đảo", "Island", kind="place")]
    scene = _scene(
        1,
        narration_vi="Ở Đài Loan, cảnh sát và viện kiểm sát vào cuộc.",
        narration_en="In Taiwan, the police and the prosecutors stepped in.",
        image_prompt="A police car parked outside a small house in rural Taiwan at dusk, cinematic wide shot.",
    )
    source = "Nguyễn Văn Hùng sống ở Đài Loan. Cảnh sát điều tra."
    checked = check_plan(_plan([scene], entities=ents), source)
    assert checked.scenes[0].flags == []
    assert checked.scenes[0].narration_vi == scene.narration_vi
    assert not any("Đài Loan" in w or "Taiwan" in w for w in checked.warnings)


def test_unrevealed_evidence_warns():
    ev = [
        CaseEvidence(id="ev1", label_vi="Chiếc búa", label_en="The hammer"),
        CaseEvidence(id="ev2", label_vi="Tờ giấy", label_en="The note"),
    ]
    scenes = [_scene(1, board_reveal=["ev1"], visual_kind="board"), _scene(2)]
    checked = check_plan(_plan(scenes, evidence=ev), "")
    assert any("ev2" in w for w in checked.check_warnings)
    assert not any("ev1" in w for w in checked.check_warnings)
    assert checked.warnings == []              # `warnings` là danh sách bền, không chứa kết quả kiểm
    # đây là cảnh báo, không chặn
    assert not has_blocking_flags(checked)


def test_check_plan_scans_prompts():
    scene = _scene(
        1,
        image_prompt="Close-up of Nguyen Van Hung sitting alone in a dim kitchen, cinematic, shallow depth of field.",
        video_prompt="Slow push in on Trần Quang Minh at the window, rain on glass, handheld.",
        visual_kind="video",
    )
    checked = check_plan(_plan([scene]), "Trần Quang Minh ở bên cửa sổ.")
    s = checked.scenes[0]
    assert "Nguyen Van Hung" not in s.image_prompt and "Trinh Quang Vu" in s.image_prompt
    assert [(f.kind, f.field) for f in s.flags] == [("unknown_name", "video_prompt")]


def test_check_plan_skips_disclaimer_scene():
    disc = AdaptedScene(
        order=1, part_id="p0", visual_kind="disclaimer",
        narration_vi=DISCLAIMER["vi"], narration_en=DISCLAIMER["en"],
    )
    # ngay cả khi tên regex "Câu Chuyện" hay tên entity lọt vào, cảnh miễn trừ không bị quét
    ents = [_entity("e1", ["Câu chuyện dựa"], "Aa Bb", "Aa Bb")]
    checked = check_plan(_plan([disc], entities=ents), "")
    assert checked.scenes[0].narration_vi == DISCLAIMER["vi"]
    assert checked.scenes[0].narration_en == DISCLAIMER["en"]
    assert checked.scenes[0].flags == []


def test_check_plan_replaces_names_in_title_and_labels_and_warns():
    ents = [_entity("e1", ["Nguyễn Văn Hùng"], "Trịnh Quang Vũ", "Trinh Quang Vu")]
    ev = [CaseEvidence(id="ev1", label_vi="Con dao của Nguyễn Văn Hùng", label_en="Nguyen Van Hung's knife")]
    rel = [CaseRelation(id="r1", source_id="e1", target_id="e1", label_vi="Hàng xóm của Nguyễn Văn Hùng", label_en="Neighbor of Nguyen Van Hung")]
    plan = _plan(
        [_scene(1, board_reveal=["ev1", "r1"], visual_kind="board")],
        entities=ents, evidence=ev, relations=rel,
        title_vi="Vụ án Nguyễn Văn Hùng", title_en="The Nguyen Van Hung Case",
    )
    checked = check_plan(plan, "")
    b = checked.bible
    assert b.title_vi == "Vụ án Trịnh Quang Vũ" and b.title_en == "The Trinh Quang Vu Case"
    assert b.evidence[0].label_vi == "Con dao của Trịnh Quang Vũ"
    assert b.evidence[0].label_en == "Trinh Quang Vu's knife"
    assert b.relations[0].label_vi == "Hàng xóm của Trịnh Quang Vũ"
    assert b.relations[0].label_en == "Neighbor of Trinh Quang Vu"
    joined = "\n".join(checked.warnings)
    for where in ("title_vi", "title_en", "ev1", "r1"):
        assert where in joined
    # bản gốc không bị đổi
    assert plan.bible.title_vi == "Vụ án Nguyễn Văn Hùng"


def test_unknown_name_in_title_is_blocking_plan_flag():
    plan = _plan([_scene(1)], title_vi="Vụ án Trần Quang Minh")
    checked = check_plan(plan, "Trần Quang Minh là hàng xóm.")
    assert [(f.kind, f.field) for f in checked.flags] == [("unknown_name", "title")]
    assert "Trần Quang Minh" in checked.flags[0].detail and "title_vi" in checked.flags[0].detail
    assert checked.scenes[0].flags == []
    assert has_blocking_flags(checked) is True


def test_unknown_name_in_title_en_is_blocking_plan_flag():
    plan = _plan([_scene(1)], title_en="The Tran Quang Minh Case")
    checked = check_plan(plan, "Trần Quang Minh là hàng xóm.")
    assert [(f.kind, f.field) for f in checked.flags] == [("unknown_name", "title")]
    assert has_blocking_flags(checked)


def test_unknown_name_in_evidence_and_relation_labels_is_plan_flag():
    ents = [_entity("e1", ["Nguyễn Văn Hùng"], "Trịnh Quang Vũ", "Trinh Quang Vu")]
    ev = [CaseEvidence(id="ev1", label_vi="Con dao của Trần Quang Minh", label_en="The knife")]
    rel = [CaseRelation(id="r1", source_id="e1", target_id="e1", label_vi="Hàng xóm", label_en="Neighbor of Tran Quang Minh")]
    plan = _plan([_scene(1, board_reveal=["ev1", "r1"], visual_kind="board")], entities=ents, evidence=ev, relations=rel)
    checked = check_plan(plan, "Trần Quang Minh là hàng xóm của Nguyễn Văn Hùng.")
    assert [(f.kind, f.field) for f in checked.flags] == [("unknown_name", "evidence:ev1"), ("unknown_name", "relation:r1")]
    assert checked.scenes[0].flags == []
    assert has_blocking_flags(checked)


def test_unknown_name_in_image_prompt_is_scene_flag():
    scene = _scene(1, image_prompt="Wide shot of Trần Quang Minh standing outside a shuttered shop at dusk, cinematic.")
    checked = check_plan(_plan([scene]), "Trần Quang Minh là hàng xóm.")
    assert [(f.kind, f.field) for f in checked.scenes[0].flags] == [("unknown_name", "image_prompt")]
    assert checked.flags == []
    assert has_blocking_flags(checked)


def test_known_alias_names_in_title_and_labels_never_block():
    plan = _plan([_scene(1)], title_vi="Vụ án Nguyễn Văn Hùng")
    checked = check_plan(plan, "")
    assert checked.flags == [] and not has_blocking_flags(checked)


def test_dates_outside_narration_are_check_warnings_only():
    ev = [CaseEvidence(id="ev1", label_vi="Hồ sơ năm 2014", label_en="File from 2014")]
    plan = _plan(
        [_scene(1, board_reveal=["ev1"], visual_kind="board",
                image_prompt="A newspaper clipping dated March 3, 2014 on a cluttered desk, cinematic close-up shot.")],
        evidence=ev, title_vi="Vụ án năm 2014",
    )
    checked = check_plan(plan, "")
    joined = "\n".join(checked.check_warnings)
    assert "March 3, 2014" in joined and "image_prompt" in joined
    assert "năm 2014" in joined and "title_vi" in joined and "ev1" in joined
    assert checked.warnings == []
    assert checked.scenes[0].flags == [] and checked.flags == []
    assert not has_blocking_flags(checked)


def test_warnings_persist_across_check_plan_calls_without_duplicates():
    scenes = [_scene(1, narration_en="Nguyen Van Hung left.")]
    plan = _plan(scenes)
    plan.warnings = ["Bài chỉ đủ tư liệu cho khoảng 6 phút."]       # thông báo do bước khác ghi vào
    once = check_plan(plan, "")
    assert once.warnings[0] == "Bài chỉ đủ tư liệu cho khoảng 6 phút."
    replaced = [w for w in once.warnings if "Đã tự thay" in w]
    assert len(replaced) == 1

    twice = check_plan(once, "")
    thrice = check_plan(twice, "")
    assert twice.warnings == once.warnings == thrice.warnings
    assert plan.warnings == ["Bài chỉ đủ tư liệu cho khoảng 6 phút."]    # đầu vào không bị đổi

    # người dùng gõ lại đúng tên thật đó ở đúng trường đó: cùng một thông báo, không nhân đôi
    retyped = once.model_copy(deep=True)
    retyped.scenes[0].narration_en = "Nguyen Van Hung left."
    assert check_plan(retyped, "").warnings == once.warnings

    # người dùng sửa cảnh thêm một lần có tên thật: thông báo cũ còn, thông báo mới được nối
    edited = twice.model_copy(deep=True)
    edited.scenes[0].narration_vi = "Ông Hùng ở lại."
    after = check_plan(edited, "")
    assert after.warnings[: len(once.warnings)] == once.warnings
    assert len(after.warnings) == len(once.warnings) + 1
    assert "narration_vi" in after.warnings[-1]


def test_check_warnings_and_flags_are_recomputed_each_call():
    ev = [CaseEvidence(id="ev1", label_vi="Chiếc búa", label_en="The hammer")]
    plan = _plan([_scene(1)], evidence=ev, title_vi="Vụ án Trần Quang Minh")
    source = "Trần Quang Minh là hàng xóm."
    first = check_plan(plan, source)
    assert any("ev1" in w for w in first.check_warnings)
    assert [f.field for f in first.flags] == ["title"] and has_blocking_flags(first)

    fixed = first.model_copy(deep=True)
    fixed.scenes[0].board_reveal = ["ev1"]
    fixed.bible.title_vi = "Đêm Không Ngủ"
    second = check_plan(fixed, source)
    assert second.check_warnings == []
    assert second.flags == []
    assert not has_blocking_flags(second)


def test_check_plan_ignores_stale_check_warnings_and_plan_flags_from_input():
    plan = _plan([_scene(1)])
    plan.check_warnings = ["cũ"]
    plan.flags = [SceneFlag(kind="unknown_name", field="title", detail="cũ")]
    checked = check_plan(plan, "")
    assert checked.check_warnings == [] and checked.flags == []
    assert not has_blocking_flags(checked)


def test_has_blocking_flags_false_for_clean_plan():
    checked = check_plan(_plan([_scene(1), _scene(2)]), "")
    assert has_blocking_flags(checked) is False
    assert checked.warnings == [] and checked.check_warnings == [] and checked.flags == []
