"""
Dựng dự án từ kế hoạch chuyển thể vụ án và tạo bản ngôn ngữ khác (spec 7.7, 7.8).

- Kế hoạch lấy từ hàng việc giả (LLM giả của tests/case_adaptation_fakes.py), thư mục projects tạm (isolated_projects_dir).
- Không gọi 9router thật: bản tiếng Anh của cảnh sửa/thêm đi qua rewrite_english với LLM giả.
"""
import asyncio
import copy
import json
import sys
from itertools import combinations
from pathlib import Path

import pytest
from PIL import Image, ImageChops

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.case_adaptation_schemas import DISCLAIMER, CaseEvidence, SceneFlag
from models.evidence_schemas import EvidenceNode
from models.schemas import ProjectCreateRequest, Scene, SceneCreateRequest
from services import case_project_builder, case_store, project_service
from services.case_adaptation_checks import has_blocking_flags
from services.case_project_builder import (
    BOARD_TITLE,
    NODE_TYPE_LABELS_EN,
    BlockingFlagsError,
    LanguageVersionError,
    create_language_version,
    create_project_from_plan,
    plan_board_items,
    render_board_scene,
    render_disclaimer_card,
)
from services.investigation_board_engine import card_footprint, render_polaroid_card
from tests.case_adaptation_fakes import make_fake_llm
from tests.test_case_worker import _drain, _start

VI_VOICE = "vieneu-test-voice"
EN_VOICE = "en-US-AndrewMultilingualNeural"

# Lời Anh viết lại: 20-70 từ, không tên thật, không ngày tháng, dùng tên hư cấu dạng Anh.
REWRITE_3 = (                       # video 8 phút: lời Anh mỗi cảnh tối đa 33 từ
    "Shaking, Dang Thu Ha told the duty officer that a figure in a dark jacket had just sprinted through the port "
    "gate and vanished into the pouring rain."
)
REWRITE_NEW = (
    "Days later, a harbor clerk came forward with a handwritten gate log that placed one more visitor inside the "
    "port that night, long after the last shift had gone home."
)


# ---------------------------------------------------------------- helpers

def build_plan():
    """Kế hoạch 7 cảnh: 1 disclaimer, 2-5 image, 6 board (evd_1..evd_8), 7 video. Không còn cờ chặn."""
    case_id = _start()
    llm, _calls = make_fake_llm()
    _drain(llm)
    plan = case_store.load_plan(case_id)
    assert plan is not None and not has_blocking_flags(plan)
    return plan


def make_vi_project(plan):
    return create_project_from_plan(plan, "vi", VI_VOICE)


def scene_by_order(project, order):
    return next(s for s in project.scenes if s.order == order)


def media_file(project_id, rel):
    return project_service._get_project_dir(project_id) / rel


def run(coro):
    return asyncio.run(coro)


def real_names(plan):
    return [n for e in plan.bible.entities for n in e.real_names]


# ---------------------------------------------------------------- bảng ghim theo ngôn ngữ

def test_board_items_english_labels(isolated_projects_dir):
    plan = build_plan()
    nodes, _edges = plan_board_items(plan, "en")

    by_id = {n.id: n for n in nodes}
    evidence = {e.id: e for e in plan.bible.evidence}
    assert set(evidence) <= set(by_id)
    for ev_id, ev in evidence.items():
        node = by_id[ev_id]
        assert node.label == ev.label_en
        assert node.metadata["badge_label"] in NODE_TYPE_LABELS_EN.values()
        assert node.metadata["badge_label"] == NODE_TYPE_LABELS_EN[node.node_type]


def test_board_items_vietnamese_labels_keep_default_badge(isolated_projects_dir):
    plan = build_plan()
    nodes, _edges = plan_board_items(plan, "vi")

    by_id = {n.id: n for n in nodes}
    for ev in plan.bible.evidence:
        assert by_id[ev.id].label == ev.label_vi
        assert "badge_label" not in by_id[ev.id].metadata      # tiếng Việt dùng nhãn có sẵn của engine


def test_board_items_appear_at_first_reveal_and_have_fixed_layout(isolated_projects_dir):
    plan = build_plan()
    nodes, _edges = plan_board_items(plan, "vi")

    assert nodes and all(n.appearance_scene_order == 6 for n in nodes)    # cảnh 6 là cảnh board đầu tiên
    assert all(n.pinned and (n.x, n.y) != (0, 0) for n in nodes)
    assert len({(n.x, n.y) for n in nodes}) == len(nodes)                 # không hai thẻ trùng một vị trí

    # Đổi ngôn ngữ không đổi chỗ thẻ: cùng một bảng ghim, chỉ khác chữ.
    en_nodes, _ = plan_board_items(plan, "en")
    assert {n.id: (n.x, n.y, n.rotation_deg, n.metadata["card_scale"]) for n in nodes} == \
        {n.id: (n.x, n.y, n.rotation_deg, n.metadata["card_scale"]) for n in en_nodes}


def assert_cards_do_not_overlap(nodes):
    boxes = {n.id: card_footprint(n) for n in nodes}
    for (id_a, a), (id_b, b) in combinations(boxes.items(), 2):
        assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), f"thẻ {id_a} đè thẻ {id_b}"


