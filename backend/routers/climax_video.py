"""API video cho cảnh cao trào (dự án vụ án). Xử lý ở services/climax_video.py.

- POST /api/projects/{project_id}/climax-video/pick?mode=ai|score   chọn cảnh đủ video_rules.TARGET_SHARE thời lượng video: "ai" (mặc
                                                                     định, chạy nền, services/climax_ai_pick.py) hoặc
                                                                     "score" (chấm theo nhãn kịch bản, trả ngay)
- GET  /api/projects/{project_id}/climax-video/pick-status          lượt AI chọn cảnh gần nhất (idle/running/done/failed)
- PUT  /api/projects/{project_id}/climax-video/scenes/{scene_id}   bật/tắt một cảnh
- POST /api/projects/{project_id}/climax-video/run                  chạy nền các cảnh đã chọn (tốn lượt Muse)
- GET  /api/projects/{project_id}/climax-video/status               tiến độ từng cảnh
- GET  /api/projects/{project_id}/climax-video/scenes/{scene_id}/grid?i=1   ảnh grid đang chờ duyệt / đã duyệt
- POST /api/projects/{project_id}/climax-video/scenes/{scene_id}/grid/approve
- POST /api/projects/{project_id}/climax-video/scenes/{scene_id}/grid/reject  body {"feedback": "..."} (vẽ lại lượt sau)

Mỗi cảnh hai pha (28/10/2026): "Tạo video" vẽ grid rồi dừng ở "grid_review"; duyệt grid xong, "Tạo video" lần nữa làm clip.

Làm từng bước theo ý chủ dự án: không tự chạy trong "Sản xuất video dài".
"""
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from models.schemas import Project
from routers import muse_bridge
from routers.muse_bridge import (enqueue_and_wait_muse_task, ensure_local_fleet_runner, is_kind_online, routing_kind,
                                 usable_online_accounts)
from runners import single_instance
from security import is_within, validate_path_ids
from services import climax_ai_pick, climax_video, one_pass_visuals, project_service
from services.case_adaptation_steps import StepFailed

logger = logging.getLogger("story_studio.climax_video_router")

router = APIRouter(prefix="/api", tags=["Climax video"], dependencies=[Depends(validate_path_ids)])

WORKER_STAGGER_S = 20   # tài khoản thứ hai bắt đầu sau một chút: hai tài khoản không gửi Muse cùng một giây
RUNNER_START_WAIT_S = 60   # như image_service: runner vừa bật cần chừng này để đăng ký tài khoản
RUNNABLE = ("selected", "failed", "grid_approved")
KEEP_ON_PICK = ("ready", "grid_review", "grid_approved")   # "Chọn cảnh cao trào" không xoá công đã làm
# Trạng thái đang làm; lúc không có lượt chạy nào mà cảnh còn ở đây là lượt trước bị ngắt (tắt server): chạy lại được
WORKING = ("grid", "clips", "checking")
# Một lượt chạy nền cho mỗi dự án (giữ tham chiếu để task không bị dọn giữa chừng)
_running: dict[str, asyncio.Task] = {}
# Lượt AI chọn cảnh (chạy nền, như "Tìm nhân vật" ở routers/character_sheets.py) và kết quả lượt gần nhất của từng dự án
PICK_MODES = ("ai", "score")
LOST_PICK_MESSAGE = "Lượt chọn bị gián đoạn, bấm lại"
_picking: dict[str, asyncio.Task] = {}
_pick_status: dict[str, dict] = {}


class SceneToggle(BaseModel):
    enabled: bool


class GridFeedback(BaseModel):
    feedback: str = Field(..., max_length=climax_video.FEEDBACK_MAX)


def _is_running(project_id: str) -> bool:
    task = _running.get(project_id)
    return task is not None and not task.done()


def _is_picking(project_id: str) -> bool:
    task = _picking.get(project_id)
    return task is not None and not task.done()


# Dự án đang được một yêu cầu pick/run giữ chỗ (từ lúc kiểm tới lúc tạo task, qua các lần await đọc ghi đĩa): yêu cầu
# thứ hai tới trong khoảng đó (bấm đúp, pick đua với run) bị 409, không chạy hai lượt AI hay pick chen vào lượt Muse.
_starting: set[str] = set()


