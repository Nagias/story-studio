"""Gói SEO YouTube: chia chương, AI viết trong khuôn (LLM giả), lưu vào dự án, sửa tay, tải về, API, thumbnail."""
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import config
from models.schemas import ProjectCreateRequest, ProjectUpdateRequest, SceneCreateRequest
from routers import youtube_seo as seo_router
from services import project_service, youtube_keywords
from services import youtube_seo_pack as seo
from services import youtube_seo_rules as rules
from services.case_adaptation_steps import SoftRejected, StepRejected

SCENES = 40
SCENE_S = 30.0
VIDEO_S = SCENES * SCENE_S          # 20 phút
KEYWORDS = ["rừng sương mù", "truyện ma", "kể chuyện đêm khuya"]


def _make_project(name="Rừng Sương Mù", *, language=None, case_id=None, durations=True):
    project = project_service.create_project(ProjectCreateRequest(name=name))
    for i in range(SCENES):
        project_service.add_scene(project.id, SceneCreateRequest(text=f"Cảnh {i + 1}: đoàn người đi sâu vào rừng sương mù.",
                                                                image_prompt="misty forest"))
    project = project_service.get_project(project.id)
    for i, scene in enumerate(project.scenes):
        scene.duration = SCENE_S if durations else None
        scene.metadata = {"narrative_beat": f"nhịp {i // 10}"}   # đổi nhịp ở cảnh 11, 21, 31
    if language:
        project.metadata["language"] = language
    if case_id:
        project.metadata["case_id"] = case_id
    project_service.save_project(project)
    return project


def _with_final_video(project_id, monkeypatch, seconds=VIDEO_S):
    video = project_service.get_render_media_paths(project_id)["final_video"]
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"fake mp4")
    monkeypatch.setattr(seo, "get_audio_duration", lambda path: seconds)


def _good_answer(prompt: str, language="vi") -> dict:
    n = int(re.search(r'đúng (\d+) nhãn', prompt).group(1))
    if language == "en":
        return {"titles": ["rừng sương mù: a ghost story", "The misty forest tale", "rừng sương mù explained"],
                "description_intro": "x"}
    return {
        "titles": ["Rừng sương mù: chuyến đi không trở về", "Truyện ma rừng sương mù kể lúc nửa đêm",
                   "Bí mật của khu rừng sương mù phía bắc"],
        "description_intro": "Rừng sương mù là nơi đoàn người lạc lối trong một đêm mưa. Video kể lại toàn bộ chuyến đi "
                             "và điều họ gặp ở bìa rừng.",
        "chapter_labels": [f"Chặng {i + 1}: đi sâu hơn vào rừng" for i in range(n)],
        "thumbnail_lines": ["RỪNG SƯƠNG MÙ", "KHÔNG LỐI VỀ"],
    }


class FakeLLM:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []
        self.systems = []

    async def __call__(self, system, user, **kwargs):
        self.systems.append(system)
        self.prompts.append(user)
        answer = self.answers.pop(0) if self.answers else "good"
        return _good_answer(user) if answer == "good" else answer


# ----------------------------------------------------------------------------- chương
def test_chapters_follow_real_video_time_and_prefer_beat_changes(isolated_projects_dir):
    project = _make_project()
    drafts = seo.plan_chapters(project, VIDEO_S)
    starts = [d.start_s for d in drafts]
    assert len(drafts) == 8                                   # 20 phút / 2,5 phút
    assert rules.all_ok(rules.check_chapters(starts, VIDEO_S))
    assert {300, 600, 900} <= set(starts)                     # chỗ đổi nhịp truyện (cảnh 11, 21, 31)


def test_chapters_scale_to_the_rendered_video_length(isolated_projects_dir):
    project = _make_project()
    drafts = seo.plan_chapters(project, VIDEO_S * 1.1)        # video dài hơn tổng giọng (khoảng nghỉ, chuyển cảnh)
    starts = [d.start_s for d in drafts]
    assert all(s % 33 == 0 for s in starts)                   # mỗi cảnh 30 s giọng thành 33 s trong video
    assert rules.all_ok(rules.check_chapters(starts, VIDEO_S * 1.1))


