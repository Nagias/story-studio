"""
G1–G4 của luồng chuyển thể vụ án: cắt bài thành đoạn, đọc từng đoạn, gộp tên, đặt tên hư cấu → hồ sơ (CaseBible).

- LLM giả (tests/case_adaptation_fakes.py) đọc marker ở dòng đầu prompt và trả fixture trong
  tests/fixtures/case_adaptation/; không gọi 9router thật.
- Đầu ra mỏng, sai cấu trúc hoặc vi phạm quy tắc tên phải bị loại và gọi lại kèm lý do; hỏng 3 lần thì StepFailed.
- Chạy trong thư mục tạm qua fixture isolated_projects_dir.
"""
import asyncio
import copy
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.case_adaptation_schemas import MAX_ATTEMPTS, CaseBible, CasePipeline
from services import case_adaptation_llm, case_adaptation_steps, case_store
from services.case_adaptation_checks import GENERIC_TERMS, fold, is_kept_term
from services.case_adaptation_llm import LLMError
from services.case_adaptation_prompts import extract_prompt
from services.case_adaptation_steps import (
    StepFailed,
    StepRejected,
    StepResult,
    ask_validated,
    chunk_source,
    initial_steps,
    run_step,
)
from tests.case_adaptation_fakes import FIXTURES_DIR, load_fixture, make_fake_llm

DOSSIER = (FIXTURES_DIR / "dossier.txt").read_text(encoding="utf-8")
RETRY_MARK = "LẦN TRƯỚC BỊ LOẠI VÌ"
LAZY_EXTRACT = {
    "names": [],
    "events": [{"summary": "Có án mạng.", "time_label": "", "names": []}],
    "evidence": [],
    "relations": [],
}


# ---------------------------------------------------------------- helpers

def _new_pipeline() -> CasePipeline:
    """Vụ án mẫu trên đĩa tạm: bài gốc, 2 đoạn (chunk_chars=900) và hàng việc ban đầu."""
    now = datetime.now(timezone.utc).isoformat()
    case_id = case_store.new_case_id()
    chunks = chunk_source(DOSSIER, 900)
    pipeline = CasePipeline(
        case_id=case_id, target_minutes=8, visual_style="cinematic", chunk_chars=900,
        created_at=now, updated_at=now, steps=initial_steps(len(chunks)),
    )
    case_store.save_source(case_id, DOSSIER)
    case_store.save_chunks(case_id, chunks)
    case_store.save_pipeline(pipeline)
    return pipeline


def _step(pipeline: CasePipeline, step_id: str):
    return next(s for s in pipeline.steps if s.id == step_id)


def _run(pipeline: CasePipeline, step_id: str, llm) -> StepResult:
    """Chạy một việc rồi lưu kết quả như worker sẽ làm."""
    result = asyncio.run(run_step(pipeline, _step(pipeline, step_id), llm=llm))
    case_store.save_step_output(pipeline.case_id, step_id, result.output)
    return result


def _run_until(pipeline: CasePipeline, last_step_id: str, llm) -> StepResult:
    result = None
    for step in pipeline.steps:
        result = _run(pipeline, step.id, llm)
        if step.id == last_step_id:
            return result
    raise AssertionError(f"không có việc {last_step_id}")


# ---------------------------------------------------------------- G1: cắt đoạn, hàng việc ban đầu

def test_chunk_source_respects_paragraphs():
    short_a = "Đoạn mở đầu ngắn kể về bối cảnh của vụ việc ở một thị trấn ven biển."
    sentences = [f"Câu số {i} kể một chi tiết riêng của cuộc điều tra kéo dài nhiều tuần liền." for i in range(1, 41)]
    long_b = " ".join(sentences[:20]) + "\n" + " ".join(sentences[20:])
    short_c = "Đoạn kết ngắn nói về những câu hỏi còn bỏ ngỏ sau phiên toà."
    text = f"{short_a}\n\n{long_b}\n\n\n{short_c}\n"
    max_chars = 500

    chunks = chunk_source(text, max_chars)

    assert len(chunks) > 2
    assert all(0 < len(c) <= max_chars for c in chunks)
    for sentence in sentences:                       # mọi câu còn nguyên trong một đoạn nào đó
        assert any(sentence in c for c in chunks), sentence
    assert any(short_a in c for c in chunks)         # đoạn văn vừa cỡ không bị cắt
    assert any(short_c in c for c in chunks)
    assert " ".join(chunks).split() == text.split()  # nối lại thì đủ chữ, đúng thứ tự


