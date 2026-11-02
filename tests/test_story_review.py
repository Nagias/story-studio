"""Lời review truyện chữ viết từng phần, kiểm đủ ý bằng code (services/story_review.py, services/coverage_guard.py).

CLAUDE.md mục 1.2 câu 10, 14, 15, 16, 21. Không gọi LLM thật: tests/story_review_fakes.py.
"""
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import routers.api as api_module  # noqa: E402
from services import coverage_guard, project_service, story_review  # noqa: E402
from tests.story_review_fakes import FakeStoryLLM  # noqa: E402

PARA = ("Nanahoshi Shizuka tỉnh dậy trong căn phòng đá lạnh lẽo, ánh nến leo lét hắt lên những dòng ma pháp trận "
        "chi chít trên sàn. Cô nhớ lại buổi chiều tan học, khi một luồng sáng trắng nuốt chửng cả con phố quen thuộc. "
        "Người đàn ông đeo mặt nạ bạc bước vào, đặt lên bàn một chiếc đồng hồ cát và nói rằng thời gian của cô chỉ "
        "còn một năm. Nanahoshi siết chặt nắm tay, tự hứa sẽ tìm bằng được đường trở về thế giới cũ dù phải trả giá "
        "thế nào. Đêm đó cô thức trắng, chép lại từng ký hiệu trên sàn vào cuốn sổ nhỏ mang theo từ trường học.")


def _story(paragraphs: int = 3) -> str:
    return "\n\n".join(PARA.replace("Đêm đó", f"Đêm thứ {i + 1}") for i in range(paragraphs))


@pytest.mark.asyncio
async def test_review_covers_every_point_and_passes_facts_to_next_part():
    llm = FakeStoryLLM()
    text = _story(6)
    res = await story_review.review_story(text, llm=llm)
    parts = story_review.chunk_source(text, story_review.PART_MAX_CHARS)
    assert len(parts) >= 2
    assert res["language"] == "vi" and res["verified"] is True
    assert llm.calls[:3] == ["liet_ke_y", "viet_review", "kiem_loi_ke"]
    assert len(res["coverage"]) == len(parts)
    for st in res["coverage"]:
        assert st["review_words"] >= story_review.MIN_WORD_RATIO[("vi", "vi")] * st["source_words"]
    covered = {c for s in res["scenes"] for c in s["metadata"]["covers"] if s["metadata"]["story_part"] == 1}
    assert covered == {f"p{i}" for i in range(1, res["coverage"][0]["points"] + 1)}
    # phần 2 nhận bảng sự thật của phần 1
    second_write = [p for p in llm.prompts if p.startswith("TASK: viet_review (phần 2/")][0]
    assert "sự thật của p1" in second_write


@pytest.mark.asyncio
async def test_writer_that_skips_a_point_must_rewrite():
    llm = FakeStoryLLM(broken="skip_point")
    res = await story_review.review_story(_story(1), llm=llm)
    assert res["scenes"]
    rewrites = [p for p in llm.prompts if p.startswith("TASK: viet_review")]
    assert len(rewrites) == 2 and "chưa kể các ý p1" in rewrites[1]      # code bắt thiếu ý, viết lại lần 2


@pytest.mark.asyncio
async def test_fake_quote_is_rejected_and_rechecked():
    llm = FakeStoryLLM(broken="fake_quote")
    await story_review.review_story(_story(1), llm=llm)
    assert llm.calls.count("kiem_loi_ke") == 2
    assert "không có nguyên văn trong lời kể" in [p for p in llm.prompts if p.startswith("TASK: kiem_loi_ke")][1]


@pytest.mark.asyncio
async def test_first_person_narrator_is_rejected():
    llm = FakeStoryLLM(broken="first_person")
    with pytest.raises(story_review.StoryReviewError) as err:
        await story_review.review_story(_story(1), llm=llm)
    assert "xưng" in err.value.user_message
    assert all(c != "kiem_loi_ke" for c in llm.calls)


