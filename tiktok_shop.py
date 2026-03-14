import argparse
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


PRODUCT_SKU = "G-BOX-FD-STRAWBERRY-SHOTCAKE-M"

# --- Combine Orders modal ---
COMBINE_CONFIRM_BUTTON_SELECTORS = [
    "button[data-id='fulfillment.combine_package.confirm_all_combination']",
    "button[data-log_click_for='accept_all_combination']",
    "//button[.//span[normalize-space()='Combine orders and continue']]",
]


async def handle_combine_orders_modal(page: Page, timeout: float = 8.0) -> bool:
    """
    Return True only if the Combine Orders modal was actually present and acted upon.

    Polls for the "Combine orders and continue" confirm button for up to `timeout`
    seconds.  When found, scrolls to it and tries several click strategies
    (normal click → JS click → Space key → MouseEvent dispatch).  Returns True
    as soon as the button disappears after a click, meaning the modal was
    successfully dismissed.  Returns the last value of `seen` (True if the
    button was ever visible) if the timeout expires before the modal clears.
    """
    import time as _time

    end = _time.time() + timeout
    seen = False

    while _time.time() < end:
        # Try each selector until we find a visible button
        btn = None
        for selector in COMBINE_CONFIRM_BUTTON_SELECTORS:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=1500)
                btn = locator
                break
            except Exception:
                continue

        if btn is None:
            await asyncio.sleep(0.2)
            continue

        seen = True
        print("Combine Orders modal detected.")

        try:
            await btn.scroll_into_view_if_needed()
        except Exception:
            pass

        # Strategy 1: normal Playwright click
        clicked = False
        try:
            await btn.click()
            clicked = True
        except Exception:
            pass

        # Strategy 2: JS element.click()
        if not clicked:
            try:
                handle = await btn.element_handle()
                if handle:
                    await page.evaluate("el => el.click()", handle)
                    clicked = True
            except Exception:
                pass

        # Strategy 3: Space key press
        if not clicked:
            try:
                await btn.press("Space")
                clicked = True
            except Exception:
                pass

        # Strategy 4: synthetic MouseEvent dispatch
        if not clicked:
            try:
                handle = await btn.element_handle()
                if handle:
                    await page.evaluate(
                        "el => el.dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true}))",
                        handle,
                    )
                    clicked = True
            except Exception:
                pass

        await asyncio.sleep(0.5)

        # If the button is gone the modal was dismissed — success
        still_visible = False
        for selector in COMBINE_CONFIRM_BUTTON_SELECTORS:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=1200)
                still_visible = True
                break
            except Exception:
                continue

        if not still_visible:
            print("Combine Orders modal dismissed.")
            return True

    return seen