def test_chunk_source_single_newline_paragraphs():
    # Bài dán từ web: đoạn văn chỉ ngăn bằng một lần xuống dòng, không có dòng trống.
    paragraphs = [" ".join(f"Đoạn {p} câu {s} kể thêm một chi tiết của vụ án." for s in range(1, 3 + p % 4))
                  for p in range(1, 16)]
    text = "\n".join(paragraphs)
    max_chars = 400
    assert len(text) > 3 * max_chars and all(len(p) <= max_chars for p in paragraphs)

    chunks = chunk_source(text, max_chars)

    assert len(chunks) > 3
    for chunk in chunks:
        assert len(chunk) <= max_chars
        assert all(line in paragraphs for line in chunk.split("\n")), chunk   # chỉ cắt ở chỗ hết đoạn văn
    assert " ".join(chunks).split() == text.split()


def test_chunk_source_splits_overlong_sentence_without_losing_words():
    words = [f"chu{i}" for i in range(400)]          # một "câu" không có dấu chấm, dài hơn max_chars
    text = " ".join(words)
    chunks = chunk_source(text, 300)
    assert all(len(c) <= 300 for c in chunks)
    assert " ".join(chunks).split() == words
    assert chunk_source("   \n\n  ", 300) == []


def test_dossier_splits_into_two_chunks_and_initial_steps():
    chunks = chunk_source(DOSSIER, 900)
    assert len(chunks) == 2
    assert " ".join(chunks).split() == DOSSIER.split()
    steps = initial_steps(2)
    assert [(s.id, s.kind) for s in steps] == [
        ("extract_00", "extract_chunk"), ("extract_01", "extract_chunk"),
        ("cluster", "cluster_names"), ("aliases", "assign_aliases"), ("outline", "build_outline"),
    ]
    assert [s.params.get("index") for s in steps[:2]] == [0, 1]
    assert all(s.status == "pending" for s in steps)


# ---------------------------------------------------------------- ask_validated

def test_ask_validated_scalar_result_is_rejected_and_retried():
    seen = []

    async def llm(system, user, *, temperature=0.4, timeout=240.0, client=None):
        seen.append(user)
        return [None, 42, {"ok": True}][len(seen) - 1]

    result = asyncio.run(ask_validated("TASK: X", lambda raw: raw, llm=llm, step_label="thử"))
    assert result == {"ok": True}
    assert len(seen) == 3
    assert RETRY_MARK in seen[1] and "JSON object/array" in seen[1]


def test_ask_validated_reason_appended_and_failure_names_step():
    seen = []

    async def llm(system, user, *, temperature=0.4, timeout=240.0, client=None):
        seen.append(user)
        return {"n": len(seen)}

    def validate(raw):
        raise StepRejected("thiếu thứ gì đó.")

    with pytest.raises(StepFailed) as info:
        asyncio.run(ask_validated("TASK: X", validate, llm=llm, step_label="gộp tên"))
    assert len(seen) == MAX_ATTEMPTS
    assert seen[0] == "TASK: X"
    assert seen[1] == "TASK: X\n\nLẦN TRƯỚC BỊ LOẠI VÌ: thiếu thứ gì đó. Hãy làm lại đầy đủ, không tóm gọn."
    assert info.value.user_message == f"Bước gộp tên thất bại sau {MAX_ATTEMPTS} lần: thiếu thứ gì đó."


