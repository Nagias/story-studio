# Nguồn hiệu ứng âm thanh CC0 / Public Domain

Tải ngày 26/10/2026. Chỉ nhận file có giấy phép CC0 hoặc Public Domain, xem trực tiếp trên trang nguồn (Wikimedia Commons đọc qua API `extmetadata` + mã nguồn trang; OpenGameArt đọc khối "License(s)" trên trang). Không đăng nhập ở đâu.

Xử lý: `goc/` giữ file gốc nguyên vẹn. `wav/<tên>.wav` = cắt đoạn (cột "Đoạn lấy"), chuyển 48 kHz / stereo / 16-bit, cắt im lặng đầu/cuối (tiếng nền: chỉ cắt im lặng tuyệt đối < -80 dBFS; tiếng đơn: ngưỡng thấp hơn đỉnh 60 dB), chuẩn hoá đỉnh -3 dBFS bằng ffmpeg. `bgm/<tên>.mp3` = 48 kHz stereo, 192 kbps, đỉnh -1 dBFS.

Ghi chú tên giấy phép: trên Commons, "Public domain" là tên giấy phép rút gọn (LicenseShortName) hiển thị trên trang; trong ngoặc là bản mẫu (template) giấy phép ghi trên trang. File gốc PDSounds.org được trang Commons ghi `{{PD-pdsounds.org}}` + `{{PD-author|<tác giả>}}` (tác giả tự đưa vào phạm vi công cộng).

## Hiệu ứng (wav)

| Tên | Trang nguồn | Tác giả | Giấy phép (trên trang) | Đoạn lấy từ file gốc | Thời lượng sau xử lý | Ghi chú |
|---|---|---|---|---|---|---|
| rain_heavy | https://commons.wikimedia.org/wiki/File:Rain_(1).ogg | ezwa | Public domain (PD-author, PD-pdsounds.org) | 10–40 s | 30,00 s | mưa to ("Raining cats and dogs") |
| rain_on_window | https://commons.wikimedia.org/wiki/File:Rain_against_the_window.ogg | cori | Public domain (PD-author, PD-pdsounds.org) | 2–32 s | 30,00 s | mưa + gió đập kính |
| thunder_distant | https://commons.wikimedia.org/wiki/File:Tonitrus.ogg | Mysid | Public domain (PD-self) | 10–30 s | 20,00 s | sấm rền, ghi ở Phần Lan |
| wind_howl | https://commons.wikimedia.org/wiki/File:Howling_wind.ogg | Tvabutzku1234 | CC0 (Creative Commons Zero, Public Domain Dedication) | 30–60 s | 30,00 s | gió hú trong toà nhà |
| wind_soft | https://commons.wikimedia.org/wiki/File:Vento_fisterra.ogg | Escoitar.org | Public domain (PD-self) | 30–60 s | 30,00 s | đoạn gió nhẹ đầu bản ghi |
| fire_crackle | https://commons.wikimedia.org/wiki/File:Dry_grass_burning_in_open_fireplace.ogg | ezwa | Public domain (PD-author, PD-pdsounds.org) | cả file | 25,49 s | cỏ khô cháy trong lò sưởi |
| footsteps_indoor | https://opengameart.org/content/steps-in-wood-floor | mikeask | CC0 | cả file | 3,48 s | bước chân trên sàn gỗ |
| footsteps_wet | https://commons.wikimedia.org/wiki/File:Forest_track.ogg | tball74 | Public domain (PD-author, PD-pdsounds.org) | cả file | 22,10 s | đi chậm trên đường rừng ướt, đá sỏi; khá nhỏ, có 1 bước to ở giây 12 |
| door_creak | https://commons.wikimedia.org/wiki/File:Squeaky_door.ogg | leonmire | Public domain (PD-author, PD-pdsounds.org) | cả file | 7,99 s | cửa kẽo kẹt mở/đóng |
| door_knock | https://commons.wikimedia.org/wiki/File:Knocking_on_wood_or_door.ogg | stephan | Public domain (PD-author, PD-pdsounds.org) | cả file | 6,24 s | 3 lượt gõ |
| door_slam_metal | https://commons.wikimedia.org/wiki/File:Son_de_l%27ouverture_et_fermeture_du_portail_du_cimeti%C3%A8re_du_Mas_Rillier.ogg | Benoît Prieur | CC0 (Creative Commons Zero, Public Domain Dedication) | 8 s–hết | 9,13 s | cổng sắt nghĩa trang đóng lại (kẽo kẹt + tiếng chốt), không phải sập mạnh. File gốc đổi tên ASCII: `goc/door_slam_metal/Son_portail_cimetiere_Mas_Rillier.ogg` |
| clock_ticking | https://commons.wikimedia.org/wiki/File:Clock_ticking.ogg | natalie | Public domain (PD-author, PD-pdsounds.org) | cả file | 18,05 s | đồng hồ nhựa ghi rất gần |
| heartbeat | https://commons.wikimedia.org/wiki/File:Athletic_bradycardia_wav.wav | Athletearrhythmia | CC0 (Creative Commons Zero, Public Domain Dedication) | cả file | 19,95 s | tim người thật, chậm 42 nhịp/phút |
| paper_rustle | https://commons.wikimedia.org/wiki/File:Book_paper_pages_assorted.ogg | stephan | Public domain (PD-author, PD-pdsounds.org) | 56–76 s | 20,00 s | lật/sột soạt giấy, sách |
| camera_shutter | https://commons.wikimedia.org/wiki/File:Holga_shuttersound.ogg | Doitashimashite (nl.wikipedia) | Public domain (PD-user-nl) | cả file | 2,01 s | màn trập máy Holga 120S |
| police_radio_static | https://opengameart.org/content/radio-noise-1 | Kresiek The Furry | CC0 | 0–20 s | 20,00 s | nhiễu thật thu từ máy dò sóng Uniden SDS100; gốc 8 kHz mono nên tiếng "rè" kiểu bộ đàm |
| siren_distant | https://commons.wikimedia.org/wiki/File:American_police_siren_i.ogg | lezer | Public domain (PD-author, PD-pdsounds.org) | cả file | 29,20 s | còi cảnh sát Washington DC nghe từ trong căn hộ |
| fluorescent_hum | https://commons.wikimedia.org/wiki/File:MainsBrum50Hz.ogg | Julo | Public domain (PD-self) | 0,2–5,2 s, lặp 4 lần | 20,00 s | TẠM: tiếng ù điện lưới 50 Hz ghi qua ampli, không phải đèn tuýp thật; rất đặc, cần để nhỏ |
| water_drip | https://opengameart.org/content/water-drops | CeoxBlackj | CC0 | 0–30 s | 30,00 s | trang không ghi rõ là ghi âm hay tổng hợp |
| glass_break | https://opengameart.org/content/glass-break | Till Behrend | CC0 | cả file | 1,25 s | ngắn hơn 2 s (tiếng vỡ tự nhiên ngắn); trang không ghi rõ là ghi âm hay tổng hợp |
| dark_drone | https://opengameart.org/content/ambient-horror | techiew | CC0 | cả file | 22,19 s | trang ghi "Random recording" |
| city_night_ambience | https://commons.wikimedia.org/wiki/File:Two_Lane_Road_in_Kelowna_at_Midnight.flac | Extemporalist | CC0 (Creative Commons Zero, Public Domain Dedication) | 420–450 s | 30,00 s | đường 2 làn lúc nửa đêm, có 2 xe chạy qua; gốc rất nhỏ nên đã tăng ~30 dB |
| dog_bark_distant | https://opengameart.org/content/dog-barking-mono | HaelDB | OGA-BY 3.0, CC0 (trang cho chọn 1 trong 2; dùng theo CC0) | file `dog_barking.wav`, cả file | 6,47 s | chó sủa ghi bằng Tascam, nghe gần chứ không xa |
| impact_hit | https://commons.wikimedia.org/wiki/File:Timpani_64-c-p5.wav | spt3125 (gốc Freesound 24820) | CC0 (Creative Commons Zero, Public Domain Dedication) | 5,0–10,6 s (cú đánh thứ 2) | 3,14 s | trống timpani thật, tiếng "bùm" trầm |

