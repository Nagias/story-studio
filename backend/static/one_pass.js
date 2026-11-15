/* Nút "Tạo hình cho cả dự án" ở trang Cảnh (task B 15/11/2026): cảnh thường ra ảnh, cảnh cao trào ra video, một lần
 * bấm. Bấm: hỏi kế hoạch (không tốn gì), hiện ô xác nhận "X ảnh cho cảnh thường · Y video cho cảnh cao trào · khoảng Z
 * lượt Muse"; điều kiện còn thiếu (chưa có giọng, nhân vật chưa duyệt bảng) liệt kê kèm nút mở trang cần tới, và nút
 * "Chạy phần làm được" bỏ qua cảnh thiếu điều kiện. Đang chạy: thanh tiến độ, nút Dừng (dừng sau bước đang làm), thẻ
 * cảnh tải lại sau mỗi cảnh xong. "Tạo ảnh còn thiếu" (#btn-auto-gen-all, app.js) vẫn giữ làm nút phụ.
 * API: GET .../one-pass/plan, POST .../one-pass/run, GET .../one-pass/status, POST .../one-pass/stop
 * (routers/one_pass_visuals.py, services/one_pass_visuals.py).
 * Nạp sau app.js; dùng AppState, API, showToast, escapeHtml, renderSceneList, flushProjectSave, mergeServerSceneMedia
 * của app.js lúc chạy. Chữ chèn bằng textContent; nút chỉ gắn sự kiện ở đây (CLAUDE.md đường cấm 9, 10).
 */
