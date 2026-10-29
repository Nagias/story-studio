/* Video cho cảnh cao trào (dự án vụ án), Bước 2: chọn cảnh, bật/tắt từng cảnh, chạy Muse, theo dõi tiến độ.
 * API: /api/projects/{id}/climax-video/... (routers/climax_video.py). Tốn lượt Muse khi bấm "Tạo video".
 * Dùng AppState, API, showToast, escapeHtml, renderSceneList, flushProjectSave, mergeServerSceneMedia của app.js
 * (nạp sau app.js). Nhãn và nút trên thẻ cảnh dựng bằng DOM (textContent), không chèn chuỗi HTML; mỗi nút chỉ gắn
 * sự kiện ở đây, không onclick trong index.html (CLAUDE.md đường cấm 9, 10).
 */
(function () {
  const el = (id) => document.getElementById(id);
  const POLL_MS = 4000;
  const cx = { polling: null, running: false, lastSignature: '', cast: null };

  const LABEL = {
    selected: ['🎬 Sẽ làm video', 'bg-purple-50 text-purple-700 border-purple-200'],
    grid: ['🎬 Muse vẽ ảnh 9-grid…', 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse'],
    clips: ['🎬 Muse đang làm video (nhiều bước, 10–75 phút)…', 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse'],
    checking: ['🎬 Đang kiểm video của Muse…', 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse'],
    grid_review: ['🎬 Chờ duyệt grid', 'bg-amber-50 text-amber-700 border-amber-200'],
    grid_approved: ['🎬 Grid đã duyệt, chờ làm clip', 'bg-purple-50 text-purple-700 border-purple-200'],
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
      && ['selected', 'failed', 'grid_approved', ...WORKING].includes(climaxState(s).status)).length;
  }

  function countGridApproved() {
    return (project()?.scenes || []).filter(s => climaxState(s).status === 'grid_approved').length;
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
      const clips = countGridApproved();
      label.textContent = cx.running ? 'Đang tạo video cao trào…'
        : (clips && clips === n ? `Làm clip cho ${n} cảnh đã duyệt grid`
          : (clips ? `Tạo video cho ${n} cảnh (${clips} cảnh làm clip)` : `Vẽ grid cho ${n} cảnh cao trào`));
    }
    const disabled = cx.running || n === 0;
    run.disabled = disabled;
    run.classList.toggle('opacity-30', disabled);
    run.classList.toggle('cursor-not-allowed', disabled);
    pick.disabled = cx.running;
    pick.classList.toggle('opacity-30', cx.running);
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
      ? 'bg-purple-600 text-white border-purple-300' : 'bg-white text-purple-700 border-purple-300'}`;
    btn.textContent = on ? '🎬 Bỏ video' : '🎬 Làm video';
    btn.title = on
      ? 'Bỏ cảnh này khỏi danh sách làm video cao trào (cảnh đã có video thì về lại ảnh, clip vẫn giữ trên đĩa)'
      : 'Làm video cho cảnh này bằng Muse (ảnh 9-grid, duyệt, rồi giao Muse một việc nhiều bước)';
    btn.disabled = cx.running;
    if (cx.running) btn.classList.add('opacity-30', 'cursor-not-allowed');
    btn.addEventListener('click', (ev) => { ev.stopPropagation(); toggleScene(scene.id, !on); });
    return btn;
  }

  function node(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function smallButton(label, cls, onClick) {
    const b = node('button', `text-[10px] px-2 py-0.5 rounded border font-semibold transition ${cls}`, label);
    b.type = 'button';
    b.disabled = cx.running;
    if (cx.running) b.classList.add('opacity-30', 'cursor-not-allowed');
    b.addEventListener('click', (ev) => { ev.stopPropagation(); onClick(); });
    return b;
  }

  // Nhân vật của các cảnh (API Bảng nhân vật); tải lại sau mỗi lần đổi
  async function loadCast() {
    try {
      const res = await fetch(`/api/projects/${encodeURIComponent(project().id)}/characters`);
      cx.cast = res.ok ? await res.json() : null;
    } catch (err) {
      console.warn('climax-video cast', err);
      cx.cast = null;
    }
  }

  async function setCast(sceneId, ids) {
    try {
      const res = await fetch(`/api/projects/${encodeURIComponent(project().id)}/scenes/${encodeURIComponent(sceneId)}/cast`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entity_ids: ids }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
      await loadCast();
      decorateCards();
    } catch (err) {
      showToast(`Không đổi được nhân vật của cảnh: ${escapeHtml(err.message)}`, 'error', 7000);
    }
  }

  async function gridAction(sceneId, action, body) {
    try {
      if (!(await flushProjectSave({ silent: true }))) throw new Error('chưa lưu được dự án, thử lại sau');
      await call('POST', `/scenes/${encodeURIComponent(sceneId)}/grid/${action}`, body);
      await pullScenes([sceneId]);
      renderSceneList();
      showToast(action === 'approve' ? 'Đã duyệt grid. Bấm nút tạo video để làm clip.' : 'Đã ghi chỗ sai. Bấm nút tạo video để vẽ lại grid.', 'success', 5000);
    } catch (err) {
      showToast(`Grid: ${escapeHtml(err.message)}`, 'error', 7000);
    }
  }

  // Dòng dưới thanh trên của thẻ cảnh đang làm video: nhân vật của cảnh, ảnh grid chờ duyệt
  function panelFor(scene) {
    const state = climaxState(scene);
    const box = node('div', 'climax-video-panel mb-3 p-2 rounded-lg border border-purple-200 bg-purple-50 space-y-2 text-[11px]');
    const chars = Object.fromEntries((cx.cast?.characters || []).map(c => [c.entity_id, c]));
    const ids = (cx.cast?.scene_cast || {})[scene.id] || [];
    const row = node('div', 'flex items-center gap-1 flex-wrap');
    row.appendChild(node('span', 'font-semibold text-slate-700', 'Nhân vật:'));
    if (!ids.length) row.appendChild(node('span', 'text-red-700', 'chưa chọn (bắt buộc để khoá nhân vật)'));
    for (const eid of ids) {
      const c = chars[eid];
      const ok = c && c.status === 'approved';
      const chip = node('span', `px-2 py-0.5 rounded border ${ok ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`,
        `${c ? c.name_vi : eid}${ok ? '' : ' (chưa duyệt bảng)'}`);
      row.appendChild(chip);
      row.appendChild(smallButton('×', 'bg-white text-slate-600 border-slate-300', () => setCast(scene.id, ids.filter(x => x !== eid))));
    }
    const add = node('select', 'text-[10px] border border-slate-300 rounded px-1 py-0.5 bg-white');
    add.appendChild(node('option', '', '+ thêm nhân vật'));
    for (const c of cx.cast?.characters || []) {
      if (ids.includes(c.entity_id)) continue;
      const o = node('option', '', c.name_vi);
      o.value = c.entity_id;
      add.appendChild(o);
    }
    add.disabled = cx.running;
    add.addEventListener('change', () => { if (add.value) setCast(scene.id, [...ids, add.value]); });
    row.appendChild(add);
    box.appendChild(row);

    if (state.status === 'grid_review' && state.grid_count !== 0) {
      const grids = node('div', 'flex gap-2 flex-wrap');
      const n = (state.grid_paths || []).length || 1;
      for (let i = 1; i <= n; i++) {
        const url = `/api/projects/${encodeURIComponent(project().id)}/climax-video/scenes/${encodeURIComponent(scene.id)}/grid?i=${i}&v=${state.grid_version || 1}`;
        const a = node('a');
        a.href = url;
        a.target = '_blank';
        a.rel = 'noopener';
        const img = node('img', 'rounded border border-slate-300');
        img.src = url;
        img.alt = `Ảnh 9-grid ${i}`;
        img.style.width = '220px';
        a.appendChild(img);
        grids.appendChild(a);
      }
      box.appendChild(grids);
      const act = node('div', 'flex gap-1 flex-wrap items-center');
      act.appendChild(smallButton('Duyệt grid', 'bg-emerald-50 text-emerald-700 border-emerald-200', () => gridAction(scene.id, 'approve')));
      const note = node('input', 'flex-1 min-w-0 border border-slate-300 rounded px-2 py-0.5 text-[11px]');
      note.placeholder = 'Grid sai chỗ nào? (bắt buộc khi vẽ lại)';
      act.appendChild(note);
      act.appendChild(smallButton('Vẽ lại grid', 'bg-amber-50 text-amber-700 border-amber-200', () => gridAction(scene.id, 'reject', { feedback: note.value })));
      box.appendChild(act);
    }
    if (state.error) box.appendChild(node('p', 'text-red-700', state.error));
    if (state.status === 'ready' || state.status === 'failed') box.appendChild(resultFor(scene, state));
    return box;
  }

  // Kết quả của việc giao Muse nhiều bước: báo cáo của Muse, cảnh báo, ảnh cảnh đã thay, nút làm lại
  function resultFor(scene, state) {
    const wrap = node('div', 'space-y-1');
    if (state.scene_image_updated) {
      const name = String(state.backup_image || '').split(/[\\/]/).pop();
      wrap.appendChild(node('p', 'text-emerald-700', `Đã thay ảnh cảnh bằng ảnh Muse sửa (bản cũ: ${name})`));
    }
    for (const w of state.warnings || []) wrap.appendChild(node('p', 'text-amber-700', `⚠ ${w}`));
    if (state.muse_report) {
      const det = node('details', 'bg-white rounded border border-slate-200 px-2 py-1');
      det.appendChild(node('summary', 'cursor-pointer font-semibold text-slate-700', 'Báo cáo của Muse'));
      const pre = node('pre', 'whitespace-pre-wrap text-[10px] text-slate-700 max-h-48 overflow-auto', state.muse_report);
      pre.dataset.climaxReport = scene.id;
      det.appendChild(pre);
      wrap.appendChild(det);
    }
    if (state.grid_approved) {
      const b = smallButton('↻ Làm lại cảnh này', 'bg-white text-purple-700 border-purple-300', () => redo(scene.id));
      b.dataset.climaxRedo = scene.id;
      wrap.appendChild(b);
    }
    return wrap;
  }

  async function redo(sceneId) {
    const ok = window.confirm('Làm lại video cảnh này? Muse làm lại từ đầu trong chat mới, tốn tối đa 6 video + 4 ảnh '
      + 'Muse (10–75 phút). Grid đã duyệt giữ nguyên; ảnh cảnh gốc vẫn giữ ở bản dự phòng.');
    if (!ok) return;
    try {
      await flushProjectSave({ silent: true });
      await call('POST', `/scenes/${encodeURIComponent(sceneId)}/redo`);
      await pullScenes([sceneId]);
      renderSceneList();
      showToast('Cảnh đã về chờ làm video. Bấm nút tạo video để chạy.', 'info', 6000);
    } catch (err) {
      showToast(`Không làm lại được: ${escapeHtml(err.message)}`, 'error', 7000);
    }
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
      card.querySelectorAll('.climax-video-panel').forEach(n => n.remove());
      if (climaxState(scene).status && cx.cast) {
        bar.parentElement.insertAdjacentElement('afterend', panelFor(scene));
      }
    }
  }

  function signature(scenes) {
    return JSON.stringify((scenes || []).map(s => [s.scene_id, s.status, s.done, s.error, s.grid_version, s.video_seconds]));
  }

  async function toggleScene(sceneId, enabled) {
    try {
      await flushProjectSave({ silent: true });
      await call('PUT', `/scenes/${encodeURIComponent(sceneId)}`, { enabled });
      await pullScenes([sceneId]);
      await loadCast();
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
      await loadCast();
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
    const ok = window.confirm(`Chạy Muse (tài khoản video) cho ${n} cảnh?

Cảnh chưa có grid: vẽ ảnh 9-grid (1 grid mỗi 45 giây lời kể) `
      + 'rồi dừng chờ bạn duyệt. Cảnh đã duyệt grid: giao Muse một việc nhiều bước (Muse tự làm, tự kiểm, làm lại), tối đa '
      + '6 video + 4 ảnh Muse và 10–75 phút mỗi cảnh; lỗi thì giữ ảnh, không tự thử lại. Chạy nền, lần lượt từng cảnh.');
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
      await loadCast();
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
      await loadCast();
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
