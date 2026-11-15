/* Vẽ tất cả / duyệt tất cả ở trang Hình mẫu (task A6, 15/11/2026): người dùng không phải tự đếm nhân vật, bối cảnh.
 * "AI tìm và vẽ tất cả": (truyện chữ: AI tìm nhân vật nếu chưa có hoặc người dùng chọn tìm lại; bối cảnh: AI tìm nơi lặp
 * lại tương tự) rồi Muse vẽ lần lượt mọi bảng / ảnh chuẩn còn thiếu, bị ghi chỗ sai hoặc vẽ lỗi. Trước khi chạy báo tổng
 * số lượt Muse; đang chạy hiện "Đang vẽ 3/7: <tên>" và nút Dừng (dừng sau cái đang vẽ). "Duyệt tất cả" duyệt mọi bảng
 * đã vẽ đang chờ duyệt. Nút từng người / từng nơi trong character_sheets.js, location_sheets.js vẫn giữ để sửa riêng.
 * API: POST .../characters|locations/draw-all, GET .../draw-all/status, POST .../draw-all/stop, POST .../approve-all
 * (routers/character_sheets.py, routers/location_sheets.py, vòng lặp ở services/look_batch.py).
 * Nạp sau app.js, character_sheets.js, location_sheets.js; dùng AppState, showToast, escapeHtml của app.js. Chữ chèn
 * bằng textContent; nút chỉ gắn sự kiện ở đây (CLAUDE.md đường cấm 9, 10).
 */
