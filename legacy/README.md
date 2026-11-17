# legacy — code cũ giữ làm kỷ niệm

Chuyển vào đây ngày 18/11/2026 (nhánh `sua-luat-goc`), theo kế hoạch rà soát luật chồng chéo chủ dự án đã duyệt: "Code tự làm cũ có thể gom vào 1 folder để riêng làm kỷ niệm".

App không nạp gì trong thư mục này (test `tests/test_architecture.py::test_app_never_imports_legacy_code` chặn), pytest không quét (`pytest.ini`: `testpaths = tests`), Ruff bỏ qua (`ruff.toml`), gói bán không đóng gói (`tools/build_release.py` chỉ lấy `backend/`).

| File | Vì sao gỡ |
|---|---|
| `backend/services/script_splitter.py` | Bộ chia cảnh đời cũ: dặn AI "tóm tắt", người kể "tôi", chèn chữ "KA-BOOM" vào mọi phong cách, hỏng thì chép nguyên văn; 3 client LLM riêng không biết thử lại. Truyện chữ nay qua `services/story_review.py`, vụ án qua `services/case_adaptation_steps.py` (đều có bước kiểm đủ ý). |
| `backend/services/storyboard_engine.py` | Storyboard 9-grid đời cũ (luật lưới đã gỡ 22/10/2026), chỉ còn route API không ai gọi. |
| `backend/routers/api_legacy_routes.py` | Các route chỉ dùng hai file trên: `/vox/*`, `/projects/{id}/vox-script`, `/novel/ingest-chapter`, `/split-script`, `/projects/{id}/split-script`, `/storyboard/deconstruct`, nhánh `text` của `produce-long-video`. Giao diện không gọi route nào trong số này. |
| `backend/services/srt_helpers_old.py` | Đọc, ghi, ghép SRT/ASS tự viết; nay dùng thư viện `pysubs2`. |
| `tests/` | Test của các phần trên. |
