/**
 * YouTube AI Storyboard Studio - Frontend Engine
 * Modern CapCut / DSH Dark Theme Studio Controller
 */

// ================= GLOBAL STATE =================
// Phong cách mặc định duy nhất: trùng config.DEFAULT_STYLE của máy chủ (tests/test_prompt_rules.py kiểm hai bên khớp)
const DEFAULT_STYLE_PRESET = 'horror_cartoon_2d';

const AppState = {
  currentProject: null,
  projectsList: [],
  selectedSceneIndex: 0,
  currentStep: 2, // 1: Nhập liệu, 2: Bảng đạo diễn, 3: Tiến trình, 4: Rạp chiếu
  isPlaying: false,
  isPlayingAll: false,
  playAllIndex: 0,
  playbackTimer: null,
  produceState: {
    // Trạng thái dựng gắn với một dự án (projectId): đổi sang dự án khác thì trang Dựng vẽ trạng thái "chưa dựng" của
    // dự án đó, còn lần dựng đang chạy vẫn nhận tiến độ và hiện lại khi mở lại đúng dự án đang dựng.
    projectId: null,
    draft: false,
    statusMsg: '',
    failed: null,
    isProducing: false,
    renderId: null,
    progress: 0,
    step: 1,
    logs: [],
    videoUrl: null,
    videoPath: null,
    srtUrl: null,
    srtPath: null,
    startTime: null,
    timerInterval: null
  },
  serverOnline: false,
  healthCheckInterval: null,
  comicState: {
    selectedFile: null,
    slicedPanels: [],
    annotatedPreviewUrl: null,
    isSlicing: false,
    activeTab: 'panels'
  },
  museCloud: {
    status: 'offline', // 'online' | 'busy' | 'offline'
    telemetry: null,
    activeJob: null,
    galleryItems: [],
    pollingInterval: null,
    isProcessing: false
  }
};