(function () {
  const el = (id) => document.getElementById(id);
  const POLL_MS = 3000;
  const ANALYZE_POLL_MS = 2000;
  const ANALYZE_MAX_MS = 15 * 60 * 1000;
  const DRAW_STATUSES = ['draft', 'failed'];   // như BATCH_DRAW_STATUSES ở services

  const KINDS = {
    characters: {
      path: 'characters', listKey: 'characters', idKey: 'entity_id', prefix: 'character',
      what: 'nhân vật', unit: 'bảng nhân vật', each: 'mỗi bảng',
      refresh: () => window.refreshCharacterSheets,
      canAnalyze: (d) => d.source !== 'case',
    },
    locations: {
      path: 'locations', listKey: 'locations', idKey: 'location_id', prefix: 'location',
      what: 'bối cảnh', unit: 'ảnh chuẩn bối cảnh', each: 'mỗi ảnh',
      refresh: () => window.refreshLocationSheets,
      canAnalyze: (d) => d.eligible_scenes >= d.min_scenes,
    },
  };
  // run: lượt bấm đang chạy ở trình duyệt {pid} (đang chờ AI tìm, đang hỏi xác nhận); timer: hỏi tiến độ
  const st = { characters: { timer: null, busy: false, lastKey: '', run: null },
               locations: { timer: null, busy: false, lastKey: '', run: null } };

  const project = () => (typeof AppState !== 'undefined' ? AppState.currentProject : null);
  const currentId = () => project()?.id || null;
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // Người dùng đổi dự án giữa lúc một lượt bấm còn chờ: bỏ lượt đó, không chạy gì cho dự án mới
  class ProjectChanged extends Error {}

  // pid: id dự án chốt lúc bấm (không lấy dự án đang mở lúc gọi)
  async function call(kind, pid, method, path) {
    const res = await fetch(`/api/projects/${encodeURIComponent(pid)}/${KINDS[kind].path}${path}`, { method });
    let data = null;
    try { data = await res.json(); } catch { /* thân không phải JSON */ }
    if (!res.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Máy chủ trả lỗi HTTP ${res.status}`);
    return data;
  }

  const ui = (kind) => {
    const pre = KINDS[kind].prefix;
    return {
      run: el(`btn-${pre}-draw-all`), approve: el(`btn-${pre}-approve-all`), stop: el(`btn-${pre}-draw-stop`),
      progress: el(`${pre}-batch-progress`), refind: el(`${pre}-batch-refind`), refindWrap: el(`${pre}-batch-refind-wrap`),
    };
  };

  function setBusy(kind, busy) {
    st[kind].busy = busy;
    const u = ui(kind);
    for (const b of [u.run, u.approve]) {
      if (!b) continue;
      b.disabled = busy;
      b.classList.toggle('opacity-30', busy);
      b.classList.toggle('cursor-not-allowed', busy);
    }
  }

  function say(kind, text) {
    const u = ui(kind);
    if (u.progress) u.progress.textContent = text;
  }

  function refreshList(kind) {
    const fn = KINDS[kind].refresh();
    if (typeof fn === 'function') fn();
  }

  function stopPolling(kind) {
    clearInterval(st[kind].timer);
    st[kind].timer = null;
  }

  const usable = () => { const p = project(); return Boolean(p && !p.is_demo); };

  function guard(pid) {
    if (currentId() !== pid) throw new ProjectChanged();
  }

  // AI tìm nhân vật / bối cảnh rồi chờ xong (chạy nền ở máy chủ, hỏi lại 2 giây một lần)
  async function analyzeAndWait(kind, pid) {
    const k = KINDS[kind];
    say(kind, `AI đang đọc kịch bản để tìm ${k.what}…`);
    await call(kind, pid, 'POST', '/analyze');
    const end = Date.now() + ANALYZE_MAX_MS;
    while (Date.now() < end) {
      await sleep(ANALYZE_POLL_MS);
      guard(pid);
      const d = await call(kind, pid, 'GET', '');
      guard(pid);
      if (!d.analyzing) {
        if (d.analysis_error) throw new Error(`AI tìm ${k.what} lỗi: ${d.analysis_error}`);
        return d;
      }
    }
    throw new Error(`AI tìm ${k.what} quá lâu, mở lại trang Hình mẫu để xem kết quả`);
  }

  async function runAll(kind) {
    if (!usable() || st[kind].busy) return;
    const k = KINDS[kind];
    const u = ui(kind);
    const pid = currentId();
    const run = { pid };
    st[kind].run = run;
    setBusy(kind, true);
    let polling = false;
    try {
      let d = await call(kind, pid, 'GET', '');
      guard(pid);
      const items = () => d[k.listKey] || [];
      const wantFind = items().length === 0 || Boolean(u.refind?.checked);
      let searched = false;
      if (wantFind && k.canAnalyze(d)) {
        d = await analyzeAndWait(kind, pid);
        searched = true;
        if (u.refind) u.refind.checked = false;
        refreshList(kind);
      }
      if (!items().length) {
        if (searched) {
          throw new Error(kind === 'locations'
            ? 'AI đọc kịch bản xong nhưng không tìm thấy nơi nào lặp lại từ 2 cảnh trở lên'
            : 'AI đọc kịch bản xong nhưng không tìm thấy nhân vật nào');
        }
        throw new Error(kind === 'locations'
          ? `Dự án cần ít nhất ${d.min_scenes} cảnh có hình vẽ mới tìm được bối cảnh lặp lại`
          : 'Dự án chưa có nhân vật nào');
      }
      const n = items().filter(x => DRAW_STATUSES.includes(x.status) && !x.drawing).length;
      if (!n) {
        say(kind, `Không còn ${k.unit} nào cần vẽ (${items().length} ${k.what}).`);
        return;
      }
      const ok = window.confirm(`Sẽ vẽ ${n} ${k.unit}, ${k.each} 1 lượt Muse (tổng ${n} lượt). Muse vẽ lần lượt từng cái. Tiếp tục?`);
      guard(pid);   // hộp xác nhận chờ người dùng: dự án có thể đã đổi trong lúc đó
      if (!ok) {
        say(kind, '');
        return;
      }
      const s = await call(kind, pid, 'POST', '/draw-all');
      guard(pid);
      polling = true;
      poll(kind, pid);
      showStatus(kind, s);
    } catch (err) {
      polling = false;   // lỗi ở bất kỳ bước nào (kể cả sau khi đã gửi draw-all): thôi hỏi, mở khoá nút
      stopPolling(kind);
      if (!(err instanceof ProjectChanged)) {
        say(kind, '');
        showToast(`Vẽ tất cả ${k.what}: ${escapeHtml(err.message)}`, 'error', 8000);
      }
    } finally {
      if (st[kind].run === run) st[kind].run = null;
      if (currentId() !== pid) {
        sync(kind);   // lượt cũ bỏ dở: bật lại nút theo đúng dự án đang mở
      } else if (!polling) {
        setBusy(kind, false);
        ui(kind).stop?.classList.add('hidden');
      }
    }
  }

  function showStatus(kind, s) {
    const k = KINDS[kind];
    const u = ui(kind);
    if (s.running) {
      const n = Math.min(s.done + 1, s.total);
      say(kind, s.stop_requested
        ? `Đang vẽ ${n}/${s.total}: ${s.current || '…'} — sẽ dừng sau ${k.unit} này`
        : `Đang vẽ ${n}/${s.total}: ${s.current || '…'}`);
    } else if (s.total) {
      const failed = (s.failed || []).map(f => `${f.name || f.entity_id} (${f.error})`);
      say(kind, `Đã vẽ ${(s.drawn || []).length}/${s.total}${s.stopped ? ', đã dừng theo yêu cầu' : ''}`
        + `${failed.length ? `; lỗi ${failed.length}: ${failed.join('; ')}` : ''}.`);
    }
    if (u.stop) {
      u.stop.classList.toggle('hidden', !s.running);
      u.stop.disabled = Boolean(s.stop_requested);
    }
    setBusy(kind, Boolean(s.running));
  }

  // Hỏi tiến độ lượt vẽ tất cả của đúng dự án pid; đổi dự án thì thôi hỏi (sync() theo dõi dự án mới)
  function poll(kind, pid) {
    stopPolling(kind);
    st[kind].lastKey = '';
    const tick = async () => {
      if (currentId() !== pid) { stopPolling(kind); return; }
      let s;
      try {
        s = await call(kind, pid, 'GET', '/draw-all/status');
      } catch (err) {
        console.warn('look batch', err);
        return;
      }
      if (currentId() !== pid) { stopPolling(kind); return; }
      try {
        showStatus(kind, s);
        const key = `${s.done}|${s.current_id}|${s.running}`;
        if (key !== st[kind].lastKey) {   // sang cái mới hay xong một cái: vẽ lại danh sách bằng hàm sẵn có
          st[kind].lastKey = key;
          refreshList(kind);
        }
        if (!s.running) {
          stopPolling(kind);
          if (s.total) {
            const bad = (s.failed || []).length;
            showToast(escapeHtml(`Vẽ tất cả ${KINDS[kind].what}: xong ${(s.drawn || []).length}/${s.total}${bad ? `, lỗi ${bad}` : ''}`),
              bad ? 'error' : 'success', 6000);
          }
        }
      } catch (err) {   // lỗi khi vẽ giao diện: không để nút khoá mãi
        console.error('look batch', err);
        stopPolling(kind);
        setBusy(kind, false);
      }
    };
    st[kind].timer = setInterval(tick, POLL_MS);
    tick();
  }

  async function stopRun(kind) {
    const pid = currentId();
    if (!pid) return;
    try {
      const s = await call(kind, pid, 'POST', '/draw-all/stop');
      if (currentId() === pid) showStatus(kind, s);
    } catch (err) {
      showToast(`Dừng: ${escapeHtml(err.message)}`, 'error', 6000);
    }
  }

  async function approveAll(kind) {
    if (!usable() || st[kind].busy) return;
    const k = KINDS[kind];
    const pid = currentId();
    try {
      const d = await call(kind, pid, 'GET', '');
      guard(pid);
      const n = (d[k.listKey] || []).filter(x => x.status === 'review' && !x.drawing).length;
      if (!n) {
        showToast(escapeHtml(`Không có ${k.unit} nào đang chờ duyệt`), 'info', 4000);
        return;
      }
      const ok = window.confirm(`Duyệt ${n} ${k.unit} đang chờ duyệt? Bảng bị ghi chỗ sai hoặc chưa vẽ thì không duyệt.`);
      guard(pid);
      if (!ok) return;
      const r = await call(kind, pid, 'POST', '/approve-all');
      const failed = r.failed || [];
      const extra = failed.length ? `, ${failed.length} không duyệt được: ${failed.map(f => f.error).join('; ')}` : '';
      showToast(escapeHtml(`Đã duyệt ${r.approved} ${k.unit}${extra}`), failed.length ? 'error' : 'success',
        failed.length ? 8000 : 4000);
    } catch (err) {
      if (err instanceof ProjectChanged) return;
      showToast(`Duyệt tất cả ${k.what}: ${escapeHtml(err.message)}`, 'error', 7000);
    }
    if (currentId() === pid) refreshList(kind);
  }

  // Mở trang Hình mẫu / đổi dự án: ẩn ô "tìm lại" khi không tìm được (vụ án lấy từ bảng tên), tiếp tục theo dõi lượt
  // vẽ tất cả đang chạy ở máy chủ (lượt chạy sống qua lần tải lại trang). Lượt bấm của dự án khác còn đang chờ thì giữ
  // nút khoá: lượt đó tự bỏ ở lần chờ kế tiếp rồi gọi lại sync().
  async function sync(kind) {
    stopPolling(kind);
    say(kind, '');
    ui(kind).stop?.classList.add('hidden');
    const pid = currentId();
    const pending = st[kind].run;
    setBusy(kind, Boolean(pending));
    if (pending || !usable()) return;
    try {
      const d = await call(kind, pid, 'GET', '');
      if (currentId() !== pid) return;
      ui(kind).refindWrap?.classList.toggle('hidden', !KINDS[kind].canAnalyze(d));
      const s = await call(kind, pid, 'GET', '/draw-all/status');
      if (currentId() !== pid || st[kind].run) return;
      if (s.running) poll(kind, pid);
    } catch (err) {
      console.warn('look batch', err);
    }
  }

  function onLookPage() {
    return typeof window.currentPage === 'function' && window.currentPage() === 'look';
  }

  function init() {
    for (const kind of Object.keys(KINDS)) {
      const u = ui(kind);
      u.run?.addEventListener('click', () => runAll(kind));
      u.approve?.addEventListener('click', () => approveAll(kind));
      u.stop?.addEventListener('click', () => stopRun(kind));
    }
    let last = null;
    setInterval(() => {   // vào trang Hình mẫu hoặc đổi dự án: đồng bộ lại hai khối
      const key = onLookPage() ? (currentId() || '') : null;
      if (key !== last) {
        last = key;
        if (key !== null) Object.keys(KINDS).forEach(sync);
        else Object.keys(KINDS).forEach(stopPolling);
      }
    }, 1000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
