#!/usr/bin/env python3
"""
Iden Challenge — Playwright scraper with fixed navigation

"""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv

# ---------------- Config ----------------
load_dotenv()
DEFAULT_BASE_URL = "https://hiring.idenhq.com/"
EMAIL_DEFAULT = os.getenv("EMAIL")
PASSWORD_DEFAULT = os.getenv("PASSWORD")

DEFAULT_SESSION_FILE = "session.json"
DEFAULT_OUTPUT_FILE = "products.json"
DEFAULT_TIMEOUT_MS = 30000

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/114.0.0.0 Safari/537.36"
)

# ---------------- Helpers ----------------
def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str, level: str = "INFO") -> None:
    print(f"[{now_ts()}] [{level}] {msg}", flush=True)


def save_screenshot(page, name: str) -> None:
    try:
        page.screenshot(path=name, full_page=True)
        log(f"Saved screenshot: {name}", "DEBUG")
    except Exception as e:
        log(f"Failed to save screenshot {name}: {e}", "ERROR")


def debug_page_content(page, selector: str = None):
    """Debug function to log page content for troubleshooting"""
    try:
        if selector:
            elements = page.query_selector_all(selector)
            log(f"Found {len(elements)} elements matching '{selector}':", "DEBUG")
            for i, element in enumerate(elements):
                try:
                    text = element.inner_text().strip()
                    log(f"  {i}: '{text}'", "DEBUG")
                except:
                    log(f"  {i}: [cannot read text]", "DEBUG")
        else:
            # Log all buttons and links for debugging
            buttons = page.query_selector_all("button")
            log(f"Found {len(buttons)} buttons on page:", "DEBUG")
            for i, button in enumerate(buttons):
                try:
                    text = button.inner_text().strip()
                    if text:
                        log(f"  Button {i}: '{text}'", "DEBUG")
                except:
                    pass
                    
            links = page.query_selector_all("a")
            log(f"Found {len(links)} links on page:", "DEBUG")
            for i, link in enumerate(links):
                try:
                    text = link.inner_text().strip()
                    if text:
                        log(f"  Link {i}: '{text}'", "DEBUG")
                except:
                    pass
    except Exception as e:
        log(f"Error debugging page content: {e}", "DEBUG")


# ---------------- Stealth script ----------------
STEALTH_JS = r"""
// Minimal stealth adjustments to reduce common automated flags
(() => {
  try {
    // navigator.webdriver -> undefined
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // languages
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

    // plugins
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });

    // emulate chrome object
    window.chrome = { runtime: {} };

    // permissions query (avoid abnormal rejections)
    const origPerm = (navigator.permissions || {}).query;
    if (origPerm) {
      navigator.permissions.query = (params) => {
        if (params && params.name && params.name === 'notifications') {
          return Promise.resolve({ state: Notification.permission });
        }
        return origPerm(params);
      };
    }
  } catch (e) {
    // ignore
  }
})();
"""


# ---------------- Browser / Session ----------------
def init_browser_and_context(playwright, headless: bool, session_file: Optional[str], user_agent: str):
    """Launch browser and create a context, reusing session if file exists."""
    log(f"Launching browser (headless={headless})", "SESSION")
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
        ],
    )

    context_kwargs = {
        "user_agent": user_agent,
        "viewport": {"width": 1280, "height": 800},
        "locale": "en-US",
    }

    if session_file and Path(session_file).exists():
        log(f"Loading storage_state from {session_file}", "SESSION")
        context_kwargs["storage_state"] = session_file

    context = browser.new_context(**context_kwargs)
    context.add_init_script(STEALTH_JS)
    return browser, context


def save_session_state(context, session_file: str) -> None:
    try:
        context.storage_state(path=session_file)
        log(f"Saved session state to {session_file}", "SESSION")
    except Exception as e:
        log(f"Failed to save session state: {e}", "ERROR")


