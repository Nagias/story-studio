/* ================= TRUE CRIME STUDIO (modal Hồ Sơ Kỳ Án, spec 7.9) =================
 * Luồng: dán vụ án -> POST /api/true-crime/analyze -> hỏi tiến độ mỗi 2 giây -> màn xem lại kế hoạch (bảng tên,
 * cảnh báo, dàn ý, lời kể Việt/Anh từng cảnh, sửa được) -> tạo dự án bản Việt -> Bước 2.
 *
 * - Mọi request đi qua tcFetch(). Lỗi HTTP ném Error(detail) với thông báo tiếng Việt của máy chủ. Không có nhánh nào
 *   dựng kế hoạch giả hay dữ liệu mẫu: không có kế hoạch từ máy chủ thì màn xem lại để trống.
 * - Mỗi nút hành động bị khoá trong lúc request của nó đang chạy, nên bấm hai lần không gửi hai request.
 * - Các thao tác sửa kế hoạch (tên, lời kể) và tạo dự án chạy nối tiếp nhau (tcEnqueue), nên kế hoạch đang vẽ luôn là
 *   bản máy chủ trả về sau cùng.
 * - case_id đang theo dõi được nhớ trong localStorage: đóng modal hay tải lại trang, mở lại vẫn thấy tiến độ hoặc màn
 *   xem lại. Quên khi đã tạo dự án, khi bấm "Phân tích vụ khác", hoặc khi máy chủ không còn vụ đó.
 * - Kế hoạch có tên thật (bible.entities[].real_names, một số cảnh báo): đó là dữ liệu của chính người dùng trên máy họ,
 *   chỉ hiện ở màn xem lại. create-project chỉ gửi ngôn ngữ, giọng, phong cách và engine hình.
 * - Bảng ghim trong modal vẽ từ bản sao evidence/relations của kế hoạch (chỉ nhãn, không có mô tả), không sửa kế
 *   hoạch và không gửi gì lên máy chủ.
 * Dùng các global của app.js: DOM, AppState, showToast, escapeHtml, switchProject, switchStep, loadProjectsList.
 */

const TC_API = '/api/true-crime';
const TC_POLL_MS = 2000;          // hỏi tiến độ mỗi 2 giây khi đang phân tích
const TC_POLL_RETRY_MS = 5000;    // mất kết nối tạm thời: hỏi lại chậm hơn
const TC_CASE_KEY = 'story_studio_true_crime_case_id';
const TC_EN_DEFAULT_VOICE = 'en-US-AndrewMultilingualNeural';
const TC_MAX_SOURCE_CHARS = 200000;

const TC_KIND_LABELS = { person: 'Người', place: 'Địa danh', organization: 'Tổ chức', identifier: 'Định danh' };
const TC_ROLE_LABELS = {
  victim: 'nạn nhân', suspect: 'nghi phạm', perpetrator: 'hung thủ', witness: 'nhân chứng',
  investigator: 'điều tra viên', family: 'người nhà', other: ''
};
const TC_PART_LABELS = {
  hook: 'Mở đầu', setup: 'Bối cảnh', discovery: 'Phát hiện', investigation: 'Điều tra', twist: 'Bước ngoặt',
  resolution: 'Kết luận', open_questions: 'Câu hỏi bỏ ngỏ', epilogue: 'Kết'
};
const TC_VISUAL_LABELS = { image: 'Ảnh', video: 'Video', board: 'Bảng ghim', disclaimer: 'Miễn trừ' };
const TC_FLAG_LABELS = {
  unknown_name: 'Tên thật chưa có tên thay thế', date: 'Ngày tháng cụ thể', missing_text: 'Thiếu lời kể',
  bad_reveal: 'Bảng ghim nhắc tới mục không có'
};

// Hồ sơ mẫu: chỉ nạp chữ vào ô nhập, không tự phân tích.
const TC_SAMPLES = {
  sample1: `Đêm mưa bão ngày 14/10, tại căn biệt thự ven biển Cảng Tân Hải (Hải Phòng), đại gia ngành đóng tàu Chu Doãn (58 tuổi) được phát hiện tử vong tại phòng đọc sách tầng 2. Tử thi nằm gục bên bàn cờ tướng, cạnh một chén trà sen còn ấm có độc thạch tín nồng độ cao. Két sắt âm tường bị mở toang, mất tích bức tượng Phật ngọc cổ trị giá hơn 20 tỷ đồng.
Khám nghiệm hiện trường cho thấy không có dấu vết cạy phá cửa hay trèo ban công. Các nhân vật liên quan gồm:
1. Lữ Bách (Kế toán trưởng): Nợ cờ bạc hơn 5 tỷ đồng, bị ông Chu Doãn dọa báo công an vì biển thủ quỹ 3 ngày trước.
2. Mai Thục (Giúp việc 12 năm): Người duy nhất được giao pha trà sen mỗi tối và biết mật mã mở cửa phòng sách, tuy nhiên có bằng chứng camera đi siêu thị từ 21h30 đến 22h15.
3. Chu Cường (Con trai thứ): Mâu thuẫn gay gắt do bị tước quyền thừa kế trong bản di chúc mới.
Đặc biệt, bảo vệ cổng xác nhận lúc 22h15 có một chiếc taxi mang biển kiểm soát 15A-882.19 đón một người mặc áo mưa trùm kín đầu vội vã rời cổng phụ...`,
  sample2: `Đêm 28/08, giám đốc kiểm toán tài chính Trịnh Văn Hoàng rơi từ ban công tầng 13 tòa tháp đôi thương mại xuống đất tử vong. Toàn bộ máy chủ và máy tính cá nhân bị cài mã độc wipe sạch dữ liệu lúc 23h30.
Trước khi tử vong 15 phút, thẻ quẹt ra vào an ninh ghi nhận kỹ sư phần mềm Lê Quốc Tuấn có mặt tại tầng 13. Tuy nhiên Tuấn xuất trình hóa đơn thanh toán quán bar ở quận 3 cùng lúc đó. Tại hiện trường, cảnh sát thu giữ mảnh giấy bị xé vội ghi dãy số bí ẩn '70-30-DELTA' và chiếc USB bị bẻ đôi giấu trong chậu cây cảnh phòng họp...`,
  sample3: `Rạng sáng ngày 03/11, công nhân cạo mủ cao su bàng hoàng phát hiện một chiếc xe máy SH bỏ lại vệ đường ven rừng cao su xã An Lập. Cách đó 50m là áo mưa màu vàng dính bùn đỏ và chiếc bật lửa Zippo vàng khắc chữ 'V.K'.
Nạn nhân là thương lái nông sản Vũ Khang, mất tích 2 ngày trước cùng vali tiền mặt 1,2 tỷ mang đi thu mua sầu riêng. Bác sĩ pháp y xác định nạn nhân bị siết cổ từ phía sau. Dấu vết lốp xe tải loại 1,5 tấn quay đầu gấp để lại vết phanh trượt dài trên nền đất ẩm...`
};

const TrueCrimeState = {
  caseId: null,          // vụ án đang theo dõi
  plan: null,            // kế hoạch máy chủ trả về sau cùng (không bao giờ bị sửa ở client)
  progress: null,        // {status, step_label, steps_done, steps_total, error}
  modalOpen: false,
  pollTimer: null,
  pollInFlight: false,
  pollAgain: false,
  voicesPromise: null,
  busy: new Set(),       // tên các hành động đang chạy: analyze, resume, entities, add-entity, create
  queue: Promise.resolve(),
  sceneEls: new Map(),   // order -> {card, vi, en, flags, status, countVi, countEn}
  board: { nodes: [], edges: [], scale: 1, filter: 'all', lang: 'vi', hovered: null }
};

// ================= TIỆN ÍCH =================

function tcEl(id) {
  return document.getElementById(id);
}

function tcEsc(value) {
  return escapeHtml(String(value ?? ''));
}

function tcWordCount(text) {
  const trimmed = String(text || '').trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

function tcFold(text) {
  return String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[đĐ]/g, 'd').toLowerCase();
}

function tcReadCaseId() {
  try { return localStorage.getItem(TC_CASE_KEY) || null; } catch { return null; }
}

function tcRememberCaseId(caseId) {
  try { localStorage.setItem(TC_CASE_KEY, caseId); } catch { /* chế độ riêng tư / bị chặn */ }
}

function tcForgetCaseId() {
  try { localStorage.removeItem(TC_CASE_KEY); } catch { /* chế độ riêng tư / bị chặn */ }
}

function tcCaseUrl(caseId, suffix = '') {
  return `${TC_API}/cases/${encodeURIComponent(caseId)}${suffix}`;
}

function tcPlanFlagCount(plan) {
  if (!plan) return 0;
  return (plan.flags || []).length + (plan.scenes || []).filter(s => (s.flags || []).length).length;
}

