"""
Step 2: Email Verification + Password Setup
============================================
Uses Playwright to:
  1. Open Outlook Web and login
  2. Find the verification email from notifications@sarasanalytics.com
  3. Extract the "Confirm Email" link
  4. Navigate to the verification URL
  5. Fill password and submit

Usage:
  python step2_verify_email.py --env dev --email demo+poc2test@sarasanalytics.com
  python step2_verify_email.py --env dev --email demo+poc2test@sarasanalytics.com --password MyPass@123
"""

import sys
import sys
import os
import re
import time
import argparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from env_config import get_config, add_env_arg

OUTLOOK_URL = "https://outlook.office.com/mail/"


def verify_and_set_password(
    target_email: str,
    password: str = None,
    outlook_email: str = None,
    outlook_pw: str = None,
    headless: bool = False,
    timeout_seconds: int = 60,
    env: str = None,
) -> dict:
    cfg = get_config(env)
    password = password or cfg.DEFAULT_PASSWORD
    outlook_email = outlook_email or cfg.OUTLOOK_EMAIL
    outlook_pw = outlook_pw or cfg.OUTLOOK_PASSWORD

    print(f"\n[Step 2] [{cfg.env_name}] Verifying email for: {target_email}")
    print(f"[Step 2] Password to set: {password}")

    result = {
        "success": False,
        "verification_url": None,
        "error": None,
    }

    with sync_playwright() as p:
        # STEALTH MODULE: Erase Headless Bot Fingerprints & Optimize for Linux Containers (Prevent OOM memory crashes)
        stealth_args = [
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-dev-shm-usage",     # CRITICAL for Render: prevents 64MB docker memory crash
            "--disable-gpu",               # Disables graphics compute
            "--single-process",            # Forces chromium to use less RAM
            "--no-zygote",
            "--blink-settings=imagesEnabled=false" # Blocks image downloads to save massive RAM
        ]
        
        browser = p.chromium.launch(
            headless=headless, 
            args=stealth_args,
            ignore_default_args=["--enable-automation"]
        )
        
        auth_file = "outlook_auth.json"
        use_session = os.path.exists(auth_file)
        
        # Hyper-realistic User Agent spoofing
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        if use_session:
            print("[Step 2] Using Cached Outlook Session (outlook_auth.json) - Bypassing Captchas!")
            context = browser.new_context(
                viewport=None, 
                storage_state=auth_file,
                user_agent=user_agent
            )
        else:
            context = browser.new_context(
                viewport=None,
                user_agent=user_agent
            )
            
        # Natively wipe the automated webdriver javascript tag
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = context.new_page()

        try:
            verification_url = _find_verification_email(page, target_email, timeout_seconds, outlook_email, outlook_pw, use_session)

            if not verification_url:
                result["error"] = "Could not find verification email or extract link"
                return result

            result["verification_url"] = verification_url
            print(f"\n[Step 2] Verification URL found!")
            print(f"[Step 2] URL: {verification_url[:100]}...")

            _set_password(page, verification_url, password, timeout_seconds)

            result["success"] = True
            print(f"\n[Step 2] Email verified and password set successfully!")

        except PWTimeout as e:
            result["error"] = f"Timeout: {e}"
            print(f"\n[Step 2] Timeout error: {e}")
        except Exception as e:
            result["error"] = str(e)
            print(f"\n[Step 2] Error: {e}")
        finally:
            print("[Step 2] Closing browser in 3 seconds...")
            time.sleep(3)
            context.close()

    return result