def test_board_layout_gives_every_card_its_own_slot_even_with_a_victim_card(isolated_projects_dir):
    """Thẻ nạn nhân mang toạ độ mặc định (960, 540) từng làm engine xếp chồng mọi thẻ khác lên giữa bảng."""
    plan = build_plan()
    scenes = {s.order: s for s in plan.scenes}
    scenes[6].board_reveal += ["rel_1", "rel_2", "rel_3"]

    nodes, _edges = plan_board_items(plan, "vi")
    assert any(n.node_type == "victim" for n in nodes) and len(nodes) == 12
    positions = [(n.x, n.y) for n in nodes]
    assert len(set(positions)) == len(nodes)
    assert all(n.pinned for n in nodes)
    assert all(100 <= x <= 1820 and 150 <= y <= 930 for x, y in positions)
    assert_cards_do_not_overlap(nodes)
    victim = next(n for n in nodes if n.node_type == "victim")
    assert 640 <= victim.x <= 1280 and victim.y <= 600       # nạn nhân ở khoảng giữa bảng, không bị đẩy xuống đáy


def test_board_with_twenty_cards_keeps_cards_apart_in_both_languages(isolated_projects_dir, tmp_path):
    """Vụ án nhiều bằng chứng: 20 thẻ (16 bằng chứng + 4 thực thể ở đầu mút quan hệ) không thẻ nào đè thẻ nào."""
    plan = build_plan()
    kinds = ["weapon", "giám định", "địa điểm", "clue", "timeline", "clue", "clue", "forensic"]
    extra = [CaseEvidence(id=f"evd_extra_{i}", kind=kinds[i], label_vi=f"Vật chứng phụ {i}",
                          label_en=f"Extra exhibit {i}") for i in range(8)]
    plan.bible.evidence += extra
    scenes = {s.order: s for s in plan.scenes}
    scenes[6].board_reveal += ["rel_1", "rel_3"] + [e.id for e in extra[:4]]
    scenes[7].board_reveal += ["rel_2"] + [e.id for e in extra[4:]]

    vi_nodes, _ = plan_board_items(plan, "vi")
    en_nodes, _ = plan_board_items(plan, "en")

    assert len(vi_nodes) == 20
    assert_cards_do_not_overlap(vi_nodes)
    scales = {n.metadata["card_scale"] for n in vi_nodes}
    assert len(scales) == 1 and 0.8 <= scales.pop() < 1.0         # thu nhỏ đều, vẫn đọc được
    assert {n.id: (n.x, n.y, n.metadata["card_scale"]) for n in vi_nodes} == \
        {n.id: (n.x, n.y, n.metadata["card_scale"]) for n in en_nodes}

    out = render_board_scene(plan, 7, "vi", tmp_path / "board20.jpg")
    with Image.open(out) as img:
        assert img.size == (1920, 1080)


def test_board_items_skip_items_never_revealed(isolated_projects_dir):
    plan = build_plan()
    scene = next(s for s in plan.scenes if s.order == 6)
    scene.board_reveal = scene.board_reveal[:3]

    nodes, edges = plan_board_items(plan, "vi")
    assert sorted(n.id for n in nodes) == ["evd_1", "evd_2", "evd_3"]
    assert edges == []


def test_board_relations_become_threads_between_entity_cards(isolated_projects_dir):
    plan = build_plan()
    scenes = {s.order: s for s in plan.scenes}
    scenes[6].board_reveal += ["rel_1", "rel_3"]       # người báo án -> nạn nhân; nghi phạm -> nạn nhân
    scenes[7].board_reveal += ["rel_2"]                # nạn nhân -> công ty

    nodes, edges = plan_board_items(plan, "en")
    by_id = {n.id: n for n in nodes}
    entities = {e.id: e for e in plan.bible.entities}

    assert {e.id: e.appearance_scene_order for e in edges} == {"rel_1": 6, "rel_3": 6, "rel_2": 7}
    labels = {e.id: e.label for e in edges}
    assert labels["rel_1"] == "Found the body"
    # Đầu mút của quan hệ là thực thể: thẻ dùng tên hư cấu dạng Anh, hiện cùng lúc với sợi chỉ đầu tiên chạm tới nó.
    assert by_id["person_1"].label == entities["person_1"].alias_en
    assert by_id["person_1"].appearance_scene_order == 6
    assert by_id["organization_1"].appearance_scene_order == 7
    assert by_id["person_1"].node_type == "victim"
    assert by_id["person_3"].node_type == "suspect"
    assert by_id["person_1"].metadata["badge_label"] == "VICTIM"
    for edge in edges:
        assert edge.source_id in by_id and edge.target_id in by_id

    # Bảng ghim tích luỹ: ở cảnh 6 chưa có sợi chỉ của cảnh 7.
    from services.investigation_board_engine import get_cumulative_board_state
    from types import SimpleNamespace
    state6 = get_cumulative_board_state(SimpleNamespace(nodes=nodes, edges=edges), 6)
    state7 = get_cumulative_board_state(SimpleNamespace(nodes=nodes, edges=edges), 7)
    assert sorted(e.id for e in state6.cumulative_edges) == ["rel_1", "rel_3"]
    assert sorted(e.id for e in state7.cumulative_edges) == ["rel_1", "rel_2", "rel_3"]


def test_board_items_never_carry_descriptions_or_real_names(isolated_projects_dir):
    plan = build_plan()
    for ev in plan.bible.evidence:
        ev.description_vi = "Mô tả có tên thật Nguyễn Văn Hùng"
        ev.description_en = "Description naming Nguyen Van Hung"
    scene = next(s for s in plan.scenes if s.order == 6)
    scene.board_reveal += ["rel_1"]

    nodes, edges = plan_board_items(plan, "vi")
    dumped = json.dumps([n.model_dump() for n in nodes] + [e.model_dump() for e in edges], ensure_ascii=False)
    assert "Nguyễn Văn Hùng" not in dumped and "Nguyen Van Hung" not in dumped