def test_chapters_need_scene_durations_and_skip_very_short_videos(isolated_projects_dir):
    with pytest.raises(seo.SeoPackError, match="chưa có thời lượng"):
        seo.plan_chapters(_make_project(durations=False), VIDEO_S)
    assert seo.plan_chapters(_make_project(), 25) == []


# ----------------------------------------------------------------------------- kiểm kết quả AI
def _validate(raw, n=3, language="vi"):
    return seo.validate_llm_output(raw, keywords=KEYWORDS, language=language, chapter_count=n, font_path=None)


def test_llm_output_must_use_chosen_keywords():
    raw = _good_answer("đúng 3 nhãn")
    raw["titles"] = ["Một câu chuyện rất hay", "Video mới"]
    with pytest.raises(StepRejected, match="Không tiêu đề nào đạt"):
        _validate(raw)


def test_llm_output_with_some_bad_titles_is_soft_rejected_but_usable():
    raw = _good_answer("đúng 3 nhãn")
    raw["titles"][1] = "🔥 TRUYỆN MA RỪNG SƯƠNG MÙ KINH HOÀNG NHẤT"
    with pytest.raises(SoftRejected) as exc:
        _validate(raw)
    assert len(exc.value.value["titles"]) == 2


@pytest.mark.parametrize("change,reason", [
    (lambda r: r.update(chapter_labels=["a"]), "đúng 3 nhãn"),
    (lambda r: r.update(thumbnail_lines=["MỘT DÒNG CHỮ QUÁ DÀI CHO THUMBNAIL"]), "thumbnail_lines"),
    (lambda r: r.update(description_intro="Một video về rừng."), "description_intro"),
    (lambda r: r.update(description_intro=r["description_intro"].replace("ừ", "u").replace("ư", "u").replace("ơ", "o")
                        .replace("ù", "u").replace("à", "a").replace("ạ", "a").replace("ộ", "o").replace("ặ", "a")
                        .replace("ể", "e").replace("ố", "o").replace("ở", "o").replace("ì", "i").replace("ọ", "o")
                        .replace("ả", "a").replace("ỗ", "o").replace("đ", "d").replace("ờ", "o").replace("ệ", "e")),
     "từ khoá chính"),
])
def test_llm_output_rule_breaks_are_rejected(change, reason):
    raw = _good_answer("đúng 3 nhãn")
    change(raw)
    with pytest.raises(StepRejected, match=reason):
        _validate(raw)


def test_english_pack_rejects_vietnamese_words():
    raw = _good_answer("đúng 3 nhãn")
    with pytest.raises(StepRejected, match="tiếng Anh"):
        seo.validate_llm_output(raw, keywords=["misty forest"], language="en", chapter_count=3, font_path=None)


def test_hashtags_keep_vietnamese_letters():
    assert seo.hashtag("rừng sương mù") == "#RừngSươngMù"
    assert seo.hashtag("kể chuyện, đêm khuya!") == "#KểChuyệnĐêmKhuya"


# ----------------------------------------------------------------------------- tạo, sửa, tải gói
@pytest.mark.asyncio
async def test_generate_pack_saves_a_pack_that_passes_every_rule(isolated_projects_dir, monkeypatch):
    project = _make_project(case_id="case_x")
    _with_final_video(project.id, monkeypatch)
    llm = FakeLLM("good")
    pack = await seo.generate_pack(project.id, KEYWORDS, llm=llm)

    assert llm.systems == [seo.SEO_SYSTEM_PROMPT]              # không dùng system prompt của luồng vụ án
    assert all(k in llm.prompts[0] for k in KEYWORDS)
    assert rules.all_ok(seo.pack_checks(pack)), rules.failures(seo.pack_checks(pack))
    assert pack.tags == KEYWORDS and pack.hashtags[0] == "#RừngSươngMù"
    assert "Mục lục:\n00:00 " in pack.description
    assert seo.DISCLOSURE["vi"] in pack.description
    assert pack.description.rstrip().endswith(" ".join(pack.hashtags))
    saved = project_service.get_project(project.id).youtube_seo.pack
    assert saved.title == pack.title and saved.video_seconds == VIDEO_S


