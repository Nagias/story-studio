"""Test ẩn bổ sung của bộ việc mẫu T1 (docs/bo-viec-mau): chỉ chép vào tests/ của bản chấm, không thuộc bộ test dự án.

Yêu cầu 3 của đề: project_service kiểm id bằng hàm của backend/security.py, không tự viết regex (đường cấm 7).
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "backend" / "services" / "project_service.py"


def test_project_service_kiem_id_bang_security_khong_tu_viet_regex():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    regex_calls = [node.lineno for node in ast.walk(tree)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"]
    assert not regex_calls, f"project_service.py còn tự gọi re.* (dòng {regex_calls}); kiểm id bằng security.py"
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
    assert names & {"is_safe_id", "require_safe_id"}, "project_service.py chưa dùng is_safe_id/require_safe_id của security.py"


def test_project_service_van_chan_id_sai():
    from services import project_service
    for bad in ("", "../x", "a/b", "x" * 65, "proj a"):
        try:
            project_service._get_project_dir(bad)
        except ValueError:
            continue
        raise AssertionError(f"id sai {bad!r} không bị chặn")
    assert project_service._get_project_dir("proj_ab").name == "proj_ab"