// ================= OFFLINE & VECTOR VISUAL GENERATOR =================
function generateSceneVisualSvg(scene, project, index) {
  const idx = (index !== undefined ? index : (scene?.order ? scene.order - 1 : 0)) + 1;
  const style = (scene?.style_override || project?.style_preset || project?.character?.style || 'cinematic_realistic');
  const textRaw = scene?.visual_prompt || scene?.image_prompt || scene?.text || "Khung cảnh điện ảnh sắc nét 4K";
  const cleanText = escapeHtml(textRaw.length > 115 ? textRaw.substring(0, 112) + '...' : textRaw);

  const palettes = {
    anime: {
      c1: '#0b1329', c2: '#1e3a8a', c3: '#38bdf8', glow: '#67e8f9',
      styleName: 'Anime & Ghibli', accent: '#38bdf8'
    },
    cinematic_realistic: {
      c1: '#090d16', c2: '#1e293b', c3: '#d97706', glow: '#fbbf24',
      styleName: 'Cinematic Realistic', accent: '#f59e0b'
    },
    dark_fantasy: {
      c1: '#090a0f', c2: '#18181b', c3: '#881337', glow: '#f43f5e',
      styleName: 'Dark Fantasy', accent: '#ef4444'
    },
    cyberpunk: {
      c1: '#120224', c2: '#3b0764', c3: '#06b6d4', glow: '#ec4899',
      styleName: 'Cyberpunk Metropolis', accent: '#06b6d4'
    },
    comic_book: {
      c1: '#18181b', c2: '#27272a', c3: '#ca8a04', glow: '#fde047',
      styleName: 'Comic Book Graphic', accent: '#eab308'
    },
    '3d_animation': {
      c1: '#17153a', c2: '#312e81', c3: '#c026d3', glow: '#f472b6',
      styleName: '3D Pixar Animation', accent: '#ec4899'
    }
  };

  const pal = palettes[style] || palettes.cinematic_realistic;
  const stars = Array.from({ length: 28 }, (_, i) => {
    const cx = (i * 47 + 23) % 1280;
    const cy = (i * 29 + 17) % 450;
    const r = (i % 3) * 0.8 + 1.2;
    const op = ((i % 5) + 3) / 10;
    return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#ffffff" opacity="${op}"/>`;
  }).join('');

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
    <defs>
      <linearGradient id="skyGrad_${idx}" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="${pal.c1}"/>
        <stop offset="55%" stop-color="${pal.c2}"/>
        <stop offset="100%" stop-color="${pal.c3}"/>
      </linearGradient>
      <radialGradient id="sunGlow_${idx}" cx="50%" cy="38%" r="45%">
        <stop offset="0%" stop-color="${pal.glow}" stop-opacity="0.55"/>
        <stop offset="50%" stop-color="${pal.glow}" stop-opacity="0.15"/>
        <stop offset="100%" stop-color="${pal.glow}" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="groundGrad_${idx}" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#05070d" stop-opacity="0.9"/>
        <stop offset="100%" stop-color="#020306"/>
      </linearGradient>
    </defs>

    <rect width="1280" height="720" fill="url(#skyGrad_${idx})"/>
    ${stars}
    <circle cx="640" cy="270" r="320" fill="url(#sunGlow_${idx})"/>
    <path d="M0,520 L180,450 L340,490 L520,410 L700,470 L890,390 L1080,460 L1280,420 L1280,720 L0,720 Z" fill="#080c14" opacity="0.95"/>
    <path d="M0,560 L140,510 L310,540 L490,480 L680,530 L860,470 L1040,520 L1280,490 L1280,720 L0,720 Z" fill="url(#groundGrad_${idx})"/>
    <rect x="20" y="20" width="1240" height="680" rx="12" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="2"/>

    <g transform="translate(48, 48)">
      <rect width="280" height="42" rx="8" fill="rgba(10,15,28,0.85)" stroke="${pal.accent}" stroke-width="1.5"/>
      <text x="18" y="27" fill="${pal.accent}" font-family="Inter, -apple-system, sans-serif" font-size="15" font-weight="700" letter-spacing="1">
        ▶ CẢNH #${idx}  •  ${pal.styleName.toUpperCase()}
      </text>
    </g>

    <g transform="translate(640, 270)" opacity="0.35">
      <circle r="60" fill="none" stroke="#ffffff" stroke-width="2" stroke-dasharray="6 6"/>
      <polygon points="0,-45 35,35 -35,35" fill="none" stroke="${pal.glow}" stroke-width="2"/>
    </g>

    <g transform="translate(48, 555)">
      <rect width="1184" height="115" rx="12" fill="rgba(10,14,24,0.92)" stroke="rgba(255,255,255,0.2)" stroke-width="1.5"/>
      <text x="32" y="44" fill="#f8fafc" font-family="Inter, -apple-system, sans-serif" font-size="18" font-weight="600">
        ${cleanText}
      </text>
      <text x="32" y="82" fill="#94a3b8" font-family="'JetBrains Mono', monospace" font-size="13" font-weight="500">
        AI Storyboard Engine • High Dynamic Range Visualizer • 16:9
      </text>
      <text x="1152" y="82" text-anchor="end" fill="${pal.accent}" font-family="Inter, sans-serif" font-size="14" font-weight="700">
        1080p HD
      </text>
    </g>
  </svg>`;

  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

function handleSceneImageError(imgElem, idx) {
  // Ảnh không tải được (vd ảnh Muse chưa ghi xong): chỉ hiện khung báo lỗi tạm thời,
  // KHÔNG ghi đè image_url của cảnh bằng ảnh demo
  if (!imgElem) return;
  imgElem.onerror = null;
  imgElem.src = generateSceneVisualSvg(
    { text: 'Không tải được ảnh — hãy tạo lại ảnh cho cảnh này' },
    AppState.currentProject,
    idx || 0
  );
  imgElem.title = 'Không tải được ảnh. Hãy tạo lại ảnh hoặc tải lại trang.';
}

// Cảnh có file giọng đọc thật (không tính status 'ready' suông)
function sceneHasVoiceAudio(scene) {
  return Boolean(scene && (scene.voice_audio_url || scene.audio_url || scene.voice_audio_path));
}

// Ảnh minh hoạ SVG sinh trên trình duyệt và ảnh demo không phải ảnh thật của cảnh
function isPlaceholderImageUrl(url) {
  return !url || url.startsWith('data:image/svg') || url.includes('/static/demo_images/');
}

function sceneHasRealVisual(scene) {
  if (!scene) return false;
  const videoUrl = scene.video_url || scene.video_segment_url || '';
  if (videoUrl && !videoUrl.startsWith('blob:')) return true;
  return scene.status_image !== 'error' && !isPlaceholderImageUrl(scene.image_url || '');
}

// Cảnh báo hiện trên thẻ cảnh: lỗi tạo ảnh/giọng, dùng engine dự phòng, ảnh tạm
function buildSceneWarningBadges(scene) {
  const meta = scene?.metadata || {};
  const badges = [];
  const badge = (cls, icon, label, title) =>
    `<span class="text-[10px] ${cls} px-1.5 py-0.5 rounded border font-semibold" title="${escapeHtml(String(title || ''))}"><i class="fa-solid ${icon} mr-1"></i>${escapeHtml(label)}</span>`;
  if (scene?.status_image === 'error' || meta.image_error) {
    badges.push(badge('bg-red-50 text-red-700 border-red-200', 'fa-triangle-exclamation', 'Lỗi ảnh', meta.image_error || 'Tạo ảnh thất bại'));
  } else if (meta.image_placeholder) {
    badges.push(badge('bg-amber-50 text-amber-700 border-amber-200', 'fa-image', 'Ảnh tạm', 'Ảnh minh hoạ offline, không phải ảnh AI'));
  } else if (meta.image_fallback) {
    badges.push(badge('bg-amber-50 text-amber-700 border-amber-200', 'fa-shuffle', `Ảnh dự phòng (${meta.image_fallback.provider || '?'})`, meta.image_fallback.reason || ''));
  }
  if (scene?.status_voice === 'error' || meta.voice_error) {
    badges.push(badge('bg-red-50 text-red-700 border-red-200', 'fa-triangle-exclamation', 'Lỗi giọng', meta.voice_error || 'Tạo giọng thất bại'));
  } else if (meta.voice_fallback) {
    badges.push(badge('bg-amber-50 text-amber-700 border-amber-200', 'fa-microphone-slash', 'Đang dùng giọng dự phòng', `${meta.voice_fallback.used_voice || ''} — ${meta.voice_fallback.reason || ''}`));
  }
  return badges.join('');
}
window.handleSceneImageError = handleSceneImageError;
window.generateSceneVisualSvg = generateSceneVisualSvg;

// Default Initial Project Data
const DEFAULT_PROJECT = {
  id: "proj_huyen_thoai_rung_suong_mu",
  name: "Huyền thoại Rừng Sương Mù (Tập 1)",
  description: "Bộ phim ngắn hoạt hình tiên hiệp - huyền ảo kỳ bí",
  aspect_ratio: "16:9",
  resolution: "1080p",
  image_provider: "meta_muse_cloud",
  style_preset: DEFAULT_STYLE_PRESET,
  created_at: new Date().toISOString(),
  character: {
    name: "Lâm (Chiến binh áo lam)",
    prompt: "Anime style, 20yo Asian warrior boy, sharp amber eyes, spiky black hair, distinctive scar across left eyebrow, dark navy high-collared tunic, glowing blue talisman necklace, 8k cinematic masterpiece",
    style: "anime",
    negative: "ugly, deformed face, bad anatomy, lowres, blurry",
    avatar: ""
  },
  settings: {
    voice: "vi-VN-NamMinhNeural",
    speed: 1.0,
    pitch: 0,
    bgm: "ambient_peaceful",
    ducking: true,
    hardsub: true
  },
  scenes: [
    {
      id: "scene-1",
      order: 1,
      duration: 6.5,
      text: "Đêm hôm đó, sương mù bao phủ khắp ngôi làng cổ. Một chàng trai trẻ tên Lâm mang theo thanh cổ kiếm bước vào rừng cấm.",
      image_prompt: "Anime style, ancient misty Vietnamese village at moonlight, young warrior hero Lam walking towards mysterious dark bamboo forest, glowing cyan ancient sword, cinematic atmosphere, 8k wallpaper",
      visual_prompt: "Anime style, ancient misty Vietnamese village at moonlight, young warrior hero Lam walking towards mysterious dark bamboo forest, glowing cyan ancient sword, cinematic atmosphere, 8k wallpaper",
      image_url: "/static/demo_images/scene_1.jpg",
      audio_url: "",
      camera_motion: "zoom_in",
      ken_burns: "zoom_in",
      status_voice: "ready",
      status_image: "ready"
    },
    {
      id: "scene-2",
      order: 2,
      duration: 7.0,
      text: "Càng đi sâu vào lòng hang tối, tiếng gầm gừ bí ẩn càng vang lên dồn dập. Đôi mắt đỏ rực bỗng lóe lên sau lùm cây mục.",
      image_prompt: "Anime style, deep shadowy ancient cave, young warrior Lam with glowing blue blade facing glowing sinister crimson monster eyes in darkness, volumetric fog, dramatic lighting, 8k",
      visual_prompt: "Anime style, deep shadowy ancient cave, young warrior Lam with glowing blue blade facing glowing sinister crimson monster eyes in darkness, volumetric fog, dramatic lighting, 8k",
      image_url: "/static/demo_images/scene_2.jpg",
      audio_url: "",
      camera_motion: "pan_left",
      ken_burns: "pan_left",
      status_voice: "ready",
      status_image: "ready"
    },
    {
      id: "scene-3",
      order: 3,
      duration: 5.8,
      text: "Không chút sợ hãi, Lâm siết chặt chuôi kiếm, một luồng lam hỏa bùng lên xé toạc màn đêm u tối!",
      image_prompt: "Anime dynamic battle action, hero Lam unleashing magical blue flame blast from ancient broadsword, mist clearing, explosive light particles, epic anime climax scene, 8k",
      visual_prompt: "Anime dynamic battle action, hero Lam unleashing magical blue flame blast from ancient broadsword, mist clearing, explosive light particles, epic anime climax scene, 8k",
      image_url: "/static/demo_images/scene_3.jpg",
      audio_url: "",
      camera_motion: "zoom_out",
      ken_burns: "zoom_out",
      status_voice: "ready",
      status_image: "ready"
    }
  ]
};

// Sample Stories for quick auto-split & US Podcast testing
const SAMPLE_STORIES = {
  us_murata_battle: `The colossal seismic shockwave ripped through the shattered metropolis as the supreme monster Garou descended from the storm clouds.
Saitama dug his red boots into the fractured asphalt, his knuckles igniting with compressed atmospheric kinetic energy.
"You say you want to destroy this world," Saitama muttered, his gaze turning razor-sharp. "Show me what you've got."
Before the falling rubble could touch the ground, both superhuman fighters vanished at hypersonic velocity.
KA-BOOM! The sound barrier shattered into a million pieces as a blinding red shockwave obliterated the arena!`,
  us_spartan: `At the narrow cliffside Gates of Fire, three hundred Spartan warriors stood unyielding against the immense Persian horde.
King Leonidas raised his notched ash-wood dory spear, his polished bronze muscle cuirass gleaming under the blistering Mediterranean sun.
"Spartans, stand your ground! Tonight, we dine in the halls of Hades!"
With a thunderous crash of bronze hoplon shields, the frontline collided under a darkening sky filled with Persian arrows.
Blood washed over the sacred stones as the legendary Spartan phalanx carved their names into immortality.`,
  tienhiep: `Đêm hôm đó, sương mù bao phủ khắp ngôi làng cổ dưới chân núi Thương Vân. Một chàng trai trẻ tên Lâm mang theo thanh cổ kiếm bước một mình vào rừng cấm.
Càng đi sâu vào lòng hang tối, tiếng gầm gừ bí ẩn càng vang lên dồn dập. Đôi mắt đỏ rực của Thạch Cự Thú bỗng lóe lên sau lùm cây mục.
Không chút do dự, Lâm siết chặt chuôi kiếm, một luồng lam hỏa thần thánh bùng lên xé toạc màn đêm u tối!
Trận chiến kinh thiên động địa diễn ra, kiếm khí tung hoành khắp vách đá, mở ra bí mật ngàn năm chôn giấu của vương quốc cổ đại.`,
  kingdom: `Chiến trường Hàm Đan rực lửa, mười vạn quân Tần giáp đen dàn trận uy nghiêm trước cổng thành.
Tướng quân Vương Tiễn giương cao ngọn kích lệnh, tiếng trống trận rền vang như sấm sét xé toạc chân trời.
Từng đợt mưa tên bay rợp trời, chiến xa gầm rú lao qua làn khói bụi mù mịt của sa trường.
Đoàn kỵ binh tinh nhuệ đột phá vòng vây phòng thủ, mở toang cục diện thống nhất thiên hạ!`,
  paladin: `Dưới ánh hoàng hôn rực rỡ, Thánh kỵ sĩ mang bộ giáp bạc viền vàng đứng trước cổng pháo đài thiêng.
Tay nắm chặt thanh kiếm thánh tỏa ánh hào quang ngọc lam, ngài hướng ánh mắt kiên định về phía bầy quỷ dữ.
Một lời cầu nguyện vang lên, đôi cánh ánh sáng bùng nổ sau lưng xua tan bóng tối ngàn năm.
Thanh kiếm chém xuống, nguồn năng lượng thần thánh quét sạch mọi thế lực tà ác khỏi vương quốc.`,
  kinhdi: `Trời về khuya, cơn mưa rào bất chợt làm ngôi nhà cổ trên đồi hoang trở nên rùng rợn đến lạnh gáy.
Hải cầm chiếc đèn pin chập chờn bước lên bậc cầu thang gỗ kêu cót két từng hồi.
Ở góc phòng áp mái, chiếc gương cổ phủ khăn đen bất ngờ rơi xuống, để lộ bóng một người phụ nữ mặc áo trắng đang mỉm cười.
Tiếng chuông đồng hồ điểm mười hai tiếng vang vọng, cánh cửa sổ bật tung trước cơn gió lốc rít gào.`,
};

// ================= DOM ELEMENTS =================
const DOM = {
  // 4-Step Views
  stepView1: document.getElementById('step-view-1'),
  stepView2: document.getElementById('step-view-2'),
  stepView3: document.getElementById('step-view-3'),
  stepView4: document.getElementById('step-view-4'),

  // Top Header Extra Elements
  headerVoiceBadge: document.getElementById('header-voice-badge'),
  headerVoiceName: document.getElementById('header-voice-name'),

  // Step 1 Elements
  step1ScriptTextarea: document.getElementById('step1-script-textarea'),
  step1WordCount: document.getElementById('step1-word-count'),
  step1EngineSelect: document.getElementById('step1-engine-select'),
  step1PacingSelect: document.getElementById('step1-pacing-select'),
  step1LanguageSelect: document.getElementById('step1-language-select'),
  step1StyleSelect: document.getElementById('step1-style-select'),
  step1ContentKind: document.getElementById('step1-content-kind'),
  step1CaseDuration: document.getElementById('step1-case-duration'),
  btnStep1ProcessScript: document.getElementById('btn-step1-process-script'),
  step1ComicDropzone: document.getElementById('step1-comic-dropzone'),
  step1ComicFileInput: document.getElementById('step1-comic-file-input'),
  step1ComicFileName: document.getElementById('step1-comic-file-name'),
  step1ComicMode: document.getElementById('step1-comic-mode'),
  step1ComicOrder: document.getElementById('step1-comic-order'),
  btnStep1SampleGrid: document.getElementById('btn-step1-sample-grid'),
  btnStep1SampleStrip: document.getElementById('btn-step1-sample-strip'),
  btnStep1ProcessComic: document.getElementById('btn-step1-process-comic'),

  // Step 2 Extra Controls
  selectProjectStyle: document.getElementById('select-project-style'),
  selectImageProvider: document.getElementById('select-image-provider'),
  btnProduceFromBoard: document.getElementById('btn-produce-from-board'),
  btnProduceLabel: document.getElementById('btn-produce-label'),
  boardAssetReadiness: document.getElementById('board-asset-readiness'),
  readinessVoiceCount: document.getElementById('readiness-voice-count'),
  readinessImageCount: document.getElementById('readiness-image-count'),
  readinessLabelBadge: document.getElementById('readiness-label-badge'),
  btnRegenAllImages: document.getElementById('btn-regen-all-images'),
  btnRegenAllVoices: document.getElementById('btn-regen-all-voices'),

  // Step 3 Elements (Realtime Production Console)
  producerStatusText: document.getElementById('producer-status-text'),
  producerPercentText: document.getElementById('producer-percent-text'),
  producerProgressBar: document.getElementById('producer-progress-bar'),
  producerTimerText: document.getElementById('producer-timer-text'),
  producerLogConsole: document.getElementById('producer-log-console'),
  producerStep1: document.getElementById('producer-step-1'),
  producerStep2: document.getElementById('producer-step-2'),
  producerStep3: document.getElementById('producer-step-3'),
  producerStep4: document.getElementById('producer-step-4'),
  producerStep5: document.getElementById('producer-step-5'),
  producerStepIcon1: document.getElementById('producer-step-icon-1'),
  producerStepIcon2: document.getElementById('producer-step-icon-2'),
  producerStepIcon3: document.getElementById('producer-step-icon-3'),
  producerStepIcon4: document.getElementById('producer-step-icon-4'),
  producerStepIcon5: document.getElementById('producer-step-icon-5'),

  // Step 4 Elements (Cinema Player, Export & YouTube Packaging)
  cinemaVideoPlayer: document.getElementById('cinema-video-player'),
  btnCinemaDownloadVideo: document.getElementById('btn-cinema-download-video'),
  btnCinemaDownloadSrt: document.getElementById('btn-cinema-download-srt'),
  btnCinemaDownloadAss: document.getElementById('btn-cinema-download-ass'),
  btnCinemaOpenFolder: document.getElementById('btn-cinema-open-folder'),
  cinemaThumbnailPreview: document.getElementById('cinema-thumbnail-preview'),
  inputThumbHeadline: document.getElementById('input-thumb-headline'),
  inputThumbSubtext: document.getElementById('input-thumb-subtext'),
  btnGenerateCustomThumbnail: document.getElementById('btn-generate-custom-thumbnail'),
  btnCinemaDownloadThumbnail: document.getElementById('btn-cinema-download-thumbnail'),
  inputSeoTitle: document.getElementById('input-seo-title'),
  btnCopySeoTitle: document.getElementById('btn-copy-seo-title'),
  textareaSeoDesc: document.getElementById('textarea-seo-desc'),
  btnCopySeoDesc: document.getElementById('btn-copy-seo-desc'),
  inputSeoTags: document.getElementById('input-seo-tags'),
  btnCopySeoTags: document.getElementById('btn-copy-seo-tags'),

  // Header
  currentProjectTitle: document.getElementById('current-project-title'),

  // Left Panel Scene List
  sceneListContainer: document.getElementById('scene-list-container'),
  sceneCountBadge: document.getElementById('scene-count-badge'),
  totalDurationBadge: document.getElementById('total-duration-badge'),
  projectVoiceBadge: document.getElementById('project-voice-badge'),
  btnAddScene: document.getElementById('btn-add-scene'),
  btnAutoGenAll: document.getElementById('btn-auto-gen-all'),

  // Right Panel Preview Player
  playerActiveSceneBadge: document.getElementById('player-active-scene-badge'),
  previewCanvasBox: document.getElementById('preview-canvas-box'),
  previewImageWrapper: document.getElementById('preview-image-wrapper'),
  previewImageElem: document.getElementById('preview-image-elem'),
  previewVideoElem: document.getElementById('preview-video-elem'),
  previewImagePlaceholder: document.getElementById('preview-image-placeholder'),
  previewSubtitleOverlay: document.getElementById('preview-subtitle-overlay'),
  previewSubtitleText: document.getElementById('preview-subtitle-text'),
  previewKbBadge: document.getElementById('preview-kb-badge'),
  btnPreviewPlayToggle: document.getElementById('btn-preview-play-toggle'),
  previewPlayIcon: document.getElementById('preview-play-icon'),
  btnPrevScene: document.getElementById('btn-prev-scene'),
  btnNextScene: document.getElementById('btn-next-scene'),
  btnPlayAllStory: document.getElementById('btn-play-all-story'),
  previewTimeDisplay: document.getElementById('preview-time-display'),
  btnToggleFullscreen: document.getElementById('btn-toggle-fullscreen'),
  globalPreviewAudio: document.getElementById('global-preview-audio'),
  globalBgmAudio: document.getElementById('global-bgm-audio'),

  // Audio Settings Card
  selectVoice: document.getElementById('select-voice'),
  btnPreviewVoiceSample: document.getElementById('btn-preview-voice-sample'),
  iconPreviewVoice: document.getElementById('icon-preview-voice'),
  textPreviewVoice: document.getElementById('text-preview-voice'),
  voiceSampleAudio: document.getElementById('voice-sample-audio'),
  selectBgm: document.getElementById('select-bgm'),
  bgmUploadInput: document.getElementById('bgm-upload-input'),
  toggleAudioDucking: document.getElementById('toggle-audio-ducking'),
  toggleHardsub: document.getElementById('toggle-hardsub'),
  selectTransition: document.getElementById('select-transition'),
  selectSubtitleStyle: document.getElementById('select-subtitle-style'),

  // Footer Status
  backendStatusDot: document.getElementById('backend-status-dot'),
  backendStatusText: document.getElementById('backend-status-text'),

  // Project Modal
  newProjectNameInput: document.getElementById('new-project-name-input'),
  btnCreateProject: document.getElementById('btn-create-project'),
  projectListItems: document.getElementById('project-list-items'),

  // Toast
  toastContainer: document.getElementById('toast-container'),

  // Meta Muse Cloud Elements
  btnMuseCloudStatus: document.getElementById('btn-muse-cloud-status'),
  headerMuseStatusDot: document.getElementById('header-muse-status-dot'),
  headerMuseStatusText: document.getElementById('header-muse-status-text'),
  headerMuseSpecsBadge: document.getElementById('header-muse-specs-badge'),
  museModalStatusBadge: document.getElementById('muse-modal-status-badge'),
  museModalStatusDot: document.getElementById('muse-modal-status-dot'),
  museModalStatusText: document.getElementById('muse-modal-status-text'),
  museProgressCard: document.getElementById('muse-progress-card'),
  museProgressTitle: document.getElementById('muse-progress-title'),
  museProgressPercent: document.getElementById('muse-progress-percent'),
  museProgressBarFill: document.getElementById('muse-progress-bar-fill'),
  museSceneChips: document.getElementById('muse-scene-chips'),
  museGalleryGrid: document.getElementById('muse-gallery-grid'),
  museGalleryCount: document.getElementById('muse-gallery-count'),
  museGalleryPlaceholder: document.getElementById('muse-gallery-placeholder'),
  museReconnectAssistant: document.getElementById('muse-reconnect-assistant'),

  // Muse Fleet accounts view (local Fleet Runner: one Muse account per Chrome profile)
  museFleetPoolGrid: document.getElementById('muse-fleet-pool-grid'),
  museFleetImageList: document.getElementById('muse-fleet-image-list'),
  museFleetVideoList: document.getElementById('muse-fleet-video-list'),
  museFleetImageGroupStatus: document.getElementById('muse-fleet-image-group-status'),
  museFleetVideoGroupStatus: document.getElementById('muse-fleet-video-group-status'),
  museFleetImageIndicator: document.getElementById('muse-fleet-image-indicator'),
  museFleetVideoIndicator: document.getElementById('muse-fleet-video-indicator'),
  museFleetConcurrency: document.getElementById('muse-fleet-concurrency'),
  btnMuseRefreshAccounts: document.getElementById('btn-muse-refresh-accounts')
  // Hồ Sơ Kỳ Án: các phần tử do true_crime.js tự tra (khối của vụ nằm trong trang Kịch bản)
};

// ================= API SERVICE LAYER =================
const API = {
  baseUrl: '/api',

  async checkHealth() {
    try {
      const res = await fetch(`${this.baseUrl}/health`, { signal: AbortSignal.timeout(3000) });
      return res.ok;
    } catch {
      return false;
    }
  },

  async getProjects() {
    try {
      const res = await fetch(`${this.baseUrl}/projects`);
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("Backend /api/projects not reached, using local storage", e);
    }
    return null;
  },

  async createProject(name, description = "") {
    try {
      const res = await fetch(`${this.baseUrl}/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description })
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("API createProject fallback", e);
    }
    return null;
  },

  async getProject(id) {
    try {
      const res = await fetch(`${this.baseUrl}/projects/${id}`);
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn(`API getProject(${id}) fallback`, e);
    }
    return null;
  },

  // Trả về Project đã lưu, hoặc null (lý do nằm ở API.lastError)
  async saveProject(project) {
    this.lastError = null;
    try {
      const res = await fetch(`${this.baseUrl}/projects/${project.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(project)
      });
      if (res.ok) return await res.json();
      this.lastError = (await this._errorResult(res)).detail;
    } catch (e) {
      console.warn("API saveProject failed", e);
      this.lastError = `Không kết nối được máy chủ: ${e.message || e}`;
    }
    return null;
  },

  // Lỗi trả về dạng { success: false, detail } để giao diện báo đúng lý do, không tự dựng kết quả giả
  async _errorResult(res) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* body không phải JSON */ }
    return { success: false, detail };
  },

  async genVoice(projectId, sceneId, text, voice) {
    try {
      const res = await fetch(`${this.baseUrl}/projects/${projectId}/scenes/${sceneId}/gen-voice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice })
      });
      if (res.ok) return await res.json();
      return await this._errorResult(res);
    } catch (e) {
      console.warn("API genVoice failed", e);
      return { success: false, detail: `Không kết nối được máy chủ: ${e.message || e}` };
    }
  },

  async uploadSceneMedia(projectId, sceneId, file, kind) {
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('kind', kind);
      const res = await fetch(`${this.baseUrl}/projects/${projectId}/scenes/${sceneId}/upload-media`, {
        method: 'POST',
        body: form
      });
      if (res.ok) return await res.json();
      return await this._errorResult(res);
    } catch (e) {
      console.warn("API uploadSceneMedia failed", e);
      return { success: false, detail: `Không kết nối được máy chủ: ${e.message || e}` };
    }
  },

  async genImage(projectId, sceneId, prompt, style = "", consistency = {}) {
    try {
      const res = await fetch(`${this.baseUrl}/projects/${projectId}/scenes/${sceneId}/gen-image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, style, consistency })
      });
      if (res.ok) return await res.json();
      return await this._errorResult(res);
    } catch (e) {
      console.warn("API genImage failed", e);
      return { success: false, detail: `Không kết nối được máy chủ: ${e.message || e}` };
    }
  },

  async getRenderStatus(renderId) {
    try {
      const res = await fetch(`${this.baseUrl}/render-status/${renderId}`);
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("API getRenderStatus fallback", e);
    }
    return null;
  },

  async openFolder(projectId, path = "") {
    try {
      const res = await fetch(`${this.baseUrl}/open-folder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, path })
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("API openFolder fallback", e);
    }
    return null;
  },

  async sliceComic(file, mode = "grid", readingOrder = "ltr", minAreaRatio = 0.03, projectId = null) {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('mode', mode);
      formData.append('reading_order', readingOrder);
      formData.append('min_area_ratio', minAreaRatio.toString());
      if (projectId) {
        formData.append('project_id', projectId);
      }

      const endpoint = projectId 
        ? `${this.baseUrl}/projects/${projectId}/comic/slice`
        : `${this.baseUrl}/comic/slice`;

      const res = await fetch(endpoint, {
        method: 'POST',
        body: formData
      });
      if (res.ok) return await res.json();
      const err = await res.json().catch(() => ({ detail: 'Lỗi bóc tách khung tranh' }));
      throw new Error(err.detail || 'Lỗi bóc tách khung tranh');
    } catch (e) {
      console.error("API sliceComic failed", e);
      throw e;
    }
  },

  async importComicPanels(projectId, panels, clearExisting = false, textPrefix = "Khung tranh") {
    try {
      const res = await fetch(`${this.baseUrl}/projects/${projectId}/comic/import-scenes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          panels: panels,
          clear_existing: clearExisting,
          text_prefix: textPrefix
        })
      });
      if (res.ok) return await res.json();
      const err = await res.json().catch(() => ({ detail: 'Lỗi nhập phân cảnh' }));
      throw new Error(err.detail || 'Lỗi nhập phân cảnh');
    } catch (e) {
      console.error("API importComicPanels failed", e);
      throw e;
    }
  },

  async createProjectFromScript(payload) {
    try {
      const res = await fetch(`${this.baseUrl}/projects/create-from-script`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) return await res.json();
      const err = await res.json().catch(() => ({ detail: 'Lỗi tạo kịch bản và sinh ảnh' }));
      throw new Error(err.detail || 'Lỗi tạo kịch bản và sinh ảnh');
    } catch (e) {
      console.error("API createProjectFromScript failed", e);
      throw e;
    }
  },

  async produceLongVideo(projectId, options) {
    try {
      const res = await fetch(`${this.baseUrl}/projects/${projectId}/produce-long-video`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(options)
      });
      if (res.ok) return await res.json();
      const err = await res.json().catch(() => ({ detail: 'Lỗi sản xuất video dài' }));
      // Chốt tỉ lệ video Muse (services/video_share.py): 409 kèm {code, message, report}
      if (err.detail && typeof err.detail === 'object' && err.detail.code === 'VIDEO_SHARE_LOW') {
        const e = new Error(err.detail.message || 'Tỉ lệ video Muse quá thấp');
        e.shareLow = err.detail;
        throw e;
      }
      throw new Error((typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail)) || 'Lỗi sản xuất video dài');
    } catch (e) {
      if (!e.shareLow) console.error("API produceLongVideo failed", e);   // bị chốt tỉ lệ chặn là việc bình thường
      throw e;
    }
  },

  async generateThumbnail(projectId, data = {}) {
    try {
      const res = await fetch(`${this.baseUrl}/projects/${projectId}/thumbnail/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      if (res.ok) return await res.json();
      return await this._errorResult(res);
    } catch (e) {
      console.error("API generateThumbnail failed", e);
      return { success: false, detail: `Không kết nối được máy chủ: ${e.message || e}` };
    }
  },

  // Meta Muse Cloud Bridge API
  async getMuseBridgeStatus() {
    try {
      const res = await fetch(`${this.baseUrl}/muse-bridge/status`, { signal: AbortSignal.timeout(4000) });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  },

  async createMuseBridgeTask(taskData) {
    try {
      const res = await fetch(`${this.baseUrl}/muse-bridge/tasks/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(taskData)
      });
      if (res.ok) return await res.json();
      return await this._errorResult(res);
    } catch (e) {
      console.error("API createMuseBridgeTask failed", e);
      return { success: false, detail: `Không kết nối được máy chủ: ${e.message || e}` };
    }
  },

  async getMuseBridgeTask(taskId) {
    try {
      const res = await fetch(`${this.baseUrl}/muse-bridge/tasks/${encodeURIComponent(taskId)}`);
      if (res.ok) return await res.json();
      return null;
    } catch (e) {
      return null;
    }
  },

  async getMuseAccounts() {
    try {
      const res = await fetch(`${this.baseUrl}/muse-bridge/accounts`, { signal: AbortSignal.timeout(4000) });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("API getMuseAccounts failed", e);
    }
    return null;
  },

  // mode: "image" | "video". Backend returns 400 if the account type does not match the mode.
  async switchMuseAccount(mode, accountId) {
    try {
      const res = await fetch(`${this.baseUrl}/muse-bridge/accounts/switch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, account_id: accountId })
      });
      if (res.ok) return await res.json();
      let detail = `HTTP ${res.status}`;
      try {
        const errBody = await res.json();
        if (errBody && errBody.detail) {
          detail = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail);
        }
      } catch (_) { /* non-JSON error body */ }
      return { success: false, detail };
    } catch (e) {
      console.warn("API switchMuseAccount failed", e);
    }
    return null;
  },

  async deleteGalleryItem(taskId) {
    try {
      const res = await fetch(`${this.baseUrl}/muse-bridge/gallery/${encodeURIComponent(taskId)}`, {
        method: 'DELETE'
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("API deleteGalleryItem failed", e);
    }
    return null;
  },

  async clearAllGallery() {
    try {
      const res = await fetch(`${this.baseUrl}/muse-bridge/gallery/clear-all`, {
        method: 'DELETE'
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("API clearAllGallery failed", e);
    }
    return null;
  }
};

// ================= TOAST NOTIFICATION SYSTEM =================
function showToast(message, type = 'info', duration = 3500) {
  const container = DOM.toastContainer;
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'pointer-events-auto transform transition-all duration-300 translate-y-2 opacity-0 flex items-center gap-3 px-4 py-3 rounded-xl shadow-sm text-xs font-medium border max-w-sm';

  let iconHtml = '';
  if (type === 'success') {
    toast.classList.add('bg-[#14261e]', 'border-emerald-500/50', 'text-emerald-200');
    iconHtml = '<i class="fa-solid fa-circle-check text-emerald-400 text-sm"></i>';
  } else if (type === 'error') {
    toast.classList.add('bg-[#2d161a]', 'border-red-500/50', 'text-red-200');
    iconHtml = '<i class="fa-solid fa-circle-exclamation text-red-400 text-sm"></i>';
  } else if (type === 'warning') {
    toast.classList.add('bg-[#2c2214]', 'border-amber-500/50', 'text-amber-200');
    iconHtml = '<i class="fa-solid fa-triangle-exclamation text-amber-400 text-sm"></i>';
  } else {
    toast.classList.add('bg-[#1a2035]', 'border-slate-700/50', 'text-slate-300');
    iconHtml = '<i class="fa-solid fa-circle-info text-slate-400 text-sm"></i>';
  }

  toast.innerHTML = `
    ${iconHtml}
    <span class="flex-1">${message}</span>
    <button class="text-gray-400 hover:text-white p-0.5 ml-1 transition" onclick="this.parentElement.remove()">
      <i class="fa-solid fa-xmark text-xs"></i>
    </button>
  `;

  container.appendChild(toast);

  // Trigger enter animation
  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-2', 'opacity-0');
    toast.classList.add('translate-y-0', 'opacity-100');
  });

  // Auto remove
  setTimeout(() => {
    toast.classList.remove('translate-y-0', 'opacity-100');
    toast.classList.add('translate-y-2', 'opacity-0');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ================= PERSISTENCE: SERVER LÀ BẢN CHÍNH =================
// localStorage chỉ giữ id dự án mở gần nhất (và tuỳ chọn giao diện). Dữ liệu dự án luôn lưu lên
// server qua PUT /api/projects/{id}. Các bản `story_studio_proj_*` cũ chỉ còn được đọc một lần để
// đẩy lên server khi server chưa có dự án đó.
const LAST_PROJECT_KEY = 'story_studio_last_proj_id';
const LEGACY_PROJECT_KEY_PREFIX = 'story_studio_proj_';
const AUTOSAVE_DELAY_MS = 1500;
const ProjectSync = { timer: null, dirty: false, inFlight: null, lastErrorToastAt: 0 };

// Chữ trạng thái lưu ở thanh trên (#ws-save-state) thay cho nút Lưu cũ
function setSaveState(text) {
  const el = document.getElementById('ws-save-state');
  if (el) el.textContent = text;
}

function rememberLastProjectId(projectId) {
  try { localStorage.setItem(LAST_PROJECT_KEY, projectId); } catch { /* chế độ riêng tư / bị chặn */ }
}

function readLastProjectId() {
  try { return localStorage.getItem(LAST_PROJECT_KEY); } catch { return null; }
}

function readLegacyLocalProject(projectId) {
  try {
    const data = projectId ? localStorage.getItem(`${LEGACY_PROJECT_KEY_PREFIX}${projectId}`) : null;
    return data ? JSON.parse(data) : null;
  } catch {
    return null;
  }
}

// Server chỉ nhận `character` đúng mẫu Character (id, face_features...). Nhân vật dạng giao diện
// ({name, prompt, style, reference_image}) được cất vào settings.ui_character.
function buildServerPayload(project) {
  const payload = { ...project, settings: { ...(project.settings || {}) } };
  const ch = project.character;
  if (ch && !(ch.id && ch.face_features)) {
    payload.settings.ui_character = ch;
    payload.character = undefined;
    if (!payload.character_anchor && ch.prompt) payload.character_anchor = ch.prompt;
  }
  delete payload.is_demo;
  return payload;
}

function adoptServerProject(serverProject) {
  const project = serverProject;
  if (!project.settings) project.settings = {};
  if (!project.character && project.settings.ui_character) project.character = project.settings.ui_character;
  return project;
}

// Gọi sau mọi chỉnh sửa (tên cũ giữ nguyên vì được gọi ở rất nhiều nơi): hẹn lưu lên server.
function saveStateToLocal() {
  const project = AppState.currentProject;
  if (!project || !project.id) return;
  rememberLastProjectId(project.id);
  if (project.is_demo) return; // dự án mẫu chỉ để xem, không lưu
  ProjectSync.dirty = true;
  setSaveState('Đang lưu…');
  clearTimeout(ProjectSync.timer);
  ProjectSync.timer = setTimeout(() => { flushProjectSave({ silent: true }); }, AUTOSAVE_DELAY_MS);
}

// Lưu ngay (bỏ qua debounce). Trả về true nếu server đã có bản mới nhất.
async function flushProjectSave({ silent = false } = {}) {
  clearTimeout(ProjectSync.timer);
  const project = AppState.currentProject;
  if (!project || project.is_demo) return true;
  if (ProjectSync.inFlight) await ProjectSync.inFlight;
  if (!ProjectSync.dirty) { setSaveState('Đã lưu'); return true; }
  if (!AppState.serverOnline) {
    setSaveState('Chưa lưu (máy chủ offline)');
    if (!silent) showToast("Máy chủ đang offline: thay đổi CHƯA được lưu. Sẽ tự lưu khi máy chủ online lại.", "warning", 7000);
    return false;
  }
  ProjectSync.dirty = false;
  setSaveState('Đang lưu…');
  ProjectSync.inFlight = API.saveProject(buildServerPayload(project));
  const saved = await ProjectSync.inFlight;
  ProjectSync.inFlight = null;
  if (saved && saved.id) {
    // Trong lúc chờ, người dùng có thể đã sửa tiếp: khi đó vẫn là "Đang lưu…" cho tới lần lưu sau
    setSaveState(ProjectSync.dirty ? 'Đang lưu…' : 'Đã lưu');
    return true;
  }

  ProjectSync.dirty = true;
  setSaveState('Lưu thất bại');
  const now = Date.now();
  if (!silent || now - ProjectSync.lastErrorToastAt > 30000) {
    ProjectSync.lastErrorToastAt = now;
    showToast(`Lưu dự án lên máy chủ thất bại: ${escapeHtml(String(API.lastError || 'không rõ lỗi'))}`, "error", 8000);
  }
  return false;
}

// Gộp kết quả server vừa tạo (Muse, giọng...) cho một cảnh vào bản đang chỉnh trên giao diện
const SERVER_MEDIA_FIELDS = [
  'image_path', 'image_url', 'motion_video_path', 'video_url', 'video_segment_path', 'video_segment_url',
  'voice_audio_path', 'voice_audio_url', 'audio_url', 'srt_path', 'srt_url', 'duration',
  'media_view_mode', 'status', 'status_image', 'status_video', 'status_voice', 'metadata'
];

function mergeServerSceneMedia(serverProject, sceneId) {
  const local = AppState.currentProject?.scenes?.find(s => s.id === sceneId);
  const remote = serverProject?.scenes?.find(s => s.id === sceneId);
  if (!local || !remote) return false;
  for (const field of SERVER_MEDIA_FIELDS) {
    if (remote[field] !== undefined && remote[field] !== null) local[field] = remote[field];
  }
  if (local.image_url && !local.image_url.includes('?')) local.image_url = `${local.image_url}?t=${Date.now()}`;
  return true;
}

// ================= INITIALIZATION =================
async function initApp() {
  console.log("Initializing YouTube AI Storyboard Studio UI...");

  // Check backend server status trước: dự án luôn được tải từ server
  await checkServerHealth();
  AppState.healthCheckInterval = setInterval(checkServerHealth, 8000);

  // Dự án cần mở: ?project_id=... hoặc dự án mở gần nhất
  const urlParams = new URLSearchParams(window.location.search);
  const wantedId = urlParams.get('project_id') || readLastProjectId();
  await loadInitialProject(wantedId);

  // Attempt to fetch project list from backend
  loadProjectsList();

  // Bind Event Listeners
  bindEventListeners();

  // Render UI
  renderFullUI();

  // Ensure Image Engine defaults to Meta Muse Cloud (Free 2K)
  if (DOM.selectImageProvider) {
    DOM.selectImageProvider.value = AppState.currentProject?.image_provider || "meta_muse_cloud";
  }
  if (DOM.step1EngineSelect) {
    DOM.step1EngineSelect.value = "meta_muse_cloud";
  }

  // Trang mở đầu: trang đã dùng lần trước của dự án này (workspace.js, localStorage ws_page_<project_id>);
  // đọc trước khi switchStep() ghi đè; chưa có thì như cũ (có cảnh: trang Cảnh, chưa có: trang Ý tưởng)
  const savedPage = rememberedPage(AppState.currentProject?.id);
  // Dự án, Thư viện Muse, Tài khoản không phải trang làm việc: tải lại luôn mở trang làm việc (móc của chúng cũng chưa đăng ký lúc này)
  if (savedPage && !['projects', 'gallery', 'accounts'].includes(savedPage)) {
    showPage(savedPage);
  } else if (AppState.currentProject && AppState.currentProject.scenes && AppState.currentProject.scenes.length > 0) {
    switchStep(2);
  } else {
    switchStep(1);
  }

  // Initialize Meta Muse Cloud Engine
  initMuseCloud();

  // Initialize True Crime Studio (code nằm trong /static/true_crime.js)
  initTrueCrimeStudio();

  // Tự mở modal Muse khi URL yêu cầu (#muse, ?mode=muse, ?view=muse); urlParams khai báo ở đầu initApp
  if (window.location.hash === '#muse' || urlParams.get('mode') === 'muse' || urlParams.get('view') === 'muse') {
    setTimeout(openMuseModal, 200);
  }

  showToast("Storyboard Studio đã sẵn sàng!", "success");
}

async function loadInitialProject(wantedId) {
  if (wantedId && AppState.serverOnline) {
    const remote = await API.getProject(wantedId);
    if (remote && remote.id) {
      AppState.currentProject = adoptServerProject(remote);
      rememberLastProjectId(remote.id);
      return;
    }
    // Server chưa có dự án này nhưng trình duyệt còn bản cũ (trước khi server là bản chính): đẩy lên server
    const legacy = readLegacyLocalProject(wantedId);
    // (kể cả dự án mẫu cũ: trước đây người dùng có thể đã sửa thẳng trên nó)
    if (legacy && legacy.id && !legacy.is_demo) {
      const saved = await API.saveProject(buildServerPayload(legacy));
      if (saved && saved.id) {
        AppState.currentProject = adoptServerProject(saved);
        rememberLastProjectId(saved.id);
        showToast(`Đã chuyển dự án "${escapeHtml(saved.name)}" từ trình duyệt lên máy chủ.`, "info", 6000);
        return;
      }
      showToast(`Không chuyển được dự án cũ lên máy chủ: ${escapeHtml(String(API.lastError || ''))}`, "error", 8000);
    }
  } else if (wantedId && !AppState.serverOnline) {
    showToast("Máy chủ đang offline: chưa tải được dự án. Hãy chạy run.bat rồi tải lại trang.", "warning", 8000);
  }

  // Không có dự án nào để mở: hiện dự án mẫu (chỉ xem, không tự lưu)
  AppState.currentProject = JSON.parse(JSON.stringify(DEFAULT_PROJECT));
  AppState.currentProject.is_demo = true;
}

async function checkServerHealth() {
  const wasOnline = AppState.serverOnline;
  const isHealthy = await API.checkHealth();
  AppState.serverOnline = isHealthy;
  if (isHealthy && !wasOnline && ProjectSync.dirty) {
    // Máy chủ online trở lại: lưu nốt các thay đổi đang chờ
    flushProjectSave({ silent: true });
  }

  if (DOM.backendStatusDot && DOM.backendStatusText) {
    if (isHealthy) {
      DOM.backendStatusDot.className = "w-2 h-2 rounded-full bg-emerald-500 animate-pulse";
      DOM.backendStatusText.textContent = `FastAPI Backend Online (Port ${window.location.port || (window.location.protocol === 'https:' ? '443' : '80')})`;
    } else {
      DOM.backendStatusDot.className = "w-2 h-2 rounded-full bg-amber-500";
      DOM.backendStatusText.textContent = "Backend Offline - Chế độ Client Studio";
    }
  }
}

async function loadProjectsList() {
  const remoteProjects = await API.getProjects();
  if (remoteProjects && Array.isArray(remoteProjects) && remoteProjects.length > 0) {
    AppState.projectsList = remoteProjects;
  } else {
    // Local list fallback
    AppState.projectsList = [
      { id: AppState.currentProject.id, name: AppState.currentProject.name, scene_count: AppState.currentProject.scenes.length }
    ];
  }
}

// ================= RENDER UI FUNCTIONS =================
function renderFullUI() {
  if (AppState.currentProject?.scenes) {
    AppState.currentProject.scenes.forEach(sc => {
      if (!sc.audio_url && sc.voice_audio_url) sc.audio_url = sc.voice_audio_url;
      if (!sc.voice_audio_url && sc.audio_url) sc.voice_audio_url = sc.audio_url;
      if (sc.audio_url && sc.status_voice !== 'generating') sc.status_voice = 'ready';
    });
  }
  renderHeader();
  renderSceneList();
  renderPreviewPlayer();
  renderSettings();
  paintProducerForCurrentProject();
  // Nút "Tạo bản tiếng Anh" (true_crime.js) hiện hay ẩn tuỳ dự án đang mở. Hook ở đây thay vì ở switchProject để
  // cũng đúng khi tải lại trang, tạo dự án mới hay nhập dự án.
  window.refreshLanguageVersionButton?.(AppState.currentProject);
}

function formatDisplayVoice(rawVoice) {
  if (!rawVoice) rawVoice = "vi-VN-NamMinhNeural";
  const str = String(rawVoice).trim();
  // Vietnamese voices identified FIRST
  if (str.startsWith("vieneu-review-")) return formatDisplayVoice("vieneu-" + str.slice("vieneu-review-".length)) + " · review";
  if (str.includes("NamMinh") || str.includes("Nam Minh") || str === "vi-VN-NamMinhNeural") return "🇻🇳 Nam Minh";
  if (str.includes("HoaiMy") || str.includes("Hoài My") || str === "vi-VN-HoaiMyNeural") return "🇻🇳 Hoài My";
  if (str.includes("MaiAnh") || str.includes("Mai Anh") || str === "vieneu-MaiAnh") return "🇻🇳 VieNeu Mai Anh";
  if (str.includes("TrucLy") || str.includes("Trúc Ly") || str === "vieneu-TrucLy") return "🇻🇳 VieNeu Trúc Ly";
  if (str.includes("MyDuyen") || str.includes("Mỹ Duyên") || str === "vieneu-MyDuyen") return "🇻🇳 VieNeu Mỹ Duyên";
  if (str.includes("ThienMinh") || str.includes("Thiện Minh") || str === "vieneu-ThienMinh") return "🇻🇳 VieNeu Thiện Minh";
  if (str.startsWith("vi-") || str.includes("vi-VN") || str.startsWith("vieneu")) {
    return "🇻🇳 " + str.replace("vi-VN-", "").replace("vieneu-", "").replace("Neural", "");
  }
  // English voices
  if (str.includes("Andrew")) return "🇺🇸 Andrew Multilingual";
  if (str.includes("Brian")) return "🇺🇸 Brian Multilingual";
  if (str.includes("Ava")) return "🇺🇸 Ava Multilingual";
  if (str.includes("Emma")) return "🇺🇸 Emma Multilingual";
  if (str.includes("Christopher")) return "🇺🇸 Christopher";
  if (str.includes("Guy")) return "🇺🇸 Guy";
  if (str.includes("Jenny")) return "🇺🇸 Jenny";
  if (str.startsWith("en-")) return "🇺🇸 " + str.replace("en-US-", "").replace("Neural", "");
  return str;
}
window.formatDisplayVoice = formatDisplayVoice;

function renderHeader() {
  if (AppState.currentProject) {
    DOM.currentProjectTitle.textContent = AppState.currentProject.name;
    const rawVoice = AppState.currentProject.settings?.voice || AppState.currentProject.voice || (DOM.selectVoice?.value || "vi-VN-NamMinhNeural");
    const displayVoice = formatDisplayVoice(rawVoice);
    if (DOM.headerVoiceName) {
      DOM.headerVoiceName.textContent = displayVoice;
    }
  }
}

function calculateTotalDuration() {
  if (!AppState.currentProject || !AppState.currentProject.scenes) return "00:00s";
  const totalSeconds = AppState.currentProject.scenes.reduce((sum, s) => sum + (parseFloat(s.duration) || 5.0), 0);
  const mins = Math.floor(totalSeconds / 60);
  const secs = Math.floor(totalSeconds % 60);
  return `${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}s tổng`;
}

function renderSceneList() {
  const container = DOM.sceneListContainer;
  const project = AppState.currentProject;
  if (!container || !project) return;

  const scenes = project.scenes || [];
  DOM.sceneCountBadge.textContent = scenes.length;
  DOM.totalDurationBadge.textContent = calculateTotalDuration();
  updateAssetReadiness();

  if (DOM.projectVoiceBadge || DOM.headerVoiceName) {
    const rawVoice = project.settings?.voice || project.voice || (DOM.selectVoice?.value || "vi-VN-NamMinhNeural");
    const displayVoice = formatDisplayVoice(rawVoice);
    if (DOM.projectVoiceBadge) {
      DOM.projectVoiceBadge.textContent = displayVoice;
    }
    if (DOM.headerVoiceName) {
      DOM.headerVoiceName.textContent = displayVoice;
    }
  }

  if (scenes.length === 0) {
    container.innerHTML = `
      <div class="text-center py-16 bg-[#161824] rounded-2xl border border-dashed border-gray-800 p-8">
        <i class="fa-solid fa-film text-4xl text-gray-600 mb-3"></i>
        <h4 class="text-sm font-semibold text-gray-300">Chưa có phân cảnh nào</h4>
        <p class="text-xs text-gray-500 mt-1 max-w-sm mx-auto">Quay về trang Ý tưởng để dán truyện cho AI chia cảnh, hoặc bấm "Thêm cảnh mới" để bắt đầu sáng tạo.</p>
        <div class="mt-4 flex items-center justify-center gap-2">
          <button onclick="showPage('idea')" class="ws-btn ws-btn-primary">
            <i class="fa-solid fa-arrow-left mr-1"></i> Về trang Ý tưởng
          </button>
        </div>
      </div>
    `;
    if (window.renderScriptList) window.renderScriptList();
    return;
  }

  container.innerHTML = scenes.map((scene, idx) => {
    const isSelected = idx === AppState.selectedSceneIndex;
    const durStr = `${(scene.duration || 5).toFixed(1)}s`;

    // Badges status
    const hasImage = Boolean(scene.image_url);
    const hasVideo = Boolean(scene.video_segment_url || scene.video_url);
    const hasVoice = sceneHasVoiceAudio(scene);
    const isGenVoice = scene.status_voice === 'generating';
    const isGenImage = scene.status_image === 'generating';
    const isGenVideo = scene.status_video === 'generating';
    const isShowingVideo = (scene.media_view_mode === 'video') || (!hasImage && hasVideo);
    const currentVideoUrl = scene.video_segment_url || scene.video_url;
    const warnBadgesHtml = buildSceneWarningBadges(scene);

    let statusBadgeHtml = '';
    if (isGenImage || isGenVoice || isGenVideo) {
      statusBadgeHtml = `<span class="text-[11px] bg-slate-50 text-slate-700 px-2 py-0.5 rounded border border-slate-200 animate-pulse font-semibold flex items-center gap-1"><i class="fa-solid fa-spinner fa-spin"></i> Đang sinh AI... <button type="button" onclick="resetSceneImageStatus(${idx})" class="text-[9px] underline ml-1 text-slate-900 cursor-pointer">Bỏ qua</button></span>`;
    } else if (hasVideo && hasVoice) {
      statusBadgeHtml = `<span class="text-[11px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-play text-emerald-600"></i> Đủ Voice & Video${scene.duration ? escapeHtml(` · ${Number(scene.duration).toFixed(1)}s`) : ''}</span>`;
    } else if (sceneHasRealVisual(scene) && hasVoice) {
      statusBadgeHtml = `<span class="text-[11px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200 font-semibold"><i class="fa-solid fa-check mr-1"></i> Đủ Voice & Ảnh</span>`;
    } else if (hasVideo && !hasVoice) {
      statusBadgeHtml = `<span class="text-[11px] bg-slate-50 text-slate-700 px-2 py-0.5 rounded border border-slate-200 font-semibold"><i class="fa-solid fa-film mr-1"></i> Có Video (Chưa voice)</span>`;
    } else if (!sceneHasRealVisual(scene) && hasVoice) {
      statusBadgeHtml = `<span class="text-[11px] bg-amber-50 text-amber-700 px-2 py-0.5 rounded border border-amber-200 font-semibold"><i class="fa-solid fa-image mr-1"></i> Chưa có Ảnh/Video</span>`;
    } else if (hasImage && !hasVoice) {
      statusBadgeHtml = `<span class="text-[11px] bg-slate-50 text-slate-700 px-2 py-0.5 rounded border border-slate-200 font-semibold"><i class="fa-solid fa-microphone mr-1"></i> Chưa có Voice</span>`;
    } else {
      statusBadgeHtml = `<span class="text-[11px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-medium">Cảnh mới</span>`;
    }

    return `
      <div id="scene-card-${scene.id}" data-index="${idx}" class="scene-card group transition-all duration-200 rounded-xl p-3.5 border ${isSelected ? 'bg-slate-50/70 border-slate-700 shadow-md ring-2 ring-slate-700/20' : 'bg-white border-slate-200 hover:border-slate-300 hover:shadow-xs'}">
        
        <!-- Card Top Bar -->
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="cursor-pointer font-bold text-[11px] px-2.5 py-0.5 rounded ${isSelected ? 'bg-slate-900 text-white shadow-xs' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}" onclick="selectScene(${idx})">
              Cảnh #${idx + 1}
            </span>
            <span class="text-xs text-slate-500 font-mono"><i class="fa-regular fa-clock mr-1"></i> ${durStr}</span>
            ${statusBadgeHtml}
            ${warnBadgesHtml}
          </div>

          <div class="flex items-center gap-1.5">
            <!-- Ken Burns / Motion FX Selector -->
            <div class="relative">
              <select onchange="updateSceneKenBurns(${idx}, this.value)" class="text-xs bg-slate-50 hover:bg-slate-100 text-slate-700 rounded-lg px-2 py-1 border border-slate-300 focus:outline-none focus:border-slate-700 cursor-pointer font-medium shadow-2xs">
                <option value="zoom_in" ${(scene.ken_burns === 'zoom_in' || scene.camera_motion === 'zoom_in' || !scene.camera_motion) ? 'selected' : ''}>🔍 Zoom In Chậm</option>
                <option value="zoom_out" ${(scene.ken_burns === 'zoom_out' || scene.camera_motion === 'zoom_out') ? 'selected' : ''}>🔎 Zoom Out</option>
                <option value="action_camera_shake" ${(scene.camera_motion === 'action_camera_shake' || scene.ken_burns === 'action_camera_shake') ? 'selected' : ''}>💥 Camera Rung Chấn</option>
                <option value="manga_speedlines" ${(scene.camera_motion === 'manga_speedlines' || scene.ken_burns === 'manga_speedlines') ? 'selected' : ''}>⚡ Vệt Speedlines</option>
                <option value="panoramic_sweep" ${(scene.camera_motion === 'panoramic_sweep' || scene.ken_burns === 'panoramic_sweep') ? 'selected' : ''}>🔭 Lia Toàn Cảnh</option>
                <option value="punch_zoom" ${(scene.camera_motion === 'punch_zoom' || scene.ken_burns === 'punch_zoom') ? 'selected' : ''}>👊 Punch Zoom Giật</option>
                <option value="pan_left" ${(scene.ken_burns === 'pan_left' || scene.ken_burns === 'pan_left_to_right' || scene.camera_motion === 'pan_left') ? 'selected' : ''}>↔️ Pan Trái -> Phải</option>
                <option value="pan_right" ${(scene.ken_burns === 'pan_right' || scene.ken_burns === 'pan_right_to_left' || scene.camera_motion === 'pan_right') ? 'selected' : ''}>↕️ Pan Phải -> Trái</option>
                <option value="diagonal" ${(scene.ken_burns === 'diagonal' || scene.camera_motion === 'diagonal' || scene.camera_motion === 'kenburns_diagonal') ? 'selected' : ''}>↗️ Zoom Chéo</option>
                <option value="static" ${(scene.ken_burns === 'static' || scene.ken_burns === 'none' || scene.camera_motion === 'static') ? 'selected' : ''}>⏹️ Tĩnh (No Move)</option>
              </select>
            </div>

          </div>
        </div>

        <!-- Card Grid (Thumbnail/Video + Script Content) -->
        <div class="grid grid-cols-12 gap-3">
          
          <!-- Thumbnail & Video Column (4 cols) -->
          <div class="col-span-12 sm:col-span-4 relative rounded-xl overflow-hidden border border-slate-300 aspect-video bg-slate-900 flex items-center justify-center group/img shadow-2xs">
            ${hasVideo ? `
              <div class="absolute top-1.5 left-1.5 z-20 flex items-center bg-black/80 backdrop-blur-md p-0.5 rounded-lg border border-white/20 shadow-xs">
                <button type="button" onclick="setMediaViewMode(${idx}, 'image')" class="px-2 py-0.5 rounded text-[9px] font-bold ${!isShowingVideo ? 'bg-slate-900 text-white shadow-2xs' : 'text-slate-300 hover:text-white'} transition cursor-pointer flex items-center gap-1" title="Chuyển sang xem Ảnh 2K">
                  <i class="fa-solid fa-image"></i>
                  <span>Ảnh</span>
                </button>
                <button type="button" onclick="setMediaViewMode(${idx}, 'video')" class="px-2 py-0.5 rounded text-[9px] font-bold ${isShowingVideo ? 'bg-slate-900 text-white shadow-2xs' : 'text-slate-300 hover:text-white'} transition cursor-pointer flex items-center gap-1" title="Chuyển sang xem Video chuyển động">
                  <i class="fa-solid fa-film"></i>
                  <span>Video</span>
                </button>
              </div>
            ` : ''}

            ${isShowingVideo && currentVideoUrl ? `
              <video src="${currentVideoUrl}${currentVideoUrl.includes('?') ? '&' : '?'}v=${encodeURIComponent(scene.updated_at || Date.now())}" class="w-full h-full object-cover rounded-xl" data-viewer-src="${escapeHtml(currentVideoUrl)}" data-viewer-kind="video" data-viewer-caption="Cảnh #${escapeHtml(String(idx + 1))}" preload="metadata" playsinline></video>
            ` : (hasImage ? `
              <img src="${scene.image_url}" alt="Scene #${idx + 1}" class="w-full h-full object-cover" data-viewer-src="${escapeHtml(scene.image_url)}" data-viewer-kind="image" data-viewer-caption="Cảnh #${escapeHtml(String(idx + 1))}" onerror="handleSceneImageError(this, ${idx})">
            ` : `
              <div class="w-full h-full bg-slate-100 flex flex-col items-center justify-center text-center p-2">
                <i class="fa-solid fa-mountain-sun text-2xl text-slate-400 mb-1"></i>
                <span class="text-[10px] text-slate-500 font-medium">Chưa có ảnh/video</span>
              </div>
            `)}

            ${isGenImage && !isShowingVideo ? `
              <div class="absolute inset-0 bg-white/85 backdrop-blur-xs flex flex-col items-center justify-center p-2 text-center z-10">
                <i class="fa-solid fa-spinner fa-spin text-xl text-slate-700 mb-1"></i>
                <span class="text-[10px] text-slate-900 font-bold mb-1">Đang sinh ảnh AI...</span>
                <button type="button" onclick="resetSceneImageStatus(${idx})" class="text-[9px] px-2 py-0.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded cursor-pointer">Bỏ qua</button>
              </div>
            ` : (isGenVideo && isShowingVideo ? `
              <div class="absolute inset-0 bg-white/85 backdrop-blur-xs flex flex-col items-center justify-center p-2 text-center z-10">
                <i class="fa-solid fa-spinner fa-spin text-xl text-slate-700 mb-1"></i>
                <span class="text-[10px] text-slate-900 font-bold mb-1">Đang sinh video AI...</span>
              </div>
            ` : '')}

            <!-- Badges -->
            <div class="absolute bottom-1 right-1 bg-black/75 px-1.5 py-0.5 rounded text-[9px] text-white font-mono z-10">
              ${isShowingVideo ? '10s Motion' : '16:9'}
            </div>
            
            <!-- Hover Action Buttons Overlay -->
            <div class="ws-scene-actions absolute inset-0 bg-slate-950/60 opacity-0 group-hover/img:opacity-100 flex items-center justify-center gap-1.5 transition duration-200 z-10">
              <button onclick="regenerateSceneImage(${idx})" title="Gen lại ảnh AI" class="p-1.5 bg-slate-900 hover:bg-slate-700 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110">
                <i class="fa-solid fa-arrows-rotate"></i>
              </button>
              <button onclick="generateSceneWithMuse(${idx}, 'image')" title="Tạo ảnh 2K bằng Muse Fleet (tài khoản ảnh)" class="p-1.5 bg-slate-900 hover:bg-slate-700 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110">
                <i class="fa-brands fa-meta"></i>
              </button>
              <button onclick="generateSceneWithMuse(${idx}, 'video')" title="Tạo video Muse dài theo lời thoại: lời dài thì nhiều video nối nhau (báo số video trước khi chạy)" class="p-1.5 bg-slate-900 hover:bg-slate-700 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110">
                <i class="fa-solid fa-film"></i>
              </button>
              <button onclick="openMuseModalForScene(${idx})" title="Chọn video/ảnh từ Gallery Muse" class="p-1.5 bg-amber-600 hover:bg-amber-500 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110">
                <i class="fa-solid fa-photo-film"></i>
              </button>
              <label title="Tải ảnh riêng từ máy" class="p-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110 cursor-pointer">
                <i class="fa-solid fa-upload"></i>
                <input type="file" accept="image/*" class="hidden" onchange="uploadCustomSceneImage(${idx}, this)">
              </label>
              <label title="Tải video MP4 riêng từ máy" class="p-1.5 bg-slate-800 hover:bg-slate-900 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110 cursor-pointer">
                <i class="fa-solid fa-file-video"></i>
                <input type="file" accept="video/*" class="hidden" onchange="uploadCustomSceneVideo(${idx}, this)">
              </label>
              ${(isShowingVideo && currentVideoUrl) || hasImage ? `<button type="button" data-viewer-src="${escapeHtml(isShowingVideo && currentVideoUrl ? currentVideoUrl : scene.image_url)}" data-viewer-kind="${isShowingVideo && currentVideoUrl ? 'video' : 'image'}" data-viewer-caption="Cảnh #${escapeHtml(String(idx + 1))}" title="Xem lớn" class="p-1.5 bg-slate-900 hover:bg-slate-700 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110"><i class="fa-solid fa-magnifying-glass-plus"></i></button>` : ''}
              <button onclick="selectScene(${idx})" title="Xem trong Studio Player" class="p-1.5 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110">
                <i class="fa-solid fa-play"></i>
              </button>
            </div>
          </div>

          <!-- Script & Voice Column (8 cols) -->
          <div class="col-span-12 sm:col-span-8 flex flex-col justify-between space-y-2">
            
            <!-- Lời kể: chỉ đọc, sửa ở trang Kịch bản và giọng -->
            <div>
              <div class="flex items-center justify-between text-[11px] text-slate-500 mb-1">
                <span class="font-bold uppercase tracking-wider text-slate-700">Lời kể</span>
                <span class="text-[10px] text-slate-400 font-mono">${(scene.text || '').length} ký tự</span>
              </div>
              <p class="scene-narration-readonly text-xs text-slate-700 leading-relaxed" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin:0">${escapeHtml(scene.text || '') || '(Chưa có lời kể)'}</p>
            </div>

            <!-- Dual Prompt Switcher: Image Prompt vs Video Motion Prompt -->
            <div>
              <div class="flex items-center justify-between text-[11px] text-slate-500 mb-1">
                <div class="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200">
                  <button 
                    type="button" 
                    onclick="switchScenePromptTab(${idx}, 'image')" 
                    id="btn-tab-img-${idx}" 
                    class="px-2.5 py-1 rounded-md text-[10px] font-extrabold ${(!scene.active_prompt_tab || scene.active_prompt_tab === 'image') ? 'bg-white text-slate-700 shadow-2xs border border-slate-200' : 'text-slate-500 hover:text-slate-800'} transition cursor-pointer flex items-center gap-1.5"
                    title="Mô tả cảnh để vẽ ảnh 2K, và chữ đầy đủ gửi Muse"
                  >
                    <i class="fa-solid fa-image text-slate-500 text-[10px]"></i>
                    <span>Prompt Ảnh (2K)</span>
                  </button>
                  <button 
                    type="button" 
                    onclick="switchScenePromptTab(${idx}, 'video')" 
                    id="btn-tab-vid-${idx}" 
                    class="px-2.5 py-1 rounded-md text-[10px] font-extrabold ${scene.active_prompt_tab === 'video' ? 'bg-white text-slate-700 shadow-2xs border border-slate-200' : 'text-slate-500 hover:text-slate-800'} transition cursor-pointer flex items-center gap-1.5"
                    title="Chỉ đọc: prompt từng video mà nút Muse Video trên thẻ gửi (số video, số giây); cảnh được chọn làm video cao trào thì thêm bản giao việc mà nút làm video cao trào gửi"
                  >
                    <i class="fa-solid fa-film text-slate-500 text-[10px]"></i>
                    <span>Video gửi Muse</span>
                  </button>
                </div>
                <span class="text-[9px] font-mono ${scene.active_prompt_tab === 'video' ? 'text-slate-700 font-bold' : 'text-slate-400'}" id="prompt-spec-${idx}">
                  ${scene.active_prompt_tab === 'video' ? 'Dài theo lời kể' : '2K • 16:9'}
                </span>
              </div>

              <!-- Textarea for Image Prompt -->
              <div id="prompt-container-img-${idx}" class="${(!scene.active_prompt_tab || scene.active_prompt_tab === 'image') ? '' : 'hidden'}">
                <div class="ws-mp-label">Mô tả cảnh (bạn sửa được)</div>
                <textarea 
                  oninput="updateSceneVisualPromptLive(${idx}, this.value)"
                  onchange="updateSceneVisualPrompt(${idx}, this.value)" 
                  class="w-full bg-slate-50 border border-slate-300 rounded-lg p-2 text-[11px] text-slate-700 focus:bg-white focus:border-slate-700 focus:outline-none font-mono transition shadow-2xs resize-none h-14 leading-relaxed"
                  placeholder="Mô tả bối cảnh hình ảnh AI 2K/8K (Image Prompt)..."
                >${escapeHtml(scene.visual_prompt || scene.image_prompt || '')}</textarea>
                <details class="ws-mp" data-muse-prompt-kind="image" data-scene-index="${escapeHtml(idx)}">
                  <summary>Prompt đầy đủ gửi Muse</summary>
                  <div class="ws-mp-body" data-muse-prompt-body><div class="ws-mp-note">Mở ra để xem chữ Muse nhận.</div></div>
                </details>
              </div>

              <!-- Video gửi Muse: chỉ đọc (scene_prompts.js tải khi tab hiện) -->
              <div id="prompt-container-vid-${idx}" class="${scene.active_prompt_tab === 'video' ? '' : 'hidden'}">
                <div class="ws-mp-body" style="padding:0" data-muse-prompt-kind="video" data-scene-index="${escapeHtml(idx)}" data-muse-prompt-body><div class="ws-mp-note">Đang chờ tải…</div></div>
              </div>
            </div>

            <!-- Nút Muse của cảnh (nghe, tua, thu lại giọng nằm ở trang Kịch bản và giọng) -->
            <div class="flex items-center justify-end pt-2 border-t border-slate-100 flex-wrap gap-2">
              <div class="flex items-center gap-1.5 flex-wrap">
                <button 
                  onclick="generateSceneWithMuse(${idx}, 'image')" 
                  class="text-[10px] text-slate-700 hover:text-slate-900 font-bold flex items-center gap-1 transition px-2 py-1 rounded-lg bg-slate-50 border border-slate-200 hover:bg-slate-100 cursor-pointer shadow-2xs"
                  title="Tạo ảnh 2K riêng cảnh này bằng Muse Fleet (tài khoản ảnh)"
                >
                  <i class="fa-brands fa-meta text-xs text-slate-700"></i>
                  <span>Muse 2K</span>
                </button>
                <button 
                  onclick="generateSceneWithMuse(${idx}, 'video')" 
                  class="text-[10px] text-slate-700 hover:text-slate-900 font-bold flex items-center gap-1 transition px-2 py-1 rounded-lg bg-slate-50 border border-slate-200 hover:bg-slate-100 cursor-pointer shadow-2xs"
                  title="Tạo video Muse dài theo lời thoại: lời dài thì nhiều video nối nhau (báo số video trước khi chạy)"
                >
                  <i class="fa-solid fa-film text-xs text-slate-700"></i>
                  <span>Muse Video</span>
                </button>
              </div>
            </div>

          </div>

        </div>

      </div>
    `;
  }).join('');
  if (window.renderScriptList) window.renderScriptList();
}

function renderPreviewPlayer() {
  const project = AppState.currentProject;
  if (!project || !project.scenes || project.scenes.length === 0) return;

  const currentIdx = AppState.selectedSceneIndex;
  const scene = project.scenes[currentIdx] || project.scenes[0];

  DOM.playerActiveSceneBadge.textContent = `Cảnh #${currentIdx + 1} / ${project.scenes.length}`;

  // Image or Direct Motion Video Player
  const hasImage = Boolean(scene.image_url);
  const hasVideo = Boolean(scene.video_segment_url || scene.video_url);
  const isVideoMode = (scene.media_view_mode === 'video') || (!hasImage && hasVideo);
  const videoUrl = scene.video_segment_url || scene.video_url;

  if (isVideoMode && videoUrl) {
    if (DOM.previewVideoElem) {
      DOM.previewVideoElem.src = `${videoUrl}${videoUrl.includes('?') ? '&' : '?'}v=${encodeURIComponent(scene.updated_at || Date.now())}`;
      DOM.previewVideoElem.classList.remove('hidden');
    }
    DOM.previewImageElem.classList.add('hidden');
    DOM.previewImagePlaceholder.classList.add('hidden');
    DOM.previewKbBadge.innerHTML = `<i class="fa-solid fa-film text-slate-400 mr-1"></i> Video Motion`;
  } else if (hasImage) {
    if (DOM.previewVideoElem) {
      DOM.previewVideoElem.pause();
      DOM.previewVideoElem.classList.add('hidden');
    }
    DOM.previewImageElem.onerror = function() {
      this.onerror = null;
      const fallbackSvg = generateSceneVisualSvg(scene, project, currentIdx);
      this.src = fallbackSvg;
      scene.image_url = fallbackSvg;
      saveStateToLocal();
    };
    DOM.previewImageElem.src = scene.image_url;
    DOM.previewImageElem.classList.remove('hidden');
    DOM.previewImagePlaceholder.classList.add('hidden');

    // Update Ken Burns badge and animation class
    const kbEffect = scene.camera_motion || scene.ken_burns || 'zoom_in';
    DOM.previewKbBadge.textContent = formatKenBurnsName(kbEffect);
    applyKenBurnsEffect(kbEffect);
  } else {
    if (DOM.previewVideoElem) {
      DOM.previewVideoElem.pause();
      DOM.previewVideoElem.classList.add('hidden');
    }
    DOM.previewImageElem.classList.add('hidden');
    DOM.previewImagePlaceholder.classList.remove('hidden');
  }

  // Subtitle
  DOM.previewSubtitleText.textContent = scene.text || "(Không có lời thoại cho cảnh này)";

  // Duration
  DOM.previewTimeDisplay.textContent = `00:00 / ${(scene.duration || 5).toFixed(1)}s`;

  // Update play icon
  updatePlayButtonIcon();
}

function formatKenBurnsName(effect) {
  switch (effect) {
    case 'action_camera_shake': return '💥 Camera Rung Chấn Bùng Nổ';
    case 'manga_speedlines': return '⚡ Vệt Tốc Độ Speedlines';
    case 'panoramic_sweep': return '🔭 Lia Toàn Cảnh Panoramic';
    case 'punch_zoom': return '👊 Punch Zoom Giật Cục';
    case 'zoom_in': return '🔍 Zoom In chậm';
    case 'zoom_out': return '🔎 Zoom Out';
    case 'pan_left':
    case 'pan_left_to_right': return '↔️ Pan Trái sang Phải';
    case 'pan_right':
    case 'pan_right_to_left': return '↕️ Pan Phải sang Trái';
    case 'diagonal':
    case 'kenburns_diagonal':
    case 'kenburns-diagonal': return '↗️ Zoom Chéo (Diagonal)';
    case 'static':
    case 'none':
    default: return '⏹️ Tĩnh (No Move)';
  }
}

function applyKenBurnsEffect(effect) {
  const imgElem = DOM.previewImageElem;
  if (!imgElem) return;

  // Clear previous animation classes
  imgElem.classList.remove(
    'kb-effect-zoom-in',
    'kb-effect-zoom-out',
    'kb-effect-pan-left',
    'kb-effect-pan-right',
    'kb-effect-diagonal',
    'kb-effect-kenburns-diagonal',
    'kb-effect-action_camera_shake',
    'kb-effect-punch_zoom',
    'kb-effect-panoramic_sweep',
    'kb-effect-manga_speedlines'
  );

  if (!effect || effect === 'static' || effect === 'none') {
    imgElem.style.transform = '';
    return;
  }

  // Force reflow to immediately restart animation from frame 0
  void imgElem.offsetWidth;

  if (effect === 'action_camera_shake') {
    imgElem.classList.add('kb-effect-action_camera_shake');
  } else if (effect === 'punch_zoom') {
    imgElem.classList.add('kb-effect-punch_zoom');
  } else if (effect === 'panoramic_sweep') {
    imgElem.classList.add('kb-effect-panoramic_sweep');
  } else if (effect === 'manga_speedlines') {
    imgElem.classList.add('kb-effect-manga_speedlines');
  } else if (effect === 'zoom_in') {
    imgElem.classList.add('kb-effect-zoom-in');
  } else if (effect === 'zoom_out') {
    imgElem.classList.add('kb-effect-zoom-out');
  } else if (effect === 'pan_left' || effect === 'pan_left_to_right') {
    imgElem.classList.add('kb-effect-pan-left');
  } else if (effect === 'pan_right' || effect === 'pan_right_to_left') {
    imgElem.classList.add('kb-effect-pan-right');
  } else if (effect === 'diagonal' || effect === 'kenburns_diagonal' || effect === 'kenburns-diagonal') {
    imgElem.classList.add('kb-effect-diagonal');
  }
}

function updateAssetReadiness() {
  const project = AppState.currentProject;
  const scenes = project?.scenes || [];
  const total = scenes.length;
  if (total === 0) return;

  // Chỉ đếm cảnh có file thật: không tính status 'ready' suông, ảnh minh hoạ SVG hay ảnh demo
  const voicedCount = scenes.filter(sceneHasVoiceAudio).length;
  const imagedCount = scenes.filter(sceneHasRealVisual).length;

  const voiceElem = DOM.readinessVoiceCount || document.getElementById('readiness-voice-count');
  const imageElem = DOM.readinessImageCount || document.getElementById('readiness-image-count');
  const labelElem = DOM.readinessLabelBadge || document.getElementById('readiness-label-badge');

  if (voiceElem) voiceElem.textContent = `${voicedCount}/${total} Voice`;
  if (imageElem) imageElem.textContent = `${imagedCount}/${total} Ảnh`;

  const isAllReady = (voicedCount === total && imagedCount === total);
  if (labelElem) {
    if (isAllReady) {
      labelElem.className = "px-2 py-0.5 bg-emerald-100 text-emerald-800 text-[10px] font-bold rounded-full border border-emerald-300";
      labelElem.textContent = "Sẵn sàng kết xuất";
    } else {
      labelElem.className = "px-2 py-0.5 bg-amber-100 text-amber-800 text-[10px] font-bold rounded-full border border-amber-300";
      labelElem.textContent = "Chưa đủ Asset";
    }
  }
}

function renderSettings() {
  const project = AppState.currentProject;
  const settings = project?.settings;
  if (!project) return;

  if (DOM.selectVoice) {
    const v = settings?.voice || project.voice || "vi-VN-NamMinhNeural";
    DOM.selectVoice.value = v;
  }
  if (DOM.selectImageProvider) {
    DOM.selectImageProvider.value = project.image_provider || "meta_muse_cloud";
  }
  if (DOM.selectBgm) DOM.selectBgm.value = settings?.bgm || project.bgm_track || "cinematic_adventure";
  if (DOM.toggleAudioDucking) DOM.toggleAudioDucking.checked = (settings?.ducking ?? project.ducking) !== false;
  if (DOM.toggleHardsub) DOM.toggleHardsub.checked = (settings?.hardsub ?? project.hardsub) !== false;
  if (DOM.selectTransition) DOM.selectTransition.value = settings?.transition || project.transition || "dip_to_black";
  if (DOM.selectSubtitleStyle) DOM.selectSubtitleStyle.value = settings?.subtitle_style || project.subtitle_style || "kinetic_pop";

  if (DOM.selectProjectStyle && project) {
    DOM.selectProjectStyle.value = project.style_preset || DEFAULT_STYLE_PRESET;
    if (typeof window.renderLookStyleLine === "function") window.renderLookStyleLine(); // đặt .value không bắn sự kiện change nên dòng phong cách ở trang Hình mẫu phải vẽ lại tay
  }

  updateAssetReadiness();
}

// ================= EVENT LISTENERS =================
function bindEventListeners() {
  // Step 1 Event Listeners
  DOM.step1ScriptTextarea?.addEventListener('input', handleStep1ScriptInput);
  DOM.btnStep1ProcessScript?.addEventListener('click', handleStep1ProcessScript);
  DOM.step1ContentKind?.addEventListener('change', applyStep1ContentKind);
  applyStep1ContentKind();

  document.querySelectorAll('.btn-step1-sample').forEach(btn => {
    btn.addEventListener('click', () => {
      const sampleKey = btn.getAttribute('data-sample');
      if (SAMPLE_STORIES[sampleKey] && DOM.step1ScriptTextarea) {
        DOM.step1ScriptTextarea.value = SAMPLE_STORIES[sampleKey];
        handleStep1ScriptInput();

        if (sampleKey === 'us_murata_battle') {
          if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "manga_murata_battle";
          if (DOM.selectVoice) DOM.selectVoice.value = "en-US-BrianMultilingualNeural";
        } else if (sampleKey === 'us_spartan') {
          if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "spartan_epic_mythology";
          if (DOM.selectVoice) DOM.selectVoice.value = "en-US-AndrewMultilingualNeural";
        } else if (sampleKey === 'paladin') {
          if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "fantasy_paladin_armor";
          if (DOM.selectVoice) DOM.selectVoice.value = "vi-VN-NamMinhNeural";
        } else if (sampleKey === 'kingdom') {
          if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "manga_historical_war";
          if (DOM.selectVoice) DOM.selectVoice.value = "vi-VN-NamMinhNeural";
        }
        // Thẻ phong cách ở trang Ý tưởng (genres.js) theo dõi sự kiện change của ô chọn
        DOM.step1StyleSelect?.dispatchEvent(new Event('change'));

        showToast(`Đã nạp kịch bản & visual prompt: ${btn.textContent.trim()}`, "info");
      }
    });
  });

  DOM.step1ComicDropzone?.addEventListener('click', () => DOM.step1ComicFileInput?.click());
  DOM.step1ComicFileInput?.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleStep1ComicFileSelect(e.target.files[0]);
    }
  });
  DOM.step1ComicDropzone?.addEventListener('dragover', (e) => {
    e.preventDefault();
    DOM.step1ComicDropzone?.classList.add('border-amber-500', 'bg-amber-100/50');
  });
  DOM.step1ComicDropzone?.addEventListener('dragleave', (e) => {
    e.preventDefault();
    DOM.step1ComicDropzone?.classList.remove('border-amber-500', 'bg-amber-100/50');
  });
  DOM.step1ComicDropzone?.addEventListener('drop', (e) => {
    e.preventDefault();
    DOM.step1ComicDropzone?.classList.remove('border-amber-500', 'bg-amber-100/50');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleStep1ComicFileSelect(e.dataTransfer.files[0]);
    }
  });

  DOM.btnStep1SampleGrid?.addEventListener('click', () => loadComicSample('grid'));
  DOM.btnStep1SampleStrip?.addEventListener('click', () => loadComicSample('strip'));
  DOM.btnStep1ProcessComic?.addEventListener('click', handleStep1ProcessComic);

  // Step 2 & Header Produce Buttons
  DOM.selectProjectStyle?.addEventListener('change', (e) => {
    if (AppState.currentProject) {
      AppState.currentProject.style_preset = e.target.value;
      saveStateToLocal();
      renderPreviewPlayer();
      showToast(`Đã chọn phong cách: ${e.target.value}`, "info");
    }
  });

  // Nguồn ảnh: lưu vào dự án để nút tạo ảnh từng cảnh / vẽ lại toàn bộ dùng đúng nguồn đã chọn
  DOM.selectImageProvider?.addEventListener('change', (e) => {
    if (AppState.currentProject) {
      AppState.currentProject.image_provider = e.target.value;
      saveStateToLocal();
      showToast(`Đã chọn nguồn ảnh: ${e.target.options[e.target.selectedIndex]?.text || e.target.value}`, "info");
    }
  });

  DOM.btnProduceFromBoard?.addEventListener('click', startProduceLongVideo);

  DOM.btnRegenAllImages?.addEventListener('click', handleRegenAllImages);
  DOM.btnRegenAllVoices?.addEventListener('click', handleRegenAllVoices);

  // Step 4 Actions
  DOM.btnCinemaOpenFolder?.addEventListener('click', () => {
    if (AppState.currentProject) {
      API.openFolder(AppState.currentProject.id);
      showToast("Đang mở thư mục video trên Windows Explorer...", "info");
    }
  });

  // Scene Actions
  DOM.btnAddScene?.addEventListener('click', handleAddScene);
  DOM.btnAutoGenAll?.addEventListener('click', handleAutoGenAll);

  // Preview Player Actions
  DOM.btnPreviewPlayToggle?.addEventListener('click', togglePreviewPlayback);
  DOM.btnPrevScene?.addEventListener('click', prevScene);
  DOM.btnNextScene?.addEventListener('click', nextScene);
  DOM.btnPlayAllStory?.addEventListener('click', togglePlayAllStory);
  DOM.btnToggleFullscreen?.addEventListener('click', togglePlayerFullscreen);

  // Audio settings & Voice Sample Preview
  DOM.btnPreviewVoiceSample?.addEventListener('click', togglePlayVoiceSample);

  DOM.selectVoice?.addEventListener('change', (e) => {
    // If voice sample preview is playing, stop it
    if (DOM.voiceSampleAudio && !DOM.voiceSampleAudio.paused) {
      DOM.voiceSampleAudio.pause();
      DOM.voiceSampleAudio.currentTime = 0;
      resetVoiceSampleButtonState();
    }
    if (AppState.currentProject) {
      if (!AppState.currentProject.settings) AppState.currentProject.settings = {};
      AppState.currentProject.settings.voice = e.target.value;
      AppState.currentProject.voice = e.target.value;
      renderSceneList();
      saveStateToLocal();
      showToast(`Đã đổi giọng thuyết minh: ${e.target.value}`, "info");
    }
  });

  // settings.* để giao diện hiển thị; trường thật (bgm_track, ducking, hardsub) để server dùng khi dựng
  DOM.selectBgm?.addEventListener('change', (e) => {
    if (AppState.currentProject) {
      if (!AppState.currentProject.settings) AppState.currentProject.settings = {};
      AppState.currentProject.settings.bgm = e.target.value;
      AppState.currentProject.bgm_track = e.target.value;
      saveStateToLocal();
      showToast(`Đã cập nhật nhạc nền BGM`, "info");
    }
  });

  // Nút tải nhạc nền MP3 riêng (biểu tượng tải lên cạnh ô chọn nhạc)
  DOM.bgmUploadInput?.addEventListener('change', handleBgmUpload);
  loadBgmOptions();

  DOM.toggleAudioDucking?.addEventListener('change', (e) => {
    if (AppState.currentProject) {
      if (!AppState.currentProject.settings) AppState.currentProject.settings = {};
      AppState.currentProject.settings.ducking = e.target.checked;
      AppState.currentProject.ducking = e.target.checked;
      saveStateToLocal();
    }
  });

  DOM.toggleHardsub?.addEventListener('change', (e) => {
    if (AppState.currentProject) {
      if (!AppState.currentProject.settings) AppState.currentProject.settings = {};
      AppState.currentProject.settings.hardsub = e.target.checked;
      AppState.currentProject.hardsub = e.target.checked;
      saveStateToLocal();
    }
  });

  DOM.selectTransition?.addEventListener('change', (e) => {
    if (AppState.currentProject) {
      if (!AppState.currentProject.settings) AppState.currentProject.settings = {};
      AppState.currentProject.settings.transition = e.target.value;
      AppState.currentProject.transition = e.target.value;
      saveStateToLocal();
      showToast(`Đã chọn hiệu ứng chuyển cảnh: ${e.target.value}`, "info");
    }
  });

  DOM.selectSubtitleStyle?.addEventListener('change', (e) => {
    if (AppState.currentProject) {
      if (!AppState.currentProject.settings) AppState.currentProject.settings = {};
      AppState.currentProject.settings.subtitle_style = e.target.value;
      AppState.currentProject.subtitle_style = e.target.value;
      saveStateToLocal();
      showToast(`Đã chọn kiểu phụ đề động: ${e.target.value}`, "info");
    }
  });

  // YouTube Packaging & Thumbnail Events
  DOM.btnGenerateCustomThumbnail?.addEventListener('click', handleGenerateCustomThumbnail);
  DOM.btnCopySeoTitle?.addEventListener('click', () => copyToClipboard('input-seo-title', 'Đã sao chép tiêu đề YouTube!'));
  DOM.btnCopySeoDesc?.addEventListener('click', () => copyToClipboard('textarea-seo-desc', 'Đã sao chép mô tả YouTube!'));
  DOM.btnCopySeoTags?.addEventListener('click', () => copyToClipboard('input-seo-tags', 'Đã sao chép thẻ từ khóa YouTube!'));

  // Project Dropdown / Manager
  DOM.btnCreateProject?.addEventListener('click', handleCreateNewProject);

  // Global Audio and Video element listeners
  DOM.globalPreviewAudio?.addEventListener('ended', onAudioPlaybackEnded);
  DOM.globalPreviewAudio?.addEventListener('timeupdate', onAudioTimeUpdate);
  DOM.previewVideoElem?.addEventListener('timeupdate', onAudioTimeUpdate);
  DOM.previewVideoElem?.addEventListener('ended', () => {
    if (!DOM.globalPreviewAudio || !DOM.globalPreviewAudio.src || DOM.globalPreviewAudio.paused) {
      onAudioPlaybackEnded();
    }
  });

  // Click on video canvas box to toggle play/pause
  DOM.previewCanvasBox?.addEventListener('click', (e) => {
    if (e.target.closest('#preview-subtitle-overlay') || e.target.closest('#preview-kb-badge') || e.target.closest('#btn-preview-play-toggle')) return;
    togglePreviewPlayback();
  });

  // Keyboard Shortcuts
  window.addEventListener('keydown', handleGlobalKeydown);
}