function tcPlanHasFlags(plan) {
  return tcPlanFlagCount(plan) > 0;
}

function tcSortedScenes(plan) {
  return [...((plan && plan.scenes) || [])].sort((a, b) => a.order - b.order);
}

// ================= GỌI MÁY CHỦ =================

function tcErrorDetail(data, status) {
  const detail = data && data.detail;
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (Array.isArray(detail) && detail.length) {      // lỗi kiểm dữ liệu của FastAPI (422)
    const parts = detail.slice(0, 3).map(item => {
      const field = Array.isArray(item?.loc) ? item.loc.filter(p => p !== 'body').join('.') : '';
      const msg = item?.msg || 'không hợp lệ';
      return field ? `${field}: ${msg}` : msg;
    });
    return `Dữ liệu gửi lên không hợp lệ (${parts.join('; ')}).`;
  }
  return `Máy chủ trả lỗi HTTP ${status}.`;
}

async function tcFetch(url, options = {}) {
  const init = { method: options.method || 'GET', headers: { Accept: 'application/json' } };
  if (options.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.body);
  }
  let res;
  let raw = '';
  try {
    res = await fetch(url, init);
    raw = await res.text();
  } catch {
    const error = new Error('Không kết nối được máy chủ Story Studio. Kiểm tra máy chủ còn chạy rồi thử lại.');
    error.status = 0;
    throw error;
  }
  let data = null;
  if (raw) {
    try { data = JSON.parse(raw); } catch { data = null; }
  }
  if (!res.ok) {
    const error = new Error(tcErrorDetail(data, res.status));
    error.status = res.status;
    throw error;
  }
  return data;
}

// Chạy `fn` dưới tên `name`; đang chạy thì lần bấm sau bị bỏ qua (nút cũng bị khoá).
async function tcWithBusy(name, fn) {
  if (TrueCrimeState.busy.has(name)) return undefined;
  TrueCrimeState.busy.add(name);
  tcRefreshButtons();
  try {
    return await fn();
  } finally {
    TrueCrimeState.busy.delete(name);
    tcRefreshButtons();
  }
}

// Các thao tác đổi kế hoạch chạy lần lượt, theo thứ tự người dùng làm.
function tcEnqueue(task) {
  const run = TrueCrimeState.queue.then(() => task());
  TrueCrimeState.queue = run.catch(() => {});
  return run;
}

// ================= NÚT VÀ THÔNG BÁO =================