def _refuse_while_one_pass(project_id: str, what: str) -> None:
    """Nút "Tạo hình cho cả dự án" (routers/one_pass_visuals.py) đang chạy cho dự án này: không chọn, sửa hay chạy chen."""
    if one_pass_visuals.is_running(project_id):
        raise HTTPException(status_code=409, detail=f"Đang chạy \"Tạo hình cho cả dự án\" cho dự án này, chờ xong "
                                                    f"hoặc bấm Dừng rồi {what}")


def _refuse_while_picking(project_id: str, what: str) -> None:
    _refuse_while_one_pass(project_id, what)
    if _is_picking(project_id):
        raise HTTPException(status_code=409, detail=f"AI đang chọn cảnh cao trào cho dự án này, chờ xong rồi {what}")
    if project_id in _starting:
        raise HTTPException(status_code=409, detail=f"Dự án đang bắt đầu một lượt chọn cảnh hoặc tạo video, chờ chút "
                                                    f"rồi {what}")


def _state(scene) -> dict:
    value = (scene.metadata or {}).get("climax_video")
    return value if isinstance(value, dict) else {}


async def _load(project_id: str) -> Project:
    try:
        project = await asyncio.to_thread(project_service.get_project, project_id)
    except ValueError as e:   # id dành riêng cho hệ thống (vd _cases)
        raise HTTPException(status_code=400, detail=str(e)) from None
    if project is None:
        raise HTTPException(status_code=404, detail=f"Không có dự án {project_id}")
    return project


def _set_state(scene, state) -> None:
    scene.metadata = dict(scene.metadata or {})
    if state is None:
        scene.metadata.pop("climax_video", None)
    else:
        scene.metadata["climax_video"] = state


def _apply_pick(project: Project, chosen: list[str], state_for) -> list[str]:
    """Đánh dấu "selected" (state_for(scene_id)) cho cảnh chọn được; bỏ dấu "selected" cũ của cảnh khác; không đụng
    cảnh đã có công (KEEP_ON_PICK, hoặc grid đã duyệt kể cả khi làm clip lỗi). Trả id cảnh chọn còn có trong dự án và
    còn làm video được (đã đánh dấu, hoặc đã có công sẵn): số phần trăm tính trên đúng các cảnh này."""
    wanted = set(chosen)
    kept: list[str] = []
    for scene in project.scenes:
        status = _state(scene).get("status")
        if scene.id in wanted and climax_video.is_eligible(scene):
            kept.append(scene.id)
        if status in KEEP_ON_PICK or _state(scene).get("grid_approved"):
            continue
        if scene.id in wanted and climax_video.is_eligible(scene):
            _set_state(scene, state_for(scene.id))
        elif status == "selected":
            _set_state(scene, None)
    return kept


async def _ai_pick_job(project_id: str) -> None:
    """Lượt AI chọn cảnh chạy nền. AI lỗi hẳn thì ghi "failed" kèm lý do và không ghi gì vào dự án (không tự quay về
    cách chấm theo nhãn: CLAUDE.md đường cấm 3, 4)."""
    try:
        result = await climax_ai_pick.ai_pick(project_id)

        def write() -> tuple[list[str], dict]:
            # Đọc lại ngay trước khi ghi: lượt AI có thể dài vài phút
            project = project_service.get_project(project_id)
            if project is None:
                raise climax_ai_pick.ClimaxPickError(f"Không còn dự án {project_id}")
            reasons, scores = result["reasons"], result["scores"]
            applied = _apply_pick(project, result["chosen"], lambda sid: {
                "status": "selected", "picked_by": "ai", "reason": reasons.get(sid, ""), "ai_score": scores.get(sid)})
            project_service.save_project(project)
            return applied, climax_video.coverage(project, applied)

        applied, cov = await asyncio.to_thread(write)
        _pick_status[project_id] = {"state": "done", "mode": "ai", "scene_ids": applied, "coverage": cov,
                                    "scored": len(result["scores"])}
    except StepFailed as e:
        _pick_status[project_id] = {"state": "failed", "mode": "ai", "error": e.user_message}
    except climax_ai_pick.ClimaxPickError as e:
        _pick_status[project_id] = {"state": "failed", "mode": "ai", "error": str(e)}
    except Exception as e:   # lỗi ngoài dự kiến: ghi log và báo lên giao diện, không im lặng
        logger.exception(f"AI chọn cảnh cao trào {project_id}: lỗi ngoài dự kiến")
        _pick_status[project_id] = {"state": "failed", "mode": "ai",
                                    "error": f"Lỗi ngoài dự kiến: {type(e).__name__}: {e}"}