function handleGlobalKeydown(e) {
  // Ignore shortcuts if typing in input/textarea
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
    if (e.key === 'Escape') {
      document.activeElement.blur();
    }
    return;
  }

  if (e.code === 'Space') {
    // Space trên nút, liên kết, ô nhập hay vùng sửa chữ thì để trình duyệt xử lý (bấm nút, gõ chữ)
    const t = e.target;
    if (t && t.closest && t.closest('button, a, input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return;
    // Chỉ phát/dừng khi đang ở trang Cảnh hoặc ngăn Xem thử đang mở
    const previewOpen = !!document.getElementById('scenes-preview-block')?.closest('#ws-drawer-body')
      && document.getElementById('ws-drawer')?.classList.contains('open');
    const onScenes = typeof currentPage === 'function' && currentPage() === 'scenes';
    if (!onScenes && !previewOpen) return;
    e.preventDefault();
    togglePreviewPlayback();
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault();
    handleSaveProject();
  }
}

// ================= SCENE CRUD & MANIPULATION =================
function selectScene(index) {
  if (!AppState.currentProject || !AppState.currentProject.scenes[index]) return;
  AppState.selectedSceneIndex = index;
  renderSceneList();
  renderPreviewPlayer();

  // Scroll card into view
  const card = document.getElementById(`scene-card-${AppState.currentProject.scenes[index].id}`);
  if (card) {
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function handleAddScene() {
  const project = AppState.currentProject;
  if (!project) return;

  const newIndex = project.scenes.length + 1;
  const demoAiImages = [
    '/static/demo_images/scene_1.jpg',
    '/static/demo_images/scene_2.jpg',
    '/static/demo_images/scene_3.jpg',
    '/static/demo_images/scene_4.jpg'
  ];
  const visualPrompt = `Anime cinematic style, scene #${newIndex}, dynamic shot, masterpiece 8k`;
  const newScene = {
    id: `scene-${Date.now()}`,
    order: newIndex,
    duration: 5.0,
    text: `Nội dung kịch bản cho phân cảnh #${newIndex}...`,
    visual_prompt: visualPrompt,
    image_prompt: visualPrompt,
    image_url: demoAiImages[(newIndex - 1) % demoAiImages.length],
    audio_url: "",
    voice_audio_url: "",
    camera_motion: "zoom_in",
    ken_burns: "zoom_in",
    status_voice: "idle",
    status_image: "ready",
    status: "draft"
  };

  project.scenes.push(newScene);
  AppState.selectedSceneIndex = project.scenes.length - 1;
  saveStateToLocal();
  renderSceneList();
  renderPreviewPlayer();
  showToast(`Đã thêm Cảnh #${newIndex}`, "success");
}

function moveScene(index, direction) {
  const project = AppState.currentProject;
  if (!project) return;

  const targetIndex = index + direction;
  if (targetIndex < 0 || targetIndex >= project.scenes.length) return;

  const [moved] = project.scenes.splice(index, 1);
  project.scenes.splice(targetIndex, 0, moved);

  // Update order property
  project.scenes.forEach((s, idx) => s.order = idx + 1);

  AppState.selectedSceneIndex = targetIndex;
  saveStateToLocal();
  renderSceneList();
  renderPreviewPlayer();
}

function duplicateScene(index) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return;

  const source = project.scenes[index];
  const duplicated = {
    ...JSON.parse(JSON.stringify(source)),
    id: `scene-${Date.now()}`,
    order: index + 2
  };

  project.scenes.splice(index + 1, 0, duplicated);
  project.scenes.forEach((s, idx) => s.order = idx + 1);

  AppState.selectedSceneIndex = index + 1;
  saveStateToLocal();
  renderSceneList();
  renderPreviewPlayer();
  showToast(`Đã nhân bản Cảnh #${index + 1}`, "info");
}

function deleteScene(index) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return;

  if (project.scenes.length <= 1) {
    showToast("Dự án phải giữ lại ít nhất 1 phân cảnh.", "warning");
    return;
  }
  if (!confirm(`Xóa Cảnh #${index + 1}? Lời thoại, ảnh và video đã gắn với cảnh này sẽ bị bỏ khỏi dự án.`)) return;

  const deletedScene = project.scenes.splice(index, 1);
  project.scenes.forEach((s, idx) => s.order = idx + 1);

  if (AppState.selectedSceneIndex >= project.scenes.length) {
    AppState.selectedSceneIndex = project.scenes.length - 1;
  }

  saveStateToLocal();
  renderSceneList();
  renderPreviewPlayer();
  showToast(`Đã xóa Cảnh #${index + 1}`, "info");
}

function updateSceneTextLive(index, newText) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return;
  project.scenes[index].text = newText;
  if (AppState.selectedSceneIndex === index && DOM.previewSubtitleText) {
    DOM.previewSubtitleText.textContent = newText || "(Không có lời thoại cho cảnh này)";
  }
}

