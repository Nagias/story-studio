"""LLM giả cho services/story_review.py: trả lời 3 việc liet_ke_y / viet_review / kiem_loi_ke đúng khuôn, không gọi mạng.

Ý = các câu của đoạn gốc gom lại cho đủ số ý tối thiểu; lời review tiếng Việt = chính ý đó (đủ dài để qua ngưỡng số từ);
tiếng Anh = câu tiếng Anh dựng sẵn. Bản kiểm trích nguyên văn đầu câu của cảnh kể ý đó.
`broken` chọn kiểu hỏng để test đường lỗi."""
from __future__ import annotations

import re
from typing import Any, Optional

from services import story_review

_POINT = re.compile(r"^- (p\d+): (.*)$", re.M)
_SCENE = re.compile(r"^\[cảnh (\d+)\] (.*)$", re.M)
_EN_FILL = ("Then the story moves forward as the hero faces this moment with growing fear, hope and quiet resolve "
            "while everyone around waits")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", " ".join(text.split())) if s.strip()]


def _part_of(prompt: str) -> str:
    return prompt.split("ĐOẠN TRUYỆN:\n", 1)[1].rsplit("\n\nTrả:", 1)[0]


class FakeStoryLLM:
    def __init__(self, broken: Optional[str] = None):
        self.broken = broken           # None | "skip_point" | "fake_quote" | "always_missing" | "first_person"
        self.calls: list[str] = []
        self.prompts: list[str] = []
        self._written: dict[str, list[int]] = {}

    async def __call__(self, _system: str, user: str, **_kw: Any) -> Any:
        task = user.split("\n", 1)[0].split()[1]
        self.calls.append(task)
        self.prompts.append(user)
        return getattr(self, task)(user)

    def liet_ke_y(self, prompt: str) -> dict:
        part = _part_of(prompt)
        need = story_review.min_points(part)
        sents = _sentences(part)
        groups = [[] for _ in range(min(need, len(sents)) or 1)]
        for i, s in enumerate(sents):
            groups[i * len(groups) // len(sents)].append(s)
        points = [" ".join(g) for g in groups if g]
        while len(points) < need:          # đoạn ít câu: tách đôi ý dài nhất
            longest = max(points, key=len)
            words = longest.split()
            half = len(words) // 2
            points[points.index(longest):points.index(longest) + 1] = [" ".join(words[:half]), " ".join(words[half:])]
        return {"points": points}

    def viet_review(self, prompt: str) -> dict:
        lang = "en" if "TIẾNG ANH" in prompt.split("\n", 3)[2] else "vi"
        lo, hi = story_review.SCENE_WORDS[lang]
        points = _POINT.findall(prompt.split("CÁC Ý PHẢI KỂ", 1)[1])
        scenes = []
        for n, (pid, text) in enumerate(points):
            if self.broken == "skip_point" and n == 0 and "LẦN TRƯỚC BỊ LOẠI" not in prompt:
                continue
            words = text.split() if lang == "vi" else (_EN_FILL + f" in part {pid}.").split()
            want = max(len(words), 30) if lang == "en" else len(words)
            if lang == "en":
                words = (words * 4)[:want]
            chunks = [words[i:i + hi] for i in range(0, len(words), hi)] or [["..."]]
            for chunk in chunks:
                while len(chunk) < lo:
                    chunk = chunk + (["rồi", "câu", "chuyện", "tiếp", "diễn"] if lang == "vi" else ["and", "then", "it", "goes", "on"])
                body = " ".join(chunk[:hi])
                if self.broken == "first_person" and lang == "vi":
                    body = "Tôi thấy " + body
                scenes.append({"text": body, "covers": [pid], "image_prompt": f"Cinematic shot for {pid}",
                               "narrative_beat": "setting", "camera_motion": "zoom_in"})
        return {"scenes": scenes}

    def kiem_loi_ke(self, prompt: str) -> dict:
        point_pairs = _POINT.findall(prompt.split("CÁC Ý PHẢI CÓ", 1)[1].split("BẢNG SỰ THẬT", 1)[0])
        points = [pid for pid, _ in point_pairs]
        scenes = _SCENE.findall(prompt.split("LỜI KỂ CẦN KIỂM:", 1)[1])
        quotes = []
        for pid, ptext in point_pairs:
            if self.broken == "always_missing" and pid == "p1":
                continue
            # cảnh kể ý: cảnh có chữ "part pX" (tiếng Anh) hoặc chứa đầu câu của ý (tiếng Việt)
            head = " ".join(ptext.split()[:5])
            idx = next((int(k) for k, t in scenes if f"part {pid}" in t or head in t), None)
            if idx is None:
                continue
            text = dict(scenes)[str(idx)]
            quote = " ".join(text.split()[:8])
            if self.broken == "fake_quote" and pid == "p1" and self.calls.count("kiem_loi_ke") == 1:
                quote = "câu này không hề có trong lời kể đâu nhé"
            quotes.append({"point_id": pid, "scene": idx, "quote": quote})
        return {"quotes": quotes, "issues": [], "facts": [f"sự thật của {p}" for p in points[:2]]}


_SCENE_ID = re.compile(r"^- id (\S+) \(cảnh #\d+\)", re.M)


class FakePeopleLLM:
    """LLM giả cho services/story_cast.py (TASK: PEOPLE): một nhân vật chính có mặt ở mọi cảnh, một người phụ ở cảnh
    đầu. `broken="short_look"`: ngoại hình quá ngắn ở lần trả lời đầu (code phải bắt viết lại)."""

    LOOK = ("A slender young East Asian man in his early twenties with short messy black hair, thin rectangular "
            "glasses, a pale tired face, a faded grey hoodie over a white shirt and dark jeans")

    def __init__(self, broken: Optional[str] = None):
        self.broken = broken
        self.calls: list[str] = []

    async def __call__(self, _system: str, user: str, **_kw: Any) -> Any:
        self.calls.append(user)
        ids = _SCENE_ID.findall(user)
        look = "young man" if self.broken == "short_look" and len(self.calls) == 1 else self.LOOK
        return {"people": [
            {"name": "Lý Minh Hạ", "gender": "male", "age_range": "early 20s", "role": "main",
             "appearance_en": look, "scene_ids": ids},
            {"name": "Giáo sư Trần", "gender": "female", "age_range": "about 60", "role": "supporting",
             "appearance_en": "An elderly East Asian woman about sixty with silver hair tied in a low bun, round wire "
                              "glasses, a long dark green wool coat and a grey scarf", "scene_ids": ids[:1]},
        ]}
