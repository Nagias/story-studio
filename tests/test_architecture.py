"""Đường cấm trong CLAUDE.md mục 5 mà máy kiểm được.

Chỗ vi phạm có từ trước ghi trong các bảng ALLOWED_* (ngoại lệ hẹp: đúng file, đúng số lần).
- Thêm vi phạm mới (file mới hoặc nhiều hơn số đã ghi): test báo lỗi. Làm theo cột "Làm thay" ở CLAUDE.md mục 5.
- Sửa bớt vi phạm cũ: test cũng báo, để giảm số trong bảng cho khớp (ngoại lệ không được rộng hơn thực tế).
- Muốn thêm ngoại lệ: phải ghi lý do và được duyệt như thay đổi kiến trúc (CLAUDE.md mục 2.1).
"""
import ast
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
STATIC = BACKEND / "static"


def _py_files():
    files = [p for p in BACKEND.rglob("*.py") if "__pycache__" not in p.parts]
    files += [ROOT / "run.py", *sorted((ROOT / "tools").glob("*.py"))]
    return sorted(files)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _trees():
    for path in _py_files():
        yield _rel(path), ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _compare(rule: str, actual: Counter, allowed: dict) -> None:
    problems = []
    for name in sorted(set(actual) | set(allowed)):
        got, ok = actual.get(name, 0), allowed.get(name, 0)
        if got > ok:
            problems.append(f"  {name}: {got} chỗ (ngoại lệ cho phép {ok}) — vi phạm mới")
        elif got < ok:
            problems.append(f"  {name}: còn {got} chỗ nhưng ngoại lệ ghi {ok} — hãy giảm số trong bảng ngoại lệ")
    assert not problems, f"{rule}\n" + "\n".join(problems)


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


# --- Đường cấm 1: chỉ project_service ghi project.json -------------------------------------------------------------
ALLOWED_PROJECT_JSON_WRITES: dict = {}  # đã gom hết về project_service.save_project() (22/10/2026)


def test_only_project_service_writes_project_json():
    actual = Counter()
    for rel, tree in _trees():
        if rel == "backend/services/project_service.py":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) == "_save_project":
                actual[rel] += 1
            elif isinstance(node, ast.Constant) and node.value == "project.json":
                actual[rel] += 1
    _compare("Đường cấm 1: chỉ services/project_service.py được ghi project.json (gọi hàm công khai của nó).",
             actual, ALLOWED_PROJECT_JSON_WRITES)


# --- Đường cấm 5: không thêm client gọi LLM riêng --------------------------------------------------------------------
ALLOWED_LLM_CLIENTS = {
    "backend/services/script_splitter.py": 2,  # 9router + OpenRouter
    "backend/services/storyboard_engine.py": 1,
}


def test_no_new_llm_clients():
    actual = Counter()
    for rel, tree in _trees():
        if rel == "backend/services/case_adaptation_llm.py":
            continue
        for node in ast.walk(tree):
            # f-string cũng chứa phần chữ là ast.Constant nên chỉ đếm Constant; bỏ chuỗi có khoảng trắng (docstring, log)
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and "/chat/completions" in node.value and not re.search(r"\s", node.value)):
                actual[rel] += 1
    _compare("Đường cấm 5: gọi LLM qua services/case_adaptation_llm.py, không viết thêm client chat/completions.",
             actual, ALLOWED_LLM_CLIENTS)


# --- Đường cấm 6: biến môi trường chỉ đọc ở config.py ----------------------------------------------------------------
ALLOWED_ENV_READS = {
    "backend/main.py": 1,
    "backend/security.py": 2,
    "backend/services/case_worker.py": 1,
    "backend/services/image_service.py": 1,
    "backend/services/script_splitter.py": 4,
    "backend/services/tts_service.py": 3,
    "backend/services/vieneu_server.py": 2,
    "backend/runners/single_instance.py": 1,
    "backend/runners/muse_fleet_runner.py": 5,  # LocalAppData/ProgramFiles của Windows để tìm Chrome/Edge (không phải cấu hình app)
}


def _is_os_attr(node, attr: str) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == attr and isinstance(node.value, ast.Name) and node.value.id == "os"


def test_env_read_only_in_config():
    actual = Counter()
    for rel, tree in _trees():
        if rel == "backend/config.py":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and (_is_os_attr(node.func, "getenv") or (
                    isinstance(node.func, ast.Attribute) and node.func.attr == "get" and _is_os_attr(node.func.value, "environ"))):
                actual[rel] += 1
            elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and _is_os_attr(node.value, "environ"):
                actual[rel] += 1
    _compare("Đường cấm 6: đọc biến môi trường ở backend/config.py (và ghi vào .env.example), không gọi os.getenv rải rác.",
             actual, ALLOWED_ENV_READS)