## Nhạc nền (mp3, không lời)

| Tên | Trang nguồn | Tác giả | Giấy phép (trên trang) | Thời lượng | Ghi chú |
|---|---|---|---|---|---|
| bgm_dark_ambient | https://commons.wikimedia.org/wiki/File:John_Bartmann_-_dark-basement-master.ogg (gốc: https://freemusicarchive.org/music/John_Bartmann/100-ambient-atmospheric-soundtracks-straylight-drones-collection/dark-basement-master) | John Bartmann | Commons: CC0 (Creative Commons Zero, Public Domain Dedication); Free Music Archive: CC0 1.0 Universal License | 244,01 s | album "100 Ambient Atmospheric Soundtracks – Straylight Drones Collection"; nhạc điện tử (không phải ghi âm hiện trường) |
| bgm_suspense | https://commons.wikimedia.org/wiki/File:John_Bartmann_-_broken-suspense-master.ogg (gốc: https://freemusicarchive.org/music/John_Bartmann/100-ambient-atmospheric-soundtracks-straylight-drones-collection/broken-suspense-master) | John Bartmann | Commons: CC0 (Creative Commons Zero, Public Domain Dedication); Free Music Archive: CC0 1.0 Universal License | 244,01 s | cùng album |

## Đã loại (giấy phép không đạt hoặc nghi ngờ)

| File | Lý do |
|---|---|
| https://commons.wikimedia.org/wiki/File:Walking-on-gravel-38827.ogg | Commons ghi CC0 nhưng nguồn là Pixabay (giấy phép Pixabay, không phải CC0), không rõ tác giả |
| https://opengameart.org/content/rain-on-window-loop | trang ghi nhiều giấy phép (CC-BY 4.0, CC-BY 3.0, OGA-BY 3.0, CC0); không cần dùng vì đã có bản PD |
| Các file của DrTrumpet trên Commons (bước chân đêm, giao thông Wien có còi) | CC BY-SA 4.0 |
| https://opengameart.org/content/wind1, https://opengameart.org/content/heartbeat-sounds, https://opengameart.org/content/static | CC0 nhưng là âm tổng hợp (PureData / FL Studio / tự tạo), không phải ghi âm |
| https://commons.wikimedia.org/wiki/File:Dog.ogg | PD nhưng là chó liếm chân, ngáp, không sủa |
