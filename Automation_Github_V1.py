from playwright.sync_api import sync_playwright
from datetime import datetime
import os
import base64
import io

# Step 0: Setup paths and file name
today_str = datetime.now().strftime("%d-%m-%Y")
new_filename = f"Fleet Dashboard {today_str}.xlsx"

# Output folder (GitHub Actions default = Fleet_Dashboard_Files)
destination_folder = os.environ.get('DOWNLOAD_PATH', 'Fleet_Dashboard_Files')
final_path = os.path.join(destination_folder, new_filename)

# Delete file if it exists
os.makedirs(destination_folder, exist_ok=True)
if os.path.exists(final_path):
    os.remove(final_path)
    print(f"🗑️ Existing file deleted: {final_path}")


def solve_captcha(page):
    """Extract captcha alphanumeric text from DOM/canvas/image using OCR."""
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

    # Method 1: Canvas-based captcha (common on Angular/SPA sites)
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
                print(f"📸 Captcha solved via canvas OCR: {text}")
                return text
    except Exception as e:
        print(f"Canvas method failed: {e}")

    # Method 2: Captcha image element screenshot + OCR
    try:
        captcha_selectors = [
            "img[src*='captcha']",
            "img[id*='captcha']",
            "img[class*='captcha']",
            "img[alt*='captcha']",
            ".captcha img",
            "#captchaImage",
            "app-captcha img",
            "[formcontrolname='captcha'] ~ img",
            "[formcontrolname='captcha'] + span img",
        ]
        for selector in captcha_selectors:
            try:
                el = page.locator(selector).first
                if el.count() > 0 and el.is_visible(timeout=3000):
                    screenshot_bytes = el.screenshot()
                    img = Image.open(io.BytesIO(screenshot_bytes))
                    text = preprocess_and_ocr(img)
                    if text:
                        print(f"📸 Captcha solved via image OCR ({selector}): {text}")
                        return text
            except Exception:
                continue
    except Exception as e:
        print(f"Image OCR method failed: {e}")

    # Method 3: Fallback - original DOM text extraction
    try:
        text = page.inner_text("span.input-group-addon", timeout=10000).strip()
        text = ''.join(c for c in text if c.isalnum())
        if text:
            print(f"📸 Captcha from DOM text: {text}")
            return text
    except Exception as e:
        print(f"DOM text method failed: {e}")

    raise Exception("❌ Could not solve captcha - all methods failed")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(60000)

        try:
            # Step 1: Login
            print("🔐 Logging in...")
            page.goto("https://mtcbusits.in/")
            page.wait_for_load_state("networkidle")
            print("✅ Page fully loaded")

            page.fill("input[name='UserName']", "neelan.ibi")
            password = os.environ.get('LOGIN_PASSWORD', 'Neelan@123')
            page.fill("input[id='password']", password)

            print("🔢 Solving captcha...")
            captcha_text = solve_captcha(page)
            page.fill("input[formcontrolname='captcha']", captcha_text)
            page.click("button:has-text('Login')")
            page.wait_for_timeout(3000)
            print("✅ Login successful")

            # Step 2: Go to AVLS section
            print("📊 Navigating to AVLS section...")
            page.click("p:has-text('AVLS')")

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
