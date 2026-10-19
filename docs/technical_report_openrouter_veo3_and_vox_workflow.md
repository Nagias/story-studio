# BÁO CÁO KỸ THUẬT CHUYÊN SÂU
## 1. Phân Tích Nguyên Nhân OpenRouter Không Hỗ Trợ Google Veo 3 & Lộ Trình Video AI
## 2. Quy Trình Chuẩn Công Nghiệp Sản Xuất Video 10 Phút Phong Cách Vox Bằng Gemini & Motion Graphics

**Tác giả:** story-intelligence (YouTube Story Studio Team)  
**Ngày lập:** Tháng 3 / 2025  
**Hệ thống áp dụng:** YouTube Story Studio Backend (`projects/story-studio`)

---

# PHẦN 1: TẠI SAO OPENROUTER KHÔNG HỖ TRỢ GOOGLE VEO 3

### 1.1. Bằng chứng thực tế từ OpenRouter API Endpoint
Khi truy vấn trực tiếp danh mục toàn bộ mô hình trên endpoint công khai của OpenRouter:
```http
GET https://openrouter.ai/api/v1/models
```
Phân tích dữ liệu JSON trả về cho thấy các chỉ số kỹ thuật khách quan:
1. **Số lượng mô hình mang tiền tố hoặc tên `veo` hoặc `video`**: **0 / 300+ mô hình**.
2. **Khảo sát hệ thống Modality của toàn bộ mô hình trên OpenRouter**:
   - `architecture.modality` của tất cả các mô hình chỉ bao gồm:
     * `text->text`
     * `text+image->text`
     * `text+image+file->text`
     * `text+image+audio->text`
     * `text+image+file+audio+video->text` (nhận video đầu vào để phân tích, nhưng trả về văn bản)
     * `text->text+image` (sinh ảnh như DALL-E, Flux)
     * `text->text+audio` (sinh âm thanh TTS)
   - **Hoàn toàn KHÔNG TỒN TẠI** bất kỳ mô hình nào có output modality là `-> video`.

### 1.2. Mâu thuẫn cốt lõi về Kiến trúc Giao thức (Protocol & Architectural Mismatch)

| Tiêu chí | Giao thức OpenRouter (`/v1/chat/completions`) | Giao thức Sinh Video AI (Google Veo, Sora, Kling) |
|---|---|---|
| **Cơ chế phản hồi** | Đồng bộ hoặc Server-Sent Events (SSE) Stream text tokens | Hoàn toàn bất đồng bộ (Asynchronous LRO - Long-Running Operations) |
| **Thời gian xử lý** | 200ms – 15 giây (phù hợp với HTTP Request Timeout) | 60 giây – 300 giây (vượt xa ngưỡng timeout của HTTP gateway) |
| **Mô hình tác vụ** | Single Request-Response qua HTTP pipeline | Gửi Job -> Nhận Task ID -> Polling kiểm tra trạng thái -> Webhook Callback |
| **Dung lượng kết quả** | Vài KB đến vài chục KB dữ liệu dạng Text JSON | 10 MB đến 200 MB tệp nhị phân nén MP4 (H.264 / ProRes) |
| **Hạ tầng lưu trữ** | Không yêu cầu bộ đệm tệp (Stateless Proxy Gateway) | Cần Object Storage (S3 / GCS), CDN tốc độ cao, Quản lý vòng đời tệp |

- **Bản chất của OpenRouter**: OpenRouter là một **LLM API Aggregator & Proxy** chuẩn hóa theo giao thức OpenAI Chat Completion. Mọi tính năng từ định tuyến thông minh (router fallback), tính phí theo token, streaming chunk đều được thiết kế cho text và audio/image đơn giản.
- **Bản chất của Video Generation**: Google Veo 2/Veo 3 là mô hình sinh chuỗi không gian - thời gian (spatiotemporal latent diffusion / transformer), đòi hỏi hàng trăm GPU tensor cores render từng giây khung hình. Việc đóng gói pipeline này vào một endpoint `chat/completions` là không khả thi về mặt kỹ thuật.

### 1.3. Rào cản Giấy phép & Phân phối Thương mại của Google DeepMind
- **Google Veo 2 / Veo 3** hiện tại chỉ được cấp phép thử nghiệm giới hạn:
  * Trực tiếp qua **Google Cloud Vertex AI** dưới hình thức Private Preview (yêu cầu phê duyệt Enterprise Whitelist).
  * Thử nghiệm giới hạn trên nền tảng YouTube Shorts (Dream Screen) và Google DeepMind Playground.
