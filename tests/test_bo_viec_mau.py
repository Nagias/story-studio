"""Bộ việc mẫu chuẩn (docs/bo-viec-mau, tools/bo_viec_mau.py): cách tính điểm, kiểm phạm vi, chặn lách khoá, đọc
kết quả test, và bộ đề có đủ thành phần. Không dựng bài, không chạy test con (việc đó là `tinh-dap-an`, ~25 phút/việc)."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BO = ROOT / "docs" / "bo-viec-mau"
_spec = importlib.util.spec_from_file_location("story_studio_bo_viec_mau", ROOT / "tools" / "bo_viec_mau.py")
assert _spec and _spec.loader
bvm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bvm)

DAP_AN = {"f2p": ["tests/a.py::an1", "tests/a.py::an2"], "p2p": ["tests/b.py::cu1", "tests/b.py::cu2", "tests/b.py::cu3"]}
ALL_PASS = {t: "dat" for t in DAP_AN["f2p"] + DAP_AN["p2p"]}


# ----------------------------------------------------------------------------- tính điểm
def test_bai_dung_het_duoc_9_diem_may_va_cong_diem_giam_khao():
    ket = bvm.tinh_diem(DAP_AN, ALL_PASS, [], True, None)
    assert ket["diem"] == {"A": 5.0, "B": 2, "C": 1, "D": 1, "E": None, "tong": 9.0}
    assert bvm.tinh_diem(DAP_AN, ALL_PASS, [], True, 0.5)["diem"]["tong"] == 9.5


def test_bai_khong_lam_duoc_gi_thi_khong_an_diem_phu():
    chua_lam = {**ALL_PASS, "tests/a.py::an1": "hong", "tests/a.py::an2": "hong"}
    ket = bvm.tinh_diem(DAP_AN, chua_lam, [], True, None)
    assert ket["diem"]["tong"] == 0 and ket["diem"]["B"] == ket["diem"]["C"] == ket["diem"]["D"] == 0
    assert bvm.tinh_diem(DAP_AN, chua_lam, [], True, 1)["diem"]["tong"] == 1   # báo cáo trung thực vẫn được điểm


def test_diem_a_theo_ti_le_test_an_va_test_bi_bo_qua_tinh_la_hong():
    mot_nua = {**ALL_PASS, "tests/a.py::an2": "bo_qua"}
    ket = bvm.tinh_diem(DAP_AN, mot_nua, [], True, None)
    assert ket["diem"]["A"] == 2.5 and ket["test_an_hong"] == ["tests/a.py::an2"]


def test_diem_b_theo_so_test_cu_bi_hong_va_test_mat_tinh_la_hong():
    mot = {k: v for k, v in ALL_PASS.items() if k != "tests/b.py::cu1"}            # test cũ biến mất
    assert bvm.tinh_diem(DAP_AN, mot, [], True, None)["diem"]["B"] == 1
    hai = {**mot, "tests/b.py::cu2": "hong"}
    ket = bvm.tinh_diem(DAP_AN, hai, [], True, None)
    assert ket["diem"]["B"] == 0 and ket["test_cu_hong"] == ["tests/b.py::cu1", "tests/b.py::cu2"]


def test_diem_c_d_theo_pham_vi_va_cong_kiem():
    ket = bvm.tinh_diem(DAP_AN, ALL_PASS, ["sửa ngoài phạm vi: run.py"], False, None)
    assert (ket["diem"]["C"], ket["diem"]["D"], ket["diem"]["tong"]) == (0, 0, 7.0)


# ----------------------------------------------------------------------------- phạm vi, lách khoá
def test_kiem_pham_vi_thu_muc_file_dung_ten_va_file_bat_buoc():
    duoc = ["backend/services/thumbnail_service.py", "tests/", "FEATURE_MAP.md"]
    assert bvm.kiem_pham_vi(["tests/test_x.py", "backend/services/thumbnail_service.py"], duoc, []) == []
    assert bvm.kiem_pham_vi(["backend/services/thumbnail_service.py.bak", "tests_khac.py"], duoc, []) == [
        "sửa ngoài phạm vi: backend/services/thumbnail_service.py.bak", "sửa ngoài phạm vi: tests_khac.py"]
    assert bvm.kiem_pham_vi(["tests/test_x.py"], duoc, ["FEATURE_MAP.md"]) == ["chưa sửa file bắt buộc: FEATURE_MAP.md"]


def test_ngoai_le_khoa_cung_chi_duoc_giam():
    cu = 'ALLOWED_DELETES = {\n    "a.py": 2,\n}\nALLOWED_ENV: dict = {"b.py": 1}\nOTHER = {"x": 9}\n'
    giam = 'ALLOWED_DELETES = {"a.py": 1}\nALLOWED_ENV: dict = {}\n'
    assert bvm.ngoai_le_bi_nang(cu, giam, "", "") == []
    nang = 'ALLOWED_DELETES = {"a.py": 3, "c.py": 1}\nALLOWED_ENV: dict = {"b.py": 1}\n'
    assert bvm.ngoai_le_bi_nang(cu, nang, "", "") == ["nâng ngoại lệ ALLOWED_DELETES[a.py]: 2 → 3",
                                                      "nâng ngoại lệ ALLOWED_DELETES[c.py]: 0 → 1"]
    ruff_cu, ruff_moi = '{"x.py": {"S110": 2}}', '{"x.py": {"S110": 3, "F401": 1}}'
    assert bvm.ngoai_le_bi_nang("", "", ruff_cu, ruff_moi) == ["nâng mốc Ruff x.py S110: 2 → 3", "nâng mốc Ruff x.py F401: 0 → 1"]
    assert bvm.ngoai_le_bi_nang("", "", ruff_cu, '{"x.py": {"S110": 1}}') == []


def test_file_test_moi_chi_lay_file_bai_lam_tu_them(tmp_path):
    bai, dap_an = tmp_path / "bai", tmp_path / "dap_an"
    for path in (bai / "test_cu.py", bai / "test_moi.py", bai / "fixtures" / "mau.json", bai / "__pycache__" / "x.pyc",
                 dap_an / "test_cu.py", dap_an / "test_an.py"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    assert bvm.file_test_moi(bai, dap_an) == ["fixtures/mau.json", "test_moi.py"]


def test_chay_lai_chi_cuu_test_hong_ma_lan_sau_dat():
    dau = {"a": "hong", "b": "hong", "c": "dat", "d": "bo_qua"}
    gop, cuu = bvm.gop_chay_lai(dau, {"a": "dat", "b": "hong", "d": "dat"})
    assert gop == {"a": "dat", "b": "hong", "c": "dat", "d": "bo_qua"} and cuu == ["a"]


# ----------------------------------------------------------------------------- đọc kết quả pytest
def test_doc_junit_nhan_dat_hong_bo_qua_lop_va_tham_so():
    xml = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite>
      <testcase classname="tests.test_a" name="test_dat" file="tests/test_a.py" line="1"/>
      <testcase classname="tests.test_a" name="test_hong[x-1]" file="tests/test_a.py" line="2"><failure message="m"/></testcase>
      <testcase classname="tests.test_a.TestLop" name="test_bo_qua" file="tests/test_a.py" line="3"><skipped message="s"/></testcase>
      <testcase classname="tests.test_a" name="test_loi_khi_don" file="tests/test_a.py" line="4"/>
      <testcase classname="tests.test_a" name="test_loi_khi_don" file="tests/test_a.py" line="4"><error message="e"/></testcase>
      <testcase classname="tests.test_b" name="test_windows" file="tests\\test_b.py" line="1"/>
    </testsuite></testsuites>"""
    assert bvm.doc_junit(xml) == {
        "tests/test_b.py::test_windows": "dat",   # pytest trên Windows ghi dấu \ trong đường dẫn
        "tests/test_a.py::test_dat": "dat",
        "tests/test_a.py::test_hong[x-1]": "hong",
        "tests/test_a.py::TestLop::test_bo_qua": "bo_qua",
        "tests/test_a.py::test_loi_khi_don": "hong",
    }


