"""
Bộ đọc HTML nhỏ cho test giao diện (chỉ dùng thư viện chuẩn).

- ids_in: mọi id trong trang.
- ancestors / page_of / inside: tìm thẻ cha của một id (gần nhất trước).
- js_fixed_ids: id mà các file JS trong backend/static gọi bằng chuỗi cố định.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "backend" / "static"
INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

VOID_TAGS = {"input", "img", "br", "meta", "link", "hr", "source"}
_JS_ID_CALL = re.compile(r"""(?:getElementById|tcEl|\bel)\(\s*['"]([\w-]+)['"]\s*\)""")


class _Tree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict[str, str]]] = []
        self.chains: dict[str, list[dict[str, str]]] = {}
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attr = {k: (v or "") for k, v in attrs}
        element_id = attr.get("id")
        if element_id:
            self.ids.add(element_id)
            self.chains.setdefault(element_id, [a for _, a in reversed(self.stack)])
        if tag not in VOID_TAGS:
            self.stack.append((tag, attr))

    def handle_startendtag(self, tag, attrs):
        attr = {k: (v or "") for k, v in attrs}
        element_id = attr.get("id")
        if element_id:
            self.ids.add(element_id)
            self.chains.setdefault(element_id, [a for _, a in reversed(self.stack)])

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return


def _parse(html: str) -> _Tree:
    tree = _Tree()
    tree.feed(html)
    tree.close()
    return tree


def ids_in(html: str) -> set[str]:
    return _parse(html).ids


def ancestors(html: str, element_id: str) -> list[dict[str, str]]:
    """Thuộc tính của từng thẻ cha, gần nhất trước. KeyError nếu không có id."""
    return list(_parse(html).chains[element_id])


def page_of(html: str, element_id: str) -> str | None:
    for attr in ancestors(html, element_id):
        if "data-page" in attr:
            return attr["data-page"]
    return None


def inside(html: str, element_id: str, container_id: str) -> bool:
    return any(a.get("id") == container_id for a in ancestors(html, element_id))


def js_fixed_ids() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(STATIC_DIR.glob("*.js")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for element_id in _JS_ID_CALL.findall(text):
            files = found.setdefault(element_id, [])
            if path.name not in files:
                files.append(path.name)
    return found
