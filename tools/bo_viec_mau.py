"""Bộ việc mẫu chuẩn của Story Studio: chấm agent/skill trên 5 việc thật đã làm, báo điểm trước/sau.

Quy tắc của chủ dự án (CLAUDE.md mục 6): mỗi lần sửa skill hoặc agent thì chạy lại bộ này và báo điểm trước/sau.
Đề bài, thang điểm, cách chạy từng bước: docs/bo-viec-mau/README.md.

Cách dùng (luôn bằng Python của .venv):
    .venv\\Scripts\\python.exe tools\\bo_viec_mau.py chuan-bi --lan <tên> --mo-ta "<agent/skill đang thử>"
        dựng thư mục làm bài cho từng việc trong .cache/bo-viec-mau/<tên>/, ghi đề bài đầy đủ cạnh đó
    .venv\\Scripts\\python.exe tools\\bo_viec_mau.py cham --lan <tên> [--ghi-lich-su]
        chấm tự động phần A–D (9/10 điểm), soạn hồ sơ cho giám khảo, gộp điểm giám khảo (phần E) nếu đã có
    .venv\\Scripts\\python.exe tools\\bo_viec_mau.py so-sanh <lần trước> <lần sau>
        bảng điểm trước/sau từng việc
    .venv\\Scripts\\python.exe tools\\bo_viec_mau.py tinh-dap-an
        lập lại danh sách test ẩn (docs/bo-viec-mau/<việc>/dap-an.json) và tự kiểm máy chấm; chỉ cần khi đổi việc mẫu
Thêm --viec T1 T3 để chỉ làm vài việc.

Mỗi việc là một lần sửa thật trong lịch sử git: thư mục làm bài là mã nguồn ngay trước lần sửa (git archive, có git
riêng không kèm lịch sử để người làm bài không xem được đáp án), bài được chấm bằng test của lần sửa (test ẩn) và cả
bộ test mặc định (không làm hỏng chỗ khác). Công cụ này không xoá gì: thư mục cũ trong .cache/bo-viec-mau tự dọn tay.
"""
import argparse
import ast
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BO = ROOT / "docs" / "bo-viec-mau"
CACHE = ROOT / ".cache" / "bo-viec-mau"
VENV = ROOT / ".venv"
LICH_SU = BO / "lich-su-diem.md"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
DIEM_TOI_DA = {"A": 5, "B": 2, "C": 1, "D": 1, "E": 1}
TEN_TIEU_CHI = {"A": "đúng yêu cầu (test ẩn)", "B": "không hỏng chỗ khác", "C": "đúng phạm vi file",
                "D": "cổng kiểm tools/check.py", "E": "báo cáo trung thực (giám khảo)"}
# Thư mục không chép sang bản chấm (ở mọi cấp); "tests" và ".env" ở gốc cũng không chép (thay bằng bản của đáp án).
BO_QUA_KHI_CHEP = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".cache", "projects"}
ENV_RONG = ("# File rỗng do tools/bo_viec_mau.py tạo: backend/config.py đọc file này nên không dò ngược lên .env thật\n"
            "# (không lấy khoá API thật, không gọi được dịch vụ tính tiền).\n")
LOI_DAN_CHUNG = BO / "loi-dan-chung.md"
# File có trên máy thật nhưng git bỏ qua, mà tài liệu dự án có nhắc (FEATURE_MAP.md: bài mẫu và script chạy thử
# true-crime). Chép kèm vào bài để môi trường giống máy thật; thiếu thì test FEATURE_MAP và cổng kiểm luôn hỏng.
FILE_NGOAI_GIT = [".cache/samples"]
HO_SO_DIFF_TOI_DA = 60_000   # ký tự diff đưa cho giám khảo


class LoiBoViec(RuntimeError):
    """Không dựng hay chấm được bài; thông điệp nói rõ bước nào hỏng."""


# ----------------------------------------------------------------------------------------------- đọc cấu hình
def doc_viec() -> dict:
    return json.loads((BO / "viec.json").read_text(encoding="utf-8"))["viec"]


