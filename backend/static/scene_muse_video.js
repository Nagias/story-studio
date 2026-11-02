/* Nút "Muse Video" trên thẻ cảnh (Bước 2): video dài theo lời thoại. Lời ngắn: 1 video Muse; lời dài: chia thành nhiều
 * đoạn liền nhau, mỗi đoạn một video (đổi cảnh theo lời kể), server ghép lại. Trước khi chạy hỏi xác nhận kèm số video
 * Muse cần (mỗi video một lượt Muse) và lời kể từng đoạn.
 * API: /api/projects/{id}/scenes/{scene_id}/muse-video/plan|run|status (routers/scene_muse_video.py).
 * app.js gọi runSceneMuseVideo() thay cho đường cũ (gửi một video 5 giây). Dùng AppState, showToast, escapeHtml,
 * flushProjectSave, mergeServerSceneMedia, renderSceneList, renderPreviewPlayer, saveStateToLocal, API của app.js.
 */
(function () {
  const POLL_MS = 4000;
  const MAX_POLL_MIN = 120;          // mỗi video Muse tới ~20 phút khi hàng đợi bận
  const watching = new Set();

  async function call(method, projectId, sceneId, action) {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/muse-video/${action}`,
      { method });
    let data = null;
    try { data = await res.json(); } catch { /* thân không phải JSON */ }
    if (!res.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Máy chủ trả lỗi HTTP ${res.status}`);
    return data;
  }

  function planMessage(index, plan) {
    const fmt = (s) => `${Number(s).toFixed(1)} giây`;
    const lines = [
      `Cảnh #${index + 1}: lời kể dài ${fmt(plan.narration_seconds)}${plan.estimated ? ' (ước tính, chưa có giọng đọc)' : ''}.`,
      `Cần ${plan.video_count} video Muse = ${plan.video_count} lượt Muse (tài khoản video).`,
    ];
    if (plan.done_videos > 0 && plan.done_videos < plan.video_count) {
      lines.push(`Đã có ${plan.done_videos} video từ lần trước: lần này chỉ làm ${plan.video_count - plan.done_videos} video còn lại.`);
    }
    if (plan.video_count > 1) {
      lines.push('', 'Mỗi video thể hiện một đoạn lời kể (đổi cảnh khi lời kể chuyển nơi, chuyển việc):');
      plan.segments.forEach(s => {
        const t = s.text.length > 110 ? `${s.text.slice(0, 110)}…` : s.text;
        lines.push(`${s.index}. [${fmt(s.seconds)}] ${t}`);
      });
    }
    lines.push('', 'Tiếp tục?');
    return lines.join('\n');
  }

  async function runSceneMuseVideo(index) {
    const project = AppState.currentProject;
    const scene = project?.scenes?.[index];
    if (!scene) return;
    if (project.is_demo) {
      showToast('Đây là dự án mẫu (chỉ để xem). Hãy tạo dự án mới trước khi dùng Muse.', 'warning', 7000);
      return;
    }
    if (!(await flushProjectSave())) {
      showToast('Chưa lưu được dự án lên máy chủ nên chưa gửi việc Muse.', 'error', 7000);
      return;
    }
    let plan;
    try {
      plan = await call('GET', project.id, scene.id, 'plan');
    } catch (err) {
      showToast(`Cảnh #${index + 1}: ${escapeHtml(err.message)}`, 'error', 8000);
      return;
    }
    if (!window.confirm(planMessage(index, plan))) return;
    try {
      const r = await call('POST', project.id, scene.id, 'run');
      showToast(`Cảnh #${index + 1}: đã gửi ${escapeHtml(String(r.muse_calls_needed))} video Muse (tổng ${escapeHtml(String(r.video_count))} video cho cảnh).`, 'success', 6000);
    } catch (err) {
      showToast(`Cảnh #${index + 1}: ${escapeHtml(err.message)}`, 'error', 9000);
      return;
    }
    scene.status_video = 'generating';
    renderSceneList();
    watch(project.id, scene.id, index);
  }

  function watch(projectId, sceneId, index) {
    const key = `${projectId}/${sceneId}`;
    if (watching.has(key)) return;
    watching.add(key);
    const started = Date.now();
    let lastCurrent = null;
    const timer = setInterval(async () => {
      let st;
      try {
        st = await call('GET', projectId, sceneId, 'status');
      } catch (err) {
        console.warn('scene muse video', err);
        return;
      }
      if (st.running && st.current && st.current !== lastCurrent) {
        lastCurrent = st.current;
        showToast(`Cảnh #${index + 1}: Muse đang làm video ${escapeHtml(String(st.current))}/${escapeHtml(String(st.video_count))}…`, 'info', 4000);
      }
      if (st.running && Date.now() - started < MAX_POLL_MIN * 60000) return;
      clearInterval(timer);
      watching.delete(key);
      if (st.status === 'ready') {
        showToast(`Cảnh #${index + 1}: xong video ${escapeHtml(Number(st.video_seconds || 0).toFixed(1))} giây từ ${escapeHtml(String(st.done_videos))} video Muse.`, 'success', 7000);
      } else if (st.status === 'failed') {
        showToast(`Cảnh #${index + 1}: video Muse lỗi (${escapeHtml(st.error || 'không rõ lý do')}). Đã giữ ${escapeHtml(String(st.done_videos))} video xong; bấm lại để làm tiếp.`, 'error', 10000);
      }
      const fresh = await API.getProject(projectId);
      if (fresh && AppState.currentProject?.id === projectId && mergeServerSceneMedia(fresh, sceneId)) {
        const local = AppState.currentProject.scenes.find(s => s.id === sceneId);
        // video ghép luôn cùng tên file: thêm dấu thời gian để trình duyệt không phát bản cũ trong bộ nhớ đệm
        if (local?.video_url && !local.video_url.includes('?')) local.video_url = `${local.video_url}?t=${Date.now()}`;
        saveStateToLocal();
        renderSceneList();
        renderPreviewPlayer();
      } else if (AppState.currentProject?.id === projectId) {
        renderSceneList();
      }
    }, POLL_MS);
  }

  window.runSceneMuseVideo = runSceneMuseVideo;
})();
