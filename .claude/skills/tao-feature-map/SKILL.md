---
name: tao-feature-map
description: Dùng khi sắp làm hoặc kiểm chứng một tính năng hay khu vực của Story Studio mà FEATURE_MAP.md chưa có dòng nào (tính năng mới, luồng mới). Không dùng để viết lại cả bản đồ - bản đồ đã có.
---

# Thêm vùng mới vào Feature Map

Nguồn: skill tao-feature-map của bộ mẫu; bản đồ của dự án đã có, nên skill này chỉ thêm phần còn thiếu.

1. Đọc dòng tương tự đã có trong `FEATURE_MAP.md` để theo đúng cột và cách viết hiện tại.
2. Mỗi tính năng ghi đủ 5 ý:
   - nằm ở đâu trong code (file, hàm, endpoint) và trên giao diện (bước, khối);
   - mở bằng cách nào (nút, phím, lệnh);
   - phần tử cần thao tác để dùng hoặc test (`#id`);
   - điều kiện ban đầu (dự án thử `proj_ea5b04db`, dữ liệu mẫu, dịch vụ cần bật);
   - thuộc luồng xuyên suốt nào (luồng A, C… trong bản đồ), có tốn quota không (**LLM**, **Muse**, **Ảnh trả phí**).
3. Luồng xuyên suốt mới: thêm mục riêng, liệt kê các bước từ đầu tới cuối.
4. Chỉ ghi tên có thật trong code: chạy `.venv\Scripts\python.exe -m pytest tests\test_feature_map.py -q` sau khi sửa.