def test_render_board_scene_draws_language_title_and_file(isolated_projects_dir, tmp_path, monkeypatch):
    plan = build_plan()
    titles = []
    real_render = case_project_builder.render_board_image

    def spy(state, output_path=None, *args, **kwargs):
        titles.append(state.title)
        return real_render(state, output_path, *args, **kwargs)

    monkeypatch.setattr(case_project_builder, "render_board_image", spy)

    vi = render_board_scene(plan, 6, "vi", tmp_path / "out" / "vi.jpg")
    en = render_board_scene(plan, 6, "en", tmp_path / "out" / "en.jpg")

    assert titles == [BOARD_TITLE["vi"], BOARD_TITLE["en"]] == ["Hồ sơ điều tra", "Case file"]
    assert vi.is_file() and en.is_file()
    with Image.open(vi) as a, Image.open(en) as b:
        assert a.size == b.size == (1920, 1080)
        assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is not None   # chữ khác nhau


def test_render_board_scene_before_any_reveal_is_just_the_corkboard(isolated_projects_dir, tmp_path):
    plan = build_plan()
    path = render_board_scene(plan, 2, "vi", tmp_path / "early.jpg")
    assert path.is_file()


def test_badge_label_overrides_default_badge():
    node = EvidenceNode(id="n1", label="Knife", node_type="weapon", x=500, y=400)
    default = render_polaroid_card(node)
    node_en = node.model_copy(deep=True)
    node_en.metadata["badge_label"] = NODE_TYPE_LABELS_EN["weapon"]
    english = render_polaroid_card(node_en)

    assert NODE_TYPE_LABELS_EN == {
        "victim": "VICTIM", "suspect": "SUSPECT", "weapon": "WEAPON", "clue": "CLUE",
        "forensic_report": "FORENSICS", "location": "SCENE", "timeline_event": "TIMELINE",
    }
    assert ImageChops.difference(default, english).getbbox() is not None


# ---------------------------------------------------------------- thẻ miễn trừ

def test_render_disclaimer_card_is_dark_with_white_centered_text(tmp_path):
    out = render_disclaimer_card(DISCLAIMER["vi"], tmp_path / "sub" / "card.jpg")

    assert out == tmp_path / "sub" / "card.jpg" and out.is_file()
    with Image.open(out) as img:
        assert img.size == (1920, 1080)
        rgb = img.convert("RGB")
        assert max(rgb.getpixel((5, 5))) < 60                      # nền tối
        white = [(x, y) for x in range(0, 1920, 6) for y in range(0, 1080, 6) if min(rgb.getpixel((x, y))) > 200]
        assert white, "không có chữ trắng"
        xs, ys = [p[0] for p in white], [p[1] for p in white]
        assert abs((min(xs) + max(xs)) / 2 - 960) < 120            # căn giữa ngang
        assert abs((min(ys) + max(ys)) / 2 - 540) < 120            # và khối chữ nằm quanh giữa khung


def test_render_disclaimer_card_wraps_long_text_inside_the_frame(tmp_path):
    text = " ".join(["This story is based on a real case;"] * 8)
    out = render_disclaimer_card(text, tmp_path / "long.jpg")
    with Image.open(out) as img:
        rgb = img.convert("RGB")
        left = [x for x in range(0, 1920, 4) for y in range(0, 1080, 8) if min(rgb.getpixel((x, y))) > 200]
        assert left and min(left) > 100 and max(left) < 1820       # chữ không tràn mép


# ---------------------------------------------------------------- dựng dự án bản gốc

def test_create_vi_project(isolated_projects_dir):
    plan = build_plan()
    project = create_project_from_plan(plan, "vi", VI_VOICE, visual_style="neo_noir_silhouette")

    assert project.id.startswith("proj_crime_") and len(project.id) == len("proj_crime_") + 8
    assert len(project.scenes) == len(plan.scenes)
    assert project.scenes[0].text == DISCLAIMER["vi"]
    assert [s.id for s in project.scenes] == [f"scene_{s.order:03d}" for s in plan.scenes]
    assert project.metadata["language"] == "vi"
    assert project.metadata["case_id"] == plan.case_id
    assert project.metadata["sibling_project_ids"] == []
    assert project.metadata["voices"] == {"vi": VI_VOICE}
    assert project.name == plan.bible.title_vi
    assert project.voice == VI_VOICE
    assert project.style_preset == "neo_noir_silhouette"
    assert project.bgm_overall_genre == "mysterious_dark"
    assert project.image_provider == "meta_muse_cloud"

    # Lưu thật xuống đĩa
    assert project_service.get_project(project.id) == project

    for scene, adapted in zip(project.scenes, plan.scenes):
        assert scene.text == adapted.narration_vi
        assert scene.image_prompt == adapted.image_prompt
        assert scene.video_prompt == adapted.video_prompt
        assert scene.camera_motion == adapted.camera_motion
        assert scene.sfx_cue == adapted.sfx_cue
        assert scene.bgm_energy == adapted.bgm_energy
        meta = scene.metadata
        assert meta["case_id"] == plan.case_id
        assert meta["narration"] == {"vi": adapted.narration_vi, "en": adapted.narration_en}
        assert meta["narration_source"] == scene.text
        assert meta["visual_kind"] == adapted.visual_kind
        assert meta["board_reveal"] == adapted.board_reveal
        assert meta["narrative_beat"] == adapted.narrative_beat
        assert scene.shot_type == ("B_ROLL_BOARD" if adapted.visual_kind == "board" else "A_ROLL_NOIR")

    video = scene_by_order(project, 7)
    assert video.metadata["visual_kind"] == "video"
    assert video.video_prompt and "sedan" in video.video_prompt          # video_prompt được giữ lại