def _find_verification_email(page, target_email: str, timeout_seconds: int, outlook_email: str, outlook_pw: str, use_session: bool = False) -> str:
    timeout_ms = timeout_seconds * 1000

    print("[Step 2] Opening Outlook Web...")
    page.goto(OUTLOOK_URL, wait_until="domcontentloaded", timeout=timeout_ms)

    if use_session:
        print("[Step 2] Session Loaded. Re-routing directly to inbox!")
        print("[Step 2] Waiting 20 seconds for verification email to be physically delivered to the inbox...")
        page.wait_for_timeout(20000)
    else:
        # Outlook Microsoft Authentication Flow
        try:
            email_input = page.locator('input[type="email"], input[name="loginfmt"]')
            email_input.wait_for(state="visible", timeout=15000)

            print(f"[Step 2] Providing Outlook Email: {outlook_email}")
            email_input.fill(outlook_email)
            page.keyboard.press("Enter")

            pw_input = page.locator('input[type="password"], input[name="passwd"]')
            pw_input.wait_for(state="visible", timeout=15000)

            print("[Step 2] Providing Outlook Password...")
            pw_input.fill(outlook_pw)
            page.keyboard.press("Enter")

            try:
                stay_signed_in_btn = page.locator('input[type="submit"][value="Yes"], button:has-text("Yes"), input[id="idSIButton9"]')
                stay_signed_in_btn.wait_for(state="visible", timeout=5000)
                try:
                    dont_show_cb = page.locator('input[name="DontShowAgain"]')
                    if dont_show_cb.is_visible(timeout=1000):
                        dont_show_cb.click()
                except Exception:
                    pass
                stay_signed_in_btn.click()
                print("[Step 2] Accepted 'Stay signed in' prompt.")
            except PWTimeout:
                pass

            try:
                secondary_btn = page.locator('a[id="CancelLinkButton"], button:has-text("Skip for now"), button:has-text("Done"), input[value="Done"], button:has-text("Next")')
                if secondary_btn.is_visible(timeout=3000):
                    secondary_btn.first.click()
                    print("[Step 2] Handled secondary Microsoft setup prompt.")
                    page.wait_for_timeout(2000)
            except Exception:
                pass

        except PWTimeout:
            print("[Step 2] Could not find initial Microsoft login. Assuming already logged in.")

    print("[Step 2] Waiting for Outlook inbox to load...")
    page.wait_for_timeout(5000)

    # Search for the verification email
    max_retries = 3
    search_attempts = 0

    while search_attempts < max_retries:
        search_attempts += 1
        search_query = f"from:notifications@sarasanalytics.com {target_email}"
        print(f"[Step 2] Search attempt {search_attempts}/{max_retries}: {search_query}")

        search_input = page.locator('input[aria-label*="Search"], input[placeholder*="Search"], input[type="search"]').first
        try:
            search_input.wait_for(state="visible", timeout=5000)
        except Exception:
            search_btn = page.locator('[aria-label="Search"][role="button"]').first
            try:
                search_btn.click()
                page.wait_for_timeout(1000)
                search_input = page.locator('input[aria-label*="Search"], input[placeholder*="Search"], input[type="search"]').first
                search_input.wait_for(state="visible", timeout=5000)
            except Exception:
                pass

        try:
            search_input.click()
            page.wait_for_timeout(300)
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            page.wait_for_timeout(300)
            search_input.fill(search_query)
            page.keyboard.press("Enter")
            print("[Step 2] Search submitted, waiting for results...")
            page.wait_for_timeout(5000)
            break
        except PWTimeout:
            if search_attempts < max_retries:
                print(f"[Step 2] Could not find search box (attempt {search_attempts}). Retrying...")
                page.wait_for_timeout(2000)
                continue
            else:
                break

    page.wait_for_timeout(3000)

    # Find and click the verification email
    email_clicked = False
    for attempt in range(1, 4):
        print(f"[Step 2] Finding email (attempt {attempt}/3)...")
        try:
            email_items = page.locator('[role="option"]').all()
            print(f"[Step 2] Found {len(email_items)} emails in results")

            if len(email_items) == 0:
                if attempt < 3:
                    print(f"[Step 2] Waiting 3 seconds for emails to load...")
                    page.wait_for_timeout(3000)
                    continue
                else:
                    break

            for i, email_item in enumerate(email_items[:5]):
                try:
                    item_text = email_item.text_content(timeout=2000)
                    print(f"[Step 2]   [{i}] {item_text[:100]}...")
                except Exception:
                    pass

            for i, email_item in enumerate(email_items):
                try:
                    item_text = email_item.text_content(timeout=1500).lower()
                    if any(keyword in item_text for keyword in ["saras", "verify", "confirm", "email", "notification"]):
                        print(f"[Step 2] Found verification email #{i}")
                        email_item.click()
                        page.wait_for_timeout(2000)
                        email_clicked = True
                        break
                except Exception:
                    pass

            if email_clicked:
                break

            if len(email_items) > 0:
                print(f"[Step 2] Trying first email in list...")
                email_items[0].click()
                page.wait_for_timeout(2000)
                email_clicked = True
                break

        except Exception as e:
            print(f"[Step 2] Error finding emails (attempt {attempt}): {e}")
            if attempt < 3:
                page.wait_for_timeout(3000)

    if not email_clicked:
        print("[Step 2] Could not find or click verification email")
        return None

    # Extract the verification link
    print("[Step 2] Looking for verification link in email body...")
    page.wait_for_timeout(2000)

    confirm_selectors = [
        'a:has-text("Confirm Email")',
        'a:has-text("Verify Email")',
        'a:has-text("Verify")',
        'a:has-text("Confirm")',
        'a[href*="verify"]',
        'a[href*="code="]',
        'button:has-text("Confirm Email")',
        'button:has-text("Verify")',
    ]

    for selector in confirm_selectors:
        try:
            link = page.locator(selector).first
            if link.is_visible(timeout=2000):
                href = link.get_attribute("href")
                if href:
                    print(f"[Step 2] Found confirm link: {href[:100]}...")
                    return href
        except Exception:
            continue

    print("[Step 2] Searching for verification link in page content...")
    try:
        email_body = page.locator('[role="document"], .ms-fontColor-neutralPrimary, [aria-label*="Message body"]').first
        emails = email_body.locator('a').all()
        for link in emails:
            try:
                href = link.get_attribute("href")
                if href and ("accounts" in href or "verify" in href.lower() or "code=" in href):
                    print(f"[Step 2] Found verification link: {href[:100]}...")
                    return href
            except Exception:
                pass
    except Exception as e:
        print(f"[Step 2] Error searching links: {e}")

    print("[Step 2] Extracting link from page source...")
    try:
        page_source = page.content()
        url_patterns = [
            r'https://[\w-]+accounts\.sarasanalytics\.com[^"\'<>\s]+mode=verifyEmail[^"\'<>\s]*',
            r'https://[\w-]+accounts\.sarasanalytics\.com[^"\'<>\s]+(verify|code)[^"\'<>\s]*',
            r'https://[\w-]+accounts\.sarasanalytics\.com/[^"\'<>\s]+',
        ]
        for pattern in url_patterns:
            matches = re.findall(pattern, page_source)
            if matches:
                verification_url = max(matches, key=len)
                verification_url = verification_url.replace("&amp;", "&").split('"')[0].split("'")[0]
                if "accounts" in verification_url:
                    print(f"[Step 2] Found verification URL via regex: {verification_url[:100]}...")
                    return verification_url
    except Exception as e:
        print(f"[Step 2] Regex extraction error: {e}")

    print("[Step 2] Could not find verification link in email")
    return None


