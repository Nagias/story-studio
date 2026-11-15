/* Khuôn thể loại và trang Ý tưởng (spec 4.3, 4.4). Nạp sau app.js, trước true_crime.js.
 * Một nơi duy nhất khai báo thể loại: thêm thể loại mới thì thêm một mục vào GENRES.
 * Thẻ thể loại đặt giá trị cho ô #step1-content-kind rồi phát sự kiện change, để applyStep1ContentKind() của app.js chạy như cũ.
 * AppState của app.js là const (không nằm trên window): chỉ đọc qua typeof AppState, lúc chạy. */
(function () {
  'use strict';

  const el = (id) => document.getElementById(id);
  const ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (text) => (typeof escapeHtml === 'function' ? escapeHtml(text)
    : String(text).replace(/[&<>"']/g, (c) => ESC_MAP[c]));

  const SOON_DESC = 'Chưa làm. Khi cần chỉ thêm một khuôn.';

  const GENRES = [
    { code: 'story', name: 'Truyện chữ', desc: 'Dán truyện, AI kể lại kiểu review.',
      rewriteNote: 'AI kể lại kiểu review, kiểm đủ ý từng phần.',
      skipLook: false, enabled: true, contentKind: 'story' },
    { code: 'case', name: 'Vụ án có thật', desc: 'Dán bài, AI lập dàn ý, đổi tên người và nơi chốn.',
      rewriteNote: 'AI lập dàn ý cho bạn duyệt, đổi tên, rồi viết lại.',
      skipLook: false, enabled: true, contentKind: 'case' },
    { code: 'comic', name: 'Truyện tranh', desc: 'Thả ảnh trang truyện, app cắt thành từng khung.',
      rewriteNote: 'Không viết lại. Mỗi khung thành một cảnh, bạn tự gõ lời.',
      skipLook: true, enabled: true },
    { code: 'news', name: 'Tổng hợp tin tức', desc: SOON_DESC, rewriteNote: '',
      skipLook: false, enabled: false },
    { code: 'knowledge', name: 'Video kiến thức', desc: SOON_DESC, rewriteNote: '',
      skipLook: false, enabled: false },
    { code: 'shorts', name: 'Tổng hợp video ngắn', desc: SOON_DESC, rewriteNote: '',
      skipLook: false, enabled: false },
  ];

  // Thể loại của dự án đang mở, suy từ dữ liệu có sẵn (spec 4.3): không thêm trường mới vào dự án
  function projectGenre(project) {
    if (project && project.metadata && project.metadata.case_id) return 'case';
    const scenes = (project && Array.isArray(project.scenes)) ? project.scenes : [];
    if (scenes.some((scene) => scene && scene.metadata && scene.metadata.source === 'comic_slicer')) return 'comic';
    return 'story';
  }

  let current = GENRES[0];

  function byCode(code) { return GENRES.find((g) => g.code === code) || GENRES[0]; }

  function paintGenre() {
    document.querySelectorAll('#idea-genre-cards [data-genre]').forEach((btn) => {
      btn.setAttribute('aria-pressed', btn.dataset.genre === current.code ? 'true' : 'false');
    });
    const note = el('idea-genre-note');
    if (note) note.textContent = current.rewriteNote;
    const isComic = current.code === 'comic';
    el('idea-text-block')?.classList.toggle('hidden', isComic);
    el('idea-comic-block')?.classList.toggle('hidden', !isComic);
  }

  function renderGenreCards() {
    const box = el('idea-genre-cards');
    if (!box) return;
    box.innerHTML = GENRES.map((g) => {
      const tag = g.enabled ? '' : '<span class="ws-pick-tag">Sau này</span>';
      return '<button type="button" class="ws-pick" data-genre="' + esc(g.code) + '" aria-pressed="false"'
        + (g.enabled ? '' : ' disabled') + '><b>' + esc(g.name) + tag + '</b><span>' + esc(g.desc) + '</span></button>';
    }).join('');
    paintGenre();
  }

  function pickGenre(code) {
    const genre = byCode(code);
    if (!genre.enabled) return;
    current = genre;
    const kind = el('step1-content-kind');
    if (genre.contentKind && kind) {
      kind.value = genre.contentKind;
      kind.dispatchEvent(new Event('change'));
    }
    paintGenre();
  }

  function styleParts(option) {
    // "🕵️ Neo-Noir Silhouette (Án Mạng Đêm Mưa / Phim Noir)" -> tên và mô tả, bỏ biểu tượng đầu dòng
    const text = (option.textContent || '').replace(/^[^\p{L}\p{N}]+/u, '').trim();
    const open = text.indexOf(' (');
    if (open > 0 && text.endsWith(')')) return { name: text.slice(0, open), desc: text.slice(open + 2, -1) };
    return { name: text, desc: '' };
  }

  function paintStyle() {
    const select = el('step1-style-select');
    document.querySelectorAll('#idea-style-cards [data-style]').forEach((btn) => {
      btn.setAttribute('aria-pressed', select && btn.dataset.style === select.value ? 'true' : 'false');
    });
  }

  function renderStyleCards() {
    const box = el('idea-style-cards');
    const select = el('step1-style-select');
    if (!box || !select) return;
    box.innerHTML = Array.from(select.options).map((option) => {
      const parts = styleParts(option);
      return '<button type="button" class="ws-pick" data-style="' + esc(option.value) + '" aria-pressed="false"><b>'
        + esc(parts.name) + '</b><span>' + esc(parts.desc) + '</span></button>';
    }).join('');
    paintStyle();
  }

  function init() {
    // Trình duyệt có thể khôi phục giá trị ô ẩn sau khi tải lại: thẻ phải theo giá trị đó, không theo mặc định
    const savedKind = el('step1-content-kind');
    const restored = savedKind && GENRES.find((g) => g.contentKind === savedKind.value);
    if (restored) current = restored;
    renderGenreCards();
    renderStyleCards();
    if (typeof applyStep1ContentKind === 'function') applyStep1ContentKind();

    el('idea-genre-cards')?.addEventListener('click', (event) => {
      const btn = event.target.closest('[data-genre]');
      if (btn && !btn.disabled) pickGenre(btn.dataset.genre);
    });
    el('idea-style-cards')?.addEventListener('click', (event) => {
      const btn = event.target.closest('[data-style]');
      const select = el('step1-style-select');
      if (!btn || !select) return;
      select.value = btn.dataset.style;
      select.dispatchEvent(new Event('change'));
    });
    // Ô phong cách đổi từ nơi khác (nút kịch bản mẫu) thì thẻ theo
    el('step1-style-select')?.addEventListener('change', paintStyle);
    // Loại nội dung đổi từ nơi khác thì thẻ thể loại theo (trừ khi đang ở thẻ Truyện tranh, thẻ này không đổi ô)
    el('step1-content-kind')?.addEventListener('change', () => {
      if (current.code === 'comic') return;
      const kind = el('step1-content-kind').value;
      const genre = GENRES.find((g) => g.contentKind === kind);
      if (genre && genre !== current) { current = genre; paintGenre(); }
    });
    el('btn-idea-options')?.addEventListener('click', () => {
      const block = el('idea-options-block');
      if (block && typeof openDrawer === 'function') openDrawer('Tuỳ chọn', block);
    });
  }

  // Trang Hình mẫu của dự án có cờ skipLook (truyện tranh): hiện câu báo có thể bỏ qua bước này
  function paintLookSkipNote() {
    const note = el('look-skip-note');
    if (!note) return;
    const project = typeof AppState !== 'undefined' && AppState ? AppState.currentProject : null;
    note.hidden = !(project && byCode(projectGenre(project)).skipLook);
  }
  if (typeof onPageShow === 'function') onPageShow('look', paintLookSkipNote);

  window.GENRES = GENRES;
  window.projectGenre = projectGenre;
  window.renderGenreCards = renderGenreCards;
  window.pickGenre = pickGenre;   // nút "Phân tích vụ khác" (true_crime.js) chọn lại thẻ Vụ án có thật

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