function updateSceneText(index, newText) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return;

  project.scenes[index].text = newText;
  // Estimate duration roughly (words / 3.0 words per sec, min 4s)
  const wordCount = (newText.trim().split(/\s+/).filter(Boolean)).length;
  const estimatedDur = Math.max(4.0, parseFloat((wordCount / 2.8).toFixed(1)));
  project.scenes[index].duration = estimatedDur;

  saveStateToLocal();
  if (AppState.selectedSceneIndex === index) {
    renderPreviewPlayer();
  }
  DOM.totalDurationBadge.textContent = calculateTotalDuration();
}

function updateSceneVisualPrompt(index, newPrompt) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return;

  project.scenes[index].visual_prompt = newPrompt;
  project.scenes[index].image_prompt = newPrompt;
  saveStateToLocal();
}

function updateSceneVisualPromptLive(index, newPrompt) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return;

  project.scenes[index].visual_prompt = newPrompt;
  project.scenes[index].image_prompt = newPrompt;
}

function switchScenePromptTab(index, tab) {
  const project = AppState.currentProject;
  if (!project || !project.scenes || !project.scenes[index]) return;
  const scene = project.scenes[index];
  scene.active_prompt_tab = tab;

  const tabImgBtn = document.getElementById(`btn-tab-img-${index}`);
  const tabVidBtn = document.getElementById(`btn-tab-vid-${index}`);
  const containerImg = document.getElementById(`prompt-container-img-${index}`);
  const containerVid = document.getElementById(`prompt-container-vid-${index}`);
  const specBadge = document.getElementById(`prompt-spec-${index}`);

  if (tab === 'video') {
    if (tabImgBtn) {
      tabImgBtn.className = "px-2.5 py-1 rounded-md text-[10px] font-bold text-slate-500 hover:text-slate-800 transition cursor-pointer flex items-center gap-1.5";
    }
    if (tabVidBtn) {
      tabVidBtn.className = "px-2.5 py-1 rounded-md text-[10px] font-extrabold bg-white text-slate-700 shadow-2xs border border-slate-200 transition cursor-pointer flex items-center gap-1.5";
    }
    if (containerImg) containerImg.classList.add('hidden');
    if (containerVid) containerVid.classList.remove('hidden');
    // Prompt video thật (chỉ đọc) theo lời kể: scene_prompts.js hỏi máy chủ
    if (typeof window.loadSceneMusePrompt === 'function') window.loadSceneMusePrompt(index, 'video');
    if (specBadge) {
      specBadge.textContent = "Dài theo lời kể";
      specBadge.className = "text-[9px] font-mono text-slate-700 font-bold";
    }
  } else {
    if (tabImgBtn) {
      tabImgBtn.className = "px-2.5 py-1 rounded-md text-[10px] font-extrabold bg-white text-slate-700 shadow-2xs border border-slate-200 transition cursor-pointer flex items-center gap-1.5";
    }
    if (tabVidBtn) {
      tabVidBtn.className = "px-2.5 py-1 rounded-md text-[10px] font-bold text-slate-500 hover:text-slate-800 transition cursor-pointer flex items-center gap-1.5";
    }
    if (containerVid) containerVid.classList.add('hidden');
    if (containerImg) {
      containerImg.classList.remove('hidden');
    }
    if (specBadge) {
      specBadge.textContent = "2K • 16:9";
      specBadge.className = "text-[9px] font-mono text-slate-400";
    }
  }
}

function updateSceneKenBurns(index, effect) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return;

  project.scenes[index].ken_burns = effect;
  project.scenes[index].camera_motion = effect;
  saveStateToLocal();

  if (AppState.selectedSceneIndex === index) {
    renderPreviewPlayer();
  } else {
    selectScene(index);
  }
}

// ================= AI GENERATION (VOICE & IMAGE) =================
// Cảnh đang tạo giọng/ảnh: bấm thêm lần nữa không gửi yêu cầu thứ hai (hai kết quả về lệch nhau sẽ ghi đè trạng thái)
const SceneJobsInFlight = { voice: new Set(), image: new Set() };

// Trả về true nếu tạo xong, false nếu lỗi, null nếu bỏ qua (cảnh đang tạo dở)
async function regenerateSceneVoice(index) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return null;

  const scene = project.scenes[index];
  const jobKey = scene.id || scene;
  if (SceneJobsInFlight.voice.has(jobKey)) {
    showToast(`Cảnh #${index + 1} đang tạo giọng đọc, chờ xong rồi bấm lại.`, "info");
    return null;
  }
  SceneJobsInFlight.voice.add(jobKey);
  try {
    return await regenerateSceneVoiceInner(project, scene, index);
  } finally {
    SceneJobsInFlight.voice.delete(jobKey);
  }
}

async function regenerateSceneVoiceInner(project, scene, index) {
  const isEn = !(/[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]/i.test(scene.text || ''));
  const fallbackVoice = isEn ? "en-US-AndrewMultilingualNeural" : "vi-VN-NamMinhNeural";
  const voice = project.settings?.voice || project.voice || fallbackVoice;

  scene.status_voice = 'generating';
  renderSceneList();
  showToast(`Đang sinh âm thanh Voice cho Cảnh #${index + 1}...`, "info");

  // Call API
  let result = null;
  if (AppState.serverOnline) {
    result = await API.genVoice(project.id, scene.id, scene.text, voice);
  }

  if (result && result.audio_url) {
    scene.audio_url = result.audio_url;
    scene.voice_audio_url = result.audio_url;
    if (result.duration) scene.duration = parseFloat(result.duration);
    scene.status_voice = 'ready';
    if (result.scene?.metadata) scene.metadata = result.scene.metadata;
    if (result.fallback_used) {
      showToast(`Cảnh #${index + 1}: đang dùng giọng dự phòng ${escapeHtml(String(result.voice || ''))} (${escapeHtml(String(result.fallback_reason || 'giọng yêu cầu không chạy được'))}).`, "warning", 7000);
    } else {
      showToast(`Đã tạo xong Voice cho Cảnh #${index + 1}!`, "success");
    }
  } else {
    scene.status_voice = 'error';
    scene.metadata = { ...(scene.metadata || {}), voice_error: result?.detail || 'Máy chủ không phản hồi' };
    showToast(`Lỗi tạo Voice cho Cảnh #${index + 1}: ${escapeHtml(String(result?.detail || (AppState.serverOnline ? 'Máy chủ không phản hồi âm thanh.' : 'Máy chủ đang offline.')))}`, "error");
  }

  saveStateToLocal();
  renderSceneList();
  return scene.status_voice === 'ready';
}

// Mã phong cách máy chủ hiểu = các lựa chọn của ô "Phong cách" ở bước 2
function knownStylePresetIds() {
  return new Set([...(DOM.selectProjectStyle?.options || [])].map(o => o.value));
}

// Phong cách riêng của nhân vật chỉ dùng khi là mã hợp lệ; để trống = theo phong cách dự án
function characterStyleOverride(char) {
  const style = char?.style || '';
  return style && knownStylePresetIds().has(style) ? style : '';
}