def doc_dap_an(ma: str) -> dict:
    path = BO / ma / "dap-an.json"
    if not path.exists():
        raise LoiBoViec(f"{ma}: chưa có {path.relative_to(ROOT).as_posix()}; chạy tinh-dap-an trước")
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------------------------- lệnh ngoài
def _run(cmd: list, cwd: Path, timeout: int, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    if input_bytes is not None:
        return subprocess.run(cmd, cwd=cwd, env=ENV, input=input_bytes, capture_output=True, timeout=timeout)
    return subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def _git(args: list, cwd: Path = ROOT, timeout: int = 300) -> str:
    proc = _run(["git", *args], cwd, timeout)
    if proc.returncode != 0:
        raise LoiBoViec(f"git {' '.join(args)} (ở {cwd}): {(proc.stderr or proc.stdout).strip()[-600:]}")
    return proc.stdout


def _python(cay: Path) -> Path:
    return cay / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _noi_venv(cay: Path) -> None:
    """.venv của bài trỏ về .venv của dự án (junction trên Windows: không cần quyền quản trị, không chép thư viện)."""
    link = cay / ".venv"
    if os.name == "nt":
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(VENV)], capture_output=True, text=True,
                              errors="replace", timeout=60)
        if proc.returncode != 0:
            raise LoiBoViec(f"Không tạo được junction .venv: {(proc.stderr or proc.stdout).strip()}")
    else:
        link.symlink_to(VENV, target_is_directory=True)
    if not _python(cay).exists():
        raise LoiBoViec(f"Không thấy Python trong {link}")


# ----------------------------------------------------------------------------------------------- dựng bài
def _giai_nen(commit: str, dich: Path) -> None:
    # Lấy file đúng như lưu trong git (LF): máy có core.autocrlf=true thì archive đổi sang CRLF và bản vá không áp được
    proc = _run(["git", "-c", "core.autocrlf=false", "archive", "--format=tar", commit], ROOT, 300, input_bytes=b"")
    if proc.returncode != 0:
        raise LoiBoViec(f"git archive {commit}: {proc.stderr.decode('utf-8', 'replace').strip()[-400:]}")
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tf:
        # bộ việc mẫu (đề, đáp án) không bao giờ nằm trong bài làm, kể cả khi sau này dựng bài từ commit mới
        members = [m for m in tf.getmembers() if not m.name.startswith("docs/bo-viec-mau")]
        tf.extractall(dich, members=members, filter="data")


def _ap_ban_va(cay: Path, muc: str | dict, dao_nguoc: bool = False) -> None:
    """Áp thay đổi của một commit (hoặc đảo ngược) vào cây. muc: mã commit, hoặc {"commit", "chi_lay": [file...],
    "bo_qua_ngu_canh": true} (không đòi khớp dòng xung quanh: dùng cho nhật ký đã được viết thêm sau commit đó).
    Cây phải là repo git riêng: git apply chạy trong thư mục con của repo khác sẽ lặng lẽ bỏ qua đường dẫn nằm ngoài."""
    muc = {"commit": muc} if isinstance(muc, str) else muc
    commit, chi_lay = muc["commit"], muc.get("chi_lay") or []
    patch = _run(["git", "show", "--binary", "--format=", commit, "--", *chi_lay], ROOT, 120, input_bytes=b"")
    if patch.returncode != 0 or not patch.stdout.strip():
        raise LoiBoViec(f"Không lấy được thay đổi của {commit} ({chi_lay or 'cả commit'})")
    cmd = ["git", "apply", "--whitespace=nowarn", *(["-R"] if dao_nguoc else []),
           *(["-C0", "--unidiff-zero"] if muc.get("bo_qua_ngu_canh") else []), "-"]
    proc = _run(cmd, cay, 120, input_bytes=patch.stdout)
    if proc.returncode != 0:
        raise LoiBoViec(f"git apply {'-R ' if dao_nguoc else ''}{commit} {chi_lay}: "
                        f"{proc.stderr.decode('utf-8', 'replace')[-600:]}")


def _chep_file_ngoai_git(dich: Path) -> None:
    for rel in FILE_NGOAI_GIT:
        nguon = ROOT / rel
        if nguon.is_dir() and not (dich / rel).exists():
            shutil.copytree(nguon, dich / rel, ignore=shutil.ignore_patterns("__pycache__"))


def _khoi_tao_git(cay: Path) -> None:
    _git(["init", "-q", "-b", "master"], cay)
    for key, value in (("user.name", "nguoi-lam-bai"), ("user.email", "nguoi-lam-bai@bo-viec-mau.local"),
                       ("core.autocrlf", "false"), ("core.longpaths", "true")):
        _git(["config", key, value], cay)


def _cai_hook(cay: Path) -> str:
    proc = _run([str(_python(cay)), "-X", "utf8", "tools/check.py", "--install-hook"], cay, 120)
    return "đã cài hook git" if proc.returncode == 0 else f"không cài được hook: {(proc.stderr or proc.stdout)[-300:]}"


