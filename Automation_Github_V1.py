# -*- coding: utf-8 -*-
"""
MTC Bus ITS Portal - Fleet Dashboard Downloader (GitHub Actions)
================================================================
Uses the exact login/captcha pattern from the verified working local
script, but runs a HEADED browser under Xvfb so the client-side canvas
captcha renders with real fonts (headless Chromium renders it badly and
easyOCR then fails). After login it navigates to AVLS, searches for the
Fleet Dashboard report and exports the Excel file.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import re
import base64
from datetime import datetime
from playwright.sync_api import sync_playwright

# ── CONFIG ───────────────────────────────────────────────────
USERNAME = "neelan.ibi"

today_str = datetime.now().strftime("%d-%m-%Y")
new_filename = f"Fleet Dashboard {today_str}.xlsx"
destination_folder = os.environ.get('DOWNLOAD_PATH', 'Fleet_Dashboard_Files')
final_path = os.path.join(destination_folder, new_filename)

os.makedirs(destination_folder, exist_ok=True)
if os.path.exists(final_path):
    os.remove(final_path)
    print(f"🗑️ Existing file deleted: {final_path}")

DEBUG_DIR = "captcha_debug"
os.makedirs(DEBUG_DIR, exist_ok=True)


def main():
    import easyocr
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)

    with sync_playwright() as p:
        # HEADED under Xvfb so the canvas captcha renders with real fonts
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(60_000)

        try:
            # ── Login (exact working pattern) ──────────────────────
            print("[LOGIN]  ...")
            page.goto("https://mtcbusits.in/")
            page.fill("input[name='UserName']", USERNAME)
            password = os.environ.get('LOGIN_PASSWORD', 'Neelan@123')
            page.fill("input[id='password']", password)

            logged_in = False
            for attempt in range(15):
                captcha_img_src = page.get_attribute('img[src^="data:image"]', "src")
                if captcha_img_src and captcha_img_src.startswith("data:image"):
                    # Save the image so it can be inspected from the artifact if needed
                    if attempt < 3:
                        try:
                            with open(os.path.join(DEBUG_DIR, f"captcha_attempt{attempt+1}.png"), "wb") as f:
                                f.write(base64.b64decode(captcha_img_src.split(",")[1]))
                        except Exception:
                            pass
                    image_data = base64.b64decode(captcha_img_src.split(",")[1])
                    result = reader.readtext(image_data, detail=0, mag_ratio=2)
                    captcha = re.sub(r'[^A-Za-z0-9]', '', "".join(result).strip())
                    print(f"[LOGIN]  CAPTCHA via OCR (attempt {attempt+1}/15): {captcha}")
                else:
                    captcha = page.inner_text("span.input-group-addon").strip()
                    captcha = re.sub(r'[^A-Za-z0-9]', '', captcha)
                    print(f"[LOGIN]  CAPTCHA via text (attempt {attempt+1}/15): {captcha}")

                page.fill("input[formcontrolname='captcha']", captcha)
                page.click("button:has-text('Login')")

                # Wait up to 10s for URL to change to confirm login
                for _ in range(50):
                    page.wait_for_timeout(200)
                    if "login" not in page.url and page.url != "https://mtcbusits.in/":
                        break

                if "login" not in page.url and page.url != "https://mtcbusits.in/":
                    print("[LOGIN]  Successfully logged in!")
                    logged_in = True
                    break

                print(f"[LOGIN]  OCR guessed wrong (attempt {attempt+1}/15). Retrying...")
                try:
                    old_src = captcha_img_src
                    page.locator(".k-i-reload").click(timeout=1000)
                    for _ in range(25):
                        page.wait_for_timeout(200)
                        new_src = page.get_attribute('img[src^="data:image"]', "src")
                        if new_src and new_src != old_src:
                            break
                except Exception:
                    pass

            if not logged_in:
                raise Exception("All 15 login attempts failed - check credentials")

            # ── Navigate to AVLS ──────────────────────────────────
            print("[NAV]    Navigating to AVLS section...")
            page.goto("https://mtcbusits.in/avls/")
            page.wait_for_timeout(10_000)
            try:
                page.locator("#nb-global-spinner").wait_for(state="hidden", timeout=60_000)
            except Exception:
                pass
            print("[NAV]    AVLS section loaded.")

            # ── Search for Fleet Dashboard ──────────────────────────
            print("[SEARCH] Searching for Fleet Dashboard...")
            search_box = page.locator("input[placeholder='Search']")
            search_box.fill("Fleet Dashboard")
            search_box.press("Enter")
            page.wait_for_timeout(15_000)

            # ── Export Excel ─────────────────────────────────────
            print("[EXPORT] Downloading Excel file...")
            export_button = page.get_by_role("button", name="Export Excel All Data")
            export_button.scroll_into_view_if_needed()

            with page.expect_download(timeout=90_000) as download_info:
                export_button.click()

            download_info.value.save_as(final_path)
            print(f"[SAVED]  {final_path}")

        except Exception as e:
            try:
                page.screenshot(path="error_screenshot.png")
            except Exception:
                pass
            print(f"[ERROR]  {str(e)}")
            raise
        finally:
            browser.close()

    print("✅ Process completed successfully!")
    return final_path


if __name__ == "__main__":
    main()
