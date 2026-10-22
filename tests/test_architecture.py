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
    # tiến trình riêng, không nạp backend/config.py:
    "backend/services/vieneu_server.py": 2,  # chạy bằng uv với Python 3.11 riêng
    "backend/runners/single_instance.py": 1,  # dùng cả trong tiến trình Fleet Runner
    "backend/runners/muse_fleet_runner.py": 5,  # LocalAppData/ProgramFiles của Windows để tìm Chrome/Edge
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


_OS_ENV_NAMES = {"LocalAppData", "ProgramFiles", "ProgramFiles(x86)"}  # biến của Windows, không phải cấu hình app


def test_every_env_var_is_documented_in_env_example():
    """Biến môi trường code có đọc thì phải có dòng `TÊN=` trong .env.example (người dùng mới biết mà đặt)."""
    names = set()
    for _, tree in _trees():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                continue
            f = node.func
            reads_env = _is_os_attr(f, "getenv") or (isinstance(f, ast.Attribute) and f.attr == "get"
                                                     and _is_os_attr(f.value, "environ"))
            if reads_env or (isinstance(f, ast.Name) and f.id in ("env_flag", "_env_list")):
                names.add(node.args[0].value)
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^([A-Z0-9_]+)=", example, re.M))
    missing = sorted(names - documented - _OS_ENV_NAMES)
    assert not missing, f"Biến môi trường code có đọc mà .env.example chưa có: {', '.join(missing)}"


# --- Đường cấm 7: kiểm đường dẫn bằng security.py, không dùng str.startswith ----------------------------------------
ALLOWED_STARTSWITH_PATH: dict = {}  # muse_bridge.complete_task() chuyển sang is_within (22/10/2026)


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


# --- Đường cấm 9: thông báo (toast) không chèn chữ từ máy chủ/người dùng chưa lọc -----------------------------------
_UNTRUSTED_IN_TOAST = re.compile(r"err\.message|\.detail\b|errText|errMsg|file\.name|\baid\b|accLabel")


def _strip_escaped_calls(line: str) -> str:
    """Bỏ mọi đoạn escapeHtml(...)/tcEsc(...) (đếm ngoặc cân bằng, lồng bao nhiêu lớp cũng được)."""
    out, i = [], 0
    while i < len(line):
        m = re.compile(r"\b(escapeHtml|tcEsc)\(").search(line, i)
        if not m:
            out.append(line[i:])
            break
        out.append(line[i:m.start()])
        depth, j = 0, m.end() - 1
        while j < len(line):
            depth += {"(": 1, ")": -1}.get(line[j], 0)
            j += 1
            if depth == 0:
                break
        i = j
    return "".join(out)


def _unescaped_toasts(source: str) -> list:
    found = []
    for no, line in enumerate(source.splitlines(), 1):
        if "showToast(" in line and _UNTRUSTED_IN_TOAST.search(_strip_escaped_calls(line)):
            found.append((no, line.strip()))
    return found


def test_toasts_escape_untrusted_text():
    problems = [f"  {name}:{no}: {text[:140]}" for name in ("app.js", "true_crime.js")
                for no, text in _unescaped_toasts((STATIC / name).read_text(encoding="utf-8"))]
    assert not problems, ("Đường cấm 9: showToast() hiển thị HTML; chữ từ lỗi, máy chủ hay máy người dùng phải qua "
                          "escapeHtml()/tcEsc():\n" + "\n".join(problems))


# --- Đường cấm 9 (phần innerHTML): chữ chèn vào khuôn HTML phải qua escapeHtml()/tcEsc() ----------------------------
# Khoá cứng từ 22/10/2026 (CLAUDE.md mục 2.4): đã gặp 9 chỗ ở thư viện ảnh Muse (d33d9df). Đếm mọi ${...} chưa lọc nằm
# trong chuỗi `...` có thẻ HTML; chỗ cũ ghi đúng số lần (gồm cả số, chữ nội bộ an toàn — chưa rà từng chỗ).
ALLOWED_UNESCAPED_HTML_INTERPOLATIONS = {
    "backend/static/app.js": 122,
    "backend/static/true_crime.js": 28,
}
_REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^")
_LITERAL_TERNARY = re.compile(r"""^[^?`]*\?\s*(['"])[^'"]*\1\s*:\s*(['"])[^'"]*\2\s*$""")
_HTML_TAG = re.compile(r"<[a-zA-Z/!]")


