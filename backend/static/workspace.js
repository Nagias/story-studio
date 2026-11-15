/**
 * Khung giao diện gọn: 8 trang, thanh bên thu gọn được, đường dẫn trang ở thanh trên, ô tìm cảnh, ngăn kéo bên phải.
 * Nạp trước app.js. Gắn lên window: showPage, onPageShow, openDrawer, closeDrawer, currentPage, rememberedPage,
 * renderCaseStrip (true_crime.js gọi mỗi lần vẽ tiến độ vụ án).
 * Dùng các global của app.js lúc chạy (không lúc nạp): AppState, selectScene, showToast, escapeHtml.
 * localStorage luôn đọc ghi trong try/catch: bị chặn thì trang vẫn chạy, chỉ không nhớ.
 */
(function () {
  'use strict';

  const PAGES = {
    idea: 'Ý tưởng',
    script: 'Kịch bản và giọng',
    look: 'Hình mẫu',
    scenes: 'Cảnh',
    publish: 'Dựng và xuất bản',
    projects: 'Dự án',
    gallery: 'Thư viện Muse',
    accounts: 'Tài khoản và kết nối',
  };
  const COLLAPSE_KEY = 'ws_sidebar_collapsed';
  const NARROW_QUERY = '(max-width: 859px)';

  const hooks = {};
  let current = null;
  let drawerContent = null;   // khối đang nằm trong ngăn kéo
  let drawerAnchor = null;    // chỗ cũ của khối đó (để trả về khi đóng)

  function storageGet(key) {
    try { return window.localStorage.getItem(key); } catch (err) { console.warn('localStorage bị chặn:', err); return null; }
  }
  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); } catch (err) { console.warn('localStorage bị chặn:', err); }
  }

  function project() {
    return (typeof AppState !== 'undefined' && AppState) ? AppState.currentProject : null;
  }

  // Chỉ tên trang: tên dự án hiện ở #current-project-title trên thanh trên (app.js tự cập nhật khi đổi dự án)
  function renderCrumb(name) {
    const crumb = document.getElementById('ws-crumb');
    if (!crumb) return;
    crumb.textContent = '';
    const b = document.createElement('b');
    b.textContent = PAGES[name] || '';
    crumb.appendChild(b);
  }

  function showPage(name) {
    if (!Object.prototype.hasOwnProperty.call(PAGES, name)) {
      console.warn('showPage: không có trang', name);
      return;
    }
    const previous = current;
    current = name;
    if (previous === 'look' && name !== 'look') stopLookPolling();
    // Đổi trang thì đóng ngăn kéo: khối Xem thử không phát tiếng, khối Tuỳ chọn không treo sang trang khác
    // (đóng ngăn xem thử thì scenes_publish_page.js dừng tiếng đang phát)
    if (previous !== name) closeDrawer();
    closeStylePopover();
    for (const code of Object.keys(PAGES)) {
      const page = document.getElementById(`page-${code}`);
      if (page) page.hidden = code !== name;
    }
    document.querySelectorAll('.ws-nav[data-go]').forEach((btn) => {
      if (btn.dataset.go === name) btn.setAttribute('aria-current', 'page');
      else btn.removeAttribute('aria-current');
    });
    document.body.dataset.wsPage = name;
    renderCrumb(name);
    paintCaseStrip();
    const canvas = document.getElementById('ws-canvas');
    if (canvas) canvas.scrollTop = 0;
    const proj = project();
    if (proj && proj.id) storageSet(`ws_page_${proj.id}`, name);
    for (const fn of hooks[name] || []) {
      try { fn(); } catch (err) { console.error(`Móc của trang ${name} bị lỗi:`, err); }
    }
  }

  // ---------- Vụ án đang theo dõi (chưa tạo dự án) ----------
  // Dự án đang mở vẫn là dự án cũ (spec 5.2): trang Kịch bản ghi rõ điều đó, các trang Hình mẫu, Cảnh, Dựng có dải
  // "Vụ mới đang phân tích NN%" bấm để về trang Kịch bản. Dữ liệu do true_crime.js đưa qua renderCaseStrip().
  const CASE_BANNER_PAGES = ['look', 'scenes', 'publish'];
  let caseStrip = { tracking: false, percent: null, status: null };

  // Chữ trên dải theo trạng thái vụ (true_crime.js đưa status của việc phân tích)
  function caseBannerText() {
    const status = caseStrip.status;
    if (status === 'review') return 'Vụ mới chờ duyệt dàn ý: xem ở Kịch bản';
    if (status === 'done') return 'Vụ mới đã phân tích xong, tạo dự án ở Kịch bản';
    if (status === 'failed' || status === 'stopped') return 'Vụ mới bị dừng, xem ở Kịch bản';
    const pct = caseStrip.percent === null ? '' : ' ' + caseStrip.percent + '%';
    return 'Vụ mới đang phân tích' + pct + ': xem ở Kịch bản';
  }

  function paintCaseStrip() {
    const note = document.getElementById('ws-case-note');
    const banner = document.getElementById('ws-case-banner');
    const tracking = caseStrip.tracking;
    if (note) {
      note.hidden = !(tracking && current === 'script');
      if (!note.hidden) {
        const proj = project();
        const name = (proj && (proj.name || proj.id)) || 'chưa có tên';
        const line = (shown) => 'Đang làm vụ mới. Dự án đang mở là «' + shown + '»: xem ở Hình mẫu, Cảnh, Dựng';
        if (typeof escapeHtml === 'function') note.innerHTML = line(escapeHtml(String(name)));
        else note.textContent = line(String(name));
      }
    }
    if (banner) {
      banner.hidden = !(tracking && CASE_BANNER_PAGES.includes(current));
      if (!banner.hidden) {
        banner.textContent = caseBannerText();
      }
    }
  }

  function renderCaseStrip(state) {
    // percent null: chưa hỏi được tiến độ lần nào (vd. vừa tải lại trang, chưa mở trang Kịch bản)
    const raw = state ? state.percent : null;
    const percent = raw === null || raw === undefined ? NaN : Number(raw);
    const status = state && typeof state.status === 'string' ? state.status : null;
    caseStrip = { tracking: !!(state && state.tracking), percent: Number.isFinite(percent) ? Math.round(percent) : null, status };
    paintCaseStrip();
  }

  // ---------- Trang Hình mẫu ----------
  function stopLookPolling() {
    for (const fn of [window.stopCharacterSheets, window.stopLocationSheets]) {
      try { if (typeof fn === 'function') fn(); } catch (err) { console.error('Không dừng được việc hỏi tiến độ của trang Hình mẫu:', err); }
    }
  }

  function startLookPolling() {
    for (const fn of [window.startCharacterSheets, window.startLocationSheets]) {
      if (typeof fn === 'function') fn();
    }
  }

  // Tên phong cách của dự án: nhãn <option> đang chọn của #select-project-style, bỏ biểu tượng emoji đầu nhãn
  function renderLookStyleLine() {
    const line = document.getElementById('look-style-line');
    const sel = document.getElementById('select-project-style');
    if (!line) return;
    const opt = sel && sel.selectedOptions && sel.selectedOptions[0];
    const label = opt ? opt.textContent.replace(/^[^\p{L}\p{N}]+/u, '').trim() : '';
    line.textContent = label || 'Chưa có dự án';
  }

  function stylePopover() { return document.getElementById('look-style-popover'); }
  function closeStylePopover() {
    const pop = stylePopover();
    if (pop) pop.hidden = true;
  }

  function initLookPage() {
    const pop = stylePopover();
    document.getElementById('btn-look-change-style')?.addEventListener('click', () => {
      if (pop) pop.hidden = !pop.hidden;
    });
    document.getElementById('select-project-style')?.addEventListener('change', renderLookStyleLine);
    onPageShow('look', () => { startLookPolling(); renderLookStyleLine(); });
  }

  function onPageShow(name, fn) {
    (hooks[name] = hooks[name] || []).push(fn);
  }

  function currentPage() {
    return current;
  }

  // Trang đã mở lần trước của một dự án (null nếu chưa có hoặc localStorage bị chặn)
  function rememberedPage(projectId) {
    if (!projectId) return null;
    const saved = storageGet(`ws_page_${projectId}`);
    return saved && Object.prototype.hasOwnProperty.call(PAGES, saved) ? saved : null;
  }

  // ---------- Ngăn kéo ----------
  function openDrawer(title, contentEl) {
    const drawer = document.getElementById('ws-drawer');
    const body = document.getElementById('ws-drawer-body');
    if (!drawer || !body || !contentEl) return;
    if (drawerContent && drawerContent !== contentEl) closeDrawer();
    if (drawerContent !== contentEl) {
      drawerAnchor = document.createComment('ws-drawer-anchor');
      if (contentEl.parentNode) contentEl.parentNode.insertBefore(drawerAnchor, contentEl);
      body.appendChild(contentEl);
      drawerContent = contentEl;
    }
    const titleEl = document.getElementById('ws-drawer-title');
    if (titleEl) titleEl.textContent = title || '';
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
  }

  function closeDrawer() {
    const drawer = document.getElementById('ws-drawer');
    if (drawerContent) {
      if (drawerAnchor && drawerAnchor.parentNode) {
        drawerAnchor.parentNode.insertBefore(drawerContent, drawerAnchor);
        drawerAnchor.remove();
      } else {
        drawerContent.remove();
        console.warn('closeDrawer: chỗ cũ của khối không còn, khối được gỡ khỏi ngăn');
      }
    }
    drawerContent = null;
    drawerAnchor = null;
    if (drawer) {
      drawer.classList.remove('open');
      drawer.setAttribute('aria-hidden', 'true');
    }
  }

  function drawerIsOpen() {
    const drawer = document.getElementById('ws-drawer');
    return !!(drawer && drawer.classList.contains('open'));
  }

  // ---------- Thanh bên ----------
  function setCollapsed(collapsed, remember) {
    document.body.classList.toggle('ws-collapsed', collapsed);
    const btn = document.getElementById('btn-ws-toggle-sidebar');
    if (btn) btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    if (remember) storageSet(COLLAPSE_KEY, collapsed ? '1' : '0');
  }

  function initSidebar() {
    const narrow = window.matchMedia ? window.matchMedia(NARROW_QUERY) : null;
    const saved = storageGet(COLLAPSE_KEY) === '1';
    setCollapsed(saved || !!(narrow && narrow.matches), false);
    if (narrow) {
      const onChange = (e) => setCollapsed(e.matches || storageGet(COLLAPSE_KEY) === '1', false);
      if (narrow.addEventListener) narrow.addEventListener('change', onChange);
      else if (narrow.addListener) narrow.addListener(onChange);
    }
    document.getElementById('btn-ws-toggle-sidebar')?.addEventListener('click', () => {
      setCollapsed(!document.body.classList.contains('ws-collapsed'), true);
    });
    document.querySelectorAll('.ws-nav[data-go]').forEach((btn) => {
      btn.addEventListener('click', () => showPage(btn.dataset.go));
    });
  }

  // ---------- Ô tìm cảnh ----------
  function findSceneIndex(scenes, query) {
    const q = query.trim();
    if (!q) return -1;
    if (/^\d+$/.test(q)) {
      const n = parseInt(q, 10);
      if (n >= 1 && n <= scenes.length) return n - 1;
    }
    const lower = q.toLowerCase();
    return scenes.findIndex((s) => String((s && s.text) || '').toLowerCase().includes(lower));
  }

  function initSearch() {
    const input = document.getElementById('ws-search');
    if (!input) return;
    input.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const query = input.value;
      if (!query.trim()) return;
      const proj = project();
      const scenes = (proj && Array.isArray(proj.scenes)) ? proj.scenes : [];
      const idx = findSceneIndex(scenes, query);
      if (idx < 0) {
        if (typeof showToast === 'function' && typeof escapeHtml === 'function') {
          showToast('Không tìm thấy cảnh khớp với "' + escapeHtml(query.trim()) + '"', 'warning');
        }
        return;
      }
      showPage('scenes');
      if (typeof selectScene === 'function') {
        selectScene(idx);  // đặt AppState.selectedSceneIndex, vẽ lại và cuộn tới thẻ cảnh
      } else if (typeof AppState !== 'undefined') {
        AppState.selectedSceneIndex = idx;
      }
      const card = scenes[idx] && document.getElementById(`scene-card-${scenes[idx].id}`);
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  // ---------- Esc: đóng ngăn kéo (đang gõ trong ô nhập thì để handleGlobalKeydown() xử lý như cũ) ----------
  function isTyping(el) {
    if (!el) return false;
    return ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || !!el.closest?.('[contenteditable]:not([contenteditable="false"])');
  }

  function initKeys() {
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || isTyping(document.activeElement)) return;
      const pop = stylePopover();
      if (pop && !pop.hidden) { pop.hidden = true; return; }
      if (drawerIsOpen()) closeDrawer();
    });
  }

  function init() {
    initSidebar();
    initSearch();
    initKeys();
    initLookPage();
    document.getElementById('btn-ws-drawer-close')?.addEventListener('click', closeDrawer);
    document.getElementById('ws-case-banner')?.addEventListener('click', () => showPage('script'));
  }

  window.showPage = showPage;
  window.onPageShow = onPageShow;
  window.openDrawer = openDrawer;
  window.closeDrawer = closeDrawer;
  window.currentPage = currentPage;
  window.renderLookStyleLine = renderLookStyleLine;
  window.rememberedPage = rememberedPage;
  window.renderCaseStrip = renderCaseStrip;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