def test_create_project_draws_board_and_disclaimer_images_into_the_project(isolated_projects_dir):
    plan = build_plan()
    project = make_vi_project(plan)

    for order in (1, 6):
        scene = scene_by_order(project, order)
        file = media_file(project.id, f"images/scene_{order:03d}.jpg")
        assert file.is_file()
        with Image.open(file) as img:
            assert img.size == (1920, 1080)
        assert scene.image_path == str(file)
        assert scene.image_url == f"/api/projects/{project.id}/media/images/scene_{order:03d}.jpg"
        assert (scene.status, scene.status_image) == ("imaged", "ready")

    for order in (2, 3, 4, 5, 7):
        scene = scene_by_order(project, order)
        assert (scene.status, scene.status_image) == ("draft", "idle")
        assert scene.image_path is None and scene.image_url is None
        assert not media_file(project.id, f"images/scene_{order:03d}.jpg").exists()

    # Bảng ghim chỉ ghi trong thư mục dự án, không đụng thư mục công khai.
    static_boards = Path(project_service.__file__).resolve().parent.parent / "static" / "evidence_boards" / plan.case_id
    assert not static_boards.exists()


def test_create_project_board_follows_language(isolated_projects_dir):
    plan = build_plan()
    vi = make_vi_project(plan)
    en = create_project_from_plan(plan, "en", EN_VOICE)

    assert en.scenes[0].text == DISCLAIMER["en"]
    assert en.name == plan.bible.title_en
    assert en.metadata["language"] == "en"
    with Image.open(media_file(vi.id, "images/scene_006.jpg")) as a, Image.open(media_file(en.id, "images/scene_006.jpg")) as b:
        assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is not None
    with Image.open(media_file(vi.id, "images/scene_001.jpg")) as a, Image.open(media_file(en.id, "images/scene_001.jpg")) as b:
        assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is not None


def test_create_project_voices_param_is_stored_with_chosen_voice(isolated_projects_dir):
    plan = build_plan()
    project = create_project_from_plan(plan, "vi", VI_VOICE, voices={"en": EN_VOICE, "vi": "ignored"})
    assert project.metadata["voices"] == {"en": EN_VOICE, "vi": VI_VOICE}


def test_create_project_never_copies_real_names_into_files(isolated_projects_dir):
    plan = build_plan()
    # Cố tình để thông tin nhạy cảm trong các field kế hoạch không được phép đưa vào dự án.
    plan.warnings.append("Đã tự thay tên thật 'Nguyễn Văn Hùng' bằng 'Trịnh Quang Vũ' ở cảnh 3.")
    plan.check_warnings.append("Cảnh bị nghi tên Lê Thị Mai")
    for ev in plan.bible.evidence:
        ev.description_vi = "Liên quan Nguyễn Văn Hùng"
    project = make_vi_project(plan)

    root = project_service._get_project_dir(project.id)
    blob = (root / "project.json").read_text(encoding="utf-8").lower()
    for name in real_names(plan):
        assert name.lower() not in blob, name


def test_create_blocked_by_flags(isolated_projects_dir):
    plan = build_plan()
    plan.scenes[2].flags = [SceneFlag(kind="unknown_name", field="narration_vi",
                                      detail="Tên thật chưa có tên thay thế: 'Zed Quux'")]
    with pytest.raises(BlockingFlagsError) as info:
        make_vi_project(plan)
    assert "Zed Quux" not in str(info.value)                         # không in chi tiết cờ (có thể chứa tên thật)
    assert "3" in str(info.value)                                    # nhưng nói được cảnh nào bị đánh dấu
    assert [p for p in isolated_projects_dir.iterdir() if p.name != "_cases"] == []   # không để lại dự án dở

    plan = build_plan()
    plan.flags = [SceneFlag(kind="unknown_name", field="title", detail="x")]          # cờ cấp kế hoạch cũng chặn
    with pytest.raises(BlockingFlagsError):
        make_vi_project(plan)


def test_create_project_cleans_up_when_drawing_fails(isolated_projects_dir, monkeypatch):
    plan = build_plan()

    def boom(*args, **kwargs):
        raise RuntimeError("không vẽ được")

    monkeypatch.setattr(case_project_builder, "render_board_scene", boom)
    with pytest.raises(RuntimeError):
        make_vi_project(plan)
    assert [p for p in isolated_projects_dir.iterdir() if p.name != "_cases"] == []


def force_project_ids(monkeypatch, *ids):
    """Ép những id dự án đầu tiên builder sinh ra (để dựng va chạm id); hết danh sách thì sinh id thật."""
    queue = list(ids)
    real = case_project_builder._new_project_id
    monkeypatch.setattr(case_project_builder, "_new_project_id", lambda: queue.pop(0) if queue else real())


def snapshot_project(project_id):
    root = project_service._get_project_dir(project_id)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_create_project_id_collision_regenerates_id_and_keeps_existing_project(isolated_projects_dir, monkeypatch):
    plan = build_plan()
    existing = make_vi_project(plan)
    (project_service._get_project_dir(existing.id) / "images" / "ghi_chu.txt").write_text("giữ nguyên", encoding="utf-8")
    before = snapshot_project(existing.id)

    force_project_ids(monkeypatch, existing.id, existing.id, "proj_crime_00000001")
    created = make_vi_project(plan)

    assert created.id == "proj_crime_00000001"
    assert snapshot_project(existing.id) == before                   # dự án trùng id không bị ghi đè hay xoá
    assert project_service.get_project(created.id) is not None