function tcSetBusyLabel(btn, busy, label) {
  if (!btn) return;
  if (busy) {
    if (btn.dataset.idleHtml === undefined) btn.dataset.idleHtml = btn.innerHTML;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>${tcEsc(label)}</span>`;
  } else if (btn.dataset.idleHtml !== undefined) {
    btn.innerHTML = btn.dataset.idleHtml;
    delete btn.dataset.idleHtml;
  }
}

function tcRefreshButtons() {
  const s = TrueCrimeState;
  const busy = name => s.busy.has(name);
  const failed = s.progress?.status === 'failed';

  const analyze = tcEl('btn-tc-analyze');
  if (analyze) {
    analyze.disabled = !!s.caseId || busy('analyze');
    analyze.title = s.caseId ? 'Đang theo dõi một vụ án. Bấm "Phân tích vụ khác" để bắt đầu vụ mới.' : '';
    tcSetBusyLabel(analyze, busy('analyze'), 'Đang gửi vụ án...');
  }

  const resume = tcEl('btn-tc-resume');
  if (resume) {
    resume.classList.toggle('hidden', !failed);
    resume.disabled = busy('resume');
    tcSetBusyLabel(resume, busy('resume'), 'Đang gửi...');
  }

  const newCase = tcEl('btn-tc-new-case');
  if (newCase) newCase.disabled = busy('analyze') || busy('resume') || busy('create');

  const saveEntities = tcEl('btn-tc-save-entities');
  if (saveEntities) {
    saveEntities.disabled = !s.plan || busy('entities');
    tcSetBusyLabel(saveEntities, busy('entities'), 'Đang lưu tên...');
  }

  const addEntity = tcEl('btn-tc-add-entity');
  if (addEntity) {
    addEntity.disabled = !s.plan || busy('add-entity');
    tcSetBusyLabel(addEntity, busy('add-entity'), 'Đang thêm...');
  }

  const create = tcEl('btn-tc-create-vi');
  if (create) {
    create.disabled = !s.plan || tcPlanHasFlags(s.plan) || busy('create');
    tcSetBusyLabel(create, busy('create'), 'Đang tạo dự án...');
  }
  tcRenderCreateHint();
}

function tcRenderCreateHint() {
  const hint = tcEl('tc-create-hint');
  const icon = tcEl('tc-create-hint-icon');
  if (!hint || !icon) return;
  const plan = TrueCrimeState.plan;
  let text = 'Phân tích xong và không còn cảnh bị đánh dấu thì tạo được dự án bản Việt.';
  let iconClass = 'fa-solid fa-circle-info text-slate-500';
  if (!plan && TrueCrimeState.caseId) {
    text = TrueCrimeState.progress?.status === 'failed'
      ? 'Phân tích bị dừng: bấm "Thử lại" để chạy tiếp từ bước bị dừng.'
      : 'Đang phân tích; xong mới tạo được dự án.';
  } else if (plan) {
    const flagged = tcSortedScenes(plan).filter(s => (s.flags || []).length).map(s => s.order);
    const planFlags = (plan.flags || []).length;
    if (flagged.length || planFlags) {
      const where = [];
      if (flagged.length) where.push(`cảnh ${flagged.slice(0, 8).join(', ')}${flagged.length > 8 ? '...' : ''}`);
      if (planFlags) where.push('tên tập hoặc nhãn bảng ghim');
      text = `Còn mục bị đánh dấu (${where.join('; ')}): sửa lời kể hoặc thêm tên rồi mới tạo được dự án.`;
      iconClass = 'fa-solid fa-triangle-exclamation text-rose-400';
    } else {
      text = `Sẵn sàng tạo dự án bản Việt (${(plan.scenes || []).length} cảnh).`;
      iconClass = 'fa-solid fa-circle-check text-emerald-400';
    }
  }
  hint.textContent = text;
  icon.className = iconClass;
}

function tcShowInputError(message) {
  const box = tcEl('tc-input-error');
  if (!box) return;
  box.textContent = message || '';
  box.classList.toggle('hidden', !message);
}

function tcUpdateWordCount() {
  const text = tcEl('tc-case-text')?.value || '';
  const counter = tcEl('tc-case-word-count');
  if (!counter) return;
  const tooLong = text.length > TC_MAX_SOURCE_CHARS;
  counter.textContent = `${tcWordCount(text)} từ • ${text.length} ký tự${tooLong ? ' (quá 200.000 ký tự)' : ''}`;
  counter.classList.toggle('text-rose-300', tooLong);
  counter.classList.toggle('text-slate-400', !tooLong);
}

function tcLoadSample(key) {
  const text = TC_SAMPLES[key];
  const input = tcEl('tc-case-text');
  if (!text || !input) return;
  const current = input.value;
  if (current.trim() && current !== text && !window.confirm('Thay nội dung đang có trong ô bằng hồ sơ mẫu?')) return;
  input.value = text;
  tcUpdateWordCount();
  tcShowInputError('');
  showToast('Đã nạp hồ sơ mẫu vào ô nhập. Bấm "Phân tích hồ sơ" khi sẵn sàng.', 'info');
}

// ================= GIỌNG ĐỌC =================

function tcFillVoiceSelect(select, voices, defaultId) {
  if (!select) return;
  const previous = select.value;
  select.innerHTML = '';
  if (!voices.length) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'Không có giọng nào cho ngôn ngữ này (dùng giọng mặc định của máy chủ)';
    select.appendChild(opt);
    return;
  }
  voices.forEach(voice => {
    const opt = document.createElement('option');
    opt.value = String(voice.id);
    opt.textContent = voice.name ? String(voice.name) : String(voice.id);
    select.appendChild(opt);
  });
  select.value = voices.some(v => String(v.id) === previous) ? previous : (defaultId || String(voices[0].id));
}

function tcLoadVoices() {
  if (TrueCrimeState.voicesPromise) return TrueCrimeState.voicesPromise;
  TrueCrimeState.voicesPromise = (async () => {
    const viSelect = tcEl('tc-voice-vi');
    const enSelect = tcEl('tc-voice-en');
    try {
      const data = await tcFetch('/api/voices');
      const list = Array.isArray(data) ? data.filter(v => v && v.id) : [];
      const locale = v => String(v.locale || '').toLowerCase();
      const vi = list.filter(v => locale(v).startsWith('vi'));
      const en = list.filter(v => locale(v).startsWith('en'));
      // Việt: giọng VieNeu đầu tiên; Anh: en-US-AndrewMultilingualNeural (spec, mục Giọng mặc định)
      const viDefault = (vi.find(v => String(v.id).startsWith('vieneu-')) || vi[0])?.id;
      const enDefault = en.some(v => v.id === TC_EN_DEFAULT_VOICE) ? TC_EN_DEFAULT_VOICE : en[0]?.id;
      tcFillVoiceSelect(viSelect, vi, viDefault && String(viDefault));
      tcFillVoiceSelect(enSelect, en, enDefault && String(enDefault));
    } catch (err) {
      TrueCrimeState.voicesPromise = null;     // lần mở modal sau thử lại
      [viSelect, enSelect].forEach(select => tcFillVoiceSelect(select, [], ''));
      showToast(`Không tải được danh sách giọng: ${tcEsc(err.message)}`, 'warning', 6000);
    }
  })();
  return TrueCrimeState.voicesPromise;
}

// ================= PHÂN TÍCH VÀ TIẾN ĐỘ =================

async function tcAnalyze() {
  if (TrueCrimeState.caseId) return;
  await tcWithBusy('analyze', async () => {
    const raw = tcEl('tc-case-text')?.value || '';
    tcShowInputError('');
    if (!raw.trim()) {
      tcShowInputError('Hãy dán bài viết về vụ án vào ô trước khi phân tích.');
      return;
    }
    const body = {
      raw_report: raw,
      target_minutes: parseInt(tcEl('tc-duration-select')?.value || '8', 10),
      visual_style: tcEl('tc-visual-style')?.value || 'neo_noir_silhouette'
    };
    try {
      const res = await tcFetch(`${TC_API}/analyze`, { method: 'POST', body });
      if (!res || !res.case_id) throw new Error('Máy chủ không trả mã vụ án.');
      tcFollowCase(res.case_id);
      showToast('Đã gửi vụ án cho máy chủ phân tích. Có thể đóng modal; mở lại sẽ thấy tiến độ.', 'info', 6000);
    } catch (err) {
      tcShowInputError(err.message);
      showToast(`Không bắt đầu phân tích được: ${tcEsc(err.message)}`, 'error', 7000);
    }
  });
}

function tcFollowCase(caseId) {
  TrueCrimeState.caseId = caseId;
  TrueCrimeState.plan = null;
  TrueCrimeState.progress = null;
  tcRememberCaseId(caseId);
  tcBuildBoard();
  tcRenderProgress();
  tcRenderReview();
  tcStartPolling();
}

// Thôi theo dõi vụ án hiện tại (vụ án vẫn nằm trên máy chủ).
function tcDetach() {
  tcStopPolling();
  tcForgetCaseId();
  TrueCrimeState.caseId = null;
  TrueCrimeState.plan = null;
  TrueCrimeState.progress = null;
  tcBuildBoard();
  tcRenderProgress();
  tcRenderReview();
}

function tcCaseMissing(message) {
  tcDetach();
  tcShowInputError(message || 'Máy chủ không còn vụ án đang theo dõi (có thể đã bị xoá). Hãy phân tích lại.');
}

function tcNewCase() {
  if (!TrueCrimeState.caseId) return;
  let message = 'Giao diện sẽ thôi theo dõi vụ hiện tại (kế hoạch vẫn lưu trên máy chủ). Phân tích một vụ khác?';
  if (!TrueCrimeState.plan) {
    message = TrueCrimeState.progress?.status === 'failed'
      ? 'Vụ bị dừng vẫn nằm trên máy chủ, nhưng giao diện sẽ thôi theo dõi nó (không bấm Thử lại được nữa). Phân tích một vụ khác?'
      : 'Vụ đang phân tích vẫn chạy tiếp trên máy chủ, nhưng giao diện sẽ thôi theo dõi nó. Phân tích một vụ khác?';
  }
  if (!window.confirm(message)) return;
  tcDetach();
  tcShowInputError('');
  tcEl('tc-case-text')?.focus();
}

function tcStopPolling() {
  if (TrueCrimeState.pollTimer) {
    clearTimeout(TrueCrimeState.pollTimer);
    TrueCrimeState.pollTimer = null;
  }
}

function tcSchedulePoll(delay) {
  tcStopPolling();
  if (!TrueCrimeState.modalOpen || !TrueCrimeState.caseId) return;
  TrueCrimeState.pollTimer = setTimeout(tcPollProgress, delay);
}

function tcStartPolling() {
  tcSchedulePoll(0);
}

async function tcPollProgress() {
  TrueCrimeState.pollTimer = null;
  const caseId = TrueCrimeState.caseId;
  if (!caseId || !TrueCrimeState.modalOpen) return;
  if (TrueCrimeState.pollInFlight) {       // đang có một lần hỏi: hỏi lại ngay khi lần đó xong
    TrueCrimeState.pollAgain = true;
    return;
  }
  TrueCrimeState.pollInFlight = true;
  TrueCrimeState.pollAgain = false;
  let next = null;
  try {
    const progress = await tcFetch(tcCaseUrl(caseId, '/progress'));
    if (caseId !== TrueCrimeState.caseId) return;
    TrueCrimeState.progress = progress;
    tcRenderProgress();
    if (progress.status === 'running') {
      next = TC_POLL_MS;
    } else if (progress.status === 'done') {
      await tcLoadPlan(caseId);
    }
    // failed: dừng hỏi, chờ người dùng bấm "Thử lại"
  } catch (err) {
    if (caseId !== TrueCrimeState.caseId) return;
    if ([400, 404, 422].includes(err.status)) {
      tcCaseMissing(err.status === 404 ? '' : `Không theo dõi được vụ án đã lưu: ${err.message}`);
      return;
    }
    tcRenderProgressNotice(`Chưa hỏi được tiến độ: ${err.message} Sẽ hỏi lại sau ít giây.`);
    next = TC_POLL_RETRY_MS;
  } finally {
    TrueCrimeState.pollInFlight = false;
    if (TrueCrimeState.pollAgain) {
      TrueCrimeState.pollAgain = false;
      next = 0;
    }
    if (next !== null) tcSchedulePoll(next);
  }
}

async function tcLoadPlan(caseId) {
  try {
    const plan = await tcFetch(tcCaseUrl(caseId));
    if (caseId !== TrueCrimeState.caseId) return;
    tcSetPlan(plan);
  } catch (err) {
    if (caseId !== TrueCrimeState.caseId) return;
    if (err.status === 404) {
      tcCaseMissing();
      return;
    }
    // 409: máy chủ chưa có kế hoạch (trạng thái vừa đổi); lỗi khác: mất kết nối... -> hỏi lại tiến độ
    tcRenderProgressNotice(`Chưa tải được kế hoạch: ${err.message}`);
    tcSchedulePoll(TC_POLL_RETRY_MS);
  }
}

async function tcResume() {
  const caseId = TrueCrimeState.caseId;
  if (!caseId) return;
  await tcWithBusy('resume', async () => {
    try {
      const progress = await tcFetch(tcCaseUrl(caseId, '/resume'), { method: 'POST' });
      if (caseId !== TrueCrimeState.caseId) return;
      TrueCrimeState.progress = progress;
      tcRenderProgress();
      if (progress.status === 'done') {
        await tcLoadPlan(caseId);
      } else {
        tcStartPolling();
        showToast('Đã cho phân tích chạy tiếp từ bước bị dừng.', 'info');
      }
    } catch (err) {
      if (err.status === 404) {
        tcCaseMissing();
        return;
      }
      showToast(`Không chạy tiếp được: ${tcEsc(err.message)}`, 'error', 7000);
    }
  });
}

function tcRenderProgress() {
  const block = tcEl('tc-progress');
  if (!block) return;
  const s = TrueCrimeState;
  block.classList.toggle('hidden', !s.caseId);
  const p = s.progress;
  const status = p?.status || 'running';
  const done = Number(p?.steps_done) || 0;
  const total = Number(p?.steps_total) || 0;
  const percent = status === 'done' ? 100 : (total ? Math.min(100, Math.round(done / total * 100)) : 0);

  const label = tcEl('tc-progress-label');
  if (label) label.textContent = p?.step_label || (s.caseId ? 'Đang hỏi tiến độ...' : '');
  const count = tcEl('tc-progress-count');
  if (count) count.textContent = total ? `${done}/${total} bước` : '';
  const bar = tcEl('tc-progress-bar');
  if (bar) {
    bar.style.width = `${percent}%`;
    bar.className = 'h-full rounded-full transition-all duration-300 ' +
      (status === 'failed' ? 'bg-amber-500' : status === 'done' ? 'bg-emerald-500' : 'bg-red-500');
  }
  const icon = tcEl('tc-progress-icon');
  if (icon) {
    icon.className = status === 'failed' ? 'fa-solid fa-triangle-exclamation text-rose-400'
      : status === 'done' ? 'fa-solid fa-circle-check text-emerald-400'
        : 'fa-solid fa-spinner fa-spin text-amber-400';
  }
  const error = tcEl('tc-progress-error');
  if (error) {
    const message = status === 'failed' ? (p?.error || 'Phân tích bị dừng. Bấm Thử lại để chạy tiếp.') : '';
    error.textContent = message;
    error.classList.toggle('hidden', !message);
  }
  const caseLabel = tcEl('tc-progress-case');
  if (caseLabel) caseLabel.textContent = s.caseId ? `Mã vụ: ${s.caseId}` : '';
  tcRefreshButtons();
}

// Lỗi tạm thời (mất kết nối...) trong lúc vẫn theo dõi: hiện ở ô lỗi của khối tiến độ.
function tcRenderProgressNotice(message) {
  if (TrueCrimeState.progress?.status === 'failed') return;
  const error = tcEl('tc-progress-error');
  if (!error) return;
  error.textContent = message;
  error.classList.remove('hidden');
}

// ================= MÀN XEM LẠI =================

function tcSetPlan(plan) {
  const firstLoad = TrueCrimeState.plan?.case_id !== plan.case_id;
  TrueCrimeState.plan = plan;
  if (firstLoad) {
    // Ô phong cách hình trở về phong cách đã chọn lúc phân tích (sau khi tải lại trang ô này về mặc định)
    const style = tcEl('tc-visual-style');
    if (style && [...style.options].some(o => o.value === plan.visual_style)) style.value = plan.visual_style;
  }
  tcBuildBoard();
  tcRenderReview();
}

async function tcReloadPlan() {
  const caseId = TrueCrimeState.caseId;
  if (caseId) await tcLoadPlan(caseId);
}

function tcRenderReview() {
  const plan = TrueCrimeState.plan;
  tcEl('tc-review-empty')?.classList.toggle('hidden', !!plan);
  tcEl('tc-review')?.classList.toggle('hidden', !plan);
  if (plan) {
    tcRenderSummary(plan);
    tcRenderWarnings(plan);
    tcRenderEntities(plan);
    tcRenderOutline(plan);
    tcRenderScenes(plan);
    tcRenderScrubber(plan);
  } else {
    const list = tcEl('tc-scene-review');
    if (list) {
      list.innerHTML = '';
      delete list.dataset.orders;
    }
    TrueCrimeState.sceneEls = new Map();
    const table = tcEl('tc-entity-table');
    if (table) {
      table.innerHTML = '';
      delete table.dataset.ids;
    }
  }
  EvidenceBoardRenderer.render();
  tcRefreshButtons();
}

function tcRenderSummary(plan) {
  const bible = plan.bible || {};
  const titleVi = tcEl('tc-plan-title-vi');
  if (titleVi) titleVi.textContent = bible.title_vi || '(chưa có tên tập tiếng Việt)';
  const titleEn = tcEl('tc-plan-title-en');
  if (titleEn) titleEn.textContent = bible.title_en ? `EN: ${bible.title_en}` : '';
  const stats = tcEl('tc-plan-stats');
  if (stats) {
    const scenes = (plan.scenes || []).length;
    const flagged = (plan.scenes || []).filter(s => (s.flags || []).length).length;
    stats.textContent = `${plan.target_minutes} phút • ${scenes} cảnh • ${(plan.parts || []).length} nhịp • ${flagged} cảnh bị đánh dấu`;
  }
}

function tcRenderWarnings(plan) {
  const box = tcEl('tc-warnings');
  if (!box) return;
  const styles = {
    block: 'bg-[#2d161a] border border-rose-500/50 text-rose-200',
    warn: 'bg-[#2c2214] border border-amber-500/50 text-amber-200',
    info: 'bg-slate-900 border border-slate-700 text-slate-300',
    ok: 'bg-[#14261e] border border-emerald-500/50 text-emerald-200'
  };
  const icons = {
    block: 'fa-solid fa-ban text-rose-400',
    warn: 'fa-solid fa-triangle-exclamation text-amber-400',
    info: 'fa-solid fa-circle-info text-slate-400',
    ok: 'fa-solid fa-circle-check text-emerald-400'
  };
  const items = [];
  const flagged = tcSortedScenes(plan).filter(s => (s.flags || []).length);
  if (flagged.length) {
    const links = flagged.map(s =>
      `<button type="button" data-tc-goto="${tcEsc(s.order)}" class="underline hover:text-white cursor-pointer">${tcEsc(s.order)}</button>`
    ).join(', ');
    items.push({ level: 'block', html: `Còn ${flagged.length} cảnh bị đánh dấu, chưa tạo được dự án: cảnh ${links}.` });
  }
  (plan.flags || []).forEach(flag => {
    items.push({ level: 'block', text: `${TC_FLAG_LABELS[flag.kind] || flag.kind} (${flag.field}): ${flag.detail}` });
  });
  (plan.check_warnings || []).forEach(text => items.push({ level: 'warn', text }));
  (plan.warnings || []).forEach(text => items.push({ level: 'info', text }));
  if (!items.length) items.push({ level: 'ok', text: 'Không có cảnh báo: đã kiểm lọt tên thật và ngày tháng.' });

  box.innerHTML = items.map(item => `
    <div class="${styles[item.level]} rounded-lg px-2.5 py-1.5 leading-relaxed flex items-start gap-1.5">
      <i class="${icons[item.level]} mt-0.5 shrink-0"></i>
      <span class="min-w-0">${item.html !== undefined ? item.html : tcEsc(item.text)}</span>
    </div>`).join('');
}

function tcGotoScene(order) {
  const card = TrueCrimeState.sceneEls.get(Number(order))?.card;
  if (!card) return;
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  const target = card.querySelector('textarea:not([readonly])');
  if (target) setTimeout(() => target.focus({ preventScroll: true }), 300);
}

// ---------------- bảng tên ----------------

function tcEntityInputs() {
  return Array.from(document.querySelectorAll('#tc-entity-table input[data-tc-entity]'));
}

function tcRenderEntities(plan) {
  const body = tcEl('tc-entity-table');
  if (!body) return;
  const entities = (plan.bible && plan.bible.entities) || [];
  const ids = entities.map(e => e.id).join('|');
  // Cùng danh sách thực thể: chỉ cập nhật ô chưa sửa, giữ nguyên chữ người dùng đang gõ dở.
  if (body.dataset.ids === ids) {
    const byId = new Map(entities.map(e => [e.id, e]));
    tcEntityInputs().forEach(input => {
      const ent = byId.get(input.dataset.tcEntity);
      if (!ent) return;
      const serverValue = ent[`alias_${input.dataset.lang}`] || '';
      const dirty = input.value !== input.dataset.original;
      input.dataset.original = serverValue;
      if (!dirty) input.value = serverValue;
    });
    return;
  }
  const dirty = {};
  tcEntityInputs().forEach(input => {
    if (input.value !== input.dataset.original) dirty[`${input.dataset.tcEntity}:${input.dataset.lang}`] = input.value;
  });
  body.innerHTML = '';
  if (!entities.length) {
    body.innerHTML = '<tr><td colspan="4" class="px-2 py-2 text-slate-500">Kế hoạch chưa có tên nào.</td></tr>';
  }
  entities.forEach(ent => {
    const tr = document.createElement('tr');
    tr.className = 'border-b border-slate-800';
    const role = ent.kind === 'person' ? (TC_ROLE_LABELS[ent.role] ?? ent.role ?? '') : '';
    tr.innerHTML = `
      <td class="px-2 py-1.5 text-slate-300">
        <div class="font-semibold">${tcEsc(TC_KIND_LABELS[ent.kind] || ent.kind)}</div>
        <div class="text-[10px] text-slate-500">${tcEsc(role)}</div>
      </td>
      <td class="px-2 py-1.5 text-red-300 font-mono text-[11px]">${tcEsc((ent.real_names || []).join('; '))}</td>
      <td class="px-2 py-1.5" data-slot="vi"></td>
      <td class="px-2 py-1.5" data-slot="en"></td>`;
    ['vi', 'en'].forEach(lang => {
      const input = document.createElement('input');
      input.type = 'text';
      input.maxLength = 120;
      input.className = 'w-full bg-slate-950/90 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-200 focus:border-red-500 focus:outline-none';
      input.dataset.tcEntity = ent.id;
      input.dataset.lang = lang;
      input.dataset.original = ent[`alias_${lang}`] || '';
      input.value = dirty[`${ent.id}:${lang}`] ?? input.dataset.original;
      input.setAttribute('aria-label', `Tên ${lang === 'vi' ? 'Việt' : 'Anh'} của ${ent.id}`);
      tr.querySelector(`[data-slot="${lang}"]`).appendChild(input);
    });
    body.appendChild(tr);
  });
  body.dataset.ids = ids;
}

async function tcSaveEntities() {
  const plan = TrueCrimeState.plan;
  if (!plan) return;
  const caseId = plan.case_id;
  const changedIds = new Set(tcEntityInputs().filter(i => i.value !== i.dataset.original).map(i => i.dataset.tcEntity));
  if (!changedIds.size) {
    showToast('Chưa có tên nào được sửa.', 'info');
    return;
  }
  await tcWithBusy('entities', () => tcEnqueue(async () => {
    if (caseId !== TrueCrimeState.caseId) return;
    const inputs = tcEntityInputs().filter(i => changedIds.has(i.dataset.tcEntity));
    const valueOf = (id, lang) => inputs.find(i => i.dataset.tcEntity === id && i.dataset.lang === lang)?.value ?? '';
    const updates = [...changedIds].map(id => ({ id, alias_vi: valueOf(id, 'vi'), alias_en: valueOf(id, 'en') }));
    try {
      const next = await tcFetch(tcCaseUrl(caseId, '/entities'), { method: 'PUT', body: { updates, additions: [] } });
      if (caseId !== TrueCrimeState.caseId) return;
      inputs.forEach(input => { input.value = input.dataset.original; });   // đã lưu: lấy lại giá trị máy chủ
      tcSetPlan(next);
      showToast(`Đã lưu ${updates.length} tên và áp cho toàn bộ cảnh.`, 'success');
    } catch (err) {
      tcHandleEditError(err, 'Không lưu được tên');
    }
  }));
}

async function tcAddEntity() {
  const plan = TrueCrimeState.plan;
  if (!plan) return;
  const caseId = plan.case_id;
  const kind = tcEl('tc-add-kind')?.value || 'person';
  const realNames = (tcEl('tc-add-real')?.value || '').split(/[;\n]/).map(s => s.trim()).filter(Boolean);
  const aliasVi = (tcEl('tc-add-alias-vi')?.value || '').trim();
  const aliasEn = (tcEl('tc-add-alias-en')?.value || '').trim();
  if (!realNames.length || !aliasVi || !aliasEn) {
    showToast('Điền tên thật, tên Việt và tên Anh trước khi thêm.', 'warning');
    return;
  }
  await tcWithBusy('add-entity', () => tcEnqueue(async () => {
    if (caseId !== TrueCrimeState.caseId) return;
    try {
      const next = await tcFetch(tcCaseUrl(caseId, '/entities'), {
        method: 'PUT',
        body: { updates: [], additions: [{ kind, real_names: realNames, alias_vi: aliasVi, alias_en: aliasEn }] }
      });
      if (caseId !== TrueCrimeState.caseId) return;
      ['tc-add-real', 'tc-add-alias-vi', 'tc-add-alias-en'].forEach(id => { const el = tcEl(id); if (el) el.value = ''; });
      tcSetPlan(next);
      showToast('Đã thêm tên và áp cho toàn bộ cảnh.', 'success');
    } catch (err) {
      tcHandleEditError(err, 'Không thêm được tên');
    }
  }));
}

function tcHandleEditError(err, prefix) {
  if (err.status === 404) {
    tcCaseMissing();
    return;
  }
  showToast(`${prefix}: ${tcEsc(err.message)}`, 'error', 8000);
  if (err.status === 409) tcReloadPlan();
}

// ---------------- dàn ý ----------------

function tcRenderOutline(plan) {
  const list = tcEl('tc-outline');
  if (!list) return;
  const counts = {};
  (plan.scenes || []).forEach(s => { counts[s.part_id] = (counts[s.part_id] || 0) + 1; });
  const parts = plan.parts || [];
  if (!parts.length) {
    list.innerHTML = '<li class="text-slate-500">Kế hoạch chưa có dàn ý.</li>';
    return;
  }
  list.innerHTML = parts.map((part, idx) => `
    <li class="flex items-start gap-2">
      <span class="w-6 h-6 rounded-full bg-slate-800 border border-slate-700 text-slate-300 flex items-center justify-center text-[10px] font-bold shrink-0">${idx + 1}</span>
      <div class="min-w-0">
        <div class="font-bold text-slate-200">${tcEsc(TC_PART_LABELS[part.kind] || part.kind)}
          <span class="text-[10px] text-slate-500 font-mono font-semibold">${tcEsc(counts[part.id] || 0)} cảnh</span>
        </div>
        <div class="text-slate-400 leading-relaxed">${tcEsc(part.summary_vi)}</div>
      </div>
    </li>`).join('');
}

// ---------------- danh sách cảnh ----------------

function tcSceneCardClass(flagged) {
  return flagged
    ? 'rounded-xl border-2 border-red-500 bg-slate-900/60 p-2.5 space-y-2'
    : 'rounded-xl border border-slate-800 bg-slate-900/60 p-2.5 space-y-2';
}

function tcBuildSceneCard(scene, partsById) {
  const card = document.createElement('div');
  card.id = `tc-scene-${scene.order}`;
  card.className = tcSceneCardClass((scene.flags || []).length > 0);
  const part = partsById.get(scene.part_id);
  const isDisclaimer = scene.visual_kind === 'disclaimer';
  card.innerHTML = `
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <span class="font-bold text-white">Cảnh ${tcEsc(scene.order)}</span>
        <span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono">${tcEsc(TC_VISUAL_LABELS[scene.visual_kind] || scene.visual_kind)}</span>
        <span class="text-[10px] text-slate-500">${tcEsc(part ? (TC_PART_LABELS[part.kind] || part.kind) : (isDisclaimer ? 'câu cố định' : scene.part_id))}</span>
      </div>
      <span data-role="status" class="text-[10px] text-slate-500"></span>
    </div>
    <div data-role="flags" class="hidden text-[11px] text-rose-200 space-y-0.5"></div>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
      <label class="block space-y-1">
        <span class="text-[10px] uppercase font-semibold text-slate-400">Lời Việt • <span data-role="count-vi"></span></span>
        <textarea data-lang="vi" rows="4" class="w-full bg-slate-950/90 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:border-red-500 focus:outline-none leading-relaxed resize-y"></textarea>
      </label>
      <label class="block space-y-1">
        <span class="text-[10px] uppercase font-semibold text-slate-400">Lời Anh • <span data-role="count-en"></span></span>
        <textarea data-lang="en" rows="4" class="w-full bg-slate-950/90 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:border-red-500 focus:outline-none leading-relaxed resize-y"></textarea>
      </label>
    </div>`;
  const els = {
    card,
    vi: card.querySelector('textarea[data-lang="vi"]'),
    en: card.querySelector('textarea[data-lang="en"]'),
    flags: card.querySelector('[data-role="flags"]'),
    status: card.querySelector('[data-role="status"]'),
    countVi: card.querySelector('[data-role="count-vi"]'),
    countEn: card.querySelector('[data-role="count-en"]')
  };
  ['vi', 'en'].forEach(lang => {
    const textarea = els[lang];
    textarea.value = scene[`narration_${lang}`] || '';
    textarea.dataset.original = textarea.value;
    if (isDisclaimer) {
      textarea.readOnly = true;
      textarea.classList.add('opacity-75');
      textarea.title = 'Câu miễn trừ cố định, không sửa được.';
    } else {
      textarea.addEventListener('input', () => tcUpdateSceneCounts(els));
      textarea.addEventListener('change', () => tcSaveScene(scene.order, lang, textarea));
    }
  });
  return els;
}

function tcUpdateSceneCounts(els) {
  els.countVi.textContent = `${tcWordCount(els.vi.value)} từ`;
  els.countEn.textContent = `${tcWordCount(els.en.value)} từ`;
}

function tcPatchSceneCard(els, scene) {
  const flags = scene.flags || [];
  els.card.className = tcSceneCardClass(flags.length > 0);
  els.flags.classList.toggle('hidden', !flags.length);
  els.flags.innerHTML = flags.map(flag =>
    `<div>• ${tcEsc(TC_FLAG_LABELS[flag.kind] || flag.kind)} (${tcEsc(flag.field)}): ${tcEsc(flag.detail)}</div>`
  ).join('');
  ['vi', 'en'].forEach(lang => {
    const textarea = els[lang];
    const serverValue = scene[`narration_${lang}`] || '';
    textarea.dataset.original = serverValue;
    // Không ghi đè ô đang gõ, đang lưu, hoặc còn chữ chưa lưu được
    const keep = document.activeElement === textarea || textarea.dataset.saving || textarea.dataset.unsaved;
    if (!keep && textarea.value !== serverValue) textarea.value = serverValue;
  });
  tcUpdateSceneCounts(els);
}

function tcRenderScenes(plan) {
  const list = tcEl('tc-scene-review');
  if (!list) return;
  const scenes = tcSortedScenes(plan);
  const partsById = new Map((plan.parts || []).map(p => [p.id, p]));
  const orders = scenes.map(s => s.order).join(',');
  if (list.dataset.orders !== orders) {
    list.innerHTML = '';
    TrueCrimeState.sceneEls = new Map();
    scenes.forEach(scene => {
      const els = tcBuildSceneCard(scene, partsById);
      TrueCrimeState.sceneEls.set(scene.order, els);
      list.appendChild(els.card);
    });
    list.dataset.orders = orders;
    if (!scenes.length) list.innerHTML = '<div class="text-slate-500">Kế hoạch chưa có cảnh nào.</div>';
  }
  scenes.forEach(scene => {
    const els = TrueCrimeState.sceneEls.get(scene.order);
    if (els) tcPatchSceneCard(els, scene);
  });
}

function tcSetSceneStatus(order, text, tone) {
  const status = TrueCrimeState.sceneEls.get(order)?.status;
  if (!status) return;
  status.textContent = text;
  status.className = 'text-[10px] ' + (tone === 'error' ? 'text-rose-300' : tone === 'ok' ? 'text-emerald-400' : 'text-slate-500');
}

function tcSaveScene(order, lang, textarea) {
  const plan = TrueCrimeState.plan;
  if (!plan) return undefined;
  const caseId = plan.case_id;
  const field = lang === 'vi' ? 'narration_vi' : 'narration_en';
  textarea.readOnly = true;
  textarea.dataset.saving = '1';
  tcSetSceneStatus(order, 'Đang lưu...', 'muted');
  return tcEnqueue(async () => {
    const value = textarea.value;
    try {
      if (caseId !== TrueCrimeState.caseId) return;
      const next = await tcFetch(tcCaseUrl(caseId, `/scenes/${order}`), { method: 'PUT', body: { [field]: value } });
      if (caseId !== TrueCrimeState.caseId) return;
      delete textarea.dataset.unsaved;
      delete textarea.dataset.saving;
      textarea.readOnly = false;
      tcSetPlan(next);
      const flagged = (next.scenes || []).find(s => s.order === order)?.flags?.length;
      tcSetSceneStatus(order, flagged ? 'Đã lưu, vẫn còn bị đánh dấu' : 'Đã lưu', flagged ? 'error' : 'ok');
    } catch (err) {
      textarea.dataset.unsaved = '1';
      tcSetSceneStatus(order, `Chưa lưu: ${err.message}`, 'error');
      tcHandleEditError(err, `Không lưu được lời kể cảnh ${order}`);
    } finally {
      delete textarea.dataset.saving;
      textarea.readOnly = false;
    }
  });
}

// ================= TẠO DỰ ÁN BẢN VIỆT =================

async function tcCreateVietnameseProject() {
  const plan = TrueCrimeState.plan;
  if (!plan) return;
  const caseId = plan.case_id;
  await tcWithBusy('create', () => tcEnqueue(async () => {
    const current = TrueCrimeState.plan;
    if (!current || caseId !== TrueCrimeState.caseId) return;
    if (tcPlanHasFlags(current)) {
      showToast('Kế hoạch còn mục bị đánh dấu: sửa lời kể hoặc thêm tên rồi mới tạo được dự án.', 'warning', 7000);
      return;
    }
    const voiceVi = tcEl('tc-voice-vi')?.value || '';
    const voiceEn = tcEl('tc-voice-en')?.value || '';
    const voices = {};
    if (voiceVi) voices.vi = voiceVi;
    if (voiceEn) voices.en = voiceEn;
    const body = {
      language: 'vi',
      voice: voiceVi,
      voices,
      visual_style: tcEl('tc-visual-style')?.value || current.visual_style || 'neo_noir_silhouette',
      image_provider: tcEl('tc-vision-engine')?.value || 'meta_muse_cloud'
    };
    let result;
    try {
      result = await tcFetch(tcCaseUrl(caseId, '/create-project'), { method: 'POST', body });
    } catch (err) {
      if (err.status === 404) {
        tcCaseMissing();
        return;
      }
      showToast(`Không tạo được dự án: ${tcEsc(err.message)}`, 'error', 9000);
      if (err.status === 409) await tcLoadPlan(caseId);     // vẽ lại các cảnh bị đánh dấu theo máy chủ
      return;
    }
    const projectId = result && result.project_id;
    if (!projectId) {
      showToast('Máy chủ không trả mã dự án sau khi tạo.', 'error', 7000);
      return;
    }
    tcDetach();        // dự án đã có trên máy chủ: thôi theo dõi vụ án này
    if (typeof loadProjectsList === 'function') loadProjectsList();
    await switchProject(projectId);
    if (AppState.currentProject?.id !== projectId) {
      showToast(`Đã tạo dự án ${tcEsc(projectId)} nhưng chưa mở được. Hãy mở nó trong danh sách dự án.`, 'warning', 9000);
      return;
    }
    closeTrueCrimeModal();
    switchStep(2);
    refreshLanguageVersionButton(AppState.currentProject);
    showToast('Đã tạo dự án bản Việt và chuyển sang Bảng Đạo Diễn (Bước 2).', 'success', 6000);
  }));
}

// Nút "Tạo bản tiếng Anh" ở Bước 2/4: thân hàm viết ở Task 10.
function refreshLanguageVersionButton(project) { // eslint-disable-line no-unused-vars
}

// ================= BẢNG GHIM (vẽ từ bản sao evidence/relations) =================

const TC_NODE_KEYWORDS = [
  ['weapon', ['weapon', 'hung khi', 'vu khi']],
  ['forensic_report', ['forensic', 'giam dinh', 'phap y']],
  ['location', ['location', 'place', 'dia diem', 'hien truong']],
  ['timeline_event', ['timeline', 'moc thoi gian']],
  ['victim', ['victim', 'nan nhan']],
  ['suspect', ['suspect', 'nghi pham']]
];
const TC_BADGES = {
  victim: { vi: 'NẠN NHÂN', en: 'VICTIM', color: '#dc2626', icon: '💀' },
  suspect: { vi: 'NGHI PHẠM', en: 'SUSPECT', color: '#d97706', icon: '👤' },
  person: { vi: 'NHÂN VẬT', en: 'PERSON', color: '#2563eb', icon: '👤' },
  weapon: { vi: 'HUNG KHÍ', en: 'WEAPON', color: '#059669', icon: '🗡️' },
  forensic_report: { vi: 'GIÁM ĐỊNH', en: 'FORENSICS', color: '#059669', icon: '📋' },
  location: { vi: 'ĐỊA ĐIỂM', en: 'LOCATION', color: '#2563eb', icon: '🏢' },
  timeline_event: { vi: 'MỐC GIỜ', en: 'TIMELINE', color: '#7c3aed', icon: '⏱️' },
  clue: { vi: 'CHỨNG CỨ', en: 'EVIDENCE', color: '#475569', icon: '🔍' }
};

function tcEvidenceType(kind) {
  const folded = tcFold(kind);
  if (TC_BADGES[folded] && folded !== 'person') return folded;
  const hit = TC_NODE_KEYWORDS.find(([, words]) => words.some(w => folded.includes(w)));
  return hit ? hit[0] : 'clue';
}

function tcEntityType(ent) {
  if (ent.kind === 'place') return 'location';
  if (ent.kind === 'person') {
    if (ent.role === 'victim') return 'victim';
    if (ent.role === 'suspect' || ent.role === 'perpetrator') return 'suspect';
    return 'person';
  }
  return 'clue';
}

function tcBuildBoard() {
  const board = TrueCrimeState.board;
  board.hovered = null;
  board.nodes = [];
  board.edges = [];
  const plan = TrueCrimeState.plan;
  if (!plan) return;
  // Bản sao chỉ gồm các trường cần cho bảng ghim (không có tên thật, không có mô tả)
  const bible = plan.bible || {};
  const evidence = (bible.evidence || []).map(ev => ({ id: ev.id, kind: ev.kind, label_vi: ev.label_vi, label_en: ev.label_en }));
  const relations = (bible.relations || []).map(rel => ({
    id: rel.id, source_id: rel.source_id, target_id: rel.target_id, relation_type: rel.relation_type,
    label_vi: rel.label_vi, label_en: rel.label_en
  }));
  const entities = (bible.entities || []).map(ent => ({
    id: ent.id, kind: ent.kind, role: ent.role, alias_vi: ent.alias_vi, alias_en: ent.alias_en
  }));

  const first = new Map();       // id -> order của cảnh đầu tiên cho nó hiện ra
  tcSortedScenes(plan).forEach(scene => (scene.board_reveal || []).forEach(id => {
    if (!first.has(id)) first.set(id, scene.order);
  }));
  const appears = new Map();
  evidence.forEach(ev => { if (first.has(ev.id)) appears.set(ev.id, first.get(ev.id)); });
  relations.forEach(rel => {
    if (!first.has(rel.id)) return;
    [rel.source_id, rel.target_id].forEach(end => {
      appears.set(end, Math.min(appears.get(end) ?? Infinity, first.get(rel.id)));
    });
  });

  const nodes = [];
  const evidenceIds = new Set(evidence.map(ev => ev.id));
  evidence.forEach(ev => {
    if (!appears.has(ev.id)) return;
    nodes.push({ id: ev.id, label_vi: ev.label_vi || ev.label_en, label_en: ev.label_en || ev.label_vi,
      type: tcEvidenceType(ev.kind), scene: appears.get(ev.id) });
  });
  entities.forEach(ent => {
    if (!appears.has(ent.id) || evidenceIds.has(ent.id)) return;
    nodes.push({ id: ent.id, label_vi: ent.alias_vi || ent.alias_en, label_en: ent.alias_en || ent.alias_vi,
      type: tcEntityType(ent), scene: appears.get(ent.id) });
  });
  nodes.sort((a, b) => a.scene - b.scene);
  const nodeIds = new Set(nodes.map(n => n.id));
  board.edges = relations
    .filter(rel => first.has(rel.id) && nodeIds.has(rel.source_id) && nodeIds.has(rel.target_id))
    .map(rel => ({ id: rel.id, from: rel.source_id, to: rel.target_id, label_vi: rel.label_vi || '',
      label_en: rel.label_en || '', scene: first.get(rel.id), relation_type: rel.relation_type }));

  // Xếp lưới cố định trên khung 1280x720; ít thẻ thì phóng to (tối đa 1,5 lần), nhiều thẻ thì thu nhỏ cho vừa ô.
  const count = nodes.length;
  if (count) {
    const cols = Math.max(1, Math.ceil(Math.sqrt(count * 1.8)));
    const rows = Math.ceil(count / cols);
    const cellW = 1160 / cols;
    const cellH = 600 / rows;
    board.scale = Math.min(1.5, cellW / 175, cellH / 200);
    nodes.forEach((node, idx) => {
      const col = idx % cols;
      const row = Math.floor(idx / cols);
      const stagger = rows > 1 ? ((col % 2) ? 0.08 : -0.08) * cellH : 0;
      node.x = Math.round(60 + cellW * (col + 0.5));
      node.y = Math.round(80 + cellH * (row + 0.5) + stagger);
    });
  }
  board.nodes = nodes;
}

function tcRenderScrubber(plan) {
  const select = tcEl('tc-scene-scrubber');
  if (!select) return;
  const previous = select.value;
  const orders = tcSortedScenes(plan).filter(s => (s.board_reveal || []).length).map(s => s.order);
  select.innerHTML = '<option value="all">Toàn bộ</option>' +
    orders.map(order => `<option value="${tcEsc(order)}">Tới cảnh ${tcEsc(order)}</option>`).join('');
  select.value = orders.map(String).includes(previous) ? previous : 'all';
  TrueCrimeState.board.filter = select.value;
}

const EvidenceBoardRenderer = {
  canvas: null,
  ctx: null,
  baseWidth: 155,
  baseHeight: 180,

  init(canvasElem) {
    this.canvas = canvasElem;
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.setupEvents();
    this.render();
  },

  cardSize() {
    const scale = TrueCrimeState.board.scale || 1;
    return { w: this.baseWidth * scale, h: this.baseHeight * scale, scale };
  },

  getCanvasCoords(e) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) * (this.canvas.width / (rect.width || 1)),
      y: (e.clientY - rect.top) * (this.canvas.height / (rect.height || 1))
    };
  },

  getVisibleNodes() {
    const board = TrueCrimeState.board;
    if (board.filter === 'all') return board.nodes;
    const upTo = parseInt(board.filter, 10);
    return board.nodes.filter(n => n.scene <= upTo);
  },

  getVisibleEdges() {
    const board = TrueCrimeState.board;
    const visible = new Set(this.getVisibleNodes().map(n => n.id));
    const upTo = board.filter === 'all' ? Infinity : parseInt(board.filter, 10);
    return board.edges.filter(e => visible.has(e.from) && visible.has(e.to) && e.scene <= upTo);
  },

  findNodeAt(x, y) {
    const { w, h } = this.cardSize();
    const nodes = this.getVisibleNodes();
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (x >= n.x - w / 2 && x <= n.x + w / 2 && y >= n.y - h / 2 && y <= n.y + h / 2) return n;
    }
    return null;
  },

  setupEvents() {
    this.canvas.addEventListener('mousemove', (e) => {
      const coords = this.getCanvasCoords(e);
      const hit = this.findNodeAt(coords.x, coords.y);
      if (hit !== TrueCrimeState.board.hovered) {
        TrueCrimeState.board.hovered = hit;
        this.render();
      }
      if (hit) this.showTooltip(hit, e.clientX, e.clientY);
      else this.hideTooltip();
    });
    this.canvas.addEventListener('mouseleave', () => {
      if (TrueCrimeState.board.hovered) {
        TrueCrimeState.board.hovered = null;
        this.render();
      }
      this.hideTooltip();
    });
  },

  showTooltip(node, clientX, clientY) {
    const tip = tcEl('tc-canvas-tooltip');
    const title = tcEl('tc-tooltip-title');
    const body = tcEl('tc-tooltip-body');
    if (!tip || !title || !body) return;
    const lang = TrueCrimeState.board.lang;
    const badge = TC_BADGES[node.type] || TC_BADGES.clue;
    title.textContent = node[`label_${lang}`] || node.id;
    const links = TrueCrimeState.board.edges.filter(e => e.from === node.id || e.to === node.id).length;
    body.textContent = `${badge[lang]} • hiện từ cảnh ${node.scene} • ${links} dây nối`;
    tip.classList.remove('hidden');
    const parentRect = tip.parentElement.getBoundingClientRect();
    const x = Math.min(parentRect.width - 240, Math.max(10, clientX - parentRect.left + 15));
    const y = Math.min(parentRect.height - 80, Math.max(10, clientY - parentRect.top + 15));
    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
  },

  hideTooltip() {
    tcEl('tc-canvas-tooltip')?.classList.add('hidden');
  },

  fitText(ctx, text, maxWidth) {
    let value = String(text || '');
    if (ctx.measureText(value).width <= maxWidth) return value;
    while (value.length > 1 && ctx.measureText(value + '…').width > maxWidth) value = value.slice(0, -1);
    return value + '…';
  },

  // Chia nhãn thành tối đa 2 dòng vừa chiều rộng thẻ.
  wrapLabel(ctx, text, maxWidth) {
    const words = String(text || '').split(/\s+/).filter(Boolean);
    const lines = [];
    let current = '';
    words.forEach(word => {
      const candidate = current ? `${current} ${word}` : word;
      if (ctx.measureText(candidate).width <= maxWidth || !current) current = candidate;
      else { lines.push(current); current = word; }
    });
    if (current) lines.push(current);
    if (lines.length <= 2) return lines.map(l => this.fitText(ctx, l, maxWidth));
    return [this.fitText(ctx, lines[0], maxWidth), this.fitText(ctx, lines.slice(1).join(' '), maxWidth)];
  },

  render() {
    if (!this.ctx || !this.canvas) return;
    const ctx = this.ctx;
    const width = this.canvas.width;
    const height = this.canvas.height;
    const board = TrueCrimeState.board;

    // Nền bần (cork) + viền gỗ
    ctx.save();
    const bgGrad = ctx.createRadialGradient(width / 2, height / 2, 80, width / 2, height / 2, width * 0.7);
    bgGrad.addColorStop(0, '#be8751');
    bgGrad.addColorStop(0.6, '#a46f3c');
    bgGrad.addColorStop(1, '#66401d');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = 'rgba(70, 40, 15, 0.12)';
    for (let i = 0; i < 400; i++) {
      ctx.fillRect((Math.sin(i * 997) * 0.5 + 0.5) * width, (Math.cos(i * 733) * 0.5 + 0.5) * height, 2 + (i % 3), 2 + ((i * 2) % 3));
    }
    const vignette = ctx.createRadialGradient(width / 2, height / 2, width * 0.35, width / 2, height / 2, width * 0.72);
    vignette.addColorStop(0, 'rgba(0,0,0,0)');
    vignette.addColorStop(1, 'rgba(0,0,0,0.65)');
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, width, height);
    ctx.lineWidth = 14;
    ctx.strokeStyle = '#2d180a';
    ctx.strokeRect(7, 7, width - 14, height - 14);
    ctx.restore();

    const nodes = this.getVisibleNodes();
    const edges = this.getVisibleEdges();
    const stats = tcEl('tc-board-stats');
    if (stats) stats.textContent = `${nodes.length} thẻ • ${edges.length} dây`;

    if (!board.nodes.length) {
      ctx.save();
      ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
      ctx.beginPath();
      ctx.roundRect(width / 2 - 330, height / 2 - 34, 660, 68, 12);
      ctx.fill();
      ctx.fillStyle = '#fde68a';
      ctx.font = 'bold 20px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(TrueCrimeState.plan ? 'Kế hoạch chưa ghim bằng chứng nào lên bảng.' : 'Bảng ghim hiện ra sau khi phân tích xong.', width / 2, height / 2);
      ctx.restore();
      return;
    }

    const byId = new Map(nodes.map(n => [n.id, n]));
    const { h } = this.cardSize();
    edges.forEach(edge => {
      const a = byId.get(edge.from);
      const b = byId.get(edge.to);
      if (!a || !b) return;
      const p1 = { x: a.x, y: a.y - h / 2 + 10 };
      const p2 = { x: b.x, y: b.y - h / 2 + 10 };
      const hovered = board.hovered && (board.hovered.id === edge.from || board.hovered.id === edge.to);
      this.drawThread(ctx, p1, p2, edge[`label_${board.lang}`], hovered);
    });
    nodes.forEach(node => this.drawCard(ctx, node, board.hovered && board.hovered.id === node.id));
  },

  drawThread(ctx, p1, p2, label, hovered) {
    const sag = Math.min(60, Math.hypot(p2.x - p1.x, p2.y - p1.y) * 0.12 + 15);
    const midX = (p1.x + p2.x) / 2;
    const midY = (p1.y + p2.y) / 2 + sag;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y + 6);
    ctx.quadraticCurveTo(midX, midY + 6, p2.x, p2.y + 6);
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.35)';
    ctx.lineWidth = hovered ? 4.5 : 3;
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.quadraticCurveTo(midX, midY, p2.x, p2.y);
    ctx.strokeStyle = hovered ? '#ff2244' : '#c81e36';
    ctx.lineWidth = hovered ? 4 : 2.5;
    if (hovered) {
      ctx.shadowColor = '#ff2244';
      ctx.shadowBlur = 12;
    }
    ctx.stroke();
    ctx.restore();
    if (!label) return;
    ctx.save();
    ctx.font = 'bold 10px JetBrains Mono, monospace';
    const text = this.fitText(ctx, label, 200);
    const pillW = ctx.measureText(text).width + 16;
    ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
    ctx.strokeStyle = hovered ? '#ff2244' : '#c81e36';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.roundRect(midX - pillW / 2, midY - 9, pillW, 18, 6);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = hovered ? '#ffffff' : '#fed7aa';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, midX, midY + 1);
    ctx.restore();
  },

  drawCard(ctx, node, hovered) {
    const w = this.baseWidth;
    const h = this.baseHeight;
    const { scale } = this.cardSize();
    const lang = TrueCrimeState.board.lang;
    const badge = TC_BADGES[node.type] || TC_BADGES.clue;
    ctx.save();
    ctx.translate(node.x, node.y);
    ctx.scale(scale, scale);
    ctx.rotate(Math.sin(node.x * 13 + node.y * 7) * 0.04);
    ctx.shadowColor = hovered ? 'rgba(220, 38, 38, 0.8)' : 'rgba(0, 0, 0, 0.45)';
    ctx.shadowBlur = hovered ? 18 : 10;
    ctx.shadowOffsetY = hovered ? 0 : 6;
    ctx.fillStyle = '#faf8f5';
    ctx.strokeStyle = hovered ? '#dc2626' : '#dcd5c9';
    ctx.lineWidth = hovered ? 2 : 1;
    ctx.beginPath();
    ctx.roundRect(-w / 2, -h / 2, w, h, 6);
    ctx.fill();
    ctx.stroke();
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.shadowOffsetY = 0;

    // "Ảnh" tối có biểu tượng theo loại thẻ
    const photoW = w - 18;
    const photoH = 88;
    const photoX = -photoW / 2;
    const photoY = -h / 2 + 18;
    const grad = ctx.createLinearGradient(photoX, photoY, photoX, photoY + photoH);
    grad.addColorStop(0, '#1e293b');
    grad.addColorStop(1, '#090d16');
    ctx.fillStyle = grad;
    ctx.fillRect(photoX, photoY, photoW, photoH);
    ctx.fillStyle = 'rgba(239, 68, 68, 0.25)';
    ctx.beginPath();
    ctx.arc(0, photoY + photoH / 2, 30, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#fbbf24';
    ctx.font = '26px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(badge.icon, 0, photoY + photoH / 2 + 2);

    ctx.fillStyle = badge.color;
    ctx.beginPath();
    ctx.roundRect(photoX + 4, photoY + 4, 74, 14, 3);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 8px JetBrains Mono, monospace';
    ctx.fillText(badge[lang], photoX + 41, photoY + 11.5);

    ctx.fillStyle = '#0f172a';
    ctx.font = 'bold 11px Inter, sans-serif';
    const lines = this.wrapLabel(ctx, node[`label_${lang}`] || node.id, w - 16);
    lines.forEach((line, idx) => ctx.fillText(line, 0, photoY + photoH + 16 + idx * 14));
    ctx.fillStyle = '#64748b';
    ctx.font = '9px Inter, sans-serif';
    ctx.fillText(lang === 'en' ? `from scene ${node.scene}` : `từ cảnh ${node.scene}`, 0, h / 2 - 12);

    // Ghim
    const pinGrad = ctx.createRadialGradient(-2, -h / 2 + 6, 1, 0, -h / 2 + 8, 7);
    pinGrad.addColorStop(0, '#fca5a5');
    pinGrad.addColorStop(0.5, '#ef4444');
    pinGrad.addColorStop(1, '#991b1b');
    ctx.fillStyle = pinGrad;
    ctx.beginPath();
    ctx.arc(0, -h / 2 + 8, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
};

// ================= MỞ / ĐÓNG MODAL =================

function openTrueCrimeModal() {
  const modal = tcEl('modal-true-crime');
  if (!modal) return;
  modal.classList.remove('hidden');
  TrueCrimeState.modalOpen = true;
  tcLoadVoices();
  if (!TrueCrimeState.caseId) {
    const stored = tcReadCaseId();
    if (stored) TrueCrimeState.caseId = stored;
  }
  tcRenderProgress();
  tcRenderReview();
  if (TrueCrimeState.caseId && !TrueCrimeState.plan) tcStartPolling();
  requestAnimationFrame(() => EvidenceBoardRenderer.render());
}

function closeTrueCrimeModal() {
  tcEl('modal-true-crime')?.classList.add('hidden');
  TrueCrimeState.modalOpen = false;
  tcStopPolling();
  EvidenceBoardRenderer.hideTooltip();
}

let tcInitialized = false;

function initTrueCrimeStudio() {
  if (tcInitialized) return;
  tcInitialized = true;
  const on = (id, event, handler) => tcEl(id)?.addEventListener(event, handler);

  on('btn-open-true-crime-modal', 'click', openTrueCrimeModal);
  on('btn-step1-open-true-crime', 'click', openTrueCrimeModal);
  on('btn-close-true-crime-modal', 'click', closeTrueCrimeModal);
  on('btn-cancel-true-crime-modal', 'click', closeTrueCrimeModal);

  document.querySelectorAll('#modal-true-crime [data-tc-sample]').forEach(btn => {
    btn.addEventListener('click', () => tcLoadSample(btn.dataset.tcSample));
  });
  on('tc-case-text', 'input', tcUpdateWordCount);
  on('btn-tc-analyze', 'click', tcAnalyze);
  on('btn-tc-resume', 'click', tcResume);
  on('btn-tc-new-case', 'click', tcNewCase);
  on('btn-tc-save-entities', 'click', tcSaveEntities);
  on('btn-tc-add-entity', 'click', tcAddEntity);
  on('btn-tc-create-vi', 'click', tcCreateVietnameseProject);
  on('tc-warnings', 'click', (e) => {
    const target = e.target.closest('[data-tc-goto]');
    if (target) tcGotoScene(target.dataset.tcGoto);
  });
  on('tc-scene-scrubber', 'change', (e) => {
    TrueCrimeState.board.filter = e.target.value;
    EvidenceBoardRenderer.render();
  });
  on('tc-board-lang', 'change', (e) => {
    TrueCrimeState.board.lang = e.target.value === 'en' ? 'en' : 'vi';
    EvidenceBoardRenderer.render();
  });

  const canvas = tcEl('tc-evidence-canvas');
  if (canvas) EvidenceBoardRenderer.init(canvas);
  tcUpdateWordCount();
  tcRenderProgress();
  tcRenderReview();

  const urlParams = new URLSearchParams(window.location.search);
  if (window.location.hash === '#true-crime' || urlParams.get('mode') === 'true-crime' || urlParams.get('view') === 'true-crime') {
    setTimeout(openTrueCrimeModal, 150);
  }
}

window.initTrueCrimeStudio = initTrueCrimeStudio;
window.openTrueCrimeModal = openTrueCrimeModal;
window.closeTrueCrimeModal = closeTrueCrimeModal;
window.refreshLanguageVersionButton = refreshLanguageVersionButton;
