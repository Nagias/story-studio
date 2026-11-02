/* Khoá bối cảnh (Bước 2): nơi lặp lại ở từ 2 cảnh trở lên có mô tả cố định và ảnh chuẩn; chủ dự án xem, sửa mô tả
 * và danh sách cảnh, cho Muse vẽ ảnh chuẩn, ghi chỗ sai rồi vẽ lại, duyệt. Chỉ bối cảnh ĐÃ DUYỆT mới được dùng khi tạo
 * ảnh / video cảnh. API: /api/projects/{id}/locations... (routers/location_sheets.py).
 * "Tìm bối cảnh lặp lại" tốn 1 lượt LLM; "Vẽ ảnh chuẩn" tốn 1 lượt Muse (tài khoản ảnh).
 * Dùng AppState, showToast, escapeHtml của app.js (nạp sau app.js). Mọi phần tử dựng bằng DOM + textContent, không chèn
 * chuỗi HTML; nút chỉ gắn sự kiện ở đây (CLAUDE.md đường cấm 9, 10).
 */
(function () {
  const el = (id) => document.getElementById(id);
  const POLL_MS = 4000;
  const st = { data: null, timer: null };

  const STATUS = {
    draft: ['Chưa có ảnh chuẩn', 'bg-slate-100 text-slate-600 border-slate-200'],
    drawing: ['Muse đang vẽ…', 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse'],
    review: ['Chờ duyệt', 'bg-amber-50 text-amber-700 border-amber-200'],
    approved: ['Đã duyệt — đang khoá', 'bg-emerald-50 text-emerald-700 border-emerald-200'],
    failed: ['Vẽ lỗi', 'bg-red-50 text-red-700 border-red-200'],
  };

  const project = () => AppState.currentProject;
  const scenes = () => project()?.scenes || [];
  const usable = () => {
    const p = project();
    return Boolean(p && !p.is_demo && scenes().length >= 2);
  };

  async function call(method, path, body) {
    const res = await fetch(`/api/projects/${encodeURIComponent(project().id)}/locations${path}`, {
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
      if (okMsg) showToast(escapeHtml(okMsg), 'success', 3500);
    } catch (err) {
      showToast(`Bối cảnh: ${escapeHtml(err.message)}`, 'error', 7000);
    }
    await refresh();
  }

  // Số thứ tự cảnh trên giao diện (#1, #2...) <-> id cảnh
  const sceneNo = (sid) => {
    const i = scenes().findIndex(s => s.id === sid);
    return i >= 0 ? `#${i + 1}` : sid;
  };
  function parseScenes(text) {
    const ids = [];
    for (const raw of String(text || '').split(/[\s,;]+/)) {
      const t = raw.replace(/^#/, '').trim();
      if (!t) continue;
      const n = Number(t);
      if (Number.isInteger(n) && n >= 1 && n <= scenes().length) ids.push(scenes()[n - 1].id);
      else throw new Error(`Không có cảnh số "${t}" (ghi số cảnh như 3, 5, 12)`);
    }
    return ids;
  }

  function card(loc) {
    const drawing = loc.drawing || loc.status === 'drawing';
    const box = node('div', 'border border-slate-200 rounded-xl p-3 bg-white flex flex-wrap gap-3');
    box.dataset.locationId = loc.location_id;
    const left = node('div', 'flex-1 min-w-0 space-y-2');
    const head = node('div', 'flex items-center gap-2 flex-wrap');
    const name = node('input', 'border border-slate-300 rounded-lg px-2 py-1 text-sm font-bold text-slate-900');
    name.value = loc.name_vi;
    name.disabled = drawing;
    head.appendChild(name);
    const [label, cls] = STATUS[drawing ? 'drawing' : loc.status] || [loc.status, STATUS.draft[1]];
    head.appendChild(node('span', `text-[11px] px-2 py-0.5 rounded border font-semibold ${cls}`, label));
    if (loc.source === 'manual') head.appendChild(node('span', 'text-[11px] text-slate-500', 'tự thêm'));
    left.appendChild(head);
    const sceneRow = node('label', 'flex items-center gap-2 text-[11px] text-slate-600');
    sceneRow.appendChild(node('span', '', `Cảnh (${loc.scene_ids.length}):`));
    const sceneInput = node('input', 'flex-1 border border-slate-300 rounded-lg px-2 py-1 text-[11px]');
    sceneInput.value = loc.scene_ids.map(sceneNo).join(', ');
    sceneInput.disabled = drawing;
    sceneRow.appendChild(sceneInput);
    left.appendChild(sceneRow);
    if (loc.error) left.appendChild(node('p', 'text-[11px] text-red-700', loc.error));
    left.appendChild(node('p', 'text-[11px] text-slate-500', 'Mô tả cố định (tiếng Anh, gửi nguyên văn cho Muse ở mọi cảnh của nơi này):'));
    const design = node('textarea', 'w-full border border-slate-300 rounded-lg p-2 text-[11px] font-mono');
    design.rows = 5;
    design.value = loc.design_en;
    design.disabled = drawing;
    left.appendChild(design);
    if (loc.feedback?.length) {
      left.appendChild(node('p', 'text-[11px] text-amber-700', `Đã ghi chỗ sai: ${loc.feedback.join(' | ')}`));
    }
    const note = node('input', 'w-full border border-slate-300 rounded-lg p-2 text-[11px]');
    note.placeholder = 'Ảnh chuẩn sai chỗ nào? (bắt buộc khi Vẽ lại, vd: cửa sổ phải ở bên trái, không có người)';
    left.appendChild(note);
    const actions = node('div', 'flex flex-wrap gap-2');
    const lid = encodeURIComponent(loc.location_id);
    actions.appendChild(button('Lưu', 'bg-white text-slate-700 border-slate-300', () =>
      act(() => call('PUT', `/${lid}`, { name_vi: name.value, design_en: design.value, scene_ids: parseScenes(sceneInput.value) }),
        'Đã lưu bối cảnh'), drawing));
    actions.appendChild(button(loc.versions ? 'Vẽ ảnh chuẩn mới' : 'Vẽ ảnh chuẩn (Muse)', 'bg-purple-600 text-white border-purple-300', () =>
      act(() => call('POST', `/${lid}/draw`), 'Đã gửi Muse vẽ ảnh chuẩn (1 lượt Muse ảnh)'), drawing));
    actions.appendChild(button('Duyệt', 'bg-emerald-50 text-emerald-700 border-emerald-200', () =>
      act(() => call('POST', `/${lid}/approve`), 'Đã duyệt: ảnh cảnh của nơi này sẽ dùng mô tả và ảnh chuẩn'),
      drawing || !loc.plate_url || loc.status === 'approved'));
    actions.appendChild(button('Ghi chỗ sai rồi vẽ lại', 'bg-amber-50 text-amber-700 border-amber-200', () =>
      act(async () => {
        await call('POST', `/${lid}/reject`, { feedback: note.value });
        await call('POST', `/${lid}/draw`);
      }, 'Đã gửi Muse vẽ lại'), drawing || !loc.plate_url));
    actions.appendChild(button('Bỏ bối cảnh', 'bg-white text-red-700 border-red-200', () => {
      if (!window.confirm(`Bỏ bối cảnh "${loc.name_vi}"? Các cảnh của nó thôi khoá; ảnh chuẩn đã vẽ vẫn giữ trên máy.`)) return;
      act(() => call('DELETE', `/${lid}`), 'Đã bỏ bối cảnh');
    }, drawing));
    left.appendChild(actions);
    box.appendChild(left);
    const right = node('div', 'shrink-0');
    right.style.width = '340px';
    right.style.maxWidth = '100%';
    if (loc.plate_url) {
      const a = node('a');
      a.href = loc.plate_url;
      a.target = '_blank';
      a.rel = 'noopener';
      const img = node('img', 'w-full rounded-lg border border-slate-200');
      img.src = loc.plate_url;
      img.alt = `Ảnh chuẩn bối cảnh ${loc.name_vi}`;
      a.appendChild(img);
      right.appendChild(a);
      right.appendChild(node('p', 'text-[10px] text-slate-500 mt-1', `Phiên bản ${loc.versions} — bấm ảnh để xem cỡ thật`));
    } else {
      right.appendChild(node('div', 'w-full aspect-video rounded-lg bg-slate-100 flex items-center justify-center text-slate-500', 'Chưa có ảnh chuẩn'));
    }
    box.appendChild(right);
    return box;
  }

  function addForm() {
    const box = node('details', 'border border-dashed border-slate-300 rounded-xl p-3 bg-slate-50');
    box.appendChild(node('summary', 'text-xs font-semibold text-slate-700 cursor-pointer', '+ Tự thêm một bối cảnh'));
    const name = node('input', 'w-full border border-slate-300 rounded-lg px-2 py-1 text-xs mt-2');
    name.placeholder = 'Tên (vd: Hành lang đồn cảnh sát)';
    const sc = node('input', 'w-full border border-slate-300 rounded-lg px-2 py-1 text-xs mt-2');
    sc.placeholder = 'Số các cảnh ở nơi này, ít nhất 2 (vd: 4, 6, 15)';
    const design = node('textarea', 'w-full border border-slate-300 rounded-lg p-2 text-[11px] font-mono mt-2');
    design.rows = 4;
    design.placeholder = 'Mô tả cố định bằng tiếng Anh, ít nhất 25 từ: kiến trúc, bố cục, đồ vật cố định, màu sắc, nguồn sáng';
    box.append(name, sc, design);
    const row = node('div', 'mt-2');
    row.appendChild(button('Thêm bối cảnh', 'bg-white text-slate-700 border-slate-300', () =>
      act(() => call('POST', '', { name_vi: name.value, design_en: design.value, scene_ids: parseScenes(sc.value) }),
        'Đã thêm bối cảnh')));
    box.appendChild(row);
    return box;
  }

  function render() {
    const list = el('location-sheets-list');
    if (!list || !st.data) return;
    list.replaceChildren();
    const d = st.data;
    const bar = node('div', 'flex items-center justify-between gap-2 flex-wrap');
    const approved = d.locations.filter(l => l.status === 'approved').length;
    bar.appendChild(node('p', 'text-slate-600', d.analyzing
      ? 'AI đang đọc các cảnh để tìm nơi lặp lại…'
      : (d.locations.length
        ? `${d.locations.length} bối cảnh lặp lại, ${approved} đã duyệt (đang khoá ảnh cảnh).`
        : `Chưa có bối cảnh nào. Bấm "Tìm bối cảnh lặp lại" (AI đọc ${d.eligible_scenes} cảnh, 1 lượt LLM).`)));
    const analyze = button(d.locations.length ? 'Tìm lại bối cảnh (LLM)' : 'Tìm bối cảnh lặp lại (LLM)',
      'bg-indigo-600 text-white border-indigo-300', () => {
        if (d.locations.length && !window.confirm('Tìm lại sẽ thay các bối cảnh AI tìm trước đó còn ở dạng nháp. Bối cảnh tự thêm và bối cảnh đã có ảnh chuẩn được giữ. Tiếp tục? (1 lượt LLM)')) return;
        act(() => call('POST', '/analyze'), 'Đã gửi AI tìm bối cảnh');
      }, d.analyzing || d.eligible_scenes < d.min_scenes);
    analyze.id = 'btn-location-analyze';
    bar.appendChild(analyze);
    list.appendChild(bar);
    if (d.analysis_error) list.appendChild(node('p', 'text-[11px] text-red-700', `Lần tìm trước lỗi: ${d.analysis_error}`));
    d.locations.forEach(l => list.appendChild(card(l)));
    list.appendChild(addForm());
  }

  async function refresh() {
    if (!usable()) return;
    try {
      st.data = await call('GET', '');
      render();
    } catch (err) {
      console.warn('location sheets', err);
    }
  }

  function open() {
    el('modal-location-sheets')?.classList.remove('hidden');
    refresh();
    clearInterval(st.timer);
    st.timer = setInterval(() => {
      if (st.data?.analyzing || (st.data?.locations || []).some(l => l.drawing)) refresh();
    }, POLL_MS);
  }

  function close() {
    el('modal-location-sheets')?.classList.add('hidden');
    clearInterval(st.timer);
    st.timer = null;
  }

  function init() {
    el('btn-location-sheets')?.addEventListener('click', open);
    el('btn-close-location-sheets')?.addEventListener('click', close);
    document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') close(); });
    let lastId = null;
    setInterval(() => {   // nút hiện với dự án thật có từ 2 cảnh; đổi dự án thì đóng cửa sổ
      const id = project()?.id || null;
      el('btn-location-sheets')?.classList.toggle('hidden', !usable());
      if (id !== lastId) { lastId = id; st.data = null; close(); }
    }, 1000);
  }

  window.refreshLocationSheets = refresh;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