async def _apply_product_filter(
    page: Page,
    sku: str,
    order_contents: str,
    shipping_method: str,
    combine_split: str,
) -> None:
    """
    Click the Filter button, type the SKU into the Product field, and apply.
    Selectors are derived from the live TikTok Shop filter-drawer HTML.
    """
    # The Filter button shown in the page toolbar (not the drawer)
    filter_btn = page.locator("button", has_text="Filter").first
    await filter_btn.wait_for(state="visible", timeout=15_000)
    await filter_btn.click()
    print("Filter panel opened.")
    await asyncio.sleep(1)

    # Product input — scoped to the wrapper whose prefix label is exactly "Product"
    # (other inputs share the same placeholder pattern, so we key off the label)
    product_input = page.locator(
        '.core-input-inner-wrapper:has(.core-input-group-prefix:text-is("Product")) input'
    )
    await product_input.wait_for(state="visible", timeout=10_000)
    await product_input.fill(sku)
    print(f"Typed SKU '{sku}' into product filter.")
    await asyncio.sleep(0.5)

    # Order Contents dropdown — keyed on data-log_json content_type="order_count_type_comp"
    order_contents_combobox = page.locator(
        '[data-log_click_for="filter_select"][data-log_json*="order_count_type_comp"] [role="combobox"]'
    )
    await order_contents_combobox.wait_for(state="visible", timeout=8_000)
    await order_contents_combobox.click()
    await asyncio.sleep(0.5)
    order_contents_option = page.locator(
        '[data-log_click_for="filter_select_option"]', has_text=order_contents
    )
    await order_contents_option.wait_for(state="visible", timeout=8_000)
    await order_contents_option.click()
    print(f"'{order_contents}' selected from Order Contents dropdown.")

    # Shipping Method dropdown — keyed on content_type="fulfillment_type_v2_comp_us"
    shipping_combobox = page.locator(
        '[data-log_click_for="filter_select"][data-log_json*="fulfillment_type_v2_comp_us"] [role="combobox"]'
    )
    await shipping_combobox.wait_for(state="visible", timeout=8_000)
    await shipping_combobox.click()
    await asyncio.sleep(0.5)
    shipping_option = page.locator(
        '[data-log_click_for="filter_select_option"]', has_text=shipping_method
    )
    await shipping_option.wait_for(state="visible", timeout=8_000)
    await shipping_option.click()
    print(f"'{shipping_method}' selected from Shipping Method dropdown.")

    # Order combine/split dropdown — keyed on content_type="combine_split_comp"
    combine_split_combobox = page.locator(
        '[data-log_click_for="filter_select"][data-log_json*="combine_split_comp"] [role="combobox"]'
    )
    await combine_split_combobox.wait_for(state="visible", timeout=8_000)
    await combine_split_combobox.click()
    await asyncio.sleep(0.5)
    combine_split_option = page.locator(
        '[data-log_click_for="filter_select_option"]', has_text=combine_split
    )
    await combine_split_option.wait_for(state="visible", timeout=8_000)
    await combine_split_option.click()
    print(f"'{combine_split}' selected from Order combine/split dropdown.")

    # Apply button — identified by data-log_click_for="apply" in the drawer HTML
    apply_btn = page.locator('[data-log_click_for="apply"]')
    await apply_btn.wait_for(state="visible", timeout=10_000)
    await apply_btn.click()
    print("Filter applied.")


def _is_checked(cls: str, aria: str | None) -> bool:
    return "checked" in cls.lower() or (aria or "").lower() == "true"


async def _click_select_all_checkbox(page: Page) -> None:
    """
    Click the 'select all' header checkbox to select all rows on the current page.

    Strategy (mirrors the battle-tested Selenium approach in the archive):
      1. Find the label via data-id / data-tid attributes.
      2. Skip if already checked (class contains 'checked' or aria-checked=true).
      3. Try several click strategies in order:
           a) Playwright click with force=True on the label
           b) JS element.click() on the label
           c) Playwright click with force=True on the mask wrapper
           d) JS click on the mask wrapper
           e) JS click on the bare <input>
           f) Dispatch a synthetic MouseEvent on the label
      4. Verify the checkbox is now checked after each successful click.
    """
    label_selector = "label[data-tid='m4b_checkbox'][data-id='fulfillment.table.select_current_package']"
    label = page.locator(label_selector).first
    try:
        await label.wait_for(state="visible", timeout=10_000)
    except Exception:
        # Fallback: first header checkbox
        label = page.locator("th[data-log_click_for='select_all_items_in_page'] label").first
        await label.wait_for(state="visible", timeout=8_000)

    # Boost z-index so nothing intercepts clicks
    try:
        handle = await label.element_handle()
        if handle:
            await page.evaluate("el => { el.style.zIndex = '2147483647'; }", handle)
    except Exception:
        pass

    async def is_now_checked() -> bool:
        try:
            cls = await label.get_attribute("class") or ""
            aria = await label.get_attribute("aria-checked")
            if _is_checked(cls, aria):
                return True
            # Also accept: input.checked is truthy
            inp_loc = label.locator("input[type='checkbox']").first
            if await inp_loc.count() > 0:
                inp_handle = await inp_loc.element_handle()
                if inp_handle:
                    checked = await page.evaluate("el => el.checked", inp_handle)
                    return bool(checked)
        except Exception:
            pass
        return False

    # Already checked — nothing to do
    if await is_now_checked():
        print("Select-all checkbox already checked.")
        return

    lbl_handle = await label.element_handle()
    mask = label.locator(".core-checkbox-mask-wrapper").first
    mask_handle = await mask.element_handle() if await mask.count() > 0 else None
    inp_loc = label.locator("input[type='checkbox']").first
    inp_handle = await inp_loc.element_handle() if await inp_loc.count() > 0 else None

    async def try_click_playwright(loc) -> bool:
        try:
            await loc.scroll_into_view_if_needed()
            await loc.click(force=True)
            return True
        except Exception:
            return False

    async def try_js_click(handle) -> bool:
        if not handle:
            return False
        try:
            await page.evaluate("el => el.click()", handle)
            return True
        except Exception:
            return False

    async def try_dispatch_event(handle) -> bool:
        if not handle:
            return False
        try:
            await page.evaluate(
                "el => el.dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true,view:window}))",
                handle,
            )
            return True
        except Exception:
            return False

    strategies = [
        ("Playwright force-click label", lambda: try_click_playwright(label)),
        ("JS click label", lambda: try_js_click(lbl_handle)),
        ("Playwright force-click mask", lambda: try_click_playwright(mask)),
        ("JS click mask", lambda: try_js_click(mask_handle)),
        ("JS click input", lambda: try_js_click(inp_handle)),
        ("MouseEvent dispatch on label", lambda: try_dispatch_event(lbl_handle)),
    ]

    for name, strategy in strategies:
        try:
            await strategy()
        except Exception:
            continue
        await asyncio.sleep(0.4)
        if await is_now_checked():
            print(f"Select-all checkbox checked via: {name}")
            return

    screenshot_path = Path("debug_select_all.png")
    await page.screenshot(path=str(screenshot_path), full_page=True)
    raise RuntimeError(
        "Could not check the select-all checkbox after trying all strategies. "
        f"Screenshot saved to '{screenshot_path}'."
    )