@pytest.mark.asyncio
async def test_generate_pack_retries_when_ai_breaks_the_rules(isolated_projects_dir, monkeypatch):
    project = _make_project()
    _with_final_video(project.id, monkeypatch)
    llm = FakeLLM({"titles": ["không có từ khoá"], "description_intro": "", "chapter_labels": [], "thumbnail_lines": []},
                  "good")
    await seo.generate_pack(project.id, KEYWORDS, llm=llm)
    assert len(llm.prompts) == 2
    assert "LẦN TRƯỚC BỊ LOẠI" in llm.prompts[1]


@pytest.mark.asyncio
async def test_generate_pack_needs_the_rendered_video(isolated_projects_dir):
    project = _make_project()
    with pytest.raises(seo.SeoPackError, match="Chưa có video dựng xong"):
        await seo.generate_pack(project.id, KEYWORDS, llm=FakeLLM("good"))


@pytest.mark.asyncio
async def test_manual_edits_must_pass_rules_and_ui_saves_do_not_touch_the_pack(isolated_projects_dir, monkeypatch):
    project = _make_project()
    _with_final_video(project.id, monkeypatch)
    pack = await seo.generate_pack(project.id, KEYWORDS, llm=FakeLLM("good"))

    with pytest.raises(seo.SeoPackRejected) as exc:
        seo.update_pack(project.id, title="rừng sương mù " + "x" * 100, description=pack.description, tags=pack.tags,
                        hashtags=pack.hashtags)
    assert any(c.rule == "title.length" and not c.ok for c in exc.value.checks)
    assert project_service.get_project(project.id).youtube_seo.pack.title == pack.title   # bản lỗi không được lưu

    edited = seo.update_pack(project.id, title="Truyện ma rừng sương mù (bản sửa)", description=pack.description,
                             tags=pack.tags, hashtags=pack.hashtags)
    assert edited.edited_at is not None

    project_service.update_project(project.id, ProjectUpdateRequest(name="Đổi tên từ giao diện"))
    assert project_service.get_project(project.id).youtube_seo.pack.title == "Truyện ma rừng sương mù (bản sửa)"


@pytest.mark.asyncio
async def test_download_text_has_everything_to_paste_into_youtube_studio(isolated_projects_dir, monkeypatch):
    project = _make_project(case_id="case_x")
    _with_final_video(project.id, monkeypatch)
    pack = await seo.generate_pack(project.id, KEYWORDS, llm=FakeLLM("good"))
    text = seo.download_text(project_service.get_project(project.id))
    assert pack.title in text and pack.description in text and ", ".join(pack.tags) in text
    assert "Nội dung bị thay đổi" in text
    with pytest.raises(seo.SeoPackError):
        seo.download_text(_make_project("Chưa có gói"))


# ----------------------------------------------------------------------------- API
@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(seo_router.router)
    with TestClient(app) as c:
        yield c


def test_api_full_flow(isolated_projects_dir, monkeypatch, client):
    project = _make_project()
    _with_final_video(project.id, monkeypatch)

    async def fake_suggestions(seed, language, *, client):
        return [f"{seed} full", "truyện ma"]

    monkeypatch.setattr(youtube_keywords, "fetch_suggestions", fake_suggestions)
    monkeypatch.setattr(seo, "call_llm_json", FakeLLM("good"))
    base = f"/api/projects/{project.id}/youtube-seo"

    state = client.get(base).json()
    assert state["language"] == "vi" and state["pack"] is None and state["research"] is None

    r = client.post(f"{base}/research", json={"seed": "rừng sương mù", "sources": ["youtube_suggest"],
                                              "manual_keywords": ["kể chuyện đêm khuya"]})
    assert r.status_code == 200, r.text
    assert [c["keyword"] for c in r.json()["research"]["candidates"]] == ["kể chuyện đêm khuya", "rừng sương mù full",
                                                                          "truyện ma"]

    r = client.post(f"{base}/generate", json={"keywords": KEYWORDS})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack"]["title"] and all(c["ok"] for c in body["checks"])

    bad = client.put(f"{base}/pack", json={"title": "x" * 120, "description": body["pack"]["description"],
                                           "tags": body["pack"]["tags"], "hashtags": body["pack"]["hashtags"]})
    assert bad.status_code == 422
    assert any(c["rule"] == "title.length" and not c["ok"] for c in bad.json()["detail"]["checks"])

    dl = client.get(f"{base}/download")
    assert dl.status_code == 200 and dl.content.startswith(b"\xef\xbb\xbf")
    assert body["pack"]["title"] in dl.content.decode("utf-8-sig")


