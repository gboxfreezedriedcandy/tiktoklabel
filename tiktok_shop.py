import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page

COOKIES_FILE = Path("cookies.json")
TIKTOK_SHOP_URL = "https://seller-us.tiktok.com/account/login"


async def save_cookies(context: BrowserContext) -> None:
    cookies = await context.cookies()
    COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
    print(f"Saved {len(cookies)} cookies to {COOKIES_FILE}")


async def load_cookies(context: BrowserContext) -> bool:
    """Load cookies from file into context. Returns True if cookies were loaded."""
    if not COOKIES_FILE.exists():
        return False
    cookies = json.loads(COOKIES_FILE.read_text())
    await context.add_cookies(cookies)
    print(f"Loaded {len(cookies)} cookies from {COOKIES_FILE}")
    return True


CAPTCHA_SELECTORS = [
    "[class*='captcha']",
    "[id*='captcha']",
    "[class*='verify']",
    "[id*='verify']",
    "iframe[src*='captcha']",
    "iframe[src*='recaptcha']",
]


async def wait_for_captcha_if_present(page: Page) -> None:
    """If a CAPTCHA is detected, pause until the user solves it."""
    for selector in CAPTCHA_SELECTORS:
        try:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
                print("\n*** CAPTCHA detected! Please solve it in the browser window. ***")
                print("Waiting for CAPTCHA to be resolved...")
                # Poll until none of the CAPTCHA selectors are visible
                while True:
                    await asyncio.sleep(1)
                    visible = False
                    for sel in CAPTCHA_SELECTORS:
                        el = await page.query_selector(sel)
                        if el and await el.is_visible():
                            visible = True
                            break
                    if not visible:
                        print("CAPTCHA resolved. Continuing...")
                        break
                return
        except Exception:
            continue


async def login(playwright) -> None:
    """Open browser for manual login, then save session cookies."""
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()

    print("Opening TikTok Shop Seller Center...")
    await page.goto(TIKTOK_SHOP_URL)
    await wait_for_captcha_if_present(page)

    print("Please log in manually in the browser window.")
    print("Waiting for you to reach the seller dashboard...")

    # Wait until the URL changes away from the login page; no hard timeout so
    # CAPTCHAs that appear mid-login don't cause a premature failure.
    while True:
        await asyncio.sleep(1)
        await wait_for_captcha_if_present(page)
        if "login" not in page.url and "passport" not in page.url:
            break

    # Give the page a moment to fully settle after redirect
    await page.wait_for_load_state("domcontentloaded")
    await asyncio.sleep(2)

    await save_cookies(context)
    print("Login complete. Cookies saved.")
    await browser.close()


