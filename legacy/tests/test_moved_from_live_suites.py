"""Test của code đã chuyển vào legacy/ ngày 18/11/2026 (bộ chia cảnh đời cũ, storyboard 9-grid, nhánh text của
produce-long-video). Giữ làm kỷ niệm: pytest không quét thư mục legacy/ (pytest.ini testpaths = tests)."""

# ---- chuyển từ tests/test_adversarial_qa.py ----
def test_adversarial_vox_pacing_and_hook():
    """
    Adversarial QA Test for Vox Narrative Engine:
    1. Tests pacing='fast' / 'vox' (target 3-4s per scene rhythm for high retention).
    2. Validates that Scene 1 is designated as 'hook' (0-30s YouTube retention).
    3. Validates that scene durations strictly follow the Vox fast rhythm (average 3-4s).
    4. Validates rich semantic bisection: setting, subject, action, lighting, camera_framing.
    5. Validates cinematic English prompt generation without empty placeholders.
    """
    res = split_text_into_vox_scenes_offline(
        full_text=VOX_PUNCHY_SCRIPT,
        pacing="fast",
        style_preset="cinematic_realistic",
    )

    scenes = res["scenes"]
    assert len(scenes) >= 8, f"Expected >= 8 scenes for fast Vox pacing, got {len(scenes)}"

    # 1. Check Hook in Scene 1
    assert scenes[0]["narrative_beat"] == "hook", f"Scene 1 must be 'hook', got '{scenes[0]['narrative_beat']}'"

    # 2. Check 3-4s timing per scene
    durations = [sc["estimated_duration"] for sc in scenes]
    avg_duration = sum(durations) / len(durations)
    print(f"\n[QA Vox Pacing] Total scenes: {len(scenes)} | Avg scene duration: {avg_duration:.2f}s | Range: {min(durations)}s - {max(durations)}s")

    assert 3.0 <= avg_duration <= 4.0, (
        f"Vox fast pacing rhythm out of bounds! Expected average 3-4s, got {avg_duration:.2f}s"
    )

    # 3. Check Semantic Layers and Cinematic Prompts
    for sc in scenes:
        assert sc["setting"], f"Scene {sc['order']} has empty setting"
        assert sc["subject"], f"Scene {sc['order']} has empty subject"
        assert sc["lighting"], f"Scene {sc['order']} has empty lighting"
        assert sc["camera_framing"], f"Scene {sc['order']} has empty camera_framing"
        assert sc["camera_motion"] in ("zoom_in", "zoom_out", "pan_left", "pan_right", "diagonal"), (
            f"Invalid camera motion: {sc['camera_motion']}"
        )
        prompt = sc["image_prompt"]
        assert len(prompt) > 40, f"Prompt too short: '{prompt}'"
        assert any(term in prompt.lower() for term in ["cinematic", "photorealistic", "shot", "lighting", "ultra"]), (
            f"Prompt missing cinematic cues: '{prompt}'"
        )



def test_adversarial_pacing_tiers_comparison():
    """
    Adversarial QA Test comparing Pacing Tiers:
    - Fast / Vox (3-4s): yields highest scene count.
    - Balanced (5-6s): yields intermediate scene count.
    - Deep Story (7-8s): yields lowest scene count.
    Validates strictly monotonic relationship: count(fast) > count(balanced) > count(deep_story).
    """
    res_fast = split_text_into_vox_scenes_offline(VOX_STORY_SAMPLE, pacing="fast")
    res_balanced = split_text_into_vox_scenes_offline(VOX_STORY_SAMPLE, pacing="balanced")
    res_deep = split_text_into_vox_scenes_offline(VOX_STORY_SAMPLE, pacing="deep_story")

    n_fast = res_fast["total_scenes"]
    n_bal = res_balanced["total_scenes"]
    n_deep = res_deep["total_scenes"]

    print(f"\n[QA Pacing Comparison] Fast: {n_fast} scenes | Balanced: {n_bal} scenes | Deep Story: {n_deep} scenes")

    assert n_fast > n_bal, f"Fast pacing ({n_fast}) should yield more scenes than Balanced ({n_bal})"
    assert n_bal > n_deep, f"Balanced pacing ({n_bal}) should yield more scenes than Deep Story ({n_deep})"

    # Check that average durations scale up accordingly
    avg_f = res_fast["estimated_total_duration"] / n_fast
    avg_b = res_balanced["estimated_total_duration"] / n_bal
    avg_d = res_deep["estimated_total_duration"] / n_deep

    assert avg_f < avg_b < avg_d, f"Average scene durations must strictly increase: {avg_f:.2f} < {avg_b:.2f} < {avg_d:.2f}"



