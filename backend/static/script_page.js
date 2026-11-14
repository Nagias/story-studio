/* Trang "Kịch bản và giọng": sửa lời kể từng cảnh và chọn giọng ở MỘT chỗ.
 * Nạp sau app.js. Dựng bằng DOM (textContent) nên không chèn chữ thô vào HTML (đường cấm 9).
 * Gọi lại các hàm có sẵn của app.js: updateSceneText, updateSceneTextLive, moveScene, duplicateScene, deleteScene,
 * playSceneVoice, seekSceneAudio, regenerateSceneVoice. */
(function () {
  'use strict';

  function mk(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function toolBtn(icon, title, onClick, opts) {
    const b = mk('button', 'ws-srow-btn' + (opts && opts.danger ? ' ws-srow-danger' : ''));
    b.type = 'button';
    b.title = title;
    if (opts && opts.disabled) b.disabled = true;
    b.appendChild(mk('i', 'fa-solid ' + icon));
    b.addEventListener('click', onClick);
    return b;
  }

  function buildRow(scene, idx, total) {
    const state = (typeof AppState !== 'undefined' ? AppState : null) || {};
    const isSelected = idx === state.selectedSceneIndex;
    const playing = isSelected && state.isPlaying;
    const generating = scene.status_voice === 'generating';

    const row = mk('div', 'ws-srow' + (isSelected ? ' ws-srow-selected' : ''));
    row.dataset.index = String(idx);

    row.appendChild(mk('span', 'ws-srow-num', String(idx + 1)));

    const ta = mk('textarea', 'ws-srow-text');
    ta.rows = 2;
    ta.value = scene.text || '';
    ta.placeholder = 'Nhập lời kể cho cảnh này...';
    ta.addEventListener('input', () => updateSceneTextLive(idx, ta.value));
    ta.addEventListener('change', () => {
      updateSceneText(idx, ta.value);
      const dur = row.querySelector('.ws-srow-dur');
      const sc = state.currentProject && state.currentProject.scenes[idx];
      if (dur && sc) dur.textContent = (sc.duration || 5).toFixed(1) + 's';
      updateSummary();
    });
    row.appendChild(ta);

    const side = mk('div', 'ws-srow-side');
    side.appendChild(mk('span', 'ws-srow-dur', (scene.duration || 5).toFixed(1) + 's'));

    const play = toolBtn(playing ? 'fa-pause' : 'fa-play', 'Nghe thử giọng đọc của cảnh này', () => playSceneVoice(idx));
    play.classList.add('ws-srow-play');
    side.appendChild(play);

    const bar = mk('div', 'ws-srow-seek');
    bar.title = 'Bấm để tua giọng đọc';
    const fill = mk('div', 'ws-srow-seek-fill');
    fill.id = 'scene-progress-' + idx;
    bar.appendChild(fill);
    bar.addEventListener('click', (ev) => seekSceneAudio(idx, ev));
    side.appendChild(bar);
    row.appendChild(side);

    const tools = mk('div', 'ws-srow-tools');
    tools.appendChild(toolBtn('fa-arrow-up', 'Đưa cảnh lên', () => moveScene(idx, -1), { disabled: idx === 0 }));
    tools.appendChild(toolBtn('fa-arrow-down', 'Đưa cảnh xuống', () => moveScene(idx, 1), { disabled: idx === total - 1 }));
    tools.appendChild(toolBtn('fa-copy', 'Nhân bản cảnh', () => duplicateScene(idx)));
    tools.appendChild(toolBtn('fa-trash-can', 'Xoá cảnh này', () => deleteScene(idx), { danger: true }));
    tools.appendChild(toolBtn(generating ? 'fa-rotate-right fa-spin' : 'fa-rotate-right',
      'Thu lại giọng của cảnh này (tốn lượt đọc giọng)', () => regenerateSceneVoice(idx)));
    row.appendChild(tools);
    return row;
  }

  function updateSummary() {
    const project = typeof AppState !== 'undefined' && AppState ? AppState.currentProject : null;
    const count = document.getElementById('script-scene-count');
    const dur = document.getElementById('script-total-duration');
    if (count) count.textContent = String(project && project.scenes ? project.scenes.length : 0);
    if (dur && project && typeof calculateTotalDuration === 'function') dur.textContent = calculateTotalDuration();
  }

  function renderScriptList() {
    const box = document.getElementById('script-scene-list');
    if (!box) return;
    const project = typeof AppState !== 'undefined' && AppState ? AppState.currentProject : null;
    const scenes = (project && project.scenes) || [];
    box.replaceChildren();
    updateSummary();
    if (!scenes.length) {
      box.appendChild(mk('p', 'ws-lede ws-srow-empty', 'Chưa có cảnh nào. Bấm "Thêm cảnh" hoặc nhập kịch bản ở trang Ý tưởng.'));
      return;
    }
    scenes.forEach((scene, idx) => box.appendChild(buildRow(scene, idx, scenes.length)));
  }
  window.renderScriptList = renderScriptList;

  function showScriptTab(name) {
    document.querySelectorAll('#script-tabs [data-tab]').forEach((t) => {
      t.setAttribute('aria-selected', t.dataset.tab === name ? 'true' : 'false');
    });
    document.querySelectorAll('#page-script [data-tab-panel]').forEach((p) => {
      p.hidden = p.dataset.tabPanel !== name;
    });
  }
  window.showScriptTab = showScriptTab;

  document.querySelectorAll('#script-tabs [data-tab]').forEach((t) => {
    t.addEventListener('click', () => showScriptTab(t.dataset.tab));
  });

  if (typeof window.onPageShow === 'function') window.onPageShow('script', renderScriptList);
  renderScriptList();
})();
