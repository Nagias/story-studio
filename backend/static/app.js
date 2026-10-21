/**
 * YouTube AI Storyboard Studio - Frontend Engine
 * Modern CapCut / DSH Dark Theme Studio Controller
 */

// ================= GLOBAL STATE =================
const AppState = {
  currentProject: null,
  projectsList: [],
  selectedSceneIndex: 0,
  currentStep: 2, // 1: Nhập liệu, 2: Bảng đạo diễn, 3: Tiến trình, 4: Rạp chiếu
  characterReferenceImage: null, // Base64 data URL or image URL for Step 1 character anchor
  isPlaying: false,
  isPlayingAll: false,
  playAllIndex: 0,
  playbackTimer: null,
  produceState: {
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
  style_preset: "cinematic_realistic",
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
  step1StyleSelect: document.getElementById('step1-style-select'),
  step1CharPresetSelect: document.getElementById('step1-char-preset-select'),
  step1CharName: document.getElementById('step1-char-name'),
  step1CharAnchor: document.getElementById('step1-char-anchor'),
  step1CharRefDropzone: document.getElementById('step1-char-ref-dropzone'),
  step1CharRefFileInput: document.getElementById('step1-char-ref-file-input'),
  step1CharRefPreviewCard: document.getElementById('step1-char-ref-preview-card'),
  step1CharRefPreviewImg: document.getElementById('step1-char-ref-preview-img'),
  step1CharRefFileName: document.getElementById('step1-char-ref-file-name'),
  btnStep1CharRefRemove: document.getElementById('btn-step1-char-ref-remove'),
  step1CharRefUrl: document.getElementById('step1-char-ref-url'),
  btnStep1CharRefApplyUrl: document.getElementById('btn-step1-char-ref-apply-url'),
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
  btnProduceLongVideo: document.getElementById('btn-produce-long-video'),
  btnProduceLabel: document.getElementById('btn-produce-label'),
  boardAssetReadiness: document.getElementById('board-asset-readiness'),
  readinessVoiceCount: document.getElementById('readiness-voice-count'),
  readinessImageCount: document.getElementById('readiness-image-count'),
  readinessLabelBadge: document.getElementById('readiness-label-badge'),
  btnToggleAssetAccordion: document.getElementById('btn-toggle-asset-accordion'),
  assetAccordionBody: document.getElementById('asset-accordion-body'),
  assetAccordionChevron: document.getElementById('asset-accordion-chevron'),
  btnRegenAllImages: document.getElementById('btn-regen-all-images'),
  btnRegenAllVoices: document.getElementById('btn-regen-all-voices'),

  // Step 3 Elements (Realtime Production Console)
  producerStatusText: document.getElementById('producer-status-text'),
  producerPercentText: document.getElementById('producer-percent-text'),
  producerProgressBar: document.getElementById('producer-progress-bar'),
  producerTimerText: document.getElementById('producer-timer-text'),
  producerLogConsole: document.getElementById('producer-log-console'),
  btnProducerGotoCinema: document.getElementById('btn-producer-goto-cinema'),
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
  btnDownloadThumbnailDirect: document.getElementById('btn-download-thumbnail-direct'),
  inputSeoTitle: document.getElementById('input-seo-title'),
  btnCopySeoTitle: document.getElementById('btn-copy-seo-title'),
  textareaSeoDesc: document.getElementById('textarea-seo-desc'),
  btnCopySeoDesc: document.getElementById('btn-copy-seo-desc'),
  inputSeoTags: document.getElementById('input-seo-tags'),
  btnCopySeoTags: document.getElementById('btn-copy-seo-tags'),
  btnRefreshSeoPack: document.getElementById('btn-refresh-seo-pack'),

  // Header
  currentProjectTitle: document.getElementById('current-project-title'),
  btnProjectDropdown: document.getElementById('btn-project-dropdown'),
  btnSaveProject: document.getElementById('btn-save-project'),
  btnOpenScriptModal: document.getElementById('btn-open-script-modal'),

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

  // Character Consistency Card
  characterConsistencyCard: document.getElementById('character-consistency-card'),
  charStatusBadge: document.getElementById('char-status-badge'),
  charThumbElem: document.getElementById('char-thumb-elem'),
  charIconFallback: document.getElementById('char-icon-fallback'),
  charNameDisplay: document.getElementById('char-name-display'),
  charPromptPreview: document.getElementById('char-prompt-preview'),
  btnEditCharacter: document.getElementById('btn-edit-character'),

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

  // Modals
  // Script Modal
  modalScriptImporter: document.getElementById('modal-script-importer'),
  btnCloseScriptModal: document.getElementById('btn-close-script-modal'),
  btnCancelScriptModal: document.getElementById('btn-cancel-script-modal'),
  btnSubmitScriptSplit: document.getElementById('btn-submit-script-split'),
  importScriptTextarea: document.getElementById('import-script-textarea'),
  scriptWordCount: document.getElementById('script-word-count'),
  splitModeSelect: document.getElementById('split-mode-select'),
  splitStyleSelect: document.getElementById('split-style-select'),

  // Character Modal
  modalCharacterEditor: document.getElementById('modal-character-editor'),
  btnCloseCharacterModal: document.getElementById('btn-close-character-modal'),
  btnCancelCharModal: document.getElementById('btn-cancel-char-modal'),
  btnSaveCharacter: document.getElementById('btn-save-character'),
  editCharName: document.getElementById('edit-char-name'),
  editCharPrompt: document.getElementById('edit-char-prompt'),
  editCharStyle: document.getElementById('edit-char-style'),
  editCharNegative: document.getElementById('edit-char-negative'),

  // Project Modal
  modalProjectManager: document.getElementById('modal-project-manager'),
  btnCloseProjectModal: document.getElementById('btn-close-project-modal'),
  newProjectNameInput: document.getElementById('new-project-name-input'),
  btnCreateProject: document.getElementById('btn-create-project'),
  projectListItems: document.getElementById('project-list-items'),

  // Comic Slicer Modal & Controls
  btnOpenComicModal: document.getElementById('btn-open-comic-modal'),
  modalComicSlicer: document.getElementById('modal-comic-slicer'),
  btnCloseComicModal: document.getElementById('btn-close-comic-modal'),
  btnCancelComicModal: document.getElementById('btn-cancel-comic-modal'),
  comicDropzone: document.getElementById('comic-dropzone'),
  comicFileInput: document.getElementById('comic-file-input'),
  comicSelectedFileInfo: document.getElementById('comic-selected-file-info'),
  comicLayoutMode: document.getElementById('comic-layout-mode'),
  comicReadingOrderBox: document.getElementById('comic-reading-order-box'),
  comicReadingOrder: document.getElementById('comic-reading-order'),
  comicMinArea: document.getElementById('comic-min-area'),
  btnSampleMangaGrid: document.getElementById('btn-sample-manga-grid'),
  btnSampleWebtoonStrip: document.getElementById('btn-sample-webtoon-strip'),
  btnStartSlice: document.getElementById('btn-start-slice'),
  comicSliceLoading: document.getElementById('comic-slice-loading'),
  comicUploadSection: document.getElementById('comic-upload-section'),
  comicResultsSection: document.getElementById('comic-results-section'),
  comicPanelCount: document.getElementById('comic-panel-count'),
  comicModeBadge: document.getElementById('comic-mode-badge'),
  tabBtnPanels: document.getElementById('tab-btn-panels'),
  tabBtnAnnotated: document.getElementById('tab-btn-annotated'),
  comicPanelsTabContent: document.getElementById('comic-panels-tab-content'),
  comicAnnotatedTabContent: document.getElementById('comic-annotated-tab-content'),
  comicAnnotatedImg: document.getElementById('comic-annotated-img'),
  btnResetComic: document.getElementById('btn-reset-comic'),
  comicClearExistingCb: document.getElementById('comic-clear-existing-cb'),
  btnImportComicToStoryboard: document.getElementById('btn-import-comic-to-storyboard'),
  importCountLabel: document.getElementById('import-count-label'),

  // Toast
  toastContainer: document.getElementById('toast-container'),

  // Meta Muse Cloud Elements
  btnMuseCloudStatus: document.getElementById('btn-muse-cloud-status'),
  headerMuseStatusDot: document.getElementById('header-muse-status-dot'),
  headerMuseStatusText: document.getElementById('header-muse-status-text'),
  headerMuseSpecsBadge: document.getElementById('header-muse-specs-badge'),
  modalMuseCloud: document.getElementById('modal-muse-cloud'),
  btnCloseMuseModal: document.getElementById('btn-close-muse-modal'),
  btnCloseMuseModalFooter: document.getElementById('btn-close-muse-modal-footer'),
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
  btnMuseRefreshAccounts: document.getElementById('btn-muse-refresh-accounts'),

  // True Crime Studio: chỉ giữ modal (closeAllModals dùng); các phần tử khác do true_crime.js tự tra
  modalTrueCrime: document.getElementById('modal-true-crime')
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

  async splitScript(projectId, text, options = {}) {
    try {
      const endpoint = projectId ? `${this.baseUrl}/projects/${projectId}/split-script` : `${this.baseUrl}/split-script`;
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, ...options })
      });
      if (res.ok) return await res.json();
      return await this._errorResult(res);
    } catch (e) {
      console.warn("API splitScript failed", e);
      return { success: false, detail: `Không kết nối được máy chủ: ${e.message || e}` };
    }
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
      throw new Error(err.detail || 'Lỗi sản xuất video dài');
    } catch (e) {
      console.error("API produceLongVideo failed", e);
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
      return null;
    } catch (e) {
      console.error("API generateThumbnail failed", e);
      return null;
    }
  },

  async getSeoPack(projectId) {
    try {
      const res = await fetch(`${this.baseUrl}/projects/${projectId}/seo-pack`);
      if (res.ok) return await res.json();
      return null;
    } catch (e) {
      console.error("API getSeoPack failed", e);
      return null;
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
  toast.className = 'pointer-events-auto transform transition-all duration-300 translate-y-2 opacity-0 flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl text-xs font-medium border max-w-sm';

  let iconHtml = '';
  if (type === 'success') {
    toast.classList.add('bg-[#14261e]', 'border-emerald-500/50', 'text-emerald-200');
    iconHtml = '<i class="fa-solid fa-circle-check text-emerald-400 text-sm"></i>';
  } else if (type === 'error') {
    toast.classList.add('bg-[#2d161a]', 'border-rose-500/50', 'text-rose-200');
    iconHtml = '<i class="fa-solid fa-circle-exclamation text-rose-400 text-sm"></i>';
  } else if (type === 'warning') {
    toast.classList.add('bg-[#2c2214]', 'border-amber-500/50', 'text-amber-200');
    iconHtml = '<i class="fa-solid fa-triangle-exclamation text-amber-400 text-sm"></i>';
  } else {
    toast.classList.add('bg-[#1a2035]', 'border-indigo-500/50', 'text-indigo-200');
    iconHtml = '<i class="fa-solid fa-circle-info text-indigo-400 text-sm"></i>';
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
  clearTimeout(ProjectSync.timer);
  ProjectSync.timer = setTimeout(() => { flushProjectSave({ silent: true }); }, AUTOSAVE_DELAY_MS);
}

// Lưu ngay (bỏ qua debounce). Trả về true nếu server đã có bản mới nhất.
async function flushProjectSave({ silent = false } = {}) {
  clearTimeout(ProjectSync.timer);
  const project = AppState.currentProject;
  if (!project || project.is_demo) return true;
  if (ProjectSync.inFlight) await ProjectSync.inFlight;
  if (!ProjectSync.dirty) return true;
  if (!AppState.serverOnline) {
    if (!silent) showToast("Máy chủ đang offline: thay đổi CHƯA được lưu. Sẽ tự lưu khi máy chủ online lại.", "warning", 7000);
    return false;
  }
  ProjectSync.dirty = false;
  ProjectSync.inFlight = API.saveProject(buildServerPayload(project));
  const saved = await ProjectSync.inFlight;
  ProjectSync.inFlight = null;
  if (saved && saved.id) return true;

  ProjectSync.dirty = true;
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

  // Set initial step view
  if (AppState.currentProject && AppState.currentProject.scenes && AppState.currentProject.scenes.length > 0) {
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
      DOM.backendStatusText.textContent = "FastAPI Backend Online (Port 8000)";
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
  renderCharacterCard();
  renderSettings();
  // Nút "Tạo bản tiếng Anh" (true_crime.js) hiện hay ẩn tuỳ dự án đang mở. Hook ở đây thay vì ở switchProject để
  // cũng đúng khi tải lại trang, tạo dự án mới hay nhập dự án.
  window.refreshLanguageVersionButton?.(AppState.currentProject);
}

function formatDisplayVoice(rawVoice) {
  if (!rawVoice) rawVoice = "vi-VN-NamMinhNeural";
  const str = String(rawVoice).trim();
  // Vietnamese voices identified FIRST
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
        <p class="text-xs text-gray-500 mt-1 max-w-sm mx-auto">Bấm "Nhập kịch bản truyện" để AI tự động chia cảnh, hoặc bấm "Thêm cảnh mới" để bắt đầu sáng tạo.</p>
        <div class="mt-4 flex items-center justify-center gap-2">
          <button onclick="openScriptModal()" class="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold shadow-md">
            <i class="fa-solid fa-wand-magic-sparkles mr-1"></i> Nhập kịch bản truyện
          </button>
        </div>
      </div>
    `;
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
      statusBadgeHtml = `<span class="text-[11px] bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-200 animate-pulse font-semibold flex items-center gap-1"><i class="fa-solid fa-spinner fa-spin"></i> Đang sinh AI... <button type="button" onclick="resetSceneImageStatus(${idx})" class="text-[9px] underline ml-1 text-indigo-900 cursor-pointer">Bỏ qua</button></span>`;
    } else if (hasVideo && hasVoice) {
      statusBadgeHtml = `<span class="text-[11px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-play text-emerald-600"></i> Đủ Voice & Video (10s)</span>`;
    } else if (sceneHasRealVisual(scene) && hasVoice) {
      statusBadgeHtml = `<span class="text-[11px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200 font-semibold"><i class="fa-solid fa-check mr-1"></i> Đủ Voice & Ảnh</span>`;
    } else if (hasVideo && !hasVoice) {
      statusBadgeHtml = `<span class="text-[11px] bg-purple-50 text-purple-700 px-2 py-0.5 rounded border border-purple-200 font-semibold"><i class="fa-solid fa-film mr-1"></i> Có Video (Chưa voice)</span>`;
    } else if (!sceneHasRealVisual(scene) && hasVoice) {
      statusBadgeHtml = `<span class="text-[11px] bg-amber-50 text-amber-700 px-2 py-0.5 rounded border border-amber-200 font-semibold"><i class="fa-solid fa-image mr-1"></i> Chưa có Ảnh/Video</span>`;
    } else if (hasImage && !hasVoice) {
      statusBadgeHtml = `<span class="text-[11px] bg-purple-50 text-purple-700 px-2 py-0.5 rounded border border-purple-200 font-semibold"><i class="fa-solid fa-microphone mr-1"></i> Chưa có Voice</span>`;
    } else {
      statusBadgeHtml = `<span class="text-[11px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-medium">Cảnh mới</span>`;
    }

    return `
      <div id="scene-card-${scene.id}" data-index="${idx}" class="scene-card group transition-all duration-200 rounded-xl p-3.5 border ${isSelected ? 'bg-indigo-50/70 border-indigo-500 shadow-md ring-2 ring-indigo-500/20' : 'bg-white border-slate-200 hover:border-slate-300 hover:shadow-xs'}">
        
        <!-- Card Top Bar -->
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="cursor-pointer font-bold text-[11px] px-2.5 py-0.5 rounded ${isSelected ? 'bg-indigo-600 text-white shadow-xs' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}" onclick="selectScene(${idx})">
              Cảnh #${idx + 1}
            </span>
            <span class="text-xs text-slate-500 font-mono"><i class="fa-regular fa-clock mr-1"></i> ${durStr}</span>
            ${statusBadgeHtml}
            ${warnBadgesHtml}
          </div>

          <div class="flex items-center gap-1.5">
            <!-- Ken Burns / Motion FX Selector -->
            <div class="relative">
              <select onchange="updateSceneKenBurns(${idx}, this.value)" class="text-xs bg-slate-50 hover:bg-slate-100 text-slate-700 rounded-lg px-2 py-1 border border-slate-300 focus:outline-none focus:border-indigo-500 cursor-pointer font-medium shadow-2xs">
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

            <!-- Move Up -->
            <button onclick="moveScene(${idx}, -1)" title="Di chuyển lên" class="text-slate-400 hover:text-slate-800 p-1 rounded hover:bg-slate-100 ${idx === 0 ? 'opacity-30 cursor-not-allowed' : ''}">
              <i class="fa-solid fa-arrow-up text-xs"></i>
            </button>
            <!-- Move Down -->
            <button onclick="moveScene(${idx}, 1)" title="Di chuyển xuống" class="text-slate-400 hover:text-slate-800 p-1 rounded hover:bg-slate-100 ${idx === scenes.length - 1 ? 'opacity-30 cursor-not-allowed' : ''}">
              <i class="fa-solid fa-arrow-down text-xs"></i>
            </button>
            <!-- Duplicate Scene -->
            <button onclick="duplicateScene(${idx})" title="Nhân bản cảnh" class="text-slate-400 hover:text-indigo-600 p-1 rounded hover:bg-slate-100">
              <i class="fa-solid fa-copy text-xs"></i>
            </button>
            <!-- Delete Scene -->
            <button onclick="deleteScene(${idx})" title="Xóa cảnh này" class="text-slate-400 hover:text-red-600 p-1 rounded hover:bg-slate-100">
              <i class="fa-solid fa-trash-can text-xs"></i>
            </button>
          </div>
        </div>

        <!-- Card Grid (Thumbnail/Video + Script Content) -->
        <div class="grid grid-cols-12 gap-3">
          
          <!-- Thumbnail & Video Column (4 cols) -->
          <div class="col-span-12 sm:col-span-4 relative rounded-xl overflow-hidden border border-slate-300 aspect-video bg-slate-900 flex items-center justify-center group/img shadow-2xs">
            ${hasVideo ? `
              <div class="absolute top-1.5 left-1.5 z-20 flex items-center bg-black/80 backdrop-blur-md p-0.5 rounded-lg border border-white/20 shadow-xs">
                <button type="button" onclick="setMediaViewMode(${idx}, 'image')" class="px-2 py-0.5 rounded text-[9px] font-bold ${!isShowingVideo ? 'bg-indigo-600 text-white shadow-2xs' : 'text-slate-300 hover:text-white'} transition cursor-pointer flex items-center gap-1" title="Chuyển sang xem Ảnh 2K">
                  <i class="fa-solid fa-image"></i>
                  <span>Ảnh</span>
                </button>
                <button type="button" onclick="setMediaViewMode(${idx}, 'video')" class="px-2 py-0.5 rounded text-[9px] font-bold ${isShowingVideo ? 'bg-purple-600 text-white shadow-2xs' : 'text-slate-300 hover:text-white'} transition cursor-pointer flex items-center gap-1" title="Chuyển sang xem Video chuyển động">
                  <i class="fa-solid fa-film"></i>
                  <span>Video</span>
                </button>
              </div>
            ` : ''}

            ${isShowingVideo && currentVideoUrl ? `
              <video src="${currentVideoUrl}${currentVideoUrl.includes('?') ? '&' : '?'}v=${encodeURIComponent(scene.updated_at || Date.now())}" class="w-full h-full object-cover rounded-xl" controls preload="metadata" playsinline></video>
            ` : (hasImage ? `
              <img src="${scene.image_url}" alt="Scene #${idx + 1}" class="w-full h-full object-cover" onerror="handleSceneImageError(this, ${idx})">
            ` : `
              <div class="w-full h-full bg-slate-100 flex flex-col items-center justify-center text-center p-2">
                <i class="fa-solid fa-mountain-sun text-2xl text-slate-400 mb-1"></i>
                <span class="text-[10px] text-slate-500 font-medium">Chưa có ảnh/video</span>
              </div>
            `)}

            ${isGenImage && !isShowingVideo ? `
              <div class="absolute inset-0 bg-white/85 backdrop-blur-xs flex flex-col items-center justify-center p-2 text-center z-10">
                <i class="fa-solid fa-spinner fa-spin text-xl text-indigo-600 mb-1"></i>
                <span class="text-[10px] text-indigo-900 font-bold mb-1">Đang sinh ảnh AI...</span>
                <button type="button" onclick="resetSceneImageStatus(${idx})" class="text-[9px] px-2 py-0.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded cursor-pointer">Bỏ qua</button>
              </div>
            ` : (isGenVideo && isShowingVideo ? `
              <div class="absolute inset-0 bg-white/85 backdrop-blur-xs flex flex-col items-center justify-center p-2 text-center z-10">
                <i class="fa-solid fa-spinner fa-spin text-xl text-purple-600 mb-1"></i>
                <span class="text-[10px] text-purple-900 font-bold mb-1">Đang sinh video AI...</span>
              </div>
            ` : '')}

            <!-- Badges -->
            <div class="absolute bottom-1 right-1 bg-black/75 px-1.5 py-0.5 rounded text-[9px] text-white font-mono z-10">
              ${isShowingVideo ? '10s Motion' : '16:9'}
            </div>
            
            <!-- Hover Action Buttons Overlay -->
            <div class="absolute inset-0 bg-slate-950/60 opacity-0 group-hover/img:opacity-100 flex items-center justify-center gap-1.5 transition duration-200 z-10">
              <button onclick="regenerateSceneImage(${idx})" title="Gen lại ảnh AI" class="p-1.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110">
                <i class="fa-solid fa-arrows-rotate"></i>
              </button>
              <button onclick="generateSceneWithMuse(${idx}, 'image')" title="Tạo ảnh 2K bằng Muse Fleet (tài khoản ảnh)" class="p-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110">
                <i class="fa-brands fa-meta"></i>
              </button>
              <button onclick="generateSceneWithMuse(${idx}, 'video')" title="Tạo video chuyển động bằng Muse Fleet (tài khoản video)" class="p-1.5 bg-purple-600 hover:bg-purple-500 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110">
                <i class="fa-solid fa-film"></i>
              </button>
              <button onclick="openMuseModalForScene(${idx})" title="Chọn video/ảnh từ Gallery Muse" class="p-1.5 bg-amber-600 hover:bg-amber-500 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110">
                <i class="fa-solid fa-photo-film"></i>
              </button>
              <label title="Tải ảnh riêng từ máy" class="p-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110 cursor-pointer">
                <i class="fa-solid fa-upload"></i>
                <input type="file" accept="image/*" class="hidden" onchange="uploadCustomSceneImage(${idx}, this)">
              </label>
              <label title="Tải video MP4 riêng từ máy" class="p-1.5 bg-purple-700 hover:bg-purple-600 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110 cursor-pointer">
                <i class="fa-solid fa-file-video"></i>
                <input type="file" accept="video/*" class="hidden" onchange="uploadCustomSceneVideo(${idx}, this)">
              </label>
              <button onclick="selectScene(${idx})" title="Xem trong Studio Player" class="p-1.5 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-white text-xs shadow-md transition transform hover:scale-110">
                <i class="fa-solid fa-play"></i>
              </button>
            </div>
          </div>

          <!-- Script & Voice Column (8 cols) -->
          <div class="col-span-12 sm:col-span-8 flex flex-col justify-between space-y-2">
            
            <!-- Voiceover Textarea -->
            <div>
              <div class="flex items-center justify-between text-[11px] text-slate-500 mb-1">
                <label class="font-bold uppercase tracking-wider text-slate-700">Lời thuyết minh (Voiceover):</label>
                <span class="text-[10px] text-slate-400 font-mono">${(scene.text || '').length} ký tự</span>
              </div>
              <textarea 
                oninput="updateSceneTextLive(${idx}, this.value)"
                onchange="updateSceneText(${idx}, this.value)" 
                class="w-full bg-slate-50 border border-slate-300 rounded-xl p-2.5 text-xs text-slate-800 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none resize-none h-16 leading-relaxed transition shadow-2xs font-normal"
                placeholder="Nhập lời đọc thuyết minh cho phân cảnh này..."
              >${escapeHtml(scene.text || '')}</textarea>
            </div>

            <!-- Dual Prompt Switcher: Image Prompt vs Video Motion Prompt -->
            <div>
              <div class="flex items-center justify-between text-[11px] text-slate-500 mb-1">
                <div class="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200">
                  <button 
                    type="button" 
                    onclick="switchScenePromptTab(${idx}, 'image')" 
                    id="btn-tab-img-${idx}" 
                    class="px-2.5 py-1 rounded-md text-[10px] font-extrabold ${(!scene.active_prompt_tab || scene.active_prompt_tab === 'image') ? 'bg-white text-indigo-700 shadow-2xs border border-indigo-200' : 'text-slate-500 hover:text-slate-800'} transition cursor-pointer flex items-center gap-1.5"
                    title="Chỉnh sửa mô tả hình ảnh tĩnh (Visual Prompt)"
                  >
                    <i class="fa-solid fa-image text-indigo-500 text-[10px]"></i>
                    <span>Prompt Ảnh (2K)</span>
                  </button>
                  <button 
                    type="button" 
                    onclick="switchScenePromptTab(${idx}, 'video')" 
                    id="btn-tab-vid-${idx}" 
                    class="px-2.5 py-1 rounded-md text-[10px] font-extrabold ${scene.active_prompt_tab === 'video' ? 'bg-white text-purple-700 shadow-2xs border border-purple-200' : 'text-slate-500 hover:text-slate-800'} transition cursor-pointer flex items-center gap-1.5"
                    title="Chỉnh sửa chuyển động nhân vật & góc quay (Video Motion Prompt)"
                  >
                    <i class="fa-solid fa-film text-purple-500 text-[10px]"></i>
                    <span>Prompt Video (Chuyển động)</span>
                  </button>
                </div>
                <span class="text-[9px] font-mono ${scene.active_prompt_tab === 'video' ? 'text-purple-600 font-bold' : 'text-slate-400'}" id="prompt-spec-${idx}">
                  ${scene.active_prompt_tab === 'video' ? '🎬 5s Motion • Nhân vật & Máy quay' : '8K • Cinema Masterpiece'}
                </span>
              </div>

              <!-- Textarea for Image Prompt -->
              <div id="prompt-container-img-${idx}" class="${(!scene.active_prompt_tab || scene.active_prompt_tab === 'image') ? '' : 'hidden'}">
                <textarea 
                  oninput="updateSceneVisualPromptLive(${idx}, this.value)"
                  onchange="updateSceneVisualPrompt(${idx}, this.value)" 
                  class="w-full bg-slate-50 border border-slate-300 rounded-lg p-2 text-[11px] text-slate-700 focus:bg-white focus:border-indigo-500 focus:outline-none font-mono transition shadow-2xs resize-none h-14 leading-relaxed"
                  placeholder="Mô tả bối cảnh hình ảnh AI 2K/8K (Image Prompt)..."
                >${escapeHtml(scene.visual_prompt || scene.image_prompt || '')}</textarea>
              </div>

              <!-- Textarea for Video Motion Prompt -->
              <div id="prompt-container-vid-${idx}" class="${scene.active_prompt_tab === 'video' ? '' : 'hidden'}">
                <textarea 
                  oninput="updateSceneVideoPromptLive(${idx}, this.value)"
                  onchange="updateSceneVideoPrompt(${idx}, this.value)" 
                  class="w-full bg-purple-50/40 border border-purple-200 rounded-lg p-2 text-[11px] text-purple-900 focus:bg-white focus:border-purple-500 focus:outline-none font-mono transition shadow-2xs resize-none h-14 leading-relaxed"
                  placeholder="Mô tả hành động nhân vật & chuyển động máy quay (ví dụ: thám tử bước đi chậm rãi trong mưa, áo khoác bay theo gió, đèn xe cảnh sát nhấp nháy, camera tracking theo bước chân)..."
                >${escapeHtml(scene.video_prompt || '')}</textarea>
              </div>
            </div>

            <!-- Mini Audio Player & Controls -->
            <div class="flex items-center justify-between pt-2 border-t border-slate-100 flex-wrap gap-2">
              <div class="flex items-center gap-2">
                <button 
                  onclick="playSceneVoice(${idx})" 
                  class="w-7 h-7 rounded-full ${isSelected && AppState.isPlaying ? 'bg-indigo-600 text-white animate-pulse' : 'bg-indigo-600 hover:bg-indigo-700 text-white'} flex items-center justify-center text-xs transition shadow-xs"
                  title="Nghe thử voice đọc"
                >
                  <i class="fa-solid ${isSelected && AppState.isPlaying ? 'fa-pause' : 'fa-play'} ml-0.5"></i>
                </button>
                <div class="w-24 sm:w-36 h-1.5 bg-slate-200 rounded-full overflow-hidden cursor-pointer" onclick="seekSceneAudio(${idx}, event)">
                  <div id="scene-progress-${idx}" class="h-full bg-indigo-600 w-0 transition-all duration-100"></div>
                </div>
                <span class="text-[10px] font-mono text-slate-500 font-medium">${durStr}</span>
              </div>

              <div class="flex items-center gap-1.5 flex-wrap">
                <button 
                  onclick="regenerateSceneVoice(${idx})" 
                  class="text-[10px] text-indigo-700 hover:text-indigo-900 font-bold flex items-center gap-1 transition px-2 py-1 rounded-lg bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 cursor-pointer"
                  title="Tạo lại file âm thanh Edge-TTS"
                >
                  <i class="fa-solid fa-rotate-right ${isGenVoice ? 'fa-spin' : ''}"></i>
                  <span>Voice</span>
                </button>
                <button 
                  onclick="generateSceneWithMuse(${idx}, 'image')" 
                  class="text-[10px] text-blue-700 hover:text-blue-900 font-bold flex items-center gap-1 transition px-2 py-1 rounded-lg bg-blue-50 border border-blue-200 hover:bg-blue-100 cursor-pointer shadow-2xs"
                  title="Tạo ảnh 2K riêng cảnh này bằng Muse Fleet (tài khoản ảnh)"
                >
                  <i class="fa-brands fa-meta text-xs text-blue-600"></i>
                  <span>Muse 2K</span>
                </button>
                <button 
                  onclick="generateSceneWithMuse(${idx}, 'video')" 
                  class="text-[10px] text-purple-700 hover:text-purple-900 font-bold flex items-center gap-1 transition px-2 py-1 rounded-lg bg-purple-50 border border-purple-200 hover:bg-purple-100 cursor-pointer shadow-2xs"
                  title="Tạo Video 5s riêng cảnh này bằng Muse Fleet (tài khoản video)"
                >
                  <i class="fa-solid fa-film text-xs text-purple-600"></i>
                  <span>Muse Video</span>
                </button>
              </div>
            </div>

          </div>

        </div>

      </div>
    `;
  }).join('');
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
    DOM.previewKbBadge.innerHTML = `<i class="fa-solid fa-film text-purple-400 mr-1"></i> Video Motion`;
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

function renderCharacterCard() {
  const project = AppState.currentProject;
  const char = project?.character;
  const anchor = project?.character_anchor;
  const isTrueCrime = project?.style_preset === 'neo_noir_silhouette' || project?.id?.includes('crime');
  const card = DOM.characterConsistencyCard || document.getElementById('character-consistency-card');
  const statusBadge = DOM.charStatusBadge || document.getElementById('char-status-badge');

  if (isTrueCrime || (!char && !anchor)) {
    if (card) card.classList.add('hidden');
    if (statusBadge) {
      statusBadge.className = "text-[10px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded border border-slate-200 font-semibold";
      statusBadge.innerHTML = '<i class="fa-solid fa-ban mr-1"></i> Tắt';
    }
    if (DOM.charNameDisplay) DOM.charNameDisplay.textContent = "Không áp dụng (True Crime / Tự do)";
    if (DOM.charPromptPreview) DOM.charPromptPreview.textContent = "Không sử dụng neo nhân vật cho dự án này.";
    if (DOM.charThumbElem) DOM.charThumbElem.classList.add('hidden');
    if (DOM.charIconFallback) DOM.charIconFallback.classList.remove('hidden');
    return;
  }

  // Active character for anime/fantasy
  if (card) card.classList.remove('hidden');
  if (statusBadge) {
    statusBadge.className = "text-[10px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200 font-bold";
    statusBadge.innerHTML = '<i class="fa-solid fa-check mr-1"></i> Bật';
  }
  if (DOM.charNameDisplay) DOM.charNameDisplay.textContent = char?.name || anchor || "Chưa đặt tên";
  if (DOM.charPromptPreview) DOM.charPromptPreview.textContent = char?.prompt || anchor || "Chưa có mô tả đặc điểm nhân vật.";

  if (char?.avatar) {
    DOM.charThumbElem.src = char.avatar;
    DOM.charThumbElem.classList.remove('hidden');
    DOM.charIconFallback.classList.add('hidden');
  } else {
    DOM.charThumbElem.classList.add('hidden');
    DOM.charIconFallback.classList.remove('hidden');
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

  // If all ready, keep advanced accordion collapsed by default to avoid confusion
  const accordionBody = DOM.assetAccordionBody || document.getElementById('asset-accordion-body');
  if (isAllReady && accordionBody && !accordionBody.dataset.userOpened) {
    accordionBody.classList.add('hidden');
    const chevron = DOM.assetAccordionChevron || document.getElementById('asset-accordion-chevron');
    if (chevron) chevron.classList.remove('rotate-180');
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
    DOM.selectProjectStyle.value = project.style_preset || "cinematic_realistic";
  }

  updateAssetReadiness();
}

// ================= EVENT LISTENERS =================
function bindEventListeners() {
  // Step 1 Event Listeners
  DOM.step1ScriptTextarea?.addEventListener('input', handleStep1ScriptInput);
  DOM.btnStep1ProcessScript?.addEventListener('click', handleStep1ProcessScript);

  // Step 1 Character Reference Image Event Listeners
  DOM.step1CharRefDropzone?.addEventListener('click', () => DOM.step1CharRefFileInput?.click());
  DOM.step1CharRefFileInput?.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleCharRefFileSelect(e.target.files[0]);
    }
  });
  DOM.step1CharRefDropzone?.addEventListener('dragover', (e) => {
    e.preventDefault();
    DOM.step1CharRefDropzone?.classList.add('border-indigo-500', 'bg-indigo-50');
  });
  DOM.step1CharRefDropzone?.addEventListener('dragleave', (e) => {
    e.preventDefault();
    DOM.step1CharRefDropzone?.classList.remove('border-indigo-500', 'bg-indigo-50');
  });
  DOM.step1CharRefDropzone?.addEventListener('drop', (e) => {
    e.preventDefault();
    DOM.step1CharRefDropzone?.classList.remove('border-indigo-500', 'bg-indigo-50');
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleCharRefFileSelect(e.dataTransfer.files[0]);
    }
  });
  DOM.btnStep1CharRefRemove?.addEventListener('click', handleCharRefRemove);
  DOM.btnStep1CharRefApplyUrl?.addEventListener('click', handleCharRefUrlApply);
  DOM.step1CharRefUrl?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleCharRefUrlApply();
    }
  });

  const charPresetSelect = document.getElementById('step1-char-preset-select');
  if (charPresetSelect) {
    charPresetSelect.addEventListener('change', () => {
      const val = charPresetSelect.value;
      if (val === 'custom') {
        if (DOM.step1CharName && DOM.step1CharName.value.includes("Võ Giả Cuồng Nộ")) DOM.step1CharName.value = "";
        if (DOM.step1CharAnchor && DOM.step1CharAnchor.value.includes("Tattered dark martial arts")) DOM.step1CharAnchor.value = "";
      } else if (val === 'murata_fighter') {
        if (DOM.step1CharName) DOM.step1CharName.value = "Võ Giả Cuồng Nộ (Murata Fighter)";
        if (DOM.step1CharAnchor) DOM.step1CharAnchor.value = "Tattered dark martial arts dogi gi pants, bare muscular athletic chest, scarred arms wrapped in white combat tape, radiant fiery red shockwave energy fists";
        if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "manga_murata_battle";
      } else if (val === 'spartan_leon') {
        if (DOM.step1CharName) DOM.step1CharName.value = "Dũng Tướng Leon (Spartan Champion)";
        if (DOM.step1CharAnchor) DOM.step1CharAnchor.value = "Spartan hoplite champion, sculpted bronze muscle cuirass with filigree, golden Corinthian helmet with plume, circular bronze hoplon shield with embossed sun, sharp dory spear";
        if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "spartan_epic_mythology";
      } else if (val === 'paladin_kai') {
        if (DOM.step1CharName) DOM.step1CharName.value = "Dũng Sĩ Kai (Paladin)";
        if (DOM.step1CharAnchor) DOM.step1CharAnchor.value = "Silver full plate armor with glowing cyan turquoise gemstones, crimson velvet cape, two-handed carved gold broadsword";
        if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "fantasy_paladin_armor";
      } else if (val === 'roman_titus') {
        if (DOM.step1CharName) DOM.step1CharName.value = "Chiến Binh Titus (Quân Đoàn La Mã)";
        if (DOM.step1CharAnchor) DOM.step1CharAnchor.value = "Roman legionary soldier, polished iron lorica segmentata, bronze galea helmet with red crest, curved red scutum shield with golden bull, pilum spear";
        if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "roman_legionary_epic";
      } else if (val === 'kingdom_shin') {
        if (DOM.step1CharName) DOM.step1CharName.value = "Tướng Quân Shin (Kingdom)";
        if (DOM.step1CharAnchor) DOM.step1CharAnchor.value = "Young warrior general, pale blue scale lamellar armor, messy black ponytail, massive broadsword carried on back, determined battle smirk";
        if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "manga_historical_war";
      } else if (val === 'tienhiep_lam') {
        if (DOM.step1CharName) DOM.step1CharName.value = "Lâm (Chiến binh áo lam)";
        if (DOM.step1CharAnchor) DOM.step1CharAnchor.value = "Asian warrior boy, sharp amber eyes, spiky black hair, dark navy tunic, glowing blue talisman necklace";
        if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "anime";
      }
    });
  }
  
  document.querySelectorAll('.btn-step1-sample').forEach(btn => {
    btn.addEventListener('click', () => {
      const sampleKey = btn.getAttribute('data-sample');
      if (SAMPLE_STORIES[sampleKey] && DOM.step1ScriptTextarea) {
        DOM.step1ScriptTextarea.value = SAMPLE_STORIES[sampleKey];
        handleStep1ScriptInput();

        const charSelect = document.getElementById('step1-char-preset-select');
        if (sampleKey === 'us_murata_battle') {
          if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "manga_murata_battle";
          if (charSelect) charSelect.value = "murata_fighter";
          if (DOM.step1CharName) DOM.step1CharName.value = "Võ Giả Cuồng Nộ (Murata Fighter)";
          if (DOM.step1CharAnchor) DOM.step1CharAnchor.value = "Tattered dark martial arts dogi gi pants, bare muscular athletic chest, scarred arms wrapped in white combat tape, radiant fiery red shockwave energy fists";
          if (DOM.selectVoice) DOM.selectVoice.value = "en-US-BrianMultilingualNeural";
        } else if (sampleKey === 'us_spartan') {
          if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "spartan_epic_mythology";
          if (charSelect) charSelect.value = "spartan_leon";
          if (DOM.step1CharName) DOM.step1CharName.value = "Dũng Tướng Leon (Spartan Champion)";
          if (DOM.step1CharAnchor) DOM.step1CharAnchor.value = "Spartan hoplite champion, sculpted bronze muscle cuirass with filigree, golden Corinthian helmet with plume, circular bronze hoplon shield with embossed sun, sharp dory spear";
          if (DOM.selectVoice) DOM.selectVoice.value = "en-US-AndrewMultilingualNeural";
        } else if (sampleKey === 'paladin') {
          if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "fantasy_paladin_armor";
          if (charSelect) charSelect.value = "paladin_kai";
          if (DOM.step1CharName) DOM.step1CharName.value = "Dũng Sĩ Kai (Paladin)";
          if (DOM.step1CharAnchor) DOM.step1CharAnchor.value = "Silver full plate armor with glowing cyan turquoise gemstones, crimson velvet cape, two-handed carved gold broadsword";
          if (DOM.selectVoice) DOM.selectVoice.value = "vi-VN-NamMinhNeural";
        } else if (sampleKey === 'kingdom') {
          if (DOM.step1StyleSelect) DOM.step1StyleSelect.value = "manga_historical_war";
          if (charSelect) charSelect.value = "kingdom_shin";
          if (DOM.step1CharName) DOM.step1CharName.value = "Tướng Quân Shin (Kingdom)";
          if (DOM.step1CharAnchor) DOM.step1CharAnchor.value = "Young warrior general, pale blue scale lamellar armor, messy black ponytail, massive broadsword carried on back, determined battle smirk";
          if (DOM.selectVoice) DOM.selectVoice.value = "vi-VN-NamMinhNeural";
        }

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
  DOM.btnProduceLongVideo?.addEventListener('click', startProduceLongVideo);

  // Asset Regeneration Accordion
  DOM.btnToggleAssetAccordion?.addEventListener('click', () => {
    const body = DOM.assetAccordionBody || document.getElementById('asset-accordion-body');
    const chevron = DOM.assetAccordionChevron || document.getElementById('asset-accordion-chevron');
    if (body) {
      const isHidden = body.classList.contains('hidden');
      if (isHidden) {
        body.classList.remove('hidden');
        body.dataset.userOpened = "true";
        if (chevron) chevron.classList.add('rotate-180');
      } else {
        body.classList.add('hidden');
        delete body.dataset.userOpened;
        if (chevron) chevron.classList.remove('rotate-180');
      }
    }
  });

  DOM.btnRegenAllImages?.addEventListener('click', handleRegenAllImages);
  DOM.btnRegenAllVoices?.addEventListener('click', handleRegenAllVoices);

  // Step 4 Actions
  DOM.btnCinemaOpenFolder?.addEventListener('click', () => {
    if (AppState.currentProject) {
      API.openFolder(AppState.currentProject.id);
      showToast("Đang mở thư mục video trên Windows Explorer...", "info");
    }
  });

  // Save Project
  DOM.btnSaveProject?.addEventListener('click', handleSaveProject);

  // Comic Slicer Modal Actions
  DOM.btnOpenComicModal?.addEventListener('click', openComicModal);
  DOM.btnCloseComicModal?.addEventListener('click', closeComicModal);
  DOM.btnCancelComicModal?.addEventListener('click', closeComicModal);
  DOM.btnResetComic?.addEventListener('click', resetComicModal);

  // Comic Dropzone & File Input
  DOM.comicDropzone?.addEventListener('click', () => DOM.comicFileInput?.click());
  DOM.comicFileInput?.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleComicFileSelect(e.target.files[0]);
    }
  });

  DOM.comicDropzone?.addEventListener('dragover', (e) => {
    e.preventDefault();
    DOM.comicDropzone?.classList.add('border-amber-500', 'bg-amber-100/50');
  });
  DOM.comicDropzone?.addEventListener('dragleave', (e) => {
    e.preventDefault();
    DOM.comicDropzone?.classList.remove('border-amber-500', 'bg-amber-100/50');
  });
  DOM.comicDropzone?.addEventListener('drop', (e) => {
    e.preventDefault();
    DOM.comicDropzone?.classList.remove('border-amber-500', 'bg-amber-100/50');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleComicFileSelect(e.dataTransfer.files[0]);
    }
  });

  // Comic Layout Mode Change
  DOM.comicLayoutMode?.addEventListener('change', (e) => {
    if (e.target.value === 'strip') {
      DOM.comicReadingOrderBox?.classList.add('hidden');
    } else {
      DOM.comicReadingOrderBox?.classList.remove('hidden');
    }
  });

  // Comic Quick Samples
  DOM.btnSampleMangaGrid?.addEventListener('click', () => loadComicSample('grid'));
  DOM.btnSampleWebtoonStrip?.addEventListener('click', () => loadComicSample('strip'));

  // Comic Slice & Tab Actions
  DOM.btnStartSlice?.addEventListener('click', handleStartSlice);
  DOM.tabBtnPanels?.addEventListener('click', () => switchComicResultTab('panels'));
  DOM.tabBtnAnnotated?.addEventListener('click', () => switchComicResultTab('annotated'));

  // Import Comic to Storyboard
  DOM.btnImportComicToStoryboard?.addEventListener('click', handleImportComicToStoryboard);

  // Script Modal Actions
  DOM.btnOpenScriptModal?.addEventListener('click', openScriptModal);
  DOM.btnCloseScriptModal?.addEventListener('click', closeScriptModal);
  DOM.btnCancelScriptModal?.addEventListener('click', closeScriptModal);
  DOM.btnSubmitScriptSplit?.addEventListener('click', handleSubmitScriptSplit);
  DOM.importScriptTextarea?.addEventListener('input', handleScriptInputCount);

  // Quick Sample Stories
  document.querySelectorAll('.btn-sample-story').forEach(btn => {
    btn.addEventListener('click', () => {
      const sampleKey = btn.getAttribute('data-sample');
      if (SAMPLE_STORIES[sampleKey] && DOM.importScriptTextarea) {
        DOM.importScriptTextarea.value = SAMPLE_STORIES[sampleKey];
        handleScriptInputCount();
        showToast(`Đã nạp kịch bản mẫu: ${btn.textContent.trim()}`, "info");
      }
    });
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
  DOM.btnRefreshSeoPack?.addEventListener('click', async () => {
    await loadCinemaYouTubePackage();
    showToast(AppState.serverOnline ? "Đã tải lại gói SEO (tiêu đề, mô tả, thẻ) từ máy chủ." : "Máy chủ đang offline, chưa tải lại được gói SEO.", AppState.serverOnline ? "info" : "warning");
  });
  DOM.btnGenerateCustomThumbnail?.addEventListener('click', handleGenerateCustomThumbnail);
  DOM.btnCopySeoTitle?.addEventListener('click', () => copyToClipboard('input-seo-title', 'Đã sao chép tiêu đề YouTube!'));
  DOM.btnCopySeoDesc?.addEventListener('click', () => copyToClipboard('textarea-seo-desc', 'Đã sao chép mô tả YouTube!'));
  DOM.btnCopySeoTags?.addEventListener('click', () => copyToClipboard('input-seo-tags', 'Đã sao chép thẻ từ khóa YouTube!'));

  // Character Modal
  DOM.btnEditCharacter?.addEventListener('click', openCharacterModal);
  DOM.btnCloseCharacterModal?.addEventListener('click', closeCharacterModal);
  DOM.btnCancelCharModal?.addEventListener('click', closeCharacterModal);
  DOM.btnSaveCharacter?.addEventListener('click', handleSaveCharacter);

  // Project Dropdown / Manager
  DOM.btnProjectDropdown?.addEventListener('click', openProjectModal);
  DOM.btnCloseProjectModal?.addEventListener('click', closeProjectModal);
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
    e.preventDefault();
    togglePreviewPlayback();
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault();
    handleSaveProject();
  } else if (e.key === 'Escape') {
    closeAllModals();
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

function updateSceneVideoPrompt(index, newPrompt) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return;

  project.scenes[index].video_prompt = newPrompt;
  saveStateToLocal();
}

function updateSceneVideoPromptLive(index, newPrompt) {
  const project = AppState.currentProject;
  if (!project || !project.scenes[index]) return;

  project.scenes[index].video_prompt = newPrompt;
}

function switchScenePromptTab(index, tab) {
  const project = AppState.currentProject;
  if (!project || !project.scenes || !project.scenes[index]) return;
  const scene = project.scenes[index];
  scene.active_prompt_tab = tab;

  // Tự động khởi tạo prompt chuyển động điện ảnh nếu chưa có
  if (tab === 'video' && (!scene.video_prompt || scene.video_prompt.trim() === '')) {
    const rawImgPrompt = scene.image_prompt || scene.visual_prompt || scene.text || "";
    scene.video_prompt = `${rawImgPrompt}, cinematic continuous human walking motion, person moving forward through the scene, natural dynamic character movement, camera tracking front shot, fluid realistic motion`;
    saveStateToLocal();
  }

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
      tabVidBtn.className = "px-2.5 py-1 rounded-md text-[10px] font-extrabold bg-white text-purple-700 shadow-2xs border border-purple-200 transition cursor-pointer flex items-center gap-1.5";
    }
    if (containerImg) containerImg.classList.add('hidden');
    if (containerVid) {
      containerVid.classList.remove('hidden');
      const vidTa = containerVid.querySelector('textarea');
      if (vidTa) {
        vidTa.value = scene.video_prompt || '';
      }
    }
    if (specBadge) {
      specBadge.textContent = "🎬 5s Motion • Nhân vật & Máy quay";
      specBadge.className = "text-[9px] font-mono text-purple-600 font-bold";
    }
  } else {
    if (tabImgBtn) {
      tabImgBtn.className = "px-2.5 py-1 rounded-md text-[10px] font-extrabold bg-white text-indigo-700 shadow-2xs border border-indigo-200 transition cursor-pointer flex items-center gap-1.5";
    }
    if (tabVidBtn) {
      tabVidBtn.className = "px-2.5 py-1 rounded-md text-[10px] font-bold text-slate-500 hover:text-slate-800 transition cursor-pointer flex items-center gap-1.5";
    }
    if (containerVid) containerVid.classList.add('hidden');
    if (containerImg) {
      containerImg.classList.remove('hidden');
    }
    if (specBadge) {
      specBadge.textContent = "8K • Cinema Masterpiece";
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
  // Máy chủ tự ghép character_anchor; chỉ thêm mô tả nhân vật khi nó khác anchor (tránh lặp hai lần)
  if (char && char.prompt && char.prompt !== project.character_anchor) {
    finalPrompt = `${char.prompt}, ${finalPrompt}`;
  }

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

function openMuseModalForScene(index) {
  AppState.selectedSceneIndex = index;
  openMuseModal();
  showToast(`Đang mở Gallery Muse cho Cảnh #${index + 1}. Bấm [📌 Gắn vào Cảnh #${index + 1}] để chọn!`, "info");
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
  closeMuseModal();
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
    btn.className = "absolute w-14 h-14 rounded-full bg-indigo-600/75 hover:bg-indigo-600 text-white flex items-center justify-center text-xl shadow-2xl transition-all duration-300 opacity-0 hover:opacity-100 cursor-pointer z-20";
    btn.title = "Tạm dừng";
  } else {
    icon.className = "fa-solid fa-play ml-0.5 text-xl";
    btn.className = "absolute w-14 h-14 rounded-full bg-indigo-600/90 hover:bg-indigo-600 text-white flex items-center justify-center text-xl shadow-2xl transition-all duration-300 opacity-90 hover:opacity-100 transform hover:scale-110 active:scale-95 cursor-pointer z-20";
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
  if (DOM.iconPreviewVoice) DOM.iconPreviewVoice.className = "fa-solid fa-volume-high text-indigo-600 text-xs";
  if (DOM.textPreviewVoice) DOM.textPreviewVoice.textContent = "Nghe thử";
  if (DOM.btnPreviewVoiceSample) {
    DOM.btnPreviewVoiceSample.classList.remove("bg-indigo-600", "text-white");
    DOM.btnPreviewVoiceSample.classList.add("bg-indigo-50", "text-indigo-700");
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
      DOM.btnPreviewVoiceSample.classList.remove("bg-indigo-50", "text-indigo-700");
      DOM.btnPreviewVoiceSample.classList.add("bg-indigo-600", "text-white");
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

// ================= COMIC & WEBTOON SLICER CONTROLLER =================
function openComicModal() {
  if (!DOM.modalComicSlicer) return;
  DOM.modalComicSlicer.classList.remove('hidden');
  if (!AppState.comicState.slicedPanels || AppState.comicState.slicedPanels.length === 0) {
    resetComicModal();
  }
}

function closeComicModal() {
  if (!DOM.modalComicSlicer) return;
  DOM.modalComicSlicer.classList.add('hidden');
}

function resetComicModal() {
  AppState.comicState.selectedFile = null;
  AppState.comicState.slicedPanels = [];
  AppState.comicState.annotatedPreviewUrl = null;
  AppState.comicState.isSlicing = false;
  AppState.comicState.activeTab = 'panels';

  if (DOM.comicFileInput) DOM.comicFileInput.value = '';
  if (DOM.comicSelectedFileInfo) {
    DOM.comicSelectedFileInfo.textContent = '';
    DOM.comicSelectedFileInfo.classList.add('hidden');
  }
  if (DOM.btnStartSlice) {
    DOM.btnStartSlice.disabled = true;
    DOM.btnStartSlice.innerHTML = '<i class="fa-solid fa-scissors mr-1.5"></i> <span>Phân tích & Cắt khung tranh (OpenCV)</span>';
  }
  if (DOM.comicUploadSection) DOM.comicUploadSection.classList.remove('hidden');
  if (DOM.comicSliceLoading) DOM.comicSliceLoading.classList.add('hidden');
  if (DOM.comicResultsSection) DOM.comicResultsSection.classList.add('hidden');
  if (DOM.btnResetComic) DOM.btnResetComic.classList.add('hidden');
  if (DOM.btnImportComicToStoryboard) DOM.btnImportComicToStoryboard.disabled = true;
  if (DOM.importCountLabel) DOM.importCountLabel.textContent = '0';
  if (DOM.comicPanelsTabContent) DOM.comicPanelsTabContent.innerHTML = '';
}

function handleComicFileSelect(file) {
  if (!file) return;
  if (!file.type.startsWith('image/')) {
    showToast("Vui lòng chọn file hình ảnh (JPG, PNG, WebP)!", "warning");
    return;
  }

  AppState.comicState.selectedFile = file;
  const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
  if (DOM.comicSelectedFileInfo) {
    DOM.comicSelectedFileInfo.textContent = `📁 ${file.name} (${sizeMb} MB)`;
    DOM.comicSelectedFileInfo.classList.remove('hidden');
  }
  if (DOM.btnStartSlice) {
    DOM.btnStartSlice.disabled = false;
  }
}

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

    if (type === 'strip') {
      if (DOM.comicLayoutMode) DOM.comicLayoutMode.value = 'strip';
      if (DOM.comicReadingOrderBox) DOM.comicReadingOrderBox.classList.add('hidden');
    } else {
      if (DOM.comicLayoutMode) DOM.comicLayoutMode.value = 'grid';
      if (DOM.comicReadingOrderBox) DOM.comicReadingOrderBox.classList.remove('hidden');
    }

    handleComicFileSelect(file);
    // Nút mẫu ở Bước 1 dùng chung hàm này: cập nhật cả ô file và nút "Cắt khung" của Bước 1
    if (DOM.step1ComicMode) DOM.step1ComicMode.value = type === 'strip' ? 'strip' : 'grid';
    handleStep1ComicFileSelect(file);
    showToast(`Đã nạp ảnh mẫu: ${escapeHtml(filename)}`, "info");
  } catch (err) {
    console.error("loadComicSample failed", err);
    showToast("Không tìm thấy file ảnh mẫu trên máy chủ", "warning");
  }
}

async function handleStartSlice() {
  const file = AppState.comicState.selectedFile;
  if (!file) {
    showToast("Vui lòng chọn hoặc kéo thả ảnh truyện tranh trước!", "warning");
    return;
  }

  const mode = DOM.comicLayoutMode?.value || 'grid';
  const readingOrder = DOM.comicReadingOrder?.value || 'ltr';
  const minAreaRatio = parseFloat(DOM.comicMinArea?.value || '0.03');
  const projectId = AppState.currentProject?.id || null;

  if (DOM.comicUploadSection) DOM.comicUploadSection.classList.add('hidden');
  if (DOM.comicSliceLoading) DOM.comicSliceLoading.classList.remove('hidden');
  if (DOM.btnStartSlice) DOM.btnStartSlice.disabled = true;

  try {
    const result = await API.sliceComic(file, mode, readingOrder, minAreaRatio, projectId);
    if (!result || !result.success) {
      throw new Error(result?.error || "Không thể cắt khung tranh từ ảnh này");
    }

    AppState.comicState.slicedPanels = result.panels || [];
    AppState.comicState.annotatedPreviewUrl = result.annotated_preview_url || null;

    // Display Results
    if (DOM.comicSliceLoading) DOM.comicSliceLoading.classList.add('hidden');
    if (DOM.comicResultsSection) DOM.comicResultsSection.classList.remove('hidden');
    if (DOM.btnResetComic) DOM.btnResetComic.classList.remove('hidden');

    if (DOM.comicPanelCount) DOM.comicPanelCount.textContent = result.total_panels;
    if (DOM.comicModeBadge) {
      const modeText = result.mode === 'strip' ? 'Webtoon Strip (Cuộn dọc)' : `Manga Grid (${result.reading_order.toUpperCase()})`;
      DOM.comicModeBadge.textContent = `${modeText} • ${result.source_dimensions?.width}x${result.source_dimensions?.height}px`;
    }

    // Set annotated image
    if (DOM.comicAnnotatedImg && result.annotated_preview_url) {
      DOM.comicAnnotatedImg.src = result.annotated_preview_url;
    }

    // Render panel cards
    renderComicPanelCards(result.panels);

    // Switch to panels tab initially
    switchComicResultTab('panels');

    showToast(`Bóc tách thành công ${result.total_panels} khung tranh!`, "success");
  } catch (err) {
    console.error("handleStartSlice error", err);
    if (DOM.comicSliceLoading) DOM.comicSliceLoading.classList.add('hidden');
    if (DOM.comicUploadSection) DOM.comicUploadSection.classList.remove('hidden');
    if (DOM.btnStartSlice) DOM.btnStartSlice.disabled = false;
    showToast(`Lỗi cắt ảnh: ${escapeHtml(err.message || err)}`, "error");
  }
}

function renderComicPanelCards(panels) {
  const container = DOM.comicPanelsTabContent;
  if (!container) return;

  if (!panels || panels.length === 0) {
    container.innerHTML = `<div class="col-span-full py-8 text-center text-slate-400">Không tìm thấy khung tranh nào phù hợp.</div>`;
    return;
  }

  container.innerHTML = panels.map((p, idx) => {
    const isSelected = p.selected !== false;
    const isWide = p.is_wide || (p.aspect_ratio > 1.5);
    const motion = p.camera_motion || (isWide ? 'pan_right' : 'zoom_in');

    const motionBadgeColor = isWide
      ? 'bg-blue-50 text-blue-700 border-blue-200'
      : 'bg-purple-50 text-purple-700 border-purple-200';

    return `
      <div class="comic-panel-card bg-white border border-slate-200 rounded-xl p-3 shadow-xs hover:border-amber-400 hover:shadow-md transition flex flex-col gap-2.5 relative group" data-panel-index="${idx}">
        <!-- Top bar: Checkbox + Panel # + Aspect Ratio badge -->
        <div class="flex items-center justify-between">
          <label class="flex items-center gap-1.5 cursor-pointer select-none">
            <input type="checkbox" class="comic-panel-cb rounded text-amber-600 focus:ring-amber-500" data-idx="${idx}" ${isSelected ? 'checked' : ''}>
            <span class="font-bold text-slate-800 text-xs">Cảnh #${p.index}</span>
          </label>
          <span class="text-[10px] font-mono px-2 py-0.5 rounded-full border ${motionBadgeColor} font-semibold">
            AR: ${p.aspect_ratio} (${isWide ? 'Rộng' : 'Dọc/Vuông'})
          </span>
        </div>

        <!-- Thumbnail Image with Hover Zoom -->
        <div class="w-full aspect-video bg-slate-900 rounded-lg overflow-hidden relative border border-slate-200 flex items-center justify-center">
          <img src="${p.image_url}" alt="Panel ${p.index}" class="w-full h-full object-contain group-hover:scale-105 transition-transform duration-300">
          <span class="absolute bottom-1 right-1 text-[9px] bg-black/70 text-white font-mono px-1.5 py-0.5 rounded backdrop-blur-xs">
            ${p.width}x${p.height}
          </span>
        </div>

        <!-- Camera Motion Selector -->
        <div>
          <label class="text-[11px] text-slate-500 font-semibold block mb-0.5">Góc quay Ken Burns:</label>
          <select class="comic-panel-motion-select w-full bg-slate-50 border border-slate-300 rounded-lg p-1.5 text-xs text-slate-800 font-medium focus:border-amber-500" data-idx="${idx}">
            <option value="pan_right" ${motion === 'pan_right' ? 'selected' : ''}>Pan Phải (Khung ngang)</option>
            <option value="pan_left" ${motion === 'pan_left' ? 'selected' : ''}>Pan Trái (Khung ngang)</option>
            <option value="zoom_in" ${motion === 'zoom_in' ? 'selected' : ''}>Zoom In (Cận cảnh / Kịch tính)</option>
            <option value="zoom_out" ${motion === 'zoom_out' ? 'selected' : ''}>Zoom Out (Bao quát)</option>
            <option value="static" ${motion === 'static' ? 'selected' : ''}>Tĩnh (Static)</option>
          </select>
        </div>

        <!-- Caption / Prompt input -->
        <div>
          <input type="text" class="comic-panel-caption-input w-full bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1 text-xs text-slate-800 focus:bg-white focus:border-amber-500" placeholder="Lời thoại hoặc mô tả cảnh #${p.index}..." value="${p.custom_text || ''}" data-idx="${idx}">
        </div>
      </div>
    `;
  }).join('');

  updateImportButtonCount();

  // Attach card event listeners
  container.querySelectorAll('.comic-panel-cb').forEach(cb => {
    cb.addEventListener('change', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (AppState.comicState.slicedPanels[idx]) {
        AppState.comicState.slicedPanels[idx].selected = e.target.checked;
      }
      updateImportButtonCount();
    });
  });

  container.querySelectorAll('.comic-panel-motion-select').forEach(sel => {
    sel.addEventListener('change', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (AppState.comicState.slicedPanels[idx]) {
        AppState.comicState.slicedPanels[idx].camera_motion = e.target.value;
      }
    });
  });

  container.querySelectorAll('.comic-panel-caption-input').forEach(inp => {
    inp.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (AppState.comicState.slicedPanels[idx]) {
        AppState.comicState.slicedPanels[idx].custom_text = e.target.value;
      }
    });
  });
}