def test_create_project_failure_after_id_collision_never_deletes_existing_project(isolated_projects_dir, monkeypatch):
    plan = build_plan()
    existing = make_vi_project(plan)
    before = snapshot_project(existing.id)

    def boom(*args, **kwargs):
        raise RuntimeError("không vẽ được")

    force_project_ids(monkeypatch, existing.id, "proj_crime_00000002")
    monkeypatch.setattr(case_project_builder, "render_board_scene", boom)
    with pytest.raises(RuntimeError):
        make_vi_project(plan)

    assert snapshot_project(existing.id) == before                   # hoàn tác chỉ xoá thư mục do lần gọi này tạo
    assert sorted(p.name for p in isolated_projects_dir.iterdir() if p.name != "_cases") == [existing.id]


# ---------------------------------------------------------------- bản ngôn ngữ khác

def prepare_source_media(project):
    """Giả lập dự án đã làm một phần: ảnh cảnh 2, clip Muse cảnh 3, giọng, phụ đề, đoạn dựng, video cuối."""
    root = project_service._get_project_dir(project.id)
    Image.new("RGB", (64, 36), (10, 120, 200)).save(root / "images" / "scene_002.jpg")
    (root / "videos" / "scene_003_muse.mp4").write_bytes(b"fake-muse-clip")
    (root / "videos" / "scene_003.mp4").write_bytes(b"fake-segment")
    (root / "audio" / "scene_002.mp3").write_bytes(b"fake-audio")
    (root / "audio" / "scene_002.srt").write_bytes(b"fake-srt")
    (root / "renders" / "story_final.mp4").write_bytes(b"fake-final")
    (root / "renders" / "thumb.jpg").write_bytes(b"fake-thumb")

    project = project_service.get_project(project.id)
    s2, s3 = scene_by_order(project, 2), scene_by_order(project, 3)
    s2.image_path = str(root / "images" / "scene_002.jpg")
    s2.image_url = f"/api/projects/{project.id}/media/images/scene_002.jpg"
    s2.status_image, s2.status = "ready", "ready"
    s2.voice_audio_path = str(root / "audio" / "scene_002.mp3")
    s2.audio_path = s2.voice_audio_path
    s2.voice_audio_url = f"/api/projects/{project.id}/media/audio/scene_002.mp3"
    s2.audio_url = s2.voice_audio_url
    s2.srt_path = str(root / "audio" / "scene_002.srt")
    s2.srt_url = f"/api/projects/{project.id}/media/audio/scene_002.srt"
    s2.status_voice, s2.duration = "ready", 6.5
    s3.motion_video_path = str(root / "videos" / "scene_003_muse.mp4")
    s3.video_url = f"/api/projects/{project.id}/media/videos/scene_003_muse.mp4"
    s3.video_segment_path = str(root / "videos" / "scene_003.mp4")
    s3.video_segment_url = f"/api/projects/{project.id}/media/videos/scene_003.mp4"
    s3.media_view_mode, s3.status_video = "video", "ready"
    project.final_video_path = str(root / "renders" / "story_final.mp4")
    project.final_video_url = f"/api/projects/{project.id}/media/renders/story_final.mp4"
    project.thumbnail_path = str(root / "renders" / "thumb.jpg")
    project.thumbnail_url = f"/api/projects/{project.id}/media/renders/thumb.jpg"
    project.seo_title, project.seo_description, project.seo_tags = "Tiêu đề SEO", "Mô tả SEO", ["a"]
    project_service._save_project(project)
    return project_service.get_project(project.id)