@pytest.mark.live  # 9router chia cảnh + Edge-TTS thật
@pytest.mark.asyncio
async def test_adversarial_produce_long_video_pipeline(tmp_path):
    """
    Adversarial QA Test for produce_long_video (MoneyPrinterTurbo 5-phase Stepper):
    - Creates project with mock_cinematic image provider and Paladin Kai character.
    - Executes complete 5-step pipeline:
      (1) Script parsing & character anchoring (15%)
      (2) Edge-TTS voice generation & timed SRT subtitles (40%)
      (3) 8K Style Preset Visual generation (65%)
      (4) Motion FX Scene segments (85%)
      (5) Video assembly + Studio BGM Ducking + Hardsub subtitles (100%)
    - Verifies rendered output:
      * Full HD MP4 file exists and size > 50KB
      * ffprobe validates H.264 video stream & AAC audio stream
      * Master SRT subtitle file with multiple cues exists
      * Project cleanup succeeds without memory leak
    """
    project = create_project(ProjectCreateRequest(
        name="QA Long Video Stepper Test",
        image_provider="mock_cinematic",
        style_preset="fantasy_paladin_armor",
        character_anchor="Paladin Kai with ornate silver full plate armor and glowing cyan runes",
    ))
    proj_id = project.id
    render_id = f"test_render_{proj_id}"
    active_renders[render_id] = {"logs": []}

    story_script = """
    Dũng Sĩ Kai vung thanh kiếm runic tỏa ánh sáng lam ngọc rực rỡ.
    Khuôn mặt kiên định của chàng không hề nao núng trước bầy quái vật.
    Ánh bình minh ló rạng trên chiến trường, đem lại hòa bình cho vương quốc.
    """

    req = LongVideoProduceRequest(
        text=story_script,
        pacing="fast",
        style_preset="fantasy_paladin_armor",
        character_anchor="Paladin Kai with ornate silver full plate armor and glowing cyan runes",
        voice="vi-VN-HoaiMyNeural",
        resolution="720p",
        fps=25,
        ducking=True,
        hardsub=True,
    )

    try:
        await execute_produce_long_video(proj_id, render_id, req)
        render_state = active_renders.get(render_id, {})
        status = render_state.get("status")
        err = render_state.get("error")

        assert status == "completed", f"Long video production failed: {err}"
        video_path = render_state.get("video_path")
        srt_path = render_state.get("srt_path")

        assert video_path and os.path.exists(video_path), f"Final video not found: {video_path}"
        assert srt_path and os.path.exists(srt_path), f"Final SRT not found: {srt_path}"

        # Deep ffprobe inspection
        probe = probe_media_file(video_path)
        streams = probe.get("streams", [])
        v_stream = next((s for s in streams if s["codec_type"] == "video"), None)
        a_stream = next((s for s in streams if s["codec_type"] == "audio"), None)

        assert v_stream is not None, "Missing video stream in assembled long video"
        assert a_stream is not None, "Missing audio stream in assembled long video"
        assert v_stream["codec_name"] == "h264"
        assert a_stream["codec_name"] == "aac"
        assert v_stream["width"] == 1280
        assert v_stream["height"] == 720

        total_dur = float(probe["format"]["duration"])
        assert total_dur >= 6.0, f"Long video duration too short: {total_dur}s"

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()
        assert "-->" in srt_content, "Missing SRT timestamp cues"
        assert "Dũng Sĩ Kai" in srt_content or "Kai" in srt_content

        print(f"\n[QA Long Video Stepper] Final video duration: {total_dur:.2f}s | Codec: {v_stream['codec_name']}/{a_stream['codec_name']} | SRT size: {len(srt_content)} bytes")

    finally:
        delete_project(proj_id)