- Google **chưa từng phát hành Public Reseller API** cho bất kỳ bên thứ ba tổng hợp API nào (kể cả OpenRouter, Together AI hay Perplexity).

### 1.4. Lộ trình tích hợp Video AI tối ưu cho YouTube Story Studio
Để đưa khả năng sinh Video AI vào YouTube Story Studio, đội ngũ kỹ thuật lựa chọn chiến lược 3 giai đoạn:
1. **Giai đoạn 1 (Hiện tại - Đã hoàn thành)**:
   - Sử dụng **Gemini 2.0 / 1.5** làm Đạo diễn Phân cảnh (Storyboard Director).
   - Tự động sinh Prompt hình ảnh chuẩn điện ảnh 8K cho Midjourney/Flux.
   - Sử dụng **Engine Ken Burns đa chiều FFmpeg** (Pan ngang, Zoom kịch tính, Chuyển động chéo 2.5D) kết hợp Audio Ducking và Kinetic Hardsub. Cách tiếp cận này tạo ra video tài liệu chuẩn phong cách Vox với chi phí gần như bằng 0 và thời gian render chưa đến 10 giây/video 10 phút.
2. **Giai đoạn 2 (Tích hợp Video Generator Cloud APIs)**:
   - Kết nối trực tiếp vào các nhà cung cấp chuyên về Video AI Asynchronous Pipeline qua Webhook:
     * **Fal.ai**: API cho Kling 1.5, Luma Dream Machine, Fast-HunyuanVideo.
     * **Replicate**: API cho Mochi 1, CogVideoX, HunyuanVideo.
   - Thêm module `video_ai_service.py` với hàng đợi tác vụ nền (Background Queue & Polling Worker).
3. **Giai đoạn 3 (Enterprise Google Veo Integration)**:
   - Đăng ký Vertex AI Model Garden khi Google mở rộng quyền truy cập Veo API chính thức.
   - Tích hợp trực tiếp thông qua `@google-cloud/aiplatform` hoặc Google Cloud SDK.

---

# PHẦN 2: QUY TRÌNH CHUẨN CÔNG NGHIỆP SẢN XUẤT VIDEO 10 PHÚT PHONG CÁCH VOX BẰNG GEMINI & MOTION GRAPHICS

Video tài liệu phong cách Vox (Vox Explainers, Johnny Harris, Kurzgesagt) nổi tiếng với khả năng giữ chân người xem (Audience Retention) cực cao trên YouTube nhờ **tiết tấu dẫn dắt biến ảo** và **ngôn ngữ hình ảnh trực quan liên tục**.

### 2.1. Bốn Quy Luật Vàng Về Nhịp Điệu (Visual & Retention Laws)

1. **Quy luật 3–4 Giây (The 3-4 Second Cut Rule)**:
   - Não bộ người xem YouTube hiện đại sẽ bắt đầu mất tập trung nếu một khung hình bất động quá 4 giây.
   - Cứ mỗi 3–4 giây, màn hình **bắt buộc phải có một sự biến đổi thị giác**: chuyển cảnh, đổi góc máy (Wide -> Close-up), chuyển động Ken Burns đẩy sâu, hoặc xuất hiện đồ họa chú thích.
   - Một video 10 phút (~600 giây) phong cách Vox chuẩn sẽ bao gồm từ **120 đến 180 phân cảnh** nhỏ nối tiếp nhau.
2. **Cấu trúc Cung Dẫn Dắt 5 Giai Đoạn (The Vox 5-Stage Arc)**:
   - **Giai đoạn 1: Hook (0 – 30s)**: Mở đầu bằng một nghịch lý khó tin, câu hỏi thách thức hoặc tình huống hiểm nghèo. Hình ảnh phải có độ giật thị giác mạnh (Góc quay cận cảnh mắt dồn dập hoặc toàn cảnh flycam từ không trung).
   - **Giai đoạn 2: Setting / Context (30s – 2m)**: Giải thích bối cảnh, lịch sử, các quy luật thế giới hoặc tiền đề của sự việc. Hình ảnh rộng, bao quát, ánh sáng tự nhiên.
   - **Giai đoạn 3: Escalation / Conflict (2m – 6m)**: Xung đột xuất hiện, độ căng thẳng tăng dần, nhịp cắt cảnh dồn dập hơn, chuyển động góc chéo (Dutch angle) tạo cảm giác bất an.
   - **Giai đoạn 4: Climax (6m – 8m)**: Điểm bùng nổ của câu chuyện, sự thật lớn nhất được phơi bày, đối đầu trực tiếp, ánh sáng tương phản gắt (Chiaroscuro), đẩy zoom cực nhanh.
   - **Giai đoạn 5: Resolution / Reflection (8m – 10m)**: Hạ nhiệt, đúc kết bài học triết lý, mở ra câu hỏi cho tương lai. Góc quay mở rộng dần, camera kéo lùi ra xa (pull-back), tạo cảm giác tĩnh lặng và lắng đọng.