def test_retryable_llm_error_is_retried(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm({"EXTRACT 0": [LLMError("invalid_json", "Model trả về nội dung không phải JSON hợp lệ.")]})
    result = _run(pipeline, "extract_00", llm)
    assert calls == ["EXTRACT 0", "EXTRACT 0"]
    assert len(result.output["events"]) == 6


# ---------------------------------------------------------------- ask_validated: 9router bận

def _busy(seconds=None) -> LLMError:
    return LLMError("busy", "9router đang bận hoặc tạm thời không dùng được (HTTP 503).", retry_after_s=seconds)


def _scripted_llm(replies: list):
    """LLM giả trả lần lượt `replies` (phần tử là Exception thì raise); `seen` ghi user prompt từng lần gọi."""
    seen: list[str] = []

    async def llm(system, user, *, temperature=0.4, timeout=240.0, client=None):
        seen.append(user)
        reply = replies[len(seen) - 1]
        if isinstance(reply, BaseException):
            raise reply
        return reply

    return llm, seen


@pytest.fixture
def busy_sleeps(monkeypatch):
    """Thay hàm chờ khi 9router bận bằng hàm ghi lại số giây, để test không phải chờ thật."""
    waited: list[float] = []

    async def fake_sleep(seconds):
        waited.append(seconds)

    monkeypatch.setattr(case_adaptation_steps, "busy_sleep", fake_sleep)
    return waited


def test_busy_sleep_defaults_to_asyncio_sleep():
    assert case_adaptation_steps.busy_sleep is asyncio.sleep


def test_busy_waits_then_retries_without_using_an_attempt(busy_sleeps):
    def validate(raw):
        if raw.get("ok"):
            return raw
        raise StepRejected("chưa đủ")

    llm, seen = _scripted_llm([_busy(120), {"n": 1}, {"n": 2}, {"ok": True}])
    result = asyncio.run(ask_validated("TASK: X", validate, llm=llm, step_label="thử"))

    assert result == {"ok": True}
    assert len(seen) == 1 + MAX_ATTEMPTS        # lần bị bận không tính vào MAX_ATTEMPTS
    assert busy_sleeps == [120]                 # chờ đúng số giây 9router báo
    assert seen[1] == "TASK: X"                 # bận: prompt chưa tới model, không nối lý do


def test_busy_without_hint_backs_off_from_60s(busy_sleeps):
    llm, seen = _scripted_llm([_busy(), _busy(), {"ok": True}])
    assert asyncio.run(ask_validated("TASK: X", lambda raw: raw, llm=llm, step_label="thử")) == {"ok": True}
    assert busy_sleeps == [60, 120]


def test_busy_zero_hint_still_waits_a_little(busy_sleeps):
    llm, _seen = _scripted_llm([_busy(0), {"ok": True}])
    asyncio.run(ask_validated("TASK: X", lambda raw: raw, llm=llm, step_label="thử"))
    assert busy_sleeps == [case_adaptation_steps.BUSY_MIN_WAIT_S]
    assert busy_sleeps[0] > 0


def test_busy_too_long_fails_step(busy_sleeps):
    llm, seen = _scripted_llm([_busy()] * 20)
    with pytest.raises(StepFailed) as info:
        asyncio.run(ask_validated("TASK: X", lambda raw: raw, llm=llm, step_label="gộp tên"))

    assert busy_sleeps == [60, 120, 240, 480]
    assert sum(busy_sleeps) == case_adaptation_steps.BUSY_WAIT_CAP_S == 15 * 60
    assert len(seen) == 5                       # gọi lại sau mỗi lần chờ, lần cuối vẫn bận thì dừng
    message = info.value.user_message
    assert "gộp tên" in message and "9router" in message and "15 phút" in message
    assert "HTTP 503" in message                # kèm lỗi gần nhất


def test_busy_long_hint_is_capped(busy_sleeps):
    llm, _seen = _scripted_llm([_busy(600)] * 5)
    with pytest.raises(StepFailed):
        asyncio.run(ask_validated("TASK: X", lambda raw: raw, llm=llm, step_label="thử"))
    assert busy_sleeps == [600, 300]


def test_auth_error_not_retried_and_no_wait(busy_sleeps):
    llm, seen = _scripted_llm([LLMError("auth", "9router từ chối API key (401)."), {"ok": True}])
    with pytest.raises(StepFailed) as info:
        asyncio.run(ask_validated("TASK: X", lambda raw: raw, llm=llm, step_label="thử"))
    assert len(seen) == 1 and busy_sleeps == []
    assert "401" in info.value.user_message


def test_busy_inside_pipeline_step(isolated_projects_dir, busy_sleeps):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm({"EXTRACT 0": [_busy(30)]})
    result = _run(pipeline, "extract_00", llm)
    assert calls == ["EXTRACT 0", "EXTRACT 0"]
    assert busy_sleeps == [30]
    assert len(result.output["events"]) == 6


# ---------------------------------------------------------------- G2: đọc đoạn

def test_extract_lazy_output_retried_with_reason(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm({"EXTRACT 0": [LAZY_EXTRACT, load_fixture("EXTRACT 0")]})

    result = _run(pipeline, "extract_00", llm)

    assert calls == ["EXTRACT 0", "EXTRACT 0"]
    assert RETRY_MARK not in llm.prompts[0]
    assert RETRY_MARK in llm.prompts[1]
    assert "Có án mạng." in llm.prompts[1]            # lý do nêu đúng tóm tắt bị chê
    assert len(result.output["events"]) == 6
    assert result.new_steps == []
    assert llm.prompts[0].split("\n", 1)[0] == "TASK: EXTRACT 0"


def test_extract_fails_after_three_lazy_attempts(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm({"EXTRACT 0": LAZY_EXTRACT})
    with pytest.raises(StepFailed) as info:
        _run(pipeline, "extract_00", llm)
    assert calls == ["EXTRACT 0"] * MAX_ATTEMPTS
    assert "đọc đoạn 1" in info.value.user_message
    assert info.value.user_message.startswith(f"Bước đọc đoạn 1 thất bại sau {MAX_ATTEMPTS} lần:")


def test_extract_too_few_events_for_long_chunk_rejected(isolated_projects_dir):
    pipeline = _new_pipeline()
    long_chunk = " ".join(["Ông Hùng đi bộ dọc bờ biển vào lúc chiều muộn và nhìn về phía cảng."] * 50)  # 800 từ
    case_store.save_chunks(pipeline.case_id, [long_chunk, "đoạn hai"])
    one_event = copy.deepcopy(load_fixture("EXTRACT 0"))
    one_event["events"] = one_event["events"][:2]       # 800 từ cần ít nhất 4 sự việc
    llm, calls = make_fake_llm({"EXTRACT 0": [one_event, load_fixture("EXTRACT 0")]})
    _run(pipeline, "extract_00", llm)
    assert calls == ["EXTRACT 0", "EXTRACT 0"]
    assert RETRY_MARK in llm.prompts[1] and "sự việc" in llm.prompts[1].split(RETRY_MARK, 1)[1]


def test_extract_bad_schema_retried(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("EXTRACT 0"))
    bad["names"][0]["kind"] = "spaceship"
    llm, calls = make_fake_llm({"EXTRACT 0": [bad, load_fixture("EXTRACT 0")]})
    _run(pipeline, "extract_00", llm)
    assert calls == ["EXTRACT 0", "EXTRACT 0"]
    assert RETRY_MARK in llm.prompts[1] and "kind" in llm.prompts[1].split(RETRY_MARK, 1)[1]


def test_extract_name_missing_from_names_rejected(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("EXTRACT 0"))
    bad["names"] = [n for n in bad["names"] if n["name"] != "Lê Thị Mai"]
    llm, calls = make_fake_llm({"EXTRACT 0": [bad, load_fixture("EXTRACT 0")]})
    _run(pipeline, "extract_00", llm)
    assert calls == ["EXTRACT 0", "EXTRACT 0"]
    assert RETRY_MARK in llm.prompts[1] and "Lê Thị Mai" in llm.prompts[1].split(RETRY_MARK, 1)[1]


def test_extract_prompt_lists_the_same_generic_terms_code_skips():
    prompt = extract_prompt("Một đoạn ngắn.", 0, 1, [])
    for term in GENERIC_TERMS:
        assert f'"{term}"' in prompt, term
        assert is_kept_term(term) and is_kept_term(term.capitalize()) and is_kept_term(term, "person")
    assert is_kept_term("Việt Nam", "place") and not is_kept_term("Nga", "person")   # "Nga" cũng là tên người


def test_generic_terms_match_with_diacritics():
    # Tên thật bỏ dấu trùng một danh từ chung ("Gia Định" ~ "gia đình", "Hưng Thu" ~ "hung thủ") không được bỏ.
    assert not is_kept_term("Gia Định", "place") and not is_kept_term("Gia Định")
    assert not is_kept_term("Hưng Thu", "person") and not is_kept_term("Hùng Thu", "person")
    assert is_kept_term("gia đình") and is_kept_term("Gia đình") and is_kept_term("GIA  ĐÌNH", "person")
    assert is_kept_term("hung thủ") and is_kept_term("Hung thủ", "person")
    assert is_kept_term("Tòa án") and is_kept_term("Toà án nhân dân")          # hai cách đặt dấu đều là danh từ chung


def test_extract_keeps_real_names_that_fold_like_generic_terms(isolated_projects_dir):
    pipeline = _new_pipeline()
    first = copy.deepcopy(load_fixture("EXTRACT 0"))
    first["names"] += [
        {"name": "Gia Định", "kind": "place", "role": "other", "context": "Vùng nạn nhân từng sống."},
        {"name": "Hưng Thu", "kind": "person", "role": "witness", "context": "Người bảo vệ cảng."},
    ]
    first["events"][0]["names"] += ["Gia Định", "Hưng Thu"]
    llm, calls = make_fake_llm({"EXTRACT 0": first})
    result = _run(pipeline, "extract_00", llm)
    assert calls == ["EXTRACT 0"]
    names = [n["name"] for n in result.output["names"]]
    assert "Gia Định" in names and "Hưng Thu" in names
    assert {"Gia Định", "Hưng Thu"} <= set(result.output["events"][0]["names"])


def test_extract_generic_term_only_in_event_names_is_accepted(isolated_projects_dir):
    # Model làm đúng lời dặn: không đưa "Cơ quan điều tra" vào names, chỉ nhắc trong events → không bị loại.
    pipeline = _new_pipeline()
    second = copy.deepcopy(load_fixture("EXTRACT 1"))
    second["events"][0]["names"].append("Cơ quan điều tra")
    second["events"][3]["names"].append("Lực lượng chức năng")   # chữ hoa đầu câu, không có trong danh sách
    second["evidence"][0]["names"].append("Pháp y")
    llm, calls = make_fake_llm({"EXTRACT 1": second})
    _run(pipeline, "extract_00", llm)
    result = _run(pipeline, "extract_01", llm)
    assert calls == ["EXTRACT 0", "EXTRACT 1"]
    assert len(result.output["events"]) == 6


def test_extract_generic_terms_listed_in_names_are_dropped(isolated_projects_dir):
    # Model vẫn đưa danh từ chung vào names: code bỏ, để chúng không bị đặt tên hư cấu (spec mục 6).
    pipeline = _new_pipeline()
    first = copy.deepcopy(load_fixture("EXTRACT 0"))
    first["names"] += [
        {"name": "Cơ quan điều tra", "kind": "organization", "role": "other", "context": "Cơ quan thụ lý vụ án."},
        {"name": "Pháp y", "kind": "person", "role": "investigator", "context": "Người khám nghiệm tử thi."},
        {"name": "Nạn nhân", "kind": "person", "role": "victim", "context": "Người bị sát hại."},
        {"name": "Lực lượng chức năng", "kind": "organization", "role": "other", "context": "Lực lượng có mặt."},
        {"name": "Việt Nam", "kind": "place", "role": "other", "context": "Quốc gia nơi xảy ra vụ án."},
        {"name": "Nga", "kind": "person", "role": "witness", "context": "Hàng xóm tên Nga."},
    ]
    first["events"][0]["names"] += ["Cơ quan điều tra", "Việt Nam", "Nga"]
    llm, calls = make_fake_llm({"EXTRACT 0": first})

    result = _run(pipeline, "extract_00", llm)

    assert calls == ["EXTRACT 0"]
    names = [n["name"] for n in result.output["names"]]
    assert not {"Cơ quan điều tra", "Pháp y", "Nạn nhân", "Lực lượng chức năng", "Việt Nam"} & set(names)
    assert "Nga" in names                                  # người tên "Nga" vẫn được giữ để đặt tên hư cấu
    assert "Nguyễn Văn Hùng" in names and "bà Mai" in names


def test_extract_keeps_person_nickname(isolated_projects_dir):
    # Biệt danh chỉ viết hoa chữ đầu vẫn là tên người: bỏ đi thì không có tên hư cấu và lọt tên thật.
    pipeline = _new_pipeline()
    first = copy.deepcopy(load_fixture("EXTRACT 0"))
    first["names"].append({"name": "Hùng sẹo", "kind": "person", "role": "suspect", "context": "Biệt danh của một người."})
    first["events"][1]["names"].append("Hùng sẹo")
    llm, calls = make_fake_llm({"EXTRACT 0": first})
    result = _run(pipeline, "extract_00", llm)
    assert calls == ["EXTRACT 0"]
    assert "Hùng sẹo" in [n["name"] for n in result.output["names"]]
    assert "Hùng sẹo" in result.output["events"][1]["names"]


def test_extract_nickname_missing_from_names_rejected(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("EXTRACT 0"))
    bad["events"][2]["names"].append("Sáu lùn")                       # có trong sự việc, thiếu trong names
    llm, calls = make_fake_llm({"EXTRACT 0": [bad, load_fixture("EXTRACT 0")]})
    _run(pipeline, "extract_00", llm)
    assert calls == ["EXTRACT 0", "EXTRACT 0"]
    reason = llm.prompts[1].split(RETRY_MARK, 1)[1]
    assert "thiếu trong names" in reason and "Sáu lùn" in reason


@pytest.mark.parametrize("phrase, kind", [
    ("Cảnh sát giao thông", "organization"), ("Trường tiểu học", "place"), ("Bệnh viện đa khoa", "organization"),
])
def test_extract_listed_generic_phrase_accepted_without_alias(isolated_projects_dir, phrase, kind):
    # Model liệt kê cụm chung vào names và nhắc trong sự việc: nhận ngay, cụm đó không thành tên cần đặt alias.
    pipeline = _new_pipeline()
    first = copy.deepcopy(load_fixture("EXTRACT 0"))
    first["names"].append({"name": phrase, "kind": kind, "role": "other", "context": "Có mặt ở hiện trường."})
    first["events"][0]["names"].append(phrase)
    llm, calls = make_fake_llm({"EXTRACT 0": first})

    result = _run_until(pipeline, "cluster", llm)

    assert calls == ["EXTRACT 0", "EXTRACT 1", "CLUSTER"]
    assert phrase not in [n["name"] for n in case_store.load_step_output(pipeline.case_id, "extract_00")["names"]]
    assert f'"{phrase}"' not in llm.prompts[-1]               # không có trong danh sách gửi đi gộp tên
    assert phrase not in [n for g in result.output["groups"] for n in g["real_names"]]


@pytest.mark.parametrize("phrase", ["Cảnh sát giao thông", "Gia đình", "Phòng cháy chữa cháy"])
def test_extract_event_only_generic_phrase_accepted(isolated_projects_dir, phrase):
    pipeline = _new_pipeline()
    first = copy.deepcopy(load_fixture("EXTRACT 0"))
    first["events"][0]["names"].append(phrase)
    llm, calls = make_fake_llm({"EXTRACT 0": first})
    _run(pipeline, "extract_00", llm)
    assert calls == ["EXTRACT 0"]


def test_listing_missing_name_on_retry_clears_rejection(isolated_projects_dir):
    # Cụm không có trong GENERIC_TERMS, chỉ nhắc trong sự việc: bị đòi thêm vào names. Model thêm (kind bất kỳ)
    # là qua, dù bước lọc vẫn bỏ cụm đó khỏi danh sách tên; không thành vòng loại đi loại lại.
    phrase = "Đội phản ứng nhanh"
    assert not is_kept_term(phrase)
    pipeline = _new_pipeline()
    attempt1 = copy.deepcopy(load_fixture("EXTRACT 0"))
    attempt1["events"][0]["names"].append(phrase)
    attempt2 = copy.deepcopy(attempt1)
    attempt2["names"].append({"name": phrase, "kind": "organization", "role": "other", "context": "Đội tới hiện trường."})
    llm, calls = make_fake_llm({"EXTRACT 0": [attempt1, attempt2, LAZY_EXTRACT]})

    result = _run(pipeline, "extract_00", llm)

    assert calls == ["EXTRACT 0", "EXTRACT 0"]
    assert phrase in llm.prompts[1].split(RETRY_MARK, 1)[1]
    assert phrase not in [n["name"] for n in result.output["names"]]


def test_extract_second_chunk_gets_known_names(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm()
    _run(pipeline, "extract_00", llm)
    _run(pipeline, "extract_01", llm)
    assert calls == ["EXTRACT 0", "EXTRACT 1"]
    first_prompt, second_prompt = llm.prompts
    assert "Nguyễn Văn Hùng" in second_prompt and "Cảng Tân Hải" in second_prompt
    assert "Vũ Đình Trọng" in second_prompt          # chính văn bản đoạn 2
    assert "Vũ Đình Trọng" not in first_prompt       # đoạn 1 không chứa đoạn 2


def test_no_credentials_not_retried(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm({"EXTRACT 0": LLMError("no_credentials", "9router chưa có tài khoản Gemini đang hoạt động.")})
    with pytest.raises(StepFailed) as info:
        _run(pipeline, "extract_00", llm)
    assert calls.count("EXTRACT 0") == 1
    assert "đọc đoạn 1" in info.value.user_message
    assert "9router chưa có tài khoản Gemini" in info.value.user_message


def test_run_step_resolves_llm_at_call_time(isolated_projects_dir, monkeypatch):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm()
    monkeypatch.setattr(case_adaptation_llm, "call_llm_json", llm)
    result = asyncio.run(run_step(pipeline, _step(pipeline, "extract_00")))
    assert calls == ["EXTRACT 0"]
    assert len(result.output["events"]) == 6


# ---------------------------------------------------------------- G3: gộp tên

def test_cluster_rejects_missing_name(isolated_projects_dir):
    pipeline = _new_pipeline()
    missing = copy.deepcopy(load_fixture("CLUSTER"))
    for group in missing["groups"]:
        group["real_names"] = [n for n in group["real_names"] if n != "bà Mai"]
    llm, calls = make_fake_llm({"CLUSTER": [missing, load_fixture("CLUSTER")]})

    result = _run_until(pipeline, "cluster", llm)

    assert calls.count("CLUSTER") == 2
    reason = llm.prompts[-1].split(RETRY_MARK, 1)[1]
    assert "bà Mai" in reason
    names = [n for g in result.output["groups"] for n in g["real_names"]]
    assert "bà Mai" in names and len(names) == len(set(names))


def test_cluster_rejects_name_in_two_groups(isolated_projects_dir):
    pipeline = _new_pipeline()
    doubled = copy.deepcopy(load_fixture("CLUSTER"))
    doubled["groups"][0]["real_names"].append("bà Mai")     # bà Mai vừa ở nhóm Hùng vừa ở nhóm Mai
    llm, calls = make_fake_llm({"CLUSTER": [doubled, load_fixture("CLUSTER")]})
    _run_until(pipeline, "cluster", llm)
    assert calls.count("CLUSTER") == 2
    assert "bà Mai" in llm.prompts[-1].split(RETRY_MARK, 1)[1]


def test_cluster_input_has_every_distinct_name_once(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, _calls = make_fake_llm()
    result = _run_until(pipeline, "cluster", llm)
    prompt = llm.prompts[-1]
    assert prompt.split("\n", 1)[0] == "TASK: CLUSTER"
    for name in ["Nguyễn Văn Hùng", "ông Hùng", "Lê Thị Mai", "bà Mai", "Vũ Đình Trọng", "ông Trọng",
                 "Cảng Tân Hải", "Đường Lê Lợi", "Hải Phòng", "Công ty Vận tải Biển Đông", "15B1-987.65", "0912345678"]:
        assert f'"{name}"' in prompt, name
    assert prompt.count('"bà Mai"') == 1                 # có ở cả hai đoạn nhưng chỉ gửi một lần
    ids = [g["id"] for g in result.output["groups"]]
    assert len(ids) == len(set(ids)) == 9


# ---------------------------------------------------------------- G4: đặt tên hư cấu → hồ sơ

def test_aliases_builds_bible(isolated_projects_dir):
    pipeline = _new_pipeline()
    llm, calls = make_fake_llm()

    result = _run_until(pipeline, "aliases", llm)

    assert calls == ["EXTRACT 0", "EXTRACT 1", "CLUSTER", "ALIASES"]
    bible = CaseBible.model_validate(result.output)
    entity_ids = {e.id for e in bible.entities}
    assert len(bible.entities) == 9
    assert bible.source_language == "vi" and bible.culture == "vietnamese" and bible.solved is False
    assert "Hùng" not in bible.title_vi

    # sự việc: id ev_<đoạn>_<n>, thứ tự theo (đoạn, vị trí), entity_ids trỏ tới entity có thật
    assert [e.id for e in bible.timeline][:2] == ["ev_0_1", "ev_0_2"]
    assert bible.timeline[6].id == "ev_1_1" and bible.timeline[6].chunk_index == 1
    assert [e.order for e in bible.timeline] == list(range(1, 13))
    for event in bible.timeline:
        assert set(event.entity_ids) <= entity_ids
    assert any(event.entity_ids for event in bible.timeline)
    by_id = {e.id: e for e in bible.timeline}
    assert by_id["ev_1_2"].entity_ids == ["person_3", "person_1"]     # "ông Trọng", "ông Hùng"

    # bằng chứng và quan hệ: ánh xạ bằng fold; quan hệ không ánh xạ được thì bỏ, trùng thì gộp
    for ev in bible.evidence:
        assert set(ev.entity_ids) <= entity_ids
    assert len(bible.evidence) == 8
    pairs = [(r.source_id, r.target_id, r.relation_type) for r in bible.relations]
    assert ("person_2", "person_1", "witness_seen") in pairs
    assert pairs.count(("person_3", "person_1", "motive")) == 1
    assert ("person_3", "person_1", "alibi_contradiction") in pairs
    assert len(pairs) == 4
    for rel in bible.relations:
        assert rel.source_id in entity_ids and rel.target_id in entity_ids
    assert len({r.id for r in bible.relations}) == len(bible.relations)

    hung = next(e for e in bible.entities if e.id == "person_1")
    assert hung.real_names == ["Nguyễn Văn Hùng", "ông Hùng"]
    assert hung.alias_vi == "Trịnh Quang Vũ" and hung.alias_en == "Trinh Quang Vu"
    assert hung.role == "victim" and hung.appearance_en


def test_evidence_merged_only_when_label_and_description_match(isolated_projects_dir):
    pipeline = _new_pipeline()
    first = load_fixture("EXTRACT 0")
    wound, call = first["evidence"][0], first["evidence"][1]
    other_call = "Cuộc gọi thứ hai, từ một số lạ, báo tin có người lạ ở cổng cảng trước khi án mạng xảy ra."
    second = copy.deepcopy(load_fixture("EXTRACT 1"))
    second["evidence"] += [
        {**call, "description_vi": other_call, "description_en": "A second call from an unknown number.",
         "names": ["ông Trọng"]},                                    # cùng nhãn, khác mô tả: bằng chứng khác
        {**wound, "label_vi": wound["label_vi"].upper(), "names": ["ông Hùng", "bà Mai"]},   # trùng hẳn: gộp
    ]
    llm, _calls = make_fake_llm({"EXTRACT 1": second})

    bible = CaseBible.model_validate(_run_until(pipeline, "aliases", llm).output)

    assert len(bible.evidence) == 9                          # 4 + 4 + 1 cuộc gọi khác; vết thương trùng được gộp
    calls_found = [e for e in bible.evidence if e.label_vi == call["label_vi"]]
    assert len(calls_found) == 2 and calls_found[0].id != calls_found[1].id
    assert {e.description_vi for e in calls_found} == {call["description_vi"], other_call}
    assert calls_found[1].entity_ids == ["person_3"]
    wounds = [e for e in bible.evidence if fold(e.label_vi) == fold(wound["label_vi"])]
    assert len(wounds) == 1 and wounds[0].entity_ids == ["person_1", "person_2"]
    assert len({e.id for e in bible.evidence}) == len(bible.evidence)


@pytest.mark.parametrize("entity_id", ["person_2", "person_1"])   # alias trùng tên thật của chính nó / của người khác
def test_aliases_rejects_alias_equal_real_name(isolated_projects_dir, entity_id):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("ALIASES"))
    next(e for e in bad["entities"] if e["id"] == entity_id)["alias_vi"] = "Lê Thị Mai"
    llm, calls = make_fake_llm({"ALIASES": [bad, load_fixture("ALIASES")]})

    result = _run_until(pipeline, "aliases", llm)

    assert calls.count("ALIASES") == 2
    assert "Lê Thị Mai" in llm.prompts[-1].split(RETRY_MARK, 1)[1]
    aliases = {e["alias_vi"] for e in result.output["entities"]}
    assert "Lê Thị Mai" not in aliases


def test_aliases_rejects_unaccented_real_name_and_duplicates(isolated_projects_dir):
    pipeline = _new_pipeline()
    unaccented = copy.deepcopy(load_fixture("ALIASES"))
    unaccented["entities"][2]["alias_en"] = "VU DINH TRONG"          # bỏ dấu, viết hoa: vẫn là tên thật
    duplicate = copy.deepcopy(load_fixture("ALIASES"))
    duplicate["entities"][1]["alias_vi"] = "Trịnh Quang Vũ"          # trùng alias của person_1
    empty = copy.deepcopy(load_fixture("ALIASES"))
    empty["entities"][3]["alias_en"] = "  "
    llm, calls = make_fake_llm({"ALIASES": [unaccented, duplicate, empty]})

    with pytest.raises(StepFailed) as info:
        _run_until(pipeline, "aliases", llm)

    assert calls.count("ALIASES") == MAX_ATTEMPTS
    assert "VU DINH TRONG" in llm.prompts[-2].split(RETRY_MARK, 1)[1]
    assert "Trịnh Quang Vũ" in llm.prompts[-1].split(RETRY_MARK, 1)[1]
    assert info.value.user_message.startswith("Bước đặt tên hư cấu thất bại sau")
    assert "place_1" in info.value.user_message


def test_aliases_rejects_person_alias_keeping_real_given_name(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("ALIASES"))
    bad["entities"][0]["alias_vi"] = "Phạm Văn Hùng"                 # người thật là Nguyễn Văn Hùng
    llm, calls = make_fake_llm({"ALIASES": [bad, load_fixture("ALIASES")]})
    _run_until(pipeline, "aliases", llm)
    assert calls.count("ALIASES") == 2
    assert "Phạm Văn Hùng" in llm.prompts[-1].split(RETRY_MARK, 1)[1]


def test_aliases_rejects_real_name_in_title(isolated_projects_dir):
    pipeline = _new_pipeline()
    bad = copy.deepcopy(load_fixture("ALIASES"))
    bad["title_vi"] = "Kỳ án Cảng Tân Hải"
    llm, calls = make_fake_llm({"ALIASES": [bad, load_fixture("ALIASES")]})
    result = _run_until(pipeline, "aliases", llm)
    assert calls.count("ALIASES") == 2
    assert "Cảng Tân Hải" in llm.prompts[-1].split(RETRY_MARK, 1)[1]
    assert result.output["title_vi"] == load_fixture("ALIASES")["title_vi"]


def test_aliases_prompt_has_groups_and_only_opening_excerpt(isolated_projects_dir):
    pipeline = _new_pipeline()
    tail = "ĐOẠN CUỐI KHÔNG ĐƯỢC GỬI CHO VIỆC ĐẶT TÊN."
    base = DOSSIER.replace("\r\n", "\n").strip()        # git trên Windows có thể đổi file sang CRLF
    long_source = base + "\n\n" + "Thêm chi tiết điều tra. " * 60 + "\n\n" + tail
    assert len(long_source) > 1500 + len(tail)
    case_store.save_source(pipeline.case_id, long_source)
    llm, _calls = make_fake_llm()

    _run_until(pipeline, "aliases", llm)

    prompt = llm.prompts[-1]
    assert prompt.split("\n", 1)[0] == "TASK: ALIASES"
    assert "person_2" in prompt and '"bà Mai"' in prompt
    assert long_source[:1500] in prompt                  # đúng 1.500 ký tự đầu bài
    assert tail not in prompt
