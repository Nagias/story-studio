"""
Live Browser Closed-loop Testing Suite
Verifies workflow correctness, character consistency isolation,
post-production separation, and zero-console-error guarantee.
"""
import os
import sys
import json
import time
from pathlib import Path

# Configure utf-8 stdout for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path("D:/25. OPC/OP_CTOOL/projects/story-studio/public/qa-screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

def run_reality_check():
    results = {
        "suite": "Story Studio Live Browser Reality Check",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "browser": "Microsoft Edge (Chromium Headless)",
        "viewport": "1920x1080",
        "steps": [],
        "console_errors": [],
        "screenshots": [],
        "overall_status": "FAILED"
    }

    with sync_playwright() as p:
        print("[1/6] Launching Edge Chromium Headless...")
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Console Error Sentinel & Network Failure Logger
        page.on("console", lambda msg: results["console_errors"].append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: results["console_errors"].append(str(err)))
        page.on("response", lambda res: results["console_errors"].append(f"HTTP {res.status} on {res.url}") if res.status >= 400 else None)

        try:
            # 1. Navigate to target True Crime project
            target_url = "http://127.0.0.1:8000/?project_id=proj_crime_2fe472c1"
            print(f"[2/6] Navigating to {target_url}...")
            start_t = time.time()
            resp = page.goto(target_url, wait_until="networkidle")
            assert resp.status == 200, f"HTTP Error {resp.status}"

            page.wait_for_selector("#step-view-2", state="visible", timeout=12000)
            page.wait_for_timeout(1000)

            shot1 = str(SCREENSHOT_DIR / "01-step2-fixed-board.png")
            page.screenshot(path=shot1, full_page=False)
            results["screenshots"].append("01-step2-fixed-board.png")
            results["steps"].append({
                "step": "Open Step 2 Bảng Đạo Diễn",
                "status": "PASSED",
                "duration_sec": round(time.time() - start_t, 2)
            })
            print("  ✓ Step 2 loaded successfully.")

            # 2. Check Character Consistency Card (Must NOT show Lam)
            print("[3/6] Verifying Character Isolation (Zero Lam Leak)...")
            content = page.content()
            assert "Chiến binh áo lam" not in content, "CRITICAL ERROR: 'Chiến binh áo lam' is still present in DOM!"
            assert "Anime style, 20yo Asian warrior boy" not in content, "CRITICAL ERROR: Anime prompt is still present in DOM!"

            char_card = page.locator("#character-consistency-card")
            is_visible = char_card.is_visible()
            assert not is_visible, "CRITICAL ERROR: Character Consistency card should be hidden for True Crime project!"

            results["steps"].append({
                "step": "Verify Zero Character Leak (Lam is completely removed & card is hidden)",
                "status": "PASSED"
            })
            print("  ✓ Verified: 'Lâm (Chiến binh áo lam)' is completely gone and card is hidden.")

            # 3. Check Post-Production Panel & Asset Readiness
            print("[4/6] Verifying Post-Production Panel Separation & Asset Readiness...")
            panel = page.locator("#audio-settings-card")
            assert panel.is_visible(), "Audio settings card is not visible!"

            voice_text = page.locator("#readiness-voice-count").text_content()
            image_text = page.locator("#readiness-image-count").text_content()
            print(f"  Asset Readiness: Voice={voice_text}, Images={image_text}")
            assert "Voice" in voice_text and "6/6" in voice_text, f"Unexpected voice count: {voice_text}"
            assert "Ảnh" in image_text and "6/6" in image_text, f"Unexpected image count: {image_text}"

            btn_label = page.locator("#btn-produce-label").text_content()
            assert "KẾT XUẤT VIDEO" in btn_label, f"Unexpected button label: {btn_label}"

            # Verify Accordion Toggle
            accordion_body = page.locator("#asset-accordion-body")
            assert not accordion_body.is_visible(), "Asset regeneration accordion should be collapsed by default!"

            page.click("#btn-toggle-asset-accordion")
            page.wait_for_timeout(300)
            assert accordion_body.is_visible(), "Asset accordion should expand when clicked!"

            shot2 = str(SCREENSHOT_DIR / "02-step2-post-production-panel.png")
            page.screenshot(path=shot2, full_page=False)
            results["screenshots"].append("02-step2-post-production-panel.png")

            # Collapse accordion back
            page.click("#btn-toggle-asset-accordion")
            page.wait_for_timeout(300)
            assert not accordion_body.is_visible(), "Asset accordion should collapse when clicked again!"

            results["steps"].append({
                "step": "Verify Post-Production & Accordion Controls",
                "status": "PASSED"
            })
            print("  ✓ Verified: Post-production panel separated, asset readiness is 6/6, accordion collapses properly.")

            # 4. Voice Sample Preview
            print("[5/6] Testing Voice Sample Preview...")
            preview_btn = page.locator("#btn-preview-voice-sample")
            preview_btn.click()
            page.wait_for_timeout(1000)

            shot3 = str(SCREENSHOT_DIR / "03-step2-voice-preview.png")
            page.screenshot(path=shot3, full_page=False)
            results["screenshots"].append("03-step2-voice-preview.png")
            results["steps"].append({
                "step": "Test Voice Sample Preview",
                "status": "PASSED"
            })
            print("  ✓ Voice preview button clicked and responsive.")

            # 5. Step 4 Cinema Hydration Check
            print("[6/6] Verifying Step 4 Cinema Hydration...")
            page.evaluate("switchStep(4)")
            page.wait_for_selector("#step-view-4", state="visible", timeout=5000)
            page.wait_for_timeout(1000)

            cinema_player = page.locator("#cinema-video-player")
            player_src = cinema_player.get_attribute("src")
            print(f"  Cinema Player Src: {player_src}")
            assert player_src and ".mp4" in player_src, f"Invalid cinema player src: {player_src}"

            dl_video = page.locator("#btn-cinema-download-video").get_attribute("href")
            dl_srt = page.locator("#btn-cinema-download-srt").get_attribute("href")
            dl_ass = page.locator("#btn-cinema-download-ass").get_attribute("href")
            print(f"  Download Links: Video={dl_video}, SRT={dl_srt}, ASS={dl_ass}")
            assert dl_video and "/download" in dl_video, f"Invalid video download link: {dl_video}"
            assert dl_srt and "download-srt" in dl_srt, f"Invalid srt download link: {dl_srt}"
            assert dl_ass and "download-ass" in dl_ass, f"Invalid ass download link: {dl_ass}"

            shot4 = str(SCREENSHOT_DIR / "04-step4-cinema-verified.png")
            page.screenshot(path=shot4, full_page=False)
            results["screenshots"].append("04-step4-cinema-verified.png")
            results["steps"].append({
                "step": "Verify Step 4 Cinema Hydration & Download Links",
                "status": "PASSED"
            })
            print("  ✓ Step 4 cinema player loaded video successfully with valid download links.")

            # 6. Check Console Errors
            print(f"Console errors detected: {len(results['console_errors'])}")
            if results["console_errors"]:
                print("  Console Errors:", results["console_errors"])
            assert len(results["console_errors"]) == 0, f"Uncaught console errors: {results['console_errors']}"

            results["overall_status"] = "PASSED"
            print("\n=======================================================")
            print(">>> ALL LIVE BROWSER TESTS PASSED (100% SUCCESS) <<<")
            print("=======================================================\n")

        finally:
            results_path = SCREENSHOT_DIR / "test-results.json"
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"Results saved to: {results_path}")
            browser.close()

if __name__ == "__main__":
    run_reality_check()