// Trả về true nếu tạo xong, false nếu lỗi, null nếu bỏ qua (cảnh đang tạo dở)
async function regenerateSceneImage(index) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return null;

  const scene = project.scenes[index];
  const jobKey = scene.id || scene;
  if (SceneJobsInFlight.image.has(jobKey)) {
    showToast(`Cảnh #${index + 1} đang tạo ảnh, chờ xong rồi bấm lại.`, "info");
    return null;
  }
  SceneJobsInFlight.image.add(jobKey);
  try {
    return await regenerateSceneImageInner(project, scene, index);
  } finally {
    SceneJobsInFlight.image.delete(jobKey);
  }
}

async function regenerateSceneImageInner(project, scene, index) {
  const char = project.character;

  scene.status_image = 'generating';
  renderSceneList();
  if (AppState.selectedSceneIndex === index) {
    renderPreviewPlayer();
  }
  showToast(`Đang sinh ảnh AI đồng bộ cho Cảnh #${index + 1}...`, "info");

  // Build combined prompt with Character Consistency
  let finalPrompt = scene.visual_prompt || scene.image_prompt || scene.text || "";
  // Nhân vật do máy chủ khoá theo cảnh (services/scene_locks.py); không ghép mô tả nhân vật chung vào prompt

  let result = null;
  if (AppState.serverOnline) {
    result = await API.genImage(project.id, scene.id, finalPrompt, characterStyleOverride(char) || project.style_preset, char);
  }

  if (result && result.image_url) {
    const cacheBuster = result.image_url.includes('?') ? `&t=${Date.now()}` : `?t=${Date.now()}`;
    scene.image_url = `${result.image_url}${cacheBuster}`;
    scene.status_image = 'ready';
    if (result.scene?.metadata) scene.metadata = result.scene.metadata;
    if (result.is_placeholder) {
      showToast(`Cảnh #${index + 1}: đã tạo ảnh tạm offline (không phải ảnh AI).`, "warning", 6000);
    } else if (result.fallback_reason) {
      showToast(`Cảnh #${index + 1}: ảnh được tạo bằng ${escapeHtml(String(result.provider || ''))} vì ${escapeHtml(String(result.fallback_reason))}`, "warning", 7000);
    } else {
      showToast(`Đã sinh ảnh AI thành công cho Cảnh #${index + 1}!`, "success");
    }
  } else {
    // Không có ảnh mới: giữ nguyên ảnh cũ (nếu có), báo lỗi thật
    scene.status_image = 'error';
    scene.metadata = { ...(scene.metadata || {}), image_error: result?.detail || 'Máy chủ không phản hồi' };
    showToast(`Lỗi tạo ảnh cho Cảnh #${index + 1}: ${escapeHtml(String(result?.detail || (AppState.serverOnline ? 'Máy chủ không phản hồi.' : 'Máy chủ đang offline.')))}`, "error", 8000);
  }

  saveStateToLocal();
  renderSceneList();
  if (AppState.selectedSceneIndex === index) {
    renderPreviewPlayer();
  }
  return scene.status_image === 'ready';
}

// Ảnh/video tự tải lên được gửi lên server (images/{scene}.jpg, videos/{scene}_muse.mp4) để bước
// dựng trên server dùng được; không còn nhét data URL hoặc blob: (mất khi tải lại trang) vào dự án.
async function uploadCustomSceneMedia(index, fileInput, kind) {
  const file = fileInput.files?.[0];
  fileInput.value = '';
  const project = AppState.currentProject;
  const scene = project?.scenes?.[index];
  if (!file || !scene) return;
  if (project.is_demo) {
    showToast("Đây là dự án mẫu (chỉ để xem). Hãy tạo dự án mới trước khi tải media lên.", "warning", 7000);
    return;
  }
  if (!AppState.serverOnline) {
    showToast("Máy chủ đang offline nên chưa tải file lên được.", "error", 6000);
    return;
  }
  if (!(await flushProjectSave())) return;

  const label = kind === 'video' ? 'video' : 'ảnh';
  showToast(`Đang tải ${label} lên cho Cảnh #${index + 1}...`, "info");
  const res = await API.uploadSceneMedia(project.id, scene.id, file, kind);
  if (!res?.success || !res.scene) {
    showToast(`Tải ${label} thất bại: ${escapeHtml(String(res?.detail || 'không rõ lỗi'))}`, "error", 7000);
    return;
  }
  mergeServerSceneMedia({ scenes: [res.scene] }, scene.id);
  saveStateToLocal();
  renderSceneList();
  if (AppState.selectedSceneIndex === index) {
    renderPreviewPlayer();
  }
  showToast(`Đã tải ${label} cho Cảnh #${index + 1} lên máy chủ!`, "success");
}

function uploadCustomSceneImage(index, fileInput) {
  return uploadCustomSceneMedia(index, fileInput, 'image');
}

function uploadCustomSceneVideo(index, fileInput) {
  return uploadCustomSceneMedia(index, fileInput, 'video');
}

function setMediaViewMode(index, mode) {
  const project = AppState.currentProject;
  if (!project || !project.scenes || !project.scenes[index]) return;
  project.scenes[index].media_view_mode = mode;
  saveStateToLocal();
  renderSceneList();
  if (AppState.selectedSceneIndex === index) {
    renderPreviewPlayer();
  }
}

function resetSceneImageStatus(index) {
  const project = AppState.currentProject;
  if (!project || !project.scenes || !project.scenes[index]) return;
  project.scenes[index].status_image = 'idle';
  project.scenes[index].status_video = 'ready';
  saveStateToLocal();
  renderSceneList();
  showToast(`Đã xóa trạng thái kẹt cho Cảnh #${index + 1}`, "info");
}

// Cảnh đang được chọn ảnh/video từ Thư viện Muse (null: đang xem thư viện bình thường)
let museAttachSceneIndex = null;

function updateMuseAttachStrip() {
  const strip = document.getElementById('muse-attach-strip');
  const text = document.getElementById('muse-attach-strip-text');
  if (!strip || !text) return;
  strip.hidden = museAttachSceneIndex === null;
  if (museAttachSceneIndex !== null) {
    text.textContent = `Đang chọn ảnh cho cảnh ${String(museAttachSceneIndex + 1).padStart(3, '0')}. Bấm "Gắn Cảnh" trên ảnh hoặc video muốn dùng.`;
  }
}

function clearMuseAttachMode() {
  museAttachSceneIndex = null;
  updateMuseAttachStrip();
}

function openMuseModalForScene(index) {
  AppState.selectedSceneIndex = index;
  museAttachSceneIndex = index;
  showPage('gallery');
  showToast(`Đang mở Thư viện Muse cho Cảnh #${index + 1}. Bấm [📌 Gắn vào Cảnh #${index + 1}] để chọn!`, "info");
}

async function attachMediaToScene(index, mediaUrl, isVideo, outputPath = '') {
  const project = AppState.currentProject;
  if (!project || !project.scenes || !project.scenes[index]) return;
  const scene = project.scenes[index];

  if (isVideo) {
    scene.video_segment_url = mediaUrl;
    scene.video_url = mediaUrl;
    // Clip gốc lưu ở motion_video_path; video_segment_path là đoạn dựng, sẽ bị ghi lại khi render
    if (outputPath) scene.motion_video_path = outputPath;
    scene.media_view_mode = 'video';
    scene.status_video = 'ready';
    scene.status_image = 'idle';
  } else {
    scene.image_url = mediaUrl;
    if (outputPath) scene.image_path = outputPath;
    scene.media_view_mode = 'image';
    scene.status_image = 'ready';
  }

  // Lưu qua flushProjectSave (dùng buildServerPayload): gửi thẳng project sẽ bị máy chủ từ chối (422)
  // khi dự án có nhân vật tự sửa trong hộp "Khóa nhân vật".
  ProjectSync.dirty = true;
  const saved = AppState.serverOnline ? await flushProjectSave({ silent: true }) : false;
  if (saved) {
    showToast(`Đã gắn ${isVideo ? 'video' : 'ảnh'} vào Cảnh #${index + 1} và lưu lên máy chủ.`, "success");
  } else {
    showToast(`Đã gắn ${isVideo ? 'video' : 'ảnh'} vào Cảnh #${index + 1} nhưng CHƯA lưu được lên máy chủ. Bấm "Lưu" để thử lại.`, "warning", 7000);
  }
  renderSceneList();
  renderPreviewPlayer();
  showPage('scenes');
}

// Chạy lần lượt từng cảnh cho các nút "làm cả dự án": khoá nút khi đang chạy (bấm lại không chạy hai lượt),
// và báo đúng cảnh nào lỗi thay vì luôn báo hoàn tất. runOne(i) trả về số lỗi của cảnh i.
async function runSceneBatch(button, runOne, labels) {
  const project = AppState.currentProject;
  if (!project || !project.scenes || project.scenes.length === 0) return;
  if (button && button.dataset.busy === '1') {
    showToast(labels.busy, "info");
    return;
  }
  if (labels.confirm && !confirm(labels.confirm(project.scenes.length))) return;

  if (button) {
    button.dataset.busy = '1';
    button.disabled = true;
    button.style.opacity = '0.5';
  }
  showToast(labels.start, "info");
  const failed = [];
  try {
    for (let i = 0; i < project.scenes.length; i++) {
      if (AppState.currentProject !== project) break; // người dùng đã mở dự án khác
      if (await runOne(project.scenes[i], i)) failed.push(i + 1);
    }
  } finally {
    if (button) {
      delete button.dataset.busy;
      button.disabled = false;
      button.style.opacity = '';
    }
  }

  updateAssetReadiness();
  const total = project.scenes.length;
  if (failed.length) {
    showToast(`${labels.done}: lỗi ở cảnh ${failed.map(n => '#' + n).join(', ')} (${total - failed.length}/${total} cảnh ổn). Bấm nút trên từng cảnh lỗi để thử lại.`, "warning", 9000);
  } else {
    showToast(`${labels.done}: xong cả ${total} cảnh!`, "success");
  }
}

async function handleAutoGenAll() {
  await runSceneBatch(DOM.btnAutoGenAll, async (s, i) => {
    let errors = 0;
    if (!s.image_url || s.status_image !== 'ready') {
      if (await regenerateSceneImage(i) === false) errors++;
    }
    if ((!s.audio_url && !s.voice_audio_url) || s.status_voice !== 'ready') {
      if (await regenerateSceneVoice(i) === false) errors++;
    }
    return errors;
  }, {
    busy: "Auto-Gen đang chạy, chờ xong đã.",
    start: "Bắt đầu Auto-Gen Voice & Ảnh còn thiếu cho tất cả các cảnh...",
    done: "Auto-Gen toàn bộ dự án",
  });
}

async function handleRegenAllImages() {
  await runSceneBatch(DOM.btnRegenAllImages, async (s, i) => (await regenerateSceneImage(i) === false ? 1 : 0), {
    busy: "Đang vẽ lại toàn bộ ảnh, chờ xong đã.",
    confirm: n => `Vẽ lại ảnh cho cả ${n} cảnh? Ảnh hiện có sẽ bị thay (mỗi cảnh tốn 1 lượt tạo ảnh của nguồn ảnh đang chọn).`,
    start: "Đang vẽ lại toàn bộ ảnh AI theo phong cách mới...",
    done: "Vẽ lại toàn bộ ảnh AI",
  });
}

async function handleRegenAllVoices() {
  await runSceneBatch(DOM.btnRegenAllVoices, async (s, i) => (await regenerateSceneVoice(i) === false ? 1 : 0), {
    busy: "Đang thu lại toàn bộ voice, chờ xong đã.",
    confirm: n => `Thu âm lại giọng đọc cho cả ${n} cảnh? Giọng hiện có sẽ bị thay.`,
    start: "Đang thu âm lại toàn bộ Voice cho dự án...",
    done: "Thu âm lại toàn bộ Voice",
  });
}

// ================= UNIFIED AUDIO-VIDEO STUDIO PLAYER CONTROLLER =================
function togglePreviewPlayback() {
  if (AppState.isPlaying) {
    pausePlayback();
  } else {
    playCurrentScene();
  }
}

// fromStart: phát lại từ 0 giây (phát toàn bộ truyện). Mặc định phát tiếp từ chỗ đang dừng/đã tua.
function playCurrentScene({ fromStart = false } = {}) {
  const project = AppState.currentProject;
  if (!project || !project.scenes) return;

  const scene = project.scenes[AppState.selectedSceneIndex];
  if (!scene) return;

  AppState.isPlaying = true;
  updatePlayButtonIcon();

  const hasImage = Boolean(scene.image_url);
  const hasVideo = Boolean(scene.video_segment_url || scene.video_url);
  const isVideoMode = (scene.media_view_mode === 'video') || (!hasImage && hasVideo);
  const videoUrl = scene.video_segment_url || scene.video_url;
  const audioSrc = scene.audio_url || scene.voice_audio_url;

  // 1. Đồng bộ luồng phát Video Motion
  if (isVideoMode && videoUrl && DOM.previewVideoElem) {
    if (DOM.previewVideoElem.src !== videoUrl && !DOM.previewVideoElem.src.endsWith(videoUrl)) {
      DOM.previewVideoElem.src = videoUrl;
    }
    DOM.previewVideoElem.currentTime = 0;
    // Tôn trọng âm thanh video: Giữ âm thanh môi trường gốc (ambient sound: mưa, xe, bước chân) ở mức 25%, không tắt hẳn
    DOM.previewVideoElem.muted = false;
    DOM.previewVideoElem.volume = 0.25;
    DOM.previewVideoElem.play().catch(e => console.warn("Video play error", e));
    DOM.previewVideoElem.classList.remove('hidden');
    DOM.previewImageElem.classList.add('hidden');
    applyKenBurnsEffect('none');
  } else {
    if (DOM.previewVideoElem) {
      DOM.previewVideoElem.pause();
      DOM.previewVideoElem.classList.add('hidden');
    }
    if (scene.image_url) {
      DOM.previewImageElem.src = scene.image_url;
      DOM.previewImageElem.classList.remove('hidden');
      applyKenBurnsEffect(scene.camera_motion || scene.ken_burns || 'zoom_in');
    }
  }

  // 2. Đồng bộ luồng phát Voiceover Audio
  if (audioSrc) {
    const sameSrc = DOM.globalPreviewAudio.src === audioSrc || DOM.globalPreviewAudio.src.endsWith(audioSrc);
    if (!sameSrc) {
      DOM.globalPreviewAudio.src = audioSrc;
    }
    if (fromStart || !sameSrc || DOM.globalPreviewAudio.ended) {
      DOM.globalPreviewAudio.currentTime = 0;
    }
    DOM.globalPreviewAudio.play().catch(e => {
      console.warn("Audio play prevented:", e);
      showToast("Trình duyệt chặn tự động phát âm thanh. Vui lòng click tương tác.", "warning");
      fallbackTimer(scene.duration || 5);
    });
  } else if (!isVideoMode) {
    showToast(`Cảnh #${AppState.selectedSceneIndex + 1} chưa có voice. Hãy bấm nút 'Voice' để sinh âm thanh chuẩn!`, "warning");
    fallbackTimer(scene.duration || 5);
  } else {
    // Có video nhưng chưa có voice: dùng thời lượng video để đếm nhịp
    const dur = scene.duration || (DOM.previewVideoElem?.duration) || 5;
    fallbackTimer(dur);
  }
}

function fallbackTimer(duration) {
  const durMs = (duration || 5) * 1000;
  const startTime = Date.now();

  const interval = setInterval(() => {
    if (!AppState.isPlaying) {
      clearInterval(interval);
      return;
    }
    const elapsed = (Date.now() - startTime) / 1000;
    DOM.previewTimeDisplay.textContent = `${elapsed.toFixed(1)}s / ${(duration || 5).toFixed(1)}s`;

    const pct = (elapsed / duration) * 100;
    const bar = document.getElementById('preview-timeline-bar');
    if (bar) bar.style.width = `${Math.min(100, pct)}%`;

    if (elapsed >= duration) {
      clearInterval(interval);
      if (AppState.isPlayingAll) {
        onAudioPlaybackEnded();
      } else {
        pausePlayback();
      }
    }
  }, 100);
}

function pausePlayback() {
  AppState.isPlaying = false;
  AppState.isPlayingAll = false;
  if (AppState.playbackTimer) clearTimeout(AppState.playbackTimer);

  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }

  if (DOM.globalPreviewAudio) {
    DOM.globalPreviewAudio.pause();
  }
  if (DOM.previewVideoElem) {
    DOM.previewVideoElem.pause();
  }

  updatePlayButtonIcon();
  applyKenBurnsEffect('none');
}

function updatePlayButtonIcon() {
  const btn = DOM.btnPreviewPlayToggle;
  const icon = DOM.previewPlayIcon;
  if (!btn || !icon) return;

  if (AppState.isPlaying) {
    icon.className = "fa-solid fa-pause text-xl";
    btn.className = "absolute w-14 h-14 rounded-full bg-slate-900/75 hover:bg-slate-900 text-white flex items-center justify-center text-xl shadow-sm transition-all duration-300 opacity-0 hover:opacity-100 cursor-pointer z-20";
    btn.title = "Tạm dừng";
  } else {
    icon.className = "fa-solid fa-play ml-0.5 text-xl";
    btn.className = "absolute w-14 h-14 rounded-full bg-slate-900/90 hover:bg-slate-900 text-white flex items-center justify-center text-xl shadow-sm transition-all duration-300 opacity-90 hover:opacity-100 transform hover:scale-110 active:scale-95 cursor-pointer z-20";
    btn.title = "Phát Cảnh này";
  }
}

function onAudioTimeUpdate() {
  const audio = DOM.globalPreviewAudio;
  const video = DOM.previewVideoElem;
  const project = AppState.currentProject;
  const scene = project?.scenes?.[AppState.selectedSceneIndex];
  
  const hasAudio = audio && audio.src && !isNaN(audio.duration) && audio.duration > 0;
  const hasVid = video && video.src && !isNaN(video.duration) && video.duration > 0;
  const isVidMode = (scene?.media_view_mode === 'video');

  let current = 0;
  let total = scene?.duration || 5.0;

  if (hasAudio) {
    current = audio.currentTime;
    total = scene?.duration || audio.duration || total;
  } else if (isVidMode && hasVid) {
    current = video.currentTime;
    total = scene?.duration || video.duration || total;
  }

  DOM.previewTimeDisplay.textContent = `${current.toFixed(1)}s / ${total.toFixed(1)}s`;

  // Cập nhật thanh timeline trượt dưới Player
  const pct = total > 0 ? (current / total) * 100 : 0;
  const bar = document.getElementById('preview-timeline-bar');
  if (bar) bar.style.width = `${Math.min(100, pct)}%`;

  // Cập nhật thanh tiến độ trên thẻ phân cảnh
  const progressBar = document.getElementById(`scene-progress-${AppState.selectedSceneIndex}`);
  if (progressBar) {
    progressBar.style.width = `${Math.min(100, pct)}%`;
  }

  // Khóa đồng bộ nhịp hình ảnh (AV Lip-Sync Lock): Giữ video chạy khớp tuyệt đối với giọng đọc
  if (isVidMode && hasVid && hasAudio && !video.paused && !audio.paused && video.duration) {
    const targetVidTime = current % video.duration;
    if (Math.abs(video.currentTime - targetVidTime) > 0.35) {
      video.currentTime = targetVidTime;
    }
  }
}

function onAudioPlaybackEnded() {
  if (AppState.isPlayingAll) {
    // Tự động chuyển tiếp mượt mà sang cảnh kế tiếp
    const project = AppState.currentProject;
    if (project && AppState.selectedSceneIndex < project.scenes.length - 1) {
      selectScene(AppState.selectedSceneIndex + 1);
      setTimeout(() => {
        playCurrentScene({ fromStart: true });
        AppState.isPlayingAll = true;
      }, 300);
      return;
    }
  }

  pausePlayback();
  if (DOM.globalPreviewAudio) DOM.globalPreviewAudio.currentTime = 0;
  if (DOM.previewVideoElem) DOM.previewVideoElem.currentTime = 0;
  onAudioTimeUpdate();
}

function seekStudioPlayback(event) {
  const container = document.getElementById('preview-timeline-container');
  if (!container) return;
  const rect = container.getBoundingClientRect();
  const clickX = event.clientX - rect.left;
  const pct = Math.max(0, Math.min(1, clickX / rect.width));

  const audio = DOM.globalPreviewAudio;
  const video = DOM.previewVideoElem;
  const project = AppState.currentProject;
  const scene = project?.scenes?.[AppState.selectedSceneIndex];
  const total = (audio && audio.duration) || (video && video.duration) || scene?.duration || 5.0;
  const targetTime = pct * total;

  if (audio && audio.src && audio.duration) {
    audio.currentTime = Math.min(targetTime, audio.duration);
  }
  if (video && video.src && video.duration) {
    video.currentTime = targetTime % video.duration;
  }

  onAudioTimeUpdate();
}
window.seekStudioPlayback = seekStudioPlayback;

function prevScene() {
  if (AppState.selectedSceneIndex > 0) {
    selectScene(AppState.selectedSceneIndex - 1);
  }
}

function nextScene() {
  const project = AppState.currentProject;
  if (project && AppState.selectedSceneIndex < project.scenes.length - 1) {
    selectScene(AppState.selectedSceneIndex + 1);
  }
}

function togglePlayAllStory() {
  if (AppState.isPlaying && AppState.isPlayingAll) {
    pausePlayback();
    showToast("Đã dừng phát toàn bộ truyện", "info");
  } else {
    AppState.selectedSceneIndex = 0;
    selectScene(0);
    AppState.isPlayingAll = true;
    playCurrentScene({ fromStart: true });
    showToast("Đang phát toàn bộ kịch bản truyện từ Cảnh #1...", "info");
  }
}

function playSceneVoice(idx) {
  selectScene(idx);
  playCurrentScene();
}

let isVoiceSamplePlaying = false;

function resetVoiceSampleButtonState() {
  isVoiceSamplePlaying = false;
  if (DOM.iconPreviewVoice) DOM.iconPreviewVoice.className = "fa-solid fa-volume-high text-slate-700 text-xs";
  if (DOM.textPreviewVoice) DOM.textPreviewVoice.textContent = "Nghe thử";
  if (DOM.btnPreviewVoiceSample) {
    DOM.btnPreviewVoiceSample.classList.remove("bg-slate-900", "text-white");
    DOM.btnPreviewVoiceSample.classList.add("bg-slate-50", "text-slate-700");
  }
}

async function togglePlayVoiceSample() {
  const audio = DOM.voiceSampleAudio;
  const voiceId = DOM.selectVoice?.value || "vi-VN-NamMinhNeural";
  if (!audio) return;

  if (isVoiceSamplePlaying && !audio.paused) {
    audio.pause();
    audio.currentTime = 0;
    resetVoiceSampleButtonState();
    return;
  }

  // Set loading state
  if (DOM.iconPreviewVoice) DOM.iconPreviewVoice.className = "fa-solid fa-spinner fa-spin text-xs";
  if (DOM.textPreviewVoice) DOM.textPreviewVoice.textContent = "Đang tải...";

  try {
    const sampleUrl = `/api/voices/${encodeURIComponent(voiceId)}/sample`;
    audio.src = sampleUrl;

    audio.onended = () => {
      resetVoiceSampleButtonState();
    };
    audio.onerror = () => {
      resetVoiceSampleButtonState();
      showToast("Không thể tải mẫu âm thanh cho giọng đọc này.", "error");
    };

    await audio.play();
    isVoiceSamplePlaying = true;
    if (DOM.iconPreviewVoice) DOM.iconPreviewVoice.className = "fa-solid fa-pause text-xs";
    if (DOM.textPreviewVoice) DOM.textPreviewVoice.textContent = "Tạm dừng";
    if (DOM.btnPreviewVoiceSample) {
      DOM.btnPreviewVoiceSample.classList.remove("bg-slate-50", "text-slate-700");
      DOM.btnPreviewVoiceSample.classList.add("bg-slate-900", "text-white");
    }
  } catch (err) {
    console.error("Play voice sample failed", err);
    resetVoiceSampleButtonState();
    showToast("Lỗi nghe thử giọng: " + escapeHtml(err.message || err), "error");
  }
}

// Bấm vào thanh tiến độ trên thẻ cảnh: chọn cảnh rồi tua giọng đọc tới đúng vị trí bấm
function seekSceneAudio(idx, event) {
  const bar = event?.currentTarget;
  const rect = bar?.getBoundingClientRect?.();
  const pct = rect && rect.width ? Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) : 0;
  selectScene(idx);

  const scene = AppState.currentProject?.scenes?.[idx];
  const audio = DOM.globalPreviewAudio;
  const src = scene && (scene.audio_url || scene.voice_audio_url);
  if (!audio || !src) {
    showToast(`Cảnh #${idx + 1} chưa có giọng đọc để tua.`, "info");
    return;
  }
  const seek = () => {
    if (!audio.duration || isNaN(audio.duration)) return;
    audio.currentTime = pct * audio.duration;
    onAudioTimeUpdate();
  };
  if (audio.src !== src && !audio.src.endsWith(src)) {
    audio.addEventListener('loadedmetadata', seek, { once: true });
    audio.src = src;
  } else if (audio.readyState >= 1) {
    seek();
  } else {
    audio.addEventListener('loadedmetadata', seek, { once: true });
  }
}

// Thêm các bản nhạc nền đã tải lên (custom_*) vào ô chọn nhạc, rồi chọn lại nhạc của dự án đang mở
async function loadBgmOptions() {
  const sel = DOM.selectBgm;
  if (!sel) return;
  let tracks = [];
  try {
    const res = await fetch(`${API.baseUrl}/bgm-tracks`);
    if (res.ok) tracks = await res.json();
  } catch (e) {
    return;
  }
  const have = new Set([...sel.options].map(o => o.value));
  const before = sel.querySelector('option[value="none"]');
  (Array.isArray(tracks) ? tracks : []).forEach(t => {
    const id = String(t?.id || '');
    if (!/^custom_[A-Za-z0-9_-]+$/.test(id) || have.has(id)) return;
    const label = String(t.name || id).replace(/^custom\s+/i, '').replace(/\s+[0-9a-f]{6}$/i, '');
    sel.insertBefore(new Option(`🎵 Nhạc tải lên: ${label}`, id), before);
    have.add(id);
  });
  const project = AppState.currentProject;
  const wanted = project?.settings?.bgm || project?.bgm_track;
  if (wanted && have.has(wanted)) sel.value = wanted;
}

