"""
Run this script to open TikTok Shop Manage Orders, take a screenshot,
and save the page HTML for selector inspection.

Usage (Windows CMD or PowerShell):
    python explore_orders.py
"""
import asyncio
from playwright.async_api import async_playwright

ORDERS_URL = "https://seller-us.tiktok.com/order/list/all"


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("Opening TikTok Shop login page...")
        await page.goto("https://seller-us.tiktok.com/")

        print("\nPlease log in manually in the browser window.")
        print("Waiting for login to complete...")

        # Wait until we leave the login/passport pages
        while True:
            await asyncio.sleep(1)
            url = page.url
            if "login" not in url and "passport" not in url and "seller-us.tiktok.com" in url:
                break

        print(f"Logged in! URL: {page.url}")
        await page.wait_for_load_state("networkidle")

        print(f"\nNavigating to Manage Orders: {ORDERS_URL}")
        await page.goto(ORDERS_URL)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)  # let JS-rendered tabs finish

        # Save screenshot
        await page.screenshot(path="orders.png", full_page=True)
        print("Screenshot saved: orders.png")

        # Save full HTML
        html = await page.content()
        with open("orders.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML saved: orders.html")

        # Dump candidate selectors to console
        selectors = await page.evaluate("""() => {
            const out = [];

            // Status tabs
            document.querySelectorAll('[role="tab"]').forEach(el => {
                out.push({type: 'tab', text: el.innerText?.trim(), class: el.className, id: el.id});
            });

            // Any element containing "Awaiting" or "Shipment"
            document.querySelectorAll('*').forEach(el => {
                if (el.children.length === 0) {
                    const t = el.innerText?.trim();
                    if (t && (t.toLowerCase().includes('awaiting') || t.toLowerCase().includes('shipment'))) {
                        out.push({
                            type: 'text-match',
                            text: t,
                            tag: el.tagName,
                            class: el.className,
                            id: el.id,
                            dataAttrs: el.dataset
                        });
                    }
                }
            });

            // Dropdowns / selects
            document.querySelectorAll('select,[role="combobox"],[role="listbox"],[class*="select"],[class*="filter"]').forEach(el => {
                out.push({type: 'dropdown', tag: el.tagName, class: el.className, id: el.id});
            });

            return out;
        }""")

        print("\n=== Candidate selectors ===")
        for s in selectors:
            print(s)

        input("\nDone! Press Enter to close the browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