def _js_templates(src: str) -> list:
    """Mọi chuỗi `...` trong file JS: (phần chữ cố định, [(dòng, biểu thức trong ${})]). Quét gần đúng nhưng ổn định."""
    templates, n = [], len(src)

    def skip_quote(i: int, q: str) -> int:
        j = i + 1
        while j < n and src[j] not in (q, "\n"):
            j += 2 if src[j] == "\\" else 1
        return j + 1

    def skip_regex(i: int) -> int:
        j, in_class = i + 1, False
        while j < n and src[j] != "\n":
            c = src[j]
            if c == "\\":
                j += 2
                continue
            if c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                return j + 1
            j += 1
        return j

    def read_expr(j: int) -> int:
        depth = 0
        while j < n:
            c = src[j]
            if c in "'\"":
                j = skip_quote(j, c)
                continue
            if c == "`":
                j = read_template(j)
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                if depth == 0:
                    return j
                depth -= 1
            j += 1
        return n

    def read_template(i: int) -> int:
        static, exprs, j = [], [], i + 1
        while j < n:
            c = src[j]
            if c == "\\":
                j += 2
                continue
            if c == "`":
                templates.append(("".join(static), exprs))
                return j + 1
            if src.startswith("${", j):
                k = read_expr(j + 2)
                exprs.append((src.count("\n", 0, j) + 1, src[j + 2:k]))
                j = k + 1
                continue
            static.append(c)
            j += 1
        return n

    i = 0
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            k = src.find("\n", i)
            i = n if k < 0 else k
        elif src.startswith("/*", i):
            k = src.find("*/", i + 2)
            i = n if k < 0 else k + 2
        elif c in "'\"":
            i = skip_quote(i, c)
        elif c == "`":
            i = read_template(i)
        elif c == "/":
            prev = src[:i].rstrip()
            i = skip_regex(i) if (not prev or prev[-1] in _REGEX_PREV or prev.endswith("return")) else i + 1
        else:
            i += 1
    return templates


def _unescaped_html_interpolations(src: str) -> list:
    found = []
    for static, exprs in _js_templates(src):
        if not _HTML_TAG.search(static):
            continue
        for line, expr in exprs:
            e = expr.strip()
            if "`" in e or _LITERAL_TERNARY.match(e):  # khuôn lồng (đã đếm riêng) hoặc chỉ chọn giữa hai chữ cố định
                continue
            if re.match(r"^(escapeHtml|tcEsc)\(", e) and e.endswith(")"):
                continue
            found.append((line, e))
    return found


def test_html_templates_escape_interpolations():
    actual, sample = Counter(), {}
    for name in ("app.js", "true_crime.js"):
        found = _unescaped_html_interpolations((STATIC / name).read_text(encoding="utf-8"))
        if found:
            actual[f"backend/static/{name}"] = len(found)
            sample[name] = found[-3:]
    _compare("Đường cấm 9: chữ chèn vào khuôn HTML (`<div>${...}</div>`) phải bọc escapeHtml()/tcEsc() (nhận mọi kiểu, "
             f"cả số). Vài chỗ cuối tìm thấy: {sample}", actual, ALLOWED_UNESCAPED_HTML_INTERPOLATIONS)


# --- Đường cấm 2 (phần trả rỗng): except không được lặng lẽ trả None/False/""/[]/{} --------------------------------
# Khoá cứng từ 22/10/2026 (CLAUDE.md mục 2.4). Phần `except: pass` do Ruff S110 chặn (tools/ruff_baseline.json).
# Chỗ cũ chưa rà từng chỗ: có chỗ hợp lệ (vd. is_within trả False khi khác ổ đĩa). Code mới: ghi log rồi mới trả.
ALLOWED_SILENT_EXCEPT_RETURNS = {
    "backend/routers/muse_bridge.py": 1,
    "backend/runners/muse_fleet_runner.py": 6,
    "backend/runners/single_instance.py": 3,
    "backend/security.py": 2,  # hợp lệ: is_within/is_safe_id trả False nghĩa là "không an toàn"
    "backend/services/case_project_builder.py": 1,
    "backend/services/investigation_board_engine.py": 1,
    "backend/services/safe_files.py": 1,
    "backend/services/thumbnail_service.py": 1,
    "backend/services/tts_service.py": 1,
    "run.py": 1,
}


def _is_empty_value(node) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Constant) and node.value in (None, False, "", 0):
        return True
    return isinstance(node, (ast.List, ast.Dict, ast.Tuple, ast.Set)) and not (
        node.keys if isinstance(node, ast.Dict) else node.elts)


def test_except_does_not_silently_return_empty():
    actual = Counter()
    for rel, tree in _trees():
        for node in ast.walk(tree):
            if (isinstance(node, ast.ExceptHandler) and len(node.body) == 1
                    and isinstance(node.body[0], ast.Return) and _is_empty_value(node.body[0].value)):
                actual[rel] += 1
    _compare("Đường cấm 2: except chỉ có `return None/False/\"\"/[]` biến lỗi thành 'không có'. Để lỗi nổi lên, "
             "hoặc ghi log (logger.warning/exception) rồi mới trả.", actual, ALLOWED_SILENT_EXCEPT_RETURNS)