function updateImportButtonCount() {
  const panels = AppState.comicState.slicedPanels || [];
  const selectedCount = panels.filter(p => p.selected !== false).length;
  if (DOM.importCountLabel) DOM.importCountLabel.textContent = selectedCount;
  if (DOM.btnImportComicToStoryboard) {
    DOM.btnImportComicToStoryboard.disabled = selectedCount === 0;
  }
}

function switchComicResultTab(tabName) {
  AppState.comicState.activeTab = tabName;
  if (tabName === 'panels') {
    DOM.comicPanelsTabContent?.classList.remove('hidden');
    DOM.comicAnnotatedTabContent?.classList.add('hidden');
    DOM.tabBtnPanels?.classList.add('bg-white', 'text-amber-800', 'font-bold', 'border-amber-300', 'shadow-2xs');
    DOM.tabBtnPanels?.classList.remove('text-slate-600');
    DOM.tabBtnAnnotated?.classList.remove('bg-white', 'text-amber-800', 'font-bold', 'border-amber-300', 'shadow-2xs');
    DOM.tabBtnAnnotated?.classList.add('text-slate-600');
  } else {
    DOM.comicPanelsTabContent?.classList.add('hidden');
    DOM.comicAnnotatedTabContent?.classList.remove('hidden');
    DOM.tabBtnAnnotated?.classList.add('bg-white', 'text-amber-800', 'font-bold', 'border-amber-300', 'shadow-2xs');
    DOM.tabBtnAnnotated?.classList.remove('text-slate-600');
    DOM.tabBtnPanels?.classList.remove('bg-white', 'text-amber-800', 'font-bold', 'border-amber-300', 'shadow-2xs');
    DOM.tabBtnPanels?.classList.add('text-slate-600');
  }
}