# ---------------- Login ----------------
def fill_login_and_submit(page, email: str, password: str, base_url: str) -> bool:
    """Fill in the login form and submit. Returns True if sign-in likely succeeded."""
    log("Opening login page...", "LOGIN")
    page.goto(base_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
    page.set_default_timeout(DEFAULT_TIMEOUT_MS)

    # Wait for login form to appear
    try:
        # Look for email field with multiple selectors
        email_field = page.wait_for_selector(
            "input[type='email'], input[type='text'][placeholder*='email'], "
            "input[name='email'], input[id*='email']",
            timeout=10000
        )
        email_field.fill(email)
        log("Filled email field", "LOGIN")
    except PlaywrightTimeoutError:
        log("Could not find email input on login page.", "ERROR")
        save_screenshot(page, "login_form_missing.png")
        return False

    # Find and fill password field
    try:
        password_field = page.wait_for_selector(
            "input[type='password'], input[name='password'], "
            "input[id*='password'], input[placeholder*='Password']",
            timeout=5000
        )
        password_field.fill(password)
        log("Filled password field", "LOGIN")
    except PlaywrightTimeoutError:
        log("Could not find password input on login page.", "ERROR")
        save_screenshot(page, "password_missing.png")
        return False

    # Submit the form
    try:
        # Try to find and click submit button
        submit_button = page.wait_for_selector(
            "button[type='submit'], input[type='submit'], "
            "button:has-text('Sign in'), button:has-text('Sign In'), "
            "button:has-text('Login'), button:has-text('Log in')",
            timeout=5000
        )
        submit_button.click()
        log("Clicked submit button", "LOGIN")
    except PlaywrightTimeoutError:
        # Fallback: press Enter on password field
        log("Submit button not found, pressing Enter instead", "LOGIN")
        password_field.press("Enter")

    return True


def wait_for_login_result(page, base_url: str, timeout_s: int = 30) -> bool:
    """Wait for login result with improved detection to avoid false positives."""
    start = time.time()
    error_selectors = [
        "text=invalid", "text=Invalid", "text=incorrect", "text=Incorrect", 
        ".toast-error", ".alert-danger", "text=error", "text=Error"
    ]
    
    # More specific success indicators that shouldn't appear on login page
    success_selectors = [
        "text=Product Dashboard", 
        "text=Assessment ID:",
        "text=Layout: Table",
        "text=Open the menu to access system features"
    ]

    while time.time() - start < timeout_s:
        # Check for URL change first (most reliable indicator)
        current_url = page.url
        if current_url != base_url and not current_url.endswith("/login"):
            log(f"URL changed to {current_url}, assuming login success", "LOGIN")
            return True

        # Check for success indicators
        for selector in success_selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=1000):
                    log(f"Found success indicator: {selector}", "LOGIN")
                    return True
            except:
                pass

        # Check for error indicators
        for selector in error_selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=1000):
                    error_text = element.inner_text()
                    log(f"Login error: {error_text}", "LOGIN")
                    save_screenshot(page, "login_error.png")
                    return False
            except:
                pass

        time.sleep(1)

    log("Timed out waiting for login result", "ERROR")
    save_screenshot(page, "login_timeout.png")
    return False


def is_logged_in(page) -> bool:
    """Check if we're already logged in by looking for post-login elements."""
    try:
        # Look for elements that only appear after successful login
        indicators = [
            "text=Product Dashboard", 
            "text=Assessment ID:",
            "text=Layout: Table",
            "text=Open the menu to access system features"
        ]
        
        for selector in indicators:
            if page.locator(selector).count() > 0:
                return True
                
        return False
    except:
        return False


def is_menu_open(page) -> bool:
    """Check if the menu is already open by looking for menu items."""
    try:
        menu_item_selectors = [
            "text=Data Tools",
            "text=Reporting", 
            "text=Search",
            "[role='menuitem']"
        ]
        
        for selector in menu_item_selectors:
            if page.locator(selector).count() > 0:
                return True
        return False
    except:
        return False


