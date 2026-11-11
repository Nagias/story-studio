"""Luật chuyển động cho mọi việc làm video gửi Muse (một nơi cho cả video theo lời thoại và việc video trực tiếp).

Gặp 10/11/2026 (vụ xưởng sắt, bản Anh): 48 clip "Muse Video theo lời thoại" chỉ có máy quay lia hoặc zoom trên ảnh tĩnh;
sau khi trừ chuyển động máy quay, độ cử động còn 3,8–6,6, bằng ảnh tĩnh zoom (3,8). Chủ dự án: "máy quay lia với zoom
in out đâu phải là chuyển động, chuyển động là phải có người chuyển động". Nguyên nhân: việc video mặc định xin "lia máy
chậm" và prompt không đòi người cử động. Thử hai video ép cử động và khoá máy quay (cảnh 20): độ cử động 11,2, nhân vật
vẫn giữ đầu tròn. Vì vậy mọi việc video xin máy quay đứng yên và đòi cử động thật."""

# Máy quay mặc định của việc video Muse (thay câu xin lia máy chậm cũ)
LOCKED_CAMERA_EN = ("locked-off static camera on a tripod: no pan, no zoom, no dolly, no camera shake; all motion comes "
                    "from the characters and things inside the scene")

# Luật dặn Muse trong prompt video (tiếng Việt như phần còn lại của prompt)
REAL_MOTION_RULES_VI = (
    "- CHUYỂN ĐỘNG THẬT: người trong cảnh phải cử động bằng cơ thể theo lời kể (đi, quay người, quay đầu, cúi xuống, "
    "giơ tay, cầm nắm đồ vật, đổi nét mặt, khóc, run). Cảnh không có người thì chuyển động đến từ vật trong cảnh (gió "
    "lay cây, khói, mưa, nước chảy, đèn chập chờn, cửa đung đưa).",
    "- MÁY QUAY ĐỨNG YÊN như đặt trên chân máy: không lia, không zoom, không trượt máy. Video chỉ có máy quay lia hoặc "
    "zoom trên một ảnh tĩnh là SAI, phải làm lại.",
)
