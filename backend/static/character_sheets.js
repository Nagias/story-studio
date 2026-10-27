/* Bảng nhân vật đủ góc (dự án vụ án), Bước 2: sửa thiết kế, Muse vẽ bảng, duyệt, vẽ lại có ghi chú chỗ sai.
 * API: /api/projects/{id}/characters... (routers/character_sheets.py). "Vẽ bảng" tốn 1 lượt Muse (tài khoản video).
 * Dùng AppState, showToast, escapeHtml của app.js (nạp sau app.js). Mọi phần tử dựng bằng DOM + textContent, không chèn
 * chuỗi HTML; nút chỉ gắn sự kiện ở đây (CLAUDE.md đường cấm 9, 10).
 */
(function () {
  const el = (id) => document.getElementById(id);
  const POLL_MS = 5000;
  const st = { data: null, timer: null, showAll: false };

  const STATUS = {
    draft: ['Chưa có bảng', 'bg-slate-100 text-slate-600 border-slate-200'],
    drawing: ['Muse đang vẽ…', 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse'],
    review: ['Chờ duyệt', 'bg-amber-50 text-amber-700 border-amber-200'],
    approved: ['Đã duyệt', 'bg-emerald-50 text-emerald-700 border-emerald-200'],
    failed: ['Vẽ lỗi', 'bg-red-50 text-red-700 border-red-200'],
  };

  const project = () => AppState.currentProject;
  const isCaseProject = () => {
    const p = project();
    return Boolean(p && !p.is_demo && (p.scenes || []).some(s => ['image', 'video'].includes(s.metadata?.visual_kind)));
  };

  async function call(method, path, body) {
    const res = await fetch(`/api/projects/${encodeURIComponent(project().id)}/characters${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch { /* thân không phải JSON */ }
    if (!res.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Máy chủ trả lỗi HTTP ${res.status}`);
    return data;
  }

  function node(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function button(label, cls, onClick, disabled = false) {
    const b = node('button', `text-xs px-3 py-1.5 rounded-lg border font-semibold transition ${cls}`, label);
    b.type = 'button';
    b.disabled = disabled;
    if (disabled) b.classList.add('opacity-30', 'cursor-not-allowed');
    b.addEventListener('click', onClick);
    return b;
  }

  async function act(fn, okMsg) {
    try {
      await fn();
      if (okMsg) showToast(okMsg, 'success', 3500);
    } catch (err) {
      showToast(`Bảng nhân vật: ${escapeHtml(err.message)}`, 'error', 7000);
    }
    await refresh();
  }

  function card(c, scenesOf) {
    const drawing = c.drawing || c.status === 'drawing';
    const box = node('div', 'border border-slate-200 rounded-xl p-3 bg-white flex flex-wrap gap-3');
    const left = node('div', 'flex-1 min-w-0 space-y-2');
    const head = node('div', 'flex items-center gap-2 flex-wrap');
    head.appendChild(node('span', 'text-sm font-bold text-slate-900', c.name_vi));
    head.appendChild(node('span', 'text-[11px] text-slate-500', c.role));
    const [label, cls] = STATUS[drawing ? 'drawing' : c.status] || [c.status, STATUS.draft[1]];
    head.appendChild(node('span', `text-[11px] px-2 py-0.5 rounded border font-semibold ${cls}`, label));
    left.appendChild(head);
    if (scenesOf.length) left.appendChild(node('p', 'text-[11px] text-slate-500', `Có mặt ở: ${scenesOf.join(', ')}`));
    if (c.error) left.appendChild(node('p', 'text-[11px] text-red-700', c.error));
    const design = node('textarea', 'w-full border border-slate-300 rounded-lg p-2 text-[11px] font-mono');
    design.rows = 7;
    design.value = c.design_en;
    design.disabled = drawing;
    left.appendChild(design);
    if (c.feedback?.length) {
      left.appendChild(node('p', 'text-[11px] text-amber-700', `Đã ghi chỗ sai: ${c.feedback.join(' | ')}`));
    }
    const note = node('input', 'w-full border border-slate-300 rounded-lg p-2 text-[11px]');
    note.placeholder = 'Bảng sai chỗ nào? (bắt buộc khi Vẽ lại, vd: tóc góc sau phủ kín đầu, góc trước lại hói)';
    left.appendChild(note);
    const actions = node('div', 'flex flex-wrap gap-2');
    const eid = encodeURIComponent(c.entity_id);
    actions.appendChild(button('Lưu thiết kế', 'bg-white text-slate-700 border-slate-300', () =>
      act(() => call('PUT', `/${eid}`, { design_en: design.value }), 'Đã lưu thiết kế'), drawing));
    actions.appendChild(button(c.versions ? 'Vẽ bảng mới' : 'Vẽ bảng (Muse)', 'bg-purple-600 text-white border-purple-300', () =>
      act(() => call('POST', `/${eid}/draw`), 'Đã gửi Muse vẽ bảng'), drawing));
    actions.appendChild(button('Duyệt', 'bg-emerald-50 text-emerald-700 border-emerald-200', () =>
      act(() => call('POST', `/${eid}/approve`), 'Đã duyệt bảng'), drawing || !c.sheet_url || c.status === 'approved'));
    actions.appendChild(button('Ghi chỗ sai rồi vẽ lại', 'bg-amber-50 text-amber-700 border-amber-200', () =>
      act(async () => {
        await call('POST', `/${eid}/reject`, { feedback: note.value });
        await call('POST', `/${eid}/draw`);
      }, 'Đã gửi Muse vẽ lại'), drawing || !c.sheet_url));
    left.appendChild(actions);
    box.appendChild(left);
    const right = node('div', 'shrink-0');
    right.style.width = '340px';
    right.style.maxWidth = '100%';
    if (c.sheet_url) {
      const a = node('a');
      a.href = c.sheet_url;
      a.target = '_blank';
      a.rel = 'noopener';
      const img = node('img', 'w-full rounded-lg border border-slate-200');
      img.src = c.sheet_url;
      img.alt = `Bảng nhân vật ${c.name_vi}`;
      a.appendChild(img);
      right.appendChild(a);
      right.appendChild(node('p', 'text-[10px] text-slate-500 mt-1', `Phiên bản ${c.versions} — bấm ảnh để xem cỡ thật`));
    } else {
      right.appendChild(node('div', 'w-full aspect-video rounded-lg bg-slate-100 flex items-center justify-center text-slate-500', 'Chưa có bảng'));
    }
    box.appendChild(right);
    return box;
  }

  function render() {
    const list = el('character-sheets-list');
    if (!list || !st.data) return;
    list.replaceChildren();
    const sceneIndex = {};
    (project()?.scenes || []).forEach((s, i) => { sceneIndex[s.id] = i + 1; });
    const scenesOf = {};
    for (const [sid, ids] of Object.entries(st.data.scene_cast || {})) {
      for (const eid of ids) (scenesOf[eid] = scenesOf[eid] || []).push(`#${sceneIndex[sid] || sid}`);
    }
    const needed = new Set(st.data.needed || []);
    const chars = (st.data.characters || []).filter(c => st.showAll || needed.has(c.entity_id) || c.status !== 'draft');
    const bar = node('div', 'flex items-center justify-between');
    bar.appendChild(node('p', 'text-slate-600', needed.size
      ? `Cần cho các cảnh đang chọn làm video: ${needed.size} nhân vật.`
      : 'Chưa chọn cảnh cao trào nào (nút "Chọn cảnh cao trào"), hoặc các cảnh đó chưa có nhân vật.'));
    bar.appendChild(button(st.showAll ? 'Chỉ hiện người cần' : `Hiện cả ${st.data.characters.length} người`,
      'bg-white text-slate-700 border-slate-300', () => { st.showAll = !st.showAll; render(); }));
    list.appendChild(bar);
    if (!chars.length) list.appendChild(node('p', 'text-slate-500', 'Không có nhân vật nào để hiện.'));
    chars.forEach(c => list.appendChild(card(c, scenesOf[c.entity_id] || [])));
  }

  async function refresh() {
    if (!project() || !isCaseProject()) return;
    try {
      st.data = await call('GET', '');
      render();
    } catch (err) {
      console.warn('character sheets', err);
    }
  }

  function open() {
    el('modal-character-sheets')?.classList.remove('hidden');
    refresh();
    clearInterval(st.timer);
    st.timer = setInterval(() => {
      if ((st.data?.characters || []).some(c => c.drawing)) refresh();
    }, POLL_MS);
  }

  function close() {
    el('modal-character-sheets')?.classList.add('hidden');
    clearInterval(st.timer);
    st.timer = null;
  }

  function init() {
    el('btn-character-sheets')?.addEventListener('click', open);
    el('btn-close-character-sheets')?.addEventListener('click', close);
    document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') close(); });
    let lastId = null;
    setInterval(() => {   // nút chỉ hiện với dự án vụ án; đổi dự án thì đóng cửa sổ
      const id = project()?.id || null;
      el('btn-character-sheets')?.classList.toggle('hidden', !isCaseProject());
      if (id !== lastId) { lastId = id; st.data = null; close(); }
    }, 1000);
  }

  window.refreshCharacterSheets = refresh;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
