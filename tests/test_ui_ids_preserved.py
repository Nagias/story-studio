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
    "modal-project-manager": "spec 4.1: cửa sổ thành trang Dự án",
    "modal-muse-cloud": "spec 4.1: cửa sổ tách thành trang Tài khoản và trang Thư viện Muse",
    "btn-close-project-modal": "spec 4.1: cửa sổ thành trang, không còn nút đóng",
    "btn-close-muse-modal": "spec 4.1: cửa sổ thành trang, không còn nút đóng",
    "btn-close-muse-modal-footer": "spec 4.1: cửa sổ thành trang, không còn nút đóng",
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


REMOVED |= {i: "spec 4.2: nhân vật chính kiểu cũ, app tự bỏ khi có bảng nhân vật" for i in (
    "step1-char-preset-select", "step1-char-name", "step1-char-anchor", "step1-char-ref-file-input",
    "step1-char-ref-url", "btn-step1-char-ref-apply-url", "btn-step1-char-ref-remove", "step1-char-ref-dropzone",
    "step1-char-ref-preview-card", "step1-char-ref-preview-img", "step1-char-ref-file-name")}
REMOVED |= {"btn-project-dropdown": "trùng trang Dự án ở thanh bên, chủ dự án yêu cầu bỏ 15/11/2026"}
REMOVED |= {"btn-step1-open-true-crime": "spec 4.2: không còn cửa sổ Hồ Sơ Kỳ Án để mở"}
REMOVED |= {"modal-true-crime": "spec 4.2: Hồ Sơ Kỳ Án vào trang Kịch bản",
            "btn-open-true-crime-modal": "như trên", "btn-close-true-crime-modal": "như trên",
            "btn-cancel-true-crime-modal": "như trên", "btn-tc-analyze": "spec 4.2: trùng nút chính trang Ý tưởng",
            "btn-tc-sample-1": "spec 4.2: nút mẫu gỡ hẳn", "btn-tc-sample-2": "như trên", "btn-tc-sample-3": "như trên"}


REMOVED |= {i: 'spec 4.2: cửa sổ cắt truyện tranh, trùng thể loại Truyện tranh ở trang Ý tưởng' for i in (
    "modal-comic-slicer", "btn-close-comic-modal", "comic-upload-section", "comic-dropzone",
    "comic-file-input", "comic-selected-file-info", "comic-layout-mode", "comic-reading-order-box",
    "comic-reading-order", "comic-min-area", "btn-sample-manga-grid", "btn-sample-webtoon-strip",
    "btn-start-slice", "comic-slice-loading", "comic-results-section", "comic-panel-count",
    "comic-mode-badge", "tab-btn-panels", "tab-btn-annotated", "comic-panels-tab-content",
    "comic-annotated-tab-content", "comic-annotated-img", "btn-reset-comic", "comic-clear-existing-cb",
    "btn-cancel-comic-modal", "btn-import-comic-to-storyboard", "import-count-label")}
REMOVED |= {i: 'spec 4.2: cửa sổ Kịch bản AI, chủ dự án chốt không bê nguyên văn' for i in (
    "modal-script-importer", "btn-close-script-modal", "script-word-count", "import-script-textarea",
    "split-mode-select", "split-style-select", "btn-cancel-script-modal", "btn-submit-script-split")}
REMOVED |= {i: 'spec 4.2: nhân vật chính kiểu cũ, cửa sổ sửa nhân vật; bảng nhân vật ở trang Hình mẫu thay thế' for i in (
    "modal-character-editor", "btn-close-character-modal", "edit-char-name", "edit-char-prompt",
    "edit-char-style", "edit-char-negative", "btn-cancel-char-modal", "btn-save-character")}
REMOVED |= {i: 'spec 4.2: cửa sổ 9-Grid Spec, lối tạo dự án thứ ba ngoài luồng đã chốt' for i in (
    "modal-master-storyboard", "btn-close-master-sb-modal", "btn-msb-sample-detective",
    "btn-msb-sample-scifi", "master-sb-script-text", "master-sb-style-dna", "master-sb-grid-mode",
    "master-sb-preview-container", "master-sb-preview-title", "master-sb-scene-count",
    "master-sb-preview-cards", "btn-cancel-master-sb-modal", "btn-run-master-sb-deconstruct",
    "btn-apply-master-sb-to-project")}
REMOVED |= {i: 'spec 4.2: thẻ Khoá nhân vật kiểu cũ, bảng nhân vật ở trang Hình mẫu thay thế' for i in (
    "character-consistency-card", "char-status-badge", "char-consistency-desc", "char-info-box",
    "char-thumb-elem", "char-icon-fallback", "char-name-display", "char-prompt-preview", "btn-edit-character")}
REMOVED |= {
    "btn-open-comic-modal": "spec 4.2: nút mở cửa sổ cắt truyện tranh",
    "btn-open-master-storyboard-modal": "spec 4.2: nút mở cửa sổ 9-Grid Spec",
    "btn-open-script-modal": "spec 4.2: nút mở cửa sổ Kịch bản AI",
    "btn-save-project": "spec 4.2: app tự lưu sau 1,5 giây, chữ Đã lưu ở thanh trên, Ctrl+S vẫn chạy",
    "btn-produce-long-video": "spec 4.2: trùng #btn-produce-from-board ở trang Dựng và xuất bản",
    "btn-download-thumbnail-direct": "spec 4.2: giữ #btn-cinema-download-thumbnail vì nằm cùng hàng các nút tải khác của thành phẩm",
}


def test_removed_modal_code_is_gone_and_shared_comic_helpers_stay():
    """Hàm của bốn cửa sổ đã gỡ không còn trong app.js; hàm dùng chung với trang Ý tưởng phải còn."""
    js = (Path(__file__).resolve().parent.parent / "backend" / "static" / "app.js").read_text(encoding="utf-8")
    for dead in ("openComicModal", "handleStartSlice", "handleImportComicToStoryboard", "openScriptModal",
                 "handleSubmitScriptSplit", "openCharacterModal", "handleSaveCharacter", "renderCharacterCard",
                 "initMasterStoryboardSpec", "closeAllModals"):
        assert dead not in js, f"{dead} đã gỡ nhưng còn trong app.js"
    for alive in ("loadComicSample", "handleStep1ProcessComic", "handleSaveProject", "setSaveState"):
        assert alive in js, f"{alive} bị xoá nhầm"
    assert "showPage('idea')" in js  # nút "Về trang Ý tưởng" của danh sách cảnh rỗng
