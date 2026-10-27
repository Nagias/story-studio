/* Video cho cảnh cao trào (dự án vụ án), Bước 2: chọn cảnh, bật/tắt từng cảnh, chạy Muse, theo dõi tiến độ.
 * API: /api/projects/{id}/climax-video/... (routers/climax_video.py). Tốn lượt Muse khi bấm "Tạo video".
 * Dùng AppState, API, showToast, escapeHtml, renderSceneList, flushProjectSave, mergeServerSceneMedia của app.js
 * (nạp sau app.js). Nhãn và nút trên thẻ cảnh dựng bằng DOM (textContent), không chèn chuỗi HTML; mỗi nút chỉ gắn
 * sự kiện ở đây, không onclick trong index.html (CLAUDE.md đường cấm 9, 10).
 */
(function () {
  const el = (id) => document.getElementById(id);
  const POLL_MS = 4000;
  const cx = { polling: null, running: false, lastSignature: '' };

  const LABEL = {
    selected: ['🎬 Sẽ làm video', 'bg-purple-50 text-purple-700 border-purple-200'],
    grid: ['🎬 Muse vẽ ảnh 9-grid…', 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse'],
    clips: ['🎬 Muse làm clip…', 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse'],
    checking: ['🎬 Đang ghép clip…', 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse'],
    ready: ['🎬 Đã có video cao trào', 'bg-emerald-50 text-emerald-700 border-emerald-200'],
    failed: ['🎬 Video lỗi, giữ ảnh', 'bg-red-50 text-red-700 border-red-200'],
  };
  const WORKING = ['grid', 'clips', 'checking'];

  function project() { return AppState.currentProject; }

  function isEligible(scene) {
    const kind = scene && scene.metadata && scene.metadata.visual_kind;
    return kind === 'image' || kind === 'video';
  }

  function isCaseProject() {
    const p = project();
    return Boolean(p && !p.is_demo && (p.scenes || []).some(isEligible));
  }

  function climaxState(scene) {
    const v = scene && scene.metadata && scene.metadata.climax_video;
    return v && typeof v === 'object' ? v : {};
  }

  async function call(method, path, body) {
    const p = project();
    const res = await fetch(`/api/projects/${encodeURIComponent(p.id)}/climax-video${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch { /* thân không phải JSON */ }
    if (!res.ok) {
      const detail = data && data.detail;
      throw new Error(typeof detail === 'string' ? detail : `Máy chủ trả lỗi HTTP ${res.status}`);
    }
    return data;
  }

  // Lấy bản mới của dự án từ máy chủ và gộp phần media/metadata của các cảnh vào bản đang mở (app.js)
  async function pullScenes(sceneIds) {
    const p = project();
    const remote = await API.getProject(p.id);
    if (!remote || !remote.scenes) return false;
    let changed = false;
    for (const s of p.scenes || []) {
      if (!sceneIds || sceneIds.includes(s.id)) changed = mergeServerSceneMedia(remote, s.id) || changed;
    }
    return changed;
  }

  function countRunnable() {
    return (project()?.scenes || []).filter(s => isEligible(s)
      && ['selected', 'failed', ...WORKING].includes(climaxState(s).status)).length;
  }

  function refreshButtons() {
    const pick = el('btn-climax-video-pick');
    const run = el('btn-climax-video-run');
    if (!pick || !run) return;
    const show = isCaseProject();
    pick.classList.toggle('hidden', !show);
    run.classList.toggle('hidden', !show);
    if (!show) return;
    const n = countRunnable();
    const label = run.querySelector('span');
    if (label) {
      label.textContent = cx.running ? 'Đang tạo video cao trào…' : `Tạo video cho ${n} cảnh cao trào`;
    }
    const disabled = cx.running || n === 0;
    run.disabled = disabled;
    run.classList.toggle('opacity-50', disabled);
    run.classList.toggle('cursor-not-allowed', disabled);
    pick.disabled = cx.running;
    pick.classList.toggle('opacity-50', cx.running);
  }

  function badgeFor(scene) {
    const state = climaxState(scene);
    const status = state.status;
    if (!status) return null;
    let [text, cls] = LABEL[status] || [`🎬 ${status}`, 'bg-slate-100 text-slate-600 border-slate-200'];
    if (WORKING.includes(status) && !cx.running) {
      [text, cls] = ['🎬 Bị ngắt giữa chừng', 'bg-amber-50 text-amber-700 border-amber-200'];
    } else if (status === 'clips' && state.done !== undefined) {
      text = `${text} (xong ${state.done})`;
    }
    const span = document.createElement('span');
    span.className = `climax-video-badge text-[11px] px-2 py-0.5 rounded border font-semibold ${cls}`;
    span.textContent = text;
    if (state.error) span.title = state.error;
    return span;
  }

  function toggleFor(scene) {
    const status = climaxState(scene).status;
    const on = Boolean(status);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `climax-video-toggle text-[10px] px-2 py-0.5 rounded border font-semibold transition ${on
      ? 'bg-purple-600 text-white border-purple-500' : 'bg-white text-purple-700 border-purple-300'}`;
    btn.textContent = on ? '🎬 Bỏ video' : '🎬 Làm video';
    btn.title = on
      ? 'Bỏ cảnh này khỏi danh sách làm video cao trào (cảnh đã có video thì về lại ảnh, clip vẫn giữ trên đĩa)'
      : 'Làm video cho cảnh này bằng Muse (ảnh 9-grid rồi các clip 5 giây)';
    btn.disabled = cx.running;
    if (cx.running) btn.classList.add('opacity-50', 'cursor-not-allowed');
    btn.addEventListener('click', (ev) => { ev.stopPropagation(); toggleScene(scene.id, !on); });
    return btn;
  }

  // Gắn nhãn và nút vào thẻ cảnh do renderSceneList() (app.js) vẽ
  function decorateCards() {
    refreshButtons();
    if (!isCaseProject()) return;
    for (const scene of project().scenes || []) {
      if (!isEligible(scene)) continue;
      const card = document.getElementById(`scene-card-${scene.id}`);
      const bar = card && card.querySelector('.flex.items-center.justify-between > .flex.items-center.gap-2');
      if (!bar) continue;
      bar.querySelectorAll('.climax-video-badge, .climax-video-toggle').forEach(n => n.remove());
      const badge = badgeFor(scene);
      if (badge) bar.appendChild(badge);
      bar.appendChild(toggleFor(scene));
    }
  }

  function signature(scenes) {
    return JSON.stringify((scenes || []).map(s => [s.scene_id, s.status, s.done, s.error]));
  }

  async function toggleScene(sceneId, enabled) {
    try {
      await flushProjectSave({ silent: true });
      await call('PUT', `/scenes/${encodeURIComponent(sceneId)}`, { enabled });
      await pullScenes([sceneId]);
      renderSceneList();
    } catch (err) {
      showToast(`Không đổi được cảnh: ${escapeHtml(err.message)}`, 'error', 7000);
    }
  }

  async function pick() {
    try {
      await flushProjectSave({ silent: true });
      const data = await call('POST', '/pick');
      await pullScenes(null);
      renderSceneList();
      const n = (data.scene_ids || []).length;
      showToast(n
        ? `Đã chọn ${escapeHtml(n)} cảnh cao trào (tối đa ${escapeHtml(data.limit)}). Bật/tắt từng cảnh trên thẻ rồi bấm "Tạo video".`
        : 'Không có cảnh nào đủ dấu hiệu cao trào; bật tay từng cảnh trên thẻ cảnh.', n ? 'success' : 'info', 6000);
    } catch (err) {
      showToast(`Không chọn được cảnh: ${escapeHtml(err.message)}`, 'error', 7000);
    }
  }

  async function run() {
    const n = countRunnable();
    if (!n) return;
    const ok = window.confirm(`Tạo video cho ${n} cảnh bằng Muse?\n\nMỗi cảnh: 1 ảnh 9-grid (thêm 1 grid cho mỗi 45 giây lời kể) `
      + 'và 1 clip 5 giây cho mỗi 5 giây lời kể; clip lỗi thì thử lại 1 lần. Chạy nền, có thể mất nhiều phút mỗi cảnh.');
    if (!ok) return;
    try {
      await flushProjectSave({ silent: true });
      const data = await call('POST', '/run');
      cx.running = true;
      refreshButtons();
      showToast(`Đã đưa ${escapeHtml((data.queued || []).length)} cảnh vào hàng làm video Muse.`, 'info', 5000);
      startPolling();
    } catch (err) {
      showToast(`Không chạy được: ${escapeHtml(err.message)}`, 'error', 7000);
    }
  }

  async function poll() {
    const p = project();
    if (!p || !isCaseProject()) { stopPolling(); return; }
    let data;
    try {
      data = await call('GET', '/status');
    } catch (err) {
      console.warn('climax-video status', err);
      return;
    }
    const wasRunning = cx.running;
    cx.running = Boolean(data.running);
    const sig = signature(data.scenes);
    if (sig !== cx.lastSignature || wasRunning !== cx.running) {
      cx.lastSignature = sig;
      await pullScenes((data.scenes || []).map(s => s.scene_id));
      renderSceneList();
    }
    if (wasRunning && !cx.running) {
      stopPolling();
      const ready = (data.scenes || []).filter(s => s.status === 'ready').length;
      const failed = (data.scenes || []).filter(s => s.status === 'failed');
      showToast(`Xong lượt làm video cao trào: ${escapeHtml(ready)} cảnh có video, ${escapeHtml(failed.length)} cảnh lỗi`
        + (failed.length ? ' (rê chuột lên nhãn đỏ để xem lý do).' : '.'), failed.length ? 'warning' : 'success', 8000);
    }
  }

  function startPolling() {
    stopPolling();
    cx.polling = setInterval(poll, POLL_MS);
  }

  function stopPolling() {
    if (cx.polling) clearInterval(cx.polling);
    cx.polling = null;
  }

  // Mở dự án (hoặc tải lại trang khi đang chạy nền): hỏi trạng thái một lần, đang chạy thì theo dõi tiếp
  async function checkOnce() {
    if (!isCaseProject()) return;
    try {
      const data = await call('GET', '/status');
      cx.running = Boolean(data.running);
      cx.lastSignature = signature(data.scenes);
      if (cx.running) startPolling();
      decorateCards();
    } catch (err) {
      console.warn('climax-video status', err);
    }
  }

  function init() {
    el('btn-climax-video-pick')?.addEventListener('click', pick);
    el('btn-climax-video-run')?.addEventListener('click', run);
    const container = el('scene-list-container');
    if (container) new MutationObserver(decorateCards).observe(container, { childList: true });
    let lastProjectId = null;
    setInterval(() => {   // đổi dự án (switchProject trong app.js): hỏi lại trạng thái của dự án mới
      const id = project()?.id || null;
      if (id !== lastProjectId) {
        lastProjectId = id;
        stopPolling();
        cx.running = false;
        cx.lastSignature = '';
        checkOnce();
        decorateCards();
      }
    }, 1000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