def test_language_version_copies_media_and_switches_text(isolated_projects_dir):
    plan = build_plan()
    source = prepare_source_media(make_vi_project(plan))
    llm, calls = make_fake_llm()

    new, rewritten = run(create_language_version(source.id, "en", llm=llm))

    assert rewritten == [] and calls == []                       # không scene nào đổi: không gọi REWRITE_EN
    assert new.id != source.id and new.id.startswith("proj_crime_")
    assert new.voice == EN_VOICE
    assert new.metadata["language"] == "en" and new.metadata["case_id"] == plan.case_id
    assert new.metadata["voices"] == {"vi": VI_VOICE, "en": EN_VOICE}
    assert new.name == plan.bible.title_en
    assert len(new.scenes) == len(source.scenes)
    for scene, adapted in zip(new.scenes, plan.scenes):
        assert scene.text == adapted.narration_en
        assert scene.metadata["narration_source"] == adapted.narration_en
        assert scene.metadata["narration"] == {"vi": adapted.narration_vi, "en": adapted.narration_en}
        assert scene.image_prompt == adapted.image_prompt and scene.video_prompt == adapted.video_prompt
    assert new.scenes[0].text == DISCLAIMER["en"]

    # Media được chép, đường dẫn và URL trỏ sang dự án mới
    clip = media_file(new.id, "videos/scene_003_muse.mp4")
    assert clip.read_bytes() == b"fake-muse-clip"
    s3 = scene_by_order(new, 3)
    assert s3.motion_video_path == str(clip)
    assert s3.video_url == s3.video_segment_url == f"/api/projects/{new.id}/media/videos/scene_003_muse.mp4"
    assert (s3.media_view_mode, s3.status_video) == ("video", "ready")
    s2 = scene_by_order(new, 2)
    assert s2.image_path == str(media_file(new.id, "images/scene_002.jpg"))
    assert s2.image_url == f"/api/projects/{new.id}/media/images/scene_002.jpg"
    assert (s2.status_image, s2.status) == ("ready", "imaged")
    assert Image.open(media_file(new.id, "images/scene_002.jpg")).size == (64, 36)

    # Giọng, phụ đề, đoạn dựng, video cuối và ảnh bìa không đi theo
    assert not list((project_service._get_project_dir(new.id) / "audio").iterdir())
    assert sorted(p.name for p in (project_service._get_project_dir(new.id) / "videos").iterdir()) == ["scene_003_muse.mp4"]
    assert not list((project_service._get_project_dir(new.id) / "renders").iterdir())
    for scene in new.scenes:
        assert scene.voice_audio_path is None and scene.voice_audio_url is None
        assert scene.audio_path is None and scene.audio_url is None
        assert scene.srt_path is None and scene.srt_url is None
        assert scene.duration is None and scene.status_voice == "idle"
        assert scene.video_segment_path is None
    assert s2.voice_audio_path is None
    assert new.final_video_path is None and new.final_video_url is None
    assert new.thumbnail_path is None and new.thumbnail_url is None
    assert new.seo_title is None and new.seo_description is None and new.seo_tags == []

    # Cảnh board và disclaimer vẽ lại bằng chữ của ngôn ngữ mới
    for order in (1, 6):
        with Image.open(media_file(source.id, f"images/scene_{order:03d}.jpg")) as a, \
                Image.open(media_file(new.id, f"images/scene_{order:03d}.jpg")) as b:
            assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is not None
        scene = scene_by_order(new, order)
        assert scene.image_path == str(media_file(new.id, f"images/scene_{order:03d}.jpg"))
        assert scene.image_url == f"/api/projects/{new.id}/media/images/scene_{order:03d}.jpg"

    # Liên kết hai chiều, lưu cả hai dự án
    reloaded_new = project_service.get_project(new.id)
    reloaded_source = project_service.get_project(source.id)
    assert reloaded_new.metadata["sibling_project_ids"] == [source.id]
    assert reloaded_source.metadata["sibling_project_ids"] == [new.id]
    # Dự án gốc giữ nguyên media và lời
    assert reloaded_source.scenes[0].text == DISCLAIMER["vi"]
    assert media_file(source.id, "audio/scene_002.mp3").read_bytes() == b"fake-audio"
    assert reloaded_source.final_video_path == source.final_video_path


def test_language_version_uses_given_voice_and_settings_voice(isolated_projects_dir):
    plan = build_plan()
    source = make_vi_project(plan)
    saved = project_service.get_project(source.id)
    saved.settings = {"voice": VI_VOICE, "bgm": "x"}     # giao diện ưu tiên settings.voice hơn project.voice
    project_service._save_project(saved)

    new, _ = run(create_language_version(source.id, "en", "en-GB-RyanNeural"))

    assert new.voice == "en-GB-RyanNeural"
    assert new.settings == {"voice": "en-GB-RyanNeural", "bgm": "x"}
    assert new.metadata["voices"]["en"] == "en-GB-RyanNeural"
    assert project_service.get_project(source.id).settings["voice"] == VI_VOICE     # bản gốc không đổi


def test_language_version_prefers_voice_remembered_in_metadata(isolated_projects_dir):
    plan = build_plan()
    source = create_project_from_plan(plan, "vi", VI_VOICE, voices={"en": "en-AU-WilliamNeural"})

    new, _ = run(create_language_version(source.id, "en"))
    assert new.voice == "en-AU-WilliamNeural"


def test_language_version_rewrites_changed_scenes(isolated_projects_dir):
    plan = build_plan()
    source = make_vi_project(plan)
    saved = project_service.get_project(source.id)
    edited_vi = "Run rẩy, bà Hà gọi trực ban hình sự và nói vừa thấy một bóng người áo khoác sẫm chạy qua cổng cảng."
    scene_by_order(saved, 3).text = edited_vi                   # cảnh bị sửa lời Việt
    new_vi = "Vài ngày sau, một nhân viên cảng đến trình ra cuốn sổ ghi tay người ra vào cổng đêm đó."
    new_order = len(saved.scenes) + 1
    saved.scenes.append(Scene(id=f"scene_{new_order:03d}", order=new_order, text=new_vi))     # cảnh thêm sau khi tạo dự án
    project_service._save_project(saved)

    llm, calls = make_fake_llm({"REWRITE_EN": {"scenes": [
        {"order": 3, "narration_en": REWRITE_3},
        {"order": new_order, "narration_en": REWRITE_NEW},
    ]}})

    new, rewritten = run(create_language_version(source.id, "en", llm=llm))

    assert rewritten == [3, new_order]
    assert calls == ["REWRITE_EN"]                              # đúng một lần gọi cho cả hai cảnh
    assert edited_vi in llm.prompts[0] and new_vi in llm.prompts[0]
    s3 = scene_by_order(new, 3)
    assert s3.text == REWRITE_3
    assert s3.metadata["narration_source"] == REWRITE_3
    assert s3.metadata["narration"] == {"vi": edited_vi, "en": REWRITE_3}
    added_scene = scene_by_order(new, new_order)
    assert added_scene.text == REWRITE_NEW
    assert added_scene.metadata["narration"] == {"vi": new_vi, "en": REWRITE_NEW}
    assert added_scene.metadata["narration_source"] == REWRITE_NEW
    for scene, adapted in zip(new.scenes, plan.scenes):                # các cảnh còn lại giữ lời Anh của kế hoạch
        if scene.order not in (3, new_order):
            assert scene.text == adapted.narration_en
    assert len(new.scenes) == len(plan.scenes) + 1


