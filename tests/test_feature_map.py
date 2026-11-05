"""FEATURE_MAP.md và CLAUDE.md chỉ được nhắc tên có thật trong code.

Mọi thứ viết trong dấu backtick đều được kiểm:
- `#id`: phải là id trong backend/static/index.html (trừ #muse, #true-crime là đường dẫn trên URL);
- `ten_ham()`: phải có hàm/lớp/hằng tên đó trong backend/ (Python) hoặc backend/static/*.js;
- `GET /api/...` (POST, PUT, DELETE, WEBSOCKET): phải có route đó trong backend/routers/ hoặc backend/main.py;
- đường dẫn file (.py, .js, .bat, .json, .md, .txt, .html, .css) không chứa <…> hay *: phải tồn tại.
Đổi tên trong code thì sửa luôn tài liệu, nếu không test này báo lỗi.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "backend" / "static"
DOCS = ["FEATURE_MAP.md", "CLAUDE.md"]
HASH_LINKS = {"muse", "true-crime"}
FILE_SEARCH_DIRS = ["", "backend", "backend/services", "backend/routers", "backend/static", "backend/runners"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _html_ids() -> set:
    return set(re.findall(r'\bid="([^"]+)"', _read(STATIC / "index.html")))


def _sources() -> str:
    py = [p for p in (ROOT / "backend").rglob("*.py") if "__pycache__" not in p.parts]
    py += [ROOT / "run.py", *(ROOT / "tools").glob("*.py")]
    js = sorted(STATIC.glob("*.js"))  # mọi file JS của giao diện
    return "\n".join(_read(p) for p in py + js)


def _routes() -> set:
    routes = set()
    for f in (ROOT / "backend" / "routers").glob("*.py"):
        src = _read(f)
        m = re.search(r'APIRouter\(prefix="([^"]*)"', src)
        prefix = m.group(1) if m else ""
        for meth, path in re.findall(r'@router\.(get|post|put|delete)\("([^"]+)"', src):
            routes.add((meth.upper(), _norm(prefix + path)))
    for meth, path in re.findall(r'@app\.(get|websocket)\("([^"]+)"', _read(ROOT / "backend" / "main.py")):
        routes.add((meth.upper(), _norm(path)))
    return routes


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path.split("?")[0])


def _defined(name: str, src: str) -> bool:
    patterns = [rf"\bdef {name}\(", rf"\bfunction {name}\(", rf"\bconst {name}\s*=", rf"\bclass {name}\b",
                rf"\b{name}\s*=\s*(async\s*)?\(", rf"\n\s+(async )?{name}\([^)]*\)\s*\{{"]
    return any(re.search(p, src) for p in patterns)


def _expand_ids(token: str):
    for m in re.finditer(r"#([A-Za-z][\w-]*)(?:\.\.(\d+))?", token):
        name, upto = m.group(1), m.group(2)
        if name in HASH_LINKS:
            continue
        if upto:  # btn-tc-sample-1..3
            base, start = re.match(r"(.*?)(\d+)$", name).groups()
            yield from (f"{base}{i}" for i in range(int(start), int(upto) + 1))
        else:
            yield name


@pytest.fixture(scope="module")
def code():
    return {"ids": _html_ids(), "src": _sources(), "routes": _routes()}


@pytest.mark.parametrize("doc", DOCS)
def test_names_in_doc_exist_in_code(doc, code):
    text = _read(ROOT / doc)
    problems = []
    for token in re.findall(r"`([^`\n]+)`", text):
        for name in _expand_ids(token):
            if name not in code["ids"]:
                problems.append(f"id không có trong index.html: #{name}")
        for name in re.findall(r"\b([A-Za-z_]\w*)\(\)", token):
            if not _defined(name, code["src"]):
                problems.append(f"không thấy hàm {name}()")
        for meth, path in re.findall(r"\b(GET|POST|PUT|DELETE|WEBSOCKET)\s+(/[^\s`,]+)", token):
            if (meth, _norm(path)) not in code["routes"]:
                problems.append(f"không có endpoint {meth} {path}")
        if token.startswith("/ws/") and ("WEBSOCKET", _norm(token)) not in code["routes"]:
            problems.append(f"không có websocket {token}")
        if re.fullmatch(r"[\w./\\-]+\.(py|js|bat|json|md|txt|html|css|ini|toml)", token) and "<" not in token and "*" not in token:
            rel = token.replace("\\", "/")
            # .cache/ không vào git (.gitignore): file mẫu ở đó chỉ có trên máy làm, máy clone từ GitHub không có
            if rel.startswith(".cache/"):
                continue
            if not any((ROOT / d / rel).exists() for d in FILE_SEARCH_DIRS):
                problems.append(f"không thấy file {token}")
    assert not problems, f"{doc} nhắc tới tên không có trong code (sửa tài liệu cho khớp code):\n  " + "\n  ".join(sorted(set(problems)))


def test_checker_catches_wrong_names(code):
    """Tự kiểm bộ kiểm: tên bịa phải bị bắt."""
    fake = "`#khong-co-id-nay` `ham_khong_ton_tai()` `GET /api/khong-co` `backend/khong_co.py`"
    found = []
    for token in re.findall(r"`([^`\n]+)`", fake):
        found += [n for n in _expand_ids(token) if n not in code["ids"]]
        found += [n for n in re.findall(r"\b([A-Za-z_]\w*)\(\)", token) if not _defined(n, code["src"])]
        found += [p for m, p in re.findall(r"\b(GET)\s+(/[^\s`,]+)", token) if (m, _norm(p)) not in code["routes"]]
    assert found == ["khong-co-id-nay", "ham_khong_ton_tai", "/api/khong-co"]
