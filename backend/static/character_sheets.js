/* Bảng nhân vật đủ góc (truyện chữ và vụ án, luồng chung 03/11/2026), Bước 2: danh sách nhân vật cố định (vụ án: từ
 * bảng tên; truyện chữ: AI tìm), sửa thiết kế, Muse vẽ bảng, duyệt, vẽ lại có ghi chú chỗ sai. Mỗi ảnh cảnh vẽ sau dùng
 * mô tả cố định của người trong cảnh, bảng đã duyệt được đính kèm cho Muse (services/scene_locks.py).
 * API: /api/projects/{id}/characters... (routers/character_sheets.py). "Vẽ bảng" tốn 1 lượt Muse (tài khoản video),
 * "AI tìm nhân vật" tốn 1 lượt LLM.
 * Dùng AppState, showToast, escapeHtml của app.js (nạp sau app.js). Mọi phần tử dựng bằng DOM + textContent, không chèn
 * chuỗi HTML; nút chỉ gắn sự kiện ở đây (CLAUDE.md đường cấm 9, 10).
 */
(function () {
  const el = (id) => document.getElementById(id);
  const POLL_MS = 5000;
  const st = { data: null, timer: null, showAll: true };

  const STATUS = {
    draft: ['Chưa có bảng', 'bg-slate-100 text-slate-600 border-slate-200'],
    drawing: ['Muse đang vẽ…', 'bg-slate-50 text-slate-700 border-slate-200 animate-pulse'],
    review: ['Chờ duyệt', 'bg-amber-50 text-amber-700 border-amber-200'],
    approved: ['Đã duyệt', 'bg-emerald-50 text-emerald-700 border-emerald-200'],
    failed: ['Vẽ lỗi', 'bg-red-50 text-red-700 border-red-200'],
  };

  const project = () => AppState.currentProject;
  // Cảnh có hình vẽ của câu chuyện; cảnh không ghi loại (truyện chữ cũ) là cảnh ảnh
  const isDrawn = (s) => ['image', 'video'].includes(s.metadata?.visual_kind || 'image');
  const usable = () => {
    const p = project();
    return Boolean(p && !p.is_demo && (p.scenes || []).some(isDrawn));
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
    const b = node('button', `ws-btn text-xs ${cls}`, label);
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
    actions.appendChild(button(c.versions ? 'Vẽ bảng mới' : 'Vẽ bảng (Muse)', 'ws-btn-primary', () =>
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
      if (typeof window.bindMediaViewerLink === 'function') window.bindMediaViewerLink(a, 'image', `Bảng nhân vật ${c.name_vi}`);
      a.appendChild(img);
      right.appendChild(a);
      right.appendChild(node('p', 'text-[10px] text-slate-500 mt-1', `Phiên bản ${c.versions} — bấm ảnh để xem cỡ thật`));
    } else {
      right.appendChild(node('div', 'w-full aspect-video rounded-lg bg-slate-100 flex items-center justify-center text-slate-500', 'Chưa có bảng'));
    }
    box.appendChild(right);
    return box;
  }

  // Nguồn nhân vật: vụ án lấy từ bảng tên đã duyệt; truyện chữ do AI tìm từ lời kể (chạy khi tạo dự án, tìm lại được)
  function sourceBar() {
    const d = st.data;
    const bar = node('div', 'flex items-center justify-between gap-2 bg-slate-50 border border-slate-200 rounded-xl p-2.5');
    if (d.source === 'case') {
      bar.appendChild(node('p', 'text-slate-600', 'Nhân vật lấy từ bảng tên đã duyệt của vụ án.'));
      return bar;
    }
    const info = node('div', 'space-y-1');
    info.appendChild(node('p', 'text-slate-600', d.analyzing
      ? 'AI đang đọc lời kể để tìm nhân vật…'
      : d.analyzed_at ? `AI đã tìm nhân vật từ lời kể (${d.characters.length} người).`
        : 'Chưa tìm nhân vật cho truyện này.'));
    if (d.analysis_error) info.appendChild(node('p', 'text-[11px] text-red-700', `Lần tìm trước lỗi: ${d.analysis_error}`));
    bar.appendChild(info);
    bar.appendChild(button(d.analyzed_at ? 'AI tìm lại nhân vật' : 'AI tìm nhân vật', 'ws-btn-primary',
      () => act(() => call('POST', '/analyze'), 'Đã gửi AI tìm nhân vật'), Boolean(d.analyzing)));
    bar.lastChild.id = 'btn-character-analyze';
    return bar;
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
    const chars = (st.data?.characters || []).filter(c => st.showAll || needed.has(c.entity_id) || c.status !== 'draft');
    list.appendChild(sourceBar());
    const bar = node('div', 'flex items-center justify-between gap-2');
    bar.appendChild(node('p', 'text-slate-600', needed.size
      ? `Cần cho các cảnh đang chọn làm video cao trào: ${needed.size} nhân vật.`
      : 'Mọi ảnh cảnh vẽ sau dùng mô tả cố định của người có mặt trong cảnh; ai có bảng đã duyệt thì Muse nhận thêm ảnh bảng.'));
    bar.appendChild(button(st.showAll ? 'Chỉ hiện người cần cho video cao trào' : `Hiện cả ${st.data.characters.length} người`,
      'bg-white text-slate-700 border-slate-300', () => { st.showAll = !st.showAll; render(); }));
    list.appendChild(bar);
    if (!chars.length) list.appendChild(node('p', 'text-slate-500', 'Không có nhân vật nào để hiện.'));
    chars.forEach(c => list.appendChild(card(c, scenesOf[c.entity_id] || [])));
  }

  async function refresh() {
    if (!project() || !usable()) return;
    try {
      st.data = await call('GET', '');
      render();
    } catch (err) {
      console.warn('character sheets', err);
    }
  }

  function showReason() {
    const list = el('character-sheets-list');
    if (!list) return;
    list.replaceChildren(node('p', 'text-slate-500', 'Chưa dùng được: dự án này chưa có cảnh vẽ nào, hoặc là dự án mẫu chỉ để xem.'));
  }

  // Trang Hình mẫu đang hiện: nạp danh sách và hỏi lại khi Muse/AI còn đang làm. Không đụng class hidden (khối luôn hiện trong trang).
  function start() {
    if (!usable()) showReason();
    refresh();
    clearInterval(st.timer);
    st.timer = setInterval(() => {
      if (st.data?.analyzing || (st.data?.characters || []).some(c => c.drawing)) refresh();
    }, POLL_MS);
  }

  function stop() {
    clearInterval(st.timer);
    st.timer = null;
  }

  function onLookPage() {
    return typeof window.currentPage === 'function' && window.currentPage() === 'look';
  }

  function init() {
    let lastId = null;
    setInterval(() => {   // đổi dự án: bỏ dữ liệu cũ, nếu trang Hình mẫu đang mở thì nạp lại cho dự án mới
      const id = project()?.id || null;
      if (id !== lastId) {
        lastId = id; st.data = null; stop(); el('character-sheets-list')?.replaceChildren();
        if (onLookPage()) start();
      }
    }, 1000);
  }

  window.startCharacterSheets = start;
  window.stopCharacterSheets = stop;
  window.refreshCharacterSheets = refresh;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