# --- Đường cấm 3: không "thành công giả" -----------------------------------------------------------------------------
# Khoá cứng một phần từ 22/10/2026 (CLAUDE.md mục 2.4): đã gặp 4 lần (get_audio_duration đoán 3 giây; nhập truyện tranh
# gán ảnh không có; màn Render giả kèm video mẫu BigBuckBunny; chuỗi tạo ảnh báo xong khi lỗi). Máy chặn hai dạng
# nhận ra được: link media mẫu và hàm chỉ có `pass`. Từng vụ cũ có test hồi quy riêng.
_SAMPLE_MEDIA = re.compile(r"BigBuckBunny|gtv-videos-bucket|sample-videos|picsum\.photos|placeholder\.com|placehold\.co"
                           r"|dummyimage|loremflickr|source\.unsplash|via\.placeholder", re.IGNORECASE)


def test_no_sample_media_links():
    files = [*_py_files(), STATIC / "app.js", STATIC / "true_crime.js", STATIC / "index.html"]
    found = [f"  {_rel(p)}:{no}: {line.strip()[:120]}" for p in files
             for no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if _SAMPLE_MEDIA.search(line)]
    assert not found, ("Đường cấm 3: link ảnh/video mẫu làm kết quả trông như thật (thành công giả). Báo lỗi hoặc đánh "
                       "dấu thất bại thay vì gắn media mẫu:\n" + "\n".join(found))


def test_no_functions_that_only_pass():
    found = []
    for rel, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = [b for b in node.body if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)
                                                     and isinstance(b.value.value, str))]
                if body and all(isinstance(b, ast.Pass) or (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)
                                                            and b.value.value is Ellipsis) for b in body):
                    found.append(f"  {rel}:{node.lineno} {node.name}()")
    assert not found, ("Đường cấm 3: hàm chỉ có `pass`/`...` được gọi là chạy mà không làm gì (thành công giả). "
                       "Làm thật hoặc raise NotImplementedError:\n" + "\n".join(found))


# --- Đường cấm 12: không thêm chỗ xoá file vĩnh viễn ----------------------------------------------------------------
# Khoá cứng từ 22/10/2026 (CLAUDE.md mục 2.4): 3 chỗ xoá dữ liệu người dùng vĩnh viễn (xoá dự án, xoá một mục gallery
# Muse, xoá cả gallery). Đếm mọi lệnh xoá (rmtree, unlink, os.remove, rmdir); chỗ cũ ghi rõ là dọn file tạm hay vi phạm.
# Chỗ mới: xoá dữ liệu người dùng thì chuyển vào Thùng rác hoặc hỏi trước; dọn file tạm thì ghi thêm ngoại lệ có lý do.
ALLOWED_DELETES = {
    # VI PHẠM (dữ liệu người dùng mất hẳn, sửa là việc riêng chờ chủ dự án chọn):
    "backend/services/project_service.py": 1,  # delete_project(): xoá cả thư mục dự án
    "backend/routers/muse_bridge.py": 2,  # delete_gallery_item(), clear_all_gallery(): xoá ảnh/video Muse
    # Hợp lệ: chỉ dọn file tạm, file khoá hay file hỏng do chính code vừa tạo
    "backend/routers/api.py": 4,  # file zip/srt tạm sau khi gửi tải về
    "backend/runners/muse_fleet_runner.py": 4,  # khoá SingletonLock của Chrome (2), video tải về không hợp lệ, ảnh đính kèm tạm
    "backend/services/safe_files.py": 1,  # file tạm khi ghi an toàn thất bại
    "backend/services/thumbnail_service.py": 1,  # file thumbnail tạm
    "backend/services/tts_service.py": 1,  # file .words.json cũ trước khi thu lại giọng
    "backend/services/video_service.py": 1,  # thư mục đoạn dựng tạm
    "backend/services/vieneu_worker.py": 2,  # file wav tạm, file đích cũ trước khi thay
    "tools/build_release.py": 1,  # file tạm khi đóng gói
}
_DELETE_ATTRS = {"rmtree", "unlink", "rmdir", "removedirs"}


def test_no_new_permanent_deletes():
    actual = Counter()
    for rel, tree in _trees():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            attr = node.func.attr
            if attr in _DELETE_ATTRS or (attr == "remove" and _is_os_attr(node.func, "remove")):
                actual[rel] += 1
    _compare("Đường cấm 12: lệnh xoá file mới. Dữ liệu người dùng: chuyển vào Thùng rác hoặc hỏi trước; file tạm: ghi "
             "ngoại lệ kèm lý do vào ALLOWED_DELETES.", actual, ALLOWED_DELETES)


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
