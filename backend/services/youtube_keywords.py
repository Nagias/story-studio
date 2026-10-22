"""Từ khoá cho gói SEO YouTube, lấy từ dữ liệu thật (không để AI tự nghĩ từ khoá).

Nguồn (người dùng bấm "Tìm từ khoá" mới gọi, không tự chạy nền):
- youtube_suggest: gợi ý của ô tìm kiếm YouTube (không cần key). Đây là đường không chính thức: điều khoản YouTube
  cấm truy cập tự động, nên chỉ gọi một lần mỗi lần bấm và không đóng gói cho khách khi chưa xem xét pháp lý.
- youtube_data_api: YouTube Data API v3 (cần YOUTUBE_API_KEY, miễn phí): 10 video đứng đầu tìm kiếm và tags của chúng.
  search.list có hạn mức riêng khoảng 100 lần mỗi ngày; videos.list tốn 1 đơn vị.
- manual: từ khoá người dùng dán tay (ví dụ từ tab Nghiên cứu của YouTube Studio).

Theo chính sách nhà phát triển của YouTube, dữ liệu lấy từ API chỉ giữ tối đa 30 ngày (xem `is_expired`) và chỉ hiện
dữ liệu thô (đếm số video có tag), không tự chấm điểm.
"""
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

import httpx

import config
from models.youtube_seo import KeywordCandidate, KeywordResearch, TopVideo

logger = logging.getLogger(__name__)

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
DATA_API_URL = "https://www.googleapis.com/youtube/v3"
REGION = {"vi": ("vi", "VN"), "en": ("en", "US")}
RESEARCH_TTL = timedelta(days=30)
TOP_VIDEOS = 10
TOP_TAGS_SHOWN = 30
TIMEOUT_S = 20.0
SOURCES = ("youtube_suggest", "youtube_data_api")


class KeywordSourceError(Exception):
    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


def is_expired(research: Optional[KeywordResearch], now: Optional[datetime] = None) -> bool:
    if research is None:
        return True
    fetched = research.fetched_at if research.fetched_at.tzinfo else research.fetched_at.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - fetched > RESEARCH_TTL


