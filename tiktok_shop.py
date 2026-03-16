import argparse
import json
import asyncio
from pathlib import Path
from typing import Any, Optional
from playwright.async_api import async_playwright, BrowserContext, Locator, Page

TIKTOK_SHOP_URL = "https://seller-us.tiktok.com/account/login"


def _cookies_file(account: str) -> Path:
    if account == "default":
        return Path("cookies.json")
    return Path(f"cookies_{account}.json")


async def save_cookies(context: BrowserContext, account: str = "default") -> None:
    path = _cookies_file(account)
    cookies = await context.cookies()
    path.write_text(json.dumps(cookies, indent=2))
    print(f"Saved {len(cookies)} cookies to {path}")


async def load_cookies(context: BrowserContext, account: str = "default") -> bool:
    """Load cookies from file into context. Returns True if cookies were loaded."""
    path = _cookies_file(account)
    if not path.exists():
        return False
    cookies = json.loads(path.read_text())
    await context.add_cookies(cookies)
    print(f"Loaded {len(cookies)} cookies from {path}")
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


async def login(playwright, account: str = "default") -> None:
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

    await save_cookies(context, account)
    print("Login complete. Cookies saved.")
    await browser.close()


async def get_authenticated_context(playwright, account: str = "default") -> tuple[object, BrowserContext, Page]:
    """
    Return (browser, context, page) with an authenticated session.
    Reuses saved cookies if available, otherwise triggers manual login.
    """
    has_cookies = await _try_cookies_exist(account)

    if not has_cookies:
        print(f"No saved cookies found for account '{account}'. Starting fresh login...")
        await login(playwright, account)

    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    await load_cookies(context, account)
    page = await context.new_page()

    print("Resuming session with saved cookies...")
    await page.goto(TIKTOK_SHOP_URL, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # Check whether cookies are still valid
    if "login" in page.url or "passport" in page.url:
        print("Saved cookies expired. Triggering fresh login...")
        await browser.close()
        await login(playwright, account)

        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        await load_cookies(context, account)
        page = await context.new_page()
        await page.goto(TIKTOK_SHOP_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

    return browser, context, page


async def _try_cookies_exist(account: str = "default") -> bool:
    return _cookies_file(account).exists()


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

# Weight (kg) per SKU used to auto-fill the package weight field.
SKU_WEIGHTS: dict[str, float] = {
    "G-BOX-GIFT-BOX-V1": 2,
    "G-BOX-FD-CHOCOLATE-ECLAIR-M": 0.3,
    "G-BOX-FD-CHOCOLATE-ECLAIR-L": 0.59375,
    "G-BOX-SOUR-WORM-GUMMY": 0.24375,
    "G-BOX-WORM-GUMMY": 0.2375,
    "G-BOX-CROCODILES-GUMMY": 0.2375,
    "G-BOX-FD-JELLO-SAMPLE-PACK": 1.75,
    "G-BOX-FD-JELLO-WATERMELON-M": 0.19375,
    "G-BOX-FD-JELLO-WATERMELON-L": 0.35625,
    "G-BOX-FD-JELLO-CHERRY-L": 0.3625,
    "G-BOX-FD-JELLO-CHERRY-M": 0.20625,
    "G-BOX-FD-JELLO-LEMON-L": 0.38125,
    "G-BOX-FD-JELLO-LEMON-M": 0.2125,
    "G-BOX-FD-JELLO-PEACH-L": 0.375,
    "G-BOX-FD-JELLO-PEACH-M": 0.2,
    "G-BOX-FD-JELLO-STRAWBERRY-L": 0.375,
    "G-BOX-FD-JELLO-STRAWBERRY-M": 0.20625,
    "G-BOX-FD-JELLO-STRAWBERRY-PINK-L": 0.325,
    "G-BOX-FD-JELLO-STRAWBERRY-PINK-M": 0.2,
    "G-BOX-FD-JELLO-BLUEBERRY-L": 0.35625,
    "G-BOX-FD-JELLO-BLUEBERRY-M": 0.20625,
    "G-BOX-FD-JELLO-LIME-L": 0.36875,
    "G-BOX-FD-JELLO-LIME-M": 0.19375,
    "G-BOX-FD-JELLO-ORANGE-L": 0.4,
    "G-BOX-FD-JELLO-ORANGE-M": 0.20625,
    "G-BOX-FD-JELLO-PINEAPPLE-L": 0.3625,
    "G-BOX-FD-JELLO-PINEAPPLE-M": 0.20625,
    "RANCH-CUCUMBER-LARGE": 0.18125,
    "G-BOX-PICKLES-SMALL": 0.11875,
    "G-BOX-PICKLES-MEDIUM": 0.11875,
    "G-BOX-PICKLES-LARGE": 0.18125,
    "G-BOX-CHAMOY-PICKLES-LARGE": 0.2625,
    "G-BOX-CHAMOY-PICKLES-SMALL": 0.14375,
    "CHAMOY-CUCUMBER-LARGE": 0.2625,
    "G-BOX-FRUIT-ROLL-UP-L": 0.375,
    "G-BOX-FRUIT-ROLL-UP-M": 0.21875,
    "G-BOX-FD-LEMONCANDY-8OZ": 0.625,
    "LEMONCANDY-4OZ": 0.3125,
    "G-BOX-FD-GUMMY-BEAR": 0.5625,
    "G-BOX-FD-FROZEN-GUMMY-BEAR": 0.5625,
    "G-BOX-FD-AIR-CRUNCH": 0.4,
    "G-BOX-SOUR-FRETTLE-SMALL": 0.275,
    "G-BOX-SOUR-MEDIUM": 0.41875,
    "G-BOX-FD-FRETTLES-LARGE": 0.8,
    "G-BOX-SOUR-FRETTLE-LARGE": 0.79375,
    "G-BOX-FD-FRETTLES-SMALL": 0.275,
    "G-BOX-FD-FRETTLES-MEDIUM": 0.4625,
    "G-BOX-FD-WILDBERRY-SMALL": 0.23125,
    "G-BOX-FD-MARSHMALLOWS-MINI": 0.3375,
    "G-BOX-FD-MARSHMALLOWS-CAR-M": 0.35625,
    "G-BOX-FD-MARSHMALLOWS-CAR-L": 0.5375,
    "G-BOX-LARGE-GUMMY-CLUSTER": 0.4875,
    "G-BOX-FD-ICECREAM-SANDWICH-3OZ": 0.3375,
    "G-BOX-FD-ICECREAM-SANDWICH-7OZ": 0.59375,
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-S": 0.203125,
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-M": 0.2625,
    "G-BOX-FD-STRAWBERRY-SHORTCAKE-L": 0.53125,
    "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-M": 0.24375,
    "G-BOX-FD-ICE-CREAM-CUBES-VANILLA-L": 0.44375,
    "G-BOX-FD-ICECREAMCUBESVANILLA-L": 0.44375,
    "G-BOX-FD-ICE-CREAM-CUBES-CHOCOLATE-M": 0.2875,
    "G-BOX-FD-ICE-CREAM-CUBES-CHOCOLATE-L": 0.43125,
    "G-BOX-CHAMOY-FRETTLES-MEDIUM": 0.45625,
    "G-BOX-CHAMOY-FRETTLES-LARGE": 0.8,
    "G-BOX-CHAMOY-MEDIUM": 0.45625,
    "G-BOX-CHAMOY-LARGE": 0.8,
    "G-BOX-PEACH-RING": 0.33125,
    "G-BOX-CHAMOY-PEACH-RING": 0.34375,
    "G-BOX-FD-STRAWBERRY-GUMMY": 0.3,
    "G-BOX-FD-WATERMELON-GUMMY": 0.475,
    "G-BOX-FD-HONEY-CANDY": 0.475,
    "G-BOX-SUBSCRIPTION-BOX-V1": 2,
    "G-BOX-FD-FRETTLES-XLARGE": 1.5625,
    "G-BOX-FD-GUMMY-FROGS-3": 0.21875,
    "G-BOX-FD-TAFFY-COTTON-CANDY": 0.28125,
    "G-BOX-FD-TAFFY-VANILLA": 0.33125,
    "G-BOX-FD-TAFFY-WATERMELON": 0.25,
    "G-BOX-FD-TAFFY-BANANA": 0.2375,
    "G-BOX-FD-TAFFY-PEPPERMINT": 0.2625,
    "G-BOX-FD-TAFFY-GREEN-APPLE": 0.28125,
    "G-BOX-FD-TAFFY-SHAVED-ICE": 0.3125,
    "G-BOX-FD-TAFFY-KIWI-STRAWBERRY": 0.28125,
    "G-BOX-FD-TAFFY-BLACKBERRY-CRUMBLE": 0.325,
    "G-BOX-FD-CHOCO-CRUNCH-L": 0.5,
    "G-BOX-FD-CHOCO-CRUNCH-M": 0.24375,
    "G-BOX-FD-FRETTLES-SOUR-XLARGE": 1.8125,
    "G-BOX-SOUR-FRETTLE-MEDIUM": 0.35,
    "G-BOX-FREESES-M": 0.3375,
    "G-BOX-FREESES-L": 0.625,
    "G-BOX-CHAMOY-FRETTLES-XL-JAR": 1.875,
    "G-BOX-FD-JELLO-BB-LEMON-L": 0.35,
    "G-BOX-FD-JELLO-BB-LEMON-M": 0.20625,
    "G-BOX-FD-DUBAI-CHOCOLATE-L": 0.75625,
    "G-BOX-FD-DUBAI-CHOCOLATE-M": 0.4125,
    "G-BOX-FD-DUBAI-CHOCOLATE-S": 0.1875,
}

# --- Combine Orders modal ---
COMBINE_CONFIRM_BUTTON_SELECTORS = [
    "button[data-id='fulfillment.combine_package.confirm_all_combination']",
    "button[data-log_click_for='accept_all_combination']",
    "//button[.//span[contains(normalize-space(),'ombine') and contains(normalize-space(),'and continue')]]",
]

REFRESH_ORDERS_SELECTOR = "button[data-log_click_for='refresh_orders']"


async def _click_refresh_orders_button(page: Page) -> None:
    """Click the refresh orders button and wait for the page to settle."""
    try:
        btn = page.locator(REFRESH_ORDERS_SELECTOR).first
        await btn.wait_for(state="visible", timeout=10_000)
        await btn.click()
        print("Refresh orders button clicked.")
        await asyncio.sleep(3)  # wait for orders to reload after combining
    except Exception as e:
        print(f"Warning: could not click refresh orders button: {e}")


async def handle_combine_orders_modal(page: Page, timeout: float = 15.0) -> bool:
    """
    Check for the Combine Orders modal and handle it if present.

    Polls for the "Accept all X combinations and continue" button for up to
    `timeout` seconds. When found, clicks it, waits for combining to finish,
    then clicks the refresh orders button. Returns True if the modal was found
    and handled, False otherwise.
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
            await asyncio.sleep(0.3)
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

        await asyncio.sleep(1)

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
            print("Combine Orders modal dismissed. Waiting for combining to finish...")
            await asyncio.sleep(3)  # wait for combining to complete
            return True

    return seen


async def _set_page_size(page: Page, size: int) -> None:
    """Change the pagination page-size dropdown to the given value (e.g. 50)."""
    combobox = page.locator('.core-pagination-option [role="combobox"]')
    await combobox.wait_for(state="visible", timeout=10_000)

    # Grab a handle to the first existing row so we can detect when the table
    # unmounts and re-mounts with the new page size.
    first_row = page.locator("table tbody tr").first
    old_row_handle = None
    try:
        old_row_handle = await first_row.element_handle(timeout=3_000)
    except Exception:
        pass  # no rows yet — nothing to wait for detachment on

    await combobox.click()
    await asyncio.sleep(1)
    # Resolve popup container from aria-controls, then find the option by text.
    popup_id = await combobox.get_attribute("aria-controls")
    if popup_id:
        option = page.locator(f"#{popup_id}").get_by_text(f"{size}/Page", exact=True)
    else:
        option = page.get_by_text(f"{size}/Page", exact=True).last
    await option.wait_for(state="visible", timeout=8_000)
    await option.click()
    print(f"Page size set to {size}. Waiting for table to refresh...")

    # Wait for the old row to detach (table teardown), then for new rows to appear.
    if old_row_handle:
        try:
            await page.wait_for_function(
                "el => !el.isConnected", arg=old_row_handle, timeout=10_000
            )
            print("Old rows detached — table is refreshing.")
        except Exception:
            pass  # may already be gone or same DOM reused

    await page.wait_for_selector("table tbody tr", state="visible", timeout=20_000)
    print(f"Table reloaded with {size}/page.")


async def _apply_shipping_method_filter(page: Page, shipping_method: str) -> None:
    """Apply only the Shipping Method filter (used by mixed-orders mode)."""
    filter_btn = page.locator("button", has_text="Filter").first
    await filter_btn.wait_for(state="visible", timeout=15_000)
    await filter_btn.click()
    print("Filter panel opened.")
    await asyncio.sleep(1)

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

    apply_btn = page.locator('[data-log_click_for="apply"]')
    await apply_btn.wait_for(state="visible", timeout=10_000)
    await apply_btn.click()
    print("Filter applied.")


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


async def _click_bulk_select_all_if_present(page: Page) -> None:
    """
    After the header checkbox is checked, TikTok may show a 'Select all N packages'
    button (data-log_click_for='bulk_select') when the total exceeds the current
    page.  Click it if it appears so that ALL packages across pages are selected.
    """
    # Give TikTok a moment to render the bulk-select button after the checkbox change
    await asyncio.sleep(2)

    selectors = [
        "button[data-log_click_for='bulk_select'][data-id='fulfillment.table.select_all_package']",
        "button[data-log_click_for='bulk_select']",
        "//button[.//span[contains(normalize-space(),'Select all') and contains(normalize-space(),'package')]]",
    ]

    btn = None
    for selector in selectors:
        try:
            is_xpath = selector.startswith("//")
            loc = page.locator(f"xpath={selector}" if is_xpath else selector).first
            await loc.wait_for(state="visible", timeout=3_000)
            btn = loc
            print(f"Bulk-select-all button found via: {selector!r}")
            break
        except Exception:
            continue

    if btn is None:
        print("No bulk-select-all button found; current page selection is sufficient.")
        return

    total = await btn.get_attribute("data-log_total_cnt") or "?"
    handle = await btn.element_handle()

    strategies: list[tuple[str, Any]] = [
        ("direct click",       lambda: btn.click(timeout=5_000)),
        ("force click",        lambda: btn.click(force=True, timeout=5_000)),
        ("JS click",           lambda: page.evaluate("el => el.click()", handle)),
        ("dispatch click",     lambda: page.evaluate(
            "el => el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}))", handle
        )),
    ]

    for name, strategy in strategies:
        try:
            await strategy()
            await asyncio.sleep(0.5)
            print(f"Clicked 'Select all {total} packages' via: {name}")
            await asyncio.sleep(1)
            return
        except Exception as exc:
            print(f"Bulk-select strategy '{name}' failed: {exc}")
            continue

    print("Warning: could not click bulk-select-all button after all strategies.")


async def _close_weight_drawer(page: Page) -> None:
    """Dismiss the batch-edit-weight drawer via Escape, ensuring it doesn't block subsequent clicks."""
    try:
        drawer = page.locator("[data-log_module_name='batch_edit_weight_all_package_info_drawer']").first
        await drawer.wait_for(state="visible", timeout=3_000)
        await page.keyboard.press("Escape")
        await drawer.wait_for(state="hidden", timeout=5_000)
    except Exception:
        pass


async def _batch_edit_weight(page: Page, weight: float | None) -> None:
    """Click 'Edit weight', set the weight value, and click Apply.
    Skips silently if weight is None or the button is not found."""
    if weight is None:
        return

    edit_btn_selector = "button[data-log_click_for='4pl_batch_edit_weight_all_package_info']"
    try:
        btn = page.locator(edit_btn_selector).first
        await btn.wait_for(state="visible", timeout=10_000)
        await btn.click()
        print(f"Edit weight button clicked. Setting weight to {weight}.")
    except Exception as e:
        print(f"Warning: could not click Edit weight button: {e}")
        return

    # Wait for the drawer, then clear the input and type the new value.
    # el.select() selects all text at the DOM level (reliable on Vue spinbuttons
    # where keyboard shortcuts like Ctrl+A may not work after a programmatic click).
    # Typing via page.keyboard replaces the selection and triggers Vue's v-model.
    input_selector = "input#packageWeight_input"
    try:
        inp = page.locator(input_selector).first
        await inp.wait_for(state="visible", timeout=10_000)
        await inp.click()
        await asyncio.sleep(0.2)
        await inp.evaluate("el => el.select()")
        await asyncio.sleep(0.1)
        await page.keyboard.type(str(weight), delay=100)
        # Confirm the value was accepted
        actual = await inp.input_value()
        print(f"Weight input value after typing: {actual!r}")
    except Exception as e:
        print(f"Warning: could not set weight value: {e}")
        await _close_weight_drawer(page)
        return

    # Click the Apply button
    apply_selector = "button[data-log_click_for='bulk_edit_weight_amending_apply']"
    try:
        apply_btn = page.locator(apply_selector).first
        await apply_btn.wait_for(state="visible", timeout=10_000)
        await apply_btn.click()
        print("Apply clicked for batch weight edit.")
        await asyncio.sleep(2)
    except Exception as e:
        print(f"Warning: could not click Apply for weight edit: {e}")
        await _close_weight_drawer(page)


async def _print_document(page: Page) -> None:
    """
    Click 'Print document', open the edit drawer, ensure Shipping label and
    Packing slip are checked, then confirm.
    """
    # 1. Click the Print document button
    print_btn = page.locator("[data-id='fulfillment.create_shipping_label.print_document']").first
    try:
        await print_btn.wait_for(state="visible", timeout=15_000)
        await print_btn.click()
        print("Clicked 'Print document'.")
    except Exception as e:
        print(f"Warning: could not click Print document: {e}")
        return

    # 2. Wait for the popover and click Edit
    edit_btn = page.locator("[data-id='fulfillment.create_shipping_label.print_document_edit']").first
    try:
        await edit_btn.wait_for(state="visible", timeout=10_000)
        await edit_btn.click()
        print("Clicked 'Edit' in print document popover.")
    except Exception as e:
        print(f"Warning: could not click Edit in print popover: {e}")
        return

    # 3. Wait for the drawer
    drawer = page.locator(".core-drawer-inner").first
    try:
        await drawer.wait_for(state="visible", timeout=10_000)
    except Exception as e:
        print(f"Warning: print settings drawer did not appear: {e}")
        return

    # 4. Ensure Shipping label and Packing slip checkboxes are checked
    for data_id, label in [
        ("fulfillment.print_document.selection.shipping_label", "Shipping label"),
        ("fulfillment.print_document.selection.packing_slip", "Packing slip"),
    ]:
        cb_label = page.locator(f"label[data-id='{data_id}']").first
        cb_input = cb_label.locator("input[type='checkbox']").first
        try:
            await cb_input.wait_for(state="attached", timeout=5_000)
            is_checked = await cb_input.is_checked()
            if not is_checked:
                await cb_label.click()
                print(f"Checked '{label}'.")
            else:
                print(f"'{label}' already checked.")
        except Exception as e:
            print(f"Warning: could not check '{label}': {e}")

    # 5. Click Confirm
    confirm_btn = page.locator("button[data-log_click_for='select_print_document_drawer_confirm']").first
    try:
        await confirm_btn.wait_for(state="visible", timeout=5_000)
        await confirm_btn.click()
        print("Clicked Confirm on print settings drawer.")
    except Exception as e:
        print(f"Warning: could not click Confirm on print settings: {e}")


async def combine_orders_mode(page: Page) -> None:
    """
    combine-orders mode: no filters, select all, arrange shipment,
    handle combine popup if it appears, then wait for the next page.
    """
    print("combine-orders mode: navigating to orders page...")
    await page.goto(ORDERS_URL, wait_until="domcontentloaded")
    await asyncio.sleep(4)

    await _click_select_all_checkbox(page)
    await _click_bulk_select_all_if_present(page)
    await _click_arrange_shipment_button(page)

    combined = await handle_combine_orders_modal(page, timeout=15.0)
    if combined:
        print("Orders combined. Waiting for shipment page...")
    else:
        print("No combine modal. Waiting for shipment page...")

    await page.wait_for_load_state("domcontentloaded")
    try:
        await page.wait_for_selector(
            "table[data-table-component='true'] tbody tr",
            state="visible",
            timeout=30_000,
        )
        print("Shipment page loaded.")
    except Exception:
        print("Warning: could not confirm table rows; proceeding anyway.")


async def navigate_to_awaiting_shipment(
    page: Page,
    sku: str,
    order_contents: str,
    shipping_method: str,
    combine_split: str,
    weight: float | None = None,
    mode: str = "single-order",
) -> None:
    """
    Navigate to Manage Orders and filter to 'Awaiting shipment' orders.

    mode='single-order': applies all filters; clicks bulk-select-all on both pages.
    mode='mixed-orders': applies only shipping_method filter; skips bulk-select-all.
    """
    print(f"Navigating to Manage Orders: {ORDERS_URL}")
    await page.goto(ORDERS_URL, wait_until="domcontentloaded")
    await asyncio.sleep(4)  # wait for JS-rendered page

    await _set_page_size(page, 50)

    if mode == "mixed-orders":
        await _apply_shipping_method_filter(page, shipping_method)
    else:
        await _apply_product_filter(page, sku, order_contents, shipping_method, combine_split)

    # Wait for the filtered rows to actually appear before selecting.
    print("Waiting for filtered rows to appear...")
    try:
        await page.wait_for_selector("table tbody tr", state="visible", timeout=20_000)
    except Exception:
        print("No orders found after filtering. Nothing to do.")
        return
    print("Filtered rows visible.")

    await _click_select_all_checkbox(page)
    if mode != "mixed-orders":
        await _click_bulk_select_all_if_present(page)
    await _click_arrange_shipment_button(page)

    combined = await handle_combine_orders_modal(page, timeout=15.0)
    if combined:
        print("Orders combined. Proceeding to shipment page...")
    else:
        print("No combine orders modal appeared. Proceeding normally.")

    await _wait_for_shipment_page_and_select_all(page)
    if mode != "mixed-orders":
        await _click_bulk_select_all_if_present(page)
    if mode == "mixed-orders":
        await scan_order_skus(page)
    else:
        await _batch_edit_weight(page, weight)
    await _print_document(page)


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


SHIPMENT_PAGE_SELECT_ALL_SELECTORS = [
    "th[data-log_click_for='select_all_items_in_page'] label",
    "th[data-log_click_for='select_all_items_in_page'] input[type='checkbox']",
    "label[data-id='fulfillment.table.select_current_package']",
]


async def _wait_for_shipment_page_and_select_all(page: Page) -> None:
    """
    After the 'Arrange shipment' button is clicked, wait for the new page to
    finish loading, then click the select-all checkbox in the shipment table.

    Uses the same robust multi-strategy approach as _click_select_all_checkbox
    to handle TikTok's custom checkbox components that resist simple clicks.
    """
    print("Waiting for shipment page to load...")
    # The arrange-shipment button navigates to a new URL; wait for that navigation
    await page.wait_for_load_state("domcontentloaded")

    # Wait for the table body rows to actually populate (async data load)
    print("Waiting for shipment table rows to populate...")
    try:
        await page.wait_for_selector(
            "table[data-table-component='true'] tbody tr",
            state="visible",
            timeout=30_000,
        )
        print("Shipment table rows detected.")
    except Exception:
        print("Warning: could not confirm table rows; proceeding anyway.")
    await asyncio.sleep(1)  # brief settle after rows appear

    # Locate the select-all label using the same selectors, with fallbacks
    label: Optional[Locator] = None
    for selector in SHIPMENT_PAGE_SELECT_ALL_SELECTORS:
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=10_000)
            label = loc
            print(f"Shipment select-all found via: {selector!r}")
            break
        except Exception:
            continue

    if label is None:
        screenshot_path = Path("debug_shipment_select_all.png")
        await page.screenshot(path=str(screenshot_path), full_page=True)
        raise RuntimeError(
            "Could not find the select-all checkbox on the shipment page. "
            f"Screenshot saved to '{screenshot_path}'."
        )

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
            inp_loc = label.locator("input[type='checkbox']").first
            if await inp_loc.count() > 0:
                inp_handle = await inp_loc.element_handle()
                if inp_handle:
                    checked = await page.evaluate("el => el.checked", inp_handle)
                    return bool(checked)
        except Exception:
            pass
        return False

    if await is_now_checked():
        print("Shipment select-all checkbox already checked.")
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
            print(f"Shipment select-all checkbox checked via: {name}")
            return

    screenshot_path = Path("debug_shipment_select_all.png")
    await page.screenshot(path=str(screenshot_path), full_page=True)
    raise RuntimeError(
        "Could not check the shipment select-all checkbox after trying all strategies. "
        f"Screenshot saved to '{screenshot_path}'."
    )


async def scan_order_skus(page: Page) -> None:
    """
    For each row in the current orders table, hover over the order-ID cell to
    trigger the product-info popover, extract the 'Seller SKU:' value, then
    print all SKUs to the console.
    """
    rows = page.locator("table tbody tr")
    count = await rows.count()
    print(f"Found {count} rows. Scanning SKUs...")

    skus: list[list[tuple[str, str]]] = []
    for i in range(count):
        row = rows.nth(i)
        trigger = row.locator("[data-log_click_for='cell_product']").first
        try:
            await trigger.scroll_into_view_if_needed()
            await trigger.click()
        except Exception as e:
            print(f"Row {i}: could not click product cell: {e}")
            skus.append([("(click failed)", "")])
            continue

        # Wait for the product popover
        popover = page.locator("[data-log_module_name='product_edit_popover']").first
        try:
            await popover.wait_for(state="visible", timeout=2_000)
        except Exception:
            print(f"Row {i}: popover did not appear.")
            skus.append([("(no popover)", "")])
            continue

        # Extract all SKU+qty pairs in one JS round-trip instead of per-item awaits.
        raw_items: list[list[str]] = await popover.evaluate("""el => {
            const seen = new Set();
            const out = [];
            el.querySelectorAll("div[data-tid='m4b_space'] > div.core-space-item").forEach(item => {
                const skuEl = item.querySelector("div.line-clamp-2");
                if (!skuEl) return;
                const txt = skuEl.innerText || '';
                if (!txt.includes('Seller SKU:')) return;
                const sku = txt.replace('Seller SKU:', '').trim();
                if (!sku || seen.has(sku)) return;
                seen.add(sku);
                const qtyEl = item.querySelector("[data-tid='m4b_input_number']");
                out.push([sku, qtyEl ? (qtyEl.value || '1') : '1']);
            });
            return out;
        }""")
        order_skus: list[tuple[str, str]] = [(s, q) for s, q in raw_items]
        skus.append(order_skus)

        print(f"  Row {i + 1}: {', '.join(f'{sku} x{qty}' for sku, qty in order_skus)}")

        # Close the product popover by clicking the trigger cell again (toggle),
        # then wait for it to disappear before interacting with the weight cell.
        try:
            await trigger.click()
            await popover.wait_for(state="hidden", timeout=2_000)
        except Exception:
            pass

        # Click the weight edit icon scoped to this row (avoids hitting another row's icon).
        weight_popover = page.locator("[data-log_module_name='package_weight_edit_popover']").first
        edit_icon = row.locator("svg.theme-arco-icon-edit").first

        weight_opened = False
        try:
            await edit_icon.click(force=True)
            await weight_popover.wait_for(state="visible", timeout=800)
            weight_opened = True
        except Exception:
            # one retry with a longer window
            try:
                await edit_icon.click(force=True)
                await weight_popover.wait_for(state="visible", timeout=1_500)
                weight_opened = True
            except Exception:
                pass

        if not weight_opened:
            print(f"  Row {i + 1}: warning — weight popover did not appear; skipping weight set.")
            continue

        # Compute weight from SKU lookup: sum(unit_weight * qty) for each SKU.
        for sku, _ in order_skus:
            if sku not in SKU_WEIGHTS:
                print(f"  Row {i + 1}: warning — no weight entry for SKU '{sku}'")
        total_weight = sum(
            SKU_WEIGHTS.get(sku, 0) * float(qty)
            for sku, qty in order_skus
        )
        if total_weight <= 0:
            print(f"  Row {i + 1}: warning — total weight is 0; skipping weight set.")
            continue
        weight_str = str(round(total_weight, 5)).rstrip("0").rstrip(".")

        # Set the weight using key-event approach (fill()/JS setter don't trigger v-model).
        weight_input = weight_popover.locator("input#packageWeight_input").first
        try:
            await weight_input.wait_for(state="visible", timeout=5_000)
            await weight_input.click()
            await asyncio.sleep(0.2)
            await weight_input.evaluate("el => el.select()")
            await asyncio.sleep(0.1)
            await page.keyboard.type(weight_str, delay=50)
            actual = await weight_input.input_value()
            print(f"  Row {i + 1}: weight set to {actual!r} (computed {weight_str} from {order_skus})")
        except Exception as e:
            print(f"  Row {i + 1}: warning — could not set weight: {e}")
            continue

        # Confirm the value (Enter closes/saves the inline popover).
        await weight_input.press("Enter")
        await asyncio.sleep(0.5)

    print("\n=== SKUs found ===")
    for idx, order_skus in enumerate(skus, 1):
        print(f"  Order {idx:>3}:")
        for sku, qty in order_skus:
            print(f"             {sku}  x{qty}")
    print(f"Total orders: {len(skus)}")


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
    parser.add_argument("--weight", type=float, default=None, dest="weight",
                        help="Package weight in kg to set (e.g. 0.65)")
    parser.add_argument("--mode", default="single-order",
                        choices=["single-order", "mixed-orders", "combine-orders"],
                        help="Order processing mode (default: single-order)")
    parser.add_argument("--account", default="default",
                        help="Account name to use for login (determines which cookies file to load, e.g. 'foo' → cookies_foo.json)")
    args = parser.parse_args()

    async with async_playwright() as playwright:
        browser, context, page = await get_authenticated_context(playwright, args.account)
        print(f"Current URL: {page.url}")

        if args.mode == "combine-orders":
            await combine_orders_mode(page)
            print("Done. Closing browser.")
            await browser.close()
            return
        else:
            await navigate_to_awaiting_shipment(
                page, args.sku, args.order_contents, args.shipping_method, args.combine_split,
                weight=args.weight,
                mode=args.mode,
            )
        order_ids = await get_awaiting_shipment_order_ids(page)
        print("Order IDs:", order_ids)

        input("Press Enter to close the browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
