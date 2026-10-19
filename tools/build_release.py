"""Đóng gói Story Studio để gửi khách, theo DANH SÁCH CHO PHÉP (whitelist).

Chạy:  .venv\\Scripts\\python.exe tools\\build_release.py
Ra:    dist\\story-studio-<YYYY-MM-DD>.zip

Chỉ những file khớp WHITELIST mới vào zip. Sau khi đóng gói, script đọc lại zip và
FAIL (exit 1, xoá zip) nếu thấy: .env, chrome_profiles, *.log, __pycache__, .pyc,
chuỗi giống API key (sk-...), IP 100.x.x.x, đường dẫn máy dev, hoặc giá trị bí mật trong .env.
"""

import json
import os
import re
import sys
import zipfile
from datetime import date
from pathlib import Path, PurePosixPath

if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
TOP = "story-studio"  # thư mục gốc bên trong zip

# File bắt buộc phải có
REQUIRED_FILES = [
    "backend/main.py",
    "backend/config.py",
    "backend/security.py",
    "backend/requirements.txt",
    "backend/static/index.html",
    "backend/static/app.js",
    "backend/static/tailwind.css",  # CSS Tailwind build sẵn (index.html không còn dùng CDN)
    "run.py",
    "run.bat",
    "setup_muse_accounts.bat",
    "start_muse_fleet.bat",
    ".env.example",
    "README.md",
]

# Nhóm file theo glob (tương đối với ROOT)
WHITELIST_GLOBS = [
    "backend/routers/**/*.py",
    "backend/services/**/*.py",
    "backend/models/**/*.py",
    "backend/runners/*.py",
    "backend/static/demo_images/scene_*.jpg",
    "backend/static/demo_images/style_*.jpg",
    "backend/static/voice_samples/*",
    "backend/static/test_comic/test_*.jpg",  # ảnh mẫu cho nút "dùng thử" ở tab cắt truyện (app.js loadComicSample)
    "backend/assets/**/*",
]

# Thư mục rỗng tạo sẵn trong zip
EMPTY_DIRS = ["projects", "backend/config"]

FLEET_CONFIG_ARCNAME = "backend/config/muse_fleet_accounts.json"

FORBIDDEN_CONTENT = [
    ("chuỗi giống API key (sk-...)", re.compile(rb"sk-[A-Za-z0-9_\-]{16,}")),
    ("IP 100.x.x.x (Tailscale)", re.compile(rb"(?<![\d.])100\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d])")),
    ("đường dẫn C:/Users/pc", re.compile(rb"(?i)c:[\\/]+users[\\/]+pc(?![a-z0-9])")),
    ("đường dẫn D:/25. OPC", re.compile(rb"(?i)d:[\\/]+25\. ?opc")),
]

# Đường dẫn tĩnh viết cố định trong giao diện (bỏ qua đường dẫn ghép động có ${...})
STATIC_REF_RE = re.compile(r"/static/([A-Za-z0-9_./-]+\.(?:css|js|jpe?g|png|webp|svg|mp3|mp4|json))")


def fleet_accounts_template() -> dict:
    """5 tài khoản ảnh + 5 tài khoản video, trạng thái ready, chưa đăng nhập (giống mặc định của muse_bridge)."""
    accounts = []
    for kind, short, caps in (("image", "img", ["text-to-image", "image-upscale-2k"]),
                              ("video", "vid", ["image-to-video", "text-to-video"])):
        for i in range(1, 6):
            aid = f"muse_acc_{short}_{i:02d}"
            accounts.append({
                "account_id": aid,
                "label": f"Muse {kind.capitalize()} Account {i:02d}",
                "type": kind,
                "capabilities": caps,
                "profile_dir": f"chrome_profiles/{aid}",
                "status": "ready",
                "cooldown_until": 0,
                "is_active_for_image": kind == "image" and i == 1,
                "is_active_for_video": kind == "video" and i == 1,
                "last_used": 0,
                "success_count": 0,
                "fail_count": 0,
                "last_error": None,
                "has_profile": False,
            })
    return {
        "concurrency_limit": 2,
        "max_memory_mb": 1500,
        "loopback_url": "http://127.0.0.1:8000/api/muse-bridge",
        "accounts": accounts,
    }