# --- Đường cấm 7: kiểm đường dẫn bằng security.py, không dùng str.startswith ----------------------------------------
ALLOWED_STARTSWITH_PATH = {
    "backend/routers/muse_bridge.py": 2,  # complete_task()
}


def test_no_string_prefix_path_checks():
    actual = Counter()
    pattern = re.compile(r"\.startswith\(\s*str\(")
    for path in _py_files():
        n = len(pattern.findall(path.read_text(encoding="utf-8")))
        if n:
            actual[_rel(path)] = n
    _compare("Đường cấm 7: kiểm đường dẫn bằng security.is_within(), không so chuỗi bằng startswith "
             "(proj_a khớp nhầm proj_ab).", actual, ALLOWED_STARTSWITH_PATH)


# --- Đường cấm 13: services không import routers --------------------------------------------------------------------
ALLOWED_SERVICE_ROUTER_IMPORTS = {
    "backend/services/image_service.py": 1,  # from routers.muse_bridge import ...
}


def test_services_do_not_import_routers():
    actual = Counter()
    for rel, tree in _trees():
        if not rel.startswith("backend/services/"):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "routers":
                actual[rel] += 1
            elif isinstance(node, ast.Import) and any(a.name.split(".")[0] == "routers" for a in node.names):
                actual[rel] += 1
    _compare("Đường cấm 13: services/ không import routers/; đưa phần dùng chung xuống services/.",
             actual, ALLOWED_SERVICE_ROUTER_IMPORTS)


# --- Đường cấm 14: không đường dẫn tuyệt đối của máy này, không trỏ sang dự án khác -------------------------------
ALLOWED_ABSOLUTE_PATHS = {
    "backend/services/thumbnail_service.py": 1,  # C:\Windows\Fonts — vi phạm, nên lấy từ biến WINDIR
    "backend/runners/muse_fleet_runner.py": 4,  # hợp lệ: "C:/Program Files…" chỉ là giá trị dự phòng khi thiếu biến ProgramFiles
    "tools/build_release.py": 2,  # hợp lệ: nhãn của bộ chặn đường dẫn máy này khi đóng gói
}
_ABS_PATH = re.compile(r"^[A-Za-z]:[\\/]|[\\/]Users[\\/]|25\. ?OPC|douyin-movie-studio", re.IGNORECASE)


def test_no_machine_specific_paths():
    actual = Counter()
    for rel, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _ABS_PATH.search(node.value):
                if "\n" in node.value:  # docstring nhiều dòng, không phải đường dẫn
                    continue
                actual[rel] += 1
    _compare("Đường cấm 14: không viết đường dẫn của máy này hay của dự án khác; lấy đường dẫn từ backend/config.py.",
             actual, ALLOWED_ABSOLUTE_PATHS)


# --- Đường cấm 10: một sự kiện click không gắn hai lần ---------------------------------------------------------------
def _inline_click_ids(html: str) -> set:
    ids = set()
    for tag in re.findall(r"<[a-zA-Z][^>]*>", html):
        if re.search(r"\sonclick=", tag):
            m = re.search(r'\sid="([^"]+)"', tag)
            if m:
                ids.add(m.group(1))
    return ids


def _js_click_ids(app: str, tc: str) -> set:
    dom = dict(re.findall(r"^\s+(\w+):\s*document\.getElementById\('([^']+)'\)", app, re.M))
    ids = {dom[k] for k in re.findall(r"DOM\.(\w+)\??\.addEventListener\(\s*'click'", app) if k in dom}
    for src in (app, tc):
        ids |= set(re.findall(r"getElementById\('([^']+)'\)\??\.addEventListener\(\s*'click'", src))
    ids |= set(re.findall(r"tcEl\('([^']+)'\)\??\.addEventListener\(\s*'click'", tc))
    ids |= set(re.findall(r"\bon\('([^']+)',\s*'click'", tc))
    for var, id_ in re.findall(r"const (\w+) = document\.getElementById\('([^']+)'\);", app + tc):
        if re.search(rf"\b{var}\??\.addEventListener\(\s*'click'", app + tc):
            ids.add(id_)
    return ids


def test_click_handlers_bound_once():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    tc = (STATIC / "true_crime.js").read_text(encoding="utf-8")
    both = sorted(_inline_click_ids(html) & _js_click_ids(app, tc))
    assert not both, ("Đường cấm 10: các nút vừa có onclick trong index.html vừa gắn addEventListener('click') trong JS, "
                      "bấm một lần chạy hai lần: " + ", ".join(both))