# ----------------------------------------------------------------------------- bộ đề đủ thành phần
def test_moi_viec_mau_co_du_de_bai_test_bo_sung_va_dap_an_da_kiem():
    viec = bvm.doc_viec()
    # 23/10/2026 chủ dự án chọn 3–5 việc; 29/10/2026 (CLAUDE.md mục 1.2 câu 13): "cứ thêm việc khó và đo liên tục"
    assert 3 <= len(viec) <= 10, "bộ việc mẫu 3–10 việc (CLAUDE.md mục 1.2 câu 13)"
    loi_dan = (BO / "loi-dan-chung.md").read_text(encoding="utf-8")
    assert "{THU_MUC}" in loi_dan
    for ma, v in viec.items():
        assert (BO / ma / "de-bai.md").exists(), f"{ma}: thiếu de-bai.md"
        for ten in v.get("test_them", []):
            assert (BO / ma / ten).exists(), f"{ma}: thiếu test bổ sung {ten}"
        for mau in v.get("phai_sua", []):
            assert any(mau == d or (d.endswith("/") and mau.startswith(d)) for d in v["duoc_sua"]), \
                f"{ma}: file bắt buộc {mau} không nằm trong danh sách được sửa"
        dap_an = json.loads((BO / ma / "dap-an.json").read_text(encoding="utf-8"))
        assert dap_an["goc"] == v["goc"] and dap_an["dap_an"] == v["dap_an"] and \
            dap_an.get("bo_cham", []) == sorted(v.get("bo_cham", [])), \
            f"{ma}: viec.json đã đổi mà dap-an.json chưa lập lại (chạy tools/bo_viec_mau.py tinh-dap-an --viec {ma})"
        assert dap_an["f2p"] and dap_an["p2p"], f"{ma}: đáp án thiếu test ẩn hoặc test cũ"
        if v.get("bo_cham"):
            assert v.get("ly_do_bo_cham"), f"{ma}: bỏ chấm test của lần sửa thật phải ghi lý do (ly_do_bo_cham)"
            assert not set(v["bo_cham"]) & set(dap_an["f2p"] + dap_an["p2p"]), f"{ma}: test bỏ chấm vẫn đang được chấm"
        for ten in v.get("test_them", []):
            assert any(t.startswith(f"tests/{ten}::") for t in dap_an["f2p"] + dap_an["p2p"]), \
                f"{ma}: test bổ sung {ten} không đạt ở đáp án (không vào danh sách chấm nào)"