async function handleImportComicToStoryboard() {
  const panels = AppState.comicState.slicedPanels || [];
  const selectedPanels = panels.filter(p => p.selected !== false);

  if (selectedPanels.length === 0) {
    showToast("Vui lòng chọn ít nhất một khung tranh để nhập!", "warning");
    return;
  }

  const project = AppState.currentProject;
  if (!project) {
    showToast("Chưa có dự án nào được chọn!", "error");
    return;
  }

  const clearExisting = DOM.comicClearExistingCb?.checked || false;
  const existing = project.scenes?.length || 0;
  if (clearExisting && existing > 0 && !confirm(`Xóa ${existing} cảnh hiện có của dự án "${project.name}" rồi thay bằng ${selectedPanels.length} khung tranh?`)) return;

  DOM.btnImportComicToStoryboard.disabled = true;
  DOM.btnImportComicToStoryboard.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Đang nhập vào Storyboard...';

  try {
    // Server sẽ ghi các cảnh mới vào bản trên server: lưu chỉnh sửa hiện tại trước
    if (!(await flushProjectSave())) throw new Error("Chưa lưu được dự án lên máy chủ");
    const res = await API.importComicPanels(project.id, selectedPanels, clearExisting, "Khung tranh");
    if (!res || !res.success) {
      throw new Error(res?.detail || "Nhập phân cảnh thất bại");
    }

    if (res.project) {
      AppState.currentProject = adoptServerProject(res.project);
      rememberLastProjectId(res.project.id);
    }

    // Refresh UI
    renderSceneList();
    if (AppState.currentProject.scenes.length > 0) {
      selectScene(clearExisting ? 0 : AppState.currentProject.scenes.length - selectedPanels.length);
    }

    closeComicModal();
    switchStep(2); // mở Bảng Đạo Diễn để thấy ngay các cảnh vừa nhập
    if (res.failed_panels > 0) {
      showToast(`Đã đưa ${res.imported_scenes_count} phân cảnh vào Storyboard, nhưng ${res.failed_panels} khung không chép được ảnh (đánh dấu "Lỗi ảnh").`, "warning", 8000);
    } else {
      showToast(`Đã đưa ${res.imported_scenes_count} phân cảnh truyện tranh vào Storyboard! Bạn có thể lồng tiếng và render video ngay.`, "success", 4500);
    }
  } catch (err) {
    console.error("handleImportComicToStoryboard error", err);
    showToast(`Lỗi nhập phân cảnh: ${escapeHtml(err.message || err)}`, "error");
  } finally {
    if (DOM.btnImportComicToStoryboard) {
      DOM.btnImportComicToStoryboard.disabled = false;
      DOM.btnImportComicToStoryboard.innerHTML = '<i class="fa-solid fa-layer-group mr-1.5"></i> <span>Nhập vào Storyboard (<span id="import-count-label">' + selectedPanels.length + '</span> cảnh)</span>';
      // Ô đếm vừa được tạo lại: trỏ DOM vào ô mới, nếu không số khung đã chọn sẽ không cập nhật nữa
      DOM.importCountLabel = document.getElementById('import-count-label');
    }
  }
}

