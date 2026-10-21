"""Test không bao giờ ghi vào projects/ thật (CLAUDE.md đường cấm 11): conftest đổi PROJECTS_DIR ở mọi module."""
import sys
from pathlib import Path

from models.schemas import ProjectCreateRequest
from services import project_service

REAL_PROJECTS = (Path(__file__).resolve().parent.parent / "projects").resolve()


def test_no_loaded_module_points_at_real_projects_dir(isolated_projects_dir):
    leaking = []
    for name, module in list(sys.modules.items()):
        namespace = getattr(module, "__dict__", None)
        value = namespace.get("PROJECTS_DIR") if isinstance(namespace, dict) else None
        if isinstance(value, Path) and value.resolve() == REAL_PROJECTS:
            leaking.append(name)
    assert not leaking, f"các module này vẫn trỏ vào projects/ thật: {leaking}"


def test_created_project_lands_in_tmp_dir(isolated_projects_dir):
    project = project_service.create_project(ProjectCreateRequest(name="Thử cô lập"))
    assert (isolated_projects_dir / project.id / "project.json").exists()
    assert not (REAL_PROJECTS / project.id).exists()