# ----------------------------------------------------------------------------- dựng bài
def test_bai_lam_khong_co_de_dap_an_nhung_co_file_giu_cho_readme(tmp_path, monkeypatch):
    """Gặp 29/10/2026 khi thêm T6, T7: CLAUDE.md nhắc docs/bo-viec-mau/README.md mà bài làm bỏ cả thư mục đó, nên test
    FEATURE_MAP hỏng ngay trên đáp án (điểm D = 0). Bài làm phải có file giữ chỗ, không có đề hay đáp án."""
    import io
    import tarfile
    from types import SimpleNamespace
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, text in {"CLAUDE.md": "xem docs/bo-viec-mau/README.md", "docs/bo-viec-mau/T1/de-bai.md": "đề",
                           "docs/bo-viec-mau/viec.json": "{}", "docs/khac.md": "giữ"}.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    monkeypatch.setattr(bvm, "_run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=buf.getvalue(), stderr=b""))
    bvm._giai_nen("abc1234", tmp_path)
    assert (tmp_path / "docs/khac.md").exists() and (tmp_path / "CLAUDE.md").exists()
    assert sorted(p.relative_to(tmp_path).as_posix() for p in (tmp_path / "docs/bo-viec-mau").rglob("*")) == [
        "docs/bo-viec-mau/README.md"]
    assert "đáp án" in (tmp_path / "docs/bo-viec-mau/README.md").read_text(encoding="utf-8")
