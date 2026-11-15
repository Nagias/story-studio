/* Khối "Kết nối AI, YouTube, giọng đọc" ở trang Tài khoản và kết nối (#accounts-connections).
 * API: GET /api/connections/status (mỗi lần mở trang), POST /api/connections/llm-ping (nút #btn-connections-ping, tốn 1 lượt AI).
 * Dùng onPageShow, escapeHtml của workspace.js / app.js. Server không bao giờ trả khoá, chỉ true/false.
 */
(function () {
  const box = document.getElementById('accounts-connections');
  const pingBtn = document.getElementById('btn-connections-ping');
  const pingOut = document.getElementById('connections-ping-result');
  if (!box || !pingBtn) return;

  function line(label, ok, text) {
    const color = ok === true ? '#047857' : ok === false ? '#B91C1C' : '#52525B';
    return `<div style="display:flex;gap:8px;padding:3px 0"><b style="min-width:150px;color:#18181B">${escapeHtml(label)}</b>`
      + `<span style="color:${escapeHtml(color)}">${escapeHtml(text)}</span></div>`;
  }

  async function loadStatus() {
    try {
      const res = await fetch('/api/connections/status');
      if (!res.ok) throw new Error(`Máy chủ trả lỗi HTTP ${res.status}`);
      const d = await res.json();
      box.innerHTML = [
        line('Cổng AI viết lời', null, d.llm.base_url),
        line('Khoá cổng AI', d.llm.has_key, d.llm.has_key ? 'Đã có khoá' : 'Chưa có khoá (thêm NINEROUTER_API_KEY vào file .env)'),
        line('Model chữ', null, d.llm.text_model),
        line('Model ảnh', null, d.llm.image_model),
        line('Nguồn tạo ảnh mặc định', null, d.image_provider_default),
        line('YouTube Data API', d.youtube.has_key, d.youtube.has_key ? 'Đã có khoá' : 'Chưa có khoá (gói SEO dùng gợi ý tìm kiếm hoặc dán tay)'),
        line('Giọng VieNeu', d.vieneu.port_open, d.vieneu.port_open ? 'Đang chạy (cổng đang mở)' : 'Chưa chạy (cổng đóng)'),
        line('Giọng Edge-TTS', null, 'Cần mạng, không kiểm trước'),
      ].join('');
    } catch (e) {
      box.innerHTML = `<span style="color:#B91C1C">Không đọc được trạng thái kết nối: ${escapeHtml(String(e.message || e))}</span>`;
    }
  }

  pingBtn.addEventListener('click', async () => {
    pingBtn.disabled = true;
    pingOut.textContent = 'Đang gọi thử...';
    try {
      const res = await fetch('/api/connections/llm-ping', { method: 'POST' });
      const d = await res.json();
      pingOut.textContent = d.ok
        ? `Cổng AI trả lời bình thường sau ${d.seconds} giây.`
        : `Gọi thử lỗi sau ${d.seconds} giây: ${d.error}`;
      pingOut.style.color = d.ok ? '#047857' : '#B91C1C';
    } catch (e) {
      pingOut.textContent = `Gọi thử lỗi: ${String(e.message || e)}`;
      pingOut.style.color = '#B91C1C';
    } finally {
      pingBtn.disabled = false;
    }
  });

  onPageShow('accounts', loadStatus);
})();
