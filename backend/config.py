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

# Server configuration (Defaults to localhost 127.0.0.1 for local safety)
HOST = os.getenv("STORY_STUDIO_HOST", "127.0.0.1")
PORT = int(os.getenv("STORY_STUDIO_PORT", "8000"))

# Defaults (US Podcast & Murata/Spartan Manga Art)
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "vi-VN-NamMinhNeural")
DEFAULT_STYLE = os.getenv("DEFAULT_STYLE", "manga_murata_battle")
DEFAULT_IMAGE_PROVIDER = os.getenv("DEFAULT_IMAGE_PROVIDER", "meta_muse_cloud")
DEFAULT_RESOLUTION = "1080p"  # 1920x1080 or 1280x720