def click_launch_challenge(page) -> bool:
    """Click the Launch Challenge button if it exists."""
    try:
        # Try multiple selectors for the Launch Challenge button
        launch_selectors = [
            "button:has-text('Launch Challenge')",
            "a:has-text('Launch Challenge')",
            "text=Launch Challenge",
            "[data-testid='launch-challenge']"
        ]
        
        for selector in launch_selectors:
            try:
                launch_button = page.wait_for_selector(selector, timeout=5000)
                if launch_button.is_visible():
                    launch_button.click()
                    log("Clicked Launch Challenge button", "NAV")
                    
                    # Wait for the dashboard to appear after launching challenge
                    try:
                        page.wait_for_selector(
                            "text=Product Dashboard, text=Assessment ID:", 
                            timeout=15000
                        )
                        log("Product Dashboard is now visible", "NAV")
                        return True
                    except PlaywrightTimeoutError:
                        log("Dashboard not found after launching challenge", "WARN")
                        # Continue anyway, maybe the dashboard is already visible
                        return True
            except PlaywrightTimeoutError:
                continue
                
        log("Launch Challenge button not found", "DEBUG")
        return False
    except Exception as e:
        log(f"Error clicking Launch Challenge: {e}", "ERROR")
        return False


def navigate_to_product_catalog(page) -> bool:
    """Navigate to the product catalog through the menu."""
    log("Navigating to Product Catalog...", "NAV")
    
    # First try to click Launch Challenge if it exists
    click_launch_challenge(page)
    
    # Check if menu is already open
    if not is_menu_open(page):
        # Try to find and open the menu
        try:
            # Look for menu button
            menu_selectors = [
                "button:has-text('Menu')",
                "button[aria-label*='menu']",
                "button[aria-label*='Menu']",
                "button >> svg",
                "[data-testid*='menu']",
                "[class*='menu'] button"
            ]
            
            menu_button = None
            for selector in menu_selectors:
                try:
                    element = page.wait_for_selector(selector, timeout=3000)
                    if element.is_visible():
                        menu_button = element
                        log(f"Found menu button with selector: {selector}", "DEBUG")
                        break
                except PlaywrightTimeoutError:
                    continue
            
            if menu_button:
                menu_button.click()
                log("Clicked menu button", "NAV")
                time.sleep(1)  # Wait for menu to open
            else:
                log("Menu button not found", "ERROR")
                return False
        except Exception as e:
            log(f"Error opening menu: {e}", "ERROR")
            return False

    # Click Data Tools in the menu
    data_tools_selectors = [
        "text=Data Tools",
        "a:has-text('Data Tools')",
        "li:has-text('Data Tools')",
        "[role='menuitem']:has-text('Data Tools')",
        ".menu-item:has-text('Data Tools')"
    ]
    
    data_tools = None
    for selector in data_tools_selectors:
        try:
            element = page.wait_for_selector(selector, timeout=5000)
            if element.is_visible():
                data_tools = element
                log(f"Found Data Tools with selector: {selector}", "DEBUG")
                break
        except PlaywrightTimeoutError:
            continue
    
    if not data_tools:
        log("Data Tools menu item not found", "ERROR")
        return False
    
    # Click Data Tools
    data_tools.click()
    log("Clicked Data Tools", "NAV")
    time.sleep(2)  # Wait for content to load

    # Click Inventory Management (now in the main content area)
    inventory_management_selectors = [
        "text=Inventory Management",
        "a:has-text('Inventory Management')",
        "button:has-text('Inventory Management')",
        "[data-testid='inventory-management']",
        "h2:has-text('Inventory Management')",
        "h3:has-text('Inventory Management')"
    ]
    
    inventory_management = None
    for selector in inventory_management_selectors:
        try:
            element = page.wait_for_selector(selector, timeout=5000)
            if element.is_visible():
                inventory_management = element
                log(f"Found Inventory Management with selector: {selector}", "DEBUG")
                break
        except PlaywrightTimeoutError:
            continue
    
    if not inventory_management:
        log("Inventory Management not found", "ERROR")
        return False
    
    # Click Inventory Management
    inventory_management.click()
    log("Clicked Inventory Management", "NAV")
    time.sleep(2)  # Wait for content to load

    # Click Product Catalog (now in the main content area)
    product_catalog_selectors = [
        "text=Product Catalog",
        "a:has-text('Product Catalog')",
        "button:has-text('Product Catalog')",
        "[data-testid='product-catalog']",
        "h2:has-text('Product Catalog')",
        "h3:has-text('Product Catalog')"
    ]
    
    product_catalog = None
    for selector in product_catalog_selectors:
        try:
            element = page.wait_for_selector(selector, timeout=5000)
            if element.is_visible():
                product_catalog = element
                log(f"Found Product Catalog with selector: {selector}", "DEBUG")
                break
        except PlaywrightTimeoutError:
            continue
    
    if not product_catalog:
        log("Product Catalog not found", "ERROR")
        return False
    
    # Click Product Catalog
    product_catalog.click()
    log("Clicked Product Catalog", "NAV")
    time.sleep(2)  # Wait for content to load

    # Click Load Product Data button
    load_data_selectors = [
        "button:has-text('Load Product Data')",
        "button:has-text('Load Data')",
        "button:has-text('Load Products')",
        "text=Load Product Data",
        "[data-testid='load-data']",
        "[data-testid='load-products']"
    ]
    
    load_data_button = None
    for selector in load_data_selectors:
        try:
            element = page.wait_for_selector(selector, timeout=5000)
            if element.is_visible():
                load_data_button = element
                log(f"Found Load Product Data button with selector: {selector}", "DEBUG")
                break
        except PlaywrightTimeoutError:
            continue
    
    if not load_data_button:
        log("Load Product Data button not found", "ERROR")
        return False
    
    # Click Load Product Data button
    load_data_button.click()
    log("Clicked Load Product Data button", "NAV")
    time.sleep(3)  # Wait for data to load

    # Wait for the product table to load
    try:
        page.wait_for_selector("table, [role=table]", timeout=15000)
        log("Product table loaded", "NAV")
        
        # Also wait for the table to have some content
        page.wait_for_selector("table tbody tr", timeout=10000)
        log("Product table has data", "NAV")
        
    except PlaywrightTimeoutError:
        log("Product table not found after navigation", "ERROR")
        save_screenshot(page, "table_not_found.png")
        return False
    
    return True