def test_language_version_rewritten_text_gets_aliases_and_blocks_real_names(isolated_projects_dir, monkeypatch):
    plan = build_plan()
    source = make_vi_project(plan)
    saved = project_service.get_project(source.id)
    scene_by_order(saved, 4).text = "Câu đã sửa của cảnh bốn, kể lại diễn biến bằng lời mới."
    project_service._save_project(saved)

    seen = []

    async def leaky(bible, items, *, llm=None, target_minutes=None, total_scenes=None):
        seen.append((target_minutes, total_scenes))
        return {4: "Nguyen Van Hung lay still in the loading yard while the rain kept falling on the silent containers "
                   "and nobody yet knew who had been standing beside him in the dark."}

    monkeypatch.setattr(case_project_builder, "rewrite_english", leaky)

    # Tên thật đã có tên hư cấu: tự thay, không chặn.
    new, rewritten = run(create_language_version(source.id, "en"))
    assert rewritten == [4]
    assert seen == [(plan.target_minutes, len(plan.scenes))]          # lời Anh viết lại theo thời lượng và số cảnh
    text = scene_by_order(new, 4).text
    assert "Nguyen Van Hung" not in text and "Trinh Quang Vu lay still" in text

    # Tên chỉ regex bắt được trên bài gốc (chưa có tên hư cấu): chặn, và thông báo không nêu tên thật.
    case_store.save_source(plan.case_id, case_store.load_source(plan.case_id) + "\nÔng Hoàng Minh Tuấn là tài xế xe tải.")

    async def leaky_unknown(bible, items, *, llm=None, target_minutes=None, total_scenes=None):
        return {4: "Hoang Minh Tuan watched the yard from his truck while the rain kept falling and nobody noticed "
                   "him there, parked in the dark beside the silent containers all night long."}

    monkeypatch.setattr(case_project_builder, "rewrite_english", leaky_unknown)
    before = sorted(p.name for p in isolated_projects_dir.iterdir())
    with pytest.raises(LanguageVersionError) as info:
        run(create_language_version(source.id, "en"))
    message = str(info.value)
    assert "4" in message and "Hoang" not in message and "Hoàng" not in message
    assert sorted(p.name for p in isolated_projects_dir.iterdir()) == before          # không để lại dự án dở
    assert project_service.get_project(source.id).metadata["sibling_project_ids"] == [new.id]


def test_language_version_rewritten_text_with_exact_date_is_blocked_without_naming_the_text(isolated_projects_dir, monkeypatch):
    plan = build_plan()
    source = make_vi_project(plan)
    saved = project_service.get_project(source.id)
    scene_by_order(saved, 4).text = "Câu đã sửa của cảnh bốn, kể lại diễn biến bằng lời mới."
    project_service._save_project(saved)

    async def dated(bible, items, *, llm=None, target_minutes=None, total_scenes=None):
        return {4: "On October 7, 2014 the loading yard lay silent under the rain while nobody yet knew who had been "
                   "standing beside the victim in the dark, parked between the silent containers all night long."}

    monkeypatch.setattr(case_project_builder, "rewrite_english", dated)
    before = sorted(p.name for p in isolated_projects_dir.iterdir())

    with pytest.raises(LanguageVersionError) as info:
        run(create_language_version(source.id, "en"))

    message = str(info.value)
    assert "4" in message                                            # nêu cảnh nào
    assert "October" not in message and "2014" not in message        # không nêu lại nội dung
    assert sorted(p.name for p in isolated_projects_dir.iterdir()) == before          # không để lại dự án dở
    assert project_service.get_project(source.id).metadata["sibling_project_ids"] == []


def test_language_version_id_collision_regenerates_id_and_keeps_source(isolated_projects_dir, monkeypatch):
    plan = build_plan()
    source = prepare_source_media(make_vi_project(plan))
    before = snapshot_project(source.id)

    force_project_ids(monkeypatch, source.id, "proj_crime_00000003")
    new, _ = run(create_language_version(source.id, "en"))

    assert new.id == "proj_crime_00000003"
    after = snapshot_project(source.id)
    changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
    assert changed == {"project.json"}                               # chỉ thêm liên kết anh em; media của dự án gốc còn nguyên
    assert project_service.get_project(source.id).metadata["sibling_project_ids"] == [new.id]
    assert media_file(source.id, "audio/scene_002.mp3").read_bytes() == b"fake-audio"


def test_language_version_failure_after_id_collision_never_deletes_source(isolated_projects_dir, monkeypatch):
    plan = build_plan()
    source = prepare_source_media(make_vi_project(plan))
    before = snapshot_project(source.id)

    def boom(*args, **kwargs):
        raise RuntimeError("không vẽ được")

    force_project_ids(monkeypatch, source.id, "proj_crime_00000004")
    monkeypatch.setattr(case_project_builder, "_draw_text_image", boom)
    with pytest.raises(RuntimeError):
        run(create_language_version(source.id, "en"))

    assert snapshot_project(source.id) == before
    assert sorted(p.name for p in isolated_projects_dir.iterdir() if p.name != "_cases") == [source.id]