def collect_files() -> list[str]:
    """Danh sách file (posix, tương đối ROOT) theo whitelist. Thiếu file bắt buộc -> dừng."""
    missing = [f for f in REQUIRED_FILES if not (ROOT / f).is_file()]
    if missing:
        raise SystemExit("[FAIL] Thiếu file bắt buộc: " + ", ".join(missing))

    files = set(REQUIRED_FILES)
    for pattern in WHITELIST_GLOBS:
        matched = [p for p in ROOT.glob(pattern) if p.is_file()]
        if not matched:
            raise SystemExit(f"[FAIL] Không có file nào khớp whitelist: {pattern}")
        for p in matched:
            rel = p.relative_to(ROOT).as_posix()
            if "__pycache__" in rel.split("/") or rel.endswith((".pyc", ".pyo")):
                continue
            files.add(rel)
    return sorted(files)


def secret_values_from_env() -> list[bytes]:
    """Giá trị các biến bí mật trong .env của máy đóng gói (để chắc chúng không lọt vào zip)."""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return []
    values = []
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if sep and not key.startswith("#") and re.search(r"KEY|TOKEN|SECRET|PASSWORD", key, re.I) and len(value) >= 8:
            values.append(value.encode("utf-8"))
    return values


def name_problem(arcname: str) -> str | None:
    parts = PurePosixPath(arcname).parts
    base = parts[-1] if parts else ""
    if re.fullmatch(r"\.env(\..+)?", base) and base != ".env.example":
        return "file .env"
    if "chrome_profiles" in parts:
        return "thư mục chrome_profiles"
    if ".cache" in parts:
        return "thư mục .cache (uv/Python/model VieNeu)"
    if "__pycache__" in parts:
        return "__pycache__"
    if base.endswith((".pyc", ".pyo")):
        return "file .pyc"
    if re.search(r"\.log(\.\d+)?$", base, re.I):
        return "file log"
    return None


def verify_zip(zip_path: Path) -> list[str]:
    """Đọc lại zip đã tạo, trả về danh sách vi phạm (rỗng = sạch)."""
    problems = []
    secrets = secret_values_from_env()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for name in names:
            issue = name_problem(name)
            if issue:
                problems.append(f"{name}: {issue}")
            if name.endswith("/"):
                continue
            data = zf.read(name)
            for label, rx in FORBIDDEN_CONTENT:
                m = rx.search(data)
                if m:
                    problems.append(f"{name}: {label} tại byte {m.start()}")
            if any(s in data for s in secrets):
                problems.append(f"{name}: chứa giá trị bí mật lấy từ .env")
        for d in EMPTY_DIRS:
            if f"{TOP}/{d}/" not in names:
                problems.append(f"thiếu thư mục {d}/")
        for f in REQUIRED_FILES + [FLEET_CONFIG_ARCNAME]:
            if f"{TOP}/{f}" not in names:
                problems.append(f"thiếu file {f}")
        # Mọi file /static/... mà giao diện gọi cố định phải có trong gói (tránh gửi bản thiếu CSS/ảnh)
        for ui_file in ("backend/static/index.html", "backend/static/app.js"):
            arc = f"{TOP}/{ui_file}"
            if arc not in names:
                continue
            for ref in sorted(set(STATIC_REF_RE.findall(zf.read(arc).decode("utf-8", "replace")))):
                if f"{TOP}/backend/static/{ref}" not in names:
                    problems.append(f"{ui_file} gọi /static/{ref} nhưng file này không có trong gói")
    return problems


def main() -> int:
    files = collect_files()
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DIST_DIR / f"story-studio-{date.today().isoformat()}.zip"
    tmp_path = zip_path.with_name(zip_path.name + ".tmp")

    raw_bytes = 0
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for d in EMPTY_DIRS:
            zf.mkdir(f"{TOP}/{d}")
        for rel in files:
            zf.write(ROOT / rel, f"{TOP}/{rel}")
            raw_bytes += (ROOT / rel).stat().st_size
        zf.writestr(f"{TOP}/{FLEET_CONFIG_ARCNAME}",
                    json.dumps(fleet_accounts_template(), indent=2, ensure_ascii=False) + "\n")

    problems = verify_zip(tmp_path)
    if problems:
        tmp_path.unlink()
        print(f"[FAIL] Gói không an toàn, đã huỷ ({len(problems)} vi phạm):")
        for p in problems:
            print("  - " + p)
        return 1

    os.replace(tmp_path, zip_path)
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"[OK] {zip_path}")
    print(f"     {len(files) + 1} file, {raw_bytes / 1024 / 1024:.1f} MB gốc -> zip {size_mb:.2f} MB")
    print("     Đã kiểm: .env, chrome_profiles, *.log, __pycache__, .pyc, sk-..., IP 100.x, đường dẫn máy dev, bí mật trong .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
