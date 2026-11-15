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
  const st = { timer: null, busy: false, planning: false, lastKey: '', pid: null };

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
    if (pop) { pop.hidden = true; pop.textContent = ''; pop.style.right = ''; }
    el('btn-one-pass-run')?.setAttribute('aria-expanded', 'false');
  }

  // Ô nổi neo ở mép phải nút; màn hẹp (thanh nút xuống dòng) thì đẩy sang phải cho khỏi tràn mép trái / phải
  function keepInView(pop) {
    pop.style.right = '0px';
    const gap = 8;
    const r = pop.getBoundingClientRect();
    if (r.left < gap) pop.style.right = `${r.left - gap}px`;
    const r2 = pop.getBoundingClientRect();
    if (r2.right > window.innerWidth - gap) {
      pop.style.right = `${parseFloat(pop.style.right) + (r2.right - (window.innerWidth - gap))}px`;
    }
  }

  // "Tạo ảnh còn thiếu" (app.js runSceneBatch) hay nút ảnh trên thẻ đang chạy ở trình duyệt: không chạy chen
  function browserImageBusy() {
    if (el('btn-auto-gen-all')?.dataset.busy === '1') return 'Đang chạy "Tạo ảnh còn thiếu"';
    if (typeof SceneJobsInFlight !== 'undefined' && SceneJobsInFlight.image.size) return 'Đang tạo ảnh cho một cảnh';
    if ((project()?.scenes || []).some(s => s.status_image === 'generating')) return 'Có cảnh đang tạo ảnh';
    return '';
  }

  function setPlanning(on) {
    st.planning = on;
    const run = el('btn-one-pass-run');
    if (!run) return;
    run.disabled = on || st.busy;
    run.classList.toggle('ws-cx-busy', on);
    const label = run.querySelector('span:not(.ws-cx-spinner)');
    if (label) label.textContent = on ? 'Đang tính kế hoạch…' : (st.busy ? 'Đang tạo hình…' : 'Tạo hình cho cả dự án');
    let spin = run.querySelector('.ws-cx-spinner');
    if (on && !spin) {
      spin = node('span', 'ws-cx-spinner');
      spin.setAttribute('aria-hidden', 'true');
      run.prepend(spin);
    } else if (!on && spin) {
      spin.remove();
    }
  }

  function sceneNumbers(nums) {
    const shown = nums.slice(0, 12).join(', ');
    return nums.length > 12 ? `${shown}…` : shown;
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
    // Phần đầu luôn thấy: dòng tổng và nút; phần dưới (ghi chú, điều kiện thiếu) cuộn trong ô
    const head = node('div', 'ws-op-pop-head');
    head.appendChild(node('p', 'ws-op-pop-title', summaryLine(plan)));
    const missing = plan.missing || [];
    const groups = plan.missing_groups || [];
    const canRun = plan.images + plan.climax_videos > 0;
    const actions = node('div', 'ws-op-pop-actions');
    if (canRun) {
      actions.appendChild(button(missing.length ? 'Chạy phần làm được' : 'Chạy', 'ws-btn ws-btn-primary',
        () => start(pid)));
    }
    actions.appendChild(button('Huỷ', 'ws-btn ws-btn-ghost', closePop));
    const pages = [];
    for (const g of groups) if (!pages.some(p => p.page === g.page)) pages.push({ page: g.page, label: g.page_label });
    for (const p of pages) actions.appendChild(button(`Mở trang ${p.label}`, 'ws-btn', () => goTo(p.page)));
    head.appendChild(actions);
    if (!canRun) head.appendChild(node('p', 'ws-note', 'Không còn ảnh hay video nào làm được lúc này.'));
    pop.appendChild(head);

    const body = node('div', 'ws-op-pop-body');
    const notes = [];
    if (plan.images_climax) notes.push(`Gồm cả ${plan.images_climax} ảnh cho cảnh cao trào chưa có ảnh.`);
    if (plan.climax_videos) {
      notes.push('Cảnh cao trào: Muse vẽ lưới 9 khung, app tự duyệt rồi làm clip ngay (mỗi cảnh 10–75 phút).');
    }
    const pending = plan.grids_pending_review || [];
    if (pending.length) {
      notes.push(`${pending.length} lưới đang chờ bạn duyệt sẽ được TỰ DUYỆT rồi làm clip luôn: `
        + `${pending.map(x => x.label).join(', ')}. Muốn vẽ lại lưới nào thì bấm "Vẽ lại grid" trên thẻ đó trước.`);
    }
    if (plan.climax_ready) notes.push(`${plan.climax_ready} cảnh cao trào đã có video, không làm lại.`);
    if (!plan.climax_total) notes.push('Chưa chọn cảnh cao trào nào: chỉ tạo ảnh. Muốn có video thì bấm "AI chọn cảnh cao trào" trước.');
    notes.push('Làm lần lượt từng cảnh, chạy nền; cảnh lỗi thì ghi lý do và làm tiếp cảnh sau.');
    if (missing.length) {
      body.appendChild(node('p', 'ws-op-pop-warn', `${missing.length} cảnh cao trào còn thiếu điều kiện, sẽ bị bỏ qua:`));
      const list = node('ul', 'ws-op-missing');
      for (const g of groups) {
        const n = (g.scene_ids || []).length;
        list.appendChild(node('li', '', `${g.reason} — ${n} cảnh: ${sceneNumbers(g.numbers || [])}`));
      }
      body.appendChild(list);
    }
    for (const t of notes) body.appendChild(node('p', 'ws-note', t));
    pop.appendChild(body);
    pop.hidden = false;
    keepInView(pop);
    el('btn-one-pass-run')?.setAttribute('aria-expanded', 'true');
  }

  async function openPlan() {
    if (!usable() || st.busy || st.planning) return;
    const pop = el('one-pass-pop');
    if (pop && !pop.hidden) { closePop(); return; }
    const busy = browserImageBusy();
    if (busy) {
      showToast(escapeHtml(`${busy}, chờ xong rồi bấm "Tạo hình cho cả dự án".`), 'info', 6000);
      return;
    }
    const pid = currentId();
    setPlanning(true);
    try {
      if (typeof flushProjectSave === 'function') await flushProjectSave({ silent: true });
      const plan = await call(pid, 'GET', '/plan');
      if (currentId() !== pid) return;
      if (plan.running) { poll(pid); return; }
      setPlanning(false);
      showPlan(pid, plan);
    } catch (err) {
      showToast(`Tạo hình cho cả dự án: ${escapeHtml(err.message)}`, 'error', 8000);
    } finally {
      if (st.planning) setPlanning(false);
    }
  }

  async function start(pid) {
    closePop();
    if (currentId() !== pid) return;
    const busy = browserImageBusy();
    if (busy) {
      showToast(escapeHtml(`${busy}, chờ xong rồi bấm lại.`), 'info', 6000);
      return;
    }
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
    if (run && !st.planning) {
      run.disabled = busy;
      run.classList.toggle('opacity-30', busy);
      run.classList.toggle('cursor-not-allowed', busy);
      const label = run.querySelector('span:not(.ws-cx-spinner)');
      if (label) label.textContent = busy ? 'Đang tạo hình…' : 'Tạo hình cho cả dự án';
    }
    // "Tạo ảnh còn thiếu" chạy ở trình duyệt: khoá trong lúc lượt máy chủ chạy; chỉ mở lại khi chính file này đã khoá
    // (app.js có thể đang tự khoá nút trong lúc chạy lượt của nó)
    const gen = el('btn-auto-gen-all');
    if (gen && busy && !gen.disabled) {
      gen.disabled = true;
      gen.dataset.onePassLock = '1';
    } else if (gen && !busy && gen.dataset.onePassLock === '1') {
      gen.disabled = false;
      delete gen.dataset.onePassLock;
    }
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
          + ` · xong ${(s.images_done || []).length} ảnh, ${(s.videos_done || []).length} video`
          + ((s.failed || []).length ? ` · lỗi ${(s.failed || []).length} (mới nhất: ${s.failed[s.failed.length - 1].label}: `
            + `${s.failed[s.failed.length - 1].error})` : '')
          + ((s.skipped || []).length ? ` · bỏ qua ${(s.skipped || []).length}` : '');
      } else if (s.total) {
        const failed = (s.failed || []).map(f => `${f.label} (${f.error})`);
        text.textContent = `Xong ${(s.images_done || []).length} ảnh, ${(s.videos_done || []).length} video`
          + (s.stopped ? ', đã dừng theo yêu cầu' : '')
          + (failed.length ? `; lỗi ${failed.length}: ${failed.join('; ')}` : '')
          + ((s.skipped || []).length ? `; bỏ qua ${(s.skipped || []).length}: ${(s.skipped || []).map(x => `${x.label} (${x.reason})`).join('; ')}` : '')
          + '.';
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