def dung_bai(ma: str, viec: dict, dich: Path, ap_dap_an: bool = False) -> dict:
    """Thư mục làm bài: mã nguồn trước lần sửa, có git riêng (một commit "gốc"), .env rỗng, .venv nối về dự án.
    ap_dap_an=True: áp thêm lần sửa thật lên trên (chưa commit), như một bài làm đúng hoàn toàn."""
    if dich.exists():
        raise LoiBoViec(f"{dich} đã có; chọn tên lần chạy khác (công cụ không xoá thư mục cũ)")
    dich.mkdir(parents=True)
    goc = viec["goc"]
    _giai_nen(goc["commit"], dich)
    _khoi_tao_git(dich)
    dao_nguoc = goc.get("dao_nguoc", [])
    for muc in dao_nguoc:
        _ap_ban_va(dich, muc, dao_nguoc=True)
    (dich / ".env").write_text(ENV_RONG, encoding="utf-8")
    _git(["add", "-A"], dich)
    bo = dict.fromkeys(m if isinstance(m, str) else m["commit"] for m in dao_nguoc)
    mo_ta = goc["commit"] + "".join(f" bỏ {c}" for c in bo)
    _git(["commit", "-q", "-m", f"gốc: {ma} ({mo_ta})"], dich)
    sha = _git(["rev-parse", "HEAD"], dich).strip()
    _chep_file_ngoai_git(dich)
    _noi_venv(dich)
    hook = _cai_hook(dich)
    if ap_dap_an:
        for muc in viec["dap_an"]:
            _ap_ban_va(dich, muc)
    return {"thu_muc": str(dich), "goc_sha": sha, "hook": hook}


