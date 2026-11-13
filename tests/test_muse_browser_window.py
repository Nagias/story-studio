"""Cửa sổ Chrome có giao diện (đăng nhập, xem hạn mức Muse) phải theo cỡ màn hình, không khoá khung trang.
Lỗi 13/11/2026: màn hình 1280x720 mà khung trang khoá 1280x800, phần dưới trang Muse bị cắt, chủ dự án không bấm được."""
import inspect

from runners import muse_fleet_runner as fr


def test_headed_window_follows_screen_size():
    opts = fr.browser_window_options(headless=False)
    assert opts.get("no_viewport") is True
    assert "viewport" not in opts
    assert "--start-maximized" in opts["args"]
    assert not any(a.startswith("--window-size=") for a in opts["args"])


def test_headless_keeps_fixed_viewport():
    opts = fr.browser_window_options(headless=True)
    assert opts["viewport"] == {"width": 1280, "height": 800}
    assert "no_viewport" not in opts


def test_every_chrome_launch_uses_window_options():
    src = inspect.getsource(fr)
    launches = src.count("launch_persistent_context(")
    assert launches >= 1
    assert src.count("**browser_window_options(") == launches
    assert "viewport={" not in src
