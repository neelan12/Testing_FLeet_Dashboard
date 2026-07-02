# -*- coding: utf-8 -*-
"""
MTC Bus ITS Portal - Fleet Dashboard Downloader (GitHub Actions)
================================================================
Runs a HEADED browser under Xvfb so the client-side canvas captcha renders
with real fonts, reads it with easyOCR (same pattern as the working local
script), logs in, opens AVLS, searches the Fleet Dashboard report and exports
the Excel file.

NOTE: the login password comes from the LOGIN_PASSWORD env var, but falls back
to the hardcoded default if that var is missing OR empty (an unset GitHub
secret is injected as an empty string, which previously blanked the password
field and caused every login to fail with 'Username and Password Required').
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
# Empty env var must fall back to the default -> use `or`, NOT os.environ.get default
PASSWORD = os.environ.get("LOGIN_PASSWORD") or "Neelan@123"

today_str = datetime.now().strftime("%d-%m-%Y")
new_filename = f"Fleet Dashboard {today_str}.xlsx"
destination_folder = os.environ.get('DOWNLOAD_PATH', 'Fleet_Dashboard_Files')
final_path = os.path.join(destination_folder, new_filename)

os.makedirs(destination_folder, exist_ok=True)
if os.path.exists(final_path):
    os.remove(final_path)
    print(f"🗑️ Existing file deleted: {final_path}")


def fill_credentials(page):
    """Fill username + password and verify they actually stuck (Angular form)."""
    page.fill("input[name='UserName']", USERNAME)
    page.fill("input[id='password']", PASSWORD)
    # Verify - re-fill once if the value did not register
    if not page.input_value("input[name='UserName']"):
        page.locator("input[name='UserName']").click()
        page.locator("input[name='UserName']").press_sequentially(USERNAME, delay=40)
    if not page.input_value("input[id='password']"):
        page.locator("input[id='password']").click()
        page.locator("input[id='password']").press_sequentially(PASSWORD, delay=40)


def main():
    import easyocr
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headed under Xvfb
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(60_000)

        try:
            print("[LOGIN]  Opening login page...")
            page.goto("https://mtcbusits.in/")
            page.wait_for_load_state("networkidle")

            logged_in = False
            for attempt in range(1, 21):
                # Always (re-)fill credentials in case a refresh/reload cleared them
                fill_credentials(page)

                # Read captcha from the single data:image on the page
                captcha_img_src = page.get_attribute('img[src^="data:image"]', "src")
                if captcha_img_src and captcha_img_src.startswith("data:image"):
                    image_data = base64.b64decode(captcha_img_src.split(",")[1])
                    result = reader.readtext(image_data, detail=0, mag_ratio=2)
                    captcha = re.sub(r'[^A-Za-z0-9]', '', "".join(result).strip())
                else:
                    captcha = re.sub(r'[^A-Za-z0-9]', '', page.inner_text("span.input-group-addon").strip())

                u_ok = bool(page.input_value("input[name='UserName']"))
                p_ok = bool(page.input_value("input[id='password']"))
                print(f"[LOGIN]  Attempt {attempt}/20 | user_filled={u_ok} pass_filled={p_ok} | captcha='{captcha}'")

                page.fill("input[formcontrolname='captcha']", captcha)
                page.click("button:has-text('Login')")

                # Wait up to 10s for the URL to leave the login page
                for _ in range(50):
                    page.wait_for_timeout(200)
                    if "login" not in page.url and page.url.rstrip("/") != "https://mtcbusits.in":
                        break

                if "login" not in page.url and page.url.rstrip("/") != "https://mtcbusits.in":
                    print(f"[LOGIN]  ✅ Successfully logged in on attempt {attempt}! URL={page.url}")
                    logged_in = True
                    break

                print(f"[LOGIN]  ❌ Attempt {attempt}/20 rejected. Refreshing captcha...")
                try:
                    old_src = captcha_img_src
                    page.locator(".k-i-reload").click(timeout=1500)
                    for _ in range(25):
                        page.wait_for_timeout(200)
                        new_src = page.get_attribute('img[src^="data:image"]', "src")
                        if new_src and new_src != old_src:
                            break
                except Exception:
                    pass

            if not logged_in:
                raise Exception("All 20 login attempts failed")

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
            print(f"[SAVED]  ✅ {final_path}")

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
