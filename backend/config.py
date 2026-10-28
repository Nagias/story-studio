import os
from pathlib import Path
from dotenv import load_dotenv

# Paths configuration
BACKEND_DIR = Path(__file__).resolve().parent
STORY_STUDIO_DIR = BACKEND_DIR.parent
PROJECTS_DIR = STORY_STUDIO_DIR / "projects"
STATIC_DIR = BACKEND_DIR / "static"
ASSETS_DIR = BACKEND_DIR / "assets"
BGM_DIR = ASSETS_DIR / "bgm"
# Font đóng gói kèm app (giấy phép SIL OFL, file OFL-*.txt cùng thư mục): đủ chữ tiếng Việt, không phụ thuộc font
# của Windows. Chủ dự án chọn 26/10/2026: Be Vietnam Pro (phụ đề, chữ thường), Oswald (thumbnail), Patrick Hand (nhãn bảng ghim).
FONTS_DIR = ASSETS_DIR / "fonts"
# Tiếng động thật CC0/Public Domain cho video vụ án (services/scene_sound.py; nguồn và giấy phép: NGUON.md cùng thư mục)
SFX_LIBRARY_DIR = ASSETS_DIR / "sfx_cc0"
COMIC_SLICES_DIR = STATIC_DIR / "comic_slices"

# Load environment configuration
ENV_PATH = STORY_STUDIO_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()

# Ensure essential directories exist
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
BGM_DIR.mkdir(parents=True, exist_ok=True)
COMIC_SLICES_DIR.mkdir(parents=True, exist_ok=True)

# 9router AI Gateway Configuration
NINEROUTER_BASE_URL = os.getenv("NINEROUTER_BASE_URL", "http://127.0.0.1:20128/v1")
NINEROUTER_API_KEY = os.getenv("NINEROUTER_API_KEY", "")
NINEROUTER_IMAGE_MODEL = os.getenv("NINEROUTER_IMAGE_MODEL", "ag/gemini-3.1-flash-image")
NINEROUTER_LLM_MODEL = os.getenv("NINEROUTER_LLM_MODEL", "ag/gemini-3.8-flash-high")
# Model chia kịch bản thành cảnh (script_splitter). Đo thật 20/10/2026 trên khúc 2.700 ký tự tiếng Việt:
# bản -low 16 s, kể đủ sự kiện (57%); bản -high 100-150 s, hay quá timeout mà không kể đủ hơn.
NINEROUTER_SCENE_MODEL = os.getenv("NINEROUTER_SCENE_MODEL", "ag/gemini-3.8-flash-low")

# Server configuration (Defaults to localhost 127.0.0.1 for local safety)
HOST = os.getenv("STORY_STUDIO_HOST", "127.0.0.1")
PORT = int(os.getenv("STORY_STUDIO_PORT", "8000"))

# Defaults (US Podcast & Murata/Spartan Manga Art)
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "vi-VN-NamMinhNeural")  # giọng của dự án mới
DEFAULT_STYLE = os.getenv("DEFAULT_STYLE", "manga_murata_battle")
DEFAULT_IMAGE_PROVIDER = os.getenv("DEFAULT_IMAGE_PROVIDER", "meta_muse_cloud")


def _env_list(name: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]


# Bảo mật (backend/security.py): server chỉ nhận truy cập từ máy này; thêm host/origin khác bằng danh sách phẩy
ALLOWED_HOSTS_EXTRA = [h.lower() for h in _env_list("STORY_STUDIO_ALLOWED_HOSTS")]
ALLOWED_ORIGINS_EXTRA = _env_list("STORY_STUDIO_ALLOWED_ORIGINS")
MAX_UPLOAD_MB = int(os.getenv("STORY_STUDIO_MAX_UPLOAD_MB", "200"))

# Video cao trào: thời gian tối đa chờ Muse làm xong một yêu cầu nhiều bước (tạo, tự kiểm, làm lại, ghép).
# Đo thật 28/10/2026: 10–21 phút cho tối đa 6 video + 4 ảnh.
MUSE_AGENT_WAIT_MIN = int(os.getenv("STORY_STUDIO_MUSE_AGENT_WAIT_MIN") or "45")   # để trống trong .env = mặc định

# Khoá dịch vụ tuỳ chọn: để trống thì nhánh đó tự bỏ qua
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")          # chia cảnh gọi Gemini trực tiếp khi không có 9router
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")  # chia cảnh qua OpenRouter khi không có 9router
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")          # nguồn ảnh "api" (DALL-E)
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")        # gói SEO: xem video đứng đầu tìm kiếm (YouTube Data API v3)

# Thư mục font của Windows (thumbnail cần font đủ chữ có dấu tiếng Việt); không phải Windows thì None
WINDOWS_FONTS_DIR = Path(os.environ["WINDIR"]) / "Fonts" if os.environ.get("WINDIR") else None
# Thư mục profile Chrome đã đăng nhập Muse của app khác (vd videopic-workflow), cách nhau bằng ";". Tài khoản trong
# muse_fleet_accounts.json được trỏ profile_dir vào đây; Fleet Runner không dọn khoá và không mở khi app kia đang dùng.
EXTRA_CHROME_PROFILES_DIRS = [Path(x.strip()) for x in os.getenv("STORY_STUDIO_EXTRA_CHROME_PROFILES", "").split(";")
                              if x.strip()]

# Server giọng VieNeu giữ model trong RAM (services/vieneu_server.py chạy tiến trình riêng)
VIENEU_HOST = os.getenv("VIENEU_HOST", "127.0.0.1")
VIENEU_PORT = int(os.getenv("VIENEU_PORT", "5005"))
# Tốc độ đọc VieNeu (1.0 = tốc độ gốc). Chủ dự án 26/10/2026: giọng đọc nhanh, trôi tuồn tuột; 0.87 khớp
# case_adaptation_checks.VI_WORDS_PER_MINUTE (200 chữ/phút). Đổi số này thì đo lại và sửa số chữ/phút đó.
VIENEU_SPEED = float(os.getenv("VIENEU_SPEED", "0.87"))


# Công tắc đọc lúc gọi (không phải lúc nạp module): test và server thử bật/tắt được khi đang chạy
def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def case_worker_disabled() -> bool:
    """STORY_STUDIO_DISABLE_CASE_WORKER=1: server không chạy hàng việc phân tích vụ án."""
    return env_flag("STORY_STUDIO_DISABLE_CASE_WORKER")


def vieneu_autostart_disabled() -> bool:
    """STORY_STUDIO_DISABLE_VIENEU_AUTOSTART=1: không tự bật server VieNeu (test, máy không có uv)."""
    return env_flag("STORY_STUDIO_DISABLE_VIENEU_AUTOSTART")