# ---------------- Extraction ----------------
def extract_table_rows_from_page(page) -> List[Dict[str, Any]]:
    """Return list of row dicts from current visible table."""
    rows_data: List[Dict[str, Any]] = []

    # Try to find the table
    try:
        table = page.wait_for_selector("table, [role=table]", timeout=10000)
    except PlaywrightTimeoutError:
        log("No table found on page", "ERROR")
        return rows_data

    # Extract headers
    headers = []
    try:
        header_elements = table.query_selector_all("thead th, th")
        headers = [header.inner_text().strip() for header in header_elements if header.inner_text().strip()]
    except Exception as e:
        log(f"Error extracting headers: {e}", "WARN")

    # If no headers found, try to infer from first row
    if not headers:
        try:
            first_row = table.query_selector("tbody tr, tr")
            if first_row:
                cell_elements = first_row.query_selector_all("td")
                headers = [f"Column_{i+1}" for i in range(len(cell_elements))]
        except Exception as e:
            log(f"Error inferring headers: {e}", "WARN")

    # Extract rows
    try:
        rows = table.query_selector_all("tbody tr, tr")
        for row in rows:
            cells = row.query_selector_all("td")
            if not cells:
                continue
                
            row_data = {}
            for i, cell in enumerate(cells):
                header = headers[i] if i < len(headers) else f"Column_{i+1}"
                row_data[header] = cell.inner_text().strip()
                
            rows_data.append(row_data)
            
    except Exception as e:
        log(f"Error extracting rows: {e}", "WARN")

    return rows_data