async function handleBgmUpload(e) {
  const file = e.target.files?.[0];
  e.target.value = '';
  if (!file) return;
  const project = AppState.currentProject;
  if (!project || project.is_demo) {
    showToast("Hãy mở hoặc tạo một dự án trước khi tải nhạc nền.", "warning");
    return;
  }
  if (!/\.mp3$/i.test(file.name)) {
    showToast("Chỉ nhận file nhạc .mp3.", "warning");
    return;
  }
  if (!AppState.serverOnline) {
    showToast("Máy chủ đang offline nên chưa tải nhạc nền lên được.", "error", 6000);
    return;
  }
  showToast(`Đang tải nhạc nền "${escapeHtml(file.name)}" lên...`, "info");
  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${API.baseUrl}/bgm-tracks/upload`, { method: 'POST', body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.id) throw new Error(data.detail || `HTTP ${res.status}`);
    await loadBgmOptions();
    DOM.selectBgm.value = data.id;
    DOM.selectBgm.dispatchEvent(new Event('change', { bubbles: true }));
    showToast(`Đã tải lên và chọn nhạc nền "${escapeHtml(file.name)}" cho dự án.`, "success");
  } catch (err) {
    showToast(`Tải nhạc nền thất bại: ${escapeHtml(String(err.message || err))}`, "error", 7000);
  }
}

function togglePlayerFullscreen() {
  const box = DOM.previewCanvasBox;
  if (!box) return;

  if (!document.fullscreenElement) {
    box.requestFullscreen().catch(err => {
      console.warn("Fullscreen request error", err);
      showToast("Trình duyệt này không cho phóng to toàn màn hình. Mở Story Studio bằng Chrome/Edge rồi bấm lại.", "warning", 6000);
    });
  } else {
    document.exitFullscreen();
  }
}

// ================= TRUYỆN TRANH: ẢNH MẪU CỦA TRANG Ý TƯỞNG =================
async function loadComicSample(type) {
  try {
    const sampleUrl = type === 'strip' 
      ? '/static/test_comic/test_strip.jpg' 
      : '/static/test_comic/test_grid.jpg';

    const res = await fetch(sampleUrl);
    if (!res.ok) throw new Error("Không thể tải ảnh mẫu");
    const blob = await res.blob();
    const filename = type === 'strip' ? 'sample_webtoon_strip.jpg' : 'sample_manga_grid.jpg';
    const file = new File([blob], filename, { type: 'image/jpeg' });

    // Cập nhật ô chế độ và nút "Cắt khung" của trang Ý tưởng
    if (DOM.step1ComicMode) DOM.step1ComicMode.value = type === 'strip' ? 'strip' : 'grid';
    handleStep1ComicFileSelect(file);
    showToast(`Đã nạp ảnh mẫu: ${escapeHtml(filename)}`, "info");
  } catch (err) {
    console.error("loadComicSample failed", err);
    showToast("Không tìm thấy file ảnh mẫu trên máy chủ", "warning");
  }
}

// ================= ĐIỀU HƯỚNG: BƯỚC CŨ 1–4 → TRANG (workspace.js) =================
// Giữ tên cho mọi chỗ gọi cũ; ẩn hiện theo trang, không còn đổi lớp từng khối bước.
const STEP_TO_PAGE = { 1: 'idea', 2: 'scenes', 3: 'publish', 4: 'publish' };

function switchStep(stepNumber) {
  AppState.currentStep = stepNumber;
  showPage(STEP_TO_PAGE[stepNumber]);
  // Bước 3 và 4 chung trang Dựng và xuất bản (bước 3 ở trên): bước 4 cuộn tới khối Rạp chiếu
  if (stepNumber === 4) {
    document.getElementById('step-view-4')?.scrollIntoView({ block: 'start' });
  }
}

// Vào trang Dựng và xuất bản thì nạp video thành phẩm và gói YouTube (trước đây switchStep(4) gọi thẳng)
onPageShow('publish', loadCinemaYouTubePackage);

async function loadCinemaYouTubePackage() {
  const project = AppState.currentProject;
  if (!project) return;

  renderFinalVideoBlock(project);

  const thumbUrl = `/api/projects/${project.id}/thumbnail?t=${Date.now()}`;
  if (DOM.cinemaThumbnailPreview) {
    DOM.cinemaThumbnailPreview.src = thumbUrl;
    DOM.cinemaThumbnailPreview.onerror = () => {
      DOM.cinemaThumbnailPreview.src = '/static/demo_images/scene_1.jpg';
    };
  }
  if (DOM.btnCinemaDownloadThumbnail) {
    DOM.btnCinemaDownloadThumbnail.href = `/api/projects/${project.id}/thumbnail`;
  }

  // Gói SEO YouTube: xử lý trong /static/youtube_seo.js
  if (AppState.serverOnline && typeof window.ytSeoLoad === 'function') {
    await window.ytSeoLoad(project);
  }
}

async function handleGenerateCustomThumbnail() {
  const project = AppState.currentProject;
  if (!project) return;

  const h1 = DOM.inputThumbHeadline?.value.trim() || undefined;
  const h2 = DOM.inputThumbSubtext?.value.trim() || undefined;

  if (DOM.btnGenerateCustomThumbnail) {
    DOM.btnGenerateCustomThumbnail.disabled = true;
    DOM.btnGenerateCustomThumbnail.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i> Đang tạo...';
  }

  try {
    const res = await API.generateThumbnail(project.id, {
      custom_headline: h1,
      custom_subtext: h2,
    });
    if (res && res.success) {
      if (DOM.cinemaThumbnailPreview) {
        DOM.cinemaThumbnailPreview.src = `/api/projects/${project.id}/thumbnail?t=${Date.now()}`;
      }
      showToast("Đã tạo mới Thumbnail YouTube 1080p!", "success");
    } else {
      showToast("Không tạo được Thumbnail: " + escapeHtml(res?.detail || "lỗi không rõ"), "error", 8000);
    }
  } catch (err) {
    showToast("Lỗi tạo Thumbnail: " + escapeHtml(err.message || err), "error");
  } finally {
    if (DOM.btnGenerateCustomThumbnail) {
      DOM.btnGenerateCustomThumbnail.disabled = false;
      DOM.btnGenerateCustomThumbnail.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles mr-1"></i> Tạo lại Thumbnail';
    }
  }
}

function copyToClipboard(elemId, toastMsg) {
  const el = document.getElementById(elemId);
  if (el) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(el.value).then(() => {
        showToast(toastMsg || "Đã sao chép vào bộ nhớ tạm!", "success");
      }).catch(() => {
        el.select();
        document.execCommand('copy');
        showToast(toastMsg || "Đã sao chép!", "success");
      });
    } else {
      el.select();
      document.execCommand('copy');
      showToast(toastMsg || "Đã sao chép!", "success");
    }
  }
}
window.copyToClipboard = copyToClipboard;

// STEP 1 HANDLERS
function handleStep1ScriptInput() {
  const text = DOM.step1ScriptTextarea?.value.trim() || '';
  const wordCount = text ? text.split(/\s+/).filter(Boolean).length : 0;
  if (DOM.step1WordCount) {
    DOM.step1WordCount.textContent = `${wordCount} từ`;
  }
}

// Bước 1 là lối vào chung (luồng chung truyện chữ và vụ án, 03/11/2026): chỉ khác bước nội dung. Truyện chữ: AI kể
// kiểu review (story_review). Vụ án: gửi bài sang luồng phân tích vụ án (true_crime.js) để duyệt dàn ý và bảng tên.
const STEP1_PROCESS_LABELS = {
  story: '⚡ Tạo dự án review truyện',
  case: '🕵️ Gửi vụ án cho AI phân tích',
};

function step1ContentKind() {
  return DOM.step1ContentKind?.value === 'case' ? 'case' : 'story';
}

function step1IdleButtonHtml() {
  return '<i class="fa-solid fa-bolt-lightning text-amber-300 mr-1.5 animate-bounce"></i> <span id="step1-process-label">'
    + escapeHtml(STEP1_PROCESS_LABELS[step1ContentKind()]) + '</span> <i class="fa-solid fa-arrow-right ml-1"></i>';
}

function applyStep1ContentKind() {
  const kind = step1ContentKind();
  document.querySelectorAll('[data-step1-kind]').forEach(node => {
    node.classList.toggle('hidden', node.dataset.step1Kind !== kind);
  });
  const label = document.getElementById('step1-process-label');
  if (label) label.textContent = STEP1_PROCESS_LABELS[kind];
  if (DOM.step1ScriptTextarea) {
    DOM.step1ScriptTextarea.placeholder = kind === 'case'
      ? 'Dán toàn bộ bài viết về vụ án có thật (tối đa 200.000 ký tự). AI đọc từng đoạn, lập dàn ý để bạn duyệt, rồi viết lại và đổi tên người, nơi chốn.'
      : 'Dán nội dung truyện chữ (light novel, tiếng Việt, tiếng Anh hoặc tiếng Trung). AI kể lại kiểu review từng phần và kiểm đủ ý.';
  }
}

async function handleStep1ProcessScript() {
  if (step1ContentKind() === 'case') {
    const caseText = DOM.step1ScriptTextarea?.value.trim();
    if (!caseText) {
      showToast("Hãy dán bài viết về vụ án trước.", "warning");
      return;
    }
    if (typeof window.tcStartFromStep1 !== 'function') {
      showToast("Chưa nạp được phần vụ án (true_crime.js). Hãy tải lại trang.", "error", 7000);
      return;
    }
    await window.tcStartFromStep1({
      text: caseText,
      minutes: parseInt(DOM.step1CaseDuration?.value || '20', 10),
      style: DOM.step1StyleSelect?.value || 'horror_cartoon_2d',
    });
    return;
  }

  const text = DOM.step1ScriptTextarea?.value.trim();
  if (!text) {
    showToast("Vui lòng nhập hoặc chọn kịch bản mẫu trước!", "warning");
    return;
  }

  const pacing = DOM.step1PacingSelect?.value || 'fast';
  const style = DOM.step1StyleSelect?.value || 'horror_cartoon_2d';
  const imageProvider = DOM.step1EngineSelect?.value || DOM.selectImageProvider?.value || 'meta_muse_cloud';

  const isEnglish = !(/[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]/i.test(text));
  // Ngôn ngữ lời review (CLAUDE.md mục 1.2 câu 15): rỗng = theo ngôn ngữ truyện
  const outputLanguage = DOM.step1LanguageSelect?.value || '';
  const reviewEnglish = outputLanguage ? outputLanguage === 'en' : isEnglish;
  const selectedVoice = DOM.selectVoice?.value;
  const voiceFits = selectedVoice && (reviewEnglish ? selectedVoice.startsWith('en-') : !selectedVoice.startsWith('en-'));
  const autoVoice = voiceFits ? selectedVoice : (reviewEnglish ? "en-US-AndrewMultilingualNeural" : "vi-VN-NamMinhNeural");
  // Server viết và kiểm từng phần (có thể vài chục phút): hỏi tiến độ để hiện lên nút
  const progressId = 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  let progressTimer = null;

  DOM.btnStep1ProcessScript.disabled = true;
  DOM.btnStep1ProcessScript.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Đang viết lời review và kiểm đủ ý...';

  try {
    let createdProject = null;
    if (AppState.serverOnline) {
      progressTimer = setInterval(async () => {
        try {
          const r = await fetch(`${API.baseUrl}/projects/create-from-script/progress/${progressId}`);
          const d = r.ok ? await r.json() : null;
          if (d && d.progress && DOM.btnStep1ProcessScript) {
            DOM.btnStep1ProcessScript.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> ' + escapeHtml(d.progress);
          }
        } catch (e) { /* hỏi tiến độ lỗi thì lần sau hỏi lại; việc chính vẫn chạy */ }
      }, 3000);
      createdProject = await API.createProjectFromScript({
        name: text.split('\n')[0].substring(0, 45).trim() || "Câu Chuyện Mới",
        text: text,
        pacing: pacing,
        style_preset: style,
        voice: autoVoice,
        image_provider: imageProvider,
        // Làm từng bước (CLAUDE.md mục 1.2 câu 4): ảnh cảnh tạo sau khi khoá nhân vật và bối cảnh
        generate_initial_images: false,
        output_language: outputLanguage || undefined,
        progress_id: progressId
      });
    }

    if (createdProject && Array.isArray(createdProject.scenes) && createdProject.scenes.length > 0) {
      AppState.currentProject = adoptServerProject(createdProject);
      saveStateToLocal();
      renderFullUI();
      selectScene(0);
      switchStep(2);
      const total = createdProject.scenes.length;
      const castInfo = createdProject.metadata?.story_cast || {};
      if (castInfo.error) {
        showToast(`Đã tạo ${total} cảnh, nhưng chưa tìm được nhân vật: ${escapeHtml(castInfo.error)}. Mở nút "Nhân vật" để tìm lại trước khi tạo ảnh.`, "warning", 10000);
      } else {
        showToast(`Đã tạo ${total} cảnh và tìm được ${castInfo.people || 0} nhân vật. Bước tiếp: duyệt "Nhân vật" và "Bối cảnh", rồi mới tạo ảnh cảnh.`, "success", 9000);
      }
    } else if (!AppState.serverOnline) {
      showToast("Máy chủ đang offline nên chưa tạo được dự án. Hãy chạy run.bat rồi thử lại.", "error", 7000);
    } else {
      showToast("Máy chủ không trả về phân cảnh nào cho kịch bản này. Hãy kiểm tra nội dung rồi thử lại.", "error", 7000);
    }
  } catch (err) {
    console.error("handleStep1ProcessScript error", err);
    showToast("Lỗi phân tích kịch bản: " + escapeHtml(err.message || err), "error");
  } finally {
    if (progressTimer) clearInterval(progressTimer);
    if (DOM.btnStep1ProcessScript) {
      DOM.btnStep1ProcessScript.disabled = false;
      DOM.btnStep1ProcessScript.innerHTML = step1IdleButtonHtml();
    }
  }
}

function handleStep1ComicFileSelect(file) {
  if (!file) return;
  AppState.comicState.selectedFile = file;
  if (DOM.step1ComicFileName) {
    DOM.step1ComicFileName.textContent = `📁 ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
    DOM.step1ComicFileName.classList.remove('hidden');
  }
  if (DOM.btnStep1ProcessComic) {
    DOM.btnStep1ProcessComic.disabled = false;
  }
}

async function handleStep1ProcessComic() {
  const file = AppState.comicState.selectedFile;
  if (!file) {
    showToast("Vui lòng chọn hoặc kéo thả ảnh truyện tranh trước!", "warning");
    return;
  }

  const mode = DOM.step1ComicMode?.value || 'grid';
  const order = DOM.step1ComicOrder?.value || 'rtl';
  if (!AppState.serverOnline) {
    showToast("Máy chủ đang offline nên chưa cắt được truyện tranh.", "error", 6000);
    return;
  }

  DOM.btnStep1ProcessComic.disabled = true;
  DOM.btnStep1ProcessComic.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Đang bóc tách khung tranh OpenCV...';

  try {
    // Bước 1 = bắt đầu video mới: tạo dự án mới cho truyện tranh, không ghi đè cảnh của dự án đang mở
    if (!(await flushProjectSave())) throw new Error("chưa lưu được dự án đang mở lên máy chủ");
    const baseName = (file.name || '').replace(/\.[^.]+$/, '').trim() || 'Truyện tranh mới';
    const project = await API.createProject(`Truyện tranh: ${baseName}`.slice(0, 60));
    if (!project || !project.id) throw new Error("không tạo được dự án mới trên máy chủ");
    AppState.currentProject = adoptServerProject(project);
    rememberLastProjectId(project.id);
    AppState.projectsList.push({ id: project.id, name: project.name, scenes_count: 0 });

    const result = await API.sliceComic(file, mode, order, 0.03, project.id);
    if (!result || !result.success) {
      throw new Error(result?.error || "Không thể cắt ảnh");
    }

    // Import panels into storyboard
    const importRes = await API.importComicPanels(project.id, result.panels, true, "Khung tranh");
    if (!importRes || !importRes.project) {
      throw new Error(importRes?.detail || "chưa nhập được khung tranh vào dự án mới");
    }
    AppState.currentProject = adoptServerProject(importRes.project);
    rememberLastProjectId(importRes.project.id);

    renderFullUI();
    selectScene(0);
    switchStep(2);
    if (importRes?.failed_panels > 0) {
      showToast(`Đã nhập ${result.total_panels} khung tranh, nhưng ${importRes.failed_panels} khung không chép được ảnh (đánh dấu "Lỗi ảnh").`, "warning", 8000);
    } else {
      showToast(`Đã bóc tách & nhập ${result.total_panels} khung tranh vào Bảng Đạo Diễn!`, "success", 4500);
    }
  } catch (err) {
    console.error("handleStep1ProcessComic error", err);
    showToast("Lỗi cắt ảnh truyện tranh: " + escapeHtml(err.message || err), "error");
  } finally {
    if (DOM.btnStep1ProcessComic) {
      DOM.btnStep1ProcessComic.disabled = false;
      DOM.btnStep1ProcessComic.innerHTML = '<i class="fa-solid fa-scissors mr-1.5"></i> <span>Cắt Khung Tranh & Sang Bước 2 (Bảng Đạo Diễn)</span> <i class="fa-solid fa-arrow-right ml-1"></i>';
    }
  }
}

// Video thành phẩm của một dự án: lần dựng vừa xong trong phiên này (đúng dự án), hoặc video máy chủ đã ghi vào dự án.
// Không có thì trả null: trang Dựng không được trỏ trình phát vào story_final.mp4 khi file chưa có (đường cấm 3).
function finalVideoOf(project) {
  if (!project) return null;
  const ps = AppState.produceState;
  if (ps.projectId === project.id && ps.videoUrl) {
    return { videoUrl: ps.videoUrl, srtUrl: ps.srtUrl || `/api/projects/${project.id}/download-srt`, draft: !!ps.draft };
  }
  const videoUrl = project.final_video_url
    || (project.final_video_path ? `/api/projects/${project.id}/media/renders/story_final.mp4` : null);
  return videoUrl ? { videoUrl, srtUrl: `/api/projects/${project.id}/download-srt`, draft: false } : null;
}

// Khối video thành phẩm (tiêu đề, trình phát, nút tải) chỉ hiện khi dự án có video; chưa có thì một dòng "Chưa có video thành phẩm"
function renderFinalVideoBlock(project) {
  const box = document.getElementById('publish-final-video');
  const none = document.getElementById('publish-no-video');
  const found = finalVideoOf(project);
  if (box) box.hidden = !found;
  if (none) none.hidden = !!found;
  if (!found) {
    if (DOM.cinemaVideoPlayer && DOM.cinemaVideoPlayer.getAttribute('src')) {
      DOM.cinemaVideoPlayer.pause();
      DOM.cinemaVideoPlayer.removeAttribute('src');
      DOM.cinemaVideoPlayer.load();
    }
    return;
  }
  // Bản nháp (dưới mức video Muse) ra file riêng, không phải video cuối: ghi rõ trên tiêu đề
  const title = document.getElementById('publish-final-title');
  if (title) title.textContent = found.draft ? 'Bản nháp (không phải thành phẩm)' : 'Video thành phẩm';
  if (DOM.cinemaVideoPlayer && DOM.cinemaVideoPlayer.getAttribute('src') !== found.videoUrl) {
    DOM.cinemaVideoPlayer.src = found.videoUrl;
  }
  if (DOM.btnCinemaDownloadVideo) DOM.btnCinemaDownloadVideo.href = `/api/projects/${project.id}/download`;
  if (DOM.btnCinemaDownloadSrt) DOM.btnCinemaDownloadSrt.href = found.srtUrl;
  if (DOM.btnCinemaDownloadAss) DOM.btnCinemaDownloadAss.href = `/api/projects/${project.id}/download-ass`;
}

// Khối tiến độ dựng về trạng thái chưa dựng: không vòng quay, 0%, năm giai đoạn trung tính
const PRODUCER_STATUS_CLASS = 'text-sm font-bold text-slate-800 flex items-center gap-2';
function resetProducerUI() {
  updateProducerStageUI(0, 0, 'Chưa dựng', []);
  if (DOM.producerStatusText) DOM.producerStatusText.className = PRODUCER_STATUS_CLASS;
  if (DOM.producerLogConsole) DOM.producerLogConsole.textContent = '> Chưa dựng lần nào trong phiên này.';
  if (DOM.producerTimerText) DOM.producerTimerText.textContent = '00:00';
}

// Vẽ khối tiến độ và khối video theo dự án đang mở (renderFullUI() gọi mỗi lần đổi, tạo hay nạp dự án).
// Lần dựng đang chạy của dự án khác không bị ngắt: tiến độ vẫn ghi vào AppState.produceState, mở lại đúng dự án thì vẽ lại.
function paintProducerForCurrentProject() {
  const project = AppState.currentProject;
  const ps = AppState.produceState;
  if (project && ps.projectId === project.id && (ps.isProducing || ps.progress > 0)) {
    updateProducerStageUI(ps.step, ps.progress, ps.statusMsg || 'Đang xử lý...', ps.logs);
    if (ps.failed && DOM.producerStatusText) {
      DOM.producerStatusText.textContent = `Thất bại: ${ps.failed}`;
      DOM.producerStatusText.className = "text-xs font-bold text-red-600 truncate";
    }
  } else {
    resetProducerUI();
  }
  renderFinalVideoBlock(project);
}

// STEP 3: PRODUCTION STEPPER EXECUTION
function updateProducerStageUI(stepNum, progressPercent, statusMsg, logs = []) {
  // Update phase indicators (1 to 5)
  for (let s = 1; s <= 5; s++) {
    const box = document.getElementById(`producer-step-${s}`);
    const icon = document.getElementById(`producer-step-icon-${s}`);
    if (box && icon) {
      if (s < stepNum) {
        // Completed phase
        box.className = "p-3 rounded-2xl border border-emerald-200 bg-emerald-50/60 transition shadow-2xs font-semibold text-emerald-800";
        icon.className = "w-7 h-7 rounded-full bg-emerald-600 text-white flex items-center justify-center mx-auto mb-1.5 text-xs font-bold";
        icon.innerHTML = '<i class="fa-solid fa-check text-[10px]"></i>';
      } else if (s === stepNum) {
        // Active phase
        box.className = "p-3 rounded-2xl border-2 border-slate-700 bg-slate-50/70 transition shadow-md font-bold text-slate-950 ring-2 ring-slate-700/20";
        icon.className = "w-7 h-7 rounded-full bg-slate-900 text-white flex items-center justify-center mx-auto mb-1.5 text-xs font-bold animate-pulse";
        icon.textContent = s;
      } else {
        // Pending phase
        box.className = "p-3 rounded-2xl border border-slate-200 bg-white transition shadow-2xs font-semibold text-slate-500";
        icon.className = "w-7 h-7 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center mx-auto mb-1.5 text-xs font-bold";
        icon.textContent = s;
      }
    }
  }

  // Update status text and progress bar
  if (DOM.producerStatusText) {
    if (stepNum === 0) {
      DOM.producerStatusText.textContent = statusMsg;   // chưa dựng: không vòng quay
    } else {
      DOM.producerStatusText.innerHTML = `<i class="fa-solid ${progressPercent >= 100 ? 'fa-circle-check text-emerald-600' : 'fa-spinner fa-spin text-slate-700'} mr-1.5"></i> <span>${statusMsg}</span>`;
    }
  }
  if (DOM.producerPercentText) {
    DOM.producerPercentText.textContent = `${progressPercent}%`;
  }
  if (DOM.producerProgressBar) {
    DOM.producerProgressBar.style.width = `${progressPercent}%`;
  }

  // Append new logs and scroll to bottom
  if (DOM.producerLogConsole && logs && logs.length > 0) {
    DOM.producerLogConsole.innerHTML = logs.map(l => `<div>> ${escapeHtml(l)}</div>`).join('');
    DOM.producerLogConsole.scrollTop = DOM.producerLogConsole.scrollHeight;
  }
}