def dung_ban_cham(bai: Path, tests_dap_an: Path, test_them: list, dich: Path) -> Path:
    """Bản chấm: mã của bài làm + thư mục tests/ của đáp án + test ẩn bổ sung. Bài làm giữ nguyên."""
    def bo_qua(thu_muc, ten_file):
        bo = {t for t in ten_file if t in BO_QUA_KHI_CHEP}
        if Path(thu_muc).resolve() == bai.resolve():
            bo |= {t for t in ten_file if t in ("tests", ".env")}
        return bo
    if dich.exists():
        raise LoiBoViec(f"{dich} đã có")
    shutil.copytree(bai, dich, ignore=bo_qua)
    shutil.copytree(tests_dap_an, dich / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    for path in test_them:
        shutil.copy2(path, dich / "tests" / path.name)
    (dich / ".env").write_text(ENV_RONG, encoding="utf-8")
    _khoi_tao_git(dich)
    _git(["add", "-A"], dich)
    _git(["commit", "-q", "-m", "chấm: bản chấm"], dich)
    _chep_file_ngoai_git(dich)
    _noi_venv(dich)
    _cai_hook(dich)
    return dich


# ----------------------------------------------------------------------------------------------- chạy test
def doc_junit(xml_text: str) -> dict:
    """Kết quả từng test từ file JUnit (pytest -o junit_family=xunit1): {id: "dat"|"hong"|"bo_qua"}.
    id dạng tests/test_x.py::TenLop::test_y[tham_so]. Một test có cả bản ghi đạt lẫn lỗi (lỗi khi dọn) thì tính hỏng.
    File do chính pytest trên máy này ghi; bộ đọc XML của Python không tải thực thể ngoài, expat từ 2.4 tự chặn bom
    mở rộng thực thể, nên không cần thêm thư viện defusedxml."""
    ket_qua: dict = {}
    for case in ET.fromstring(xml_text).iter("testcase"):
        file = (case.get("file") or "").replace("\\", "/")   # pytest trên Windows ghi tests\test_x.py
        classname = case.get("classname") or ""
        module = file[:-3].replace("/", ".") if file.endswith(".py") else ""
        lop = classname[len(module) + 1:] if module and classname.startswith(module + ".") else ""
        test_id = "::".join(p for p in (file or classname, lop, case.get("name") or "") if p)
        tags = {child.tag for child in case}
        trang_thai = "hong" if tags & {"failure", "error"} else "bo_qua" if "skipped" in tags else "dat"
        if ket_qua.get(test_id) != "hong":
            ket_qua[test_id] = trang_thai
    return ket_qua


def chay_pytest(cay: Path, xml: Path, timeout: int = 3600) -> dict:
    proc = _run([str(_python(cay)), "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 f"--junitxml={xml}", "-o", "junit_family=xunit1"], cay, timeout)
    xml.with_suffix(".log").write_text(proc.stdout[-300_000:] + "\n" + proc.stderr[-30_000:], encoding="utf-8")
    if not xml.exists():
        raise LoiBoViec(f"pytest không ghi kết quả ({xml.name}); xem {xml.with_suffix('.log')}")
    return doc_junit(xml.read_text(encoding="utf-8"))


def chay_cong_kiem(bai: Path) -> tuple:
    proc = _run([str(_python(bai)), "-X", "utf8", "tools/check.py"], bai, 1200)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()[-2500:]


# ----------------------------------------------------------------------------------------------- chấm từng phần
def file_da_doi(bai: Path, goc_sha: str) -> list:
    """File khác bản gốc (kể cả file mới chưa commit, file đã xoá). Đưa mọi thứ vào chỉ mục của bài làm để đếm."""
    _git(["add", "-A"], bai)
    return sorted(f for f in _git(["diff", "--cached", "--name-only", "--no-renames", "-z", goc_sha], bai).split("\0") if f)


def kiem_pham_vi(da_doi: list, duoc_sua: list, phai_sua: list) -> list:
    """Vấn đề về phạm vi: file sửa ngoài danh sách được sửa, file bắt buộc mà chưa sửa. Mẫu kết thúc bằng "/" là cả
    thư mục; mẫu khác phải khớp đúng tên file."""
    def khop(path: str, mau: str) -> bool:
        return path.startswith(mau) if mau.endswith("/") else path == mau
    van_de = [f"sửa ngoài phạm vi: {f}" for f in da_doi if not any(khop(f, m) for m in duoc_sua)]
    van_de += [f"chưa sửa file bắt buộc: {m}" for m in phai_sua if not any(khop(f, m) for f in da_doi)]
    return van_de


def _bang_ngoai_le(source: str) -> dict:
    """Các bảng ngoại lệ ALLOWED_* (tên file → số chỗ) ở cấp module của một file test kiến trúc."""
    bang = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id.startswith("ALLOWED_") and isinstance(value, ast.Dict):
            bang[target.id] = {k.value: v.value for k, v in zip(value.keys, value.values)
                               if isinstance(k, ast.Constant) and isinstance(v, ast.Constant) and isinstance(v.value, int)}
    return bang


def ngoai_le_bi_nang(arch_cu: str, arch_moi: str, moc_ruff_cu: str, moc_ruff_moi: str) -> list:
    """Khoá cứng chỉ cho giảm ngoại lệ (CLAUDE.md mục 5.1): ngoại lệ trong tests/test_architecture.py hoặc mốc Ruff
    tools/ruff_baseline.json tăng lên là lách khoá."""
    van_de = []
    cu, moi = _bang_ngoai_le(arch_cu), _bang_ngoai_le(arch_moi)
    for ten, bang in moi.items():
        for file, so in bang.items():
            if so > cu.get(ten, {}).get(file, 0):
                van_de.append(f"nâng ngoại lệ {ten}[{file}]: {cu.get(ten, {}).get(file, 0)} → {so}")
    ruff_cu = json.loads(moc_ruff_cu) if moc_ruff_cu.strip() else {}
    ruff_moi = json.loads(moc_ruff_moi) if moc_ruff_moi.strip() else {}
    for file, luat in ruff_moi.items():
        for ma, so in luat.items():
            if so > ruff_cu.get(file, {}).get(ma, 0):
                van_de.append(f"nâng mốc Ruff {file} {ma}: {ruff_cu.get(file, {}).get(ma, 0)} → {so}")
    return van_de


def _doc_file_goc(bai: Path, goc_sha: str, rel: str) -> str:
    proc = _run(["git", "show", f"{goc_sha}:{rel}"], bai, 60)
    return proc.stdout if proc.returncode == 0 else ""


def _doc_file(bai: Path, rel: str) -> str:
    path = bai / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""


def tinh_diem(dap_an: dict, ket_qua_test: dict, van_de_pham_vi: list, cong_kiem_ok: bool,
              diem_giam_khao: float | None) -> dict:
    """Thang 10. A: 5 × tỉ lệ test ẩn đạt. B: 2 khi không test cũ nào hỏng, 1 khi hỏng 1, 0 khi hỏng từ 2.
    C: 1 khi đúng phạm vi. D: 1 khi cổng kiểm của dự án xanh và không lách khoá. B, C, D chỉ tính khi A > 0 (bài không
    làm được gì thì không ăn điểm phụ). E: điểm giám khảo 0 / 0,5 / 1, chưa chấm thì để trống."""
    f2p, p2p = dap_an["f2p"], dap_an["p2p"]
    test_an_dat = [t for t in f2p if ket_qua_test.get(t) == "dat"]
    test_cu_hong = [t for t in p2p if ket_qua_test.get(t) != "dat"]
    diem: dict = {"A": round(DIEM_TOI_DA["A"] * len(test_an_dat) / len(f2p), 2)}
    co_lam = diem["A"] > 0
    diem["B"] = (2 if not test_cu_hong else 1 if len(test_cu_hong) == 1 else 0) if co_lam else 0
    diem["C"] = (1 if not van_de_pham_vi else 0) if co_lam else 0
    diem["D"] = (1 if cong_kiem_ok else 0) if co_lam else 0
    diem["E"] = diem_giam_khao
    diem["tong"] = round(sum(v for k, v in diem.items() if k in DIEM_TOI_DA and v is not None), 2)
    return {"diem": diem, "test_an_hong": [t for t in f2p if t not in test_an_dat], "test_cu_hong": test_cu_hong}


def doc_diem_giam_khao(path: Path) -> tuple:
    if not path.exists():
        return None, "chưa chấm"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("diem") not in (0, 0.5, 1):
        raise LoiBoViec(f"{path.name}: 'diem' phải là 0, 0.5 hoặc 1 (đang là {data.get('diem')!r})")
    return float(data["diem"]), str(data.get("ly_do", ""))


# ----------------------------------------------------------------------------------------------- chấm một bài
def _tests_dap_an(ma: str, viec: dict, thu_muc_lan: Path) -> Path:
    """tests/ của đáp án (bản gốc + lần sửa thật), dựng một lần cho mỗi lần chạy."""
    dich = thu_muc_lan / "_dap-an" / ma
    if not dich.exists():
        dung_bai(ma, viec, dich, ap_dap_an=True)
    return dich / "tests"


def _test_them(ma: str, viec: dict) -> list:
    return [BO / ma / ten for ten in viec.get("test_them", [])]


def cham_mot_bai(ma: str, viec: dict, bai: Path, goc_sha: str, thu_muc_lan: Path, ten_ban_cham: str) -> dict:
    dap_an = doc_dap_an(ma)
    da_doi = file_da_doi(bai, goc_sha)
    van_de = kiem_pham_vi(da_doi, viec["duoc_sua"], viec.get("phai_sua", []))
    lach = ngoai_le_bi_nang(_doc_file_goc(bai, goc_sha, "tests/test_architecture.py"),
                            _doc_file(bai, "tests/test_architecture.py"),
                            _doc_file_goc(bai, goc_sha, "tools/ruff_baseline.json"),
                            _doc_file(bai, "tools/ruff_baseline.json"))
    cong_ok, cong_log = chay_cong_kiem(bai)
    ban_cham = dung_ban_cham(bai, _tests_dap_an(ma, viec, thu_muc_lan), _test_them(ma, viec),
                             thu_muc_lan / ten_ban_cham)
    ket_qua_test = chay_pytest(ban_cham, thu_muc_lan / f"{ten_ban_cham}.xml")
    ket = tinh_diem(dap_an, ket_qua_test, van_de, cong_ok and not lach, None)
    return {**ket, "file_da_doi": da_doi, "van_de_pham_vi": van_de, "lach_khoa": lach,
            "cong_kiem_dat": cong_ok, "cong_kiem_log": cong_log,
            "so_test": {"an": len(dap_an["f2p"]), "cu": len(dap_an["p2p"])}}


def _ho_so_giam_khao(ma: str, thu_muc_lan: Path, bai: Path, goc_sha: str, may_cham: dict) -> Path:
    de_bai = (thu_muc_lan / f"{ma}-de-bai.md").read_text(encoding="utf-8")
    bao_cao_path = thu_muc_lan / f"{ma}-bao-cao.md"
    bao_cao = bao_cao_path.read_text(encoding="utf-8") if bao_cao_path.exists() else "(người làm bài không để lại báo cáo)"
    diff = _git(["diff", "--cached", "--no-renames", goc_sha], bai)
    if len(diff) > HO_SO_DIFF_TOI_DA:
        diff = diff[:HO_SO_DIFF_TOI_DA] + f"\n... (cắt bớt, còn {len(diff) - HO_SO_DIFF_TOI_DA} ký tự)\n"
    tom_tat = {k: may_cham[k] for k in ("diem", "test_an_hong", "test_cu_hong", "file_da_doi", "van_de_pham_vi",
                                       "lach_khoa", "cong_kiem_dat")}
    path = thu_muc_lan / f"{ma}-ho-so-giam-khao.md"
    path.write_text("\n\n".join([
        f"# Hồ sơ chấm {ma}", "## 1. Đề bài người làm nhận được", de_bai,
        "## 2. Báo cáo cuối của người làm bài", bao_cao,
        "## 3. Kết quả máy chấm (phần A–D)", "```json\n" + json.dumps(tom_tat, ensure_ascii=False, indent=1) + "\n```",
        "Nhật ký cổng kiểm tools/check.py chạy trong bài làm (đoạn cuối):", "```\n" + may_cham["cong_kiem_log"] + "\n```",
        "## 4. Thay đổi của bài làm so với bản gốc", "```diff\n" + diff + "\n```"]), encoding="utf-8")
    return path


# ----------------------------------------------------------------------------------------------- lệnh
def _chon_viec(tat_ca: dict, chon: list | None) -> dict:
    if not chon:
        return tat_ca
    thieu = [m for m in chon if m not in tat_ca]
    if thieu:
        raise LoiBoViec(f"Không có việc {', '.join(thieu)} (có: {', '.join(tat_ca)})")
    return {m: tat_ca[m] for m in chon}


def lenh_chuan_bi(lan: str, mo_ta: str, chon: list | None) -> None:
    thu_muc_lan = CACHE / lan
    if (thu_muc_lan / "lan-chay.json").exists():
        raise LoiBoViec(f"Lần chạy '{lan}' đã có; chọn tên khác")
    loi_dan = LOI_DAN_CHUNG.read_text(encoding="utf-8")
    ghi = {"lan": lan, "mo_ta": mo_ta, "tao_luc": dt.datetime.now().isoformat(timespec="seconds"), "viec": {}}
    for ma, viec in _chon_viec(doc_viec(), chon).items():
        doc_dap_an(ma)   # báo sớm nếu việc chưa có đáp án
        info = dung_bai(ma, viec, thu_muc_lan / ma)
        de_bai = (BO / ma / "de-bai.md").read_text(encoding="utf-8")
        (thu_muc_lan / f"{ma}-de-bai.md").write_text(
            loi_dan.replace("{THU_MUC}", info["thu_muc"]) + "\n\n" + de_bai, encoding="utf-8")
        ghi["viec"][ma] = info
        print(f"{ma}: {info['thu_muc']} ({info['hook']})")
    (thu_muc_lan / "lan-chay.json").write_text(json.dumps(ghi, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nĐề bài đầy đủ: {thu_muc_lan}\\<việc>-de-bai.md. Giao từng đề cho agent; báo cáo cuối của agent lưu vào "
          f"<việc>-bao-cao.md cùng thư mục, rồi chạy: tools\\bo_viec_mau.py cham --lan {lan}")


def _bang_diem(ket_qua: dict) -> str:
    dong = ["| Việc | A /5 | B /2 | C /1 | D /1 | E /1 | Tổng /10 |", "|---|---|---|---|---|---|---|"]
    tong = 0.0
    for ma, kq in ket_qua.items():
        d = kq["diem"]
        e = "chưa chấm" if d["E"] is None else f"{d['E']:g}"
        dong.append(f"| {ma} | {d['A']:g} | {d['B']} | {d['C']} | {d['D']} | {e} | {d['tong']:g} |")
        tong += d["tong"]
    dong.append(f"| **Cộng** | | | | | | **{tong:g} / {10 * len(ket_qua)}** |")
    return "\n".join(dong)


def lenh_cham(lan: str, chon: list | None, chay_lai: bool, ghi_lich_su: bool) -> None:
    thu_muc_lan = CACHE / lan
    info_lan = json.loads((thu_muc_lan / "lan-chay.json").read_text(encoding="utf-8"))
    tat_ca = doc_viec()
    ket_qua = {}
    for ma in (chon or list(info_lan["viec"])):
        viec, info = tat_ca[ma], info_lan["viec"][ma]
        may_cham_path = thu_muc_lan / f"{ma}-may-cham.json"
        if may_cham_path.exists() and not chay_lai:
            may_cham = json.loads(may_cham_path.read_text(encoding="utf-8"))
        else:
            ten = f"{ma}-cham-{dt.datetime.now():%H%M%S}"
            may_cham = cham_mot_bai(ma, viec, Path(info["thu_muc"]), info["goc_sha"], thu_muc_lan, ten)
            may_cham_path.write_text(json.dumps(may_cham, ensure_ascii=False, indent=1), encoding="utf-8")
        ho_so = _ho_so_giam_khao(ma, thu_muc_lan, Path(info["thu_muc"]), info["goc_sha"], may_cham)
        diem_e, ly_do = doc_diem_giam_khao(thu_muc_lan / f"{ma}-giam-khao.json")
        ket = {**may_cham, "diem": {**may_cham["diem"], "E": diem_e}, "giam_khao": ly_do, "ho_so": str(ho_so)}
        ket["diem"]["tong"] = round(sum(v for k, v in ket["diem"].items() if k in DIEM_TOI_DA and v is not None), 2)
        ket_qua[ma] = ket
        print(f"{ma}: {ket['diem']}  test ẩn hỏng {len(ket['test_an_hong'])}/{ket['so_test']['an']}, "
              f"test cũ hỏng {len(ket['test_cu_hong'])}/{ket['so_test']['cu']}, phạm vi {ket['van_de_pham_vi'] or 'đúng'}, "
              f"lách khoá {ket['lach_khoa'] or 'không'}, cổng kiểm {'đạt' if ket['cong_kiem_dat'] else 'HỎNG'}")
    (thu_muc_lan / "ket-qua.json").write_text(json.dumps({"lan": lan, "mo_ta": info_lan["mo_ta"], "viec": ket_qua},
                                                         ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + _bang_diem(ket_qua))
    chua = [m for m, k in ket_qua.items() if k["diem"]["E"] is None]
    if chua:
        print(f"\nChưa có điểm giám khảo (E) cho {', '.join(chua)}: đưa <việc>-ho-so-giam-khao.md cùng "
              f"docs/bo-viec-mau/giam-khao.md cho giám khảo, lưu kết quả vào <việc>-giam-khao.json rồi chạy lại lệnh này.")
    if ghi_lich_su:
        if chua:
            raise LoiBoViec("Chưa ghi lịch sử: còn việc chưa có điểm giám khảo")
        tong = sum(k["diem"]["tong"] for k in ket_qua.values())
        cot = " | ".join(f"{ket_qua[m]['diem']['tong']:g}" if m in ket_qua else "—" for m in tat_ca)
        with LICH_SU.open("a", encoding="utf-8") as f:
            f.write(f"| {dt.date.today():%d/%m/%Y} | {lan} | {info_lan['mo_ta']} | {cot} | {tong:g} / {10 * len(ket_qua)} |\n")
        print(f"Đã ghi một dòng vào {LICH_SU.relative_to(ROOT).as_posix()}")


def lenh_so_sanh(truoc: str, sau: str) -> None:
    a = json.loads((CACHE / truoc / "ket-qua.json").read_text(encoding="utf-8"))
    b = json.loads((CACHE / sau / "ket-qua.json").read_text(encoding="utf-8"))
    print(f"Trước: {truoc} ({a['mo_ta']})\nSau:   {sau} ({b['mo_ta']})\n")
    print("| Việc | Trước | Sau | Chênh |\n|---|---|---|---|")
    tong_a = tong_b = 0.0
    for ma in sorted(set(a["viec"]) | set(b["viec"])):
        da = a["viec"].get(ma, {}).get("diem", {}).get("tong")
        db = b["viec"].get(ma, {}).get("diem", {}).get("tong")
        chenh = f"{db - da:+g}" if da is not None and db is not None else "—"
        print(f"| {ma} | {'—' if da is None else f'{da:g}'} | {'—' if db is None else f'{db:g}'} | {chenh} |")
        tong_a += da or 0
        tong_b += db or 0
    print(f"| **Cộng** | {tong_a:g} | {tong_b:g} | {tong_b - tong_a:+g} |")
    print("\nChênh từ 1 điểm trở xuống ở một việc có thể chỉ là dao động giữa hai lần chạy (README, mục Giới hạn).")


def lenh_tinh_dap_an(chon: list | None) -> None:
    """Dựng bài gốc và bài đáp án, chạy cả bộ test (đáp án chạy 2 lần để loại test chập chờn), lập danh sách:
    f2p = test hỏng ở bài gốc, đạt ở đáp án (test ẩn); p2p = test đạt ở cả hai (không được làm hỏng).
    Sau đó tự kiểm máy chấm: bài gốc phải được 0 điểm, đáp án phải được đủ 9 điểm tự động."""
    thu_muc = CACHE / f"_tinh-dap-an-{dt.datetime.now():%Y%m%d-%H%M%S}"
    for ma, viec in _chon_viec(doc_viec(), chon).items():
        print(f"== {ma}: {viec['ten']}", flush=True)
        goc = dung_bai(ma, viec, thu_muc / ma / "goc")
        da = dung_bai(ma, viec, thu_muc / ma / "dap-an", ap_dap_an=True)
        tests = Path(da["thu_muc"]) / "tests"
        them = _test_them(ma, viec)
        ban_goc = dung_ban_cham(Path(goc["thu_muc"]), tests, them, thu_muc / ma / "goc-cham")
        ban_da = dung_ban_cham(Path(da["thu_muc"]), tests, them, thu_muc / ma / "dap-an-cham")
        kq_goc = chay_pytest(ban_goc, thu_muc / ma / "goc.xml")
        kq_da1 = chay_pytest(ban_da, thu_muc / ma / "dap-an-1.xml")
        kq_da2 = chay_pytest(ban_da, thu_muc / ma / "dap-an-2.xml")
        tat_ca_id = sorted(set(kq_goc) | set(kq_da1) | set(kq_da2))
        on_dinh = [t for t in tat_ca_id if kq_da1.get(t) == kq_da2.get(t)]
        dap_an = {
            "viec": ma, "goc": viec["goc"], "dap_an": viec["dap_an"], "tao_luc": dt.datetime.now().isoformat(timespec="seconds"),
            "f2p": [t for t in on_dinh if kq_da1.get(t) == "dat" and kq_goc.get(t) != "dat"],
            "p2p": [t for t in on_dinh if kq_da1.get(t) == "dat" and kq_goc.get(t) == "dat"],
            "khong_on_dinh": [t for t in tat_ca_id if kq_da1.get(t) != kq_da2.get(t)],
            "hong_ca_hai_hoac_bo_qua": [t for t in on_dinh if kq_da1.get(t) != "dat"],
        }
        if not dap_an["f2p"]:
            raise LoiBoViec(f"{ma}: không có test nào hỏng ở bài gốc mà đạt ở đáp án; việc mẫu này không chấm được")
        (BO / ma / "dap-an.json").write_text(json.dumps(dap_an, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        thieu_them = [p.name for p in them if not any(t.startswith(f"tests/{p.name}::") for t in dap_an["f2p"] + dap_an["p2p"])]
        # tự kiểm máy chấm trên hai bài biết trước kết quả
        kiem = {}
        for ten, info, kq in (("goc", goc, kq_goc), ("dap-an", da, kq_da1)):
            bai = Path(info["thu_muc"])
            van_de = kiem_pham_vi(file_da_doi(bai, info["goc_sha"]), viec["duoc_sua"], viec.get("phai_sua", []))
            lach = ngoai_le_bi_nang(_doc_file_goc(bai, info["goc_sha"], "tests/test_architecture.py"),
                                    _doc_file(bai, "tests/test_architecture.py"),
                                    _doc_file_goc(bai, info["goc_sha"], "tools/ruff_baseline.json"),
                                    _doc_file(bai, "tools/ruff_baseline.json"))
            cong_ok, cong_log = chay_cong_kiem(bai)
            kiem[ten] = tinh_diem(dap_an, kq, van_de, cong_ok and not lach, None)
            kiem[ten].update(van_de_pham_vi=van_de, lach_khoa=lach, cong_kiem_dat=cong_ok,
                             cong_kiem_log=cong_log if not cong_ok else "")
        dat = kiem["goc"]["diem"]["tong"] == 0 and kiem["dap-an"]["diem"]["tong"] == 9
        (thu_muc / ma / "tu-kiem.json").write_text(json.dumps(kiem, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"   test ẩn (f2p) {len(dap_an['f2p'])}: {dap_an['f2p']}")
        print(f"   test cũ phải giữ (p2p) {len(dap_an['p2p'])}, chập chờn {len(dap_an['khong_on_dinh'])}, "
              f"hỏng cả hai/bỏ qua {len(dap_an['hong_ca_hai_hoac_bo_qua'])}")
        if thieu_them:
            print(f"   [CHÚ Ý] test bổ sung không vào danh sách nào (hỏng ở đáp án?): {thieu_them}")
        print(f"   tự kiểm máy chấm: bài gốc {kiem['goc']['diem']}, đáp án {kiem['dap-an']['diem']} → "
              f"{'ĐẠT' if dat else 'CHƯA ĐẠT'}", flush=True)
    print(f"\nThư mục làm việc: {thu_muc}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Bộ việc mẫu chuẩn: chấm agent/skill, báo điểm trước/sau")
    sub = parser.add_subparsers(dest="lenh", required=True)
    p = sub.add_parser("chuan-bi", help="dựng thư mục làm bài cho một lần chạy")
    p.add_argument("--lan", required=True, help="tên lần chạy, vd 2026-10-23-goc")
    p.add_argument("--mo-ta", required=True, help="agent/skill đang thử, vd 'general-purpose, chưa cài skill'")
    p.add_argument("--viec", nargs="*")
    p = sub.add_parser("cham", help="chấm một lần chạy")
    p.add_argument("--lan", required=True)
    p.add_argument("--viec", nargs="*")
    p.add_argument("--chay-lai", action="store_true", help="chấm lại phần tự động dù đã có kết quả")
    p.add_argument("--ghi-lich-su", action="store_true", help="ghi một dòng vào docs/bo-viec-mau/lich-su-diem.md")
    p = sub.add_parser("so-sanh", help="bảng điểm trước/sau")
    p.add_argument("truoc")
    p.add_argument("sau")
    p = sub.add_parser("tinh-dap-an", help="lập danh sách test ẩn, tự kiểm máy chấm")
    p.add_argument("--viec", nargs="*")
    args = parser.parse_args()
    try:
        if args.lenh == "chuan-bi":
            lenh_chuan_bi(args.lan, args.mo_ta, args.viec)
        elif args.lenh == "cham":
            lenh_cham(args.lan, args.viec, args.chay_lai, args.ghi_lich_su)
        elif args.lenh == "so-sanh":
            lenh_so_sanh(args.truoc, args.sau)
        else:
            lenh_tinh_dap_an(args.viec)
    except (LoiBoViec, subprocess.TimeoutExpired) as e:
        print(f"[LỖI] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