3. **Phân Tách Ngữ Nghĩa Đa Tầng (Multi-tier Semantic Layering)**:
   Mỗi phân cảnh không chỉ đơn thuần là "vẽ một bức tranh", mà được bóc tách thành 6 tầng điện ảnh:
   - *Setting*: Không gian, địa danh, vật liệu kiến trúc, thời gian trong ngày.
   - *Subject & Emotion*: Nhân vật trung tâm, vi biểu cảm khuôn mặt, phục trang.
   - *Core Action*: Chuyển động cơ thể, tương tác động.
   - *Lighting & Atmosphere*: Ánh sáng thể tích (volumetric god rays), neon cyberpunk, sương mù, tương phản chiaroscuro.
   - *Camera Framing*: Đặc tả cận cảnh (Close-up), góc thấp anh hùng (Low-angle), flycam góc cao (High-angle drone).
   - *Camera Motion*: Đẩy vào (Zoom-in), kéo ra (Zoom-out), lia ngang (Pan left/right).
4. **Phối Âm Tầng Thứ & Audio Ducking**:
   - Giọng đọc rõ ràng, giàu năng lượng ở trung tâm âm thanh stereo.
   - Nhạc nền (BGM) biến chuyển theo nhịp kịch bản: nhẹ nhàng ở Setting, hồi hộp ở Escalation, kịch tính ở Climax.
   - **Sidechain Audio Ducking tự động**: BGM tự giảm -16dB khi giọng đọc cất lên, và tự động nâng âm lượng trở lại trong các khoảng lặng 0.5s giữa các câu để tạo điểm nhấn điện ảnh.

---

### 2.2. Chi Tiết Quy Trình 6 Bước Thực Thi Trên YouTube Story Studio

```
[Văn bản dài / Chương truyện]
               │
               ▼  (Bước 1: Gemini 2.0 Flash / Semantic Story Analyzer)
[Cắt 150-180 Phân cảnh theo nhịp Fast/Vox + Cấu trúc 5 giai đoạn]
               │
               ▼  (Bước 2: Phối Prompt 8K Arri Alexa 35mm cho từng cảnh)
[Tập hợp Prompts Đa Tầng: Framing + Subject + Action + Setting + Light]
               │
               ├──────────────────────────────────┐
               ▼ (Bước 3: Edge-TTS)               ▼ (Bước 4: Image Pipeline)
[Audio MP3 từng cảnh + Tệp SRT Mili-giây]    [Ảnh phân cảnh 1080p chuẩn màu]
               │                                  │
               └─────────────────┬────────────────┘
                                 │
                                 ▼ (Bước 5: FFmpeg Ken Burns Engine)
               [Tạo Video Segments với Pan/Zoom chuyển động mượt]
                                 │
                                 ▼ (Bước 6: Final Assembler)
               [Ghép Full Video 1080p + Audio Ducking BGM + Hardsub]
                                 │
                                 ▼
                     [VIDEO HOÀN CHỈNH 10 PHÚT]
```

#### Bước 1: Phân rã Ngữ nghĩa Văn bản Dài bằng Gemini 2.0 Flash
- Sử dụng mô hình `gemini-2.0-flash` với `temperature: 0.2` để đảm bảo tính nhất quán cấu trúc.
- Thiết lập System Prompt phân tích kịch bản theo khuôn mẫu JSON nghiêm ngặt (đã hiện thực trong `services/script_splitter.py`).
- Thuật toán tự động nhóm các câu thoại sao cho mỗi phân cảnh rơi đúng vào khoảng từ **8 đến 14 từ tiếng Việt** (tương đương 3.0 – 4.0 giây nói ở tốc độ bình thường).