async def get_authenticated_context(playwright) -> tuple[object, BrowserContext, Page]:
    """
    Return (browser, context, page) with an authenticated session.
    Reuses saved cookies if available, otherwise triggers manual login.
    """
    has_cookies = await _try_cookies_exist()

    if not has_cookies:
        print("No saved cookies found. Starting fresh login...")
        await login(playwright)

    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    await load_cookies(context)
    page = await context.new_page()

    print("Resuming session with saved cookies...")
    await page.goto(TIKTOK_SHOP_URL, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # Check whether cookies are still valid
    if "login" in page.url or "passport" in page.url:
        print("Saved cookies expired. Triggering fresh login...")
        await browser.close()
        await login(playwright)

        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        await load_cookies(context)
        page = await context.new_page()
        await page.goto(TIKTOK_SHOP_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

    return browser, context, page


async def _try_cookies_exist() -> bool:
    return COOKIES_FILE.exists()


ORDERS_URL = "https://seller-us.tiktok.com/order"


async def _click_to_ship_tab(page: Page) -> None:
    """
    Click the 'To ship' status tab using several selector strategies in order.
    Takes a debug screenshot if all strategies fail so the caller can inspect
    what was actually rendered.
    """
    # Strategies tried in order (most-specific → least-specific)
    strategies = [
        # 1. data attribute (older TikTok Shop builds)
        page.locator('[data-log_click_for="to_ship"]'),
        # 2. ARIA tab role with visible label
        page.get_by_role("tab", name="To ship"),
        page.get_by_role("tab", name="To Ship"),
        # 3. Plain text inside any clickable element
        page.locator("text=To ship").first,
        page.locator("text=To Ship").first,
        # 4. TikTok Shop sometimes renders tabs as <li> items
        page.locator("li", has_text="To ship").first,
    ]

    for locator in strategies:
        try:
            await locator.wait_for(state="visible", timeout=5_000)
            await locator.click()
            print("'To ship' tab clicked.")
            return
        except Exception:
            continue

    # All strategies failed — take a screenshot to help with debugging
    screenshot_path = Path("debug_to_ship_tab.png")
    await page.screenshot(path=str(screenshot_path), full_page=True)
    raise RuntimeError(
        f"Could not find the 'To ship' tab after trying {len(strategies)} selectors. "
        f"A full-page screenshot was saved to '{screenshot_path}'. "
        "Open it to inspect the actual page layout and update the selector."
    )


async def _click_awaiting_shipment_option(page: Page) -> None:
    """
    Open the Order-status combobox and select 'Awaiting shipment'.
    Falls back to a plain text search when the data-attribute selector misses.
    """
    # Try the data-attribute wrapper first, then a plain combobox search
    combobox_strategies = [
        page.locator(
            '[data-log_content_type="order_status_comp_for_to_ship_in_us"] [role="combobox"]'
        ),
        page.get_by_role("combobox").first,
    ]
    for locator in combobox_strategies:
        try:
            await locator.wait_for(state="visible", timeout=8_000)
            await locator.click()
            print("Order status combobox opened.")
            break
        except Exception:
            continue
    else:
        screenshot_path = Path("debug_combobox.png")
        await page.screenshot(path=str(screenshot_path), full_page=True)
        raise RuntimeError(
            f"Could not open the Order status combobox. "
            f"Screenshot saved to '{screenshot_path}'."
        )

    await asyncio.sleep(1)  # wait for dropdown animation

    # Pick 'Awaiting shipment' from the listbox
    awaiting_option = page.locator('[role="option"]', has_text="Awaiting shipment")
    await awaiting_option.first.wait_for(state="visible", timeout=10_000)
    await awaiting_option.first.click()
    print("'Awaiting shipment' option selected.")


async def navigate_to_awaiting_shipment(page: Page) -> None:
    """
    Navigate to Manage Orders and filter to 'Awaiting shipment' orders.

    Steps:
      1. Go to the all-orders list page.
      2. Click the 'To ship' status tab.
      3. Open the 'Order status' dropdown and choose 'Awaiting shipment'.
    """
    print(f"Navigating to Manage Orders: {ORDERS_URL}")
    await page.goto(ORDERS_URL, wait_until="domcontentloaded")
    await asyncio.sleep(4)  # wait for JS-rendered tabs to appear

    await _click_to_ship_tab(page)
    await asyncio.sleep(2)  # SPA tab switch — no full navigation event

    await _click_awaiting_shipment_option(page)
    await asyncio.sleep(2)  # wait for filtered results to load
    print("Filter applied: Awaiting shipment")


async def get_awaiting_shipment_order_ids(page: Page) -> list[str]:
    """
    Return a list of order IDs currently visible on the filtered orders page.
    Each order row carries data-log_order_status="101" and
    data-log_order_sub_status="1" for 'Awaiting shipment'.
    """
    rows = await page.query_selector_all(
        '[data-log_order_status="101"][data-log_order_sub_status="1"]'
    )
    order_ids: list[str] = []
    for row in rows:
        oid = await row.get_attribute("data-log_order_id")
        if oid:
            order_ids.append(oid)
    print(f"Found {len(order_ids)} awaiting-shipment orders on this page.")
    return order_ids


async def main():
    async with async_playwright() as playwright:
        browser, context, page = await get_authenticated_context(playwright)
        print(f"Current URL: {page.url}")

        await navigate_to_awaiting_shipment(page)
        order_ids = await get_awaiting_shipment_order_ids(page)
        print("Order IDs:", order_ids)

        input("Press Enter to close the browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