def test_language_version_twice_creates_two_projects(isolated_projects_dir):
    plan = build_plan()
    source = make_vi_project(plan)

    first, _ = run(create_language_version(source.id, "en"))
    second, _ = run(create_language_version(source.id, "en"))

    assert first.id != second.id
    assert project_service.get_project(source.id).metadata["sibling_project_ids"] == [first.id, second.id]
    assert project_service.get_project(first.id).metadata["sibling_project_ids"] == [source.id]
    assert project_service.get_project(second.id).metadata["sibling_project_ids"] == [source.id]
    ids = {p["id"] for p in project_service.list_projects()}
    assert {source.id, first.id, second.id} <= ids


def test_language_version_rejects_plain_project(isolated_projects_dir):
    plain = project_service.create_project(ProjectCreateRequest(name="Dự án thường"))
    with pytest.raises(LanguageVersionError, match="Dự án này không được tạo từ kế hoạch chuyển thể."):
        run(create_language_version(plain.id, "en"))

    # Có case_id nhưng không có lời kể theo ngôn ngữ cũng bị từ chối.
    project_service.add_scene(plain.id, SceneCreateRequest(text="Một cảnh", metadata={"case_id": "case_x"}))
    saved = project_service.get_project(plain.id)
    saved.metadata["case_id"] = "case_x"
    project_service._save_project(saved)
    with pytest.raises(LanguageVersionError, match="Dự án này không được tạo từ kế hoạch chuyển thể."):
        run(create_language_version(plain.id, "en"))


def test_language_version_needs_the_saved_plan(isolated_projects_dir):
    plan = build_plan()
    source = make_vi_project(plan)
    saved = project_service.get_project(source.id)
    saved.metadata["case_id"] = "case_khongco1"
    project_service._save_project(saved)

    with pytest.raises(LanguageVersionError, match="kế hoạch"):
        run(create_language_version(source.id, "en"))
    assert sorted(p.name for p in isolated_projects_dir.iterdir() if p.name != "_cases") == [source.id]


def test_language_version_rejects_unknown_project_language_and_same_language(isolated_projects_dir):
    plan = build_plan()
    source = make_vi_project(plan)

    with pytest.raises(LanguageVersionError):
        run(create_language_version("proj_khongco", "en"))
    with pytest.raises(LanguageVersionError):
        run(create_language_version("../ngoai thu muc", "en"))
    with pytest.raises(LanguageVersionError):
        run(create_language_version(source.id, "fr"))
    with pytest.raises(LanguageVersionError):
        run(create_language_version(source.id, "vi"))        # đã là tiếng Việt


def test_language_version_to_vietnamese_reuses_plan_text_but_cannot_rewrite(isolated_projects_dir):
    plan = build_plan()
    en_project = create_project_from_plan(plan, "en", EN_VOICE)

    vi, rewritten = run(create_language_version(en_project.id, "vi"))
    assert rewritten == []
    assert vi.metadata["language"] == "vi"
    assert [s.text for s in vi.scenes] == [s.narration_vi for s in plan.scenes]
    assert vi.voice == "vi-VN-NamMinhNeural"

    # Cảnh tiếng Anh bị sửa thì chưa có đường viết lại sang tiếng Việt: báo rõ, không im lặng giữ lời cũ.
    saved = project_service.get_project(en_project.id)
    scene_by_order(saved, 3).text = "A line the user rewrote by hand in English."
    project_service._save_project(saved)
    with pytest.raises(LanguageVersionError, match="3"):
        run(create_language_version(en_project.id, "vi"))


def test_language_version_failure_of_rewrite_leaves_no_new_project(isolated_projects_dir):
    plan = build_plan()
    source = make_vi_project(plan)
    saved = project_service.get_project(source.id)
    scene_by_order(saved, 3).text = "Một lời Việt mới cho cảnh ba, được sửa tay sau khi tạo dự án."
    project_service._save_project(saved)

    bad = {"scenes": [{"order": 3, "narration_en": "Too short."}]}
    llm, calls = make_fake_llm({"REWRITE_EN": bad})
    from services.case_adaptation_steps import StepFailed

    with pytest.raises(StepFailed):
        run(create_language_version(source.id, "en", llm=llm))
    assert calls == ["REWRITE_EN"] * 3
    assert sorted(p.name for p in isolated_projects_dir.iterdir() if p.name != "_cases") == [source.id]
    assert project_service.get_project(source.id).metadata["sibling_project_ids"] == []


def test_language_version_whitespace_only_edit_is_not_a_rewrite(isolated_projects_dir):
    plan = build_plan()
    source = make_vi_project(plan)
    saved = project_service.get_project(source.id)
    scene = scene_by_order(saved, 3)
    scene.text = "  " + scene.text.replace(" ", "  ", 2) + "\n"        # giao diện có thể tự chuẩn hoá khoảng trắng
    project_service._save_project(saved)
    llm, calls = make_fake_llm()

    new, rewritten = run(create_language_version(source.id, "en", llm=llm))
    assert rewritten == [] and calls == []
    assert scene_by_order(new, 3).text == plan.scenes[2].narration_en


def test_language_version_disclaimer_is_always_the_fixed_sentence(isolated_projects_dir):
    plan = build_plan()
    source = make_vi_project(plan)
    saved = project_service.get_project(source.id)
    scene_by_order(saved, 1).text = "Lời miễn trừ bị sửa tay."
    project_service._save_project(saved)
    llm, calls = make_fake_llm()

    new, rewritten = run(create_language_version(source.id, "en", llm=llm))
    assert rewritten == [] and calls == []
    assert new.scenes[0].text == DISCLAIMER["en"]
    assert new.scenes[0].metadata["narration"] == dict(DISCLAIMER)
