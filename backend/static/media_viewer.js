/* Xem lớn ảnh/video dùng chung: window.openMediaViewer({src, kind: 'image'|'video', caption}).
 * Nạp sau app.js. Chữ chú thích đặt bằng textContent. Đóng bằng Esc, nút ×, bấm nền; đóng thì dừng video
 * và trả focus về phần tử trước đó. Bấm vào phần tử có data-viewer-src trong thẻ cảnh cũng mở (uỷ quyền sự kiện).
 */
(function () {
  let root = null;
  let lastFocus = null;

  function close() {
    if (!root) return;
    const v = root.querySelector('video');
    if (v) { try { v.pause(); } catch (e) { console.warn('media_viewer: không dừng được video', e); } }
    root.remove();
    root = null;
    document.removeEventListener('keydown', onKey, true);
    if (lastFocus && typeof lastFocus.focus === 'function' && document.contains(lastFocus)) lastFocus.focus();
    lastFocus = null;
  }

  function onKey(ev) {
    if (ev.key === 'Escape') { ev.stopPropagation(); close(); }
  }

  function open(opts) {
    const o = opts || {};
    if (!o.src) return;
    close();
    lastFocus = document.activeElement;
    root = document.createElement('div');
    root.className = 'ws-viewer-backdrop';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', o.caption || 'Xem lớn');
    const box = document.createElement('div');
    box.className = 'ws-viewer-box';
    let media;
    if (o.kind === 'video') {
      media = document.createElement('video');
      media.controls = true;
      media.autoplay = true;
      media.playsInline = true;
    } else {
      media = document.createElement('img');
      media.alt = o.caption || '';
    }
    media.className = 'ws-viewer-media';
    media.src = o.src;
    box.appendChild(media);
    if (o.caption) {
      const cap = document.createElement('div');
      cap.className = 'ws-viewer-caption';
      cap.textContent = o.caption;
      box.appendChild(cap);
    }
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ws-viewer-close';
    btn.setAttribute('aria-label', 'Đóng');
    btn.textContent = '\u00d7';
    btn.addEventListener('click', close);
    root.appendChild(box);
    root.appendChild(btn);
    root.addEventListener('click', (ev) => { if (ev.target === root) close(); });
    document.body.appendChild(root);
    document.addEventListener('keydown', onKey, true);
    btn.focus();
  }

  window.openMediaViewer = open;

  // Gắn vào link mở ảnh: chuột trái không phím phụ thì mở viewer, còn lại giữ hành vi mở tab mới.
  window.bindMediaViewerLink = function (a, kind, caption) {
    a.addEventListener('click', (ev) => {
      if (ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) return;
      ev.preventDefault();
      open({ src: a.href, kind: kind || 'image', caption: caption || '' });
    });
  };

  const list = document.getElementById('scene-list-container');
  if (list) {
    list.addEventListener('click', (ev) => {
      const t = ev.target.closest('[data-viewer-src]');
      if (!t || !list.contains(t)) return;
      if (t.tagName === 'VIDEO') { try { t.pause(); } catch (e) { console.warn('media_viewer: không dừng được video', e); } }
      open({ src: t.getAttribute('data-viewer-src'), kind: t.getAttribute('data-viewer-kind') || 'image', caption: t.getAttribute('data-viewer-caption') || '' });
    });
  }
})();