def collect_all_products(page) -> List[Dict[str, Any]]:
    """Collect all products from infinite scroll table with optimized scrolling."""
    log("Starting optimized infinite scroll collection...", "SCRAPER")
    all_rows: List[Dict[str, Any]] = []
    seen = set()
    
    # Initial extraction
    new_rows = extract_table_rows_from_page(page)
    for row in new_rows:
        row_hash = str(sorted(row.items()))
        if row_hash not in seen:
            seen.add(row_hash)
            all_rows.append(row)
    
    log(f"Initial extraction: {len(new_rows)} rows", "SCRAPER")
    
    # Get the infinite scroll container
    try:
        infinite_container = page.wait_for_selector(".infinite-table", timeout=5000)
        log("Found infinite scroll container", "SCRAPER")
    except PlaywrightTimeoutError:
        log("No infinite scroll container found, using page scrolling", "SCRAPER")
        infinite_container = None
    
    # Optimized scrolling parameters
    scroll_attempts = 0
    max_scroll_attempts = 500  # High limit for safety
    no_new_data_count = 0
    max_no_new_data = 5
    
    last_count = len(all_rows)
    last_log_time = time.time()
    
    while scroll_attempts < max_scroll_attempts and no_new_data_count < max_no_new_data:
        try:
            # FAST SCROLLING: Minimal wait time
            if infinite_container:
                infinite_container.evaluate("""
                    element => {
                        element.scrollTop = element.scrollHeight;
                        // Small additional scroll to trigger loading
                        setTimeout(() => element.scrollBy(0, 10), 10);
                    }
                """)
            else:
                page.evaluate("""
                    window.scrollTo(0, document.body.scrollHeight);
                    setTimeout(() => window.scrollBy(0, 10), 10);
                """)
            
            # VERY SHORT WAIT - most modern infinite scroll loads quickly
            time.sleep(0.3)
            
            # Extract new rows but only check every few scrolls to save time
            if scroll_attempts % 3 == 0:  # Check every 3rd scroll
                new_rows = extract_table_rows_from_page(page)
                added_count = 0
                
                for row in new_rows:
                    row_hash = str(sorted(row.items()))
                    if row_hash not in seen:
                        seen.add(row_hash)
                        all_rows.append(row)
                        added_count += 1
                
                # Progress logging
                current_time = time.time()
                if added_count > 0 or current_time - last_log_time > 8:
                    log(f"Rows: {len(all_rows)}, New: {added_count}, Attempt: {scroll_attempts}", "SCRAPER")
                    last_log_time = current_time
                
                # Check if we got new data
                if added_count > 0:
                    no_new_data_count = 0
                    last_count = len(all_rows)
                else:
                    no_new_data_count += 1
            
            scroll_attempts += 1
            
            # Dynamic completion detection - check for "0 remaining" or no change
            if scroll_attempts % 15 == 0:  # Check every 15 scrolls
                try:
                    # Look for the "remaining products" text
                    remaining_text_elements = page.query_selector_all("div.text-center span, div.text-muted-foreground")
                    for element in remaining_text_elements:
                        text = element.inner_text().lower()
                        if "0 remaining" in text or "all products loaded" in text:
                            log("Completion detected: " + text, "SCRAPER")
                            no_new_data_count = max_no_new_data
                            break
                    
                    # Also check if scroll height isn't increasing (end of content)
                    if infinite_container:
                        current_scroll_height = infinite_container.evaluate("element => element.scrollHeight")
                        scroll_position = infinite_container.evaluate("element => element.scrollTop")
                        if scroll_position > 0 and current_scroll_height - scroll_position < 100:
                            log("Reached end of scroll container", "SCRAPER")
                            no_new_data_count += 1
                    
                except Exception as e:
                    log(f"Completion check error: {e}", "SCRAPER")
            
            # Additional check: if we've scrolled a lot with no new data, likely done
            if no_new_data_count >= 2 and scroll_attempts > 50:
                log("Multiple scrolls with no new data, likely completed", "SCRAPER")
                break
                
        except Exception as e:
            log(f"Scroll error: {e}", "SCRAPER")
            scroll_attempts += 1
            time.sleep(0.1)
    
    # Final comprehensive check
    try:
        log("Performing final comprehensive check...", "SCRAPER")
        # Scroll to very end one more time
        if infinite_container:
            infinite_container.evaluate("element => element.scrollTop = element.scrollHeight")
        else:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        time.sleep(1)
        
        # Extract any remaining rows
        new_rows = extract_table_rows_from_page(page)
        final_added = 0
        for row in new_rows:
            row_hash = str(sorted(row.items()))
            if row_hash not in seen:
                seen.add(row_hash)
                all_rows.append(row)
                final_added += 1
        
        if final_added > 0:
            log(f"Final check found {final_added} additional rows", "SCRAPER")
        
        # One last check for completion message
        try:
            completion_elements = page.query_selector_all("text/0 remaining, text/all products, text/loaded")
            for element in completion_elements:
                text = element.inner_text().lower()
                if "0" in text and "remaining" in text:
                    log("Confirmed: 0 products remaining", "SCRAPER")
        except:
            pass
            
    except Exception as e:
        log(f"Final check error: {e}", "SCRAPER")
    
    log(f"Collection complete. Total unique rows: {len(all_rows)}", "SCRAPER")
    return all_rows