async def navigate_to_awaiting_shipment(
    page: Page,
    sku: str,
    order_contents: str,
    shipping_method: str,
    combine_split: str,
) -> None:
    """
    Navigate to Manage Orders and filter to 'Awaiting shipment' orders
    for the given product SKU and filter values.

    Steps:
      1. Go to the orders page.
      2. Click the Filter button and filter by product SKU.
      3. Click the select-all checkbox to select all visible rows.
    """
    print(f"Navigating to Manage Orders: {ORDERS_URL}")
    await page.goto(ORDERS_URL, wait_until="domcontentloaded")
    await asyncio.sleep(4)  # wait for JS-rendered page

    await _apply_product_filter(page, sku, order_contents, shipping_method, combine_split)
    await asyncio.sleep(2)  # wait for filtered results to load
    print(f"Filter applied: product={sku}")

    await _click_select_all_checkbox(page)
    await _click_arrange_shipment_button(page)


ARRANGE_SHIPMENT_SELECTORS = [
    "button[data-id='fulfillment.manage_order.batch_arrange_shipment']",
    "button[data-log_click_for='arrange_shipment']",
    "//button[.//span[contains(normalize-space(),'Arrange shipment')]]",
]


async def _click_arrange_shipment_button(page: Page) -> None:
    """
    Wait for the 'Arrange shipment' button to appear (it only shows after rows
    are selected) then click it.
    """
    for selector in ARRANGE_SHIPMENT_SELECTORS:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=10_000)
            await locator.click()
            print("'Arrange shipment' button clicked.")
            return
        except Exception:
            continue

    screenshot_path = Path("debug_arrange_shipment.png")
    await page.screenshot(path=str(screenshot_path), full_page=True)
    raise RuntimeError(
        "Could not find the 'Arrange shipment' button. "
        f"Screenshot saved to '{screenshot_path}'."
    )


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
    parser = argparse.ArgumentParser(description="TikTok Shop order automation")
    parser.add_argument("--sku", default=PRODUCT_SKU, help="Product SKU to filter by")
    parser.add_argument("--order-contents", default="Single item", dest="order_contents",
                        help="Order Contents filter value (default: 'Single item')")
    parser.add_argument("--shipping-method", default="TikTok Shipping (Upgraded)", dest="shipping_method",
                        help="Shipping Method filter value (default: 'TikTok Shipping (Upgraded)')")
    parser.add_argument("--combine-split", default="Original", dest="combine_split",
                        help="Order combine/split filter value (default: 'Original')")
    args = parser.parse_args()

    async with async_playwright() as playwright:
        browser, context, page = await get_authenticated_context(playwright)
        print(f"Current URL: {page.url}")

        await navigate_to_awaiting_shipment(
            page, args.sku, args.order_contents, args.shipping_method, args.combine_split
        )
        order_ids = await get_awaiting_shipment_order_ids(page)
        print("Order IDs:", order_ids)

        input("Press Enter to close the browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
