"""Khoá cứng: giao diện gọn không được làm mất id nào (spec mục 4.2), trừ id đã duyệt gỡ."""
from pathlib import Path

from tests.ui_html import INDEX_HTML, ids_in, js_fixed_ids

BASELINE = Path(__file__).resolve().parent / "data" / "ui_ids_truoc_giao_dien_gon.txt"

# id đã duyệt gỡ -> lý do. Task sau thêm vào đây.
REMOVED: dict[str, str] = {
    "step-nav-1": "spec 4.2: thay bằng thanh bên",
    "step-nav-2": "spec 4.2: thay bằng thanh bên",
    "step-nav-3": "spec 4.2: thay bằng thanh bên",
    "step-nav-4": "spec 4.2: thay bằng thanh bên",
    "btn-character-sheets": "spec 4.2/4.1: Hình mẫu là một trang, không còn nút mở cửa sổ",
    "btn-location-sheets": "spec 4.2/4.1: Hình mẫu là một trang, không còn nút mở cửa sổ",
    "btn-close-character-sheets": "spec 4.2/4.1: Hình mẫu là một trang, không còn nút đóng cửa sổ",
    "btn-close-location-sheets": "spec 4.2/4.1: Hình mẫu là một trang, không còn nút đóng cửa sổ",
    "btn-producer-goto-cinema": "spec 4.2: Bước 3 gộp vào trang Dựng, không cần nút sang rạp chiếu",
    "btn-toggle-asset-accordion": "spec 4.1: nút Nâng cao không còn gì để mở",
    "advanced-asset-accordion": "spec 4.1: nút Nâng cao không còn gì để mở",
    "asset-accordion-body": "spec 4.1: nút Nâng cao không còn gì để mở",
    "asset-accordion-chevron": "spec 4.1: nút Nâng cao không còn gì để mở",
    "audio-settings-card": "spec 4.1: thẻ cấu hình dựng thành #render-settings trong ngăn Tuỳ chỉnh dựng",
}

# id do JS tự dựng lúc chạy (không có sẵn trong index.html). Task sau thêm vào đây.
JS_BUILT_IDS: set[str] = set()


def test_no_id_lost_except_approved_removals():
    before = set(BASELINE.read_text(encoding="utf-8").split())
    lost = before - ids_in(INDEX_HTML) - set(REMOVED)
    assert not lost, f"Mất id không có trong danh sách gỡ (spec mục 4.2): {sorted(lost)}"


def test_removed_ids_are_really_gone():
    assert not (set(REMOVED) & ids_in(INDEX_HTML))


def test_every_fixed_js_id_exists():
    missing = {i: files for i, files in js_fixed_ids().items() if i not in ids_in(INDEX_HTML) | JS_BUILT_IDS}
    assert not missing, f"JS gọi id mà trang không có: {missing}"