# ---------------- Save export ----------------
def export_to_json(data: List[Dict[str, Any]], out_file: str) -> None:
    try:
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log(f"Exported {len(data)} rows to {out_file}", "EXPORT")
    except Exception as e:
        log(f"Failed to export JSON: {e}", "ERROR")


# ---------------- Main runner ----------------
def main(
    base_url: str,
    email: Optional[str],
    password: Optional[str],
    session_file: str,
    output_file: str,
    headed: bool,
):
    if not email or not password:
        log("Email and password are required", "ERROR")
        return

    with sync_playwright() as pw:
        browser, context = init_browser_and_context(
            pw, headless=not headed, session_file=session_file, user_agent=DEFAULT_USER_AGENT
        )
        page = context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)

        try:
            # Check if we're already logged in with the existing session
            page.goto(base_url, wait_until="domcontentloaded")
            
            if is_logged_in(page):
                log("Already logged in with existing session", "SESSION")
            else:
                log("No valid session found, attempting login", "SESSION")
                if not fill_login_and_submit(page, email, password, base_url):
                    log("Failed to fill login form", "ERROR")
                    return
                    
                if not wait_for_login_result(page, base_url):
                    log("Login failed", "ERROR")
                    return
                    
                log("Login successful", "SESSION")
                save_session_state(context, session_file)

            # Navigate to product catalog
            if not navigate_to_product_catalog(page):
                log("Failed to navigate to product catalog", "ERROR")
                return

            # Collect products
            products = collect_all_products(page)

            # Export JSON
            export_to_json(products, output_file)

            log("Script completed successfully", "SUCCESS")
            
        except Exception as e:
            log(f"Unhandled exception: {e}", "ERROR")
            save_screenshot(page, "error.png")
        finally:
            context.close()
            browser.close()


# ---------------- CLI ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Iden Challenge scraper with fixed navigation")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="App base URL")
    parser.add_argument("--email", default=EMAIL_DEFAULT, help="Login email")
    parser.add_argument("--password", default=PASSWORD_DEFAULT, help="Login password")
    parser.add_argument("--session-file", default=DEFAULT_SESSION_FILE, help="Session storage file")
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE, help="Output JSON file")
    parser.add_argument("--headed", action="store_true", help="Run browser headed (visible)")
    
    args = parser.parse_args()

    if not args.email or not args.password:
        log("Email and password are required (set via .env or command line)", "ERROR")
        exit(1)

    main(
        base_url=args.base_url.rstrip("/"),
        email=args.email,
        password=args.password,
        session_file=args.session_file,
        output_file=args.output_file,
        headed=args.headed,
    )