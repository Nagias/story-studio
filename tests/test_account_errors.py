"""Khoá tài khoản Muse theo MÃ LỖI, không dò chữ trong cả câu (rà soát 18/11/2026).

Trước đây cầu nối dò chữ "exceeded", "429", "quota" trong toàn bộ câu lỗi: lỗi trình duyệt quá giờ của Playwright
("Timeout 90000ms exceeded") và câu Muse kể lại nối sau "| Muse nói:" bị coi là hết quota, tài khoản bị khoá 15 phút
tới 6 giờ, các cảnh ghim cho tài khoản đó bị bỏ lại. Các câu dưới đây lấy từ log thật của hai vụ Khang Cúc Hoa và
Vương Nghĩa Tường (.cache/*.log), có chỉnh mã việc."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from routers import muse_bridge  # noqa: E402
from runners import muse_fleet_runner as runner  # noqa: E402

REAL_QUOTA = ("QUOTA_EXCEEDED: Muse không tạo được video nào (hạn mức video): ngờ vì các cảnh trước trong hôm nay và hai "
              "ngày qua vẫn tạo video bình thường. Nếu hạn chế này được gỡ ở phía tài khoản/khu vực, bạn chỉ cần gửi lại")
REAL_SESSION = "SESSION_EXPIRED: Tài khoản muse_acc_vp_04 cần đăng nhập lại (chạy setup_muse_accounts.bat)"
NOT_ACCOUNT_PROBLEMS = [
    "BROWSER_ERROR: Page.goto: Timeout 90000ms exceeded.",
    "ATTACH_FAILED: Lỗi đính kèm ảnh: Timeout 8000ms exceeded while waiting for event \"filechooser\"",
    "AGENT_TIMEOUT: Muse chưa xong sau 4500s (chưa thấy dòng kết thúc XONG-1a2b3c4d)",
    "NO_MEDIA: Không nhận được video hợp lệ sau 300s cho task task_m_4291ab | Muse nói: video vượt hạn mức thời lượng",
    "NO_FINAL: Không tải được video cuối của Muse: blob:https://muse.ai/6b291b90 | Muse nói: quota ổn, thử lại",
    "MUSE_REPLIED_ERROR: Em chưa tạo được khung này anh ạ — cảnh rơi từ cửa sổ cao như mô tả thì em không vẽ được",
]


def test_only_real_account_codes_block_the_account():
    quota = muse_bridge.account_block_for(REAL_QUOTA)
    assert quota is not None and "Hết lượt dùng" in quota[0] and quota[1] >= muse_bridge.ACCOUNT_BLOCK_SEC
    session = muse_bridge.account_block_for(REAL_SESSION)
    assert session is not None and "phiên đăng nhập" in session[0] and session[1] == muse_bridge.ACCOUNT_BLOCK_SEC
    for err in NOT_ACCOUNT_PROBLEMS:
        assert muse_bridge.account_block_for(err) is None, err


def test_muse_reply_naming_a_limit_still_blocks():
    assert muse_bridge.account_block_for("MUSE_REPLIED_ERROR: You have reached your usage limit. Upgrade to continue")


def test_quality_report_with_zero_passing_clips_is_not_a_quota_problem():
    # Muse làm 6 video, không cái nào đạt: báo cáo chất lượng, không phải hết hạn mức
    assert runner.agent_no_video_reason("Tổng số đã tạo: 6 video, 0 video đạt. Kết quả cuối: KHÔNG ĐẠT") is None
    assert runner.agent_no_video_reason("Đã tạo 4 video / 2 ảnh; 0 video hợp lệ") is None
    # Muse khai không tạo được video nào, hoặc nói tới hạn mức: đúng là hết lượt
    assert runner.agent_no_video_reason("Tổng số đã tạo: 0 video / 0 ảnh mới — lần gọi clip A bị chặn ở cổng hạn mức")
    assert runner.agent_no_video_reason("Tổng số đã tạo: 0 video / 1 ảnh")


def test_server_waits_longer_than_the_runner_for_agent_tasks():
    runner_extra = runner.TASK_OVERHEAD_SEC + runner.agent_turn.AGENT_STABLE_SEC
    assert muse_bridge.AGENT_TASK_EXTRA_SEC > runner_extra
