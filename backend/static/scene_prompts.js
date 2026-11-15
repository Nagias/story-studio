/* Prompt thật gửi Muse trên thẻ cảnh: khối "Prompt đầy đủ gửi Muse" (tab ảnh) và tab "Video gửi Muse".
 * Hỏi GET /api/projects/{project_id}/scenes/{scene_id}/muse-prompt?kind=image|video (routers/scene_prompt_preview.py,
 * không tốn gì), tải lười: khối ảnh khi mở, tab video khi hiện và trang Cảnh đang mở. Chữ từ máy chủ đặt bằng textContent.
 * Nạp sau app.js; dùng AppState, flushProjectSave của app.js. app.js gọi window.loadSceneMusePrompt(index, kind).
 * Tab video ghi rõ nút nào gửi gì: nút "Muse Video" trên thẻ (video theo lời thoại) và, nếu cảnh được chọn làm video
 * cao trào, nút làm video cao trào (bản giao việc, hoặc lý do lượt đó sẽ dừng).
 */
(function () {
  // Chỉ gộp các lần hỏi liền nhau (thẻ vẽ lại nhiều lần): khoá nhân vật/bối cảnh có thể vừa đổi ở trang khác
  const CACHE_MS = 5000;
  const cache = new Map();   // `${scene_id}|${kind}` -> {sig, at, promise}

  function project() {
    return typeof AppState !== 'undefined' ? AppState.currentProject : null;
  }

  // Đổi lời kể, mô tả ảnh, độ dài, trạng thái cao trào hay phong cách thì hỏi lại máy chủ
  function signature(p, scene) {
    const climax = ((scene.metadata || {}).climax_video || {}).status || '';
    return JSON.stringify([scene.text, scene.image_prompt, scene.visual_prompt, scene.duration, climax,
      p.style_preset, p.character_anchor]);
  }

  async function fetchPreview(p, scene, kind) {
    const key = `${scene.id}|${kind}`;
    const sig = signature(p, scene);
    const hit = cache.get(key);
    if (hit && hit.sig === sig && Date.now() - hit.at < CACHE_MS) return hit.promise;
    const promise = (async () => {
      // Xem trước theo bản đã lưu: chưa lưu được thì báo, không hiện chữ cũ trên máy chủ như thể là chữ mới
      if (typeof flushProjectSave === 'function' && !(await flushProjectSave({ silent: true }))) {
        throw new Error('chưa lưu được chỉnh sửa lên máy chủ nên chữ trên máy chủ có thể đã cũ; lưu xong rồi mở lại');
      }
      const res = await fetch(`/api/projects/${encodeURIComponent(p.id)}/scenes/${encodeURIComponent(scene.id)}/muse-prompt?kind=${encodeURIComponent(kind)}`);
      let data = null;
      try { data = await res.json(); } catch (e) { console.warn('scene_prompts: máy chủ trả không phải JSON', e); }
      if (!res.ok) throw new Error((data && data.detail) || `Máy chủ trả lỗi ${res.status}`);
      return data;
    })();
    cache.set(key, { sig, at: Date.now(), promise });
    promise.catch(() => cache.delete(key));
    return promise;
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function block(title, text) {
    const wrap = el('div', 'ws-mp-block');
    const head = el('div', 'ws-mp-head');
    head.appendChild(el('span', '', title));
    const copy = el('button', 'ws-btn ws-mp-copy', 'Sao chép');
    copy.type = 'button';
    copy.setAttribute('data-muse-copy', '');
    head.appendChild(copy);
    wrap.appendChild(head);
    wrap.appendChild(el('pre', 'ws-mp-text', text || ''));
    return wrap;
  }

  function secs(v) {
    return Number(v || 0).toFixed(1);
  }

  function renderImage(body, d) {
    const atts = d.attachments || [];
    body.appendChild(el('div', 'ws-mp-note', atts.length
      ? 'Ảnh đính kèm: ' + atts.map(a => `${a.role_vi} (${a.name})`).join(', ')
      : 'Không có ảnh đính kèm.'));
    const locks = d.locks || {};
    const parts = [];
    if ((locks.characters || []).length) parts.push('nhân vật ' + locks.characters.join(', '));
    if (locks.location) parts.push('bối cảnh ' + locks.location);
    body.appendChild(el('div', 'ws-mp-note', parts.length ? 'Khoá đã áp: ' + parts.join('; ') + '.' : 'Chưa có khoá nhân vật hay bối cảnh cho cảnh này.'));
    body.appendChild(block('Chữ Muse nhận', d.prompt));
  }

  function renderDialogue(body, d) {
    body.appendChild(el('div', 'ws-mp-label', 'Nút "Muse Video" trên thẻ gửi:'));
    if (!d || d.error) {
      body.appendChild(el('div', 'ws-mp-note', 'Chưa chia được lời kể thành video: ' + ((d && d.error) || 'không rõ lý do')));
      return;
    }
    const segs = d.segments || [];
    body.appendChild(el('div', 'ws-mp-summary', `${d.video_count} video · khoảng ${secs(d.narration_seconds)} giây`
      + (d.estimated ? ' (ước theo số chữ, cảnh chưa có giọng đọc)' : '')));
    if (d.blocked) body.appendChild(el('div', 'ws-mp-note', 'Bấm lúc này nút sẽ dừng: ' + d.blocked));
    segs.forEach(s => body.appendChild(block(`Video ${s.index}/${segs.length} · khoảng ${secs(s.seconds)} giây lời kể`, s.prompt)));
  }

  function renderClimax(body, c) {
    const head = el('div', 'ws-mp-label', 'Lượt làm video cao trào gửi:');
    head.style.marginTop = '10px';
    body.appendChild(head);
    if (c.blocked) {
      body.appendChild(el('div', 'ws-mp-note', 'Lượt cao trào sẽ dừng: ' + c.blocked));
      return;
    }
    body.appendChild(el('div', 'ws-mp-summary', `Video cao trào · Muse tự chia clip, tổng khoảng ${c.target_seconds} giây`));
    if (c.needs_grid_first) {
      body.appendChild(el('div', 'ws-mp-note', `Cảnh này vẽ ${c.grid_count} ảnh lưới 9 ô trước và chờ bạn duyệt, sau đó Muse mới nhận bản giao việc dưới đây.`));
    }
    body.appendChild(el('div', 'ws-mp-note', `Mã kết thúc thật sinh lúc chạy; ở đây ghi ${c.done_token_placeholder}.`));
    body.appendChild(block('Bản giao việc gửi Muse', c.prompt));
  }

  function renderVideo(body, d) {
    renderDialogue(body, d.dialogue);
    if (d.climax) renderClimax(body, d.climax);
  }

  async function load(body, kind, index) {
    const p = project();
    const scene = p && (p.scenes || [])[index];
    if (!body || !scene) return;
    if (!scene.id || p.is_demo) {
      body.replaceChildren(el('div', 'ws-mp-note', 'Dự án mẫu hoặc cảnh chưa lưu: chưa xem được prompt gửi Muse.'));
      return;
    }
    const token = String(Date.now() + Math.random());
    body.dataset.museLoad = token;
    body.replaceChildren(el('div', 'ws-mp-note', 'Đang ghép prompt…'));
    try {
      const d = await fetchPreview(p, scene, kind);
      if (body.dataset.museLoad !== token) return;
      body.replaceChildren();
      if (kind === 'image') renderImage(body, d); else renderVideo(body, d);
      body.dataset.museLoaded = '1';
    } catch (err) {
      if (body.dataset.museLoad !== token) return;
      body.replaceChildren(el('div', 'ws-mp-note', 'Chưa xem được prompt: ' + (err && err.message ? err.message : 'không rõ lý do')));
    }
  }

  function bodyFor(index, kind) {
    const host = document.querySelector(`[data-muse-prompt-kind="${kind}"][data-scene-index="${Number(index)}"]`);
    if (!host) return null;
    return host.matches('[data-muse-prompt-body]') ? host : host.querySelector('[data-muse-prompt-body]');
  }

  function loadSceneMusePrompt(index, kind) {
    return load(bodyFor(index, kind), kind === 'video' ? 'video' : 'image', Number(index));
  }

  // Tab video đang mở sẵn sau mỗi lần renderSceneList() vẽ lại thẻ
  function loadVisibleVideoTabs() {
    document.querySelectorAll('[data-muse-prompt-kind="video"][data-muse-prompt-body]').forEach(body => {
      if (body.dataset.museLoaded || body.dataset.museLoad) return;
      if (body.closest('.hidden') || body.closest('[hidden]')) return;   // tab ẩn hoặc trang Cảnh chưa mở
      load(body, 'video', Number(body.dataset.sceneIndex));
    });
  }

  document.addEventListener('toggle', ev => {
    const d = ev.target;
    if (!(d instanceof HTMLDetailsElement) || !d.open || d.dataset.musePromptKind !== 'image') return;
    load(d.querySelector('[data-muse-prompt-body]'), 'image', Number(d.dataset.sceneIndex));
  }, true);   // sự kiện toggle không nổi bọt: bắt ở pha capture

  document.addEventListener('click', async ev => {
    const btn = ev.target.closest && ev.target.closest('[data-muse-copy]');
    if (!btn) return;
    const pre = btn.closest('.ws-mp-block')?.querySelector('pre');
    if (!pre) return;
    try {
      await navigator.clipboard.writeText(pre.textContent);
      btn.textContent = 'Đã chép';
    } catch (err) {
      console.warn('scene_prompts: không chép được vào bộ nhớ tạm', err);
      const range = document.createRange();
      range.selectNodeContents(pre);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      btn.textContent = 'Đã chọn chữ, bấm Ctrl+C';
    }
    setTimeout(() => { btn.textContent = 'Sao chép'; }, 2000);
  });

  const container = document.getElementById('scene-list-container');
  if (container) new MutationObserver(loadVisibleVideoTabs).observe(container, { childList: true });
  const page = document.getElementById('page-scenes');   // mở trang Cảnh thì tải tab video đang hiện
  if (page) new MutationObserver(loadVisibleVideoTabs).observe(page, { attributes: true, attributeFilter: ['hidden'] });

  window.loadSceneMusePrompt = loadSceneMusePrompt;
})();
