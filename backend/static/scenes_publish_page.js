/* Trang "Cảnh" và trang "Dựng và xuất bản": nút mở ngăn kéo Xem thử, ngăn kéo Tuỳ chỉnh dựng và ô nổi "Thêm".
 * Nạp sau app.js và workspace.js. Không chèn chữ thô vào HTML (đường cấm 9): file này không dựng HTML. */
(function () {
  'use strict';

  const el = (id) => document.getElementById(id);

  function morePopover() { return el('scenes-more-popover'); }

  function setMore(open) {
    const pop = morePopover();
    if (pop) pop.hidden = !open;
    el('btn-scenes-more')?.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function openBlock(title, id) {
    const block = el(id);
    if (block && typeof openDrawer === 'function') openDrawer(title, block);
  }

  // Đóng ngăn xem thử thì dừng tiếng đang phát, để khối bị cất đi không còn đọc lời trong im lặng
  function watchPreviewDrawer() {
    const drawer = el('ws-drawer');
    if (!drawer || typeof MutationObserver === 'undefined') return;
    new MutationObserver(() => {
      const block = el('scenes-preview-block');
      const inDrawer = block && block.closest('#ws-drawer-body');
      if (!drawer.classList.contains('open') && !inDrawer && typeof pausePlayback === 'function'
          && typeof AppState !== 'undefined' && AppState.isPlaying) {
        pausePlayback();
      }
    }).observe(drawer, { attributes: true, attributeFilter: ['class'] });
  }

  function init() {
    el('btn-scenes-preview')?.addEventListener('click', () => { setMore(false); openBlock('Xem thử', 'scenes-preview-block'); });
    el('btn-render-settings')?.addEventListener('click', () => openBlock('Tuỳ chỉnh dựng', 'render-settings'));
    el('btn-scenes-more')?.addEventListener('click', () => {
      const pop = morePopover();
      setMore(!!(pop && pop.hidden));
    });
    // Bấm ra ngoài ô nổi, hoặc bấm nút bên trong nó, thì đóng ô nổi
    document.addEventListener('click', (e) => {
      const pop = morePopover();
      if (!pop || pop.hidden) return;
      if (e.target.closest('#btn-scenes-more')) return;
      if (!pop.contains(e.target) || e.target.closest('#btn-regen-all-images')) setMore(false);
    });
    // Esc khi không gõ trong ô nhập: đóng ô nổi trước (workspace.js đóng ngăn kéo)
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      const a = document.activeElement;
      if (a && (['INPUT', 'TEXTAREA', 'SELECT'].includes(a.tagName))) return;
      const pop = morePopover();
      if (pop && !pop.hidden) setMore(false);
    });
    // Rời trang thì đóng ngăn kéo để khối xem thử hay tuỳ chỉnh dựng không treo sang trang khác
    for (const page of ['scenes', 'publish']) {
      if (typeof onPageShow === 'function') onPageShow(page, () => { setMore(false); if (typeof closeDrawer === 'function') closeDrawer(); });
    }
    watchPreviewDrawer();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
