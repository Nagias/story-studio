"""Các route đã gỡ khỏi backend/routers/api.py ngày 18/11/2026 (giữ làm kỷ niệm, không được nạp).

Giao diện không gọi các route này. Chúng dùng bộ chia cảnh đời cũ (legacy/backend/services/script_splitter.py,
storyboard_engine.py): dặn AI "tóm tắt", chèn chữ "KA-BOOM" vào mọi phong cách, hỏng thì chép nguyên văn.
"""
# flake8: noqa

# ----------------- SCRIPT SPLITTING & VOX NARRATIVE ENGINE -----------------

@router.get("/vox/pacing-presets")
async def get_vox_pacing_presets():
    """Return available Vox narrative pacing presets."""
    return PACING_CONFIGS

@router.post("/vox/analyze-script", response_model=VoxScriptAnalysisResponse)
async def analyze_vox_script(req: VoxScriptAnalysisRequest):
    """
    Semantic Story Analyzer (Vox Narrative Engine):
    - Cuts long text / chapter into Vox 5-Stage Arc (Hook, Setting, Escalation, Climax, Resolution).
    - Supports Fast/Vox (3-4s), Balanced (5-6s), Deep Story (7-8s) pacing.
    - Generates multi-layered semantic attributes & rich cinematic English prompts.
    - Uses Gemini API / OpenRouter when available, with automatic offline semantic parser fallback.
    """
    try:
        result = await analyze_vox_script_async(
            full_text=req.text,
            pacing=req.pacing or "fast",
            max_words_per_scene=req.max_words_per_scene,
            style_preset=req.style_preset or DEFAULT_STYLE,
            character_anchor=req.character_anchor,
            gemini_api_key=req.api_key if req.provider in ("gemini", "auto") else None,
            openrouter_api_key=req.api_key if req.provider in ("openrouter", "auto") else None,
            provider=req.provider or "auto",
            model_name=req.model_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze Vox script: {str(e)}")

@router.post("/projects/{project_id}/vox-script")
async def import_vox_script_to_project(project_id: str, req: VoxProjectScriptRequest):
    """
    Analyze long text / novel chapter with Vox Narrative Engine and inject scenes directly into project.
    Optionally replaces existing scenes if replace_existing=True.
    """
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    style_preset = req.style_preset or project.style_preset or DEFAULT_STYLE
    character_anchor = req.character_anchor or project.character_anchor or None

    try:
        analysis = await analyze_vox_script_async(
            full_text=req.text,
            pacing=req.pacing or "fast",
            max_words_per_scene=req.max_words_per_scene,
            style_preset=style_preset,
            character_anchor=character_anchor,
            gemini_api_key=req.api_key if req.provider in ("gemini", "auto") else None,
            openrouter_api_key=req.api_key if req.provider in ("openrouter", "auto") else None,
            provider=req.provider or "auto",
            model_name=req.model_name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze Vox script: {str(e)}")
    if analysis.get("fallback_reason"):
        logger.warning(f"vox-script dùng bộ chia offline: {analysis['fallback_reason']}")

    if req.replace_existing:
        for existing_scene in list(project.scenes):
            delete_scene(project_id, existing_scene.id)

    created_scenes = []
    for sc in analysis.get("scenes", []):
        meta = {
            "narrative_beat": sc.get("narrative_beat", "setting"),
            "estimated_duration": sc.get("estimated_duration", 3.5),
            "setting": sc.get("setting", ""),
            "subject": sc.get("subject", ""),
            "emotion": sc.get("emotion", ""),
            "action": sc.get("action", ""),
            "lighting": sc.get("lighting", ""),
            "camera_framing": sc.get("camera_framing", ""),
        }
        c_req = SceneCreateRequest(
            text=sc["text"],
            image_prompt=sc.get("image_prompt", ""),
            camera_motion=sc.get("camera_motion", "zoom_in"),
            metadata=meta,
        )
        scene_obj = add_scene(project_id, c_req)
        if scene_obj:
            created_scenes.append(scene_obj)

    updated_proj = get_project(project_id)
    return {
        "success": True,
        "pacing": req.pacing or "fast",
        "provider_used": analysis.get("provider_used", "offline_semantic_rules"),
        "fallback_reason": analysis.get("fallback_reason"),
        "narrative_summary": analysis.get("narrative_summary", {}),
        "added_scenes": len(created_scenes),
        "total_scenes": len(updated_proj.scenes) if updated_proj else 0,
        "project": updated_proj,
    }

@router.post("/novel/ingest-chapter")
async def ingest_novel_chapter(req: NovelIngestRequest):
    """
    US Light Novel Storyboard Ingest Pipeline:
    - Analyzes raw chapter with 9router Gemini 3.8 Flash.
    - Generates high-retention English story podcast script (with 5s Hook).
    - Produces ultra-detailed visual prompts for 9router Gemini Image (Murata / Spartan / Ink styles).
    - Creates or updates project with default US voice (Guy) and 9router Gemini image generator.
    """
    clean_text = req.novel_text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Novel text cannot be empty.")

    style_preset = req.style_preset or DEFAULT_STYLE
    pacing = req.pacing or "fast"
    voice = req.voice or "en-US-GuyNeural"

    analysis = await adapt_novel_chapter_to_us_podcast(
        novel_text=clean_text,
        pacing=pacing,
        style_preset=style_preset,
        target_character=req.target_character,
    )

    fallback_reason = analysis.get("fallback_reason")
    if fallback_reason:
        logger.warning(f"ingest-chapter dùng bộ chia offline: {fallback_reason}")
    scenes_list = analysis.get("scenes", [])
    if not scenes_list:
        detail = "Failed to parse scenes from novel text."
        raise HTTPException(status_code=500, detail=f"{detail} {fallback_reason}" if fallback_reason else detail)

    proj_id = req.project_id
    if not proj_id or req.create_new_project:
        title = req.project_title or "Light Novel US Podcast Episode"
        new_proj_req = ProjectCreateRequest(
            name=title,
            description="Auto-generated US Story Podcast from Light Novel Chapter",
            voice=voice,
            style_preset=style_preset,
            image_provider="9router_gemini",
        )
        created_proj = create_project(new_proj_req)
        proj_id = created_proj.id

    created_scenes = []
    for sc in scenes_list:
        c_req = SceneCreateRequest(
            text=sc.get("text", "").strip(),
            image_prompt=sc.get("image_prompt", "").strip(),
            camera_motion=sc.get("camera_motion", "zoom_in"),
            metadata={
                "narrative_beat": sc.get("narrative_beat", "setting"),
                "estimated_duration": sc.get("estimated_duration", 4.0),
            },
        )
        s_obj = add_scene(proj_id, c_req)
        if s_obj:
            created_scenes.append(s_obj)

    project = get_project(proj_id)
    return {
        "success": True,
        "project_id": proj_id,
        "total_scenes": len(created_scenes),
        "style_preset": style_preset,
        "voice": voice,
        "image_provider": "9router_gemini",
        "fallback_reason": fallback_reason,
        "project": project,
        "scenes": created_scenes,
    }

@router.post("/split-script")
async def split_script(req: SplitScriptRequest):
    """Parse text into scene drafts without attaching to a project."""
    scenes = split_text_into_scenes(
        full_text=req.text,
        max_words_per_scene=req.max_words_per_scene or 30,
        language=req.language or "vi",
        pacing=req.pacing or "fast",
        style_preset=req.style_preset or DEFAULT_STYLE,
        character_anchor=req.character_anchor,
    )
    return {"scenes": scenes, "count": len(scenes)}

@router.post("/projects/{project_id}/split-script")
async def split_script_to_project(project_id: str, req: SplitScriptRequest):
    """Parse text and append the generated scenes directly to the project."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    style_preset = req.style_preset or project.style_preset
    character_anchor = req.character_anchor or project.character_anchor

    new_scenes = split_text_into_scenes(
        full_text=req.text,
        max_words_per_scene=req.max_words_per_scene or 30,
        language=req.language or "vi",
        pacing=req.pacing or "fast",
        style_preset=style_preset,
        character_anchor=character_anchor,
    )

    created = []
    for sc in new_scenes:
        c_req = SceneCreateRequest(
            text=sc["text"],
            image_prompt=sc["image_prompt"],
            camera_motion=sc["camera_motion"],
        )
        scene_obj = add_scene(project_id, c_req)
        if scene_obj:
            created.append(scene_obj)

    updated_proj = get_project(project_id)
    return {
        "success": True,
        "added_scenes": len(created),
        "total_scenes": len(updated_proj.scenes) if updated_proj else 0,
        "project": updated_proj,
    }



# ---- produce-long-video: nhánh chia cảnh từ text (đã gỡ) ----
#         analysis_note = None  # lý do cảnh được chia offline (prompt ảnh mẫu chung), để báo trong log
#         if req.text and req.text.strip():
#             pacing = req.pacing or "fast"
#             try:
#                 vox_res = await analyze_vox_script_async(
#                     full_text=req.text.strip(),
#                     pacing=pacing,
#                     style_preset=project.style_preset,
#                     character_anchor=project.character_anchor,
#                     provider="9router",
#                 )
#                 raw_scenes = vox_res.get("scenes", [])
#                 analysis_note = vox_res.get("fallback_reason")
#             except Exception as e:
#                 analysis_note = f"Lỗi phân tích cảnh bằng 9router: {e}"
#                 raw_scenes = split_text_into_vox_scenes_offline(
#                     full_text=req.text.strip(),
#                     pacing=pacing,
#                     style_preset=project.style_preset,
#                     character_anchor=project.character_anchor,
#                 )["scenes"]
#             if analysis_note:
#                 logger.warning(f"produce-long-video dùng bộ chia offline: {analysis_note}")
# 
#             new_scenes = []
#             for idx, sc in enumerate(raw_scenes, start=1):
#                 motion = req.camera_motion or sc.get("camera_motion") or project.default_motion
#                 sc_id = f"scene_{idx:02d}_{uuid.uuid4().hex[:4]}"
#                 new_scenes.append(Scene(
#                     id=sc_id,
#                     order=idx,
#                     text=sc.get("text", f"Cảnh #{idx}"),
#                     image_prompt=sc.get("image_prompt", ""),
#                     camera_motion=motion,
#                     status="draft"
#                 ))
#             project.scenes = new_scenes
#             update_project(project_id, ProjectUpdateRequest(scenes=project.scenes))
# 

@router.post("/storyboard/deconstruct", response_model=MasterStoryboard)
async def api_deconstruct_storyboard(req: DeconstructScriptRequest):
    """
    Deconstructs raw script into Master Storyboard JSON adhering to OP_CTOOL Spec:
    - DNA Style & Character Anchors
    - 9-Grid Sequential Narrative Slicing Prompts
    - 3-Layer Audio Design & SFX Cues
    - Dramatic Pacing Pauses (0.3s - 2.0s)
    - 2.5D Parallax Depth hints
    """
    try:
        storyboard = await deconstruct_script_async(
            raw_text=req.script_text,
            art_style=req.art_style or "Dark moody cinematic neo-noir, 35mm anamorphic film grain",
            tone_and_mood=req.tone_and_mood or "tense_suspense",
            batch_9_grid=req.batch_9_grid,
            provider=req.provider or "auto",
            api_key=req.api_key,
        )
        return storyboard
    except Exception as e:
        logger.error(f"Error in deconstruct_storyboard: {e}", exc_info=True)
        # Always fallback to offline deterministic parse
        return deconstruct_script_offline(
            raw_text=req.script_text,
            art_style=req.art_style or "Dark moody cinematic neo-noir, 35mm anamorphic film grain",
            tone_and_mood=req.tone_and_mood or "tense_suspense",
            batch_9_grid=req.batch_9_grid,
        )