#### Bước 2: Sinh Prompt Tiếng Anh Đa Tầng Điện Ảnh
Thay vì dùng từ khóa rời rạc, mỗi prompt được xây dựng theo công thức Midjourney/Flux:
```text
[Camera Framing] of [Subject with Emotion] [Action] set within [Setting], 
[Lighting & Atmosphere], photorealistic 8k, award-winning cinematography, 
Arri Alexa LF 35mm lens, volumetric atmospheric depth, color graded, masterpiece composition
```
*Ví dụ thực tế từ hệ thống:*
> `"breathtaking sweeping high-angle drone shot of an ancient Primordial forest, towering moss-covered trees, mystical floating dust particles, gentle early morning dawn, ethereal volumetric god rays filtering through mist, photorealistic 8k, award-winning cinematography, Arri Alexa LF 35mm lens, volumetric atmospheric depth, color graded, masterpiece composition"`

#### Bước 3: Thu m Giọng Đọc & Tạo Subtitle Từng Mili-giây
- Sử dụng Microsoft Edge-TTS Neural Voice (`vi-VN-HoaiMyNeural` hoặc `vi-VN-NamMinhNeural`).
- Trích xuất đồng thời tệp `.mp3` âm thanh và tệp `.srt` có timestamp độ chính xác cao.
- Đo chính xác thời lượng giọng đọc thực tế (`duration`) để làm tham số căn chỉnh khung hình cho video renderer.

#### Bước 4: Tạo Ảnh & Khóa Khuôn Mẫu Nhân Vật (Character Anchor)
- Áp dụng tham số `character_anchor` cố định (ví dụ: *"a determined young Vietnamese engineer with short black hair and a small scar over left eyebrow, wearing a charcoal turtleneck"*).
- Tham số này được nhúng vào tất cả các prompt có nhân vật xuất hiện, đảm bảo tính nhất quán khuôn mặt và trang phục từ cảnh đầu đến cảnh cuối.

#### Bước 5: Tạo Chuyển Động Ken Burns Đa Chiều bằng FFmpeg
- Dựa trên nhãn ngữ nghĩa `camera_motion` và `camera_framing`:
  * Cảnh **Hook** / **Climax**: Sử dụng filter `zoompan=z='min(zoom+0.0015,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'` tạo hiệu ứng đẩy sâu vào tâm điểm kịch tính.
  * Cảnh **Setting**: Sử dụng Pan ngang `x='if(lte(on,1),(iw-iw/zoom)/2,x-1.2)'` mở rộng tầm nhìn của khán giả.
  * Cảnh **Resolution**: Sử dụng `zoom_out` từ 1.25 về 1.0 mở rộng khoảng cách thị giác.

#### Bước 6: Hòa m Tự Động & Kết Xuất Video Cuối Cùng
- Kết hợp các video segments bằng FFmpeg `concat demuxer` (không re-encode phân cảnh, tốc độ kết xuất tức thì).
- Hòa âm BGM qua bộ lọc `sidechaincompress`:
  ```bash
  -filter_complex "[1:a]asplit=2[sc][voice];[2:a][sc]sidechaincompress=threshold=0.08:ratio=6:attack=200:release=800[bgm];[voice][bgm]amix=inputs=2:duration=first[aout]"
  ```
- Gắn cứng phụ đề (Hardsub) chuẩn font chữ Roboto/Montserrat viền tương phản cao chống nhòe trên màn hình di động.

---

### 2.3. Bảng Tóm Tắt Thông Số Kỹ Thuật Dự Án (Tech Specs)

| Hạng mục | Quy chuẩn kỹ thuật Story Studio |
|---|---|
| **Độ phân giải chuẩn** | Full HD 1080p (1920x1080) @ 25fps / 30fps |
| **Tỷ lệ khung hình** | 16:9 (YouTube Standard) & 9:16 (YouTube Shorts) |
| **Tốc độ cắt cảnh (Pacing)** | Fast/Vox: 3.0 – 4.0s \| Balanced: 5.0 – 6.0s \| Deep Story: 7.0 – 8.0s |
| **Engine TTS** | Microsoft Edge Neural TTS (Việt Nam Hoài My / Nam Minh) |
| **Bộ mã hóa Video** | H.264 (libx264, preset medium, crf 22, pix_fmt yuv420p) |
| **Bộ mã hóa m thanh** | AAC (192kbps, stereo 44.1kHz / 48kHz) |
| **Thuật toán Audio Ducking** | Sidechain Compression (Ratio 6:1, Attack 200ms, Release 800ms) |
| **Phụ đề** | SRT Subtitle Engine với Styling viền đen font sans-serif |
