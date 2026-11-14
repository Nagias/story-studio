"""Kiểm bố cục giao diện gọn: mỗi id nằm đúng trang."""
from tests.ui_html import INDEX_HTML, inside, page_of

# id -> mã trang (giá trị data-page); None là nằm ngoài mọi trang (ví dụ thanh bên). Task sau thêm dòng.
PLACEMENT: dict[str, str | None] = {}

HIDDEN_STORE = "ws-hidden-inputs"


def test_each_id_sits_on_its_page():
    wrong = {i: (page_of(INDEX_HTML, i), p) for i, p in PLACEMENT.items() if page_of(INDEX_HTML, i) != p}
    assert not wrong, f"id nằm sai trang (đang ở, phải ở): {wrong}"


def test_ui_html_reader():
    h = '<div data-page="a"><section id="s"><input id="i"><p id="p">x</p></section></div><div id="o"></div>'
    assert page_of(h, "p") == "a" and page_of(h, "i") == "a" and page_of(h, "o") is None
    assert inside(h, "p", "s") and not inside(h, "o", "s")
