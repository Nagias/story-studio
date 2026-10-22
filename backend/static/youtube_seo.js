/* Gói SEO YouTube ở Bước 4: tìm từ khoá thật, chọn từ khoá, AI viết gói trong khuôn, sửa tay, kiểm luật, tải .txt.
 * API: /api/projects/{id}/youtube-seo (routers/youtube_seo.py). app.js gọi ytSeoLoad(project) khi mở Bước 4.
 * Dùng escapeHtml() và showToast() của app.js. Mọi chữ từ máy chủ hay người dùng đều qua escapeHtml() trước khi chèn
 * vào HTML (CLAUDE.md đường cấm 9); mỗi nút chỉ gắn sự kiện ở đây, không onclick trong HTML (đường cấm 10).
 */
(function () {
  const el = (id) => document.getElementById(id);
  const yt = { projectId: null, data: null, selected: [], dirty: false };

  const SOURCE_LABEL = {
    youtube_suggest: 'gợi ý tìm kiếm',
    youtube_data_api: 'video đứng đầu',
    manual: 'dán tay',
  };

  async function call(method, path, body) {
    const res = await fetch(`/api/projects/${encodeURIComponent(yt.projectId)}/youtube-seo${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch { /* thân không phải JSON */ }
    if (!res.ok) {
      const detail = data && data.detail;
      const error = new Error(typeof detail === 'string' ? detail : ((detail && detail.message) || `Máy chủ trả lỗi HTTP ${res.status}`));
      error.checks = (detail && detail.checks) || null;
      throw error;
    }
    return data;
  }

  function setBusy(id, busy, label) {
    const btn = el(id);
    if (!btn) return;
    btn.disabled = busy;
    btn.classList.toggle('cursor-not-allowed', busy);
    const span = btn.querySelector('span');
    if (span && label) span.textContent = label;
  }

  // ------------------------------------------------------------------ vẽ
  function renderResearch() {
    const research = yt.data && yt.data.research;
    const errors = el('yt-seo-research-errors');
    const box = el('yt-seo-candidates');
    const videos = el('yt-seo-top-videos');
    if (!research) {
      errors.classList.add('hidden');
      box.innerHTML = '<p class="text-slate-400">Chưa có từ khoá (hoặc dữ liệu đã quá 30 ngày). Nhập từ khoá gốc rồi bấm Tìm từ khoá.</p>';
      videos.innerHTML = '';
      return;
    }
    if (research.errors.length) {
      errors.innerHTML = research.errors.map((e) => `<div>${escapeHtml(e)}</div>`).join('');
      errors.classList.remove('hidden');
    } else {
      errors.classList.add('hidden');
    }
    box.innerHTML = research.candidates.map((c) => `
      <label class="flex items-start gap-2 py-0.5 cursor-pointer">
        <input type="checkbox" class="yt-seo-kw accent-indigo-600 mt-0.5" data-kw="${escapeHtml(c.keyword)}" ${yt.selected.includes(c.keyword) ? 'checked' : ''}>
        <span><span class="font-semibold text-slate-800">${escapeHtml(c.keyword)}</span>
          <span class="text-slate-400">· ${escapeHtml(SOURCE_LABEL[c.source] || c.source)}: ${escapeHtml(c.evidence)}</span></span>
      </label>`).join('');
    videos.innerHTML = research.top_videos.length ? `
      <details class="bg-slate-50 border border-slate-200 rounded-lg p-2">
        <summary class="cursor-pointer font-bold text-slate-700">Bằng chứng: ${escapeHtml(research.top_videos.length)} video đứng đầu tìm kiếm "${escapeHtml(research.seed)}"</summary>
        ${research.top_videos.map((v) => `
          <div class="py-1 border-b border-slate-100">
            <div class="font-semibold text-slate-800">${escapeHtml(v.title)}</div>
            <div class="text-slate-500">${escapeHtml(v.channel)} · tags: ${escapeHtml(v.tags.join(', ') || '(không có)')}</div>
          </div>`).join('')}
      </details>` : '';
  }

  function renderSelected() {
    const box = el('yt-seo-selected');
    if (!yt.selected.length) {
      box.innerHTML = '<span class="text-slate-400">Chưa chọn từ khoá nào. Tích vào từ khoá ở trên; từ khoá tích đầu tiên là từ khoá chính.</span>';
      return;
    }
    box.innerHTML = yt.selected.map((kw, i) => `
      <span class="inline-flex items-center gap-1 px-2 py-1 rounded-lg border ${i === 0 ? 'bg-indigo-50 border-indigo-300 text-indigo-700 font-bold' : 'bg-white border-slate-300 text-slate-700'}">
        ${i === 0 ? '<i class="fa-solid fa-star"></i>' : ''}${escapeHtml(kw)}
        ${i === 0 ? '' : `<button type="button" class="yt-seo-make-main text-indigo-600 hover:text-indigo-800" data-index="${escapeHtml(i)}" title="Đặt làm từ khoá chính">↑</button>`}
        <button type="button" class="yt-seo-unselect text-slate-400 hover:text-rose-600" data-index="${escapeHtml(i)}" title="Bỏ chọn">×</button>
      </span>`).join('');
  }

  function renderChecks(checks) {
    const box = el('yt-seo-checks');
    const failed = (checks || []).filter((c) => !c.ok);
    const passed = (checks || []).length - failed.length;
    box.className = `rounded-lg border p-2 ${failed.length ? 'bg-rose-50 border-rose-200 text-rose-600' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`;
    box.innerHTML = failed.length
      ? `<div class="font-bold">Chưa đạt ${escapeHtml(failed.length)} luật (đạt ${escapeHtml(passed)}). Sửa rồi bấm Lưu và kiểm lại:</div>`
        + failed.map((c) => `<div>✗ ${escapeHtml(c.message)}</div>`).join('')
      : `<div class="font-bold">✓ Đạt cả ${escapeHtml(passed)} luật YouTube. Tải về được.</div>`;
  }

  function renderPack() {
    const pack = yt.data && yt.data.pack;
    el('yt-seo-result').classList.toggle('hidden', !pack);
    if (!pack) return;
    el('yt-seo-title-options').innerHTML = pack.title_options.length > 1
      ? '<div class="text-slate-500">Các tiêu đề AI viết (bấm để chọn):</div>' + pack.title_options.map((t) => `
        <button type="button" class="yt-seo-title-option block w-full text-left px-2 py-1 rounded-lg border ${t === pack.title ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 bg-white hover:bg-slate-50'}" data-title="${escapeHtml(t)}">${escapeHtml(t)}</button>`).join('')
      : '';
    el('input-seo-title').value = pack.title;
    el('textarea-seo-desc').value = pack.description;
    el('input-seo-tags').value = pack.tags.join(', ');
    el('yt-seo-hashtags').value = pack.hashtags.join(' ');
    renderChecks(yt.data.checks);
    const reminder = el('yt-seo-reminder');
    reminder.classList.toggle('hidden', !yt.data.true_crime);
    reminder.textContent = 'Nhắc khi đăng: video dựa trên vụ án có thật và hình do AI tạo. Trong YouTube Studio, mục "Nội dung bị thay đổi hoặc nội dung tổng hợp", chọn Có.';
    el('btn-yt-seo-download').href = `/api/projects/${encodeURIComponent(yt.projectId)}/youtube-seo/download`;
    yt.dirty = false;
    if (pack.thumbnail_lines.length && !el('input-thumb-headline').value && !el('input-thumb-subtext').value) {
      el('input-thumb-headline').placeholder = `Để trống: dùng "${pack.thumbnail_lines.join(' / ')}" (chữ thumbnail của gói SEO)`;
    }
  }

  function renderAll() {
    const data = yt.data;
    el('yt-seo-language').textContent = data ? `Ngôn ngữ gói: ${data.language === 'en' ? 'English' : 'Tiếng Việt'}` : '';
    const api = el('yt-seo-src-api');
    api.disabled = !(data && data.has_youtube_api_key);
    if (api.disabled) api.checked = false;
    el('yt-seo-src-api-label').title = api.disabled
      ? 'Chưa có YOUTUBE_API_KEY trong file .env (key miễn phí của Google Cloud). Thêm key rồi khởi động lại app.'
      : 'Xem tiêu đề, tags của 10 video đứng đầu tìm kiếm (tốn 1 lần trong hạn mức khoảng 100 lần mỗi ngày).';
    renderResearch();
    renderSelected();
    renderPack();
  }

  // ------------------------------------------------------------------ thao tác
  async function ytSeoLoad(project) {
    yt.projectId = project.id;
    yt.data = null;
    if (!el('yt-seo-seed').value) el('yt-seo-seed').value = project.name || '';
    try {
      yt.data = await call('GET', '');
      yt.selected = yt.data.pack ? [...yt.data.pack.keywords] : [];
    } catch (e) {
      showToast('Không tải được gói SEO: ' + escapeHtml(e.message), 'error');
    }
    renderAll();
  }

  async function research() {
    const sources = [];
    if (el('yt-seo-src-suggest').checked) sources.push('youtube_suggest');
    if (el('yt-seo-src-api').checked) sources.push('youtube_data_api');
    const manual = el('yt-seo-manual').value.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
    if (!sources.length && !manual.length) {
      showToast('Chọn ít nhất một nguồn từ khoá hoặc dán từ khoá tay.', 'warning');
      return;
    }
    setBusy('btn-yt-seo-research', true, 'Đang tìm...');
    try {
      yt.data = await call('POST', '/research', { seed: el('yt-seo-seed').value.trim(), sources, manual_keywords: manual });
      const n = yt.data.research ? yt.data.research.candidates.length : 0;
      showToast(`Tìm được ${escapeHtml(n)} từ khoá. Tích chọn những từ khoá đúng nội dung video.`, 'success');
      renderAll();
    } catch (e) {
      showToast(escapeHtml(e.message), 'error', 8000);
    } finally {
      setBusy('btn-yt-seo-research', false, 'Tìm từ khoá');
    }
  }

  async function generate() {
    if (!yt.selected.length) {
      showToast('Chọn ít nhất một từ khoá trước (từ khoá tích đầu tiên là từ khoá chính).', 'warning');
      return;
    }
    setBusy('btn-yt-seo-generate', true, 'AI đang viết (khoảng 1 phút)...');
    try {
      yt.data = await call('POST', '/generate', { keywords: yt.selected });
      showToast('Đã tạo gói SEO, đạt luật YouTube.', 'success');
      renderAll();
    } catch (e) {
      if (e.checks) renderChecks(e.checks);
      showToast('Chưa tạo được gói SEO: ' + escapeHtml(e.message), 'error', 10000);
    } finally {
      setBusy('btn-yt-seo-generate', false, 'Tạo gói SEO');
    }
  }

  async function save() {
    const body = {
      title: el('input-seo-title').value,
      description: el('textarea-seo-desc').value,
      tags: el('input-seo-tags').value.split(',').map((s) => s.trim()).filter(Boolean),
      hashtags: el('yt-seo-hashtags').value.split(/\s+/).map((s) => s.trim()).filter(Boolean),
    };
    setBusy('btn-yt-seo-save', true, 'Đang kiểm...');
    try {
      yt.data = await call('PUT', '/pack', body);
      showToast('Đã lưu: đạt cả luật YouTube.', 'success');
      renderAll();
    } catch (e) {
      if (e.checks) renderChecks(e.checks);
      showToast('Chưa lưu: ' + escapeHtml(e.message), 'error', 10000);
    } finally {
      setBusy('btn-yt-seo-save', false, 'Lưu và kiểm lại');
    }
  }

  function toggleKeyword(keyword, on) {
    yt.selected = yt.selected.filter((k) => k !== keyword);
    if (on) yt.selected.push(keyword);
    renderSelected();
  }

  function bind() {
    el('btn-yt-seo-research')?.addEventListener('click', research);
    el('btn-yt-seo-generate')?.addEventListener('click', generate);
    el('btn-yt-seo-save')?.addEventListener('click', save);
    el('yt-seo-candidates')?.addEventListener('change', (ev) => {
      const box = ev.target.closest('.yt-seo-kw');
      if (box) toggleKeyword(box.dataset.kw, box.checked);
    });
    el('yt-seo-selected')?.addEventListener('click', (ev) => {
      const btn = ev.target.closest('.yt-seo-make-main, .yt-seo-unselect');
      if (!btn) return;
      const keyword = yt.selected[Number(btn.dataset.index)];
      if (keyword === undefined) return;
      if (btn.classList.contains('yt-seo-unselect')) {
        toggleKeyword(keyword, false);
        renderResearch();
      } else {
        yt.selected = [keyword, ...yt.selected.filter((k) => k !== keyword)];
        renderSelected();
      }
    });
    el('yt-seo-title-options')?.addEventListener('click', (ev) => {
      const btn = ev.target.closest('.yt-seo-title-option');
      if (!btn) return;
      el('input-seo-title').value = btn.dataset.title;
      yt.dirty = true;
    });
    ['input-seo-title', 'textarea-seo-desc', 'input-seo-tags', 'yt-seo-hashtags'].forEach((id) => {
      el(id)?.addEventListener('input', () => { yt.dirty = true; });
    });
    el('btn-yt-seo-download')?.addEventListener('click', (ev) => {
      if (yt.dirty) {
        ev.preventDefault();
        showToast('Bạn vừa sửa gói SEO: bấm Lưu và kiểm lại trước khi tải (file tải về là bản đã lưu, đã đạt luật).', 'warning', 7000);
      }
    });
  }

  window.ytSeoLoad = ytSeoLoad;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