@router.post("/projects/{project_id}/climax-video/pick")
async def pick_scenes(project_id: str, mode: str = "ai"):
    """mode "ai" (mặc định): AI chấm từng cảnh rồi chọn, chạy nền; theo dõi ở pick-status. mode "score": chấm theo nhãn
    kịch bản (nhịp, nhạc, tiếng động), trả ngay danh sách. Cả hai không đụng cảnh đã có công (KEEP_ON_PICK)."""
    if mode not in PICK_MODES:
        raise HTTPException(status_code=400, detail=f"mode phải là một trong: {', '.join(PICK_MODES)}")
    # Kiểm và giữ chỗ liền nhau, không có await ở giữa: yêu cầu thứ hai tới trong lúc đọc ghi đĩa thì bị 409
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này, chờ xong rồi chọn lại")
    _refuse_while_picking(project_id, "chọn lại")
    _starting.add(project_id)
    try:
        project = await _load(project_id)
        if mode == "ai":
            if not any(climax_video.is_eligible(s) for s in project.scenes):
                raise HTTPException(status_code=400, detail="Dự án chưa có cảnh vẽ nào làm video được")
            _pick_status[project_id] = {"state": "running", "mode": "ai"}
            _picking[project_id] = asyncio.create_task(_ai_pick_job(project_id))
            return {"picking": True, "mode": "ai"}
        chosen = await asyncio.to_thread(climax_video.pick_climax_scenes, project)
        applied = _apply_pick(project, chosen, lambda sid: {"status": "selected", "picked_by": "score"})
        await asyncio.to_thread(project_service.save_project, project)
        cov = climax_video.coverage(project, applied)
        _pick_status[project_id] = {"state": "done", "mode": "score", "scene_ids": applied, "coverage": cov}
        return {"scene_ids": applied, "limit": len(applied), "coverage": cov, "mode": "score"}
    finally:
        _starting.discard(project_id)


@router.get("/projects/{project_id}/climax-video/pick-status")
async def pick_status(project_id: str):
    await _load(project_id)
    status = dict(_pick_status.get(project_id) or {"state": "idle"})
    if status.get("state") == "running" and not _is_picking(project_id):   # task mất (không nên có): báo, không treo
        status = {"state": "failed", "mode": "ai", "error": LOST_PICK_MESSAGE}
    return status


@router.put("/projects/{project_id}/climax-video/scenes/{scene_id}")
async def toggle_scene(project_id: str, scene_id: str, req: SceneToggle):
    """Bật (đánh dấu "selected") hoặc tắt một cảnh. Tắt cảnh đã có video: về lại ảnh, clip vẫn giữ trên đĩa."""
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này, chờ xong rồi sửa")
    _refuse_while_picking(project_id, "sửa")
    project = await _load(project_id)
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"Dự án không có cảnh {scene_id}")
    if not climax_video.is_eligible(scene):
        raise HTTPException(status_code=400, detail="Chỉ cảnh vụ án có hình vẽ (không phải bảng ghim, thẻ miễn trừ) "
                                                    "mới làm video cao trào được")
    status = _state(scene).get("status")
    if req.enabled:
        # 50% là mức sàn thời lượng (CLAUDE.md mục 1.2 câu 24), không phải mức trần: bật thêm cảnh luôn được
        if status not in ("selected", *KEEP_ON_PICK) and not _state(scene).get("grid_approved"):
            _set_state(scene, {"status": "selected", "picked_by": "manual"})
    else:
        if status == "ready" and scene.media_view_mode == "video":
            scene.media_view_mode = "image"
        _set_state(scene, None)
    await asyncio.to_thread(project_service.save_project, project)
    return {"scene_id": scene_id, "status": _state(scene).get("status")}


