"""Test ẩn bổ sung của bộ việc mẫu T5 (docs/bo-viec-mau): chỉ chép vào tests/ của bản chấm, không thuộc bộ test dự án.

Yêu cầu 2 của đề: không còn vệt sáng ở góc trái dưới (hai lớp làm tối bên trái và phía dưới phải chồng lên nhau).
Yêu cầu 1 (vế sau): người dùng tự chọn cảnh thì vẫn dùng đúng cảnh đó, kể cả khi là ảnh chữ.
"""
from pathlib import Path

import pytest
from PIL import Image

import config
from models.schemas import ProjectCreateRequest, SceneCreateRequest
from services import project_service


def _project_with(images: list, tmp_path: Path, kinds: dict | None = None):
    project = project_service.create_project(ProjectCreateRequest(name="Thử thumbnail"))
    for i in range(len(images)):
        project_service.add_scene(project.id, SceneCreateRequest(text=f"Cảnh {i + 1}.", image_prompt="x"))
    project = project_service.get_project(project.id)
    for i, (scene, color) in enumerate(zip(project.scenes, images)):
        path = tmp_path / f"anh_{i}.jpg"
        Image.new("RGB", (1280, 720), color).save(path)
        scene.image_path = str(path)
        scene.metadata = {"visual_kind": (kinds or {}).get(i, "scene")}
    project_service.save_project(project)
    return project


def _skip_without_font():
    from services.thumbnail_service import thumbnail_font_path
    if config.WINDOWS_FONTS_DIR is None or thumbnail_font_path() is None:
        pytest.skip("máy không có font thumbnail")


def _luma(im, x, y):
    r, g, b = im.getpixel((x, y))
    return 0.299 * r + 0.587 * g + 0.114 * b


def test_khong_con_vet_sang_o_goc_trai_duoi(isolated_projects_dir, tmp_path):
    _skip_without_font()
    from services.thumbnail_service import generate_youtube_thumbnail
    project = _project_with([(210, 210, 210)], tmp_path)
    out = Path(generate_youtube_thumbnail(project, custom_headline="THỬ")["thumbnail_path"])
    with Image.open(out) as raw:
        im = raw.convert("RGB")
        # dọc theo một cột (tránh chỗ có chữ), xuống càng thấp thì lớp tối phía dưới càng dày: ảnh không được sáng lên
        for x in (450, 600, 900, 1200):
            column = [_luma(im, x, y) for y in range(760, 1076, 10)]
            jumps = [(760 + 10 * i, round(column[i - 1]), round(column[i])) for i in range(1, len(column))
                     if column[i] > column[i - 1] + 4]
            assert not jumps, f"cột x={x}: ảnh sáng lên khi xuống thấp (vệt sáng) ở (y, trước, sau) = {jumps[:3]}"


def test_nguoi_dung_chon_anh_chu_thi_van_dung_anh_do(isolated_projects_dir, tmp_path):
    _skip_without_font()
    from services.thumbnail_service import generate_youtube_thumbnail
    project = _project_with([(230, 20, 20), (20, 20, 230)], tmp_path, kinds={0: "disclaimer"})
    out = Path(generate_youtube_thumbnail(project, scene_index=0, custom_headline="THỬ")["thumbnail_path"])
    with Image.open(out) as raw:
        r, g, b = raw.convert("RGB").getpixel((1850, 60))
    assert r > b, "người dùng chọn cảnh 0 (thẻ chữ đỏ) mà nền lại lấy cảnh khác"
