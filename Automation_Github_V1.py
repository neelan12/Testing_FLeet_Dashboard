from playwright.sync_api import sync_playwright
from datetime import datetime
import os
import base64
import io

# Step 0: Setup paths and file name
today_str = datetime.now().strftime("%d-%m-%Y")
new_filename = f"Fleet Dashboard {today_str}.xlsx"

destination_folder = os.environ.get('DOWNLOAD_PATH', 'Fleet_Dashboard_Files')
final_path = os.path.join(destination_folder, new_filename)

os.makedirs(destination_folder, exist_ok=True)
if os.path.exists(final_path):
    os.remove(final_path)
    print(f"🗑️ Existing file deleted: {final_path}")


def solve_captcha(page):
    """Extract captcha alphanumeric text from canvas/image using OCR."""
    from PIL import Image, ImageEnhance, ImageFilter
    import pytesseract

    ocr_config = '--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

    def preprocess_and_ocr(img):
        img = img.convert('L')
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = img.filter(ImageFilter.SHARPEN)
        text = pytesseract.image_to_string(img, config=ocr_config).strip()
        return ''.join(c for c in text if c.isalnum())

    # Method 1: Canvas-based captcha
    try:
        canvases = page.evaluate("""
            () => {
                const canvases = document.querySelectorAll('canvas');
                return Array.from(canvases).map(c => c.toDataURL('image/png'));
            }
        """)
        for canvas_data in (canvases or []):
            if not canvas_data:
                continue
            img_data = base64.b64decode(canvas_data.split(',')[1])
            img = Image.open(io.BytesIO(img_data))
            text = preprocess_and_ocr(img)
            if text:
                print(f"📸 Captcha via canvas OCR: {text}")
                return text
    except Exception as e:
        print(f"Canvas method failed: {e}")

    # Method 2: Captcha image element screenshot
    captcha_selectors = [
        ".captcha img",
        "img[src*='captcha']",
        "img[id*='captcha']",
        "img[class*='captcha']",
        "img[alt*='captcha']",
        "#captchaImage",
        "app-captcha img",
    ]
    for selector in captcha_selectors:
        try:
            el = page.locator(selector).first
            if el.count() > 0 and el.is_visible(timeout=3000):
                screenshot_bytes = el.screenshot()
                img = Image.open(io.BytesIO(screenshot_bytes))
                text = preprocess_and_ocr(img)
                if text:
                    print(f"📸 Captcha via image OCR ({selector}): {text}")
                    return text
        except Exception:
            continue

    # Method 3: DOM text fallback
    try:
        text = page.inner_text("span.input-group-addon", timeout=10000).strip()
        text = ''.join(c for c in text if c.isalnum())
        if text:
            print(f"📸 Captcha from DOM text: {text}")
            return text
    except Exception as e:
        print(f"DOM text method failed: {e}")

    raise Exception("❌ Could not solve captcha - all methods failed")


def try_login(page, password, attempt=1):
    """Attempt login and verify it succeeded. Returns True on success."""
    print(f"🔢 Solving captcha (attempt {attempt})...")

    # Re-fill credentials in case page refreshed
    page.fill("input[name='UserName']", "neelan.ibi")
    page.fill("input[id='password']", password)

    captcha_text = solve_captcha(page)
    page.fill("input[formcontrolname='captcha']", captcha_text)
    page.click("button:has-text('Login')")

    # Wait for page to settle after clicking login
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Check if login actually succeeded by looking for post-login elements
    # If still on login page, login failed
    still_on_login = False
    try:
        if page.locator("input[name='UserName']").is_visible(timeout=3000):
            still_on_login = True
    except Exception:
        pass

    if still_on_login:
        print(f"❌ Login attempt {attempt} failed (wrong captcha or credentials)")
        return False

    print(f"✅ Login successful on attempt {attempt}")
    return True


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(60000)

        try:
            # Step 1: Navigate to site
            print("🔐 Logging in...")
            page.goto("https://mtcbusits.in/")
            page.wait_for_load_state("networkidle")
            print("✅ Page fully loaded")

            password = os.environ.get('LOGIN_PASSWORD', 'Neelan@123')

            # Retry login up to 3 times (in case OCR misreads captcha)
            logged_in = False
            for attempt in range(1, 4):
                if try_login(page, password, attempt):
                    logged_in = True
                    break
                if attempt < 3:
                    print(f"🔄 Retrying login... reloading page to get fresh captcha")
                    page.reload()
                    page.wait_for_load_state("networkidle")

            if not logged_in:
                raise Exception("❌ All 3 login attempts failed - check credentials or captcha")

            # Step 2: Navigate to AVLS section
            print("📊 Navigating to AVLS section...")
            avls_selectors = [
                "p:has-text('AVLS')",
                "a:has-text('AVLS')",
                "span:has-text('AVLS')",
                "li:has-text('AVLS')",
                "div:has-text('AVLS')",
                "[class*='menu'] :has-text('AVLS')",
            ]
            avls_clicked = False
            for selector in avls_selectors:
                try:
                    el = page.locator(selector).first
                    if el.count() > 0 and el.is_visible(timeout=5000):
                        el.click()
                        avls_clicked = True
                        print(f"✅ Clicked AVLS via: {selector}")
                        break
                except Exception:
                    continue

            if not avls_clicked:
                page.screenshot(path="avls_not_found.png")
                raise Exception("❌ Could not find AVLS navigation element - page structure may have changed")

            # Wait until spinner disappears
            print("⏳ Waiting for AVLS data to load...")
            page.locator("#nb-global-spinner").wait_for(state="hidden", timeout=60000)
            print("✅ AVLS section loaded")

            # Step 3: Search for Fleet Dashboard
            search_box = page.locator("input[placeholder='Search']")
            search_box.fill("Fleet Dashboard")
            search_box.press("Enter")
            page.wait_for_timeout(15000)

            # Step 4: Export Excel and save
            print("📥 Downloading Excel file...")
            export_button = page.get_by_role("button", name="Export Excel All Data")
            export_button.scroll_into_view_if_needed()

            with page.expect_download() as download_info:
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
