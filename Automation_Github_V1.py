from playwright.sync_api import sync_playwright
from datetime import datetime
import os
import base64
import re

# Step 0: Setup paths and file name
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


def save_debug_captcha_images(page, attempt):
    """Save every data:image element on the page so we can see what the OCR is actually reading."""
    imgs = page.query_selector_all('img[src^="data:image"]')
    print(f"🔍 Found {len(imgs)} data:image element(s) on page (attempt {attempt})")
    for idx, img in enumerate(imgs):
        try:
            src = img.get_attribute("src")
            if not src:
                continue
            img_bytes = base64.b64decode(src.split(",")[1])
            out_path = os.path.join(DEBUG_DIR, f"attempt{attempt}_img{idx}.png")
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            print(f"   💾 Saved {out_path} ({len(img_bytes)} bytes)")
        except Exception as e:
            print(f"   ⚠️ Could not save image {idx}: {e}")


def main():
    import easyocr
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(60000)

        try:
            # ── Step 1: Login ──────────────────────────────────────────────
            print("🔐 Navigating to login page...")
            page.goto("https://mtcbusits.in/")
            page.wait_for_load_state("networkidle")
            print("✅ Page fully loaded")
            page.screenshot(path=os.path.join(DEBUG_DIR, "full_page_before_login.png"), full_page=True)

            page.fill("input[name='UserName']", "neelan.ibi")
            password = os.environ.get('LOGIN_PASSWORD', 'Neelan@123')
            page.fill("input[id='password']", password)

            logged_in = False
            for attempt in range(1, 16):
                # Save every data:image element for debugging (first 3 attempts only, to limit artifact size)
                if attempt <= 3:
                    save_debug_captcha_images(page, attempt)

                # Read captcha from base64 inline image src (last matching image, in case
                # earlier data:image elements on the page are logos/icons, not the captcha)
                imgs = page.query_selector_all('img[src^="data:image"]')
                captcha_img_src = imgs[-1].get_attribute("src") if imgs else None

                if captcha_img_src and captcha_img_src.startswith("data:image"):
                    image_data = base64.b64decode(captcha_img_src.split(",")[1])
                    result = reader.readtext(image_data, detail=0, mag_ratio=2)
                    captcha = re.sub(r'[^A-Za-z0-9]', '', "".join(result).strip())
                    print(f"🔢 CAPTCHA via easyocr (attempt {attempt}, img_count={len(imgs)}): {captcha}")
                else:
                    captcha = page.inner_text("span.input-group-addon").strip()
                    captcha = re.sub(r'[^A-Za-z0-9]', '', captcha)
                    print(f"🔢 CAPTCHA via DOM text (attempt {attempt}): {captcha}")

                page.fill("input[formcontrolname='captcha']", captcha)
                page.click("button:has-text('Login')")

                # Wait up to 10s for URL to change away from login page
                for _ in range(50):
                    page.wait_for_timeout(200)
                    if "login" not in page.url and page.url != "https://mtcbusits.in/":
                        break

                if "login" not in page.url and page.url != "https://mtcbusits.in/":
                    print(f"✅ Login successful on attempt {attempt}!")
                    logged_in = True
                    break

                print(f"❌ OCR guessed wrong (attempt {attempt}/15). Refreshing captcha...")
                try:
                    old_src = captcha_img_src
                    page.locator(".k-i-reload").click(timeout=1000)
                    for _ in range(25):
                        page.wait_for_timeout(200)
                        new_imgs = page.query_selector_all('img[src^="data:image"]')
                        new_src = new_imgs[-1].get_attribute("src") if new_imgs else None
                        if new_src and new_src != old_src:
                            break
                except Exception:
                    pass

            if not logged_in:
                raise Exception("❌ All 15 login attempts failed - check credentials")

            # ── Step 2: Navigate directly to AVLS section ──────────────────
            print("📊 Navigating to AVLS section...")
            page.goto("https://mtcbusits.in/avls/")
            page.wait_for_load_state("networkidle")
            try:
                page.locator("#nb-global-spinner").wait_for(state="hidden", timeout=60000)
            except Exception:
                pass
            print("✅ AVLS section loaded")

            # ── Step 3: Search for Fleet Dashboard ─────────────────────────
            print("🔍 Searching for Fleet Dashboard...")
            search_box = page.locator("input[placeholder='Search']")
            search_box.fill("Fleet Dashboard")
            search_box.press("Enter")
            page.wait_for_timeout(15000)

            # ── Step 4: Export Excel and save ──────────────────────────────
            print("📥 Downloading Excel file...")
            export_button = page.get_by_role("button", name="Export Excel All Data")
            export_button.scroll_into_view_if_needed()

            with page.expect_download(timeout=90000) as download_info:
                export_button.click()

            download = download_info.value
            download.save_as(final_path)
            print(f"✅ File downloaded: {final_path}")

        except Exception as e:
            page.screenshot(path="error_screenshot.png")
            print(f"❌ Error occurred: {str(e)}")
            raise
        finally:
            browser.close()

    print("✅ Process completed successfully!")
    return final_path


if __name__ == "__main__":
    main()