async def muse_call_starting_runner(task: dict) -> dict:
    """enqueue_and_wait_muse_task, nhưng Fleet Runner chưa chạy thì bật và chờ nó đăng ký trước (không thì cảnh thất
    bại ngay vì "không có tài khoản online"). Test tắt tự bật runner bằng STORY_STUDIO_DISABLE_FLEET_AUTOSTART."""
    kind = routing_kind(task)   # việc ảnh grid chạy trên tài khoản video (route_kind)
    if not is_kind_online(kind) and not single_instance.autostart_disabled():
        ensure_local_fleet_runner()
        deadline = time.monotonic() + RUNNER_START_WAIT_S
        while not is_kind_online(kind) and time.monotonic() < deadline:
            await asyncio.sleep(2.0)
    call = enqueue_and_wait_muse_task
    if call is _ENQUEUE_ORIGINAL:   # chưa bị thay ở module này: dùng bản hiện hành của muse_bridge (test có thể thay ở đó)
        call = muse_bridge.enqueue_and_wait_muse_task
    return await call(task)


_ENQUEUE_ORIGINAL = enqueue_and_wait_muse_task
_muse_call = muse_call_starting_runner   # tên cũ (test)


# Lỗi cho biết không còn tài khoản video làm được: dừng cả lượt chạy, các cảnh chưa tới giữ nguyên trạng thái. Gặp
# 12/11/2026: tài khoản video duy nhất hết lượt dùng Muse, 24 cảnh sau bị ghi "failed" hàng loạt trong vài giây.
# Một tài khoản hết lượt (QUOTA_EXCEEDED) thì backend khoá riêng tài khoản đó, tài khoản khác làm tiếp: không dừng.
STOP_RUN_WORDS = ("Không có tài khoản Muse video nào đang online",)


# Lỗi cho biết riêng tài khoản đang làm không dùng được nữa (hết lượt, mất đăng nhập, bị khoá): người làm của tài khoản
# đó nghỉ, tài khoản khác làm tiếp các cảnh còn lại.
# Chỉ theo mã lỗi của Fleet Runner và câu của cầu nối Muse, không dò chữ trong báo cáo Muse (rà soát 18/11/2026: báo
# cáo có chữ "hạn mức" làm tài khoản nghỉ giữa chừng).
ACCOUNT_DOWN_WORDS = ("không dùng được (offline, bị khoá hoặc mất", "QUOTA_EXCEEDED", "SESSION_EXPIRED")


def _scene_owners(project_id: str, scene_ids: list[str], accounts: list[str]) -> dict[str, Optional[str]]:
    """Tài khoản đã nhận từng cảnh ở lượt trước (metadata climax_video.account_id), nếu tài khoản đó đang dùng được."""
    project = project_service.get_project(project_id)
    wanted = set(scene_ids)
    out: dict[str, Optional[str]] = {}
    for scene in project.scenes if project else []:
        if scene.id in wanted:
            acc = _state(scene).get("account_id")
            out[scene.id] = acc if acc in accounts else None
    return out


def _release_scene(project_id: str, scene_id: str) -> None:
    """Cảnh hỏng vì tài khoản không dùng được: bỏ chat và tài khoản cũ để tài khoản khác làm lại cả cảnh."""
    try:
        climax_video.release_account(project_id, scene_id)
    except (climax_video.ClimaxVideoError, LookupError) as e:   # dự án/cảnh vừa bị xoá: tài khoản khác sẽ báo lỗi rõ
        logger.warning(f"Không gỡ được tài khoản cũ của {project_id}/{scene_id}: {e}")