@pytest.mark.asyncio
async def test_point_never_covered_fails_loudly_without_raw_text():
    llm = FakeStoryLLM(broken="always_missing")
    with pytest.raises(story_review.StoryReviewError) as err:
        await story_review.review_story(_story(1), llm=llm)
    assert "sau 3 lần viết lại" in err.value.user_message and "p1" in err.value.user_message
    assert llm.calls.count("viet_review") == story_review.MAX_ROUNDS


@pytest.mark.asyncio
async def test_english_output_from_vietnamese_story():
    res = await story_review.review_story(_story(1), language="en", llm=FakeStoryLLM())
    assert res["language"] == "en"
    assert all(not story_review._VI_MARKS.search(s["text"]) for s in res["scenes"])


def test_quote_and_first_person_rules():
    scenes = ["Đúng lúc đó, cánh cửa khóa trái bỗng bật mở trong đêm."]
    assert coverage_guard.quote_found("cánh cửa khóa trái bỗng bật mở", scenes)
    assert not coverage_guard.quote_found("cửa mở", scenes)                   # quá ngắn, không làm bằng chứng
    assert coverage_guard.first_person_hits('Tôi nghĩ cô ấy sai. Anh ta nói "tôi không biết".', "vi") == ["Tôi"]
    assert coverage_guard.first_person_hits("Chúng ta cùng xem tiếp.", "vi") == []
    with pytest.raises(coverage_guard.QuoteRejected):
        coverage_guard.check_verify({"quotes": [{"point_id": "p1", "scene": 1, "quote": "một câu bịa ra hoàn toàn"}]},
                                    ["p1"], scenes)
    res = coverage_guard.check_verify({"quotes": [], "issues": [
        {"scene": 1, "kind": "lap_lai", "quote": "câu bịa không có", "detail": "x"},
        {"scene": 1, "kind": "lap_lai", "quote": "cánh cửa khóa trái bỗng bật mở", "detail": "kể lại"}]}, ["p1"], scenes)
    assert res["missing"] == ["p1"] and len(res["issues"]) == 1           # lỗi không có câu trích thật thì bỏ


# ----------------------------------------------------------------------------- API 1-Click

@pytest.fixture
def client(isolated_projects_dir, monkeypatch):
    monkeypatch.setattr(api_module, "PROJECTS_DIR", isolated_projects_dir)
    app = FastAPI()
    app.include_router(api_module.router)
    with TestClient(app) as c:
        yield c


def test_one_click_creates_project_from_verified_review(client, monkeypatch):
    monkeypatch.setattr(story_review, "_story_llm", FakeStoryLLM())
    resp = client.post("/api/projects/create-from-script", json={
        "text": _story(2), "generate_initial_images": False, "output_language": "en", "progress_id": "pabc123"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["metadata"]["scene_analysis"]["provider"] == "story_review"
    assert body["metadata"]["story_language"] == "en"
    assert body["voice"].startswith("en-")
    assert client.get("/api/projects/create-from-script/progress/pabc123").json() == {"progress": None}


def test_one_click_failure_is_reported_and_creates_no_project(client, monkeypatch):
    monkeypatch.setattr(story_review, "_story_llm", FakeStoryLLM(broken="always_missing"))
    before = len(project_service.list_projects())
    resp = client.post("/api/projects/create-from-script", json={"text": _story(1), "generate_initial_images": False})
    assert resp.status_code == 502
    assert "Chưa viết được lời review" in resp.json()["detail"]
    assert len(project_service.list_projects()) == before


def test_progress_id_must_be_safe(client):
    assert client.get("/api/projects/create-from-script/progress/..%2Fx").status_code in (400, 404)


def test_chinese_source_is_counted_by_han_characters_and_reviewed_in_vietnamese():
    zh = "李明夏跟在陈鸿文教授身后，从三楼一路下到地下一层。" * 30
    assert story_review.detect_text_language(zh) == "zh"
    assert story_review.source_words(zh, "zh") == len([c for c in zh if "\u4e00" <= c <= "\u9fff"])
    assert story_review.min_points(zh) >= len(zh) // story_review.CHARS_PER_POINT_ZH
    parts = story_review.chunk_source(zh, story_review.PART_MAX_CHARS_ZH)
    assert all(len(p) <= story_review.PART_MAX_CHARS_ZH for p in parts)
