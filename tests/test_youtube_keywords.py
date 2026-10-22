"""Từ khoá thật cho gói SEO (services/youtube_keywords.py), gọi mạng giả bằng httpx.MockTransport."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import config
from models.youtube_seo import KeywordResearch
from services import youtube_keywords as kw

SECRET = "AIza-test-key-123"


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _suggest_ok(request: httpx.Request) -> httpx.Response:
    q = request.url.params["q"]
    return httpx.Response(200, json=[q, [f"{q} full", f"{q} review", f"{q} tập 1"]])


@pytest.mark.asyncio
async def test_suggestions_use_language_region_and_keep_vietnamese():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return _suggest_ok(request)

    async with _client(handler) as client:
        out = await kw.fetch_suggestions("rừng sương mù", "vi", client=client)
    assert out == ["rừng sương mù full", "rừng sương mù review", "rừng sương mù tập 1"]
    assert (seen["hl"], seen["gl"], seen["ds"]) == ("vi", "VN", "yt")


@pytest.mark.asyncio
async def test_suggestion_errors_become_plain_messages():
    async with _client(lambda r: httpx.Response(503)) as client:
        with pytest.raises(kw.KeywordSourceError, match="HTTP 503"):
            await kw.fetch_suggestions("x", "en", client=client)

    def boom(request):
        raise httpx.ConnectError("no route")

    async with _client(boom) as client:
        with pytest.raises(kw.KeywordSourceError, match="lỗi mạng"):
            await kw.fetch_suggestions("x", "en", client=client)


def _data_api(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/search"):
        return httpx.Response(200, json={"items": [{"id": {"videoId": "v1"}}, {"id": {"videoId": "v2"}}]})
    return httpx.Response(200, json={"items": [
        {"id": "v1", "snippet": {"title": "Video 1", "channelTitle": "Kênh A", "tags": ["truyện ma", "Rừng Sâu"]}},
        {"id": "v2", "snippet": {"title": "Video 2", "channelTitle": "Kênh B", "tags": ["rừng sâu"]}},
    ]})


@pytest.mark.asyncio
async def test_top_videos_and_tag_counts_keep_raw_evidence():
    async with _client(_data_api) as client:
        videos = await kw.fetch_top_videos("rừng", "vi", client=client, api_key=SECRET)
    assert [v.video_id for v in videos] == ["v1", "v2"]
    assert kw.tag_counts(videos) == [("Rừng Sâu", 2), ("truyện ma", 1)]


@pytest.mark.parametrize("status,reason,expect", [
    (403, "quotaExceeded", "Hết hạn mức"),
    (400, "keyInvalid", "không hợp lệ"),
    (403, "accessNotConfigured", "bật API"),
])
@pytest.mark.asyncio
async def test_data_api_errors_are_plain_and_never_leak_the_key(status, reason, expect):
    body = {"error": {"errors": [{"reason": reason}], "message": f"bad key {SECRET}"}}
    async with _client(lambda r: httpx.Response(status, content=json.dumps(body))) as client:
        with pytest.raises(kw.KeywordSourceError) as exc:
            await kw.fetch_top_videos("rừng", "vi", client=client, api_key=SECRET)
    assert expect in exc.value.user_message
    assert SECRET not in exc.value.user_message


@pytest.mark.asyncio
async def test_research_combines_sources_and_records_errors(monkeypatch):
    monkeypatch.setattr(config, "YOUTUBE_API_KEY", "")

    async with _client(_suggest_ok) as client:
        result = await kw.research("rừng", "vi", ["youtube_suggest", "youtube_data_api"], ["Truyện ma, rừng"], client=client)
    words = [(c.keyword, c.source) for c in result.candidates]
    assert words[:2] == [("Truyện ma", "manual"), ("rừng", "manual")]
    assert ("rừng full", "youtube_suggest") in words
    assert any("YOUTUBE_API_KEY" in e for e in result.errors)


@pytest.mark.asyncio
async def test_research_with_api_key_adds_tags_from_top_videos(monkeypatch):
    monkeypatch.setattr(config, "YOUTUBE_API_KEY", SECRET)
    async with _client(_data_api) as client:
        result = await kw.research("rừng", "en", ["youtube_data_api"], client=client)
    assert result.top_videos and result.candidates[0].keyword == "Rừng Sâu"
    assert "2/2" in result.candidates[0].evidence


@pytest.mark.asyncio
async def test_research_without_any_keyword_fails_loudly():
    async with _client(lambda r: httpx.Response(500)) as client:
        with pytest.raises(kw.KeywordSourceError, match="Không có từ khoá nào"):
            await kw.research("rừng", "vi", ["youtube_suggest"], client=client)
    with pytest.raises(kw.KeywordSourceError):
        await kw.research("", "vi", ["youtube_suggest"])
    with pytest.raises(kw.KeywordSourceError):
        await kw.research("rừng", "fr", ["youtube_suggest"])


def test_research_older_than_30_days_expires():
    now = datetime.now(timezone.utc)
    fresh = KeywordResearch(seed="x", language="vi", fetched_at=now - timedelta(days=29))
    old = KeywordResearch(seed="x", language="vi", fetched_at=now - timedelta(days=31))
    assert not kw.is_expired(fresh, now)
    assert kw.is_expired(old, now)
    assert kw.is_expired(None, now)