# ---- chuyển từ tests/test_no_fake_success_and_motion_render.py ----
@pytest.mark.asyncio
async def test_scene_analysis_reports_why_it_fell_back_offline(monkeypatch):
    """9router lỗi (vd key sai → 401) thì kết quả offline phải mang lý do, không im lặng."""
    from services import script_splitter

    async def failing_llm(self, *args, **kwargs):
        self.last_error = '9router HTTP 401: {"error":{"message":"Invalid API key"}}'
        return None

    monkeypatch.setattr(script_splitter.SemanticStoryAnalyzer, "call_9router_semantic_analyzer", failing_llm)
    monkeypatch.setattr(script_splitter, "NINEROUTER_API_KEY", "dummy-key-for-test")
    res = await script_splitter.analyze_vox_script_async(full_text="Đêm mưa. Một chiếc taxi dừng lại.", provider="9router")

    assert res["scenes"]
    assert "401" in res["fallback_reason"]



@pytest.mark.asyncio
async def test_storyboard_llm_request_disables_streaming(monkeypatch):
    """Thiếu stream:false thì 9router trả body không phải JSON, storyboard luôn rơi về offline."""
    from services import storyboard_engine
    sent = {}

    class FakeResp:
        status_code = 500
        text = "stop here"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            sent["payload"] = json
            return FakeResp()

    monkeypatch.setattr(storyboard_engine.httpx, "AsyncClient", FakeClient)
    await storyboard_engine.deconstruct_script_async(
        "Đêm mưa. Một chiếc taxi dừng lại.", api_key="test-key", base_url="http://127.0.0.1:9/v1")

    assert sent["payload"]["stream"] is False



# ---- chuyển từ tests/test_comic.py ----
@pytest.mark.live  # produce-long-video thật: 9router, ảnh, Edge-TTS
@pytest.mark.asyncio
async def test_api_produce_long_video_endpoint():
    """Verify POST /api/projects/{id}/produce-long-video initiates MoneyPrinterTurbo stepper pipeline."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        test_proj_id = f"test_proj_produce_{uuid.uuid4().hex[:6]}"
        produce_req = {
            "text": "Trận chiến nổ ra tại cổng thành. Tướng quân giơ cao thanh kiếm lệnh.",
            "pacing": "fast",
            "style_preset": "manga_battle_action",
            "character_anchor": "Vị tướng áo giáp đen",
            "voice": "vi-VN-HoaiMyNeural",
            "bgm": "none",
            "ducking": False,
            "hardsub": False,
            "resolution": "720p",
            "fps": 25
        }
        resp = await client.post(f"/api/projects/{test_proj_id}/produce-long-video", json=produce_req)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "render_id" in data
        assert data["status"] == "queued"

        # Check render status
        render_id = data["render_id"]
        resp_status = await client.get(f"/api/render-status/{render_id}")
        assert resp_status.status_code == 200
        status_data = resp_status.json()
        assert status_data["render_id"] == render_id
        assert status_data["project_id"] == test_proj_id

        delete_project(test_proj_id)


# ---- chuyển từ tests/test_api.py ----
@pytest.mark.asyncio
async def test_post_split_script():
    """Verify POST /api/split-script intelligently splits long story text."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        long_story = (
            "Ngày xửa ngày xưa có một chú bé dũng cảm sống ở một ngôi làng ven biển. "
            "Một ngày kia, bầu trời bỗng nổi cơn giông bão dữ dội và một con thuyền lạ dạt vào bờ. "
            "Cậu bé quyết định leo lên thuyền để tìm kiếm những người còn sống sót."
        )
        resp = await client.post("/api/split-script", json={
            "text": long_story,
            "max_words_per_scene": 18,
            "language": "vi",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "scenes" in data
        assert data["count"] >= 2
        for sc in data["scenes"]:
            assert "text" in sc
            assert "image_prompt" in sc
            assert "camera_motion" in sc