def test_api_reports_missing_video_and_unknown_project(isolated_projects_dir, client):
    project = _make_project()
    r = client.post(f"/api/projects/{project.id}/youtube-seo/generate", json={"keywords": KEYWORDS})
    assert r.status_code == 409 and "Bước 3" in r.json()["detail"]
    assert client.get("/api/projects/proj_khongco/youtube-seo").status_code == 404
    assert client.get(f"/api/projects/{project.id}/youtube-seo/download").status_code == 409


# ----------------------------------------------------------------------------- thumbnail
@pytest.mark.skipif(config.WINDOWS_FONTS_DIR is None, reason="không phải Windows")
@pytest.mark.asyncio
async def test_thumbnail_uses_seo_lines_and_vietnamese_font(isolated_projects_dir, monkeypatch):
    from services.thumbnail_service import ThumbnailError, generate_youtube_thumbnail, thumbnail_font_path
    if thumbnail_font_path() is None:
        pytest.skip("máy không có font thumbnail")
    project = _make_project()
    _with_final_video(project.id, monkeypatch)
    await seo.generate_pack(project.id, KEYWORDS, llm=FakeLLM("good"))
    result = generate_youtube_thumbnail(project_service.get_project(project.id))
    out = Path(result["thumbnail_path"])
    assert result["lines"] == ["RỪNG SƯƠNG MÙ", "KHÔNG LỐI VỀ"]
    assert rules.all_ok(rules.check_thumbnail(out))
    with Image.open(out) as im:
        assert im.size == (1920, 1080)

    with pytest.raises(ThumbnailError, match="🔥"):
        generate_youtube_thumbnail(project, badge_text="🔥 1080P")
    long = generate_youtube_thumbnail(project, custom_headline="MỘT DÒNG CHỮ RẤT DÀI " * 4)
    assert len(long["lines"]) >= 2                          # quá dài thì tự xuống dòng


@pytest.mark.skipif(config.WINDOWS_FONTS_DIR is None, reason="không phải Windows")
def test_thumbnail_background_skips_text_cards(isolated_projects_dir, tmp_path):
    """Thẻ miễn trừ, bảng ghim là ảnh chữ do app vẽ: không làm nền thumbnail (đã gặp khi xem ảnh thật 22/10/2026)."""
    from services.thumbnail_service import generate_youtube_thumbnail, thumbnail_font_path
    if thumbnail_font_path() is None:
        pytest.skip("máy không có font thumbnail")
    project = _make_project()
    card, photo = tmp_path / "card.jpg", tmp_path / "photo.jpg"
    Image.new("RGB", (1280, 720), (230, 20, 20)).save(card)     # đỏ: thẻ miễn trừ
    Image.new("RGB", (1280, 720), (20, 20, 230)).save(photo)    # xanh: ảnh cảnh thật
    project.scenes[0].image_path, project.scenes[0].metadata = str(card), {"visual_kind": "disclaimer"}
    project.scenes[1].image_path = str(photo)
    out = Path(generate_youtube_thumbnail(project, custom_headline="THỬ")["thumbnail_path"])
    with Image.open(out) as im:
        r, g, b = im.convert("RGB").getpixel((1850, 60))       # góc phải trên: không bị nền tối và chữ che
    assert b > r


@pytest.mark.asyncio
async def test_seo_data_of_another_language_is_dropped(isolated_projects_dir, monkeypatch):
    """Gặp 26/10/2026: dự án bản Anh mang từ khoá và gói SEO tiếng Việt chép từ bản Việt, thumbnail ra chữ Việt."""
    from services.thumbnail_service import default_lines
    project = _make_project(language="vi")
    _with_final_video(project.id, monkeypatch)
    await seo.generate_pack(project.id, KEYWORDS, llm=FakeLLM("good"))
    project = project_service.get_project(project.id)
    assert seo.current_state(project).pack is not None
    assert default_lines(project) == ["RỪNG SƯƠNG MÙ", "KHÔNG LỐI VỀ"]

    project.metadata["language"] = "en"                       # như dự án bản Anh chép nguyên youtube_seo bản Việt
    state = seo.current_state(project)
    assert state.pack is None and state.research is None
    assert default_lines(project) == [project.name]