// ================= 4-STEP STEPPER CONTROLLER (MoneyPrinterTurbo Architecture) =================
function switchStep(stepNumber) {
  AppState.currentStep = stepNumber;

  // 1. Update navigation button styles
  for (let i = 1; i <= 4; i++) {
    const btn = document.getElementById(`step-nav-${i}`);
    const view = document.getElementById(`step-view-${i}`);

    if (btn) {
      const badge = btn.querySelector('.step-badge');
      if (i === stepNumber) {
        btn.classList.add('bg-white', 'text-indigo-700', 'font-bold', 'shadow-xs');
        btn.classList.remove('text-slate-600');
        if (badge) {
          badge.classList.add('bg-indigo-600', 'text-white');
          badge.classList.remove('bg-slate-200', 'text-slate-700');
        }
      } else {
        btn.classList.remove('bg-white', 'text-indigo-700', 'font-bold', 'shadow-xs');
        btn.classList.add('text-slate-600');
        if (badge) {
          badge.classList.remove('bg-indigo-600', 'text-white');
          badge.classList.add('bg-slate-200', 'text-slate-700');
        }
      }
    }

    if (view) {
      if (i === stepNumber) {
        view.classList.remove('hidden');
      } else {
        view.classList.add('hidden');
      }
    }
  }

  const currentView = document.getElementById(`step-view-${stepNumber}`);
  if (currentView) currentView.scrollTop = 0;

  if (stepNumber === 4) {
    loadCinemaYouTubePackage();
  }
}