async def _run_one(project_id: str, scene_id: str, account: Optional[str]) -> str:
    """Chạy một cảnh; trả chuỗi lỗi ("" khi không lỗi). Lỗi ngoài dự kiến: cảnh đã được ghi "failed"."""
    try:
        state = await climax_video.run_scene_climax_video(project_id, scene_id, muse_call=muse_call_starting_runner,
                                                          account=account)
    except Exception as e:
        logger.exception(f"Video cao trào {project_id}/{scene_id}: lỗi ngoài dự kiến")
        return f"{type(e).__name__}: {e}"
    return str((state or {}).get("error") or "") if (state or {}).get("status") == "failed" else ""


async def _run_all(project_id: str, scene_ids: list[str]) -> None:
    """Mỗi tài khoản video đang dùng được có một người làm, các người làm lấy lần lượt cảnh tiếp theo trong hàng chung:
    các tài khoản thay phiên nhau và chạy song song. Mỗi cảnh ghim vào đúng một tài khoản từ đầu tới cuối (chủ dự án
    13/11/2026: "không được 1 cảnh mà chia sang 2 tài khoản lại lệch nhân vật"). Chưa có tài khoản nào online (runner
    vừa bật): chạy lần lượt như cũ, không ghim."""
    accounts = usable_online_accounts("video")
    queue = list(scene_ids)
    if not accounts:
        for scene_id in queue:
            error = await _run_one(project_id, scene_id, None)
            if any(w in error for w in STOP_RUN_WORDS):
                logger.warning(f"Video cao trào {project_id}: dừng lượt chạy ở {scene_id}, không còn tài khoản video "
                               f"làm được ({error[:200]})")
                break
        return
    owner = await asyncio.to_thread(_scene_owners, project_id, queue, accounts)
    alive = set(accounts)
    logger.info(f"Video cao trào {project_id}: {len(queue)} cảnh, chia cho {len(accounts)} tài khoản {accounts}")

    async def worker(account: str, delay: float) -> None:
        await asyncio.sleep(delay)
        while True:
            # Cảnh đã bắt đầu trên một tài khoản đang dùng được thì chỉ tài khoản đó làm tiếp (gặp 13/11/2026: cảnh 052
            # bắt đầu trên vp_01, server tắt giữa chừng, lần chạy lại tài khoản kia nhận mất).
            scene_id = next((s for s in queue if owner.get(s) in (None, account)), None)
            if scene_id is None:
                return
            queue.remove(scene_id)
            logger.info(f"Video cao trào {project_id}/{scene_id}: giao cho {account}")
            error = await _run_one(project_id, scene_id, account)
            if any(w in error for w in STOP_RUN_WORDS + ACCOUNT_DOWN_WORDS):
                logger.warning(f"Video cao trào {project_id}: {account} nghỉ sau {scene_id} ({error[:200]})")
                # Cảnh của tài khoản này (kể cả cảnh vừa hỏng vì tài khoản) làm lại từ đầu trên tài khoản khác, chat
                # mới: trước đây chúng bị bỏ lại vì chỉ tài khoản đã ghim được nhận (rà soát 18/11/2026). Cả cảnh
                # chuyển sang một tài khoản, không chia một cảnh cho hai tài khoản.
                for s in [s for s, acc in owner.items() if acc == account]:
                    owner[s] = None
                if not any(w in error for w in STOP_RUN_WORDS) and len(alive) > 1:
                    queue.append(scene_id)
                    await asyncio.to_thread(_release_scene, project_id, scene_id)
                alive.discard(account)
                return

    await asyncio.gather(*(worker(a, i * WORKER_STAGGER_S) for i, a in enumerate(accounts)))


@router.post("/projects/{project_id}/climax-video/run")
async def run_scenes(project_id: str):
    """Chạy nền lần lượt các cảnh "selected" hoặc "failed" (và cảnh bị ngắt giữa chừng ở lượt trước); trả ngay danh
    sách đưa vào hàng. Tốn lượt Muse."""
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này")
    _refuse_while_picking(project_id, "tạo video")
    _starting.add(project_id)   # giữ chỗ qua lần đọc đĩa: bấm đúp hay pick đua tới thì 409, không chạy hai lượt Muse
    try:
        project = await _load(project_id)
        queued = [s.id for s in project.scenes
                  if climax_video.is_eligible(s) and _state(s).get("status") in RUNNABLE + WORKING]
        if not queued:
            raise HTTPException(status_code=400, detail="Chưa có cảnh nào được chọn: bấm \"AI chọn cảnh cao trào\" hoặc "
                                                        "bật từng cảnh trước")
        _running[project_id] = asyncio.create_task(_run_all(project_id, queued))
        return {"queued": queued}
    finally:
        _starting.discard(project_id)