(function () {
  const el = (id) => document.getElementById(id);
  const POLL_MS = 3000;
  const st = { timer: null, busy: false, lastKey: '', pid: null };

  const project = () => (typeof AppState !== 'undefined' ? AppState.currentProject : null);
  const currentId = () => project()?.id || null;
  const usable = () => { const p = project(); return Boolean(p && !p.is_demo && (p.scenes || []).length); };

  async function call(pid, method, path) {
    const res = await fetch(`/api/projects/${encodeURIComponent(pid)}/one-pass${path}`, { method });
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

  function button(text, cls, onClick) {
    const b = node('button', cls, text);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  // ---------------------------------------------------------------------------------------------- ô xác nhận
  function closePop() {
    const pop = el('one-pass-pop');
    if (pop) { pop.hidden = true; pop.textContent = ''; }
    el('btn-one-pass-run')?.setAttribute('aria-expanded', 'false');
  }

  function goTo(page) {
    closePop();
    if (typeof window.showPage === 'function') window.showPage(page);
  }

  function summaryLine(plan) {
    return `${plan.images_normal} ảnh cho cảnh thường · ${plan.climax_videos} video cho cảnh cao trào · `
      + `khoảng ${plan.muse_turns} lượt Muse`;
  }

  function showPlan(pid, plan) {
    const pop = el('one-pass-pop');
    if (!pop) return;
    pop.textContent = '';
    pop.appendChild(node('p', 'ws-op-pop-title', summaryLine(plan)));
    const notes = [];
    if (plan.images_climax) notes.push(`Gồm cả ${plan.images_climax} ảnh cho cảnh cao trào chưa có ảnh.`);
    if (plan.climax_videos) {
      notes.push('Cảnh cao trào: Muse vẽ lưới 9 khung, app tự duyệt rồi làm clip ngay (mỗi cảnh 10–75 phút).');
    }
    if (plan.climax_ready) notes.push(`${plan.climax_ready} cảnh cao trào đã có video, không làm lại.`);
    if (!plan.climax_total) notes.push('Chưa chọn cảnh cao trào nào: chỉ tạo ảnh. Muốn có video thì bấm "AI chọn cảnh cao trào" trước.');
    notes.push('Làm lần lượt từng cảnh, chạy nền; cảnh lỗi thì ghi lý do và làm tiếp cảnh sau.');
    for (const t of notes) pop.appendChild(node('p', 'ws-note', t));

    const missing = plan.missing || [];
    if (missing.length) {
      pop.appendChild(node('p', 'ws-op-pop-warn', `${missing.length} cảnh cao trào còn thiếu điều kiện, sẽ bị bỏ qua:`));
      const list = node('ul', 'ws-op-missing');
      for (const m of missing) list.appendChild(node('li', '', `${m.label}: ${m.reason}`));
      pop.appendChild(list);
      const pages = [];
      for (const m of missing) if (!pages.some(p => p.page === m.page)) pages.push({ page: m.page, label: m.page_label });
      const go = node('div', 'ws-op-pop-actions');
      for (const p of pages) go.appendChild(button(`Mở trang ${p.label}`, 'ws-btn', () => goTo(p.page)));
      pop.appendChild(go);
    }
    const canRun = plan.images + plan.climax_videos > 0;
    const actions = node('div', 'ws-op-pop-actions');
    if (canRun) {
      actions.appendChild(button(missing.length ? 'Chạy phần làm được' : 'Chạy', 'ws-btn ws-btn-primary',
        () => start(pid)));
    } else {
      pop.appendChild(node('p', 'ws-note', 'Không còn ảnh hay video nào làm được lúc này.'));
    }
    actions.appendChild(button('Huỷ', 'ws-btn ws-btn-ghost', closePop));
    pop.appendChild(actions);
    pop.hidden = false;
    el('btn-one-pass-run')?.setAttribute('aria-expanded', 'true');
  }

  async function openPlan() {
    if (!usable() || st.busy) return;
    const pop = el('one-pass-pop');
    if (pop && !pop.hidden) { closePop(); return; }
    const pid = currentId();
    try {
      if (typeof flushProjectSave === 'function') await flushProjectSave({ silent: true });
      const plan = await call(pid, 'GET', '/plan');
      if (currentId() !== pid) return;
      if (plan.running) { poll(pid); return; }
      showPlan(pid, plan);
    } catch (err) {
      showToast(`Tạo hình cho cả dự án: ${escapeHtml(err.message)}`, 'error', 8000);
    }
  }

  async function start(pid) {
    closePop();
    if (currentId() !== pid) return;
    try {
      if (typeof flushProjectSave === 'function') await flushProjectSave({ silent: true });
      const data = await call(pid, 'POST', '/run');
      showToast(escapeHtml(`Đã bắt đầu: ${summaryLine(data)}.`), 'info', 6000);
      poll(pid);
    } catch (err) {
      showToast(`Không chạy được: ${escapeHtml(err.message)}`, 'error', 8000);
    }
  }

  // ---------------------------------------------------------------------------------------------- tiến độ
  function setBusy(busy) {
    st.busy = busy;
    const run = el('btn-one-pass-run');
    if (run) {
      run.disabled = busy;
      run.classList.toggle('opacity-30', busy);
      run.classList.toggle('cursor-not-allowed', busy);
      const label = run.querySelector('span');
      if (label) label.textContent = busy ? 'Đang tạo hình…' : 'Tạo hình cho cả dự án';
    }
    const gen = el('btn-auto-gen-all');   // "Tạo ảnh còn thiếu" chạy ở trình duyệt: không chạy chen lượt máy chủ
    if (gen) gen.disabled = busy;
  }

  function showStatus(s) {
    const box = el('one-pass-progress');
    const text = el('one-pass-progress-text');
    const fill = el('one-pass-bar-fill');
    const stop = el('btn-one-pass-stop');
    const show = Boolean(s.running || s.total);
    if (box) box.hidden = !show;
    if (fill) fill.style.width = `${s.total ? Math.round(100 * Math.min(s.done, s.total) / s.total) : 0}%`;
    if (text) {
      if (s.running) {
        const step = s.phase === 'climax' ? 'Làm video cao trào' : 'Tạo ảnh';
        const n = Math.min(s.done + 1, s.total);
        text.textContent = `${step} ${n}/${s.total}: ${s.current || '…'}`
          + (s.stop_requested ? ' — sẽ dừng sau bước này' : '')
          + ((s.failed || []).length ? ` · lỗi ${(s.failed || []).length}` : '');
      } else if (s.total) {
        const failed = (s.failed || []).map(f => `${f.label} (${f.error})`);
        const fb = (s.fallbacks || []).map(f => `${f.label}: ${f.provider} vì ${f.reason}`);
        text.textContent = `Xong ${(s.images_done || []).length} ảnh, ${(s.videos_done || []).length} video`
          + (s.stopped ? ', đã dừng theo yêu cầu' : '')
          + (failed.length ? `; lỗi ${failed.length}: ${failed.join('; ')}` : '')
          + ((s.skipped || []).length ? `; bỏ qua ${(s.skipped || []).length}: ${(s.skipped || []).map(x => `${x.label} (${x.reason})`).join('; ')}` : '')
          + (fb.length ? `; ảnh không dùng Muse: ${fb.join('; ')}` : '') + '.';
      } else {
        text.textContent = '';
      }
    }
    if (stop) {
      stop.classList.toggle('hidden', !s.running);
      stop.disabled = Boolean(s.stop_requested);
    }
    setBusy(Boolean(s.running));
  }

  function stopPolling() {
    clearInterval(st.timer);
    st.timer = null;
  }

  async function pullScenes(pid) {
    if (typeof API === 'undefined' || typeof mergeServerSceneMedia !== 'function') return;
    const remote = await API.getProject(pid);
    if (!remote || !remote.scenes || currentId() !== pid) return;
    for (const s of project().scenes || []) mergeServerSceneMedia(remote, s.id);
    if (typeof renderSceneList === 'function') renderSceneList();
  }

  function poll(pid) {
    stopPolling();
    st.lastKey = '';
    st.pid = pid;
    const tick = async () => {
      if (currentId() !== pid) { stopPolling(); return; }
      let s;
      try {
        s = await call(pid, 'GET', '/status');
      } catch (err) {
        console.warn('one-pass status', err);
        return;
      }
      if (currentId() !== pid) { stopPolling(); return; }
      try {
        showStatus(s);
        const key = `${s.done}|${s.current_id}|${s.running}`;
        if (key !== st.lastKey) {   // xong một cảnh hay sang cảnh mới: tải lại thẻ cảnh bằng hàm sẵn có
          st.lastKey = key;
          await pullScenes(pid);
        }
        if (!s.running) {
          stopPolling();
          if (s.total) {
            const bad = (s.failed || []).length;
            showToast(escapeHtml(`Tạo hình cho cả dự án: xong ${(s.images_done || []).length} ảnh, `
              + `${(s.videos_done || []).length} video${bad ? `, lỗi ${bad}` : ''}`), bad ? 'warning' : 'success', 8000);
          }
        }
      } catch (err) {   // lỗi khi vẽ giao diện: không để nút khoá mãi
        console.error('one-pass', err);
        stopPolling();
        setBusy(false);
      }
    };
    st.timer = setInterval(tick, POLL_MS);
    tick();
  }

  async function stopRun() {
    const pid = currentId();
    if (!pid) return;
    try {
      const s = await call(pid, 'POST', '/stop');
      if (currentId() === pid) showStatus(s);
    } catch (err) {
      showToast(`Dừng: ${escapeHtml(err.message)}`, 'error', 6000);
    }
  }

  // Mở dự án (hoặc tải lại trang khi lượt đang chạy nền): hỏi trạng thái một lần, đang chạy thì theo dõi tiếp
  async function sync() {
    stopPolling();
    closePop();
    showStatus({ running: false, total: 0 });
    const pid = currentId();
    if (!pid || !usable()) return;
    try {
      const s = await call(pid, 'GET', '/status');
      if (currentId() !== pid) return;
      if (s.running) poll(pid);
    } catch (err) {
      console.warn('one-pass status', err);
    }
  }

  function init() {
    el('btn-one-pass-run')?.addEventListener('click', openPlan);
    el('btn-one-pass-stop')?.addEventListener('click', stopRun);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePop(); });
    let last = null;
    setInterval(() => {   // đổi dự án (switchProject trong app.js): theo dõi lượt của dự án mới
      const id = currentId();
      if (id !== last) {
        last = id;
        sync();
      }
    }, 1000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
