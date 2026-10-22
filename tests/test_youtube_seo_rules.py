"""Luật SEO YouTube (services/youtube_seo_rules.py): khoá cứng của gói SEO."""
import pytest
from PIL import Image

import config
from services import youtube_seo_rules as rules


def _ok(checks, rule):
    return next(c for c in checks if c.rule == rule).ok


# ----------------------------------------------------------------------------- tiêu đề
def test_title_length_limit_is_100_characters():
    assert _ok(rules.check_title("rừng sương mù " + "a" * 86, ["rừng sương mù"]), "title.length")
    assert not _ok(rules.check_title("rừng sương mù " + "a" * 87, ["rừng sương mù"]), "title.length")
    assert not _ok(rules.check_title("   ", ["x"]), "title.length")


def test_title_must_contain_a_chosen_keyword_case_insensitive():
    assert _ok(rules.check_title("Bí ẩn Rừng Sương Mù kể lại", ["rừng sương mù"]), "title.keyword")
    assert not _ok(rules.check_title("Bí ẩn khu rừng", ["rừng sương mù"]), "title.keyword")
    # dấu là một phần của từ khoá: không dấu thì không tính
    assert not _ok(rules.check_title("Rung suong mu", ["rừng sương mù"]), "title.keyword")


def test_title_rejects_angle_brackets_emoji_and_all_caps():
    assert not _ok(rules.check_title("a <b> rừng", ["rừng"]), "title.angle")
    assert not _ok(rules.check_title("🔥 rừng sương mù", ["rừng"]), "title.emoji")
    assert not _ok(rules.check_title("RỪNG SƯƠNG MÙ BÍ MẬT KINH HOÀNG", ["rừng"]), "title.caps")
    assert _ok(rules.check_title("Rừng Sương Mù: Bí Mật Của Làng", ["rừng"]), "title.caps")
    assert _ok(rules.check_title("ĐẢO X", ["đảo"]), "title.caps")   # ngắn quá thì không xét


# ----------------------------------------------------------------------------- mô tả, tags, hashtag
def test_description_limit_counts_utf8_bytes_not_characters():
    vietnamese = "ằ" * 1667          # 1667 ký tự nhưng 5001 byte
    assert len(vietnamese) < 5000
    assert not _ok(rules.check_description("rừng " + vietnamese, "rừng"), "description.bytes")
    assert _ok(rules.check_description("rừng " + "a" * 4990, "rừng"), "description.bytes")


def test_description_main_keyword_must_be_in_first_150_characters():
    assert _ok(rules.check_description("Câu chuyện rừng sương mù kể về...", "rừng sương mù"), "description.keyword")
    late = "x" * 150 + " rừng sương mù"
    assert not _ok(rules.check_description(late, "rừng sương mù"), "description.keyword")


def test_tags_length_follows_youtube_counting():
    # "a b" có khoảng trắng: 3 + 2 ngoặc kép; dấu phẩy giữa 2 tag: 1
    assert rules.tags_length(["a b", "cd"]) == 5 + 2 + 1
    assert rules.tags_length([]) == 0
    many = ["x" * 49] * 10                     # 490 + 9 dấu phẩy = 499
    assert _ok(rules.check_tags(many), "tags.length")
    assert not _ok(rules.check_tags(many + ["y"]), "tags.length")
    assert not _ok(rules.check_tags(["a,b"]), "tags.comma")


def test_hashtags_need_no_spaces_and_at_most_15():
    assert _ok(rules.check_hashtags(["#RừngSươngMù", "#TruyệnMa"]), "hashtags.format")
    assert not _ok(rules.check_hashtags(["#rừng sương"]), "hashtags.format")
    assert not _ok(rules.check_hashtags(["rừng"]), "hashtags.format")
    assert not _ok(rules.check_hashtags([f"#t{i}" for i in range(16)]), "hashtags.count")
    assert not _ok(rules.check_hashtags([], description=" ".join(f"#t{i}" for i in range(16))), "hashtags.count")


# ----------------------------------------------------------------------------- chương
def test_timestamps_switch_to_hours_for_long_videos():
    assert rules.format_timestamp(75, long_video=False) == "01:15"
    assert rules.format_timestamp(3725, long_video=True) == "1:02:05"
    assert rules.parse_timestamp("1:02:05") == 3725
    assert rules.chapter_starts_in("Mở đầu\n00:00 A\n02:30 B\nkhông phải 03:00\n1:02:05 C") == [0, 150, 3725]


def test_chapters_follow_youtube_rules():
    assert rules.all_ok(rules.check_chapters([0, 60, 120], video_seconds=200))
    assert not _ok(rules.check_chapters([5, 60, 120], 200), "chapters.first")
    assert not _ok(rules.check_chapters([0, 60], 200), "chapters.count")
    assert not _ok(rules.check_chapters([0, 120, 60], 200), "chapters.order")
    assert not _ok(rules.check_chapters([0, 5, 60], 200), "chapters.length")
    assert not _ok(rules.check_chapters([0, 60, 195], 200), "chapters.length")   # chương cuối 5 giây
    assert rules.all_ok(rules.check_chapters([], 200))                           # không có chương: hợp lệ


# ----------------------------------------------------------------------------- thumbnail, font
def test_thumbnail_rules(tmp_path):
    good = tmp_path / "good.jpg"
    Image.new("RGB", (1280, 720)).save(good, "JPEG")
    assert rules.all_ok(rules.check_thumbnail(good))
    square = tmp_path / "square.jpg"
    Image.new("RGB", (800, 800)).save(square, "JPEG")
    assert not _ok(rules.check_thumbnail(square), "thumbnail.ratio")
    small = tmp_path / "small.png"
    Image.new("RGB", (320, 180)).save(small, "PNG")
    assert not _ok(rules.check_thumbnail(small), "thumbnail.width")
    assert not rules.all_ok(rules.check_thumbnail(tmp_path / "missing.jpg"))


@pytest.mark.skipif(config.WINDOWS_FONTS_DIR is None, reason="không phải Windows")
def test_missing_glyphs_finds_characters_a_font_cannot_draw():
    impact = config.WINDOWS_FONTS_DIR / "impact.ttf"
    segoe = config.WINDOWS_FONTS_DIR / "seguibl.ttf"
    if not (impact.exists() and segoe.exists()):
        pytest.skip("máy không có Impact hoặc Segoe UI Black")
    assert "Ư" in rules.missing_glyphs(impact, "THỬ MUSE ƯỚC")      # Impact thiếu chữ có dấu tiếng Việt
    assert rules.missing_glyphs(segoe, "THỬ MUSE ƯỚC ĐỀ Ở") == ""
    assert "🔥" in rules.missing_glyphs(segoe, "🔥 1080P")


def test_check_pack_puts_all_rules_together():
    checks = rules.check_pack(title="Rừng sương mù kể lại", description="Rừng sương mù là...\n\n00:00 A\n01:00 B\n02:00 C",
                              tags=["rừng sương mù"], hashtags=["#RừngSươngMù"], keywords=["rừng sương mù"],
                              video_seconds=200)
    assert rules.all_ok(checks), rules.failures(checks)
    assert not rules.all_ok(rules.check_pack(title="x", description="y", tags=[], hashtags=[], keywords=[],
                                             video_seconds=200))