async function loadCinemaYouTubePackage() {
  const project = AppState.currentProject;
  if (!project) return;

  const videoUrl = AppState.produceState.videoUrl || project.final_video_url || `/api/projects/${project.id}/media/renders/story_final.mp4`;
  const srtUrl = AppState.produceState.srtUrl || `/api/projects/${project.id}/download-srt`;

  // Hydrate video player & download links directly
  if (DOM.cinemaVideoPlayer) {
    DOM.cinemaVideoPlayer.src = videoUrl;
  }
  if (DOM.btnCinemaDownloadVideo) {
    DOM.btnCinemaDownloadVideo.href = `/api/projects/${project.id}/download`;
  }
  if (DOM.btnCinemaDownloadSrt) {
    DOM.btnCinemaDownloadSrt.href = srtUrl;
  }
  if (DOM.btnCinemaDownloadAss) {
    DOM.btnCinemaDownloadAss.href = `/api/projects/${project.id}/download-ass`;
  }

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
  if (DOM.btnDownloadThumbnailDirect) {
    DOM.btnDownloadThumbnailDirect.href = `/api/projects/${project.id}/thumbnail`;
  }

  // Fetch SEO Pack
  if (AppState.serverOnline) {
    const seoData = await API.getSeoPack(project.id);
    if (seoData) {
      if (DOM.inputSeoTitle) DOM.inputSeoTitle.value = seoData.recommended_title || "";
      if (DOM.textareaSeoDesc) DOM.textareaSeoDesc.value = seoData.description || "";
      if (DOM.inputSeoTags) DOM.inputSeoTags.value = (seoData.tags || []).join(", ");
    }
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
      showToast("Không thể tạo Thumbnail", "error");
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

// CHARACTER REFERENCE IMAGE HANDLERS
function handleCharRefFileSelect(file) {
  if (!file) return;
  if (!file.type.startsWith('image/')) {
    showToast("Vui lòng chọn file ảnh hợp lệ (PNG, JPG, WebP)!", "warning");
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target.result;
    AppState.characterReferenceImage = dataUrl;
    if (DOM.step1CharRefPreviewImg) DOM.step1CharRefPreviewImg.src = dataUrl;
    if (DOM.step1CharRefFileName) DOM.step1CharRefFileName.textContent = `${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
    if (DOM.step1CharRefPreviewCard) DOM.step1CharRefPreviewCard.classList.remove('hidden');
    if (DOM.step1CharRefDropzone) DOM.step1CharRefDropzone.classList.add('hidden');
    if (DOM.step1CharRefUrl) DOM.step1CharRefUrl.value = '';
    showToast(`Đã nạp ảnh tham chiếu nhân vật: ${escapeHtml(file.name)}`, "success");
  };
  reader.onerror = () => {
    showToast("Không thể đọc file ảnh tham chiếu!", "error");
  };
  reader.readAsDataURL(file);
}

function handleCharRefUrlApply() {
  const url = DOM.step1CharRefUrl?.value.trim();
  if (!url) {
    showToast("Vui lòng dán liên kết URL ảnh tham chiếu trước!", "warning");
    return;
  }
  if (!/^https?:\/\//i.test(url) && !url.startsWith('data:image/')) {
    showToast("URL ảnh phải bắt đầu bằng http:// hoặc https://", "warning");
    return;
  }
  AppState.characterReferenceImage = url;
  if (DOM.step1CharRefPreviewImg) DOM.step1CharRefPreviewImg.src = url;
  if (DOM.step1CharRefFileName) DOM.step1CharRefFileName.textContent = url.length > 40 ? url.substring(0, 37) + '...' : url;
  if (DOM.step1CharRefPreviewCard) DOM.step1CharRefPreviewCard.classList.remove('hidden');
  if (DOM.step1CharRefDropzone) DOM.step1CharRefDropzone.classList.add('hidden');
  showToast("Đã nạp ảnh tham chiếu từ URL!", "success");
}

function handleCharRefRemove() {
  AppState.characterReferenceImage = null;
  if (DOM.step1CharRefPreviewCard) DOM.step1CharRefPreviewCard.classList.add('hidden');
  if (DOM.step1CharRefDropzone) DOM.step1CharRefDropzone.classList.remove('hidden');
  if (DOM.step1CharRefFileInput) DOM.step1CharRefFileInput.value = '';
  if (DOM.step1CharRefUrl) DOM.step1CharRefUrl.value = '';
  showToast("Đã gỡ bỏ ảnh tham chiếu nhân vật", "info");
}

// STEP 1 HANDLERS
function handleStep1ScriptInput() {
  const text = DOM.step1ScriptTextarea?.value.trim() || '';
  const wordCount = text ? text.split(/\s+/).filter(Boolean).length : 0;
  if (DOM.step1WordCount) {
    DOM.step1WordCount.textContent = `${wordCount} từ`;
  }
}

async function handleStep1ProcessScript() {
  const text = DOM.step1ScriptTextarea?.value.trim();
  if (!text) {
    showToast("Vui lòng nhập hoặc chọn kịch bản mẫu trước!", "warning");
    return;
  }

  const pacing = DOM.step1PacingSelect?.value || 'fast';
  const style = DOM.step1StyleSelect?.value || 'cinematic_realistic';
  const imageProvider = DOM.step1EngineSelect?.value || DOM.selectImageProvider?.value || 'meta_muse_cloud';
  const charName = DOM.step1CharName?.value.trim() || '';
  const charAnchor = DOM.step1CharAnchor?.value.trim() || '';
  const charPreset = document.getElementById('step1-char-preset-select')?.value || '';
  const charRefImage = AppState.characterReferenceImage || DOM.step1CharRefUrl?.value.trim() || undefined;

  const isEnglish = !(/[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]/i.test(text));
  const selectedVoice = DOM.selectVoice?.value;
  const autoVoice = selectedVoice || (isEnglish ? "en-US-AndrewMultilingualNeural" : "vi-VN-NamMinhNeural");

  DOM.btnStep1ProcessScript.disabled = true;
  DOM.btnStep1ProcessScript.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Đang tạo Video Review Truyện (Muse AI)...';

  try {
    let createdProject = null;
    if (AppState.serverOnline) {
      createdProject = await API.createProjectFromScript({
        name: text.split('\n')[0].substring(0, 45).trim() || "Câu Chuyện Mới",
        text: text,
        pacing: pacing,
        style_preset: style,
        character_preset_id: charPreset && charPreset !== 'custom' ? charPreset : undefined,
        character_name: charName || undefined,
        character_anchor: charAnchor,
        character_reference_image: charRefImage,
        voice: autoVoice,
        image_provider: imageProvider,
        generate_initial_images: true
      });
    }

    if (createdProject && Array.isArray(createdProject.scenes) && createdProject.scenes.length > 0) {
      AppState.currentProject = adoptServerProject(createdProject);
      if (charRefImage && !AppState.currentProject.character_reference_image) {
        AppState.currentProject.character_reference_image = charRefImage;
      }
      saveStateToLocal();
      renderFullUI();
      selectScene(0);
      switchStep(2);
      const total = createdProject.scenes.length;
      const failedImages = createdProject.scenes.filter(s => s.status_image === 'error').length;
      const analysisNote = createdProject.metadata?.scene_analysis?.fallback_reason;
      if (analysisNote && createdProject.metadata?.scene_analysis?.provider === 'partial') {
        // AI chia được phần lớn bài; vài phần chia offline, lý do ghi rõ cảnh nào
        showToast(`AI đã chia cảnh, nhưng một số đoạn phải chia offline. ${escapeHtml(String(analysisNote))}.`, "warning", 12000);
      } else if (analysisNote) {
        showToast(`AI chia cảnh không chạy được (${escapeHtml(String(analysisNote))}). Các cảnh được chia offline, prompt ảnh chỉ là mẫu chung.`, "warning", 10000);
      }
      if (failedImages > 0) {
        showToast(`Đã tạo ${total} phân cảnh, nhưng ${failedImages} cảnh tạo ảnh thất bại (đánh dấu "Lỗi ảnh"). Hãy tạo lại ảnh cho các cảnh đó.`, "warning", 8000);
      } else {
        showToast(`Đã tạo câu chuyện mới với ${total} phân cảnh chuẩn Muse AI!`, "success", 4000);
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
    if (DOM.btnStep1ProcessScript) {
      DOM.btnStep1ProcessScript.disabled = false;
      DOM.btnStep1ProcessScript.innerHTML = '<i class="fa-solid fa-bolt-lightning text-amber-300 mr-1.5 animate-bounce"></i> <span>⚡ 1-Click Tạo Video Review Truyện (Muse AI)</span> <i class="fa-solid fa-arrow-right ml-1"></i>';
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
        box.className = "p-3 rounded-2xl border-2 border-indigo-500 bg-indigo-50/70 transition shadow-md font-bold text-indigo-950 ring-2 ring-indigo-500/20";
        icon.className = "w-7 h-7 rounded-full bg-indigo-600 text-white flex items-center justify-center mx-auto mb-1.5 text-xs font-bold animate-pulse";
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
    DOM.producerStatusText.innerHTML = `<i class="fa-solid ${progressPercent >= 100 ? 'fa-circle-check text-emerald-600' : 'fa-spinner fa-spin text-indigo-600'} mr-1.5"></i> <span>${statusMsg}</span>`;
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

async function startProduceLongVideo() {
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

  // Reset produce state
  AppState.produceState.isProducing = true;
  AppState.produceState.progress = 5;
  AppState.produceState.step = 1;
  AppState.produceState.logs = ["Bắt đầu quy trình sản xuất Video Dài (MoneyPrinterTurbo Stepper Pipeline)..."];
  AppState.produceState.startTime = Date.now();

  if (DOM.btnProducerGotoCinema) DOM.btnProducerGotoCinema.disabled = true;

  // Start timer
  if (AppState.produceState.timerInterval) clearInterval(AppState.produceState.timerInterval);
  AppState.produceState.timerInterval = setInterval(() => {
    if (!AppState.produceState.isProducing) {
      clearInterval(AppState.produceState.timerInterval);
      return;
    }
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
      style_preset: DOM.selectProjectStyle?.value || project.style_preset || "cinematic_realistic",
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
      camera_motion: project.default_motion || "zoom_in"
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
    console.error("startProduceLongVideo error", err);
    AppState.produceState.isProducing = false;
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

    const progress = data.progress || 0;
    const step = data.step || 1;
    const stepLabel = data.step_label || "Đang xử lý...";
    const logs = data.logs || [];

    AppState.produceState.progress = progress;
    AppState.produceState.step = step;
    AppState.produceState.logs = logs;

    updateProducerStageUI(step, progress, stepLabel, logs);

    // Fail-Safe: Check failure first (Anti-Fail-Open)
    if (data.status === 'failed' || data.error) {
      AppState.produceState.isProducing = false;
      if (ws) {
        try { ws.close(); } catch {}
      }
      if (pollInterval) clearInterval(pollInterval);
      const errMsg = data.error || 'Quy trình sản xuất video dài thất bại!';
      showToast(`❌ LỖI SẢN XUẤT: ${escapeHtml(errMsg)}`, "error", 6000);
      if (DOM.producerStatusText) {
        DOM.producerStatusText.textContent = `Thất bại: ${errMsg}`;
        DOM.producerStatusText.className = "text-xs font-bold text-rose-600 truncate";
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

      const videoUrl = data.video_url || `/api/projects/${AppState.currentProject.id}/media/renders/story_final.mp4`;
      const srtUrl = data.srt_url || `/api/projects/${AppState.currentProject.id}/download-srt`;

      AppState.produceState.videoUrl = videoUrl;
      AppState.produceState.srtUrl = srtUrl;

      // Populate Cinema Player
      if (DOM.cinemaVideoPlayer) {
        DOM.cinemaVideoPlayer.src = videoUrl;
      }
      if (DOM.btnCinemaDownloadVideo) {
        DOM.btnCinemaDownloadVideo.href = `/api/projects/${AppState.currentProject.id}/download`;
      }
      if (DOM.btnCinemaDownloadSrt) {
        DOM.btnCinemaDownloadSrt.href = srtUrl;
      }
      if (DOM.btnCinemaDownloadAss) {
        DOM.btnCinemaDownloadAss.href = `/api/projects/${AppState.currentProject.id}/download-ass`;
      }
      if (DOM.btnProducerGotoCinema) {
        DOM.btnProducerGotoCinema.disabled = false;
      }

      showToast("🎉 Hoàn tất sản xuất Video Dài 1080p! Đang mở Rạp Chiếu Phim...", "success", 4000);

      // Auto switch to Step 4 after 1.5 seconds
      setTimeout(() => {
        switchStep(4);
      }, 1500);
    }
  }
}

// ================= MODAL 1: SCRIPT IMPORTER =================
function openScriptModal() {
  DOM.modalScriptImporter.classList.remove('hidden');
  DOM.importScriptTextarea.focus();
}

function closeScriptModal() {
  DOM.modalScriptImporter.classList.add('hidden');
}

function handleScriptInputCount() {
  const text = DOM.importScriptTextarea.value.trim();
  const words = text ? text.split(/\s+/).length : 0;
  const sentences = text ? (text.match(/[^.!?]+[.!?]+/g) || [text]).length : 0;
  DOM.scriptWordCount.textContent = `${words} từ • ${sentences} câu`;
}

async function handleSubmitScriptSplit() {
  const text = DOM.importScriptTextarea.value.trim();
  if (!text) {
    showToast("Vui lòng dán nội dung câu chuyện trước!", "warning");
    return;
  }

  const mode = DOM.splitModeSelect.value;
  const style = DOM.splitStyleSelect.value;
  const project = AppState.currentProject;

  DOM.btnSubmitScriptSplit.disabled = true;
  DOM.btnSubmitScriptSplit.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Đang phân tích kịch bản...';

  // Server tách kịch bản và THÊM các cảnh mới vào dự án; giao diện lấy lại đúng bản dự án server trả về
  let result;
  if (!AppState.serverOnline) {
    result = { success: false, detail: 'Máy chủ đang offline.' };
  } else if (project.is_demo) {
    result = { success: false, detail: 'đây là dự án mẫu, hãy tạo dự án mới trước.' };
  } else if (!(await flushProjectSave())) {
    result = { success: false, detail: 'chưa lưu được dự án hiện tại lên máy chủ.' };
  } else {
    result = await API.splitScript(project.id, text, { mode, style, pacing: mode, style_preset: style });
  }

  if (result?.success && result.project && Array.isArray(result.project.scenes)) {
    const firstNewIndex = Math.max(0, result.project.scenes.length - (result.added_scenes || 0));
    AppState.currentProject = adoptServerProject(result.project);
    AppState.selectedSceneIndex = firstNewIndex;
    rememberLastProjectId(result.project.id);
    renderFullUI();
    closeScriptModal();
    showToast(`Đã thêm ${result.added_scenes || 0} phân cảnh (tổng ${result.total_scenes || result.project.scenes.length}).`, "success");
  } else {
    showToast(`Không thể phân tích kịch bản: ${escapeHtml(String(result?.detail || 'máy chủ không phản hồi'))}`, "error", 7000);
  }

  DOM.btnSubmitScriptSplit.disabled = false;
  DOM.btnSubmitScriptSplit.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Tự động phân tích & tạo Storyboard</span>';
}

// ================= MODAL 3: CHARACTER CONSISTENCY =================
function openCharacterModal() {
  const char = AppState.currentProject?.character;
  if (char) {
    DOM.editCharName.value = char.name || "";
    DOM.editCharPrompt.value = char.prompt || "";
    // Giá trị cũ không còn hợp lệ (realistic, 3d_disney, manhwa) -> theo phong cách dự án
    DOM.editCharStyle.value = characterStyleOverride(char);
    if (DOM.editCharStyle.value !== characterStyleOverride(char)) DOM.editCharStyle.value = "";
    DOM.editCharNegative.value = char.negative || "";
  } else {
    // character_anchor là mô tả ngoại hình, không phải tên
    DOM.editCharName.value = "";
    DOM.editCharPrompt.value = AppState.currentProject?.character_anchor || "";
    DOM.editCharStyle.value = "";
    DOM.editCharNegative.value = "";
  }
  DOM.modalCharacterEditor.classList.remove('hidden');
}

function closeCharacterModal() {
  DOM.modalCharacterEditor.classList.add('hidden');
}

function handleSaveCharacter() {
  const project = AppState.currentProject;
  if (!project) return;

  project.character = {
    name: DOM.editCharName.value.trim(),
    prompt: DOM.editCharPrompt.value.trim(),
    style: DOM.editCharStyle.value,
    negative: DOM.editCharNegative.value.trim(),
    avatar: project.character?.avatar || ""
  };
  // Mô tả ngoại hình trong hộp này chính là character_anchor máy chủ ghép vào mọi ảnh
  project.character_anchor = project.character.prompt;

  saveStateToLocal();
  renderCharacterCard();
  closeCharacterModal();
  showToast("Đã lưu cấu hình Khóa nhân vật đồng bộ!", "success");
}

// ================= MODAL 4: PROJECT MANAGER =================
function openProjectModal() {
  DOM.modalProjectManager.classList.remove('hidden');
  renderProjectListModal();
  // Lấy lại danh sách để số cảnh của các dự án khác là số mới nhất
  if (AppState.serverOnline) {
    loadProjectsList().then(() => {
      if (!DOM.modalProjectManager.classList.contains('hidden')) renderProjectListModal();
    }).catch(() => {});
  }
}

function closeProjectModal() {
  DOM.modalProjectManager.classList.add('hidden');
}

function renderProjectListModal() {
  const container = DOM.projectListItems;
  if (!container) return;

  const projects = AppState.projectsList || [];
  container.innerHTML = projects.map(p => {
    const isCurrent = AppState.currentProject && AppState.currentProject.id === p.id;
    return `
      <div class="flex items-center justify-between p-3 rounded-xl border ${isCurrent ? 'bg-indigo-50 border-indigo-300' : 'bg-slate-50 border-slate-200 hover:border-slate-300'} transition">
        <div>
          <div class="text-xs font-bold text-slate-800 flex items-center gap-2">
            <span>${escapeHtml(p.name)}</span>
            ${isCurrent ? '<span class="text-[10px] bg-indigo-600 text-white px-1.5 py-0.5 rounded font-semibold">Đang mở</span>' : ''}
          </div>
          <div class="text-[10px] text-slate-500 mt-0.5">${isCurrent ? (AppState.currentProject.scenes?.length || 0) : (p.scenes_count ?? p.scene_count ?? 0)} phân cảnh • 1080p</div>
        </div>
        <div class="flex items-center gap-1.5">
          ${!isCurrent ? `
            <button onclick="switchProject('${p.id}')" class="px-2.5 py-1 bg-white hover:bg-indigo-50 border border-slate-300 text-xs font-semibold text-slate-700 hover:text-indigo-600 rounded-lg transition shadow-2xs">
              Mở
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
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
  closeProjectModal();
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
  closeProjectModal();
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

function closeAllModals() {
  DOM.modalScriptImporter?.classList.add('hidden');
  DOM.modalComicSlicer?.classList.add('hidden');
  DOM.modalCharacterEditor?.classList.add('hidden');
  DOM.modalProjectManager?.classList.add('hidden');
  document.getElementById('modal-master-storyboard')?.classList.add('hidden');
  // closeTrueCrimeModal (true_crime.js) còn dừng việc hỏi tiến độ phân tích
  if (typeof closeTrueCrimeModal === 'function') closeTrueCrimeModal();
  else DOM.modalTrueCrime?.classList.add('hidden');
}

// ================= OP_CTOOL MASTER STORYBOARD SPEC HANDLER =================
let cachedMasterStoryboard = null;

function initMasterStoryboardSpec() {
  const btnOpen = document.getElementById('btn-open-master-storyboard-modal');
  const modal = document.getElementById('modal-master-storyboard');
  const btnClose = document.getElementById('btn-close-master-sb-modal');
  const btnCancel = document.getElementById('btn-cancel-master-sb-modal');
  const btnSampleDet = document.getElementById('btn-msb-sample-detective');
  const btnSampleSciFi = document.getElementById('btn-msb-sample-scifi');
  const btnDeconstruct = document.getElementById('btn-run-master-sb-deconstruct');
  const btnApply = document.getElementById('btn-apply-master-sb-to-project');
  const textarea = document.getElementById('master-sb-script-text');

  if (!modal) return;

  btnOpen?.addEventListener('click', () => {
    modal.classList.remove('hidden');
    if (textarea && !textarea.value) {
      textarea.value = "Cơn mưa rào trút xuống màn đêm tĩnh mịch, xóa nhòa mọi dấu vết trên con đường dẫn vào căn biệt thự bỏ hoang.\nNam đẩy nhẹ cánh cổng sắt rỉ sét. Một tiếng kẽo kẹt xé toạc không gian... nhưng bên trong phòng khách, một đốm sáng đỏ kỳ dị vẫn đang nhấp nháy.\nTừng bước chân trĩu nặng trên sỏi ướt, hơi thở anh ngưng trệ khi nhìn thấy vệt máu loang trên thảm nhung.";
    }
  });

  const closeModal = () => modal.classList.add('hidden');
  btnClose?.addEventListener('click', closeModal);
  btnCancel?.addEventListener('click', closeModal);

  btnSampleDet?.addEventListener('click', () => {
    if (textarea) {
      textarea.value = "Cơn mưa rào trút xuống màn đêm tĩnh mịch, xóa nhòa mọi dấu vết trên con đường dẫn vào căn biệt thự bỏ hoang.\nNam đẩy nhẹ cánh cổng sắt rỉ sét. Một tiếng kẽo kẹt xé toạc không gian... nhưng bên trong phòng khách, một đốm sáng đỏ kỳ dị vẫn đang nhấp nháy.\nTừng bước chân trĩu nặng trên sỏi ướt, hơi thở anh ngưng trệ khi nhìn thấy vệt máu loang trên thảm nhung.";
    }
  });

  btnSampleSciFi?.addEventListener('click', () => {
    if (textarea) {
      textarea.value = "Giữa khoảng không vô tận của vũ trụ, trạm không gian Aethelgard trôi dạt trong im lặng tuyệt đối.\nTín hiệu cầu cứu phát ra từ ba mươi năm trước bất ngờ kích hoạt trở lại trên màn hình radar.\nHệ thống dưỡng khí đang cạn kiệt, và một bóng đen khổng lồ đang từ từ bao trùm khoang điều khiển.";
    }
  });

  btnDeconstruct?.addEventListener('click', async () => {
    const text = textarea?.value?.trim();
    if (!text) {
      showToast("Vui lòng nhập kịch bản cần phân rã!", "warning");
      return;
    }

    const styleDna = document.getElementById('master-sb-style-dna')?.value || "Dark moody cinematic neo-noir, 35mm film grain";
    const gridMode = document.getElementById('master-sb-grid-mode')?.value === "true";

    btnDeconstruct.disabled = true;
    btnDeconstruct.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>Đang phân tích LLM...</span>';

    try {
      const resp = await fetch('/api/storyboard/deconstruct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          script_text: text,
          art_style: styleDna,
          tone_and_mood: "tense_suspense",
          batch_9_grid: gridMode,
          provider: "auto",
        }),
      });

      if (!resp.ok) throw new Error("Lỗi gọi API phân rã kịch bản");
      const sb = await resp.json();
      cachedMasterStoryboard = sb;

      // Render preview
      const previewCont = document.getElementById('master-sb-preview-container');
      const cardsCont = document.getElementById('master-sb-preview-cards');
      const countLabel = document.getElementById('master-sb-scene-count');
      const titleLabel = document.getElementById('master-sb-preview-title');

      if (previewCont && cardsCont) {
        previewCont.classList.remove('hidden');
        if (titleLabel) titleLabel.textContent = sb.project_metadata?.title || "Master Storyboard";
        if (countLabel) countLabel.textContent = `${sb.scenes?.length || 0} cảnh`;

        // Nội dung do LLM viết: luôn escape trước khi đưa vào HTML
        const esc = v => escapeHtml(String(v ?? ''));
        cardsCont.innerHTML = (sb.scenes || []).map(sc => `
          <div class="p-2.5 bg-white rounded-lg border border-slate-200 space-y-1">
            <div class="flex items-center justify-between text-[11px] font-bold">
              <span class="text-purple-700">Cảnh ${esc(sc.scene_id)} • ${esc(sc.visual?.shot_type || 'Medium Shot')}</span>
              <span class="text-amber-700 font-mono bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                ${sc.visual?.generation_mode === '9_grid_composite' ? '⚡ 9-Grid' : 'Single'} • ⏱️ ${esc(sc.estimated_duration_sec)}s (Nghỉ ${esc(sc.audio?.pause_after_sec)}s)
              </span>
            </div>
            <div class="text-slate-800 font-medium">"${esc(sc.audio?.voiceover_text)}"</div>
            <div class="text-[11px] text-slate-500 flex flex-wrap gap-2 pt-1 border-t border-slate-100">
              <span>🔊 SFX: <b>${esc((sc.sound_design?.sfx_cue || []).join(', ') || 'none')}</b></span>
              <span>🎵 BGM: <b>${esc(sc.sound_design?.bgm_energy || 'ambient')}</b></span>
              <span>✨ Từ khóa: <b class="text-amber-600">${esc((sc.subtitles?.kinetic_highlight_words || []).join(', '))}</b></span>
            </div>
          </div>
        `).join('');
      }

      btnApply?.classList.remove('hidden');
      showToast("Phân rã Master Storyboard thành công!", "success");
    } catch (err) {
      console.error(err);
      showToast("Lỗi phân rã kịch bản: " + escapeHtml(err.message), "error");
    } finally {
      btnDeconstruct.disabled = false;
      btnDeconstruct.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Phân rã Master Storyboard</span>';
    }
  });

  btnApply?.addEventListener('click', async () => {
    if (!cachedMasterStoryboard) return;

    btnApply.disabled = true;
    btnApply.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>Đang nạp vào dự án...</span>';

    try {
      // Không gửi project_id: máy chủ ghi đè TOÀN BỘ dự án có id đó. Storyboard luôn được nạp thành dự án mới.
      if (!(await flushProjectSave())) throw new Error("chưa lưu được dự án đang mở lên máy chủ");
      const resp = await fetch('/api/storyboard/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          storyboard: cachedMasterStoryboard,
          title: cachedMasterStoryboard.project_metadata?.title,
        }),
      });

      if (!resp.ok) throw new Error("Lỗi nạp storyboard vào dự án");
      const resData = await resp.json();

      closeModal();
      showToast(`Đã tạo dự án mới "${escapeHtml(String(resData.title || ''))}" với ${resData.scenes_count} phân cảnh!`, "success");

      // Reload project
      if (resData.project_id) {
        await switchProject(resData.project_id);
        switchStep(2);
      }
    } catch (err) {
      console.error(err);
      showToast("Lỗi nạp storyboard: " + escapeHtml(err.message), "error");
    } finally {
      btnApply.disabled = false;
      btnApply.innerHTML = '<i class="fa-solid fa-check"></i> <span>Nạp vào Dự Án & Bắt đầu Dựng</span>';
    }
  });
}

// Call on startup
document.addEventListener('DOMContentLoaded', () => {
  initMasterStoryboardSpec();
});

// ================= META MUSE CLOUD STUDIO ENGINE =================
function initMuseCloud() {
  console.log("Initializing Meta Muse Cloud Studio Engine...");

  // Bind Header Button & Modal Controls
  if (DOM.btnMuseCloudStatus) {
    DOM.btnMuseCloudStatus.addEventListener('click', openMuseModal);
  }
  if (DOM.btnCloseMuseModal) {
    DOM.btnCloseMuseModal.addEventListener('click', closeMuseModal);
  }
  if (DOM.btnCloseMuseModalFooter) {
    DOM.btnCloseMuseModalFooter.addEventListener('click', closeMuseModal);
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
        ? "Đã sao chép lệnh: 'setup_muse_accounts.bat'! Chạy file này để đăng nhập lần đầu cho 10 tài khoản."
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
  return (t === 'image' || t === 'video') ? t : null;
}

// Active account id of the given kind ('image' | 'video'), or null when none is set.
function getActiveMuseAccountId(kind) {
  const fromState = kind === 'video' ? museFleetState.activeVideoAccount : museFleetState.activeImageAccount;
  if (fromState) {
    const acc = (cachedMuseAccounts || []).find(a => a.account_id === fromState);
    if (!acc || museAccountKind(acc) === kind) return fromState;
  }
  const flag = kind === 'video' ? 'is_active_for_video' : 'is_active_for_image';
  const acc = (cachedMuseAccounts || []).find(a => museAccountKind(a) === kind && a[flag]);
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
  return cachedMuseAccounts.some(a => museAccountKind(a) === kind && a.online);
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
      return make('text-teal-700 bg-teal-50 border-teal-200', 'bg-teal-500', 'sẵn sàng');
    case 'busy':
      return make('text-indigo-700 bg-indigo-50 border-indigo-200', 'bg-indigo-500 animate-pulse', 'đang chạy');
    case 'cooldown':
      return make('text-amber-700 bg-amber-50 border-amber-200', 'bg-amber-400', 'nghỉ (cooldown)', until ? `Nghỉ tới ${until}` : '');
    case 'blocked':
      return make('text-rose-700 bg-rose-50 border-rose-200', 'bg-rose-500', 'bị khóa',
        [acc.block_reason, until ? `tới ${until}` : ''].filter(Boolean).join(' • ') || 'Tài khoản đang bị khóa');
    case 'needs_login':
      return make('text-rose-700 bg-rose-50 border-rose-200', 'bg-rose-500', 'cần đăng nhập lại', 'Phiên đăng nhập đã hết hạn: chạy lại lệnh --setup cho tài khoản này');
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
    ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 cursor-default'
    : (acc.has_profile ? 'bg-indigo-600 hover:bg-indigo-500 text-white cursor-pointer' : 'bg-slate-200 text-slate-500 cursor-pointer');
  return `
    <div class="p-2.5 bg-white rounded-lg border ${isActive ? 'border-indigo-400 ring-2 ring-indigo-50' : 'border-slate-200'} flex items-center justify-between gap-2"${rowTitle}>
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
    const icon = kind === 'video' ? 'fa-film text-purple-500' : 'fa-image text-indigo-500';
    const tone = v === true
      ? ['bg-emerald-50 border-emerald-200 text-emerald-800', 'bg-emerald-500 animate-pulse', 'online']
      : (v === false ? ['bg-rose-50 border-rose-200 text-rose-700', 'bg-rose-500', 'offline'] : ['bg-slate-50 border-slate-200 text-slate-600', 'bg-slate-400', 'chưa rõ']);
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
    const kind = museAccountKind(acc);
    if (kind) groups[kind].push(acc);
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
    const msg = '<p class="text-[11px] text-rose-500 px-1">Không tải được danh sách tài khoản (server không phản hồi).</p>';
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
  if (acc && museAccountKind(acc) !== mode) {
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

function openMuseModal() {
  if (DOM.modalMuseCloud) {
    DOM.modalMuseCloud.classList.remove('hidden');
    pollMuseBridgeStatus(); // Immediate refresh on open
    loadMuseAccountsUI(); // Immediate refresh of multi-account switcher
  }
}

function closeMuseModal() {
  if (DOM.modalMuseCloud) {
    DOM.modalMuseCloud.classList.add('hidden');
  }
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
      DOM.btnMuseCloudStatus.className = "px-2.5 py-1.5 bg-gradient-to-r from-emerald-50 to-teal-50 hover:from-emerald-100 hover:to-teal-100 text-emerald-800 rounded-lg text-xs font-bold border border-emerald-300 transition flex items-center gap-1.5 shadow-xs group cursor-pointer";
      DOM.headerMuseStatusDot.innerHTML = `
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
      `;
      DOM.headerMuseStatusText.textContent = "Sẵn sàng";
      DOM.headerMuseStatusText.className = "text-emerald-900";
      DOM.headerMuseStatusText.title = "";
      DOM.headerMuseSpecsBadge.className = "hidden min-[1880px]:inline text-[10px] bg-white px-1.5 py-0.5 rounded text-emerald-700 border border-emerald-200 font-mono";
      DOM.headerMuseSpecsBadge.textContent = museFleetKindSummary();
    } else if (statusStr === 'busy') {
      DOM.btnMuseCloudStatus.className = "px-2.5 py-1.5 bg-gradient-to-r from-amber-50 to-orange-50 text-amber-900 rounded-lg text-xs font-bold border border-amber-300 transition flex items-center gap-1.5 shadow-xs group cursor-pointer animate-pulse";
      DOM.headerMuseStatusDot.innerHTML = `
        <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
      `;
      const activeMsg = data?.active_job?.status_message || "Đang render...";
      DOM.headerMuseStatusText.textContent = activeMsg.length > 25 ? activeMsg.substring(0, 22) + "..." : activeMsg;
      // Giới hạn bề rộng để thông báo dài không ép mất tên dự án trên màn 1280-1600px; rê chuột xem đủ câu.
      // 140px vừa đủ các câu runner gửi lâu nhất ("Muse đang tạo video..." 136px, "Gửi prompt lên Muse..." 137px).
      DOM.headerMuseStatusText.className = "text-amber-900 truncate max-w-[140px]";
      DOM.headerMuseStatusText.title = activeMsg;
      DOM.headerMuseSpecsBadge.className = "hidden min-[1880px]:inline text-[10px] bg-white px-1.5 py-0.5 rounded text-amber-800 border border-amber-200 font-mono";
      DOM.headerMuseSpecsBadge.textContent = museFleetKindSummary();   // chữ trạng thái bên cạnh đã nói đang render
    } else {
      DOM.btnMuseCloudStatus.className = "px-2.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-lg text-xs font-bold border border-rose-300 transition flex items-center gap-1.5 shadow-xs group cursor-pointer";
      DOM.headerMuseStatusDot.innerHTML = `
        <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500"></span>
      `;
      DOM.headerMuseStatusText.textContent = "Chưa kết nối";
      DOM.headerMuseStatusText.className = "text-rose-700 underline decoration-rose-300";
      DOM.headerMuseStatusText.title = "";
      DOM.headerMuseSpecsBadge.className = "hidden min-[1880px]:inline text-[10px] bg-rose-100 px-1.5 py-0.5 rounded text-rose-800 font-semibold";
      DOM.headerMuseSpecsBadge.textContent = "Bấm để xem Fleet";
    }
  }

  // 2. Update Modal Status Badge
  if (DOM.museModalStatusBadge && DOM.museModalStatusDot && DOM.museModalStatusText) {
    if (statusStr === 'online') {
      DOM.museModalStatusBadge.className = "px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1.5";
      DOM.museModalStatusDot.className = "w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse";
      DOM.museModalStatusText.textContent = "Đang kết nối (Online)";
    } else if (statusStr === 'busy') {
      DOM.museModalStatusBadge.className = "px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1.5";
      DOM.museModalStatusDot.className = "w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse";
      DOM.museModalStatusText.textContent = "Đang render tác vụ (Busy)";
    } else {
      DOM.museModalStatusBadge.className = "px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30 flex items-center gap-1.5";
      DOM.museModalStatusDot.className = "w-1.5 h-1.5 rounded-full bg-rose-400";
      DOM.museModalStatusText.textContent = "Chưa kết nối (Offline)";
    }
  }

  // 3. Fleet accounts: refresh the account list when the modal is visible (accounts come with every status poll)
  if (DOM.modalMuseCloud && !DOM.modalMuseCloud.classList.contains('hidden') && data && Array.isArray(data.accounts)) {
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
            <a href="${escapeHtml(downloadUrl)}" download="${escapeHtml(sceneId)}${isVideo ? '.mp4' : '.jpg'}" class="px-2 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg text-xs font-bold transition flex items-center gap-1 shadow-2xs" title="Tải file về máy tính">
              <i class="fa-solid fa-download"></i>
              <span class="hidden sm:inline">Tải</span>
            </a>
            <button type="button" class="btn-delete-gallery-item px-2 py-1 bg-rose-50 hover:bg-rose-100 text-rose-600 rounded-lg text-xs font-bold transition flex items-center gap-1 shadow-2xs cursor-pointer" data-task-id="${escapeHtml(taskId)}" title="Xóa tệp media này">
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
    const stylePreset = DOM.selectProjectStyle?.value || project.style_preset || 'spartan_epic_mythology';
    let promptText = "";
    if (isVideo) {
      if (!scene.video_prompt || scene.video_prompt.trim() === '') {
        const rawImgPrompt = scene.image_prompt || scene.visual_prompt || scene.text || "";
        scene.video_prompt = `${rawImgPrompt}, cinematic continuous human walking motion, person moving forward through the scene, natural dynamic character movement, camera tracking front shot, fluid realistic motion`;
        saveStateToLocal();
      }
      promptText = scene.video_prompt;
    } else {
      promptText = scene.image_prompt || scene.visual_prompt || scene.text || "";
      if (project.character_anchor && !promptText.includes(project.character_anchor)) {
        promptText = `${project.character_anchor}, ${promptText}`;
      }
    }

    const taskPayload = withMuseAccount({
      project_id: project.id,
      scene_id: scene.id || `scene_${index + 1}`,
      mode: isVideo ? "image-to-video" : "text-to-image",
      prompt: promptText,
      action_prompt: promptText,
      negative_prompt: scene.negative_prompt || "",
      input_image_url: isVideo ? (scene.image_url || null) : null,
      camera_motion: scene.camera_motion || "cinematic slow tracking pan, smooth camera motion",
      parameters: {
        resolution: "2K",
        aspect_ratio: "16:9",
        style_preset: stylePreset,
        duration_sec: 5,
        fps: 25,
        camera_motion: scene.camera_motion || "cinematic slow tracking pan, smooth camera motion",
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
window.openComicModal = openComicModal;
window.closeComicModal = closeComicModal;
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
window.updateSceneVideoPrompt = updateSceneVideoPrompt;
window.updateSceneVideoPromptLive = updateSceneVideoPromptLive;
window.playSceneVoice = playSceneVoice;
window.togglePlayVoiceSample = togglePlayVoiceSample;
window.seekSceneAudio = seekSceneAudio;
window.regenerateSceneVoice = regenerateSceneVoice;
window.openScriptModal = openScriptModal;
window.switchProject = switchProject;
window.openMuseModal = openMuseModal;
window.closeMuseModal = closeMuseModal;
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