async function startProduceLongVideo(opts) {
  // Nút gắn bằng addEventListener truyền sự kiện click vào đây: chỉ coi là bản nháp khi gọi rõ { draft: true }
  const draft = Boolean(opts && opts.draft === true);
  const project = AppState.currentProject;
  if (!project || !project.scenes || project.scenes.length === 0) {
    showToast("Vui lòng nhập kịch bản hoặc ảnh truyện tranh ở Bước 1 trước!", "warning");
    switchStep(1);
    return;
  }
  if (project.is_demo) {
    showToast("Đây là dự án mẫu (chỉ để xem). Hãy tạo dự án từ kịch bản ở Bước 1 rồi mới sản xuất video.", "warning", 7000);
    return;
  }

  // Máy chủ dựng từ bản trên server: lưu mọi chỉnh sửa trước khi bắt đầu
  ProjectSync.dirty = true;
  if (!(await flushProjectSave())) {
    showToast("Chưa lưu được dự án lên máy chủ nên chưa thể sản xuất video.", "error", 7000);
    return;
  }

  // Switch to Step 3 immediately
  switchStep(3);

  // Reset produce state (gắn với dự án đang dựng)
  AppState.produceState.projectId = project.id;
  AppState.produceState.renderId = null;
  AppState.produceState.videoUrl = null;
  AppState.produceState.srtUrl = null;
  AppState.produceState.failed = null;
  AppState.produceState.draft = draft;
  AppState.produceState.statusMsg = "Bước 1/5: Phân tích kịch bản & Khóa đặc điểm nhân vật đồng bộ...";
  AppState.produceState.isProducing = true;
  AppState.produceState.progress = 5;
  AppState.produceState.step = 1;
  AppState.produceState.logs = ["Bắt đầu quy trình sản xuất Video Dài (MoneyPrinterTurbo Stepper Pipeline)..."];
  AppState.produceState.startTime = Date.now();

  // Start timer
  if (AppState.produceState.timerInterval) clearInterval(AppState.produceState.timerInterval);
  AppState.produceState.timerInterval = setInterval(() => {
    if (!AppState.produceState.isProducing) {
      clearInterval(AppState.produceState.timerInterval);
      return;
    }
    if (AppState.currentProject?.id !== AppState.produceState.projectId) return;
    const elapsedSecs = Math.floor((Date.now() - AppState.produceState.startTime) / 1000);
    const m = Math.floor(elapsedSecs / 60);
    const s = elapsedSecs % 60;
    if (DOM.producerTimerText) {
      DOM.producerTimerText.textContent = `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
    }
  }, 1000);

  updateProducerStageUI(1, 5, "Bước 1/5: Phân tích kịch bản & Khóa đặc điểm nhân vật đồng bộ...", AppState.produceState.logs);

  try {
    const produceReq = {
      pacing: "fast",
      style_preset: DOM.selectProjectStyle?.value || project.style_preset || DEFAULT_STYLE_PRESET,
      image_provider: DOM.selectImageProvider?.value || project.image_provider || "meta_muse_cloud",
      character_anchor: project.character_anchor || (project.character?.prompt || ""),
      character_reference_image: project.character_reference_image || project.character?.reference_image || undefined,
      voice: DOM.selectVoice?.value || project.settings?.voice || project.voice || "vi-VN-NamMinhNeural",
      bgm: DOM.selectBgm?.value || project.settings?.bgm || "cinematic_adventure",
      ducking: DOM.toggleAudioDucking ? DOM.toggleAudioDucking.checked : true,
      hardsub: DOM.toggleHardsub ? DOM.toggleHardsub.checked : true,
      transition: DOM.selectTransition?.value || project.transition || "dip_to_black",
      subtitle_style: DOM.selectSubtitleStyle?.value || project.subtitle_style || "kinetic_pop",
      resolution: "1080p",
      fps: 25,
      draft,
      // Không gửi camera_motion chung: mỗi cảnh dùng chuyển động riêng (máy chủ lấy scene.camera_motion, không có thì
      // project.default_motion). Gặp 03/11/2026: gửi "zoom_in" chung đè hết, cả video chỉ một kiểu chuyển động.
    };

    const res = await API.produceLongVideo(project.id, produceReq);
    if (!res || !res.success) {
      throw new Error(res?.detail || "Khởi chạy sản xuất thất bại");
    }

    const renderId = res.render_id;
    AppState.produceState.renderId = renderId;

    // WebSocket / Polling progress listener
    listenToProduceProgress(renderId);

  } catch (err) {
    if (err && err.shareLow) {
      // Bị chốt tỉ lệ video Muse chặn trước khi dựng: không có gì chạy. Hỏi có dựng bản nháp (không phải thành phẩm) không.
      AppState.produceState.isProducing = false;
      AppState.produceState.progress = 0;
      AppState.produceState.statusMsg = 'Chưa dựng: tỉ lệ video Muse chưa đủ';
      AppState.produceState.logs = [err.message];
      updateProducerStageUI(1, 0, 'Chưa dựng: tỉ lệ video Muse chưa đủ', [err.message]);
      const ok = window.confirm(`${err.message}\n\nDựng BẢN NHÁP để xem thử? Bản nháp ra file riêng, không phải thành phẩm, `
        + 'không ghi đè video cuối của dự án.');
      if (ok) return startProduceLongVideo({ draft: true });
      switchStep(2);
      showToast('Chưa dựng video. Làm thêm video Muse ("Chọn cảnh cao trào" rồi "Tạo video") hoặc duyệt clip trên thẻ cảnh.', 'warning', 9000);
      return;
    }
    console.error("startProduceLongVideo error", err);
    AppState.produceState.isProducing = false;
    AppState.produceState.progress = 100;
    AppState.produceState.statusMsg = `Lỗi sản xuất: ${err.message || err}`;
    AppState.produceState.logs = [`LỖI: ${err.message || err}`];
    updateProducerStageUI(1, 100, `Lỗi sản xuất: ${err.message || err}`, [
      `LỖI: ${err.message || err}`
    ]);
    showToast(`Lỗi sản xuất: ${escapeHtml(err.message || err)}`, "error");
  }
}

function listenToProduceProgress(renderId) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/render/${renderId}`;

  let ws = null;
  let pollInterval = null;

  try {
    ws = new WebSocket(wsUrl);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleProduceStatusUpdate(data);
      } catch {}
    };
    ws.onerror = () => {
      startProducePolling();
    };
  } catch {
    startProducePolling();
  }

  function startProducePolling() {
    if (pollInterval) return;
    pollInterval = setInterval(async () => {
      if (!AppState.produceState.isProducing) {
        clearInterval(pollInterval);
        return;
      }
      const st = await API.getRenderStatus(renderId);
      if (st) {
        handleProduceStatusUpdate(st);
      }
    }, 1500);
  }

  function handleProduceStatusUpdate(data) {
    if (!data) return;
    // Tin của một lần dựng cũ (đã bắt đầu lần khác) thì bỏ, để không ghi đè trạng thái lần mới
    if (AppState.produceState.renderId !== renderId) return;

    const progress = data.progress || 0;
    const step = data.step || 1;
    const stepLabel = data.step_label || "Đang xử lý...";
    const logs = data.logs || [];
    const renderedProjectId = AppState.produceState.projectId;
    // Đang mở dự án khác thì chỉ giữ trạng thái; mở lại dự án đang dựng thì paintProducerForCurrentProject() vẽ lại
    const visible = AppState.currentProject?.id === renderedProjectId;

    AppState.produceState.progress = progress;
    AppState.produceState.step = step;
    AppState.produceState.logs = logs;
    AppState.produceState.statusMsg = stepLabel;

    if (visible) updateProducerStageUI(step, progress, stepLabel, logs);

    // Fail-Safe: Check failure first (Anti-Fail-Open)
    if (data.status === 'failed' || data.error) {
      AppState.produceState.isProducing = false;
      if (ws) {
        try { ws.close(); } catch {}
      }
      if (pollInterval) clearInterval(pollInterval);
      const errMsg = data.error || 'Quy trình sản xuất video dài thất bại!';
      AppState.produceState.failed = errMsg;
      showToast(`❌ LỖI SẢN XUẤT: ${escapeHtml(errMsg)}`, "error", 6000);
      if (visible && DOM.producerStatusText) {
        DOM.producerStatusText.textContent = `Thất bại: ${errMsg}`;
        DOM.producerStatusText.className = "text-xs font-bold text-red-600 truncate";
      }
      return;
    }

    // Only complete and switch to cinema when status is explicitly 'completed'
    if (data.status === 'completed') {
      AppState.produceState.isProducing = false;
      if (ws) {
        try { ws.close(); } catch {}
      }
      if (pollInterval) clearInterval(pollInterval);

      const videoUrl = data.video_url || `/api/projects/${renderedProjectId}/media/renders/story_final.mp4`;
      const srtUrl = data.srt_url || `/api/projects/${renderedProjectId}/download-srt`;

      AppState.produceState.videoUrl = videoUrl;
      AppState.produceState.srtUrl = srtUrl;

      if (!visible) {
        showToast("Đã dựng xong video của dự án đang dựng. Mở lại dự án đó để xem.", "success", 6000);
        return;
      }
      // Hiện trình phát và nút tải (chỉ khi đúng dự án đang mở)
      renderFinalVideoBlock(AppState.currentProject);

      showToast("🎉 Hoàn tất sản xuất Video Dài 1080p! Đang mở Rạp Chiếu Phim...", "success", 4000);

      // Auto switch to Step 4 after 1.5 seconds
      setTimeout(() => {
        if (AppState.currentProject?.id === renderedProjectId) switchStep(4);
      }, 1500);
    }
  }
}

// ================= MODAL 4: PROJECT MANAGER =================
// Trang Dự án: việc nạp danh sách nằm ở móc onPageShow('projects') trong initMuseCloud()

// Mở hoặc tạo xong một dự án thì rời trang Dự án: về trang đã dùng lần trước của dự án đó, chưa có thì Cảnh hoặc Ý tưởng
function leaveProjectsPage() {
  const proj = AppState.currentProject;
  const saved = typeof rememberedPage === 'function' ? rememberedPage(proj?.id) : null;
  const target = (saved && !['projects', 'gallery', 'accounts'].includes(saved)) ? saved
    : (proj?.scenes?.length ? 'scenes' : 'idea');
  showPage(target);
}

function renderProjectListModal() {
  const container = DOM.projectListItems;
  if (!container) return;

  const projects = AppState.projectsList || [];
  container.classList.add('ws-project-grid');
  container.innerHTML = projects.map(p => {
    const isCurrent = AppState.currentProject && AppState.currentProject.id === p.id;
    const unreadable = !!p.unreadable;
    const scenes = isCurrent ? (AppState.currentProject.scenes?.length || 0) : (p.scenes_count ?? p.scene_count ?? 0);
    const when = p.updated_at ? new Date(p.updated_at) : null;
    const whenText = when && !isNaN(when) ? when.toLocaleDateString('vi-VN') : '';
    const meta = unreadable ? 'Không đọc được' : `${scenes} cảnh${whenText ? ' · sửa ' + escapeHtml(whenText) : ''}`;
    const cover = p.cover_url
      ? `<img src="${escapeHtml(p.cover_url)}" alt="" loading="lazy">`
      : '<i class="fa-solid fa-film" aria-hidden="true"></i>';
    return `
      <button type="button" class="ws-card ws-project-card" data-project-id="${escapeHtml(p.id)}"${isCurrent ? ' aria-current="true"' : ''}${unreadable ? ' disabled' : ''}>
        <span class="ws-project-cover">${cover}</span>
        <span class="ws-project-body">
          <span class="ws-project-title">${escapeHtml(p.name)}</span>
          <span class="ws-project-meta">${isCurrent ? '<span class="ws-project-badge">Đang mở</span>' : ''}<span>${meta}</span></span>
        </span>
      </button>
    `;
  }).join('');
  container.querySelectorAll('.ws-project-card[data-project-id]').forEach(card => {
    card.addEventListener('click', () => {
      if (AppState.currentProject && AppState.currentProject.id === card.dataset.projectId) leaveProjectsPage();
      else switchProject(card.dataset.projectId);
    });
  });
}

async function handleCreateNewProject() {
  const name = DOM.newProjectNameInput.value.trim();
  if (!name) {
    showToast("Vui lòng nhập tên cho dự án mới!", "warning");
    return;
  }

  // Dự án mới tạo trên server, bắt đầu trống (không sao chép dự án mẫu và nhân vật của nó)
  if (!AppState.serverOnline) {
    showToast("Máy chủ đang offline nên chưa tạo được dự án mới.", "error", 6000);
    return;
  }
  if (!(await flushProjectSave())) return;
  const remote = await API.createProject(name);
  if (!remote || !remote.id) {
    showToast("Tạo dự án trên máy chủ thất bại. Vui lòng thử lại!", "error", 6000);
    return;
  }

  AppState.currentProject = adoptServerProject(remote);
  rememberLastProjectId(remote.id);
  AppState.projectsList.push({ id: remote.id, name: remote.name, scene_count: 0 });
  renderFullUI();
  leaveProjectsPage();
  DOM.newProjectNameInput.value = "";
  showToast(`Đã tạo dự án mới: "${escapeHtml(name)}"`, "success");
}

async function switchProject(projectId) {
  if (!AppState.serverOnline) {
    showToast("Máy chủ đang offline nên chưa mở được dự án.", "error", 6000);
    return;
  }
  // Lưu nốt dự án đang mở trước khi chuyển
  if (!(await flushProjectSave())) return;

  const remote = await API.getProject(projectId);
  if (!remote || !remote.id) {
    showToast("Không tải được dự án từ máy chủ.", "error", 6000);
    return;
  }
  AppState.currentProject = adoptServerProject(remote);
  rememberLastProjectId(remote.id);
  renderFullUI();
  leaveProjectsPage();
  showToast(`Đã mở dự án: ${escapeHtml(remote.name)}`, "info");
}

async function handleSaveProject() {
  const project = AppState.currentProject;
  if (!project) return;

  if (project.is_demo) {
    showToast("Đây là dự án mẫu (chỉ để xem). Hãy tạo dự án mới để lưu công việc.", "warning", 7000);
    return;
  }
  if (!AppState.serverOnline) {
    showToast("Máy chủ đang offline: thay đổi CHƯA được lưu. Sẽ tự lưu khi máy chủ online lại.", "warning", 7000);
    return;
  }

  // Lưu ngay toàn bộ dự án (kể cả khi chưa có thay đổi nào đang chờ); lỗi do flushProjectSave báo
  ProjectSync.dirty = true;
  if (await flushProjectSave()) {
    showToast("Đã lưu dự án lên máy chủ thành công!", "success");
  }
}

// ================= META MUSE CLOUD STUDIO ENGINE =================
function initMuseCloud() {
  console.log("Initializing Meta Muse Cloud Studio Engine...");

  // Bind Header Button & Modal Controls
  if (DOM.btnMuseCloudStatus) {
    DOM.btnMuseCloudStatus.addEventListener('click', openMuseModal);
  }
  document.getElementById('btn-muse-attach-cancel')?.addEventListener('click', () => {
    clearMuseAttachMode();
    if (typeof showPage === 'function') showPage('scenes');
  });
  // Mở trang thì nạp lại dữ liệu như cửa sổ cũ làm khi mở; rời trang Thư viện thì bỏ chế độ chọn ảnh cho cảnh
  if (typeof onPageShow === 'function') {
    onPageShow('gallery', () => { pollMuseBridgeStatus(); updateMuseAttachStrip(); });
    onPageShow('accounts', () => { pollMuseBridgeStatus(); loadMuseAccountsUI(); });
    for (const page of ['idea', 'script', 'look', 'scenes', 'publish', 'projects', 'accounts']) onPageShow(page, clearMuseAttachMode);
    onPageShow('projects', () => {
      renderProjectListModal();
      if (AppState.serverOnline) loadProjectsList().then(() => { if (currentPage() === 'projects') renderProjectListModal(); }).catch(() => {});
    });
  }

  const btnRefreshAcc = DOM.btnMuseRefreshAccounts;
  if (btnRefreshAcc) {
    btnRefreshAcc.addEventListener('click', async () => {
      await loadMuseAccountsUI();
      showToast("Đã làm mới danh sách tài khoản Muse Fleet!", "info");
    });
  }

  // Fleet accounts: delegated handlers ("Đặt làm mặc định" + copy login command)
  if (DOM.museFleetPoolGrid) {
    DOM.museFleetPoolGrid.addEventListener('click', handleMuseFleetAccountClick);
  }

  // Fleet Runner 1-Click Utilities listeners
  const btnStartFleetCmd = document.getElementById('btn-copy-start-fleet-cmd');
  if (btnStartFleetCmd) {
    btnStartFleetCmd.addEventListener('click', async () => {
      const cmd = "start_muse_fleet.bat";
      const ok = await copyTextToClipboard(cmd);
      showToast(ok
        ? "Đã sao chép lệnh: 'start_muse_fleet.bat'! Chạy file này trên PC này để khởi động lại Muse Fleet (server thường tự khởi động sẵn)."
        : "Chưa chép được vào bộ nhớ tạm. Hãy chạy file start_muse_fleet.bat trong thư mục story-studio.", ok ? "success" : "warning", 5000);
    });
  }

  const btnSetupAccountsCmd = document.getElementById('btn-copy-setup-accounts-cmd');
  if (btnSetupAccountsCmd) {
    btnSetupAccountsCmd.addEventListener('click', async () => {
      const cmd = "setup_muse_accounts.bat";
      const ok = await copyTextToClipboard(cmd);
      showToast(ok
        ? "Đã sao chép lệnh: 'setup_muse_accounts.bat'! Chạy file này để đăng nhập lần đầu cho các tài khoản."
        : "Chưa chép được vào bộ nhớ tạm. Hãy chạy file setup_muse_accounts.bat trong thư mục story-studio.", ok ? "success" : "warning", 5000);
    });
  }

  // Clear All Gallery Media
  const btnClearAllGallery = document.getElementById('btn-clear-all-gallery');
  if (btnClearAllGallery) {
    btnClearAllGallery.addEventListener('click', async () => {
      if (!confirm("Bạn có chắc chắn muốn dọn sạch toàn bộ ảnh và video trong bộ sưu tập không?")) return;
      const res = await API.clearAllGallery();
      if (res && res.success) {
        showToast(res.message || "Đã dọn sạch bộ sưu tập!", "success");
        renderMuseGalleryItems([]);
      } else {
        showToast("Lỗi khi dọn dẹp bộ sưu tập!", "error");
      }
    });
  }

  // Start polling status
  pollMuseBridgeStatus();
  if (AppState.museCloud.pollingInterval) clearInterval(AppState.museCloud.pollingInterval);
  AppState.museCloud.pollingInterval = setInterval(pollMuseBridgeStatus, 5000);
}

// Muse Fleet state (local Fleet Runner: Playwright + one logged-in Chrome profile per Muse account).
// Image tasks only go to image accounts, video tasks only to video accounts. Active ids are nullable.
let cachedMuseAccounts = [];
const museFleetState = {
  activeImageAccount: null,
  activeVideoAccount: null,
  imageOnline: null,      // from /status image_online (null = unknown)
  videoOnline: null,      // from /status video_online (null = unknown)
  concurrencyLimit: null,
  lastRenderKey: '',
};

async function copyTextToClipboard(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (err) {
    console.warn("Clipboard API failed, fallback to execCommand", err);
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const successful = document.execCommand('copy');
    document.body.removeChild(ta);
    return successful;
  } catch (e) {
    return false;
  }
}

// ---- Muse Fleet accounts helpers ----
function museAccountKind(acc) {
  const t = acc && (acc.type || acc.kind);
  return (t === 'image' || t === 'video' || t === 'both') ? t : null;
}

// Tài khoản nhận được việc loại kind ('image' | 'video'); 'both' nhận cả hai (chủ dự án 17/11/2026)
function museAccountServes(acc, kind) {
  const t = museAccountKind(acc);
  return t === 'both' || t === kind;
}

// Active account id of the given kind ('image' | 'video'), or null when none is set.
function getActiveMuseAccountId(kind) {
  const fromState = kind === 'video' ? museFleetState.activeVideoAccount : museFleetState.activeImageAccount;
  if (fromState) {
    const acc = (cachedMuseAccounts || []).find(a => a.account_id === fromState);
    if (!acc || museAccountServes(acc, kind)) return fromState;
  }
  const flag = kind === 'video' ? 'is_active_for_video' : 'is_active_for_image';
  const acc = (cachedMuseAccounts || []).find(a => museAccountServes(a, kind) && a[flag]);
  return acc ? acc.account_id : null;
}

// Adds assigned_account/account_id to a task payload only when an account of the right kind is known.
function withMuseAccount(payload, accountId) {
  if (!accountId) return payload;
  payload.assigned_account = accountId;
  payload.account_id = accountId;
  if (payload.parameters) {
    payload.parameters.assigned_account = accountId;
    payload.parameters.account_id = accountId;
  }
  return payload;
}

// Stores accounts + active ids from /accounts, /accounts/switch or /status responses.
function applyMuseFleetAccounts(data) {
  if (!data || !Array.isArray(data.accounts)) return false;
  cachedMuseAccounts = data.accounts;
  museFleetState.activeImageAccount = data.active_image_account || null;
  museFleetState.activeVideoAccount = data.active_video_account || null;
  return true;
}

function museKindOnline(kind) {
  const flag = kind === 'video' ? museFleetState.videoOnline : museFleetState.imageOnline;
  if (typeof flag === 'boolean') return flag;
  if (!cachedMuseAccounts.length) return null;
  return cachedMuseAccounts.some(a => museAccountServes(a, kind) && a.online);
}

function museFleetKindSummary() {
  const mark = (v) => v === true ? '✓' : (v === false ? '✗' : '?');
  return `Ảnh ${mark(museKindOnline('image'))} • Video ${mark(museKindOnline('video'))}`;
}

function formatMuseEpoch(v) {
  const n = Number(v);
  if (!v || !isFinite(n) || n <= 0) return '';
  return new Date(n < 1e12 ? n * 1000 : n).toLocaleString('vi-VN');
}

function museFleetStatusBadge(acc) {
  const make = (cls, dotCls, label, title = '') =>
    `<span class="flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border shrink-0 ${cls}"${title ? ` title="${escapeHtml(String(title))}"` : ''}><span class="w-1.5 h-1.5 rounded-full ${dotCls}"></span> ${label}</span>`;
  if (!acc.has_profile) {
    return make('text-slate-500 bg-slate-100 border-slate-200', 'bg-slate-400', 'chưa đăng nhập', 'Profile Chrome chưa có phiên đăng nhập Muse');
  }
  const until = formatMuseEpoch(acc.blocked_until);
  switch (acc.status) {
    case 'online':
      return make('text-emerald-700 bg-emerald-50 border-emerald-200', 'bg-emerald-500 animate-pulse', 'online');
    case 'ready':
      return make('text-slate-700 bg-slate-50 border-slate-200', 'bg-slate-700', 'sẵn sàng');
    case 'busy':
      return make('text-slate-700 bg-slate-50 border-slate-200', 'bg-slate-700 animate-pulse', 'đang chạy');
    case 'cooldown':
      return make('text-amber-700 bg-amber-50 border-amber-200', 'bg-amber-400', 'nghỉ (cooldown)', until ? `Nghỉ tới ${until}` : '');
    case 'blocked':
      return make('text-red-700 bg-red-50 border-red-200', 'bg-red-500', 'bị khóa',
        [acc.block_reason, until ? `tới ${until}` : ''].filter(Boolean).join(' • ') || 'Tài khoản đang bị khóa');
    case 'needs_login':
      return make('text-red-700 bg-red-50 border-red-200', 'bg-red-500', 'cần đăng nhập lại', 'Phiên đăng nhập đã hết hạn: chạy lại lệnh --setup cho tài khoản này');
    default:
      return make('text-slate-500 bg-slate-100 border-slate-200', 'bg-slate-400', 'offline');
  }
}

function renderMuseFleetAccountRow(acc, kind, activeId) {
  const aid = String(acc.account_id || '');
  const isActive = !!activeId && aid === activeId;
  const hasCounts = (acc.success_count !== undefined && acc.success_count !== null) || (acc.fail_count !== undefined && acc.fail_count !== null);
  const counts = hasCounts
    ? `<span class="text-slate-500 shrink-0" title="Số lần thành công / thất bại">✓ ${Number(acc.success_count) || 0} · ✗ ${Number(acc.fail_count) || 0}</span>`
    : '';
  const rowTitle = acc.last_error ? ` title="Lỗi gần nhất: ${escapeHtml(String(acc.last_error))}"` : '';
  const setBtnCls = isActive
    ? 'bg-slate-50 text-slate-700 border border-slate-200 cursor-default'
    : (acc.has_profile ? 'bg-slate-900 hover:bg-slate-700 text-white cursor-pointer' : 'bg-slate-200 text-slate-500 cursor-pointer');
  return `
    <div class="p-2.5 bg-white rounded-lg border ${isActive ? 'border-slate-300 ring-2 ring-slate-100' : 'border-slate-200'} flex items-center justify-between gap-2"${rowTitle}>
      <div class="min-w-0">
        <div class="flex items-center gap-1.5 flex-wrap">
          <span class="text-xs font-bold text-slate-900 truncate">${escapeHtml(String(acc.label || aid))}</span>
          ${isActive ? '<span class="text-[9px] bg-amber-100 text-amber-800 font-bold px-1 rounded border border-amber-200 shrink-0">⭐ Mặc định</span>' : ''}
        </div>
        <div class="flex items-center gap-2 text-[10px] font-mono text-slate-400 min-w-0">
          <span class="truncate">${escapeHtml(aid)}</span>
          ${counts}
        </div>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        ${museFleetStatusBadge(acc)}
        <button type="button" class="btn-muse-copy-setup w-6 h-6 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg text-[10px] flex items-center justify-center transition cursor-pointer" data-account-id="${escapeHtml(aid)}" title="Chép lệnh đăng nhập: ${escapeHtml(museSetupCommand(aid))}">
          <i class="fa-solid fa-key"></i>
        </button>
        <button type="button" class="btn-muse-set-default px-2 py-0.5 ${setBtnCls} rounded-lg text-[10px] font-bold transition shadow-xs" data-account-id="${escapeHtml(aid)}" data-mode="${kind}" ${isActive ? 'disabled' : ''}>
          ${isActive ? 'Đang mặc định' : 'Đặt làm mặc định'}
        </button>
      </div>
    </div>
  `;
}

function updateMuseFleetIndicators() {
  const paint = (el, kind, label) => {
    if (!el) return;
    const v = museKindOnline(kind);
    const icon = kind === 'video' ? 'fa-film text-slate-500' : 'fa-image text-slate-500';
    const tone = v === true
      ? ['bg-emerald-50 border-emerald-200 text-emerald-800', 'bg-emerald-500 animate-pulse', 'online']
      : (v === false ? ['bg-red-50 border-red-200 text-red-700', 'bg-red-500', 'offline'] : ['bg-slate-50 border-slate-200 text-slate-600', 'bg-slate-400', 'chưa rõ']);
    el.className = `px-2.5 py-1 border rounded-lg text-[10px] sm:text-[11px] font-mono font-bold flex items-center gap-1 ${tone[0]}`;
    el.innerHTML = `<span class="w-1.5 h-1.5 rounded-full ${tone[1]}"></span><i class="fa-solid ${icon}"></i> ${label}: ${tone[2]}`;
  };
  paint(DOM.museFleetImageIndicator, 'image', 'Ảnh');
  paint(DOM.museFleetVideoIndicator, 'video', 'Video');
  if (DOM.museFleetConcurrency) {
    const n = museFleetState.concurrencyLimit;
    DOM.museFleetConcurrency.textContent = `⚡ Slot: ${n !== null && n !== undefined ? n : '–'}`;
  }
}

function renderMuseFleetAccounts(force = false) {
  const lists = { image: DOM.museFleetImageList, video: DOM.museFleetVideoList };
  if (!lists.image && !lists.video) return;
  const active = { image: museFleetState.activeImageAccount, video: museFleetState.activeVideoAccount };
  const key = JSON.stringify([cachedMuseAccounts, active, museFleetState.imageOnline, museFleetState.videoOnline]);
  if (!force && key === museFleetState.lastRenderKey) return;
  museFleetState.lastRenderKey = key;

  const groups = { image: [], video: [] };
  (cachedMuseAccounts || []).forEach(acc => {
    ['image', 'video'].forEach(kind => { if (museAccountServes(acc, kind)) groups[kind].push(acc); });
  });

  ['image', 'video'].forEach(kind => {
    const kindLabel = kind === 'video' ? 'video' : 'ảnh';
    const accs = groups[kind];
    const listEl = lists[kind];
    if (listEl) {
      listEl.innerHTML = accs.length
        ? accs.map(acc => renderMuseFleetAccountRow(acc, kind, active[kind])).join('')
        : `<p class="text-[11px] text-slate-400 px-1">Chưa có tài khoản ${kindLabel} nào trong cấu hình Fleet.</p>`;
    }
    const statusEl = kind === 'video' ? DOM.museFleetVideoGroupStatus : DOM.museFleetImageGroupStatus;
    if (statusEl) {
      const onlineCount = accs.filter(a => a.online).length;
      const notLoggedIn = accs.filter(a => !a.has_profile || a.status === 'needs_login').length;
      const kindOnline = museKindOnline(kind);
      statusEl.className = `text-[10px] font-bold px-2 py-0.5 rounded-full border ${kindOnline ? 'text-emerald-700 bg-emerald-50 border-emerald-200' : 'text-slate-500 bg-slate-100 border-slate-200'}`;
      statusEl.textContent = `${onlineCount}/${accs.length} online` + (notLoggedIn ? ` • ${notLoggedIn} cần đăng nhập` : '') + (active[kind] ? '' : ' • chưa chọn mặc định');
    }
  });
}

async function loadMuseAccountsUI() {
  if (!DOM.museFleetImageList && !DOM.museFleetVideoList) return;
  const data = await API.getMuseAccounts();
  if (applyMuseFleetAccounts(data)) {
    renderMuseFleetAccounts(true);
    updateMuseFleetIndicators();
    return;
  }
  if (!cachedMuseAccounts.length) {
    const msg = '<p class="text-[11px] text-red-500 px-1">Không tải được danh sách tài khoản (server không phản hồi).</p>';
    if (DOM.museFleetImageList) DOM.museFleetImageList.innerHTML = msg;
    if (DOM.museFleetVideoList) DOM.museFleetVideoList.innerHTML = msg;
    museFleetState.lastRenderKey = '';
  }
}

// Lệnh đăng nhập 1 tài khoản Muse, chạy trong thư mục story-studio (dùng Python của .venv, có sẵn Playwright)
function museSetupCommand(accountId) {
  return `.venv\\Scripts\\python.exe backend\\runners\\muse_fleet_runner.py --setup ${accountId}`;
}

async function handleMuseFleetAccountClick(e) {
  const setupBtn = e.target.closest('.btn-muse-copy-setup');
  if (setupBtn) {
    const aid = setupBtn.getAttribute('data-account-id');
    const cmd = museSetupCommand(aid);
    const ok = await copyTextToClipboard(cmd);
    showToast(ok
      ? `Đã chép lệnh đăng nhập ${aid}. Chạy trong thư mục story-studio trên PC này (hoặc dùng setup_muse_accounts.bat).`
      : `Chạy lệnh: ${cmd}`, ok ? "info" : "warning", 5000);
    return;
  }

  const btn = e.target.closest('.btn-muse-set-default');
  if (!btn || btn.disabled) return;
  const aid = btn.getAttribute('data-account-id');
  const mode = btn.getAttribute('data-mode');
  if (mode !== 'image' && mode !== 'video') return;
  const kindLabel = mode === 'video' ? 'video' : 'ảnh';
  const acc = cachedMuseAccounts.find(a => a.account_id === aid);
  if (acc && !museAccountServes(acc, mode)) {
    showToast(`${escapeHtml(aid)} không phải tài khoản ${kindLabel}.`, "error");
    return;
  }
  if (acc && !acc.has_profile) {
    showToast(`Tài khoản ${escapeHtml(aid)} chưa đăng nhập. Chạy: ${escapeHtml(museSetupCommand(aid))}`, "warning", 6000);
    return;
  }

  btn.disabled = true;
  const res = await API.switchMuseAccount(mode, aid);
  if (res && res.success) {
    showToast(`Đã đặt ${escapeHtml(aid)} làm tài khoản ${kindLabel} mặc định.`, "success");
    if (applyMuseFleetAccounts(res)) {
      renderMuseFleetAccounts(true);
      updateMuseFleetIndicators();
    } else {
      await loadMuseAccountsUI();
    }
  } else {
    showToast(escapeHtml(res?.detail || `Không thể đổi tài khoản ${kindLabel} mặc định.`), "error", 5000);
    btn.disabled = false;
  }
}

// Mở trang Tài khoản và kết nối; nạp lại trạng thái và tài khoản nằm ở móc onPageShow('accounts') trong initMuseCloud()
function openMuseModal() {
  showPage('accounts');
}

// Một lần /status lỗi hoặc quá 4 s (trang bị ẩn, máy bận) chưa phải mất kết nối: giữ trạng thái cũ,
// chỉ báo offline sau MUSE_STATUS_MAX_FAILURES lần lỗi liên tiếp. Máy chủ tự báo offline khi runner im 60 s.
const MUSE_STATUS_MAX_FAILURES = 3;
let museStatusFailures = 0;
let museStatusEverLoaded = false;

async function pollMuseBridgeStatus() {
  try {
    const data = await API.getMuseBridgeStatus();
    if (data) {
      updateMuseCloudUI(data);
      museStatusFailures = 0;
      museStatusEverLoaded = true;
      return;
    }
  } catch (err) {
    console.debug("Muse bridge status poll silent catch", err);
  }
  museStatusFailures += 1;
  // Chưa từng nhận được trạng thái thì không có gì để giữ: báo offline ngay
  if (!museStatusEverLoaded || museStatusFailures >= MUSE_STATUS_MAX_FAILURES) {
    updateMuseCloudUI(null);
  }
}

function updateMuseCloudUI(data) {
  const isOnline = !!(data && (data.online === true || data.status === 'online' || data.status === 'busy' || data.status === 'processing' || (data.worker && data.worker.is_alive)));
  const isBusy = !!(data && (data.status === 'busy' || data.status === 'processing' || (data.active_job && data.active_job.status === 'processing') || (data.queue && data.queue.processing > 0) || (data.stats && data.stats.processing_tasks > 0)));
  
  const statusStr = !isOnline ? 'offline' : (isBusy ? 'busy' : 'online');
  AppState.museCloud.status = statusStr;

  // 0. Sync Muse Fleet state (per-kind online flags, concurrency, accounts + nullable active ids)
  museFleetState.imageOnline = data ? (typeof data.image_online === 'boolean' ? data.image_online : null) : false;
  museFleetState.videoOnline = data ? (typeof data.video_online === 'boolean' ? data.video_online : null) : false;
  museFleetState.concurrencyLimit = (data && data.concurrency_limit !== undefined) ? data.concurrency_limit : null;
  applyMuseFleetAccounts(data);

  // 1. Update Header Status Badge (huy hiệu chỉ hiện từ 1880px, khớp với nút trong header của index.html)
  if (DOM.btnMuseCloudStatus && DOM.headerMuseStatusDot && DOM.headerMuseStatusText && DOM.headerMuseSpecsBadge) {
    if (statusStr === 'online') {
      DOM.btnMuseCloudStatus.dataset.state = "online";
      DOM.headerMuseStatusDot.innerHTML = `
        <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
      `;
      DOM.headerMuseStatusText.textContent = "Sẵn sàng";
      DOM.headerMuseStatusText.title = "";
      DOM.headerMuseSpecsBadge.textContent = museFleetKindSummary();
    } else if (statusStr === 'busy') {
      DOM.btnMuseCloudStatus.dataset.state = "busy";
      DOM.headerMuseStatusDot.innerHTML = `
        <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
      `;
      const activeMsg = data?.active_job?.status_message || "Đang render...";
      DOM.headerMuseStatusText.textContent = activeMsg.length > 25 ? activeMsg.substring(0, 22) + "..." : activeMsg;
      // Giới hạn bề rộng để thông báo dài không ép mất tên dự án trên màn 1280-1600px; rê chuột xem đủ câu.
      // 140px vừa đủ các câu runner gửi lâu nhất ("Muse đang tạo video..." 136px, "Gửi prompt lên Muse..." 137px).
      DOM.headerMuseStatusText.title = activeMsg;
      DOM.headerMuseSpecsBadge.textContent = museFleetKindSummary();   // chữ trạng thái bên cạnh đã nói đang render
    } else {
      DOM.btnMuseCloudStatus.dataset.state = "offline";
      DOM.headerMuseStatusDot.innerHTML = `
        <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500"></span>
      `;
      DOM.headerMuseStatusText.textContent = "Chưa kết nối";
      DOM.headerMuseStatusText.title = "";
      DOM.headerMuseSpecsBadge.textContent = "Bấm để xem Fleet";
    }
  }

  // 2. Update Modal Status Badge
  if (DOM.museModalStatusBadge && DOM.museModalStatusDot && DOM.museModalStatusText) {
    if (statusStr === 'online') {
      DOM.museModalStatusBadge.dataset.state = "online";
      DOM.museModalStatusDot.className = "w-1.5 h-1.5 rounded-full bg-emerald-500";
      DOM.museModalStatusText.textContent = "Đang kết nối (Online)";
    } else if (statusStr === 'busy') {
      DOM.museModalStatusBadge.dataset.state = "busy";
      DOM.museModalStatusDot.className = "w-1.5 h-1.5 rounded-full bg-amber-500";
      DOM.museModalStatusText.textContent = "Đang render tác vụ (Busy)";
    } else {
      DOM.museModalStatusBadge.dataset.state = "offline";
      DOM.museModalStatusDot.className = "w-1.5 h-1.5 rounded-full bg-red-500";
      DOM.museModalStatusText.textContent = "Chưa kết nối (Offline)";
    }
  }

  // 3. Fleet accounts: refresh the account list when the accounts page is visible (accounts come with every status poll)
  if (typeof currentPage === 'function' && currentPage() === 'accounts' && data && Array.isArray(data.accounts)) {
    renderMuseFleetAccounts();
  }
  updateMuseFleetIndicators();

  // 4. Toggle Fleet offline assistant (show if offline, hide if online)
  if (DOM.museReconnectAssistant) {
    if (!isOnline) {
      DOM.museReconnectAssistant.classList.remove('hidden');
    } else {
      DOM.museReconnectAssistant.classList.add('hidden');
    }
  }

  // 5. Update Progress Card if Active Job
  if (data && data.active_job) {
    const job = data.active_job;
    if (DOM.museProgressCard) DOM.museProgressCard.classList.remove('hidden');
    if (DOM.museProgressTitle) DOM.museProgressTitle.textContent = job.status_message || `Đang xử lý ${job.mode}...`;
    const pct = job.progress_percent || 0;
    if (DOM.museProgressPercent) DOM.museProgressPercent.textContent = `${pct}%`;
    if (DOM.museProgressBarFill) DOM.museProgressBarFill.style.width = `${pct}%`;
  } else if (!AppState.museCloud.isProcessing) {
    if (DOM.museProgressCard) DOM.museProgressCard.classList.add('hidden');
  }

  // 6. Update Recent Completed Gallery Items
  if (data && data.recent_completed && Array.isArray(data.recent_completed)) {
    renderMuseGalleryItems(data.recent_completed);
  }
}

function renderMuseGalleryItems(items) {
  if (!DOM.museGalleryGrid) return;
  if (!items || items.length === 0) {
    if (DOM.museGalleryPlaceholder) DOM.museGalleryPlaceholder.classList.remove('hidden');
    if (DOM.museGalleryCount) DOM.museGalleryCount.textContent = '0 sản phẩm';
    DOM.museGalleryGrid.innerHTML = `
      <div id="muse-gallery-placeholder" class="col-span-full py-10 bg-white rounded-2xl border border-dashed border-slate-300 text-center text-slate-400 space-y-2">
        <i class="fa-solid fa-images text-3xl text-slate-300"></i>
        <p class="text-xs">Chưa có ảnh hoặc video nào được tạo trong phiên này.</p>
        <p class="text-[10px] text-slate-400">Bấm nút Muse 2K / Muse Video trên thẻ cảnh để bắt đầu sinh media qua Muse Fleet.</p>
      </div>
    `;
    return;
  }

  if (DOM.museGalleryPlaceholder) {
    DOM.museGalleryPlaceholder.classList.add('hidden');
  }
  if (DOM.museGalleryCount) {
    DOM.museGalleryCount.textContent = `${items.length} sản phẩm`;
  }

  DOM.museGalleryGrid.innerHTML = items.map((item, idx) => {
    const isVideo = item.media_type === 'video' || (item.media_url && item.media_url.endsWith('.mp4'));
    const rawUrl = item.media_url || item.file_url || '';
    const mediaUrl = (rawUrl && !rawUrl.endsWith('/') && !rawUrl.includes('None')) ? rawUrl : '/static/demo_images/scene_1.jpg';
    const downloadUrl = item.download_url || (item.task_id ? `/api/muse-bridge/download/${escapeHtml(item.task_id)}` : mediaUrl);
    const sceneId = item.scene_id || `Cảnh #${idx + 1}`;
    const taskId = item.task_id || '';
    
    return `
      <div id="gallery-card-${escapeHtml(taskId || idx)}" class="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs hover:shadow-md transition flex flex-col group">
        <div class="relative aspect-video bg-slate-900 overflow-hidden flex items-center justify-center">
          ${isVideo ? `
            <video src="${escapeHtml(mediaUrl)}" class="w-full h-full object-cover" controls preload="metadata"></video>
          ` : `
            <img src="${escapeHtml(mediaUrl)}" alt="${escapeHtml(sceneId)}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" onerror="this.onerror=null;this.src='/static/demo_images/scene_1.jpg'">
          `}
          <span class="absolute top-2 left-2 px-1.5 py-0.5 rounded bg-black/70 backdrop-blur-md text-[10px] font-mono font-bold text-white border border-white/20">
            ${isVideo ? '🎬 Muse 5s' : '💎 Muse 2K'}
          </span>
          <span class="absolute bottom-2 right-2 px-1.5 py-0.5 rounded bg-black/60 text-[9px] font-mono text-emerald-300">
            ${escapeHtml(sceneId)}
          </span>
        </div>
        <div class="p-2.5 flex items-center justify-between text-xs gap-1.5 flex-wrap">
          <span class="font-bold text-slate-800 text-[11px] truncate flex-1 min-w-[100px]" title="${escapeHtml(sceneId)}">${escapeHtml(sceneId)}</span>
          <div class="flex items-center gap-1 shrink-0">
            <button type="button" class="btn-attach-to-scene px-2 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 rounded-lg text-xs font-bold transition flex items-center gap-1 shadow-2xs cursor-pointer" data-media-url="${escapeHtml(mediaUrl)}" data-is-video="${isVideo ? 'true' : 'false'}" data-output-path="${escapeHtml(item.output_path || '')}" title="Gắn tệp này trực tiếp vào Cảnh #${AppState.selectedSceneIndex + 1}">
              <i class="fa-solid fa-thumbtack text-[10px]"></i>
              <span>Gắn Cảnh #${AppState.selectedSceneIndex + 1}</span>
            </button>
            <a href="${escapeHtml(downloadUrl)}" download="${escapeHtml(sceneId)}${isVideo ? '.mp4' : '.jpg'}" class="px-2 py-1 bg-slate-50 hover:bg-slate-100 text-slate-700 rounded-lg text-xs font-bold transition flex items-center gap-1 shadow-2xs" title="Tải file về máy tính">
              <i class="fa-solid fa-download"></i>
              <span class="hidden sm:inline">Tải</span>
            </a>
            <button type="button" class="btn-delete-gallery-item px-2 py-1 bg-red-50 hover:bg-red-50 text-red-600 rounded-lg text-xs font-bold transition flex items-center gap-1 shadow-2xs cursor-pointer" data-task-id="${escapeHtml(taskId)}" title="Xóa tệp media này">
              <i class="fa-solid fa-trash-can"></i>
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');

  // Attach button to assign media to selected scene
  DOM.museGalleryGrid.querySelectorAll('.btn-attach-to-scene').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const mediaUrl = btn.getAttribute('data-media-url');
      const isVideo = btn.getAttribute('data-is-video') === 'true';
      const outPath = btn.getAttribute('data-output-path') || '';
      const targetIdx = AppState.selectedSceneIndex || 0;
      await attachMediaToScene(targetIdx, mediaUrl, isVideo, outPath);
    });
  });

  // Attach delete handlers for individual media items
  DOM.museGalleryGrid.querySelectorAll('.btn-delete-gallery-item').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const tid = btn.getAttribute('data-task-id');
      if (!tid) return;
      if (!confirm("Bạn có chắc chắn muốn xóa tệp này khỏi bộ sưu tập không?")) return;
      
      const res = await API.deleteGalleryItem(tid);
      if (res && res.success) {
        showToast("Đã xóa tệp media khỏi bộ sưu tập!", "info");
        const card = document.getElementById(`gallery-card-${tid}`);
        if (card) card.remove();
        pollMuseBridgeStatus();
      } else {
        showToast("Không thể xóa tệp media!", "error");
      }
    });
  });
}

async function generateSceneWithMuse(index, mode = 'image') {
  const project = AppState.currentProject;
  if (!project || !project.scenes || !project.scenes[index]) return;
  const scene = project.scenes[index];

  // Video: dài theo lời thoại, có thể nhiều video Muse (scene_muse_video.js báo số video trước khi chạy)
  if (mode === 'video' && typeof window.runSceneMuseVideo === 'function') {
    switchScenePromptTab(index, mode);
    return window.runSceneMuseVideo(index);
  }

  if (AppState.museCloud.status === 'offline') {
    showToast("Muse Fleet chưa có tài khoản nào online! Mở bảng Muse Fleet để kiểm tra.", "error", 4000);
    return;
  }

  const isVideo = mode === 'video';
  const kind = isVideo ? 'video' : 'image';
  // Tự động chuyển tab prompt trên thẻ cảnh tương ứng với hành động
  switchScenePromptTab(index, mode);

  // Image tasks -> active image account, video tasks -> active video account (null = let the Fleet pick)
  const assignedAccount = getActiveMuseAccountId(kind);
  const kindLabel = isVideo ? 'tài khoản video' : 'tài khoản ảnh';
  const accLabel = assignedAccount ? `${kindLabel} ${assignedAccount}` : kindLabel;
  if (museKindOnline(kind) === false) {
    showToast(`Chưa có ${kindLabel} nào online — tác vụ sẽ chờ trong hàng đợi.`, "warning", 4000);
  }

  if (project.is_demo) {
    showToast("Đây là dự án mẫu (chỉ để xem). Hãy tạo dự án mới trước khi dùng Muse.", "warning", 7000);
    return;
  }
  // Task Muse ghi kết quả vào bản dự án trên server: lưu chỉnh sửa (prompt...) trước khi gửi
  if (!(await flushProjectSave())) {
    showToast("Chưa lưu được dự án lên máy chủ nên chưa gửi task Muse.", "error", 7000);
    return;
  }

  showToast(`Đang gửi yêu cầu tạo ${isVideo ? 'video chuyển động' : 'ảnh 2K'} qua Muse (${escapeHtml(accLabel)}) cho Cảnh #${index + 1}...`, "info");

  if (isVideo) {
    scene.status_video = 'generating';
  } else {
    scene.status_image = 'generating';
  }
  renderSceneList();

  try {
    const stylePreset = project.style_preset || DOM.selectProjectStyle?.value || DEFAULT_STYLE_PRESET;
    let promptText = "";
    if (isVideo) {
      if (!scene.video_prompt || scene.video_prompt.trim() === '') {
        const rawImgPrompt = scene.image_prompt || scene.visual_prompt || scene.text || "";
        scene.video_prompt = rawImgPrompt;   // luật chuyển động và máy quay do máy chủ ghép (services/prompt_rules.py)
        saveStateToLocal();
      }
      promptText = scene.video_prompt;
    } else {
      // Khoá nhân vật theo cảnh do máy chủ ghép (services/scene_locks.py); không ghép nhân vật chính chung cũ
      promptText = scene.image_prompt || scene.visual_prompt || scene.text || "";
    }

    const taskPayload = withMuseAccount({
      project_id: project.id,
      scene_id: scene.id || `scene_${index + 1}`,
      mode: isVideo ? "image-to-video" : "text-to-image",
      prompt: promptText,
      action_prompt: promptText,
      negative_prompt: scene.negative_prompt || "",
      input_image_url: isVideo ? (scene.image_url || null) : null,
      // Máy quay do máy chủ đặt (đứng yên, services/prompt_rules.py); chuyển động Ken Burns của ảnh không gửi cho Muse
      parameters: {
        resolution: "2K",
        aspect_ratio: "16:9",
        style_preset: stylePreset,
        duration_sec: 5,
        fps: 25,
        action_cues: promptText,
      }
    }, assignedAccount);

    const res = await API.createMuseBridgeTask(taskPayload);
    const taskId = res && (res.task?.task_id || res.task_id);
    if (taskId) {
      showToast(`Đã đưa Cảnh #${index + 1} vào hàng đợi Muse (${escapeHtml(accLabel)})! Đang xử lý...`, "success");
      
      // Auto-poll task completion and update project/scene dynamically
      // Muse: ảnh ~45s, video 5s ~75s (tối đa vài phút khi hàng đợi bận)
      let pollCount = 0;
      const maxPolls = isVideo ? 144 : 96; // 2.5s/lần: video 6 phút, ảnh 4 phút
      const pollTimer = setInterval(async () => {
        pollCount++;
        if (pollCount > maxPolls) {
          clearInterval(pollTimer);
          if (isVideo) scene.status_video = 'idle';
          else scene.status_image = 'idle';
          renderSceneList();
          showToast(`Cảnh #${index + 1}: Muse chưa trả kết quả sau ${Math.round(maxPolls * 2.5 / 60)} phút. Nếu xong muộn, kết quả sẽ nằm trong Gallery Muse.`, "warning", 8000);
          return;
        }

        const taskRes = await API.getMuseBridgeTask(taskId);
        if (taskRes && taskRes.task) {
          const t = taskRes.task;
          if (t.status === 'completed') {
            clearInterval(pollTimer);
            showToast(`Cảnh #${index + 1}: Đã hoàn tất render ${isVideo ? 'video 5s' : 'ảnh 2K'}!`, "success");
            // Chỉ gộp kết quả của cảnh này, giữ nguyên các chỉnh sửa khác chưa lưu trên giao diện
            const refreshedProj = await API.getProject(project.id);
            if (refreshedProj && AppState.currentProject?.id === project.id && mergeServerSceneMedia(refreshedProj, scene.id)) {
              saveStateToLocal();
              renderSceneList();
              renderPreviewPlayer();
            }
          } else if (t.status === 'failed') {
            clearInterval(pollTimer);
            // Không tự thay bằng video Ken Burns dựng từ ảnh: báo đúng là Muse thất bại
            const errText = String(t.error || 'Lỗi server');
            const hint = isVideo ? ' Cảnh vẫn dùng ảnh tĩnh (Ken Burns) khi dựng video.' : '';
            showToast(`Cảnh #${index + 1}: Muse tạo ${isVideo ? 'video' : 'ảnh'} thất bại (${escapeHtml(errText)}).${hint}`, "error", 8000);
            if (isVideo) scene.status_video = 'error';
            else scene.status_image = 'error';
            renderSceneList();
          }
        }
      }, 2500);
    } else {
      const errText = String(res?.detail || 'máy chủ không nhận task');
      showToast(`Không thể gửi task tới Muse Fleet (${kindLabel}): ${escapeHtml(errText)}`, "error", 7000);
      if (isVideo) scene.status_video = 'error';
      else scene.status_image = 'error';
      renderSceneList();
    }
  } catch (err) {
    showToast("Lỗi gửi task: " + escapeHtml(err.message), "error");
    if (isVideo) scene.status_video = 'idle';
    else scene.status_image = 'idle';
    renderSceneList();
  }
}
window.generateSceneWithMuse = generateSceneWithMuse;

// ================= UTILITIES =================
function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Window function exports for inline HTML events
window.switchStep = switchStep;
window.startProduceLongVideo = startProduceLongVideo;
window.updateSceneTextLive = updateSceneTextLive;
window.selectScene = selectScene;
window.updateSceneKenBurns = updateSceneKenBurns;
window.moveScene = moveScene;
window.duplicateScene = duplicateScene;
window.deleteScene = deleteScene;
window.regenerateSceneImage = regenerateSceneImage;
window.uploadCustomSceneImage = uploadCustomSceneImage;
window.updateSceneText = updateSceneText;
window.updateSceneVisualPrompt = updateSceneVisualPrompt;
window.updateSceneVisualPromptLive = updateSceneVisualPromptLive;
window.switchScenePromptTab = switchScenePromptTab;
window.playSceneVoice = playSceneVoice;
window.togglePlayVoiceSample = togglePlayVoiceSample;
window.seekSceneAudio = seekSceneAudio;
window.regenerateSceneVoice = regenerateSceneVoice;
window.switchProject = switchProject;
window.openMuseModal = openMuseModal;
window.loadMuseAccountsUI = loadMuseAccountsUI;
window.setMediaViewMode = setMediaViewMode;
window.resetSceneImageStatus = resetSceneImageStatus;
window.uploadCustomSceneVideo = uploadCustomSceneVideo;
window.openMuseModalForScene = openMuseModalForScene;
window.attachMediaToScene = attachMediaToScene;

// Self bootstrap on DOM content ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