def _set_password(page, verification_url: str, password: str, timeout_seconds: int):
    timeout_ms = timeout_seconds * 1000

    import urllib.parse
    import base64
    
    if "protection.sophos.com" in verification_url:
        parsed = urllib.parse.urlparse(verification_url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "u" in qs:
            try:
                raw_u = qs["u"][0]
                print(f"[Step 2] Raw Sophos payload: {raw_u[:50]}...")
                
                # Sophos sometimes returns URL-encoded string or URL-safe base64 (-_)
                b64_url = urllib.parse.unquote(raw_u)
                b64_url = b64_url.replace("-", "+").replace("_", "/")
                
                # Force strictly valid base64 padding
                b64_url += "=" * ((4 - len(b64_url) % 4) % 4)
                
                verification_url = base64.b64decode(b64_url).decode('utf-8', errors='ignore')
                print(f"[Step 2] Sophos Firewall Bypassed! Extracted RAW Backend URL: {verification_url[:100]}...")
            except Exception as e:
                import traceback
                print(f"[Step 2] Warning: Sophos decryption failed: {e}\n{traceback.format_exc()}")

    print(f"\n[Step 2] Navigating directly to raw verification page...")
    page.goto(verification_url, wait_until="domcontentloaded", timeout=timeout_ms)
    
    try:
        print("[Step 2] Monitoring for Cloudflare Gateway...")
        cf_text = page.locator('text="Checking your browser"')
        cf_link = page.locator('text="Click here"')
        if cf_text.is_visible(timeout=5000) or cf_link.is_visible(timeout=2000):
            print("[Step 2] Cloudflare Intercepted! Clicking manual bypass link...")
            cf_link.first.click()
            page.wait_for_timeout(4000)
    except Exception:
        pass

    page.wait_for_timeout(4000)

    print("[Step 2] Waiting for password form...")
    try:
        verified_msg = page.locator('text="Your email is verified"')
        verified_msg.wait_for(state="visible", timeout=10000)
        print("[Step 2] Email verified successfully! Setting up password...")
    except PWTimeout:
        print("[Step 2] Verification message not found, continuing with password setup...")

    password_selectors = [
        'input[placeholder="Enter Password"]',
        'input[type="password"]:nth-of-type(1)',
        'input[formcontrolname="password"]',
    ]

    password_filled = False
    for selector in password_selectors:
        try:
            pw_field = page.locator(selector).first
            if pw_field.is_visible(timeout=5000):
                pw_field.click()
                pw_field.fill(password)
                password_filled = True
                print(f"[Step 2] Filled 'Enter Password'")
                break
        except Exception:
            continue

    if not password_filled:
        pw_inputs = page.locator('input[type="password"]').all()
        if len(pw_inputs) >= 1:
            pw_inputs[0].fill(password)
            password_filled = True
            print(f"[Step 2] Filled password (fallback)")

    if not password_filled:
        # ABSOLUTE DEBUGGING
        print("\n==== ERROR DEBUG: PAGE CONTENT DUMP ====")
        try:
            print(page.locator("body").inner_text()[:1500])
        except Exception:
            try:
                print(page.content()[:1500])
            except Exception:
                print("Could not dump page content.")
        print("========================================")
        try:
            page.screenshot(path="ERROR_DUMP_VERIFY_PAGE.png", full_page=True)
            print("\n[Step 2] CRITICAL: A visual screenshot of the broken page was saved to 'C:\\Projects\\All-Env-Onboard\\ERROR_DUMP_VERIFY_PAGE.png'")
        except Exception as e:
            print(f"[Step 2] Failed to take screenshot: {e}")
        
        raise Exception("Could not find password input field. See ERROR_DUMP_VERIFY_PAGE.png for visual state.")

    confirm_selectors = [
        'input[placeholder="Confirm Password"]',
        'input[type="password"]:nth-of-type(2)',
        'input[formcontrolname="confirmPassword"]',
    ]

    confirm_filled = False
    for selector in confirm_selectors:
        try:
            cf_field = page.locator(selector).first
            if cf_field.is_visible(timeout=3000):
                cf_field.click()
                cf_field.fill(password)
                confirm_filled = True
                print(f"[Step 2] Filled 'Confirm Password'")
                break
        except Exception:
            continue

    if not confirm_filled:
        pw_inputs = page.locator('input[type="password"]').all()
        if len(pw_inputs) >= 2:
            pw_inputs[1].fill(password)
            confirm_filled = True
            print(f"[Step 2] Filled confirm password (fallback)")

    if not confirm_filled:
        raise Exception("Could not find confirm password input field")

    page.wait_for_timeout(500)

    submit_selectors = [
        'button:has-text("Get Started")',
        'sa-button:has-text("Get Started")',
        'sa-button label:has-text("Get Started")',
        'button[type="submit"]',
    ]

    clicked = False
    for selector in submit_selectors:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=3000):
                btn.click()
                clicked = True
                print(f"[Step 2] Clicked 'Get Started'!")
                break
        except Exception:
            continue

    if not clicked:
        raise Exception("Could not find 'Get Started' button")

    print("[Step 2] Waiting for confirmation (5 seconds)...")
    page.wait_for_timeout(5000)

    try:
        page.reload(timeout=15000, wait_until="load")
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"[Step 2] Warning during refresh: {e}")

    current_url = page.url
    print(f"[Step 2] Current page after refresh: {current_url}")

    if "login" in current_url or "dashboard" in current_url or "auth" in current_url:
        print("[Step 2] Redirected to login/dashboard -- password setup complete!")
    else:
        print("[Step 2] Page after submit -- check if successful")


def main():
    parser = argparse.ArgumentParser(description="Step 2: Verify Email & Set Password")
    add_env_arg(parser)
    parser.add_argument("--email", required=True, help="The email address to verify")
    parser.add_argument("--password", default=None, help="Password to set (default from env config)")
    parser.add_argument("--headless", action="store_true", help="Run browser without UI")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds (default: 60)")
    args = parser.parse_args()

    result = verify_and_set_password(
        target_email=args.email,
        password=args.password,
        headless=args.headless,
        timeout_seconds=args.timeout,
        env=args.env,
    )

    if result["success"]:
        print(f"\n{'='*50}")
        print(f"  SUCCESS! Email verified & password set.")
        print(f"  Next: Run step3_get_token.py --email {args.email}")
        print(f"{'='*50}\n")
    else:
        print(f"\n  FAILED: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
