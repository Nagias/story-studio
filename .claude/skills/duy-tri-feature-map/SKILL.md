---
name: duy-tri-feature-map
description: Dùng trong mọi thay đổi Story Studio có đụng tới tính năng, giao diện, API, luồng người dùng hay cách thao tác (thêm/bớt nút, đổi endpoint, đổi điều kiện ban đầu, đổi hành vi người dùng thấy được). Giữ FEATURE_MAP.md khớp với sản phẩm thật trong cùng thay đổi.
---

# Duy trì Feature Map

Nguồn: skill duy-tri-feature-map của bộ mẫu.

1. Trước khi kết thúc thay đổi, tự hỏi: thay đổi này làm `FEATURE_MAP.md` sai ở dòng nào không? (thêm/bớt tính năng, đổi phần tử `#id`, đổi hàm JS, đổi endpoint, đổi điều kiện ban đầu, đổi cột tốn quota **LLM** / **Muse** / **Ảnh trả phí**, đổi file test liệt kê trong bản đồ).
2. Có thì sửa đúng dòng đó trong **cùng** nhánh/commit. Không để "cập nhật bản đồ sau".
3. Tính năng mới chưa có trong bản đồ: thêm dòng theo cấu trúc của skill tao-feature-map.
4. Máy chỉ kiểm được một nửa: `tests/test_feature_map.py` bắt tên sai (id, hàm, endpoint, file không có), không bắt được dòng còn thiếu hay mô tả lỗi thời. Phần đó phải tự soát.
5. Báo cáo ghi một dòng: "Feature map: đã cập nhật dòng X" hoặc "Feature map: không bị ảnh hưởng".
