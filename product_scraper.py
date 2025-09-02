import argparse, json, time
from playwright.sync_api import sync_playwright

def log(msg): print(f"[LOG] {msg}", flush=True)

def login(page, base_url, email, password):
    log("Opening login page...")
    page.goto(base_url, wait_until="domcontentloaded")

    page.fill("input[type='email']", email)
    page.fill("input[type='password']", password)
    page.click("button[type='submit']")

    # Wait until dashboard appears
    page.wait_for_selector("text=Product Dashboard", timeout=20000)
    log("Login successful")

def navigate_to_product_catalog(page):
    log("Navigating to Product Catalog...")
    page.click("text=Data Tools")
    page.click("text=Inventory Management")
    page.click("text=Product Catalog")
    page.wait_for_selector("table", timeout=10000)
    log("Product Catalog loaded")

def extract_table(page):
    log("Extracting product rows...")
    headers = [h.inner_text().strip() for h in page.query_selector_all("thead th")]
    rows = []
    for row in page.query_selector_all("tbody tr"):
        cells = [c.inner_text().strip() for c in row.query_selector_all("td")]
        if cells:
            rows.append(dict(zip(headers, cells)))
    log(f"Extracted {len(rows)} rows")
    return rows

def main(base_url, email, password, output_file, headed):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        page = browser.new_page()
        
        login(page, base_url, email, password)
        navigate_to_product_catalog(page)
        data = extract_table(page)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log(f"Saved {len(data)} products to {output_file}")

        browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://hiring.idenhq.com/")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--output-file", default="products.json")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    main(args.base_url, args.email, args.password, args.output_file, args.headed)