def _scene_of(project: Project, scene_id: str):
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"Dự án không có cảnh {scene_id}")
    return scene


@router.get("/projects/{project_id}/climax-video/scenes/{scene_id}/grid")
async def grid_image(project_id: str, scene_id: str, i: int = 1):
    project = await _load(project_id)
    paths = _state(_scene_of(project, scene_id)).get("grid_paths") or []
    if not 1 <= i <= len(paths):
        raise HTTPException(status_code=404, detail="Cảnh chưa có ảnh grid này")
    path = Path(paths[i - 1])
    if not path.is_file() or not is_within(path, project_service.get_scene_media_paths(project_id, scene_id)["video"].parent):
        raise HTTPException(status_code=404, detail="Không còn file ảnh grid")
    return FileResponse(path, media_type="image/jpeg")


async def _grid_action(fn, *args) -> dict:
    try:
        return await asyncio.to_thread(fn, *args)
    except climax_video.ClimaxVideoError as e:
        raise HTTPException(status_code=400, detail=e.message) from None
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/projects/{project_id}/climax-video/scenes/{scene_id}/grid/approve")
async def approve_grid(project_id: str, scene_id: str):
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này, chờ xong rồi duyệt")
    _refuse_while_one_pass(project_id, "duyệt")
    state = await _grid_action(climax_video.approve_grid, project_id, scene_id)
    return {"scene_id": scene_id, "status": state.get("status")}


@router.post("/projects/{project_id}/climax-video/scenes/{scene_id}/grid/reject")
async def reject_grid(project_id: str, scene_id: str, body: GridFeedback):
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này, chờ xong rồi sửa")
    _refuse_while_one_pass(project_id, "sửa")
    state = await _grid_action(climax_video.reject_grid, project_id, scene_id, body.feedback)
    return {"scene_id": scene_id, "status": state.get("status")}


@router.post("/projects/{project_id}/climax-video/scenes/{scene_id}/redo")
async def redo_scene(project_id: str, scene_id: str):
    """"Làm lại cảnh này": cảnh đã xong hoặc lỗi (grid đã duyệt) về chờ làm clip ở chat mới. Bấm "Tạo video" để chạy;
    mỗi lần tốn tới 6 video + 4 ảnh Muse."""
    if _is_running(project_id):
        raise HTTPException(status_code=409, detail="Đang tạo video cao trào cho dự án này, chờ xong rồi làm lại")
    _refuse_while_one_pass(project_id, "làm lại")
    state = await _grid_action(climax_video.redo_scene, project_id, scene_id)
    return {"scene_id": scene_id, "status": state.get("status")}


@router.get("/projects/{project_id}/climax-video/status")
async def climax_status(project_id: str):
    project = await _load(project_id)
    scenes = []
    for scene in project.scenes:
        state = _state(scene)
        if state.get("status"):
            scenes.append({"scene_id": scene.id, "status": state["status"], "error": state.get("error"),
                           **{k: state[k] for k in ("clips", "grids", "grid", "done", "attempts", "grid_version",
                                                    "muse_report", "media_count", "warnings", "scene_image_updated",
                                                    "backup_image", "video_seconds", "motion_score", "picked_by",
                                                    "reason", "ai_score", "grid_approved_by")
                              if k in state},
                           "grid_count": len(state.get("grid_paths") or [])})
    return {
        "running": _is_running(project_id),
        "picking": _is_picking(project_id),
        "one_pass_running": one_pass_visuals.is_running(project_id),
        "limit": await asyncio.to_thread(climax_video.climax_limit, project),
        "eligible": sum(1 for s in project.scenes if climax_video.is_eligible(s)),
        "scenes": scenes,
    }