def _redact(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


async def fetch_suggestions(seed: str, language: str, *, client: httpx.AsyncClient) -> list[str]:
    hl, gl = REGION[language]
    params = {"client": "firefox", "ds": "yt", "q": seed, "hl": hl, "gl": gl}
    try:
        response = await client.get(SUGGEST_URL, params=params, timeout=TIMEOUT_S)
    except httpx.HTTPError as exc:
        raise KeywordSourceError(f"Không lấy được gợi ý tìm kiếm của YouTube (lỗi mạng: {type(exc).__name__}).") from None
    if response.status_code != 200:
        raise KeywordSourceError(f"Gợi ý tìm kiếm của YouTube trả lỗi HTTP {response.status_code}.")
    try:
        data = response.json()
        suggestions = [s.strip() for s in data[1] if isinstance(s, str) and s.strip()]
    except (ValueError, IndexError, TypeError, KeyError):
        raise KeywordSourceError("Gợi ý tìm kiếm của YouTube trả về dữ liệu không đọc được (có thể YouTube đã đổi cách trả).") from None
    return suggestions


def _data_api_error(response: httpx.Response, key: str) -> KeywordSourceError:
    try:
        reasons = {e.get("reason") for e in response.json()["error"].get("errors", [])}
    except (ValueError, KeyError, TypeError, AttributeError):
        reasons = set()
    if reasons & {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}:
        return KeywordSourceError("Hết hạn mức YouTube Data API hôm nay (khoảng 100 lần tìm mỗi ngày). Thử lại ngày mai.")
    if reasons & {"keyInvalid", "badRequest"} and response.status_code == 400:
        return KeywordSourceError("YOUTUBE_API_KEY trong file .env không hợp lệ. Kiểm tra lại key trong Google Cloud.")
    if "accessNotConfigured" in reasons or response.status_code == 403:
        return KeywordSourceError("Key chưa được phép gọi YouTube Data API v3: bật API này trong project Google Cloud của key.")
    return KeywordSourceError(_redact(f"YouTube Data API trả lỗi HTTP {response.status_code}.", key))


async def fetch_top_videos(seed: str, language: str, *, client: httpx.AsyncClient, api_key: str) -> list[TopVideo]:
    hl, gl = REGION[language]
    search_params = {"part": "snippet", "type": "video", "maxResults": TOP_VIDEOS, "q": seed, "regionCode": gl,
                     "relevanceLanguage": hl, "key": api_key}
    try:
        found = await client.get(f"{DATA_API_URL}/search", params=search_params, timeout=TIMEOUT_S)
        if found.status_code != 200:
            raise _data_api_error(found, api_key)
        ids = [item["id"]["videoId"] for item in found.json().get("items", []) if item.get("id", {}).get("videoId")]
        if not ids:
            return []
        detail = await client.get(f"{DATA_API_URL}/videos",
                                  params={"part": "snippet", "id": ",".join(ids), "key": api_key}, timeout=TIMEOUT_S)
        if detail.status_code != 200:
            raise _data_api_error(detail, api_key)
        items = detail.json().get("items", [])
    except httpx.HTTPError as exc:
        raise KeywordSourceError(f"Không gọi được YouTube Data API (lỗi mạng: {type(exc).__name__}).") from None
    except (ValueError, KeyError, TypeError):
        raise KeywordSourceError("YouTube Data API trả về dữ liệu không đọc được.") from None
    by_id = {item.get("id"): item.get("snippet", {}) for item in items}
    return [TopVideo(video_id=vid, title=by_id[vid].get("title", ""), channel=by_id[vid].get("channelTitle", ""),
                     tags=[t for t in by_id[vid].get("tags", []) if isinstance(t, str)])
            for vid in ids if vid in by_id]


def tag_counts(videos: Sequence[TopVideo]) -> list[tuple[str, int]]:
    """Tag và số video (trong danh sách) có tag đó; không phân biệt hoa thường, giữ cách viết gặp đầu tiên."""
    counts, spelling = Counter(), {}
    for video in videos:
        for tag in {t.strip().casefold(): t.strip() for t in video.tags if t.strip()}.items():
            counts[tag[0]] += 1
            spelling.setdefault(tag[0], tag[1])
    return [(spelling[k], n) for k, n in counts.most_common()]


def _clean_manual(manual: Sequence[str]) -> list[str]:
    seen, out = set(), []
    for line in manual:
        for part in str(line).replace("\n", ",").split(","):
            kw = " ".join(part.split())
            if kw and kw.casefold() not in seen:
                seen.add(kw.casefold())
                out.append(kw)
    return out


async def research(seed: str, language: str, sources: Sequence[str], manual: Sequence[str] = (), *,
                   client: Optional[httpx.AsyncClient] = None) -> KeywordResearch:
    """Gọi các nguồn được chọn; nguồn lỗi thì ghi lý do vào `errors` và đi tiếp. Không có từ khoá nào thì báo lỗi."""
    seed = " ".join((seed or "").split())
    if not seed and not manual:
        raise KeywordSourceError("Nhập từ khoá gốc (ví dụ tên truyện, chủ đề) hoặc dán từ khoá tay.")
    if language not in REGION:
        raise KeywordSourceError(f"Ngôn ngữ {language!r} chưa hỗ trợ (chỉ vi, en).")
    unknown = [s for s in sources if s not in SOURCES]
    if unknown:
        raise KeywordSourceError(f"Nguồn từ khoá không có: {', '.join(unknown)}")

    result = KeywordResearch(seed=seed, language=language, fetched_at=datetime.now(timezone.utc))
    seen: set[str] = set()

    def add(keyword: str, source: str, evidence: str) -> None:
        if keyword.casefold() not in seen:
            seen.add(keyword.casefold())
            result.candidates.append(KeywordCandidate(keyword=keyword, source=source, evidence=evidence))

    for kw in _clean_manual(manual):
        add(kw, "manual", "bạn dán tay")

    own_client = client is None
    http = httpx.AsyncClient() if own_client else client
    try:
        if seed and "youtube_suggest" in sources:
            try:
                for i, kw in enumerate(await fetch_suggestions(seed, language, client=http), 1):
                    add(kw, "youtube_suggest", f"gợi ý số {i} của ô tìm kiếm YouTube cho \"{seed}\"")
            except KeywordSourceError as exc:
                result.errors.append(exc.user_message)
        if seed and "youtube_data_api" in sources:
            api_key = (config.YOUTUBE_API_KEY or "").strip()
            if not api_key:
                result.errors.append("Chưa có YOUTUBE_API_KEY trong file .env nên chưa xem được video đứng đầu tìm kiếm.")
            else:
                try:
                    result.top_videos = await fetch_top_videos(seed, language, client=http, api_key=api_key)
                    total = len(result.top_videos)
                    for tag, n in tag_counts(result.top_videos)[:TOP_TAGS_SHOWN]:
                        add(tag, "youtube_data_api", f"có trong tags của {n}/{total} video đứng đầu tìm kiếm")
                except KeywordSourceError as exc:
                    result.errors.append(exc.user_message)
    finally:
        if own_client:
            await http.aclose()

    if not result.candidates:
        reasons = " ".join(result.errors) or "Các nguồn không trả về từ khoá nào cho từ khoá gốc này."
        raise KeywordSourceError(f"Không có từ khoá nào. {reasons}")
    return result
